"""Sign in with Pocket ID, linking accounts, and the admin recovery login."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from .. import config
from ..services import auth, oidc, users
from .pages import login_context, safe_next, templates

router = APIRouter(tags=["auth"])


def _login_error(request: Request, message: str, status: int = 400):
    settings = config.load_settings()
    return templates.TemplateResponse(
        request,
        "login.html",
        login_context(request, settings, "/", message),
        status_code=status,
    )


@router.get("/auth/oidc/start")
def oidc_start(request: Request, next: str = "/", link: bool = False):
    settings = config.load_settings()
    if not oidc.configured(settings):
        raise HTTPException(404, "Pocket ID sign-in is not set up")
    link_uid = None
    if link:
        me = getattr(request.state, "user", None)
        if not me or not me.get("id"):
            return RedirectResponse("/login?next=/account", status_code=303)
        link_uid = me["id"]
        next = "/account"
    try:
        url, state = oidc.begin(safe_next(next), link_uid)
    except oidc.OidcError as exc:
        return _login_error(request, str(exc), 503)
    response = RedirectResponse(url, status_code=303)
    # Lax, not Strict: Strict drops the cookie on Pocket ID's redirect back.
    response.set_cookie(
        oidc.STATE_COOKIE,
        state,
        max_age=oidc.STATE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=oidc.cookie_secure(settings),
        path="/auth/oidc",
    )
    return response


@router.get("/auth/oidc/callback")
def oidc_callback(
    request: Request,
    code: str = "",
    state: str = "",
    iss: str | None = None,
    error: str = "",
):
    settings = config.load_settings()
    try:
        trip = oidc.take(state, request.cookies.get(oidc.STATE_COOKIE))
        if error or not code:
            raise oidc.OidcError("Pocket ID did not sign you in. Try again.")
        claims = oidc.finish(code, trip, iss)
    except oidc.OidcError as exc:
        response = _login_error(request, str(exc))
        response.delete_cookie(oidc.STATE_COOKIE, path="/auth/oidc")
        return response

    sub = str(claims["sub"])
    if trip.get("link"):
        me = users.get_user(trip["link"])
        if not me or me.get("disabled"):
            return _login_error(request, "Sign in again, then link Pocket ID from your account page.")
        try:
            users.link_sub(me["id"], sub)
        except ValueError as exc:
            return _login_error(request, str(exc), 409)
        users.sync_role(me["id"], oidc.groups(claims), oidc.ADMIN_GROUP)
        response = RedirectResponse("/account?linked=1", status_code=303)
    else:
        user = users.get_by_sub(sub)
        if not user or user.get("disabled"):
            return _login_error(
                request,
                "That Pocket ID account is not linked to anyone in SQ yet. "
                "Sign in the usual way once, then link it from your account page.",
                403,
            )
        users.sync_role(user["id"], oidc.groups(claims), oidc.ADMIN_GROUP)
        response = RedirectResponse(trip.get("next") or "/", status_code=303)
        user = users.get_by_sub(sub)
        auth.set_session(response, user, auth.METHOD_OIDC, oidc.cookie_secure(settings))
    response.delete_cookie(oidc.STATE_COOKIE, path="/auth/oidc")
    return response


@router.post("/api/account/oidc/unlink")
def oidc_unlink(request: Request):
    me = getattr(request.state, "user", None)
    if not me or not me.get("id"):
        raise HTTPException(401)
    if oidc.only():
        raise HTTPException(
            422, "Pocket ID is the only way in right now, so it cannot be unlinked."
        )
    users.unlink_sub(me["id"])
    return {"ok": True}


@router.get("/login/recovery")
def recovery_page(request: Request, next: str = "/"):
    settings = config.load_settings()
    if not oidc.only(settings):
        return RedirectResponse("/login", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        login_context(request, settings, safe_next(next), "", recovery=True),
    )


@router.post("/login/recovery")
def recovery_login(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    next: str = Form("/"),
):
    """The way back in for admins when Pocket ID is down. Members and
    viewers wait for Pocket ID; an admin can still reach everything."""
    settings = config.load_settings()
    if not oidc.only(settings):
        return RedirectResponse("/login", status_code=303)
    user = users.verify_login(username, password)
    if user and user["role"] == "admin":
        response = RedirectResponse(safe_next(next), status_code=303)
        auth.set_session(response, user, auth.METHOD_RECOVERY, oidc.cookie_secure(settings))
        return response
    return templates.TemplateResponse(
        request,
        "login.html",
        login_context(
            request, settings, safe_next(next),
            "Wrong username or password, or not an admin.", recovery=True,
        ),
        status_code=401,
    )
