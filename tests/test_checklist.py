from app.services import checklist

DESC = """Prep work first.

- [ ] sand the door
- [x] buy paint
* [ ] tape the trim

Then paint.
"""


def test_parse_checklist():
    items = checklist.parse_checklist(DESC)
    assert [i["text"] for i in items] == ["sand the door", "buy paint", "tape the trim"]
    assert [i["checked"] for i in items] == [False, True, False]


def test_progress():
    assert checklist.progress(DESC) == (1, 3)
    assert checklist.progress("no lists here") == (0, 0)
    assert checklist.progress("") == (0, 0)


def test_toggle_item_preserves_everything_else():
    updated = checklist.toggle_item(DESC, 0, True)
    assert "- [x] sand the door" in updated
    assert "Prep work first." in updated and "Then paint." in updated
    assert updated.endswith("\n")
    assert checklist.progress(updated) == (2, 3)

    unchecked = checklist.toggle_item(updated, 1, False)
    assert "- [ ] buy paint" in unchecked


def test_toggle_item_bad_index():
    assert checklist.toggle_item(DESC, 99, True) is None
    assert checklist.toggle_item("plain text", 0, True) is None


def test_checklist_api(client):
    p = client.post("/api/projects", json={"name": "A"}).json()
    col = client.get(f"/api/projects/{p['id']}/board").json()["columns"][0]["id"]
    card = client.post(
        "/api/cards",
        json={"project_id": p["id"], "column_id": col, "title": "T",
              "description": "- [ ] one\n- [ ] two"},
    ).json()

    updated = client.post(
        f"/api/cards/{card['id']}/checklist", json={"index": 1, "checked": True}
    ).json()
    assert "- [x] two" in updated["description"]

    resp = client.post(
        f"/api/cards/{card['id']}/checklist", json={"index": 5, "checked": True}
    )
    assert resp.status_code == 400

    # Progress travels to the display payload once the card is on Today.
    client.post(f"/api/cards/{card['id']}/today", json={"today": True})
    task = client.get("/api/display").json()["tasks"][0]
    assert task["checklist"] == "1/2"
