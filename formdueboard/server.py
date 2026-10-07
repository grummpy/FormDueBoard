"""Local-only web board. It binds to 127.0.0.1 and does not talk to a cloud backend."""

from __future__ import annotations

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from formdueboard.board import build_board
from formdueboard.checklist import render_checklist
from formdueboard.config import AppConfig
from formdueboard.db import STATUSES, Database
from formdueboard.gmail_fetch import GmailConfigError, GmailDisabled, fetch_to_inbox
from formdueboard.ics_export import build_ics
from formdueboard.ingest import fingerprint, ingest_messages
from formdueboard.mail import load_messages_from_path
from formdueboard.paths import bundle_root
from formdueboard.samples import write_samples

BIND_HOST = "127.0.0.1"
MAX_JSON = 1_000_000
MAX_UPLOAD = 25_000_000


class App:
    def __init__(self, config: AppConfig):
        self.config = config
        self.db = Database(config.db_path)

    def close(self) -> None:
        self.db.close()

    def scan(self) -> dict:
        messages = load_messages_from_path(self.config.inbox_dir)
        result = ingest_messages(
            self.db,
            messages,
            self.config.kids,
            threshold=self.config.confidence_threshold,
            tz_name=self.config.timezone,
        )
        return {
            "messages": result.messages,
            "created": result.created,
            "updated": result.updated,
            "duplicates": result.duplicates,
            "skipped": result.skipped,
        }

    def load_samples(self) -> dict:
        write_samples(self.config.inbox_dir)
        summary = self.scan()
        summary["loaded"] = True
        return summary


def make_server(app: App, port: int = 0) -> ThreadingHTTPServer:
    handler = handler_factory(app)
    return ThreadingHTTPServer((BIND_HOST, port), handler)


def serve_forever(app: App, port: int) -> ThreadingHTTPServer:
    httpd = make_server(app, port)
    httpd.serve_forever()
    return httpd


def handler_factory(app: App):
    web_dir = bundle_root() / "formdueboard" / "web"
    icon_png = bundle_root() / "assets" / "icon.png"
    icon_ico = bundle_root() / "assets" / "icon.ico"

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            return

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                self._file(web_dir / "index.html", "text/html; charset=utf-8")
                return
            if path == "/styles.css":
                self._file(web_dir / "styles.css", "text/css; charset=utf-8")
                return
            if path == "/app.js":
                self._file(web_dir / "app.js", "text/javascript; charset=utf-8")
                return
            if path in {"/icon.png", "/apple-touch-icon.png"}:
                self._file(icon_png, "image/png")
                return
            if path == "/favicon.ico":
                self._file(icon_ico, "image/x-icon")
                return
            if path == "/api/health":
                self._json({"ok": True, "host": BIND_HOST})
                return
            if path == "/api/board":
                self._json(build_board(app.db, app.config))
                return
            if path == "/api/ics":
                board = build_board(app.db, app.config)
                flat = [item for kid in board["kids"] for item in kid["items"]]
                payload = build_ics(flat).encode("utf-8")
                self._bytes(
                    payload,
                    "text/calendar; charset=utf-8",
                    extra={"Content-Disposition": 'attachment; filename="formdueboard.ics"'},
                )
                return
            if path == "/print":
                page = render_checklist(build_board(app.db, app.config)).encode("utf-8")
                self._bytes(page, "text/html; charset=utf-8")
                return
            item_match = re.fullmatch(r"/api/items/(\d+)", path)
            if item_match:
                item = app.db.get_item(int(item_match.group(1)))
                if item is None:
                    self._json({"error": "No form with that id."}, status=404)
                    return
                self._json(item)
                return
            self._json({"error": "Not found."}, status=404)

        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                self._json({"error": "That upload is larger than 25 MB."}, status=400)
                return
            # Read the body before responding. A leftover body on a keep-alive
            # connection is parsed as the next request.
            self._body = self.rfile.read(length) if length else b""
            path = urlparse(self.path).path
            try:
                if path == "/api/scan":
                    self._json(app.scan())
                    return
                if path == "/api/samples":
                    self._json(app.load_samples())
                    return
                if path == "/api/upload":
                    self._json(self._upload())
                    return
                if path == "/api/gmail/fetch":
                    self._gmail()
                    return
                status_match = re.fullmatch(r"/api/items/(\d+)/status", path)
                if status_match:
                    self._set_status(int(status_match.group(1)))
                    return
                done_match = re.fullmatch(r"/api/items/(\d+)/done", path)
                if done_match:
                    updated = app.db.set_status(int(done_match.group(1)), "returned")
                    if updated is None:
                        self._json({"error": "No form with that id."}, status=404)
                        return
                    self._json({"ok": True, "status": "returned"})
                    return
                assign_match = re.fullmatch(r"/api/items/(\d+)/assign", path)
                if assign_match:
                    self._assign(int(assign_match.group(1)))
                    return
            except (GmailDisabled, GmailConfigError, ValueError) as exc:
                self._json({"error": str(exc)}, status=400)
                return
            self._json({"error": "Not found."}, status=404)

        def _set_status(self, item_id: int) -> None:
            body = self._read_json()
            status = str(body.get("status") or "")
            if status not in STATUSES:
                raise ValueError("Status must be todo, signed, or returned.")
            updated = app.db.set_status(item_id, status)
            if updated is None:
                self._json({"error": "No form with that id."}, status=404)
                return
            self._json({"ok": True, "status": status})

        def _assign(self, item_id: int) -> None:
            body = self._read_json()
            kid_name = str(body.get("kid_name") or "")
            known = {kid.name for kid in app.config.kids}
            if kid_name not in known:
                raise ValueError("That kid is not in the config.")
            item = app.db.get_item(item_id)
            if item is None:
                self._json({"error": "No form with that id."}, status=404)
                return
            fp = fingerprint(kid_name, item["form_type"], item["title"], item.get("due_date"))
            app.db.assign_kid(item_id, kid_name, fp)
            self._json({"ok": True, "kid_name": kid_name})

        def _gmail(self) -> None:
            try:
                saved = fetch_to_inbox(app.config)
            except GmailDisabled as exc:
                self._json({"error": str(exc)}, status=403)
                return
            summary = app.scan()
            summary["saved"] = len(saved)
            self._json(summary)

        def _upload(self) -> dict:
            body = getattr(self, "_body", b"")
            content_type = self.headers.get("Content-Type") or ""
            files = _parse_multipart(body, content_type)
            if not files:
                raise ValueError("Choose an .eml or .mbox file to add.")
            inbox = app.config.inbox_dir
            inbox.mkdir(parents=True, exist_ok=True)
            saved = 0
            for filename, data in files:
                safe = Path(filename).name
                if not safe or safe.startswith("."):
                    continue
                target = inbox / safe
                target.write_bytes(data)
                saved += 1
            summary = app.scan()
            summary["saved"] = saved
            return summary

        def _read_json(self) -> dict:
            raw = getattr(self, "_body", b"")
            if len(raw) > MAX_JSON:
                raise ValueError("That request is too large.")
            if not raw:
                return {}
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object.")
            return data

        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self._bytes(body, "application/json; charset=utf-8", status=status)

        def _file(self, path: Path, content_type: str) -> None:
            if not path.is_file():
                self._json({"error": "Missing file."}, status=404)
                return
            self._bytes(path.read_bytes(), content_type)

        def _bytes(self, payload: bytes, content_type: str, status: int = 200, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if extra:
                for key, value in extra.items():
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

    return Handler


def start_background(app: App, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    httpd = make_server(app, port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    host, bound = httpd.server_address[:2]
    return httpd, f"http://{host}:{bound}"


def _parse_multipart(body: bytes, content_type: str) -> list[tuple[str, bytes]]:
    match = re.search(r'boundary=("?)([^";]+)\1', content_type)
    if not match:
        return []
    boundary = match.group(2).encode("utf-8", "replace")
    files: list[tuple[str, bytes]] = []
    for part in body.split(b"--" + boundary):
        if b"Content-Disposition" not in part:
            continue
        header, _, data = part.partition(b"\r\n\r\n")
        if b"filename=" not in header:
            continue
        name_match = re.search(rb'filename="([^"]*)"', header) or re.search(rb"filename=([^;\r\n]+)", header)
        filename = "upload.eml"
        if name_match:
            filename = name_match.group(1).decode("utf-8", "replace").strip().strip('"')
        data = data.removesuffix(b"\r\n")
        if data.endswith(b"--"):
            data = data[:-2].removesuffix(b"\r\n")
        if data:
            files.append((filename, data))
    return files
