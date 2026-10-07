"""Command line entry point used by the double-click launchers."""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser

from formdueboard import __version__
from formdueboard.config import load_config
from formdueboard.gmail_fetch import GmailConfigError, GmailDisabled, fetch_to_inbox
from formdueboard.ics_export import build_ics
from formdueboard.mail import load_messages_from_path
from formdueboard.samples import write_samples
from formdueboard.server import App, make_server


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    no_browser = "--no-browser" in argv or os.environ.get("FORMDUEBOARD_NO_BROWSER") == "1"
    argv = [arg for arg in argv if arg != "--no-browser"]

    parser = argparse.ArgumentParser(
        prog="formdueboard",
        description="School form due dates, one checklist per kid. Everything stays on this computer.",
    )
    parser.add_argument("--config", help="Path to config.yaml. Defaults to data/config.yaml.")
    parser.add_argument("--port", type=int, help="Port on 127.0.0.1. Defaults to the config, usually 8765.")
    parser.add_argument("--version", action="version", version=f"FormDueBoard {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="Open the board in your browser (the default).")
    scan = sub.add_parser("scan", help="Read .eml and mbox files from the inbox folder.")
    scan.add_argument("path", nargs="?", help="Folder or file to read. Defaults to the configured inbox.")
    export = sub.add_parser("export-ics", help="Write a calendar of open due dates.")
    export.add_argument("-o", "--output", default="-", help="Output path, or - for stdout.")
    sub.add_parser("load-samples", help="Add fictional Student A and Student B mail, then scan it.")
    sub.add_parser("gmail-fetch", help="Read-only Gmail pull. Refuses to run unless gmail.enabled is true.")

    args = parser.parse_args(argv)
    command = args.command or "serve"
    config = load_config(args.config if args.config else None)
    if args.port:
        config.port = args.port

    if command == "serve":
        return _serve(config, open_browser=not no_browser)
    if command == "scan":
        return _scan(config, args.path)
    if command == "export-ics":
        return _export(config, args.output)
    if command == "load-samples":
        write_samples(config.inbox_dir)
        return _scan(config, None)
    if command == "gmail-fetch":
        return _gmail(config)
    parser.print_help()
    return 2


def _serve(config, open_browser: bool) -> int:
    app = App(config)
    port = _bind_port(config.port)
    try:
        httpd = make_server(app, port)
    except OSError:
        httpd = make_server(app, 0)
    host, bound = httpd.server_address[:2]
    url = f"http://{host}:{bound}/"
    print(f"FormDueBoard is running at {url}")
    print("It is only on this computer. Close this window to stop it.")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()
        app.close()
    return 0


def _bind_port(preferred: int) -> int:
    if preferred == 0:
        return 0
    return preferred


def _scan(config, path: str | None) -> int:
    from formdueboard.db import Database
    from formdueboard.ingest import ingest_messages

    target = path or config.inbox_dir
    messages = load_messages_from_path(target)
    db = Database(config.db_path)
    try:
        result = ingest_messages(
            db,
            messages,
            config.kids,
            threshold=config.confidence_threshold,
            tz_name=config.timezone,
        )
    finally:
        db.close()
    print(
        f"Read {result.messages} messages. "
        f"New forms: {result.created}. Updated: {result.updated}. "
        f"Duplicates: {result.duplicates}."
    )
    return 0


def _export(config, output: str) -> int:
    from formdueboard.board import build_board
    from formdueboard.db import Database

    db = Database(config.db_path)
    try:
        board = build_board(db, config)
    finally:
        db.close()
    flat = [item for kid in board["kids"] for item in kid["items"]]
    payload = build_ics(flat)
    if output == "-":
        sys.stdout.write(payload)
    else:
        with open(output, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
        print(f"Wrote {output}")
    return 0


def _gmail(config) -> int:
    try:
        saved = fetch_to_inbox(config)
    except GmailDisabled as exc:
        print(exc)
        return 2
    except GmailConfigError as exc:
        print(exc)
        return 2
    print(f"Saved {len(saved)} message(s) into {config.inbox_dir}.")
    return _scan(config, None)
