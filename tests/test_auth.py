from app import config
from app.services import auth, users


def test_password_hash_roundtrip():
    stored = auth.hash_password("hunter2")
    assert auth.check_password("hunter2", stored)
    assert not auth.check_password("wrong", stored)
    assert not auth.check_password("hunter2", "garbage")


def test_session_token_roundtrip(temp_data_dir):
    user = users.create_user("dan", "hunter2", "admin")
    fp = users.session_fingerprint(user["id"])
    token = auth.make_session_token(user["id"], fp)
    assert auth.session_user_id(token) == user["id"]
    assert auth.session_user_id(token + "x") is None
    assert auth.session_user_id(None) is None

    # Changing the password invalidates the old token.
    users.update_user(user["id"], password="newpass")
    assert auth.session_user_id(token) is None


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )


def test_open_until_first_user(client):
    assert client.get("/api/projects").status_code == 200
    users.create_user("dan", "hunter2", "admin")
    assert client.get("/api/projects").status_code == 401
    assert client.get("/", follow_redirects=False).status_code == 303
    assert client.get("/health").status_code == 200


def test_login_flow(client):
    users.create_user("dan", "hunter2", "admin")
    assert login(client, "dan", "nope").status_code == 401
    assert login(client, "ghost", "hunter2").status_code == 401
    assert login(client, "dan", "hunter2").status_code == 303
    assert client.get("/api/projects").status_code == 200
    client.get("/logout")
    assert client.get("/api/projects").status_code == 401


def test_disabled_user_cannot_login_and_loses_session(client):
    admin = users.create_user("dan", "hunter2", "admin")
    other = users.create_user("kid", "letmein", "member")
    assert login(client, "kid", "letmein").status_code == 303
    assert client.get("/api/projects").status_code == 200
    users.update_user(other["id"], disabled=True)
    assert client.get("/api/projects").status_code == 401
    assert login(client, "kid", "letmein").status_code == 401
    assert admin["id"]


def test_display_token_still_works_when_locked(client):
    users.create_user("dan", "hunter2", "admin")
    config.save_settings({"display_token": "wall-token"})
    assert client.get("/api/display").status_code == 401
    assert client.get("/api/display", params={"token": "wall-token"}).status_code == 200
    assert client.get("/api/display", params={"token": "bad"}).status_code == 401


def test_legacy_password_becomes_admin_account(client, temp_data_dir):
    config.save_settings({"password_hash": auth.hash_password("oldpass")})
    users.migrate_legacy_password()
    assert [u["username"] for u in users.list_users()] == ["admin"]
    assert login(client, "admin", "oldpass").status_code == 303
    # Running it again does not duplicate.
    users.migrate_legacy_password()
    assert len(users.list_users()) == 1


def test_settings_saves_are_partial(temp_data_dir):
    config.save_settings({"gemini_api_key": "abc"})
    config.save_settings({"llm_provider": "anthropic"})
    s = config.load_settings()
    assert s["gemini_api_key"] == "abc"
    assert s["llm_provider"] == "anthropic"
