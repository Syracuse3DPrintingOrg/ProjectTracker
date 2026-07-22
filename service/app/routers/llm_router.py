"""LLM assist endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services import llm, store

router = APIRouter(prefix="/api/assist", tags=["assist"])


class AssistIn(BaseModel):
    card_id: int


class PlanDayIn(BaseModel):
    list: str = "shared"


@router.post("/subtasks")
def subtasks(body: AssistIn):
    card = store.get_card(body.card_id)
    if not card:
        raise HTTPException(404)
    if not llm.is_configured():
        raise HTTPException(400, "no LLM provider configured")
    try:
        items = llm.suggest_subtasks(card["title"], card["description"])
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc))
    # These become real subtasks now, not description text.
    existing = {s["title"].lower() for s in store.list_subtasks(body.card_id)}
    created = []
    for item in items:
        if item.lower() not in existing:
            created.append(store.create_subtask(body.card_id, item))
    return {
        "subtasks": [s["title"] for s in created],
        "card": store.get_card(body.card_id),
        "created": created,
    }


@router.post("/plan-day")
def plan_day(request: Request, body: PlanDayIn | None = None):
    """Ask the LLM to pick today's tasks from open cards and add them
    to the chosen Today list (shared by default, "mine" for the signed-in
    user's personal list)."""
    from datetime import date

    from .boards import list_owner

    if not llm.is_configured():
        raise HTTPException(400, "no LLM provider configured")
    owner = list_owner(request, body.list if body else "shared")
    candidates = store.plan_candidates(owner=owner)
    if not candidates:
        return {"added": [], "note": "nothing open to plan with"}
    try:
        ids = llm.plan_today(candidates, date.today().isoformat())
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc))
    added = []
    for card_id in ids:
        card = store.set_today(card_id, True, owner=owner)
        if card:
            added.append(card)
    return {"added": added}


@router.post("/research")
def research(body: AssistIn):
    """Ask the LLM for ways to complete this card. Returns markdown; the
    client decides whether to append it to the description."""
    card = store.get_card(body.card_id)
    if not card:
        raise HTTPException(404)
    if not llm.is_configured():
        raise HTTPException(400, "no LLM provider configured")
    project = store.get_project(card["project_id"])
    try:
        text = llm.research(
            card["title"], card["description"], project["name"] if project else ""
        )
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc))
    return {"research": text}


@router.post("/describe")
def describe(body: AssistIn):
    card = store.get_card(body.card_id)
    if not card:
        raise HTTPException(404)
    if not llm.is_configured():
        raise HTTPException(400, "no LLM provider configured")
    try:
        text = llm.draft_description(card["title"], card["description"])
    except llm.LLMError as exc:
        raise HTTPException(502, str(exc))
    store.update_card(body.card_id, description=text)
    return {"card": store.get_card(body.card_id)}
