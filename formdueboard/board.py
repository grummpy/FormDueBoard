"""Assemble the checklist the web UI renders."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from formdueboard.config import AppConfig
from formdueboard.db import Database

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def today_in(tz_name: str) -> date:
    return datetime.now(ZoneInfo(tz_name)).date()


def highlight(due: date | None, status: str, cancelled: bool, today: date, soon_days: int) -> str:
    if cancelled:
        return "cancelled"
    if status == "returned" or due is None:
        return "normal"
    if due < today:
        return "overdue"
    if due <= today + timedelta(days=soon_days):
        return "due_soon"
    return "normal"


def format_day(value: date, today: date) -> str:
    month = MONTHS[value.month - 1]
    if value.year == today.year:
        return f"{month} {value.day}"
    return f"{month} {value.day}, {value.year}"


def build_board(db: Database, config: AppConfig, today: date | None = None) -> dict:
    today = today or today_in(config.timezone)
    items = [_present(db, row, today, config.due_soon_days) for row in db.list_items()]
    columns = []
    for kid in config.kids:
        columns.append(
            {
                "name": kid.name,
                "grade": kid.grade,
                "teachers": kid.teachers,
                "items": [item for item in items if item["kid_name"] == kid.name and not item["needs_review"]],
            }
        )
    review = [item for item in items if item["needs_review"]]
    active = [item for item in items if not item["needs_review"] and not item["cancelled"] and item["status"] == "todo"]
    return {
        "today": today.isoformat(),
        "timezone": config.timezone,
        "due_soon_days": config.due_soon_days,
        "inbox_dir": str(config.inbox_dir),
        "gmail_enabled": config.gmail.enabled,
        "kids": columns,
        "review": review,
        "counts": {
            "todo": len(active),
            "overdue": sum(1 for item in active if item["highlight"] == "overdue"),
            "due_soon": sum(1 for item in active if item["highlight"] == "due_soon"),
            "review": len(review),
        },
    }


def _present(db: Database, row: dict, today: date, soon_days: int) -> dict:
    due = date.fromisoformat(row["due_date"]) if row.get("due_date") else None
    event = date.fromisoformat(row["event_date"]) if row.get("event_date") else None
    message = db.message_for(row.get("primary_message_id"))
    attachments = db.attachments_for(row.get("primary_message_id"))
    cancelled = bool(row["cancelled"])
    status = row["status"]
    gmail_url = None
    if message and message.get("gmail_id"):
        gmail_url = f"https://mail.google.com/mail/u/0/#all/{message['gmail_id']}"
    source_path = message.get("source_path") if message else None
    return {
        "id": row["id"],
        "kid_name": row.get("kid_name"),
        "suggested_kid": row.get("suggested_kid"),
        "title": row["title"],
        "form_type": row["form_type"],
        "form_label": row["form_label"],
        "due_date": row.get("due_date"),
        "due_display": format_day(due, today) if due else None,
        "event_date": row.get("event_date"),
        "event_display": format_day(event, today) if event else None,
        "fee_amount": row.get("fee_amount"),
        "status": status,
        "cancelled": cancelled,
        "confidence": row["confidence"],
        "needs_review": bool(row["needs_review"]),
        "review_reason": row.get("review_reason"),
        "snippet": row.get("snippet") or "",
        "highlight": highlight(due, status, cancelled, today, soon_days),
        "sender": message.get("sender") if message else "",
        "subject": message.get("subject") if message else "",
        "source_path": source_path,
        "source_name": file_name(source_path),
        "gmail_url": gmail_url,
        "attachments": attachments,
    }


def file_name(path: str | None) -> str | None:
    if not path:
        return None
    return path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
