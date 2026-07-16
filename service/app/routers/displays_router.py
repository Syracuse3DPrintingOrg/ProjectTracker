"""Wall display management: registry CRUD and Android TV control."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .. import config
from ..services import displays
from .pages import _page_context, templates

router = APIRouter(tags=["displays"])


class DisplayIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: str = "browser"
    adb_host: str = ""
    params: dict = {}


class DisplayUpdate(BaseModel):
    name: str | None = None
    kind: str | None = None
    adb_host: str | None = None
    params: dict | None = None


def _base_url(request: Request, settings: dict) -> str:
    configured = (settings.get("base_url") or "").strip()
    if configured:
        return configured
    return str(request.base_url).rstrip("/")


def _with_urls(d: dict, request: Request, settings: dict) -> dict:
    base = _base_url(request, settings)
    return {
        **d,
        "url": displays.display_url(d, base, settings),
        "api_url": displays.api_url(d, base, settings),
    }


@router.get("/displays")
def displays_page(request: Request):
    settings = config.load_settings()
    return templates.TemplateResponse(
        request,
        "displays.html",
        {
            **_page_context(settings),
            "displays": [
                _with_urls(d, request, settings) for d in displays.list_displays(settings)
            ],
            "adb_available": displays.adb_available(),
            "base_url": _base_url(request, settings),
            "base_url_configured": bool((settings.get("base_url") or "").strip()),
            "has_token": bool(settings.get("display_token")),
            "needs_token": bool(settings.get("password_hash")),
        },
    )


@router.get("/api/displays")
def list_displays(request: Request):
    settings = config.load_settings()
    return [_with_urls(d, request, settings) for d in displays.list_displays(settings)]


@router.post("/api/displays", status_code=201)
def create_display(request: Request, body: DisplayIn):
    if body.kind not in displays.KINDS:
        raise HTTPException(422, f"kind must be one of {displays.KINDS}")
    d = displays.create_display(
        body.name, body.kind, adb_host=body.adb_host, params=body.params
    )
    return _with_urls(d, request, config.load_settings())


@router.patch("/api/displays/{display_id}")
def update_display(request: Request, display_id: str, body: DisplayUpdate):
    d = displays.update_display(display_id, **body.model_dump(exclude_unset=True))
    if not d:
        raise HTTPException(404)
    return _with_urls(d, request, config.load_settings())


@router.delete("/api/displays/{display_id}", status_code=204)
def delete_display(display_id: str):
    if not displays.delete_display(display_id):
        raise HTTPException(404)


@router.post("/api/displays/{display_id}/tv/{action}")
def tv_action(request: Request, display_id: str, action: str):
    if action not in ("show", "hide", "sleep", "status"):
        raise HTTPException(404)
    settings = config.load_settings()
    d = displays.get_display(display_id, settings)
    if not d:
        raise HTTPException(404)
    if d["kind"] != "androidtv":
        raise HTTPException(400, "this display is not an Android TV")
    url = displays.display_url(d, _base_url(request, settings), settings)
    try:
        return displays.run_adb(d["adb_host"], action, url)
    except displays.AdbError as exc:
        raise HTTPException(502, str(exc))
