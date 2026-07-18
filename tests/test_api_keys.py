import pytest

from app.services import api_keys, users


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )


def test_key_lifecycle(temp_data_dir):
    key = api_keys.create_key("Home Assistant", "member")
    assert key["token"].startswith("sq_")
    assert [k["name"] for k in api_keys.list_keys()] == ["Home Assistant"]
    assert "token" not in api_keys.list_keys()[0]

    who = api_keys.verify(key["token"])
    assert who == {"id": None, "username": "key:Home Assistant", "role": "member"}
    assert api_keys.verify("sq_wrong") is None
    assert api_keys.verify(None) is None

    assert api_keys.delete_key(key["id"]) is True
    assert api_keys.verify(key["token"]) is None


def test_key_validation(temp_data_dir):
    with pytest.raises(ValueError):
        api_keys.create_key("", "member")
    with pytest.raises(ValueError):
        api_keys.create_key("x", "admin")  # headless callers never administer


def test_member_key_acts_viewer_key_reads(client):
    users.create_user("dan", "hunter2", "admin")
    member_key = api_keys.create_key("ha", "member")["token"]
    viewer_key = api_keys.create_key("ro", "viewer")["token"]

    # No auth: locked.
    assert client.get("/api/ha/summary").status_code == 401

    h_member = {"X-API-Key": member_key}
    h_viewer = {"X-API-Key": viewer_key}
    assert client.get("/api/ha/summary", headers=h_viewer).status_code == 200
    p = client.post("/api/projects", json={"name": "House"}, headers=h_member)
    assert p.status_code == 201
    assert client.post(
        "/api/projects", json={"name": "Nope"}, headers=h_viewer
    ).status_code == 403
    # Keys never administer, regardless of role.
    assert client.get("/api/users", headers=h_member).status_code == 403
    assert client.post(
        "/api/settings", json={"app_title": "X"}, headers=h_member
    ).status_code == 403
    assert client.get("/api/keys", headers=h_member).status_code == 403


def test_member_key_can_trigger_tv_but_not_manage_displays(client, monkeypatch):
    from app.services import displays

    users.create_user("dan", "hunter2", "admin")
    login(client, "dan", "hunter2")
    d = client.post(
        "/api/displays",
        json={"name": "TV", "kind": "androidtv", "adb_host": "192.168.1.60"},
    ).json()
    client.get("/logout")

    key = api_keys.create_key("ha", "member")["token"]
    headers = {"X-API-Key": key}
    monkeypatch.setattr(
        displays, "run_adb", lambda host, action, url="": {"ok": True, "detail": ""}
    )
    assert client.post(
        f"/api/displays/{d['id']}/tv/show", headers=headers
    ).status_code == 200
    assert client.post(
        "/api/displays", json={"name": "X", "kind": "browser"}, headers=headers
    ).status_code == 403
    assert client.delete(f"/api/displays/{d['id']}", headers=headers).status_code == 403


def test_ha_summary_shape(client):
    p = client.post("/api/projects", json={"name": "House"}).json()
    board = client.get(f"/api/projects/{p['id']}/board").json()
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": board["columns"][0]["id"],
        "title": "Fix gate", "due_date": "2020-01-01"}).json()
    client.post(f"/api/cards/{card['id']}/today", json={"today": True})

    data = client.get("/api/ha/summary").json()
    assert data["today_count"] == 1
    assert data["today_remaining"] == 1
    assert data["today_tasks"][0]["title"] == "Fix gate"
    assert data["overdue"] == 1
    assert data["projects"][0]["open_cards"] == 1
    assert data["stalest"]["name"] == "House"


def test_keys_admin_api(client):
    users.create_user("dan", "hunter2", "admin")
    users.create_user("kid", "letmein", "member")
    login(client, "dan", "hunter2")
    key = client.post("/api/keys", json={"name": "HA", "role": "member"}).json()
    assert key["token"].startswith("sq_")
    assert client.post(
        "/api/keys", json={"name": "bad", "role": "admin"}
    ).status_code == 422
    assert len(client.get("/api/keys").json()) == 1
    assert client.delete(f"/api/keys/{key['id']}").status_code == 204
    client.get("/logout")

    login(client, "kid", "letmein")
    assert client.get("/api/keys").status_code == 403
    assert client.post("/api/keys", json={"name": "x"}).status_code == 403
