#!/usr/bin/env python3
"""Report Claude Code activity to Project Tracker.

Run this on any machine where Claude Code works:

    python3 claude-code-connector.py --url http://192.168.1.170:9280 --token XXXX

Every interval it scans Claude Code's local session transcripts
(~/.claude/projects) and each repo's beads export (.beads/issues.jsonl),
then posts one small JSON snapshot to the tracker. Nothing else leaves
the machine; the tracker shows it on the Claude Code dashboard.

Standard library only. --once posts a single snapshot (handy for cron);
--install writes a systemd user service so it runs at boot.
"""

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"

# A session updated this recently is actively working.
WORKING_WINDOW = 120
# A session whose last entry is an assistant turn is waiting for the user
# up to this old; beyond it the session counts as idle.
WAITING_WINDOW = 6 * 3600


def session_state(age_seconds: float, last_type: str) -> str:
    """Classify one session. Heuristic: a transcript that just changed is
    working; one that ended on an assistant turn is waiting for input."""
    if age_seconds < WORKING_WINDOW:
        return "working"
    if age_seconds < WAITING_WINDOW and last_type == "assistant":
        return "waiting"
    return "idle"


def _tail_lines(path: Path, chunk: int = 131072) -> list[bytes]:
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            f.seek(max(0, size - chunk))
            return f.read().splitlines()
    except OSError:
        return []


def last_message_type(path: Path) -> str:
    """The type of the newest conversational entry (user or assistant).

    Transcripts also carry metadata entries (system, file-history-snapshot,
    mode changes); those say nothing about whether Claude is waiting, so
    they are skipped."""
    for raw in reversed(_tail_lines(path)):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("type") in ("user", "assistant"):
            return entry["type"]
    return ""


def _iter_json(lines) -> list[dict]:
    out = []
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def session_details(path: Path, max_lines: int = 80) -> dict:
    """Title, branch, and last-assistant snippet for one chat.

    The title prefers the user's custom title (renames land near the end
    of the transcript, so the tail wins), then the generated slug. The
    snippet is the newest assistant text, so a chat that is waiting shows
    what Claude last said."""
    head = []
    try:
        with open(path, "r", errors="replace") as f:
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                head.append(line)
    except OSError:
        pass
    tail_entries = _iter_json(_tail_lines(path))
    head_entries = _iter_json(head)

    title = ""
    for entry in reversed(tail_entries):
        if entry.get("type") == "custom-title" and entry.get("customTitle"):
            title = str(entry["customTitle"])
            break
    if not title:
        for entry in head_entries:
            if entry.get("type") == "custom-title" and entry.get("customTitle"):
                title = str(entry["customTitle"])
                break
    if not title:
        for entry in tail_entries + head_entries:
            if entry.get("slug"):
                title = str(entry["slug"]).replace("-", " ")
                break

    branch = ""
    for entry in reversed(tail_entries):
        if entry.get("gitBranch"):
            branch = str(entry["gitBranch"])
            break

    snippet = ""
    for entry in reversed(tail_entries):
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str):
            snippet = content
        elif isinstance(content, list):
            snippet = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ).strip()
        if snippet:
            break
    snippet = " ".join(snippet.split())
    if len(snippet) > 220:
        snippet = snippet[:217] + "..."

    return {"title": title[:120], "branch": branch[:80], "snippet": snippet}


def find_cwd(path: Path, max_lines: int = 80) -> str:
    """The session's working directory. Early transcript lines are
    metadata without a cwd, so scan forward a bit, then fall back to the
    end of the file."""
    try:
        with open(path, "r", errors="replace") as f:
            for _ in range(max_lines):
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict) and entry.get("cwd"):
                    return str(entry["cwd"])
    except OSError:
        return ""
    for raw in reversed(_tail_lines(path)):
        raw = raw.strip()
        if not raw:
            continue
        try:
            entry = json.loads(raw)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("cwd"):
            return str(entry["cwd"])
    return ""


def summarize_beads(lines) -> dict | None:
    """Counts from a .beads/issues.jsonl export."""
    counts = {"open": 0, "in_progress": 0, "blocked": 0}
    titles = []
    saw_any = False
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            issue = json.loads(raw)
        except ValueError:
            continue
        saw_any = True
        status = str(issue.get("status", "")).lower()
        if status == "open":
            counts["open"] += 1
        elif status == "in_progress":
            counts["in_progress"] += 1
            if issue.get("title"):
                titles.append(str(issue["title"]))
        elif status == "blocked":
            counts["blocked"] += 1
    if not saw_any:
        return None
    return {**counts, "in_progress_titles": titles[:5]}


def scan(days: int) -> list[dict]:
    """One snapshot of every repo with recent Claude Code sessions."""
    cutoff = time.time() - days * 86400
    repos: dict[str, dict] = {}
    if not CLAUDE_PROJECTS.is_dir():
        return []
    for project_dir in CLAUDE_PROJECTS.iterdir():
        if not project_dir.is_dir():
            continue
        for transcript in project_dir.glob("*.jsonl"):
            try:
                mtime = transcript.stat().st_mtime
            except OSError:
                continue
            if mtime < cutoff:
                continue
            cwd = find_cwd(transcript)
            if not cwd:
                continue
            age = max(0, time.time() - mtime)
            last_type = last_message_type(transcript)
            state = session_state(age, last_type)
            session = {"state": state, "age_seconds": int(age)}
            session.update(session_details(transcript))
            if state != "waiting":
                session.pop("snippet", None)
            repo = repos.setdefault(cwd, {"path": cwd, "sessions": []})
            repo["sessions"].append(session)
    order = {"waiting": 0, "working": 1, "idle": 2}
    for repo in repos.values():
        repo["sessions"].sort(key=lambda s: (order[s["state"]], s["age_seconds"]))
        repo["sessions"] = repo["sessions"][:10]
        repo["name"] = os.path.basename(repo["path"])
        beads_file = Path(repo["path"]) / ".beads" / "issues.jsonl"
        if beads_file.is_file():
            try:
                with open(beads_file, "r", errors="replace") as f:
                    beads = summarize_beads(f)
                if beads:
                    repo["beads"] = beads
            except OSError:
                pass
    return sorted(repos.values(), key=lambda r: r["sessions"][0]["age_seconds"])


def post_snapshot(url: str, token: str, machine: str, projects: list[dict]) -> str:
    body = json.dumps({"machine": machine, "projects": projects}).encode()
    req = urllib.request.Request(
        url.rstrip("/") + "/api/connectors/claude-code",
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Connector-Token": token,
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode()


def install_service(url: str, token: str, interval: int) -> None:
    unit_dir = Path.home() / ".config" / "systemd" / "user"
    unit_dir.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    unit = unit_dir / "claude-code-connector.service"
    unit.write_text(
        "[Unit]\n"
        "Description=Project Tracker Claude Code connector\n"
        "After=network-online.target\n\n"
        "[Service]\n"
        f"ExecStart={sys.executable} {script} --url {url} --token {token}"
        f" --interval {interval}\n"
        "Restart=always\nRestartSec=30\n\n"
        "[Install]\nWantedBy=default.target\n"
    )
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", "claude-code-connector.service"],
        check=False,
    )
    print(f"Installed and started {unit}")
    print("Tip: run 'loginctl enable-linger' so it also runs while logged out.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True, help="tracker base URL")
    ap.add_argument("--token", required=True, help="connector token from the dashboard")
    ap.add_argument("--interval", type=int, default=60, help="seconds between reports")
    ap.add_argument("--days", type=int, default=7, help="ignore sessions older than this")
    ap.add_argument("--machine", default=socket.gethostname(), help="name shown on the dashboard")
    ap.add_argument("--once", action="store_true", help="post one snapshot and exit")
    ap.add_argument("--install", action="store_true", help="install as a systemd user service")
    args = ap.parse_args()

    if args.install:
        install_service(args.url, args.token, args.interval)
        return 0

    while True:
        projects = scan(args.days)
        try:
            post_snapshot(args.url, args.token, args.machine, projects)
            print(f"reported {len(projects)} projects", flush=True)
        except (urllib.error.URLError, OSError) as exc:
            print(f"report failed: {exc}", file=sys.stderr, flush=True)
        if args.once:
            return 0
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    sys.exit(main())
