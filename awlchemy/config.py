"""Paths and user settings for Awlchemy.

Everything lives next to the project folder (or in $AWLCHEMY_HOME):
    library/<source name>/      one mirrored folder per pattern source (see sources.py)
    library/Imported/           patterns you added through Import
    data/                       database, thumbnails, settings, chat photos

Nothing personal is in the code: your sources (Drive links, folders), toolkit
and preferences live in data/settings.json, which is git-ignored.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ROOT = Path(os.environ.get("AWLCHEMY_HOME", Path(__file__).resolve().parent.parent))
LIBRARY_DIR = ROOT / "library"
IMPORT_DIR = LIBRARY_DIR / "Imported"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "awlchemy.db"
THUMB_DIR = DATA_DIR / "thumbs"
UPLOAD_DIR = DATA_DIR / "chat_photos"
SETTINGS_PATH = DATA_DIR / "settings.json"
KNOWLEDGE_DIR = Path(__file__).resolve().parent / "knowledge"   # ships with the app
USER_KNOWLEDGE_DIR = DATA_DIR / "knowledge"                        # your own extra notes for the teacher

DEFAULT_SETTINGS: dict = {
    "model": "claude-sonnet-5-5",
    "sources": [],  # [{"name", "kind": "gdrive"|"folder", "location", "enabled"}], see sources.py
    "auto_sync_on_start": True,
    "last_sync": None,
    "experience": "complete beginner",
    "country": "",   # two-letter code; used to find shops that ship to you
    "currency": "",
    "units": "metric",
    "toolkit": [],  # tools the user owns, free text
    "about_me": "",  # anything else the teacher should know
}

_lock = threading.Lock()


def ensure_dirs() -> None:
    for d in (LIBRARY_DIR, IMPORT_DIR, DATA_DIR, THUMB_DIR, UPLOAD_DIR, USER_KNOWLEDGE_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _migrate(data: dict) -> dict:
    """Settings from before multiple sources had a single "drive_folder" link."""
    if data.get("drive_folder") and "sources" not in data:
        mirrors = [m.parent.name for m in LIBRARY_DIR.glob("*/.sync-manifest.json")
                   if m.parent.name != IMPORT_DIR.name] if LIBRARY_DIR.exists() else []
        name = mirrors[0] if mirrors else "Google Drive"
        data["sources"] = [{"name": name, "kind": "gdrive", "location": data["drive_folder"], "enabled": True}]
    return data


def load_settings() -> dict:
    with _lock:
        data = {}
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        data = _migrate(data)
        # unknown keys (e.g. the API key older versions stored) are dropped
        return {**DEFAULT_SETTINGS, **{k: v for k, v in data.items() if k in DEFAULT_SETTINGS}}


def save_settings(updates: dict) -> dict:
    current = load_settings()
    allowed = {k: v for k, v in updates.items() if k in DEFAULT_SETTINGS}
    current.update(allowed)
    with _lock:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(SETTINGS_PATH)
    return current
