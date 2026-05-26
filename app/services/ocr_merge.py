from __future__ import annotations

from pathlib import Path


def merge_page_texts(ocr_dir: Path, output_path: Path) -> str:
    page_files = sorted(ocr_dir.glob("page_*.md"))
    chunks: list[str] = []
    for index, path in enumerate(page_files, start=1):
        text = path.read_text(encoding="utf-8").strip()
        chunks.append(f"[PAGE {index}]\n\n{text}".rstrip())
    merged = "\n\n".join(chunks).strip() + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(merged, encoding="utf-8")
    return merged

