"""SQLite storage. One small database file under the data dir.

Connections are short-lived (open, use, close per request) which is plenty
for a single-user tracker and keeps the code free of pooling machinery.
"""

import os
import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    archived INTEGER NOT NULL DEFAULT 0,
    claude_path TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS columns (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    is_done INTEGER NOT NULL DEFAULT 0,
    wip_limit INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    column_id INTEGER NOT NULL REFERENCES columns(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    labels TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL DEFAULT 2,
    due_date TEXT NOT NULL DEFAULT '',
    today INTEGER NOT NULL DEFAULT 0,
    today_position INTEGER NOT NULL DEFAULT 0,
    recur_days INTEGER NOT NULL DEFAULT 0,
    assignee_id INTEGER,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS subtasks (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS card_events (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    actor TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_subtasks_card ON subtasks(card_id, position);
CREATE INDEX IF NOT EXISTS idx_events_card ON card_events(card_id, id);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    stored TEXT NOT NULL UNIQUE,
    size INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'member',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_used TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_cards_column ON cards(column_id, position);
CREATE INDEX IF NOT EXISTS idx_cards_today ON cards(today, today_position);
CREATE TABLE IF NOT EXISTS user_today (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, card_id)
);
"""


def db_path() -> Path:
    return config.DATA_DIR / "tracker.db"


def connect() -> sqlite3.Connection:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive migrations for databases created by older versions."""
    project_cols = {r["name"] for r in conn.execute("PRAGMA table_info(projects)")}
    if "claude_path" not in project_cols:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN claude_path TEXT NOT NULL DEFAULT ''"
        )
    if "status" not in project_cols:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN status TEXT NOT NULL DEFAULT 'active'"
        )
    column_cols = {r["name"] for r in conn.execute("PRAGMA table_info(columns)")}
    if "wip_limit" not in column_cols:
        conn.execute(
            "ALTER TABLE columns ADD COLUMN wip_limit INTEGER NOT NULL DEFAULT 0"
        )
    card_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cards)")}
    if "recur_days" not in card_cols:
        conn.execute(
            "ALTER TABLE cards ADD COLUMN recur_days INTEGER NOT NULL DEFAULT 0"
        )
    if "assignee_id" not in card_cols:
        conn.execute("ALTER TABLE cards ADD COLUMN assignee_id INTEGER")
    # Personal Today lists arrived after 0.x installs shipped; the shared
    # list stays in cards.today untouched, personal picks live here.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_today ("
        " user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        " card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,"
        " position INTEGER NOT NULL DEFAULT 0,"
        " PRIMARY KEY (user_id, card_id))"
    )
