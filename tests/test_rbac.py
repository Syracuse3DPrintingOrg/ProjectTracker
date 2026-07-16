import pytest

from app.services import rbac, users


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )


def make_users():
    users.create_user("boss", "adminpw", "admin")
    users.create_user("worker", "memberpw", "member")
    users.create_user("guest", "viewerpw", "viewer")


# ---- pure rules ----

def test_allowed_matrix():
    assert rbac.allowed("admin", "POST", "/api/settings")
    assert rbac.allowed("admin", "GET", "/api/export")
    assert rbac.allowed("member", "POST", "/api/cards")
    assert rbac.allowed("member", "POST", "/api/account/password")
    assert not rbac.allowed("member", "POST", "/api/settings")
    assert not rbac.allowed("member", "POST", "/api/users")
    assert not rbac.allowed("member", "DELETE", "/api/displays/x")
    assert not rbac.allowed("member", "GET", "/api/export")
    assert rbac.allowed("viewer", "GET", "/api/projects")
    assert rbac.allowed("viewer", "POST", "/api/account/password")
    assert not rbac.allowed("viewer", "POST", "/api/cards")
    assert not rbac.allowed("viewer", "DELETE", "/api/cards/1")


# ---- enforcement through the app ----

def test_member_can_work_but_not_administer(client):
    make_users()
    login(client, "worker", "memberpw")
    p = client.post("/api/projects", json={"name": "House"})
    assert p.status_code == 201
    assert client.post("/api/settings", json={"app_title": "X"}).status_code == 403
    assert client.get("/api/users").status_code == 403
    assert client.get("/api/export").status_code == 403
    assert client.post(
        "/api/displays", json={"name": "TV", "kind": "browser"}
    ).status_code == 403
    # Settings page bounces members to their account page.
    resp = client.get("/settings", follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/account"


def test_viewer_reads_only(client):
    make_users()
    login(client, "boss", "adminpw")
    proj = client.post("/api/projects", json={"name": "House"}).json()
    client.get("/logout")

    login(client, "guest", "viewerpw")
    assert client.get(f"/api/projects/{proj['id']}/board").status_code == 200
    assert client.get(f"/project/{proj['id']}").status_code == 200
    assert client.post("/api/projects", json={"name": "Nope"}).status_code == 403
    board = client.get(f"/api/projects/{proj['id']}/board").json()
    assert client.post("/api/cards", json={
        "project_id": proj["id"], "column_id": board["columns"][0]["id"],
        "title": "sneaky"}).status_code == 403
    assert client.post("/api/today/clear-done").status_code == 403


def test_admin_can_do_everything(client):
    make_users()
    login(client, "boss", "adminpw")
    assert client.post("/api/settings", json={"app_title": "SQ HQ"}).status_code == 200
    assert client.get("/api/users").status_code == 200
    assert client.get("/api/export").status_code == 200
    assert client.get("/settings").status_code == 200


# ---- user management ----

def test_user_crud_and_guards(client):
    make_users()
    login(client, "boss", "adminpw")

    all_users = client.get("/api/users").json()
    assert [u["username"] for u in all_users] == ["boss", "guest", "worker"]
    boss = next(u for u in all_users if u["username"] == "boss")
    worker = next(u for u in all_users if u["username"] == "worker")

    # Duplicate and invalid creates are refused.
    assert client.post("/api/users", json={
        "username": "worker", "password": "xxxx", "role": "member"}).status_code == 422
    assert client.post("/api/users", json={
        "username": "new", "password": "abc", "role": "member"}).status_code == 422
    assert client.post("/api/users", json={
        "username": "new", "password": "abcd", "role": "boss"}).status_code == 422

    # Promote, demote, disable.
    assert client.patch(f"/api/users/{worker['id']}", json={"role": "admin"}).json()["role"] == "admin"
    assert client.patch(f"/api/users/{worker['id']}", json={"role": "member"}).status_code == 200

    # Last-admin guards.
    assert client.patch(f"/api/users/{boss['id']}", json={"role": "member"}).status_code == 422
    assert client.patch(f"/api/users/{boss['id']}", json={"disabled": True}).status_code == 422
    assert client.delete(f"/api/users/{boss['id']}").status_code == 422

    # Deleting someone else works.
    assert client.delete(f"/api/users/{worker['id']}").status_code == 204


def test_first_user_must_be_admin(temp_data_dir):
    with pytest.raises(ValueError):
        users.create_user("dan", "hunter2", "member")
    users.create_user("dan", "hunter2", "admin")
    users.create_user("kid", "hunter2", "member")


def test_change_own_password_invalidates_session(client):
    make_users()
    login(client, "worker", "memberpw")
    resp = client.post("/api/account/password", json={
        "current_password": "wrong", "new_password": "newpass"})
    assert resp.status_code == 422
    resp = client.post("/api/account/password", json={
        "current_password": "memberpw", "new_password": "newpass"})
    assert resp.json()["relogin"] is True
    # Old session is dead.
    assert client.get("/api/projects").status_code == 401
    assert login(client, "worker", "newpass").status_code == 303


def test_account_page(client):
    make_users()
    login(client, "guest", "viewerpw")
    resp = client.get("/account")
    assert resp.status_code == 200
    assert "guest" in resp.text
