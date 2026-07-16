"""Status display endpoints for wall screens.

A Raspberry Pi points a browser at /display (self-refreshing page). An
ESP32 polls /api/display, a compact JSON payload small enough to parse on
a microcontroller. Both accept ?token=... when a password is set, so the
display never needs a login flow.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from .. import config
from ..services import store
from .pages import templates

router = APIRouter(tags=["display"])


def _compact_today() -> dict:
    tasks = []
    for card in store.list_today():
        tasks.append(
            {
                "id": card["id"],
                "title": card["title"],
                "project": card["project_name"],
                "status": card["status"],
                "done": bool(card["done"]),
                "priority": card["priority"],
                "due": card["due_date"],
            }
        )
    return {
        "app": "projecttracker",
        "version": config.APP_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(tasks),
        "remaining": sum(1 for t in tasks if not t["done"]),
        "tasks": tasks,
    }


@router.get("/api/display")
def display_data():
    return _compact_today()


@router.get("/display")
def display_page(request: Request):
    return templates.TemplateResponse(
        request, "display.html", {"settings": config.load_settings()}
    )
