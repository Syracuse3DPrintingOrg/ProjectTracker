"""Settings page (sidebar panes), save endpoint, overview and update checks."""

import os
import secrets

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .. import config
from ..services import auth, displays, llm, store
from ..services import users as users_svc
from .connectors_router import _connector_token
from .displays_router import _base_url, _with_urls
from .pages import _page_context, templates

router = APIRouter(tags=["settings"])

PROVIDERS = ["gemini", "anthropic", "openai", "ollama"]

# Where releases live and what the shipped image is called. The image name
# is pinned on purpose; never derive it from the repository name.
GITHUB_REPO = "Syracuse3DPrintingOrg/ProjectTracker"
DOCKER_IMAGE = "ghcr.io/syracuse3dprintingorg/projecttracker"
UPDATE_CHECK_TIMEOUT = 5.0


class SettingsIn(BaseModel):
    llm_provider: str | None = None
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_url: str | None = None
    llm_model: str | None = None
    app_title: str | None = None
    base_url: str | None = None
    password: str | None = None
    clear_password: bool | None = None
    rotate_display_token: bool | None = None
    clear_display_token: bool | None = None


@router.get("/settings")
def settings_page(request: Request):
    settings = config.load_settings()
    me = getattr(request.state, "user", None)
    if auth.auth_required(settings) and (not me or me["role"] != "admin"):
        return RedirectResponse("/account", status_code=303)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            **_page_context(settings, request),
            "settings": settings,
            "providers": PROVIDERS,
            "default_model": config.default_model(
                settings.get("llm_provider", "gemini")
            ),
            "has_keys": {
                p: bool(settings.get(f"{p}_api_key")) for p in PROVIDERS if p != "ollama"
            },
            # Hardware pane: the wall display registry and device helpers.
            "displays": [
                _with_urls(d, request, settings)
                for d in displays.list_displays(settings)
            ],
            "adb_available": displays.adb_available(),
            "base_url": _base_url(request, settings),
            "base_url_configured": bool((settings.get("base_url") or "").strip()),
            "has_token": bool(settings.get("display_token")),
            "needs_token": auth.auth_required(settings),
            # Only admins (or an unlocked instance) reach this page, so the
            # connector token may be rendered into the setup command.
            "connector_token": _connector_token(settings),
            "github_repo": GITHUB_REPO,
            "docker_image": DOCKER_IMAGE,
        },
    )


@router.post("/api/settings")
def save_settings(body: SettingsIn):
    updates = {}
    data = body.model_dump(exclude_unset=True)
    for key in (
        "llm_provider",
        "ollama_url",
        "llm_model",
        "app_title",
        "base_url",
    ):
        if key in data and data[key] is not None:
            updates[key] = data[key].strip()
    if updates.get("llm_provider") not in (None, *PROVIDERS):
        updates.pop("llm_provider")
    # API keys: an empty or missing field leaves the stored secret alone.
    for key in ("gemini_api_key", "anthropic_api_key", "openai_api_key"):
        if data.get(key):
            updates[key] = data[key].strip()
    # Passwords moved to real user accounts (see /api/users); the old
    # password fields are ignored if an outdated client still sends them.
    if data.get("rotate_display_token"):
        updates["display_token"] = secrets.token_urlsafe(16)
    if data.get("clear_display_token"):
        updates["display_token"] = ""
    settings = config.save_settings(updates)
    return {
        "ok": True,
        "ai_configured": llm.is_configured(settings),
        "display_token": settings.get("display_token", ""),
    }


@router.post("/api/settings/test-llm")
def test_llm():
    settings = config.load_settings()
    if not llm.is_configured(settings):
        return {"ok": False, "error": "no provider configured"}
    try:
        reply = llm.complete(
            'Reply with ONLY this JSON: {"ok": true}', settings
        )
        data = llm.parse_json_response(reply)
        return {"ok": bool(data.get("ok")), "provider": settings["llm_provider"]}
    except llm.LLMError as exc:
        return {"ok": False, "error": str(exc)}


def _data_dir_writable() -> bool:
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        return os.access(config.DATA_DIR, os.W_OK)
    except OSError:
        return False


@router.get("/api/settings/overview")
def settings_overview():
    """Quick numbers and health touches for the Overview pane."""
    settings = config.load_settings()
    open_cards = sum(p.get("open_cards", 0) for p in store.project_open_counts())
    return {
        "app_title": settings.get("app_title") or config.APP_NAME,
        "version": config.APP_VERSION,
        "projects": len(store.list_projects()),
        "open_cards": open_cards,
        "users": len(users_svc.list_users()),
        "displays": len(displays.list_displays(settings)),
        "health": {
            "data_dir_writable": _data_dir_writable(),
            "ai_configured": llm.is_configured(settings),
            "users_configured": auth.auth_required(settings),
        },
    }


def _github_get(path: str):
    """One GitHub API GET, decoded as JSON. Split out so tests can stub it."""
    resp = httpx.get(
        f"https://api.github.com/repos/{GITHUB_REPO}{path}",
        timeout=UPDATE_CHECK_TIMEOUT,
        headers={"Accept": "application/vnd.github+json"},
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.json()


def _version_tuple(tag: str) -> tuple | None:
    tag = (tag or "").strip().lstrip("vV")
    try:
        return tuple(int(p) for p in tag.split("."))
    except ValueError:
        return None


def _latest_release() -> tuple[str, str]:
    """The newest published (tag, link). Falls back to plain git tags when
    the repository has no releases yet; returns ("", "") when there is
    nothing to compare against."""
    try:
        release = _github_get("/releases/latest")
        tag = (release.get("tag_name") or "").strip()
        if tag:
            url = release.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases"
            return tag, url
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
    best = None
    for entry in _github_get("/tags") or []:
        name = (entry.get("name") or "").strip() if isinstance(entry, dict) else ""
        version = _version_tuple(name)
        if version and (best is None or version > best[0]):
            best = (version, name)
    if best is None:
        return "", ""
    return best[1], f"https://github.com/{GITHUB_REPO}/releases/tag/{best[1]}"


@router.get("/api/settings/updates")
def check_updates():
    """Current version plus the newest release on GitHub.

    A failed check is a normal answer, not an error status: an offline
    tracker still deserves a working Updates pane."""
    result = {
        "current": config.APP_VERSION,
        "latest": "",
        "update_available": False,
        "url": f"https://github.com/{GITHUB_REPO}/releases",
        "image": DOCKER_IMAGE,
        "checked": False,
        "error": "",
    }
    try:
        tag, url = _latest_release()
    except (httpx.HTTPError, ValueError):
        result["error"] = "Could not check for updates. If this tracker has no internet access, that is fine."
        return result
    result["checked"] = True
    if not tag:
        return result
    result["latest"] = tag.lstrip("vV")
    if url:
        result["url"] = url
    latest = _version_tuple(tag)
    current = _version_tuple(config.APP_VERSION)
    if latest and current:
        result["update_available"] = latest > current
    return result


@router.get("/settings/")
def settings_slash():
    return RedirectResponse("/settings", status_code=303)
