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


def hash_password(password: str) -> str:
    salt = secrets.token_hex(8)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"


def check_password(password: str, stored: str) -> bool:
    if "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    candidate = hashlib.sha256((salt + password).encode()).hexdigest()
    return hmac.compare_digest(candidate, digest)


def _secret_key() -> str:
    """Persist a random signing key under the data dir on first use."""
    env = os.environ.get("TRACKER_SECRET_KEY")
    if env:
        return env
    path = config.DATA_DIR / "secret_key"
    try:
        return path.read_text().strip()
    except OSError:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        path.write_text(key)
        return key


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_secret_key(), salt="tracker-session")


def make_session_token() -> str:
    return _serializer().dumps({"user": "owner"})


def valid_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        _serializer().loads(token, max_age=SESSION_MAX_AGE)
        return True
    except BadSignature:
        return False


def auth_required(settings: dict | None = None) -> bool:
    s = settings or config.load_settings()
    return bool(s.get("password_hash"))


def valid_display_token(token: str | None, settings: dict | None = None) -> bool:
    s = settings or config.load_settings()
    expected = s.get("display_token", "")
    return bool(expected) and bool(token) and hmac.compare_digest(token, expected)
