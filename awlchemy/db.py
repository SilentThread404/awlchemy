"""SQLite storage for the pattern library, guides, notes and tutor chats."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS patterns (
    id           INTEGER PRIMARY KEY,
    rel_path     TEXT UNIQUE NOT NULL,     -- relative to library/
    title        TEXT NOT NULL,
    collection   TEXT,                     -- folder the PDF sits in
    difficulty   TEXT,                     -- Easy / Medium / Hard / Very Hard / NULL
    source       TEXT,                     -- source name (top folder in library/) or Imported
    kind         TEXT DEFAULT 'pattern',   -- pattern | guide
    source_url   TEXT,
    pages        INTEGER,
    file_size    INTEGER,
    mtime        REAL,
    text         TEXT,                     -- extracted text for search (may be empty for image-only PDFs)
    added_at     TEXT,
    missing      INTEGER DEFAULT 0,        -- file no longer on disk
    favorite     INTEGER DEFAULT 0,
    status       TEXT DEFAULT '',          -- '' | wishlist | in_progress | done
    notes        TEXT DEFAULT '',
    progress     TEXT DEFAULT '[]',        -- JSON list of completed step indexes
    guide        TEXT,                     -- JSON from the tutor
    guide_model  TEXT,
    guide_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_patterns_collection ON patterns(collection);

CREATE TABLE IF NOT EXISTS chats (
    id          INTEGER PRIMARY KEY,
    pattern_id  INTEGER REFERENCES patterns(id) ON DELETE CASCADE,
    title       TEXT,
    session_id  TEXT,                      -- Claude Code session, resumed on every turn
    created_at  TEXT,
    updated_at  TEXT
);

CREATE TABLE IF NOT EXISTS technique_videos (
    id          INTEGER PRIMARY KEY,
    technique   TEXT NOT NULL,             -- normalised technique name, e.g. 'saddle stitch'
    video_id    TEXT NOT NULL,             -- YouTube id
    title       TEXT,
    channel     TEXT,
    why         TEXT,                      -- what this video is good for
    found_at    TEXT,
    UNIQUE (technique, video_id)
);
CREATE TABLE IF NOT EXISTS technique_searches (
    technique   TEXT PRIMARY KEY,          -- searched already (even if nothing was found)
    searched_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY,
    chat_id     INTEGER NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,             -- user | assistant
    content     TEXT NOT NULL,             -- JSON list of text / image_ref blocks
    display     TEXT,                      -- plain text/markdown for the UI
    sources     TEXT DEFAULT '[]',         -- JSON list of {title,url}
    created_at  TEXT
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def session():
    conn = connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    config.ensure_dirs()
    with session() as conn:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(chats)")}
        if "session_id" not in cols:  # databases from before the Claude Code switch
            conn.execute("ALTER TABLE chats ADD COLUMN session_id TEXT")


def row_to_pattern(row: sqlite3.Row, full: bool = False) -> dict:
    d = dict(row)
    d.pop("text", None)
    d["progress"] = json.loads(d.get("progress") or "[]")
    d["has_guide"] = bool(d.get("guide"))
    if full:
        d["guide"] = json.loads(d["guide"]) if d.get("guide") else None
    else:
        d.pop("guide", None)
    return d
