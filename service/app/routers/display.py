"""Status display endpoints for wall screens.

A Raspberry Pi points a browser at /display (self-refreshing page). An
ESP32 polls /api/display, a compact JSON payload small enough to parse on
a microcontroller. Both accept ?token=... when a password is set, so the
display never needs a login flow.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Request

from .. import config
from ..services import checklist, store
from .pages import templates

router = APIRouter(tags=["display"])


def _compact_today() -> dict:
    tasks = []
    for card in store.list_today():
        task = {
            "id": card["id"],
            "title": card["title"],
            "project": card["project_name"],
            "status": card["status"],
            "done": bool(card["done"]),
            "priority": card["priority"],
            "due": card["due_date"],
        }
        done, total = checklist.progress(card["description"])
        if total:
            task["checklist"] = f"{done}/{total}"
        tasks.append(task)
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
def display_page(request: Request, d: str = ""):
    """The wall display page.

    Look options come from query parameters; a registered display
    (?d=<id>) contributes its saved options as defaults, so its look is
    managed from the Displays page without touching the device.
    """
    from ..services import displays as displays_svc

    params: dict = {}
    if d:
        entry = displays_svc.get_display(d)
        if entry:
            params.update(entry.get("params") or {})
            params.setdefault("title", entry.get("name", ""))
    for key in displays_svc.PARAM_KEYS:
        if key in request.query_params:
            params[key] = request.query_params[key]
    return templates.TemplateResponse(
        request,
        "display.html",
        {
            "theme": params.get("theme", "dark"),
            "scale": params.get("scale", "1"),
            "clock": params.get("clock", "1") not in ("0", "false", ""),
            "hide_done": params.get("hide_done", "") in ("1", "true"),
            "tv": params.get("tv", "") in ("1", "true"),
            "title": params.get("title", ""),
        },
    )
