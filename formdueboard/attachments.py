"""Pull text out of PDF and DOCX attachments. Scanned images are left alone."""

from __future__ import annotations

import io


def extract_attachment_text(filename: str, content_type: str, data: bytes) -> str:
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    try:
        if ctype == "application/pdf" or name.endswith(".pdf"):
            return _pdf_text(data)
        if name.endswith(".docx") or "wordprocessingml" in ctype:
            return _docx_text(data)
    except Exception:
        return ""
    return ""


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()


def _docx_text(data: bytes) -> str:
    from docx import Document

    document = Document(io.BytesIO(data))
    return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
