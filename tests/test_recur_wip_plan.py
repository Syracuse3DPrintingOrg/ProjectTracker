from datetime import date, timedelta

from app.services import llm, store


def seed(client):
    p = client.post("/api/projects", json={"name": "Chores"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    return p, cols


def test_recurring_card_respawns_on_done(client):
    p, cols = seed(client)
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[1]["id"],
        "title": "Water plants", "recur_days": 7,
        "description": "- [x] front room\n- [ ] kitchen",
    }).json()
    client.post(f"/api/cards/{card['id']}/today", json={"today": True})

    moved = client.post(
        f"/api/cards/{card['id']}/move",
        json={"column_id": cols[-1]["id"], "position": 0},
    ).json()

    # Respawned: back in the first column, checklist reset, off Today,
    # due a week out.
    assert moved["column_id"] == cols[0]["id"]
    assert moved["description"] == "- [ ] front room\n- [ ] kitchen"
    assert moved["today"] == 0
    assert moved["due_date"] == (date.today() + timedelta(days=7)).isoformat()


def test_non_recurring_card_stays_done(client):
    p, cols = seed(client)
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "One-off"}).json()
    moved = client.post(
        f"/api/cards/{card['id']}/move",
        json={"column_id": cols[-1]["id"], "position": 0},
    ).json()
    assert moved["column_id"] == cols[-1]["id"]


def test_recurring_card_can_move_within_done_without_respawn(client):
    p, cols = seed(client)
    done = cols[-1]["id"]
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": done, "title": "weird start",
        "recur_days": 7}).json()
    # Reordering inside the done column is not a completion.
    moved = client.post(
        f"/api/cards/{card['id']}/move", json={"column_id": done, "position": 0}
    ).json()
    assert moved["column_id"] == done


def test_wip_limit_roundtrip(client):
    p, cols = seed(client)
    client.patch(f"/api/columns/{cols[2]['id']}", json={"wip_limit": 3})
    board = client.get(f"/api/projects/{p['id']}/board").json()
    assert board["columns"][2]["wip_limit"] == 3
    assert client.patch(
        f"/api/columns/{cols[2]['id']}", json={"wip_limit": 200}
    ).status_code == 422

    export = client.get("/api/export").json()
    export["confirm"] = True
    client.post("/api/import", json=export)
    board = client.get(f"/api/projects/{p['id']}/board").json()
    assert board["columns"][2]["wip_limit"] == 3


def test_recur_survives_export_import(client):
    p, cols = seed(client)
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"],
        "title": "Trash night", "recur_days": 7}).json()
    export = client.get("/api/export").json()
    export["confirm"] = True
    client.post("/api/import", json=export)
    assert store.get_card(card["id"])["recur_days"] == 7


def test_plan_candidates_excludes_done_today_and_inactive(client):
    p, cols = seed(client)
    a = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "A",
        "due_date": "2026-07-10"}).json()
    b = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "B"}).json()
    on_today = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "C"}).json()
    client.post(f"/api/cards/{on_today['id']}/today", json={"today": True})
    done = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[-1]["id"], "title": "D"}).json()

    names = [c["title"] for c in store.plan_candidates()]
    assert names == ["A", "B"]  # due-dated first, no today/done cards
    assert a["id"] and b["id"] and done["id"]


def test_plan_today_validates_ids(monkeypatch):
    candidates = [
        {"id": 1, "title": "A", "project_name": "P", "due_date": "", "priority": 2},
        {"id": 2, "title": "B", "project_name": "P", "due_date": "", "priority": 1},
    ]
    monkeypatch.setattr(llm, "complete", lambda prompt, settings=None: "[2, 9, 1, 2, \"x\"]")
    assert llm.plan_today(candidates, "2026-07-16") == [2, 1]

    monkeypatch.setattr(llm, "complete", lambda prompt, settings=None: '{"nope": 1}')
    try:
        llm.plan_today(candidates, "2026-07-16")
        assert False, "expected LLMError"
    except llm.LLMError:
        pass


def test_plan_day_endpoint(client, monkeypatch):
    p, cols = seed(client)
    card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "A"}).json()

    resp = client.post("/api/assist/plan-day")
    assert resp.status_code == 400  # no provider configured

    monkeypatch.setattr(llm, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(llm, "plan_today", lambda cands, today: [card["id"]])
    data = client.post("/api/assist/plan-day").json()
    assert [c["id"] for c in data["added"]] == [card["id"]]
    assert client.get("/api/today").json()[0]["id"] == card["id"]


def test_migration_adds_new_columns(temp_data_dir):
    from app import database

    with database.connect() as conn:
        conn.execute("ALTER TABLE cards DROP COLUMN recur_days")
        conn.execute("ALTER TABLE columns DROP COLUMN wip_limit")
    database.init_db()
    p = store.create_project("Old")
    col = store.list_columns(p["id"])[0]
    assert col["wip_limit"] == 0
    card = store.create_card(p["id"], col["id"], "A")
    assert card["recur_days"] == 0
