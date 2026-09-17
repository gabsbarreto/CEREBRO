from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from app import config
from app.models import JobSettings
from app.services import jobs, supplementary_sources
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


def run_job(
    job_id: str,
    settings: JobSettings,
    *,
    project_id: str | None = None,
    defer_openai: bool = False,
) -> None:
    root = jobs.job_dir(job_id, project_id)
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
            message="Preparing study bundle",
            progress=0.02,
            event={"event": "stage", "stage": "upload"},
            project_id=project_id,
        )
        if not pdf_path.exists() or pdf_path.stat().st_size == 0:
            raise RuntimeError("Uploaded PDF was not saved correctly.")
        process_control.raise_if_cancelled(job_id)

        metadata = jobs.read_metadata(root)
        source_records = jobs.source_file_records(root, metadata)
        if not source_records:
            raise RuntimeError("No source files were saved for this job.")
        source_pdf_records = jobs.source_pdf_records(root, metadata)
        supplementary_pdf_records = [record for record in source_pdf_records if record.get("role") != "primary_pdf"]
        spreadsheet_records = jobs.source_spreadsheet_records(root, metadata)
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
                project_id=project_id,
            )
            try:
                primary_pages = page_count(pdf_path)
                supporting_pages = sum(page_count(Path(record["path"])) for record in supplementary_pdf_records)
                if primary_pages > 0:
                    jobs.update_metadata(
                        root,
                        number_of_pages=primary_pages,
                        source_pdf_page_count=primary_pages + supporting_pages,
                        supporting_pdf_count=len(supplementary_pdf_records),
                    )
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
                project_id=project_id,
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
                project_id=project_id,
            )
            primary_pages = page_count(pdf_path)
            if primary_pages <= 0:
                raise RuntimeError("No pages found in the uploaded PDF.")
            primary_images = render_pdf_to_images(
                pdf_path,
                root / "rendered_pages",
                root / "ocr_images",
                dpi=settings.ocr_dpi,
            )
            if not primary_images:
                raise RuntimeError("PDF rendering produced no OCR images.")
            ocr_images = list(primary_images)
            ocr_names = [
                f"page_{page_index:06d}__primary_{page_index:04d}"
                for page_index, _path in enumerate(primary_images, start=1)
            ]
            total_pages = primary_pages
            for source_index, record in enumerate(supplementary_pdf_records, start=1):
                attachment_path = Path(record["path"])
                attachment_name = str(record.get("filename") or attachment_path.name)
                try:
                    attachment_pages = page_count(attachment_path)
                except Exception as exc:
                    jobs.append_warning(root, f"Could not inspect supporting PDF {attachment_name}: {exc}")
                    continue
                if attachment_pages <= 0:
                    jobs.append_warning(root, f"Supporting PDF has no pages: {attachment_name}")
                    continue
                try:
                    attachment_images = render_pdf_to_images(
                        attachment_path,
                        root / "rendered_pages" / "attachments" / f"{source_index:03d}",
                        root / "ocr_images" / "attachments" / f"{source_index:03d}",
                        dpi=settings.ocr_dpi,
                    )
                except Exception as exc:
                    jobs.append_warning(root, f"Could not render supporting PDF {attachment_name}: {exc}")
                    continue
                if not attachment_images:
                    jobs.append_warning(root, f"Could not render supporting PDF: {attachment_name}")
                    continue
                total_pages += attachment_pages
                ocr_images.extend(attachment_images)
                sequence_start = len(ocr_names)
                ocr_names.extend(
                    f"page_{sequence_start + page_index:06d}__supporting_{source_index:03d}_{page_index:04d}"
                    for page_index, _path in enumerate(attachment_images, start=1)
                )
            jobs.update_metadata(
                root,
                number_of_pages=primary_pages,
                source_pdf_page_count=total_pages,
                supporting_pdf_count=len(supplementary_pdf_records),
                rendered_images=[str(path) for path in ocr_images],
            )
            process_control.raise_if_cancelled(job_id)

            jobs.update_status(
                job_id,
                stage="find_deepseek",
                message="Finding DeepSeekOCR2",
                progress=0.18,
                event={"event": "stage", "stage": "find_deepseek"},
                project_id=project_id,
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
                project_id=project_id,
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
                jobs.update_status(job_id, stage="ocr", message=message, progress=progress, event=event, project_id=project_id)

            run_deepseek_ocr(
                job_id=job_id,
                image_paths=ocr_images,
                output_dir=root / "ocr_text",
                model_path=model_path,
                max_tokens=config.DEFAULT_DEEPSEEK_OCR_MAX_TOKENS,
                temperature=config.DEFAULT_DEEPSEEK_OCR_TEMPERATURE,
                batch_size=settings.ocr_batch_size,
                prompt=config.DEFAULT_DEEPSEEK_OCR_PROMPT,
                names=ocr_names,
                on_event=handle_ocr_event,
            )
            process_control.raise_if_cancelled(job_id)

            jobs.update_status(
                job_id,
                stage="merge",
                message="Merging OCR text",
                progress=0.60,
                event={"event": "stage", "stage": "merge"},
                project_id=project_id,
            )
            merged_text = merge_page_texts(root / "ocr_text", merged_file)
            if not merged_text.strip() or len(merged_text.strip()) < 20:
                raise RuntimeError("No OCR text extracted. Inspect the page files in the job folder.")
            spreadsheet_transcripts = supplementary_sources.transcript_spreadsheet_sources(
                spreadsheet_records,
                root / "outputs" / "supplementary_text",
            )
            transcript_text = "\n\n".join(item.text.strip() for item in spreadsheet_transcripts if item.text.strip())
            warnings = [item.warning for item in spreadsheet_transcripts if item.warning]
            for warning in warnings:
                jobs.append_warning(root, warning)
            if transcript_text:
                merged_text = merged_text.rstrip() + "\n\n" + transcript_text + "\n"
                merged_file.write_text(merged_text, encoding="utf-8")
            jobs.update_metadata(
                root,
                ocr_complete=True,
                supplementary_transcript_files=[str(item.output_path) for item in spreadsheet_transcripts if item.output_path],
            )
            process_control.raise_if_cancelled(job_id)

        jobs.update_status(
            job_id,
            stage="prompt",
            message="Building RQ prompts",
            progress=0.66,
            event={"event": "stage", "stage": "prompt"},
            project_id=project_id,
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
            "Use the attached primary PDF and every supporting source file to assess the full study. "
            "Consider text, tables, figures, charts, captions, appendices, and supplementary data when applying "
            "the system prompt."
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
        openai_source_paths = jobs.source_file_paths(root, jobs.read_metadata(root)) if use_openai_pdf_file else []
        reusable_openai_file_ids = jobs.reusable_openai_file_ids(root, jobs.read_metadata(root)) if use_openai_pdf_file else []
        uses_bundle_openai_inputs = use_openai_pdf_file and len(openai_source_paths) > 1

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
                        project_id=project_id,
                        prompt_filename=prompt_filename,
                        prompt_source_path=prompt_source_path,
                        system_prompt_file=system_prompt_file,
                        user_prompt_file=user_prompt_file,
                        output_file=output_file,
                        pdf_path=pdf_path,
                        source_file_paths=tuple(openai_source_paths),
                        openai_input_mode=settings.openai_input_mode,
                        openai_file_ids=tuple(reusable_openai_file_ids),
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
                input_file_id=(reusable_openai_file_ids[0] if reusable_openai_file_ids and not uses_bundle_openai_inputs else ""),
                input_file_path=(openai_source_paths[0] if use_openai_pdf_file and not reusable_openai_file_ids and not uses_bundle_openai_inputs else None),
                input_file_ids=reusable_openai_file_ids if uses_bundle_openai_inputs else [],
                input_file_paths=openai_source_paths if uses_bundle_openai_inputs and not reusable_openai_file_ids else [],
                on_event=lambda event: handle_llm_event(job_id, event, provider="openai", project_id=project_id),
            )
        else:
            jobs.update_status(
                job_id,
                stage="rq_model",
                message="Loading RQ screening model",
                progress=0.72,
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
                on_event=lambda event: handle_llm_event(job_id, event, provider="local", project_id=project_id),
            )
        process_control.raise_if_cancelled(job_id)

        complete_screening_job(
            job_id=job_id,
            settings=settings,
            project_id=project_id,
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
            project_id=project_id,
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
            project_id=project_id,
        )


def handle_llm_event(
    job_id: str,
    event: dict[str, Any],
    *,
    provider: str,
    project_id: str | None = None,
) -> None:
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
        message = "Uploading source file to OpenAI"
        progress = 0.76
    elif name in {"openai_file_uploaded", "openai_file_reused"}:
        file_id = str(event.get("file_id") or "")
        if file_id:
            jobs.record_openai_source_file(
                jobs.job_dir(job_id, project_id),
                file_id=file_id,
                source_index=int(event.get("source_index") or 0),
                uploaded=name == "openai_file_uploaded",
            )
        message = "OpenAI source file ready"
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
        project_id=project_id,
    )
