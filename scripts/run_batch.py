from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Iterable

from _bootstrap import ensure_project_root

ensure_project_root()

from app.shared.cli import emit_json_event as emit
from app import config
from app.models import JobSettings
from app.services import jobs
from app.services.rq_screening_pipeline import run_job


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local RQ screening sequentially over a PDF folder or list of PDF files."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--pdf-dir", type=Path, help="Folder containing PDFs.")
    source.add_argument("--file-list", type=Path, help="Text file with one PDF path per line.")
    source.add_argument("--files-json", help="JSON array of PDF paths.")
    parser.add_argument("--recursive", action="store_true", help="Search --pdf-dir recursively.")
    parser.add_argument("--watch", action="store_true", help="Keep watching --pdf-dir for new PDFs until stopped.")
    parser.add_argument("--poll-seconds", type=float, default=30.0)
    parser.add_argument("--limit", type=int, default=0, help="Maximum PDFs to process; 0 means no limit.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop after the first failed job.")
    parser.add_argument("--ocr-dpi", type=int, default=config.DEFAULT_OCR_DPI)
    parser.add_argument("--ocr-batch-size", type=int, default=config.DEFAULT_OCR_BATCH_SIZE)
    parser.add_argument(
        "--deepseek-ocr-model-path",
        default="",
        help="Override auto-detection. By default the app prefers local DeepSeek-OCR-2-8bit.",
    )
    parser.add_argument("--rq-provider", default=config.RQ_SCREENING_PROVIDER, choices=["local", "openai"])
    parser.add_argument("--rq-model", default=config.RQ_SCREENING_MODEL)
    parser.add_argument("--rq-max-tokens", type=int, default=config.RQ_SCREENING_MAX_TOKENS)
    parser.add_argument("--rq-temperature", type=float, default=config.RQ_SCREENING_TEMPERATURE)
    parser.add_argument("--rq-top-p", type=float, default=config.RQ_SCREENING_TOP_P)
    parser.add_argument("--rq-top-k", type=int, default=config.RQ_SCREENING_TOP_K)
    parser.add_argument("--rq-min-p", type=float, default=config.RQ_SCREENING_MIN_P)
    parser.add_argument("--rq-presence-penalty", type=float, default=config.RQ_SCREENING_PRESENCE_PENALTY)
    parser.add_argument("--rq-repetition-penalty", type=float, default=config.RQ_SCREENING_REPETITION_PENALTY)
    parser.add_argument("--rq-enable-thinking", default=str(config.RQ_SCREENING_ENABLE_THINKING).lower())
    parser.add_argument("--openai-reasoning-effort", default=config.OPENAI_REASONING_EFFORT)
    return parser.parse_args()


def paths_from_args(args: argparse.Namespace) -> list[Path]:
    if args.pdf_dir:
        pattern = "**/*.pdf" if args.recursive else "*.pdf"
        return sorted(path for path in args.pdf_dir.expanduser().glob(pattern) if path.is_file())
    if args.file_list:
        return [
            Path(line.strip()).expanduser()
            for line in args.file_list.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    return [Path(path).expanduser() for path in json.loads(args.files_json)]


def stable_existing_pdfs(paths: Iterable[Path], seen: set[Path]) -> list[Path]:
    ready: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen or not resolved.exists() or path.suffix.lower() != ".pdf":
            continue
        try:
            first = resolved.stat().st_size
            time.sleep(0.2)
            second = resolved.stat().st_size
        except OSError:
            continue
        if first > 0 and first == second:
            ready.append(resolved)
    return ready


def build_settings(args: argparse.Namespace) -> JobSettings:
    return JobSettings.from_form(
        {
            "ocr_dpi": int(args.ocr_dpi),
            "ocr_batch_size": max(1, int(args.ocr_batch_size)),
            "deepseek_ocr_model_path": str(args.deepseek_ocr_model_path or "").strip(),
            "rq_provider": str(args.rq_provider),
            "rq_screening_model": str(args.rq_model),
            "rq_max_tokens": int(args.rq_max_tokens),
            "rq_temperature": float(args.rq_temperature),
            "rq_top_p": float(args.rq_top_p),
            "rq_top_k": int(args.rq_top_k),
            "rq_min_p": float(args.rq_min_p),
            "rq_presence_penalty": float(args.rq_presence_penalty),
            "rq_repetition_penalty": float(args.rq_repetition_penalty),
            "rq_enable_thinking": str(args.rq_enable_thinking),
            "openai_reasoning_effort": str(args.openai_reasoning_effort),
        }
    )


def run_one(pdf_path: Path, settings: JobSettings) -> dict:
    job_id = jobs.new_job_id()
    root = jobs.create_job(job_id, pdf_path.name, settings)
    dest = root / "input" / "uploaded.pdf"
    shutil.copy2(pdf_path, dest)
    jobs.update_metadata(root, uploaded_pdf=str(dest), source_pdf=str(pdf_path))
    emit({"event": "batch_job_started", "job_id": job_id, "source_pdf": str(pdf_path), "job_dir": str(root)})
    run_job(job_id, settings)
    status = jobs.read_status(job_id)
    emit(
        {
            "event": "batch_job_finished",
            "job_id": job_id,
            "source_pdf": str(pdf_path),
            "status": status.get("status"),
            "message": status.get("message"),
            "job_dir": str(root),
        }
    )
    return status


def main() -> int:
    args = parse_args()
    settings = build_settings(args)
    seen: set[Path] = set()
    processed = 0

    while True:
        candidates = stable_existing_pdfs(paths_from_args(args), seen)
        if not candidates and not args.watch:
            emit({"event": "batch_no_pdfs_found"})
            return 1 if processed == 0 else 0

        for pdf_path in candidates:
            seen.add(pdf_path.resolve())
            status = run_one(pdf_path, settings)
            processed += 1
            if status.get("status") != "complete" and args.stop_on_error:
                return 1
            if args.limit and processed >= args.limit:
                emit({"event": "batch_limit_reached", "processed": processed})
                return 0

        if not args.watch:
            emit({"event": "batch_finished", "processed": processed})
            return 0
        time.sleep(max(float(args.poll_seconds), 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
