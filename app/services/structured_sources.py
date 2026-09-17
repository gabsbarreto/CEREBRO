from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services import jobs, projects


STRUCTURED_EXTRACTION_TYPE = "pdf_structured"
STRUCTURED_SOURCES_DIRNAME = "structured_sources"
SOURCE_FILENAME = "source.json"


def list_sources(project_id: str) -> list[dict[str, Any]]:
    require_structured_project(project_id)
    sources: list[dict[str, Any]] = []
    for path in sorted(sources_root(project_id).glob(f"*/{SOURCE_FILENAME}"), key=lambda item: item.parent.name.lower()):
        try:
            source = read_source_file(path)
        except Exception:
            continue
        sources.append(public_source(source, project_id))
    sources.sort(key=lambda source: (str(source.get("created_at") or ""), str(source.get("source_id") or "")))
    return sources


def get_source(project_id: str, source_id: str) -> dict[str, Any]:
    require_structured_project(project_id)
    safe_source_id = validate_source_id(source_id)
    path = source_root(project_id, safe_source_id) / SOURCE_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"Structured source not found: {safe_source_id}")
    return read_source_file(path)


def create_sources(project_id: str, upload_bundles: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Persist project-level study bundles for later use by any structured workbook."""

    require_structured_project(project_id)
    created: list[dict[str, Any]] = []
    existing: list[dict[str, Any]] = []
    for bundle in upload_bundles:
        upload = bundle["upload"]
        relative_path = str(bundle.get("relative_path") or "")
        attachments = list(bundle.get("attachments") or [])
        signature = jobs.upload_source_bundle_sha256(upload, relative_path, attachments)
        match = find_source_by_bundle_sha256(project_id, signature)
        if match is not None:
            existing.append(public_source(match, project_id))
            continue
        primary_name = jobs.source_display_filename(upload, fallback="uploaded.pdf")
        source_id = unique_source_id(project_id, primary_name)
        root = source_root(project_id, source_id)
        root.mkdir(parents=True, exist_ok=True)
        try:
            bundle_metadata = jobs.save_source_bundle(root, upload, relative_path, attachments)
            now = utc_now()
            source = {
                "source_id": source_id,
                "project_id": projects.validate_project_id(project_id),
                "original_filename": primary_name,
                "source_relative_path": relative_path or primary_name,
                "source_folder": source_folder_from_relative_path(relative_path),
                "created_at": now,
                "updated_at": now,
                **bundle_metadata,
            }
            jobs.write_json(root / SOURCE_FILENAME, source)
        except Exception:
            shutil.rmtree(root, ignore_errors=True)
            raise
        created.append(public_source(source, project_id))
    return {"created": created, "existing": existing}


def copy_source_to_job(project_id: str, source_id: str, target_root: Path) -> dict[str, Any]:
    source = get_source(project_id, source_id)
    source_root_path = source_root(project_id, str(source["source_id"]))
    bundle_metadata = jobs.copy_source_bundle_records(source_root_path, source, target_root)
    return {
        **bundle_metadata,
        "source_library_id": str(source["source_id"]),
        "source_library_bundle_sha256": str(source.get("source_bundle_sha256") or ""),
        "source_library_created_at": str(source.get("created_at") or ""),
    }


def delete_source(project_id: str, source_id: str) -> None:
    source = get_source(project_id, source_id)
    root = source_root(project_id, str(source["source_id"]))
    if root.exists():
        shutil.rmtree(root)


def sources_root(project_id: str) -> Path:
    projects.validate_project_id(project_id)
    path = projects.project_root(project_id) / STRUCTURED_SOURCES_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_root(project_id: str, source_id: str) -> Path:
    return sources_root(project_id) / validate_source_id(source_id)


def validate_source_id(source_id: str) -> str:
    safe_source_id = str(source_id or "").strip()
    if not safe_source_id:
        raise ValueError("Source id is required.")
    projects.validate_project_id(safe_source_id)
    return safe_source_id


def read_source_file(path: Path) -> dict[str, Any]:
    payload = jobs.read_json(path)
    payload["source_id"] = validate_source_id(str(payload.get("source_id") or path.parent.name))
    payload["project_id"] = projects.validate_project_id(str(payload.get("project_id") or path.parents[2].name))
    payload["original_filename"] = str(payload.get("original_filename") or "uploaded.pdf")
    payload["source_relative_path"] = str(payload.get("source_relative_path") or payload["original_filename"])
    payload["source_files"] = payload.get("source_files") if isinstance(payload.get("source_files"), list) else []
    payload["supporting_filenames"] = [str(value or "") for value in payload.get("supporting_filenames") or []]
    payload["supporting_file_count"] = int(payload.get("supporting_file_count") or len(payload["supporting_filenames"]))
    payload.setdefault("created_at", "")
    payload.setdefault("updated_at", "")
    return payload


def public_source(source: dict[str, Any], project_id: str) -> dict[str, Any]:
    source_id = str(source.get("source_id") or "")
    source_files = source.get("source_files") if isinstance(source.get("source_files"), list) else []
    attachments = [
        {
            "filename": str(record.get("filename") or ""),
            "relative_path": str(record.get("relative_path") or ""),
            "content_type": str(record.get("content_type") or ""),
        }
        for record in source_files
        if isinstance(record, dict) and str(record.get("role") or "") != "primary_pdf"
    ]
    used_by_jobs = sum(
        1
        for record in jobs.list_jobs(limit=0, project_id=project_id)
        if str((record.get("metadata") or {}).get("source_library_id") or "") == source_id
    )
    return {
        "source_id": source_id,
        "project_id": str(source.get("project_id") or project_id),
        "primary_filename": str(source.get("original_filename") or "uploaded.pdf"),
        "source_relative_path": str(source.get("source_relative_path") or ""),
        "source_folder": str(source.get("source_folder") or ""),
        "source_bundle_sha256": str(source.get("source_bundle_sha256") or ""),
        "supporting_file_count": len(attachments),
        "supporting_files": attachments,
        "created_at": str(source.get("created_at") or ""),
        "used_by_jobs": used_by_jobs,
    }


def find_source_by_bundle_sha256(project_id: str, signature: str) -> dict[str, Any] | None:
    clean_signature = str(signature or "").strip()
    if not clean_signature:
        return None
    for path in sources_root(project_id).glob(f"*/{SOURCE_FILENAME}"):
        try:
            source = read_source_file(path)
        except Exception:
            continue
        if str(source.get("source_bundle_sha256") or "") == clean_signature:
            return source
    return None


def unique_source_id(project_id: str, filename: str) -> str:
    stem = projects.sanitize_slug(Path(str(filename or "source")).stem or "source")
    for _attempt in range(20):
        candidate = f"{stem}-{uuid.uuid4().hex[:8]}"
        if not source_root(project_id, candidate).exists():
            return candidate
    return uuid.uuid4().hex


def require_structured_project(project_id: str) -> dict[str, Any]:
    project = projects.get_project(project_id)
    if projects.normalize_extraction_type(project.get("extraction_type")) != STRUCTURED_EXTRACTION_TYPE:
        raise ValueError("Project is not a structured PDF extraction project.")
    return project


def source_folder_from_relative_path(relative_path: str) -> str:
    parent = Path(str(relative_path or "").replace("\\", "/")).parent
    return "" if str(parent) in {"", "."} else str(parent).replace("\\", "/")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
