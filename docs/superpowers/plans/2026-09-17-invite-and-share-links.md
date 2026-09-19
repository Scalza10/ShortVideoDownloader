# Invite Link and Share Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let friends in with one invite link, let anyone open a shared reel on a view-only page (with a WhatsApp preview) without ever seeing the pile, and grow the pile to 100 reels.

**Architecture:** Every job gets a random `share_key`. `/files/<id>.mp4|jpg` accept `?k=<share_key>` for that reel only. `GET /` picks the board (cookie), the view-only page (right key), the expired page (reel gone) or the login page. A new `reels_api/pages.py` renders the two new pages from HTML templates with `{{name}}` placeholders and fills in Open Graph tags on the server, because link-preview fetchers run no JavaScript. The view-only page reuses `player.js` in a new `standalone` mode. `GET /join/<INVITE_TOKEN>` sets the same cookie as the passcode.

**Tech Stack:** Python 3.12, FastAPI, pydantic-settings, pytest + anyio (existing); stdlib `html`, `json`, `re`, `secrets`; plain HTML, CSS and ES modules; Node 22 only for `node --check` syntax checks.

**Spec:** `docs/superpowers/specs/2026-09-17-invite-and-share-links-design.md` (the "links spec"). Read it first; this plan argues from it. It builds on `docs/superpowers/specs/2026-09-16-reels-board-ui-design.md` (the "board spec").

## Global Constraints

- No new Python or JS dependencies. No template engine, no build step, no framework, no JS test harness.
- Automated tests run with no network and no ffmpeg: `.venv/Scripts/python.exe -m pytest -q` from the repo root (Git Bash) or `.venv\Scripts\python.exe -m pytest -q` (PowerShell). The suite is green (166 passed, 1 deselected) before Task 1.
- JS syntax check after every JS edit: `node --check reels_api/static/<file>.js` (Node 22 detects ES modules).
- Share key: `secrets.token_urlsafe(12)`, 16 URL-safe characters. Share link: `<origin>/?reel=<id>&k=<share_key>`.
- `INVITE_TOKEN`: unset or empty means disabled; when set, at least 16 characters.
- Compare secrets with `secrets.compare_digest` on bytes (`.encode()`), never on `str`.
- Every response from `GET /` and `GET /join/{token}` sends `Cache-Control: no-store`.
- UI and preview copy, exactly: `have the passcode? log in` (with `log in` inside `<u>`), `this reel has expired`, `reels only stay up for 12 hours` / `1 hour`, `tap for options`, `couldn't play that one`, `a reel`, `reels your friends pasted. no names, ever.`
- Every commit message ends with a second `-m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"`.
- ffmpeg is not installed locally. Manual checks use the dev server inside Docker (Task 7 shows the command) and Chrome at 390×844 (DevTools device mode, touch) and 1280×800. Before tapping **Share** or **Save** in an automated browser, stub `navigator.share`: `Object.defineProperty(navigator, "share", { configurable: true, value: (data) => { console.log("share", data); return Promise.resolve(); } })`.

## File map

| file | change | responsibility |
|------|--------|----------------|
| `reels_api/settings.py` | modify | `max_videos` default 100; `invite_token` (empty → None, min 16) |
| `reels_api/jobs.py` | modify | `JobStore.list_recent` returns every done job by default |
| `reels_api/models.py` | modify | `new_share_key()`, `Job.share_key`, `share_key` in `job_to_dict` for done jobs |
| `reels_api/auth.py` | modify | `has_access`, `share_key_matches`, public `unauthorized` |
| `reels_api/routes.py` | modify | file routes accept key, cookie or `k` |
| `reels_api/pages.py` | create | render `watch.html` and `expired.html`, preview text, safe JSON |
| `reels_api/web.py` | modify | `GET /` routing, `GET /join/{token}`, shared set-cookie helper |
| `reels_api/static/watch.html` | create | view-only page template |
| `reels_api/static/expired.html` | create | expired page template |
| `reels_api/static/watch.js` | create | reads the reel data, opens the standalone player, handles video errors |
| `reels_api/static/player.js` | modify | `standalone` option; share links with `k` |
| `reels_api/static/style.css` | modify | `.login-hint`, `.expired-note` |
| `reels_api/static/app.html`, `login.html` | modify | static preview tags, `robots` `noindex` |
| `scripts/dev_board.py` | modify | invite token, prints invite and share links, default `max_videos` |
| `.env.example` | modify | `INVITE_TOKEN`, `MAX_VIDEOS=100` |
| `README.md`, `CLAUDE.md` | modify | document the feature |
| `tests/test_settings.py`, `test_jobs.py`, `test_models.py`, `test_routes.py`, `test_web.py`, `test_dev_board.py` | modify | per task |
| `tests/test_pages.py` | create | rendering unit tests |

The links spec's code layout puts page rendering in `web.py`. This plan puts it in a new `pages.py`, so rendering is testable without HTTP and `web.py` keeps only routing. Behaviour is unchanged.

---

### Task 1: The pile holds 100 reels

**Files:**
- Modify: `reels_api/settings.py:17` (`max_videos`)
- Modify: `reels_api/jobs.py:44` (`JobStore.list_recent`)
- Modify: `.env.example` (`MAX_VIDEOS`)
- Test: `tests/test_settings.py`, `tests/test_jobs.py`, `tests/test_routes.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `Settings.max_videos` defaults to `100`. `JobStore.list_recent(limit: int | None = None) -> list[Job]` returns every done job, newest first, when called without `limit`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_settings.py`, in `test_defaults_applied`, change:

```python
    assert s.max_videos == 10
```

to:

```python
    assert s.max_videos == 100
```

In `tests/test_jobs.py`, replace the whole `test_list_recent_default_cap_is_50` test with:

```python
@pytest.mark.anyio
async def test_list_recent_returns_every_done_job_by_default():
    store = JobStore()
    now = datetime.now(UTC)
    for i in range(60):
        await store.add(_done_job(f"j{i}", i, now))
    recent = await store.list_recent()
    assert len(recent) == 60
    assert recent[0].id == "j0"
```

In `tests/test_routes.py`, replace the imports at the top of the file with:

```python
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reels_api.auth import SESSION_COOKIE, session_cookie_value
from reels_api.main import create_app
from reels_api.models import ErrorCode, Job, JobError, JobResult, JobStatus, Source
from reels_api.routes import slugify
from tests.conftest import make_settings
```

and add at the end of the file:

```python
def test_list_jobs_returns_every_stored_reel(app_factory):
    with TestClient(app_factory()) as client:
        now = datetime.now(UTC)
        for i in range(60):
            job = Job(id=f"j{i:02d}", url=f"https://vm.tiktok.com/{i}/", source=Source.TIKTOK, status=JobStatus.DONE)
            job.finished_at = now - timedelta(minutes=i)
            job.result = JobResult(Path(f"j{i:02d}.mp4"), "T", Source.TIKTOK, 1.0, 1, 1, 1)
            client.app.state.store._jobs[job.id] = job
        jobs = client.get("/jobs", headers=HEADERS).json()["jobs"]
    assert len(jobs) == 60
    assert jobs[0]["id"] == "j00"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_settings.py::test_defaults_applied tests/test_jobs.py::test_list_recent_returns_every_done_job_by_default tests/test_routes.py::test_list_jobs_returns_every_stored_reel -q`

Expected: 3 failed: `assert 10 == 100`, `assert 50 == 60`, `assert 50 == 60`.

- [ ] **Step 3: Implement**

In `reels_api/settings.py`, change:

```python
    max_videos: int = Field(10, ge=1)  # oldest finished videos are deleted beyond this
```

to:

```python
    max_videos: int = Field(100, ge=1)  # oldest finished videos are deleted beyond this
```

In `reels_api/jobs.py`, change:

```python
    async def list_recent(self, limit: int | None = 50) -> list[Job]:
```

to:

```python
    async def list_recent(self, limit: int | None = None) -> list[Job]:
```

In `.env.example`, change `MAX_VIDEOS=10` to `MAX_VIDEOS=100`.

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: all pass (167 passed, 1 deselected).

- [ ] **Step 5: Commit**

```bash
git add reels_api/settings.py reels_api/jobs.py .env.example tests/test_settings.py tests/test_jobs.py tests/test_routes.py
git commit -m "feat: keep up to 100 reels and list all of them on the board" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: A share key on every reel

**Files:**
- Modify: `reels_api/models.py` (imports, new `new_share_key`, `Job`, `job_to_dict`)
- Test: `tests/test_models.py`, `tests/test_routes.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `new_share_key() -> str` in `reels_api.models` (16 URL-safe characters). `Job.share_key: str`, filled at creation. `job_to_dict(job)` includes `"share_key"` for done jobs only.

- [ ] **Step 1: Write the failing tests**

In `tests/test_models.py`, add `new_share_key` to the import list:

```python
from reels_api.models import (
    WHATSAPP_MAX_BYTES,
    ErrorCode,
    Job,
    JobError,
    JobResult,
    JobStatus,
    Source,
    job_to_dict,
    new_share_key,
)
```

and add at the end of the file:

```python
def test_new_share_key_shape():
    keys = {new_share_key() for _ in range(50)}
    assert len(keys) == 50
    for key in keys:
        assert len(key) == 16
        assert all(c.isalnum() or c in "-_" for c in key)


def test_every_job_gets_its_own_share_key():
    a = Job(id="a", url="u", source=Source.TIKTOK)
    b = Job(id="b", url="u", source=Source.TIKTOK)
    assert len(a.share_key) == 16
    assert a.share_key != b.share_key


def test_job_to_dict_share_key_only_when_done():
    job = Job(id="abc", url="u", source=Source.TIKTOK)
    assert "share_key" not in job_to_dict(job)

    job.status = JobStatus.FAILED
    job.error = ErrorCode.TIMEOUT
    assert "share_key" not in job_to_dict(job)

    job.status = JobStatus.DONE
    job.result = _result(100)
    assert job_to_dict(job)["share_key"] == job.share_key
```

In `tests/test_routes.py`, add at the end of the file:

```python
def test_share_key_in_job_json_and_stable_for_same_url(app_factory):
    with TestClient(app_factory()) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
        assert len(body["share_key"]) == 16

        again = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()
        assert again["id"] == job_id
        assert client.get(f"/jobs/{job_id}", headers=HEADERS).json()["share_key"] == body["share_key"]
        assert client.get("/jobs", headers=HEADERS).json()["jobs"][0]["share_key"] == body["share_key"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_models.py tests/test_routes.py::test_share_key_in_job_json_and_stable_for_same_url -q`

Expected: collection error in `tests/test_models.py` (`ImportError: cannot import name 'new_share_key'`); the routes test fails with `KeyError: 'share_key'`.

- [ ] **Step 3: Implement**

In `reels_api/models.py`, add `import secrets` below `from __future__ import annotations`:

```python
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
```

Directly after the `utcnow` function, add:

```python
def new_share_key() -> str:
    """The secret half of a reel's share link: 16 URL-safe characters (links spec 4.1)."""
    return secrets.token_urlsafe(12)
```

Add the field as the last field of `Job`:

```python
    error: ErrorCode | None = None
    message: str | None = None
    share_key: str = field(default_factory=new_share_key)
```

In `job_to_dict`, in the `body.update({...})` for done jobs, after the `"finished_at"` entry, add:

```python
                "share_key": job.share_key,
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: all pass (171 passed, 1 deselected).

- [ ] **Step 5: Commit**

```bash
git add reels_api/models.py tests/test_models.py tests/test_routes.py
git commit -m "feat: every reel gets a share key, included in the job JSON when done" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Files open with the share key

**Files:**
- Modify: `reels_api/auth.py`
- Modify: `reels_api/routes.py` (imports, the two `/files/` routes)
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: `Job.share_key` (Task 2).
- Produces, in `reels_api.auth`:
  - `has_access(request: Request, x_api_key: str | None) -> bool`
  - `share_key_matches(job: Job | None, key: str | None) -> bool`
  - `unauthorized() -> HTTPException` (renamed from `_unauthorized`)
- `GET /files/{id}.mp4` and `GET /files/{id}.jpg` accept query parameter `k`.

- [ ] **Step 1: Write the failing tests**

Add at the end of `tests/test_routes.py`:

```python
def _done_reel(client, url="https://vm.tiktok.com/x/"):
    job_id = client.post("/jobs", json={"url": url}, headers=HEADERS).json()["id"]
    return poll_until_finished(client, job_id)


def test_share_key_opens_that_reels_files_without_login(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        key = {"k": reel["share_key"]}

        video = client.get(f"/files/{reel['id']}.mp4", params=key)
        assert video.status_code == 200
        assert video.content == b"0123456789"
        assert 'filename="my-cool-reel.mp4"' in video.headers["content-disposition"]

        part = client.get(f"/files/{reel['id']}.mp4", params=key, headers={"Range": "bytes=0-0"})
        assert part.status_code == 206

        thumb = client.get(f"/files/{reel['id']}.jpg", params=key)
        assert thumb.status_code == 200
        assert thumb.headers["cache-control"] == "private, max-age=21600"


def test_wrong_share_key_is_401(app_factory):
    with TestClient(app_factory()) as client:
        first = _done_reel(client, "https://vm.tiktok.com/1/")
        second = _done_reel(client, "https://vm.tiktok.com/2/")
        for path in (f"/files/{first['id']}.mp4", f"/files/{first['id']}.jpg"):
            for bad in ("", "nope", second["share_key"]):
                r = client.get(path, params={"k": bad})
                assert r.status_code == 401, (path, bad)
                assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}
        assert client.get("/files/nope.mp4", params={"k": first["share_key"]}).status_code == 401
        assert client.get("/files/nope.jpg", params={"k": first["share_key"]}).status_code == 401


def test_share_key_does_not_open_the_api(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        key = {"k": reel["share_key"]}
        assert client.get("/jobs", params=key).status_code == 401
        assert client.get(f"/jobs/{reel['id']}", params=key).status_code == 401
        assert client.post("/jobs", params=key, json={"url": "https://vm.tiktok.com/z/"}).status_code == 401


def test_share_key_with_missing_files_is_404(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        job = client.app.state.store._jobs[reel["id"]]
        job.result.file_path.unlink()
        job.result.thumbnail_path.unlink()
        key = {"k": reel["share_key"]}
        assert client.get(f"/files/{reel['id']}.mp4", params=key).status_code == 404
        assert client.get(f"/files/{reel['id']}.jpg", params=key).status_code == 404


def test_cookie_opens_files_without_share_key(app_factory):
    app = app_factory(web_passcode="letmein")
    with TestClient(app) as client:
        reel = _done_reel(client)
        client.cookies.set(SESSION_COOKIE, session_cookie_value(app.state.settings))
        assert client.get(f"/files/{reel['id']}.mp4").status_code == 200
        assert client.get(f"/files/{reel['id']}.jpg").status_code == 200
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_routes.py -q -k "share_key or cookie_opens_files"`

Expected: `test_share_key_opens_that_reels_files_without_login` and `test_share_key_with_missing_files_is_404` fail with 401 instead of 200/404. The others pass already (the routes still require the key); they guard against opening too much in Step 3.

- [ ] **Step 3: Implement**

Replace everything in `reels_api/auth.py` below `session_is_valid` (the `_unauthorized` and `require_access` functions) with:

```python
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
```

and add the model import below the existing imports:

```python
from reels_api.models import Job
from reels_api.settings import Settings
```

In `reels_api/routes.py`, replace the imports with:

```python
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse

from reels_api import media
from reels_api.auth import has_access, require_access, share_key_matches, unauthorized
from reels_api.downloader import ytdlp_version
from reels_api.models import CreateJobRequest, Job, JobStatus, job_to_dict
```

Replace the two file routes (`get_file` and `get_thumbnail`, both decorated with `@protected.get`) with:

```python
async def _file_job(request: Request, job_id: str, k: str | None, x_api_key: str | None) -> Job:
    """The done job behind /files/, once the API key, the cookie or its share key allows it (links spec 5.2)."""
    job = await request.app.state.store.get(job_id)
    if not has_access(request, x_api_key) and not share_key_matches(job, k):
        raise unauthorized()
    if job is None or job.status != JobStatus.DONE or job.result is None:
        raise _not_found()
    return job


@router.get("/files/{job_id}.mp4")
async def get_file(
    job_id: str, request: Request, k: str | None = None, x_api_key: str | None = Header(default=None)
) -> FileResponse:
    job = await _file_job(request, job_id, k, x_api_key)
    if not job.result.file_path.is_file():
        raise _not_found()
    return FileResponse(
        job.result.file_path,
        media_type="video/mp4",
        filename=f"{slugify(job.result.title)}.mp4",
    )


@router.get("/files/{job_id}.jpg")
async def get_thumbnail(
    job_id: str, request: Request, k: str | None = None, x_api_key: str | None = Header(default=None)
) -> FileResponse:
    job = await _file_job(request, job_id, k, x_api_key)
    thumb = job.result.thumbnail_path
    if thumb is None or not thumb.is_file():
        raise _not_found()
    return FileResponse(
        thumb,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=21600"},
    )
```

Keep `router.include_router(protected)` as the last line of the file.

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: all pass (176 passed, 1 deselected). `test_missing_or_wrong_key` and `test_unknown_job_404` still pass: no key or cookie gives 401, an authenticated unknown id gives 404.

- [ ] **Step 5: Commit**

```bash
git add reels_api/auth.py reels_api/routes.py tests/test_routes.py
git commit -m "feat: a reel's video and thumbnail open with its share key" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Invite link

**Files:**
- Modify: `reels_api/settings.py` (`invite_token`, validator)
- Modify: `reels_api/web.py` (imports, `_set_session_cookie`, `login`, new `join`, `install`)
- Modify: `.env.example`
- Test: `tests/test_settings.py`, `tests/test_web.py`

**Interfaces:**
- Consumes: `AttemptLimiter`, `session_cookie_value`, `SESSION_COOKIE` (existing).
- Produces: `Settings.invite_token: str | None`. `GET /join/{token}` registered by `web.install` when `settings.invite_token` is set. `_set_session_cookie(response, settings)` in `web.py`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_settings.py`, add `from pydantic import ValidationError` below `import pytest`, and add at the end:

```python
def test_invite_token_unset_empty_short_and_valid(monkeypatch):
    monkeypatch.setenv("API_KEY", "abc")
    monkeypatch.delenv("INVITE_TOKEN", raising=False)
    assert Settings(_env_file=None).invite_token is None

    monkeypatch.setenv("INVITE_TOKEN", "")
    assert Settings(_env_file=None).invite_token is None

    monkeypatch.setenv("INVITE_TOKEN", "a" * 15)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("INVITE_TOKEN", "a" * 16)
    assert Settings(_env_file=None).invite_token == "a" * 16
```

In `tests/test_web.py`, below `PASSCODE = "letmein"`, add:

```python
INVITE = "invite-token-0123456789"
```

and add at the end of the file:

```python
# ---- GET /join/{token}

def test_join_with_right_token_logs_in(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        r = client.get(f"/join/{INVITE}", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        assert r.headers["cache-control"] == "no-store"
        cookie = r.headers["set-cookie"]
        assert cookie.startswith(f"{SESSION_COOKIE}={session_cookie_value(client.app.state.settings)};")
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=31536000"):
            assert attr in lowered, attr
        assert client.get("/jobs").status_code == 200


def test_join_with_wrong_token_redirects_without_cookie(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        r = client.get("/join/wrong-token-0123456789", follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/"
        assert r.headers["cache-control"] == "no-store"
        assert "set-cookie" not in r.headers
        assert client.get("/jobs").status_code == 401


def test_join_blocked_after_ten_wrong_tokens(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(10):
            client.get("/join/wrong", follow_redirects=False)
        r = client.get(f"/join/{INVITE}", follow_redirects=False)
        assert r.status_code == 303
        assert "set-cookie" not in r.headers


def test_wrong_passcodes_and_wrong_tokens_share_one_limit(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(5):
            client.post("/web/login", json={"passcode": "nope"})
            client.get("/join/wrong", follow_redirects=False)
        assert client.post("/web/login", json={"passcode": PASSCODE}).status_code == 429


def test_join_404_without_invite_token(web_app):
    with TestClient(web_app()) as client:
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 404


def test_join_404_when_web_disabled(tmp_path):
    settings = make_settings(tmp_path, invite_token=INVITE)
    app = create_app(settings=settings, pipeline=FakePipeline(settings))
    with TestClient(app) as client:
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_settings.py tests/test_web.py -q -k "invite or join or share_one_limit"`

Expected: the settings test fails (no `invite_token` attribute). The right-token, wrong-token and blocked tests fail with 404 instead of 303, and the shared-limit test fails with 204 instead of 429 (the `/join` calls 404 and record nothing). The two 404 tests pass.

- [ ] **Step 3: Implement the setting**

In `reels_api/settings.py`, change `from pydantic import Field` to:

```python
from pydantic import Field, field_validator
```

and add below `web_passcode`:

```python
    invite_token: str | None = Field(None, min_length=16)  # secret in /join/<token>; empty disables it
```

and at the end of the class:

```python

    @field_validator("invite_token", mode="before")
    @classmethod
    def _empty_invite_token_is_unset(cls, value):
        return value or None
```

- [ ] **Step 4: Implement the route**

In `reels_api/web.py`, change `from fastapi.responses import FileResponse` to:

```python
from fastapi.responses import FileResponse, RedirectResponse
```

Replace the body of `login` from `limiter.clear(ip)` to the end of the function with:

```python
    limiter.clear(ip)
    _set_session_cookie(response, settings)
```

Directly above `@router.post("/web/login", status_code=204)`, add:

```python
def _set_session_cookie(response: Response, settings) -> None:
    """The one login cookie, set by the passcode form and by the invite link."""
    response.set_cookie(
        SESSION_COOKIE,
        session_cookie_value(settings),
        max_age=COOKIE_MAX_AGE_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


```

Directly above `def install(app: FastAPI) -> None:`, add:

```python
async def join(token: str, request: Request) -> RedirectResponse:
    """The invite link: the right token logs this browser in, like the passcode (links spec 5.4)."""
    settings = request.app.state.settings
    limiter: AttemptLimiter = request.app.state.login_limiter
    ip = _client_ip(request)
    response = RedirectResponse("/", status_code=303, headers=NO_STORE)
    if limiter.is_blocked(ip):
        return response
    if secrets.compare_digest(token.encode(), settings.invite_token.encode()):
        limiter.clear(ip)
        _set_session_cookie(response, settings)
    else:
        limiter.record_failure(ip)
    return response


```

Replace `install` with:

```python
def install(app: FastAPI) -> None:
    """Attach the web page to the app. Only called when WEB_PASSCODE is set."""
    app.state.login_limiter = AttemptLimiter()
    app.include_router(router)
    if app.state.settings.invite_token:
        app.add_api_route("/join/{token}", join, methods=["GET"], include_in_schema=False)
    app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")
```

In `.env.example`, below the `WEB_PASSCODE=` line, add:

```
# Secret for the invite link https://<site>/join/<token>. Empty disables it.
# Generate one with: openssl rand -hex 16
INVITE_TOKEN=
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: all pass (183 passed, 1 deselected). `test_login_success_sets_cookie` still passes with the shared helper.

- [ ] **Step 6: Commit**

```bash
git add reels_api/settings.py reels_api/web.py .env.example tests/test_settings.py tests/test_web.py
git commit -m "feat: invite link that logs a phone in like the passcode" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: View-only and expired page rendering

**Files:**
- Create: `reels_api/pages.py`
- Create: `reels_api/static/watch.html`
- Create: `reels_api/static/expired.html`
- Modify: `reels_api/static/style.css` (append)
- Test: `tests/test_pages.py` (create)

**Interfaces:**
- Consumes: `Job.share_key`, `job_to_dict` (Task 2).
- Produces, in `reels_api.pages`:
  - `STATIC_DIR: Path`
  - `fill(template: str, values: dict[str, str], raw: dict[str, str] | None = None) -> str`
  - `script_json(data: dict) -> str`
  - `preview_title(caption: str | None) -> str`
  - `preview_description(source: Source, duration_seconds: float | None) -> str`
  - `retention_text(hours: float) -> str`
  - `render_watch(job: Job, base_url: str) -> str` (job must be done with a result; `base_url` has no trailing slash)
  - `render_expired(retention_hours: float) -> str`
- `watch.html` contains `#player` (standalone markup), `#reel-data`, `#toast`, and loads `/static/watch.js` (created in Task 8).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pages.py`:

```python
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from reels_api import pages
from reels_api.models import Job, JobResult, JobStatus, Source

BASE = "https://reels.example.com"


def _job(caption="wait for it", thumbnail=True, source=Source.TIKTOK, duration=19.7) -> Job:
    job = Job(id="abc123", url="https://vm.tiktok.com/x/", source=source, status=JobStatus.DONE)
    job.finished_at = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    job.expires_at = datetime(2026, 9, 17, 22, 0, tzinfo=UTC)
    job.result = JobResult(
        file_path=Path("abc123.mp4"),
        title="Video by someone",
        source=source,
        duration_seconds=duration,
        size_bytes=100,
        width=720,
        height=1280,
        thumbnail_path=Path("abc123.jpg") if thumbnail else None,
        caption=caption,
    )
    return job


def meta(page: str, prop: str) -> str | None:
    match = re.search(rf'<meta property="{prop}" content="([^"]*)">', page)
    return html.unescape(match.group(1)) if match else None


def reel_data(page: str) -> dict:
    match = re.search(r'<script type="application/json" id="reel-data">(.*?)</script>', page, re.S)
    return json.loads(match.group(1))


def page_title(page: str) -> str:
    return html.unescape(re.search(r"<title>(.*?)</title>", page).group(1))


# ---- helpers

def test_fill_escapes_values_and_inserts_raw_values_as_is():
    template = '<p title="{{a}}">{{b}}</p>{{c}}'
    out = pages.fill(template, {"a": '"x"', "b": "<b>&"}, raw={"c": "<i>ok</i>"})
    assert out == '<p title="&quot;x&quot;">&lt;b&gt;&amp;</p><i>ok</i>'


def test_fill_does_not_rescan_inserted_values():
    assert pages.fill("{{a}}", {"a": "{{b}}"}) == "{{b}}"


def test_fill_missing_value_raises():
    with pytest.raises(KeyError):
        pages.fill("{{nope}}", {})


def test_script_json_cannot_close_the_script():
    data = {"caption": "</script><b>&amp;"}
    text = pages.script_json(data)
    assert "<" not in text and ">" not in text and "&" not in text
    assert json.loads(text) == data


def test_preview_title():
    assert pages.preview_title("  wait\n\nfor   it ") == "wait for it"
    assert pages.preview_title(None) == "a reel"
    assert pages.preview_title("   ") == "a reel"
    assert pages.preview_title("x" * 100) == "x" * 100
    long = pages.preview_title("y" * 101)
    assert long == "y" * 99 + "…"
    assert len(long) == 100


def test_preview_description():
    assert pages.preview_description(Source.TIKTOK, 19.7) == "TikTok · 0:19"
    assert pages.preview_description(Source.INSTAGRAM, 125) == "Instagram · 2:05"
    assert pages.preview_description(Source.TIKTOK, None) == "TikTok"
    assert pages.preview_description(Source.TIKTOK, float("nan")) == "TikTok"


def test_retention_text():
    assert pages.retention_text(12) == "12 hours"
    assert pages.retention_text(1) == "1 hour"
    assert pages.retention_text(1.5) == "1.5 hours"


# ---- view-only page

def test_render_watch_tags_and_reel_data():
    job = _job()
    key = job.share_key
    page = pages.render_watch(job, BASE)

    assert "{{" not in page
    assert page_title(page) == "wait for it"
    assert meta(page, "og:title") == "wait for it"
    assert meta(page, "og:description") == "TikTok · 0:19"
    assert meta(page, "og:image") == f"{BASE}/files/abc123.jpg?k={key}"
    assert meta(page, "og:url") == f"{BASE}/?reel=abc123&k={key}"
    assert meta(page, "og:type") == "video.other"
    assert meta(page, "og:site_name") == "reels"
    assert '<meta name="robots" content="noindex">' in page
    assert '<meta name="referrer" content="strict-origin-when-cross-origin">' in page
    assert '<script type="module" src="/static/watch.js"></script>' in page

    data = reel_data(page)
    assert data["id"] == "abc123"
    assert data["file_url"] == f"/files/abc123.mp4?k={key}"
    assert data["thumbnail_url"] == f"/files/abc123.jpg?k={key}"
    assert data["caption"] == "wait for it"
    assert data["source"] == "tiktok"


def test_render_watch_has_standalone_player_markup():
    page = pages.render_watch(_job(), BASE)
    assert 'id="player"' in page
    assert 'id="toast"' in page
    assert page.count('data-action="save"') == 2
    assert page.count('href="/?reel=abc123"') == 2
    assert "have the passcode? <u>log in</u>" in page
    assert "tap for options" in page
    for gone in ("close", "prev", "next", "share", "copy", "whatsapp"):
        assert f'data-action="{gone}"' not in page, gone


def test_render_watch_escapes_a_hostile_caption():
    caption = 'x</script><script>alert("hi")</script> & more'
    page = pages.render_watch(_job(caption=caption), BASE)
    assert "<script>alert" not in page
    assert page_title(page) == caption
    assert meta(page, "og:title") == caption
    assert reel_data(page)["caption"] == caption


def test_render_watch_without_thumbnail():
    page = pages.render_watch(_job(thumbnail=False), BASE)
    assert meta(page, "og:image") is None
    assert reel_data(page)["thumbnail_url"] is None


def test_render_watch_instagram_without_duration():
    page = pages.render_watch(_job(source=Source.INSTAGRAM, duration=None), BASE)
    assert meta(page, "og:description") == "Instagram"


# ---- expired page

def test_render_expired():
    page = pages.render_expired(12)
    assert "{{" not in page
    assert "this reel has expired" in page
    assert "reels only stay up for 12 hours" in page
    assert 'href="/"' in page
    assert "have the passcode? <u>log in</u>" in page
    assert meta(page, "og:title") == "reels"
    assert meta(page, "og:description") == "this reel has expired"
    assert '<meta name="robots" content="noindex">' in page
    assert "reels only stay up for 1 hour<" in pages.render_expired(1)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_pages.py -q`

Expected: collection error, `ImportError: cannot import name 'pages' from 'reels_api'`.

- [ ] **Step 3: Create `reels_api/pages.py`**

```python
"""Pages for people without the cookie: a shared reel and an expired one (links spec 6, 7).

The HTML lives in static/ with {{name}} placeholders. Link-preview fetchers run no
JavaScript, so everything a preview needs is filled in here, on the server.
"""
from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

from reels_api.models import Job, Source, job_to_dict

STATIC_DIR = Path(__file__).parent / "static"
TITLE_MAX = 100
SOURCE_NAMES = {Source.TIKTOK: "TikTok", Source.INSTAGRAM: "Instagram"}
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def fill(template: str, values: dict[str, str], raw: dict[str, str] | None = None) -> str:
    """Replace each {{name}}: from raw as is, otherwise from values, HTML-escaped. Unknown names raise KeyError."""
    raw = raw or {}

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name in raw:
            return raw[name]
        return html.escape(values[name], quote=True)

    return _PLACEHOLDER.sub(replace, template)


def script_json(data: dict) -> str:
    """JSON that is safe inside <script type="application/json">: <, > and & become \\u escapes."""
    return json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def preview_title(caption: str | None) -> str:
    """The caption on one line, at most 100 characters; "a reel" when there is none."""
    text = " ".join((caption or "").split())
    if not text:
        return "a reel"
    if len(text) > TITLE_MAX:
        return text[: TITLE_MAX - 1] + "…"
    return text


def _duration(seconds: float | None) -> str:
    """m:ss, floored; "" when unknown. Same rules as formatDuration in format.js."""
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return ""
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def preview_description(source: Source, duration_seconds: float | None) -> str:
    """ "TikTok · 0:19", without the duration when it is unknown. No expiry: previews are cached."""
    return " · ".join(part for part in (SOURCE_NAMES[source], _duration(duration_seconds)) if part)


def retention_text(hours: float) -> str:
    return f"{hours:g} hour" + ("" if hours == 1 else "s")


def render_watch(job: Job, base_url: str) -> str:
    """The view-only page for a done job. base_url has no trailing slash (links spec 6.1, 7.1)."""
    result = job.result
    key = job.share_key
    reel = job_to_dict(job)
    reel["file_url"] = f"/files/{job.id}.mp4?k={key}"
    if reel["thumbnail_url"]:
        reel["thumbnail_url"] = f"/files/{job.id}.jpg?k={key}"

    image_tag = ""
    if result.thumbnail_path is not None:
        image_url = html.escape(f"{base_url}/files/{job.id}.jpg?k={key}", quote=True)
        image_tag = f'<meta property="og:image" content="{image_url}">'

    template = (STATIC_DIR / "watch.html").read_text(encoding="utf-8")
    return fill(
        template,
        {
            "id": job.id,
            "title": preview_title(reel["caption"]),
            "description": preview_description(result.source, result.duration_seconds),
            "url": f"{base_url}/?reel={job.id}&k={key}",
        },
        raw={"image_tag": image_tag, "reel_json": script_json(reel)},
    )


def render_expired(retention_hours: float) -> str:
    """The page for a share link whose reel is gone (links spec 6.2)."""
    template = (STATIC_DIR / "expired.html").read_text(encoding="utf-8")
    return fill(template, {"hours": retention_text(retention_hours)})
```

- [ ] **Step 4: Create `reels_api/static/watch.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0a0b0d">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="robots" content="noindex">
<title>{{title}}</title>
<meta property="og:title" content="{{title}}">
<meta property="og:description" content="{{description}}">
{{image_tag}}
<meta property="og:url" content="{{url}}">
<meta property="og:type" content="video.other">
<meta property="og:site_name" content="reels">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700;12..96,800&amp;display=swap">
<link rel="stylesheet" href="/static/style.css">
<script type="application/json" id="reel-data">{{reel_json}}</script>
<script type="module" src="/static/watch.js"></script>
</head>
<body>
<!-- The player block from app.html without close, prev/next, Share, Copy link and WhatsApp (links spec 6.1).
     A change to the player markup in app.html must be mirrored here. -->
<div id="player" class="player" hidden>
  <div class="player-backdrop"></div>
  <div class="player-row">
    <div class="player-inner">
      <div class="player-stage">
        <div class="player-frame">
          <video playsinline loop preload="auto"></video>
          <div class="idle-bar">
            <div class="idle-track"><div class="idle-fill"></div></div>
            <p class="idle-hint">tap for options</p>
          </div>
          <div class="chrome">
            <div class="chrome-top">
              <span class="source"><span data-icon="clock"></span><span class="js-source"></span></span>
            </div>
            <div class="chrome-bottom">
              <p class="caption js-caption"></p>
              <div class="controls">
                <span class="time js-elapsed">0:00</span>
                <input class="scrubber" type="range" min="0" max="1" step="0.1" value="0" aria-label="seek">
                <span class="time total js-duration">0:00</span>
                <button class="volume" type="button" data-action="volume" aria-label="mute"></button>
              </div>
              <div class="actions">
                <button class="btn save" type="button" data-action="save"><span data-icon="download"></span><span class="spinner" aria-hidden="true"></span>Save</button>
              </div>
              <a class="login-hint" href="/?reel={{id}}">have the passcode? <u>log in</u></a>
            </div>
          </div>
        </div>
        <div class="controls desk-controls">
          <span class="time js-elapsed">0:00</span>
          <input class="scrubber" type="range" min="0" max="1" step="0.1" value="0" aria-label="seek">
          <span class="time total js-duration">0:00</span>
          <button class="volume" type="button" data-action="volume" aria-label="mute"></button>
        </div>
      </div>
      <aside class="player-panel">
        <span class="source"><span data-icon="clock"></span><span class="js-source"></span></span>
        <p class="caption js-caption"></p>
        <div class="panel-actions">
          <div class="panel-row">
            <button class="btn save" type="button" data-action="save"><span data-icon="download"></span><span class="spinner" aria-hidden="true"></span>Download</button>
          </div>
        </div>
        <a class="login-hint" href="/?reel={{id}}">have the passcode? <u>log in</u></a>
      </aside>
    </div>
  </div>
</div>

<div id="toast" class="toast" role="status" aria-live="polite"></div>
</body>
</html>
```

- [ ] **Step 5: Create `reels_api/static/expired.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0a0b0d">
<meta name="referrer" content="strict-origin-when-cross-origin">
<meta name="robots" content="noindex">
<title>reels</title>
<meta property="og:title" content="reels">
<meta property="og:description" content="this reel has expired">
<meta property="og:site_name" content="reels">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700;12..96,800&amp;display=swap">
<link rel="stylesheet" href="/static/style.css">
</head>
<body class="login">
<main class="login-box">
  <h1 class="wordmark">reels</h1>
  <p class="login-lead">this reel has expired</p>
  <p class="expired-note">reels only stay up for {{hours}}</p>
  <a class="login-hint" href="/">have the passcode? <u>log in</u></a>
</main>
</body>
</html>
```

- [ ] **Step 6: Append the styles to `reels_api/static/style.css`**

```css

/* ---- view-only and expired pages (links spec 6) ---- */

.login-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 36px;
  margin-top: 8px;
  font: 500 12.5px var(--font);
  color: var(--ink-50);
  text-decoration: none;
}
.login-hint u { text-underline-offset: 2px; }
.login-box .login-hint { justify-content: flex-start; margin-top: 0; }
.expired-note { font-size: 13px; color: var(--ink-50); }

@media (min-width: 700px) {
  .player-panel .login-hint { justify-content: flex-start; margin-top: 0; }
}
```

- [ ] **Step 7: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: all pass (196 passed, 1 deselected).

- [ ] **Step 8: Commit**

```bash
git add reels_api/pages.py reels_api/static/watch.html reels_api/static/expired.html reels_api/static/style.css tests/test_pages.py
git commit -m "feat: render the view-only and expired pages with link preview tags" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `GET /` picks the board, the view-only page, the expired page or login

**Files:**
- Modify: `reels_api/web.py` (imports, `STATIC_DIR`, `index`, new `_login_page` and `_base_url`)
- Modify: `reels_api/static/login.html`, `reels_api/static/app.html` (head)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `pages.render_watch`, `pages.render_expired`, `pages.STATIC_DIR` (Task 5); `share_key_matches` (Task 3); `Job.share_key` (Task 2).
- Produces: `GET /?reel=<id>&k=<key>` behaviour of links spec 5.1.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web.py`, replace the imports with:

```python
import pytest
from fastapi.testclient import TestClient

from reels_api.auth import SESSION_COOKIE, session_cookie_value
from reels_api.main import create_app
from reels_api.models import Job, JobStatus, Source
from reels_api.web import AttemptLimiter
from tests.conftest import make_settings
from tests.test_routes import FakePipeline, _done_reel
```

(`_done_reel` was added to `tests/test_routes.py` in Task 3.) Add at the end of the file:

```python
# ---- GET / with a share link (links spec 5.1)

def _is_login(r):
    return r.status_code == 200 and 'id="passcode"' in r.text and r.headers["cache-control"] == "no-store"


def _is_expired(r):
    return r.status_code == 200 and "this reel has expired" in r.text and r.headers["cache-control"] == "no-store"


def test_index_with_cookie_ignores_share_key(web_app):
    with https_client(web_app()) as client:
        reel = _done_reel(client)
        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.get("/", params={"reel": reel["id"], "k": reel["share_key"]})
        assert 'id="grid"' in r.text
        assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "params",
    [{"reel": "abc"}, {"k": "abc"}, {"reel": "abc", "k": ""}, {"reel": "", "k": "abc"}],
)
def test_index_without_reel_and_key_is_login(web_app, params):
    with TestClient(web_app()) as client:
        assert _is_login(client.get("/", params=params))


def test_index_unknown_reel_is_expired(web_app):
    with TestClient(web_app(retention_hours=12)) as client:
        r = client.get("/", params={"reel": "nope", "k": "whatever"})
        assert _is_expired(r)
        assert r.headers["content-type"].startswith("text/html")
        assert "reels only stay up for 12 hours" in r.text
    with TestClient(web_app(retention_hours=1)) as client:
        assert "reels only stay up for 1 hour<" in client.get("/", params={"reel": "nope", "k": "x"}).text


def test_index_wrong_key_is_login(web_app):
    with TestClient(web_app()) as client:
        reel = _done_reel(client)
        assert _is_login(client.get("/", params={"reel": reel["id"], "k": "wrong-key-000000"}))


def test_index_failed_job_or_missing_file_is_expired(web_app):
    with TestClient(web_app()) as client:
        failed = Job(id="failed1", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
        client.app.state.store._jobs[failed.id] = failed
        assert _is_expired(client.get("/", params={"reel": failed.id, "k": failed.share_key}))

        reel = _done_reel(client)
        client.app.state.store._jobs[reel["id"]].result.file_path.unlink()
        assert _is_expired(client.get("/", params={"reel": reel["id"], "k": reel["share_key"]}))


def test_index_right_key_is_view_only_page(web_app):
    with TestClient(web_app()) as client:
        reel = _done_reel(client)
        key = reel["share_key"]
        r = client.get("/", params={"reel": reel["id"], "k": key})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["cache-control"] == "no-store"
        assert '<script type="module" src="/static/watch.js"></script>' in r.text
        assert f'"file_url": "/files/{reel["id"]}.mp4?k={key}"' in r.text
        assert f'content="http://testserver/?reel={reel["id"]}&amp;k={key}"' in r.text
        assert f'content="http://testserver/files/{reel["id"]}.jpg?k={key}"' in r.text
        # the page's own file links work without a cookie
        assert client.get(f"/files/{reel['id']}.mp4", params={"k": key}).status_code == 200


def test_view_only_page_uses_public_base_url(web_app):
    with TestClient(web_app(public_base_url="https://reels.example.com/")) as client:
        reel = _done_reel(client)
        r = client.get("/", params={"reel": reel["id"], "k": reel["share_key"]})
        assert f'content="https://reels.example.com/files/{reel["id"]}.jpg?k={reel["share_key"]}"' in r.text


def test_login_and_app_pages_have_preview_tags(web_app):
    with https_client(web_app()) as client:
        login = client.get("/").text
        client.post("/web/login", json={"passcode": PASSCODE})
        board = client.get("/").text
    for page in (login, board):
        assert '<meta name="robots" content="noindex">' in page
        assert '<meta property="og:title" content="reels">' in page
        assert '<meta property="og:description" content="reels your friends pasted. no names, ever.">' in page
        assert '<meta property="og:type" content="website">' in page
        assert '<meta property="og:site_name" content="reels">' in page
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py -q -k "index or view_only or preview_tags"`

Expected: the expired, view-only, public-base-url, failed-or-missing and preview-tag tests fail (the server returns the login page and the pages have no tags). The cookie, login and wrong-key tests pass already.

- [ ] **Step 3: Implement the routing**

In `reels_api/web.py`:

Remove `from pathlib import Path` and the line `STATIC_DIR = Path(__file__).parent / "static"`.

Change the imports to include:

```python
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
```

```python
from reels_api import pages
from reels_api.auth import SESSION_COOKIE, session_cookie_value, session_is_valid, share_key_matches
from reels_api.models import JobStatus
from reels_api.pages import STATIC_DIR
```

Replace the `index` route with:

```python
def _login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "login.html", media_type="text/html", headers=NO_STORE)


def _base_url(request: Request) -> str:
    """Scheme and host for absolute links in preview tags, without a trailing slash."""
    configured = request.app.state.settings.public_base_url
    return (configured or str(request.base_url)).rstrip("/")


@router.get("/")
async def index(request: Request, reel: str | None = None, k: str | None = None) -> Response:
    """The board, a shared reel, an expired reel or the login page, checked in that order (links spec 5.1)."""
    settings = request.app.state.settings
    if session_is_valid(settings, request.cookies.get(SESSION_COOKIE)):
        return FileResponse(STATIC_DIR / "app.html", media_type="text/html", headers=NO_STORE)
    if not reel or not k:
        return _login_page()
    job = await request.app.state.store.get(reel)
    if job is None:
        return HTMLResponse(pages.render_expired(settings.retention_hours), headers=NO_STORE)
    if not share_key_matches(job, k):
        return _login_page()  # a guessed key gets the same answer as no key
    if job.status != JobStatus.DONE or job.result is None or not job.result.file_path.is_file():
        return HTMLResponse(pages.render_expired(settings.retention_hours), headers=NO_STORE)
    return HTMLResponse(pages.render_watch(job, _base_url(request)), headers=NO_STORE)
```

- [ ] **Step 4: Add the static preview tags**

In both `reels_api/static/login.html` and `reels_api/static/app.html`, directly after the `<title>reels</title>` line, add:

```html
<meta name="robots" content="noindex">
<meta property="og:title" content="reels">
<meta property="og:description" content="reels your friends pasted. no names, ever.">
<meta property="og:type" content="website">
<meta property="og:site_name" content="reels">
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: all pass (207 passed, 1 deselected).

- [ ] **Step 6: Commit**

```bash
git add reels_api/web.py reels_api/static/login.html reels_api/static/app.html tests/test_web.py
git commit -m "feat: share links open a view-only page without the cookie" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Dev server prints the invite and share links

**Files:**
- Modify: `scripts/dev_board.py` (docstring, `INVITE_TOKEN`, `link_lines`, `main`)
- Test: `tests/test_dev_board.py`

**Interfaces:**
- Consumes: `Settings.invite_token` (Task 4), `Job.share_key` (Task 2).
- Produces: `dev_board.INVITE_TOKEN = "dev-invite-token-0000"`; `dev_board.link_lines(port: int, seeds: list[Job]) -> list[str]`.

- [ ] **Step 1: Write the failing tests**

Add at the end of `tests/test_dev_board.py`:

```python
def test_seed_jobs_have_share_keys(tmp_path):
    jobs = dev_board.seed_jobs(make_settings(tmp_path), fake_clips(tmp_path))
    assert all(len(j.share_key) == 16 for j in jobs)
    assert len({j.share_key for j in jobs}) == len(jobs)


def test_link_lines(tmp_path):
    jobs = dev_board.seed_jobs(make_settings(tmp_path), fake_clips(tmp_path))
    assert dev_board.link_lines(8000, jobs) == [
        "invite link: http://localhost:8000/join/dev-invite-token-0000",
        f"share link:  http://localhost:8000/?reel=seed00&k={jobs[0].share_key}",
    ]
    assert dev_board.link_lines(9000, []) == ["invite link: http://localhost:9000/join/dev-invite-token-0000"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_dev_board.py -q`

Expected: `test_link_lines` fails with `AttributeError: module 'dev_board' has no attribute 'link_lines'`; `test_seed_jobs_have_share_keys` passes (keys come from Task 2).

- [ ] **Step 3: Implement**

In `scripts/dev_board.py`, replace the last paragraph of the module docstring (starting "Open http://localhost:8000/ in Chrome") with:

```
Open http://localhost:8000/ in Chrome and log in with "dev". Pasted links
wait 3 seconds, then fail if the URL contains "private", "login", "blocked"
or "slow", and otherwise succeed with a copy of a seed clip.

On start it prints the invite link and the newest seeded reel's share link.
Open them in a private window to see what someone without the cookie sees.
```

Below `PASSCODE = "dev"`, add:

```python
INVITE_TOKEN = "dev-invite-token-0000"
```

Directly above `async def _add_all`, add:

```python
def link_lines(port: int, seeds: list[Job]) -> list[str]:
    """The invite link and, when there are seeded reels, the newest one's share link (links spec 9)."""
    base = f"http://localhost:{port}"
    lines = [f"invite link: {base}/join/{INVITE_TOKEN}"]
    if seeds:
        newest = seeds[0]
        lines.append(f"share link:  {base}/?reel={newest.id}&k={newest.share_key}")
    return lines


```

In `main`, replace the `Settings(...)` call with:

```python
    settings = Settings(
        _env_file=None,
        api_key="dev",
        web_passcode=PASSCODE,
        invite_token=INVITE_TOKEN,
        storage_dir=root / "files",
        temp_dir=root / "tmp",
        workers=1,
    )
```

and replace from `app = create_app(...)` down to (not including) `try:` with:

```python
    app = create_app(settings=settings, pipeline=DevPipeline(settings, clips))
    seeds: list[Job] = []
    if not args.empty:
        # Before the app starts: startup deletes stored files that belong to no known job.
        seeds = seed_jobs(settings, clips)
        asyncio.run(_add_all(app.state.store, seeds))
    print(f"open http://localhost:{args.port}/ and log in with passcode {PASSCODE!r}", flush=True)
    for line in link_lines(args.port, seeds):
        print(line, flush=True)
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: all pass (209 passed, 1 deselected).

- [ ] **Step 5: Commit**

```bash
git add scripts/dev_board.py tests/test_dev_board.py
git commit -m "feat: dev server prints an invite link and a share link" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

The dev server for Tasks 8 to 10 (PowerShell, from the repo root; ffmpeg runs inside the image):

```powershell
docker build -t reels-dev .
docker run --rm -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app `
  -v "${PWD}/reels_api:/app/reels_api:ro" -v "${PWD}/scripts:/app/scripts:ro" `
  reels-dev python scripts/dev_board.py --host 0.0.0.0
```

It prints the passcode, the invite link and a share link. Python changes need a restart of the container; static file edits show up on reload.

---

### Task 8: Standalone player on the view-only page

**Files:**
- Create: `reels_api/static/watch.js`
- Modify: `reels_api/static/player.js`
- Test: `tests/test_web.py` (`APP_MODULES`)

**Interfaces:**
- Consumes: `watch.html` markup and `#reel-data` (Task 5); `createPlayer`, `hydrateIcons`, `showToast` (existing).
- Produces: `createPlayer({ root, onGone, standalone = false })` in `player.js`. In standalone mode `onGone(id)` is called on a video error without closing the player.

- [ ] **Step 1: Write the failing test**

In `tests/test_web.py`, change `APP_MODULES` to:

```python
APP_MODULES = ["app.js", "api.js", "format.js", "icons.js", "board.js", "paste.js", "toast.js", "player.js", "watch.js"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py::test_app_modules_are_served -q`

Expected: FAIL, `AssertionError: watch.js` (404).

- [ ] **Step 3: Create `reels_api/static/watch.js`**

```js
import { hydrateIcons } from "./icons.js";
import { createPlayer } from "./player.js";
import { showToast } from "./toast.js";

// The view-only page: one reel from a share link, no pile (links spec 6.1).
const reel = JSON.parse(document.getElementById("reel-data").textContent);

hydrateIcons(document);

// The video failed. If the reel is gone, reload so the server shows the expired page.
// Otherwise stay: reloading a clip the browser cannot play would loop forever.
async function onGone() {
  try {
    const response = await fetch(reel.file_url, { headers: { Range: "bytes=0-0" } });
    if (response.status === 401 || response.status === 404) {
      location.reload();
      return;
    }
  } catch (_) {
    // network error: say so below
  }
  showToast("couldn't play that one", { error: true });
}

const player = createPlayer({ root: document.getElementById("player"), onGone, standalone: true });
player.open([reel], reel.id, { gesture: false, push: false });
```

- [ ] **Step 4: Add standalone mode to `reels_api/static/player.js`**

Make these edits.

a) Change the signature and the desktop focus target. Replace:

```js
export function createPlayer({ root, onGone }) {
```

with:

```js
// standalone: the view-only page's single reel. No history, no closing, no swiping (links spec 8).
export function createPlayer({ root, onGone, standalone = false }) {
```

and replace:

```js
  const desktopClose = root.querySelector(".player-close-desktop");
```

with:

```js
  const desktopClose = root.querySelector(".player-close-desktop");
  // Where focus goes when the overlay opens on desktop; the view-only page has no close button.
  const desktopFocus = desktopClose || saveButtons[saveButtons.length - 1];
```

b) Tolerate missing nav buttons. Replace:

```js
  function renderNav() {
    prevButton.disabled = index <= 0;
    nextButton.disabled = index >= reels.length - 1;
  }
```

with:

```js
  function renderNav() {
    if (prevButton) prevButton.disabled = index <= 0;
    if (nextButton) nextButton.disabled = index >= reels.length - 1;
  }
```

c) No history in standalone. In `open`, replace:

```js
    if (push) history.pushState({ reel: id }, "", reelPath(id));
    else history.replaceState({ reel: id }, "", reelPath(id));
    pushed = push;
    cancelAnimationFrame(frameRequest);
    tick();
    if (desktopQuery.matches) desktopClose.focus();
```

with:

```js
    if (!standalone) {
      if (push) history.pushState({ reel: id }, "", reelPath(id));
      else history.replaceState({ reel: id }, "", reelPath(id));
      pushed = push;
    }
    cancelAnimationFrame(frameRequest);
    tick();
    if (desktopQuery.matches && desktopFocus) desktopFocus.focus();
```

In `move`, replace:

```js
    history.replaceState({ reel: current().id }, "", reelPath(current().id));
```

with:

```js
    if (!standalone) history.replaceState({ reel: current().id }, "", reelPath(current().id));
```

d) No dragging in standalone. In the `pointermove` listener, replace:

```js
    if (!drag || event.pointerId !== drag.id) return;
    const dy = event.clientY - drag.y;
```

with:

```js
    if (!drag || event.pointerId !== drag.id || standalone) return;
    const dy = event.clientY - drag.y;
```

In the `pointerup` listener, replace:

```js
      setChrome(!root.classList.contains("chrome-on"));
      return;
    }
    const step = dy < 0 ? 1 : -1; // finger up: next reel
```

with:

```js
      setChrome(!root.classList.contains("chrome-on"));
      return;
    }
    if (standalone) return; // the frame never moved
    const step = dy < 0 ? 1 : -1; // finger up: next reel
```

e) Video errors. Replace:

```js
  video.addEventListener("error", () => {
    if (!isOpen()) return;
    const gone = current();
    close();
```

with:

```js
  video.addEventListener("error", () => {
    if (!isOpen()) return;
    const gone = current();
    if (standalone) {
      onGone(gone.id); // the page decides: expired page or a toast
      return;
    }
    close();
```

f) Escape does nothing in standalone. In the `keydown` listener, replace:

```js
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
```

with:

```js
    if (event.key === "Escape") {
      if (standalone) return;
      event.preventDefault();
      close();
      return;
    }
```

- [ ] **Step 5: Syntax check and run the full suite**

Run: `node --check reels_api/static/player.js && node --check reels_api/static/watch.js && .venv/Scripts/python.exe -m pytest -q`

Expected: no output from `node`; all pass (209 passed, 1 deselected).

- [ ] **Step 6: Manual check in Chrome**

Start the dev server (command after Task 7). Open the printed **share link** in a new incognito window.

At 390×844 (device mode, touch):
- the reel plays full screen, muted, with the idle bar reading "tap for options"
- tapping shows the source line, caption, controls, **Save** and "have the passcode? log in"; tapping again hides them
- the volume button unmutes
- dragging up or down does not move the video
- the scrubber seeks
- **Save** shows "saved to your downloads"
- the address still ends in `&k=…`

At 1280×800:
- the overlay shows the video, desk controls and the side panel with **Download** and the login hint, with no close or arrow buttons
- Esc and ← → do nothing
- clicking the video pauses and plays

Login hint: click it, log in with `dev`, and check that the board opens with that reel playing.

Video error: stop the container while the view-only page is open, then scrub the video. Expect the toast "couldn't play that one" and no reload.

- [ ] **Step 7: Commit**

```bash
git add reels_api/static/watch.js reels_api/static/player.js tests/test_web.py
git commit -m "feat: standalone player on the view-only page" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: The board hands out share links

**Files:**
- Modify: `reels_api/static/player.js` (`reelPath`, `reelLink`, their call sites)

**Interfaces:**
- Consumes: `share_key` in the job JSON (Task 2); `player.js` after Task 8.
- Produces: `reelPath(reel)` and `reelLink(reel)` take a reel object. Share, Copy link, the WhatsApp button and the address bar use `/?reel=<id>&k=<share_key>`.

- [ ] **Step 1: Change the link helpers**

In `reels_api/static/player.js`, replace:

```js
function reelPath(id) {
  return `/?reel=${encodeURIComponent(id)}`;
}

// The link that Share and Copy link hand out (spec 4).
function reelLink(id) {
  return location.origin + reelPath(id);
}
```

with:

```js
// The share link: opens the reel for anyone, the board only with the cookie (links spec 4.3).
function reelPath(reel) {
  const path = `/?reel=${encodeURIComponent(reel.id)}`;
  return reel.share_key ? `${path}&k=${encodeURIComponent(reel.share_key)}` : path;
}

// The link that Share, Copy link and the WhatsApp button hand out.
function reelLink(reel) {
  return location.origin + reelPath(reel);
}
```

- [ ] **Step 2: Update every call site**

In `open`, replace:

```js
      if (push) history.pushState({ reel: id }, "", reelPath(id));
      else history.replaceState({ reel: id }, "", reelPath(id));
```

with:

```js
      if (push) history.pushState({ reel: id }, "", reelPath(current()));
      else history.replaceState({ reel: id }, "", reelPath(current()));
```

In `move`, replace:

```js
    if (!standalone) history.replaceState({ reel: current().id }, "", reelPath(current().id));
```

with:

```js
    if (!standalone) history.replaceState({ reel: current().id }, "", reelPath(current()));
```

In `share`, replace:

```js
    const url = reelLink(current().id);
```

with:

```js
    const url = reelLink(current());
```

In `copyLink`, replace:

```js
      await navigator.clipboard.writeText(reelLink(current().id));
```

with:

```js
      await navigator.clipboard.writeText(reelLink(current()));
```

In the `actions` object, replace:

```js
    whatsapp: () => openWhatsApp(reelLink(current().id)),
```

with:

```js
    whatsapp: () => openWhatsApp(reelLink(current())),
```

- [ ] **Step 3: Check nothing still passes an id**

Run: `grep -n "reelPath(\|reelLink(" reels_api/static/player.js`

Expected: 9 lines. That's the two definitions and seven calls: one inside `reelLink`, two in `open`, and one each in `move`, `share`, `copyLink` and the `whatsapp` action. Every call passes `current()` or `reel`, and none passes `id` or `.id`.

- [ ] **Step 4: Syntax check and run the full suite**

Run: `node --check reels_api/static/player.js && .venv/Scripts/python.exe -m pytest -q`

Expected: all pass (209 passed, 1 deselected).

- [ ] **Step 5: Manual check in Chrome**

In a normal window, log in with `dev` at 390×844:
- Open a reel. The address bar reads `/?reel=seedNN&k=…`.
- Swipe to the next reel. The address changes to that reel's id and key.
- Stub `navigator.share` (Global Constraints), tap **Share**. The console logs a URL with `&k=`.
- Tap **Copy link**. "link copied" appears. Paste it into an incognito window, and the view-only page for that reel opens.
- Close the player with ✕, then press browser Back and Forward. Back returns to the board, and Forward reopens the reel.

At 1280×800:
- **Share to WhatsApp** opens `wa.me` with the encoded link containing `k`.
- **Copy link** copies the link with `k`.

- [ ] **Step 6: Commit**

```bash
git add reels_api/static/player.js
git commit -m "feat: board Share, Copy link and address bar use the share link" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: README, CLAUDE.md and the full manual pass

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: documentation only.

- [ ] **Step 1: Update `README.md`**

In "The board (phone web page)", on the line that reads

```
pasted in the last `RETENTION_HOURS`, up to `MAX_VIDEOS` (default 10; past
```

change `default 10` to `default 100`.

Replace the bullet:

```markdown
- **Share** and **Copy link** hand out `https://<site>/?reel=<id>`, which
  opens that reel (after the passcode, for someone new) until it ages out.
```

with:

```markdown
- **Share** and **Copy link** hand out `https://<site>/?reel=<id>&k=<key>`.
  Friends with the login cookie land on the board with that reel playing.
  Anyone else gets a view-only page with just that reel: they can watch and
  save it, never see the pile, and get a "have the passcode? log in" link.
  In WhatsApp the link shows the reel's thumbnail and caption. When the
  reel has aged out, the link shows "this reel has expired".
```

Replace the paragraph:

```markdown
The login cookie lasts a year. Changing `API_KEY` or `WEB_PASSCODE` logs
everyone out. Ten wrong passcodes from one IP block it for up to 15 minutes.
```

with:

```markdown
**Getting in.** Set `INVITE_TOKEN` and pin `https://<site>/join/<token>` in
the group: tapping it logs a phone in with nothing to type. The passcode
still works as the fallback. The login cookie lasts a year. Changing
`INVITE_TOKEN` stops the old link but keeps everyone logged in; changing
`API_KEY` or `WEB_PASSCODE` logs everyone out. Ten wrong passcodes or invite
tokens from one IP block it for up to 15 minutes.
```

In "JSON API", in the `GET /jobs/{id}` row, replace

```
`finished_at` and `expires_at`.
```

with

```
`finished_at`, `expires_at` and `share_key`.
```

Directly below the table, add:

```markdown
The two `/files/` routes also open with `?k=<share_key>` instead of the key
or cookie, for that reel only.
```

In "Configuration", replace the `MAX_VIDEOS` row with:

```markdown
| `MAX_VIDEOS` | `100` | Most videos kept at once; the oldest goes first. |
```

and below the `WEB_PASSCODE` row add:

```markdown
| `INVITE_TOKEN` | empty | Secret in the invite link `/join/<token>`, at least 16 characters. Empty disables it. |
```

In "Trying the board without downloading anything", after the paragraph ending `and otherwise succeed with a copy of a test clip.`, add a new paragraph:

```markdown
On start it also prints an invite link and the newest reel's share link.
Open them in a private window to see what someone without the cookie sees.
```

In "A new VM", replace:

```markdown
  `API_KEY` (for example `openssl rand -hex 24`), `WEB_PASSCODE` and
  `SITE_ADDRESS`.
```

with:

```markdown
  `API_KEY` (for example `openssl rand -hex 24`), `WEB_PASSCODE`,
  `INVITE_TOKEN` (`openssl rand -hex 16`) and `SITE_ADDRESS`.
```

- [ ] **Step 2: Update `CLAUDE.md`**

Replace the whole paragraph that starts with `**Auth**` with these two paragraphs:

```markdown
**Auth** (`auth.py`). `require_access` accepts either `X-API-Key` or the `reels_session` cookie (`has_access`). The cookie value is one shared HMAC of `API_KEY` + `WEB_PASSCODE`, so there are no per-user sessions and changing either secret logs everyone out. Two ways to get the cookie: the passcode form (`POST /web/login`) and the invite link `GET /join/<INVITE_TOKEN>`; both share one per-IP attempt limiter. `web.install(app)` (login, `/`, `/join`, manifest, `/sw.js`, `/static`) is only called when `WEB_PASSCODE` is set; otherwise those routes 404. Every job also has a random `share_key` (in the job JSON when done): `?k=<share_key>` opens that reel's `/files/` and its view-only page, and nothing else. It must never open `/jobs` or the board.

**`GET /` decides the page** (`web.index`, links spec 5.1): valid cookie → `app.html`; no `reel`+`k` → login; unknown reel → expired page; wrong key → login (deliberately the same as no key); reel not done or file gone → expired page; otherwise the view-only page. The view-only and expired pages are rendered by `pages.py` from `static/watch.html` and `static/expired.html`: `{{name}}` placeholders are HTML-escaped, `raw=` values are inserted as is, and the reel JSON goes through `script_json`. Open Graph tags are filled in on the server because WhatsApp's preview fetcher runs no JavaScript and has no cookie.
```

In the **Frontend** paragraph, replace:

```markdown
`login.html`/`login.js` are a separate non-module page. `GET /` serves `login.html` or `app.html` depending on the cookie.
```

with:

```markdown
`login.html`/`login.js` are a separate non-module page. `watch.html` + `watch.js` is the view-only page: it runs `player.js` with `standalone: true` (no history, no close, no swiping). **The player markup exists in both `app.html` and `watch.html`; mirror any change.** Share links are built by `reelPath(reel)`/`reelLink(reel)` in `player.js` and include `k` when the reel has a `share_key`.
```

In **Commands**, replace:

```markdown
- To try the page by hand, `scripts/dev_board.py` runs the real app with passcode `dev`, 12 seeded reels and a fake pipeline.
```

with:

```markdown
- To try the page by hand, `scripts/dev_board.py` runs the real app with passcode `dev`, 12 seeded reels and a fake pipeline, and prints an invite link and a share link (open those in a private window).
```

- [ ] **Step 3: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: all pass (209 passed, 1 deselected).

- [ ] **Step 4: Full manual pass**

Restart the dev server so it runs the final code. Walk links spec section 11.2 at 390×844 and 1280×800. Each item not already covered by Tasks 8 and 9:
- **Invite link:** the printed link in a new incognito window opens the board, and the address bar shows `/`. `http://localhost:8000/join/wrong-token-000000` opens the login page.
- **Expired page:** `http://localhost:8000/?reel=nope&k=x` shows it, reading "reels only stay up for 12 hours", and the login link goes to `/`.
- **Preview tags:** view the source of the share link page. The `og:title`, `og:description`, `og:image`, `og:url`, `og:type` and `og:site_name` tags are filled in, and the `og:image` URL opens the thumbnail in the incognito window.
- **Regression pass on the board:** paste success and an error hint, swiping on the phone, the desktop overlay with ← → and Esc, and the empty board (`--empty`).

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: invite link, share links and previews in README and CLAUDE.md" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## After the plan

Deploying is the owner's step (links spec section 12). None of it runs from this plan:

1. On the VM, in `~/reels/.env`, set `INVITE_TOKEN=<openssl rand -hex 16>`, `MAX_VIDEOS=100` and `RETENTION_HOURS=12`.
2. From the PC, run `.\scripts\deploy.ps1`. The restart empties the pile.
3. Pin `https://<site>/join/<token>` in the group.
4. Real-device checks from links spec 11.3:
   - A shared reel in WhatsApp shows its thumbnail and caption.
   - A phone that has never logged in opens it on the view-only page.
   - Save on iPhone puts it in Photos.
   - The invite link logs a new phone in.
