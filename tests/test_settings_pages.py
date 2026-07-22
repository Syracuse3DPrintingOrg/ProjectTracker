"""The pane-based Settings page, the /displays redirect, and the
overview and update-check endpoints."""

import httpx

from app import config
from app.routers import settings_router
from app.services import users

PANES = ("overview", "ai", "general", "users", "hardware", "backup", "updates")


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )


# ---- the page ----

def test_settings_page_renders_all_panes_for_admin(client):
    users.create_user("boss", "adminpw", "admin")
    login(client, "boss", "adminpw")
    page = client.get("/settings").text
    for pane in PANES:
        assert f'data-pane="{pane}"' in page
    assert 'class="settings-nav"' in page


def test_settings_page_renders_all_panes_when_open(client):
    page = client.get("/settings").text
    for pane in PANES:
        assert f'data-pane="{pane}"' in page


def test_hardware_pane_lists_registered_displays(client):
    client.post("/api/displays", json={"name": "Kitchen TV", "kind": "browser"})
    page = client.get("/settings").text
    assert "Kitchen TV" in page


def test_displays_redirects_to_hardware_pane(client):
    resp = client.get("/displays", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings#hardware"


# ---- overview ----

def test_overview_shape_and_counts(client):
    project = client.post("/api/projects", json={"name": "House"}).json()
    board = client.get(f"/api/projects/{project['id']}/board").json()
    client.post("/api/cards", json={
        "project_id": project["id"],
        "column_id": board["columns"][0]["id"],
        "title": "Fix the gutter",
    })
    client.post("/api/displays", json={"name": "Pi", "kind": "browser"})

    data = client.get("/api/settings/overview").json()
    assert data["version"] == config.APP_VERSION
    assert data["projects"] == 1
    assert data["open_cards"] == 1
    assert data["users"] == 0
    assert data["displays"] == 1
    assert data["health"] == {
        "data_dir_writable": True,
        "ai_configured": False,
        "users_configured": False,
    }


def test_overview_and_updates_are_admin_only(client):
    users.create_user("boss", "adminpw", "admin")
    users.create_user("kid", "memberpw", "member")
    login(client, "kid", "memberpw")
    assert client.get("/api/settings/overview").status_code == 403
    assert client.get("/api/settings/updates").status_code == 403
    client.get("/logout")
    login(client, "boss", "adminpw")
    assert client.get("/api/settings/overview").status_code == 200


# ---- update checks (GitHub stubbed out) ----

def test_updates_reports_current(client, monkeypatch):
    monkeypatch.setattr(
        settings_router, "_github_get",
        lambda path: {"tag_name": f"v{config.APP_VERSION}",
                      "html_url": "https://example.test/release"},
    )
    data = client.get("/api/settings/updates").json()
    assert data["current"] == config.APP_VERSION
    assert data["latest"] == config.APP_VERSION
    assert data["update_available"] is False
    assert data["checked"] is True
    assert data["error"] == ""
    assert data["image"] == settings_router.DOCKER_IMAGE


def test_updates_reports_newer_release(client, monkeypatch):
    monkeypatch.setattr(
        settings_router, "_github_get",
        lambda path: {"tag_name": "v99.1.0",
                      "html_url": "https://example.test/release"},
    )
    data = client.get("/api/settings/updates").json()
    assert data["update_available"] is True
    assert data["latest"] == "99.1.0"
    assert data["url"] == "https://example.test/release"


def test_updates_falls_back_to_tags_when_no_releases(client, monkeypatch):
    def fake(path):
        if path == "/releases/latest":
            request = httpx.Request("GET", "https://api.github.com/x")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("no releases", request=request, response=response)
        assert path == "/tags"
        return [{"name": "v0.2.0"}, {"name": "v99.1.0"}, {"name": "not-a-version"}]

    monkeypatch.setattr(settings_router, "_github_get", fake)
    data = client.get("/api/settings/updates").json()
    assert data["update_available"] is True
    assert data["latest"] == "99.1.0"
    assert data["url"].endswith("/releases/tag/v99.1.0")


def test_updates_offline_is_graceful(client, monkeypatch):
    def boom(path):
        raise httpx.ConnectError("no network")

    monkeypatch.setattr(settings_router, "_github_get", boom)
    resp = client.get("/api/settings/updates")
    assert resp.status_code == 200
    data = resp.json()
    assert data["current"] == config.APP_VERSION
    assert data["update_available"] is False
    assert data["checked"] is False
    assert "Could not check" in data["error"]
