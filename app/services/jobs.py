from __future__ import annotations

import json
import hashlib
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import config
from app.models import JobSettings, JobStatus

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def new_job_id() -> str:
    return uuid.uuid4().hex


def job_dir(job_id: str) -> Path:
    return config.JOBS_DIR / job_id


def create_job(job_id: str, filename: str, settings: JobSettings) -> Path:
    root = job_dir(job_id)
    for name in ["input", "rendered_pages", "ocr_images", "ocr_text", "outputs"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    metadata = {
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "original_filename": filename,
        "settings": settings.to_metadata_dict(),
        "warnings": [],
    }
    write_json(root / "metadata.json", metadata)
    write_status(JobStatus(job_id=job_id))
    return root


def save_upload(src_file, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        shutil.copyfileobj(src_file, out)


def delete_job(job_id: str) -> None:
    root = job_dir(job_id)
    if not root.exists():
        return
    shutil.rmtree(root)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def settings_metadata_updates(
    settings: JobSettings,
    *,
    rq_prompt_filename: str | None = None,
    include_settings: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rq_provider": settings.rq_provider,
        "rq_screening_model": settings.rq_screening_model,
        "rq_max_tokens": settings.rq_max_tokens,
        "rq_thinking_budget": settings.rq_thinking_budget,
        "rq_temperature": settings.rq_temperature,
        "rq_top_p": settings.rq_top_p,
        "rq_top_k": settings.rq_top_k,
        "rq_min_p": settings.rq_min_p,
        "rq_presence_penalty": settings.rq_presence_penalty,
        "rq_repetition_penalty": settings.rq_repetition_penalty,
        "rq_enable_thinking": settings.rq_enable_thinking,
        "openai_reasoning_effort": settings.openai_reasoning_effort,
        "openai_input_mode": settings.openai_input_mode,
        "rq_prompt_filename": rq_prompt_filename if rq_prompt_filename is not None else settings.rq_prompt_filename,
    }
    if include_settings:
        payload["settings"] = settings.to_metadata_dict()
    return payload


def find_screened_jobs_by_filename(filename: str) -> list[dict[str, Any]]:
    if not filename:
        return []
    filename = str(filename)
    basename = Path(filename).name
    matches: list[dict[str, Any]] = []
    for record in list_jobs(limit=0):
        status = record.get("status") or {}
        metadata = record.get("metadata") or {}
        root = job_dir(str(record["job_id"]))
        output = root / "outputs" / "rq_screening_output.md"
        if status.get("status") != "complete" or not output.exists() or output.stat().st_size <= 0:
            continue
        original = str(metadata.get("original_filename") or "")
        if original == filename or Path(original).name == basename:
            matches.append(record)
    return matches


def find_screened_job_by_run_identity(
    filename: str,
    prompt_filename: str,
    model: str,
    openai_input_mode: str = "ocr_text",
) -> dict[str, Any] | None:
    for record in find_screened_jobs_by_filename(filename):
        metadata = record.get("metadata") or {}
        if (
            str(metadata.get("rq_prompt_filename") or "") == str(prompt_filename or "")
            and str(metadata.get("rq_screening_model") or "") == str(model or "")
            and str(metadata.get("openai_input_mode") or "ocr_text") == str(openai_input_mode or "ocr_text")
        ):
            return record
    return None


def find_reusable_ocr_job_by_filename(filename: str) -> dict[str, Any] | None:
    for record in find_screened_jobs_by_filename(filename):
        root = job_dir(str(record["job_id"]))
        merged = root / "outputs" / "merged_full_text.txt"
        if merged.exists() and len(merged.read_text(encoding="utf-8").strip()) >= 20:
            return record
    return None


def find_reusable_openai_file_job(pdf_sha256: str, filename: str = "") -> dict[str, Any] | None:
    basename = Path(str(filename or "")).name
    for record in list_jobs(limit=0):
        metadata = record.get("metadata") or {}
        file_id = str(metadata.get("openai_file_id") or "")
        if not file_id:
            continue
        if pdf_sha256 and str(metadata.get("pdf_sha256") or "") == str(pdf_sha256):
            return record
        original = str(metadata.get("original_filename") or "")
        if basename and Path(original).name == basename:
            return record
    return None


def job_matches_run_identity(root: Path, settings: JobSettings) -> bool:
    metadata = read_metadata(root)
    nested_settings = metadata.get("settings") if isinstance(metadata.get("settings"), dict) else {}
    prompt_filename = str(
        metadata.get("rq_prompt_filename")
        or nested_settings.get("rq_prompt_filename")
        or config.DEFAULT_RQ_PROMPT_FILENAME
    )
    model = str(
        metadata.get("rq_screening_model")
        or nested_settings.get("rq_screening_model")
        or load_job_settings(root).rq_screening_model
    )
    openai_input_mode = str(metadata.get("openai_input_mode") or nested_settings.get("openai_input_mode") or "ocr_text")
    return (
        prompt_filename == settings.rq_prompt_filename
        and model == settings.rq_screening_model
        and openai_input_mode == settings.openai_input_mode
    )


def create_screening_rerun_child_job(source_job_id: str, settings: JobSettings) -> tuple[str, Path]:
    source_root = job_dir(source_job_id)
    source_metadata = read_metadata(source_root)
    source_pdf = source_root / "input" / "uploaded.pdf"
    if not source_pdf.exists() or source_pdf.stat().st_size == 0:
        raise FileNotFoundError(f"Source PDF is missing for job {source_job_id}")

    filename = str(source_metadata.get("original_filename") or source_pdf.name)
    child_job_id = new_job_id()
    child_root = create_job(child_job_id, filename, settings)
    child_pdf = child_root / "input" / "uploaded.pdf"
    shutil.copy2(source_pdf, child_pdf)
    update_metadata(
        child_root,
        **settings_metadata_updates(settings),
        uploaded_pdf=str(child_pdf),
        pdf_sha256=file_sha256(child_pdf),
        rerun_created_from_job_id=source_job_id,
        rerun_requested_at=datetime.now(timezone.utc).isoformat(),
    )
    copy_reusable_ocr(source_job_id, child_root)
    copy_reusable_openai_file(source_job_id, child_root)
    return child_job_id, child_root


def copy_reusable_ocr(source_job_id: str, target_root: Path) -> None:
    source_root = job_dir(source_job_id)
    source_ocr = source_root / "ocr_text"
    target_ocr = target_root / "ocr_text"
    if source_ocr.exists():
        target_ocr.mkdir(parents=True, exist_ok=True)
        for source_file in source_ocr.glob("*.md"):
            shutil.copy2(source_file, target_ocr / source_file.name)

    source_merged = source_root / "outputs" / "merged_full_text.txt"
    target_merged = target_root / "outputs" / "merged_full_text.txt"
    if source_merged.exists():
        target_merged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_merged, target_merged)

    source_metadata = read_metadata(source_root)
    updates: dict[str, Any] = {
        "ocr_complete": True,
        "pending_rerun_screening_only": True,
        "rerun_reuses_ocr": True,
        "reused_ocr_from_job_id": source_job_id,
    }
    if source_metadata.get("number_of_pages") is not None:
        updates["number_of_pages"] = source_metadata.get("number_of_pages")
    update_metadata(target_root, **updates)


def copy_reusable_openai_file(source_job_id: str, target_root: Path) -> None:
    source_metadata = read_metadata(job_dir(source_job_id))
    file_id = str(source_metadata.get("openai_file_id") or "")
    if not file_id:
        return
    update_metadata(
        target_root,
        openai_file_id=file_id,
        openai_file_reused_from_job_id=source_job_id,
        openai_file_uploaded=False,
    )


def read_status(job_id: str) -> dict[str, Any]:
    path = job_dir(job_id) / "status.json"
    if not path.exists():
        raise FileNotFoundError(f"Job not found: {job_id}")
    return read_json(path)


def write_status(status: JobStatus | dict[str, Any]) -> None:
    payload = status.to_dict() if isinstance(status, JobStatus) else status
    write_json(job_dir(str(payload["job_id"])) / "status.json", payload)


def update_status(
    job_id: str,
    *,
    status: str = "running",
    stage: str,
    message: str,
    progress: float,
    error: str | None = None,
    event: dict[str, Any] | None = None,
) -> None:
    current_path = job_dir(job_id) / "status.json"
    with _path_lock(current_path):
        current = read_json(current_path) if current_path.exists() else {"job_id": job_id, "events": []}
        events = list(current.get("events") or [])
        if event is not None:
            events.append(event)
            events = events[-200:]
        current.update(
            {
                "job_id": job_id,
                "status": status,
                "stage": stage,
                "message": message,
                "progress": max(0.0, min(1.0, float(progress))),
                "error": error,
                "events": events,
            }
        )
        write_json(current_path, current)


def read_metadata(root: Path) -> dict[str, Any]:
    path = root / "metadata.json"
    return read_json(path) if path.exists() else {}


def update_metadata(root: Path, **updates: Any) -> dict[str, Any]:
    path = root / "metadata.json"
    with _path_lock(path):
        metadata = read_metadata(root)
        metadata.update(updates)
        write_json(path, metadata)
        return metadata


def append_warning(root: Path, warning: str) -> None:
    path = root / "metadata.json"
    with _path_lock(path):
        metadata = read_metadata(root)
        warnings = list(metadata.get("warnings") or [])
        warnings.append(warning)
        metadata["warnings"] = warnings
        write_json(path, metadata)


def list_jobs(limit: int = 200) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for root in config.JOBS_DIR.iterdir() if config.JOBS_DIR.exists() else []:
        if not root.is_dir():
            continue
        status_path = root / "status.json"
        metadata_path = root / "metadata.json"
        if not status_path.exists() or not metadata_path.exists():
            continue
        try:
            status = read_json(status_path)
            metadata = read_json(metadata_path)
        except (OSError, json.JSONDecodeError):
            continue
        created_at = str(metadata.get("created_at") or "")
        records.append(
            {
                "job_id": root.name,
                "filename": str(metadata.get("original_filename") or ""),
                "created_at": created_at,
                "status": status,
                "metadata": metadata,
                "job_dir": str(root),
            }
        )
    records.sort(key=lambda record: str(record.get("created_at") or ""), reverse=True)
    if limit > 0:
        return records[:limit]
    return records


def load_job_settings(root: Path) -> JobSettings:
    metadata = read_metadata(root)
    raw_settings = metadata.get("settings") if isinstance(metadata.get("settings"), dict) else {}
    if raw_settings.get("rq_screening_model") in {None, "", "leonsarmiento/Qwen3.6-27B-3bit-mlx"}:
        raw_settings = dict(raw_settings)
        raw_settings["rq_screening_model"] = config.RQ_SCREENING_MODEL
        raw_settings["rq_max_tokens"] = config.RQ_SCREENING_MAX_TOKENS
        raw_settings["rq_thinking_budget"] = config.RQ_SCREENING_THINKING_BUDGET
        raw_settings["rq_enable_thinking"] = config.RQ_SCREENING_ENABLE_THINKING
    return JobSettings.from_form(raw_settings)


def load_original_job_settings(root: Path) -> JobSettings:
    metadata = read_metadata(root)
    raw_settings = metadata.get("settings") if isinstance(metadata.get("settings"), dict) else None
    if not raw_settings or not (raw_settings.get("rq_model_preset") or raw_settings.get("rq_screening_model")):
        raise ValueError("Missing original queued settings")
    return load_job_settings(root)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[key] = lock
        return lock
