from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

TRANSLATION_PROJECT = Path(
    "/Users/ha25082/Library/CloudStorage/OneDrive-UniversityofBristol/Documents/Translation Project"
)
NAME_PATTERNS = ("deepseek", "deepseek-ocr", "deepseekocr", "deepseekocr2", "ocr")


def likely_roots() -> list[Path]:
    home = Path.home()
    roots = [
        home / ".cache" / "huggingface" / "hub",
        home / ".cache" / "modelscope",
        home / ".cache" / "mlx",
        home / "Library" / "Caches" / "huggingface",
        TRANSLATION_PROJECT,
        TRANSLATION_PROJECT / "models",
        TRANSLATION_PROJECT / "checkpoints",
        TRANSLATION_PROJECT / "cache",
        TRANSLATION_PROJECT / ".cache",
    ]
    return roots


def candidate_from_env(name: str) -> dict[str, Any] | None:
    value = os.getenv(name)
    if not value:
        return None
    path = Path(value).expanduser()
    return {
        "source": f"environment:{name}",
        "path": str(path) if path.exists() else value,
        "exists": path.exists(),
        "kind": "python-env" if name == "DEEPSEEK_OCR_PYTHON" else "model-env",
    }


def looks_interesting(path: Path) -> bool:
    lowered = path.name.lower()
    return any(pattern in lowered for pattern in NAME_PATTERNS)


def find_candidates(max_depth: int = 6) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for env_name in ["DEEPSEEK_OCR_MODEL_PATH", "DEEPSEEK_OCR_PYTHON"]:
        env_candidate = candidate_from_env(env_name)
        if env_candidate:
            key = str(env_candidate.get("path"))
            seen.add(key)
            candidates.append(env_candidate)

    for root in likely_roots():
        if not root.exists():
            continue
        root_depth = len(root.parts)
        for path in root.rglob("*"):
            if len(path.parts) - root_depth > max_depth:
                continue
            if not looks_interesting(path):
                continue
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            if path.is_dir() and path.name.startswith("models--") and "deepseek" in path.name.lower():
                snapshots = sorted((path / "snapshots").glob("*")) if (path / "snapshots").exists() else []
                for snapshot in snapshots:
                    snapshot_key = str(snapshot)
                    if snapshot_key in seen:
                        continue
                    seen.add(snapshot_key)
                    candidates.append(
                        {
                            "source": str(path),
                            "path": snapshot_key,
                            "exists": snapshot.exists(),
                            "kind": "model-snapshot",
                            "model_id": path.name.replace("models--", "").replace("--", "/"),
                        }
                    )
            candidates.append(
                {
                    "source": str(root),
                    "path": key,
                    "exists": path.exists(),
                    "kind": "directory" if path.is_dir() else "file",
                }
            )
    return sorted(candidates, key=rank_candidate)


def rank_candidate(candidate: dict[str, Any]) -> tuple[int, str]:
    path = str(candidate.get("path") or "").lower()
    kind = str(candidate.get("kind") or "")
    if kind == "model-env":
        return (0, path)
    if kind == "model-snapshot" and "deepseek-ocr-2-8bit" in path:
        return (1, path)
    if kind == "model-snapshot" and "deepseek-ocr-2-bf16" in path:
        return (2, path)
    if kind == "model-snapshot" and "deepseek-ocr-2" in path:
        return (3, path)
    if kind == "model-snapshot" and "deepseek-ocr" in path:
        return (4, path)
    if kind == "directory" and "deepseek-ocr-2" in path and ".locks" not in path:
        return (5, path)
    if "deepseek" in path and ".locks" not in path:
        return (6, path)
    if kind == "python-env":
        return (98, path)
    return (99, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Find local DeepSeek OCR / DeepSeekOCR2 candidates.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()
    candidates = find_candidates()
    if args.json:
        print(json.dumps({"candidates": candidates}, ensure_ascii=False, indent=2))
        return 0
    if not candidates:
        print("No DeepSeek OCR candidates found.")
        return 1
    for candidate in candidates:
        print(f"{candidate['kind']}: {candidate['path']} ({candidate['source']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
