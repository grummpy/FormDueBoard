"""Load the local YAML config. Gmail stays off unless the file turns it on."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from formdueboard.paths import app_root

DEFAULT_GMAIL_QUERY = (
    'newer_than:120d (permission OR "permission slip" OR "field trip" '
    'OR "picture day" OR "sign and return" OR fee OR form)'
)


@dataclass
class KidConfig:
    name: str
    nicknames: list[str]
    grade: str
    teachers: list[str]


@dataclass
class GmailConfig:
    enabled: bool = False
    credentials_file: str = "data/gmail_client_secret.json"
    token_file: str = "data/gmail_token.json"
    query: str = DEFAULT_GMAIL_QUERY
    max_messages: int = 200


@dataclass
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    inbox_dir: Path = field(default_factory=lambda: Path("data/inbox"))
    db_path: Path = field(default_factory=lambda: Path("data/formdueboard.sqlite"))
    timezone: str = "America/New_York"
    due_soon_days: int = 7
    confidence_threshold: float = 0.55
    kids: list[KidConfig] = field(default_factory=list)
    gmail: GmailConfig = field(default_factory=GmailConfig)
    config_path: Path | None = None


def default_kids() -> list[KidConfig]:
    return [
        KidConfig(
            name="Student A",
            nicknames=["Student A", "Kid A"],
            grade="4",
            teachers=["Ms. Calder", "mscalder@example.com"],
        ),
        KidConfig(
            name="Student B",
            nicknames=["Student B", "Kid B"],
            grade="2",
            teachers=["Mr. Okonkwo", "mokonkwo@example.com"],
        ),
    ]


def example_config_path() -> Path:
    return app_root() / "config.example.yaml"


def default_config_path() -> Path:
    return app_root() / "data" / "config.yaml"


def ensure_config_file(path: str | Path | None = None) -> Path:
    """Copy the example config into the gitignored data folder on first launch."""
    target = Path(path) if path is not None else default_config_path()
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    example = example_config_path()
    if example.exists():
        shutil.copyfile(example, target)
    else:
        target.write_text(_fallback_yaml(), encoding="utf-8")
    return target


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = ensure_config_file(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{config_path} must contain a mapping")
    root = config_path.parent.parent if config_path.parent.name == "data" else config_path.parent
    # Paths in a config that lives outside the repo (tests) resolve against the file's folder
    # when they are relative. The shipped file lives in data/, so hop up to the app root.
    if path is not None and config_path.parent.name != "data":
        root = config_path.parent

    kids_raw = raw.get("kids")
    kids = _kids_from_raw(kids_raw) if kids_raw else default_kids()
    gmail_raw = raw.get("gmail") or {}
    gmail = GmailConfig(
        enabled=bool(gmail_raw.get("enabled", False)),
        credentials_file=str(gmail_raw.get("credentials_file", "data/gmail_client_secret.json")),
        token_file=str(gmail_raw.get("token_file", "data/gmail_token.json")),
        query=str(gmail_raw.get("query", DEFAULT_GMAIL_QUERY)),
        max_messages=int(gmail_raw.get("max_messages", 200)),
    )
    cfg = AppConfig(
        host="127.0.0.1",
        port=int(raw.get("port", 8765)),
        inbox_dir=_resolve(root, raw.get("inbox_dir", "data/inbox")),
        db_path=_resolve(root, raw.get("db_path", "data/formdueboard.sqlite")),
        timezone=str(raw.get("timezone", "America/New_York")),
        due_soon_days=int(raw.get("due_soon_days", 7)),
        confidence_threshold=float(raw.get("confidence_threshold", 0.55)),
        kids=kids,
        gmail=gmail,
        config_path=config_path,
    )
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.gmail.credentials_file = str(_resolve(root, cfg.gmail.credentials_file))
    cfg.gmail.token_file = str(_resolve(root, cfg.gmail.token_file))
    return cfg


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (root / path).resolve()


def _kids_from_raw(rows: object) -> list[KidConfig]:
    if not isinstance(rows, list):
        raise ValueError("kids must be a list")
    kids: list[KidConfig] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("name"):
            raise ValueError("each kid needs a name")
        nicknames = row.get("nicknames") or [row["name"]]
        teachers = row.get("teachers") or []
        kids.append(
            KidConfig(
                name=str(row["name"]),
                nicknames=[str(n) for n in nicknames],
                grade=str(row.get("grade") or ""),
                teachers=[str(t) for t in teachers],
            )
        )
    return kids


def _fallback_yaml() -> str:
    return (
        "timezone: America/New_York\n"
        "due_soon_days: 7\n"
        "confidence_threshold: 0.55\n"
        "inbox_dir: data/inbox\n"
        "db_path: data/formdueboard.sqlite\n"
        "gmail:\n"
        "  enabled: false\n"
        "kids:\n"
        "  - name: Student A\n"
        "    nicknames: [Student A, Kid A]\n"
        "    grade: '4'\n"
        "    teachers: [Ms. Calder, mscalder@example.com]\n"
        "  - name: Student B\n"
        "    nicknames: [Student B, Kid B]\n"
        "    grade: '2'\n"
        "    teachers: [Mr. Okonkwo, mokonkwo@example.com]\n"
    )
