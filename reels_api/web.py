"""Everything the phone page needs that is not the JSON API: login, page shells, static files."""
from __future__ import annotations

import secrets
import time
from pathlib import PurePath
from typing import Callable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles

from reels_api import pages
from reels_api.auth import (
    AGREED,
    SESSION_COOKIE,
    UNASKED,
    require_access,
    session_cookie_value,
    session_is_valid,
    session_state,
    share_key_matches,
    unauthorized,
)
from reels_api.models import JobStatus
from reels_api.pages import STATIC_DIR

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 15 * 60
COOKIE_MAX_AGE_SECONDS = 365 * 24 * 3600
# Set and deleted with the same attributes; a different path would leave the cookie in place.
SESSION_COOKIE_ATTRS = {"path": "/", "secure": True, "httponly": True, "samesite": "lax"}
NO_CACHE = {"Cache-Control": "no-cache"}
NO_STORE = {"Cache-Control": "no-store"}
TOO_MANY_ATTEMPTS = {"error": "too_many_attempts", "message": "Too many wrong tries. Wait 15 minutes and try again."}
INVALID_INVITE = {"error": "invalid_invite", "message": "That invite link is not right."}

router = APIRouter(include_in_schema=False)


class LoginRequest(BaseModel):
    passcode: str


class AttemptLimiter:
    """Per-IP failed-login counter. Every call prunes every entry, so it cannot grow unbounded."""

    def __init__(
        self,
        max_attempts: int = MAX_ATTEMPTS,
        window_seconds: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._clock = clock
        self._attempts: dict[str, list[float]] = {}

    def _prune(self) -> None:
        cutoff = self._clock() - self.window_seconds
        for ip in list(self._attempts):
            kept = [t for t in self._attempts[ip] if t > cutoff]
            if kept:
                self._attempts[ip] = kept
            else:
                del self._attempts[ip]

    def is_blocked(self, ip: str) -> bool:
        self._prune()
        return len(self._attempts.get(ip, ())) >= self.max_attempts

    def record_failure(self, ip: str) -> None:
        self._prune()
        self._attempts.setdefault(ip, []).append(self._clock())

    def clear(self, ip: str) -> None:
        self._attempts.pop(ip, None)


# mimetypes may say application/javascript (Windows registry) and knows no .woff2 (Python 3.12).
FORCED_CONTENT_TYPES = {".js": "text/javascript; charset=utf-8", ".woff2": "font/woff2"}


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles that asks browsers to revalidate on every load (ETag makes that cheap)."""

    def file_response(self, full_path, *args, **kwargs) -> Response:
        response = super().file_response(full_path, *args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        content_type = FORCED_CONTENT_TYPES.get(PurePath(str(full_path)).suffix)
        if content_type:
            response.headers["Content-Type"] = content_type
        return response


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "login.html", media_type="text/html", headers=NO_STORE)


def _base_url(request: Request) -> str:
    """Scheme and host for absolute links in preview tags, without a trailing slash."""
    configured = request.app.state.settings.public_base_url
    return (configured or str(request.base_url)).rstrip("/")


def _app_page(ask: bool) -> HTMLResponse:
    return HTMLResponse(pages.render_app(ask), headers=NO_STORE)


def _login_or_ask(state: str | None) -> Response:
    """Where the login page goes: a cookie set before the login page asked gets the board and its pop-up."""
    return _app_page(ask=True) if state == UNASKED else _login_page()


@router.get("/")
async def index(request: Request, reel: str | None = None, k: str | None = None) -> Response:
    """The board, a shared reel, an expired reel or the login page, checked in that order (pop-up spec 4).

    A share link behaves the same for an unasked cookie as for no cookie. Only the login page is
    swapped for the board with the cookie pop-up.
    """
    settings = request.app.state.settings
    state = session_state(settings, request.cookies.get(SESSION_COOKIE))
    if state == AGREED:
        return _app_page(ask=False)
    if not reel or not k:
        return _login_or_ask(state)
    job = await request.app.state.store.get(reel)
    if job is None:
        return HTMLResponse(pages.render_expired(settings.retention_hours), headers=NO_STORE)
    if not share_key_matches(job, k):
        return _login_or_ask(state)  # a guessed key gets the same answer as no key
    if job.status != JobStatus.DONE or job.result is None or not job.result.file_path.is_file():
        return HTMLResponse(pages.render_expired(settings.retention_hours), headers=NO_STORE)
    return HTMLResponse(pages.render_watch(job, _base_url(request)), headers=NO_STORE)


def _set_session_cookie(response: Response, settings) -> None:
    """The one login cookie, set by the passcode form and by the invite link."""
    response.set_cookie(
        SESSION_COOKIE,
        session_cookie_value(settings),
        max_age=COOKIE_MAX_AGE_SECONDS,
        **SESSION_COOKIE_ATTRS,
    )


@router.post("/web/login", status_code=204)
async def login(body: LoginRequest, request: Request, response: Response) -> None:
    settings = request.app.state.settings
    limiter: AttemptLimiter = request.app.state.login_limiter
    ip = _client_ip(request)
    if limiter.is_blocked(ip):
        raise HTTPException(status_code=429, detail=TOO_MANY_ATTEMPTS)
    # Compare bytes: compare_digest rejects non-ASCII str, and a passcode may contain any character.
    if not secrets.compare_digest(body.passcode.encode(), settings.web_passcode.encode()):
        limiter.record_failure(ip)
        raise HTTPException(
            status_code=401,
            detail={"error": "wrong_passcode", "message": "That passcode is not right."},
        )
    limiter.clear(ip)
    _set_session_cookie(response, settings)


@router.post("/web/logout", status_code=204, dependencies=[Depends(require_access)])
async def logout(response: Response) -> None:
    """Deletes this phone's login cookie (cookie spec 5.3).

    The cookie value is shared, so other phones stay logged in. Requiring access means a
    cross-site POST, which carries no SameSite=Lax cookie, gets 401 and deletes nothing.
    """
    response.delete_cookie(SESSION_COOKIE, **SESSION_COOKIE_ATTRS)


@router.post("/web/cookie", status_code=204)
async def agree_to_cookie(request: Request) -> Response:
    """allow cookie on the board's pop-up: re-sets this phone's cookie with the agreed value (pop-up spec 5.2).

    Checks the cookie itself rather than require_access: an API key alone has no cookie to mark.
    A cross-site POST carries no SameSite=Lax cookie, so it gets 401 and cannot agree for anyone.
    """
    settings = request.app.state.settings
    if not session_is_valid(settings, request.cookies.get(SESSION_COOKIE)):
        raise HTTPException(status_code=401, detail=unauthorized().detail, headers=NO_STORE)
    response = Response(status_code=204, headers=NO_STORE)
    _set_session_cookie(response, settings)
    return response


@router.get("/manifest.webmanifest")
async def manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json", headers=NO_CACHE)


@router.get("/sw.js")
async def service_worker() -> FileResponse:
    # Served at the root so its scope is "/".
    return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript", headers=NO_CACHE)


def _invite_token_matches(settings, token: str) -> bool:
    # Compare bytes: compare_digest rejects non-ASCII str, and a URL path may contain any character.
    return secrets.compare_digest(token.encode(), settings.invite_token.encode())


async def join(token: str, request: Request) -> Response:
    """The invite link asks first: the right token gets the login page in invite mode, never a cookie (cookie spec 5.1).

    WhatsApp's preview fetcher GETs this link too, so a GET must not log anything in.
    """
    settings = request.app.state.settings
    to_board = RedirectResponse("/", status_code=303, headers=NO_STORE)
    if session_is_valid(settings, request.cookies.get(SESSION_COOKIE)):
        return to_board  # already agreed and logged in
    limiter: AttemptLimiter = request.app.state.login_limiter
    ip = _client_ip(request)
    if limiter.is_blocked(ip):
        return to_board
    if not _invite_token_matches(settings, token):
        limiter.record_failure(ip)
        return to_board
    return _login_page()


async def accept_invite(token: str, request: Request) -> Response:
    """Allow cookie & join: the right token sets the login cookie (cookie spec 5.2)."""
    settings = request.app.state.settings
    limiter: AttemptLimiter = request.app.state.login_limiter
    ip = _client_ip(request)
    if limiter.is_blocked(ip):
        raise HTTPException(status_code=429, detail=TOO_MANY_ATTEMPTS, headers=NO_STORE)
    if not _invite_token_matches(settings, token):
        limiter.record_failure(ip)
        raise HTTPException(status_code=401, detail=INVALID_INVITE, headers=NO_STORE)
    limiter.clear(ip)
    response = Response(status_code=204, headers=NO_STORE)
    _set_session_cookie(response, settings)
    return response


def install(app: FastAPI) -> None:
    """Attach the web page to the app. Only called when WEB_PASSCODE is set."""
    app.state.login_limiter = AttemptLimiter()
    app.include_router(router)
    if app.state.settings.invite_token:
        app.add_api_route("/join/{token}", join, methods=["GET"], include_in_schema=False)
        app.add_api_route("/join/{token}", accept_invite, methods=["POST"], include_in_schema=False)
    app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")
