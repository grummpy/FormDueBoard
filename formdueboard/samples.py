"""Fictional sample mail so the board can be tried before any real email is added."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import format_datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def write_samples(inbox: Path, today: date | None = None) -> list[Path]:
    inbox.mkdir(parents=True, exist_ok=True)
    today = today or date.today()
    written: list[Path] = []
    for name, message in _messages(today):
        path = inbox / name
        path.write_bytes(message)
        written.append(path)
    return written


def _messages(today: date) -> list[tuple[str, bytes]]:
    zone = ZoneInfo("America/New_York")

    def stamp(day: date, hour: int = 9) -> str:
        moment = datetime(day.year, day.month, day.day, hour, 0, tzinfo=zone)
        return format_datetime(moment)

    sent = today - timedelta(days=1)
    trip_due = today + timedelta(days=3)
    trip_event = today + timedelta(days=10)
    sports_due = today + timedelta(days=9)
    museum_due = today + timedelta(days=6)
    club_due = today + timedelta(days=2)
    samples = [
        (
            "sample-science-center.eml",
            _eml(
                subject="Science center field trip permission slip",
                sender="Ms. Calder <mscalder@example.com>",
                message_id="<sample-science@example.com>",
                date=stamp(sent),
                body=(
                    "Hello families,\n\n"
                    f"The field trip to the Science Center is on {_long(trip_event)}. "
                    f"Please return the permission slip by {_long(trip_due)}.\n\n"
                    "Thank you,\nMs. Calder\n"
                ),
            ),
        ),
        (
            "sample-sports-day.eml",
            _eml(
                subject="Sports day permission slip",
                sender="Ms. Calder <mscalder@example.com>",
                message_id="<sample-sports@example.com>",
                date=stamp(sent, 10),
                body=(
                    f"Sports Day Participation permission slip is due {_long(sports_due)}. Please sign and return it.\n"
                ),
            ),
        ),
        (
            "sample-museum.eml",
            _eml(
                subject="Museum visit form",
                sender="Mr. Okonkwo <mokonkwo@example.com>",
                message_id="<sample-museum@example.com>",
                date=stamp(sent, 11),
                body=f"The museum visit permission slip is due {_long(museum_due)}.\n",
            ),
        ),
        (
            "sample-after-school.eml",
            _eml(
                subject="After-school club form",
                sender="Mr. Okonkwo <mokonkwo@example.com>",
                message_id="<sample-club@example.com>",
                date=stamp(sent, 12),
                body=(f"After-School Club permission slip. Please return it by {_long(club_due)}.\n"),
            ),
        ),
        (
            "sample-cancelled.eml",
            _eml(
                subject="Zoo trip cancelled",
                sender="Ms. Calder <mscalder@example.com>",
                message_id="<sample-cancelled@example.com>",
                date=stamp(sent, 13),
                body=("The field trip to the zoo has been cancelled. Please do not return a permission slip.\n"),
            ),
        ),
        (
            "sample-review.eml",
            _eml(
                subject="Permission slip",
                sender="Activities <activities@example.com>",
                message_id="<sample-review@example.com>",
                date=stamp(sent, 14),
                body=(f"A permission slip is due {_long(today + timedelta(days=4))}. Please send it back.\n"),
            ),
        ),
    ]
    return samples


def _long(day: date) -> str:
    months = [
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
    return f"{months[day.month - 1]} {day.day}"


def _eml(*, subject: str, sender: str, message_id: str, date: str, body: str) -> bytes:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = "family@example.com"
    message["Date"] = date
    message["Message-ID"] = message_id
    message.set_content(body)
    return message.as_bytes()
