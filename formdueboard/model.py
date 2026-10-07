"""Shared data objects for parsed mail and extracted form items."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class ParsedAttachment:
    filename: str
    content_type: str
    extracted_text: str


@dataclass
class ParsedMessage:
    message_id: str | None
    raw_hash: str
    source_path: str | None
    subject: str
    sender: str
    recipients: str
    sent_at: datetime | None
    body_text: str
    in_reply_to: str | None
    references: str | None
    attachments: list[ParsedAttachment] = field(default_factory=list)
    gmail_id: str | None = None

    def combined_text(self) -> str:
        parts = [self.subject or "", self.body_text or ""]
        parts.extend(att.extracted_text for att in self.attachments if att.extracted_text)
        return "\n".join(parts)

    def anchor_date(self, tz_name: str) -> date | None:
        if self.sent_at is None:
            return None
        sent = self.sent_at
        if sent.tzinfo is not None:
            from zoneinfo import ZoneInfo

            sent = sent.astimezone(ZoneInfo(tz_name))
        return sent.date()


@dataclass
class ExtractedItem:
    title: str
    form_type: str
    form_label: str
    due_date: date | None
    event_date: date | None
    fee_amount: str | None
    kid_name: str | None
    suggested_kid: str | None
    confidence: float
    needs_review: bool
    review_reason: str | None
    cancelled: bool
    snippet: str
    due_changed: bool
    normalized_subject: str
    attachment_names: list[str] = field(default_factory=list)
