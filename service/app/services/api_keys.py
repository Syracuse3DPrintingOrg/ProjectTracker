"""API keys for headless callers: Home Assistant, scripts, cron jobs.

A key is minted once by an admin with a name and a role (member to act,
viewer to read; never admin, headless callers do not manage the
instance). Only a SHA-256 hash is stored; the plaintext is shown exactly
once at creation. Callers send it as an X-API-Key header and flow
through the same role checks as a logged-in user.
"""

import hashlib
import secrets

from .. import database

KEY_ROLES = ("member", "viewer")
_PREFIX = "sq_"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_key(name: str, role: str) -> dict:
    """Returns the key record plus the plaintext token, shown only now."""
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("give the key a short name")
    if role not in KEY_ROLES:
        raise ValueError(f"key role must be one of {KEY_ROLES}")
    token = _PREFIX + secrets.token_urlsafe(24)
    with database.connect() as conn:
        cur = conn.execute(
            "INSERT INTO api_keys (name, key_hash, role) VALUES (?, ?, ?)",
            (name, _hash(token), role),
        )
        row = conn.execute(
            "SELECT id, name, role, created_at, last_used FROM api_keys WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
    return {**dict(row), "token": token}


def list_keys() -> list[dict]:
    with database.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id, name, role, created_at, last_used FROM api_keys"
                " ORDER BY name"
            )
        ]


def delete_key(key_id: int) -> bool:
    with database.connect() as conn:
        cur = conn.execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        return cur.rowcount > 0


def verify(token: str | None) -> dict | None:
    """The pseudo-user for a valid key: {id: None, username, role}."""
    if not token:
        return None
    with database.connect() as conn:
        row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ?", (_hash(token),)
        ).fetchone()
        if not row:
            return None
        conn.execute(
            "UPDATE api_keys SET last_used = datetime('now') WHERE id = ?",
            (row["id"],),
        )
    return {"id": None, "username": f"key:{row['name']}", "role": row["role"]}
