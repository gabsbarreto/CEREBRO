from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app import config
from app.services import jobs, process_control

logger = logging.getLogger(__name__)


class LocalInferenceWorker:
    """Single persistent local-model worker.

    Qwen/MLX model loading is expensive and memory-heavy. This worker keeps one
    subprocess and one model instance alive across queued jobs. Requests are
    serialized with a lock, while pause/cancel can still terminate the worker
    process for the current job.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._proc: subprocess.Popen[str] | None = None
        self._stderr_lines: deque[str] = deque(maxlen=300)
        self._stderr_thread: threading.Thread | None = None
        self._pid_file = config.DATA_DIR / "local_inference_worker.json"
        self._active_request_id: str | None = None
        self._active_on_event: Callable[[dict[str, Any]], None] | None = None

    def run(
        self,
        *,
        job_id: str | None,
        model: str,
        system_prompt_file: Path,
        user_prompt_file: Path,
        output_file: Path,
        max_tokens: int,
        thinking_budget: int,
        temperature: float,
        top_p: float,
        top_k: int,
        min_p: float,
        presence_penalty: float,
        repetition_penalty: float,
        enable_thinking: bool,
        verbose: bool,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        request_id = uuid.uuid4().hex
        with self._lock:
            proc = self._ensure_process()
            process_control.register_process(job_id, proc)
            output_lines: list[str] = []
            try:
                payload = {
                    "command": "run",
                    "request_id": request_id,
                    "job_id": job_id,
                    "model": model,
                    "system_prompt_file": str(system_prompt_file),
                    "user_prompt_file": str(user_prompt_file),
                    "output_file": str(output_file),
                    "max_tokens": max_tokens,
                    "thinking_budget": thinking_budget,
                    "temperature": temperature,
                    "top_p": top_p,
                    "top_k": top_k,
                    "min_p": min_p,
                    "presence_penalty": presence_penalty,
                    "repetition_penalty": repetition_penalty,
                    "enable_thinking": enable_thinking,
                    "verbose": verbose,
                }
                self._active_request_id = request_id
                self._active_on_event = on_event
                assert proc.stdin is not None
                proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
                proc.stdin.flush()
                self._write_pid_file(job_id=job_id, request_id=request_id)

                while True:
                    assert proc.stdout is not None
                    line = proc.stdout.readline()
                    if line == "":
                        if process_control.is_cancelled(job_id):
                            raise process_control.JobCancelled("RQ screening worker was interrupted by queue pause.")
                        self._clear_dead_process_locked()
                        details = "\n".join(output_lines + list(self._stderr_lines)).strip()
                        raise RuntimeError(
                            "Persistent RQ screening worker exited unexpectedly. "
                            f"Details: {details[-1200:]}"
                        )
                    output_lines.append(line.rstrip("\n"))
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        logger.warning("Ignoring non-JSON local worker output: %s", line.rstrip())
                        continue
                    if str(event.get("request_id") or request_id) != request_id:
                        continue

                    event_name = str(event.get("event") or "")
                    if event_name == "rq_request_complete":
                        return
                    if event_name == "rq_request_failed":
                        raise RuntimeError(str(event.get("error") or "Local RQ screening worker failed."))
                    if on_event is not None:
                        event_for_callback = dict(event)
                        event_for_callback.pop("request_id", None)
                        on_event(event_for_callback)
            finally:
                self._active_request_id = None
                self._active_on_event = None
                process_control.unregister_process(job_id, proc)
                self._write_pid_file(job_id=None, request_id=None)
                if proc.poll() is not None:
                    self._clear_dead_process_locked()
                if process_control.is_cancelled(job_id):
                    raise process_control.JobCancelled("RQ screening worker was interrupted by queue pause.")

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
            if proc is None:
                self._remove_pid_file()
                return
            if proc.poll() is None:
                try:
                    assert proc.stdin is not None
                    proc.stdin.write(json.dumps({"command": "shutdown"}) + "\n")
                    proc.stdin.flush()
                    proc.wait(timeout=5)
                except Exception:
                    process_control.terminate_process(proc)
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
            self._clear_dead_process_locked()

    def terminate_stale_external_worker(self) -> None:
        payload = self._read_pid_file()
        pid = int(payload.get("pid") or 0)
        if pid <= 0:
            return
        with self._lock:
            if self._proc is not None and self._proc.pid == pid:
                return
        if not _pid_exists(pid):
            self._remove_pid_file()
            return
        logger.warning("Terminating stale local inference worker process %s", pid)
        try:
            os.killpg(pid, signal.SIGTERM)
        except Exception:
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
        self._remove_pid_file()

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self.terminate_stale_external_worker()
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        proc = subprocess.Popen(
            [
                sys.executable,
                str(config.BASE_DIR / "scripts" / "rq_llm_persistent_worker.py"),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
            env=env,
        )
        self._proc = proc
        self._stderr_lines.clear()
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            args=(proc,),
            name="local-inference-worker-stderr",
            daemon=True,
        )
        self._stderr_thread.start()
        self._write_pid_file(job_id=None, request_id=None)
        self._wait_until_ready(proc)
        return proc

    def _wait_until_ready(self, proc: subprocess.Popen[str]) -> None:
        assert proc.stdout is not None
        while True:
            line = proc.stdout.readline()
            if line == "":
                self._clear_dead_process_locked()
                details = "\n".join(self._stderr_lines).strip()
                raise RuntimeError(f"Persistent RQ screening worker failed to start. Details: {details[-1200:]}")
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Ignoring non-JSON local worker startup output: %s", line.rstrip())
                continue
            if event.get("event") == "rq_worker_ready":
                return
            if event.get("event") == "rq_request_failed":
                raise RuntimeError(str(event.get("error") or "Persistent RQ screening worker failed to start."))

    def _read_stderr(self, proc: subprocess.Popen[str]) -> None:
        if proc.stderr is None:
            return
        buffer = ""
        last_emit = time.monotonic()
        while True:
            char = proc.stderr.read(1)
            if char == "":
                break
            buffer += char
            if char == "\n" or len(buffer) >= 160 or time.monotonic() - last_emit >= 0.75:
                self._forward_stderr_text(buffer)
                buffer = ""
                last_emit = time.monotonic()
        if buffer:
            self._forward_stderr_text(buffer)

    def _forward_stderr_text(self, text: str) -> None:
        text = text.rstrip("\n")
        if not text:
            return
        self._stderr_lines.append(text)
        logger.debug("local inference worker: %s", text)
        callback = self._active_on_event
        if callback is None:
            return
        try:
            callback({"event": "rq_generation_log", "line": text})
        except Exception:
            logger.debug("Failed to forward local worker stderr text to callback.")

    def _clear_dead_process_locked(self) -> None:
        self._proc = None
        self._stderr_thread = None
        self._remove_pid_file()

    def _write_pid_file(self, *, job_id: str | None, request_id: str | None) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            self._remove_pid_file()
            return
        jobs.write_json(
            self._pid_file,
            {
                "pid": proc.pid,
                "job_id": job_id,
                "request_id": request_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _read_pid_file(self) -> dict[str, Any]:
        try:
            return jobs.read_json(self._pid_file)
        except Exception:
            return {}

    def _remove_pid_file(self) -> None:
        try:
            self._pid_file.unlink()
        except FileNotFoundError:
            pass


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


local_inference_worker = LocalInferenceWorker()
