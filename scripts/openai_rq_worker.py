from __future__ import annotations

import argparse
import json
from pathlib import Path

from _bootstrap import ensure_project_root

ensure_project_root()

from app.shared.cli import emit_json_event as emit, parse_bool
from app.shared.openai_responses import response_diagnostics, response_text, write_response_artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Run OpenAI Responses API RQ screening.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--system-prompt-file", required=True)
    parser.add_argument("--user-prompt-file", required=True)
    parser.add_argument("--output-file", required=True)
    parser.add_argument("--max-output-tokens", type=int, default=30000)
    parser.add_argument("--enable-reasoning", default="true")
    parser.add_argument("--reasoning-effort", default="medium")
    parser.add_argument("--response-json-file", default="")
    parser.add_argument("--request-json-file", default="")
    parser.add_argument("--input-file-id", default="")
    parser.add_argument("--input-file-path", default="")
    args = parser.parse_args()

    from openai import OpenAI

    system_prompt = Path(args.system_prompt_file).read_text(encoding="utf-8")
    user_prompt = Path(args.user_prompt_file).read_text(encoding="utf-8")
    enable_reasoning = parse_bool(args.enable_reasoning)
    effort = str(args.reasoning_effort or "medium").strip()

    emit({"event": "rq_model_loading", "model": args.model, "provider": "openai"})
    client = OpenAI()
    emit({"event": "rq_model_loaded", "provider": "openai"})
    input_file_id = str(args.input_file_id or "").strip()
    uploaded_file_id = ""
    if not input_file_id and str(args.input_file_path or "").strip():
        input_path = Path(args.input_file_path)
        emit({"event": "openai_file_upload_started", "provider": "openai", "path": str(input_path)})
        with input_path.open("rb") as handle:
            uploaded = client.files.create(file=handle, purpose="user_data")
        input_file_id = str(uploaded.id)
        uploaded_file_id = input_file_id
        emit({"event": "openai_file_uploaded", "provider": "openai", "file_id": input_file_id})
    elif input_file_id:
        emit({"event": "openai_file_reused", "provider": "openai", "file_id": input_file_id})
    emit(
        {
            "event": "rq_generation_started",
            "provider": "openai",
            "model": args.model,
            "max_output_tokens": int(args.max_output_tokens),
            "enable_reasoning": enable_reasoning,
            "reasoning_effort": effort if enable_reasoning else None,
            "input_file": bool(input_file_id),
        }
    )
    user_content: list[dict[str, str]] = []
    if input_file_id:
        user_content.append(
            {
                "type": "input_file",
                "file_id": input_file_id,
            }
        )
    user_content.append(
        {
            "type": "input_text",
            "text": user_prompt,
        }
    )
    request: dict[str, Any] = {
        "model": args.model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": system_prompt,
                    }
                ],
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        "max_output_tokens": int(args.max_output_tokens),
    }
    if enable_reasoning:
        request["reasoning"] = {"effort": effort}
    response = client.responses.create(**request)
    response_json_file = Path(args.response_json_file) if args.response_json_file else Path(args.output_file).with_name("openai_response.json")
    request_json_file = Path(args.request_json_file) if args.request_json_file else Path(args.output_file).with_name("openai_request.json")
    write_response_artifacts(
        response=response,
        response_json_file=response_json_file,
        request_json_file=request_json_file,
        request_summary={
            "model": args.model,
            "system_prompt_file": str(Path(args.system_prompt_file).resolve()),
            "user_prompt_file": str(Path(args.user_prompt_file).resolve()),
            "output_file": str(Path(args.output_file).resolve()),
            "max_output_tokens": int(args.max_output_tokens),
            "enable_reasoning": enable_reasoning,
            "reasoning_effort": effort if enable_reasoning else None,
            "input_file_id": input_file_id,
            "input_file_uploaded": bool(uploaded_file_id),
        },
    )
    output = response_text(response)
    diagnostics = response_diagnostics(response)
    if not output.strip():
        emit(
            {
                "event": "rq_generation_empty",
                "provider": "openai",
                "response_id": diagnostics.get("id"),
                "status": diagnostics.get("status"),
                "incomplete_details": diagnostics.get("incomplete_details"),
                "output_types": diagnostics.get("output_types"),
                "usage": diagnostics.get("usage"),
                "response_json_file": str(response_json_file),
                "request_json_file": str(request_json_file),
            }
        )
        raise RuntimeError(
            "OpenAI returned an empty final output. "
            f"Diagnostics: {json.dumps(diagnostics, ensure_ascii=False)}. "
            f"Raw response saved to {response_json_file}"
        )
    Path(args.output_file).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output_file).write_text(output.strip() + "\n", encoding="utf-8")
    emit(
        {
            "event": "rq_generation_finished",
            "provider": "openai",
            "response_id": getattr(response, "id", None),
            "chars": len(output),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
