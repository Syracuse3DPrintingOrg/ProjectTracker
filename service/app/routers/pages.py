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


def _page_context(settings: dict) -> dict:
    return {
        "app_title": settings.get("app_title") or config.APP_NAME,
        "version": config.APP_VERSION,
        "ai_configured": llm.is_configured(settings),
        "auth_required": auth.auth_required(settings),
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
        {**_page_context(settings), "projects": projects},
    )


@router.get("/project/{project_id}")
def project_board(request: Request, project_id: int):
    project = store.get_project(project_id)
    if not project:
        return RedirectResponse("/", status_code=303)
    settings = config.load_settings()
    from ..services import connectors

    claude_status = (
        connectors.project_status(project.get("claude_path", ""))
        if project.get("claude_path")
        else None
    )
    return templates.TemplateResponse(
        request,
        "board.html",
        {
            **_page_context(settings),
            "project": project,
            "claude_status": claude_status,
            "projects": store.list_projects(),
            "columns": store.list_columns(project_id),
            "cards": store.list_cards(project_id),
            "today_ids": [c["id"] for c in store.list_today()],
        },
    )


@router.get("/today")
def today_page(request: Request):
    settings = config.load_settings()
    return templates.TemplateResponse(
        request,
        "today.html",
        {
            **_page_context(settings),
            "projects": store.list_projects(),
            "tasks": store.list_today(),
        },
    )


@router.get("/search")
def search_page(request: Request, q: str = ""):
    settings = config.load_settings()
    results = store.search_cards(q) if q.strip() else []
    return templates.TemplateResponse(
        request,
        "search.html",
        {**_page_context(settings), "q": q, "results": results},
    )


@router.get("/calendar")
def calendar_page(request: Request):
    settings = config.load_settings()
    return templates.TemplateResponse(
        request,
        "calendar.html",
        {
            **_page_context(settings),
            "projects": store.list_projects(),
        },
    )


@router.get("/login")
def login_page(request: Request, next: str = "/"):
    settings = config.load_settings()
    if not auth.auth_required(settings):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {**_page_context(settings), "next": next, "error": ""},
    )


@router.post("/login")
def login(request: Request, password: str = Form(""), next: str = Form("/")):
    settings = config.load_settings()
    if not next.startswith("/") or next.startswith("//"):
        next = "/"
    if auth.check_password(password, settings.get("password_hash", "")):
        response = RedirectResponse(next, status_code=303)
        response.set_cookie(
            auth.SESSION_COOKIE,
            auth.make_session_token(),
            max_age=auth.SESSION_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
        return response
    return templates.TemplateResponse(
        request,
        "login.html",
        {**_page_context(settings), "next": next, "error": "Wrong password."},
        status_code=401,
    )


@router.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(auth.SESSION_COOKIE)
    return response
