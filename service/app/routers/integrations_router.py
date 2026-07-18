"""Headless integrations: API keys and the Home Assistant summary."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import config
from ..services import api_keys, store

router = APIRouter(tags=["integrations"])


class KeyIn(BaseModel):
    name: str
    role: str = "member"


@router.get("/api/keys")
def list_keys():
    return api_keys.list_keys()


@router.post("/api/keys", status_code=201)
def create_key(body: KeyIn):
    try:
        return api_keys.create_key(body.name, body.role)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.delete("/api/keys/{key_id}", status_code=204)
def delete_key(key_id: int):
    if not api_keys.delete_key(key_id):
        raise HTTPException(404)


@router.get("/api/ha/summary")
def ha_summary():
    """One payload for Home Assistant REST sensors: the Today list state,
    overdue count, and per-project open cards."""
    today = store.list_today()
    nudge = store.nudge_data()
    return {
        "app": "projecttracker",
        "version": config.APP_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "today_count": len(today),
        "today_remaining": sum(1 for t in today if not t["done"]),
        "today_tasks": [
            {"title": t["title"], "project": t["project_name"], "done": bool(t["done"])}
            for t in today
        ],
        "overdue": store.overdue_count(),
        "projects": store.project_open_counts(),
        "stalest": (
            {
                "name": nudge[0]["name"],
                "open_cards": nudge[0]["open_cards"],
                "days_quiet": nudge[0]["days_quiet"],
            }
            if nudge
            else None
        ),
    }
