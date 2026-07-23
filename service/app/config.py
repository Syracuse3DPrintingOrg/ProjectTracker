"""App settings.

Environment variables override values saved from the Settings page
(data/settings.json). APP_VERSION is the single source of truth for the
app version.
"""

import json
import os
import threading
from pathlib import Path

APP_VERSION = "0.16.0"
APP_NAME = "SQ"
APP_TAGLINE = "the project tracker for the easily distracted"

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
    "connector_token",
    "app_title",
    "base_url",
    "displays",
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
    "connector_token": "",
    "app_title": APP_NAME,
    "base_url": "",
    "displays": [],
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
    "connector_token": "TRACKER_CONNECTOR_TOKEN",
    "app_title": "TRACKER_TITLE",
    "base_url": "TRACKER_BASE_URL",
}

_MODEL_DEFAULTS = {
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2",
}


def settings_path() -> Path:
    return DATA_DIR / "settings.json"


_settings_lock = threading.Lock()
# (path, mtime_ns) -> parsed file, so per-request loads skip the disk when
# nothing changed. Env overrides are applied after the cache, so they
# always win and never get stale.
_settings_cache: tuple | None = None


def load_settings() -> dict:
    """Effective settings: defaults, then settings.json, then env overrides."""
    global _settings_cache
    merged = dict(_DEFAULTS)
    path = settings_path()
    try:
        stamp = (str(path), path.stat().st_mtime_ns)
        if _settings_cache and _settings_cache[0] == stamp:
            saved = _settings_cache[1]
        else:
            saved = json.loads(path.read_text())
            _settings_cache = (stamp, saved)
        merged.update({k: v for k, v in saved.items() if k in _SAVEABLE})
    except (OSError, ValueError):
        pass
    for key, env in _ENV_MAP.items():
        val = os.environ.get(env)
        if val:
            merged[key] = val
    return merged


def save_settings(updates: dict) -> dict:
    """Persist only saveable keys; leaves keys absent from updates untouched.

    The read-modify-write is serialized so two sections saving at the
    same moment cannot drop each other's fields."""
    with _settings_lock:
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
        # Filesystem timestamps can be coarser than back-to-back saves,
        # so never trust the mtime stamp across our own writes.
        global _settings_cache
        _settings_cache = None
    return load_settings()


def default_model(provider: str) -> str:
    return _MODEL_DEFAULTS.get(provider, "")
