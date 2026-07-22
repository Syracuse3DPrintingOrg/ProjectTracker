"""Card activity: comments and the automatic trail.

One table holds both. Comments are kind "comment" with the text the
user wrote; everything else (created, moved, done, assigned, attached)
is written by the routers as things happen. The log is local history,
deliberately excluded from export/import.
"""

from .. import database

KINDS = ("comment", "created", "moved", "assigned", "attached", "respawned")

FEED_LIMIT = 100


def log(card_id: int, actor: str, kind: str, text: str = "") -> None:
    if kind not in KINDS:
        return
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO card_events (card_id, actor, kind, text) VALUES (?, ?, ?, ?)",
            (card_id, (actor or "someone")[:80], kind, text[:2000]),
        )


def list_for_card(card_id: int) -> list[dict]:
    """Oldest first, capped; the dialog shows the recent tail."""
    with database.connect() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM card_events WHERE card_id = ?"
                " ORDER BY id DESC LIMIT ?",
                (card_id, FEED_LIMIT),
            )
        ]
    rows.reverse()
    return rows
