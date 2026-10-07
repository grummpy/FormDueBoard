import json
import urllib.request

from formdueboard.board import build_board
from formdueboard.config import AppConfig, GmailConfig, default_kids
from formdueboard.db import Database
from formdueboard.server import start_background
from tests.conftest import ingest_files
from tests.mailutil import make_eml


def _seed(tmp_path):
    message = make_eml(
        subject="Permission slip",
        sender="Ms. Calder <mscalder@example.com>",
        message_id="<status-1@example.com>",
        body="Please return the permission slip by May 16.\n",
    )
    database, _result = ingest_files(tmp_path, [("status.eml", message)])
    return database


def test_status_survives_reopening_the_database(tmp_path):
    database = _seed(tmp_path)
    item_id = database.list_items()[0]["id"]
    database.set_status(item_id, "signed")
    database.close()

    again = Database(tmp_path / "board.sqlite")
    try:
        item = again.get_item(item_id)
    finally:
        again.close()
    assert item["status"] == "signed"


def test_mark_done_over_http_persists(tmp_path):
    database = _seed(tmp_path)
    item_id = database.list_items()[0]["id"]
    config = AppConfig(
        inbox_dir=tmp_path / "inbox",
        db_path=tmp_path / "board.sqlite",
        kids=default_kids(),
        gmail=GmailConfig(enabled=False),
    )
    app_db = database
    from formdueboard.server import App

    app = App.__new__(App)
    app.config = config
    app.db = app_db
    httpd, url = start_background(app, 0)
    try:
        request = urllib.request.Request(
            f"{url}/api/items/{item_id}/done",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            payload = json.loads(response.read().decode())
            assert response.status == 200
        assert payload["status"] == "returned"
        board = build_board(app.db, config, today=__import__("datetime").date(2026, 5, 13))
        filed = board["kids"][0]["items"][0]
        assert filed["status"] == "returned"
    finally:
        httpd.shutdown()
        app.db.close()

    reopened = Database(tmp_path / "board.sqlite")
    try:
        assert reopened.get_item(item_id)["status"] == "returned"
    finally:
        reopened.close()
