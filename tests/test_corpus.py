"""One test per synthetic email shape. Every address is @example.com."""

from __future__ import annotations

from tests.conftest import ingest_files
from tests.mailutil import make_eml, simple_docx, simple_pdf

TEACHER_A = "Ms. Calder <mscalder@example.com>"
TEACHER_B = "Mr. Okonkwo <mokonkwo@example.com>"
OFFICE = "School Office <office@example.com>"
DATE = "Wed, 13 May 2026 09:00:00 -0400"


def _one(tmp_path, **kwargs):
    database, _result = ingest_files(tmp_path, [("note.eml", make_eml(**kwargs))])
    try:
        return database.list_items()
    finally:
        database.close()


def test_absolute_due_and_event_from_teacher(tmp_path):
    items = _one(
        tmp_path,
        subject="Science center field trip permission slip",
        sender=TEACHER_A,
        message_id="<abs-1@example.com>",
        date=DATE,
        body=("The field trip to the Science Center is on May 20. Please return the permission slip by May 16.\n"),
    )
    assert len(items) == 1
    item = items[0]
    assert item["kid_name"] == "Student A"
    assert item["needs_review"] == 0
    assert item["title"] == "Field Trip to Science Center"
    assert item["form_type"] == "permission_slip"
    assert item["due_date"] == "2026-05-16"
    assert item["event_date"] == "2026-05-20"
    assert item["confidence"] >= 0.55


def test_by_friday_relative_to_the_email_date(tmp_path):
    items = _one(
        tmp_path,
        subject="Permission slip reminder",
        sender=TEACHER_A,
        message_id="<fri-1@example.com>",
        date=DATE,
        body="Please sign and return the permission slip by Friday.\n",
    )
    assert items[0]["due_date"] == "2026-05-15"
    assert items[0]["kid_name"] == "Student A"
    assert items[0]["needs_review"] == 0


def test_tomorrow(tmp_path):
    items = _one(
        tmp_path,
        subject="Museum visit form",
        sender=TEACHER_B,
        message_id="<tom-1@example.com>",
        date=DATE,
        body="The museum visit permission slip is due tomorrow.\n",
    )
    assert items[0]["due_date"] == "2026-05-14"
    assert items[0]["kid_name"] == "Student B"
    assert items[0]["title"] == "Museum Visit"


def test_both_kids_in_one_email(tmp_path):
    items = _one(
        tmp_path,
        subject="Picture day forms",
        sender=OFFICE,
        message_id="<both-1@example.com>",
        date=DATE,
        body=("Student A and Student B both need the picture day form returned by May 18. The fee is $15.\n"),
    )
    assert len(items) == 2
    assert {item["kid_name"] for item in items} == {"Student A", "Student B"}
    assert all(item["needs_review"] == 0 for item in items)
    assert all(item["due_date"] == "2026-05-18" for item in items)
    assert all(item["form_type"] == "picture_day" for item in items)
    assert all(item["fee_amount"] == "15" for item in items)


def test_teacher_email_that_names_the_other_kid(tmp_path):
    items = _one(
        tmp_path,
        subject="Note for the other class",
        sender=TEACHER_A,
        message_id="<other-1@example.com>",
        date=DATE,
        body="Please give this to Student B. The museum visit permission slip is due May 18.\n",
    )
    assert len(items) == 1
    assert items[0]["kid_name"] == "Student B"


def test_ambiguous_or_goes_to_review_unassigned(tmp_path):
    items = _one(
        tmp_path,
        subject="Permission slip",
        sender=OFFICE,
        message_id="<or-1@example.com>",
        date=DATE,
        body="Either Student A or Student B should return the permission slip by May 16.\n",
    )
    assert len(items) == 1
    assert items[0]["kid_name"] is None
    assert items[0]["needs_review"] == 1
    assert "not assigned" in items[0]["review_reason"].lower() or "more than one" in items[0]["review_reason"]


def test_unknown_sender_is_not_silently_assigned(tmp_path):
    items = _one(
        tmp_path,
        subject="Form due",
        sender="Activities <activities@example.com>",
        message_id="<unk-1@example.com>",
        date=DATE,
        body="A permission slip is due May 21. Please send it back.\n",
    )
    assert items[0]["kid_name"] is None
    assert items[0]["needs_review"] == 1
    assert items[0]["due_date"] == "2026-05-21"


def test_pdf_attachment_supplies_the_form_and_date(tmp_path):
    pdf = simple_pdf(["Sports Day Participation permission slip.", "Due: May 20."])
    database, _result = ingest_files(
        tmp_path,
        [
            (
                "note.eml",
                make_eml(
                    subject="See attached",
                    sender=TEACHER_A,
                    message_id="<pdf-1@example.com>",
                    date=DATE,
                    body="See the attached permission slip.\n",
                    attachments=[("sports-day.pdf", pdf, "application", "pdf")],
                ),
            )
        ],
    )
    try:
        items = database.list_items()
        names = [row["filename"] for row in database.attachments_for(items[0]["primary_message_id"])]
    finally:
        database.close()
    assert len(items) == 1
    assert items[0]["kid_name"] == "Student A"
    assert items[0]["title"] == "Sports Day Participation"
    assert items[0]["due_date"] == "2026-05-20"
    assert items[0]["needs_review"] == 0
    assert names == ["sports-day.pdf"]


def test_docx_attachment(tmp_path):
    docx = simple_docx(["After-School Club permission slip. Please return by May 22."])
    items = _one(
        tmp_path,
        subject="Attached form",
        sender=TEACHER_B,
        message_id="<docx-1@example.com>",
        date=DATE,
        body="Attached is the form to sign and return.\n",
        attachments=[
            (
                "club.docx",
                docx,
                "application",
                "vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        ],
    )
    assert items[0]["kid_name"] == "Student B"
    assert items[0]["title"] == "After-School Club"
    assert items[0]["due_date"] == "2026-05-22"
    assert items[0]["needs_review"] == 0


def test_cancelled_trip_is_not_an_open_task(tmp_path):
    items = _one(
        tmp_path,
        subject="Science center trip cancelled",
        sender=TEACHER_A,
        message_id="<cancel-1@example.com>",
        date="Thu, 14 May 2026 09:00:00 -0400",
        body="The field trip to the Science Center has been cancelled. Please do not return a permission slip.\n",
    )
    assert len(items) == 1
    assert items[0]["cancelled"] == 1
    assert items[0]["kid_name"] == "Student A"
    assert items[0]["needs_review"] == 0
    assert items[0]["title"] == "Field Trip to Science Center"


def test_numeric_date(tmp_path):
    items = _one(
        tmp_path,
        subject="Permission slip",
        sender=TEACHER_A,
        message_id="<num-1@example.com>",
        date=DATE,
        body="Permission slip due 5/16/2026 for the field trip to the Science Center.\n",
    )
    assert items[0]["due_date"] == "2026-05-16"
    assert items[0]["title"] == "Field Trip to Science Center"


def test_html_only_message(tmp_path):
    items = _one(
        tmp_path,
        subject="Permission slip",
        sender=TEACHER_A,
        message_id="<html-1@example.com>",
        date=DATE,
        html="<p>Please return the <strong>permission slip</strong> by May 16.</p>",
    )
    assert items[0]["due_date"] == "2026-05-16"
    assert items[0]["kid_name"] == "Student A"


def test_gradelink_notice_uses_grade(tmp_path):
    items = _one(
        tmp_path,
        subject="[GradeLink] Permission slip",
        sender="GradeLink Notices <notices@example.com>",
        message_id="<grade-1@example.com>",
        date=DATE,
        body=(
            "GradeLink notice for 4th grade. Permission slip for the field trip to the Science Center is due May 16.\n"
        ),
    )
    assert items[0]["kid_name"] == "Student A"
    assert items[0]["due_date"] == "2026-05-16"
    assert items[0]["needs_review"] == 0


def test_smartsend_notice_with_relative_date(tmp_path):
    items = _one(
        tmp_path,
        subject="SmartSend: Picture day",
        sender="SmartSend <smartsend@example.com>",
        message_id="<smart-1@example.com>",
        date=DATE,
        body="SmartSend notice: Student B picture day form is due by Friday.\n",
    )
    assert items[0]["kid_name"] == "Student B"
    assert items[0]["form_type"] == "picture_day"
    assert items[0]["due_date"] == "2026-05-15"


def test_by_next_monday(tmp_path):
    items = _one(
        tmp_path,
        subject="Permission slip",
        sender=TEACHER_B,
        message_id="<mon-1@example.com>",
        date=DATE,
        body="Please return the permission slip by next Monday.\n",
    )
    assert items[0]["due_date"] == "2026-05-18"
    assert items[0]["kid_name"] == "Student B"


def test_fee_amount(tmp_path):
    items = _one(
        tmp_path,
        subject="Yearbook fee for Student A",
        sender=OFFICE,
        message_id="<fee-1@example.com>",
        date=DATE,
        body="Student A's yearbook fee of $25.00 is due by May 22.\n",
    )
    assert items[0]["kid_name"] == "Student A"
    assert items[0]["form_type"] == "fee"
    assert items[0]["fee_amount"] == "25.00"
    assert items[0]["due_date"] == "2026-05-22"
    assert items[0]["title"] == "Yearbook Fee"


def test_nickname(tmp_path):
    items = _one(
        tmp_path,
        subject="Permission slip",
        sender=OFFICE,
        message_id="<nick-1@example.com>",
        date=DATE,
        body="Kid A needs the permission slip returned by May 16.\n",
    )
    assert items[0]["kid_name"] == "Student A"


def test_grade_overrides_the_from_teacher(tmp_path):
    items = _one(
        tmp_path,
        subject="Museum visit",
        sender=TEACHER_A,
        message_id="<grov-1@example.com>",
        date=DATE,
        body="The 2nd grade museum visit permission slip is due May 18.\n",
    )
    assert items[0]["kid_name"] == "Student B"


def test_chatter_with_no_form_creates_nothing(tmp_path):
    items = _one(
        tmp_path,
        subject="Hello",
        sender=TEACHER_A,
        message_id="<hi-1@example.com>",
        date=DATE,
        body="Hope you have a wonderful week. No homework tonight.\n",
    )
    assert items == []


def test_form_without_a_date_or_kid_is_review_only(tmp_path):
    items = _one(
        tmp_path,
        subject="A form",
        sender="Someone <someone@example.com>",
        message_id="<low-1@example.com>",
        date=DATE,
        body="There is a form in the folder.\n",
    )
    assert len(items) == 1
    assert items[0]["needs_review"] == 1
    assert items[0]["kid_name"] is None


def test_known_kid_without_a_due_date_is_still_not_filed(tmp_path):
    items = _one(
        tmp_path,
        subject="Permission slip",
        sender=TEACHER_A,
        message_id="<nodue-1@example.com>",
        date=DATE,
        body="Please sign the permission slip when you can.\n",
    )
    assert items[0]["kid_name"] is None
    assert items[0]["suggested_kid"] == "Student A"
    assert items[0]["needs_review"] == 1
    assert "due date" in items[0]["review_reason"].lower()


def test_forward_chain_message_extracts_the_original_teacher(tmp_path):
    body = (
        "Please see below.\n\n"
        "---------- Forwarded message ---------\n"
        "From: Ms. Calder <mscalder@example.com>\n"
        "Subject: Fwd: Permission slip for sports day\n\n"
        "---------- Forwarded message ---------\n"
        "From: Ms. Calder <mscalder@example.com>\n"
        "Subject: Permission slip for sports day\n\n"
        "Sports Day Participation permission slip is due May 20.\n"
    )
    items = _one(
        tmp_path,
        subject="Fwd: Fwd: Permission slip for sports day",
        sender=OFFICE,
        message_id="<fwd-1@example.com>",
        date=DATE,
        body=body,
    )
    assert len(items) == 1
    assert items[0]["kid_name"] == "Student A"
    assert items[0]["title"] == "Sports Day Participation"
    assert items[0]["due_date"] == "2026-05-20"
    assert items[0]["needs_review"] == 0


def test_conflicting_due_dates_are_not_filed(tmp_path):
    items = _one(
        tmp_path,
        subject="Permission slip",
        sender=TEACHER_A,
        message_id="<conflict-1@example.com>",
        date=DATE,
        body="The permission slip is due May 16 or due May 18.\n",
    )
    assert items[0]["needs_review"] == 1
    assert items[0]["kid_name"] is None
    assert items[0]["suggested_kid"] == "Student A"


def test_event_date_alone_is_not_treated_as_the_deadline(tmp_path):
    items = _one(
        tmp_path,
        subject="Field trip",
        sender=TEACHER_A,
        message_id="<event-1@example.com>",
        date=DATE,
        body="The field trip to the Science Center is on May 20.\n",
    )
    assert items[0]["due_date"] is None
    assert items[0]["event_date"] == "2026-05-20"
    assert items[0]["needs_review"] == 1
    assert items[0]["kid_name"] is None
