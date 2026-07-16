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
)
from .services import auth


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield


app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, lifespan=lifespan)

_STATIC = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=_STATIC), name="static")

# Paths that never require a session.
_OPEN_PREFIXES = ("/static/", "/login", "/health")
_DISPLAY_PREFIXES = ("/display", "/api/display")


@app.middleware("http")
async def session_guard(request: Request, call_next):
    path = request.url.path
    settings = config.load_settings()
    if auth.auth_required(settings):
        open_path = path in ("/login", "/health") or path.startswith(_OPEN_PREFIXES)
        display_ok = path.startswith(_DISPLAY_PREFIXES) and auth.valid_display_token(
            request.query_params.get("token"), settings
        )
        # Connector reports carry their own token, checked by the endpoint.
        if path == "/api/connectors/claude-code" and request.method == "POST":
            open_path = True
        session_ok = auth.valid_session(request.cookies.get(auth.SESSION_COOKIE))
        if not (open_path or display_ok or session_ok):
            if path.startswith("/api/"):
                from fastapi.responses import JSONResponse

                return JSONResponse({"detail": "not authenticated"}, status_code=401)
            return RedirectResponse(f"/login?next={path}", status_code=303)
    return await call_next(request)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": "projecttracker", "version": config.APP_VERSION}


app.include_router(pages.router)
app.include_router(boards.router)
app.include_router(display.router)
app.include_router(displays_router.router)
app.include_router(connectors_router.router)
app.include_router(llm_router.router)
app.include_router(settings_router.router)
