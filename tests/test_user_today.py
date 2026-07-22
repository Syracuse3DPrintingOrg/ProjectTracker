"""Personal Today lists living alongside the shared one.

The shared list stays in cards.today/today_position (so older installs
and the ESP32 payload keep working); personal picks live in user_today.
"""

from app import config
from app.services import api_keys, llm, store, users


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )


def make_board():
    p = store.create_project("Chores")
    return p, store.list_columns(p["id"])


def seed_api(client):
    """One card on the shared list, one on the signed-in user's list."""
    p = client.post("/api/projects", json={"name": "Chores"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    a = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"],
        "title": "Shared card"}).json()
    b = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"],
        "title": "Mine card"}).json()
    client.post(f"/api/cards/{a['id']}/today", json={"today": True})
    client.post(f"/api/cards/{b['id']}/today", json={"today": True, "list": "mine"})
    return p, cols, a, b


# ---- store level ----

def test_personal_list_isolated_from_shared(temp_data_dir):
    dan = users.create_user("dan", "hunter2", "admin")
    p, cols = make_board()
    a = store.create_card(p["id"], cols[0]["id"], "A")
    b = store.create_card(p["id"], cols[0]["id"], "B")

    store.set_today(a["id"], True)                    # shared
    store.set_today(b["id"], True, owner=dan["id"])   # personal
    assert [t["title"] for t in store.list_today()] == ["A"]
    assert [t["title"] for t in store.list_today(owner=dan["id"])] == ["B"]

    # Add and reorder inside the personal list; the shared list stays put.
    store.set_today(a["id"], True, owner=dan["id"])
    assert [t["title"] for t in store.list_today(owner=dan["id"])] == ["B", "A"]
    store.set_today(a["id"], True, position=0, owner=dan["id"])
    assert [t["title"] for t in store.list_today(owner=dan["id"])] == ["A", "B"]
    assert [t["title"] for t in store.list_today()] == ["A"]

    # Removing from the personal list leaves the shared flag alone.
    store.set_today(a["id"], False, owner=dan["id"])
    assert [t["title"] for t in store.list_today(owner=dan["id"])] == ["B"]
    assert [t["title"] for t in store.list_today()] == ["A"]

    # Unknown cards are refused, same as the shared path.
    assert store.set_today(999, True, owner=dan["id"]) is None


def test_two_users_do_not_share_a_personal_list(temp_data_dir):
    dan = users.create_user("dan", "hunter2", "admin")
    kid = users.create_user("kid", "hunter2", "member")
    p, cols = make_board()
    a = store.create_card(p["id"], cols[0]["id"], "A")
    store.set_today(a["id"], True, owner=dan["id"])
    assert store.list_today(owner=kid["id"]) == []


def test_clear_done_per_list(temp_data_dir):
    dan = users.create_user("dan", "hunter2", "admin")
    p, cols = make_board()
    a = store.create_card(p["id"], cols[0]["id"], "A")
    b = store.create_card(p["id"], cols[0]["id"], "B")
    store.set_today(a["id"], True)
    store.set_today(a["id"], True, owner=dan["id"])
    store.set_today(b["id"], True, owner=dan["id"])
    store.move_card(a["id"], cols[-1]["id"], 0)  # A is finished

    # Clearing the personal list touches only it.
    assert store.clear_done_today(owner=dan["id"]) == 1
    assert [t["title"] for t in store.list_today(owner=dan["id"])] == ["B"]
    assert [t["title"] for t in store.list_today()] == ["A"]

    # And the shared clear leaves the personal list alone.
    assert store.clear_done_today() == 1
    assert store.list_today() == []
    assert [t["title"] for t in store.list_today(owner=dan["id"])] == ["B"]


def test_deleting_a_card_drops_it_from_personal_lists(temp_data_dir):
    dan = users.create_user("dan", "hunter2", "admin")
    p, cols = make_board()
    a = store.create_card(p["id"], cols[0]["id"], "A")
    store.set_today(a["id"], True, owner=dan["id"])
    store.delete_card(a["id"])
    assert store.list_today(owner=dan["id"]) == []


def test_migration_creates_user_today_and_keeps_shared_data(temp_data_dir):
    from app import database

    with database.connect() as conn:
        conn.execute("DROP TABLE user_today")
    database.init_db()  # an older database picks the table up

    dan = users.create_user("dan", "hunter2", "admin")
    p, cols = make_board()
    a = store.create_card(p["id"], cols[0]["id"], "A")
    store.set_today(a["id"], True)
    store.set_today(a["id"], True, owner=dan["id"])
    assert store.get_card(a["id"])["today"] == 1  # shared columns untouched
    assert [t["title"] for t in store.list_today(owner=dan["id"])] == ["A"]


# ---- API: list selection ----

def test_api_mine_list_for_signed_in_user(client):
    users.create_user("dan", "hunter2", "admin")
    login(client, "dan", "hunter2")
    p, cols, a, b = seed_api(client)

    shared = [t["title"] for t in client.get("/api/today").json()]
    assert shared == ["Shared card"]
    mine = [t["title"] for t in client.get("/api/today", params={"list": "mine"}).json()]
    assert mine == ["Mine card"]

    # Clear finished on "mine" leaves the shared list alone.
    client.post(f"/api/cards/{b['id']}/move",
                json={"column_id": cols[-1]["id"], "position": 0})
    cleared = client.post("/api/today/clear-done", params={"list": "mine"}).json()
    assert cleared["cleared"] == 1
    assert client.get("/api/today", params={"list": "mine"}).json() == []
    assert [t["title"] for t in client.get("/api/today").json()] == ["Shared card"]


def test_unauthenticated_mine_falls_back_to_shared(client):
    # An open instance has nobody to own a personal list.
    p = client.post("/api/projects", json={"name": "Chores"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    a = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "A"}).json()
    client.post(f"/api/cards/{a['id']}/today", json={"today": True, "list": "mine"})
    assert [t["title"] for t in client.get("/api/today").json()] == ["A"]
    mine = client.get("/api/today", params={"list": "mine"}).json()
    assert [t["title"] for t in mine] == ["A"]


# ---- displays and kiosk ----

def test_display_list_param_selects_personal_list(client):
    dan = users.create_user("dan", "hunter2", "admin")
    login(client, "dan", "hunter2")
    seed_api(client)
    chosen = "user:%d" % dan["id"]

    data = client.get("/api/kiosk/data").json()
    assert [t["title"] for t in data["tasks"]] == ["Shared card"]
    data = client.get("/api/kiosk/data", params={"list": chosen}).json()
    assert [t["title"] for t in data["tasks"]] == ["Mine card"]

    # Bad or unknown user ids fall back to the shared list.
    for bad in ("user:9999", "user:banana", "nonsense"):
        data = client.get("/api/kiosk/data", params={"list": bad}).json()
        assert [t["title"] for t in data["tasks"]] == ["Shared card"]

    # The ESP32 payload honors the same choice.
    data = client.get("/api/display", params={"list": chosen}).json()
    assert [t["title"] for t in data["tasks"]] == ["Mine card"]


def test_registered_display_carries_list_choice(client):
    dan = users.create_user("dan", "hunter2", "admin")
    login(client, "dan", "hunter2")
    seed_api(client)
    chosen = "user:%d" % dan["id"]

    d = client.post("/api/displays", json={
        "name": "Dan's screen", "kind": "browser",
        "params": {"list": chosen}}).json()
    assert ("list=user%%3A%d" % dan["id"]) in d["url"]
    page = client.get(f"/kiosk?d={d['id']}").text
    assert chosen in page  # the kiosk polls with this list

    esp = client.post("/api/displays", json={
        "name": "Desk ESP", "kind": "esp32", "params": {"list": chosen}}).json()
    assert ("list=user%%3A%d" % dan["id"]) in esp["api_url"]

    # A wall screen with just the display token still gets the named list.
    config.save_settings({"display_token": "wall"})
    client.get("/logout")
    data = client.get(
        "/api/kiosk/data", params={"token": "wall", "list": chosen}
    ).json()
    assert [t["title"] for t in data["tasks"]] == ["Mine card"]


# ---- plan my day ----

def test_plan_day_into_personal_list(client, monkeypatch):
    users.create_user("dan", "hunter2", "admin")
    login(client, "dan", "hunter2")
    p = client.post("/api/projects", json={"name": "Chores"}).json()
    cols = client.get(f"/api/projects/{p['id']}/board").json()["columns"]
    a = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "A"}).json()
    b = client.post("/api/cards", json={
        "project_id": p["id"], "column_id": cols[0]["id"], "title": "B"}).json()
    client.post(f"/api/cards/{b['id']}/today", json={"today": True, "list": "mine"})

    seen = {}

    def fake_plan(cands, today):
        seen["ids"] = [c["id"] for c in cands]
        return [a["id"]]

    monkeypatch.setattr(llm, "is_configured", lambda settings=None: True)
    monkeypatch.setattr(llm, "plan_today", fake_plan)

    data = client.post("/api/assist/plan-day", json={"list": "mine"}).json()
    assert [c["id"] for c in data["added"]] == [a["id"]]
    assert b["id"] not in seen["ids"]  # already on the target list

    mine = [t["title"] for t in client.get("/api/today", params={"list": "mine"}).json()]
    assert mine == ["B", "A"]
    assert client.get("/api/today").json() == []  # shared list untouched


# ---- roles and keys ----

def test_viewer_reads_any_list_but_cannot_modify(client):
    dan = users.create_user("dan", "hunter2", "admin")
    users.create_user("guest", "viewerpw", "viewer")
    login(client, "dan", "hunter2")
    p, cols, a, b = seed_api(client)
    client.get("/logout")

    login(client, "guest", "viewerpw")
    assert [t["title"] for t in client.get("/api/today").json()] == ["Shared card"]
    kiosk = client.get(
        "/api/kiosk/data", params={"list": "user:%d" % dan["id"]}
    ).json()
    assert [t["title"] for t in kiosk["tasks"]] == ["Mine card"]
    assert client.get("/api/today", params={"list": "mine"}).json() == []
    assert client.post(
        f"/api/cards/{a['id']}/today", json={"today": True, "list": "mine"}
    ).status_code == 403
    assert client.post(
        "/api/today/clear-done", params={"list": "mine"}
    ).status_code == 403


def test_api_key_mine_falls_back_to_shared(client):
    users.create_user("dan", "hunter2", "admin")
    login(client, "dan", "hunter2")
    p, cols, a, b = seed_api(client)
    client.get("/logout")

    key = api_keys.create_key("ha", "member")["token"]
    headers = {"X-API-Key": key}
    titles = [t["title"] for t in client.get(
        "/api/today", params={"list": "mine"}, headers=headers).json()]
    assert titles == ["Shared card"]  # a key has no user behind it

    # Writing with "mine" from a key lands on the shared list too.
    resp = client.post(
        f"/api/cards/{b['id']}/today",
        json={"today": True, "list": "mine"}, headers=headers)
    assert resp.status_code == 200
    titles = [t["title"] for t in client.get("/api/today", headers=headers).json()]
    assert titles == ["Shared card", "Mine card"]
