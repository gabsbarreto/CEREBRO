from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from app import config
from app.models import JobSettings
from app.services import jobs
from app.services.openai_rq import run_openai_rq
from app.services.rq_completion import complete_screening_job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OpenAIInferenceJob:
    job_id: str
    settings: JobSettings
    started_at: float
    prompt_filename: str
    prompt_source_path: str
    system_prompt_file: Path
    user_prompt_file: Path
    output_file: Path
    pdf_path: Path
    openai_input_mode: str = "ocr_text"
    openai_file_id: str = ""


OpenAIRunner = Callable[..., None]
CompletionHandler = Callable[..., None]


class OpenAIInferenceQueue:
    """Bounded background queue for OpenAI inference.

    OpenAI inference is network-bound and does not use the local GPU, so these
    workers may run while the main OCR queue continues using the GPU for the
    next PDF. Local model inference stays in the main queue to avoid competing
    with OCR for GPU memory.
    """

    def __init__(
        self,
        *,
        max_workers: int = config.MAX_OPENAI_CONCURRENT_REQUESTS,
        max_retries: int = config.OPENAI_INFERENCE_MAX_RETRIES,
        retry_base_seconds: float = config.OPENAI_INFERENCE_RETRY_BASE_SECONDS,
        runner: OpenAIRunner = run_openai_rq,
        completion_handler: CompletionHandler = complete_screening_job,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.max_workers = max(1, int(max_workers))
        self.max_retries = max(0, int(max_retries))
        self.retry_base_seconds = max(0.0, float(retry_base_seconds))
        self._runner = runner
        self._completion_handler = completion_handler
        self._sleep = sleep
        self._clock = clock
        self._pending: queue.Queue[OpenAIInferenceJob | None] = queue.Queue()
        self._lock = threading.Lock()
        self._queued: set[str] = set()
        self._running: set[str] = set()
        self._workers = [
            threading.Thread(
                target=self._worker,
                name=f"openai-inference-{index + 1}",
                daemon=True,
            )
            for index in range(self.max_workers)
        ]
        for worker in self._workers:
            worker.start()

    def enqueue(self, inference_job: OpenAIInferenceJob) -> bool:
        with self._lock:
            if inference_job.job_id in self._queued or inference_job.job_id in self._running:
                return False
            self._queued.add(inference_job.job_id)
        jobs.update_status(
            inference_job.job_id,
            status="running",
            stage="openai_queued",
            message="OpenAI inference queued",
            progress=0.72,
            event={"event": "openai_queued", "job_id": inference_job.job_id},
        )
        self._pending.put(inference_job)
        return True

    def active_job_ids(self) -> set[str]:
        with self._lock:
            return set(self._queued) | set(self._running)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "openai_pending_job_ids": list(self._queued),
                "openai_running_job_ids": list(self._running),
                "openai_pending_count": len(self._queued),
                "openai_running_count": len(self._running),
                "max_openai_concurrent_requests": self.max_workers,
            }

    def join(self) -> None:
        self._pending.join()

    def shutdown(self) -> None:
        for _worker in self._workers:
            self._pending.put(None)
        for worker in self._workers:
            worker.join(timeout=5)

    def _worker(self) -> None:
        while True:
            inference_job = self._pending.get()
            if inference_job is None:
                self._pending.task_done()
                return
            with self._lock:
                self._queued.discard(inference_job.job_id)
                self._running.add(inference_job.job_id)
            try:
                self._run_inference_job(inference_job)
            except Exception as exc:
                logger.exception("OpenAI inference job %s failed", inference_job.job_id)
                jobs.update_status(
                    inference_job.job_id,
                    status="failed",
                    stage="error",
                    message=str(exc),
                    progress=1.0,
                    error=str(exc),
                    event={"event": "error", "message": str(exc), "provider": "openai"},
                )
            finally:
                with self._lock:
                    self._running.discard(inference_job.job_id)
                self._pending.task_done()

    def _run_inference_job(self, inference_job: OpenAIInferenceJob) -> None:
        inference_started_at = self._clock()
        jobs.update_status(
            inference_job.job_id,
            status="running",
            stage="openai_running",
            message="OpenAI inference running",
            progress=0.84,
            event={"event": "openai_running", "job_id": inference_job.job_id},
        )

        def handle_event(event: dict[str, Any]) -> None:
            name = str(event.get("event", "openai"))
            if name == "rq_generation_finished":
                message = "OpenAI inference complete"
                progress = 0.96
            elif name == "rq_generation_empty":
                message = "OpenAI returned no final text"
                progress = 0.94
            elif name == "openai_file_upload_started":
                message = "Uploading PDF to OpenAI"
                progress = 0.76
            elif name in {"openai_file_uploaded", "openai_file_reused"}:
                file_id = str(event.get("file_id") or "")
                if file_id:
                    jobs.update_metadata(
                        jobs.job_dir(inference_job.job_id),
                        openai_file_id=file_id,
                        openai_file_uploaded=name == "openai_file_uploaded",
                    )
                message = "OpenAI PDF file ready"
                progress = 0.80
            else:
                message = "OpenAI inference running"
                progress = 0.84
            jobs.update_status(
                inference_job.job_id,
                status="running",
                stage="openai_running",
                message=message,
                progress=progress,
                event=event,
            )

        for attempt in range(self.max_retries + 1):
            try:
                self._runner(
                    job_id=inference_job.job_id,
                    model=inference_job.settings.rq_screening_model,
                    system_prompt_file=inference_job.system_prompt_file,
                    user_prompt_file=inference_job.user_prompt_file,
                    output_file=inference_job.output_file,
                    max_tokens=inference_job.settings.rq_max_tokens,
                    enable_reasoning=inference_job.settings.rq_enable_thinking,
                    reasoning_effort=inference_job.settings.openai_reasoning_effort,
                    api_key=inference_job.settings.openai_api_key,
                    input_file_id=inference_job.openai_file_id
                    if inference_job.openai_input_mode == "pdf_file"
                    else "",
                    input_file_path=inference_job.pdf_path
                    if inference_job.openai_input_mode == "pdf_file" and not inference_job.openai_file_id
                    else None,
                    on_event=handle_event,
                )
                self._completion_handler(
                    job_id=inference_job.job_id,
                    settings=inference_job.settings,
                    started_at=inference_started_at,
                    prompt_filename=inference_job.prompt_filename,
                    prompt_source_path=inference_job.prompt_source_path,
                    system_prompt_file=inference_job.system_prompt_file,
                    user_prompt_file=inference_job.user_prompt_file,
                    output_file=inference_job.output_file,
                    pdf_path=inference_job.pdf_path,
                )
                return
            except Exception as exc:
                if attempt >= self.max_retries or not is_retryable_openai_error(exc):
                    raise
                delay = self.retry_base_seconds * (2**attempt)
                jobs.update_status(
                    inference_job.job_id,
                    status="running",
                    stage="openai_queued",
                    message=f"OpenAI transient error; retrying in {delay:g}s",
                    progress=0.78,
                    event={
                        "event": "openai_retry",
                        "attempt": attempt + 1,
                        "max_retries": self.max_retries,
                        "delay_seconds": delay,
                        "error": str(exc),
                    },
                )
                self._sleep(delay)


def is_retryable_openai_error(exc: Exception) -> bool:
    text = str(exc).lower()
    retry_markers = [
        "rate limit",
        "rate_limit",
        "429",
        "timeout",
        "timed out",
        "temporarily",
        "temporary",
        "unavailable",
        "connection",
        "reset",
        "server error",
        "internal server error",
        " 500",
        " 502",
        " 503",
        " 504",
    ]
    return any(marker in text for marker in retry_markers)


openai_inference_queue = OpenAIInferenceQueue()
