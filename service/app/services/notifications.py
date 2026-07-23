"""Per-user notifications: an inbox under the nav bell, plus optional push.

Rows land in the notifications table and the bell shows the unread count.
A user who sets a webhook URL on their account page also gets each
notification pushed: SQ POSTs the notification text as the request body
with an X-Title header, which ntfy accepts directly and generic webhook
receivers can parse. The one exception is a URL whose last path segment
contains "hook" (a Slack-style receiver): that gets JSON
{"text": ..., "url": ...} instead. Pushes use a 3 second timeout and
failures are swallowed; the inbox row is already written and a dead
webhook must never break the request that triggered it.
"""

import re
from urllib.parse import urlsplit

import httpx

from .. import database

PUSH_TIMEOUT = 3.0
PUSH_TITLE = "SQ"

_MENTION = re.compile(r"@([A-Za-z0-9_.-]{1,40})")


def notify(user_id: int, text: str, url: str = "") -> None:
    """Store a notification and, if the user set a webhook, push it."""
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO notifications (user_id, text, url) VALUES (?, ?, ?)",
            (user_id, text[:500], url[:500]),
        )
        row = conn.execute(
            "SELECT webhook_url FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    hook = row["webhook_url"] if row else ""
    if hook:
        try:
            _push(hook, text[:500], url)
        except Exception:
            pass  # push is best effort; the inbox row already exists


def _push(hook: str, text: str, url: str) -> None:
    last_segment = urlsplit(hook).path.rsplit("/", 1)[-1].lower()
    if "hook" in last_segment:
        httpx.post(hook, json={"text": text, "url": url}, timeout=PUSH_TIMEOUT)
    else:
        httpx.post(
            hook,
            content=text.encode("utf-8"),
            headers={"X-Title": PUSH_TITLE},
            timeout=PUSH_TIMEOUT,
        )


def list_for_user(
    user_id: int, unread_only: bool = False, limit: int = 50
) -> list[dict]:
    """Newest first, capped."""
    sql = "SELECT * FROM notifications WHERE user_id = ?"
    if unread_only:
        sql += " AND read = 0"
    sql += " ORDER BY id DESC LIMIT ?"
    with database.connect() as conn:
        return [dict(r) for r in conn.execute(sql, (user_id, limit))]


def unread_count(user_id: int) -> int:
    with database.connect() as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id = ? AND read = 0",
            (user_id,),
        ).fetchone()[0]


def mark_read(user_id: int, ids: list[int] | None = None) -> int:
    """Mark the given notifications read, or all of them when ids is None.

    Scoped to user_id, so nobody can clear anyone else's inbox."""
    with database.connect() as conn:
        if ids is not None:
            if not ids:
                return 0
            marks = ",".join("?" for _ in ids)
            cur = conn.execute(
                "UPDATE notifications SET read = 1"
                f" WHERE user_id = ? AND read = 0 AND id IN ({marks})",
                (user_id, *ids),
            )
        else:
            cur = conn.execute(
                "UPDATE notifications SET read = 1 WHERE user_id = ? AND read = 0",
                (user_id,),
            )
        return cur.rowcount


def set_webhook(user_id: int, url: str) -> None:
    with database.connect() as conn:
        conn.execute(
            "UPDATE users SET webhook_url = ? WHERE id = ?", (url, user_id)
        )


def mention_targets(text: str) -> list[int]:
    """User ids for every @username in the text, in order, no duplicates.

    Matching is case-insensitive against enabled users only. A trailing
    dot or dash sticks to the token (both are legal in usernames), so a
    token that misses gets one retry with that punctuation stripped.
    The caller decides about self-mentions; this helper does not know
    who is talking.
    """
    tokens = _MENTION.findall(text or "")
    if not tokens:
        return []
    with database.connect() as conn:
        rows = conn.execute(
            "SELECT id, username FROM users WHERE disabled = 0"
        ).fetchall()
    by_name = {r["username"]: r["id"] for r in rows}
    ids: list[int] = []
    for token in tokens:
        token = token.lower()
        for candidate in (token, token.rstrip(".-")):
            uid = by_name.get(candidate)
            if uid is not None:
                if uid not in ids:
                    ids.append(uid)
                break
    return ids
