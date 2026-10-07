"""Find due dates and event dates without an LLM.

Weekday phrases are resolved from the email's own date:

* "by Friday", "this Friday", and "on Friday" mean the next time that weekday
  occurs, including today when the email was sent on that weekday.
* "next Friday" means the same upcoming weekday, unless the email was sent on
  Friday, in which case it means one week later.
* "tomorrow" and "today" are one day after the email date, and the email date.
* A month-day without a year uses the email's year. If that day is more than
  14 days before the email, it rolls to next year.
* Numeric dates are month/day/year, matching America/New_York school mail.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

MONTH_RE = re.compile(
    r"\b(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|"
    r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+"
    r"(?P<day>\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{4}))?\b",
    re.IGNORECASE,
)
NUMERIC_RE = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{2,4})\b")
ISO_RE = re.compile(r"\b(?P<year>20\d{2})-(?P<month>\d{2})-(?P<day>\d{2})\b")
RELATIVE_RE = re.compile(r"\b(?P<word>today|tomorrow)\b", re.IGNORECASE)
WEEKDAY_RE = re.compile(
    r"\b(?:(?P<qual>next|this|by|before|on|due)\s+)?"
    r"(?P<day>monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
    re.IGNORECASE,
)
DUE_CUES = re.compile(
    r"\b(due date|due by|due on|due|deadline|no later than|submit by|turn in by|"
    r"return(?:ed)? by|please return|sign and return|forms? (?:is|are) due)\b",
    re.IGNORECASE,
)
EVENT_CUES = re.compile(
    r"\b(field trip|trip is|trip on|takes place|scheduled for|will be held|held on|"
    r"picture day is|event is|event on|visit is|visit on)\b",
    re.IGNORECASE,
)
DUE_CHANGE = re.compile(
    r"\b(extended|now due|changed to|moved to|postponed|pushed to|"
    r"new due date|new due|rescheduled)\b",
    re.IGNORECASE,
)


@dataclass
class DateHit:
    found: date
    start: int
    end: int
    kind: str
    raw: str


def weekday_to_date(anchor: date, weekday: int, qualifier: str | None) -> date:
    delta = (weekday - anchor.weekday()) % 7
    if qualifier and qualifier.lower() == "next" and delta == 0:
        delta = 7
    return anchor + timedelta(days=delta)


def infer_year(month: int, day: int, anchor: date) -> date | None:
    try:
        candidate = date(anchor.year, month, day)
    except ValueError:
        return None
    if candidate < anchor - timedelta(days=14):
        try:
            return date(anchor.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def find_dates(text: str, anchor: date | None) -> list[DateHit]:
    if anchor is None:
        anchor = date.today()
    hits: list[DateHit] = []
    occupied: list[tuple[int, int]] = []

    def claim(start: int, end: int) -> bool:
        for left, right in occupied:
            if start < right and end > left:
                return False
        occupied.append((start, end))
        return True

    for match in MONTH_RE.finditer(text):
        month = MONTHS[match.group("mon").lower().rstrip(".")]
        day = int(match.group("day"))
        year = match.group("year")
        if year:
            try:
                found = date(int(year), month, day)
            except ValueError:
                continue
        else:
            found = infer_year(month, day, anchor)
            if found is None:
                continue
        if claim(match.start(), match.end()):
            hits.append(DateHit(found, match.start(), match.end(), "unknown", match.group(0)))

    for match in NUMERIC_RE.finditer(text):
        month = int(match.group("month"))
        day = int(match.group("day"))
        year = int(match.group("year"))
        if year < 100:
            year += 2000
        try:
            found = date(year, month, day)
        except ValueError:
            continue
        if claim(match.start(), match.end()):
            hits.append(DateHit(found, match.start(), match.end(), "unknown", match.group(0)))

    for match in ISO_RE.finditer(text):
        try:
            found = date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
        except ValueError:
            continue
        if claim(match.start(), match.end()):
            hits.append(DateHit(found, match.start(), match.end(), "unknown", match.group(0)))

    for match in RELATIVE_RE.finditer(text):
        if not claim(match.start(), match.end()):
            continue
        word = match.group("word").lower()
        found = anchor if word == "today" else anchor + timedelta(days=1)
        hits.append(DateHit(found, match.start(), match.end(), "unknown", match.group(0)))

    for match in WEEKDAY_RE.finditer(text):
        if not claim(match.start(), match.end()):
            continue
        # "Friday, May 15" is the absolute date, not a second weekday guess.
        tail = text[match.end() : match.end() + 6]
        end = match.end()
        if re.match(r"\s*,?\s*[A-Z]", tail) and any(h.start >= end and h.start <= end + 4 for h in hits):
            continue
        weekday = WEEKDAYS[match.group("day").lower()]
        found = weekday_to_date(anchor, weekday, match.group("qual"))
        hits.append(DateHit(found, match.start(), match.end(), "unknown", match.group(0)))

    hits.sort(key=lambda hit: hit.start)
    for hit in hits:
        window = text[max(0, hit.start - 90) : hit.start]
        hit.kind = _classify(window)
    return hits


def _classify(window: str) -> str:
    due = list(DUE_CUES.finditer(window))
    event = list(EVENT_CUES.finditer(window))
    if not due and not event:
        return "unknown"
    due_at = due[-1].end() if due else -1
    event_at = event[-1].end() if event else -1
    return "due" if due_at >= event_at else "event"


def is_due_change(text: str) -> bool:
    return DUE_CHANGE.search(text) is not None


@dataclass
class DateDecision:
    due_date: date | None
    event_date: date | None
    conflict: bool
    due_changed: bool


def decide_dates(text: str, anchor: date | None) -> DateDecision:
    hits = find_dates(text, anchor)
    dues = [hit for hit in hits if hit.kind == "due"]
    events = [hit for hit in hits if hit.kind == "event"]
    unknowns = [hit for hit in hits if hit.kind == "unknown"]
    changed = is_due_change(text)

    if changed and (dues or unknowns):
        pool = dues or unknowns
        change_at = DUE_CHANGE.search(text).start()  # type: ignore[union-attr]
        after = [hit for hit in pool if hit.start >= change_at]
        chosen = (after or pool)[-1]
        event_date = next((hit.found for hit in events if hit.found != chosen.found), None)
        return DateDecision(chosen.found, event_date, False, True)

    if not dues and len(unknowns) == 1 and not events:
        dues = unknowns

    unique_dues = list(dict.fromkeys(hit.found for hit in dues))
    conflict = len(unique_dues) > 1
    due_date = unique_dues[0] if len(unique_dues) == 1 else None
    event_date = next((hit.found for hit in events if hit.found != due_date), None)
    return DateDecision(due_date, event_date, conflict, False)
