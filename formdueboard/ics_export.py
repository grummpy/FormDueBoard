"""Write an iCalendar file with a reminder two days before each open due date."""

from __future__ import annotations

from datetime import UTC, date, datetime


def build_ics(items: list[dict], now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    stamp = moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//FormDueBoard//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:FormDueBoard",
        "X-WR-TIMEZONE:America/New_York",
        *_timezone(),
    ]
    for item in items:
        if not _include(item):
            continue
        due = _as_date(item.get("due_date"))
        if due is None:
            continue
        summary = f"{item.get('kid_name') or 'Form'}: {item.get('title') or 'School form'}"
        description = _description(item)
        uid = f"formdueboard-{item.get('id')}@example.com"
        start = due.strftime("%Y%m%dT090000")
        end_hour = due.strftime("%Y%m%dT093000")
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{stamp}",
                f"DTSTART;TZID=America/New_York:{start}",
                f"DTEND;TZID=America/New_York:{end_hour}",
                f"SUMMARY:{_escape(summary)}",
                f"DESCRIPTION:{_escape(description)}",
                "STATUS:CONFIRMED",
                "BEGIN:VALARM",
                "ACTION:DISPLAY",
                "DESCRIPTION:Form due in 2 days",
                "TRIGGER:-P2D",
                "END:VALARM",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    folded = [_fold(line) for line in lines]
    return "\r\n".join(folded) + "\r\n"


def _include(item: dict) -> bool:
    if item.get("cancelled") in (1, True, "1"):
        return False
    if item.get("needs_review") in (1, True, "1"):
        return False
    if not item.get("due_date"):
        return False
    if item.get("status") == "returned":
        return False
    return True


def _as_date(value) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    return None


def _description(item: dict) -> str:
    parts = [item.get("form_label") or "Form"]
    if item.get("fee_amount"):
        parts.append(f"Fee ${item['fee_amount']}")
    if item.get("snippet"):
        parts.append(str(item["snippet"]))
    if item.get("subject"):
        parts.append(f"Email: {item['subject']}")
    return "\n".join(parts)


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\n", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def _fold(line: str) -> str:
    raw = line.encode("utf-8")
    if len(raw) <= 73:
        return line
    chunks: list[str] = []
    current = ""
    for char in line:
        candidate = current + char
        if len(candidate.encode("utf-8")) > 73:
            chunks.append(current)
            current = " " + char
        else:
            current = candidate
    chunks.append(current)
    return "\r\n".join(chunks)


def _timezone() -> list[str]:
    return [
        "BEGIN:VTIMEZONE",
        "TZID:America/New_York",
        "X-LIC-LOCATION:America/New_York",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:-0500",
        "TZOFFSETTO:-0400",
        "TZNAME:EDT",
        "DTSTART:19700308T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:-0400",
        "TZOFFSETTO:-0500",
        "TZNAME:EST",
        "DTSTART:19701101T020000",
        "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU",
        "END:STANDARD",
        "END:VTIMEZONE",
    ]
