"""Wall display registry and Android TV control.

Registered displays live in settings.json under "displays". Each entry
carries a kind (browser for a Pi or TV browser, esp32, androidtv), its
look options, and for Android TV the ADB address used to pop the display
up on screen.

ADB keys persist under the data dir, so a TV only asks to authorize the
tracker once.
"""

import os
import secrets
import shutil
import subprocess
from urllib.parse import urlencode

from .. import config

KINDS = ("browser", "androidtv", "esp32")

# Look options a display may carry; values are kept as strings because
# they travel as query parameters.
PARAM_KEYS = ("theme", "scale", "clock", "hide_done", "tv", "title")

ADB_TIMEOUT = 20


def list_displays(settings: dict | None = None) -> list[dict]:
    s = settings or config.load_settings()
    displays = s.get("displays") or []
    return [d for d in displays if isinstance(d, dict) and d.get("id")]


def get_display(display_id: str, settings: dict | None = None) -> dict | None:
    for d in list_displays(settings):
        if d["id"] == display_id:
            return d
    return None


def _save(displays: list[dict]) -> None:
    config.save_settings({"displays": displays})


def create_display(name: str, kind: str, adb_host: str = "", params: dict | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"unknown display kind: {kind}")
    entry = {
        "id": secrets.token_hex(4),
        "name": name.strip() or "Display",
        "kind": kind,
        "adb_host": adb_host.strip(),
        "params": _clean_params(params or {}),
    }
    displays = list_displays()
    displays.append(entry)
    _save(displays)
    return entry


def update_display(display_id: str, **fields) -> dict | None:
    displays = list_displays()
    target = None
    for d in displays:
        if d["id"] == display_id:
            target = d
            break
    if not target:
        return None
    if "name" in fields and fields["name"] is not None:
        target["name"] = str(fields["name"]).strip() or target["name"]
    if "adb_host" in fields and fields["adb_host"] is not None:
        target["adb_host"] = str(fields["adb_host"]).strip()
    if fields.get("kind") in KINDS:
        target["kind"] = fields["kind"]
    if "params" in fields and fields["params"] is not None:
        target["params"] = _clean_params(fields["params"])
    _save(displays)
    return target


def delete_display(display_id: str) -> bool:
    displays = list_displays()
    kept = [d for d in displays if d["id"] != display_id]
    if len(kept) == len(displays):
        return False
    _save(kept)
    return True


def _clean_params(params: dict) -> dict:
    return {k: str(v) for k, v in params.items() if k in PARAM_KEYS and str(v)}


def display_url(display: dict, base_url: str, settings: dict | None = None) -> str:
    """Absolute /display URL for a registered display, token included."""
    s = settings or config.load_settings()
    query = {"d": display["id"]}
    query.update(display.get("params") or {})
    token = s.get("display_token", "")
    if token:
        query["token"] = token
    return f"{base_url.rstrip('/')}/display?{urlencode(query)}"


def api_url(display: dict, base_url: str, settings: dict | None = None) -> str:
    s = settings or config.load_settings()
    query = {}
    token = s.get("display_token", "")
    if token:
        query["token"] = token
    suffix = f"?{urlencode(query)}" if query else ""
    return f"{base_url.rstrip('/')}/api/display{suffix}"


# ---- Android TV over ADB ----

class AdbError(Exception):
    pass


def adb_available() -> bool:
    return shutil.which("adb") is not None


def _normalize_host(adb_host: str) -> str:
    host = adb_host.strip()
    if not host:
        raise AdbError("no ADB address set for this display")
    if ":" not in host:
        host += ":5555"
    return host


def build_adb_commands(adb_host: str, action: str, url: str = "") -> list[list[str]]:
    """The exact adb invocations for an action. Pure, for tests."""
    host = _normalize_host(adb_host)
    connect = ["adb", "connect", host]
    if action == "show":
        if not url:
            raise AdbError("no URL to show")
        return [
            connect,
            ["adb", "-s", host, "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
            [
                "adb", "-s", host, "shell", "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", url,
            ],
        ]
    if action == "hide":
        return [connect, ["adb", "-s", host, "shell", "input", "keyevent", "KEYCODE_HOME"]]
    if action == "sleep":
        return [connect, ["adb", "-s", host, "shell", "input", "keyevent", "KEYCODE_SLEEP"]]
    if action == "status":
        return [connect, ["adb", "-s", host, "get-state"]]
    raise AdbError(f"unknown action: {action}")


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    # Keep ADB keys with the app data so TV authorizations survive restarts.
    env.setdefault("HOME", str(config.DATA_DIR))
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=ADB_TIMEOUT, env=env
    )


def run_adb(adb_host: str, action: str, url: str = "") -> dict:
    """Run an ADB action against a TV. Returns {ok, detail}."""
    if not adb_available():
        raise AdbError("adb is not installed on the server")
    detail = []
    try:
        for cmd in build_adb_commands(adb_host, action, url):
            proc = _run(cmd)
            out = (proc.stdout + proc.stderr).strip()
            detail.append(out)
            failed = proc.returncode != 0 or "failed to connect" in out or "error:" in out.lower()
            if failed:
                raise AdbError(out or f"{' '.join(cmd)} failed")
    except subprocess.TimeoutExpired:
        raise AdbError(f"the TV at {adb_host} did not answer (ADB timeout)")
    return {"ok": True, "detail": "\n".join(d for d in detail if d)}
