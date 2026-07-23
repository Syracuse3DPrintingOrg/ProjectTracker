"""Trello board import and the finished-card archive sweep."""

import copy

from app import database
from app.services import store, users


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )


# A realistic Trello board export slice: two open lists (one named Done),
# a closed list, three open cards with pos ordering, a closed card,
# labels, due datetimes, and a checklist with both item states.
TRELLO = {
    "name": "Workshop Move",
    "id": "board1",
    "lists": [
        {"id": "l2", "name": "Done", "closed": False, "pos": 200},
        {"id": "l1", "name": "To Do", "closed": False, "pos": 100},
        {"id": "l3", "name": "Old ideas", "closed": True, "pos": 300},
    ],
    "cards": [
        {
            "id": "c2", "name": "Pack the bench", "idList": "l1",
            "closed": False, "pos": 2000,
            "desc": "Bubble wrap the vise",
            "due": "2026-08-01T12:00:00.000Z",
            "labels": [
                {"name": "heavy", "color": "red"},
                {"name": "", "color": "green"},
            ],
            "dateLastActivity": "2026-07-01T09:30:00.123Z",
            "idChecklists": ["ch1"],
        },
        {"id": "c1", "name": "Label boxes", "idList": "l1",
         "closed": False, "pos": 1000},
        {"id": "c3", "name": "Sold the lathe", "idList": "l2",
         "closed": False, "pos": 500},
        {"id": "c4", "name": "Scrapped plan", "idList": "l1",
         "closed": True, "pos": 3000},
    ],
    "checklists": [
        {
            "id": "ch1", "idCard": "c2", "name": "Packing",
            "checkItems": [
                {"id": "i2", "name": "find boxes", "state": "complete", "pos": 200},
                {"id": "i1", "name": "buy tape", "state": "incomplete", "pos": 100},
            ],
        },
    ],
    "labels": [{"id": "lab1", "name": "heavy", "color": "red"}],
}


# ---- Trello import ----

def test_trello_import_maps_the_board(client):
    resp = client.post("/api/import/trello", json=TRELLO)
    assert resp.status_code == 200
    result = resp.json()
    assert result["project_name"] == "Workshop Move"
    assert result["counts"] == {
        "lists": 2, "cards": 3, "subtasks": 2,
        "skipped_lists": 1, "skipped_cards": 1,
    }

    board = client.get(f"/api/projects/{result['project_id']}/board").json()
    # Open lists arrive in pos order; the list named Done is the done column.
    assert [c["name"] for c in board["columns"]] == ["To Do", "Done"]
    assert [c["is_done"] for c in board["columns"]] == [0, 1]
    todo, done = board["columns"]

    tops = [c for c in board["cards"] if c["parent_id"] is None]
    in_todo = sorted(
        (c for c in tops if c["column_id"] == todo["id"]),
        key=lambda c: c["position"],
    )
    assert [c["title"] for c in in_todo] == ["Label boxes", "Pack the bench"]
    assert [c["title"] for c in tops if c["column_id"] == done["id"]] == ["Sold the lathe"]

    pack = in_todo[1]
    assert pack["description"] == "Bubble wrap the vise"
    assert pack["due_date"] == "2026-08-01"
    assert pack["labels"] == "heavy"
    assert pack["updated_at"] == "2026-07-01 09:30:00"

    # Checklist items became subtasks, pos-ordered, completion preserved.
    subs = client.get(f"/api/cards/{pack['id']}/subtasks").json()
    assert [(s["title"], bool(s["done"])) for s in subs] == [
        ("buy tape", False), ("find boxes", True),
    ]


def test_trello_import_appends_done_column_when_none_matches(client):
    data = copy.deepcopy(TRELLO)
    data["lists"][0]["name"] = "Doing"  # no list reads as finished now
    result = client.post("/api/import/trello", json=data).json()
    board = client.get(f"/api/projects/{result['project_id']}/board").json()
    assert [c["name"] for c in board["columns"]] == ["To Do", "Doing", "Done"]
    assert [c["is_done"] for c in board["columns"]] == [0, 0, 1]
    # The complete checklist item still lands in the appended Done column.
    pack = next(c for c in board["cards"] if c["title"] == "Pack the bench")
    subs = client.get(f"/api/cards/{pack['id']}/subtasks").json()
    assert [(s["title"], bool(s["done"])) for s in subs] == [
        ("buy tape", False), ("find boxes", True),
    ]


def test_trello_import_name_collision_gets_suffix(client):
    client.post("/api/projects", json={"name": "Workshop Move"})
    result = client.post("/api/import/trello", json=TRELLO).json()
    assert result["project_name"] == "Workshop Move (imported)"
    assert store.get_project(result["project_id"])["name"] == "Workshop Move (imported)"


def test_trello_import_rejects_garbage(client):
    assert client.post("/api/import/trello", json={"nope": 1}).status_code == 422
    assert client.post("/api/import/trello", json=[1, 2, 3]).status_code == 422
    assert client.post(
        "/api/import/trello", json={"name": "X", "lists": "what", "cards": []}
    ).status_code == 422
    # A friendly message, not a stack trace.
    detail = client.post("/api/import/trello", json={"nope": 1}).json()["detail"]
    assert "Trello" in detail


def test_trello_import_tolerates_sparse_exports(client):
    result = client.post(
        "/api/import/trello",
        json={"lists": [{"id": "a"}], "cards": [{"idList": "a"}]},
    ).json()
    assert result["counts"]["cards"] == 1
    board = client.get(f"/api/projects/{result['project_id']}/board").json()
    assert board["cards"][0]["title"] == "Untitled card"


def test_trello_import_is_admin_only(client):
    users.create_user("boss", "adminpw", "admin")
    users.create_user("worker", "memberpw", "member")

    login(client, "worker", "memberpw")
    assert client.post("/api/import/trello", json=TRELLO).status_code == 403
    client.get("/logout")

    login(client, "boss", "adminpw")
    assert client.post("/api/import/trello", json=TRELLO).status_code == 200


# ---- archive sweep ----

def test_archived_column_migrates_in(temp_data_dir):
    # An older database has no archived column; init_db adds it.
    with database.connect() as conn:
        conn.execute("ALTER TABLE cards DROP COLUMN archived")
    database.init_db()
    with database.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(cards)")}
    assert "archived" in cols


def seed_board(client):
    """A project with a finished card (one open and one done subtask in
    tow), an open card, and the finished card on the shared Today list."""
    p = client.post("/api/projects", json={"name": "Garage"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    shipped = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"],
        "title": "Ship it"}).json()
    client.post(f"/api/cards/{shipped['id']}/subtasks", json={"title": "loose end"})
    sub = client.post(f"/api/cards/{shipped['id']}/subtasks", json={"title": "wrapped"}).json()
    client.patch(f"/api/subtasks/{sub['id']}", json={"done": True})
    client.post(f"/api/cards/{shipped['id']}/move",
                json={"column_id": cols[-1]["id"], "position": 0})
    client.post(f"/api/cards/{shipped['id']}/today", json={"today": True})
    keep = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"],
        "title": "Keep working"}).json()
    return p, cols, shipped, keep


def test_archive_sweep_takes_done_cards_and_children(client):
    p, cols, shipped, keep = seed_board(client)
    resp = client.post(f"/api/projects/{p['id']}/archive-done")
    # The finished card plus both subtasks, wherever those sat.
    assert resp.json() == {"archived": 3}
    # Nothing left to sweep on a second pass.
    assert client.post(f"/api/projects/{p['id']}/archive-done").json() == {"archived": 0}
    assert client.post("/api/projects/999/archive-done").status_code == 404

    # Gone from the board API and the board page, open card untouched.
    board = client.get(f"/api/projects/{p['id']}/board").json()
    assert [c["title"] for c in board["cards"]] == ["Keep working"]
    page = client.get(f"/project/{p['id']}").text
    assert "Ship it" not in page and "Keep working" in page

    # Gone from Today (it was on the shared list), kiosk, and search.
    assert client.get("/api/today").json() == []
    assert client.get("/api/kiosk/data").json()["tasks"] == []
    assert client.get("/api/display").json()["count"] == 0
    assert client.get("/api/search", params={"q": "Ship it"}).json() == []

    # The overview moves it from Completed to Archived.
    data = store.project_overview(p["id"])
    assert data["done_cards"] == []
    assert [c["title"] for c in data["archived_cards"]] == ["Ship it"]
    assert data["counts"]["done"] == 0 and data["counts"]["archived"] == 1
    overview = client.get(f"/project/{p['id']}/overview").text
    assert "1 archived task" in overview and "Unarchive" in overview


def test_unarchive_brings_the_card_back_whole(client):
    p, cols, shipped, keep = seed_board(client)
    client.post(f"/api/projects/{p['id']}/archive-done")

    card = client.patch(f"/api/cards/{shipped['id']}", json={"archived": False}).json()
    assert card["archived"] == 0
    board = client.get(f"/api/projects/{p['id']}/board").json()
    assert {c["title"] for c in board["cards"]} == {
        "Ship it", "Keep working", "loose end", "wrapped"}
    data = store.project_overview(p["id"])
    assert [c["title"] for c in data["done_cards"]] == ["Ship it"]
    assert data["archived_cards"] == []
    # The subtasks came back with it and count again.
    assert store.subtask_progress(p["id"])[shipped["id"]] == (1, 2)


def test_archived_children_leave_subtask_progress(client):
    p = client.post("/api/projects", json={"name": "Loft"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "Insulate"}).json()
    open_sub = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "quote"}).json()
    done_sub = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "measure"}).json()
    client.patch(f"/api/subtasks/{done_sub['id']}", json={"done": True})
    assert store.subtask_progress(p["id"])[card["id"]] == (1, 2)

    client.patch(f"/api/cards/{open_sub['id']}", json={"archived": True})
    assert store.subtask_progress(p["id"])[card["id"]] == (1, 1)
    subs = client.get(f"/api/cards/{card['id']}/subtasks").json()
    assert [s["title"] for s in subs] == ["measure"]


def test_archived_skips_due_plan_nudge_and_calendar(client):
    p = client.post("/api/projects", json={"name": "Yard"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"],
        "title": "Rake leaves", "due_date": "2020-01-01"}).json()
    assert store.overdue_count() == 1
    assert [c["title"] for c in store.plan_candidates()] == ["Rake leaves"]
    assert store.nudge_data()[0]["open_cards"] == 1

    client.patch(f"/api/cards/{card['id']}", json={"archived": True})
    assert store.overdue_count() == 0
    assert store.due_lists()["overdue"] == []
    assert store.plan_candidates() == []
    assert store.nudge_data() == []
    assert store.project_open_counts()[0]["open_cards"] == 0
    assert client.get(
        "/api/calendar", params={"start": "2019-12-01", "end": "2020-02-01"}
    ).json() == []
    kiosk = client.get("/api/kiosk/data").json()
    assert kiosk["overdue"] == 0 and kiosk["overdue_tasks"] == []


def test_archived_leaves_my_work_and_personal_today(temp_data_dir):
    boss = users.create_user("boss", "adminpw", "admin")
    p = store.create_project("Shed")
    col = store.list_columns(p["id"])[0]
    card = store.create_card(p["id"], col["id"], "Hang shelves")
    store.update_card(card["id"], assignee_id=boss["id"])
    store.set_today(card["id"], True, owner=boss["id"])
    assert [c["title"] for c in store.my_work(boss["id"])] == ["Hang shelves"]
    assert [c["title"] for c in store.list_today(owner=boss["id"])] == ["Hang shelves"]

    store.set_card_archived(card["id"], True)
    assert store.my_work(boss["id"]) == []
    assert store.list_today(owner=boss["id"]) == []


def test_export_import_roundtrip_preserves_archived(client):
    p, cols, shipped, keep = seed_board(client)
    client.post(f"/api/projects/{p['id']}/archive-done")

    export = client.get("/api/export").json()
    archived_titles = {c["title"] for c in export["cards"] if c["archived"]}
    assert archived_titles == {"Ship it", "loose end", "wrapped"}

    export["confirm"] = True
    assert client.post("/api/import", json=export).status_code == 200
    assert store.get_card(shipped["id"])["archived"] == 1
    board = client.get(f"/api/projects/{p['id']}/board").json()
    assert [c["title"] for c in board["cards"]] == ["Keep working"]
    data = store.project_overview(p["id"])
    assert [c["title"] for c in data["archived_cards"]] == ["Ship it"]
