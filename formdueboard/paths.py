"""Locate the app folder, bundled assets, and the writable data folder."""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Writable root: the repo when running from source, else the folder of the executable."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def bundle_root() -> Path:
    """Read-only root for web files and icons. PyInstaller unpacks them into _MEIPASS."""
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return app_root()
