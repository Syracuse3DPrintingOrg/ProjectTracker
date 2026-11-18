"""Users and roles for a shared SQ instance.

Three global roles: admin runs the instance (settings, users, displays,
backups), member uses the boards fully, viewer looks but does not touch.
Boards and the Today list are shared by everyone; SQ is a household or
small-team tracker, not a tenant system.

With no users at all the app is open, same as before. Creating the
first user locks the instance and that user must be an admin. A legacy
single-password install is migrated automatically: the old password
becomes the "admin" account.
"""

from .. import config, database
from . import auth

ROLES = ("admin", "member", "viewer")


def _row(r) -> dict | None:
    if not r:
        return None
    user = dict(r)
    user.pop("password_hash", None)
    return user


def any_users() -> bool:
    with database.connect() as conn:
        return conn.execute("SELECT 1 FROM users LIMIT 1").fetchone() is not None


def list_users() -> list[dict]:
    with database.connect() as conn:
        return [
            _row(r)
            for r in conn.execute(
                "SELECT * FROM users ORDER BY username"
            ).fetchall()
        ]


def get_user(user_id: int) -> dict | None:
    with database.connect() as conn:
        return _row(
            conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        )


def _get_full(conn, user_id: int):
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def create_user(username: str, password: str, role: str) -> dict:
    username = username.strip().lower()
    if not username or len(username) > 40 or not username.replace("_", "").replace("-", "").replace(".", "").isalnum():
        raise ValueError("usernames are 1-40 letters, digits, dots, dashes, underscores")
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}")
    if len(password) < 4:
        raise ValueError("password must be at least 4 characters")
    if not any_users() and role != "admin":
        raise ValueError("the first user must be an admin")
    with database.connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if exists:
            raise ValueError("that username is taken")
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            (username, auth.hash_password(password), role),
        )
        return _row(_get_full(conn, cur.lastrowid))


def _admin_count(conn, excluding: int | None = None) -> int:
    sql = "SELECT COUNT(*) FROM users WHERE role = 'admin' AND disabled = 0"
    args: list = []
    if excluding is not None:
        sql += " AND id != ?"
        args.append(excluding)
    return conn.execute(sql, args).fetchone()[0]


def update_user(
    user_id: int,
    role: str | None = None,
    password: str | None = None,
    disabled: bool | None = None,
) -> dict | None:
    with database.connect() as conn:
        user = _get_full(conn, user_id)
        if not user:
            return None
        losing_admin = (
            user["role"] == "admin"
            and not user["disabled"]
            and ((role is not None and role != "admin") or disabled)
        )
        if losing_admin and _admin_count(conn, excluding=user_id) == 0:
            raise ValueError("SQ needs at least one active admin")
        if role is not None:
            if role not in ROLES:
                raise ValueError(f"role must be one of {ROLES}")
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
        if password:
            if len(password) < 4:
                raise ValueError("password must be at least 4 characters")
            conn.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (auth.hash_password(password), user_id),
            )
        if disabled is not None:
            conn.execute(
                "UPDATE users SET disabled = ? WHERE id = ?",
                (1 if disabled else 0, user_id),
            )
        return _row(_get_full(conn, user_id))


def delete_user(user_id: int) -> bool:
    with database.connect() as conn:
        user = _get_full(conn, user_id)
        if not user:
            return False
        if user["role"] == "admin" and _admin_count(conn, excluding=user_id) == 0:
            raise ValueError("SQ needs at least one active admin")
        # Their cards stay; the assignment does not dangle.
        conn.execute(
            "UPDATE cards SET assignee_id = NULL WHERE assignee_id = ?", (user_id,)
        )
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        return True


def verify_login(username: str, password: str) -> dict | None:
    """Full user row (hash included) on success, None otherwise."""
    with database.connect() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ? AND disabled = 0",
            (username.strip().lower(),),
        ).fetchone()
    if row and auth.check_password(password, row["password_hash"]):
        return dict(row)
    return None


def change_own_password(user_id: int, current: str, new: str) -> bool:
    with database.connect() as conn:
        user = _get_full(conn, user_id)
    if not user or not auth.check_password(current, user["password_hash"]):
        return False
    update_user(user_id, password=new)
    return True


def session_fingerprint(user_id: int) -> str | None:
    """A fragment of the stored hash; baked into session tokens so a
    password change logs that user out everywhere."""
    with database.connect() as conn:
        row = _get_full(conn, user_id)
    if not row or row["disabled"]:
        return None
    return row["password_hash"][-12:]


def get_by_sub(sub: str) -> dict | None:
    """The account linked to this Pocket ID subject, hash included."""
    if not sub:
        return None
    with database.connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE oidc_sub = ?", (sub,)).fetchone()
    return dict(row) if row else None


def link_sub(user_id: int, sub: str) -> None:
    with database.connect() as conn:
        other = conn.execute(
            "SELECT id FROM users WHERE oidc_sub = ? AND id != ?", (sub, user_id)
        ).fetchone()
        if other:
            raise ValueError("That Pocket ID account is already linked to another SQ user.")
        conn.execute("UPDATE users SET oidc_sub = ? WHERE id = ?", (sub, user_id))


def unlink_sub(user_id: int) -> None:
    with database.connect() as conn:
        conn.execute("UPDATE users SET oidc_sub = NULL WHERE id = ?", (user_id,))


def sync_role(user_id: int, groups: list[str] | None, admin_group: str) -> None:
    """Pocket ID decides who is an admin: people in the admin group are
    admins here, and an admin who left it drops to member. With no groups
    claim at all nothing changes. The last active admin is never demoted."""
    if groups is None:
        return
    user = get_user(user_id)
    if not user:
        return
    if admin_group in groups:
        if user["role"] != "admin":
            update_user(user_id, role="admin")
    elif user["role"] == "admin":
        try:
            update_user(user_id, role="member")
        except ValueError:
            pass


def migrate_legacy_password() -> None:
    """Turn a pre-multi-user install's single password into the admin
    account, once, so existing logins keep working."""
    if any_users():
        return
    legacy = config.load_settings().get("password_hash", "")
    if not legacy:
        return
    with database.connect() as conn:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
            ("admin", legacy, "admin"),
        )
