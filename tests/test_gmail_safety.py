import ast
from pathlib import Path

import pytest

from formdueboard.config import AppConfig, GmailConfig
from formdueboard.gmail_fetch import (
    READONLY_SCOPE,
    SCOPES,
    GmailConfigError,
    GmailDisabled,
    fetch_to_inbox,
)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "formdueboard" / "gmail_fetch.py").read_text(encoding="utf-8")


def test_scope_is_readonly_only():
    assert SCOPES == [READONLY_SCOPE]
    assert READONLY_SCOPE == "https://www.googleapis.com/auth/gmail.readonly"
    assert "gmail.modify" not in SOURCE
    assert "gmail.send" not in SOURCE


def test_source_never_calls_mutating_gmail_methods():
    tree = ast.parse(SOURCE)
    forbidden = {"send", "trash", "delete", "modify", "batchmodify", "batchdelete", "import_"}
    found = sorted(
        {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr.lower() in forbidden}
    )
    assert found == []
    assert "messages().list" in SOURCE.replace(" ", "").replace("\n", "") or ".list(" in SOURCE
    assert 'format="raw"' in SOURCE


def test_fetch_refuses_when_disabled(tmp_path):
    config = AppConfig(
        inbox_dir=tmp_path / "inbox",
        db_path=tmp_path / "board.sqlite",
        gmail=GmailConfig(enabled=False, credentials_file=str(tmp_path / "missing.json")),
    )
    with pytest.raises(GmailDisabled):
        fetch_to_inbox(config)


def test_fetch_refuses_without_a_client_file_even_if_enabled(tmp_path):
    config = AppConfig(
        inbox_dir=tmp_path / "inbox",
        db_path=tmp_path / "board.sqlite",
        gmail=GmailConfig(enabled=True, credentials_file=str(tmp_path / "no-such-client.json")),
    )
    with pytest.raises(GmailConfigError) as caught:
        fetch_to_inbox(config)
    assert "OAuth" in str(caught.value)
