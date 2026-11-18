"""Sign in with Pocket ID, against a fake provider.

The provider is an httpx.MockTransport on the oidc module, with a real
RSA key (a throwaway one, below) signing real RS256 ID tokens."""

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app import config
from app.services import api_keys, oidc, users

ISSUER = "https://id.example.test"
CLIENT_ID = "sq-client"
SECRET = "sq-secret"
DAN_SUB = "8ca457d2-sub"

# Throwaway 2048-bit test key, made for this file and used nowhere else.
N = int(
    "c42cfeb594bb869ced528ac443b2b02ee2b625394d278f42f4ccae27a7cda4262282acfbc8dd5200144c25079691ea0d0facc1fa4c7282234b6db61210561827f9d53e7573a5161dce7fde479b163c2224dfc1afaf68b7dee398ecfb9f9f688da60edd02e3cfb53a6fea4bad0340082174c4e7ae715daf5cebff8ac15292c0a5f5a3bdd45e10bc9b38e24019d982cabeb8b8c9f54b553735270d7595ef8ca5e3ebc0f4b1807cbc1cda5452f1b4be4ad21430bd6d4e6265538e301aadce0131093acd6a6973602f80459206a2cb0b9994a46e708eaa9a1533cdaff0d8d8d9538788650cb8d9aef54a2c041a35a1ea8de386d1157c3aa8530f5402c76da10a8fa3",
    16,
)
D = int(
    "137d60e4cb5d0217af2047370e7ebf303947dd54df0c721835d7ebe976ab60868561342c639d515b3ea8fdf8ce05bb1a0717a3c1e93c6b1f748bf6cdbe9fbf10a1aa84e508533b6a44acc1799db7cccb9b9c3b52e7fb60611d7d80f5d2baf49936093dfdde82314018044ff6655f442f86b95547286e2550f7055154b98e68e32787f453b0bba8d47d2d794d7e6471ba00339252c82eceab1e1822027c5686a53931b38388fa4f16aec9b3993f52835aa1438861b3c59c0702600f3d721a890a253f96dadf3ea970ca190aabbf6ae53497dfa5996eec7b790fda0c95980b3d6c3494385ae826f315127d11783c99f72093597bb485e73d5a831beef9df189239",
    16,
)
E = 65537
_INFO = bytes.fromhex("3031300d060960864801650304020105000420")


def b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def sign(claims: dict, kid: str = "k1", alg: str = "RS256", n: int = N, d: int = D) -> str:
    head = b64(json.dumps({"alg": alg, "kid": kid, "typ": "JWT"}).encode())
    body = b64(json.dumps(claims).encode())
    k = (n.bit_length() + 7) // 8
    t = _INFO + hashlib.sha256(f"{head}.{body}".encode()).digest()
    block = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    sig = pow(int.from_bytes(block, "big"), d, n).to_bytes(k, "big")
    return f"{head}.{body}.{b64(sig)}"


class FakeProvider:
    def __init__(self):
        self.claims: dict = {}
        self.nonce = ""
        self.token_override = None
        self.token_auth = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == ISSUER + "/.well-known/openid-configuration":
            return httpx.Response(200, json={
                "issuer": ISSUER,
                "authorization_endpoint": ISSUER + "/authorize",
                "token_endpoint": ISSUER + "/api/oidc/token",
                "jwks_uri": ISSUER + "/.well-known/jwks.json",
            })
        if url == ISSUER + "/.well-known/jwks.json":
            nb = N.to_bytes(256, "big")
            return httpx.Response(200, json={"keys": [
                {"kty": "RSA", "use": "sig", "kid": "k1", "n": b64(nb), "e": b64(E.to_bytes(3, "big"))}
            ]})
        if url == ISSUER + "/api/oidc/token":
            self.token_auth = request.headers.get("authorization")
            form = parse_qs(request.content.decode())
            if form.get("code") != ["good-code"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            if self.token_override is not None:
                return httpx.Response(200, json={"id_token": self.token_override})
            now = int(time.time())
            claims = {
                "iss": ISSUER, "aud": CLIENT_ID, "sub": DAN_SUB, "exp": now + 300,
                "iat": now, "nonce": self.nonce, "groups": ["admins"],
                **self.claims,
            }
            claims = {k: v for k, v in claims.items() if v is not None}
            return httpx.Response(200, json={"id_token": sign(claims)})
        return httpx.Response(404)


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(oidc, "transport", httpx.MockTransport(fake.handler))
    oidc.reset()
    config.save_settings({
        "public_url": "http://testserver",
        "oidc_issuer": ISSUER,
        "oidc_client_id": CLIENT_ID,
        "oidc_client_secret": SECRET,
    })
    yield fake
    oidc.reset()


def password_login(client, username, password, path="/login"):
    return client.post(path, data={"username": username, "password": password, "next": "/"},
                       follow_redirects=False)


def trip(client, provider, start="/auth/oidc/start", code="good-code", iss=ISSUER):
    """Go out to the fake provider and back; returns the callback response."""
    r = client.get(start, follow_redirects=False)
    assert r.status_code == 303, r.text
    query = parse_qs(urlparse(r.headers["location"]).query)
    assert query["code_challenge_method"] == ["S256"]
    assert "groups" in query["scope"][0].split()
    assert query["redirect_uri"] == ["http://testserver/auth/oidc/callback"]
    provider.nonce = query["nonce"][0]
    params = {"code": code, "state": query["state"][0]}
    if iss is not None:
        params["iss"] = iss
    return client.get("/auth/oidc/callback", params=params, follow_redirects=False)


def link_dan(client, provider):
    dan = users.create_user("dan", "hunter2", "admin")
    assert password_login(client, "dan", "hunter2").status_code == 303
    r = trip(client, provider, "/auth/oidc/start?link=1")
    assert r.status_code == 303 and r.headers["location"] == "/account?linked=1"
    client.get("/logout")
    return dan


def test_link_then_sign_in(client, provider):
    dan = link_dan(client, provider)
    assert users.get_user(dan["id"])["oidc_sub"] == DAN_SUB
    assert client.get("/api/projects").status_code == 401
    r = trip(client, provider, "/auth/oidc/start?next=/today")
    assert r.status_code == 303 and r.headers["location"] == "/today"
    assert client.get("/api/projects").status_code == 200
    # Token endpoint got client_secret_basic.
    assert provider.token_auth.startswith("Basic ")


def test_login_page_offers_pocket_id(client, provider):
    users.create_user("dan", "hunter2", "admin")
    page = client.get("/login").text
    assert "Sign in with Pocket ID" in page and 'name="password"' in page


def test_login_page_elsewhere_points_at_public_name(client, provider):
    config.save_settings({"public_url": "https://sq.example.test"})
    users.create_user("dan", "hunter2", "admin")
    page = client.get("/login").text
    assert "Sign in with Pocket ID" not in page
    assert "https://sq.example.test/login" in page


def test_unlinked_subject_is_refused(client, provider):
    users.create_user("dan", "hunter2", "admin")
    r = trip(client, provider)
    assert r.status_code == 403
    assert client.get("/api/projects").status_code == 401


def test_disabled_user_is_refused(client, provider):
    dan = link_dan(client, provider)
    users.create_user("other", "hunter2", "admin")
    users.update_user(dan["id"], disabled=True)
    assert trip(client, provider).status_code == 403


@pytest.mark.parametrize("change", [
    {"nonce": "wrong"},
    {"aud": "someone-else"},
    {"iss": "https://evil.example.test"},
    {"exp": 1000},
    {"iat": int(time.time()) + 3600},
    {"azp": "someone-else"},
])
def test_bad_tokens_are_refused(client, provider, change):
    link_dan(client, provider)
    provider.claims = change
    r = trip(client, provider)
    assert r.status_code == 400
    assert client.get("/api/projects").status_code == 401


def test_forged_signature_is_refused(client, provider):
    link_dan(client, provider)
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": DAN_SUB, "exp": now + 300, "iat": now}
    good = sign({**claims, "nonce": "x"})
    head, body, sig = good.split(".")
    # Same signature on a different body.
    other = b64(json.dumps({**claims, "nonce": "x", "sub": "someone"}).encode())
    provider.token_override = f"{head}.{other}.{sig}"
    assert trip(client, provider).status_code == 400
    # alg none, unsigned.
    none_head = b64(json.dumps({"alg": "none"}).encode())
    provider.token_override = f"{none_head}.{body}."
    assert trip(client, provider).status_code == 400


def test_wrong_code_and_wrong_iss_are_refused(client, provider):
    link_dan(client, provider)
    assert trip(client, provider, code="bad-code").status_code == 400
    assert trip(client, provider, iss="https://evil.example.test").status_code == 400


def test_state_must_match_cookie(client, provider):
    link_dan(client, provider)
    r = client.get("/auth/oidc/start", follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    client.cookies.clear()
    r = client.get("/auth/oidc/callback", params={"code": "good-code", "state": state},
                   follow_redirects=False)
    assert r.status_code == 400


def test_state_is_single_use(client, provider):
    link_dan(client, provider)
    r = client.get("/auth/oidc/start", follow_redirects=False)
    query = parse_qs(urlparse(r.headers["location"]).query)
    provider.nonce = query["nonce"][0]
    params = {"code": "good-code", "state": query["state"][0]}
    assert client.get("/auth/oidc/callback", params=params, follow_redirects=False).status_code == 303
    client.cookies.set(oidc.STATE_COOKIE, query["state"][0], path="/auth/oidc")
    assert client.get("/auth/oidc/callback", params=params, follow_redirects=False).status_code == 400


def test_subject_links_to_one_account_only(client, provider):
    link_dan(client, provider)
    users.create_user("kid", "letmein", "member")
    assert password_login(client, "kid", "letmein").status_code == 303
    assert trip(client, provider, "/auth/oidc/start?link=1").status_code == 409


def test_admins_group_maps_to_admin(client, provider):
    users.create_user("dan", "hunter2", "admin")
    kid = users.create_user("kid", "letmein", "member")
    assert password_login(client, "kid", "letmein").status_code == 303
    trip(client, provider, "/auth/oidc/start?link=1")
    assert users.get_user(kid["id"])["role"] == "admin"
    # Leaving the group in Pocket ID drops them back to member.
    client.get("/logout")
    provider.claims = {"groups": ["family"]}
    assert trip(client, provider).status_code == 303
    assert users.get_user(kid["id"])["role"] == "member"
    # No groups claim at all changes nothing.
    provider.claims = {"groups": None}
    users.update_user(kid["id"], role="viewer")
    assert trip(client, provider).status_code == 303
    assert users.get_user(kid["id"])["role"] == "viewer"


def test_last_admin_is_never_demoted(client, provider):
    dan = link_dan(client, provider)
    provider.claims = {"groups": []}
    assert trip(client, provider).status_code == 303
    assert users.get_user(dan["id"])["role"] == "admin"


def test_pocket_id_only_switch(client, provider):
    users.create_user("dan", "hunter2", "admin")
    users.create_user("kid", "letmein", "member")
    key = api_keys.create_key("ha", "member")["token"]
    config.save_settings({"display_token": "wall"})
    assert password_login(client, "dan", "hunter2").status_code == 303
    # Not linked yet: the switch refuses.
    r = client.post("/api/settings", json={"oidc_only": True})
    assert r.status_code == 422
    trip(client, provider, "/auth/oidc/start?link=1")
    assert client.post("/api/settings", json={"oidc_only": True}).status_code == 200
    assert oidc.only()

    # The password session that turned it on stops working.
    assert client.get("/api/projects").status_code == 401
    page = client.get("/login").text
    assert 'name="password"' not in page and "recovery" in page
    assert password_login(client, "dan", "hunter2").status_code == 403
    assert client.get("/api/projects").status_code == 401

    # Pocket ID still works.
    assert trip(client, provider).status_code == 303
    assert client.get("/api/projects").status_code == 200
    client.get("/logout")

    # Recovery: admins only.
    assert password_login(client, "kid", "letmein", "/login/recovery").status_code == 401
    assert password_login(client, "dan", "hunter2", "/login/recovery").status_code == 303
    assert client.get("/api/projects").status_code == 200
    client.get("/logout")

    # Machines are not people: display token and API keys carry on.
    assert client.get("/api/display?token=wall").status_code == 200
    assert client.get("/api/projects", headers={"x-api-key": key}).status_code == 200

    # Switching it off brings passwords back.
    config.save_settings({"oidc_only": False})
    assert password_login(client, "kid", "letmein").status_code == 303


def test_unlink(client, provider):
    dan = link_dan(client, provider)
    assert password_login(client, "dan", "hunter2").status_code == 303
    assert client.post("/api/account/oidc/unlink").status_code == 200
    assert users.get_user(dan["id"])["oidc_sub"] is None


def test_not_configured_has_no_button(client):
    users.create_user("dan", "hunter2", "admin")
    assert "Pocket ID" not in client.get("/login").text
    assert client.get("/auth/oidc/start", follow_redirects=False).status_code == 404


def test_rs256_rejects_short_keys_and_tampering():
    small_n = int("c" * 128, 16)  # 512 bits
    assert not oidc._rs256_valid(small_n, E, b"x", b"\x01" * 64)
    head, body, sig = sign({"a": 1}).split(".")
    raw = oidc._unb64url(sig)
    signed = f"{head}.{body}".encode()
    assert oidc._rs256_valid(N, E, signed, raw)
    assert not oidc._rs256_valid(N, E, signed + b"x", raw)
    assert not oidc._rs256_valid(N, E, signed, raw[:-1] + bytes([raw[-1] ^ 1]))


def test_settings_and_account_pages_render(client, provider):
    link_dan(client, provider)
    assert password_login(client, "dan", "hunter2").status_code == 303
    page = client.get("/settings").text
    assert "Pocket ID sign-in" in page
    assert "http://testserver/auth/oidc/callback" in page
    assert SECRET not in page
    assert "Pocket ID is the only way in" in page
    account = client.get("/account").text
    assert "Your account is linked to Pocket ID" in account
    # Saving without a secret keeps the stored one.
    r = client.post("/api/settings", json={"oidc_client_id": CLIENT_ID, "oidc_client_secret": ""})
    assert r.status_code == 200 and oidc.client_secret() == SECRET
    assert client.post("/api/settings", json={"public_url": "sq.example"}).status_code == 422
