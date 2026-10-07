from datetime import UTC, date, datetime, timedelta

from icalendar import Calendar

from formdueboard.board import highlight
from formdueboard.ics_export import build_ics


def _item(**overrides):
    base = {
        "id": 7,
        "kid_name": "Student A",
        "title": "Field Trip to Science Center",
        "form_label": "Permission slip",
        "due_date": "2026-05-16",
        "status": "todo",
        "cancelled": False,
        "needs_review": False,
        "snippet": "Please return the permission slip by May 16.",
        "subject": "Science center",
        "fee_amount": None,
    }
    base.update(overrides)
    return base


def test_ics_is_valid_and_reminds_two_days_before_in_new_york():
    payload = build_ics(
        [
            _item(),
            _item(id=8, cancelled=True, title="Cancelled trip"),
            _item(id=9, needs_review=True, kid_name=None),
            _item(id=10, status="returned", title="Already back"),
        ],
        now=datetime(2026, 5, 13, 14, 0, tzinfo=UTC),
    )
    calendar = Calendar.from_ical(payload)
    events = [component for component in calendar.walk("VEVENT")]
    assert len(events) == 1
    event = events[0]
    assert "Student A" in str(event.get("summary"))
    start = event.get("dtstart")
    assert start.params.get("TZID") == "America/New_York"
    assert start.dt.hour == 9
    assert start.dt.date() == date(2026, 5, 16) or getattr(start.dt, "day", None) == 16
    alarms = event.walk("VALARM")
    assert len(alarms) == 1
    trigger = alarms[0].decoded("trigger")
    assert trigger == timedelta(days=-2)
    timezones = calendar.walk("VTIMEZONE")
    assert timezones
    assert str(timezones[0].get("tzid")) == "America/New_York"
    assert "BEGIN:VCALENDAR" in payload
    assert payload.endswith("\r\n")


def test_highlight_due_soon_overdue_and_done():
    today = date(2026, 5, 13)
    assert highlight(date(2026, 5, 12), "todo", False, today, 7) == "overdue"
    assert highlight(date(2026, 5, 16), "todo", False, today, 7) == "due_soon"
    assert highlight(date(2026, 6, 2), "todo", False, today, 7) == "normal"
    assert highlight(date(2026, 5, 12), "returned", False, today, 7) == "normal"
    assert highlight(date(2026, 5, 16), "todo", True, today, 7) == "cancelled"
    assert highlight(None, "todo", False, today, 7) == "normal"
