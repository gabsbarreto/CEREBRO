from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from _bootstrap import ensure_project_root

ensure_project_root()

from app.shared.cli import emit_json_event as emit, parse_bool
from app.shared.mlx_runtime import cleanup_mlx
from app.shared.rq_chat import split_thinking, strip_thinking


def generate_text(
    model: Any,
    processor: Any,
    prompt: str,
    max_tokens: int,
    thinking_budget: int,
    enable_thinking: bool,
    temperature: float,
    top_p: float,
    top_k: int,
    min_p: float,
    presence_penalty: float,
    repetition_penalty: float,
    verbose: bool = False,
) -> tuple[str, dict[str, Any]]:
    from mlx_vlm import generate

    logits_processors = None
    if presence_penalty:
        from mlx_lm import sample_utils

        logits_processors = sample_utils.make_logits_processors(
            presence_penalty=presence_penalty,
        )

    kwargs: dict[str, Any] = {
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "top_k": top_k,
        "min_p": min_p,
        "repetition_penalty": repetition_penalty,
        "enable_thinking": enable_thinking,
    }
    if enable_thinking and thinking_budget > 0:
        kwargs["thinking_budget"] = thinking_budget
        kwargs["thinking_start_token"] = "<think>"
    if logits_processors:
        kwargs["logits_processors"] = logits_processors

    if verbose:
        import sys

        from mlx_vlm.generate import StoppingCriteria, stream_generate

        tokenizer = processor.tokenizer if hasattr(processor, "tokenizer") else processor
        eos_tokens = kwargs.get("eos_tokens", None)
        stopping_criteria = kwargs.get("stopping_criteria", None)
        if eos_tokens is not None:
            tokenizer.stopping_criteria.add_eos_token_ids(eos_tokens)
        elif stopping_criteria is not None:
            if isinstance(stopping_criteria, StoppingCriteria) or callable(stopping_criteria):
                tokenizer.stopping_criteria = stopping_criteria
            else:
                raise ValueError("stopping_criteria must be an instance of StoppingCriteria or a callable")
        else:
            tokenizer.stopping_criteria.reset(model.config.eos_token_id)

        text = ""
        last_response = None
        for response in stream_generate(model, processor, prompt, image=None, **kwargs):
            print(response.text, end="", file=sys.stderr, flush=True)
            text += response.text
            last_response = response
        if last_response is None:
            metrics = {
                "prompt_tokens": 0,
                "generation_tokens": 0,
                "peak_memory": 0.0,
            }
            return text, metrics
        result = last_response
        result_text = text
    else:
        result = generate(
            model=model,
            processor=processor,
            prompt=prompt,
            image=None,
            verbose=False,
            **kwargs,
        )
        result_text = str(result.text)
    metrics = {
        "prompt_tokens": int(getattr(result, "prompt_tokens", 0) or 0),
        "generation_tokens": int(getattr(result, "generation_tokens", 0) or 0),
        "peak_memory": float(getattr(result, "peak_memory", 0.0) or 0.0),
    }
    return result_text, metrics


def build_vlm_prompt(processor: Any, config: Any, system_prompt: str, user_prompt: str, enable_thinking: bool) -> str:
    from mlx_vlm.prompt_utils import apply_chat_template

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    return str(
        apply_chat_template(
            processor,
            config,
            messages,
            num_images=0,
            enable_thinking=enable_thinking,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local MLX LLM RQ screening.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--system-prompt-file", required=True)
    parser.add_argument("--user-prompt-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--thinking-budget", type=int, default=0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--top-k", type=int, default=0)
    parser.add_argument("--min-p", type=float, default=0.0)
    parser.add_argument("--presence-penalty", type=float, default=0.0)
    parser.add_argument("--repetition-penalty", type=float, default=1.0)
    parser.add_argument("--enable-thinking", default="false")
    args = parser.parse_args()

    from mlx_vlm import load

    model = None
    processor = None
    try:
        system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
        user_prompt = Path(args.user_prompt_file).read_text(encoding="utf-8")
        enable_thinking = parse_bool(args.enable_thinking)
        thinking_budget = max(0, int(args.thinking_budget))
        emit({"event": "rq_model_loading", "model": args.model})
        model, processor = load(args.model)
        config = getattr(model, "config", None)
        emit({"event": "rq_model_loaded"})
        prompt = build_vlm_prompt(processor, config, system_prompt, user_prompt, enable_thinking)
        emit(
            {
                "event": "rq_generation_started",
                "temperature": float(args.temperature),
                "top_p": float(args.top_p),
                "top_k": int(args.top_k),
                "min_p": float(args.min_p),
                "presence_penalty": float(args.presence_penalty),
                "repetition_penalty": float(args.repetition_penalty),
                "enable_thinking": enable_thinking,
                "thinking_budget": thinking_budget,
                "max_tokens": int(args.max_tokens),
            }
        )
        raw_output, metrics = generate_text(
            model,
            processor,
            prompt,
            max_tokens=int(args.max_tokens),
            thinking_budget=thinking_budget,
            enable_thinking=enable_thinking,
            temperature=float(args.temperature),
            top_p=float(args.top_p),
            top_k=int(args.top_k),
            min_p=float(args.min_p),
            presence_penalty=float(args.presence_penalty),
            repetition_penalty=float(args.repetition_penalty),
        )
        output_path = Path(args.output_file)
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
        emit({"event": "rq_generation_finished", "chars": len(output), **metrics})
    finally:
        del model
        del processor
        cleanup_mlx(collect_garbage=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
