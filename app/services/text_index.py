from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from app.services import projects

TEXT_INDEX_FILENAME = "text_row_index.sqlite3"
TEXT_INDEX_SCHEMA_VERSION = 1
TEXT_INDEX_CELL_VALUE_LIMIT = 8_000
INDEX_WRITE_BATCH_SIZE = 1_000

_LOCK_GUARD = threading.Lock()
_PROJECT_LOCKS: dict[str, threading.RLock] = {}


def database_path(project_id: str) -> Path:
    return projects.project_root(projects.validate_project_id(project_id)) / TEXT_INDEX_FILENAME


def source_index_ready(project_id: str, source_id: str, expected_row_count: int) -> bool:
    path = database_path(project_id)
    if not path.exists():
        return False
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            row = connection.execute(
                """
                SELECT row_count, schema_version
                FROM text_source_index_meta
                WHERE project_id = ? AND source_id = ?
                """,
                (project_id, source_id),
            ).fetchone()
    return bool(
        row
        and int(row["schema_version"] or 0) == TEXT_INDEX_SCHEMA_VERSION
        and int(row["row_count"] or 0) == max(0, int(expected_row_count or 0))
    )


def rebuild_source_index(
    project_id: str,
    source_id: str,
    rows_path: Path,
) -> int:
    """Persist table-safe source values once, rather than reading rows.jsonl per poll."""

    if not rows_path.exists():
        return 0
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM text_source_rows WHERE project_id = ? AND source_id = ?",
                    (project_id, source_id),
                )
                row_count = 0
                batch: list[tuple[Any, ...]] = []
                with rows_path.open("r", encoding="utf-8") as handle:
                    for row_order, line in enumerate(handle):
                        if not line.strip():
                            continue
                        payload = json.loads(line)
                        batch.append(_source_row_values(project_id, source_id, row_order, payload))
                        row_count += 1
                        if len(batch) >= INDEX_WRITE_BATCH_SIZE:
                            _insert_source_rows(connection, batch)
                            batch.clear()
                if batch:
                    _insert_source_rows(connection, batch)
                connection.execute(
                    """
                    INSERT INTO text_source_index_meta (
                        project_id, source_id, row_count, schema_version, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(project_id, source_id) DO UPDATE SET
                        row_count = excluded.row_count,
                        schema_version = excluded.schema_version,
                        updated_at = excluded.updated_at
                    """,
                    (project_id, source_id, row_count, TEXT_INDEX_SCHEMA_VERSION, _utc_now()),
                )
    return row_count


def replace_project_job_index(project_id: str, entries: Iterable[dict[str, Any]]) -> int:
    """Replace the derived text-job rows for one project in a single transaction."""

    rows = [_job_values(project_id, entry) for entry in entries]
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            with connection:
                connection.execute("DELETE FROM text_sheet_jobs WHERE project_id = ?", (project_id,))
                connection.executemany(
                    """
                    INSERT INTO text_sheet_jobs (
                        job_id, project_id, sheet_id, source_id, source_row_index,
                        model, prompt, status, stage, message, error, started_at,
                        completed_at, duration_seconds, result_preview, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows,
                )
    return len(rows)


def upsert_job(project_id: str, entry: dict[str, Any]) -> None:
    upsert_jobs(project_id, [entry])


def upsert_jobs(project_id: str, entries: Iterable[dict[str, Any]]) -> int:
    values = [_job_values(project_id, entry) for entry in entries]
    if not values:
        return 0
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO text_sheet_jobs (
                        job_id, project_id, sheet_id, source_id, source_row_index,
                        model, prompt, status, stage, message, error, started_at,
                        completed_at, duration_seconds, result_preview, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(job_id) DO UPDATE SET
                        sheet_id = excluded.sheet_id,
                        source_id = excluded.source_id,
                        source_row_index = excluded.source_row_index,
                        model = excluded.model,
                        prompt = excluded.prompt,
                        status = excluded.status,
                        stage = excluded.stage,
                        message = excluded.message,
                        error = excluded.error,
                        started_at = excluded.started_at,
                        completed_at = excluded.completed_at,
                        duration_seconds = excluded.duration_seconds,
                        result_preview = excluded.result_preview,
                        updated_at = excluded.updated_at
                    """,
                    values,
                )
    return len(values)


def update_job_state(
    project_id: str,
    job_id: str,
    *,
    status: str,
    stage: str,
    message: str,
    error: str | None,
    started_at: str | None = None,
    completed_at: str | None = None,
    duration_seconds: float | int | None = None,
    result_preview: str | None = None,
) -> bool:
    updates = [
        "status = ?",
        "stage = ?",
        "message = ?",
        "error = ?",
        "updated_at = ?",
    ]
    values: list[Any] = [
        normalize_status(status),
        str(stage or ""),
        str(message or ""),
        str(error or ""),
        _utc_now(),
    ]
    if started_at is not None:
        updates.append("started_at = ?")
        values.append(str(started_at or ""))
    if completed_at is not None:
        updates.append("completed_at = ?")
        values.append(str(completed_at or ""))
    if duration_seconds is not None:
        updates.append("duration_seconds = ?")
        values.append(duration_seconds)
    if result_preview is not None:
        updates.append("result_preview = ?")
        values.append(_bounded(result_preview, TEXT_INDEX_CELL_VALUE_LIMIT))
    values.extend([project_id, job_id])
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            with connection:
                cursor = connection.execute(
                    f"UPDATE text_sheet_jobs SET {', '.join(updates)} WHERE project_id = ? AND job_id = ?",
                    values,
                )
    return cursor.rowcount > 0


def list_sheet_rows(
    *,
    project_id: str,
    sheet_id: str,
    source_id: str,
    offset: int,
    limit: int,
    status: str,
    search: str,
) -> dict[str, Any]:
    where_sql, parameters = _row_filters(project_id, sheet_id, source_id, status, search)
    safe_offset = max(0, int(offset or 0))
    safe_limit = max(1, min(500, int(limit or 100)))
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            total = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*) AS value
                    FROM text_source_rows AS source
                    LEFT JOIN text_sheet_jobs AS job
                        ON job.project_id = source.project_id
                        AND job.source_id = source.source_id
                        AND job.source_row_index = source.source_row_index
                        AND job.sheet_id = ?
                    WHERE {where_sql}
                    """,
                    [sheet_id, *parameters],
                ).fetchone()["value"]
            )
            rows = connection.execute(
                f"""
                SELECT
                    source.source_row_index,
                    source.row_order,
                    source.row_display_number,
                    source.record_id,
                    source.input_preview,
                    source.mapped_cells_json,
                    job.job_id,
                    job.model,
                    job.prompt,
                    job.status,
                    job.stage,
                    job.message,
                    job.error,
                    job.started_at,
                    job.completed_at,
                    job.duration_seconds,
                    job.result_preview
                FROM text_source_rows AS source
                LEFT JOIN text_sheet_jobs AS job
                    ON job.project_id = source.project_id
                    AND job.source_id = source.source_id
                    AND job.source_row_index = source.source_row_index
                    AND job.sheet_id = ?
                WHERE {where_sql}
                ORDER BY source.row_order ASC
                LIMIT ? OFFSET ?
                """,
                [sheet_id, *parameters, safe_limit, safe_offset],
            ).fetchall()
    return {
        "items": [_serialize_row(row, project_id) for row in rows],
        "total": total,
        "offset": safe_offset,
        "limit": safe_limit,
    }


def sheet_counts(project_id: str, sheet_id: str, source_id: str) -> dict[str, int]:
    counts = {"total": 0, "not_run": 0, "queued": 0, "running": 0, "completed": 0, "failed": 0}
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            rows = connection.execute(
                """
                SELECT COALESCE(job.status, 'not_run') AS status, COUNT(*) AS value
                FROM text_source_rows AS source
                LEFT JOIN text_sheet_jobs AS job
                    ON job.project_id = source.project_id
                    AND job.source_id = source.source_id
                    AND job.source_row_index = source.source_row_index
                    AND job.sheet_id = ?
                WHERE source.project_id = ? AND source.source_id = ?
                GROUP BY COALESCE(job.status, 'not_run')
                """,
                (sheet_id, project_id, source_id),
            ).fetchall()
    for row in rows:
        status = normalize_status(row["status"])
        counts[status] = int(row["value"] or 0)
        counts["total"] += int(row["value"] or 0)
    return counts


def failed_job_ids(project_id: str, sheet_id: str = "") -> list[str]:
    if not database_path(project_id).exists():
        return []
    where = "project_id = ? AND status = 'failed'"
    parameters: list[Any] = [project_id]
    if sheet_id:
        where += " AND sheet_id = ?"
        parameters.append(sheet_id)
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            rows = connection.execute(
                f"SELECT job_id FROM text_sheet_jobs WHERE {where} ORDER BY source_row_index ASC",
                parameters,
            ).fetchall()
    return [str(row["job_id"]) for row in rows]


def completed_job_ids_without_preview(project_id: str) -> list[str]:
    if not database_path(project_id).exists():
        return []
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            rows = connection.execute(
                """
                SELECT job_id
                FROM text_sheet_jobs
                WHERE project_id = ? AND status = 'completed' AND length(result_preview) = 0
                ORDER BY source_row_index ASC
                """,
                (project_id,),
            ).fetchall()
    return [str(row["job_id"]) for row in rows]


def update_result_preview(project_id: str, job_id: str, result_preview: str) -> bool:
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            with connection:
                cursor = connection.execute(
                    """
                    UPDATE text_sheet_jobs
                    SET result_preview = ?, updated_at = ?
                    WHERE project_id = ? AND job_id = ?
                    """,
                    (_bounded(result_preview, TEXT_INDEX_CELL_VALUE_LIMIT), _utc_now(), project_id, job_id),
                )
    return cursor.rowcount > 0


def has_job_index(project_id: str) -> bool:
    """Whether this project has a populated, atomically-written job index."""

    if not database_path(project_id).exists():
        return False
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            row = connection.execute(
                "SELECT 1 AS value FROM text_sheet_jobs WHERE project_id = ? LIMIT 1",
                (project_id,),
            ).fetchone()
    return row is not None


def indexed_job_count(project_id: str) -> int:
    if not database_path(project_id).exists():
        return 0
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS value FROM text_sheet_jobs WHERE project_id = ?",
                (project_id,),
            ).fetchone()
    return int(row["value"] or 0) if row else 0


def queued_job_refs(project_id: str) -> list[tuple[int, str]]:
    if not database_path(project_id).exists():
        return []
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            rows = connection.execute(
                """
                SELECT source_row_index, job_id
                FROM text_sheet_jobs
                WHERE project_id = ? AND status = 'queued'
                ORDER BY source_row_index ASC
                """,
                (project_id,),
            ).fetchall()
    return [(_as_int(row["source_row_index"], 0), str(row["job_id"])) for row in rows]


def running_job_ids(project_id: str) -> list[str]:
    if not database_path(project_id).exists():
        return []
    with _project_lock(project_id):
        with _connection(project_id) as connection:
            rows = connection.execute(
                """
                SELECT job_id
                FROM text_sheet_jobs
                WHERE project_id = ? AND status = 'running'
                ORDER BY source_row_index ASC
                """,
                (project_id,),
            ).fetchall()
    return [str(row["job_id"]) for row in rows]


def normalize_status(value: Any) -> str:
    raw = str(value or "queued").strip().lower().replace("-", "_")
    if raw in {"complete", "completed", "done"}:
        return "completed"
    if raw in {"failed", "error"}:
        return "failed"
    if raw in {"running", "rq_screening", "openai_running"}:
        return "running"
    if raw in {"not_run", "not_started", "unprocessed"}:
        return "not_run"
    return "queued"


def _source_row_values(project_id: str, source_id: str, row_order: int, payload: dict[str, Any]) -> tuple[Any, ...]:
    fields = payload.get("selected_fields") if isinstance(payload.get("selected_fields"), list) else []
    mapped_cells: dict[str, str] = {}
    preview = ""
    for field in fields:
        if not isinstance(field, dict):
            continue
        column_name = str(field.get("column_name") or "").strip()
        if not column_name:
            continue
        value = _bounded(str(field.get("value") or ""), TEXT_INDEX_CELL_VALUE_LIMIT)
        mapped_cells[column_name] = value
        if not preview and value.strip():
            preview = value.strip()[:180]
    row_display_number = _as_int(payload.get("row_display_number"), row_order + 1)
    return (
        project_id,
        source_id,
        _as_int(payload.get("source_row_index"), row_order),
        row_order,
        row_display_number,
        str(payload.get("record_id") or f"Row {row_display_number}"),
        preview or f"Row {row_display_number}",
        json.dumps(mapped_cells, ensure_ascii=False, separators=(",", ":")),
    )


def _insert_source_rows(connection: sqlite3.Connection, rows: list[tuple[Any, ...]]) -> None:
    connection.executemany(
        """
        INSERT INTO text_source_rows (
            project_id, source_id, source_row_index, row_order,
            row_display_number, record_id, input_preview, mapped_cells_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _job_values(project_id: str, entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(entry.get("job_id") or ""),
        project_id,
        str(entry.get("sheet_id") or ""),
        str(entry.get("source_id") or ""),
        _as_int(entry.get("source_row_index"), 0),
        str(entry.get("model") or ""),
        str(entry.get("prompt") or ""),
        normalize_status(entry.get("status")),
        str(entry.get("stage") or ""),
        str(entry.get("message") or ""),
        str(entry.get("error") or ""),
        str(entry.get("started_at") or ""),
        str(entry.get("completed_at") or ""),
        entry.get("duration_seconds"),
        _bounded(str(entry.get("result_preview") or ""), TEXT_INDEX_CELL_VALUE_LIMIT),
        str(entry.get("updated_at") or _utc_now()),
    )


def _row_filters(
    project_id: str,
    sheet_id: str,
    source_id: str,
    status: str,
    search: str,
) -> tuple[str, list[Any]]:
    clauses = ["source.project_id = ?", "source.source_id = ?"]
    parameters: list[Any] = [project_id, source_id]
    normalized_status = normalize_status(status) if str(status or "").strip().lower() != "all" else "all"
    if normalized_status != "all":
        clauses.append("COALESCE(job.status, 'not_run') = ?")
        parameters.append(normalized_status)
    query = str(search or "").strip().lower()
    if query:
        pattern = f"%{_escape_like(query)}%"
        clauses.append(
            "("
            "LOWER(source.record_id) LIKE ? ESCAPE '\\' OR "
            "LOWER(source.input_preview) LIKE ? ESCAPE '\\' OR "
            "LOWER(source.mapped_cells_json) LIKE ? ESCAPE '\\' OR "
            "LOWER(COALESCE(job.job_id, '')) LIKE ? ESCAPE '\\'"
            ")"
        )
        parameters.extend([pattern, pattern, pattern, pattern])
    return " AND ".join(clauses), parameters


def _serialize_row(row: sqlite3.Row, project_id: str) -> dict[str, Any]:
    status = normalize_status(row["status"] if row["job_id"] else "not_run")
    try:
        mapped_cells = json.loads(row["mapped_cells_json"] or "{}")
    except json.JSONDecodeError:
        mapped_cells = {}
    return {
        "job_id": str(row["job_id"] or ""),
        "project_id": project_id,
        "row": _as_int(row["row_display_number"], 0),
        "row_order": _as_int(row["row_order"], 0),
        "source_row_index": _as_int(row["source_row_index"], 0),
        "status": status,
        "status_label": _status_label(status),
        "stage": str(row["stage"] or ""),
        "message": str(row["message"] or ""),
        "error": str(row["error"] or ""),
        "record_id": str(row["record_id"] or ""),
        "input_preview": str(row["input_preview"] or ""),
        "mapped_cells": mapped_cells if isinstance(mapped_cells, dict) else {},
        "model": str(row["model"] or ""),
        "prompt": str(row["prompt"] or ""),
        "started_at": str(row["started_at"] or ""),
        "completed_at": str(row["completed_at"] or ""),
        "duration_seconds": row["duration_seconds"],
        "result_preview": str(row["result_preview"] or ""),
    }


@contextmanager
def _connection(project_id: str) -> Iterator[sqlite3.Connection]:
    path = database_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        _ensure_schema(connection)
        yield connection
    finally:
        connection.close()


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS text_source_rows (
            project_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_row_index INTEGER NOT NULL,
            row_order INTEGER NOT NULL,
            row_display_number INTEGER NOT NULL,
            record_id TEXT NOT NULL,
            input_preview TEXT NOT NULL,
            mapped_cells_json TEXT NOT NULL,
            PRIMARY KEY (project_id, source_id, source_row_index)
        );
        CREATE INDEX IF NOT EXISTS text_source_rows_order_idx
            ON text_source_rows (project_id, source_id, row_order);
        CREATE TABLE IF NOT EXISTS text_source_index_meta (
            project_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            schema_version INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (project_id, source_id)
        );
        CREATE TABLE IF NOT EXISTS text_sheet_jobs (
            job_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            sheet_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_row_index INTEGER NOT NULL,
            model TEXT NOT NULL,
            prompt TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT NOT NULL,
            message TEXT NOT NULL,
            error TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            duration_seconds REAL,
            result_preview TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (project_id, sheet_id, source_id, source_row_index)
        );
        CREATE INDEX IF NOT EXISTS text_sheet_jobs_lookup_idx
            ON text_sheet_jobs (project_id, sheet_id, source_id, source_row_index);
        CREATE INDEX IF NOT EXISTS text_sheet_jobs_status_idx
            ON text_sheet_jobs (project_id, sheet_id, status);
        """
    )


def _project_lock(project_id: str) -> threading.RLock:
    safe_project_id = projects.validate_project_id(project_id)
    with _LOCK_GUARD:
        lock = _PROJECT_LOCKS.get(safe_project_id)
        if lock is None:
            lock = threading.RLock()
            _PROJECT_LOCKS[safe_project_id] = lock
        return lock


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _bounded(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[:limit]}..."


def _as_int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _status_label(status: str) -> str:
    return {
        "not_run": "Not run",
        "completed": "Completed",
        "running": "Running",
        "queued": "Queued",
        "failed": "Failed",
    }.get(status, "Queued")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
