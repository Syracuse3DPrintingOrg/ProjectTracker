"""Claude Code connector endpoints and dashboard."""

import hmac
import secrets

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from .. import config
from ..services import connectors, store
from .pages import _page_context, templates

router = APIRouter(tags=["connectors"])


class SnapshotIn(BaseModel):
    machine: str
    projects: list = []


class LinkIn(BaseModel):
    claude_path: str = ""


def _connector_token(settings: dict | None = None) -> str:
    s = settings or config.load_settings()
    token = s.get("connector_token", "")
    if not token:
        token = secrets.token_urlsafe(24)
        config.save_settings({"connector_token": token})
    return token


@router.post("/api/connectors/claude-code")
def post_snapshot(
    body: SnapshotIn, x_connector_token: str = Header(default="")
):
    expected = _connector_token()
    if not x_connector_token or not hmac.compare_digest(x_connector_token, expected):
        raise HTTPException(401, "bad connector token")
    snapshot = connectors.store_snapshot(body.machine, body.projects)
    return {"ok": True, "projects": len(snapshot["projects"])}


@router.get("/api/connectors/claude-code")
def get_snapshots():
    links = {
        p["claude_path"]: {"id": p["id"], "name": p["name"]}
        for p in store.list_projects()
        if p.get("claude_path")
    }
    snaps = connectors.snapshots()
    for snap in snaps:
        for project in snap["projects"]:
            if project["path"] in links:
                project["tracker_project"] = links[project["path"]]
    return {"machines": snaps, "known_paths": connectors.known_paths()}


@router.post("/api/projects/{project_id}/claude-link")
def link_project(project_id: int, body: LinkIn):
    if not store.get_project(project_id):
        raise HTTPException(404)
    store.set_claude_link(project_id, body.claude_path)
    return store.get_project(project_id)


@router.delete("/api/connectors/claude-code/{machine}", status_code=204)
def forget_machine(machine: str):
    if not connectors.forget_machine(machine):
        raise HTTPException(404)


@router.get("/dashboard/claude-code")
def dashboard(request: Request):
    settings = config.load_settings()
    return templates.TemplateResponse(
        request,
        "dashboard_claude.html",
        {
            **_page_context(settings),
            "connector_token": _connector_token(settings),
            "tracker_projects": store.list_projects(),
        },
    )
