import hashlib
import hmac
import secrets

from fastapi import Header, HTTPException, Request

from reels_api.models import Job
from reels_api.settings import Settings

SESSION_COOKIE = "reels_session"
AGREED = "agreed"
UNASKED = "unasked"
# The cookie value records whether the phone agreed to it (pop-up spec 3).
_AGREED_PREFIX = b"reels-web-session-agreed:"
_UNASKED_PREFIX = b"reels-web-session:"  # set before the login page asked


def _session_hmac(settings: Settings, prefix: bytes) -> str:
    passcode = settings.web_passcode or ""
    return hmac.new(settings.api_key.encode(), prefix + passcode.encode(), hashlib.sha256).hexdigest()


def session_cookie_value(settings: Settings) -> str:
    """The value every login sets: the phone agreed. Changing API_KEY or WEB_PASSCODE rotates it."""
    return _session_hmac(settings, _AGREED_PREFIX)


def unasked_cookie_value(settings: Settings) -> str:
    """The value set before the login page asked. It still logs in, but the board asks first."""
    return _session_hmac(settings, _UNASKED_PREFIX)


def session_state(settings: Settings, cookie: str | None) -> str | None:
    """AGREED or UNASKED for a cookie that logs in, None otherwise."""
    if not settings.web_passcode or not cookie:
        return None
    # Compare bytes: compare_digest rejects non-ASCII str, and a cookie may contain any character.
    given = cookie.encode()
    if secrets.compare_digest(given, session_cookie_value(settings).encode()):
        return AGREED
    if secrets.compare_digest(given, unasked_cookie_value(settings).encode()):
        return UNASKED
    return None


def session_is_valid(settings: Settings, cookie: str | None) -> bool:
    return session_state(settings, cookie) is not None


def share_key_matches(job: Job | None, key: str | None) -> bool:
    """True when key is this job's share key. Never true without a job or a key (links spec 5.2)."""
    if job is None or not key:
        return False
    # Compare bytes: compare_digest rejects non-ASCII str, and a query string may contain any character.
    return secrets.compare_digest(key.encode(), job.share_key.encode())


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": "unauthorized", "message": "Missing or invalid API key."},
    )


def has_access(request: Request, x_api_key: str | None) -> bool:
    """True when the API key header or the web session cookie is valid."""
    settings: Settings = request.app.state.settings
    if x_api_key and secrets.compare_digest(x_api_key, settings.api_key):
        return True
    return session_is_valid(settings, request.cookies.get(SESSION_COOKIE))


async def require_access(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Allow the request when the API key header or the web session cookie is valid."""
    if not has_access(request, x_api_key):
        raise unauthorized()
