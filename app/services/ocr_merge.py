from __future__ import annotations

from pathlib import Path


def merge_page_texts(ocr_dir: Path, output_path: Path) -> str:
    page_files = sorted(ocr_dir.glob("page_*.md"))
    chunks: list[str] = []
    for index, path in enumerate(page_files, start=1):
        text = path.read_text(encoding="utf-8").strip()
        chunks.append(f"[{ocr_page_label(path, index)}]\n\n{text}".rstrip())
    merged = "\n\n".join(chunks).strip() + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(merged, encoding="utf-8")
    return merged


def ocr_page_label(path: Path, fallback_page_number: int) -> str:
    """Return human-readable source context for bundle-aware OCR files."""

    stem = path.stem
    if "__supporting_" in stem:
        try:
            source_number, page_number = stem.split("__supporting_", 1)[1].split("_", 1)
            return f"SUPPORTING PDF {int(source_number)} - PAGE {int(page_number)}"
        except (TypeError, ValueError):
            pass
    if "__primary_" in stem:
        try:
            page_number = int(stem.split("__primary_", 1)[1])
            return f"PRIMARY PDF - PAGE {page_number}"
        except (TypeError, ValueError):
            pass
    return f"PAGE {fallback_page_number}"
