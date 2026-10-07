"""Fail if a fixture or source file contains an email outside example.com."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
ALLOWED_HOSTS = {"example.com", "example.org", "example.net"}
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "dist", "build"}
BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".ico",
    ".icns",
    ".woff",
    ".woff2",
    ".pdf",
    ".docx",
    ".pyc",
    ".sqlite",
}


def scan_tree(root: Path) -> list[str]:
    problems: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() in BINARY_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in EMAIL_RE.finditer(text):
            host = match.group(0).rsplit("@", 1)[1].lower()
            if host not in ALLOWED_HOSTS:
                relative = path.relative_to(root)
                problems.append(f"{relative}: {match.group(0)}")
    return problems


def test_repository_uses_only_example_domains():
    problems = scan_tree(ROOT)
    assert problems == []


def test_scanner_flags_a_real_looking_address(tmp_path):
    sample = tmp_path / "note.txt"
    sample.write_text("Please reply to parent@" + "gmail.com\n", encoding="utf-8")
    problems = scan_tree(tmp_path)
    assert problems
    assert "gmail.com" in problems[0]
