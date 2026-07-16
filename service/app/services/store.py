"""Board data access: projects, columns (statuses), cards, and Today's Tasks.

All ordering uses integer positions renumbered on every move. That is an
O(n) write per drag, which is the right trade for a single-user board:
simple, gap-free, and impossible to corrupt.
"""

from .. import database

DEFAULT_COLUMNS = ["Backlog", "To Do", "In Progress", "Done"]


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ---- projects ----

def list_projects(include_archived: bool = False) -> list[dict]:
    with database.connect() as conn:
        q = "SELECT * FROM projects"
        if not include_archived:
            q += " WHERE archived = 0"
        q += " ORDER BY position, id"
        return _rows(conn.execute(q))


def get_project(project_id: int) -> dict | None:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None


def create_project(name: str, columns: list[str] | None = None) -> dict:
    columns = columns or DEFAULT_COLUMNS
    with database.connect() as conn:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM projects"
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO projects (name, position) VALUES (?, ?)", (name, pos)
        )
        project_id = cur.lastrowid
        for i, col in enumerate(columns):
            conn.execute(
                "INSERT INTO columns (project_id, name, position, is_done)"
                " VALUES (?, ?, ?, ?)",
                (project_id, col, i, 1 if i == len(columns) - 1 else 0),
            )
    return get_project(project_id)


def rename_project(project_id: int, name: str) -> None:
    with database.connect() as conn:
        conn.execute("UPDATE projects SET name = ? WHERE id = ?", (name, project_id))


def archive_project(project_id: int, archived: bool = True) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE projects SET archived = ? WHERE id = ?",
            (1 if archived else 0, project_id),
        )


def delete_project(project_id: int) -> None:
    with database.connect() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))


# ---- columns ----

def list_columns(project_id: int) -> list[dict]:
    with database.connect() as conn:
        return _rows(
            conn.execute(
                "SELECT * FROM columns WHERE project_id = ? ORDER BY position, id",
                (project_id,),
            )
        )


def create_column(project_id: int, name: str) -> dict:
    with database.connect() as conn:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM columns WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO columns (project_id, name, position) VALUES (?, ?, ?)",
            (project_id, name, pos),
        )
        return dict(
            conn.execute(
                "SELECT * FROM columns WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
        )


def rename_column(column_id: int, name: str) -> None:
    with database.connect() as conn:
        conn.execute("UPDATE columns SET name = ? WHERE id = ?", (name, column_id))


def set_column_done(column_id: int, is_done: bool) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE columns SET is_done = ? WHERE id = ?",
            (1 if is_done else 0, column_id),
        )


def move_column(column_id: int, new_position: int) -> None:
    with database.connect() as conn:
        row = conn.execute(
            "SELECT project_id FROM columns WHERE id = ?", (column_id,)
        ).fetchone()
        if not row:
            return
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM columns WHERE project_id = ? ORDER BY position, id",
                (row["project_id"],),
            )
        ]
        ids.remove(column_id)
        new_position = max(0, min(new_position, len(ids)))
        ids.insert(new_position, column_id)
        for i, cid in enumerate(ids):
            conn.execute("UPDATE columns SET position = ? WHERE id = ?", (i, cid))


def delete_column(column_id: int) -> bool:
    """Delete a column. Refuses when it still holds cards."""
    with database.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE column_id = ?", (column_id,)
        ).fetchone()[0]
        if count:
            return False
        conn.execute("DELETE FROM columns WHERE id = ?", (column_id,))
        return True


# ---- cards ----

CARD_FIELDS = {"title", "description", "labels", "priority", "due_date"}


def list_cards(project_id: int) -> list[dict]:
    with database.connect() as conn:
        return _rows(
            conn.execute(
                "SELECT * FROM cards WHERE project_id = ? ORDER BY position, id",
                (project_id,),
            )
        )


def get_card(card_id: int) -> dict | None:
    with database.connect() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return dict(row) if row else None


def create_card(project_id: int, column_id: int, title: str, **fields) -> dict:
    with database.connect() as conn:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM cards WHERE column_id = ?",
            (column_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO cards (project_id, column_id, title, description, labels,"
            " priority, due_date, position) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                column_id,
                title,
                fields.get("description", ""),
                fields.get("labels", ""),
                int(fields.get("priority", 2)),
                fields.get("due_date", ""),
                pos,
            ),
        )
        card_id = cur.lastrowid
    return get_card(card_id)


def update_card(card_id: int, **fields) -> dict | None:
    updates = {k: v for k, v in fields.items() if k in CARD_FIELDS}
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        with database.connect() as conn:
            conn.execute(
                f"UPDATE cards SET {sets}, updated_at = datetime('now') WHERE id = ?",
                (*updates.values(), card_id),
            )
    return get_card(card_id)


def delete_card(card_id: int) -> None:
    with database.connect() as conn:
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))


def _renumber_column(conn, column_id: int) -> None:
    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM cards WHERE column_id = ? ORDER BY position, id",
            (column_id,),
        )
    ]
    for i, cid in enumerate(ids):
        conn.execute("UPDATE cards SET position = ? WHERE id = ?", (i, cid))


def move_card(card_id: int, column_id: int, position: int) -> dict | None:
    """Move a card into column_id at the given index within that column."""
    with database.connect() as conn:
        card = conn.execute(
            "SELECT * FROM cards WHERE id = ?", (card_id,)
        ).fetchone()
        if not card:
            return None
        target = conn.execute(
            "SELECT * FROM columns WHERE id = ?", (column_id,)
        ).fetchone()
        if not target or target["project_id"] != card["project_id"]:
            return None
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM cards WHERE column_id = ? ORDER BY position, id",
                (column_id,),
            )
        ]
        if card_id in ids:
            ids.remove(card_id)
        position = max(0, min(position, len(ids)))
        ids.insert(position, card_id)
        old_column = card["column_id"]
        conn.execute(
            "UPDATE cards SET column_id = ?, updated_at = datetime('now')"
            " WHERE id = ?",
            (column_id, card_id),
        )
        for i, cid in enumerate(ids):
            conn.execute("UPDATE cards SET position = ? WHERE id = ?", (i, cid))
        if old_column != column_id:
            _renumber_column(conn, old_column)
    return get_card(card_id)


def search_cards(query: str, project_id: int | None = None, limit: int = 50) -> list[dict]:
    """Search titles, descriptions, and labels across active projects."""
    like = f"%{query.strip()}%"
    sql = (
        "SELECT cards.*, projects.name AS project_name,"
        " columns.name AS status, columns.is_done AS done"
        " FROM cards"
        " JOIN projects ON projects.id = cards.project_id"
        " JOIN columns ON columns.id = cards.column_id"
        " WHERE projects.archived = 0"
        " AND (cards.title LIKE ? OR cards.description LIKE ? OR cards.labels LIKE ?)"
    )
    args: list = [like, like, like]
    if project_id:
        sql += " AND cards.project_id = ?"
        args.append(project_id)
    sql += " ORDER BY cards.updated_at DESC, cards.id DESC LIMIT ?"
    args.append(limit)
    with database.connect() as conn:
        return _rows(conn.execute(sql, args))


def export_data() -> dict:
    """Everything in the database, for backups."""
    with database.connect() as conn:
        return {
            "projects": _rows(conn.execute("SELECT * FROM projects ORDER BY id")),
            "columns": _rows(conn.execute("SELECT * FROM columns ORDER BY id")),
            "cards": _rows(conn.execute("SELECT * FROM cards ORDER BY id")),
        }


def import_data(data: dict) -> dict:
    """Replace the whole database with an export. Counts what landed."""
    projects = data.get("projects") or []
    columns = data.get("columns") or []
    cards = data.get("cards") or []
    with database.connect() as conn:
        conn.execute("DELETE FROM cards")
        conn.execute("DELETE FROM columns")
        conn.execute("DELETE FROM projects")
        for p in projects:
            conn.execute(
                "INSERT INTO projects (id, name, position, archived, created_at)"
                " VALUES (?, ?, ?, ?, COALESCE(?, datetime('now')))",
                (p.get("id"), p.get("name", "Project"), p.get("position", 0),
                 p.get("archived", 0), p.get("created_at")),
            )
        for c in columns:
            conn.execute(
                "INSERT INTO columns (id, project_id, name, position, is_done)"
                " VALUES (?, ?, ?, ?, ?)",
                (c.get("id"), c["project_id"], c.get("name", "Column"),
                 c.get("position", 0), c.get("is_done", 0)),
            )
        for c in cards:
            conn.execute(
                "INSERT INTO cards (id, project_id, column_id, title, description,"
                " labels, priority, due_date, today, today_position, position,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
                " COALESCE(?, datetime('now')), COALESCE(?, datetime('now')))",
                (c.get("id"), c["project_id"], c["column_id"], c.get("title", ""),
                 c.get("description", ""), c.get("labels", ""), c.get("priority", 2),
                 c.get("due_date", ""), c.get("today", 0), c.get("today_position", 0),
                 c.get("position", 0), c.get("created_at"), c.get("updated_at")),
            )
    return {"projects": len(projects), "columns": len(columns), "cards": len(cards)}


def list_due_cards(
    start: str, end: str, project_ids: list[int] | None = None
) -> list[dict]:
    """Cards with a due date in [start, end], for the calendar.

    Dates are ISO strings (YYYY-MM-DD) so plain string comparison is
    correct. Archived projects are excluded; project_ids narrows further.
    """
    query = (
        "SELECT cards.*, projects.name AS project_name,"
        " columns.name AS status, columns.is_done AS done"
        " FROM cards"
        " JOIN projects ON projects.id = cards.project_id"
        " JOIN columns ON columns.id = cards.column_id"
        " WHERE projects.archived = 0 AND cards.due_date != ''"
        " AND cards.due_date >= ? AND cards.due_date <= ?"
    )
    args: list = [start, end]
    if project_ids:
        marks = ",".join("?" for _ in project_ids)
        query += f" AND cards.project_id IN ({marks})"
        args.extend(project_ids)
    query += " ORDER BY cards.due_date, cards.priority, cards.id"
    with database.connect() as conn:
        return _rows(conn.execute(query, args))


# ---- Today's Tasks ----

def list_today() -> list[dict]:
    """Today's tasks across all projects, with project name and done state."""
    with database.connect() as conn:
        return _rows(
            conn.execute(
                "SELECT cards.*, projects.name AS project_name,"
                " columns.name AS status, columns.is_done AS done"
                " FROM cards"
                " JOIN projects ON projects.id = cards.project_id"
                " JOIN columns ON columns.id = cards.column_id"
                " WHERE cards.today = 1"
                " ORDER BY cards.today_position, cards.id"
            )
        )


def set_today(card_id: int, today: bool, position: int | None = None) -> dict | None:
    with database.connect() as conn:
        if today:
            ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM cards WHERE today = 1"
                    " ORDER BY today_position, id"
                )
            ]
            if card_id in ids:
                ids.remove(card_id)
            pos = len(ids) if position is None else max(0, min(position, len(ids)))
            ids.insert(pos, card_id)
            conn.execute("UPDATE cards SET today = 1 WHERE id = ?", (card_id,))
            for i, cid in enumerate(ids):
                conn.execute(
                    "UPDATE cards SET today_position = ? WHERE id = ?", (i, cid)
                )
        else:
            conn.execute(
                "UPDATE cards SET today = 0, today_position = 0 WHERE id = ?",
                (card_id,),
            )
    return get_card(card_id)


def clear_done_today() -> int:
    """Drop finished cards off the Today list. Returns how many were cleared."""
    with database.connect() as conn:
        cur = conn.execute(
            "UPDATE cards SET today = 0, today_position = 0"
            " WHERE today = 1 AND column_id IN"
            " (SELECT id FROM columns WHERE is_done = 1)"
        )
        return cur.rowcount
