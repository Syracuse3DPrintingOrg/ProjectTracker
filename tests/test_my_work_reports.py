from app.services import store, users


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )


def seed(client):
    users.create_user("dan", "hunter2", "admin")
    users.create_user("kid", "letmein", "member")
    login(client, "dan", "hunter2")
    p = client.post("/api/projects", json={"name": "Farm"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    return p, cols


def test_my_work_lists_only_my_open_cards(client):
    p, cols = seed(client)
    names = client.get("/api/assignees").json()
    dan = next(u for u in names if u["username"] == "dan")
    kid = next(u for u in names if u["username"] == "kid")

    mine = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "Mine",
        "due_date": "2026-08-01"}).json()
    client.patch(f"/api/cards/{mine['id']}", json={"assignee_id": dan["id"]})
    theirs = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "Theirs"}).json()
    client.patch(f"/api/cards/{theirs['id']}", json={"assignee_id": kid["id"]})
    done = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[-1]["id"], "title": "Done one"}).json()
    client.patch(f"/api/cards/{done['id']}", json={"assignee_id": dan["id"]})

    work = store.my_work(dan["id"])
    assert [c["title"] for c in work] == ["Mine"]

    page = client.get("/my").text
    assert "Mine" in page and "Theirs" not in page and "Done one" not in page
    assert "1 open card" in page


def test_my_page_redirects_anonymous(client):
    assert client.get("/my", follow_redirects=False).status_code == 303


def test_project_report_shape(client):
    p, cols = seed(client)
    open_card = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "Open"}).json()
    finished = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "Finish me"}).json()
    client.post(f"/api/cards/{finished['id']}/move",
                json={"column_id": cols[-1]["id"], "position": 0})

    report = store.project_report(p["id"])
    assert len(report["weeks"]) == 8
    assert report["weeks"][-1]["done"] == 1  # finished this week
    assert report["peak"] == 1
    assert report["avg_open_age_days"] == 0
    by_name = {c["name"]: c["n"] for c in report["columns"]}
    assert by_name["Done"] == 1 and by_name["Backlog"] == 1
    assert open_card["id"]


def test_overview_page_shows_reports(client):
    p, cols = seed(client)
    client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "Open"})
    page = client.get(f"/project/{p['id']}/overview").text
    assert "Finished per week" in page
    assert "Open cards average" in page
