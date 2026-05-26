from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.services.local_inference_worker import local_inference_worker


def run_rq_llm(
    *,
    job_id: str | None = None,
    model: str,
    system_prompt_file: Path,
    user_prompt_file: Path,
    output_file: Path,
    max_tokens: int,
    thinking_budget: int,
    temperature: float,
    top_p: float,
    top_k: int,
    min_p: float,
    presence_penalty: float,
    repetition_penalty: float,
    enable_thinking: bool,
    verbose: bool,
    on_event: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    try:
        local_inference_worker.run(
            job_id=job_id,
            model=model,
            system_prompt_file=system_prompt_file,
            user_prompt_file=user_prompt_file,
            output_file=output_file,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            temperature=temperature,
            top_p=top_p,
            top_k=top_k,
            min_p=min_p,
            presence_penalty=presence_penalty,
            repetition_penalty=repetition_penalty,
            enable_thinking=enable_thinking,
            verbose=verbose,
            on_event=on_event,
        )
    except RuntimeError as exc:
        details = str(exc)
        lowered = details.lower()
        if "no module named" in lowered and ("mlx_lm" in lowered or "mlx_vlm" in lowered):
            raise RuntimeError("mlx_vlm/mlx_lm is missing. Install mlx-vlm and mlx-lm in this app environment.") from exc
        if "out of memory" in lowered or "memory" in lowered:
            raise RuntimeError(f"RQ screening model ran out of memory. Details: {details[-1200:]}") from exc
        raise RuntimeError(f"RQ screening generation failed. Details: {details[-1200:]}") from exc
