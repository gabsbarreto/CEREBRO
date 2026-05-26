from __future__ import annotations

import os
import signal
import subprocess
import threading


class JobCancelled(RuntimeError):
    pass


_LOCK = threading.Lock()
_PROCESSES: dict[str, subprocess.Popen] = {}
_CANCELLED: set[str] = set()


def register_process(job_id: str | None, process: subprocess.Popen) -> None:
    if not job_id:
        return
    with _LOCK:
        _PROCESSES[job_id] = process


def unregister_process(job_id: str | None, process: subprocess.Popen) -> None:
    if not job_id:
        return
    with _LOCK:
        if _PROCESSES.get(job_id) is process:
            _PROCESSES.pop(job_id, None)


def request_cancel(job_id: str) -> None:
    with _LOCK:
        _CANCELLED.add(job_id)
        process = _PROCESSES.get(job_id)
    if process is not None and process.poll() is None:
        terminate_process(process)


def clear_cancel(job_id: str) -> None:
    with _LOCK:
        _CANCELLED.discard(job_id)


def is_cancelled(job_id: str | None) -> bool:
    if not job_id:
        return False
    with _LOCK:
        return job_id in _CANCELLED


def raise_if_cancelled(job_id: str | None) -> None:
    if is_cancelled(job_id):
        raise JobCancelled("Job was paused and returned to the front of the queue.")


def terminate_process(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except Exception:
        try:
            process.terminate()
        except Exception:
            return

