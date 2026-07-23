"""Board data access: projects, columns (statuses), cards, and Today's Tasks.

All ordering uses integer positions renumbered on every move. That is an
O(n) write per drag, which is the right trade for a single-user board:
simple, gap-free, and impossible to corrupt.
"""

from .. import database

DEFAULT_COLUMNS = ["Backlog", "To Do", "In Progress", "Done"]

# Project statuses, squirrel edition: chasing it now, buried for later,
# or cracked open and finished.
PROJECT_STATUSES = ("active", "buried", "cracked")


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


PROJECT_KINDS = ("board", "list")

# A simple list wants no kanban ceremony: one working column, one done.
LIST_COLUMNS = ["Items", "Done"]


def create_project(
    name: str, columns: list[str] | None = None, kind: str = "board"
) -> dict:
    if kind not in PROJECT_KINDS:
        raise ValueError(f"unknown project kind: {kind}")
    columns = columns or (LIST_COLUMNS if kind == "list" else DEFAULT_COLUMNS)
    with database.connect() as conn:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM projects"
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO projects (name, position, kind) VALUES (?, ?, ?)",
            (name, pos, kind),
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


def set_project_status(project_id: int, status: str) -> None:
    if status not in PROJECT_STATUSES:
        raise ValueError(f"unknown status: {status}")
    with database.connect() as conn:
        conn.execute(
            "UPDATE projects SET status = ? WHERE id = ?", (status, project_id)
        )


def set_project_description(project_id: int, text: str) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE projects SET description = ? WHERE id = ?", (text, project_id)
        )


# Caps for the overview page lists; the counts stay exact.
OVERVIEW_DONE_CAP = 100
OVERVIEW_FILE_CAP = 100
OVERVIEW_ACTIVITY_CAP = 30


def project_overview(project_id: int) -> dict:
    """Everything the project overview page shows, in a handful of
    queries: open work, finished work, archived work, the project's
    files, recent activity, and the headline counts.

    The card lists are top-level cards only; subtasks surface through
    their parent's progress numbers. Days quiet counts from the newest
    card update anywhere in the project, subtasks included."""
    card_select = (
        "SELECT cards.*, columns.name AS column_name,"
        " users.username AS assignee"
        " FROM cards"
        " JOIN columns ON columns.id = cards.column_id"
        " LEFT JOIN users ON users.id = cards.assignee_id"
        " WHERE cards.project_id = ? AND cards.parent_id IS NULL"
    )
    with database.connect() as conn:
        open_cards = _rows(
            conn.execute(
                card_select + " AND cards.archived = 0 AND columns.is_done = 0"
                " ORDER BY columns.position, columns.id, cards.position, cards.id",
                (project_id,),
            )
        )
        done_cards = _rows(
            conn.execute(
                card_select + " AND cards.archived = 0 AND columns.is_done = 1"
                " ORDER BY cards.updated_at DESC, cards.id DESC LIMIT ?",
                (project_id, OVERVIEW_DONE_CAP),
            )
        )
        archived_cards = _rows(
            conn.execute(
                card_select + " AND cards.archived = 1"
                " ORDER BY cards.updated_at DESC, cards.id DESC LIMIT ?",
                (project_id, OVERVIEW_DONE_CAP),
            )
        )
        files = _rows(
            conn.execute(
                "SELECT attachments.id, attachments.filename, attachments.size,"
                " attachments.created_at, cards.id AS card_id,"
                " cards.title AS card_title"
                " FROM attachments JOIN cards ON cards.id = attachments.card_id"
                " WHERE cards.project_id = ?"
                " ORDER BY attachments.id DESC LIMIT ?",
                (project_id, OVERVIEW_FILE_CAP),
            )
        )
        activity = _rows(
            conn.execute(
                "SELECT card_events.*, cards.title AS card_title"
                " FROM card_events JOIN cards ON cards.id = card_events.card_id"
                " WHERE cards.project_id = ?"
                " ORDER BY card_events.id DESC LIMIT ?",
                (project_id, OVERVIEW_ACTIVITY_CAP),
            )
        )
        tallies = conn.execute(
            "SELECT COALESCE(SUM(CASE WHEN cards.parent_id IS NULL"
            "   AND cards.archived = 0"
            "   AND columns.is_done = 1 THEN 1 ELSE 0 END), 0) AS done_n,"
            " COALESCE(SUM(CASE WHEN cards.parent_id IS NULL"
            "   AND cards.archived = 1 THEN 1 ELSE 0 END), 0) AS archived_n,"
            " CAST(julianday('now') - julianday(COALESCE(MAX(cards.updated_at),"
            "   (SELECT created_at FROM projects WHERE id = ?)))"
            "   AS INTEGER) AS days_quiet"
            " FROM cards JOIN columns ON columns.id = cards.column_id"
            " WHERE cards.project_id = ?",
            (project_id, project_id),
        ).fetchone()
        file_count = conn.execute(
            "SELECT COUNT(*) FROM attachments"
            " JOIN cards ON cards.id = attachments.card_id"
            " WHERE cards.project_id = ?",
            (project_id,),
        ).fetchone()[0]
    progress = subtask_progress(project_id)
    for c in open_cards:
        c["subtasks_done"], c["subtasks_total"] = progress.get(c["id"], (0, 0))
    return {
        "open_cards": open_cards,
        "done_cards": done_cards,
        "archived_cards": archived_cards,
        "files": files,
        "activity": activity,
        "counts": {
            "open": len(open_cards),
            "done": tallies["done_n"],
            "archived": tallies["archived_n"],
            "files": file_count,
            "days_quiet": tallies["days_quiet"] or 0,
        },
    }


def nudge_data(exclude_project_id: int | None = None) -> list[dict]:
    """The guilt list: active projects with open cards, stalest first.

    Open means the card sits in a column not flagged done. Quiet days
    count from the newest card update in the project (or the project's
    creation when it has no cards)."""
    sql = (
        "SELECT projects.id, projects.name,"
        " COUNT(cards.id) AS open_cards,"
        " CAST(julianday('now') - julianday(COALESCE(MAX(cards.updated_at),"
        "   projects.created_at)) AS INTEGER) AS days_quiet"
        " FROM projects"
        " LEFT JOIN cards ON cards.project_id = projects.id"
        "   AND cards.archived = 0"
        "   AND cards.column_id IN (SELECT id FROM columns WHERE is_done = 0)"
        " WHERE projects.archived = 0 AND projects.status = 'active'"
    )
    args: list = []
    if exclude_project_id:
        sql += " AND projects.id != ?"
        args.append(exclude_project_id)
    sql += " GROUP BY projects.id HAVING open_cards > 0"
    sql += " ORDER BY days_quiet DESC, open_cards DESC"
    with database.connect() as conn:
        return _rows(conn.execute(sql, args))


def set_claude_link(project_id: int, claude_path: str) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE projects SET claude_path = ? WHERE id = ?",
            (claude_path.strip(), project_id),
        )


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


def set_wip_limit(column_id: int, limit: int) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE columns SET wip_limit = ? WHERE id = ?",
            (max(0, limit), column_id),
        )


def plan_candidates(limit: int = 40, owner: int | None = None) -> list[dict]:
    """Open cards worth considering for today: not already on the target
    Today list (shared, or owner's personal one), in active projects,
    ordered by due date then priority."""
    if owner is None:
        not_listed = "cards.today = 0"
        args: list = [limit]
    else:
        not_listed = (
            "cards.id NOT IN (SELECT card_id FROM user_today WHERE user_id = ?)"
        )
        args = [owner, limit]
    with database.connect() as conn:
        return _rows(
            conn.execute(
                "SELECT cards.id, cards.title, cards.due_date, cards.priority,"
                " projects.name AS project_name"
                " FROM cards"
                " JOIN projects ON projects.id = cards.project_id"
                " JOIN columns ON columns.id = cards.column_id"
                " WHERE projects.archived = 0 AND projects.status = 'active'"
                f" AND columns.is_done = 0 AND cards.archived = 0 AND {not_listed}"
                " ORDER BY CASE WHEN cards.due_date = '' THEN 1 ELSE 0 END,"
                " cards.due_date, cards.priority, cards.id LIMIT ?",
                args,
            )
        )


def my_work(user_id: int) -> list[dict]:
    """Open cards assigned to one user across active projects, due-date
    first, then priority. Children count; they are real work."""
    with database.connect() as conn:
        return _rows(
            conn.execute(
                "SELECT cards.*, projects.name AS project_name,"
                " columns.name AS column_name"
                " FROM cards"
                " JOIN projects ON projects.id = cards.project_id"
                " JOIN columns ON columns.id = cards.column_id"
                " WHERE projects.archived = 0 AND projects.status = 'active'"
                " AND columns.is_done = 0 AND cards.archived = 0"
                " AND cards.assignee_id = ?"
                " ORDER BY CASE WHEN cards.due_date = '' THEN 1 ELSE 0 END,"
                " cards.due_date, cards.priority, projects.position, cards.id",
                (user_id,),
            )
        )


def project_report(project_id: int, weeks: int = 8) -> dict:
    """Throughput and aging for the overview's reports section.

    Done-per-week buckets finished cards by when they last changed,
    which is when they landed in a done column for almost every card;
    an honest approximation that needs no history table."""
    with database.connect() as conn:
        per_week = {
            r["week"]: r["n"]
            for r in conn.execute(
                "SELECT strftime('%Y-%W', cards.updated_at) AS week,"
                " COUNT(*) AS n FROM cards"
                " JOIN columns ON columns.id = cards.column_id"
                " WHERE cards.project_id = ? AND columns.is_done = 1"
                " AND cards.updated_at >= datetime('now', ?)"
                " GROUP BY week",
                (project_id, f"-{weeks * 7} days"),
            )
        }
        weeks_out = []
        for i in range(weeks - 1, -1, -1):
            row = conn.execute(
                "SELECT strftime('%Y-%W', datetime('now', ?)) AS wk,"
                " strftime('%m/%d', datetime('now', ?, 'weekday 1', '-7 days')) AS label",
                (f"-{i * 7} days", f"-{i * 7} days"),
            ).fetchone()
            weeks_out.append(
                {"label": row["label"], "done": per_week.get(row["wk"], 0)}
            )
        avg_age = conn.execute(
            "SELECT AVG(julianday('now') - julianday(cards.created_at)) AS age"
            " FROM cards JOIN columns ON columns.id = cards.column_id"
            " WHERE cards.project_id = ? AND columns.is_done = 0",
            (project_id,),
        ).fetchone()["age"]
        column_counts = _rows(
            conn.execute(
                "SELECT columns.name, columns.is_done, COUNT(cards.id) AS n"
                " FROM columns LEFT JOIN cards ON cards.column_id = columns.id"
                " AND cards.parent_id IS NULL"
                " WHERE columns.project_id = ?"
                " GROUP BY columns.id ORDER BY columns.position",
                (project_id,),
            )
        )
    peak = max((w["done"] for w in weeks_out), default=0)
    return {
        "weeks": weeks_out,
        "peak": peak,
        "avg_open_age_days": round(avg_age or 0),
        "columns": column_counts,
    }


def due_lists(soon_days: int = 3) -> dict:
    """Open cards past due and due within soon_days, across active
    projects, for the kiosk footer views."""
    sql = (
        "SELECT cards.id, cards.title, cards.due_date, cards.priority,"
        " projects.name AS project_name"
        " FROM cards"
        " JOIN projects ON projects.id = cards.project_id"
        " JOIN columns ON columns.id = cards.column_id"
        " WHERE projects.archived = 0 AND projects.status = 'active'"
        " AND columns.is_done = 0 AND cards.archived = 0 AND cards.due_date != ''"
        " AND cards.due_date <= date('now', 'localtime', ?)"
        " ORDER BY cards.due_date, cards.priority LIMIT 50"
    )
    with database.connect() as conn:
        rows = _rows(conn.execute(sql, (f"+{soon_days} days",)))
        today = conn.execute("SELECT date('now', 'localtime')").fetchone()[0]
    return {
        "overdue": [r for r in rows if r["due_date"] < today],
        "due_soon": [r for r in rows if r["due_date"] >= today],
    }


def overdue_count() -> int:
    with database.connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM cards"
            " JOIN columns ON columns.id = cards.column_id"
            " JOIN projects ON projects.id = cards.project_id"
            " WHERE projects.archived = 0 AND columns.is_done = 0"
            " AND cards.archived = 0"
            " AND cards.due_date != '' AND cards.due_date < date('now', 'localtime')"
        ).fetchone()[0]


def project_open_counts() -> list[dict]:
    """Active projects with their open-card counts, zero included."""
    with database.connect() as conn:
        return _rows(
            conn.execute(
                "SELECT projects.id, projects.name, projects.status,"
                " COUNT(cards.id) AS open_cards"
                " FROM projects"
                " LEFT JOIN cards ON cards.project_id = projects.id"
                "   AND cards.archived = 0"
                "   AND cards.column_id IN"
                "   (SELECT id FROM columns WHERE is_done = 0)"
                " WHERE projects.archived = 0 AND projects.status = 'active'"
                " GROUP BY projects.id ORDER BY projects.position, projects.id"
            )
        )


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

CARD_FIELDS = {
    "title", "description", "labels", "priority", "due_date", "recur_days",
    "assignee_id",
}


def list_cards(project_id: int, include_archived: bool = False) -> list[dict]:
    with database.connect() as conn:
        q = "SELECT * FROM cards WHERE project_id = ?"
        if not include_archived:
            q += " AND archived = 0"
        q += " ORDER BY position, id"
        return _rows(conn.execute(q, (project_id,)))


def get_card(card_id: int) -> dict | None:
    with database.connect() as conn:
        row = conn.execute("SELECT * FROM cards WHERE id = ?", (card_id,)).fetchone()
        return dict(row) if row else None


def create_card(project_id: int, column_id: int, title: str, **fields) -> dict:
    with database.connect() as conn:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM cards"
            " WHERE column_id = ? AND parent_id IS NULL",
            (column_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO cards (project_id, column_id, title, description, labels,"
            " priority, due_date, recur_days, position)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                column_id,
                title,
                fields.get("description", ""),
                fields.get("labels", ""),
                int(fields.get("priority", 2)),
                fields.get("due_date", ""),
                int(fields.get("recur_days", 0)),
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
    """Delete a card. Its children are promoted to top level, not deleted:
    each stays in the column it sits in (so a finished child stays
    finished) and lands at the end of that column."""
    with database.connect() as conn:
        card = conn.execute(
            "SELECT parent_id, column_id FROM cards WHERE id = ?", (card_id,)
        ).fetchone()
        if not card:
            return
        children = conn.execute(
            "SELECT id, column_id FROM cards WHERE parent_id = ?"
            " ORDER BY position, id",
            (card_id,),
        ).fetchall()
        ends: dict[int, int] = {}
        for child in children:
            col = child["column_id"]
            if col not in ends:
                ends[col] = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 FROM cards"
                    " WHERE column_id = ? AND parent_id IS NULL",
                    (col,),
                ).fetchone()[0]
            conn.execute(
                "UPDATE cards SET parent_id = NULL, position = ?,"
                " updated_at = datetime('now') WHERE id = ?",
                (ends[col], child["id"]),
            )
            ends[col] += 1
        conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))
        if card["parent_id"] is not None:
            _renumber_children(conn, card["parent_id"])
        else:
            _renumber_column(conn, card["column_id"])


def _renumber_column(conn, column_id: int) -> None:
    """Renumber the top-level cards of a column. Child cards keep their
    position as an order among siblings, so they stay out of this."""
    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM cards WHERE column_id = ? AND parent_id IS NULL"
            " ORDER BY position, id",
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
        if card["parent_id"] is not None:
            # A child card lives outside the column ordering: switching
            # columns flips its done state, its position stays a sibling
            # index. Recurring children still respawn on a done landing.
            old_column = card["column_id"]
            conn.execute(
                "UPDATE cards SET column_id = ?, updated_at = datetime('now')"
                " WHERE id = ?",
                (column_id, card_id),
            )
            if (
                card["recur_days"] > 0
                and target["is_done"]
                and old_column != column_id
            ):
                _respawn(conn, dict(card), column_id)
            return get_card(card_id)
        ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM cards WHERE column_id = ? AND parent_id IS NULL"
                " ORDER BY position, id",
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
        # A recurring card that lands in a done column respawns for the
        # next round instead of staying finished.
        if (
            card["recur_days"] > 0
            and target["is_done"]
            and old_column != column_id
        ):
            _respawn(conn, dict(card), column_id)
    return get_card(card_id)


def _respawn(conn, card: dict, done_column_id: int) -> None:
    """Send a recurring card back to the start with a fresh due date and
    an unticked checklist."""
    first = conn.execute(
        "SELECT id FROM columns WHERE project_id = ? AND is_done = 0"
        " ORDER BY position, id LIMIT 1",
        (card["project_id"],),
    ).fetchone()
    target = first["id"] if first else done_column_id
    pos = conn.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM cards WHERE column_id = ?",
        (target,),
    ).fetchone()[0]
    description = card["description"].replace("- [x]", "- [ ]").replace("- [X]", "- [ ]")
    conn.execute(
        "UPDATE cards SET column_id = ?, position = ?, description = ?,"
        " due_date = date('now', 'localtime', ?), today = 0, today_position = 0,"
        " updated_at = datetime('now') WHERE id = ?",
        (target, pos, description, f"+{card['recur_days']} days", card["id"]),
    )
    _renumber_column(conn, done_column_id)


def search_cards(query: str, project_id: int | None = None, limit: int = 50) -> list[dict]:
    """Search titles, descriptions, and labels across active projects."""
    like = f"%{query.strip()}%"
    sql = (
        "SELECT cards.*, projects.name AS project_name,"
        " columns.name AS status, columns.is_done AS done"
        " FROM cards"
        " JOIN projects ON projects.id = cards.project_id"
        " JOIN columns ON columns.id = cards.column_id"
        " WHERE projects.archived = 0 AND cards.archived = 0"
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


# ---- the archive ----
#
# Archived cards keep their row, their column, and their history; they
# just stop appearing anywhere except the project overview's Archived
# list and backups. Nothing here deletes anything.

def archive_done_cards(project_id: int) -> int:
    """Sweep the project's finished work into the archive: every
    top-level card sitting in a done column, plus each one's subtasks
    wherever those sit. Returns how many cards were archived."""
    with database.connect() as conn:
        tops = [
            r["id"]
            for r in conn.execute(
                "SELECT cards.id FROM cards"
                " JOIN columns ON columns.id = cards.column_id"
                " WHERE cards.project_id = ? AND cards.parent_id IS NULL"
                " AND cards.archived = 0 AND columns.is_done = 1",
                (project_id,),
            )
        ]
        if not tops:
            return 0
        marks = ",".join("?" for _ in tops)
        cur = conn.execute(
            f"UPDATE cards SET archived = 1 WHERE archived = 0"
            f" AND (id IN ({marks}) OR parent_id IN ({marks}))",
            (*tops, *tops),
        )
        return cur.rowcount


def set_card_archived(card_id: int, archived: bool) -> None:
    """Archive or unarchive one card. A top-level card's subtasks travel
    with it both ways, so a card never comes back missing its pieces."""
    with database.connect() as conn:
        conn.execute(
            "UPDATE cards SET archived = ? WHERE id = ? OR parent_id = ?",
            (1 if archived else 0, card_id, card_id),
        )


def export_data() -> dict:
    """Everything in the database, for backups. Subtasks are child cards,
    so they ride along in the cards list through parent_id."""
    with database.connect() as conn:
        return {
            "projects": _rows(conn.execute("SELECT * FROM projects ORDER BY id")),
            "columns": _rows(conn.execute("SELECT * FROM columns ORDER BY id")),
            "cards": _rows(conn.execute("SELECT * FROM cards ORDER BY id")),
        }


def import_data(data: dict) -> dict:
    """Replace the whole database with an export. Counts what landed.

    Old backups carry a separate subtasks list; those rows land as child
    cards, the same conversion the schema migration does."""
    projects = data.get("projects") or []
    columns = data.get("columns") or []
    cards = data.get("cards") or []
    subtasks = data.get("subtasks") or []
    with database.connect() as conn:
        conn.execute("DELETE FROM cards")
        conn.execute("DELETE FROM columns")
        conn.execute("DELETE FROM projects")
        for p in projects:
            status = p.get("status", "active")
            conn.execute(
                "INSERT INTO projects (id, name, position, archived, claude_path,"
                " status, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))",
                (p.get("id"), p.get("name", "Project"), p.get("position", 0),
                 p.get("archived", 0), p.get("claude_path", ""),
                 status if status in PROJECT_STATUSES else "active",
                 p.get("created_at")),
            )
        for c in columns:
            conn.execute(
                "INSERT INTO columns (id, project_id, name, position, is_done,"
                " wip_limit) VALUES (?, ?, ?, ?, ?, ?)",
                (c.get("id"), c["project_id"], c.get("name", "Column"),
                 c.get("position", 0), c.get("is_done", 0), c.get("wip_limit", 0)),
            )
        for c in cards:
            conn.execute(
                "INSERT INTO cards (id, project_id, column_id, title, description,"
                " labels, priority, due_date, today, today_position, recur_days,"
                " assignee_id, parent_id, archived, position, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,"
                " COALESCE(?, datetime('now')), COALESCE(?, datetime('now')))",
                (c.get("id"), c["project_id"], c["column_id"], c.get("title", ""),
                 c.get("description", ""), c.get("labels", ""), c.get("priority", 2),
                 c.get("due_date", ""), c.get("today", 0), c.get("today_position", 0),
                 c.get("recur_days", 0), c.get("assignee_id"), c.get("parent_id"),
                 c.get("archived", 0),
                 c.get("position", 0), c.get("created_at"), c.get("updated_at")),
            )
        done_columns: dict[int, int | None] = {}
        next_pos: dict[int, int] = {}
        ordered = sorted(
            subtasks,
            key=lambda s: (s.get("card_id", 0), s.get("position", 0), s.get("id", 0)),
        )
        for s in ordered:
            parent = conn.execute(
                "SELECT project_id, column_id FROM cards WHERE id = ?",
                (s.get("card_id"),),
            ).fetchone()
            if not parent:
                continue
            target = parent["column_id"]
            if s.get("done"):
                if parent["project_id"] not in done_columns:
                    done_columns[parent["project_id"]] = database.first_done_column(
                        conn, parent["project_id"]
                    )
                target = done_columns[parent["project_id"]] or target
            if s["card_id"] not in next_pos:
                next_pos[s["card_id"]] = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 FROM cards"
                    " WHERE parent_id = ?",
                    (s["card_id"],),
                ).fetchone()[0]
            conn.execute(
                "INSERT INTO cards (project_id, column_id, title, parent_id,"
                " position, created_at)"
                " VALUES (?, ?, ?, ?, ?, COALESCE(?, datetime('now')))",
                (parent["project_id"], target, s.get("title", ""), s["card_id"],
                 next_pos[s["card_id"]], s.get("created_at")),
            )
            next_pos[s["card_id"]] += 1
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
        " WHERE projects.archived = 0 AND cards.archived = 0"
        " AND cards.due_date != ''"
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


# ---- subtasks (child cards) ----
#
# A subtask is a card whose parent_id points at another card in the same
# project, one level deep. Done means the child sits in a done column. A
# child's position is its order among siblings; column ordering ignores
# children entirely. The functions below keep the old subtask wire shape
# ({id, card_id, title, done, position}) so the board and any callers of
# the /api/subtasks endpoints keep working unchanged.

def _child_rows(conn, parent_id: int) -> list[dict]:
    return _rows(
        conn.execute(
            "SELECT cards.*, columns.is_done AS done FROM cards"
            " JOIN columns ON columns.id = cards.column_id"
            " WHERE cards.parent_id = ? AND cards.archived = 0"
            " ORDER BY cards.position, cards.id",
            (parent_id,),
        )
    )


def _subtask_shape(child: dict, index: int) -> dict:
    return {
        "id": child["id"],
        "card_id": child["parent_id"],
        "title": child["title"],
        "done": child["done"],
        "position": index,
        "created_at": child["created_at"],
    }


def has_children(card_id: int) -> bool:
    with database.connect() as conn:
        return bool(
            conn.execute(
                "SELECT 1 FROM cards WHERE parent_id = ? LIMIT 1", (card_id,)
            ).fetchone()
        )


def children_map(project_id: int) -> dict[int, list[dict]]:
    """{parent_id: [child cards]} for the board page, each child carrying
    a done flag from its column, in sibling order."""
    with database.connect() as conn:
        rows = _rows(
            conn.execute(
                "SELECT cards.*, columns.is_done AS done FROM cards"
                " JOIN columns ON columns.id = cards.column_id"
                " WHERE cards.project_id = ? AND cards.parent_id IS NOT NULL"
                " AND cards.archived = 0"
                " ORDER BY cards.position, cards.id",
                (project_id,),
            )
        )
    out: dict[int, list[dict]] = {}
    for r in rows:
        out.setdefault(r["parent_id"], []).append(r)
    return out


def _renumber_children(conn, parent_id: int) -> None:
    ids = [
        r["id"]
        for r in conn.execute(
            "SELECT id FROM cards WHERE parent_id = ? ORDER BY position, id",
            (parent_id,),
        )
    ]
    for i, cid in enumerate(ids):
        conn.execute("UPDATE cards SET position = ? WHERE id = ?", (i, cid))


def set_parent(card_id: int, parent_id: int | None) -> dict | None:
    """Nest a card under a parent, or promote it to top level.

    Validity (same project, one level, not self) is the caller's job;
    this handles the position bookkeeping on both sides."""
    with database.connect() as conn:
        card = conn.execute(
            "SELECT * FROM cards WHERE id = ?", (card_id,)
        ).fetchone()
        if not card:
            return None
        old_parent = card["parent_id"]
        if parent_id is None:
            if old_parent is None:
                return get_card(card_id)
            end = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM cards"
                " WHERE column_id = ? AND parent_id IS NULL",
                (card["column_id"],),
            ).fetchone()[0]
            conn.execute(
                "UPDATE cards SET parent_id = NULL, position = ?,"
                " updated_at = datetime('now') WHERE id = ?",
                (end, card_id),
            )
            _renumber_children(conn, old_parent)
        else:
            pos = conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM cards"
                " WHERE parent_id = ?",
                (parent_id,),
            ).fetchone()[0]
            conn.execute(
                "UPDATE cards SET parent_id = ?, position = ?,"
                " updated_at = datetime('now') WHERE id = ?",
                (parent_id, pos, card_id),
            )
            if old_parent is None:
                # The card left the column's top-level flow.
                _renumber_column(conn, card["column_id"])
            elif old_parent != parent_id:
                _renumber_children(conn, old_parent)
    return get_card(card_id)


def list_subtasks(card_id: int) -> list[dict]:
    with database.connect() as conn:
        children = _child_rows(conn, card_id)
    return [_subtask_shape(c, i) for i, c in enumerate(children)]


def create_subtask(card_id: int, title: str) -> dict | None:
    """Add a child card in the parent's column. Returns None when the
    parent is missing or is itself a child (one level only)."""
    parent = get_card(card_id)
    if not parent or parent["parent_id"] is not None:
        return None
    with database.connect() as conn:
        pos = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM cards WHERE parent_id = ?",
            (card_id,),
        ).fetchone()[0]
        cur = conn.execute(
            "INSERT INTO cards (project_id, column_id, title, parent_id, position)"
            " VALUES (?, ?, ?, ?, ?)",
            (parent["project_id"], parent["column_id"], title.strip(), card_id, pos),
        )
        child_id = cur.lastrowid
        conn.execute(
            "UPDATE cards SET updated_at = datetime('now') WHERE id = ?",
            (card_id,),
        )
    for i, s in enumerate(list_subtasks(card_id)):
        if s["id"] == child_id:
            return s
    return None


def _set_child_done(conn, child: dict, done: bool) -> None:
    current = conn.execute(
        "SELECT is_done FROM columns WHERE id = ?", (child["column_id"],)
    ).fetchone()
    if current and bool(current["is_done"]) == done:
        return
    target = conn.execute(
        "SELECT id FROM columns WHERE project_id = ? AND is_done = ?"
        " ORDER BY position, id LIMIT 1",
        (child["project_id"], 1 if done else 0),
    ).fetchone()
    if target:
        move_card(child["id"], target["id"], 0)


def update_subtask(
    subtask_id: int,
    title: str | None = None,
    done: bool | None = None,
    position: int | None = None,
) -> dict | None:
    child = get_card(subtask_id)
    if not child or child["parent_id"] is None:
        return None
    parent_id = child["parent_id"]
    if title is not None and title.strip():
        update_card(subtask_id, title=title.strip())
    with database.connect() as conn:
        if done is not None:
            _set_child_done(conn, child, done)
        if position is not None:
            ids = [
                r["id"]
                for r in conn.execute(
                    "SELECT id FROM cards WHERE parent_id = ? ORDER BY position, id",
                    (parent_id,),
                )
            ]
            ids.remove(subtask_id)
            position = max(0, min(position, len(ids)))
            ids.insert(position, subtask_id)
            for i, cid in enumerate(ids):
                conn.execute("UPDATE cards SET position = ? WHERE id = ?", (i, cid))
        conn.execute(
            "UPDATE cards SET updated_at = datetime('now') WHERE id = ?",
            (parent_id,),
        )
    for s in list_subtasks(parent_id):
        if s["id"] == subtask_id:
            return s
    return None


def delete_subtask(subtask_id: int) -> bool:
    """Delete a child card. Top-level cards are not this function's to
    delete; use delete_card for those."""
    child = get_card(subtask_id)
    if not child or child["parent_id"] is None:
        return False
    with database.connect() as conn:
        conn.execute("DELETE FROM cards WHERE id = ?", (subtask_id,))
        _renumber_children(conn, child["parent_id"])
    return True


def subtask_progress(project_id: int) -> dict[int, tuple[int, int]]:
    """{card_id: (done, total)} over child cards, for every parent in the
    project. Done means the child sits in a done column."""
    with database.connect() as conn:
        return {
            r["parent_id"]: (r["done_n"] or 0, r["total_n"])
            for r in conn.execute(
                "SELECT cards.parent_id, SUM(columns.is_done) AS done_n,"
                " COUNT(*) AS total_n FROM cards"
                " JOIN columns ON columns.id = cards.column_id"
                " WHERE cards.project_id = ? AND cards.parent_id IS NOT NULL"
                " AND cards.archived = 0"
                " GROUP BY cards.parent_id",
                (project_id,),
            )
        }


def subtask_progress_for_card(card_id: int) -> tuple[int, int]:
    return subtask_progress_for_cards([card_id]).get(card_id, (0, 0))


def subtask_progress_for_cards(card_ids: list[int]) -> dict[int, tuple[int, int]]:
    """One query for many cards; the kiosk polls this every few seconds."""
    if not card_ids:
        return {}
    marks = ",".join("?" for _ in card_ids)
    with database.connect() as conn:
        return {
            r["parent_id"]: (r["d"] or 0, r["t"])
            for r in conn.execute(
                f"SELECT cards.parent_id, SUM(columns.is_done) AS d,"
                f" COUNT(*) AS t FROM cards"
                f" JOIN columns ON columns.id = cards.column_id"
                f" WHERE cards.parent_id IN ({marks}) AND cards.archived = 0"
                f" GROUP BY cards.parent_id",
                card_ids,
            )
        }


# ---- Today's Tasks ----
#
# Two kinds of list share one shape: the household list everyone sees
# (cards.today / cards.today_position, the original columns, untouched so
# older installs and the ESP32 payload keep working) and one personal
# list per user in the user_today table. owner=None means the shared
# list throughout.

def list_today(owner: int | None = None) -> list[dict]:
    """Today's tasks across all projects, with project name and done state.

    owner picks a user's personal list; None is the shared list."""
    select = (
        "SELECT cards.*, projects.name AS project_name,"
        " columns.name AS status, columns.is_done AS done"
        " FROM cards"
        " JOIN projects ON projects.id = cards.project_id"
        " JOIN columns ON columns.id = cards.column_id"
    )
    with database.connect() as conn:
        if owner is None:
            return _rows(
                conn.execute(
                    select + " WHERE cards.today = 1 AND cards.archived = 0"
                    " ORDER BY cards.today_position, cards.id"
                )
            )
        return _rows(
            conn.execute(
                select + " JOIN user_today ON user_today.card_id = cards.id"
                " WHERE user_today.user_id = ? AND cards.archived = 0"
                " ORDER BY user_today.position, cards.id",
                (owner,),
            )
        )


def set_today(
    card_id: int,
    today: bool,
    position: int | None = None,
    owner: int | None = None,
) -> dict | None:
    with database.connect() as conn:
        if owner is not None:
            exists = conn.execute(
                "SELECT 1 FROM cards WHERE id = ?", (card_id,)
            ).fetchone()
            if not exists:
                return None
            if today:
                ids = [
                    r["card_id"]
                    for r in conn.execute(
                        "SELECT card_id FROM user_today WHERE user_id = ?"
                        " ORDER BY position, card_id",
                        (owner,),
                    )
                ]
                if card_id in ids:
                    ids.remove(card_id)
                pos = len(ids) if position is None else max(0, min(position, len(ids)))
                ids.insert(pos, card_id)
                conn.execute(
                    "INSERT OR IGNORE INTO user_today (user_id, card_id, position)"
                    " VALUES (?, ?, 0)",
                    (owner, card_id),
                )
                for i, cid in enumerate(ids):
                    conn.execute(
                        "UPDATE user_today SET position = ?"
                        " WHERE user_id = ? AND card_id = ?",
                        (i, owner, cid),
                    )
            else:
                conn.execute(
                    "DELETE FROM user_today WHERE user_id = ? AND card_id = ?",
                    (owner, card_id),
                )
        elif today:
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


def toggle_done(card_id: int) -> dict | None:
    """Kiosk tap: send a card to the first done column, or back to the
    first working column when it is already done. Recurring cards
    respawn through the normal move logic."""
    card = get_card(card_id)
    if not card:
        return None
    with database.connect() as conn:
        current = conn.execute(
            "SELECT is_done FROM columns WHERE id = ?", (card["column_id"],)
        ).fetchone()
        target = conn.execute(
            "SELECT id FROM columns WHERE project_id = ? AND is_done = ?"
            " ORDER BY position, id LIMIT 1",
            (card["project_id"], 0 if current and current["is_done"] else 1),
        ).fetchone()
    if not target:
        return card
    with database.connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM cards WHERE column_id = ?", (target["id"],)
        ).fetchone()[0]
    return move_card(card_id, target["id"], count)


def clear_done_today(owner: int | None = None) -> int:
    """Drop finished cards off the Today list. Returns how many were cleared."""
    with database.connect() as conn:
        if owner is not None:
            cur = conn.execute(
                "DELETE FROM user_today WHERE user_id = ? AND card_id IN"
                " (SELECT id FROM cards WHERE column_id IN"
                "  (SELECT id FROM columns WHERE is_done = 1))",
                (owner,),
            )
            return cur.rowcount
        cur = conn.execute(
            "UPDATE cards SET today = 0, today_position = 0"
            " WHERE today = 1 AND column_id IN"
            " (SELECT id FROM columns WHERE is_done = 1)"
        )
        return cur.rowcount
