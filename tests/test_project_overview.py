from app import database
from app.services import store, users


def seed_project(client, name="Treehouse"):
    p = client.post("/api/projects", json={"name": name}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    return p, cols


def make_card(client, p, cols, title):
    return client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": title}).json()


def seed_overview(client):
    """A project with an open card (one done subtask of two), a finished
    card, an attachment, and a comment, all through the API."""
    p, cols = seed_project(client)
    card = make_card(client, p, cols, "Build ladder")
    client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "cut rungs"})
    sub = client.post(f"/api/cards/{card['id']}/subtasks", json={"title": "sand rungs"}).json()
    client.patch(f"/api/subtasks/{sub['id']}", json={"done": True})
    done = make_card(client, p, cols, "Pick the tree")
    client.post(f"/api/cards/{done['id']}/move",
                json={"column_id": cols[-1]["id"], "position": 0})
    att = client.post(
        f"/api/cards/{card['id']}/attachments",
        files={"file": ("plan.txt", b"step one: acquire wood", "text/plain")},
    ).json()
    client.post(f"/api/cards/{card['id']}/comments", json={"text": "ladder first"})
    return p, cols, card, done, att


def test_description_column_migrates_in(temp_data_dir):
    # An older database has no description column; init_db adds it.
    with database.connect() as conn:
        conn.execute("ALTER TABLE projects DROP COLUMN description")
    database.init_db()
    with database.connect() as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(projects)")}
    assert "description" in cols


def test_description_save_and_roundtrip(client):
    p, _ = seed_project(client)
    assert p["description"] == ""
    updated = client.patch(
        f"/api/projects/{p['id']}",
        json={"description": "A fort.\n\nWith snacks."},
    ).json()
    assert updated["description"] == "A fort.\n\nWith snacks."
    assert store.get_project(p["id"])["description"] == "A fort.\n\nWith snacks."
    # Other PATCH fields leave the description alone.
    client.patch(f"/api/projects/{p['id']}", json={"name": "Fort", "status": "buried"})
    after = store.get_project(p["id"])
    assert after["description"] == "A fort.\n\nWith snacks."
    assert after["name"] == "Fort" and after["status"] == "buried"
    # And it rides along in the list endpoint too (SELECT *).
    listed = client.get("/api/projects", params={"include_archived": True}).json()
    assert listed[0]["description"] == "A fort.\n\nWith snacks."


def test_project_overview_store_shape(client):
    p, cols, card, done, att = seed_overview(client)
    data = store.project_overview(p["id"])

    assert [c["title"] for c in data["open_cards"]] == ["Build ladder"]
    open_card = data["open_cards"][0]
    assert open_card["column_name"] == cols[0]["name"]
    assert open_card["assignee"] is None
    assert (open_card["subtasks_done"], open_card["subtasks_total"]) == (1, 2)

    assert [c["title"] for c in data["done_cards"]] == ["Pick the tree"]
    assert data["done_cards"][0]["column_name"] == cols[-1]["name"]

    assert [f["filename"] for f in data["files"]] == ["plan.txt"]
    f = data["files"][0]
    assert f["id"] == att["id"]
    assert f["card_id"] == card["id"] and f["card_title"] == "Build ladder"
    assert f["size"] == len(b"step one: acquire wood")

    # Newest first: the comment landed last.
    assert data["activity"][0]["kind"] == "comment"
    assert data["activity"][0]["text"] == "ladder first"
    assert data["activity"][0]["card_title"] == "Build ladder"
    kinds = {e["kind"] for e in data["activity"]}
    assert {"comment", "created", "moved", "attached"} <= kinds

    assert data["counts"] == {
        "open": 1, "done": 1, "archived": 0, "files": 1, "days_quiet": 0,
    }


def test_overview_assignee_username(client):
    users.create_user("dan", "hunter2", "admin")
    client.post("/login", data={"username": "dan", "password": "hunter2", "next": "/"})
    p, cols = seed_project(client)
    card = make_card(client, p, cols, "Bracket")
    dan = next(u for u in client.get("/api/assignees").json() if u["username"] == "dan")
    client.patch(f"/api/cards/{card['id']}", json={"assignee_id": dan["id"]})
    data = store.project_overview(p["id"])
    assert data["open_cards"][0]["assignee"] == "dan"


def test_overview_page_renders(client):
    p, cols, card, done, att = seed_overview(client)
    client.patch(f"/api/projects/{p['id']}", json={"description": "A fort in a tree."})

    page = client.get(f"/project/{p['id']}/overview")
    assert page.status_code == 200
    text = page.text
    assert "A fort in a tree." in text
    assert "Build ladder" in text and "Pick the tree" in text
    assert "1/2 subtasks" in text
    assert "plan.txt" in text
    assert f'data-attachment-id="{att["id"]}"' in text
    assert "ladder first" in text
    assert "days quiet" in text
    # No auth means full edit rights: the description form is present.
    assert "desc-form" in text
    # The page loads the preview stack and links back to the board.
    assert "preview.js" in text and "stl-viewer.js" in text
    assert f'href="/project/{p["id"]}"' in text

    # The board header links here.
    board = client.get(f"/project/{p['id']}").text
    assert f"/project/{p['id']}/overview" in board


def test_viewer_sees_page_without_description_form(client):
    users.create_user("dan", "hunter2", "admin")
    users.create_user("tv", "viewerpw", "viewer")
    client.post("/login", data={"username": "dan", "password": "hunter2", "next": "/"})
    p, _ = seed_project(client)
    client.patch(f"/api/projects/{p['id']}", json={"description": "Secret fort plans"})
    client.get("/logout")

    client.post("/login", data={"username": "tv", "password": "viewerpw", "next": "/"})
    page = client.get(f"/project/{p['id']}/overview")
    assert page.status_code == 200
    assert "Secret fort plans" in page.text
    assert "desc-form" not in page.text
    # The write itself is refused for viewers as well.
    assert client.patch(
        f"/api/projects/{p['id']}", json={"description": "nope"}
    ).status_code == 403
    assert store.get_project(p["id"])["description"] == "Secret fort plans"


def test_missing_project_redirects_home(client):
    resp = client.get("/project/9999/overview", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
