def seed(client):
    p = client.post("/api/projects", json={"name": "Garage"}).json()
    col = client.get(f"/api/projects/{p['id']}/board").json()["columns"][0]["id"]
    client.post("/api/cards", json={
        "project_id": p["id"], "column_id": col,
        "title": "Paint the fence", "labels": "outdoor"})
    client.post("/api/cards", json={
        "project_id": p["id"], "column_id": col,
        "title": "Oil change", "description": "5w30 and a filter"})
    return p


def test_search_matches_title_description_labels(client):
    seed(client)
    assert [c["title"] for c in client.get("/api/search", params={"q": "fence"}).json()] == ["Paint the fence"]
    assert [c["title"] for c in client.get("/api/search", params={"q": "5w30"}).json()] == ["Oil change"]
    assert [c["title"] for c in client.get("/api/search", params={"q": "outdoor"}).json()] == ["Paint the fence"]
    assert client.get("/api/search", params={"q": "zzz"}).json() == []
    assert client.get("/api/search", params={"q": "  "}).json() == []


def test_search_skips_archived(client):
    p = seed(client)
    client.post(f"/api/projects/{p['id']}/archive")
    assert client.get("/api/search", params={"q": "fence"}).json() == []


def test_search_page(client):
    seed(client)
    page = client.get("/search", params={"q": "fence"}).text
    assert "Paint the fence" in page and "Garage" in page


def test_export_import_roundtrip(client):
    p = seed(client)
    export = client.get("/api/export").json()
    assert export["app"] == "projecttracker"
    assert len(export["cards"]) == 2

    # Wipe by importing empty, then restore.
    client.post("/api/import", json={"confirm": True})
    assert client.get("/api/projects").json() == []

    export["confirm"] = True
    counts = client.post("/api/import", json=export).json()
    assert counts["projects"] == 1 and counts["cards"] == 2

    board = client.get(f"/api/projects/{p['id']}/board").json()
    assert [c["title"] for c in board["cards"]] == ["Paint the fence", "Oil change"]
    assert len(board["columns"]) == 4


def test_import_requires_confirm(client):
    assert client.post("/api/import", json={}).status_code == 400
