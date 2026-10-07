from datetime import date

from formdueboard.config import default_kids
from formdueboard.db import Database
from formdueboard.ingest import ingest_messages
from formdueboard.mail import load_messages_from_path
from formdueboard.samples import write_samples
from tests.test_privacy import scan_tree


def test_samples_are_synthetic_and_file_under_both_kids(tmp_path):
    inbox = tmp_path / "inbox"
    write_samples(inbox, today=date(2026, 5, 13))
    assert scan_tree(inbox) == []
    database = Database(tmp_path / "board.sqlite")
    try:
        result = ingest_messages(
            database,
            load_messages_from_path(inbox),
            default_kids(),
            tz_name="America/New_York",
        )
        items = database.list_items()
    finally:
        database.close()
    titles = {item["title"] for item in items if item["kid_name"]}
    assert "Field Trip to Science Center" in titles
    assert "Sports Day Participation" in titles
    assert "Museum Visit" in titles
    assert "After-School Club" in titles
    assert any(item["cancelled"] for item in items)
    assert any(item["needs_review"] for item in items)
    assert result.created >= 4
