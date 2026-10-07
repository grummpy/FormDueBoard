"""Turn one email into zero or more form items, each with a confidence score."""

from __future__ import annotations

import re

from formdueboard.assign import assign_kids
from formdueboard.config import KidConfig
from formdueboard.dates import decide_dates, is_due_change
from formdueboard.model import ExtractedItem, ParsedMessage

FORM_PATTERNS: list[tuple[str, str]] = [
    ("picture_day", r"picture day"),
    ("sports_day", r"sports day"),
    ("after_school", r"after[- ]school"),
    ("field_trip", r"field trips?"),
    ("permission_slip", r"permission slips?"),
    ("waiver", r"\bwaivers?\b"),
    ("fee", r"\b(?:fees?|tuition|payment due|yearbook fee)\b"),
    ("sign_return", r"sign(?:ed)? and return"),
    ("form", r"\bforms?\b"),
]
FORM_LABELS = {
    "picture_day": "Picture day",
    "sports_day": "Sports day",
    "after_school": "After-school",
    "field_trip": "Field trip",
    "permission_slip": "Permission slip",
    "waiver": "Waiver",
    "fee": "Fee",
    "sign_return": "Sign and return",
    "form": "Form",
}
TITLE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"field trip to (?:the )?([A-Za-z0-9][^.\n]{1,60})", re.I), "trip"),
    (re.compile(r"\bscience center\b", re.I), "Field Trip to Science Center"),
    (re.compile(r"museum visit", re.I), "Museum Visit"),
    (re.compile(r"sports day(?: participation)?", re.I), "Sports Day Participation"),
    (re.compile(r"after[- ]school club", re.I), "After-School Club"),
    (re.compile(r"picture day", re.I), "Picture Day"),
    (re.compile(r"yearbook fee", re.I), "Yearbook Fee"),
]
FEE_RE = re.compile(
    r"\$\s*(\d{1,4}(?:,\d{3})*(?:\.\d{2})?)|\b(\d{1,4}(?:\.\d{2})?)\s*dollars\b",
    re.IGNORECASE,
)
CANCEL_RE = re.compile(
    r"\b(cancell?ed|cancellation|called off|will not take place|no longer taking place)\b",
    re.IGNORECASE,
)
NOT_CANCEL_RE = re.compile(r"\bnot cancell?ed\b", re.IGNORECASE)
SUBJECT_PREFIX_RE = re.compile(
    r"^\s*(?:(?:re|fw|fwd)\s*:\s*|\[[^\]]+\]\s*|smartsend\s*:\s*|gradelink\s*:\s*)",
    re.IGNORECASE,
)


def extract_from_message(
    message: ParsedMessage,
    kids: list[KidConfig],
    threshold: float = 0.55,
    tz_name: str = "America/New_York",
) -> list[ExtractedItem]:
    text = message.combined_text()
    form_type = detect_form_type(text)
    if form_type is None:
        return []

    anchor = message.anchor_date(tz_name)
    decision = decide_dates(text, anchor)
    cancelled = _cancelled(text)
    fee = _fee(text)
    title = extract_title(text, message.subject, form_type)
    label = _label(text, form_type)
    stored_type = _stored_type(text, form_type)
    snippet = make_snippet(message.body_text, message.attachments)
    normalized = normalize_subject(message.subject)
    attachment_names = [att.filename for att in message.attachments]
    attachment_supported = any(
        att.extracted_text and detect_form_type(att.extracted_text) for att in message.attachments
    )
    assignments = assign_kids(text, message.sender, kids)
    items: list[ExtractedItem] = []
    for assignment in assignments:
        score = _score(stored_type, decision.due_date, assignment.certain, attachment_supported)
        needs_review, reason = _review(
            certain=assignment.certain,
            assignment_reason=assignment.reason,
            due_date=decision.due_date,
            conflict=decision.conflict,
            score=score,
            threshold=threshold,
            cancelled=cancelled,
            form_type=stored_type,
        )
        filed = None if needs_review else assignment.kid_name
        suggested = assignment.kid_name if needs_review and assignment.certain else None
        items.append(
            ExtractedItem(
                title=title,
                form_type=stored_type,
                form_label=label,
                due_date=None if decision.conflict and not decision.due_changed else decision.due_date,
                event_date=decision.event_date,
                fee_amount=fee,
                kid_name=filed,
                suggested_kid=suggested,
                confidence=score,
                needs_review=needs_review,
                review_reason=reason,
                cancelled=cancelled,
                snippet=snippet,
                due_changed=decision.due_changed or is_due_change(text),
                normalized_subject=normalized,
                attachment_names=attachment_names,
            )
        )
    return items


def detect_form_type(text: str) -> str | None:
    for name, pattern in FORM_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return None


def extract_title(text: str, subject: str, form_type: str) -> str:
    for pattern, title in TITLE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if title == "trip":
            destination = _clean_destination(match.group(1))
            if destination:
                return f"Field Trip to {destination}"
            continue
        return title
    cleaned = clean_subject(subject)
    if cleaned and cleaned.casefold() not in {"see attached", "attached form", "form due", "hello"}:
        return cleaned
    return FORM_LABELS.get(form_type, "Form")


def clean_subject(subject: str) -> str:
    text = subject or ""
    previous = None
    while text != previous:
        previous = text
        text = SUBJECT_PREFIX_RE.sub("", text).strip()
    return re.sub(r"\s+", " ", text).strip()


def normalize_subject(subject: str) -> str:
    return clean_subject(subject).casefold()


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()


def make_snippet(body: str, attachments) -> str:
    text = (body or "").strip()
    attachment_text = "\n".join(att.extracted_text for att in attachments if getattr(att, "extracted_text", "")).strip()
    if len(re.sub(r"\s+", " ", text)) < 40 and attachment_text:
        text = attachment_text
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 240:
        return text[:237].rstrip() + "..."
    return text


def _stored_type(text: str, form_type: str) -> str:
    """Permission slips keep that label even when the trip name is more specific."""
    if form_type in {"sports_day", "field_trip", "after_school"} and re.search(
        r"permission slips?", text, re.IGNORECASE
    ):
        return "permission_slip"
    if form_type == "sign_return" and re.search(r"permission slips?", text, re.IGNORECASE):
        return "permission_slip"
    return form_type


def _label(text: str, form_type: str) -> str:
    return FORM_LABELS[_stored_type(text, form_type)]


def _clean_destination(raw: str) -> str:
    destination = re.split(
        r"\b(is|on|permission|please|due|for|and|has|been|was|cancelled|canceled)\b",
        raw,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    destination = destination.strip(" .,-")
    words = []
    for word in destination.split():
        if word.isupper() or word.islower():
            words.append(word[:1].upper() + word[1:].lower() if word else word)
        else:
            words.append(word)
    return " ".join(words)


def _fee(text: str) -> str | None:
    match = FEE_RE.search(text)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    return raw.replace(",", "")


def _cancelled(text: str) -> bool:
    if NOT_CANCEL_RE.search(text):
        return False
    return CANCEL_RE.search(text) is not None


def _score(form_type: str, due_date, certain: bool, attachment_supported: bool) -> float:
    score = 0.22 if form_type == "form" else 0.36
    if due_date is not None:
        score += 0.32
    if certain:
        score += 0.27
    if attachment_supported:
        score += 0.05
    return round(min(score, 0.99), 2)


def _review(
    *,
    certain: bool,
    assignment_reason: str,
    due_date,
    conflict: bool,
    score: float,
    threshold: float,
    cancelled: bool,
    form_type: str,
) -> tuple[bool, str | None]:
    if not certain:
        return True, assignment_reason
    if conflict:
        return True, "The message mentions more than one due date."
    if cancelled and form_type != "form":
        return False, None
    if due_date is None:
        return True, "No due date was found."
    if score < threshold:
        return True, "Not confident enough to file automatically."
    return False, None
