from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app import config
from app.models import JobSettings
from app.services import jobs, process_control
from app.services.rq_screening_pipeline import run_job

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QueuedJob:
    job_id: str
    settings: JobSettings


class JobQueue:
    def __init__(self) -> None:
        self._pending: deque[QueuedJob] = deque()
        self._queued_or_running: set[str] = set()
        self._current: dict[str, QueuedJob] = {}
        self._settings_overrides: dict[str, JobSettings] = {}
        self._paused = self._load_paused()
        self._condition = threading.Condition()
        self._workers = [
            threading.Thread(
                target=self._run,
                name=f"rq-screening-job-queue-{index + 1}",
                daemon=True,
            )
            for index in range(config.MAX_OCR_WORKERS)
        ]
        for worker in self._workers:
            worker.start()

    def enqueue(self, job_id: str, settings: JobSettings, *, front: bool = False) -> bool:
        with self._condition:
            if job_id in self._queued_or_running:
                return False
            self._queued_or_running.add(job_id)
            queued = QueuedJob(job_id=job_id, settings=settings)
            if front:
                self._pending.appendleft(queued)
            else:
                self._pending.append(queued)
            self._condition.notify_all()
        jobs.update_status(
            job_id,
            status="queued",
            stage="queued",
            message="Queued",
            progress=0.0,
            event={"event": "queued"},
        )
        return True

    def pause(self) -> dict[str, Any]:
        with self._condition:
            self._paused = True
            current = list(self._current.values())
            self._save_paused(True)
            self._condition.notify_all()
        for queued in current:
            process_control.request_cancel(queued.job_id)
        return self.status()

    def resume(self, settings_override: JobSettings | None = None) -> dict[str, Any]:
        if settings_override is not None:
            self.update_pending_settings(settings_override)
            with self._condition:
                for current in self._current.values():
                    self._settings_overrides[current.job_id] = settings_override
        with self._condition:
            self._paused = False
            self._save_paused(False)
            self._condition.notify_all()
        return self.status()

    def update_pending_settings(self, settings: JobSettings) -> list[str]:
        with self._condition:
            pending = list(self._pending)
            self._pending = deque(QueuedJob(queued.job_id, settings) for queued in pending)
            job_ids = [queued.job_id for queued in pending]
        for job_id in job_ids:
            root = jobs.job_dir(job_id)
            self._update_reallocated_metadata(
                root,
                settings,
                previous_status=jobs.read_status(job_id),
                event_name="queue_settings_updated",
            )
        return job_ids

    def clean_queued(self) -> list[dict[str, Any]]:
        with self._condition:
            current_ids = set(self._current)
            pending_ids = [queued.job_id for queued in self._pending]
            self._pending.clear()
            for job_id in pending_ids:
                self._queued_or_running.discard(job_id)
                self._settings_overrides.pop(job_id, None)
            self._condition.notify_all()

        ids_to_remove = set(pending_ids)
        for record in jobs.list_jobs(limit=0):
            job_id = str(record["job_id"])
            status = record.get("status") or {}
            if job_id in current_ids:
                continue
            if status.get("status") == "queued":
                ids_to_remove.add(job_id)

        removed: list[dict[str, Any]] = []
        records_by_id = {str(record["job_id"]): record for record in jobs.list_jobs(limit=0)}
        for job_id in sorted(ids_to_remove):
            record = records_by_id.get(job_id)
            try:
                jobs.delete_job(job_id)
            except FileNotFoundError:
                pass
            if record is not None:
                removed.append(record)
        return removed

    def enqueue_screening_rerun(self, job_id: str, settings: JobSettings) -> dict[str, Any] | None:
        root = jobs.job_dir(job_id)
        if not root.exists():
            return None
        previous_status = jobs.read_status(job_id)
        self._update_reallocated_metadata(
            root,
            settings,
            previous_status=previous_status,
            event_name="screening_rerun",
        )
        jobs.update_metadata(
            root,
            pending_rerun_screening_only=True,
            rerun_reuses_ocr=settings.openai_input_mode != "pdf_file",
            rerun_reuses_openai_file=settings.openai_input_mode == "pdf_file",
            rerun_requested_at=datetime.now(timezone.utc).isoformat(),
        )
        for path in [
            root / "outputs" / "rq_screening_output.md",
            root / "outputs" / "rq_prompt.txt",
            root / "outputs" / "rq_system_prompt.txt",
            root / "outputs" / "rq_user_prompt.txt",
            root / "outputs" / "openai_request.json",
            root / "outputs" / "openai_response.json",
        ]:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        self.enqueue(job_id, settings)
        refreshed = {item["job_id"]: item for item in jobs.list_jobs(limit=0)}
        return refreshed.get(job_id)

    def retry_failed(self) -> dict[str, Any]:
        self.mark_stale_running_jobs_failed()
        restored: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for record in reversed(jobs.list_jobs(limit=0)):
            status = record.get("status") or {}
            if status.get("status") != "failed":
                continue
            root = jobs.job_dir(str(record["job_id"]))
            try:
                settings = jobs.load_original_job_settings(root)
            except Exception:
                message = "Missing original queued settings"
                skipped.append({"job_id": str(record["job_id"]), "filename": str(record.get("filename") or ""), "error": message})
                jobs.update_status(
                    str(record["job_id"]),
                    status="failed",
                    stage="error",
                    message=message,
                    progress=1.0,
                    error=message,
                    event={"event": "retry_failed_skipped", "message": message},
                )
                continue
            self._mark_retry_metadata(root, previous_status=status)
            if self.enqueue(str(record["job_id"]), settings):
                refreshed = jobs.list_jobs(limit=0)
                restored_by_id = {item["job_id"]: item for item in refreshed}
                restored.append(restored_by_id.get(str(record["job_id"]), record))
        return {"jobs": restored, "skipped": skipped}

    def _mark_retry_metadata(self, root, *, previous_status: dict[str, Any]) -> None:
        jobs.update_metadata(
            root,
            retry_failed_at=datetime.now(timezone.utc).isoformat(),
            retry_failed_from_status=previous_status.get("status"),
            retry_failed_from_stage=previous_status.get("stage"),
            completed_at=None,
            duration_seconds=None,
            summary_xlsx_path=None,
            qwen_9b_output_file_exists=False,
            qwen_9b_output_file=None,
        )

    def _update_reallocated_metadata(
        self,
        root,
        settings: JobSettings,
        *,
        previous_status: dict[str, Any],
        event_name: str = "reallocated",
    ) -> None:
        updates = jobs.settings_metadata_updates(settings)
        updates.update(
            {
                f"{event_name}_at": datetime.now(timezone.utc).isoformat(),
                f"{event_name}_from_status": previous_status.get("status"),
                f"{event_name}_from_stage": previous_status.get("stage"),
                "completed_at": None,
                "duration_seconds": None,
                "summary_xlsx_path": None,
                "qwen_9b_output_file_exists": False,
                "qwen_9b_output_file": None,
            }
        )
        jobs.update_metadata(
            root,
            **updates,
        )

    def enqueue_existing_queued_jobs(self) -> int:
        stale = self.mark_stale_running_jobs_failed()
        if stale:
            logger.warning("Handled %s stale running RQ screening jobs", len(stale))
        restored = 0
        for record in reversed(jobs.list_jobs(limit=0)):
            status = record.get("status") or {}
            if status.get("status") != "queued":
                continue
            root = jobs.job_dir(str(record["job_id"]))
            if self.enqueue(str(record["job_id"]), jobs.load_job_settings(root)):
                restored += 1
        if restored:
            logger.info("Restored %s queued RQ screening jobs from disk", restored)
        return restored

    def mark_stale_running_jobs_failed(self) -> list[dict[str, Any]]:
        active_job_ids = self.active_job_ids()
        marked: list[dict[str, Any]] = []
        for record in jobs.list_jobs(limit=0):
            job_id = str(record["job_id"])
            root = jobs.job_dir(job_id)
            status = record.get("status") or {}
            if status.get("status") != "running" or job_id in active_job_ids:
                continue

            previous_stage = str(status.get("stage") or "unknown")
            previous_message = str(status.get("message") or "No last message recorded.")
            if _can_requeue_stale_running_job(root):
                message = (
                    "Job was interrupted while the app was restarting and has been returned to the queue. "
                    f"Last recorded stage: {previous_stage}."
                )
                jobs.update_status(
                    job_id,
                    status="queued",
                    stage="queued",
                    message=message,
                    progress=0.0,
                    error=None,
                    event={
                        "event": "stale_job_requeued",
                        "previous_stage": previous_stage,
                        "previous_message": previous_message,
                    },
                )
                refreshed = {item["job_id"]: item for item in jobs.list_jobs(limit=0)}
                marked.append(refreshed.get(job_id, record))
                continue

            message = (
                "Job was left incomplete and is not active in the queue. "
                f"Last recorded stage: {previous_stage}. Last message: {previous_message}"
            )
            jobs.update_status(
                job_id,
                status="failed",
                stage="error",
                message=message,
                progress=1.0,
                error=message,
                event={
                    "event": "stale_job_marked_failed",
                    "previous_stage": previous_stage,
                    "previous_message": previous_message,
                },
            )
            refreshed = {item["job_id"]: item for item in jobs.list_jobs(limit=0)}
            marked.append(refreshed.get(job_id, record))
        return marked

    def active_job_ids(self) -> set[str]:
        with self._condition:
            active = set(self._queued_or_running)
            active.update(self._current)
            active.update(queued.job_id for queued in self._pending)
        active.update(_openai_active_job_ids())
        return active

    def status(self) -> dict[str, Any]:
        with self._condition:
            current_job_ids = list(self._current)
            payload = {
                "paused": self._paused,
                "current_job_id": current_job_ids[0] if current_job_ids else None,
                "current_job_ids": current_job_ids,
                "pending_job_ids": [queued.job_id for queued in self._pending],
                "pending_count": len(self._pending),
                "max_ocr_workers": len(self._workers),
            }
        payload.update(_openai_queue_status())
        return payload

    def _run(self) -> None:
        while True:
            queued = self._next_job()
            process_control.clear_cancel(queued.job_id)
            try:
                logger.info("Dequeued RQ screening job %s", queued.job_id)
                run_job(queued.job_id, queued.settings, defer_openai=True)
            except process_control.JobCancelled:
                logger.info("Paused job %s; returning it to the front of the queue", queued.job_id)
                with self._condition:
                    replacement_settings = self._settings_overrides.pop(queued.job_id, queued.settings)
                    self._current.pop(queued.job_id, None)
                    self._pending.appendleft(QueuedJob(queued.job_id, replacement_settings))
                    self._condition.notify_all()
                continue
            except Exception:
                logger.exception("Queued RQ screening job %s crashed outside pipeline handling", queued.job_id)
                jobs.update_status(
                    queued.job_id,
                    status="failed",
                    stage="error",
                    message="Queued job crashed unexpectedly.",
                    progress=1.0,
                    error="Queued job crashed unexpectedly.",
                    event={"event": "error", "message": "Queued job crashed unexpectedly."},
                )
            finally:
                with self._condition:
                    if self._current.get(queued.job_id) == queued:
                        self._current.pop(queued.job_id, None)
                    if queued.job_id not in {item.job_id for item in self._pending}:
                        self._queued_or_running.discard(queued.job_id)
                    self._condition.notify_all()

    def _next_job(self) -> QueuedJob:
        with self._condition:
            while self._paused or not self._pending:
                self._condition.wait()
            queued = self._pending.popleft()
            self._current[queued.job_id] = queued
            return queued

    def _load_paused(self) -> bool:
        path = config.DATA_DIR / "queue_state.json"
        try:
            payload = jobs.read_json(path)
        except Exception:
            return False
        return bool(payload.get("paused"))

    def _save_paused(self, paused: bool) -> None:
        jobs.write_json(
            config.DATA_DIR / "queue_state.json",
            {"paused": paused, "updated_at": datetime.now(timezone.utc).isoformat()},
        )


def _openai_active_job_ids() -> set[str]:
    try:
        from app.services.openai_inference_queue import openai_inference_queue

        return openai_inference_queue.active_job_ids()
    except Exception:
        return set()


def _openai_queue_status() -> dict[str, Any]:
    try:
        from app.services.openai_inference_queue import openai_inference_queue

        return openai_inference_queue.status()
    except Exception:
        return {
            "openai_pending_job_ids": [],
            "openai_running_job_ids": [],
            "openai_pending_count": 0,
            "openai_running_count": 0,
            "max_openai_concurrent_requests": config.MAX_OPENAI_CONCURRENT_REQUESTS,
        }


def _can_requeue_stale_running_job(root) -> bool:
    try:
        metadata = jobs.read_metadata(root)
    except Exception:
        return False
    if metadata.get("openai_input_mode") == "pdf_file":
        return (root / "input" / "uploaded.pdf").exists()
    if not (metadata.get("pending_rerun_screening_only") or metadata.get("ocr_complete")):
        return False
    merged_file = root / "outputs" / "merged_full_text.txt"
    try:
        return merged_file.exists() and len(merged_file.read_text(encoding="utf-8").strip()) >= 20
    except OSError:
        return False
