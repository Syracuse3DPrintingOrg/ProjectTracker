"""HTML pages: board, today, login."""

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from .. import config
from ..services import auth, checklist, llm, store

templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")
templates.env.globals["checklist_progress"] = checklist.progress

router = APIRouter(tags=["pages"])


def _page_context(settings: dict, request: Request | None = None) -> dict:
    user = getattr(request.state, "user", None) if request else None
    return {
        "app_title": settings.get("app_title") or config.APP_NAME,
        "version": config.APP_VERSION,
        "ai_configured": llm.is_configured(settings),
        "auth_required": auth.auth_required(settings),
        "user": user,
        "is_admin": bool(user and user.get("role") == "admin"),
        "can_edit": bool(user is None or user.get("role") in ("admin", "member")),
    }


@router.get("/")
def home(request: Request):
    projects = store.list_projects()
    if projects:
        return RedirectResponse(f"/project/{projects[0]['id']}", status_code=303)
    settings = config.load_settings()
    return templates.TemplateResponse(
        request,
        "welcome.html",
        {**_page_context(settings, request), "projects": projects},
    )


@router.get("/project/{project_id}")
def project_board(request: Request, project_id: int):
    project = store.get_project(project_id)
    if not project:
        return RedirectResponse("/", status_code=303)
    settings = config.load_settings()
    if project.get("kind") == "list":
        columns = store.list_columns(project_id)
        working = [c for c in columns if not c["is_done"]]
        done = [c for c in columns if c["is_done"]]
        cards = [c for c in store.list_cards(project_id) if c["parent_id"] is None]
        done_ids = {c["id"] for c in done}
        return templates.TemplateResponse(
            request,
            "list.html",
            {
                **_page_context(settings, request),
                "project": project,
                "projects": store.list_projects(),
                "items_column": working[0] if working else columns[0],
                "done_column_ids": list(done_ids),
                "unchecked": [c for c in cards if c["column_id"] not in done_ids],
                "checked": [c for c in cards if c["column_id"] in done_ids],
                "today_ids": [c["id"] for c in store.list_today()],
            },
        )
    from ..services import connectors

    claude_status = (
        connectors.project_status(project.get("claude_path", ""))
        if project.get("claude_path")
        else None
    )
    from ..services import attachments, users

    attachment_counts = attachments.counts_by_card(project_id)
    subtask_counts = store.subtask_progress(project_id)
    usernames = {u["id"]: u["username"] for u in users.list_users()}
    # Child cards render nested inside their parent, never as their own
    # column entries.
    cards = [c for c in store.list_cards(project_id) if c["parent_id"] is None]
    return templates.TemplateResponse(
        request,
        "board.html",
        {
            **_page_context(settings, request),
            "project": project,
            "claude_status": claude_status,
            "projects": store.list_projects(),
            "columns": store.list_columns(project_id),
            "cards": cards,
            "children": store.children_map(project_id),
            "attachment_counts": attachment_counts,
            "subtask_counts": subtask_counts,
            "usernames": usernames,
            "today_ids": [c["id"] for c in store.list_today()],
        },
    )


@router.get("/project/{project_id}/overview")
def project_overview_page(request: Request, project_id: int):
    project = store.get_project(project_id)
    if not project:
        return RedirectResponse("/", status_code=303)
    settings = config.load_settings()
    data = store.project_overview(project_id)
    report = store.project_report(project_id)
    return templates.TemplateResponse(
        request,
        "project_overview.html",
        {
            **_page_context(settings, request),
            "report": report,
            "project": project,
            "description_paragraphs": [
                p.strip() for p in project["description"].splitlines() if p.strip()
            ],
            **data,
        },
    )


@router.get("/today")
def today_page(request: Request):
    settings = config.load_settings()
    return templates.TemplateResponse(
        request,
        "today.html",
        {
            **_page_context(settings, request),
            "projects": store.list_projects(),
            "tasks": store.list_today(),
        },
    )


@router.get("/my")
def my_work_page(request: Request):
    me = getattr(request.state, "user", None)
    if not me or me.get("id") is None:
        return RedirectResponse("/", status_code=303)
    settings = config.load_settings()
    cards = store.my_work(me["id"])
    grouped: dict = {}
    for card in cards:
        grouped.setdefault(card["project_name"], []).append(card)
    return templates.TemplateResponse(
        request,
        "my.html",
        {**_page_context(settings, request), "grouped": grouped, "total": len(cards)},
    )


@router.get("/search")
def search_page(request: Request, q: str = ""):
    settings = config.load_settings()
    results = store.search_cards(q) if q.strip() else []
    return templates.TemplateResponse(
        request,
        "search.html",
        {**_page_context(settings, request), "q": q, "results": results},
    )


@router.get("/calendar")
def calendar_page(request: Request):
    settings = config.load_settings()
    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            **_page_context(settings, request),
            "projects": store.list_projects(),
        },
    )


def safe_next(next_url: str) -> str:
    """Only same-site paths, so a login link cannot bounce people elsewhere."""
    if not next_url.startswith("/") or next_url.startswith("//") or "\\" in next_url:
        return "/"
    return next_url


def login_context(
    request: Request, settings: dict, next_url: str, error: str, recovery: bool = False
) -> dict:
    from ..services import oidc

    return {
        **_page_context(settings, request),
        "next": next_url,
        "error": error,
        "recovery": recovery,
        "oidc_ready": oidc.configured(settings),
        "oidc_here": oidc.on_public_host(request.headers.get("host"), settings),
        "oidc_public": oidc.public_origin(settings),
        "oidc_only": oidc.only(settings),
        "first_run": not auth.auth_required(settings),
    }


@router.get("/login")
def login_page(request: Request, next: str = "/"):
    from ..services import oidc

    settings = config.load_settings()
    # With no users SQ is open, unless Pocket ID can claim it for a first admin.
    if not auth.auth_required(settings) and not oidc.configured(settings):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "login.html", login_context(request, settings, safe_next(next), "")
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
):
    from ..services import oidc, users

    settings = config.load_settings()
    next = safe_next(next)
    if oidc.only(settings):
        return templates.TemplateResponse(
            request,
            "login.html",
            login_context(request, settings, next, "Sign in with Pocket ID."),
            status_code=403,
        )
    user = users.verify_login(username, password)
    if user:
        response = RedirectResponse(next, status_code=303)
        # Not Secure: the password form also works over plain http on the LAN.
        auth.set_session(response, user, auth.METHOD_PASSWORD)
        return response
    return templates.TemplateResponse(
        request,
        "login.html",
        login_context(request, settings, next, "Wrong username or password."),
        status_code=401,
    )


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE)
    return response
