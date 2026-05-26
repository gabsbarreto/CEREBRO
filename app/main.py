from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app import config
from app.models import JobSettings, public_model_presets
from app.services import jobs
from app.services.excel_summary import rebuild_summary_from_jobs
from app.services.job_queue import JobQueue
from app.services.local_inference_worker import local_inference_worker
from app.services.rq_prompt import list_prompt_files, read_prompt_file, save_prompt_file

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Local RQ Screening")
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
templates = Jinja2Templates(directory=config.TEMPLATES_DIR)
job_queue = JobQueue()


@app.on_event("startup")
async def restore_queued_jobs() -> None:
    local_inference_worker.terminate_stale_external_worker()
    job_queue.enqueue_existing_queued_jobs()


@app.on_event("shutdown")
async def stop_local_inference_worker() -> None:
    local_inference_worker.stop()


@app.get("/", response_class=HTMLResponse)
async def index() -> RedirectResponse:
    return RedirectResponse(url="/rq-screening")


@app.get("/rq-screening", response_class=HTMLResponse)
async def rq_screening(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "rq_screening.html",
        context={
            "request": request,
            "defaults": {
                "ocr_dpi": config.DEFAULT_OCR_DPI,
                "ocr_batch_size": config.DEFAULT_OCR_BATCH_SIZE,
                "deepseek_ocr_model_path": "",
                "rq_model_preset": "qwen35_9b_8bit_reasoning",
            },
            "model_presets": public_model_presets(),
        },
    )


@app.post("/api/jobs")
async def create_job(
    pdfs: list[UploadFile] | None = File(None),
    pdf: UploadFile | None = File(None),
    pdf_relative_paths: list[str] | None = Form(None),
    ocr_dpi: int = Form(config.DEFAULT_OCR_DPI),
    ocr_batch_size: int = Form(config.DEFAULT_OCR_BATCH_SIZE),
    deepseek_ocr_model_path: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    openai_input_mode: str = Form("ocr_text"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
    rerun_existing: bool = Form(False),
) -> JSONResponse:
    settings = settings_from_form(
        ocr_dpi=ocr_dpi,
        ocr_batch_size=ocr_batch_size,
        deepseek_ocr_model_path=deepseek_ocr_model_path,
        rq_model_preset=rq_model_preset,
        openai_api_key=openai_api_key,
        openai_input_mode=openai_input_mode,
        rq_prompt_filename=rq_prompt_filename,
        rq_system_prompt=rq_system_prompt,
    )

    pdf_uploads = validated_pdf_uploads(pdfs, pdf)
    upload_relative_paths = normalized_relative_paths(pdf_uploads, pdf_relative_paths)

    queued_jobs: list[dict[str, str]] = []
    rerun_job_ids: set[str] = set()
    for upload, relative_path in zip(pdf_uploads, upload_relative_paths):
        filename = upload_display_filename(upload)
        existing = jobs.find_screened_job_by_run_identity(
            filename,
            settings.rq_prompt_filename,
            settings.rq_screening_model,
            settings.openai_input_mode,
        )
        if existing is not None:
            if not rerun_existing:
                continue
            existing_job_id = str(existing["job_id"])
            if existing_job_id in rerun_job_ids:
                continue
            job_queue.enqueue_screening_rerun(existing_job_id, settings)
            rerun_job_ids.add(existing_job_id)
            queued_jobs.append(
                {
                    "job_id": existing_job_id,
                    "filename": str(existing.get("filename") or filename),
                    "rerun_existing": "true",
                    "prompt_filename": settings.rq_prompt_filename,
                    "model": settings.rq_screening_model,
                    "openai_input_mode": settings.openai_input_mode,
                }
            )
            logger.info("Queued RQ screening rerun job %s for %s", existing_job_id, filename)
            continue
        reusable_ocr = jobs.find_reusable_ocr_job_by_filename(filename)
        job_id = jobs.new_job_id()
        root = jobs.create_job(job_id, filename, settings)
        dest = root / "input" / "uploaded.pdf"
        jobs.save_upload(upload.file, dest)
        pdf_sha256 = jobs.file_sha256(dest)
        jobs.update_metadata(
            root,
            uploaded_pdf=str(dest),
            pdf_sha256=pdf_sha256,
            source_relative_path=relative_path,
            source_folder=source_folder_from_relative_path(relative_path),
        )
        reusable_openai_file = (
            jobs.find_reusable_openai_file_job(pdf_sha256, filename)
            if settings.rq_provider == "openai" and settings.openai_input_mode == "pdf_file"
            else None
        )
        if reusable_openai_file is not None:
            jobs.copy_reusable_openai_file(str(reusable_openai_file["job_id"]), root)
        elif reusable_ocr is not None and settings.openai_input_mode != "pdf_file":
            jobs.copy_reusable_ocr(str(reusable_ocr["job_id"]), root)
        job_queue.enqueue(job_id, settings)
        queued_jobs.append(
            {
                "job_id": job_id,
                "filename": filename,
                "prompt_filename": settings.rq_prompt_filename,
                "model": settings.rq_screening_model,
                "openai_input_mode": settings.openai_input_mode,
                "reuses_ocr": "true" if reusable_ocr is not None and settings.openai_input_mode != "pdf_file" else "false",
                "reuses_openai_file": "true" if reusable_openai_file is not None else "false",
            }
        )
        logger.info("Queued RQ screening job %s for %s", job_id, filename)

    if not queued_jobs:
        return JSONResponse({"job_id": None, "job_ids": [], "jobs": [], "count": 0})

    return JSONResponse(
        {
            "job_id": queued_jobs[0]["job_id"],
            "job_ids": [job["job_id"] for job in queued_jobs],
            "jobs": queued_jobs,
            "count": len(queued_jobs),
        }
    )


@app.post("/api/jobs/check-existing")
async def check_existing_jobs(
    pdfs: list[UploadFile] | None = File(None),
    pdf: UploadFile | None = File(None),
    pdf_relative_paths: list[str] | None = Form(None),
    ocr_dpi: int = Form(config.DEFAULT_OCR_DPI),
    ocr_batch_size: int = Form(config.DEFAULT_OCR_BATCH_SIZE),
    deepseek_ocr_model_path: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    openai_input_mode: str = Form("ocr_text"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    settings = settings_from_form(
        ocr_dpi=ocr_dpi,
        ocr_batch_size=ocr_batch_size,
        deepseek_ocr_model_path=deepseek_ocr_model_path,
        rq_model_preset=rq_model_preset,
        openai_api_key=openai_api_key,
        openai_input_mode=openai_input_mode,
        rq_prompt_filename=rq_prompt_filename,
        rq_system_prompt=rq_system_prompt,
    )
    pdf_uploads = validated_pdf_uploads(pdfs, pdf)
    upload_relative_paths = normalized_relative_paths(pdf_uploads, pdf_relative_paths)
    duplicates: list[dict[str, str]] = []
    fresh: list[dict[str, str]] = []
    for upload, relative_path in zip(pdf_uploads, upload_relative_paths):
        filename = upload_display_filename(upload)
        existing = jobs.find_screened_job_by_run_identity(
            filename,
            settings.rq_prompt_filename,
            settings.rq_screening_model,
            settings.openai_input_mode,
        )
        if existing is None:
            fresh.append({"filename": filename, "source_relative_path": relative_path})
            continue
        existing_job_id = str(existing["job_id"])
        metadata = existing.get("metadata") or {}
        duplicates.append(
            {
                "filename": filename,
                "source_relative_path": relative_path,
                "existing_job_id": existing_job_id,
                "existing_filename": str(existing.get("filename") or ""),
                "prompt_filename": str(metadata.get("rq_prompt_filename") or settings.rq_prompt_filename),
                "model": str(metadata.get("rq_screening_model") or settings.rq_screening_model),
                "openai_input_mode": str(metadata.get("openai_input_mode") or settings.openai_input_mode),
            }
        )
    return JSONResponse(
        {
            "has_duplicates": bool(duplicates),
            "duplicates": duplicates,
            "fresh": fresh,
            "duplicate_count": len(duplicates),
            "fresh_count": len(fresh),
        }
    )


@app.get("/api/rq-prompt")
async def get_rq_prompt() -> JSONResponse:
    prompt = read_prompt_file()
    return JSONResponse({"prompt": prompt, "prompts": list_prompt_files()})


@app.post("/api/rq-prompt")
async def save_rq_prompt(filename: str = Form(...), system_prompt: str = Form(...)) -> JSONResponse:
    try:
        prompt = save_prompt_file(filename, system_prompt)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return JSONResponse({"prompt": prompt, "prompts": list_prompt_files()})


@app.get("/api/rq-prompts")
async def list_rq_prompts() -> JSONResponse:
    return JSONResponse({"prompts": list_prompt_files()})


@app.get("/api/rq-prompts/{filename}")
async def get_rq_prompt_file(filename: str) -> JSONResponse:
    try:
        return JSONResponse({"prompt": read_prompt_file(filename), "prompts": list_prompt_files()})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/api/jobs")
async def list_jobs(limit: int = 200) -> JSONResponse:
    job_queue.mark_stale_running_jobs_failed()
    return JSONResponse({"jobs": jobs.list_jobs(limit=limit)})


@app.get("/api/queue")
async def queue_status() -> JSONResponse:
    return JSONResponse(job_queue.status())


@app.post("/api/queue/pause")
async def pause_queue() -> JSONResponse:
    return JSONResponse(job_queue.pause())


@app.post("/api/queue/resume")
async def resume_queue(
    preserve_settings: bool = Form(False),
    ocr_dpi: int = Form(config.DEFAULT_OCR_DPI),
    ocr_batch_size: int = Form(config.DEFAULT_OCR_BATCH_SIZE),
    deepseek_ocr_model_path: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    openai_input_mode: str = Form("ocr_text"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    if preserve_settings:
        return JSONResponse(job_queue.resume())
    settings = settings_from_form(
        ocr_dpi=ocr_dpi,
        ocr_batch_size=ocr_batch_size,
        deepseek_ocr_model_path=deepseek_ocr_model_path,
        rq_model_preset=rq_model_preset,
        openai_api_key=openai_api_key,
        openai_input_mode=openai_input_mode,
        rq_prompt_filename=rq_prompt_filename,
        rq_system_prompt=rq_system_prompt,
    )
    return JSONResponse(job_queue.resume(settings_override=settings))


@app.post("/api/queue/retry-failed")
async def retry_failed_jobs() -> JSONResponse:
    result = job_queue.retry_failed()
    requeued_jobs = result["jobs"]
    return JSONResponse(
        {
            "requeued": len(requeued_jobs),
            "jobs": requeued_jobs,
            "skipped": result["skipped"],
            **job_queue.status(),
        }
    )


@app.post("/api/jobs/{job_id}/rerun")
async def rerun_job_screening(
    job_id: str,
    ocr_dpi: int = Form(config.DEFAULT_OCR_DPI),
    ocr_batch_size: int = Form(config.DEFAULT_OCR_BATCH_SIZE),
    deepseek_ocr_model_path: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    openai_input_mode: str = Form("ocr_text"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    root = jobs.job_dir(job_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    if job_id in job_queue.active_job_ids():
        raise HTTPException(status_code=409, detail="Job is already queued or running.")
    settings = settings_from_form(
        ocr_dpi=ocr_dpi,
        ocr_batch_size=ocr_batch_size,
        deepseek_ocr_model_path=deepseek_ocr_model_path,
        rq_model_preset=rq_model_preset,
        openai_api_key=openai_api_key,
        openai_input_mode=openai_input_mode,
        rq_prompt_filename=rq_prompt_filename,
        rq_system_prompt=rq_system_prompt,
    )
    merged_text = root / "outputs" / "merged_full_text.txt"
    has_reusable_ocr = merged_text.exists() and len(merged_text.read_text(encoding="utf-8").strip()) >= 20
    if settings.openai_input_mode == "pdf_file" and settings.rq_provider == "openai":
        if not (root / "input" / "uploaded.pdf").exists():
            raise HTTPException(status_code=400, detail="This job has no reusable PDF file.")
    elif not has_reusable_ocr:
        raise HTTPException(
            status_code=400,
            detail="This job has no reusable OCR text yet. Run the full PDF workflow first.",
        )
    if not jobs.job_matches_run_identity(root, settings):
        try:
            child_job_id, _child_root = jobs.create_screening_rerun_child_job(job_id, settings)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        job_queue.enqueue(child_job_id, settings)
        refreshed = {item["job_id"]: item for item in jobs.list_jobs(limit=0)}
        record = refreshed.get(child_job_id)
        return JSONResponse(
            {
                "job": record,
                "created_new_job": True,
                "source_job_id": job_id,
                "prompt_filename": settings.rq_prompt_filename,
                "model": settings.rq_screening_model,
                "openai_input_mode": settings.openai_input_mode,
                **job_queue.status(),
            }
        )

    record = job_queue.enqueue_screening_rerun(job_id, settings)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"job": record, "created_new_job": False, **job_queue.status()})


@app.post("/api/queue/clean")
async def clean_queue() -> JSONResponse:
    removed = job_queue.clean_queued()
    return JSONResponse({"removed": len(removed), "jobs": removed, **job_queue.status()})


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str) -> JSONResponse:
    root = jobs.job_dir(job_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    if job_id in job_queue.active_job_ids():
        raise HTTPException(status_code=409, detail="Job is queued or running and cannot be deleted.")
    jobs.delete_job(job_id)
    return JSONResponse({"deleted": True, "job_id": job_id, **job_queue.status()})


@app.get("/api/jobs/{job_id}/status")
async def job_status(job_id: str) -> JSONResponse:
    try:
        return JSONResponse(jobs.read_status(job_id))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/jobs/{job_id}/result")
async def job_result(job_id: str) -> JSONResponse:
    root = jobs.job_dir(job_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    status = jobs.read_status(job_id)
    metadata = jobs.read_metadata(root)
    output = read_text_if_exists(root / "outputs" / "rq_screening_output.md")
    merged = read_text_if_exists(root / "outputs" / "merged_full_text.txt")
    prompt = read_text_if_exists(root / "outputs" / "rq_prompt.txt")
    system_prompt = read_text_if_exists(root / "outputs" / "rq_system_prompt.txt")
    user_prompt = read_text_if_exists(root / "outputs" / "rq_user_prompt.txt")
    return JSONResponse(
        {
            "status": status,
            "metadata": metadata,
            "output": output,
            "merged_full_text": merged,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "job_dir": str(root),
        }
    )


@app.get("/api/jobs/{job_id}/download")
async def download_result(job_id: str) -> FileResponse:
    output = jobs.job_dir(job_id) / "outputs" / "rq_screening_output.md"
    if not output.exists():
        raise HTTPException(status_code=404, detail="Result is not available yet")
    return FileResponse(output, media_type="text/markdown", filename=f"{job_id}_rq_screening.md")


@app.get("/api/reports/excel")
async def download_excel_report() -> FileResponse:
    try:
        path = rebuild_summary_from_jobs()
    except Exception as exc:
        logger.exception("Failed to build Excel report")
        raise HTTPException(status_code=500, detail=f"Failed to build Excel report: {exc}")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Excel report is not available.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def settings_from_form(
    *,
    ocr_dpi: int,
    ocr_batch_size: int,
    deepseek_ocr_model_path: str,
    rq_model_preset: str,
    openai_api_key: str,
    openai_input_mode: str,
    rq_prompt_filename: str,
    rq_system_prompt: str,
) -> JobSettings:
    return JobSettings.from_form(
        {
            "ocr_dpi": ocr_dpi,
            "ocr_batch_size": ocr_batch_size,
            "deepseek_ocr_model_path": deepseek_ocr_model_path,
            "rq_model_preset": rq_model_preset,
            "openai_api_key": openai_api_key,
            "openai_input_mode": openai_input_mode,
            "rq_prompt_filename": rq_prompt_filename,
            "rq_system_prompt": rq_system_prompt,
        }
    )


def validated_pdf_uploads(
    pdfs: list[UploadFile] | None,
    pdf: UploadFile | None,
) -> list[UploadFile]:
    uploads = list(pdfs or [])
    if pdf is not None:
        uploads.append(pdf)
    pdf_uploads = [upload for upload in uploads if _is_pdf_upload(upload)]
    if not pdf_uploads:
        raise HTTPException(status_code=400, detail="Upload at least one PDF file.")
    if len(pdf_uploads) != len(uploads):
        raise HTTPException(status_code=400, detail="All uploaded files must be PDFs.")
    return pdf_uploads


def normalized_relative_paths(uploads: list[UploadFile], relative_paths: list[str] | None) -> list[str]:
    raw_paths = list(relative_paths or [])
    normalized: list[str] = []
    for index, upload in enumerate(uploads):
        candidate = raw_paths[index] if index < len(raw_paths) else upload.filename or ""
        normalized.append(str(candidate or "").replace("\\", "/").strip())
    return normalized


def upload_display_filename(upload: UploadFile) -> str:
    return Path(upload.filename or "uploaded.pdf").name or "uploaded.pdf"


def source_folder_from_relative_path(relative_path: str) -> str:
    parent = Path(str(relative_path or "").replace("\\", "/")).parent
    if str(parent) in {"", "."}:
        return ""
    return str(parent).replace("\\", "/")


def _is_pdf_upload(upload: UploadFile) -> bool:
    filename = upload.filename or ""
    if not filename.lower().endswith(".pdf"):
        return False
    return upload.content_type in {
        "application/pdf",
        "application/x-pdf",
        "application/octet-stream",
        "",
        None,
    }
