from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable

from app import config
from app.shared.process_runner import run_event_process

OPENAI_API_KEY_FILE = config.DATA_DIR / "api_key.txt"


def run_openai_rq(
    *,
    job_id: str | None = None,
    model: str,
    system_prompt_file: Path,
    user_prompt_file: Path,
    output_file: Path,
    max_tokens: int,
    enable_reasoning: bool,
    reasoning_effort: str,
    api_key: str = "",
    input_file_id: str = "",
    input_file_path: Path | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    cmd = [
        sys.executable,
        str(config.BASE_DIR / "scripts" / "openai_rq_worker.py"),
        "--model",
        model,
        "--system-prompt-file",
        str(system_prompt_file),
        "--user-prompt-file",
        str(user_prompt_file),
        "--output-file",
        str(output_file),
        "--max-output-tokens",
        str(max_tokens),
        "--enable-reasoning",
        "true" if enable_reasoning else "false",
        "--reasoning-effort",
        reasoning_effort,
    ]
    if input_file_id.strip():
        cmd.extend(["--input-file-id", input_file_id.strip()])
    elif input_file_path is not None:
        cmd.extend(["--input-file-path", str(input_file_path)])
    env = os.environ.copy()
    resolved_api_key = resolve_openai_api_key(api_key, env)
    if resolved_api_key:
        env["OPENAI_API_KEY"] = resolved_api_key
    result = run_event_process(
        cmd=cmd,
        job_id=job_id,
        on_event=on_event,
        cancel_message="OpenAI RQ screening worker was interrupted by queue pause.",
        env=env,
    )
    if result.return_code != 0:
        details = result.details
        lowered = details.lower()
        if "no module named" in lowered and "openai" in lowered:
            raise RuntimeError("openai is missing. Run `pip install -r requirements.txt`.")
        if "api key" in lowered or "openai_api_key" in lowered:
            raise RuntimeError("OPENAI_API_KEY is missing or invalid. Set it before using OpenAI models.")
        if "empty final output" in lowered:
            raise RuntimeError(f"OpenAI returned an empty final output. Details: {details[-1200:]}")
        raise RuntimeError(f"OpenAI RQ screening generation failed. Details: {details[-1200:]}")


def resolve_openai_api_key(api_key: str = "", env: dict[str, str] | None = None) -> str:
    form_key = str(api_key or "").strip()
    if form_key:
        return form_key

    source_env = env if env is not None else os.environ
    env_key = str(source_env.get("OPENAI_API_KEY") or "").strip()
    if env_key:
        return env_key

    try:
        return OPENAI_API_KEY_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
