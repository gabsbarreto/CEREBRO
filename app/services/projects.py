from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import config

DEFAULT_PROJECT_ID = "legacy-jobs"
DEFAULT_PROJECT_NAME = "Legacy jobs"
DEFAULT_PROJECT_DESCRIPTION = "Jobs created before project support was added."
DEFAULT_EXTRACTION_TYPE = "pdf"
EXTRACTION_TYPE_LABELS = {
    "pdf": "PDF extraction",
    "text": "Text extraction",
    "pdf_structured": "Structured PDF extraction",
}

_SAFE_PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_SAFE_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def list_projects() -> list[dict[str, Any]]:
    get_default_project()
    projects: list[dict[str, Any]] = []
    for path in sorted(config.PROJECTS_DIR.glob("*/project.json"), key=lambda item: item.parent.name.lower()):
        try:
            project = read_project_file(path)
        except Exception:
            continue
        projects.append(project)
    projects.sort(key=lambda item: (not bool(item.get("is_default")), str(item.get("name") or "").lower()))
    return projects


def create_project(name: str, description: str = "", extraction_type: str = DEFAULT_EXTRACTION_TYPE) -> dict[str, Any]:
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("Project name is required.")
    clean_description = str(description or "").strip()
    clean_extraction_type = normalize_extraction_type(extraction_type)
    project_id = unique_project_id(clean_name)
    now = utc_now()
    project = {
        "project_id": project_id,
        "name": clean_name,
        "description": clean_description,
        "extraction_type": clean_extraction_type,
        "created_at": now,
        "updated_at": now,
        "is_default": False,
    }
    root = project_root(project_id)
    (root / "jobs").mkdir(parents=True, exist_ok=True)
    write_project_file(root / "project.json", project)
    return read_project_file(root / "project.json")


def get_project(project_id: str) -> dict[str, Any]:
    safe_id = validate_project_id(project_id)
    path = project_root(safe_id) / "project.json"
    if not path.exists():
        raise FileNotFoundError(f"Project not found: {safe_id}")
    return read_project_file(path)


def get_default_project() -> dict[str, Any]:
    root = project_root(DEFAULT_PROJECT_ID)
    path = root / "project.json"
    if path.exists():
        try:
            raw_project = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw_project = {}
        project = read_project_file(path)
        updated = False
        if not project.get("name"):
            project["name"] = DEFAULT_PROJECT_NAME
            updated = True
        if not project.get("description"):
            project["description"] = DEFAULT_PROJECT_DESCRIPTION
            updated = True
        if not project.get("is_default"):
            project["is_default"] = True
            updated = True
        if raw_project.get("extraction_type") != DEFAULT_EXTRACTION_TYPE:
            project["extraction_type"] = DEFAULT_EXTRACTION_TYPE
            updated = True
        if updated:
            project["updated_at"] = utc_now()
            write_project_file(path, project)
        (root / "jobs").mkdir(parents=True, exist_ok=True)
        return project

    now = utc_now()
    project = {
        "project_id": DEFAULT_PROJECT_ID,
        "name": DEFAULT_PROJECT_NAME,
        "description": DEFAULT_PROJECT_DESCRIPTION,
        "extraction_type": DEFAULT_EXTRACTION_TYPE,
        "created_at": now,
        "updated_at": now,
        "is_default": True,
    }
    (root / "jobs").mkdir(parents=True, exist_ok=True)
    write_project_file(path, project)
    return read_project_file(path)


def migrate_legacy_jobs_if_needed() -> dict[str, Any]:
    project = get_default_project()
    target_jobs_dir = get_project_jobs_dir(str(project["project_id"]))
    legacy_jobs_dir = config.JOBS_DIR
    if not legacy_jobs_dir.exists() or legacy_jobs_dir.resolve() == target_jobs_dir.resolve():
        return {"project": project, "copied": [], "skipped": []}

    copied: list[str] = []
    skipped: list[str] = []
    for source in sorted(legacy_jobs_dir.iterdir(), key=lambda item: item.name):
        if not source.is_dir():
            continue
        if not (source / "metadata.json").exists() or not (source / "status.json").exists():
            continue
        destination = target_jobs_dir / source.name
        if destination.exists():
            skipped.append(source.name)
            continue
        shutil.copytree(source, destination)
        _stamp_project_id(destination, str(project["project_id"]))
        copied.append(source.name)
    if copied:
        project = dict(project)
        project["legacy_migration_last_run_at"] = utc_now()
        project["legacy_migrated_job_count"] = len(copied) + int(project.get("legacy_migrated_job_count") or 0)
        write_project_file(project_root(str(project["project_id"])) / "project.json", project)
    return {"project": project, "copied": copied, "skipped": skipped}


def get_project_jobs_dir(project_id: str) -> Path:
    safe_id = validate_project_id(project_id)
    path = project_root(safe_id) / "jobs"
    if not (project_root(safe_id) / "project.json").exists():
        raise FileNotFoundError(f"Project not found: {safe_id}")
    path.mkdir(parents=True, exist_ok=True)
    return path


def validate_project_id(project_id: str) -> str:
    safe_id = str(project_id or "").strip()
    if not safe_id:
        raise ValueError("Project id is required.")
    if not _SAFE_PROJECT_ID_RE.fullmatch(safe_id):
        raise ValueError("Project id contains invalid characters.")
    return safe_id


def project_root(project_id: str) -> Path:
    return config.PROJECTS_DIR / validate_project_id(project_id)


def project_summary_path(project_id: str) -> Path:
    project = get_project(project_id)
    stem = sanitize_slug(str(project.get("name") or project_id))
    return project_root(str(project["project_id"])) / f"{stem}_rq_screening_summary.xlsx"


def project_dashboard_path(project: dict[str, Any]) -> str:
    project_id = validate_project_id(str(project.get("project_id") or ""))
    extraction_type = normalize_extraction_type(project.get("extraction_type"))
    if extraction_type == "text":
        return f"/text?project_id={project_id}"
    if extraction_type == "pdf_structured":
        return f"/structured-pdf?project_id={project_id}"
    return f"/rq-screening?project_id={project_id}"


def unique_project_id(name: str) -> str:
    stem = sanitize_slug(name)
    for _attempt in range(20):
        candidate = f"{stem}-{uuid.uuid4().hex[:8]}"
        if not (config.PROJECTS_DIR / candidate).exists():
            return candidate
    return uuid.uuid4().hex


def sanitize_slug(value: str) -> str:
    slug = _SAFE_SLUG_RE.sub("-", str(value or "").strip().lower()).strip(".-_")
    return slug or "project"


def read_project_file(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["project_id"] = validate_project_id(str(payload.get("project_id") or path.parent.name))
    payload.setdefault("name", payload["project_id"])
    payload.setdefault("description", "")
    payload["extraction_type"] = normalize_extraction_type(payload.get("extraction_type"))
    payload["extraction_type_label"] = EXTRACTION_TYPE_LABELS[payload["extraction_type"]]
    payload["dashboard_path"] = project_dashboard_path(payload)
    payload.setdefault("created_at", "")
    payload.setdefault("updated_at", "")
    payload.setdefault("is_default", payload["project_id"] == DEFAULT_PROJECT_ID)
    return payload


def write_project_file(path: Path, payload: dict[str, Any]) -> None:
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stamp_project_id(job_root: Path, project_id: str) -> None:
    metadata_path = job_root / "metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return
    if metadata.get("project_id") == project_id:
        if metadata.get("extraction_type") == DEFAULT_EXTRACTION_TYPE:
            return
    metadata["project_id"] = project_id
    metadata["extraction_type"] = DEFAULT_EXTRACTION_TYPE
    tmp = metadata_path.with_name(f".{metadata_path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(metadata_path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def normalize_extraction_type(value: Any) -> str:
    extraction_type = str(value or DEFAULT_EXTRACTION_TYPE).strip().lower().replace("-", "_")
    if extraction_type in {"pdf", "pdf_extraction"}:
        return "pdf"
    if extraction_type in {"text", "text_extraction", "spreadsheet"}:
        return "text"
    if extraction_type in {"pdf_structured", "structured_pdf", "structured_pdf_extraction"}:
        return "pdf_structured"
    raise ValueError("Project extraction type must be 'pdf', 'text', or 'pdf_structured'.")
