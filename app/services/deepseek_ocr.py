from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Any

from app import config
from app.shared.process_runner import run_event_process


def discover_deepseek_model() -> str | None:
    env_path = os.getenv("DEEPSEEK_OCR_MODEL_PATH")
    if env_path:
        return env_path

    script = config.BASE_DIR / "scripts" / "find_deepseek_ocr.py"
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--json"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        kind = str(candidate.get("kind") or "")
        source = str(candidate.get("source") or "")
        if kind == "python-env" or "DEEPSEEK_OCR_PYTHON" in source:
            continue
        path = str(candidate.get("path") or "").lower()
        if "deepseek" not in path:
            continue
        if ".locks" in path or "__pycache__" in path:
            continue
        value = candidate.get("path") or candidate.get("value")
        if value:
            return str(value)
    return None


def run_deepseek_ocr(
    *,
    job_id: str | None = None,
    image_paths: list[Path],
    output_dir: Path,
    model_path: str,
    max_tokens: int,
    temperature: float,
    batch_size: int,
    prompt: str,
    names: list[str],
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    python_executable = os.getenv("DEEPSEEK_OCR_PYTHON", sys.executable)
    cmd = [
        python_executable,
        str(config.BASE_DIR / "scripts" / "deepseek_ocr_worker.py"),
        "--images-json",
        json.dumps([str(path) for path in image_paths]),
        "--output-dir",
        str(output_dir),
        "--model-path",
        model_path,
        "--max-tokens",
        str(max_tokens),
        "--temperature",
        str(temperature),
        "--batch-size",
        str(batch_size),
        "--prompt",
        prompt,
        "--names-json",
        json.dumps(names),
    ]
    try:
        result = run_event_process(
            cmd=cmd,
            job_id=job_id,
            on_event=on_event,
            cancel_message="DeepSeekOCR2 worker was interrupted by queue pause.",
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "DeepSeekOCR2 Python was not found. Set DEEPSEEK_OCR_PYTHON to the Python "
            "environment where mlx-vlm and DeepSeek-OCR-2 are installed."
        ) from exc

    if result.return_code != 0:
        details = result.details
        lowered = details.lower()
        if "out of memory" in lowered or "memory" in lowered:
            raise RuntimeError(f"DeepSeekOCR2 worker ran out of memory. Details: {details[-1200:]}")
        if "mlx_vlm" in lowered or "no module named" in lowered:
            raise RuntimeError(
                "DeepSeekOCR2 worker failed because mlx-vlm or its model dependencies are missing "
                f"in DEEPSEEK_OCR_PYTHON. Details: {details[-1200:]}"
            )
        raise RuntimeError(f"DeepSeekOCR2 worker failed. Details: {details[-1200:]}")
