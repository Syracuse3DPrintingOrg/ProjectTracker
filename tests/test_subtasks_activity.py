from app.services import llm, store, users


def make_card(client, title="Bracket"):
    p = client.post("/api/projects", json={"name": "Shop"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": title}).json()
    return p, cols, card


def test_subtask_lifecycle(client):
    p, cols, card = make_card(client)
    a = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "measure"}).json()
    b = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "cut"}).json()
    assert [s["title"] for s in client.get(f"/api/cards/{card['id']}/subtasks").json()] == ["measure", "cut"]

    client.patch(f"/api/subtasks/{a['id']}", json={"done": True})
    client.patch(f"/api/subtasks/{b['id']}", json={"title": "cut to length", "position": 0})
    subs = client.get(f"/api/cards/{card['id']}/subtasks").json()
    assert [s["title"] for s in subs] == ["cut to length", "measure"]
    assert subs[1]["done"] == 1
    assert store.subtask_progress_for_card(card["id"]) == (1, 2)

    assert client.delete(f"/api/subtasks/{a['id']}").status_code == 204
    assert client.delete(f"/api/subtasks/{a['id']}").status_code == 404
    assert client.post("/api/cards/999/subtasks", json={"title": "x"}).status_code == 404


def test_subtasks_cascade_and_export(client):
    p, cols, card = make_card(client)
    client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "one"})
    export = client.get("/api/export").json()
    assert len(export["subtasks"]) == 1
    export["confirm"] = True
    client.post("/api/import", json=export)
    assert len(store.list_subtasks(card["id"])) == 1
    client.delete(f"/api/cards/{card['id']}")
    with __import__("app.database", fromlist=["connect"]).connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM subtasks").fetchone()[0] == 0


def test_ai_subtasks_create_rows(client, monkeypatch):
    p, cols, card = make_card(client)
    client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "existing"})
    monkeypatch.setattr(llm, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(
        llm, "suggest_subtasks", lambda t, d: ["Existing", "sand it", "paint it"]
    )
    data = client.post("/api/assist/subtasks", json={"card_id": card["id"]}).json()
    assert data["subtasks"] == ["sand it", "paint it"]  # dedup against existing
    assert len(store.list_subtasks(card["id"])) == 3


def test_subtasks_in_handoff_and_kiosk(client):
    p, cols, card = make_card(client)
    client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "measure"})
    s = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "cut"}).json()
    client.patch(f"/api/subtasks/{s['id']}", json={"done": True})
    prompt = client.get(f"/api/cards/{card['id']}/handoff").json()["prompt"]
    assert "Subtasks (1/2 done):" in prompt and "- [x] cut" in prompt

    client.post(f"/api/cards/{card['id']}/today", json={"today": True})
    task = client.get("/api/kiosk/data").json()["tasks"][0]
    assert task["subtasks"] == "1/2"


def test_assignee_flow(client):
    users.create_user("dan", "hunter2", "admin")
    users.create_user("kid", "letmein", "member")
    client.post("/login", data={"username": "dan", "password": "hunter2", "next": "/"})
    p, cols, card = make_card(client)

    names = client.get("/api/assignees").json()
    assert [u["username"] for u in names] == ["dan", "kid"]

    kid = next(u for u in names if u["username"] == "kid")
    updated = client.patch(f"/api/cards/{card['id']}", json={"assignee_id": kid["id"]}).json()
    assert updated["assignee_id"] == kid["id"]
    assert client.patch(f"/api/cards/{card['id']}", json={"assignee_id": 999}).status_code == 422

    updated = client.patch(f"/api/cards/{card['id']}", json={"clear_assignee": True}).json()
    assert updated["assignee_id"] is None

    kinds = [e["kind"] for e in client.get(f"/api/cards/{card['id']}/events").json()]
    assert kinds.count("assigned") == 2


def test_activity_feed(client):
    users.create_user("dan", "hunter2", "admin")
    client.post("/login", data={"username": "dan", "password": "hunter2", "next": "/"})
    p, cols, card = make_card(client)
    client.post(f"/api/cards/{card['id']}/move", json={"column_id": cols[2]["id"], "position": 0})
    client.post(f"/api/cards/{card['id']}/comments", json={"text": "looks good"})

    events = client.get(f"/api/cards/{card['id']}/events").json()
    kinds = [e["kind"] for e in events]
    assert kinds == ["created", "moved", "comment"]
    assert events[0]["actor"] == "dan"
    assert events[1]["text"] == "to In Progress"
    assert events[2]["text"] == "looks good"


def test_viewer_cannot_comment_or_toggle_subtasks(client):
    users.create_user("dan", "hunter2", "admin")
    users.create_user("tv", "viewerpw", "viewer")
    client.post("/login", data={"username": "dan", "password": "hunter2", "next": "/"})
    p, cols, card = make_card(client)
    sub = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "x"}).json()
    client.get("/logout")

    client.post("/login", data={"username": "tv", "password": "viewerpw", "next": "/"})
    assert client.get(f"/api/cards/{card['id']}/events").status_code == 200
    assert client.post(
        f"/api/cards/{card['id']}/comments", json={"text": "hi"}
    ).status_code == 403
    assert client.patch(f"/api/subtasks/{sub['id']}", json={"done": True}).status_code == 403


def test_kiosk_due_views(client):
    p, cols, card = make_card(client)
    client.patch(f"/api/cards/{card['id']}", json={"due_date": "2020-01-01"})
    soon = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "Soon"}).json()
    from datetime import date, timedelta
    client.patch(f"/api/cards/{soon['id']}", json={
        "due_date": (date.today() + timedelta(days=2)).isoformat()})
    data = client.get("/api/kiosk/data").json()
    assert [t["title"] for t in data["overdue_tasks"]] == ["Bracket"]
    assert [t["title"] for t in data["due_soon_tasks"]] == ["Soon"]
    assert data["overdue"] == 1
