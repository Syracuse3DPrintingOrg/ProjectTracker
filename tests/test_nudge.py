from app import database
from app.services import store


def seed(client, name, cards=1):
    p = client.post("/api/projects", json={"name": name}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    for i in range(cards):
        client.post("/api/cards", json={
            "project_id": p["id"], "column_id": cols[0]["id"], "title": f"c{i}"})
    return p, cols


def _age_project_cards(project_id, days):
    with database.connect() as conn:
        conn.execute(
            "UPDATE cards SET updated_at = datetime('now', ?) WHERE project_id = ?",
            (f"-{days} days", project_id),
        )


def test_project_status_updates(client):
    p, _ = seed(client, "Garage")
    updated = client.patch(f"/api/projects/{p['id']}", json={"status": "buried"}).json()
    assert updated["status"] == "buried"
    assert client.patch(
        f"/api/projects/{p['id']}", json={"status": "distracted"}
    ).status_code == 422
    # Rename still works through the same endpoint.
    assert client.patch(
        f"/api/projects/{p['id']}", json={"name": "Garage 2"}
    ).json()["name"] == "Garage 2"


def test_nudge_lists_stale_active_projects(client):
    a, _ = seed(client, "Old", cards=3)
    b, _ = seed(client, "Fresh", cards=1)
    _age_project_cards(a["id"], 10)

    nudge = client.get("/api/nudge").json()
    assert [n["name"] for n in nudge] == ["Old", "Fresh"]
    assert nudge[0]["open_cards"] == 3
    assert nudge[0]["days_quiet"] >= 9


def test_nudge_excludes_buried_cracked_archived_and_current(client):
    a, _ = seed(client, "Buried", cards=1)
    b, _ = seed(client, "Cracked", cards=1)
    c, _ = seed(client, "Archived", cards=1)
    d, _ = seed(client, "Current", cards=1)
    client.patch(f"/api/projects/{a['id']}", json={"status": "buried"})
    client.patch(f"/api/projects/{b['id']}", json={"status": "cracked"})
    client.post(f"/api/projects/{c['id']}/archive")

    assert [n["name"] for n in client.get("/api/nudge").json()] == ["Current"]
    assert client.get("/api/nudge", params={"exclude": d["id"]}).json() == []


def test_nudge_ignores_projects_with_all_cards_done(client):
    p, cols = seed(client, "Finished", cards=1)
    card = client.get(f"/api/projects/{p['id']}/board").json()["cards"][0]
    client.post(
        f"/api/cards/{card['id']}/move",
        json={"column_id": cols[-1]["id"], "position": 0},
    )
    assert client.get("/api/nudge").json() == []


def test_status_survives_export_import(client):
    p, _ = seed(client, "Garage")
    client.patch(f"/api/projects/{p['id']}", json={"status": "buried"})
    export = client.get("/api/export").json()
    export["confirm"] = True
    client.post("/api/import", json=export)
    assert store.get_project(p["id"])["status"] == "buried"


def test_status_migration_on_existing_db(temp_data_dir):
    # Simulate a pre-0.6 database: drop the status column, then init again.
    with database.connect() as conn:
        conn.execute("ALTER TABLE projects DROP COLUMN status")
    database.init_db()
    p = store.create_project("Old data")
    assert p["status"] == "active"
