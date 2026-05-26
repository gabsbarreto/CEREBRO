from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def response_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text)
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            content_type = content.get("type") if isinstance(content, dict) else getattr(content, "type", None)
            if content_type in {"output_text", "text"}:
                value = content.get("text", "") if isinstance(content, dict) else getattr(content, "text", "")
                if value:
                    parts.append(str(value))
    return "\n".join(parts).strip()


def response_payload(response: Any) -> dict[str, Any] | Any:
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if hasattr(response, "to_dict"):
        return response.to_dict()
    if isinstance(response, (dict, list, str, int, float, bool)):
        return response
    return {"repr": repr(response)}


def write_response_artifacts(
    *,
    response: Any,
    request_summary: dict[str, Any],
    response_json_file: Path,
    request_json_file: Path,
) -> None:
    response_json_file.parent.mkdir(parents=True, exist_ok=True)
    response_json_file.write_text(
        json.dumps(response_payload(response), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    request_json_file.parent.mkdir(parents=True, exist_ok=True)
    request_json_file.write_text(
        json.dumps(request_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def response_diagnostics(response: Any) -> dict[str, Any]:
    output_items = getattr(response, "output", []) or []
    return {
        "id": getattr(response, "id", None),
        "status": getattr(response, "status", None),
        "incomplete_details": _jsonable(getattr(response, "incomplete_details", None)),
        "output_types": [
            item.get("type") if isinstance(item, dict) else getattr(item, "type", None)
            for item in output_items
        ],
        "usage": _jsonable(getattr(response, "usage", None)),
    }


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, (str, int, float, bool, list, dict)):
        return value
    return str(value)

