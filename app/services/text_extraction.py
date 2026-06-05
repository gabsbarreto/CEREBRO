from __future__ import annotations

import csv
import json
import logging
import shutil
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from openpyxl import Workbook, load_workbook

from app import config
from app.models import JobSettings
from app.services import jobs, projects
from app.services.openai_rq import run_openai_rq
from app.services.rq_llm import run_rq_llm
from app.services.rq_prompt import build_prompt_transcript, read_prompt_file

logger = logging.getLogger(__name__)

TEXT_EXTRACTION_TYPE = "text"
SOURCE_FILES_DIRNAME = "source_files"
ROWS_JSONL_FILENAME = "rows.jsonl"
SOURCE_MANIFEST_FILENAME = "source.json"
TEXT_EXPORT_SUFFIX = "text_extraction_export.xlsx"
TEXT_JOB_OUTPUT = "output.md"
VISIBLE_RESULT_PREVIEW_CHARS = 220
CSV_FIELD_LIMIT = 1024 * 1024 * 32

try:
    csv.field_size_limit(CSV_FIELD_LIMIT)
except OverflowError:
    pass


@dataclass(frozen=True)
class TextQueuedJob:
    project_id: str
    job_id: str


class TextJobQueue:
    def __init__(self) -> None:
        self._pending: deque[TextQueuedJob] = deque()
        self._queued_or_running: set[str] = set()
        self._current: dict[str, TextQueuedJob] = {}
        self._paused = False
        self._condition = threading.Condition()
        worker_count = max(1, min(config.MAX_OPENAI_CONCURRENT_REQUESTS, 4))
        self._workers = [
            threading.Thread(
                target=self._run,
                name=f"text-extraction-job-queue-{index + 1}",
                daemon=True,
            )
            for index in range(worker_count)
        ]
        for worker in self._workers:
            worker.start()

    def enqueue(self, project_id: str, job_id: str, *, front: bool = False) -> bool:
        key = queue_key(project_id, job_id)
        with self._condition:
            if key in self._queued_or_running:
                return False
            self._queued_or_running.add(key)
            queued = TextQueuedJob(project_id=project_id, job_id=job_id)
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
            error=None,
            event={"event": "queued"},
            project_id=project_id,
        )
        return True

    def active_job_ids(self, *, project_id: str | None = None) -> set[str]:
        with self._condition:
            return {
                job_id_from_key(key)
                for key in self._queued_or_running
                if project_id is None or key.startswith(f"{project_id}:")
            }

    def pause(self, *, project_id: str | None = None) -> dict[str, Any]:
        # Text pause/resume stops future row starts. A row already inside a model
        # call is allowed to finish so pause does not turn active work into a
        # failed retry.
        with self._condition:
            self._paused = True
            self._condition.notify_all()
        return self.status(project_id=project_id)

    def resume(self, *, project_id: str | None = None) -> dict[str, Any]:
        with self._condition:
            self._paused = False
            self._condition.notify_all()
        return self.status(project_id=project_id)

    def status(self, *, project_id: str | None = None) -> dict[str, Any]:
        with self._condition:
            current = [
                queued.job_id
                for queued in self._current.values()
                if project_id is None or queued.project_id == project_id
            ]
            pending = [
                queued.job_id
                for queued in self._pending
                if project_id is None or queued.project_id == project_id
            ]
        return {
            "paused": self._paused,
            "current_job_ids": current,
            "pending_job_ids": pending,
            "pending_count": len(pending),
            "running_count": len(current),
            "max_text_workers": len(self._workers),
        }

    def enqueue_existing_queued_jobs(self) -> int:
        self.mark_stale_running_jobs_queued()
        restored = 0
        for project_id in known_text_project_ids():
            records = sorted(
                text_job_records(project_id),
                key=lambda item: text_row_order(item.get("metadata") or {}),
            )
            for record in records:
                status = record.get("status") or {}
                if normalize_status_key(status.get("status")) != "queued":
                    continue
                if self.enqueue(project_id, str(record["job_id"])):
                    restored += 1
        if restored:
            logger.info("Restored %s queued text extraction jobs from disk", restored)
        return restored

    def mark_stale_running_jobs_queued(self, *, project_id: str | None = None) -> list[dict[str, Any]]:
        active_ids = self.active_job_ids(project_id=project_id)
        marked: list[dict[str, Any]] = []
        project_ids = [project_id] if project_id else known_text_project_ids()
        for active_project_id in project_ids:
            for record in text_job_records(active_project_id):
                status = record.get("status") or {}
                job_id = str(record["job_id"])
                if normalize_status_key(status.get("status")) != "running" or job_id in active_ids:
                    continue
                message = "Text extraction was interrupted while the app was restarting and has been returned to the queue."
                jobs.update_status(
                    job_id,
                    status="queued",
                    stage="queued",
                    message=message,
                    progress=0.0,
                    error=None,
                    event={"event": "stale_text_job_requeued"},
                    project_id=active_project_id,
                )
                marked.append(record)
        return marked

    def _run(self) -> None:
        while True:
            queued = self._next_job()
            key = queue_key(queued.project_id, queued.job_id)
            try:
                logger.info("Dequeued text extraction job %s", queued.job_id)
                run_text_job(queued.project_id, queued.job_id)
            except Exception:
                logger.exception("Queued text extraction job %s crashed outside job handling", queued.job_id)
                jobs.update_status(
                    queued.job_id,
                    status="failed",
                    stage="error",
                    message="Text extraction job crashed unexpectedly.",
                    progress=1.0,
                    error="Text extraction job crashed unexpectedly.",
                    event={"event": "error", "message": "Text extraction job crashed unexpectedly."},
                    project_id=queued.project_id,
                )
            finally:
                with self._condition:
                    if self._current.get(key) == queued:
                        self._current.pop(key, None)
                    if key not in {queue_key(item.project_id, item.job_id) for item in self._pending}:
                        self._queued_or_running.discard(key)
                    self._condition.notify_all()

    def _next_job(self) -> TextQueuedJob:
        with self._condition:
            while self._paused or not self._pending:
                self._condition.wait()
            queued = self._pending.popleft()
            self._current[queue_key(queued.project_id, queued.job_id)] = queued
            return queued


text_job_queue = TextJobQueue()


def create_text_jobs_from_upload(
    *,
    project_id: str,
    upload_file: Any,
    settings: JobSettings,
    column_mappings: list[dict[str, str]],
    study_id_column: str = "",
) -> dict[str, Any]:
    require_text_project(project_id)
    original_filename = Path(str(upload_file.filename or "uploaded_spreadsheet")).name
    suffix = Path(original_filename).suffix.lower()
    if suffix not in {".csv", ".xlsx"}:
        if suffix == ".xls":
            raise ValueError("Legacy .xls files are not supported. Save the spreadsheet as .xlsx or CSV and upload again.")
        raise ValueError("Upload a .csv or .xlsx spreadsheet.")

    source_id = uuid.uuid4().hex
    source_dir = source_dir_for(project_id, source_id)
    source_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_dir / safe_source_filename(original_filename)
    jobs.save_upload(upload_file.file, source_file)

    columns = read_spreadsheet_columns(source_file)
    mappings = normalize_column_mappings(column_mappings, columns)
    clean_study_id_column = normalize_optional_column(study_id_column, columns)
    system_prompt, prompt_filename, prompt_source_path = resolve_system_prompt(settings)
    source_manifest = {
        "source_id": source_id,
        "source_filename": original_filename,
        "stored_source_file": str(source_file),
        "created_at": utc_now(),
        "columns": columns,
        "column_mappings": mappings,
        "study_id_column": clean_study_id_column,
        "row_count": 0,
    }
    jobs.write_json(source_dir / SOURCE_MANIFEST_FILENAME, source_manifest)

    created_jobs: list[dict[str, Any]] = []
    start_order = next_project_row_order(project_id)
    rows_path = source_dir / ROWS_JSONL_FILENAME
    with rows_path.open("w", encoding="utf-8") as rows_handle:
        for source_row_index, row in enumerate(iter_spreadsheet_rows(source_file, columns)):
            if is_blank_row(row):
                continue
            row_display_number = source_row_index + 1
            row_order = start_order + len(created_jobs)
            selected_fields = selected_fields_for_row(row, mappings)
            user_prompt = build_user_prompt(selected_fields)
            record_id = record_id_for_row(row, clean_study_id_column, row_display_number)
            input_preview = input_preview_for_fields(selected_fields, row_display_number)
            row_payload = {
                "source_id": source_id,
                "source_filename": original_filename,
                "source_row_index": source_row_index,
                "row_display_number": row_display_number,
                "spreadsheet_row_number": source_row_index + 2,
                "record_id": record_id,
                "study_id_column": clean_study_id_column,
                "selected_fields": selected_fields,
                "row": row,
            }
            rows_handle.write(json.dumps(row_payload, ensure_ascii=False) + "\n")
            job_id = jobs.new_job_id()
            root = jobs.create_job(job_id, record_id, settings, project_id=project_id)
            write_text_job_files(
                root=root,
                row_payload=row_payload,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            jobs.update_metadata(
                root,
                extraction_type=TEXT_EXTRACTION_TYPE,
                project_id=project_id,
                source_id=source_id,
                source_filename=original_filename,
                stored_source_file=str(source_file),
                original_filename=record_id,
                record_id=record_id,
                study_id_column=clean_study_id_column,
                source_row_index=source_row_index,
                row_display_number=row_display_number,
                spreadsheet_row_number=source_row_index + 2,
                project_row_order=row_order,
                input_preview=input_preview,
                selected_input_fields=mappings,
                rq_prompt_source_path=prompt_source_path,
                rq_system_prompt_file=str(root / "system_prompt.txt"),
                rq_user_prompt_file=str(root / "user_prompt.txt"),
                **jobs.settings_metadata_updates(settings, rq_prompt_filename=prompt_filename),
            )
            text_job_queue.enqueue(project_id, job_id)
            created_jobs.append(
                {
                    "job_id": job_id,
                    "record_id": record_id,
                    "row_display_number": row_display_number,
                    "project_row_order": row_order,
                }
            )

    source_manifest["row_count"] = len(created_jobs)
    source_manifest["rows_jsonl"] = str(rows_path)
    jobs.write_json(source_dir / SOURCE_MANIFEST_FILENAME, source_manifest)
    return {
        "source": source_manifest,
        "jobs": created_jobs,
        "count": len(created_jobs),
        **text_job_queue.status(project_id=project_id),
    }


def run_text_job(project_id: str, job_id: str) -> None:
    root = jobs.job_dir(job_id, project_id)
    started = time.time()
    try:
        metadata = jobs.read_metadata(root)
        if metadata.get("extraction_type") != TEXT_EXTRACTION_TYPE:
            raise RuntimeError("Job is not a text extraction row job.")
        settings = jobs.load_job_settings(root)
        jobs.update_metadata(
            root,
            started_at=utc_now(),
            completed_at=None,
            duration_seconds=None,
            error_message=None,
        )
        jobs.update_status(
            job_id,
            status="running",
            stage="prompt",
            message="Preparing row prompt",
            progress=0.12,
            error=None,
            event={"event": "stage", "stage": "prompt"},
            project_id=project_id,
        )
        system_prompt_file = root / "system_prompt.txt"
        user_prompt_file = root / "user_prompt.txt"
        output_file = root / TEXT_JOB_OUTPUT
        if not system_prompt_file.exists() or not user_prompt_file.exists():
            raise RuntimeError("Stored row prompt files are missing.")

        if settings.rq_provider == "openai":
            jobs.update_status(
                job_id,
                status="running",
                stage="openai_running",
                message="OpenAI inference running",
                progress=0.36,
                event={"event": "openai_running"},
                project_id=project_id,
            )
            run_openai_rq(
                job_id=job_id,
                model=settings.rq_screening_model,
                system_prompt_file=system_prompt_file,
                user_prompt_file=user_prompt_file,
                output_file=output_file,
                max_tokens=settings.rq_max_tokens,
                enable_reasoning=settings.rq_enable_thinking,
                reasoning_effort=settings.openai_reasoning_effort,
                api_key=settings.openai_api_key,
                on_event=lambda event: handle_text_llm_event(job_id, event, provider="openai", project_id=project_id),
            )
        else:
            jobs.update_status(
                job_id,
                status="running",
                stage="rq_model",
                message="Loading extraction model",
                progress=0.28,
                event={"event": "stage", "stage": "rq_model"},
                project_id=project_id,
            )
            run_rq_llm(
                job_id=job_id,
                model=settings.rq_screening_model,
                system_prompt_file=system_prompt_file,
                user_prompt_file=user_prompt_file,
                output_file=output_file,
                max_tokens=settings.rq_max_tokens,
                thinking_budget=settings.rq_thinking_budget,
                temperature=settings.rq_temperature,
                top_p=settings.rq_top_p,
                top_k=settings.rq_top_k,
                min_p=settings.rq_min_p,
                presence_penalty=settings.rq_presence_penalty,
                repetition_penalty=settings.rq_repetition_penalty,
                enable_thinking=settings.rq_enable_thinking,
                verbose=settings.rq_local_inference_verbose,
                on_event=lambda event: handle_text_llm_event(job_id, event, provider="local", project_id=project_id),
            )

        completed_at = utc_now()
        duration_seconds = round(time.time() - started, 2)
        copy_output_for_compatibility(root)
        jobs.update_metadata(
            root,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            error_message=None,
            text_output_file=str(output_file),
            **jobs.settings_metadata_updates(settings, include_settings=False),
        )
        jobs.update_status(
            job_id,
            status="complete",
            stage="complete",
            message="Text extraction complete",
            progress=1.0,
            error=None,
            event={"event": "complete"},
            project_id=project_id,
        )
    except Exception as exc:
        logger.exception("Text extraction job %s failed", job_id)
        jobs.update_metadata(root, error_message=str(exc))
        jobs.update_status(
            job_id,
            status="failed",
            stage="error",
            message=str(exc),
            progress=1.0,
            error=str(exc),
            event={"event": "error", "message": str(exc)},
            project_id=project_id,
        )


def handle_text_llm_event(job_id: str, event: dict[str, Any], *, provider: str, project_id: str) -> None:
    name = str(event.get("event") or "")
    if name == "rq_model_loading":
        message = "Loading extraction model" if provider == "local" else "Starting OpenAI inference"
        progress = 0.36
    elif name == "rq_model_loaded":
        message = "Extraction model loaded" if provider == "local" else "OpenAI client ready"
        progress = 0.44
    elif name == "rq_generation_started":
        message = "Running row extraction" if provider == "local" else "OpenAI row extraction running"
        progress = 0.56
    elif name == "rq_generation_finished":
        message = "Row extraction complete"
        progress = 0.94
    elif name == "rq_generation_empty":
        message = "Model returned no final text"
        progress = 0.92
    elif name == "rq_generation_log":
        message = str(event.get("line") or "Model generating")
        progress = 0.72
    else:
        message = "Running row extraction"
        progress = 0.72
    jobs.update_status(
        job_id,
        status="running",
        stage="rq_screening" if provider == "local" else "openai_running",
        message=message,
        progress=progress,
        event=event,
        project_id=project_id,
    )


def list_text_jobs(
    *,
    project_id: str,
    offset: int = 0,
    limit: int = 100,
    status: str = "all",
    search: str = "",
) -> dict[str, Any]:
    require_text_project(project_id)
    text_job_queue.mark_stale_running_jobs_queued(project_id=project_id)
    normalized_status = normalize_status_key(status)
    query = str(search or "").strip().lower()
    records = sorted(
        text_job_records(project_id),
        key=lambda item: text_row_order(item.get("metadata") or {}),
    )
    filtered: list[dict[str, Any]] = []
    for record in records:
        status_payload = record.get("status") or {}
        status_key = normalize_status_key(status_payload.get("status"))
        if normalized_status != "all" and status_key != normalized_status:
            continue
        if query and query not in text_search_haystack(record):
            continue
        filtered.append(record)

    safe_offset = max(0, int(offset or 0))
    safe_limit = max(1, min(500, int(limit or 100)))
    window = filtered[safe_offset : safe_offset + safe_limit]
    return {
        "items": [serialize_text_job(record, project_id=project_id) for record in window],
        "total": len(filtered),
        "offset": safe_offset,
        "limit": safe_limit,
    }


def text_job_counts(project_id: str) -> dict[str, int]:
    require_text_project(project_id)
    text_job_queue.mark_stale_running_jobs_queued(project_id=project_id)
    counts = {"total": 0, "queued": 0, "running": 0, "completed": 0, "failed": 0}
    for record in text_job_records(project_id):
        counts["total"] += 1
        key = normalize_status_key((record.get("status") or {}).get("status"))
        if key in counts and key != "total":
            counts[key] += 1
    return counts


def retry_text_job(project_id: str, job_id: str) -> dict[str, Any]:
    require_text_project(project_id)
    root = jobs.job_dir(job_id, project_id)
    if not root.exists():
        raise FileNotFoundError("Text row job not found.")
    metadata = jobs.read_metadata(root)
    if metadata.get("extraction_type") != TEXT_EXTRACTION_TYPE:
        raise ValueError("Job is not a text extraction row job.")
    status = jobs.read_status(job_id, project_id=project_id)
    if normalize_status_key(status.get("status")) == "running" or job_id in text_job_queue.active_job_ids(project_id=project_id):
        raise ValueError("Row is already queued or running.")
    if normalize_status_key(status.get("status")) != "failed":
        raise ValueError("Only failed rows can be retried.")
    mark_text_job_for_retry(root, previous_status=status)
    text_job_queue.enqueue(project_id, job_id, front=True)
    return serialize_text_job(text_job_record(project_id, job_id), project_id=project_id)


def retry_failed_text_jobs(project_id: str) -> dict[str, Any]:
    require_text_project(project_id)
    requeued: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    records = sorted(
        text_job_records(project_id),
        key=lambda item: text_row_order(item.get("metadata") or {}),
    )
    for record in records:
        status = record.get("status") or {}
        if normalize_status_key(status.get("status")) != "failed":
            continue
        job_id = str(record["job_id"])
        try:
            root = jobs.job_dir(job_id, project_id)
            jobs.load_original_job_settings(root)
            mark_text_job_for_retry(root, previous_status=status)
            if text_job_queue.enqueue(project_id, job_id):
                requeued.append(serialize_text_job(text_job_record(project_id, job_id), project_id=project_id))
        except Exception as exc:
            skipped.append({"job_id": job_id, "error": str(exc)})
    return {"requeued": len(requeued), "jobs": requeued, "skipped": skipped, **text_job_queue.status(project_id=project_id)}


def read_text_job_output(project_id: str, job_id: str) -> dict[str, Any]:
    require_text_project(project_id)
    root = jobs.job_dir(job_id, project_id)
    if not root.exists():
        raise FileNotFoundError("Text row job not found.")
    metadata = jobs.read_metadata(root)
    if metadata.get("extraction_type") != TEXT_EXTRACTION_TYPE:
        raise ValueError("Job is not a text extraction row job.")
    return {
        "status": jobs.read_status(job_id, project_id=project_id),
        "metadata": metadata,
        "row_input": read_json_if_exists(root / "row_input.json"),
        "user_prompt": read_text_if_exists(root / "user_prompt.txt"),
        "system_prompt": read_text_if_exists(root / "system_prompt.txt"),
        "output": read_text_if_exists(root / TEXT_JOB_OUTPUT),
        "job_dir": str(root),
    }


def export_text_results(project_id: str) -> Path:
    project = require_text_project(project_id)
    records = sorted(
        text_job_records(project_id),
        key=lambda item: text_row_order(item.get("metadata") or {}),
    )
    original_columns = export_columns_for_records(project_id, records)
    cerebro_columns = [
        "cerebro_extracted_at",
        "cerebro_processing_time_seconds",
        "cerebro_model_used",
        "cerebro_prompt_used",
        "cerebro_status",
        "cerebro_error",
        "cerebro_output",
    ]
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Text Extraction"
    worksheet.append(original_columns + cerebro_columns)
    source_rows = load_all_source_rows(project_id)
    for record in records:
        metadata = record.get("metadata") or {}
        source_id = str(metadata.get("source_id") or "")
        row_index = int(metadata.get("source_row_index") or 0)
        original_row = source_rows.get(source_id, {}).get(row_index, {})
        status = record.get("status") or {}
        status_key = normalize_status_key(status.get("status"))
        root = jobs.job_dir(str(record["job_id"]), project_id)
        output = read_text_if_exists(root / TEXT_JOB_OUTPUT) if status_key == "completed" else ""
        worksheet.append(
            [original_row.get(column, "") for column in original_columns]
            + [
                str(metadata.get("completed_at") or ""),
                metadata.get("duration_seconds"),
                str(metadata.get("rq_screening_model") or ""),
                str(metadata.get("rq_prompt_filename") or ""),
                status_label(status_key),
                str(status.get("error") or metadata.get("error_message") or ""),
                output,
            ]
        )
    for column in worksheet.columns:
        letter = column[0].column_letter
        worksheet.column_dimensions[letter].width = min(max(len(str(column[0].value or "")) + 4, 14), 60)
    path = projects.project_root(project_id) / f"cerebro_{projects.sanitize_slug(str(project.get('name') or project_id))}_{TEXT_EXPORT_SUFFIX}"
    workbook.save(path)
    return path


def require_text_project(project_id: str) -> dict[str, Any]:
    project = projects.get_project(project_id)
    if projects.normalize_extraction_type(project.get("extraction_type")) != TEXT_EXTRACTION_TYPE:
        raise ValueError("Project is not a text extraction project.")
    return project


def known_text_project_ids() -> list[str]:
    return [
        str(project["project_id"])
        for project in projects.list_projects()
        if projects.normalize_extraction_type(project.get("extraction_type")) == TEXT_EXTRACTION_TYPE
    ]


def source_dir_for(project_id: str, source_id: str) -> Path:
    return projects.project_root(project_id) / SOURCE_FILES_DIRNAME / source_id


def safe_source_filename(filename: str) -> str:
    stem = projects.sanitize_slug(Path(filename).stem)
    suffix = Path(filename).suffix.lower()
    return f"{stem}{suffix or '.csv'}"


def read_spreadsheet_columns(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                raise ValueError("Spreadsheet is empty.")
            return normalize_columns(header)
    if suffix == ".xlsx":
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            worksheet = workbook.active
            header = next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
            if header is None:
                raise ValueError("Spreadsheet is empty.")
            return normalize_columns([stringify_cell(value) for value in header])
        finally:
            workbook.close()
    raise ValueError("Upload a .csv or .xlsx spreadsheet.")


def iter_spreadsheet_rows(path: Path, columns: list[str]) -> Iterable[dict[str, str]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            for raw_values in reader:
                yield {column: stringify_cell(raw_values[index] if index < len(raw_values) else "") for index, column in enumerate(columns)}
        return
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook.active
        for values in worksheet.iter_rows(min_row=2, values_only=True):
            row_values = [stringify_cell(value) for value in values or []]
            row = {column: row_values[index] if index < len(row_values) else "" for index, column in enumerate(columns)}
            yield row
    finally:
        workbook.close()


def normalize_columns(header: list[Any]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(header, start=1):
        column = stringify_cell(value).strip() or f"Column {index}"
        if column in seen:
            raise ValueError(f"Spreadsheet has a duplicate column name: {column}")
        columns.append(column)
        seen.add(column)
    if not columns:
        raise ValueError("Spreadsheet must include a header row.")
    return columns


def normalize_column_mappings(raw_mappings: list[dict[str, str]], columns: list[str]) -> list[dict[str, str]]:
    if not raw_mappings:
        raise ValueError("Add at least one column mapping.")
    available = set(columns)
    normalized: list[dict[str, str]] = []
    for index, mapping in enumerate(raw_mappings, start=1):
        column_name = str(mapping.get("column_name") or mapping.get("column") or "").strip()
        prompt_label = str(mapping.get("prompt_label") or mapping.get("label") or "").strip()
        if not column_name:
            raise ValueError(f"Column mapping {index} is missing a column name.")
        if not prompt_label:
            raise ValueError(f"Column mapping {index} is missing a prompt label.")
        if column_name not in available:
            raise ValueError(f"Spreadsheet column not found: {column_name}")
        normalized.append({"column_name": column_name, "prompt_label": prompt_label})
    return normalized


def normalize_optional_column(column_name: str, columns: list[str]) -> str:
    cleaned = str(column_name or "").strip()
    if not cleaned:
        return ""
    if cleaned not in set(columns):
        raise ValueError(f"Study ID column not found: {cleaned}")
    return cleaned


def selected_fields_for_row(row: dict[str, str], mappings: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        {
            "column_name": mapping["column_name"],
            "prompt_label": mapping["prompt_label"],
            "value": stringify_cell(row.get(mapping["column_name"], "")),
        }
        for mapping in mappings
    ]


def build_user_prompt(selected_fields: list[dict[str, str]]) -> str:
    return "\n\n".join(f"{field['prompt_label']}: {field.get('value', '')}" for field in selected_fields)


def input_preview_for_fields(selected_fields: list[dict[str, str]], row_display_number: int) -> str:
    for field in selected_fields:
        value = stringify_cell(field.get("value", "")).strip()
        if value:
            return truncate(value, 180)
    return f"Row {row_display_number}"


def record_id_for_row(row: dict[str, str], study_id_column: str, row_display_number: int) -> str:
    if study_id_column:
        value = stringify_cell(row.get(study_id_column, "")).strip()
        if value:
            return value
    return f"Row {row_display_number}"


def resolve_system_prompt(settings: JobSettings) -> tuple[str, str, str]:
    if settings.rq_system_prompt.strip():
        return settings.rq_system_prompt.strip(), settings.rq_prompt_filename, ""
    prompt_record = read_prompt_file(settings.rq_prompt_filename)
    return prompt_record["system_prompt"].strip(), prompt_record["filename"], prompt_record["path"]


def write_text_job_files(root: Path, row_payload: dict[str, Any], system_prompt: str, user_prompt: str) -> None:
    jobs.write_json(root / "row_input.json", row_payload)
    (root / "system_prompt.txt").write_text(system_prompt + "\n", encoding="utf-8")
    (root / "user_prompt.txt").write_text(user_prompt + "\n", encoding="utf-8")
    (root / "outputs" / "rq_system_prompt.txt").write_text(system_prompt + "\n", encoding="utf-8")
    (root / "outputs" / "rq_user_prompt.txt").write_text(user_prompt + "\n", encoding="utf-8")
    (root / "outputs" / "rq_prompt.txt").write_text(build_prompt_transcript(system_prompt, user_prompt), encoding="utf-8")


def copy_output_for_compatibility(root: Path) -> None:
    output = root / TEXT_JOB_OUTPUT
    if not output.exists():
        return
    compatibility_output = root / "outputs" / "rq_screening_output.md"
    compatibility_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(output, compatibility_output)


def mark_text_job_for_retry(root: Path, *, previous_status: dict[str, Any]) -> None:
    for path in [root / TEXT_JOB_OUTPUT, root / "outputs" / "rq_screening_output.md"]:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    jobs.update_metadata(
        root,
        retry_failed_at=utc_now(),
        retry_failed_from_status=previous_status.get("status"),
        retry_failed_from_stage=previous_status.get("stage"),
        completed_at=None,
        duration_seconds=None,
        error_message=None,
    )


def text_job_records(project_id: str) -> list[dict[str, Any]]:
    return [
        record
        for record in jobs.list_jobs(limit=0, project_id=project_id)
        if (record.get("metadata") or {}).get("extraction_type") == TEXT_EXTRACTION_TYPE
    ]


def text_job_record(project_id: str, job_id: str) -> dict[str, Any]:
    for record in text_job_records(project_id):
        if str(record["job_id"]) == job_id:
            return record
    raise FileNotFoundError("Text row job not found.")


def serialize_text_job(record: dict[str, Any], *, project_id: str) -> dict[str, Any]:
    metadata = record.get("metadata") or {}
    status = record.get("status") or {}
    status_key = normalize_status_key(status.get("status"))
    root = jobs.job_dir(str(record["job_id"]), project_id)
    output = read_text_if_exists(root / TEXT_JOB_OUTPUT) if status_key == "completed" else ""
    return {
        "job_id": str(record["job_id"]),
        "project_id": project_id,
        "row": int(metadata.get("row_display_number") or 0),
        "row_order": text_row_order(metadata),
        "status": status_key,
        "status_label": status_label(status_key),
        "stage": str(status.get("stage") or ""),
        "message": str(status.get("message") or ""),
        "error": str(status.get("error") or metadata.get("error_message") or ""),
        "record_id": str(metadata.get("record_id") or f"Row {metadata.get('row_display_number') or ''}"),
        "input_preview": str(metadata.get("input_preview") or ""),
        "model": str(metadata.get("rq_screening_model") or ""),
        "prompt": str(metadata.get("rq_prompt_filename") or ""),
        "started_at": str(metadata.get("started_at") or ""),
        "completed_at": str(metadata.get("completed_at") or ""),
        "duration_seconds": metadata.get("duration_seconds"),
        "result_preview": truncate(output.strip(), VISIBLE_RESULT_PREVIEW_CHARS),
    }


def text_search_haystack(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") or {}
    values = [
        metadata.get("record_id"),
        metadata.get("input_preview"),
        metadata.get("source_filename"),
        metadata.get("row_display_number"),
        record.get("job_id"),
    ]
    return " ".join(str(value or "") for value in values).lower()


def normalize_status_key(value: Any) -> str:
    raw = str(value or "queued").strip().lower().replace("-", "_")
    if raw in {"all", ""}:
        return "all"
    if raw in {"complete", "completed", "done"}:
        return "completed"
    if raw in {"failed", "error"}:
        return "failed"
    if raw in {"running", "rq_screening", "openai_running"}:
        return "running"
    return "queued"


def status_label(status_key: str) -> str:
    return {
        "completed": "Completed",
        "running": "Running",
        "queued": "Queued",
        "failed": "Failed",
    }.get(status_key, "Queued")


def text_row_order(metadata: dict[str, Any]) -> int:
    try:
        return int(metadata.get("project_row_order"))
    except (TypeError, ValueError):
        try:
            return int(metadata.get("row_display_number"))
        except (TypeError, ValueError):
            return 0


def next_project_row_order(project_id: str) -> int:
    max_order = -1
    for record in text_job_records(project_id):
        max_order = max(max_order, text_row_order(record.get("metadata") or {}))
    return max_order + 1


def export_columns_for_records(project_id: str, records: list[dict[str, Any]]) -> list[str]:
    columns: list[str] = []
    seen: set[str] = set()
    seen_sources: set[str] = set()
    ordered_source_ids: list[str] = []
    for record in records:
        source_id = str((record.get("metadata") or {}).get("source_id") or "")
        if source_id and source_id not in seen_sources:
            ordered_source_ids.append(source_id)
            seen_sources.add(source_id)
    for source_id in ordered_source_ids:
        if not source_id:
            continue
        manifest = read_json_if_exists(source_dir_for(project_id, source_id) / SOURCE_MANIFEST_FILENAME)
        for column in manifest.get("columns") or []:
            if column not in seen:
                columns.append(str(column))
                seen.add(str(column))
    if columns:
        return columns
    return ["record_id"]


def load_all_source_rows(project_id: str) -> dict[str, dict[int, dict[str, str]]]:
    source_rows: dict[str, dict[int, dict[str, str]]] = {}
    sources_root = projects.project_root(project_id) / SOURCE_FILES_DIRNAME
    if not sources_root.exists():
        return source_rows
    for source_dir in sources_root.iterdir():
        rows_path = source_dir / ROWS_JSONL_FILENAME
        if not rows_path.exists():
            continue
        rows_by_index: dict[int, dict[str, str]] = {}
        with rows_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                payload = json.loads(line)
                rows_by_index[int(payload.get("source_row_index") or 0)] = payload.get("row") or {}
        source_rows[source_dir.name] = rows_by_index
    return source_rows


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def read_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return jobs.read_json(path)


def queue_key(project_id: str, job_id: str) -> str:
    return f"{project_id}:{job_id}"


def job_id_from_key(key: str) -> str:
    return key.split(":", maxsplit=1)[1] if ":" in key else key


def stringify_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def is_blank_row(row: dict[str, str]) -> bool:
    return not any(str(value or "").strip() for value in row.values())


def truncate(value: str, limit: int) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
