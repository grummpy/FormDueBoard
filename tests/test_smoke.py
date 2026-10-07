import http.client
import json
import urllib.request

from formdueboard.cli import main
from formdueboard.config import AppConfig, default_kids, load_config
from formdueboard.server import BIND_HOST, App, start_background
from tests.mailutil import make_eml


def _config(tmp_path, gmail_enabled=False) -> AppConfig:
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    path = tmp_path / "config.yaml"
    path.write_text(
        "\n".join(
            [
                "timezone: America/New_York",
                "due_soon_days: 7",
                "confidence_threshold: 0.55",
                f"inbox_dir: {inbox}",
                f"db_path: {tmp_path / 'board.sqlite'}",
                "gmail:",
                f"  enabled: {'true' if gmail_enabled else 'false'}",
                "  credentials_file: secrets/gmail_client.json",
                "kids:",
                "  - name: Student A",
                "    nicknames: [Student A, Kid A]",
                "    grade: '4'",
                "    teachers: [Ms. Calder, mscalder@example.com]",
                "  - name: Student B",
                "    nicknames: [Student B, Kid B]",
                "    grade: '2'",
                "    teachers: [Mr. Okonkwo, mokonkwo@example.com]",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.host == "127.0.0.1"
    assert config.gmail.enabled is gmail_enabled
    return config


def test_custom_config_accepts_a_cli_string_path(tmp_path):
    config = _config(tmp_path)
    assert load_config(str(config.config_path)).config_path == config.config_path
    assert main(["--config", str(config.config_path), "export-ics"]) == 0


def test_server_on_loopback_returns_200(tmp_path):
    config = _config(tmp_path)
    app = App(config)
    httpd, url = start_background(app, 0)
    try:
        assert httpd.server_address[0] == BIND_HOST == "127.0.0.1"
        for path in (
            "/",
            "/styles.css",
            "/app.js",
            "/favicon.ico",
            "/icon.png",
            "/api/health",
            "/api/board",
        ):
            with urllib.request.urlopen(url + path) as response:
                assert response.status == 200
                body = response.read()
            assert body
        with urllib.request.urlopen(url + "/") as response:
            page = response.read().decode()
        assert "Form" in page and "Due" in page and "Board" in page
        with urllib.request.urlopen(url + "/api/board") as response:
            board = json.loads(response.read().decode())
        assert [kid["name"] for kid in board["kids"]] == ["Student A", "Student B"]
        assert board["review"] == []
    finally:
        httpd.shutdown()
        app.close()


def test_scan_upload_assign_print_and_gmail_refusal(tmp_path):
    config = _config(tmp_path)
    message = make_eml(
        subject="Permission slip",
        sender="Activities <activities@example.com>",
        message_id="<smoke-1@example.com>",
        body="A permission slip is due May 21. Please send it back.\n",
    )
    app = App(config)
    httpd, url = start_background(app, 0)
    try:
        boundary = "----formdueboard"
        payload = (
            (
                f"--{boundary}\r\n"
                'Content-Disposition: form-data; name="file"; filename="note.eml"\r\n'
                "Content-Type: message/rfc822\r\n\r\n"
            ).encode()
            + message
            + f"\r\n--{boundary}--\r\n".encode()
        )
        request = urllib.request.Request(
            url + "/api/upload",
            data=payload,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            summary = json.loads(response.read().decode())
        assert summary["created"] == 1
        with urllib.request.urlopen(url + "/api/board") as response:
            board = json.loads(response.read().decode())
        assert len(board["review"]) == 1
        item_id = board["review"][0]["id"]
        assert board["review"][0]["kid_name"] is None

        assign = urllib.request.Request(
            f"{url}/api/items/{item_id}/assign",
            data=json.dumps({"kid_name": "Student B"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(assign) as response:
            assert response.status == 200
        with urllib.request.urlopen(url + "/api/board") as response:
            board = json.loads(response.read().decode())
        assert board["review"] == []
        assert any(item["id"] == item_id for item in board["kids"][1]["items"])

        with urllib.request.urlopen(url + "/print") as response:
            page = response.read().decode()
            assert response.status == 200
        assert "Student B" in page
        assert "checklist" in page.lower()

        gmail = urllib.request.Request(url + "/api/gmail/fetch", data=b"{}", method="POST")
        try:
            urllib.request.urlopen(gmail)
            raise AssertionError("gmail fetch should refuse while disabled")
        except urllib.error.HTTPError as exc:
            assert exc.code == 403
            detail = json.loads(exc.read().decode())
            assert "off" in detail["error"].lower()
    finally:
        httpd.shutdown()
        app.close()


def test_post_then_get_on_one_connection(tmp_path):
    config = _config(tmp_path)
    app = App(config)
    httpd, url = start_background(app, 0)
    port = httpd.server_address[1]
    try:
        connection = http.client.HTTPConnection(BIND_HOST, port)
        connection.request(
            "POST",
            "/api/samples",
            body=b"{}",
            headers={"Content-Type": "application/json", "Content-Length": "2"},
        )
        posted = connection.getresponse()
        posted.read()
        assert posted.status == 200
        connection.request("GET", "/api/board")
        fetched = connection.getresponse()
        board = json.loads(fetched.read().decode())
        assert fetched.status == 200
        titles = [item["title"] for kid in board["kids"] for item in kid["items"]]
        assert "Field Trip to Science Center" in titles
        connection.close()
    finally:
        httpd.shutdown()
        app.close()


def test_default_kids_are_the_synthetic_pair():
    assert [kid.name for kid in default_kids()] == ["Student A", "Student B"]
