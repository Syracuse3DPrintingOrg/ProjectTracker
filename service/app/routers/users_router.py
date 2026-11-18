"""User management (admin) and self-service account endpoints."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from ..services import notifications, users
from .pages import templates

router = APIRouter(tags=["users"])


class UserIn(BaseModel):
    username: str
    password: str
    role: str = "member"


class UserUpdate(BaseModel):
    role: str | None = None
    password: str | None = None
    disabled: bool | None = None


class PasswordChange(BaseModel):
    current_password: str = ""
    new_password: str


class WebhookIn(BaseModel):
    webhook_url: str = ""


@router.get("/api/users")
def list_users():
    return users.list_users()


@router.post("/api/users", status_code=201)
def create_user(body: UserIn):
    try:
        return users.create_user(body.username, body.password, body.role)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.patch("/api/users/{user_id}")
def update_user(body: UserUpdate, user_id: int):
    try:
        user = users.update_user(user_id, **body.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if not user:
        raise HTTPException(404)
    return user


@router.delete("/api/users/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request):
    me = getattr(request.state, "user", None)
    if me and me["id"] == user_id:
        raise HTTPException(422, "you cannot delete yourself while logged in")
    try:
        if not users.delete_user(user_id):
            raise HTTPException(404)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.post("/api/account/password")
def change_password(body: PasswordChange, request: Request):
    me = getattr(request.state, "user", None)
    if not me:
        raise HTTPException(401)
    if len(body.new_password) < 4:
        raise HTTPException(422, "password must be at least 4 characters")
    if not users.change_own_password(
        me["id"], body.current_password, body.new_password
    ):
        raise HTTPException(422, "current password is wrong")
    # The password change invalidates every session, including this one;
    # the client should send the user to the login page.
    return {"ok": True, "relogin": True}


@router.post("/api/account/webhook")
def set_webhook(body: WebhookIn, request: Request):
    me = getattr(request.state, "user", None)
    if not me or not me.get("id"):
        raise HTTPException(401)
    url = body.webhook_url.strip()
    if len(url) > 500:
        raise HTTPException(422, "that URL is too long")
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(422, "the webhook URL must start with http:// or https://")
    notifications.set_webhook(me["id"], url)
    return {"ok": True, "webhook_url": url}


@router.get("/account")
def account_page(request: Request, linked: bool = False):
    from .. import config
    from .pages import login_context

    me = getattr(request.state, "user", None)
    if not me:
        return RedirectResponse("/login?next=/account", status_code=303)
    return templates.TemplateResponse(
        request,
        "account.html",
        {
            **login_context(request, config.load_settings(), "/account", ""),
            "me": me,
            "linked_now": linked,
        },
    )
