from datetime import UTC, date, datetime

from formdueboard.dates import decide_dates, weekday_to_date
from formdueboard.ingest import ingest_messages
from formdueboard.mail import load_messages_from_path, normalized_sent_at

ANCHOR = date(2026, 5, 13)  # Wednesday


def test_by_friday_is_the_friday_of_that_week():
    decision = decide_dates("Please sign and return the permission slip by Friday.", ANCHOR)
    assert decision.due_date == date(2026, 5, 15)
    assert decision.conflict is False


def test_tomorrow_and_today():
    assert decide_dates("The slip is due tomorrow.", ANCHOR).due_date == date(2026, 5, 14)
    assert decide_dates("The slip is due today.", ANCHOR).due_date == ANCHOR


def test_next_monday_from_wednesday():
    decision = decide_dates("Please return the permission slip by next Monday.", ANCHOR)
    assert decision.due_date == date(2026, 5, 18)


def test_next_weekday_on_that_weekday_is_one_week_out():
    friday = date(2026, 5, 15)
    assert weekday_to_date(friday, 4, "next") == date(2026, 5, 22)
    assert weekday_to_date(friday, 4, "by") == friday


def test_absolute_date_beats_the_weekday_label():
    text = "Please return the permission slip by Friday, May 15."
    assert decide_dates(text, ANCHOR).due_date == date(2026, 5, 15)


def test_event_date_is_not_the_due_date():
    text = "The field trip to the Science Center is on May 20. Please return the permission slip by May 16."
    decision = decide_dates(text, ANCHOR)
    assert decision.due_date == date(2026, 5, 16)
    assert decision.event_date == date(2026, 5, 20)


def test_event_alone_does_not_become_a_due_date():
    decision = decide_dates("The field trip to the Science Center is on May 20.", ANCHOR)
    assert decision.due_date is None
    assert decision.event_date == date(2026, 5, 20)


def test_numeric_and_iso_dates():
    assert decide_dates("Permission slip due 5/16/2026.", ANCHOR).due_date == date(2026, 5, 16)
    assert decide_dates("Permission slip due 2026-05-16.", ANCHOR).due_date == date(2026, 5, 16)


def test_missing_year_rolls_forward_when_the_day_has_passed():
    december = date(2026, 12, 15)
    decision = decide_dates("Permission slip due January 10.", december)
    assert decision.due_date == date(2027, 1, 10)


def test_conflicting_due_dates():
    decision = decide_dates("The permission slip is due May 16 or due May 18.", ANCHOR)
    assert decision.conflict is True
    assert decision.due_date is None


def test_extended_due_date_uses_the_new_day():
    text = "The permission slip was due May 16. The due date has been extended to May 22."
    decision = decide_dates(text, ANCHOR)
    assert decision.due_changed is True
    assert decision.due_date == date(2026, 5, 22)
    assert decision.conflict is False


def test_mixed_email_date_timezones_sort_and_ingest(tmp_path, kids):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "aware.eml").write_text(
        "From: sender@example.com\nTo: parent@example.com\nDate: Wed, 13 May 2026 12:00:00 -0400\n"
        "Subject: Permission slip\nMessage-ID: <aware@example.com>\n\nPermission slip due May 16.\n",
        encoding="utf-8",
    )
    (inbox / "naive.eml").write_text(
        "From: sender@example.com\nTo: parent@example.com\nDate: Wed, 13 May 2026 11:00:00\n"
        "Subject: Permission slip\nMessage-ID: <naive@example.com>\n\nPermission slip due May 17.\n",
        encoding="utf-8",
    )
    messages = load_messages_from_path(inbox)
    assert all(message.sent_at is None or message.sent_at.tzinfo is not None for message in messages)
    from formdueboard.db import Database

    db = Database(tmp_path / "board.sqlite")
    try:
        result = ingest_messages(db, messages, kids)
    finally:
        db.close()
    assert result.messages == 2


def test_naive_email_timestamp_is_documented_as_utc():
    value = normalized_sent_at(datetime(2026, 5, 13, 11, 0))
    assert value == datetime(2026, 5, 13, 11, 0, tzinfo=UTC)
