from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from app import config
from app.models import JobSettings, public_model_presets
from app.services import jobs, projects, structured_extraction, text_extraction
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
    projects.migrate_legacy_jobs_if_needed()
    local_inference_worker.terminate_stale_external_worker()
    job_queue.enqueue_existing_queued_jobs()
    text_extraction.text_job_queue.enqueue_existing_queued_jobs()


@app.on_event("shutdown")
async def stop_local_inference_worker() -> None:
    local_inference_worker.stop()


@app.get("/", response_class=HTMLResponse)
async def index(project_id: str = "") -> RedirectResponse:
    project = selected_project_or_default(project_id)
    return RedirectResponse(url=projects.project_dashboard_path(project))


@app.get("/rq-screening", response_class=HTMLResponse)
async def rq_screening(request: Request, project_id: str = "") -> HTMLResponse:
    current_project = selected_project_or_default(project_id)
    if projects.normalize_extraction_type(current_project.get("extraction_type")) != "pdf":
        return RedirectResponse(url=projects.project_dashboard_path(current_project))  # type: ignore[return-value]
    return templates.TemplateResponse(
        request,
        "rq_screening.html",
        context={
            "request": request,
            "current_project": current_project,
            "projects": projects.list_projects(),
            "defaults": {
                "ocr_dpi": config.DEFAULT_OCR_DPI,
                "ocr_batch_size": config.DEFAULT_OCR_BATCH_SIZE,
                "deepseek_ocr_model_path": "",
                "rq_model_preset": "qwen35_9b_8bit_reasoning",
            },
            "model_presets": public_model_presets(),
        },
    )


@app.get("/text", response_class=HTMLResponse)
async def text_extraction_screen(request: Request, project_id: str = "") -> HTMLResponse:
    current_project = selected_project_or_default(project_id)
    if projects.normalize_extraction_type(current_project.get("extraction_type")) != "text":
        return RedirectResponse(url=projects.project_dashboard_path(current_project))  # type: ignore[return-value]
    return templates.TemplateResponse(
        request,
        "text_extraction.html",
        context={
            "request": request,
            "current_project": current_project,
            "projects": projects.list_projects(),
            "defaults": {
                "rq_model_preset": "qwen35_9b_8bit_reasoning",
            },
            "model_presets": public_model_presets(),
        },
    )


@app.get("/structured-pdf", response_class=HTMLResponse)
async def structured_pdf_screen(request: Request, project_id: str = "") -> HTMLResponse:
    current_project = selected_project_or_default(project_id)
    if projects.normalize_extraction_type(current_project.get("extraction_type")) != "pdf_structured":
        return RedirectResponse(url=projects.project_dashboard_path(current_project))  # type: ignore[return-value]
    return templates.TemplateResponse(
        request,
        "structured_pdf.html",
        context={
            "request": request,
            "current_project": current_project,
            "projects": projects.list_projects(),
            "defaults": {
                "ocr_dpi": config.DEFAULT_OCR_DPI,
                "ocr_batch_size": config.DEFAULT_OCR_BATCH_SIZE,
                "deepseek_ocr_model_path": "",
                "rq_model_preset": "qwen35_9b_8bit_reasoning",
            },
            "model_presets": public_model_presets(),
        },
    )


@app.get("/projects/new", response_class=HTMLResponse)
async def new_project_form(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "project_new.html",
        context={"request": request, "projects": projects.list_projects()},
    )


@app.post("/projects/new")
async def create_project_form(
    project_name: str = Form(...),
    description: str = Form(""),
    extraction_type: str = Form(projects.DEFAULT_EXTRACTION_TYPE),
) -> RedirectResponse:
    try:
        project = projects.create_project(project_name, description, extraction_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=projects.project_dashboard_path(project), status_code=303)


@app.get("/api/projects")
async def api_list_projects() -> JSONResponse:
    return JSONResponse({"projects": projects.list_projects(), "default_project": projects.get_default_project()})


@app.post("/api/projects")
async def api_create_project(
    name: str = Form(...),
    description: str = Form(""),
    extraction_type: str = Form(projects.DEFAULT_EXTRACTION_TYPE),
) -> JSONResponse:
    try:
        project = projects.create_project(name, description, extraction_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "projects": projects.list_projects()})


@app.post("/api/jobs")
async def create_job(
    pdfs: list[UploadFile] | None = File(None),
    pdf: UploadFile | None = File(None),
    pdf_relative_paths: list[str] | None = Form(None),
    project_id: str = Form(""),
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
    current_project = selected_project_or_default(project_id)
    active_project_id = str(current_project["project_id"])
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
            project_id=active_project_id,
        )
        if existing is not None:
            if not rerun_existing:
                continue
            existing_job_id = str(existing["job_id"])
            if existing_job_id in rerun_job_ids:
                continue
            job_queue.enqueue_screening_rerun(existing_job_id, settings, project_id=active_project_id)
            rerun_job_ids.add(existing_job_id)
            queued_jobs.append(
                {
                    "job_id": existing_job_id,
                    "filename": str(existing.get("filename") or filename),
                    "rerun_existing": "true",
                    "prompt_filename": settings.rq_prompt_filename,
                    "model": settings.rq_screening_model,
                    "openai_input_mode": settings.openai_input_mode,
                    "project_id": active_project_id,
                }
            )
            logger.info("Queued RQ screening rerun job %s for %s", existing_job_id, filename)
            continue
        reusable_ocr = jobs.find_reusable_ocr_job_by_filename(filename, project_id=active_project_id)
        job_id = jobs.new_job_id()
        root = jobs.create_job(job_id, filename, settings, project_id=active_project_id)
        dest = root / "input" / "uploaded.pdf"
        jobs.save_upload(upload.file, dest)
        pdf_sha256 = jobs.file_sha256(dest)
        jobs.update_metadata(
            root,
            uploaded_pdf=str(dest),
            pdf_sha256=pdf_sha256,
            source_relative_path=relative_path,
            source_folder=source_folder_from_relative_path(relative_path),
            project_id=active_project_id,
        )
        reusable_openai_file = (
            jobs.find_reusable_openai_file_job(pdf_sha256, filename, project_id=active_project_id)
            if settings.rq_provider == "openai" and settings.openai_input_mode == "pdf_file"
            else None
        )
        if reusable_openai_file is not None:
            jobs.copy_reusable_openai_file(str(reusable_openai_file["job_id"]), root, source_project_id=active_project_id)
        elif reusable_ocr is not None and settings.openai_input_mode != "pdf_file":
            jobs.copy_reusable_ocr(str(reusable_ocr["job_id"]), root, source_project_id=active_project_id)
        job_queue.enqueue(job_id, settings, project_id=active_project_id)
        queued_jobs.append(
            {
                "job_id": job_id,
                "filename": filename,
                "prompt_filename": settings.rq_prompt_filename,
                "model": settings.rq_screening_model,
                "openai_input_mode": settings.openai_input_mode,
                "project_id": active_project_id,
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
    project_id: str = Form(""),
    ocr_dpi: int = Form(config.DEFAULT_OCR_DPI),
    ocr_batch_size: int = Form(config.DEFAULT_OCR_BATCH_SIZE),
    deepseek_ocr_model_path: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    openai_input_mode: str = Form("ocr_text"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    current_project = selected_project_or_default(project_id)
    active_project_id = str(current_project["project_id"])
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
            project_id=active_project_id,
        )
        if existing is None:
            fresh.append({"filename": filename, "source_relative_path": relative_path, "project_id": active_project_id})
            continue
        existing_job_id = str(existing["job_id"])
        metadata = existing.get("metadata") or {}
        duplicates.append(
            {
                "filename": filename,
                "source_relative_path": relative_path,
                "project_id": active_project_id,
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
async def list_jobs(limit: int = 200, project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    job_queue.mark_stale_running_jobs_failed(project_id=active_project_id)
    return JSONResponse({"jobs": jobs.list_jobs(limit=limit, project_id=active_project_id), "project": project})


@app.get("/api/queue")
async def queue_status(project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    return JSONResponse(job_queue.status(project_id=str(project["project_id"])))


@app.post("/api/queue/pause")
async def pause_queue(project_id: str = Form("")) -> JSONResponse:
    project = selected_project_or_default(project_id)
    return JSONResponse(job_queue.pause(project_id=str(project["project_id"])))


@app.post("/api/queue/resume")
async def resume_queue(
    preserve_settings: bool = Form(False),
    project_id: str = Form(""),
    ocr_dpi: int = Form(config.DEFAULT_OCR_DPI),
    ocr_batch_size: int = Form(config.DEFAULT_OCR_BATCH_SIZE),
    deepseek_ocr_model_path: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    openai_input_mode: str = Form("ocr_text"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    if preserve_settings:
        return JSONResponse(job_queue.resume(project_id=active_project_id))
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
    return JSONResponse(job_queue.resume(settings_override=settings, project_id=active_project_id))


@app.post("/api/queue/retry-failed")
async def retry_failed_jobs(project_id: str = Form("")) -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    result = job_queue.retry_failed(project_id=active_project_id)
    requeued_jobs = result["jobs"]
    return JSONResponse(
        {
            "requeued": len(requeued_jobs),
            "jobs": requeued_jobs,
            "skipped": result["skipped"],
            **job_queue.status(project_id=active_project_id),
        }
    )


@app.post("/api/jobs/{job_id}/rerun")
async def rerun_job_screening(
    job_id: str,
    project_id: str = Form(""),
    ocr_dpi: int = Form(config.DEFAULT_OCR_DPI),
    ocr_batch_size: int = Form(config.DEFAULT_OCR_BATCH_SIZE),
    deepseek_ocr_model_path: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    openai_input_mode: str = Form("ocr_text"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    root = jobs.job_dir(job_id, active_project_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    if job_id in job_queue.active_job_ids(project_id=active_project_id):
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
            child_job_id, _child_root = jobs.create_screening_rerun_child_job(job_id, settings, project_id=active_project_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        job_queue.enqueue(child_job_id, settings, project_id=active_project_id)
        refreshed = {item["job_id"]: item for item in jobs.list_jobs(limit=0, project_id=active_project_id)}
        record = refreshed.get(child_job_id)
        return JSONResponse(
            {
                "job": record,
                "created_new_job": True,
                "source_job_id": job_id,
                "prompt_filename": settings.rq_prompt_filename,
                "model": settings.rq_screening_model,
                "openai_input_mode": settings.openai_input_mode,
                "project_id": active_project_id,
                **job_queue.status(project_id=active_project_id),
            }
        )

    record = job_queue.enqueue_screening_rerun(job_id, settings, project_id=active_project_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JSONResponse({"job": record, "created_new_job": False, **job_queue.status(project_id=active_project_id)})


@app.post("/api/queue/clean")
async def clean_queue(project_id: str = Form("")) -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    removed = job_queue.clean_queued(project_id=active_project_id)
    return JSONResponse({"removed": len(removed), "jobs": removed, **job_queue.status(project_id=active_project_id)})


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    root = jobs.job_dir(job_id, active_project_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    if job_id in job_queue.active_job_ids(project_id=active_project_id):
        raise HTTPException(status_code=409, detail="Job is queued or running and cannot be deleted.")
    jobs.delete_job(job_id, project_id=active_project_id)
    return JSONResponse({"deleted": True, "job_id": job_id, **job_queue.status(project_id=active_project_id)})


@app.get("/api/jobs/{job_id}/status")
async def job_status(job_id: str, project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    try:
        return JSONResponse(jobs.read_status(job_id, project_id=str(project["project_id"])))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Job not found")


@app.get("/api/jobs/{job_id}/result")
async def job_result(job_id: str, project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    root = jobs.job_dir(job_id, str(project["project_id"]))
    if not root.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    status = jobs.read_status(job_id, project_id=str(project["project_id"]))
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
async def download_result(job_id: str, project_id: str = "") -> FileResponse:
    project = selected_project_or_default(project_id)
    output = jobs.job_dir(job_id, str(project["project_id"])) / "outputs" / "rq_screening_output.md"
    if not output.exists():
        raise HTTPException(status_code=404, detail="Result is not available yet")
    return FileResponse(output, media_type="text/markdown", filename=f"{job_id}_rq_screening.md")


@app.get("/api/reports/excel")
async def download_excel_report(project_id: str = "") -> FileResponse:
    project = selected_project_or_default(project_id)
    try:
        path = rebuild_summary_from_jobs(project_id=str(project["project_id"]))
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


@app.get("/api/structured/sheets")
async def structured_sheets(project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        sheets = structured_extraction.list_sheets(str(project["project_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "sheets": sheets})


@app.post("/api/structured/sheets")
async def create_structured_sheet(
    project_id: str = Form(""),
    name: str = Form(...),
    context: str = Form(""),
    row_unit: str = Form(""),
    columns: str = Form("[]"),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        sheet = structured_extraction.create_sheet(
            project_id=str(project["project_id"]),
            name=name,
            context=context,
            row_unit=row_unit,
            columns=parse_structured_columns(columns),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "sheet": sheet, "sheets": structured_extraction.list_sheets(str(project["project_id"]))})


@app.post("/api/structured/workbook/duplicate")
async def duplicate_structured_workbook(
    project_id: str = Form(""),
    sheet_ids: str = Form(...),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        parsed_sheet_ids = json.loads(sheet_ids)
        if not isinstance(parsed_sheet_ids, list) or not all(isinstance(sheet_id, str) for sheet_id in parsed_sheet_ids):
            raise ValueError("Selected sheet ids must be a JSON list of strings.")
        payload = structured_extraction.duplicate_workbook(str(project["project_id"]), parsed_sheet_ids)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(payload)


@app.post("/api/structured/sheets/parse-import")
async def parse_structured_sheet_import(
    project_id: str = Form(""),
    sheet_id: str = Form(""),
    block_text: str = Form(...),
    current_name: str = Form(""),
    current_context: str = Form(""),
    current_row_unit: str = Form(""),
    current_columns: str = Form("[]"),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        if sheet_id:
            sheet = structured_extraction.get_sheet(str(project["project_id"]), sheet_id)
            if structured_extraction.sheet_is_locked(sheet):
                raise ValueError("This sheet is locked for reproducibility. Duplicate it to edit the schema.")
        current_sheet = {
            "name": current_name,
            "context": current_context,
            "row_unit": current_row_unit,
            "columns": parse_structured_columns(current_columns),
        }
        payload = structured_extraction.parse_sheet_import(block_text, current_sheet=current_sheet)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, **payload})


@app.get("/api/structured/sheets/{sheet_id}")
async def get_structured_sheet(sheet_id: str, project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        sheet = structured_extraction.get_sheet(str(project["project_id"]), sheet_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "sheet": sheet})


@app.get("/api/structured/sheets/{sheet_id}/import-text")
async def export_structured_sheet_import_text(sheet_id: str, project_id: str = "") -> PlainTextResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        sheet = structured_extraction.get_sheet(str(project["project_id"]), sheet_id)
        text = structured_extraction.format_sheet_import_text(sheet)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    filename = f"{projects.sanitize_slug(str(sheet.get('name') or sheet_id))}_structured_sheet.txt"
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.put("/api/structured/sheets/{sheet_id}")
async def update_structured_sheet(
    sheet_id: str,
    project_id: str = Form(""),
    name: str = Form(...),
    context: str = Form(""),
    row_unit: str = Form(""),
    columns: str = Form("[]"),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        sheet = structured_extraction.update_sheet(
            project_id=str(project["project_id"]),
            sheet_id=sheet_id,
            name=name,
            context=context,
            row_unit=row_unit,
            columns=parse_structured_columns(columns),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "sheet": sheet, "sheets": structured_extraction.list_sheets(str(project["project_id"]))})


@app.delete("/api/structured/sheets/{sheet_id}")
async def delete_structured_sheet(sheet_id: str, project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        structured_extraction.delete_sheet(str(project["project_id"]), sheet_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"deleted": True, "sheet_id": sheet_id, "sheets": structured_extraction.list_sheets(str(project["project_id"]))})


@app.post("/api/structured/sheets/{sheet_id}/duplicate")
async def duplicate_structured_sheet(sheet_id: str, project_id: str = Form("")) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        sheet = structured_extraction.duplicate_sheet(str(project["project_id"]), sheet_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "sheet": sheet, "sheets": structured_extraction.list_sheets(str(project["project_id"]))})


@app.post("/api/structured/columns/parse-blocks")
async def parse_structured_column_blocks(block_text: str = Form(...)) -> JSONResponse:
    try:
        columns = structured_extraction.parse_column_blocks(block_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"columns": columns, "count": len(columns)})


@app.post("/api/structured/jobs")
async def create_structured_jobs(
    pdfs: list[UploadFile] | None = File(None),
    pdf: UploadFile | None = File(None),
    pdf_relative_paths: list[str] | None = Form(None),
    project_id: str = Form(""),
    sheet_id: str = Form(...),
    ocr_dpi: int = Form(config.DEFAULT_OCR_DPI),
    ocr_batch_size: int = Form(config.DEFAULT_OCR_BATCH_SIZE),
    deepseek_ocr_model_path: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    openai_input_mode: str = Form("ocr_text"),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    ensure_project_type(project, "pdf_structured")
    try:
        sheet = structured_extraction.get_sheet(active_project_id, sheet_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    compiled_prompt = structured_extraction.compile_sheet_prompt(sheet)
    settings = settings_from_form(
        ocr_dpi=ocr_dpi,
        ocr_batch_size=ocr_batch_size,
        deepseek_ocr_model_path=deepseek_ocr_model_path,
        rq_model_preset=rq_model_preset,
        openai_api_key=openai_api_key,
        openai_input_mode=openai_input_mode,
        rq_prompt_filename=f"structured_{sheet_id}.txt",
        rq_system_prompt=compiled_prompt,
    )
    pdf_uploads = validated_pdf_uploads(pdfs, pdf)
    upload_relative_paths = normalized_relative_paths(pdf_uploads, pdf_relative_paths)
    queued_jobs: list[dict[str, str]] = []
    locked_sheet = sheet
    for upload, relative_path in zip(pdf_uploads, upload_relative_paths):
        filename = upload_display_filename(upload)
        reusable_ocr = jobs.find_reusable_ocr_job_by_filename(filename, project_id=active_project_id)
        job_id = jobs.new_job_id()
        root = jobs.create_job(job_id, filename, settings, project_id=active_project_id)
        dest = root / "input" / "uploaded.pdf"
        jobs.save_upload(upload.file, dest)
        pdf_sha256 = jobs.file_sha256(dest)
        jobs.update_metadata(
            root,
            uploaded_pdf=str(dest),
            pdf_sha256=pdf_sha256,
            source_relative_path=relative_path,
            source_folder=source_folder_from_relative_path(relative_path),
            project_id=active_project_id,
            extraction_type="pdf_structured",
            structured_sheet_id=sheet_id,
            structured_sheet_name=str(sheet.get("name") or sheet_id),
            structured_columns=sheet.get("columns") or [],
            structured_row_unit=str(sheet.get("row_unit") or ""),
            structured_context=str(sheet.get("context") or ""),
            structured_compiled_prompt=compiled_prompt,
        )
        if not queued_jobs:
            locked_sheet = structured_extraction.lock_sheet_for_first_run(active_project_id, sheet_id, job_id)
        reusable_openai_file = (
            jobs.find_reusable_openai_file_job(pdf_sha256, filename, project_id=active_project_id)
            if settings.rq_provider == "openai" and settings.openai_input_mode == "pdf_file"
            else None
        )
        if reusable_openai_file is not None:
            jobs.copy_reusable_openai_file(str(reusable_openai_file["job_id"]), root, source_project_id=active_project_id)
        elif reusable_ocr is not None and settings.openai_input_mode != "pdf_file":
            jobs.copy_reusable_ocr(str(reusable_ocr["job_id"]), root, source_project_id=active_project_id)
        job_queue.enqueue(job_id, settings, project_id=active_project_id)
        queued_jobs.append(
            {
                "job_id": job_id,
                "filename": filename,
                "project_id": active_project_id,
                "sheet_id": sheet_id,
                "sheet_name": str(sheet.get("name") or sheet_id),
                "model": settings.rq_screening_model,
                "openai_input_mode": settings.openai_input_mode,
            }
        )
        logger.info("Queued structured PDF extraction job %s for %s", job_id, filename)
    return JSONResponse(
        {
            "project": project,
            "sheet": locked_sheet,
            "job_id": queued_jobs[0]["job_id"] if queued_jobs else None,
            "job_ids": [job["job_id"] for job in queued_jobs],
            "jobs": queued_jobs,
            "count": len(queued_jobs),
        }
    )


@app.get("/api/structured/jobs")
async def list_structured_jobs(project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    job_queue.mark_stale_running_jobs_failed(project_id=str(project["project_id"]))
    return JSONResponse(
        {
            "project": project,
            "jobs": structured_extraction.list_structured_jobs(str(project["project_id"])),
            "queue": job_queue.status(project_id=str(project["project_id"])),
        }
    )


@app.get("/api/structured/jobs/{job_id}/result")
async def structured_job_result(job_id: str, project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        payload = structured_extraction.structured_job_result(str(project["project_id"]), job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, **payload})


@app.get("/api/structured/rows")
async def structured_rows(
    project_id: str = "",
    sheet_id: str = "",
    offset: int = 0,
    limit: int = 100,
    search: str = "",
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        payload = structured_extraction.list_rows(
            project_id=str(project["project_id"]),
            sheet_id=sheet_id,
            offset=offset,
            limit=limit,
            search=search,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, **payload})


@app.get("/api/structured/export")
async def download_structured_export(project_id: str = "") -> FileResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "pdf_structured")
    try:
        path = structured_extraction.export_structured_workbook(str(project["project_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to build structured PDF export")
        raise HTTPException(status_code=500, detail=f"Failed to build structured PDF export: {exc}")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Structured PDF export is not available.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


@app.get("/api/text/workbook")
async def text_workbook(project_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        workbook = text_extraction.get_text_workbook(str(project["project_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, **workbook})


@app.post("/api/text/source")
async def create_text_source(
    spreadsheet: UploadFile = File(...),
    project_id: str = Form(""),
    column_mappings: str = Form("[]"),
    study_id_column: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    ensure_project_type(project, "text")
    settings = settings_from_form(
        ocr_dpi=config.DEFAULT_OCR_DPI,
        ocr_batch_size=config.DEFAULT_OCR_BATCH_SIZE,
        deepseek_ocr_model_path="",
        rq_model_preset=rq_model_preset,
        openai_api_key="",
        openai_input_mode="ocr_text",
        rq_prompt_filename=rq_prompt_filename,
        rq_system_prompt=rq_system_prompt,
    )
    try:
        result = text_extraction.create_text_source(
            project_id=active_project_id,
            upload_file=spreadsheet,
            column_mappings=parse_text_column_mappings(column_mappings),
            study_id_column=study_id_column,
            initial_settings=settings,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to create text extraction source")
        raise HTTPException(status_code=500, detail=f"Failed to create text extraction source: {exc}")
    return JSONResponse({"project": project, **result})


@app.post("/api/text/sheets")
async def create_text_sheet(
    project_id: str = Form(""),
    name: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        sheet = text_extraction.create_text_sheet(
            project_id=str(project["project_id"]),
            name=name,
            rq_model_preset=rq_model_preset,
            rq_prompt_filename=rq_prompt_filename,
            rq_system_prompt=rq_system_prompt,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "sheet": sheet, "sheets": text_extraction.list_text_sheets(str(project["project_id"]))})


@app.put("/api/text/sheets/{sheet_id}")
async def update_text_sheet(
    sheet_id: str,
    project_id: str = Form(""),
    name: str = Form(...),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        sheet = text_extraction.update_text_sheet(
            project_id=str(project["project_id"]),
            sheet_id=sheet_id,
            name=name,
            rq_model_preset=rq_model_preset,
            rq_prompt_filename=rq_prompt_filename,
            rq_system_prompt=rq_system_prompt,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "sheet": sheet, "sheets": text_extraction.list_text_sheets(str(project["project_id"]))})


@app.post("/api/text/sheets/{sheet_id}/duplicate")
async def duplicate_text_sheet(sheet_id: str, project_id: str = Form("")) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        sheet = text_extraction.duplicate_text_sheet(str(project["project_id"]), sheet_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "sheet": sheet, "sheets": text_extraction.list_text_sheets(str(project["project_id"]))})


@app.post("/api/text/sheets/{sheet_id}/run")
async def run_text_sheet(
    sheet_id: str,
    project_id: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    ensure_project_type(project, "text")
    settings = settings_from_form(
        ocr_dpi=config.DEFAULT_OCR_DPI,
        ocr_batch_size=config.DEFAULT_OCR_BATCH_SIZE,
        deepseek_ocr_model_path="",
        rq_model_preset=rq_model_preset,
        openai_api_key=openai_api_key,
        openai_input_mode="ocr_text",
        rq_prompt_filename=rq_prompt_filename,
        rq_system_prompt=rq_system_prompt,
    )
    try:
        result = text_extraction.create_text_jobs_for_sheet(
            project_id=active_project_id,
            sheet_id=sheet_id,
            settings=settings,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, **result})


@app.post("/api/text/jobs")
async def create_text_jobs(
    spreadsheet: UploadFile = File(...),
    project_id: str = Form(""),
    column_mappings: str = Form("[]"),
    study_id_column: str = Form(""),
    rq_model_preset: str = Form("qwen35_9b_8bit_reasoning"),
    openai_api_key: str = Form(""),
    rq_prompt_filename: str = Form(config.DEFAULT_RQ_PROMPT_FILENAME),
    rq_system_prompt: str = Form(""),
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    active_project_id = str(project["project_id"])
    ensure_project_type(project, "text")
    settings = settings_from_form(
        ocr_dpi=config.DEFAULT_OCR_DPI,
        ocr_batch_size=config.DEFAULT_OCR_BATCH_SIZE,
        deepseek_ocr_model_path="",
        rq_model_preset=rq_model_preset,
        openai_api_key=openai_api_key,
        openai_input_mode="ocr_text",
        rq_prompt_filename=rq_prompt_filename,
        rq_system_prompt=rq_system_prompt,
    )
    try:
        mappings = parse_text_column_mappings(column_mappings)
        result = text_extraction.create_text_jobs_from_upload(
            project_id=active_project_id,
            upload_file=spreadsheet,
            settings=settings,
            column_mappings=mappings,
            study_id_column=study_id_column,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to create text extraction jobs")
        raise HTTPException(status_code=500, detail=f"Failed to create text extraction jobs: {exc}")
    return JSONResponse({"project": project, **result})


@app.get("/api/text/jobs")
async def list_text_jobs(
    project_id: str = "",
    sheet_id: str = "",
    offset: int = 0,
    limit: int = 100,
    status: str = "all",
    search: str = "",
) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        payload = text_extraction.list_text_jobs(
            project_id=str(project["project_id"]),
            sheet_id=sheet_id,
            offset=offset,
            limit=limit,
            status=status,
            search=search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, **payload})


@app.get("/api/text/jobs/counts")
async def text_job_counts(project_id: str = "", sheet_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        counts = text_extraction.text_job_counts(str(project["project_id"]), sheet_id=sheet_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"project": project, "counts": counts, "queue": text_extraction.text_job_queue.status(project_id=str(project["project_id"]))})


@app.post("/api/text/queue/pause")
async def pause_text_queue(project_id: str = Form("")) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    return JSONResponse(text_extraction.text_job_queue.pause(project_id=str(project["project_id"])))


@app.post("/api/text/queue/resume")
async def resume_text_queue(project_id: str = Form("")) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    return JSONResponse(text_extraction.text_job_queue.resume(project_id=str(project["project_id"])))


@app.post("/api/text/jobs/retry-failed")
async def retry_failed_text_jobs(project_id: str = Form(""), sheet_id: str = Form("")) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        result = text_extraction.retry_failed_text_jobs(str(project["project_id"]), sheet_id=sheet_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse(result)


@app.get("/api/text/jobs/{job_id}/output")
async def text_job_output(job_id: str, project_id: str = "", sheet_id: str = "") -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        return JSONResponse(text_extraction.read_text_job_output(str(project["project_id"]), job_id, sheet_id=sheet_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/text/jobs/{job_id}/retry")
async def retry_text_job(job_id: str, project_id: str = Form(""), sheet_id: str = Form("")) -> JSONResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        job = text_extraction.retry_text_job(str(project["project_id"]), job_id, sheet_id=sheet_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return JSONResponse({"job": job, **text_extraction.text_job_queue.status(project_id=str(project["project_id"]))})


@app.get("/api/text/export")
async def download_text_export(project_id: str = "") -> FileResponse:
    project = selected_project_or_default(project_id)
    ensure_project_type(project, "text")
    try:
        path = text_extraction.export_text_results(str(project["project_id"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to build text extraction export")
        raise HTTPException(status_code=500, detail=f"Failed to build text extraction export: {exc}")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Text extraction export is not available.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
    )


def read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def selected_project_or_default(project_id: str | None = "") -> dict[str, Any]:
    raw_project_id = str(project_id or "").strip()
    try:
        if raw_project_id:
            return projects.get_project(raw_project_id)
        return projects.get_default_project()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def ensure_project_type(project: dict[str, Any], extraction_type: str) -> None:
    actual = projects.normalize_extraction_type(project.get("extraction_type"))
    if actual != extraction_type:
        raise HTTPException(status_code=400, detail=f"Project is a {actual} extraction project, not {extraction_type}.")


def parse_text_column_mappings(raw: str) -> list[dict[str, str]]:
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Column mappings must be valid JSON.") from exc
    if not isinstance(payload, list):
        raise ValueError("Column mappings must be a list.")
    mappings: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each column mapping must be an object.")
        mappings.append(
            {
                "column_name": str(item.get("column_name") or item.get("column") or ""),
                "prompt_label": str(item.get("prompt_label") or item.get("label") or ""),
            }
        )
    return mappings


def parse_structured_columns(raw: str) -> list[dict[str, str]]:
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("Structured columns must be valid JSON.") from exc
    if not isinstance(payload, list):
        raise ValueError("Structured columns must be a list.")
    columns: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("Each structured column must be an object.")
        columns.append(
            {
                "column_name": str(item.get("column_name") or item.get("name") or ""),
                "question": str(item.get("question") or ""),
                "rules": str(item.get("rules") or ""),
            }
        )
    return columns


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
