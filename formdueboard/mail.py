"""Read .eml files and mbox exports into plain text plus attachments."""

from __future__ import annotations

import hashlib
import mailbox
import re
from datetime import UTC, datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path

from formdueboard.attachments import extract_attachment_text
from formdueboard.model import ParsedAttachment, ParsedMessage

MAIL_SUFFIXES = {".eml", ".mbox", ".mbx"}


def normalized_sent_at(value: datetime | None) -> datetime | None:
    """Return a UTC-aware timestamp; malformed or missing dates stay ``None``.

    RFC 5322 dates without an offset are ambiguous. We intentionally interpret
    them as UTC so mixed exports have a deterministic ordering; the README
    documents this conservative fallback.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def load_messages_from_path(path: Path) -> list[ParsedMessage]:
    path = Path(path)
    if path.is_file():
        return _load_file(path)
    if not path.is_dir():
        raise FileNotFoundError(path)
    messages: list[ParsedMessage] = []
    for file in sorted(item for item in path.rglob("*") if item.is_file()):
        if file.name.startswith("."):
            continue
        if file.suffix.lower() in MAIL_SUFFIXES or _sniff_mail(file):
            messages.extend(_load_file(file))
    messages.sort(key=lambda message: (message.sent_at is None, message.sent_at))
    return messages


def parse_eml_bytes(data: bytes, source_path: str | None = None) -> ParsedMessage:
    raw_hash = hashlib.sha256(data).hexdigest()
    parsed = BytesParser(policy=policy.default).parsebytes(data)
    sent_at = None
    if parsed.get("date"):
        try:
            sent_at = normalized_sent_at(parsedate_to_datetime(str(parsed.get("date"))))
        except (TypeError, ValueError, IndexError, OverflowError):
            sent_at = None
    message_id = parsed.get("message-id")
    return ParsedMessage(
        message_id=str(message_id).strip() if message_id else None,
        raw_hash=raw_hash,
        source_path=source_path,
        subject=str(parsed.get("subject") or ""),
        sender=str(parsed.get("from") or ""),
        recipients=str(parsed.get("to") or ""),
        sent_at=sent_at,
        body_text=_body_text(parsed),
        in_reply_to=_clean_header(parsed.get("in-reply-to")),
        references=_clean_header(parsed.get("references")),
        attachments=_attachments(parsed),
    )


def parse_mbox_bytes(data: bytes, source_path: str | None = None) -> list[ParsedMessage]:
    # mailbox.mbox wants a filename. Callers that already have a path use parse_mbox.
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(suffix=".mbox") as handle:
        handle.write(data)
        handle.flush()
        return parse_mbox(Path(handle.name), source_path=source_path)


def parse_mbox(path: Path, source_path: str | None = None) -> list[ParsedMessage]:
    box = mailbox.mbox(path)
    try:
        messages = []
        for message in box:
            raw = message.as_bytes()
            messages.append(parse_eml_bytes(raw, source_path=source_path or str(path)))
        return messages
    finally:
        box.close()


def _load_file(path: Path) -> list[ParsedMessage]:
    if path.suffix.lower() in {".mbox", ".mbx"} or _looks_like_mbox(path):
        return parse_mbox(path, source_path=str(path))
    return [parse_eml_bytes(path.read_bytes(), source_path=str(path))]


def _sniff_mail(path: Path) -> bool:
    if path.suffix.lower() in {".pdf", ".docx", ".txt", ".html", ".ics", ".png", ".jpg", ".svg"}:
        return False
    try:
        head = path.read_bytes()[:400].lstrip()
    except OSError:
        return False
    return head.startswith((b"From ", b"Return-Path:", b"MIME-Version:", b"Received:", b"From:"))


def _looks_like_mbox(path: Path) -> bool:
    try:
        head = path.read_bytes()[:80]
    except OSError:
        return False
    return head.startswith(b"From ") and b"\n" in head


def _clean_header(value: object) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", str(value)).strip()


def _body_text(parsed) -> str:
    if parsed.is_multipart():
        plain: list[str] = []
        html: list[str] = []
        for part in parsed.walk():
            if part.get_content_disposition() == "attachment":
                continue
            ctype = part.get_content_type()
            if ctype not in {"text/plain", "text/html"}:
                continue
            try:
                content = part.get_content()
            except (KeyError, UnicodeError, LookupError, ValueError):
                continue
            if not isinstance(content, str):
                continue
            if ctype == "text/plain":
                plain.append(content)
            else:
                html.append(content)
        if any(piece.strip() for piece in plain):
            return "\n".join(plain).strip()
        if html:
            return "\n".join(html_to_text(piece) for piece in html).strip()
        return ""
    try:
        content = parsed.get_content()
    except (KeyError, UnicodeError, LookupError, ValueError):
        return ""
    if not isinstance(content, str):
        return ""
    if parsed.get_content_type() == "text/html":
        return html_to_text(content).strip()
    return content.strip()


def _attachments(parsed) -> list[ParsedAttachment]:
    if not parsed.is_multipart():
        return []
    found: list[ParsedAttachment] = []
    for part in parsed.walk():
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        ctype = part.get_content_type()
        if disposition != "attachment" and not filename:
            continue
        if ctype in {"text/plain", "text/html"} and disposition != "attachment":
            continue
        try:
            data = part.get_payload(decode=True) or b""
        except (KeyError, UnicodeError, LookupError, ValueError):
            data = b""
        if not isinstance(data, bytes):
            data = b""
        name = filename or "attachment"
        found.append(
            ParsedAttachment(
                filename=name,
                content_type=ctype,
                extracted_text=extract_attachment_text(name, ctype, data),
            )
        )
    return found


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&#39;", "'")
        .replace("&quot;", '"')
    )
    return re.sub(r"[ \t]+", " ", text).strip()
