"""Optional single-user login.

With no password set the app is open (fine on a trusted LAN). Setting a
password on the Settings page (or TRACKER_PASSWORD_HASH in the
environment) turns on a login page backed by a signed session cookie.
Display endpoints can instead present the display token, so a wall screen
never needs a login flow.
"""

import hashlib
import hmac
import os
import secrets

from itsdangerous import BadSignature, URLSafeTimedSerializer

from .. import config

SESSION_COOKIE = "tracker_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


_PBKDF2_ROUNDS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS
    ).hex()
    return f"pbkdf2${salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    if stored.startswith("pbkdf2$"):
        try:
            _, salt, digest = stored.split("$", 2)
        except ValueError:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS
        ).hex()
        return hmac.compare_digest(candidate, digest)
    # Legacy format from before 0.12: single-round salted SHA-256. Still
    # verifiable so nobody gets locked out; new hashes use PBKDF2.
    if "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    candidate = hashlib.sha256((salt + password).encode()).hexdigest()
    return hmac.compare_digest(candidate, digest)


_secret_cache: dict[str, str] = {}


def _secret_key() -> str:
    """Persist a random signing key under the data dir on first use.

    Cached per data dir so session checks stop re-reading the file on
    every request."""
    env = os.environ.get("TRACKER_SECRET_KEY")
    if env:
        return env
    path = config.DATA_DIR / "secret_key"
    cached = _secret_cache.get(str(path))
    if cached:
        return cached
    try:
        key = path.read_text().strip()
    except OSError:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        path.write_text(key)
    _secret_cache[str(path)] = key
    return key


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret_key(), salt="tracker-session")


def make_session_token(user_id: int, fingerprint: str) -> str:
    return _serializer().dumps({"uid": user_id, "fp": fingerprint})


def session_user_id(token: str | None) -> int | None:
    """The logged-in user's id, or None. The token carries a fragment of
    the password hash, so changing a password invalidates old sessions."""
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=SESSION_MAX_AGE)
    except BadSignature:
        return None
    if not isinstance(data, dict) or "uid" not in data:
        return None
    from . import users

    fingerprint = users.session_fingerprint(data["uid"])
    if fingerprint is None or data.get("fp") != fingerprint:
        return None
    return data["uid"]


def auth_required(settings: dict | None = None) -> bool:
    """The instance is locked once any user exists."""
    from . import users

    return users.any_users()


def valid_display_token(token: str | None, settings: dict | None = None) -> bool:
    s = settings or config.load_settings()
    expected = s.get("display_token", "")
    return bool(expected) and bool(token) and hmac.compare_digest(token, expected)
