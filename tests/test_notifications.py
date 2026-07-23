import httpx
import pytest

from app.services import notifications, rbac, users


def login(client, username, password):
    return client.post(
        "/login",
        data={"username": username, "password": password, "next": "/"},
        follow_redirects=False,
    )


def make_users():
    users.create_user("boss", "adminpw", "admin")
    users.create_user("worker", "memberpw", "member")
    users.create_user("guest", "viewerpw", "viewer")
    return {u["username"]: u for u in users.list_users()}


def make_card(client, title="Fix the door"):
    proj = client.post("/api/projects", json={"name": "House"}).json()
    board = client.get(f"/api/projects/{proj['id']}/board").json()
    card = client.post(
        "/api/cards",
        json={
            "project_id": proj["id"],
            "column_id": board["columns"][0]["id"],
            "title": title,
        },
    ).json()
    return proj, card


# ---- mention parsing ----

def test_mention_targets_matching(temp_data_dir):
    who = make_users()
    assert notifications.mention_targets("@worker take a look") == [
        who["worker"]["id"]
    ]
    # Case-insensitive.
    assert notifications.mention_targets("hey @WoRkEr") == [who["worker"]["id"]]
    # Unknown users are ignored, known ones still land.
    assert notifications.mention_targets("@nobody and @boss") == [who["boss"]["id"]]
    # Adjacent punctuation does not hide a mention.
    assert notifications.mention_targets("ping @worker, then @boss.") == [
        who["worker"]["id"],
        who["boss"]["id"],
    ]
    # No duplicates, order of first appearance.
    assert notifications.mention_targets("@guest @boss @guest") == [
        who["guest"]["id"],
        who["boss"]["id"],
    ]
    assert notifications.mention_targets("no mentions here") == []
    assert notifications.mention_targets("") == []


def test_mention_targets_skips_disabled_users(temp_data_dir):
    who = make_users()
    users.update_user(who["worker"]["id"], disabled=True)
    assert notifications.mention_targets("@worker @guest") == [who["guest"]["id"]]


# ---- assignment trigger ----

def test_assignment_notifies_the_assignee(client):
    who = make_users()
    login(client, "boss", "adminpw")
    proj, card = make_card(client)
    resp = client.patch(
        f"/api/cards/{card['id']}", json={"assignee_id": who["worker"]["id"]}
    )
    assert resp.status_code == 200
    rows = notifications.list_for_user(who["worker"]["id"])
    assert len(rows) == 1
    assert rows[0]["text"] == "boss assigned you: Fix the door"
    assert rows[0]["url"] == f"/project/{proj['id']}"
    assert rows[0]["read"] == 0


def test_self_assignment_stays_quiet(client):
    who = make_users()
    login(client, "boss", "adminpw")
    proj, card = make_card(client)
    resp = client.patch(
        f"/api/cards/{card['id']}", json={"assignee_id": who["boss"]["id"]}
    )
    assert resp.status_code == 200
    assert notifications.list_for_user(who["boss"]["id"]) == []


def test_reassigning_the_same_user_does_not_repeat(client):
    who = make_users()
    login(client, "boss", "adminpw")
    proj, card = make_card(client)
    client.patch(f"/api/cards/{card['id']}", json={"assignee_id": who["worker"]["id"]})
    client.patch(f"/api/cards/{card['id']}", json={"assignee_id": who["worker"]["id"]})
    assert len(notifications.list_for_user(who["worker"]["id"])) == 1


# ---- comment trigger ----

def test_comment_notifies_assignee_and_mentions_once_each(client):
    who = make_users()
    login(client, "boss", "adminpw")
    proj, card = make_card(client)
    client.patch(f"/api/cards/{card['id']}", json={"assignee_id": who["worker"]["id"]})
    notifications.mark_read(who["worker"]["id"])  # clear the assignment note

    resp = client.post(
        f"/api/cards/{card['id']}/comments",
        json={"text": "@worker @guest @boss the hinge is stripped"},
    )
    assert resp.status_code == 201

    # The assignee who is also mentioned gets exactly one notification.
    worker_rows = notifications.list_for_user(who["worker"]["id"], unread_only=True)
    assert len(worker_rows) == 1
    assert worker_rows[0]["text"] == (
        "boss commented on Fix the door: @worker @guest @boss the hinge is stripped"
    )
    assert worker_rows[0]["url"] == f"/project/{proj['id']}"
    # A mentioned bystander gets one.
    assert len(notifications.list_for_user(who["guest"]["id"])) == 1
    # The commenter never hears about their own comment.
    assert notifications.list_for_user(who["boss"]["id"]) == []


def test_comment_truncates_long_text_in_the_notification(client):
    who = make_users()
    login(client, "boss", "adminpw")
    proj, card = make_card(client)
    client.patch(f"/api/cards/{card['id']}", json={"assignee_id": who["worker"]["id"]})
    notifications.mark_read(who["worker"]["id"])
    long_text = "x" * 300
    client.post(f"/api/cards/{card['id']}/comments", json={"text": long_text})
    rows = notifications.list_for_user(who["worker"]["id"], unread_only=True)
    assert rows[0]["text"].endswith("x" * 80)
    assert ("x" * 81) not in rows[0]["text"]


# ---- the inbox API ----

def test_rbac_lets_every_role_at_their_own_inbox():
    assert rbac.allowed("viewer", "GET", "/api/notifications")
    assert rbac.allowed("viewer", "POST", "/api/notifications/read")
    assert rbac.allowed("member", "POST", "/api/notifications/read")
    assert rbac.allowed("viewer", "POST", "/api/account/webhook")


def test_viewer_reads_and_clears_only_their_own(client):
    who = make_users()
    notifications.notify(who["guest"]["id"], "for guest", "/project/1")
    notifications.notify(who["worker"]["id"], "for worker", "/project/2")

    login(client, "guest", "viewerpw")
    data = client.get("/api/notifications").json()
    assert data["unread"] == 1
    assert [n["text"] for n in data["items"]] == ["for guest"]

    # Trying to mark the other user's row does nothing to it.
    worker_row = notifications.list_for_user(who["worker"]["id"])[0]
    resp = client.post("/api/notifications/read", json={"ids": [worker_row["id"]]})
    assert resp.status_code == 200
    assert resp.json()["marked"] == 0
    assert notifications.unread_count(who["worker"]["id"]) == 1

    # Marking their own works.
    resp = client.post("/api/notifications/read", json={"all": True})
    assert resp.status_code == 200
    assert resp.json()["unread"] == 0
    assert notifications.unread_count(who["guest"]["id"]) == 0


def test_unread_count_and_ordering(client):
    who = make_users()
    for i in range(3):
        notifications.notify(who["worker"]["id"], f"note {i}", "")
    login(client, "worker", "memberpw")
    data = client.get("/api/notifications").json()
    assert data["unread"] == 3
    assert [n["text"] for n in data["items"]] == ["note 2", "note 1", "note 0"]

    first = data["items"][0]["id"]
    resp = client.post("/api/notifications/read", json={"ids": [first]})
    assert resp.json() == {"marked": 1, "unread": 2}
    unread = client.get("/api/notifications?unread_only=true").json()
    assert data["unread"] == 3 and unread["unread"] == 2
    assert [n["text"] for n in unread["items"]] == ["note 1", "note 0"]


def test_inbox_needs_a_signed_in_user(client):
    assert client.get("/api/notifications").status_code == 401
    assert (
        client.post("/api/notifications/read", json={"all": True}).status_code == 401
    )


def test_read_endpoint_requires_ids_or_all(client):
    make_users()
    login(client, "worker", "memberpw")
    assert client.post("/api/notifications/read", json={}).status_code == 422


# ---- webhook push ----

def test_ntfy_webhook_posts_raw_text_with_title(temp_data_dir, monkeypatch):
    who = make_users()
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200)

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    notifications.set_webhook(who["worker"]["id"], "https://ntfy.sh/sq-worker")
    notifications.notify(who["worker"]["id"], "hello there", "/project/1")

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == "https://ntfy.sh/sq-worker"
    assert kwargs["content"] == b"hello there"
    assert kwargs["headers"]["X-Title"] == "SQ"
    assert kwargs["timeout"] == 3.0
    # The inbox row exists regardless of the push.
    assert notifications.unread_count(who["worker"]["id"]) == 1


def test_hook_style_webhook_posts_json(temp_data_dir, monkeypatch):
    who = make_users()
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return httpx.Response(200)

    monkeypatch.setattr(notifications.httpx, "post", fake_post)
    notifications.set_webhook(
        who["worker"]["id"], "https://example.com/services/myhook"
    )
    notifications.notify(who["worker"]["id"], "hello there", "/project/1")

    assert calls[0][1]["json"] == {"text": "hello there", "url": "/project/1"}


def test_webhook_failure_is_swallowed(temp_data_dir, monkeypatch):
    who = make_users()

    def broken_post(url, **kwargs):
        raise httpx.ConnectError("nobody home")

    monkeypatch.setattr(notifications.httpx, "post", broken_post)
    notifications.set_webhook(who["worker"]["id"], "https://ntfy.sh/dead-topic")
    notifications.notify(who["worker"]["id"], "still lands", "/project/1")
    assert notifications.unread_count(who["worker"]["id"]) == 1


def test_no_webhook_means_no_post(temp_data_dir, monkeypatch):
    who = make_users()

    def fail_if_called(url, **kwargs):  # pragma: no cover - the assert IS the test
        pytest.fail("no webhook configured, nothing should be posted")

    monkeypatch.setattr(notifications.httpx, "post", fail_if_called)
    notifications.notify(who["worker"]["id"], "quiet push", "")
    assert notifications.unread_count(who["worker"]["id"]) == 1


# ---- account webhook setting ----

def test_account_webhook_save_and_clear(client):
    who = make_users()
    login(client, "guest", "viewerpw")

    resp = client.post(
        "/api/account/webhook", json={"webhook_url": "https://ntfy.sh/mine"}
    )
    assert resp.status_code == 200
    assert users.get_user(who["guest"]["id"])["webhook_url"] == "https://ntfy.sh/mine"

    # Junk schemes are refused.
    resp = client.post("/api/account/webhook", json={"webhook_url": "ftp://x"})
    assert resp.status_code == 422

    # Blank turns push off.
    resp = client.post("/api/account/webhook", json={"webhook_url": ""})
    assert resp.status_code == 200
    assert users.get_user(who["guest"]["id"])["webhook_url"] == ""


def test_account_page_shows_push_section(client):
    make_users()
    login(client, "worker", "memberpw")
    client.post("/api/account/webhook", json={"webhook_url": "https://ntfy.sh/w"})
    resp = client.get("/account")
    assert resp.status_code == 200
    assert "Push notifications" in resp.text
    assert "https://ntfy.sh/w" in resp.text
