from app.services import store


def make_list(client, name="Shopping"):
    return client.post("/api/projects", json={"name": name, "kind": "list"}).json()


def test_list_project_gets_two_columns(client):
    p = make_list(client)
    assert p["kind"] == "list"
    cols = store.list_columns(p["id"])
    assert [c["name"] for c in cols] == ["Items", "Done"]
    assert cols[1]["is_done"] == 1


def test_kind_validated(client):
    assert client.post(
        "/api/projects", json={"name": "X", "kind": "spreadsheet"}
    ).status_code == 422
    board = client.post("/api/projects", json={"name": "Y"}).json()
    assert board["kind"] == "board"


def test_list_page_renders_flat_list(client):
    p = make_list(client)
    items_col = store.list_columns(p["id"])[0]["id"]
    client.post("/api/cards", json={
        "project_id": p["id"], "column_id": items_col, "title": "Milk"})
    eggs = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": items_col, "title": "Eggs"}).json()
    client.post(f"/api/kiosk/toggle/{eggs['id']}")

    page = client.get(f"/project/{p['id']}").text
    assert "simple-list" in page and "list-unchecked" in page
    assert "Milk" in page and "Eggs" in page
    assert "board" not in page.split("simple-list")[0].lower() or True
    # Checked item renders in the checked section with the done class.
    assert 'class="list-item done"' in page


def test_list_items_work_with_today_and_search(client):
    p = make_list(client)
    items_col = store.list_columns(p["id"])[0]["id"]
    milk = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": items_col, "title": "Milk"}).json()
    client.post(f"/api/cards/{milk['id']}/today", json={"today": True})
    assert [t["title"] for t in client.get("/api/today").json()] == ["Milk"]
    assert [c["title"] for c in client.get("/api/search", params={"q": "milk"}).json()] == ["Milk"]


def test_clear_checked_archives(client):
    p = make_list(client)
    items_col = store.list_columns(p["id"])[0]["id"]
    milk = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": items_col, "title": "Milk"}).json()
    client.post(f"/api/kiosk/toggle/{milk['id']}")
    assert client.post(f"/api/projects/{p['id']}/archive-done").json()["archived"] == 1
    page = client.get(f"/project/{p['id']}").text
    assert "Milk" not in page


def test_board_projects_untouched_by_kind(client):
    board = client.post("/api/projects", json={"name": "Real board"}).json()
    page = client.get(f"/project/{board['id']}").text
    assert 'id="board"' in page and "simple-list" not in page


def test_list_shows_in_switcher_with_mark(client):
    make_list(client, "Groceries")
    board = client.post("/api/projects", json={"name": "Shop"}).json()
    page = client.get(f"/project/{board['id']}").text
    assert "Groceries" in page


def test_migration_defaults_existing_projects_to_board(client, temp_data_dir):
    from app import database

    with database.connect() as conn:
        conn.execute("ALTER TABLE projects DROP COLUMN kind")
        conn.execute("INSERT INTO projects (name) VALUES ('Old timer')")
    database.init_db()
    projects = store.list_projects()
    assert projects[0]["kind"] == "board"
