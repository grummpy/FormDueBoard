from __future__ import annotations

from pathlib import Path

import pytest

from formdueboard.config import default_kids
from formdueboard.db import Database
from formdueboard.ingest import ingest_messages
from formdueboard.mail import load_messages_from_path

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def kids():
    return default_kids()


def ingest_files(tmp_path: Path, files: list[tuple[str, bytes]], kids=None):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    for name, data in files:
        (inbox / name).write_bytes(data)
    database = Database(tmp_path / "board.sqlite")
    messages = load_messages_from_path(inbox)
    result = ingest_messages(
        database,
        messages,
        kids if kids is not None else default_kids(),
        tz_name="America/New_York",
    )
    return database, result
