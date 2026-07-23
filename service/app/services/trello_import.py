"""Turn a Trello board export into a new SQ project.

Trello's JSON export (board menu, Print and export, Export as JSON)
carries the whole board. This maps what SQ can use onto a fresh project:
open lists become statuses, open cards become cards, and checklist items
become subtasks through the same store calls the UI uses. Closed lists
and closed cards are skipped and counted. Everything already in the
tracker is left alone.

Trello exports vary by age and by what the board used, so every key is
optional here; only the basic lists/cards shape is required.
"""

from .. import database
from . import store

# A list named like this becomes the project's done column.
_DONE_NAMES = {"done", "finished", "complete"}

_NOT_TRELLO = (
    "That file does not look like a Trello board export. In Trello, open"
    " the board menu, choose Print and export, then Export as JSON, and"
    " upload that file here."
)


def _pos(item: dict) -> float:
    pos = item.get("pos", 0)
    return pos if isinstance(pos, (int, float)) else 0


def _project_name(data: dict) -> str:
    name = str(data.get("name") or "").strip() or "Imported board"
    taken = {p["name"] for p in store.list_projects(include_archived=True)}
    return name + " (imported)" if name in taken else name


def _build_columns(project_id: int, open_lists: list[dict]) -> dict:
    """Match the created columns to their Trello lists and settle the
    done flags. Returns {trello list id: column id}."""
    if not open_lists:
        # The project was created with just a Done column, already
        # flagged; there are no lists to map cards onto.
        return {}
    columns = store.list_columns(project_id)
    done_flags = [
        str(l.get("name") or "").strip().lower() in _DONE_NAMES
        for l in open_lists
    ]
    if any(done_flags):
        for col, flag in zip(columns, done_flags):
            if bool(col["is_done"]) != flag:
                store.set_column_done(col["id"], flag)
    else:
        # No list reads as finished, so give the project a Done column;
        # completed checklist items and finished cards need a home.
        for col in columns:
            if col["is_done"]:
                store.set_column_done(col["id"], False)
        done_col = store.create_column(project_id, "Done")
        store.set_column_done(done_col["id"], True)
    mapping = {}
    for trello_list, col in zip(open_lists, columns):
        if trello_list.get("id") is not None:
            mapping[trello_list["id"]] = col["id"]
    return mapping


def _card_fields(card: dict) -> dict:
    labels = []
    for label in card.get("labels") or []:
        if isinstance(label, dict):
            name = str(label.get("name") or "").strip()
            if name:
                labels.append(name)
    due = card.get("due") or ""
    return {
        "description": str(card.get("desc") or ""),
        "labels": ", ".join(labels),
        "due_date": str(due)[:10] if due else "",
    }


def _add_subtasks(card_id: int, trello_card: dict, checklists: dict) -> int:
    """Checklist items become child cards, finished ones landing in the
    done column exactly as ticking them in the UI would."""
    added = 0
    for checklist_id in trello_card.get("idChecklists") or []:
        checklist = checklists.get(checklist_id)
        if not isinstance(checklist, dict):
            continue
        items = [
            i for i in checklist.get("checkItems") or [] if isinstance(i, dict)
        ]
        for item in sorted(items, key=_pos):
            title = str(item.get("name") or "").strip()
            if not title:
                continue
            subtask = store.create_subtask(card_id, title)
            if not subtask:
                continue
            added += 1
            if item.get("state") == "complete":
                store.update_subtask(subtask["id"], done=True)
    return added


def import_trello(data: dict) -> dict:
    """Import a Trello board export, returning the new project's id and
    what was brought over. Raises ValueError when the payload is not a
    Trello board export."""
    if not isinstance(data, dict):
        raise ValueError(_NOT_TRELLO)
    lists = data.get("lists")
    cards = data.get("cards")
    if not isinstance(lists, list) or not isinstance(cards, list):
        raise ValueError(_NOT_TRELLO)

    all_lists = [l for l in lists if isinstance(l, dict)]
    open_lists = sorted(
        (l for l in all_lists if not l.get("closed")), key=_pos
    )
    column_names = [str(l.get("name") or "List") for l in open_lists]

    project = store.create_project(
        _project_name(data), columns=column_names or ["Done"]
    )
    column_for = _build_columns(project["id"], open_lists)

    checklists = {}
    for checklist in data.get("checklists") or []:
        if isinstance(checklist, dict) and checklist.get("id") is not None:
            checklists[checklist["id"]] = checklist

    all_cards = [c for c in cards if isinstance(c, dict)]
    open_cards = [
        c
        for c in all_cards
        if not c.get("closed") and c.get("idList") in column_for
    ]
    subtask_count = 0
    for trello_card in sorted(open_cards, key=_pos):
        title = str(trello_card.get("name") or "").strip() or "Untitled card"
        card = store.create_card(
            project["id"],
            column_for[trello_card["idList"]],
            title,
            **_card_fields(trello_card),
        )
        subtask_count += _add_subtasks(card["id"], trello_card, checklists)
        last_activity = trello_card.get("dateLastActivity")
        if last_activity:
            # After the subtasks: adding one bumps the parent to "now".
            with database.connect() as conn:
                conn.execute(
                    "UPDATE cards SET updated_at = ? WHERE id = ?",
                    (str(last_activity).replace("T", " ")[:19], card["id"]),
                )

    return {
        "project_id": project["id"],
        "project_name": project["name"],
        "counts": {
            "lists": len(open_lists),
            "cards": len(open_cards),
            "subtasks": subtask_count,
            "skipped_lists": len(all_lists) - len(open_lists),
            "skipped_cards": len(all_cards) - len(open_cards),
        },
    }
