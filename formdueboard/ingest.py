"""File extracted forms into SQLite, updating threads and dropping duplicates."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

from formdueboard.config import KidConfig
from formdueboard.dates import decide_dates, is_due_change
from formdueboard.db import Database
from formdueboard.extract import _cancelled, extract_from_message, normalize_title
from formdueboard.model import ParsedMessage


@dataclass
class IngestResult:
    messages: int = 0
    created: int = 0
    updated: int = 0
    duplicates: int = 0
    skipped: int = 0


def ingest_messages(
    db: Database,
    messages: list[ParsedMessage],
    kids: list[KidConfig],
    threshold: float = 0.55,
    tz_name: str = "America/New_York",
) -> IngestResult:
    result = IngestResult()
    ordered = sorted(messages, key=lambda message: (message.sent_at is None, message.sent_at or ""))
    for message in ordered:
        result.messages += 1
        if db.has_raw_hash(message.raw_hash) or db.has_message_id(message.message_id):
            result.duplicates += 1
            continue
        message_row_id = db.insert_message(message)
        related = db.items_for_references(message)
        extracted = extract_from_message(message, kids, threshold=threshold, tz_name=tz_name)
        if not extracted:
            if _apply_thread_note(db, message, message_row_id, related, tz_name):
                result.updated += 1
            else:
                result.skipped += 1
            continue
        for item in extracted:
            action = _merge_item(db, message_row_id, item, related)
            if action == "created":
                result.created += 1
            elif action == "updated":
                result.updated += 1
            else:
                result.duplicates += 1
    return result


def fingerprint(kid_name: str | None, form_type: str, title: str, due_date: date | str | None) -> str:
    if isinstance(due_date, date):
        due = due_date.isoformat()
    else:
        due = due_date or ""
    raw = "|".join(
        [
            (kid_name or "").casefold(),
            form_type or "",
            normalize_title(title or ""),
            due,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _merge_item(db: Database, message_row_id: int, item, related: list[dict]) -> str:
    fp = fingerprint(item.kid_name, item.form_type, item.title, item.due_date)
    existing = db.find_fingerprint(fp)
    if existing is None:
        existing = db.find_loose(item.normalized_subject, item.kid_name, item.form_type, item.due_date)
    thread_item = _pick_related(related, item)

    if item.cancelled and thread_item is not None:
        db.set_cancelled(int(thread_item["id"]))
        db.link_message(int(thread_item["id"]), message_row_id)
        return "updated"
    if item.due_changed and thread_item is not None and item.due_date is not None:
        new_fp = fingerprint(
            thread_item.get("kid_name"),
            thread_item["form_type"],
            thread_item["title"],
            item.due_date,
        )
        db.update_due(int(thread_item["id"]), item.due_date, new_fp)
        db.link_message(int(thread_item["id"]), message_row_id)
        return "updated"
    if existing is not None:
        db.link_message(int(existing["id"]), message_row_id)
        return "duplicate"
    if thread_item is not None and _same_due(thread_item.get("due_date"), item.due_date):
        db.link_message(int(thread_item["id"]), message_row_id)
        return "duplicate"

    db.insert_item(item, message_row_id, fp)
    return "created"


def _apply_thread_note(db, message, message_row_id: int, related: list[dict], tz_name: str) -> bool:
    if not related:
        return False
    text = message.combined_text()
    if _cancelled(text):
        for row in related:
            db.set_cancelled(int(row["id"]))
            db.link_message(int(row["id"]), message_row_id)
        return True
    if is_due_change(text):
        decision = decide_dates(text, message.anchor_date(tz_name))
        if decision.due_date is None:
            return False
        for row in related:
            new_fp = fingerprint(row.get("kid_name"), row["form_type"], row["title"], decision.due_date)
            db.update_due(int(row["id"]), decision.due_date, new_fp)
            db.link_message(int(row["id"]), message_row_id)
        return True
    return False


def _pick_related(related: list[dict], item) -> dict | None:
    if not related:
        return None
    if item.kid_name:
        same_kid = [row for row in related if (row.get("kid_name") or None) == item.kid_name]
        if same_kid:
            return same_kid[0]
    same_form = [row for row in related if row.get("form_type") == item.form_type]
    if same_form:
        return same_form[0]
    if len(related) == 1:
        return related[0]
    return None


def _same_due(stored, found: date | None) -> bool:
    if found is None:
        return True
    return (stored or None) == found.isoformat()
