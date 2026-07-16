from app import config
from app.services import auth


def test_password_hash_roundtrip():
    stored = auth.hash_password("hunter2")
    assert auth.check_password("hunter2", stored)
    assert not auth.check_password("wrong", stored)
    assert not auth.check_password("hunter2", "garbage")


def test_session_token_roundtrip(temp_data_dir):
    token = auth.make_session_token()
    assert auth.valid_session(token)
    assert not auth.valid_session(token + "x")
    assert not auth.valid_session(None)


def test_login_flow_and_display_token(client):
    # Open by default.
    assert client.get("/api/projects").status_code == 200

    config.save_settings(
        {
            "password_hash": auth.hash_password("secret"),
            "display_token": "wall-token",
        }
    )

    # Locked: pages redirect to login, APIs 401, display token works.
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/api/projects").status_code == 401
    assert client.get("/api/display").status_code == 401
    assert client.get("/api/display", params={"token": "wall-token"}).status_code == 200
    assert client.get("/api/display", params={"token": "nope"}).status_code == 401
    assert client.get("/health").status_code == 200

    # Wrong then right password.
    resp = client.post("/login", data={"password": "nope", "next": "/"})
    assert resp.status_code == 401
    resp = client.post(
        "/login", data={"password": "secret", "next": "/"}, follow_redirects=False
    )
    assert resp.status_code == 303
    assert client.get("/api/projects").status_code == 200


def test_settings_saves_are_partial(temp_data_dir):
    config.save_settings({"gemini_api_key": "abc"})
    config.save_settings({"llm_provider": "anthropic"})
    s = config.load_settings()
    assert s["gemini_api_key"] == "abc"
    assert s["llm_provider"] == "anthropic"
