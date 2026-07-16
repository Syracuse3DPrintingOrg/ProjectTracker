"""Settings page and save endpoint."""

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from .. import config
from ..services import auth, llm
from .pages import _page_context, templates

router = APIRouter(tags=["settings"])

PROVIDERS = ["gemini", "anthropic", "openai", "ollama"]


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
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            **_page_context(settings),
            "settings": settings,
            "providers": PROVIDERS,
            "default_model": config.default_model(
                settings.get("llm_provider", "gemini")
            ),
            "has_keys": {
                p: bool(settings.get(f"{p}_api_key")) for p in PROVIDERS if p != "ollama"
            },
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
    if data.get("password"):
        updates["password_hash"] = auth.hash_password(data["password"])
    if data.get("clear_password"):
        updates["password_hash"] = ""
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


@router.get("/settings/")
def settings_slash():
    return RedirectResponse("/settings", status_code=303)
