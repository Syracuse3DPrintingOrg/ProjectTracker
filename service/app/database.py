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
    description TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'board',
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
    parent_id INTEGER,
    archived INTEGER NOT NULL DEFAULT 0,
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
    webhook_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read, id);
CREATE TABLE IF NOT EXISTS card_events (
    id INTEGER PRIMARY KEY,
    card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    actor TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
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
    if "description" not in project_cols:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN description TEXT NOT NULL DEFAULT ''"
        )
    if "kind" not in project_cols:
        conn.execute(
            "ALTER TABLE projects ADD COLUMN kind TEXT NOT NULL DEFAULT 'board'"
        )
    column_cols = {r["name"] for r in conn.execute("PRAGMA table_info(columns)")}
    if "wip_limit" not in column_cols:
        conn.execute(
            "ALTER TABLE columns ADD COLUMN wip_limit INTEGER NOT NULL DEFAULT 0"
        )
    user_cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)")}
    if "webhook_url" not in user_cols:
        conn.execute(
            "ALTER TABLE users ADD COLUMN webhook_url TEXT NOT NULL DEFAULT ''"
        )
    card_cols = {r["name"] for r in conn.execute("PRAGMA table_info(cards)")}
    if "recur_days" not in card_cols:
        conn.execute(
            "ALTER TABLE cards ADD COLUMN recur_days INTEGER NOT NULL DEFAULT 0"
        )
    if "assignee_id" not in card_cols:
        conn.execute("ALTER TABLE cards ADD COLUMN assignee_id INTEGER")
    # Subtasks became child cards: a plain INTEGER (SQLite cannot add a
    # foreign key with ALTER TABLE) pointing at the parent card. A child's
    # position is its order among siblings, not a column slot.
    if "parent_id" not in card_cols:
        conn.execute("ALTER TABLE cards ADD COLUMN parent_id INTEGER")
    # Archived cards are finished work swept off the board; they only
    # surface on the project overview's Archived list and in backups.
    if "archived" not in card_cols:
        conn.execute(
            "ALTER TABLE cards ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cards_parent ON cards(parent_id)")
    _convert_legacy_subtasks(conn)
    # Personal Today lists arrived after 0.x installs shipped; the shared
    # list stays in cards.today untouched, personal picks live here.
    conn.execute(
        "CREATE TABLE IF NOT EXISTS user_today ("
        " user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,"
        " card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,"
        " position INTEGER NOT NULL DEFAULT 0,"
        " PRIMARY KEY (user_id, card_id))"
    )


def first_done_column(conn: sqlite3.Connection, project_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM columns WHERE project_id = ? AND is_done = 1"
        " ORDER BY position, id LIMIT 1",
        (project_id,),
    ).fetchone()
    return row["id"] if row else None


def _convert_legacy_subtasks(conn: sqlite3.Connection) -> None:
    """Turn every row of the old subtasks table into a child card.

    A subtask lands in its parent's project, keeps its title and order,
    and points back at the parent through parent_id. Done subtasks go to
    the project's first done column (falling back to the parent's column)
    so their finished state survives. The old table is dropped afterward.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'subtasks'"
    ).fetchone()
    if not exists:
        return
    rows = conn.execute(
        "SELECT subtasks.*, cards.project_id AS parent_project,"
        " cards.column_id AS parent_column"
        " FROM subtasks JOIN cards ON cards.id = subtasks.card_id"
        " ORDER BY subtasks.card_id, subtasks.position, subtasks.id"
    ).fetchall()
    done_columns: dict[int, int | None] = {}
    next_pos: dict[int, int] = {}
    for r in rows:
        target = r["parent_column"]
        if r["done"]:
            if r["parent_project"] not in done_columns:
                done_columns[r["parent_project"]] = first_done_column(
                    conn, r["parent_project"]
                )
            target = done_columns[r["parent_project"]] or target
        pos = next_pos.get(r["card_id"], 0)
        next_pos[r["card_id"]] = pos + 1
        conn.execute(
            "INSERT INTO cards (project_id, column_id, title, parent_id,"
            " position, created_at)"
            " VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')))",
            (r["parent_project"], target, r["title"], r["card_id"], pos,
             r["created_at"]),
        )
    conn.execute("DROP TABLE subtasks")
