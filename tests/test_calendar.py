from app.services import store


def seed(client):
    a = client.post("/api/projects", json={"name": "Alpha"}).json()
    b = client.post("/api/projects", json={"name": "Beta"}).json()
    cols_a = client.get(f"/api/projects/{a['id']}/board").json()["columns"]
    cols_b = client.get(f"/api/projects/{b['id']}/board").json()["columns"]
    client.post("/api/cards", json={
        "project_id": a["id"], "column_id": cols_a[0]["id"],
        "title": "A due", "due_date": "2026-07-10"})
    client.post("/api/cards", json={
        "project_id": a["id"], "column_id": cols_a[0]["id"],
        "title": "A undated"})
    client.post("/api/cards", json={
        "project_id": b["id"], "column_id": cols_b[0]["id"],
        "title": "B due", "due_date": "2026-07-20", "priority": 0})
    client.post("/api/cards", json={
        "project_id": b["id"], "column_id": cols_b[0]["id"],
        "title": "B next month", "due_date": "2026-08-02"})
    return a, b


def test_calendar_range_and_shape(client):
    a, b = seed(client)
    cards = client.get(
        "/api/calendar", params={"start": "2026-07-01", "end": "2026-07-31"}
    ).json()
    assert [c["title"] for c in cards] == ["A due", "B due"]
    assert cards[0]["project_name"] == "Alpha"
    assert cards[0]["status"] and "done" in cards[0]


def test_calendar_project_filter(client):
    a, b = seed(client)
    cards = client.get(
        "/api/calendar",
        params={"start": "2026-07-01", "end": "2026-08-31", "projects": str(b["id"])},
    ).json()
    assert [c["title"] for c in cards] == ["B due", "B next month"]


def test_calendar_excludes_archived_projects(client):
    a, b = seed(client)
    client.post(f"/api/projects/{b['id']}/archive")
    cards = client.get(
        "/api/calendar", params={"start": "2026-07-01", "end": "2026-08-31"}
    ).json()
    assert [c["title"] for c in cards] == ["A due"]


def test_calendar_validates_input(client):
    assert client.get(
        "/api/calendar", params={"start": "july", "end": "2026-07-31"}
    ).status_code == 422
    assert client.get(
        "/api/calendar",
        params={"start": "2026-07-01", "end": "2026-07-31", "projects": "1,x"},
    ).status_code == 422


def test_calendar_orders_by_date_then_priority(temp_data_dir):
    p = store.create_project("P")
    col = store.list_columns(p["id"])[0]["id"]
    store.create_card(p["id"], col, "later", due_date="2026-07-10", priority=0)
    store.create_card(p["id"], col, "urgent", due_date="2026-07-05", priority=0)
    store.create_card(p["id"], col, "casual", due_date="2026-07-05", priority=3)
    cards = store.list_due_cards("2026-07-01", "2026-07-31")
    assert [c["title"] for c in cards] == ["urgent", "casual", "later"]


def test_calendar_page_renders(client):
    seed(client)
    resp = client.get("/calendar")
    assert resp.status_code == 200
    assert "Projects" in resp.text and "calendar.js" in resp.text
