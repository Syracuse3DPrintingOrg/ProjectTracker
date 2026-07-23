"""The notification inbox API. Every route is self-scoped: the signed-in
user sees and clears only their own rows, whatever their role."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..services import notifications

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _me(request: Request) -> int:
    """The signed-in user's id. Anonymous callers and API keys (which
    carry a role but no user) have no inbox."""
    user = getattr(request.state, "user", None)
    if not user or not user.get("id"):
        raise HTTPException(401, "sign in to see notifications")
    return user["id"]


class ReadIn(BaseModel):
    ids: list[int] = []
    all: bool = False


@router.get("")
def list_notifications(request: Request, unread_only: bool = False):
    uid = _me(request)
    return {
        "unread": notifications.unread_count(uid),
        "items": notifications.list_for_user(uid, unread_only=unread_only),
    }


@router.post("/read")
def mark_read(body: ReadIn, request: Request):
    uid = _me(request)
    if not body.ids and not body.all:
        raise HTTPException(422, "pass ids or all=true")
    marked = notifications.mark_read(uid, None if body.all else body.ids)
    return {"marked": marked, "unread": notifications.unread_count(uid)}
