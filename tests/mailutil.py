"""Build synthetic RFC822 messages and a small text PDF."""

from __future__ import annotations

import io
from email.message import EmailMessage


def make_eml(
    *,
    subject: str,
    sender: str,
    body: str = "",
    html: str | None = None,
    to: str = "family@example.com",
    date: str = "Wed, 13 May 2026 09:00:00 -0400",
    message_id: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
    attachments: list[tuple[str, bytes, str, str]] | None = None,
) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = to
    message["Date"] = date
    if message_id:
        message["Message-ID"] = message_id
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = references
    if html and not body:
        message.set_content(html, subtype="html")
    else:
        message.set_content(body)
        if html:
            message.add_alternative(html, subtype="html")
    for filename, data, main, sub in attachments or []:
        message.add_attachment(data, maintype=main, subtype=sub, filename=filename)
    return message.as_bytes()


def simple_pdf(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 12 Tf", "72 700 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -16 Td")
        safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({safe}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{number} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_at = len(out)
    count = len(objects) + 1
    out.extend(f"xref\n0 {count}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(f"trailer << /Size {count} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode())
    return bytes(out)


def simple_docx(paragraphs: list[str]) -> bytes:
    from docx import Document

    buffer = io.BytesIO()
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(buffer)
    return buffer.getvalue()


def to_mbox(messages: list[bytes]) -> bytes:
    chunks: list[bytes] = []
    for raw in messages:
        text = raw.replace(b"\r\n", b"\n")
        if not text.endswith(b"\n"):
            text += b"\n"
        escaped = []
        for line in text.splitlines(keepends=True):
            if line.startswith(b"From "):
                line = b">" + line
            escaped.append(line)
        chunks.append(b"From sender@example.com Wed May 13 09:00:00 2026\n" + b"".join(escaped) + b"\n")
    return b"".join(chunks)
