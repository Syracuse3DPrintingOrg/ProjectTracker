from app.services import store


def make_project(name="Alpha"):
    project = store.create_project(name)
    columns = store.list_columns(project["id"])
    return project, columns


def test_create_project_gets_default_columns():
    project, columns = make_project()
    assert [c["name"] for c in columns] == store.DEFAULT_COLUMNS
    assert columns[-1]["is_done"] == 1
    assert all(c["is_done"] == 0 for c in columns[:-1])


def test_card_ordering_within_column():
    project, columns = make_project()
    col = columns[0]["id"]
    a = store.create_card(project["id"], col, "A")
    b = store.create_card(project["id"], col, "B")
    c = store.create_card(project["id"], col, "C")
    assert [x["title"] for x in store.list_cards(project["id"])] == ["A", "B", "C"]

    store.move_card(c["id"], col, 0)
    cards = store.list_cards(project["id"])
    assert [x["title"] for x in cards] == ["C", "A", "B"]
    assert [x["position"] for x in cards] == [0, 1, 2]

    store.move_card(a["id"], col, 99)  # clamped to the end
    assert [x["title"] for x in store.list_cards(project["id"])] == ["C", "B", "A"]
    assert b["id"] and a["id"]


def test_move_card_across_columns_renumbers_both():
    project, columns = make_project()
    src, dst = columns[0]["id"], columns[1]["id"]
    a = store.create_card(project["id"], src, "A")
    b = store.create_card(project["id"], src, "B")
    d = store.create_card(project["id"], dst, "D")

    store.move_card(a["id"], dst, 0)
    cards = {c["title"]: c for c in store.list_cards(project["id"])}
    assert cards["A"]["column_id"] == dst
    assert cards["A"]["position"] == 0
    assert cards["D"]["position"] == 1
    assert cards["B"]["position"] == 0  # source column closed the gap
    assert d["id"] and b["id"]


def test_move_card_to_other_project_column_is_refused():
    project, columns = make_project()
    other, other_columns = make_project("Beta")
    card = store.create_card(project["id"], columns[0]["id"], "A")
    assert store.move_card(card["id"], other_columns[0]["id"], 0) is None
    assert store.get_card(card["id"])["column_id"] == columns[0]["id"]
    assert other["id"]


def test_today_list_and_ordering():
    project, columns = make_project()
    col = columns[0]["id"]
    a = store.create_card(project["id"], col, "A")
    b = store.create_card(project["id"], col, "B")
    store.set_today(a["id"], True)
    store.set_today(b["id"], True, position=0)
    today = store.list_today()
    assert [t["title"] for t in today] == ["B", "A"]
    assert today[0]["project_name"] == "Alpha"

    store.set_today(b["id"], False)
    assert [t["title"] for t in store.list_today()] == ["A"]


def test_clear_done_today_only_drops_done_columns():
    project, columns = make_project()
    todo, done = columns[0]["id"], columns[-1]["id"]
    a = store.create_card(project["id"], todo, "A")
    b = store.create_card(project["id"], done, "B")
    store.set_today(a["id"], True)
    store.set_today(b["id"], True)
    assert store.clear_done_today() == 1
    assert [t["title"] for t in store.list_today()] == ["A"]


def test_delete_column_refuses_when_not_empty():
    project, columns = make_project()
    col = columns[0]["id"]
    store.create_card(project["id"], col, "A")
    assert store.delete_column(col) is False
    empty = store.create_column(project["id"], "Empty")
    assert store.delete_column(empty["id"]) is True


def test_move_column_reorders():
    project, columns = make_project()
    ids = [c["id"] for c in columns]
    store.move_column(ids[-1], 0)
    assert [c["id"] for c in store.list_columns(project["id"])][0] == ids[-1]


def test_delete_project_cascades():
    project, columns = make_project()
    card = store.create_card(project["id"], columns[0]["id"], "A")
    store.delete_project(project["id"])
    assert store.get_card(card["id"]) is None
    assert store.list_columns(project["id"]) == []
