from app import config
from app.services import users


def seed(client):
    p = client.post("/api/projects", json={"name": "Chores"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"],
        "title": "Water plants", "description": "- [x] front\n- [ ] back"}).json()
    client.post(f"/api/cards/{card['id']}/today", json={"today": True})
    return p, cols, card


def test_kiosk_page_renders_with_registry_params(client):
    d = client.post(
        "/api/displays",
        json={"name": "Hall Tablet", "kind": "browser",
              "params": {"theme": "contrast", "scale": "1.25"}},
    ).json()
    page = client.get(f"/kiosk?d={d['id']}").text
    assert "theme-contrast" in page and "1.25" in page and "Hall Tablet" in page
    assert client.get("/kiosk").status_code == 200


def test_registered_browser_display_url_points_at_kiosk(client):
    d = client.post(
        "/api/displays", json={"name": "Pi", "kind": "browser"}
    ).json()
    assert "/kiosk?" in d["url"]


def test_kiosk_data_shape(client):
    seed(client)
    data = client.get("/api/kiosk/data").json()
    assert data["remaining"] == 1
    task = data["tasks"][0]
    assert task["title"] == "Water plants"
    assert task["checklist"] == "1/2"
    assert data["overdue"] == 0


def test_kiosk_toggle_roundtrip(client):
    p, cols, card = seed(client)
    toggled = client.post(f"/api/kiosk/toggle/{card['id']}").json()
    assert toggled["column_id"] == cols[-1]["id"]  # into the done column
    assert client.get("/api/kiosk/data").json()["remaining"] == 0
    back = client.post(f"/api/kiosk/toggle/{card['id']}").json()
    assert back["column_id"] == cols[0]["id"]  # back to the first column
    assert client.post("/api/kiosk/toggle/999").status_code == 404


def test_kiosk_toggle_respawns_recurring(client):
    p, cols, card = seed(client)
    client.patch(f"/api/cards/{card['id']}", json={"recur_days": 7})
    toggled = client.post(f"/api/kiosk/toggle/{card['id']}").json()
    assert toggled["column_id"] == cols[0]["id"]  # respawned to the start
    assert toggled["due_date"] != ""


def test_kiosk_token_access_when_locked(client):
    p, cols, card = seed(client)
    users.create_user("dan", "hunter2", "admin")
    config.save_settings({"display_token": "wall"})

    assert client.get("/kiosk", follow_redirects=False).status_code == 303
    assert client.get("/api/kiosk/data").status_code == 401
    assert client.get("/kiosk", params={"token": "wall"}).status_code == 200
    assert client.get("/api/kiosk/data", params={"token": "wall"}).status_code == 200
    # The one write a display token may make:
    assert client.post(
        f"/api/kiosk/toggle/{card['id']}", params={"token": "wall"}
    ).status_code == 200
    assert client.post(
        f"/api/kiosk/toggle/{card['id']}", params={"token": "bad"}
    ).status_code == 401


def test_viewer_session_cannot_toggle(client):
    p, cols, card = seed(client)
    users.create_user("boss", "adminpw", "admin")
    users.create_user("tv", "viewerpw", "viewer")
    client.post("/login", data={"username": "tv", "password": "viewerpw", "next": "/"})
    assert client.get("/api/kiosk/data").status_code == 200
    assert client.post(f"/api/kiosk/toggle/{card['id']}").status_code == 403
