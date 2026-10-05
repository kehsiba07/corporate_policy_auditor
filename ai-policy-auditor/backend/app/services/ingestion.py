import logging
import re

import pdfplumber
import pytesseract
from pdf2image import convert_from_path

from app.services import PipelineError

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS = 20


class IngestionError(PipelineError):
    pass


def _table_to_text(table) -> str:
    rows = []
    for row in table or []:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows)


def _outside_tables(bboxes):
    def keep(obj):
        if obj.get("object_type") != "char":
            return True
        x = (obj["x0"] + obj["x1"]) / 2
        y = (obj["top"] + obj["bottom"]) / 2
        return not any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in bboxes)

    return keep


def _ocr_page(file_path: str, page_number: int) -> str:
    try:
        images = convert_from_path(file_path, first_page=page_number, last_page=page_number)
        return "\n".join(pytesseract.image_to_string(img) for img in images).strip()
    except Exception as exc:
        logger.exception("OCR failed on page %s", page_number)
        raise IngestionError(
            "OCR failed. Ensure Poppler and Tesseract are installed and on PATH."
        ) from exc


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extracts text with page markers ("=== PAGE n ===") and tables as pipe-separated rows.
    Falls back to Tesseract OCR for image-only pages. Raises IngestionError on failure.
    """
    parts = []
    try:
        with pdfplumber.open(file_path) as pdf:
            if not pdf.pages:
                raise IngestionError("The PDF contains no pages.")

            for number, page in enumerate(pdf.pages, start=1):
                parts.append(f"=== PAGE {number} ===")

                tables = page.find_tables()
                bboxes = [t.bbox for t in tables]
                body = page.filter(_outside_tables(bboxes)) if bboxes else page
                page_text = (body.extract_text() or "").strip()

                if not page_text and not tables:
                    logger.info("Page %s has no text layer; running OCR", number)
                    page_text = _ocr_page(file_path, number)

                if page_text:
                    parts.append(page_text)

                for t_index, table in enumerate(tables, start=1):
                    table_text = _table_to_text(table.extract())
                    if table_text:
                        parts.append(
                            f"[TABLE {t_index} - PAGE {number}]\n{table_text}\n[END TABLE]"
                        )
    except IngestionError:
        raise
    except Exception as exc:
        logger.exception("PDF ingestion failed")
        raise IngestionError(
            "The PDF could not be read. It may be corrupt or password-protected."
        ) from exc

    text = "\n".join(parts)
    content_chars = len(re.sub(r"=== PAGE \d+ ===|\s", "", text))
    if content_chars < MIN_TEXT_CHARS:
        raise IngestionError("No readable text could be extracted from the PDF.")

    logger.info("Ingested %s characters from %s pages", len(text), len(pdf.pages))
    return text