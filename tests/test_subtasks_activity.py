from app import database
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

    # A subtask is a card of its own now: done means it sits in a done
    # column, undone brings it back.
    done_child = store.get_card(a["id"])
    assert done_child["parent_id"] == card["id"]
    assert done_child["column_id"] == cols[-1]["id"]
    client.patch(f"/api/subtasks/{a['id']}", json={"done": False})
    assert store.get_card(a["id"])["column_id"] == cols[0]["id"]

    assert client.delete(f"/api/subtasks/{a['id']}").status_code == 204
    assert client.delete(f"/api/subtasks/{a['id']}").status_code == 404
    assert client.post("/api/cards/999/subtasks", json={"title": "x"}).status_code == 404
    # The subtask endpoints never touch top-level cards.
    assert client.delete(f"/api/subtasks/{card['id']}").status_code == 404
    assert client.patch(f"/api/subtasks/{card['id']}", json={"done": True}).status_code == 404


def test_children_ride_in_export_and_import(client):
    p, cols, card = make_card(client)
    client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "one"})
    export = client.get("/api/export").json()
    # No separate subtasks list anymore; children travel in cards.
    assert "subtasks" not in export
    child_rows = [c for c in export["cards"] if c["parent_id"] == card["id"]]
    assert [c["title"] for c in child_rows] == ["one"]
    export["confirm"] = True
    client.post("/api/import", json=export)
    assert [s["title"] for s in store.list_subtasks(card["id"])] == ["one"]


def test_parent_delete_promotes_children(client):
    p, cols, card = make_card(client)
    a = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "keep me"}).json()
    b = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "me too"}).json()
    client.patch(f"/api/subtasks/{b['id']}", json={"done": True})

    assert client.delete(f"/api/cards/{card['id']}").status_code == 204
    kept = store.get_card(a["id"])
    finished = store.get_card(b["id"])
    assert kept["parent_id"] is None and finished["parent_id"] is None
    # The undone child surfaces in the parent's old column; the finished
    # one stays finished in the done column.
    assert kept["column_id"] == cols[0]["id"]
    assert finished["column_id"] == cols[-1]["id"]
    board = client.get(f"/api/projects/{p['id']}/board").json()
    assert sorted(c["title"] for c in board["cards"]) == ["keep me", "me too"]


def test_nesting_via_patch_with_guards(client):
    p, cols, parent = make_card(client, "Parent")
    def add(title, project=p, columns=None):
        col = (columns or cols)[0]["id"]
        return client.post("/api/cards", json={
            "project_id": project["id"], "column_id": col, "title": title}).json()
    child = add("Child")
    grand = add("Grand")
    other = add("Other")

    nested = client.patch(f"/api/cards/{child['id']}", json={"parent_id": parent["id"]}).json()
    assert nested["parent_id"] == parent["id"]
    # One level only, in both directions.
    assert client.patch(f"/api/cards/{grand['id']}", json={"parent_id": child["id"]}).status_code == 422
    assert client.patch(f"/api/cards/{parent['id']}", json={"parent_id": other["id"]}).status_code == 422
    # Not itself, not a ghost.
    assert client.patch(f"/api/cards/{other['id']}", json={"parent_id": other["id"]}).status_code == 422
    assert client.patch(f"/api/cards/{other['id']}", json={"parent_id": 9999}).status_code == 422
    # Adding a subtask to a subtask is refused too.
    assert client.post(f"/api/cards/{child['id']}/subtasks", json={"title": "x"}).status_code == 422

    # Subtasks stay within their project.
    p2 = client.post("/api/projects", json={"name": "Elsewhere"}).json()
    cols2 = client.get(f"/api/projects/{p2['id']}/board").json()["columns"]
    stranger = add("Stranger", project=p2, columns=cols2)
    assert client.patch(f"/api/cards/{stranger['id']}", json={"parent_id": parent["id"]}).status_code == 422

    # Children stay off the board page's columns and render nested.
    page = client.get(f"/project/{p['id']}").text
    assert "child-list" in page and "child-card" in page

    promoted = client.patch(f"/api/cards/{child['id']}", json={"clear_parent": True}).json()
    assert promoted["parent_id"] is None
    assert store.subtask_progress_for_card(parent["id"]) == (0, 0)


def test_children_counted_in_due_and_plan(client):
    p, cols, card = make_card(client)
    sub = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "overdue kid"}).json()
    client.patch(f"/api/cards/{sub['id']}", json={"due_date": "2020-01-01"})

    assert "overdue kid" in [r["title"] for r in store.due_lists()["overdue"]]
    assert "overdue kid" in [r["title"] for r in store.plan_candidates()]
    assert store.overdue_count() == 1
    # The nudge counts children as open cards; they are real work.
    assert client.get("/api/nudge").json()[0]["open_cards"] == 2


def test_migration_converts_legacy_subtasks(temp_data_dir):
    # Rebuild the pre-migration shape: no parent_id on cards, a separate
    # subtasks table, all seeded with raw SQL.
    with database.connect() as conn:
        conn.execute("DROP INDEX idx_cards_parent")
        conn.execute("ALTER TABLE cards DROP COLUMN parent_id")
        conn.execute(
            "CREATE TABLE subtasks ("
            " id INTEGER PRIMARY KEY,"
            " card_id INTEGER NOT NULL,"
            " title TEXT NOT NULL,"
            " done INTEGER NOT NULL DEFAULT 0,"
            " position INTEGER NOT NULL DEFAULT 0,"
            " created_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.execute("INSERT INTO projects (id, name) VALUES (1, 'Legacy')")
        conn.execute(
            "INSERT INTO columns (id, project_id, name, position, is_done)"
            " VALUES (10, 1, 'To Do', 0, 0), (11, 1, 'Done', 1, 1)"
        )
        conn.execute(
            "INSERT INTO cards (id, project_id, column_id, title, position)"
            " VALUES (100, 1, 10, 'Build the bed', 0)"
        )
        conn.execute(
            "INSERT INTO subtasks (card_id, title, done, position) VALUES"
            " (100, 'cut wood', 0, 0), (100, 'sand it', 1, 1), (100, 'paint it', 0, 2)"
        )

    database.init_db()

    subs = store.list_subtasks(100)
    assert [s["title"] for s in subs] == ["cut wood", "sand it", "paint it"]
    assert [s["done"] for s in subs] == [0, 1, 0]
    assert store.subtask_progress_for_card(100) == (1, 3)
    children = store.children_map(1)[100]
    assert [c["column_id"] for c in children] == [10, 11, 10]
    with database.connect() as conn:
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'subtasks'"
        ).fetchone() is None


def test_old_backup_import_lands_child_cards(client):
    payload = {
        "confirm": True,
        "projects": [{"id": 1, "name": "Legacy"}],
        "columns": [
            {"id": 10, "project_id": 1, "name": "To Do", "position": 0, "is_done": 0},
            {"id": 11, "project_id": 1, "name": "Done", "position": 1, "is_done": 1},
        ],
        "cards": [{"id": 100, "project_id": 1, "column_id": 10,
                   "title": "Build the bed", "position": 0}],
        "subtasks": [
            {"id": 1, "card_id": 100, "title": "cut wood", "done": 0, "position": 0},
            {"id": 2, "card_id": 100, "title": "sand it", "done": 1, "position": 1},
            {"id": 3, "card_id": 999, "title": "orphan", "done": 0, "position": 0},
        ],
    }
    assert client.post("/api/import", json=payload).json()["ok"] is True
    subs = client.get("/api/cards/100/subtasks").json()
    assert [s["title"] for s in subs] == ["cut wood", "sand it"]
    assert [s["done"] for s in subs] == [0, 1]
    assert store.get_card(subs[1]["id"])["column_id"] == 11
    assert store.subtask_progress_for_card(100) == (1, 2)


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
