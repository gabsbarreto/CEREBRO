from __future__ import annotations

from pathlib import Path


class PageRenderer:
    """PDF page renderer adapted from existing Translation Project renderer."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, int, int, bool, bool, bool, float], Path] = {}

    def render_page(
        self,
        pdf_path: Path,
        page_number: int,
        out_path: Path,
        dpi: int = 100,
        grayscale: bool = False,
        binarize: bool = False,
        denoise: bool = False,
        contrast: float = 1.0,
    ) -> Path:
        key = (str(pdf_path), page_number, dpi, grayscale, binarize, denoise, float(contrast))
        cached = self._cache.get(key)
        if cached and cached.exists():
            return cached
        if out_path.exists():
            self._cache[key] = out_path
            return out_path

        pdfium, image_tools = _load_rendering_dependencies()
        Image, ImageEnhance, ImageFilter, ImageOps = image_tools

        pdf = pdfium.PdfDocument(str(pdf_path))
        try:
            page = pdf[page_number - 1]
            scale = dpi / 72
            bitmap = page.render(scale=scale)
            pil_image: Image.Image = bitmap.to_pil()

            if grayscale:
                pil_image = ImageOps.grayscale(pil_image)
            if contrast != 1.0:
                pil_image = ImageEnhance.Contrast(pil_image).enhance(contrast)
            if denoise:
                pil_image = pil_image.filter(ImageFilter.MedianFilter(size=3))
            if binarize:
                gray = ImageOps.grayscale(pil_image)
                pil_image = gray.point(lambda x: 0 if x < 140 else 255, mode="1")

            out_path.parent.mkdir(parents=True, exist_ok=True)
            pil_image.save(out_path)
            self._cache[key] = out_path
            return out_path
        finally:
            try:
                pdf.close()
            except Exception:
                pass


def page_count(pdf_path: Path) -> int:
    pdfium, _image_tools = _load_rendering_dependencies()
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        return len(pdf)
    finally:
        try:
            pdf.close()
        except Exception:
            pass


def render_pdf_to_images(pdf_path: Path, rendered_dir: Path, ocr_dir: Path, dpi: int = 100) -> list[Path]:
    _pdfium, image_tools = _load_rendering_dependencies()
    Image = image_tools[0]
    renderer = PageRenderer()
    total = page_count(pdf_path)
    if total <= 0:
        return []

    ocr_paths: list[Path] = []
    for page_number in range(1, total + 1):
        png_path = rendered_dir / f"page_{page_number:04d}.png"
        renderer.render_page(pdf_path, page_number, png_path, dpi=dpi)

        jpg_path = ocr_dir / f"page_{page_number:04d}.jpg"
        jpg_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(png_path) as image:
            rgb = image.convert("RGB")
            rgb.save(jpg_path, format="JPEG", quality=92)
        ocr_paths.append(jpg_path)
    return ocr_paths


def _load_rendering_dependencies():
    try:
        import pypdfium2 as pdfium
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PDF rendering dependencies are missing. Activate the project environment and run "
            "`pip install -r requirements.txt`."
        ) from exc
    return pdfium, (Image, ImageEnhance, ImageFilter, ImageOps)
