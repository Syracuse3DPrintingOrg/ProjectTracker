def make_board(client, name="Alpha"):
    project = client.post("/api/projects", json={"name": name}).json()
    board = client.get(f"/api/projects/{project['id']}/board").json()
    return project, board["columns"]


def test_health(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert data["app"] == "projecttracker"


def test_project_and_card_lifecycle(client):
    project, columns = make_board(client)
    resp = client.post(
        "/api/cards",
        json={
            "project_id": project["id"],
            "column_id": columns[0]["id"],
            "title": "Ship it",
            "priority": 1,
            "due_date": "2026-08-01",
            "labels": "infra, fun",
        },
    )
    assert resp.status_code == 201
    card = resp.json()

    resp = client.post(
        f"/api/cards/{card['id']}/move",
        json={"column_id": columns[2]["id"], "position": 0},
    )
    assert resp.json()["column_id"] == columns[2]["id"]

    resp = client.patch(f"/api/cards/{card['id']}", json={"title": "Shipped"})
    assert resp.json()["title"] == "Shipped"

    assert client.delete(f"/api/cards/{card['id']}").status_code == 204
    assert client.get(f"/api/cards/{card['id']}").status_code == 404


def test_move_to_unknown_column_404s(client):
    project, columns = make_board(client)
    card = client.post(
        "/api/cards",
        json={"project_id": project["id"], "column_id": columns[0]["id"], "title": "A"},
    ).json()
    resp = client.post(
        f"/api/cards/{card['id']}/move", json={"column_id": 9999, "position": 0}
    )
    assert resp.status_code == 404


def test_today_flow(client):
    project, columns = make_board(client)
    card = client.post(
        "/api/cards",
        json={"project_id": project["id"], "column_id": columns[0]["id"], "title": "A"},
    ).json()
    client.post(f"/api/cards/{card['id']}/today", json={"today": True})
    today = client.get("/api/today").json()
    assert [t["id"] for t in today] == [card["id"]]

    display = client.get("/api/display").json()
    assert display["count"] == 1
    assert display["remaining"] == 1
    assert display["tasks"][0]["title"] == "A"
    assert display["tasks"][0]["project"] == "Alpha"
    assert display["tasks"][0]["done"] is False

    # Move it to the done column: remaining drops, clear-done removes it.
    client.post(
        f"/api/cards/{card['id']}/move",
        json={"column_id": columns[-1]["id"], "position": 0},
    )
    display = client.get("/api/display").json()
    assert display["remaining"] == 0
    assert client.post("/api/today/clear-done").json()["cleared"] == 1
    assert client.get("/api/today").json() == []


def test_column_crud(client):
    project, columns = make_board(client)
    col = client.post(
        f"/api/projects/{project['id']}/columns", json={"name": "Review"}
    ).json()
    client.patch(f"/api/columns/{col['id']}", json={"name": "In Review", "position": 1})
    board = client.get(f"/api/projects/{project['id']}/board").json()
    assert board["columns"][1]["name"] == "In Review"

    card = client.post(
        "/api/cards",
        json={"project_id": project["id"], "column_id": col["id"], "title": "A"},
    ).json()
    assert client.delete(f"/api/columns/{col['id']}").status_code == 409
    client.delete(f"/api/cards/{card['id']}")
    assert client.delete(f"/api/columns/{col['id']}").status_code == 200


def test_validation_rejects_empty_title(client):
    project, columns = make_board(client)
    resp = client.post(
        "/api/cards",
        json={"project_id": project["id"], "column_id": columns[0]["id"], "title": ""},
    )
    assert resp.status_code == 422


def test_archive_hides_project(client):
    project, _ = make_board(client)
    client.post(f"/api/projects/{project['id']}/archive")
    assert client.get("/api/projects").json() == []
    assert len(client.get("/api/projects", params={"include_archived": True}).json()) == 1


def test_board_page_renders(client):
    project, _ = make_board(client)
    resp = client.get(f"/project/{project['id']}")
    assert resp.status_code == 200
    assert "Today's Tasks" in resp.text


def test_assist_without_provider_400s(client):
    project, columns = make_board(client)
    card = client.post(
        "/api/cards",
        json={"project_id": project["id"], "column_id": columns[0]["id"], "title": "A"},
    ).json()
    resp = client.post("/api/assist/subtasks", json={"card_id": card["id"]})
    assert resp.status_code == 400
