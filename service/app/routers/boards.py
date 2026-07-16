"""REST API for projects, columns, and cards."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import checklist, store

router = APIRouter(prefix="/api", tags=["boards"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None


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


class MoveIn(BaseModel):
    column_id: int
    position: int = 0


class TodayIn(BaseModel):
    today: bool
    position: int | None = None


class ChecklistIn(BaseModel):
    index: int = Field(ge=0)
    checked: bool


class ImportIn(BaseModel):
    confirm: bool = False
    projects: list = []
    columns: list = []
    cards: list = []


# ---- projects ----

@router.get("/projects")
def list_projects(include_archived: bool = False):
    return store.list_projects(include_archived=include_archived)


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn):
    return store.create_project(body.name.strip())


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


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int):
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
def create_card(body: CardIn):
    if not store.get_project(body.project_id):
        raise HTTPException(404, "project not found")
    return store.create_card(
        body.project_id,
        body.column_id,
        body.title.strip(),
        description=body.description,
        labels=body.labels,
        priority=body.priority,
        due_date=body.due_date,
        recur_days=body.recur_days,
    )


@router.get("/cards/{card_id}")
def get_card(card_id: int):
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(404)
    return card


@router.patch("/cards/{card_id}")
def update_card(card_id: int, body: CardUpdate):
    if not store.get_card(card_id):
        raise HTTPException(404)
    return store.update_card(card_id, **body.model_dump(exclude_unset=True))


@router.delete("/cards/{card_id}", status_code=204)
def delete_card(card_id: int):
    store.delete_card(card_id)


@router.post("/cards/{card_id}/move")
def move_card(card_id: int, body: MoveIn):
    card = store.move_card(card_id, body.column_id, body.position)
    if not card:
        raise HTTPException(404, "card or column not found")
    return card


@router.post("/cards/{card_id}/checklist")
def toggle_checklist(card_id: int, body: ChecklistIn):
    card = store.get_card(card_id)
    if not card:
        raise HTTPException(404)
    updated = checklist.toggle_item(card["description"], body.index, body.checked)
    if updated is None:
        raise HTTPException(400, "no checklist item at that index")
    return store.update_card(card_id, description=updated)


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
        {"projects": body.projects, "columns": body.columns, "cards": body.cards}
    )
    return {"ok": True, **counts}


@router.post("/cards/{card_id}/today")
def set_today(card_id: int, body: TodayIn):
    card = store.set_today(card_id, body.today, body.position)
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
def list_today():
    return store.list_today()


@router.post("/today/clear-done")
def clear_done_today():
    return {"cleared": store.clear_done_today()}
