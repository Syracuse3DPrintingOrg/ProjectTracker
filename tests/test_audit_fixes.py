from app import config
from app.services import auth, users


def lock(client):
    users.create_user("dan", "hunter2", "admin")
    config.save_settings({"display_token": "wall"})


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )


def test_display_token_cannot_reach_display_admin(client):
    """Regression: /displays and /api/displays must never fall under the
    display token's read-only reach (startswith('/display') matched them)."""
    lock(client)
    t = {"token": "wall"}
    # The token's legitimate surface still works.
    assert client.get("/api/display", params=t).status_code == 200
    assert client.get("/kiosk", params=t).status_code == 200
    # The admin surfaces do not.
    assert client.get("/api/displays", params=t).status_code == 401
    assert client.get("/displays", params=t, follow_redirects=False).status_code == 303
    assert client.post(
        "/api/displays", params=t, json={"name": "evil", "kind": "browser"}
    ).status_code == 401
    assert client.post(
        "/api/displays/x/tv/show", params=t
    ).status_code == 401


def test_display_list_is_admin_only(client):
    lock(client)
    users.create_user("kid", "letmein", "member")
    login(client, "kid", "letmein")
    assert client.get("/api/displays").status_code == 403
    resp = client.get("/displays", follow_redirects=False)
    assert resp.status_code == 403
    # Members can still trigger a TV (the operational carve-out).
    # (403 for config, but the tv action path is member-allowed; the
    #  display does not exist, so a 404 from the router proves the
    #  middleware let it through.)
    assert client.post("/api/displays/nope/tv/show").status_code == 404


def test_connector_token_hidden_from_non_admins(client):
    lock(client)
    users.create_user("kid", "letmein", "member")
    login(client, "dan", "hunter2")
    admin_page = client.get("/dashboard/claude-code").text
    assert "--token" in admin_page
    client.get("/logout")

    login(client, "kid", "letmein")
    member_page = client.get("/dashboard/claude-code").text
    token = config.load_settings()["connector_token"]
    assert token not in member_page
    assert "An admin can set up the connector" in member_page


def test_pbkdf2_hashing_with_legacy_compat():
    stored = auth.hash_password("hunter2")
    assert stored.startswith("pbkdf2$")
    assert auth.check_password("hunter2", stored)
    assert not auth.check_password("wrong", stored)

    # Pre-0.12 hashes still verify.
    import hashlib

    legacy = "abcd1234$" + hashlib.sha256(("abcd1234" + "old-pass").encode()).hexdigest()
    assert auth.check_password("old-pass", legacy)
    assert not auth.check_password("nope", legacy)


def test_deleting_user_clears_assignments(client):
    users.create_user("dan", "hunter2", "admin")
    kid = users.create_user("kid", "letmein", "member")
    login(client, "dan", "hunter2")
    p = client.post("/api/projects", json={"name": "House"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "A"}).json()
    client.patch(f"/api/cards/{card['id']}", json={"assignee_id": kid["id"]})
    users.delete_user(kid["id"])
    from app.services import store

    assert store.get_card(card["id"])["assignee_id"] is None


def test_settings_cache_sees_fresh_writes(temp_data_dir):
    config.save_settings({"app_title": "One"})
    assert config.load_settings()["app_title"] == "One"
    config.save_settings({"app_title": "Two"})
    assert config.load_settings()["app_title"] == "Two"
