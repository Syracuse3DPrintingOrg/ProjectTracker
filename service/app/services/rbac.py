"""Role checks, one table, no surprises.

Reads are open to every signed-in role. Writes need member or better.
Administration (settings, users, displays, backups, connector cleanup)
needs admin. Device endpoints (display JSON, connector reports) carry
their own tokens and never reach these checks.
"""

READ_METHODS = {"GET", "HEAD", "OPTIONS"}

# Path prefixes whose WRITES are admin-only.
ADMIN_WRITE_PREFIXES = (
    "/api/settings",
    "/api/users",
    "/api/keys",
    "/api/import",
    "/api/displays",
    "/api/connectors",
)

# Reads that are still admin-only (a full backup is the whole database,
# and the user and key lists are the admin's business).
ADMIN_READ_PATHS = ("/api/export", "/api/users", "/api/keys")

# Writes any signed-in user may make (self-service).
SELF_SERVICE_PREFIXES = ("/api/account",)


import re

# Display TV actions (show, hide, sleep, status) are operational, not
# configuration: any member (or member API key, e.g. a Home Assistant
# automation) may pop a display up.
_TV_ACTION = re.compile(r"^/api/displays/[^/]+/tv/[a-z]+$")


def allowed(role: str, method: str, path: str) -> bool:
    if role == "admin":
        return True
    if method in READ_METHODS:
        return not path.startswith(ADMIN_READ_PATHS)
    if path.startswith(SELF_SERVICE_PREFIXES):
        return True
    if role == "member":
        if _TV_ACTION.match(path):
            return True
        return not path.startswith(ADMIN_WRITE_PREFIXES)
    return False  # viewers do not write


def deny_message(role: str, method: str, path: str) -> str:
    if role == "viewer":
        return "viewers can look but not touch"
    return "that needs an admin"
