"""Project Tracker: a lightweight kanban board with a Today's Tasks list."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import config, database
from .routers import (
    boards,
    connectors_router,
    display,
    displays_router,
    llm_router,
    pages,
    settings_router,
    users_router,
)
from .services import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    from .services import users as users_svc

    users_svc.migrate_legacy_password()
    yield


app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, lifespan=lifespan)

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# Paths that never require a session.
_OPEN_PREFIXES = ("/static/", "/login", "/health")
_DISPLAY_PREFIXES = ("/display", "/api/display")


@app.middleware("http")
async def session_guard(request: Request, call_next):
    from fastapi.responses import JSONResponse

    from .services import rbac, users as users_svc

    path = request.url.path
    request.state.user = None
    if auth.auth_required():
        settings = config.load_settings()
        open_path = path in ("/login", "/health") or path.startswith(_OPEN_PREFIXES)
        display_ok = path.startswith(_DISPLAY_PREFIXES) and auth.valid_display_token(
            request.query_params.get("token"), settings
        )
        # Connector reports carry their own token, checked by the endpoint.
        if path == "/api/connectors/claude-code" and request.method == "POST":
            open_path = True
        user = None
        uid = auth.session_user_id(request.cookies.get(auth.SESSION_COOKIE))
        if uid is not None:
            user = users_svc.get_user(uid)
        if user:
            request.state.user = user
        elif not (open_path or display_ok):
            if path.startswith("/api/"):
                return JSONResponse({"detail": "not authenticated"}, status_code=401)
            return RedirectResponse(f"/login?next={path}", status_code=303)
        if user and not rbac.allowed(user["role"], request.method, path):
            return JSONResponse(
                {"detail": rbac.deny_message(user["role"], request.method, path)},
                status_code=403,
            )
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "projecttracker", "version": config.APP_VERSION}


app.include_router(pages.router)
app.include_router(boards.router)
app.include_router(display.router)
app.include_router(displays_router.router)
app.include_router(connectors_router.router)
app.include_router(users_router.router)
app.include_router(llm_router.router)
app.include_router(settings_router.router)
