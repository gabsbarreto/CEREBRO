from __future__ import annotations

import logging
import time
from typing import Any

from app import config
from app.models import JobSettings
from app.services import jobs
from app.services.deepseek_ocr import discover_deepseek_model, run_deepseek_ocr
from app.services.ocr_merge import merge_page_texts
from app.services.openai_inference_queue import OpenAIInferenceJob, openai_inference_queue
from app.services.openai_rq import run_openai_rq
from app.services import process_control
from app.services.renderer import page_count, render_pdf_to_images
from app.services.rq_completion import complete_screening_job
from app.services.rq_llm import run_rq_llm
from app.services.rq_prompt import build_prompt_transcript, read_prompt_file

logger = logging.getLogger(__name__)


def run_job(job_id: str, settings: JobSettings, *, defer_openai: bool = False) -> None:
    root = jobs.job_dir(job_id)
    pdf_path = root / "input" / "uploaded.pdf"
    started = time.time()
    try:
        jobs.update_metadata(
            root,
            **jobs.settings_metadata_updates(settings),
        )
        jobs.update_status(
            job_id,
            stage="upload",
            message="Uploading PDF",
            progress=0.02,
            event={"event": "stage", "stage": "upload"},
        )
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise RuntimeError("Uploaded PDF was not saved correctly.")
        process_control.raise_if_cancelled(job_id)

        metadata = jobs.read_metadata(root)
        merged_file = root / "outputs" / "merged_full_text.txt"
        use_openai_pdf_file = settings.rq_provider == "openai" and settings.openai_input_mode == "pdf_file"
        reuse_screening_only = bool(
            metadata.get("pending_rerun_screening_only") or metadata.get("ocr_complete")
        ) and merged_file.exists()
        if use_openai_pdf_file:
            jobs.update_status(
                job_id,
                stage="prompt",
                message="Using PDF file directly with OpenAI",
                progress=0.60,
                event={"event": "openai_pdf_file_mode"},
            )
            try:
                total_pages = page_count(pdf_path)
                if total_pages > 0:
                    jobs.update_metadata(root, number_of_pages=total_pages)
            except Exception as exc:
                jobs.append_warning(root, f"Could not count PDF pages before OpenAI upload: {exc}")
            merged_text = ""
            process_control.raise_if_cancelled(job_id)
        elif reuse_screening_only:
            jobs.update_status(
                job_id,
                stage="merge",
                message="Reusing existing OCR text",
                progress=0.60,
                event={"event": "reuse_ocr_text"},
            )
            merged_text = merged_file.read_text(encoding="utf-8")
            total_pages = int(metadata.get("number_of_pages") or 0)
            if not merged_text.strip() or len(merged_text.strip()) < 20:
                raise RuntimeError("Saved OCR text is empty. Re-run the full OCR workflow for this PDF.")
            process_control.raise_if_cancelled(job_id)
        else:
            jobs.update_status(
                job_id,
                stage="render",
                message="Rendering pages",
                progress=0.08,
                event={"event": "stage", "stage": "render"},
            )
            total_pages = page_count(pdf_path)
            if total_pages <= 0:
                raise RuntimeError("No pages found in the uploaded PDF.")
            ocr_images = render_pdf_to_images(
                pdf_path,
                root / "rendered_pages",
                root / "ocr_images",
                dpi=settings.ocr_dpi,
            )
            if not ocr_images:
                raise RuntimeError("PDF rendering produced no OCR images.")
            jobs.update_metadata(root, number_of_pages=total_pages, rendered_images=[str(path) for path in ocr_images])
            process_control.raise_if_cancelled(job_id)

            jobs.update_status(
                job_id,
                stage="find_deepseek",
                message="Finding DeepSeekOCR2",
                progress=0.18,
                event={"event": "stage", "stage": "find_deepseek"},
            )
            model_path = settings.deepseek_ocr_model_path or discover_deepseek_model()
            if not model_path:
                raise RuntimeError(
                    "DeepSeekOCR2 model not found. Paste a local model path in the settings or set "
                    "DEEPSEEK_OCR_MODEL_PATH."
                )
            jobs.update_metadata(root, detected_deepseek_ocr_model_path=model_path)
            process_control.raise_if_cancelled(job_id)

            jobs.update_status(
                job_id,
                stage="ocr",
                message=f"Running OCR on {total_pages} pages",
                progress=0.22,
                event={"event": "stage", "stage": "ocr"},
            )

            def handle_ocr_event(event: dict[str, Any]) -> None:
                name = str(event.get("event", "ocr"))
                page = int(event.get("page") or event.get("index") or 0)
                if name in {"ocr_page_started", "page_started"} and page:
                    progress = 0.22 + (0.36 * max(page - 1, 0) / max(total_pages, 1))
                    message = f"OCR page {page} of {total_pages}"
                elif name in {"ocr_page_finished", "page_done"} and page:
                    progress = 0.22 + (0.36 * page / max(total_pages, 1))
                    message = f"OCR page {page} of {total_pages} complete"
                elif name == "ocr_finished":
                    progress = 0.58
                    message = "OCR complete"
                else:
                    progress = 0.22
                    message = "Running OCR"
                jobs.update_status(job_id, stage="ocr", message=message, progress=progress, event=event)

            run_deepseek_ocr(
                job_id=job_id,
                image_paths=ocr_images,
                output_dir=root / "ocr_text",
                model_path=model_path,
                max_tokens=config.DEFAULT_DEEPSEEK_OCR_MAX_TOKENS,
                temperature=config.DEFAULT_DEEPSEEK_OCR_TEMPERATURE,
                batch_size=settings.ocr_batch_size,
                prompt=config.DEFAULT_DEEPSEEK_OCR_PROMPT,
                names=[path.stem for path in ocr_images],
                on_event=handle_ocr_event,
            )
            process_control.raise_if_cancelled(job_id)

            jobs.update_status(
                job_id,
                stage="merge",
                message="Merging OCR text",
                progress=0.60,
                event={"event": "stage", "stage": "merge"},
            )
            merged_text = merge_page_texts(root / "ocr_text", merged_file)
            if not merged_text.strip() or len(merged_text.strip()) < 20:
                raise RuntimeError("No OCR text extracted. Inspect the page files in the job folder.")
            jobs.update_metadata(root, ocr_complete=True)
            process_control.raise_if_cancelled(job_id)

        jobs.update_status(
            job_id,
            stage="prompt",
            message="Building RQ prompts",
            progress=0.66,
            event={"event": "stage", "stage": "prompt"},
        )
        if settings.rq_system_prompt.strip():
            system_prompt = settings.rq_system_prompt.strip()
            prompt_filename = settings.rq_prompt_filename
            prompt_source_path = ""
        else:
            prompt_record = read_prompt_file(settings.rq_prompt_filename)
            system_prompt = prompt_record["system_prompt"].strip()
            prompt_filename = prompt_record["filename"]
            prompt_source_path = prompt_record["path"]
        user_prompt = (
            "Use the attached PDF file to assess the full text. Consider text, tables, figures, charts, "
            "captions, and appendices when applying the system prompt."
            if use_openai_pdf_file
            else merged_text
        )
        prompt_file = root / "outputs" / "rq_prompt.txt"
        system_prompt_file = root / "outputs" / "rq_system_prompt.txt"
        user_prompt_file = root / "outputs" / "rq_user_prompt.txt"
        system_prompt_file.write_text(system_prompt + "\n", encoding="utf-8")
        user_prompt_file.write_text(user_prompt, encoding="utf-8")
        prompt_file.write_text(build_prompt_transcript(system_prompt, user_prompt), encoding="utf-8")
        jobs.update_metadata(
            root,
            rq_prompt_filename=prompt_filename,
            rq_prompt_source_path=prompt_source_path,
            rq_system_prompt_file=str(system_prompt_file),
            rq_user_prompt_file=str(user_prompt_file),
        )
        process_control.raise_if_cancelled(job_id)

        output_file = root / "outputs" / "rq_screening_output.md"

        if settings.rq_provider == "openai":
            if defer_openai:
                # Browser queue path: OpenAI inference is network-bound, so hand it
                # to the bounded OpenAI queue and release the OCR worker for the
                # next PDF instead of leaving the local GPU idle.
                jobs.update_metadata(root, ocr_complete=True)
                enqueued = openai_inference_queue.enqueue(
                    OpenAIInferenceJob(
                        job_id=job_id,
                        settings=settings,
                        started_at=started,
                        prompt_filename=prompt_filename,
                        prompt_source_path=prompt_source_path,
                        system_prompt_file=system_prompt_file,
                        user_prompt_file=user_prompt_file,
                        output_file=output_file,
                        pdf_path=pdf_path,
                        openai_input_mode=settings.openai_input_mode,
                        openai_file_id=str(jobs.read_metadata(root).get("openai_file_id") or ""),
                    )
                )
                if not enqueued:
                    raise RuntimeError("OpenAI inference is already queued or running for this job.")
                return
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
                input_file_id=str(jobs.read_metadata(root).get("openai_file_id") or "")
                if use_openai_pdf_file
                else "",
                input_file_path=pdf_path if use_openai_pdf_file else None,
                on_event=lambda event: handle_llm_event(job_id, event, provider="openai"),
            )
        else:
            jobs.update_status(
                job_id,
                stage="rq_model",
                message="Loading RQ screening model",
                progress=0.72,
                event={"event": "stage", "stage": "rq_model"},
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
                on_event=lambda event: handle_llm_event(job_id, event, provider="local"),
            )
        process_control.raise_if_cancelled(job_id)

        complete_screening_job(
            job_id=job_id,
            settings=settings,
            started_at=started,
            prompt_filename=prompt_filename,
            prompt_source_path=prompt_source_path,
            system_prompt_file=system_prompt_file,
            user_prompt_file=user_prompt_file,
            output_file=output_file,
            pdf_path=pdf_path,
        )
    except process_control.JobCancelled as exc:
        jobs.update_status(
            job_id,
            status="queued",
            stage="queued",
            message=str(exc),
            progress=0.0,
            error=None,
            event={"event": "paused", "message": str(exc)},
        )
        raise
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        jobs.update_status(
            job_id,
            status="failed",
            stage="error",
            message=str(exc),
            progress=1.0,
            error=str(exc),
            event={"event": "error", "message": str(exc)},
        )


def handle_llm_event(job_id: str, event: dict[str, Any], *, provider: str) -> None:
    name = str(event.get("event", "rq"))
    if name == "rq_model_loading":
        message = "Loading RQ screening model" if provider == "local" else "Starting OpenAI inference"
        progress = 0.74
    elif name == "rq_model_loaded":
        message = "RQ screening model loaded" if provider == "local" else "OpenAI client ready"
        progress = 0.80
    elif name == "rq_generation_started":
        message = "Running RQ screening" if provider == "local" else "OpenAI inference running"
        progress = 0.84
    elif name == "openai_file_upload_started":
        message = "Uploading PDF to OpenAI"
        progress = 0.76
    elif name in {"openai_file_uploaded", "openai_file_reused"}:
        file_id = str(event.get("file_id") or "")
        if file_id:
            jobs.update_metadata(
                jobs.job_dir(job_id),
                openai_file_id=file_id,
                openai_file_uploaded=name == "openai_file_uploaded",
            )
        message = "OpenAI PDF file ready"
        progress = 0.80
    elif name == "rq_generation_finished":
        message = "RQ screening complete" if provider == "local" else "OpenAI inference complete"
        progress = 0.96
    elif name == "rq_generation_empty":
        message = "OpenAI returned no final text"
        progress = 0.94
    elif name == "rq_generation_log":
        message = str(event.get("line") or "Local model generating")
        progress = 0.86
    else:
        message = "Running RQ screening" if provider == "local" else "OpenAI inference running"
        progress = 0.84
    jobs.update_status(
        job_id,
        stage="rq_screening" if provider == "local" else "openai_running",
        message=message,
        progress=progress,
        event=event,
    )
