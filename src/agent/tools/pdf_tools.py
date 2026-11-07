"""Contract PDF reading: pdfplumber first, OCR (Tesseract) for scanned pages."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pdfplumber

from ..config import settings

log = logging.getLogger(__name__)
MIN_CHARS_PER_PAGE = 40  # fewer characters than this => treat the page as scanned


def find_contract(supplier_name: str, contracts_dir: Path | None = None) -> Path:
    """Convention: contract_<word>_<word>.pdf where every word appears in the supplier name.
    e.g. 'Berlin Precision GmbH' -> contract_berlin_precision.pdf"""
    folder = contracts_dir or settings.contracts_dir
    name = supplier_name.lower()
    for pdf in sorted(folder.glob("contract_*.pdf")):
        words = pdf.stem.removeprefix("contract_").split("_")
        if all(w in name for w in words):
            return pdf
    raise FileNotFoundError(f"No contract PDF found for supplier '{supplier_name}' in {folder}")


def _ocr_page(path: Path, page_number: int) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("OCR needs pytesseract and pdf2image installed.") from e
    try:
        images = convert_from_path(str(path), dpi=300, first_page=page_number, last_page=page_number)
        return "\n".join(pytesseract.image_to_string(img) for img in images)
    except Exception as e:
        raise RuntimeError(
            f"OCR failed on {path.name}. Install Tesseract and poppler (see README). Details: {e}"
        ) from e


def read_pdf(path: str | Path) -> dict[str, Any]:
    """Return {'text': str, 'used_ocr': bool, 'pages': int}."""
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = settings.contracts_dir / path.name
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    parts: list[str] = []
    used_ocr = False
    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if len(text) < MIN_CHARS_PER_PAGE:
                log.info("Page %s of %s has no text layer -> OCR", i, path.name)
                text = _ocr_page(path, i).strip()
                used_ocr = True
            parts.append(text)
    return {"text": "\n\n".join(parts), "used_ocr": used_ocr, "pages": n_pages}
