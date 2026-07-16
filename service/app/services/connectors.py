"""Claude Code connector snapshots.

A small reporter script (scripts/claude-code-connector.py) runs on each
development machine and posts what Claude Code is doing there: which
repos have sessions, whether they are working or waiting for input, and
a beads issue summary per repo. Snapshots are kept in one JSON state
file under the data dir, keyed by machine name; they are status, not
history, so the database stays out of it.
"""

import json
import os
import time

from .. import config

STATE_FILE = "connectors.json"

# A machine that has not reported for this long is flagged stale.
STALE_AFTER = 180

SESSION_STATES = ("working", "waiting", "idle")


def _path():
    return config.DATA_DIR / STATE_FILE


def _read() -> dict:
    try:
        data = json.loads(_path().read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, _path())


def store_snapshot(machine: str, projects: list[dict]) -> dict:
    """Save one machine's report. Returns the stored snapshot."""
    machine = (machine or "unknown").strip()[:100]
    snapshot = {
        "machine": machine,
        "received_at": time.time(),
        "projects": [_clean_project(p) for p in projects if isinstance(p, dict)],
    }
    data = _read()
    data[machine] = snapshot
    _write(data)
    return snapshot


def _clean_project(p: dict) -> dict:
    sessions = []
    for s in p.get("sessions") or []:
        if not isinstance(s, dict):
            continue
        state = s.get("state")
        try:
            age = int(s.get("age_seconds") or 0)
        except (TypeError, ValueError):
            age = 0
        sessions.append(
            {
                "state": state if state in SESSION_STATES else "idle",
                "age_seconds": age,
            }
        )
    beads = p.get("beads") if isinstance(p.get("beads"), dict) else None
    clean = {
        "path": str(p.get("path") or "")[:500],
        "name": str(p.get("name") or "")[:200] or os.path.basename(
            str(p.get("path") or "")
        ),
        "sessions": sessions[:10],
        "state": _project_state(sessions),
    }
    if beads is not None:
        def _count(value):
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        clean["beads"] = {
            "open": _count(beads.get("open")),
            "in_progress": _count(beads.get("in_progress")),
            "blocked": _count(beads.get("blocked")),
            "in_progress_titles": [
                str(t)[:200] for t in (beads.get("in_progress_titles") or [])[:5]
            ],
        }
    return clean


def _project_state(sessions: list[dict]) -> str:
    states = {s["state"] for s in sessions}
    if "waiting" in states:
        return "waiting"
    if "working" in states:
        return "working"
    return "idle"


def snapshots() -> list[dict]:
    """All machine snapshots, freshest first, with staleness computed."""
    now = time.time()
    out = []
    for snap in _read().values():
        age = int(now - float(snap.get("received_at") or 0))
        out.append({**snap, "age_seconds": age, "stale": age > STALE_AFTER})
    out.sort(key=lambda s: s["age_seconds"])
    return out


def forget_machine(machine: str) -> bool:
    data = _read()
    if machine not in data:
        return False
    del data[machine]
    _write(data)
    return True


def project_status(claude_path: str) -> dict | None:
    """Latest reported status for one repo path, across machines."""
    if not claude_path:
        return None
    best = None
    for snap in snapshots():
        for p in snap["projects"]:
            if p["path"] == claude_path:
                candidate = {**p, "machine": snap["machine"], "stale": snap["stale"]}
                if best is None or (not candidate["stale"] and best["stale"]):
                    best = candidate
    return best


def known_paths() -> list[dict]:
    """Distinct repo paths seen across machines, for the link picker."""
    seen = {}
    for snap in snapshots():
        for p in snap["projects"]:
            if p["path"] and p["path"] not in seen:
                seen[p["path"]] = {"path": p["path"], "name": p["name"], "machine": snap["machine"]}
    return sorted(seen.values(), key=lambda p: p["name"].lower())
