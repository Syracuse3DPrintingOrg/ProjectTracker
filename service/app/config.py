"""App settings.

Environment variables override values saved from the Settings page
(data/settings.json). APP_VERSION is the single source of truth for the
app version.
"""

import json
import os
from pathlib import Path

APP_VERSION = "0.1.0"
APP_NAME = "Project Tracker"

DATA_DIR = Path(os.environ.get("TRACKER_DATA_DIR", "data"))

# Keys the Settings page may persist to settings.json.
_SAVEABLE = {
    "llm_provider",
    "gemini_api_key",
    "anthropic_api_key",
    "openai_api_key",
    "ollama_url",
    "llm_model",
    "password_hash",
    "display_token",
    "app_title",
}

_DEFAULTS = {
    "llm_provider": "gemini",
    "gemini_api_key": "",
    "anthropic_api_key": "",
    "openai_api_key": "",
    "ollama_url": "http://localhost:11434",
    "llm_model": "",
    "password_hash": "",
    "display_token": "",
    "app_title": APP_NAME,
}

# Environment variable names that override each saved setting.
_ENV_MAP = {
    "llm_provider": "TRACKER_LLM_PROVIDER",
    "gemini_api_key": "GEMINI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "openai_api_key": "OPENAI_API_KEY",
    "ollama_url": "OLLAMA_URL",
    "llm_model": "TRACKER_LLM_MODEL",
    "password_hash": "TRACKER_PASSWORD_HASH",
    "display_token": "TRACKER_DISPLAY_TOKEN",
    "app_title": "TRACKER_TITLE",
}

_MODEL_DEFAULTS = {
    "gemini": "gemini-2.0-flash",
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2",
}


def settings_path() -> Path:
    return DATA_DIR / "settings.json"


def load_settings() -> dict:
    """Effective settings: defaults, then settings.json, then env overrides."""
    merged = dict(_DEFAULTS)
    try:
        saved = json.loads(settings_path().read_text())
        merged.update({k: v for k, v in saved.items() if k in _SAVEABLE})
    except (OSError, ValueError):
        pass
    for key, env in _ENV_MAP.items():
        val = os.environ.get(env)
        if val:
            merged[key] = val
    return merged


def save_settings(updates: dict) -> dict:
    """Persist only saveable keys; leaves keys absent from updates untouched."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        saved = json.loads(settings_path().read_text())
    except (OSError, ValueError):
        saved = {}
    for key, value in updates.items():
        if key in _SAVEABLE:
            saved[key] = value
    tmp = settings_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(saved, indent=2))
    os.replace(tmp, settings_path())
    return load_settings()


def default_model(provider: str) -> str:
    return _MODEL_DEFAULTS.get(provider, "")
