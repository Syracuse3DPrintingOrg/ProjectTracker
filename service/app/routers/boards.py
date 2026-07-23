"""REST API for projects, columns, and cards."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..services import card_events, checklist, notifications, store

router = APIRouter(prefix="/api", tags=["boards"])


def actor(request: Request) -> str:
    user = getattr(request.state, "user", None)
    return user["username"] if user else "someone"


def actor_id(request: Request) -> int | None:
    """The acting user's id; None for anonymous callers and API keys.
    Used to keep people from being notified about their own actions."""
    user = getattr(request.state, "user", None)
    return user.get("id") if user else None


def list_owner(request: Request, chosen: str) -> int | None:
    """Resolve a Today-list choice to a personal list owner id.

    "mine" means the signed-in user's list; anything else, an anonymous
    caller, or an API key (no user id) lands on the shared list."""
    if chosen == "mine":
        user = getattr(request.state, "user", None)
        if user and user.get("id"):
            return user["id"]
    return None


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = "board"


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None
    description: str | None = Field(default=None, max_length=20000)


class ColumnIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ColumnUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    is_done: bool | None = None
    position: int | None = None
    wip_limit: int | None = Field(default=None, ge=0, le=99)


class CardIn(BaseModel):
    project_id: int
    column_id: int
    title: str = Field(min_length=1, max_length=500)
    description: str = ""
    labels: str = ""
    priority: int = Field(default=2, ge=0, le=4)
    due_date: str = ""
    recur_days: int = Field(default=0, ge=0, le=365)


class CardUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    labels: str | None = None
    priority: int | None = Field(default=None, ge=0, le=4)
    due_date: str | None = None
    recur_days: int | None = Field(default=None, ge=0, le=365)
    assignee_id: int | None = None
    clear_assignee: bool = False
    parent_id: int | None = None
    clear_parent: bool = False
    archived: bool | None = None


class SubtaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)


class SubtaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    done: bool | None = None
    position: int | None = None


class CommentIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class MoveIn(BaseModel):
    column_id: int
    position: int = 0


class TodayIn(BaseModel):
    today: bool
    position: int | None = None
    list: str = "shared"


class ChecklistIn(BaseModel):
    index: int = Field(ge=0)
    checked: bool


class ImportIn(BaseModel):
    confirm: bool = False
    projects: list = []
    columns: list = []
    cards: list = []
    subtasks: list = []


# ---- projects ----

@router.get("/projects")
def list_projects(include_archived: bool = False):
    return store.list_projects(include_archived=include_archived)


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn):
    if body.kind not in store.PROJECT_KINDS:
        raise HTTPException(422, f"kind must be one of {store.PROJECT_KINDS}")
    return store.create_project(body.name.strip(), kind=body.kind)


@router.patch("/projects/{project_id}")
def update_project(project_id: int, body: ProjectUpdate):
    if not store.get_project(project_id):
        raise HTTPException(404)
    if body.name is not None:
        store.rename_project(project_id, body.name.strip())
    if body.status is not None:
        if body.status not in store.PROJECT_STATUSES:
            raise HTTPException(422, f"status must be one of {store.PROJECT_STATUSES}")
        store.set_project_status(project_id, body.status)
    if body.description is not None:
        store.set_project_description(project_id, body.description.strip())
    return store.get_project(project_id)


@router.get("/nudge")
def nudge(exclude: int | None = None):
    """Active projects with open cards, stalest first. The guilt trip API."""
    return store.nudge_data(exclude)


@router.post("/projects/{project_id}/archive")
def archive_project(project_id: int, archived: bool = True):
    if not store.get_project(project_id):
        raise HTTPException(404)
    store.archive_project(project_id, archived)
    return store.get_project(project_id)


@router.post("/projects/{project_id}/archive-done")
def archive_done(project_id: int):
    """Sweep finished cards (and their subtasks) into the project's
    archive. They stay on the overview's Archived list, off the board."""
    if not store.get_project(project_id):
        raise HTTPException(404)
    return {"archived": store.archive_done_cards(project_id)}


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int):
    from ..services import attachments

    attachments.delete_files_for_project(project_id)
    store.delete_project(project_id)


@router.get("/projects/{project_id}/board")
def board(project_id: int):
    project = store.get_project(project_id)
    if not project:
        raise HTTPException(404)
    return {
        "project": project,
        "columns": store.list_columns(project_id),
        "cards": store.list_cards(project_id),
    }


# ---- columns ----

@router.post("/projects/{project_id}/columns", status_code=201)
def create_column(project_id: int, body: ColumnIn):
    if not store.get_project(project_id):
        raise HTTPException(404)
    return store.create_column(project_id, body.name.strip())


@router.patch("/columns/{column_id}")
def update_column(column_id: int, body: ColumnUpdate):
    if body.name is not None:
        store.rename_column(column_id, body.name.strip())
    if body.is_done is not None:
        store.set_column_done(column_id, body.is_done)
    if body.position is not None:
        store.move_column(column_id, body.position)
    if body.wip_limit is not None:
        store.set_wip_limit(column_id, body.wip_limit)
    return {"ok": True}


@router.delete("/columns/{column_id}")
def delete_column(column_id: int):
    if not store.delete_column(column_id):
        raise HTTPException(409, "column still has cards")
    return {"ok": True}


# ---- cards ----

@router.post("/cards", status_code=201)
def create_card(body: CardIn, request: Request):
    if not store.get_project(body.project_id):
        raise HTTPException(404, "project not found")
    card = store.create_card(
        body.project_id,
        body.column_id,
        body.title.strip(),
        description=body.description,
        labels=body.labels,
        priority=body.priority,
        due_date=body.due_date,
        recur_days=body.recur_days,
    )
    card_events.log(card["id"], actor(request), "created")
    return card


@router.get("/cards/{card_id}")
def get_card(card_id: int):
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(404)
    return card


@router.patch("/cards/{card_id}")
def update_card(card_id: int, body: CardUpdate, request: Request):
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(404)
    updates = body.model_dump(exclude_unset=True)
    archived = updates.pop("archived", None)
    if archived is not None:
        store.set_card_archived(card_id, archived)
    clear_parent = updates.pop("clear_parent", False)
    new_parent = updates.pop("parent_id", None)
    if new_parent is not None:
        parent = store.get_card(new_parent)
        if not parent:
            raise HTTPException(422, "no card to nest under")
        if new_parent == card_id:
            raise HTTPException(422, "a card cannot be its own subtask")
        if parent["project_id"] != card["project_id"]:
            raise HTTPException(422, "subtasks stay within their project")
        if parent["parent_id"] is not None:
            raise HTTPException(422, "subtasks only nest one level deep")
        if store.has_children(card_id):
            raise HTTPException(
                422, "a card with subtasks of its own cannot become a subtask"
            )
        store.set_parent(card_id, new_parent)
    elif clear_parent:
        store.set_parent(card_id, None)
    clear = updates.pop("clear_assignee", False)
    if clear:
        updates["assignee_id"] = None
    if "assignee_id" in updates and updates["assignee_id"] is not None:
        from ..services import users

        target = users.get_user(updates["assignee_id"])
        if not target:
            raise HTTPException(422, "no such user")
        if updates["assignee_id"] != card["assignee_id"]:
            card_events.log(
                card_id, actor(request), "assigned", f"to {target['username']}"
            )
            if target["id"] != actor_id(request):
                notifications.notify(
                    target["id"],
                    f"{actor(request)} assigned you: {card['title']}",
                    f"/project/{card['project_id']}",
                )
    elif clear and card["assignee_id"]:
        card_events.log(card_id, actor(request), "assigned", "to nobody")
    return store.update_card(card_id, **updates)


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int):
    from ..services import attachments

    attachments.delete_files_for_card(card_id)
    store.delete_card(card_id)


@router.post("/cards/{card_id}/move")
def move_card(card_id: int, body: MoveIn, request: Request):
    before = store.get_card(card_id)
    card = store.move_card(card_id, body.column_id, body.position)
    if not card:
        raise HTTPException(404, "card or column not found")
    if before and card["column_id"] != before["column_id"]:
        columns = {c["id"]: c for c in store.list_columns(card["project_id"])}
        if card["column_id"] != body.column_id:
            card_events.log(card_id, actor(request), "respawned")
        else:
            target = columns.get(card["column_id"])
            card_events.log(
                card_id, actor(request), "moved",
                f"to {target['name']}" if target else "",
            )
    return card


# ---- subtasks (child cards behind the old wire shape) ----

@router.get("/cards/{card_id}/subtasks")
def list_subtasks(card_id: int):
    if not store.get_card(card_id):
        raise HTTPException(404)
    return store.list_subtasks(card_id)


@router.post("/cards/{card_id}/subtasks", status_code=201)
def create_subtask(card_id: int, body: SubtaskIn):
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(404)
    if card["parent_id"] is not None:
        raise HTTPException(422, "subtasks only nest one level deep")
    return store.create_subtask(card_id, body.title)


@router.patch("/subtasks/{subtask_id}")
def update_subtask(subtask_id: int, body: SubtaskUpdate):
    subtask = store.update_subtask(subtask_id, **body.model_dump(exclude_unset=True))
    if not subtask:
        raise HTTPException(404)
    return subtask


@router.delete("/subtasks/{subtask_id}", status_code=204)
def delete_subtask(subtask_id: int):
    from ..services import attachments

    child = store.get_card(subtask_id)
    if not child or child["parent_id"] is None:
        raise HTTPException(404)
    attachments.delete_files_for_card(subtask_id)
    if not store.delete_subtask(subtask_id):
        raise HTTPException(404)


# ---- comments and activity ----

@router.get("/cards/{card_id}/events")
def list_events(card_id: int):
    if not store.get_card(card_id):
        raise HTTPException(404)
    return card_events.list_for_card(card_id)


@router.post("/cards/{card_id}/comments", status_code=201)
def add_comment(card_id: int, body: CommentIn, request: Request):
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(404)
    text = body.text.strip()
    card_events.log(card_id, actor(request), "comment", text)
    # Notify the assignee plus everyone @mentioned, once each, never
    # the commenter about their own comment.
    targets: list[int] = []
    if card["assignee_id"]:
        targets.append(card["assignee_id"])
    for uid in notifications.mention_targets(text):
        if uid not in targets:
            targets.append(uid)
    message = f"{actor(request)} commented on {card['title']}: {text[:80]}"
    me = actor_id(request)
    for uid in targets:
        if uid != me:
            notifications.notify(uid, message, f"/project/{card['project_id']}")
    return card_events.list_for_card(card_id)[-1]


@router.get("/assignees")
def list_assignees():
    """Users a card can be assigned to; open to every signed-in role."""
    from ..services import users

    return [
        {"id": u["id"], "username": u["username"]}
        for u in users.list_users()
        if not u["disabled"]
    ]


@router.post("/cards/{card_id}/checklist")
def toggle_checklist(card_id: int, body: ChecklistIn):
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(404)
    updated = checklist.toggle_item(card["description"], body.index, body.checked)
    if updated is None:
        raise HTTPException(400, "no checklist item at that index")
    return store.update_card(card_id, description=updated)


@router.get("/cards/{card_id}/handoff")
def handoff(card_id: int):
    """A self-contained prompt that hands this card to any LLM."""
    from ..services import attachments, checklist as checklist_svc

    card = store.get_card(card_id)
    if not card:
        raise HTTPException(404)
    project = store.get_project(card["project_id"])
    column = next(
        (c for c in store.list_columns(card["project_id"]) if c["id"] == card["column_id"]),
        None,
    )
    items = checklist_svc.parse_checklist(card["description"])
    files = attachments.list_for_card(card_id)

    lines = [
        "I need help completing a task from my project tracker.",
        "",
        f"Task: {card['title']}",
        f"Project: {project['name'] if project else 'unknown'}",
        f"Status: {column['name'] if column else 'unknown'}",
    ]
    if card["priority"] != 2:
        lines.append(f"Priority: P{card['priority']}")
    if card["due_date"]:
        lines.append(f"Due: {card['due_date']}")
    if card["labels"]:
        lines.append(f"Labels: {card['labels']}")
    if card["description"].strip():
        lines += ["", "Details:", card["description"].strip()]
    subtasks = store.list_subtasks(card_id)
    if subtasks:
        done_n = sum(1 for s in subtasks if s["done"])
        lines += ["", f"Subtasks ({done_n}/{len(subtasks)} done):"]
        lines += [
            f"- [{'x' if s['done'] else ' '}] {s['title']}" for s in subtasks
        ]
    if items:
        done = sum(1 for i in items if i["checked"])
        lines += ["", f"Checklist ({done}/{len(items)} done):"]
        lines += [
            f"- [{'x' if i['checked'] else ' '}] {i['text']}" for i in items
        ]
    if files:
        lines += ["", "Attached files (not included here):"]
        lines += [f"- {f['filename']} ({f['size']} bytes)" for f in files]
    lines += [
        "",
        "Please help me finish this: propose a concrete plan, do any parts"
        " you can directly, and tell me what you need from me.",
    ]
    return {"prompt": "\n".join(lines), "title": card["title"]}


@router.get("/search")
def search(q: str, project_id: int | None = None):
    if not q.strip():
        return []
    return store.search_cards(q, project_id)


@router.get("/export")
def export_data():
    from .. import config

    return {
        "app": "projecttracker",
        "version": config.APP_VERSION,
        **store.export_data(),
    }


@router.post("/import")
def import_data(body: ImportIn):
    if not body.confirm:
        raise HTTPException(400, "set confirm=true; the import replaces everything")
    counts = store.import_data(
        {"projects": body.projects, "columns": body.columns,
         "cards": body.cards, "subtasks": body.subtasks}
    )
    return {"ok": True, **counts}


@router.post("/import/trello")
def import_trello_board(body: dict):
    """Bring a Trello board export in as a new project. Additive: nothing
    already in the tracker is replaced."""
    from ..services import trello_import

    try:
        return trello_import.import_trello(body)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/cards/{card_id}/today")
def set_today(card_id: int, body: TodayIn, request: Request):
    owner = list_owner(request, body.list)
    card = store.set_today(card_id, body.today, body.position, owner=owner)
    if not card:
        raise HTTPException(404)
    return card


@router.get("/calendar")
def calendar_cards(start: str, end: str, projects: str = ""):
    """Cards due between start and end (ISO dates), optionally filtered
    to a comma-separated list of project ids."""
    import re

    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}", end
    ):
        raise HTTPException(422, "start and end must be YYYY-MM-DD")
    ids = None
    if projects.strip():
        try:
            ids = [int(p) for p in projects.split(",") if p.strip()]
        except ValueError:
            raise HTTPException(422, "projects must be comma-separated ids")
    return store.list_due_cards(start, end, ids)


@router.get("/today")
def list_today(request: Request, list: str = "shared"):
    return store.list_today(owner=list_owner(request, list))


@router.post("/today/clear-done")
def clear_done_today(request: Request, list: str = "shared"):
    return {"cleared": store.clear_done_today(owner=list_owner(request, list))}
