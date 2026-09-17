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


def jobs_dir(project_id: str | None = None) -> Path:
    if project_id:
        from app.services.projects import get_project_jobs_dir

        return get_project_jobs_dir(project_id)
    return config.JOBS_DIR


def job_dir(job_id: str, project_id: str | None = None) -> Path:
    return jobs_dir(project_id) / job_id


def create_job(job_id: str, filename: str, settings: JobSettings, project_id: str | None = None) -> Path:
    root = job_dir(job_id, project_id)
    for name in ["input", "rendered_pages", "ocr_images", "ocr_text", "outputs"]:
        (root / name).mkdir(parents=True, exist_ok=True)
    metadata = {
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "original_filename": filename,
        "settings": settings.to_metadata_dict(),
        "warnings": [],
    }
    if project_id:
        metadata["project_id"] = project_id
    write_json(root / "metadata.json", metadata)
    write_status(JobStatus(job_id=job_id), project_id=project_id)
    return root


def save_upload(src_file, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        shutil.copyfileobj(src_file, out)


def delete_job(job_id: str, project_id: str | None = None) -> None:
    root = job_dir(job_id, project_id)
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


def find_screened_jobs_by_filename(filename: str, project_id: str | None = None) -> list[dict[str, Any]]:
    if not filename:
        return []
    filename = str(filename)
    basename = Path(filename).name
    matches: list[dict[str, Any]] = []
    for record in list_jobs(limit=0, project_id=project_id):
        status = record.get("status") or {}
        metadata = record.get("metadata") or {}
        root = job_dir(str(record["job_id"]), project_id)
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
    project_id: str | None = None,
    source_bundle_sha256: str = "",
) -> dict[str, Any] | None:
    for record in find_screened_jobs_by_filename(filename, project_id=project_id):
        metadata = record.get("metadata") or {}
        if source_bundle_sha256 and str(metadata.get("source_bundle_sha256") or "") != source_bundle_sha256:
            continue
        if (
            str(metadata.get("rq_prompt_filename") or "") == str(prompt_filename or "")
            and str(metadata.get("rq_screening_model") or "") == str(model or "")
            and str(metadata.get("openai_input_mode") or "ocr_text") == str(openai_input_mode or "ocr_text")
        ):
            return record
    return None


def find_reusable_ocr_job_by_filename(
    filename: str,
    project_id: str | None = None,
    source_bundle_sha256: str = "",
) -> dict[str, Any] | None:
    for record in find_screened_jobs_by_filename(filename, project_id=project_id):
        root = job_dir(str(record["job_id"]), project_id)
        merged = root / "outputs" / "merged_full_text.txt"
        metadata = record.get("metadata") or {}
        if source_bundle_sha256 and str(metadata.get("source_bundle_sha256") or "") != source_bundle_sha256:
            continue
        if merged.exists() and len(merged.read_text(encoding="utf-8").strip()) >= 20:
            return record
    return None


def find_reusable_openai_file_job(
    pdf_sha256: str,
    filename: str = "",
    project_id: str | None = None,
    source_bundle_sha256: str = "",
) -> dict[str, Any] | None:
    basename = Path(str(filename or "")).name
    for record in list_jobs(limit=0, project_id=project_id):
        metadata = record.get("metadata") or {}
        raw_file_ids = [str(value or "").strip() for value in metadata.get("openai_file_ids") or []]
        if not raw_file_ids and metadata.get("openai_file_id"):
            raw_file_ids = [str(metadata["openai_file_id"]).strip()]
        if not raw_file_ids or not all(raw_file_ids):
            continue
        if source_bundle_sha256:
            if str(metadata.get("source_bundle_sha256") or "") != source_bundle_sha256:
                continue
            if str(metadata.get("openai_source_bundle_sha256") or "") not in {"", source_bundle_sha256}:
                continue
            source_root = job_dir(str(record["job_id"]), project_id)
            if len(raw_file_ids) != len(source_file_records(source_root, metadata)):
                continue
            return record
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


def create_screening_rerun_child_job(
    source_job_id: str,
    settings: JobSettings,
    project_id: str | None = None,
) -> tuple[str, Path]:
    source_root = job_dir(source_job_id, project_id)
    source_metadata = read_metadata(source_root)
    source_pdf = source_root / "input" / "uploaded.pdf"
    if not source_pdf.exists() or source_pdf.stat().st_size == 0:
        raise FileNotFoundError(f"Source PDF is missing for job {source_job_id}")

    filename = str(source_metadata.get("original_filename") or source_pdf.name)
    child_job_id = new_job_id()
    child_root = create_job(child_job_id, filename, settings, project_id=project_id)
    bundle_updates = copy_source_bundle(source_root, child_root)
    update_metadata(
        child_root,
        **settings_metadata_updates(settings),
        **bundle_updates,
        rerun_created_from_job_id=source_job_id,
        rerun_requested_at=datetime.now(timezone.utc).isoformat(),
    )
    copy_reusable_ocr(source_job_id, child_root, source_project_id=project_id)
    copy_reusable_openai_file(source_job_id, child_root, source_project_id=project_id)
    return child_job_id, child_root


def copy_reusable_ocr(source_job_id: str, target_root: Path, source_project_id: str | None = None) -> None:
    source_root = job_dir(source_job_id, source_project_id)
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


def copy_reusable_openai_file(source_job_id: str, target_root: Path, source_project_id: str | None = None) -> None:
    source_root = job_dir(source_job_id, source_project_id)
    source_metadata = read_metadata(source_root)
    file_ids = reusable_openai_file_ids(source_root, source_metadata)
    if not file_ids and not isinstance(source_metadata.get("source_files"), list):
        # Retain the old metadata-only fallback for pre-manifest jobs. Real
        # bundles always take the complete-record path above.
        legacy_file_id = str(source_metadata.get("openai_file_id") or "").strip()
        file_ids = [legacy_file_id] if legacy_file_id else []
    if not file_ids:
        return
    update_metadata(
        target_root,
        openai_file_id=file_ids[0],
        openai_file_ids=file_ids,
        openai_source_bundle_sha256=str(source_metadata.get("openai_source_bundle_sha256") or source_metadata.get("source_bundle_sha256") or ""),
        openai_file_reused_from_job_id=source_job_id,
        openai_file_uploaded=False,
    )


def save_source_bundle(
    root: Path,
    primary_upload: Any,
    primary_relative_path: str,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Persist one primary PDF and its optional supporting files for a single job.

    The primary PDF intentionally remains at ``input/uploaded.pdf`` so all
    pre-bundle job paths continue to work. Supporting sources are isolated
    beneath ``input/attachments`` and described in metadata for reproducibility.
    """

    primary_name = source_display_filename(primary_upload, fallback="uploaded.pdf")
    primary_path = root / "input" / "uploaded.pdf"
    save_upload(source_upload_file(primary_upload), primary_path)
    records: list[dict[str, Any]] = [
        source_file_record(
            role="primary_pdf",
            filename=primary_name,
            relative_path=primary_relative_path,
            stored_path="input/uploaded.pdf",
            path=primary_path,
            source_index=0,
        )
    ]

    attachment_root = root / "input" / "attachments"
    for index, attachment in enumerate(attachments or [], start=1):
        upload = attachment["upload"]
        filename = source_display_filename(upload, fallback=f"attachment-{index}")
        stored_name = f"{index:03d}-{safe_source_filename(filename, fallback=f'attachment-{index}')}"
        destination = attachment_root / stored_name
        save_upload(source_upload_file(upload), destination)
        records.append(
            source_file_record(
                role="supporting_file",
                filename=filename,
                relative_path=str(attachment.get("relative_path") or filename),
                stored_path=str(destination.relative_to(root)),
                path=destination,
                source_index=index,
            )
        )

    bundle_sha256 = source_bundle_sha256(records)
    primary = records[0]
    supporting = records[1:]
    return {
        "uploaded_pdf": str(primary_path),
        "pdf_sha256": str(primary["sha256"]),
        "source_relative_path": str(primary["relative_path"]),
        "source_files": records,
        "source_bundle_sha256": bundle_sha256,
        "supporting_file_count": len(supporting),
        "supporting_filenames": [str(record["filename"]) for record in supporting],
    }


def source_file_records(root: Path, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return safe, ordered source records for a job, including legacy jobs."""

    payload = metadata if metadata is not None else read_metadata(root)
    raw_records = payload.get("source_files") if isinstance(payload.get("source_files"), list) else []
    records: list[dict[str, Any]] = []
    for index, value in enumerate(raw_records):
        if not isinstance(value, dict):
            continue
        stored_path = str(value.get("stored_path") or "").strip()
        path = source_stored_path(root, stored_path)
        if path is None or not path.exists() or not path.is_file():
            continue
        record = dict(value)
        source_index = record.get("source_index")
        record["source_index"] = int(source_index) if source_index not in {None, ""} else index
        record["path"] = path
        records.append(record)
    if raw_records:
        # A manifest is authoritative. Do not silently extract a partial study
        # when a supporting source was removed or corrupted on disk.
        if len(records) != len(raw_records) or not records:
            return []
        return sorted(
            records,
            key=lambda record: int(record.get("source_index") if record.get("source_index") is not None else 0),
        )

    # Existing jobs only know about the primary PDF. Keep them fully usable.
    primary = root / "input" / "uploaded.pdf"
    if not primary.exists() or not primary.is_file():
        return []
    record = source_file_record(
        role="primary_pdf",
        filename=str(payload.get("original_filename") or primary.name),
        relative_path=str(payload.get("source_relative_path") or payload.get("original_filename") or primary.name),
        stored_path="input/uploaded.pdf",
        path=primary,
        source_index=0,
    )
    record["path"] = primary
    return [record]


def source_file_paths(root: Path, metadata: dict[str, Any] | None = None) -> list[Path]:
    return [Path(record["path"]) for record in source_file_records(root, metadata)]


def reusable_openai_file_ids(root: Path, metadata: dict[str, Any] | None = None) -> list[str]:
    """Return saved OpenAI IDs only when they cover this exact source bundle."""

    payload = metadata if metadata is not None else read_metadata(root)
    records = source_file_records(root, payload)
    ids = [str(value or "") for value in payload.get("openai_file_ids") or []]
    if not ids and payload.get("openai_file_id"):
        ids = [str(payload["openai_file_id"])]
    if len(ids) != len(records) or not all(ids):
        return []
    expected = str(payload.get("source_bundle_sha256") or "")
    saved = str(payload.get("openai_source_bundle_sha256") or "")
    if expected and saved and saved != expected:
        return []
    return ids


def source_pdf_records(root: Path, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [record for record in source_file_records(root, metadata) if source_suffix(record) == ".pdf"]


def source_spreadsheet_records(root: Path, metadata: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return [record for record in source_file_records(root, metadata) if source_suffix(record) in {".xlsx", ".csv"}]


def source_bundle_sha256(records: list[dict[str, Any]]) -> str:
    canonical = [
        {
            "source_index": int(record.get("source_index")) if record.get("source_index") not in {None, ""} else index,
            "role": str(record.get("role") or ""),
            "filename": str(record.get("filename") or ""),
            "relative_path": str(record.get("relative_path") or ""),
            "sha256": str(record.get("sha256") or ""),
        }
        for index, record in enumerate(records)
    ]
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def upload_source_bundle_sha256(
    primary_upload: Any,
    primary_relative_path: str,
    attachments: list[dict[str, Any]] | None = None,
) -> str:
    records = [
        {
            "source_index": 0,
            "role": "primary_pdf",
            "filename": source_display_filename(primary_upload, fallback="uploaded.pdf"),
            "relative_path": str(primary_relative_path or ""),
            "sha256": stream_sha256(source_upload_file(primary_upload)),
        }
    ]
    for index, attachment in enumerate(attachments or [], start=1):
        upload = attachment["upload"]
        records.append(
            {
                "source_index": index,
                "role": "supporting_file",
                "filename": source_display_filename(upload, fallback=f"attachment-{index}"),
                "relative_path": str(attachment.get("relative_path") or ""),
                "sha256": stream_sha256(source_upload_file(upload)),
            }
        )
    return source_bundle_sha256(records)


def copy_source_bundle(source_root: Path, target_root: Path) -> dict[str, Any]:
    """Copy every stored source into a rerun child and return metadata updates."""

    source_metadata = read_metadata(source_root)
    return copy_source_bundle_records(source_root, source_metadata, target_root)


def copy_source_bundle_records(
    source_root: Path,
    source_metadata: dict[str, Any],
    target_root: Path,
) -> dict[str, Any]:
    """Copy a persisted source manifest into a job while preserving safe relative paths."""

    records = source_file_records(source_root, source_metadata)
    if not records:
        raise FileNotFoundError(f"No source files found in {source_root}")
    copied_records: list[dict[str, Any]] = []
    for record in records:
        source_path = Path(record["path"])
        stored_path = str(record.get("stored_path") or "")
        destination = source_stored_path(target_root, stored_path)
        if destination is None:
            raise ValueError(f"Invalid stored source path: {stored_path}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        copied = {key: value for key, value in record.items() if key != "path"}
        copied_records.append(copied)
    primary = next((record for record in copied_records if record.get("role") == "primary_pdf"), copied_records[0])
    return {
        "uploaded_pdf": str(target_root / "input" / "uploaded.pdf"),
        "pdf_sha256": str(primary.get("sha256") or file_sha256(target_root / "input" / "uploaded.pdf")),
        "source_relative_path": str(primary.get("relative_path") or source_metadata.get("source_relative_path") or ""),
        "source_folder": str(source_metadata.get("source_folder") or ""),
        "source_files": copied_records,
        "source_bundle_sha256": str(source_metadata.get("source_bundle_sha256") or source_bundle_sha256(copied_records)),
        "supporting_file_count": max(0, len(copied_records) - 1),
        "supporting_filenames": [str(record.get("filename") or "") for record in copied_records[1:]],
    }


def record_openai_source_file(root: Path, *, file_id: str, source_index: int = 0, uploaded: bool) -> dict[str, Any]:
    """Persist OpenAI file IDs by bundle position so retries can reuse all sources."""

    if not file_id:
        return read_metadata(root)
    path = root / "metadata.json"
    with _path_lock(path):
        metadata = read_metadata(root)
        file_ids = [str(value or "") for value in metadata.get("openai_file_ids") or []]
        index = max(0, int(source_index or 0))
        while len(file_ids) <= index:
            file_ids.append("")
        file_ids[index] = file_id
        metadata.update(
            {
                "openai_file_ids": file_ids,
                "openai_file_id": file_ids[0] if file_ids else file_id,
                "openai_source_bundle_sha256": str(metadata.get("source_bundle_sha256") or ""),
                "openai_file_uploaded": bool(metadata.get("openai_file_uploaded")) or bool(uploaded),
            }
        )
        write_json(path, metadata)
        return metadata


def source_upload_file(upload: Any) -> Any:
    return getattr(upload, "file", upload)


def source_display_filename(upload: Any, *, fallback: str) -> str:
    return safe_source_filename(str(getattr(upload, "filename", "") or ""), fallback=fallback)


def safe_source_filename(filename: str, *, fallback: str) -> str:
    return Path(str(filename or fallback)).name or fallback


def source_file_record(
    *,
    role: str,
    filename: str,
    relative_path: str,
    stored_path: str,
    path: Path,
    source_index: int,
) -> dict[str, Any]:
    return {
        "source_index": source_index,
        "role": role,
        "filename": filename,
        "relative_path": str(relative_path or filename),
        "stored_path": stored_path.replace("\\", "/"),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
        "content_type": source_suffix_from_name(filename).lstrip("."),
    }


def source_stored_path(root: Path, stored_path: str) -> Path | None:
    candidate = (root / str(stored_path or "")).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def source_suffix(record: dict[str, Any]) -> str:
    return source_suffix_from_name(str(record.get("filename") or record.get("stored_path") or ""))


def source_suffix_from_name(name: str) -> str:
    return Path(str(name or "")).suffix.lower()


def stream_sha256(stream: Any) -> str:
    position = stream.tell() if hasattr(stream, "tell") else None
    try:
        if hasattr(stream, "seek"):
            stream.seek(0)
        digest = hashlib.sha256()
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        if position is not None and hasattr(stream, "seek"):
            stream.seek(position)


def read_status(job_id: str, project_id: str | None = None) -> dict[str, Any]:
    path = job_dir(job_id, project_id) / "status.json"
    if not path.exists():
        raise FileNotFoundError(f"Job not found: {job_id}")
    return read_json(path)


def write_status(status: JobStatus | dict[str, Any], project_id: str | None = None) -> None:
    payload = status.to_dict() if isinstance(status, JobStatus) else status
    write_json(job_dir(str(payload["job_id"]), project_id) / "status.json", payload)


def update_status(
    job_id: str,
    *,
    status: str = "running",
    stage: str,
    message: str,
    progress: float,
    error: str | None = None,
    event: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> None:
    current_path = job_dir(job_id, project_id) / "status.json"
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


def list_jobs(limit: int = 200, project_id: str | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    root_jobs_dir = jobs_dir(project_id)
    for root in root_jobs_dir.iterdir() if root_jobs_dir.exists() else []:
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
                "project_id": str(metadata.get("project_id") or project_id or ""),
            }
        )
    records.sort(key=lambda record: str(record.get("created_at") or ""), reverse=True)
    if limit > 0:
        return records[:limit]
    return records


def list_jobs_window(
    *,
    project_id: str | None = None,
    offset: int = 0,
    limit: int = 80,
    status: str = "all",
    search: str = "",
) -> dict[str, Any]:
    """Return a bounded, filterable job window for the dashboard.

    Job folders remain the source of truth. This keeps the API backward
    compatible while preventing the browser from receiving every historical
    job on each refresh.
    """

    records = list_jobs(limit=0, project_id=project_id)
    counts = {"all": len(records), "running": 0, "queued": 0, "completed": 0, "failed": 0}
    active_items: list[dict[str, Any]] = []
    for record in records:
        key = job_status_key(record)
        if key in counts:
            counts[key] += 1
        if key in {"running", "queued"}:
            active_items.append(record)

    requested_status = str(status or "all").strip().lower()
    query = str(search or "").strip().lower()
    filtered = [
        record
        for record in records
        if (requested_status == "all" or job_status_key(record) == requested_status)
        and (not query or query in job_search_haystack(record))
    ]
    safe_limit = max(1, min(int(limit or 80), 250))
    safe_offset = max(0, int(offset or 0))
    if filtered and safe_offset >= len(filtered):
        safe_offset = max(0, ((len(filtered) - 1) // safe_limit) * safe_limit)
    items = filtered[safe_offset : safe_offset + safe_limit]
    return {
        "items": items,
        "total": len(filtered),
        "offset": safe_offset,
        "limit": safe_limit,
        "counts": counts,
        "active_items": active_items[:50],
    }


def job_status_key(record: dict[str, Any]) -> str:
    payload = record.get("status") if isinstance(record.get("status"), dict) else {}
    value = str(payload.get("status") or record.get("status") or "queued").strip().lower()
    if value in {"complete", "completed"}:
        return "completed"
    if value in {"failed", "error"}:
        return "failed"
    if value == "running":
        return "running"
    return "queued"


def job_search_haystack(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    values = [
        record.get("job_id"),
        record.get("filename"),
        metadata.get("original_filename"),
        metadata.get("source_relative_path"),
        metadata.get("rq_prompt_filename"),
        metadata.get("rq_screening_model"),
    ]
    return " ".join(str(value or "") for value in values).lower()


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
