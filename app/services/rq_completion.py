from __future__ import annotations

import logging
import time
from pathlib import Path

from app.models import JobSettings
from app.services import jobs
from app.services.excel_summary import append_summary_row

logger = logging.getLogger(__name__)


def complete_screening_job(
    *,
    job_id: str,
    settings: JobSettings,
    started_at: float,
    prompt_filename: str,
    prompt_source_path: str,
    system_prompt_file: Path,
    user_prompt_file: Path,
    output_file: Path,
    pdf_path: Path,
) -> None:
    completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    duration_seconds = round(time.time() - started_at, 2)
    root = jobs.job_dir(job_id)
    metadata = jobs.read_metadata(root)
    original_filename = str(metadata.get("original_filename") or pdf_path.name)
    llm_output = output_file.read_text(encoding="utf-8")
    try:
        summary_path = append_summary_row(
            job_id=job_id,
            filename=original_filename,
            inferenced_at=completed_at,
            duration_seconds=duration_seconds,
            llm_model=settings.rq_screening_model,
            llm_output=llm_output,
            prompt=prompt_filename,
        )
    except Exception as exc:
        logger.exception("Failed to append Excel summary for job %s", job_id)
        jobs.append_warning(root, f"Excel summary append failed: {exc}")
        summary_path = None

    jobs.update_metadata(
        root,
        completed_at=completed_at,
        duration_seconds=duration_seconds,
        **jobs.settings_metadata_updates(
            settings,
            rq_prompt_filename=prompt_filename,
            include_settings=False,
        ),
        rq_prompt_source_path=prompt_source_path,
        rq_system_prompt_file=str(system_prompt_file),
        rq_user_prompt_file=str(user_prompt_file),
        summary_xlsx_path=str(summary_path) if summary_path is not None else None,
        pending_rerun_screening_only=False,
        rerun_reuses_ocr=False,
        ocr_complete=settings.openai_input_mode != "pdf_file",
        openai_file_complete=settings.rq_provider == "openai" and settings.openai_input_mode == "pdf_file",
    )
    jobs.update_status(
        job_id,
        status="complete",
        stage="complete",
        message="Screening complete",
        progress=1.0,
        event={"event": "complete"},
    )
