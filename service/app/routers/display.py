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


def _resolve_list(chosen: str) -> int | None:
    """Turn a display's list choice into a personal list owner id.

    Displays are token-authed devices, so they name the user outright as
    "user:<id>". Anything unrecognized (bad id, deleted user, "shared")
    falls back to the shared list."""
    if chosen.startswith("user:"):
        from ..services import users

        try:
            uid = int(chosen.split(":", 1)[1])
        except ValueError:
            return None
        if users.get_user(uid):
            return uid
    return None


def _compact_today(owner: int | None = None) -> dict:
    tasks = []
    for card in store.list_today(owner=owner):
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
def display_data(list: str = "shared"):
    return _compact_today(owner=_resolve_list(list))


@router.get("/api/kiosk/data")
def kiosk_data(list: str = "shared"):
    """Everything the kiosk dashboard shows, in one poll."""
    nudge = store.nudge_data()
    tasks = []
    today_cards = store.list_today(owner=_resolve_list(list))
    sub_progress = store.subtask_progress_for_cards([c["id"] for c in today_cards])
    for card in today_cards:
        done, total = checklist.progress(card["description"])
        sub_done, sub_total = sub_progress.get(card["id"], (0, 0))
        tasks.append(
            {
                "id": card["id"],
                "title": card["title"],
                "project": card["project_name"],
                "done": bool(card["done"]),
                "priority": card["priority"],
                "due": card["due_date"],
                "checklist": f"{done}/{total}" if total else "",
                "subtasks": f"{sub_done}/{sub_total}" if sub_total else "",
            }
        )
    due = store.due_lists()
    def _slim(rows):
        return [
            {"id": r["id"], "title": r["title"], "project": r["project_name"],
             "due": r["due_date"], "priority": r["priority"]}
            for r in rows
        ]
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tasks": tasks,
        "remaining": sum(1 for t in tasks if not t["done"]),
        "overdue": len(due["overdue"]),
        "overdue_tasks": _slim(due["overdue"]),
        "due_soon_tasks": _slim(due["due_soon"]),
        "stalest": (
            {"name": nudge[0]["name"], "days_quiet": nudge[0]["days_quiet"]}
            if nudge and nudge[0]["days_quiet"] >= 3
            else None
        ),
    }


@router.post("/api/kiosk/toggle/{card_id}")
def kiosk_toggle(card_id: int, request: Request):
    """Tap a task on a kiosk: done, or back again. This is the one write
    a display token may make."""
    before = store.get_card(card_id)
    card = store.toggle_done(card_id)
    if not card:
        from fastapi import HTTPException

        raise HTTPException(404)
    if before and card["column_id"] != before["column_id"]:
        from ..services import card_events

        user = getattr(request.state, "user", None)
        columns = {c["id"]: c["name"] for c in store.list_columns(card["project_id"])}
        card_events.log(
            card_id,
            user["username"] if user else "kiosk",
            "moved",
            f"to {columns.get(card['column_id'], '')}".rstrip(),
        )
    return card


@router.get("/kiosk")
def kiosk_page(request: Request, d: str = ""):
    """The kiosk dashboard: today's tasks, huge and tappable."""
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
        "kiosk.html",
        {
            "theme": params.get("theme", "dark"),
            "scale": params.get("scale", "1"),
            "tv": params.get("tv", "") in ("1", "true"),
            "hide_done": params.get("hide_done", "") in ("1", "true"),
            "title": params.get("title", ""),
            "list": params.get("list", ""),
        },
    )


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
            "list": params.get("list", ""),
        },
    )
