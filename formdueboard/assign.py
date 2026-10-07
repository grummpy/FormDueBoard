"""Decide which kid a message is about.

A configured teacher is the default for that teacher's student. A name, nickname,
or grade in the message wins over the sender, which is how a note from Student A's
teacher about Student B stays with Student B. Ambiguous messages are not assigned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from formdueboard.config import KidConfig

GRADE_WORDS = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
    11: "eleventh",
    12: "twelfth",
}
ORDINAL_SUFFIX = {1: "st", 2: "nd", 3: "rd"}
CONTRAST_RE = re.compile(
    r"\b(or|either|instead of|rather than|except|but not)\b",
    re.IGNORECASE,
)
FORWARD_FROM_RE = re.compile(r"(?im)^from:\s*(.+)$")


@dataclass
class Assignment:
    kid_name: str | None
    certain: bool
    reason: str


def assign_kids(text: str, sender: str, kids: list[KidConfig]) -> list[Assignment]:
    named = _named_kids(text, kids)
    if len(named) == 1:
        return [Assignment(named[0].name, True, "named in the message")]
    if len(named) > 1:
        if _contrast_between(text, named):
            return [
                Assignment(
                    None,
                    False,
                    "This email names more than one kid, so it was not assigned.",
                )
            ]
        return [Assignment(kid.name, True, "named along with the other kid") for kid in named]

    graded = _graded_kids(text, kids)
    if len(graded) == 1:
        return [Assignment(graded[0].name, True, "the grade in the message matches")]
    if len(graded) > 1:
        return [Assignment(kid.name, True, "the grade in the message matches") for kid in graded]

    teachers = _teacher_kids(sender, kids)
    if len(teachers) == 1:
        return [Assignment(teachers[0].name, True, "the sender is that student's teacher")]
    if len(teachers) > 1:
        return [
            Assignment(
                None,
                False,
                "The sender matches more than one configured teacher.",
            )
        ]

    forwarded = _forwarded_sender(text)
    if forwarded:
        forwarded_kids = _teacher_kids(forwarded, kids)
        if len(forwarded_kids) == 1:
            return [
                Assignment(
                    forwarded_kids[0].name,
                    True,
                    "a forwarded message is from that student's teacher",
                )
            ]

    return [
        Assignment(
            None,
            False,
            "No kid is named, and the sender is not a configured teacher.",
        )
    ]


def _named_kids(text: str, kids: list[KidConfig]) -> list[KidConfig]:
    found: list[KidConfig] = []
    for kid in kids:
        names = [kid.name, *kid.nicknames]
        ordered = sorted({name.strip() for name in names if len(name.strip()) >= 2}, key=len, reverse=True)
        for name in ordered:
            if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.IGNORECASE):
                found.append(kid)
                break
    return found


def _contrast_between(text: str, kids: list[KidConfig]) -> bool:
    spans: list[tuple[int, int]] = []
    for kid in kids:
        match = re.search(rf"(?<!\w){re.escape(kid.name)}(?!\w)", text, re.IGNORECASE)
        if match:
            spans.append((match.start(), match.end()))
    if len(spans) < 2:
        return bool(CONTRAST_RE.search(text))
    start = min(span[0] for span in spans)
    end = max(span[1] for span in spans)
    return CONTRAST_RE.search(text[start:end]) is not None


def _graded_kids(text: str, kids: list[KidConfig]) -> list[KidConfig]:
    return [kid for kid in kids if kid.grade and grade_mentioned(text, kid.grade)]


def grade_mentioned(text: str, grade: str) -> bool:
    token = grade.strip().lower()
    if token in {"k", "kindergarten"}:
        return re.search(r"\b(kindergarten|grade\s*k)\b", text, re.IGNORECASE) is not None
    if not token.isdigit():
        return False
    number = int(token)
    suffix = "th" if number % 100 in {11, 12, 13} else ORDINAL_SUFFIX.get(number % 10, "th")
    word = GRADE_WORDS.get(number)
    patterns = [
        rf"\b{number}{suffix}\s+grades?\b",
        rf"\bgrades?\s*{number}(?!\d)\b",
    ]
    if word:
        patterns.append(rf"\b{word}\s+grades?\b")
    return any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns)


def _teacher_kids(sender: str, kids: list[KidConfig]) -> list[KidConfig]:
    haystack = sender.casefold()
    matched: list[KidConfig] = []
    for kid in kids:
        for teacher in kid.teachers:
            token = teacher.strip()
            if token and token.casefold() in haystack:
                matched.append(kid)
                break
    return matched


def _forwarded_sender(text: str) -> str:
    lines = FORWARD_FROM_RE.findall(text)
    return "\n".join(lines)
