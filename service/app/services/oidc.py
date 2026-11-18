"""Sign in with Pocket ID (or any OpenID Connect provider).

SQ is a confidential client using the authorization code flow with PKCE.
The provider proves who is at the browser; SQ then finds the local account
linked to that person's subject (``sub``), never their email. Accounts get
linked from the Account page while signed in the old way.

The ID token is checked in full (signature against the provider's published
keys, issuer, audience, expiry, nonce) even though it arrives straight from
the token endpoint, so a mistake in transport trust alone cannot sign
anyone in. The signature check is plain RS256 done with the standard
library, which keeps the image free of a crypto dependency.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from urllib.parse import quote, urlencode, urlparse

import httpx

from .. import config

CALLBACK_PATH = "/auth/oidc/callback"
STATE_COOKIE = "sq_oidc"
SCOPES = "openid profile email groups"
ADMIN_GROUP = "admins"
CACHE_SECONDS = 3600
LEEWAY_SECONDS = 60
STATE_SECONDS = 600
MAX_PENDING = 500

# Tests swap in an httpx.MockTransport here; None means the real network.
transport: httpx.BaseTransport | None = None


class OidcError(Exception):
    """The sign-in could not be completed. The message is safe to show."""


# Settings -------------------------------------------------------------------


def _s(settings: dict | None) -> dict:
    return settings if settings is not None else config.load_settings()


def issuer(settings: dict | None = None) -> str:
    return (_s(settings).get("oidc_issuer") or "").strip().rstrip("/")


def public_origin(settings: dict | None = None) -> str:
    return (_s(settings).get("public_url") or "").strip().rstrip("/")


def client_secret(settings: dict | None = None) -> str:
    """From the environment or Settings first, then data/oidc_client_secret."""
    value = (_s(settings).get("oidc_client_secret") or "").strip()
    if value:
        return value
    try:
        return (config.DATA_DIR / "oidc_client_secret").read_text().strip()
    except OSError:
        return ""


def configured(settings: dict | None = None) -> bool:
    s = _s(settings)
    return bool(
        issuer(s).startswith("https://")
        and (s.get("oidc_client_id") or "").strip()
        and client_secret(s)
        and public_origin(s).startswith(("https://", "http://"))
    )


def only(settings: dict | None = None) -> bool:
    """Whether Pocket ID is the one way in for people (recovery aside)."""
    s = _s(settings)
    return bool(s.get("oidc_only")) and configured(s)


def redirect_uri(settings: dict | None = None) -> str:
    return public_origin(settings) + CALLBACK_PATH


def on_public_host(request_host: str | None, settings: dict | None = None) -> bool:
    """The callback comes back to the public name, so a trip started on
    another address would lose its state cookie. Only offer it there."""
    want = urlparse(public_origin(settings)).netloc.lower()
    return bool(want) and (request_host or "").lower() == want


def cookie_secure(settings: dict | None = None) -> bool:
    return public_origin(settings).startswith("https://")


# Provider documents ---------------------------------------------------------

_lock = threading.Lock()
_cache: dict[str, tuple[float, dict]] = {}


def _client() -> httpx.Client:
    return httpx.Client(transport=transport, timeout=10, follow_redirects=False)


def _fetch(url: str) -> dict:
    """GET a provider document, three tries: tunnels drop the odd connection."""
    last: Exception | None = None
    for _ in range(3):
        try:
            with _client() as c:
                r = c.get(url)
            if r.status_code == 200:
                doc = r.json()
                if isinstance(doc, dict):
                    return doc
            last = OidcError(f"status {r.status_code}")
        except (httpx.HTTPError, ValueError) as exc:
            last = exc
    raise OidcError("Pocket ID did not answer. Try again in a moment.") from last


def _cached(key: str, url: str, fresh: bool = False) -> dict:
    with _lock:
        hit = _cache.get(key)
        if hit and not fresh and hit[0] > time.time():
            return hit[1]
    doc = _fetch(url)
    with _lock:
        _cache[key] = (time.time() + CACHE_SECONDS, doc)
    return doc


def discovery(settings: dict | None = None) -> dict:
    want = issuer(settings)
    doc = _cached("discovery:" + want, want + "/.well-known/openid-configuration")
    if str(doc.get("issuer", "")).rstrip("/") != want:
        raise OidcError("Pocket ID is not the one SQ expects.")
    for field in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        if not str(doc.get(field, "")).startswith("https://"):
            raise OidcError("Pocket ID is not the one SQ expects.")
    return doc


def reset() -> None:
    with _lock:
        _cache.clear()
        _pending.clear()


# Trips in flight --------------------------------------------------------------

_pending: dict[str, dict] = {}


def _remember(**data) -> str:
    key = secrets.token_urlsafe(24)
    now = time.time()
    with _lock:
        for k in [k for k, v in _pending.items() if v["expires"] < now]:
            del _pending[k]
        if len(_pending) >= MAX_PENDING:
            raise OidcError("Too many sign-ins at once. Try again in a minute.")
        _pending[key] = {**data, "expires": now + STATE_SECONDS}
    return key


def take(state: str | None, cookie: str | None) -> dict:
    """The trip this callback belongs to, used up. The state in the URL
    and the one in the browser's cookie must match."""
    if not state or not cookie or not hmac.compare_digest(state, cookie):
        raise OidcError("That sign-in expired or came from somewhere else. Try again.")
    with _lock:
        trip = _pending.pop(state, None)
    if not trip or trip["expires"] < time.time():
        raise OidcError("That sign-in expired or came from somewhere else. Try again.")
    return trip


# The flow ---------------------------------------------------------------------


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def begin(next_url: str, link_user_id: int | None = None) -> tuple[str, str]:
    """Start a trip. Returns where to send the browser and the state value,
    which the browser keeps in a cookie until it comes back."""
    s = config.load_settings()
    if not configured(s):
        raise OidcError("Pocket ID sign-in is not set up.")
    doc = discovery(s)
    verifier = _b64url(secrets.token_bytes(48))
    nonce = _b64url(secrets.token_bytes(24))
    state = _remember(verifier=verifier, nonce=nonce, next=next_url, link=link_user_id)
    query = urlencode({
        "response_type": "code",
        "client_id": s["oidc_client_id"].strip(),
        "redirect_uri": redirect_uri(s),
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64url(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
    })
    return f"{doc['authorization_endpoint']}?{query}", state


def finish(code: str, trip: dict, iss: str | None = None) -> dict:
    """Trade the code for an ID token and return its checked claims."""
    s = config.load_settings()
    want = issuer(s)
    # Pocket ID names itself on the callback too (RFC 9207).
    if iss is not None and iss.rstrip("/") != want:
        raise OidcError("That sign-in came from a different provider.")
    doc = discovery(s)
    client_id = s["oidc_client_id"].strip()
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(s),
        "code_verifier": trip["verifier"],
    }
    try:
        with _client() as c:
            r = c.post(
                doc["token_endpoint"],
                data=form,
                auth=(quote(client_id, safe=""), quote(client_secret(s), safe="")),
            )
        body = r.json() if r.status_code == 200 else {}
    except (httpx.HTTPError, ValueError) as exc:
        raise OidcError("Pocket ID did not answer. Try again in a moment.") from exc
    token = body.get("id_token") if isinstance(body, dict) else None
    if not isinstance(token, str):
        raise OidcError("Pocket ID turned that sign-in down. Try again.")
    claims = verify_id_token(token, trip["nonce"], s)
    if not str(claims.get("sub") or ""):
        raise OidcError("That sign-in could not be checked. Try again.")
    return claims


# ID token checks -------------------------------------------------------------

# DER prefix of a SHA-256 DigestInfo (RFC 8017, section 9.2 note 1).
_SHA256_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def _rs256_valid(n: int, e: int, signed: bytes, signature: bytes) -> bool:
    """RSASSA-PKCS1-v1_5 with SHA-256: rebuild the whole expected block and
    compare it, rather than parsing what the signature decrypts to."""
    k = (n.bit_length() + 7) // 8
    if k < 256 or len(signature) != k:  # 2048-bit keys or better
        return False
    s = int.from_bytes(signature, "big")
    if s >= n:
        return False
    block = pow(s, e, n).to_bytes(k, "big")
    t = _SHA256_INFO + hashlib.sha256(signed).digest()
    expected = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    return hmac.compare_digest(block, expected)


def _keys(kid: str | None, fresh: bool) -> list[tuple[int, int]]:
    uri = discovery()["jwks_uri"]
    found = []
    for jwk in _cached("jwks:" + uri, uri, fresh=fresh).get("keys", []):
        if jwk.get("kty") != "RSA" or jwk.get("use", "sig") != "sig":
            continue
        if kid is None or jwk.get("kid") == kid:
            try:
                n = int.from_bytes(_unb64url(jwk["n"]), "big")
                e = int.from_bytes(_unb64url(jwk["e"]), "big")
            except (KeyError, ValueError, TypeError):
                continue
            found.append((n, e))
    return found


def verify_id_token(token: str, nonce: str, settings: dict | None = None) -> dict:
    s = _s(settings)
    bad = OidcError("That sign-in could not be checked. Try again.")
    try:
        head_b64, body_b64, sig_b64 = token.split(".")
        head = json.loads(_unb64url(head_b64))
        claims = json.loads(_unb64url(body_b64))
        signature = _unb64url(sig_b64)
    except (ValueError, TypeError) as exc:
        raise bad from exc
    # One algorithm, named here, never taken from the token.
    if not isinstance(head, dict) or head.get("alg") != "RS256" or not isinstance(claims, dict):
        raise bad
    signed = f"{head_b64}.{body_b64}".encode()
    kid = head.get("kid")
    # The second pass refetches, for a key the provider rotated in since.
    if not any(
        _rs256_valid(n, e, signed, signature)
        for fresh in (False, True)
        for n, e in _keys(kid, fresh)
    ):
        raise bad
    client_id = (s.get("oidc_client_id") or "").strip()
    audience = claims.get("aud")
    audiences = audience if isinstance(audience, list) else [audience]
    try:
        expires = float(claims.get("exp", 0))
        issued = float(claims.get("iat", 0))
    except (TypeError, ValueError) as exc:
        raise bad from exc
    now = time.time()
    if (
        str(claims.get("iss", "")).rstrip("/") != issuer(s)
        or client_id not in audiences
        or ("azp" in claims and claims.get("azp") != client_id)
        or expires < now - LEEWAY_SECONDS
        or issued > now + LEEWAY_SECONDS
        or not hmac.compare_digest(str(claims.get("nonce", "")).encode(), nonce.encode())
    ):
        raise bad
    return claims


def groups(claims: dict) -> list[str] | None:
    """The group names Pocket ID sent, or None when it sent no groups claim."""
    value = claims.get("groups")
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(g) for g in value]
    return []
