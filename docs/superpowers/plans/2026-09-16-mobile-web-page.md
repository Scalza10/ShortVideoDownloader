# Mobile Web Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A passcode-protected mobile web page, served by the existing FastAPI app, where friends paste a TikTok or Instagram link, watch the result, share the MP4 to WhatsApp, and see a shared "Recent" feed; plus Caddy HTTPS and an Azure free-tier deploy recipe.

**Architecture:** The API grows a cookie-based access path (`require_access`), a `GET /jobs` feed, `extract_url` for share text, and a non-fatal thumbnail stage in the pipeline. A new `reels_api/web.py` serves the login route, an in-memory attempt limiter, the page shell, the manifest, the service worker and static files, and is only installed when `WEB_PASSCODE` is set. The front end is plain HTML, CSS and JS with no build step. Caddy terminates TLS in docker compose.

**Tech Stack:** Python 3.12, FastAPI 0.141 / Starlette 1.6, uvicorn 0.53, pytest + anyio + httpx (existing), plain HTML/CSS/JS, Caddy 2, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-16-mobile-web-page-design.md` (read it first; this plan argues from it). The API it extends is `docs/superpowers/specs/2026-09-16-reels-download-api-design.md`.

## Global Constraints

- No new Python dependencies. `requirements.txt` stays as is.
- Every automated test runs with no network and no ffmpeg. Use the existing fakes in `tests/`.
- Run tests from the repo root with the venv active: `python -m pytest -q`. On Windows without activation use `.venv\Scripts\python -m pytest -q`.
- Cookie name is `reels_session`; value is lowercase hex of `HMAC-SHA256(key=API_KEY, msg="reels-web-session:" + WEB_PASSCODE)`; attributes `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, `Max-Age=31536000`.
- All secret comparisons use `secrets.compare_digest`.
- `WEB_PASSCODE` unset **or empty string** disables the web page. Everywhere the code checks it, use truthiness (`if settings.web_passcode:`).
- 401 body for protected routes stays exactly `{"error": "unauthorized", "message": "Missing or invalid API key."}`.
- Tests that need the cookie round-trip through the client jar must use `TestClient(app, base_url="https://testserver")` (the cookie is `Secure`).
- All user-facing text is English. Copy strings exactly as given in the spec and this plan.
- Commit after every task with the message shown. End each commit message with the line `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## File map

| file | change | responsibility |
|------|--------|----------------|
| `reels_api/settings.py` | modify | `web_passcode` setting |
| `reels_api/urls.py` | modify | `extract_url` |
| `reels_api/jobs.py` | modify | `submit` extracts URL; `JobStore.list_recent`; sweeper deletes `.jpg` |
| `reels_api/auth.py` | modify | `SESSION_COOKIE`, `session_cookie_value`, `session_is_valid`, `require_access` (replaces `require_api_key`) |
| `reels_api/models.py` | modify | `JobResult.thumbnail_path`, `thumbnail_url` in `job_to_dict` |
| `reels_api/media.py` | modify | `build_thumbnail_command`, `thumbnail_seek`, `make_thumbnail` |
| `reels_api/pipeline.py` | modify | `thumbnailer` stage, non-fatal |
| `reels_api/routes.py` | modify | `GET /jobs`, `GET /files/{id}.jpg`, uses `require_access` |
| `reels_api/web.py` | create | `AttemptLimiter`, login, `GET /`, manifest, sw.js, `NoCacheStaticFiles`, `install(app)` |
| `reels_api/main.py` | modify | calls `web.install(app)` when `web_passcode` is set |
| `reels_api/static/*` | create | `login.html`, `app.html`, `login.js`, `app.js`, `style.css`, `manifest.webmanifest`, `sw.js`, `icon-192.png`, `icon-512.png` |
| `scripts/make_icons.py` | create | generates the two PNG icons with the stdlib |
| `Caddyfile`, `docker-compose.yml`, `Dockerfile`, `.env.example`, `README.md` | create / modify | deployment |
| `tests/test_settings.py`, `test_urls.py`, `test_jobs.py`, `test_routes.py`, `test_models.py`, `test_media.py`, `test_pipeline.py` | modify | per task |
| `tests/test_web.py` | create | limiter, login, page choice, disabled mode, cache headers |

---

### Task 1: `web_passcode` setting and `extract_url`

**Files:**
- Modify: `reels_api/settings.py`
- Modify: `reels_api/urls.py`
- Modify: `reels_api/jobs.py:69-76` (`JobManager.submit`)
- Test: `tests/test_settings.py`, `tests/test_urls.py`, `tests/test_jobs.py`

**Interfaces:**
- Produces: `Settings.web_passcode: str | None = None`.
- Produces: `urls.extract_url(text: str) -> str`.
- `JobManager.submit(url: str)` now accepts share text and stores the extracted URL on `Job.url`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_settings.py`:

```python
def test_web_passcode_default_and_override(monkeypatch):
    monkeypatch.setenv("API_KEY", "abc")
    assert Settings(_env_file=None).web_passcode is None
    monkeypatch.setenv("WEB_PASSCODE", "letmein")
    assert Settings(_env_file=None).web_passcode == "letmein"
```

Append to `tests/test_urls.py` (add `extract_url` to the existing import line `from reels_api.urls import detect_source`):

```python
@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://vm.tiktok.com/ZMabc123/", "https://vm.tiktok.com/ZMabc123/"),
        ("  https://vm.tiktok.com/ZMabc123/  ", "https://vm.tiktok.com/ZMabc123/"),
        ("Check this out! https://vm.tiktok.com/ZMabc123/ #fyp", "https://vm.tiktok.com/ZMabc123/"),
        (
            "Check out user's video! https://www.tiktok.com/t/ZTRabc/ ",
            "https://www.tiktok.com/t/ZTRabc/",
        ),
        (
            "https://www.instagram.com/reel/C1abc/?igsh=xyz",
            "https://www.instagram.com/reel/C1abc/?igsh=xyz",
        ),
        ("look: https://www.instagram.com/reel/C1abc/.", "https://www.instagram.com/reel/C1abc/"),
        ("(https://vm.tiktok.com/ZMabc123/)", "https://vm.tiktok.com/ZMabc123/"),
        ('"https://vm.tiktok.com/ZMabc123/",', "https://vm.tiktok.com/ZMabc123/"),
        ("no link here", "no link here"),
        ("   ", ""),
    ],
)
def test_extract_url(text, expected):
    assert extract_url(text) == expected
```

Append to `tests/test_jobs.py`:

```python
@pytest.mark.anyio
async def test_submit_extracts_url_from_share_text(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    job = await manager.submit("Check this out! https://vm.tiktok.com/ZMabc123/ #fyp")
    assert job.url == "https://vm.tiktok.com/ZMabc123/"
    assert job.source == Source.TIKTOK


@pytest.mark.anyio
async def test_submit_rejects_share_text_without_url(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    with pytest.raises(JobError) as exc:
        await manager.submit("just some words")
    assert exc.value.code == ErrorCode.UNSUPPORTED_URL
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_settings.py tests/test_urls.py tests/test_jobs.py -q`
Expected: FAIL. `ImportError: cannot import name 'extract_url'` for test_urls; `AttributeError: ... web_passcode` for settings; `job.url` still contains the share text for the jobs test.

- [ ] **Step 3: Implement**

`reels_api/settings.py`, add after `public_base_url`:

```python
    web_passcode: str | None = None
```

`reels_api/urls.py`, add `import re` at the top and this function after `ALLOWED_HOSTS`:

```python
_URL_RE = re.compile(r"https?://\S+")
_TRAILING_PUNCTUATION = ".,;:!?)]}>\"'"


def extract_url(text: str) -> str:
    """Pull the first http(s) URL out of share text.

    Returns the stripped text unchanged when there is no URL, so that
    detect_source can reject it with unsupported_url as before.
    """
    match = _URL_RE.search(text)
    if match is None:
        return text.strip()
    return match.group(0).rstrip(_TRAILING_PUNCTUATION)
```

`reels_api/jobs.py`: change the import to `from reels_api.urls import detect_source, extract_url` and replace `submit` with:

```python
    async def submit(self, text: str) -> Job:
        url = extract_url(text)
        source = detect_source(url)  # raises JobError(unsupported_url)
        if self.queue.full():
            raise JobError(ErrorCode.TOO_MANY_JOBS)
        job = Job(id=new_job_id(), url=url, source=source)
        await self.store.add(job)
        self.queue.put_nowait(job)
        return job
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add reels_api/settings.py reels_api/urls.py reels_api/jobs.py tests/test_settings.py tests/test_urls.py tests/test_jobs.py
git commit -m "feat: web_passcode setting and URL extraction from share text"
```

---

### Task 2: Cookie helpers and `require_access`

**Files:**
- Modify: `reels_api/auth.py` (rewrite)
- Modify: `reels_api/routes.py:7,12`
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: `Settings.web_passcode` (Task 1).
- Produces: `auth.SESSION_COOKIE = "reels_session"`, `auth.session_cookie_value(settings: Settings) -> str`, `auth.session_is_valid(settings: Settings, cookie: str | None) -> bool`, `auth.require_access` (FastAPI dependency). `require_api_key` is removed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_routes.py` (add `from reels_api.auth import SESSION_COOKIE, session_cookie_value` and `from tests.conftest import make_settings` is already there):

```python
def test_cookie_value_is_hmac_of_passcode(tmp_path):
    import hashlib
    import hmac

    settings = make_settings(tmp_path, web_passcode="letmein")
    expected = hmac.new(b"test-key", b"reels-web-session:letmein", hashlib.sha256).hexdigest()
    assert session_cookie_value(settings) == expected
    assert session_cookie_value(make_settings(tmp_path, web_passcode="other")) != expected


def test_valid_cookie_grants_access(app_factory, tmp_path):
    app = app_factory(web_passcode="letmein")
    cookie = session_cookie_value(app.state.settings)
    with TestClient(app) as client:
        r = client.get("/jobs/nope", cookies={SESSION_COOKIE: cookie})
        assert r.status_code == 404  # authenticated, job simply does not exist
        r = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, cookies={SESSION_COOKIE: cookie})
        assert r.status_code == 202


def test_wrong_or_stale_cookie_is_401(app_factory, tmp_path):
    app = app_factory(web_passcode="letmein")
    stale = session_cookie_value(make_settings(tmp_path, web_passcode="old-passcode"))
    with TestClient(app) as client:
        for bad in ("nope", stale, ""):
            r = client.get("/jobs/nope", cookies={SESSION_COOKIE: bad})
            assert r.status_code == 401
            assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}


def test_cookie_rejected_when_web_disabled(app_factory, tmp_path):
    enabled = make_settings(tmp_path, web_passcode="letmein")
    cookie = session_cookie_value(enabled)
    with TestClient(app_factory()) as client:  # no web_passcode
        assert client.get("/jobs/nope", cookies={SESSION_COOKIE: cookie}).status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_routes.py -q`
Expected: FAIL with `ImportError: cannot import name 'SESSION_COOKIE'`.

- [ ] **Step 3: Implement**

Replace `reels_api/auth.py` entirely:

```python
import hashlib
import hmac
import secrets

from fastapi import Header, HTTPException, Request

from reels_api.settings import Settings

SESSION_COOKIE = "reels_session"
_SESSION_PREFIX = b"reels-web-session:"


def session_cookie_value(settings: Settings) -> str:
    """The one shared cookie value. Changing API_KEY or WEB_PASSCODE rotates it."""
    passcode = settings.web_passcode or ""
    return hmac.new(settings.api_key.encode(), _SESSION_PREFIX + passcode.encode(), hashlib.sha256).hexdigest()


def session_is_valid(settings: Settings, cookie: str | None) -> bool:
    if not settings.web_passcode or not cookie:
        return False
    return secrets.compare_digest(cookie, session_cookie_value(settings))


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail={"error": "unauthorized", "message": "Missing or invalid API key."},
    )


async def require_access(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Allow the request when the API key header or the web session cookie is valid."""
    settings: Settings = request.app.state.settings
    if x_api_key and secrets.compare_digest(x_api_key, settings.api_key):
        return
    if session_is_valid(settings, request.cookies.get(SESSION_COOKIE)):
        return
    raise _unauthorized()
```

`reels_api/routes.py`: change line 7 to `from reels_api.auth import require_access` and line 12 to `protected = APIRouter(dependencies=[Depends(require_access)])`.

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add reels_api/auth.py reels_api/routes.py tests/test_routes.py
git commit -m "feat: session cookie helpers and require_access dependency"
```

---

### Task 3: `JobStore.list_recent` and `GET /jobs`

**Files:**
- Modify: `reels_api/jobs.py` (`JobStore`)
- Modify: `reels_api/routes.py`
- Test: `tests/test_jobs.py`, `tests/test_routes.py`

**Interfaces:**
- Produces: `JobStore.list_recent(limit: int = 50) -> list[Job]`: only `status == DONE` with `result` and `finished_at` set, newest `finished_at` first, at most `limit`.
- Produces: `GET /jobs` (protected) returning `{"jobs": [job_to_dict(...), ...]}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_jobs.py`:

```python
def _done_job(job_id: str, finished_minutes_ago: int, now: datetime) -> Job:
    job = Job(id=job_id, url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    job.finished_at = now - timedelta(minutes=finished_minutes_ago)
    job.result = JobResult(Path(f"{job_id}.mp4"), "T", Source.TIKTOK, 1.0, 1, 1, 1)
    return job


@pytest.mark.anyio
async def test_list_recent_filters_sorts_and_caps():
    store = JobStore()
    now = datetime.now(UTC)
    await store.add(_done_job("older", 30, now))
    await store.add(_done_job("newest", 1, now))
    await store.add(_done_job("middle", 10, now))
    failed = Job(id="failed", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
    failed.finished_at = now
    await store.add(failed)
    await store.add(Job(id="queued", url="u", source=Source.TIKTOK))
    await store.add(Job(id="running", url="u", source=Source.TIKTOK, status=JobStatus.DOWNLOADING))

    recent = await store.list_recent()
    assert [j.id for j in recent] == ["newest", "middle", "older"]
    assert [j.id for j in await store.list_recent(limit=2)] == ["newest", "middle"]


@pytest.mark.anyio
async def test_list_recent_default_cap_is_50():
    store = JobStore()
    now = datetime.now(UTC)
    for i in range(60):
        await store.add(_done_job(f"j{i}", i, now))
    assert len(await store.list_recent()) == 50
```

Append to `tests/test_routes.py`:

```python
def test_list_jobs_requires_access_and_lists_done_jobs(app_factory):
    with TestClient(app_factory()) as client:
        assert client.get("/jobs").status_code == 401

        first = client.post("/jobs", json={"url": "https://vm.tiktok.com/1/"}, headers=HEADERS).json()["id"]
        poll_until_finished(client, first)
        second = client.post("/jobs", json={"url": "https://vm.tiktok.com/2/"}, headers=HEADERS).json()["id"]
        poll_until_finished(client, second)

        r = client.get("/jobs", headers=HEADERS)
        assert r.status_code == 200
        jobs = r.json()["jobs"]
        assert [j["id"] for j in jobs] == [second, first]
        assert jobs[0]["status"] == "done"
        assert jobs[0]["file_url"] == f"/files/{second}.mp4"
        assert jobs[0]["title"] == "My Cool Reel!"


def test_list_jobs_excludes_failed(app_factory):
    with TestClient(app_factory("job_error")) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/1/"}, headers=HEADERS).json()["id"]
        poll_until_finished(client, job_id)
        assert client.get("/jobs", headers=HEADERS).json() == {"jobs": []}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_jobs.py tests/test_routes.py -q`
Expected: FAIL with `AttributeError: 'JobStore' object has no attribute 'list_recent'` and the route test getting 405 or 404 for `GET /jobs` with the header (FastAPI matches `/jobs` only for POST today, so it returns 405).

- [ ] **Step 3: Implement**

`reels_api/jobs.py`, add to `JobStore` after `all`:

```python
    async def list_recent(self, limit: int = 50) -> list[Job]:
        """Finished jobs with a file, newest first, for the web feed."""
        async with self._lock:
            done = [
                j for j in self._jobs.values()
                if j.status == JobStatus.DONE and j.result is not None and j.finished_at is not None
            ]
        done.sort(key=lambda j: j.finished_at, reverse=True)
        return done[:limit]
```

`reels_api/routes.py`, add after `create_job`:

```python
@protected.get("/jobs")
async def list_jobs(request: Request) -> dict:
    jobs = await request.app.state.store.list_recent()
    base = request.app.state.settings.public_base_url
    return {"jobs": [job_to_dict(job, base) for job in jobs]}
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add reels_api/jobs.py reels_api/routes.py tests/test_jobs.py tests/test_routes.py
git commit -m "feat: GET /jobs recent feed backed by JobStore.list_recent"
```

---

### Task 4: Thumbnail command, `JobResult.thumbnail_path`, `thumbnail_url`

**Files:**
- Modify: `reels_api/media.py`
- Modify: `reels_api/models.py`
- Test: `tests/test_media.py`, `tests/test_models.py`

**Interfaces:**
- Produces: `media.build_thumbnail_command(src: Path, dst: Path, at_seconds: float) -> list[str]`.
- Produces: `media.thumbnail_seek(duration_seconds: float | None) -> float` (`min(1.0, duration / 2)`, or `0.0` when unknown or not positive).
- Produces: `media.make_thumbnail(src: Path, dst: Path, duration_seconds: float | None, timeout: float) -> None`, raises `JobError(PROCESSING_FAILED)` on non-zero exit or timeout.
- Produces: `JobResult.thumbnail_path: Path | None = None` (last field, keyword-optional; existing positional constructions keep working).
- Produces: `job_to_dict` adds `"thumbnail_url"` for done jobs (`/files/<id>.jpg`, absolute with `public_base_url`, or `None`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_media.py`:

```python
def test_build_thumbnail_command():
    cmd = media.build_thumbnail_command(Path("in.mp4"), Path("out.jpg"), 1.0)
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert cmd.index("-ss") < cmd.index("-i")          # seek before input: fast
    assert cmd[cmd.index("-ss") + 1] == "1.000"
    assert cmd[cmd.index("-i") + 1] == "in.mp4"
    assert cmd[cmd.index("-frames:v") + 1] == "1"
    assert cmd[cmd.index("-vf") + 1] == "scale=360:-2"
    assert cmd[cmd.index("-q:v") + 1] == "4"
    assert cmd[-1] == "out.jpg"


@pytest.mark.parametrize(
    "duration,expected",
    [(None, 0.0), (0, 0.0), (-3, 0.0), (0.5, 0.25), (1.5, 0.75), (2.0, 1.0), (60.0, 1.0)],
)
def test_thumbnail_seek(duration, expected):
    assert media.thumbnail_seek(duration) == expected


def test_make_thumbnail_success(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    media.make_thumbnail(tmp_path / "in.mp4", tmp_path / "out.jpg", 20.0, timeout=7)
    assert calls[0][1]["timeout"] == 7
    assert calls[0][0][calls[0][0].index("-ss") + 1] == "1.000"


def test_make_thumbnail_failure_and_timeout(monkeypatch, tmp_path):
    def fail_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Output file is empty")

    monkeypatch.setattr(media.subprocess, "run", fail_run)
    with pytest.raises(JobError) as exc:
        media.make_thumbnail(tmp_path / "in.mp4", tmp_path / "out.jpg", 5.0, timeout=7)
    assert exc.value.code == ErrorCode.PROCESSING_FAILED
    assert "Output file is empty" in exc.value.message

    def slow_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(media.subprocess, "run", slow_run)
    with pytest.raises(JobError) as exc:
        media.make_thumbnail(tmp_path / "in.mp4", tmp_path / "out.jpg", 5.0, timeout=1)
    assert exc.value.code == ErrorCode.PROCESSING_FAILED
```

Append to `tests/test_models.py` (the file already imports `Path`? If not, add `from pathlib import Path`):

```python
def test_job_to_dict_thumbnail_url():
    job = Job(id="abc", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    job.result = _result(100)
    assert job.result.thumbnail_path is None
    assert job_to_dict(job)["thumbnail_url"] is None

    job.result.thumbnail_path = Path("/data/files/abc.jpg")
    assert job_to_dict(job)["thumbnail_url"] == "/files/abc.jpg"
    assert job_to_dict(job, "https://reels.example.com/")["thumbnail_url"] == "https://reels.example.com/files/abc.jpg"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_media.py tests/test_models.py -q`
Expected: FAIL with `AttributeError: module 'reels_api.media' has no attribute 'build_thumbnail_command'` and `KeyError: 'thumbnail_url'` / `AttributeError: 'JobResult' object has no attribute 'thumbnail_path'`.

- [ ] **Step 3: Implement**

`reels_api/media.py`, append:

```python
def thumbnail_seek(duration_seconds: float | None) -> float:
    """Grab the frame one second in, or halfway through very short clips."""
    if not duration_seconds or duration_seconds <= 0:
        return 0.0
    return min(1.0, duration_seconds / 2)


def build_thumbnail_command(src: Path, dst: Path, at_seconds: float) -> list[str]:
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_seconds:.3f}", "-i", str(src),
        "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4",
        str(dst),
    ]


def make_thumbnail(src: Path, dst: Path, duration_seconds: float | None, timeout: float) -> None:
    """Write one JPEG frame of src to dst. Raises JobError(processing_failed) on any failure."""
    cmd = build_thumbnail_command(src, dst, thumbnail_seek(duration_seconds))
    log.debug("ffmpeg thumbnail: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise JobError(ErrorCode.PROCESSING_FAILED, "thumbnail timed out") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise JobError(ErrorCode.PROCESSING_FAILED, "thumbnail failed: " + stderr[-300:])
```

`reels_api/models.py`: in `JobResult`, add as the last field (after `height`):

```python
    thumbnail_path: Path | None = None
```

Replace the whole `if job.status == JobStatus.DONE and job.result is not None:` branch of `job_to_dict` with:

```python
    if job.status == JobStatus.DONE and job.result is not None:
        r = job.result
        file_url = f"/files/{job.id}.mp4"
        thumbnail_url = f"/files/{job.id}.jpg" if r.thumbnail_path is not None else None
        if public_base_url:
            base = public_base_url.rstrip("/")
            file_url = base + file_url
            if thumbnail_url:
                thumbnail_url = base + thumbnail_url
        body.update(
            {
                "file_url": file_url,
                "thumbnail_url": thumbnail_url,
                "title": r.title,
                "source": r.source.value,
                "duration_seconds": r.duration_seconds,
                "size_bytes": r.size_bytes,
                "width": r.width,
                "height": r.height,
                "whatsapp_ok": r.whatsapp_ok,
                "expires_at": _iso_z(job.expires_at) if job.expires_at else None,
            }
        )
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add reels_api/media.py reels_api/models.py tests/test_media.py tests/test_models.py
git commit -m "feat: thumbnail ffmpeg command and thumbnail_url in job JSON"
```

---

### Task 5: Non-fatal thumbnail stage in the pipeline

**Files:**
- Modify: `reels_api/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `media.make_thumbnail` (Task 4), `JobResult.thumbnail_path` (Task 4).
- Produces: `pipeline.Thumbnailer = Callable[[Path, Path, float | None, float], None]`; `Pipeline.thumbnailer: Thumbnailer` field defaulting to `media.make_thumbnail`. Thumbnail written to `<storage_dir>/<id>.jpg` after convert, with timeout `min(30.0, remaining)`. Failure is logged and leaves `thumbnail_path=None`; on job failure the `.jpg` is removed with the `.mp4`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pipeline.py`:

```python
def fake_thumbnail_factory(calls, behaviour="ok"):
    def fake_thumbnail(src, dst, duration_seconds, timeout):
        calls.append(("thumbnail", src, dst, duration_seconds, timeout))
        if behaviour == "raise":
            dst.write_bytes(b"partial")
            raise JobError(ErrorCode.PROCESSING_FAILED, "thumbnail failed")
        dst.write_bytes(b"\xff\xd8jpeg")
    return fake_thumbnail


def test_pipeline_writes_thumbnail(tmp_path):
    settings = make_settings(tmp_path, job_timeout_seconds=100)
    calls = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    result = p.run(make_job(), lambda s: None)
    assert [c[0] for c in calls] == ["download", "probe", "convert", "thumbnail"]
    thumb = calls[3]
    assert thumb[1] == settings.storage_dir / "job1.mp4"     # frame taken from the converted file
    assert thumb[2] == settings.storage_dir / "job1.jpg"
    assert thumb[3] == 9.5                                    # duration passed through
    assert 0 < thumb[4] <= 30
    assert result.thumbnail_path == settings.storage_dir / "job1.jpg"
    assert result.thumbnail_path.exists()


def test_pipeline_thumbnail_failure_is_non_fatal(tmp_path):
    settings = make_settings(tmp_path)
    calls = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls, behaviour="raise"),
    )
    result = p.run(make_job(), lambda s: None)
    assert result.file_path.exists()
    assert result.thumbnail_path is None
    assert not (settings.storage_dir / "job1.jpg").exists()   # partial file removed


def test_pipeline_removes_thumbnail_when_job_fails(tmp_path):
    settings = make_settings(tmp_path)
    calls = []
    settings.storage_dir.mkdir(parents=True)
    stale_thumb = settings.storage_dir / "job1.jpg"
    stale_thumb.write_bytes(b"old")

    def failing_convert(src, dst, transcode, timeout):
        dst.write_bytes(b"half")
        raise JobError(ErrorCode.PROCESSING_FAILED)

    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=failing_convert,
        thumbnailer=fake_thumbnail_factory(calls),
    )
    with pytest.raises(JobError):
        p.run(make_job(), lambda s: None)
    assert not (settings.storage_dir / "job1.mp4").exists()
    assert not stale_thumb.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_pipeline.py -q`
Expected: FAIL with `TypeError: Pipeline.__init__() got an unexpected keyword argument 'thumbnailer'`.

- [ ] **Step 3: Implement**

Replace `reels_api/pipeline.py` entirely:

```python
from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from reels_api import downloader, media
from reels_api.downloader import DownloadedMedia
from reels_api.media import ProbeResult
from reels_api.models import Job, JobResult, JobStatus
from reels_api.settings import Settings

log = logging.getLogger(__name__)

Downloader = Callable[[str, Path, Path | None], DownloadedMedia]
Prober = Callable[[Path], ProbeResult]
Converter = Callable[[Path, Path, bool, float], None]
Thumbnailer = Callable[[Path, Path, float | None, float], None]
StatusSetter = Callable[[JobStatus], None]

THUMBNAIL_TIMEOUT_SECONDS = 30.0


@dataclass
class Pipeline:
    """Runs the blocking stages for one job. Call from a worker thread."""

    settings: Settings
    downloader: Downloader = field(default=downloader.download)
    prober: Prober = field(default=media.probe)
    converter: Converter = field(default=media.convert)
    thumbnailer: Thumbnailer = field(default=media.make_thumbnail)

    def run(self, job: Job, set_status: StatusSetter) -> JobResult:
        deadline = time.monotonic() + self.settings.job_timeout_seconds
        temp_dir = self.settings.temp_dir / job.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        dst = self.settings.storage_dir / f"{job.id}.mp4"
        thumb = self.settings.storage_dir / f"{job.id}.jpg"
        try:
            set_status(JobStatus.DOWNLOADING)
            downloaded = self.downloader(job.url, temp_dir, self.settings.cookies_file)

            set_status(JobStatus.PROCESSING)
            probed = self.prober(downloaded.path)
            remaining = max(1.0, deadline - time.monotonic())
            self.converter(downloaded.path, dst, media.needs_transcode(probed), remaining)

            info = downloaded.info
            duration = probed.duration_seconds if probed.duration_seconds is not None else info.duration_seconds
            thumbnail_path = self._make_thumbnail(job, dst, thumb, duration, deadline)

            return JobResult(
                file_path=dst,
                title=info.title,
                source=job.source,
                duration_seconds=duration,
                size_bytes=dst.stat().st_size,
                width=probed.width if probed.width is not None else info.width,
                height=probed.height if probed.height is not None else info.height,
                thumbnail_path=thumbnail_path,
            )
        except BaseException:
            dst.unlink(missing_ok=True)
            thumb.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _make_thumbnail(
        self, job: Job, src: Path, dst: Path, duration: float | None, deadline: float
    ) -> Path | None:
        """A thumbnail failure never fails the job."""
        remaining = max(1.0, deadline - time.monotonic())
        try:
            self.thumbnailer(src, dst, duration, min(THUMBNAIL_TIMEOUT_SECONDS, remaining))
        except Exception:
            log.warning("job %s: thumbnail failed, continuing without one", job.id, exc_info=True)
            dst.unlink(missing_ok=True)
            return None
        return dst if dst.is_file() else None
```

- [ ] **Step 4: Stop the existing pipeline tests from shelling out to ffmpeg**

The four existing tests build a `Pipeline` without a `thumbnailer`, so the default `media.make_thumbnail` would now call the real `subprocess.run`. In `tests/test_pipeline.py` add `thumbnailer=fake_thumbnail_factory(calls),` to the `Pipeline(...)` constructor call in each of `test_pipeline_success`, `test_pipeline_transcodes_when_needed`, `test_pipeline_passes_cookies` and `test_pipeline_falls_back_to_download_metadata`. (`test_pipeline_cleans_temp_on_failure` fails during download, before the thumbnail stage, and needs no change.) Move `fake_thumbnail_factory` above `make_job` so it is defined before its first use.

In `test_pipeline_success` change the expected call order to:

```python
    kinds = [c[0] for c in calls]
    assert kinds == ["download", "probe", "convert", "thumbnail"]
```

- [ ] **Step 5: Run the full suite**

Run: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add reels_api/pipeline.py tests/test_pipeline.py
git commit -m "feat: non-fatal thumbnail stage in the pipeline"
```

---

### Task 6: Thumbnail route and sweeper cleanup

**Files:**
- Modify: `reels_api/routes.py`
- Modify: `reels_api/jobs.py` (`sweep`)
- Test: `tests/test_routes.py`, `tests/test_jobs.py`

**Interfaces:**
- Consumes: `JobResult.thumbnail_path` (Task 4).
- Produces: `GET /files/{job_id}.jpg` (protected): `image/jpeg`, `Cache-Control: private, max-age=21600`, no `Content-Disposition`; 404 when the job is unknown, not done, has no thumbnail, or the file is missing.
- Sweeper deletes `thumbnail_path` along with `file_path`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_routes.py`, change `FakePipeline.run` so the happy path also writes a thumbnail. Replace the last three lines of `run` with:

```python
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.storage_dir / f"{job.id}.mp4"
        path.write_bytes(b"0123456789")
        thumb = None
        if self.behaviour != "no_thumb":
            thumb = self.settings.storage_dir / f"{job.id}.jpg"
            thumb.write_bytes(b"\xff\xd8jpeg")
        return JobResult(path, "My Cool Reel!", job.source, 2.5, 10, 1080, 1920, thumbnail_path=thumb)
```

Then append:

```python
def test_thumbnail_route(app_factory):
    with TestClient(app_factory()) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
        assert body["thumbnail_url"] == f"/files/{job_id}.jpg"

        assert client.get(f"/files/{job_id}.jpg").status_code == 401
        r = client.get(f"/files/{job_id}.jpg", headers=HEADERS)
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert r.headers["cache-control"] == "private, max-age=21600"
        assert "content-disposition" not in r.headers
        assert r.content == b"\xff\xd8jpeg"

        assert client.get("/files/nope.jpg", headers=HEADERS).status_code == 404

        app = client.app
        job = app.state.store._jobs[job_id]
        job.result.thumbnail_path.unlink()
        assert client.get(f"/files/{job_id}.jpg", headers=HEADERS).status_code == 404


def test_thumbnail_route_404_when_job_has_none(app_factory):
    with TestClient(app_factory("no_thumb")) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
        assert body["thumbnail_url"] is None
        assert client.get(f"/files/{job_id}.jpg", headers=HEADERS).status_code == 404
```

In `tests/test_jobs.py::test_sweep_removes_expired_and_stray_dirs`, after `old_file.write_bytes(b"x")` add:

```python
    old_thumb = settings.storage_dir / "old.jpg"
    old_thumb.write_bytes(b"x")
```

change the `old.result = ...` line to:

```python
    old.result = JobResult(old_file, "T", Source.TIKTOK, 1.0, 1, 1, 1, thumbnail_path=old_thumb)
```

and after `assert not old_file.exists()` add:

```python
    assert not old_thumb.exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_routes.py tests/test_jobs.py -q`
Expected: FAIL. The thumbnail route test gets 404 with the header (no route yet), and the sweep test fails on `assert not old_thumb.exists()`.

- [ ] **Step 3: Implement**

`reels_api/routes.py`, add after `get_file`:

```python
@protected.get("/files/{job_id}.jpg")
async def get_thumbnail(job_id: str, request: Request) -> FileResponse:
    job = await request.app.state.store.get(job_id)
    if job is None or job.status != JobStatus.DONE or job.result is None:
        raise _not_found()
    thumb = job.result.thumbnail_path
    if thumb is None or not thumb.is_file():
        raise _not_found()
    return FileResponse(
        thumb,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=21600"},
    )
```

`reels_api/jobs.py`, in `sweep`, replace the `if job.result is not None:` block with:

```python
                if job.result is not None:
                    job.result.file_path.unlink(missing_ok=True)
                    if job.result.thumbnail_path is not None:
                        job.result.thumbnail_path.unlink(missing_ok=True)
```

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add reels_api/routes.py reels_api/jobs.py tests/test_routes.py tests/test_jobs.py
git commit -m "feat: serve thumbnails and sweep them with the video"
```

---

### Task 7: `web.py`: limiter, login, page routes, static mount, app wiring

**Files:**
- Create: `reels_api/web.py`
- Create: `reels_api/static/login.html`, `reels_api/static/app.html`, `reels_api/static/manifest.webmanifest`, `reels_api/static/sw.js`, `reels_api/static/icon-192.png`, `reels_api/static/icon-512.png`
- Create: `scripts/make_icons.py`
- Modify: `reels_api/main.py`
- Test: `tests/test_web.py` (new)

**Interfaces:**
- Consumes: `auth.SESSION_COOKIE`, `auth.session_cookie_value`, `auth.session_is_valid` (Task 2).
- Produces: `web.AttemptLimiter(max_attempts=10, window_seconds=900, clock=time.monotonic)` with `is_blocked(ip) -> bool`, `record_failure(ip) -> None`, `clear(ip) -> None`.
- Produces: `web.install(app: FastAPI) -> None`: sets `app.state.login_limiter`, includes the web router (`GET /`, `POST /web/login`, `GET /manifest.webmanifest`, `GET /sw.js`) and mounts `/static`.
- Produces: `web.STATIC_DIR: Path`.
- `main.create_app` calls `web.install(app)` only when `settings.web_passcode` is truthy.
- The HTML shells reference `/static/style.css`, `/static/login.js` and `/static/app.js`, which Tasks 8 and 9 create. Element ids used by the JS: login page `login-form`, `passcode`, `continue`, `login-error`; app page `link-form`, `link`, `paste`, `go`, `status`, `submit-error`, `retry`, `player-slot`, `feed`, templates `player-template`, `card-template`.

- [ ] **Step 1: Generate the icons**

Create `scripts/make_icons.py`:

```python
"""Write plain PNG app icons (dark square, white play triangle) with the stdlib only.

Run from the repo root: python scripts/make_icons.py
"""
import struct
import zlib
from pathlib import Path

BG = (17, 24, 39)
FG = (255, 255, 255)
OUT = Path(__file__).resolve().parent.parent / "reels_api" / "static"


def _chunk(tag: bytes, data: bytes) -> bytes:
    body = tag + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def make_icon(size: int, path: Path) -> None:
    x0, x1 = size * 0.36, size * 0.74
    y0, y1 = size * 0.26, size * 0.74
    cy = (y0 + y1) / 2
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter byte: none
        for x in range(size):
            inside = False
            if x0 <= x <= x1 and y0 <= y <= y1:
                t = (x - x0) / (x1 - x0)  # 0 at the flat left edge, 1 at the apex
                inside = abs(y - cy) <= (y1 - y0) / 2 * (1 - t)
            row += bytes(FG if inside else BG)
        rows.append(bytes(row))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    png = b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + _chunk(b"IEND", b"")
    path.write_bytes(png)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    make_icon(192, OUT / "icon-192.png")
    make_icon(512, OUT / "icon-512.png")
    print("wrote", OUT / "icon-192.png", "and", OUT / "icon-512.png")
```

Run: `python scripts/make_icons.py`
Expected: prints the two paths; both files exist and open as images.

- [ ] **Step 2: Write the static shells**

`reels_api/static/login.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#111827">
<title>Reels</title>
<link rel="stylesheet" href="/static/style.css">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/static/icon-192.png">
</head>
<body class="login">
<main class="card">
  <h1>Reels</h1>
  <p class="muted">Enter the passcode to continue.</p>
  <form id="login-form" autocomplete="off">
    <input id="passcode" type="password" autocomplete="current-password" placeholder="Passcode" required autofocus>
    <button id="continue" type="submit">Continue</button>
    <p id="login-error" class="error" hidden></p>
  </form>
</main>
<script src="/static/login.js"></script>
</body>
</html>
```

`reels_api/static/app.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#111827">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Reels">
<title>Reels</title>
<link rel="stylesheet" href="/static/style.css">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/static/icon-192.png">
</head>
<body>
<header><h1>Reels</h1></header>
<main>
  <section class="card">
    <form id="link-form" autocomplete="off">
      <div class="row">
        <input id="link" type="text" inputmode="url" autocapitalize="off" autocorrect="off" spellcheck="false"
               placeholder="Paste a TikTok or Instagram link">
        <button id="paste" type="button" class="secondary" hidden>Paste</button>
      </div>
      <button id="go" type="submit">Get video</button>
    </form>
    <p id="status" class="status" hidden></p>
    <p id="submit-error" class="error" hidden></p>
    <button id="retry" type="button" class="secondary" hidden>Try again</button>
  </section>

  <section id="player-slot"></section>

  <section>
    <h2>Recent</h2>
    <div id="feed"></div>
  </section>
</main>

<template id="player-template">
  <div class="card player">
    <video controls playsinline preload="metadata"></video>
    <h3 class="title"></h3>
    <p class="note muted" hidden>Over 16 MB. Older WhatsApp versions may refuse it.</p>
    <div class="row">
      <button class="share" type="button" hidden disabled>Preparing…</button>
      <a class="download button secondary" download>Download</a>
    </div>
    <p class="error" hidden></p>
  </div>
</template>

<template id="card-template">
  <button class="feed-card" type="button">
    <div class="thumb"><img alt="" loading="lazy"></div>
    <div class="meta">
      <div class="title"></div>
      <div class="sub muted"></div>
    </div>
  </button>
</template>

<script src="/static/app.js"></script>
</body>
</html>
```

`reels_api/static/manifest.webmanifest`:

```json
{
  "name": "Reels",
  "short_name": "Reels",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#111827",
  "theme_color": "#111827",
  "icons": [
    { "src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ],
  "share_target": {
    "action": "/",
    "method": "GET",
    "params": { "title": "title", "text": "text", "url": "url" }
  }
}
```

`reels_api/static/sw.js`:

```js
// Minimal service worker: no caching, no fetch handler.
// Exists only so older Android Chrome versions treat the page as installable.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_web.py`:

```python
import pytest
from fastapi.testclient import TestClient

from reels_api.auth import SESSION_COOKIE, session_cookie_value
from reels_api.main import create_app
from reels_api.web import AttemptLimiter
from tests.conftest import make_settings
from tests.test_routes import FakePipeline

PASSCODE = "letmein"


@pytest.fixture
def web_app(tmp_path):
    def factory(**overrides):
        settings = make_settings(tmp_path, web_passcode=PASSCODE, **overrides)
        return create_app(settings=settings, pipeline=FakePipeline(settings))
    return factory


def https_client(app) -> TestClient:
    # The cookie is Secure; httpx only sends it back over https.
    return TestClient(app, base_url="https://testserver")


# ---- AttemptLimiter

class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_limiter_blocks_after_max_failures_and_expires():
    clock = FakeClock()
    limiter = AttemptLimiter(max_attempts=3, window_seconds=900, clock=clock)
    assert limiter.is_blocked("1.1.1.1") is False
    for _ in range(3):
        limiter.record_failure("1.1.1.1")
    assert limiter.is_blocked("1.1.1.1") is True
    assert limiter.is_blocked("2.2.2.2") is False

    clock.now += 901
    assert limiter.is_blocked("1.1.1.1") is False


def test_limiter_clear_and_prunes_other_ips():
    clock = FakeClock()
    limiter = AttemptLimiter(max_attempts=2, window_seconds=60, clock=clock)
    limiter.record_failure("a")
    limiter.record_failure("b")
    limiter.record_failure("b")
    assert limiter.is_blocked("b") is True
    limiter.clear("b")
    assert limiter.is_blocked("b") is False

    clock.now += 61
    limiter.is_blocked("zzz")          # any call prunes every entry
    assert limiter._attempts == {}


# ---- POST /web/login

def test_login_success_sets_cookie(web_app):
    with https_client(web_app()) as client:
        r = client.post("/web/login", json={"passcode": PASSCODE})
        assert r.status_code == 204
        assert r.content == b""
        cookie = r.headers["set-cookie"]
        assert cookie.startswith(f"{SESSION_COOKIE}={session_cookie_value(client.app.state.settings)};")
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=31536000"):
            assert attr in lowered, attr


def test_login_wrong_passcode(web_app):
    with https_client(web_app()) as client:
        r = client.post("/web/login", json={"passcode": "nope"})
        assert r.status_code == 401
        assert r.json() == {"error": "wrong_passcode", "message": "That passcode is not right."}
        assert "set-cookie" not in r.headers


def test_login_malformed_body_422(web_app):
    with https_client(web_app()) as client:
        assert client.post("/web/login", json={}).status_code == 422


def test_login_rate_limited_after_ten_failures(web_app):
    with https_client(web_app()) as client:
        for _ in range(10):
            assert client.post("/web/login", json={"passcode": "nope"}).status_code == 401
        r = client.post("/web/login", json={"passcode": PASSCODE})   # right passcode, still blocked
        assert r.status_code == 429
        assert r.json() == {
            "error": "too_many_attempts",
            "message": "Too many wrong tries. Wait 15 minutes and try again.",
        }


def test_login_success_clears_counter(web_app):
    with https_client(web_app()) as client:
        for _ in range(9):
            client.post("/web/login", json={"passcode": "nope"})
        assert client.post("/web/login", json={"passcode": PASSCODE}).status_code == 204
        for _ in range(9):
            assert client.post("/web/login", json={"passcode": "nope"}).status_code == 401


# ---- GET / and the cookie round-trip

def test_index_serves_login_then_app(web_app):
    with https_client(web_app()) as client:
        r = client.get("/")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["cache-control"] == "no-store"
        assert 'id="passcode"' in r.text

        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.get("/?text=hello")
        assert r.status_code == 200
        assert 'id="link"' in r.text
        assert r.headers["cache-control"] == "no-store"

        # the same cookie now unlocks the API
        assert client.get("/jobs").status_code == 200


def test_index_ignores_bad_cookie(web_app):
    with https_client(web_app()) as client:
        r = client.get("/", cookies={SESSION_COOKIE: "garbage"})
        assert 'id="passcode"' in r.text


# ---- manifest, service worker, static files

def test_manifest_sw_and_static(web_app):
    with TestClient(web_app()) as client:
        m = client.get("/manifest.webmanifest")
        assert m.status_code == 200
        assert m.headers["content-type"].startswith("application/manifest+json")
        assert m.headers["cache-control"] == "no-cache"
        assert m.json()["share_target"]["action"] == "/"

        sw = client.get("/sw.js")
        assert sw.status_code == 200
        assert sw.headers["content-type"].startswith("text/javascript")
        assert sw.headers["cache-control"] == "no-cache"

        icon = client.get("/static/icon-192.png")
        assert icon.status_code == 200
        assert icon.headers["content-type"] == "image/png"
        assert icon.headers["cache-control"] == "no-cache"

        assert client.get("/static/missing.js").status_code == 404


# ---- disabled mode

@pytest.mark.parametrize("passcode", [None, ""])
def test_web_disabled_when_passcode_unset(tmp_path, passcode):
    settings = make_settings(tmp_path, web_passcode=passcode)
    app = create_app(settings=settings, pipeline=FakePipeline(settings))
    with TestClient(app) as client:
        for path in ("/", "/manifest.webmanifest", "/sw.js", "/static/icon-192.png"):
            assert client.get(path).status_code == 404, path
        assert client.post("/web/login", json={"passcode": "x"}).status_code == 404
        assert client.get("/health").status_code == 200
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `python -m pytest tests/test_web.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'reels_api.web'`.

- [ ] **Step 5: Implement `web.py`**

Create `reels_api/web.py`:

```python
"""Everything the phone page needs that is not the JSON API: login, page shells, static files."""
from __future__ import annotations

import secrets
import time
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.staticfiles import StaticFiles

from reels_api.auth import SESSION_COOKIE, session_cookie_value, session_is_valid

STATIC_DIR = Path(__file__).parent / "static"
MAX_ATTEMPTS = 10
WINDOW_SECONDS = 15 * 60
COOKIE_MAX_AGE_SECONDS = 365 * 24 * 3600
NO_CACHE = {"Cache-Control": "no-cache"}
NO_STORE = {"Cache-Control": "no-store"}

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


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles that asks browsers to revalidate on every load (ETag makes that cheap)."""

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/")
async def index(request: Request) -> FileResponse:
    settings = request.app.state.settings
    page = "app.html" if session_is_valid(settings, request.cookies.get(SESSION_COOKIE)) else "login.html"
    return FileResponse(STATIC_DIR / page, media_type="text/html", headers=NO_STORE)


@router.post("/web/login", status_code=204)
async def login(body: LoginRequest, request: Request, response: Response) -> None:
    settings = request.app.state.settings
    limiter: AttemptLimiter = request.app.state.login_limiter
    ip = _client_ip(request)
    if limiter.is_blocked(ip):
        raise HTTPException(
            status_code=429,
            detail={"error": "too_many_attempts", "message": "Too many wrong tries. Wait 15 minutes and try again."},
        )
    if not secrets.compare_digest(body.passcode, settings.web_passcode):
        limiter.record_failure(ip)
        raise HTTPException(
            status_code=401,
            detail={"error": "wrong_passcode", "message": "That passcode is not right."},
        )
    limiter.clear(ip)
    response.set_cookie(
        SESSION_COOKIE,
        session_cookie_value(settings),
        max_age=COOKIE_MAX_AGE_SECONDS,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


@router.get("/manifest.webmanifest")
async def manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json", headers=NO_CACHE)


@router.get("/sw.js")
async def service_worker() -> FileResponse:
    # Served at the root so its scope is "/".
    return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript", headers=NO_CACHE)


def install(app: FastAPI) -> None:
    """Attach the web page to the app. Only called when WEB_PASSCODE is set."""
    app.state.login_limiter = AttemptLimiter()
    app.include_router(router)
    app.mount("/static", NoCacheStaticFiles(directory=STATIC_DIR), name="static")
```

Note on the 204: the route returns `None` and sets the cookie on the injected `response`. FastAPI merges those headers into its own empty 204 response. Do **not** return a `Response` object from this route; FastAPI would then drop the injected response's headers.

`reels_api/main.py`: add `from reels_api import web` to the imports, and after `app.include_router(router)` add:

```python
    if settings.web_passcode:
        web.install(app)
```

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add reels_api/web.py reels_api/main.py reels_api/static scripts/make_icons.py tests/test_web.py
git commit -m "feat: web login, attempt limiter, page shells and static files"
```

---

### Task 8: Login page behaviour and shared styles

**Files:**
- Create: `reels_api/static/login.js`
- Create: `reels_api/static/style.css`
- Test: `tests/test_web.py` (one small addition), then a manual check

**Interfaces:**
- Consumes: element ids from `login.html` (Task 7) and `POST /web/login` (Task 7).
- Produces: `style.css` classes used by `app.html` and `app.js`: `card`, `row`, `button`, `secondary`, `muted`, `error`, `status`, `player`, `feed-card`, `thumb`, `meta`, `title`, `sub`, `empty`, `note`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`:

```python
def test_page_assets_are_served(web_app):
    with TestClient(web_app()) as client:
        for path, prefix in (("/static/style.css", "text/css"), ("/static/login.js", "text/javascript")):
            r = client.get(path)
            assert r.status_code == 200, path
            assert r.headers["content-type"].startswith(prefix), path
            assert r.headers["cache-control"] == "no-cache"
```

Run: `python -m pytest tests/test_web.py::test_page_assets_are_served -q`
Expected: FAIL with 404 on `/static/style.css`.

- [ ] **Step 2: Write `login.js`**

```js
(() => {
  "use strict";
  const form = document.getElementById("login-form");
  const input = document.getElementById("passcode");
  const button = document.getElementById("continue");
  const error = document.getElementById("login-error");

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    button.disabled = true;
    try {
      const r = await fetch("/web/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passcode: input.value }),
      });
      if (r.status === 204) {
        // Reload keeps the query string, so a shared link still starts after login.
        location.reload();
        return;
      }
      let message = "Something went wrong. Try again.";
      try {
        message = (await r.json()).message || message;
      } catch (_) {
        // non-JSON body: keep the generic message
      }
      showError(message);
    } catch (_) {
      showError("Network error. Try again.");
    } finally {
      button.disabled = false;
    }
  });
})();
```

- [ ] **Step 3: Write `style.css`**

```css
:root {
  --bg: #f3f4f6;
  --card: #ffffff;
  --text: #111827;
  --muted: #6b7280;
  --border: #e5e7eb;
  --accent: #2563eb;
  --accent-text: #ffffff;
  --error: #b91c1c;
  --radius: 14px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0b0f19;
    --card: #111827;
    --text: #f9fafb;
    --muted: #9ca3af;
    --border: #1f2937;
    --accent: #3b82f6;
    --error: #f87171;
  }
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  padding: env(safe-area-inset-top) 16px calc(env(safe-area-inset-bottom) + 24px);
  background: var(--bg);
  color: var(--text);
  font: 16px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
header h1, main h1 { font-size: 1.5rem; margin: 20px 0 12px; }
h2 { font-size: 1.1rem; margin: 24px 0 10px; }
h3 { font-size: 1rem; margin: 10px 0 4px; word-break: break-word; }
main { max-width: 560px; margin: 0 auto; }
body.login main { margin-top: 15vh; }

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 14px;
}
.row { display: flex; gap: 8px; align-items: stretch; }
.row > * { flex: 1 1 auto; min-width: 0; }
.row > button, .row > .button { flex: 0 0 auto; }

input {
  width: 100%;
  font: inherit;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg);
  color: var(--text);
  margin-bottom: 10px;
}
button, .button {
  font: inherit;
  font-weight: 600;
  padding: 12px 16px;
  border: 0;
  border-radius: 10px;
  background: var(--accent);
  color: var(--accent-text);
  width: 100%;
  cursor: pointer;
  text-align: center;
  text-decoration: none;
  display: inline-block;
}
button:disabled { opacity: 0.55; cursor: default; }
.secondary { background: transparent; color: var(--accent); border: 1px solid var(--border); }
.row .secondary { width: auto; }
.muted { color: var(--muted); font-size: 0.9rem; }
.error { color: var(--error); margin: 8px 0 0; }
.status { margin: 12px 0 0; color: var(--muted); }
.empty { color: var(--muted); padding: 8px 0; }

.player video {
  width: 100%;
  max-height: 70vh;
  background: #000;
  border-radius: 10px;
}
.player .row { margin-top: 10px; }
.player .row > * { flex: 1 1 0; }
.note { margin: 4px 0 0; }

.feed-card {
  display: flex;
  gap: 12px;
  align-items: center;
  width: 100%;
  padding: 10px;
  margin-bottom: 10px;
  background: var(--card);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  text-align: left;
  font-weight: 400;
}
.feed-card .thumb {
  flex: 0 0 64px;
  width: 64px;
  height: 96px;
  border-radius: 8px;
  overflow: hidden;
  background: var(--border);
}
.feed-card img { width: 100%; height: 100%; object-fit: cover; display: block; }
.feed-card .meta { min-width: 0; }
.feed-card .title {
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
```

- [ ] **Step 4: Run the tests, then check the login page by hand**

Run: `python -m pytest -q`
Expected: all PASS.

Manual: create a `.env` with `API_KEY=dev`, `WEB_PASSCODE=letmein`, `STORAGE_DIR=./data/files`, `TEMP_DIR=./data/tmp`; run `uvicorn reels_api.main:create_app --factory --reload`; open `http://localhost:8000/` in Chrome at phone width. Expect the login card; a wrong passcode shows "That passcode is not right."; the right one reloads into the app shell (which has no behaviour yet, that is Task 9).

- [ ] **Step 5: Commit**

```bash
git add reels_api/static/login.js reels_api/static/style.css tests/test_web.py
git commit -m "feat: login page behaviour and shared mobile styles"
```

---

### Task 9: `app.js`: submit, poll, feed, player, share

**Files:**
- Create: `reels_api/static/app.js`
- Test: `tests/test_web.py` (one small addition), then a manual check against a local run

**Interfaces:**
- Consumes: `POST /jobs` (accepts share text, Task 1), `GET /jobs/{id}`, `GET /jobs` (Task 3), `thumbnail_url` (Task 4), element ids and templates from `app.html` (Task 7), classes from `style.css` (Task 8).
- Behaviour follows spec section 7.2 to 7.5 exactly.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`:

```python
def test_app_js_is_served(web_app):
    with TestClient(web_app()) as client:
        r = client.get("/static/app.js")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/javascript")
        assert "navigator.share" in r.text
```

Run: `python -m pytest tests/test_web.py::test_app_js_is_served -q`
Expected: FAIL with 404.

- [ ] **Step 2: Write `app.js`**

```js
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const form = $("link-form");
  const linkInput = $("link");
  const pasteBtn = $("paste");
  const goBtn = $("go");
  const statusEl = $("status");
  const errorEl = $("submit-error");
  const retryBtn = $("retry");
  const playerSlot = $("player-slot");
  const feedEl = $("feed");
  const playerTemplate = $("player-template");
  const cardTemplate = $("card-template");

  const POLL_MS = 1500;
  const STATUS_TEXT = { queued: "Waiting in line…", downloading: "Downloading…", processing: "Processing…" };
  const SOURCE_NAME = { tiktok: "TikTok", instagram: "Instagram" };

  // Decided once, before any file exists (see spec 7.4).
  const canShareFiles =
    typeof navigator.canShare === "function" &&
    navigator.canShare({ files: [new File([""], "probe.mp4", { type: "video/mp4" })] });

  let lastSubmitted = "";
  let openPlayer = null; // { element, video, card, abort }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  }

  // ---------- helpers

  function show(el, text) {
    if (text !== undefined) el.textContent = text;
    el.hidden = false;
  }
  function hide(el) {
    el.hidden = true;
  }
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  class Unauthorized extends Error {}

  // Every request goes through here: a 401 anywhere means the cookie is gone.
  async function api(path, options) {
    const r = await fetch(path, options);
    if (r.status === 401) {
      location.reload();
      throw new Unauthorized();
    }
    return r;
  }

  // Same rules as routes.slugify on the server.
  function slugify(title) {
    const slug = String(title || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    return slug.slice(0, 60).replace(/-+$/g, "") || "video";
  }

  function formatDuration(seconds) {
    if (seconds == null) return "";
    const s = Math.round(seconds);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  function formatExpiry(iso) {
    if (!iso) return "";
    const ms = new Date(iso).getTime() - Date.now();
    if (ms <= 0) return "gone soon";
    const minutes = Math.round(ms / 60000);
    if (minutes < 60) return `gone in ${Math.max(1, minutes)}m`;
    return `gone in ${Math.round(minutes / 60)}h`;
  }

  // ---------- submitting a link (spec 7.2)

  function fail(message) {
    hide(statusEl);
    show(errorEl, message);
    show(retryBtn);
  }

  async function submit(text) {
    const trimmed = (text || "").trim();
    if (!trimmed) return;
    lastSubmitted = trimmed;
    hide(errorEl);
    hide(retryBtn);
    goBtn.disabled = true;
    show(statusEl, "Sending…");
    try {
      const r = await api("/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: trimmed }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        fail(body.message || "Something went wrong. Try again.");
        return;
      }
      const { id } = await r.json();
      await poll(id);
    } catch (err) {
      if (!(err instanceof Unauthorized)) fail("Network error. Try again.");
    } finally {
      goBtn.disabled = false;
    }
  }

  async function poll(id) {
    for (;;) {
      let job = null;
      try {
        const r = await api(`/jobs/${id}`);
        if (r.ok) {
          job = await r.json();
        } else if (r.status === 404) {
          fail("That download is gone. Try again.");
          return;
        }
      } catch (err) {
        if (err instanceof Unauthorized) return;
        // network error: keep polling
      }
      if (job) {
        if (job.status === "done") {
          hide(statusEl);
          linkInput.value = "";
          openPlayerFor(job, null);
          await loadFeed();
          return;
        }
        if (job.status === "failed") {
          fail(job.message || "The download failed.");
          return;
        }
        show(statusEl, STATUS_TEXT[job.status] || "Working…");
      }
      await sleep(POLL_MS);
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submit(linkInput.value);
  });
  retryBtn.addEventListener("click", () => submit(lastSubmitted));

  if (navigator.clipboard && typeof navigator.clipboard.readText === "function") {
    pasteBtn.hidden = false;
    pasteBtn.addEventListener("click", async () => {
      try {
        linkInput.value = await navigator.clipboard.readText();
        linkInput.focus();
      } catch (_) {
        // permission denied: the user can long-press to paste instead
      }
    });
  }

  // ---------- recent feed (spec 7.3)

  async function loadFeed() {
    let jobs;
    try {
      const r = await api("/jobs");
      if (!r.ok) return;
      jobs = (await r.json()).jobs || [];
    } catch (_) {
      return; // keep whatever is on screen
    }
    feedEl.replaceChildren();
    if (!jobs.length) {
      const p = document.createElement("p");
      p.className = "empty";
      p.textContent = "Nothing here yet.";
      feedEl.append(p);
      return;
    }
    for (const job of jobs) feedEl.append(buildCard(job));
  }

  function buildCard(job) {
    const card = cardTemplate.content.firstElementChild.cloneNode(true);
    const img = card.querySelector("img");
    if (job.thumbnail_url) img.src = job.thumbnail_url;
    else img.remove(); // the grey .thumb box stays as the placeholder
    card.querySelector(".title").textContent = job.title || "Video";
    card.querySelector(".sub").textContent = [
      SOURCE_NAME[job.source] || job.source,
      formatDuration(job.duration_seconds),
      formatExpiry(job.expires_at),
    ]
      .filter(Boolean)
      .join(" · ");
    card.addEventListener("click", () => openPlayerFor(job, card));
    return card;
  }

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") loadFeed();
  });

  // ---------- video player with Share and Download (spec 7.4)

  function closePlayer() {
    if (!openPlayer) return;
    const { element, video, card, abort } = openPlayer;
    abort.abort(); // stops an in-flight share prefetch and drops its memory
    video.pause();
    video.removeAttribute("src");
    video.load();
    element.remove();
    if (card) card.hidden = false;
    openPlayer = null;
  }

  // card === null: the user's own job, shown at the top. Otherwise the tapped feed card is replaced.
  function openPlayerFor(job, card) {
    closePlayer();
    const element = playerTemplate.content.firstElementChild.cloneNode(true);
    const video = element.querySelector("video");
    video.src = job.file_url;
    if (job.thumbnail_url) video.poster = job.thumbnail_url;
    element.querySelector(".title").textContent = job.title || "Video";
    element.querySelector(".download").href = job.file_url;
    if (job.whatsapp_ok === false) element.querySelector(".note").hidden = false;

    const abort = new AbortController();
    openPlayer = { element, video, card, abort };
    if (card) {
      card.hidden = true;
      card.before(element);
    } else {
      playerSlot.replaceChildren(element);
      element.scrollIntoView({ block: "start", behavior: "smooth" });
    }
    setupShare(element, job, abort.signal);
  }

  async function setupShare(element, job, signal) {
    if (!canShareFiles) return;
    const button = element.querySelector(".share");
    const shareError = element.querySelector(".error");
    button.hidden = false;
    let file = null;

    // No await before navigator.share: iOS Safari needs the fresh tap.
    button.addEventListener("click", () => {
      if (!file) return;
      navigator.share({ files: [file] }).catch((err) => {
        if (err && err.name === "AbortError") return; // user closed the sheet
        show(shareError, "Sharing failed. Use Download instead.");
      });
    });

    try {
      const r = await api(job.file_url, { signal });
      if (!r.ok) throw new Error(`fetch failed: ${r.status}`);
      const blob = await r.blob();
      file = new File([blob], `${slugify(job.title)}.mp4`, { type: "video/mp4" });
    } catch (_) {
      if (!signal.aborted) button.hidden = true;
      return;
    }
    if (!navigator.canShare({ files: [file] })) {
      button.hidden = true;
      return;
    }
    button.disabled = false;
    button.textContent = "Share to WhatsApp";
  }

  // ---------- start-up: share target and first feed load

  function consumeShareTarget() {
    const params = new URLSearchParams(location.search);
    const parts = ["url", "text", "title"].map((k) => params.get(k)).filter(Boolean);
    if (!parts.length) return;
    history.replaceState(null, "", location.pathname);
    linkInput.value = parts.join(" ");
    submit(linkInput.value);
  }

  loadFeed();
  consumeShareTarget();
})();
```

- [ ] **Step 3: Run the tests**

Run: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 4: Manual check at phone width (spec section 10, "Manual")**

With the `.env` from Task 8 and ffmpeg on `PATH`, run `uvicorn reels_api.main:create_app --factory --reload` and open `http://localhost:8000/` in Chrome's device toolbar at 390 px width. Check each item and note any failure:

1. Wrong passcode shows the message; right passcode shows the app.
2. Paste a real public TikTok link, tap **Get video**: status goes "Waiting in line…" or "Downloading…" then "Processing…", then the player appears at the top with a poster, and the feed shows the new card with a thumbnail, "TikTok", `m:ss` and "gone in 6h".
3. The video plays. **Download** saves a file named after the title. (Desktop Chrome has no file share, so the Share button is hidden; that is expected.)
4. Paste `https://www.tiktok.com/@nobody/video/1`: the job fails with a message and **Try again** appears.
5. Paste `just words`: "Only Instagram and TikTok video links are supported." appears immediately.
6. Open `http://localhost:8000/?text=Check%20this%20out%20https%3A%2F%2Fvm.tiktok.com%2FZMabc123%2F`: the box fills, the job starts, and the URL bar loses the query string.
7. Tap a feed card: it becomes a player; tap another: the first card comes back.
8. Delete the cookie in DevTools and tap **Get video**: the page reloads into the login screen.

- [ ] **Step 5: Commit**

```bash
git add reels_api/static/app.js tests/test_web.py
git commit -m "feat: app page behaviour: submit, poll, feed, player and share"
```

---

### Task 10: Caddy, docker compose, Dockerfile, `.env.example`

**Files:**
- Create: `Caddyfile`
- Modify: `docker-compose.yml`
- Modify: `Dockerfile` (CMD)
- Modify: `.env.example`

**Interfaces:**
- Produces: `caddy` service proxying `{$SITE_ADDRESS}` to `api:8000`; `api` bound to `127.0.0.1:8000` only; uvicorn trusts proxy headers.

- [ ] **Step 1: Write the files**

`Caddyfile`:

```
{$SITE_ADDRESS} {
    reverse_proxy api:8000
}
```

`docker-compose.yml`:

```yaml
services:
  api:
    build: .
    ports:
      - "127.0.0.1:8000:8000"   # reachable from the VM only; Caddy fronts it
    env_file: .env
    environment:
      STORAGE_DIR: /data/files
      TEMP_DIR: /data/tmp
    volumes:
      - ./data:/data
      # Uncomment to enable Instagram downloads, and set COOKIES_FILE=/cookies.txt in .env
      # - ./cookies.txt:/cookies.txt:ro
    restart: unless-stopped

  caddy:
    image: caddy:2
    ports:
      - "80:80"
      - "443:443"
    environment:
      # Only the host name. Caddy must not see API_KEY or WEB_PASSCODE, so no env_file here.
      SITE_ADDRESS: ${SITE_ADDRESS:-localhost}
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - api
    restart: unless-stopped

volumes:
  caddy_data:
  caddy_config:
```

`Dockerfile`, replace the `CMD` line:

```dockerfile
CMD ["uvicorn", "reels_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips=*"]
```

`.env.example`, replace entirely:

```
API_KEY=change-me
STORAGE_DIR=./data/files
TEMP_DIR=./data/tmp
RETENTION_HOURS=6
# Concurrent downloads. Use 1 on a 1 GiB VM.
WORKERS=2
MAX_QUEUE=20
JOB_TIMEOUT_SECONDS=180
# COOKIES_FILE=./cookies.txt
# PUBLIC_BASE_URL=https://reels.example.com
LOG_LEVEL=info

# Passcode for the phone web page. Leave empty to disable the page entirely.
WEB_PASSCODE=
# Public host name Caddy serves over HTTPS (docker compose only; the app ignores it).
SITE_ADDRESS=reels.example.cloudapp.azure.com
```

- [ ] **Step 2: Verify the compose file and the image**

Run: `docker compose config --quiet`
Expected: no output, exit code 0 (a `.env` must exist; copy `.env.example` if needed).

Run: `docker compose build api`
Expected: build succeeds. Then `docker compose up -d api && sleep 5 && curl -s http://127.0.0.1:8000/health && docker compose down`
Expected: `{"status":"ok",...}`. Skip this step if Docker is not installed locally and say so in the task report.

- [ ] **Step 3: Confirm the test suite is unaffected**

Run: `python -m pytest -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add Caddyfile docker-compose.yml Dockerfile .env.example
git commit -m "feat: Caddy HTTPS front, proxy headers and web env vars"
```

---

### Task 11: README: web page, local dev and Azure deploy

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update the README**

Replace the `## Run with Docker` section's first line comment with `cp .env.example .env        # set API_KEY, WEB_PASSCODE, SITE_ADDRESS` and, after `## Use`, insert this section:

```markdown
## Phone web page

Set `WEB_PASSCODE` in `.env` and the app serves a mobile page at `/`.
Friends enter the passcode once, paste a TikTok or Instagram link (or the
whole share text), watch the result and tap **Share to WhatsApp**. A
shared **Recent** feed lists everything downloaded in the last
`RETENTION_HOURS`. Leave `WEB_PASSCODE` empty to disable the page; the
JSON API is unaffected either way.

The page needs HTTPS for sharing and for the home-screen install. In
production that is Caddy (below). For local development set
`WEB_PASSCODE` in `.env`, run uvicorn, and open `http://localhost:8000/`
in Chrome or Firefox (Safari refuses the `Secure` cookie over plain http).

On Android, **Add to Home screen** installs the page and it then appears
in TikTok's share menu. On iPhone, paste the link.
```

Append this section before `## Development` (the outer fence below is four backticks only so the inner `bash` block survives; do not copy the outer fence):

````markdown
## Deploy on Azure (free account)

The Azure free account gives 12 months of 750 hours per month each of
B1s, B2pts v2 (Arm) and B2ats v2 (AMD) Linux VMs, plus two P6 (64 GiB)
Premium SSD disks. One VM running all month fits in 750 hours. Every free
size has 1 GiB of RAM, so run with `WORKERS=1` and add swap.

1. In the portal open **Free services** and create a VM from there so
   free-eligible options are selected. Image Ubuntu Server LTS, size
   `Standard_B2ats_v2`, OS disk **Premium SSD, 64 GiB** (P6). A different
   disk type or size is billed.
2. On the VM's public IP, set a **DNS name label**. The host name becomes
   `<label>.<region>.cloudapp.azure.com`; that is your `SITE_ADDRESS`.
3. In the network security group allow inbound TCP 80 and 443 from any
   source, and TCP 22 only from your own IP.
4. In **Cost Management** create a budget of 1 unit of currency per month
   with an email alert, so any charge is noticed immediately.
5. SSH in and add swap:

   ```bash
   sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

6. Install Docker Engine and the compose plugin (`https://docs.docker.com/engine/install/ubuntu/`),
   clone this repo, `cp .env.example .env`, and set `API_KEY`,
   `WEB_PASSCODE`, `SITE_ADDRESS` and `WORKERS=1`.
7. `docker compose up -d --build`. Caddy obtains the Let's Encrypt
   certificate on first start. Open `https://<SITE_ADDRESS>/` on a phone.

Cost caveats:

- The free allowance lasts 12 months from sign-up. After that the VM, disk
  and IP are billed at normal rates unless deleted.
- The public IPv4 address may not be covered: Azure now issues Standard
  SKU (static) addresses, and the free allowance has historically covered
  dynamic ones. Expect a few dollars per month for the address; the budget
  alert in step 4 shows the real figure.
- Outbound data beyond the monthly free bandwidth allowance is billed.
  Short clips of a few MB each stay far below it for a group of friends.
````

In `## Development`, add after the pytest lines:

```markdown
python scripts/make_icons.py          # regenerate the PWA icons (already committed)
```

- [ ] **Step 2: Proofread**

Read the whole README once top to bottom. Every command must be copy-pasteable; every env var named must exist in `.env.example`.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: phone web page, local dev and Azure free-tier deploy"
```

---

### Task 12: Final verification

**Files:** none new.

- [ ] **Step 1: Full suite and spec checklist**

Run: `python -m pytest -q`
Expected: all PASS, zero warnings about unclosed resources.

Walk spec section 10's automated list and confirm each item has a test:

| spec item | test |
|-----------|------|
| extract_url cases | `test_urls.py::test_extract_url` |
| header works, cookie works, wrong cookie, stale cookie, cookie with web disabled | `test_routes.py::test_valid_cookie_grants_access`, `::test_wrong_or_stale_cookie_is_401`, `::test_cookie_rejected_when_web_disabled` |
| login 204 + attributes, 401, 11th attempt 429, success clears, old entries expire | `test_web.py::test_login_*`, `::test_limiter_*` |
| disabled mode 404s | `test_web.py::test_web_disabled_when_passcode_unset` |
| `GET /` page choice | `test_web.py::test_index_serves_login_then_app`, `::test_index_ignores_bad_cookie` |
| `GET /jobs` filter, order, cap, auth | `test_jobs.py::test_list_recent_*`, `test_routes.py::test_list_jobs_*` |
| thumbnail command, seek, pipeline success, non-fatal failure, `.jpg` route, sweeper | `test_media.py::test_build_thumbnail_command`, `::test_thumbnail_seek`, `test_pipeline.py::test_pipeline_writes_thumbnail`, `::test_pipeline_thumbnail_failure_is_non_fatal`, `test_routes.py::test_thumbnail_route*`, `test_jobs.py::test_sweep_removes_expired_and_stray_dirs` |

- [ ] **Step 2: Working tree clean**

Run: `git status --short`
Expected: empty. If `data/` or `.env` show up they are ignored already; anything else is a missed `git add`.

- [ ] **Step 3: Hand off**

The remaining spec items are on real devices after deploying and are the owner's: Share to WhatsApp on an iPhone and an Android phone, and sharing from the TikTok app to the installed page on Android.
