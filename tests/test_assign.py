from formdueboard.assign import assign_kids
from formdueboard.config import default_kids

KIDS = default_kids()


def names(text: str, sender: str = "School Office <office@example.com>"):
    return [(item.kid_name, item.certain) for item in assign_kids(text, sender, KIDS)]


def test_teacher_defaults_to_that_student():
    assert names("Please return the permission slip by Friday.", "Ms. Calder <mscalder@example.com>") == [
        ("Student A", True)
    ]


def test_named_kid_overrides_the_teacher():
    found = names(
        "Please give this to Student B. The museum visit permission slip is due May 18.",
        "Ms. Calder <mscalder@example.com>",
    )
    assert found == [("Student B", True)]


def test_both_kids_named_together_are_both_assigned():
    found = names("Student A and Student B both need the picture day form returned by May 18.")
    assert found == [("Student A", True), ("Student B", True)]


def test_either_kid_is_not_assigned():
    found = names("Either Student A or Student B should return the permission slip by May 16.")
    assert found == [(None, False)]


def test_grade_overrides_teacher():
    found = names(
        "The 2nd grade museum visit permission slip is due May 18.",
        "Ms. Calder <mscalder@example.com>",
    )
    assert found == [("Student B", True)]


def test_nickname_assigns_the_kid():
    assert names("Kid B needs the permission slip returned by May 18.") == [("Student B", True)]


def test_unknown_sender_is_not_assigned():
    found = names("A permission slip is due May 21.", "Activities <activities@example.com>")
    assert found == [(None, False)]


def test_forwarded_teacher_is_used_when_the_outer_sender_is_not():
    body = (
        "---------- Forwarded message ---------\n"
        "From: Ms. Calder <mscalder@example.com>\n"
        "\n"
        "Sports Day Participation permission slip is due May 20.\n"
    )
    assert names(body, "School Office <office@example.com>") == [("Student A", True)]
