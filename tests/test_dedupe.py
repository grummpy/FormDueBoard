from tests.conftest import ingest_files
from tests.mailutil import make_eml, to_mbox

TEACHER = "Ms. Calder <mscalder@example.com>"
DATE = "Wed, 13 May 2026 09:00:00 -0400"
LATER = "Thu, 14 May 2026 09:00:00 -0400"


def _sports(message_id: str, subject: str, body: str, **headers) -> bytes:
    return make_eml(
        subject=subject,
        sender=headers.get("sender", TEACHER),
        message_id=message_id,
        date=headers.get("date", DATE),
        body=body,
        in_reply_to=headers.get("in_reply_to"),
        references=headers.get("references"),
    )


def test_reply_and_forward_collapse_to_one_item(tmp_path):
    original = _sports(
        "<trip-1@example.com>",
        "Permission slip for sports day",
        "Sports Day Participation permission slip is due May 20.\n",
    )
    reply = _sports(
        "<trip-2@example.com>",
        "Re: Permission slip for sports day",
        "Just a reminder to return the sports day permission slip.\n",
        date=LATER,
        in_reply_to="<trip-1@example.com>",
        references="<trip-1@example.com>",
    )
    forwarded = (
        "Please see below.\n\n"
        "---------- Forwarded message ---------\n"
        "From: Ms. Calder <mscalder@example.com>\n\n"
        "Sports Day Participation permission slip is due May 20.\n"
    )
    forward = make_eml(
        subject="Fwd: Fwd: Permission slip for sports day",
        sender="School Office <office@example.com>",
        message_id="<trip-3@example.com>",
        date=LATER,
        body=forwarded,
    )
    database, result = ingest_files(
        tmp_path,
        [("a.eml", original), ("b.eml", reply), ("c.eml", forward)],
    )
    try:
        items = database.list_items()
    finally:
        database.close()
    assert len(items) == 1
    assert items[0]["kid_name"] == "Student A"
    assert items[0]["due_date"] == "2026-05-20"
    assert result.created == 1
    assert result.duplicates >= 1


def test_reply_that_extends_the_due_date_updates_the_item(tmp_path):
    original = make_eml(
        subject="Science center field trip permission slip",
        sender=TEACHER,
        message_id="<ext-1@example.com>",
        date=DATE,
        body="Please return the permission slip for the field trip to the Science Center by May 16.\n",
    )
    reply = make_eml(
        subject="Re: Science center field trip permission slip",
        sender=TEACHER,
        message_id="<ext-2@example.com>",
        date=LATER,
        in_reply_to="<ext-1@example.com>",
        references="<ext-1@example.com>",
        body="The due date has been extended to May 22.\n",
    )
    database, result = ingest_files(tmp_path, [("a.eml", original), ("b.eml", reply)])
    try:
        items = database.list_items()
    finally:
        database.close()
    assert len(items) == 1
    assert items[0]["due_date"] == "2026-05-22"
    assert result.updated == 1


def test_cancellation_reply_marks_the_existing_item(tmp_path):
    original = make_eml(
        subject="Science center field trip permission slip",
        sender=TEACHER,
        message_id="<can-1@example.com>",
        date=DATE,
        body="Please return the permission slip for the field trip to the Science Center by May 16.\n",
    )
    reply = make_eml(
        subject="Re: Science center field trip permission slip",
        sender=TEACHER,
        message_id="<can-2@example.com>",
        date=LATER,
        in_reply_to="<can-1@example.com>",
        references="<can-1@example.com>",
        body="The field trip has been cancelled.\n",
    )
    database, _result = ingest_files(tmp_path, [("a.eml", original), ("b.eml", reply)])
    try:
        items = database.list_items()
    finally:
        database.close()
    assert len(items) == 1
    assert items[0]["cancelled"] == 1


def test_mbox_export_is_read(tmp_path):
    first = make_eml(
        subject="Museum visit form",
        sender="Mr. Okonkwo <mokonkwo@example.com>",
        message_id="<mbox-1@example.com>",
        date=DATE,
        body="The museum visit permission slip is due May 18.\n",
    )
    second = make_eml(
        subject="Re: Museum visit form",
        sender="Mr. Okonkwo <mokonkwo@example.com>",
        message_id="<mbox-2@example.com>",
        date=LATER,
        in_reply_to="<mbox-1@example.com>",
        references="<mbox-1@example.com>",
        body="Reminder to return the museum visit permission slip.\n",
    )
    database, _result = ingest_files(tmp_path, [("school.mbox", to_mbox([first, second]))])
    try:
        items = database.list_items()
    finally:
        database.close()
    assert len(items) == 1
    assert items[0]["kid_name"] == "Student B"
    assert items[0]["due_date"] == "2026-05-18"


def test_scanning_the_same_file_twice_does_not_duplicate(tmp_path):
    message = make_eml(
        subject="Permission slip",
        sender=TEACHER,
        message_id="<once-1@example.com>",
        date=DATE,
        body="Please return the permission slip by May 16.\n",
    )
    database, first = ingest_files(tmp_path, [("once.eml", message)])
    from formdueboard.config import default_kids
    from formdueboard.ingest import ingest_messages
    from formdueboard.mail import load_messages_from_path

    again = ingest_messages(
        database,
        load_messages_from_path(tmp_path / "inbox"),
        default_kids(),
        tz_name="America/New_York",
    )
    try:
        items = database.list_items()
    finally:
        database.close()
    assert first.created == 1
    assert again.duplicates == 1
    assert len(items) == 1
