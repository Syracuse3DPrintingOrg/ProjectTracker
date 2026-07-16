"""LLM assist endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import llm, store

router = APIRouter(prefix="/api/assist", tags=["assist"])


class AssistIn(BaseModel):
    card_id: int


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
    checklist = "\n".join(f"- [ ] {item}" for item in items)
    description = card["description"].rstrip()
    description = f"{description}\n\n{checklist}".strip()
    store.update_card(body.card_id, description=description)
    return {"subtasks": items, "card": store.get_card(body.card_id)}


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
