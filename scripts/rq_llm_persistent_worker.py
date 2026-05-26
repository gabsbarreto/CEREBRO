from __future__ import annotations

import contextlib
import json
import sys
import traceback
from pathlib import Path
from typing import Any

from _bootstrap import ensure_project_root

ensure_project_root()

from app.shared.cli import parse_bool
from app.shared.mlx_runtime import cleanup_mlx
from app.shared.rq_chat import split_thinking, strip_thinking
from rq_llm_worker import build_vlm_prompt, generate_text

PROTOCOL_STDOUT = sys.stdout


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), file=PROTOCOL_STDOUT, flush=True)


def emit_event(request_id: str, payload: dict[str, Any]) -> None:
    event = dict(payload)
    event["request_id"] = request_id
    emit(event)


def run_request(
    request: dict[str, Any],
    *,
    cache: dict[str, Any],
) -> None:
    request_id = str(request["request_id"])
    model_path = str(request["model"])
    enable_thinking = parse_bool(request.get("enable_thinking"))
    thinking_budget = max(0, int(request.get("thinking_budget") or 0))
    verbose = parse_bool(request.get("verbose"))

    model = cache.get("model")
    processor = cache.get("processor")
    config = cache.get("config")
    cached_model_path = str(cache.get("model_path") or "")

    if model is None or processor is None or cached_model_path != model_path:
        if model is not None or processor is not None:
            cache.clear()
            cleanup_mlx(collect_garbage=True)
        emit_event(request_id, {"event": "rq_model_loading", "model": model_path})
        from mlx_vlm import load

        with contextlib.redirect_stdout(sys.stderr):
            model, processor = load(model_path)
        config = getattr(model, "config", None)
        cache.update(
            {
                "model_path": model_path,
                "model": model,
                "processor": processor,
                "config": config,
            }
        )
    emit_event(request_id, {"event": "rq_model_loaded", "cached": cached_model_path == model_path})

    system_prompt = Path(str(request["system_prompt_file"])).read_text(encoding="utf-8")
    user_prompt = Path(str(request["user_prompt_file"])).read_text(encoding="utf-8")
    with contextlib.redirect_stdout(sys.stderr):
        prompt = build_vlm_prompt(processor, config, system_prompt, user_prompt, enable_thinking)

    emit_event(
        request_id,
        {
            "event": "rq_generation_started",
            "temperature": float(request["temperature"]),
            "top_p": float(request["top_p"]),
            "top_k": int(request["top_k"]),
            "min_p": float(request["min_p"]),
            "presence_penalty": float(request["presence_penalty"]),
            "repetition_penalty": float(request["repetition_penalty"]),
            "enable_thinking": enable_thinking,
            "thinking_budget": thinking_budget,
            "max_tokens": int(request["max_tokens"]),
            "verbose": verbose,
        },
    )

    with contextlib.redirect_stdout(sys.stderr):
        raw_output, metrics = generate_text(
            model,
            processor,
            prompt,
            max_tokens=int(request["max_tokens"]),
            thinking_budget=thinking_budget,
            enable_thinking=enable_thinking,
            temperature=float(request["temperature"]),
            top_p=float(request["top_p"]),
            top_k=int(request["top_k"]),
            min_p=float(request["min_p"]),
            presence_penalty=float(request["presence_penalty"]),
            repetition_penalty=float(request["repetition_penalty"]),
            verbose=verbose,
        )

    output_path = Path(str(request["output_file"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_output_file = output_path.with_name(f"{output_path.stem}_raw.md")
    raw_output_file.write_text(raw_output.strip() + "\n", encoding="utf-8")

    if enable_thinking:
        reasoning, final_output, found_separator = split_thinking(raw_output)
        if not found_separator or not final_output.strip():
            raise RuntimeError(
                "RQ screening did not reach a final answer after the thinking budget. "
                f"Raw output was saved to {raw_output_file}."
            )
        output = final_output
        metrics["reasoning_chars"] = len(reasoning)
        metrics["final_chars"] = len(final_output)
        metrics["raw_output_file"] = str(raw_output_file)
    else:
        output = strip_thinking(raw_output)

    output_path.write_text(output.strip() + "\n", encoding="utf-8")
    emit_event(request_id, {"event": "rq_generation_finished", "chars": len(output), **metrics})
    emit_event(request_id, {"event": "rq_request_complete"})


def main() -> int:
    cache: dict[str, Any] = {}
    emit({"event": "rq_worker_ready"})
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError as exc:
                emit({"event": "rq_request_failed", "request_id": "", "error": f"Invalid JSON: {exc}"})
                continue
            if request.get("command") == "shutdown":
                break
            if request.get("command") != "run":
                emit(
                    {
                        "event": "rq_request_failed",
                        "request_id": str(request.get("request_id") or ""),
                        "error": "Unknown worker command.",
                    }
                )
                continue
            request_id = str(request.get("request_id") or "")
            try:
                run_request(request, cache=cache)
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                emit_event(request_id, {"event": "rq_request_failed", "error": str(exc)})
    finally:
        cache.clear()
        cleanup_mlx(collect_garbage=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
