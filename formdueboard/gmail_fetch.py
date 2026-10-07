"""Optional read-only Gmail pull. Off unless the local config enables it.

The only Gmail scope this module requests is gmail.readonly. It downloads raw
messages with users.messages.list and users.messages.get. It does not send,
label, modify, trash, or delete.
"""

from __future__ import annotations

import base64
from pathlib import Path

from formdueboard.config import AppConfig

READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
SCOPES = [READONLY_SCOPE]


class GmailDisabled(RuntimeError):
    """Raised when a fetch is requested while gmail.enabled is false."""


class GmailConfigError(RuntimeError):
    """Raised when the local OAuth client file or libraries are missing."""


def fetch_to_inbox(config: AppConfig) -> list[Path]:
    if not config.gmail.enabled:
        raise GmailDisabled(
            "Gmail fetch is off. Set gmail.enabled to true in the local config "
            "to use a read-only pull with your own OAuth client."
        )
    credentials_path = Path(config.gmail.credentials_file)
    if not credentials_path.is_file():
        raise GmailConfigError(
            "OAuth client file not found at "
            f"{credentials_path}. Create a Desktop OAuth client in Google Cloud, "
            "download the JSON, and save it at that gitignored path."
        )
    service, creds = _service(config, credentials_path)
    saved: list[Path] = []
    page_token = None
    remaining = max(1, int(config.gmail.max_messages))
    inbox = Path(config.inbox_dir)
    inbox.mkdir(parents=True, exist_ok=True)
    while remaining > 0:
        response = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=config.gmail.query,
                maxResults=min(50, remaining),
                pageToken=page_token,
            )
            .execute()
        )
        for item in response.get("messages", []):
            payload = service.users().messages().get(userId="me", id=item["id"], format="raw").execute()
            raw = base64.urlsafe_b64decode(payload["raw"])
            dest = inbox / f"gmail-{item['id']}.eml"
            dest.write_bytes(raw)
            saved.append(dest)
            remaining -= 1
            if remaining <= 0:
                break
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    _store_token(Path(config.gmail.token_file), creds)
    return saved


def _service(config: AppConfig, credentials_path: Path):
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise GmailConfigError("Gmail libraries are not installed. Run: pip install -r requirements-gmail.txt") from exc

    token_path = Path(config.gmail.token_file)
    creds = None
    if token_path.is_file():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds is not None and creds.scopes and any(scope != READONLY_SCOPE for scope in creds.scopes):
        raise GmailConfigError(
            f"The saved token is not limited to gmail.readonly. Delete {token_path} and sign in again."
        )
    if creds is None or not creds.valid:
        if creds is not None and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            creds = flow.run_local_server(port=0)
        _store_token(token_path, creds)
    return build("gmail", "v1", credentials=creds), creds


def _store_token(path: Path, creds) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(creds.to_json(), encoding="utf-8")
    path.chmod(0o600)
