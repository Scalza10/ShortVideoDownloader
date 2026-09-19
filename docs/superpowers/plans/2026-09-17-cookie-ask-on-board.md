# Cookie Pop-up on the Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Phones whose login cookie was set before the login page asked get a pop-up on the board that they must answer: "allow cookie" marks the cookie as agreed, "no thanks, log me out" is today's "no".

**Architecture:** The session cookie gets a second value. Every login now sets the "agreed" value (HMAC with a new prefix); today's value becomes "unasked" and still logs in. `GET /` renders `app.html` through `pages.py` with `data-cookie="ask"` for an unasked cookie wherever it would otherwise serve the login page, so share links still open view-only. A new `POST /web/cookie` re-sets the agreed value. A new ES module `cookie.js` shows a modal `<dialog>` and holds back `start()` in `app.js` until the person agrees.

**Tech Stack:** Python 3.12, FastAPI, pytest (existing); plain HTML, CSS and ES modules; Node 22 only for `node --check`; Docker for the manual checks (the dev server needs ffmpeg).

**Spec:** `docs/superpowers/specs/2026-09-17-cookie-ask-on-board-design.md` (the "pop-up spec"). Read it first; this plan argues from it. It builds on `2026-09-17-cookie-consent-design.md` (the "cookie spec") and `2026-09-17-invite-and-share-links-design.md` (the "links spec").

## Global Constraints

- No new Python or JS dependencies. No build step, no framework, no JS test harness.
- Automated tests run with no network and no ffmpeg: `.venv/Scripts/python.exe -m pytest -q` from the repo root (Git Bash) or `.venv\Scripts\python.exe -m pytest -q` (PowerShell). The suite is green (221 passed, 1 deselected) before Task 1.
- JS syntax check after every JS edit: `node --check reels_api/static/<file>.js`.
- Cookie values: agreed = HMAC-SHA256 with key `API_KEY` over `b"reels-web-session-agreed:" + WEB_PASSCODE`; unasked = the same over `b"reels-web-session:" + WEB_PASSCODE`. Both log in. Only the agreed value is ever set.
- Cookie comparisons use `secrets.compare_digest` on bytes.
- The session cookie keeps its attributes: `max_age=31536000`, `path="/"`, `secure=True`, `httponly=True`, `samesite="lax"` (`_set_session_cookie` in `web.py`).
- No `GET` ever sets the session cookie.
- Every `GET /` response and every `POST /web/cookie` response sends `Cache-Control: no-store`.
- Error body, exactly: `{"error": "unauthorized", "message": "Missing or invalid API key."}`.
- Storage key `reels-cookie-choice`, value `declined`, the same strings as `login.js`. Every `localStorage` access is inside `try`/`catch`.
- Toggle visibility with `el.hidden` (`style.css` has `[hidden] { display: none !important; }`).
- UI copy, exactly (lowercase):
  - title `this site uses one cookie`
  - notice: `one cookie keeps this phone logged in for a year.` / `nothing else is stored. no tracking, no ads.` / `you can log out from the board any time.`
  - buttons `allow cookie`, `no thanks, log me out`
  - errors `couldn't save that. try again.`, `couldn't log out. try again.`
- No page requests anything from another origin.
- Every commit message ends with a second `-m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"`.
- ffmpeg is not installed locally. Manual checks use the dev server in Docker and Chrome at 390×844 (DevTools device mode, touch) and 1280×800. Build the image once (`docker build -t reels-dev .`), then run it from the repo root in PowerShell:

  ```powershell
  docker run --rm --name reels-dev -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app `
    -v "${PWD}/reels_api:/app/reels_api:ro" -v "${PWD}/scripts:/app/scripts:ro" `
    reels-dev python scripts/dev_board.py --host 0.0.0.0
  ```

  Static file edits show up on reload; Python edits need `docker stop reels-dev` and a new `docker run`. After Task 1 it prints `old cookie:  <value>`. **"Use the old cookie"** below means: log in with passcode `dev`, then DevTools → Application → Storage → Cookies → `http://localhost:8000`, double-click the `reels_session` value, paste the printed old cookie, press Enter, reload.

## File map

| file | change | responsibility |
|------|--------|----------------|
| `reels_api/auth.py` | modify | agreed and unasked values, `session_state` |
| `reels_api/web.py` | modify | `GET /` rows 1, 2, 4; `POST /web/cookie` |
| `reels_api/pages.py` | modify | `render_app` |
| `reels_api/static/app.html` | modify | `data-cookie` placeholder; `#cookie-ask` dialog |
| `reels_api/static/cookie.js` | create | the pop-up: `createCookieAsk` |
| `reels_api/static/api.js` | modify | `agreeToCookie()` |
| `reels_api/static/app.js` | modify | `start()` owns the refreshes; opens the pop-up |
| `reels_api/static/style.css` | modify | `.cookie-ask`, `::backdrop`, `.cookie-ask-title` |
| `scripts/dev_board.py` | modify | prints the old cookie value |
| `tests/test_routes.py` | modify | cookie values, access with both values |
| `tests/test_web.py` | modify | per task |
| `tests/test_pages.py` | modify | `render_app` |
| `tests/test_dev_board.py` | modify | `link_lines` |
| `README.md`, `CLAUDE.md`, two specs | modify | document the feature (Task 5) |

---

### Task 1: Two cookie values

Every login sets the agreed value; the unasked value still logs in everywhere. The dev server prints the unasked value for the manual checks.

**Files:**
- Modify: `reels_api/auth.py:10-23`
- Modify: `scripts/dev_board.py` (docstring, imports, `link_lines`, `main`)
- Test: `tests/test_routes.py:9`, `tests/test_routes.py:180-209`
- Test: `tests/test_web.py` (imports, new helper, login and invite assertions, two new tests)
- Test: `tests/test_dev_board.py:75-81`

**Interfaces:**
- Consumes: nothing new.
- Produces (in `reels_api/auth.py`):
  - `AGREED = "agreed"`, `UNASKED = "unasked"` (module constants, `str`)
  - `session_cookie_value(settings: Settings) -> str`: the agreed value (was: the only value)
  - `unasked_cookie_value(settings: Settings) -> str`
  - `session_state(settings: Settings, cookie: str | None) -> str | None`: `AGREED`, `UNASKED` or `None`
  - `session_is_valid(settings: Settings, cookie: str | None) -> bool`: unchanged signature
- Produces (in `tests/test_web.py`): `set_unasked_cookie(client) -> None`
- Produces (in `scripts/dev_board.py`): `link_lines(port: int, seeds: list[Job], settings: Settings) -> list[str]`

- [ ] **Step 1: Write the failing tests in `tests/test_routes.py`**

Change the import on line 9:

```python
from reels_api.auth import SESSION_COOKIE, session_cookie_value, session_state, unasked_cookie_value
```

Replace `test_cookie_value_is_hmac_of_passcode`, `test_valid_cookie_grants_access` and `test_wrong_or_stale_cookie_is_401` (lines 180-209) with:

```python
def test_cookie_values_are_hmacs_of_passcode(tmp_path):
    import hashlib
    import hmac

    settings = make_settings(tmp_path, web_passcode="letmein")
    agreed = hmac.new(b"test-key", b"reels-web-session-agreed:letmein", hashlib.sha256).hexdigest()
    unasked = hmac.new(b"test-key", b"reels-web-session:letmein", hashlib.sha256).hexdigest()
    assert session_cookie_value(settings) == agreed
    assert unasked_cookie_value(settings) == unasked
    other = make_settings(tmp_path, web_passcode="other")
    assert session_cookie_value(other) != agreed
    assert unasked_cookie_value(other) != unasked


def test_session_state(tmp_path):
    settings = make_settings(tmp_path, web_passcode="letmein")
    assert session_state(settings, session_cookie_value(settings)) == "agreed"
    assert session_state(settings, unasked_cookie_value(settings)) == "unasked"
    for bad in (None, "", "nope", "é", session_cookie_value(settings) + "x"):
        assert session_state(settings, bad) is None, bad
    disabled = make_settings(tmp_path)  # no web_passcode
    assert session_state(disabled, session_cookie_value(disabled)) is None
    assert session_state(disabled, unasked_cookie_value(disabled)) is None


@pytest.mark.parametrize("cookie_value", [session_cookie_value, unasked_cookie_value], ids=["agreed", "unasked"])
def test_valid_cookie_grants_access(app_factory, cookie_value):
    app = app_factory(web_passcode="letmein")
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, cookie_value(app.state.settings))
        r = client.get("/jobs/nope")
        assert r.status_code == 404  # authenticated, job simply does not exist
        r = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"})
        assert r.status_code == 202
        reel = _done_reel(client, "https://vm.tiktok.com/y/")
        assert client.get(f"/files/{reel['id']}.mp4").status_code == 200  # no k: the cookie opens it


def test_wrong_or_stale_cookie_is_401(app_factory, tmp_path):
    app = app_factory(web_passcode="letmein")
    old = make_settings(tmp_path, web_passcode="old-passcode")
    with TestClient(app) as client:
        for bad in ("nope", session_cookie_value(old), unasked_cookie_value(old), ""):
            client.cookies.set(SESSION_COOKIE, bad)
            r = client.get("/jobs/nope")
            assert r.status_code == 401
            assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}
```

(`_done_reel` is defined further down the same module; that is fine at run time.)

- [ ] **Step 2: Write the failing tests in `tests/test_web.py`**

Change the auth import on line 4:

```python
from reels_api.auth import SESSION_COOKIE, session_cookie_value, unasked_cookie_value
```

Directly after `https_client` (line 33), add:

```python
def set_unasked_cookie(client) -> None:
    # A cookie set before the login page asked (pop-up spec 3).
    client.cookies.set(SESSION_COOKIE, unasked_cookie_value(client.app.state.settings))
```

In `test_login_success_sets_cookie`, after the line `cookie = r.headers["set-cookie"]`, add:

```python
        assert unasked_cookie_value(client.app.state.settings) not in cookie
```

In `test_accept_invite_with_right_token_sets_cookie`, after the line `cookie = r.headers["set-cookie"]`, add the same line:

```python
        assert unasked_cookie_value(client.app.state.settings) not in cookie
```

After `test_logout_without_cookie_is_401`, add:

```python
def test_logout_deletes_an_unasked_cookie(web_app):
    with https_client(web_app()) as client:
        set_unasked_cookie(client)
        r = client.post("/web/logout")
        assert r.status_code == 204
        assert r.headers["set-cookie"].startswith(f'{SESSION_COOKIE}="";')
```

After `test_join_with_cookie_goes_to_board_without_counting`, add:

```python
def test_join_with_unasked_cookie_goes_to_board_without_counting(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        set_unasked_cookie(client)
        for _ in range(10):
            r = client.get("/join/wrong", follow_redirects=False)
            assert r.status_code == 303
            assert r.headers["location"] == "/"
            assert "set-cookie" not in r.headers
        client.cookies.clear()
        assert client.post("/web/login", json={"passcode": PASSCODE}).status_code == 204   # not blocked
```

- [ ] **Step 3: Write the failing test in `tests/test_dev_board.py`**

Add to the imports at the top:

```python
from reels_api.auth import unasked_cookie_value
```

Replace `test_link_lines` with:

```python
def test_link_lines(tmp_path):
    settings = make_settings(tmp_path, web_passcode="dev")
    jobs = dev_board.seed_jobs(settings, fake_clips(tmp_path))
    old_cookie = f"old cookie:  {unasked_cookie_value(settings)}"
    assert dev_board.link_lines(8000, jobs, settings) == [
        "invite link: http://localhost:8000/join/dev-invite-token-0000",
        f"share link:  http://localhost:8000/?reel=seed00&k={jobs[0].share_key}",
        old_cookie,
    ]
    assert dev_board.link_lines(9000, [], settings) == [
        "invite link: http://localhost:9000/join/dev-invite-token-0000",
        old_cookie,
    ]
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_routes.py tests/test_web.py tests/test_dev_board.py`
Expected: collection errors, `ImportError: cannot import name 'session_state' from 'reels_api.auth'` (and `unasked_cookie_value`).

- [ ] **Step 5: Implement the two values in `reels_api/auth.py`**

Replace lines 10-23 (from `SESSION_COOKIE = "reels_session"` through the end of `session_is_valid`) with:

```python
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
```

- [ ] **Step 6: Print the old cookie in `scripts/dev_board.py`**

In the module docstring, replace:

```
On start it prints the invite link and the newest seeded reel's share link.
Open them in a private window to see what someone without the cookie sees.
"""
```

with:

```
On start it prints the invite link and the newest seeded reel's share link.
Open them in a private window to see what someone without the cookie sees.
It also prints an old cookie value, from before the login page asked: log
in, paste it over the reels_session value in DevTools (Application >
Cookies) and reload to see the cookie pop-up on the board.
"""
```

After `import uvicorn` and the blank line, add the import in alphabetical order with the other `reels_api` imports:

```python
from reels_api.auth import unasked_cookie_value
```

(so the block reads `from reels_api.auth …`, `from reels_api.jobs …`, `from reels_api.main …`, `from reels_api.models …`, `from reels_api.settings …`).

Replace `link_lines` with:

```python
def link_lines(port: int, seeds: list[Job], settings: Settings) -> list[str]:
    """The invite link, the newest seeded reel's share link (links spec 9) and an old cookie (pop-up spec 7)."""
    base = f"http://localhost:{port}"
    lines = [f"invite link: {base}/join/{INVITE_TOKEN}"]
    if seeds:
        newest = seeds[0]
        lines.append(f"share link:  {base}/?reel={newest.id}&k={newest.share_key}")
    lines.append(f"old cookie:  {unasked_cookie_value(settings)}")
    return lines
```

In `main()`, change `for line in link_lines(args.port, seeds):` to:

```python
    for line in link_lines(args.port, seeds, settings):
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 225 passed, 1 deselected.

- [ ] **Step 8: Commit**

```bash
git add reels_api/auth.py scripts/dev_board.py tests/test_routes.py tests/test_web.py tests/test_dev_board.py
git commit -m "feat: logins set a cookie value that records the agreement" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `GET /` asks on the board for an unasked cookie

Wherever the login page is served, an unasked cookie gets the board marked `data-cookie="ask"`. Share links behave as without a cookie.

**Files:**
- Modify: `reels_api/pages.py:1-5` (docstring), end of file (`render_app`)
- Modify: `reels_api/static/app.html:22` (`<body>`)
- Modify: `reels_api/web.py:15` (import), `reels_api/web.py:96-115` (`_base_url` and `index`)
- Test: `tests/test_pages.py` (end of file)
- Test: `tests/test_web.py` (end of file)

**Interfaces:**
- Consumes: `AGREED`, `UNASKED`, `session_state` from Task 1; `set_unasked_cookie(client)` in `tests/test_web.py`.
- Produces: `pages.render_app(ask: bool) -> str`; `app.html`'s `<body data-cookie="ask">` or `<body data-cookie="agreed">`, which `app.js` reads in Task 4.

- [ ] **Step 1: Write the failing test in `tests/test_pages.py`**

Append:

```python
# ---- board (pop-up spec 4)

def test_render_app_marks_whether_to_ask():
    ask = pages.render_app(True)
    agreed = pages.render_app(False)
    assert '<body data-cookie="ask">' in ask
    assert '<body data-cookie="agreed">' in agreed
    for page in (ask, agreed):
        assert "{{" not in page
        assert 'id="grid"' in page
```

- [ ] **Step 2: Write the failing tests in `tests/test_web.py`**

Append:

```python
# ---- GET / with a cookie set before the login page asked (pop-up spec 4)

def _is_ask_board(r):
    return (
        r.status_code == 200
        and r.headers["content-type"].startswith("text/html")
        and r.headers["cache-control"] == "no-store"
        and 'id="grid"' in r.text
        and '<body data-cookie="ask">' in r.text
    )


@pytest.mark.parametrize(
    "params",
    [{}, {"url": "https://vm.tiktok.com/x/", "text": "look"}, {"reel": "abc"}, {"reel": "abc", "k": ""}],
)
def test_index_with_unasked_cookie_asks_on_the_board(web_app, params):
    with https_client(web_app()) as client:
        set_unasked_cookie(client)
        assert _is_ask_board(client.get("/", params=params))


def test_index_with_agreed_cookie_does_not_ask(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.get("/")
        assert 'id="grid"' in r.text
        assert '<body data-cookie="agreed">' in r.text


def test_index_with_unasked_cookie_treats_share_links_as_without_cookie(web_app):
    with https_client(web_app()) as client:
        reel = _done_reel(client)
        failed = Job(id="failed1", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
        client.app.state.store._jobs[failed.id] = failed
        set_unasked_cookie(client)

        r = client.get("/", params={"reel": reel["id"], "k": reel["share_key"]})
        assert r.status_code == 200
        assert r.headers["cache-control"] == "no-store"
        assert '<script type="module" src="/static/watch.js"></script>' in r.text
        assert "data-cookie" not in r.text

        assert _is_ask_board(client.get("/", params={"reel": reel["id"], "k": "wrong-key-000000"}))
        assert _is_expired(client.get("/", params={"reel": "nope", "k": "whatever"}))
        assert _is_expired(client.get("/", params={"reel": failed.id, "k": failed.share_key}))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_pages.py tests/test_web.py`
Expected: FAIL. `test_render_app_marks_whether_to_ask` with `AttributeError: module 'reels_api.pages' has no attribute 'render_app'`; the unasked-cookie tests because the page has no `data-cookie` (plain `/` currently serves the board without the mark, and the wrong-key case serves the board too).

- [ ] **Step 4: Add the placeholder to `reels_api/static/app.html`**

Replace the line `<body>` with:

```html
<body data-cookie="{{cookie}}">
```

`app.html` must contain no other `{{`; `pages.fill` raises `KeyError` on unknown names.

- [ ] **Step 5: Add `render_app` to `reels_api/pages.py`**

Replace the module docstring (lines 1-5) with:

```python
"""Pages filled in on the server: the board, a shared reel and an expired one (links spec 6, 7; pop-up spec 4).

The HTML lives in static/ with {{name}} placeholders. Link-preview fetchers run no
JavaScript, so everything a preview needs is filled in here, on the server.
"""
```

Append at the end of the file:

```python
def render_app(ask: bool) -> str:
    """The board. ask=True when the phone's cookie was set before the login page asked (pop-up spec 4)."""
    template = (STATIC_DIR / "app.html").read_text(encoding="utf-8")
    return fill(template, {"cookie": "ask" if ask else "agreed"})
```

- [ ] **Step 6: Swap the login page for the pop-up board in `reels_api/web.py`**

Change the auth import (line 15) to:

```python
from reels_api.auth import (
    AGREED,
    SESSION_COOKIE,
    UNASKED,
    require_access,
    session_cookie_value,
    session_is_valid,
    session_state,
    share_key_matches,
)
```

Replace the `index` route (the `@router.get("/")` decorator through its last `return`) with:

```python
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
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 232 passed, 1 deselected. The existing `GET /` tests (`test_index_serves_login_then_app`, `test_index_with_cookie_ignores_share_key`, `test_app_page_loads_entry_module`, `test_login_and_app_pages_have_preview_tags`) still pass unchanged.

- [ ] **Step 8: Commit**

```bash
git add reels_api/pages.py reels_api/web.py reels_api/static/app.html tests/test_pages.py tests/test_web.py
git commit -m "feat: an unasked cookie gets the board marked to ask" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `POST /web/cookie`

"allow cookie" re-sets the cookie with the agreed value. Only a valid session cookie qualifies.

**Files:**
- Modify: `reels_api/web.py` (auth import, new route after `logout`)
- Test: `tests/test_web.py` (new section after `test_logout_deletes_an_unasked_cookie`; `test_web_disabled_when_passcode_unset`)

**Interfaces:**
- Consumes: `session_is_valid`, `session_cookie_value`, `unauthorized` from `reels_api/auth.py`; `_set_session_cookie(response, settings)` and `NO_STORE` in `web.py`; `set_unasked_cookie(client)` in `tests/test_web.py`.
- Produces: `POST /web/cookie` → `204` with the agreed cookie, or `401` `unauthorized` body; both `no-store`. Task 4's `agreeToCookie()` calls it.

- [ ] **Step 1: Write the failing tests in `tests/test_web.py`**

After `test_logout_deletes_an_unasked_cookie`, add:

```python
# ---- POST /web/cookie: allow cookie on the board's pop-up (pop-up spec 5.2)

def test_agree_to_cookie_marks_an_unasked_cookie_as_agreed(web_app):
    with https_client(web_app()) as client:
        settings = client.app.state.settings
        set_unasked_cookie(client)
        r = client.post("/web/cookie")
        assert r.status_code == 204
        assert r.content == b""
        assert r.headers["cache-control"] == "no-store"
        cookie = r.headers["set-cookie"]
        assert cookie.startswith(f"{SESSION_COOKIE}={session_cookie_value(settings)};")
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=31536000"):
            assert attr in lowered, attr

        # The jar would now hold two cookies (the hand-set one and the response's); keep only the new one.
        client.cookies.clear()
        client.cookies.set(SESSION_COOKIE, cookie.split(";")[0].split("=", 1)[1])
        assert '<body data-cookie="agreed">' in client.get("/").text


def test_agree_to_cookie_with_agreed_cookie(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.post("/web/cookie")
        assert r.status_code == 204
        assert r.headers["set-cookie"].startswith(f"{SESSION_COOKIE}={session_cookie_value(client.app.state.settings)};")


def test_agree_to_cookie_needs_the_cookie(web_app):
    with https_client(web_app()) as client:
        for cookie in (None, "garbage"):
            client.cookies.clear()
            if cookie:
                client.cookies.set(SESSION_COOKIE, cookie)
            for headers in ({}, {"X-API-Key": "test-key"}):  # an API key alone has no cookie to mark
                r = client.post("/web/cookie", headers=headers)
                assert r.status_code == 401, (cookie, headers)
                assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}
                assert "set-cookie" not in r.headers
                assert r.headers["cache-control"] == "no-store"
```

In `test_web_disabled_when_passcode_unset`, after `assert client.post("/web/logout").status_code == 404`, add:

```python
        assert client.post("/web/cookie").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_web.py -k "agree_to_cookie or disabled"`
Expected: FAIL. The three `agree_to_cookie` tests get `404` (or `405`) instead of `204`/`401`. The disabled-mode tests still pass (the route does not exist yet, so it is `404` either way).

- [ ] **Step 3: Implement the route in `reels_api/web.py`**

Add `unauthorized` to the auth import, keeping the names sorted:

```python
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
```

Directly after the `logout` route, add:

```python
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 235 passed, 1 deselected.

- [ ] **Step 5: Commit**

```bash
git add reels_api/web.py tests/test_web.py
git commit -m "feat: POST /web/cookie marks the cookie as agreed" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: The pop-up on the board

A modal `<dialog>` that cannot be dismissed. Nothing loads behind it until the person agrees.

**Files:**
- Create: `reels_api/static/cookie.js`
- Modify: `reels_api/static/app.html` (dialog before `#toast`)
- Modify: `reels_api/static/api.js` (after `logout`)
- Modify: `reels_api/static/app.js` (import; bottom of file)
- Modify: `reels_api/static/style.css` (after `.login-note`, in the login page block)
- Test: `tests/test_web.py:13` (`APP_MODULES`), new test after `test_board_has_log_out`

**Interfaces:**
- Consumes: `<body data-cookie="ask">` from Task 2; `POST /web/cookie` from Task 3; `POST /web/logout` and `logout()` in `api.js` (existing); `Unauthorized` and `api()` in `api.js` (existing); `set_unasked_cookie(client)` in `tests/test_web.py`.
- Produces:
  - `api.js`: `export async function agreeToCookie(): Promise<void>`, throws `Unauthorized` on 401 (after starting a reload) and `Error` on any other non-ok status.
  - `cookie.js`: `export function createCookieAsk({ dialog: HTMLDialogElement, onAccepted: () => void }): { open(): void }`.

- [ ] **Step 1: Write the failing tests in `tests/test_web.py`**

Change `APP_MODULES` (line 13) to:

```python
APP_MODULES = ["app.js", "api.js", "format.js", "icons.js", "board.js", "paste.js", "toast.js", "player.js", "watch.js", "cookie.js"]
```

After `test_board_has_log_out`, add:

```python
def test_board_has_the_cookie_pop_up(web_app):
    with https_client(web_app()) as client:
        set_unasked_cookie(client)
        page = client.get("/").text
    assert '<dialog id="cookie-ask" class="cookie-ask" aria-labelledby="cookie-ask-title">' in page
    assert "this site uses one cookie" in page
    for line in NOTICE_LINES:
        assert line in page, line
    assert ">allow cookie</button>" in page
    assert "no thanks, log me out" in page
    for element_id in ("cookie-ask-title", "cookie-allow", "cookie-error", "cookie-decline"):
        assert f'id="{element_id}"' in page, element_id
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest -q tests/test_web.py -k "cookie_pop_up or app_modules"`
Expected: FAIL. `test_board_has_the_cookie_pop_up` on the `<dialog` assertion; `test_app_modules_are_served` with `cookie.js` getting `404`.

- [ ] **Step 3: Add the dialog to `reels_api/static/app.html`**

Directly before the line `<div id="toast" class="toast" role="status" aria-live="polite"></div>`, add:

```html
<!-- Asks a phone whose cookie was set before the login page asked; cookie.js opens it (pop-up spec 6). -->
<dialog id="cookie-ask" class="cookie-ask" aria-labelledby="cookie-ask-title">
  <div class="login-step">
    <h2 id="cookie-ask-title" class="cookie-ask-title">this site uses one cookie</h2>
    <p class="login-note">one cookie keeps this phone logged in for a year.<br>nothing else is stored. no tracking, no ads.<br>you can log out from the board any time.</p>
    <button id="cookie-allow" class="btn btn-primary" type="button" autofocus>allow cookie</button>
    <p id="cookie-error" class="login-error" role="alert" hidden></p>
    <button id="cookie-decline" class="login-hint" type="button"><u>no thanks, log me out</u></button>
  </div>
</dialog>

```

`watch.html` is not changed.

- [ ] **Step 4: Style the dialog in `reels_api/static/style.css`**

Directly after the line `.login-note { font-size: 13px; line-height: 1.45; color: var(--ink-50); }`, add:

```css

/* ---- cookie pop-up on the board (pop-up spec 6.1) ---- */

.cookie-ask {
  width: min(340px, calc(100% - 32px));
  max-width: none;
  padding: 24px;
  border: 1px solid var(--hairline);
  border-radius: 20px;
  background: var(--surface);
  color: var(--ink);
}
.cookie-ask::backdrop { background: var(--scrim-overlay); }
.cookie-ask-title { margin: 0; font: 700 18px/1.25 var(--font); letter-spacing: -0.01em; color: var(--ink); }
.cookie-ask .login-hint { justify-content: flex-start; margin-top: 0; }
```

(`.cookie-ask .login-hint` outranks the later `.login-hint` rule by specificity, as `.login-box .login-hint` does.)

- [ ] **Step 5: Add `agreeToCookie()` to `reels_api/static/api.js`**

Directly after the `logout` function, add:

```js
// Marks this phone's login cookie as agreed (pop-up spec 5.2). A 401 means it is already gone; api() reloads.
export async function agreeToCookie() {
  const response = await api("/web/cookie", { method: "POST" });
  if (!response.ok) throw new Error(`POST /web/cookie failed: ${response.status}`);
}
```

Run: `node --check reels_api/static/api.js`
Expected: no output, exit 0.

- [ ] **Step 6: Create `reels_api/static/cookie.js`**

```js
import { Unauthorized, agreeToCookie, logout } from "./api.js";

// The same key and value as login.js, which is not a module and cannot import them. Keep them identical.
const CHOICE_KEY = "reels-cookie-choice";
const DECLINED = "declined";

// Storage throws in some private windows and when site data is blocked: then nothing is remembered.
function saveDeclined() {
  try {
    localStorage.setItem(CHOICE_KEY, DECLINED);
  } catch (_) {
    // the login page will ask instead of showing the declined state
  }
}

function forgetChoice() {
  try {
    localStorage.removeItem(CHOICE_KEY);
  } catch (_) {
    // nothing was saved
  }
}

// Asks a phone whose cookie was set before the login page asked (pop-up spec 6.2).
// It cannot be dismissed: the only ways out are "allow cookie" and "no thanks, log me out".
export function createCookieAsk({ dialog, onAccepted }) {
  const allow = dialog.querySelector("#cookie-allow");
  const decline = dialog.querySelector("#cookie-decline");
  const error = dialog.querySelector("#cookie-error");
  let agreed = false;

  function setBusy(busy) {
    allow.disabled = busy;
    decline.disabled = busy;
    if (busy) error.hidden = true;
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
    setBusy(false);
  }

  dialog.addEventListener("cancel", (event) => event.preventDefault()); // Esc
  // Chrome still closes a modal dialog on a repeated Esc; open it again until the person agrees.
  dialog.addEventListener("close", () => {
    if (!agreed) dialog.showModal();
  });

  allow.addEventListener("click", async () => {
    setBusy(true);
    try {
      await agreeToCookie();
    } catch (err) {
      if (err instanceof Unauthorized) return; // api() is already reloading
      showError("couldn't save that. try again.");
      return;
    }
    agreed = true;
    dialog.close();
    onAccepted();
  });

  decline.addEventListener("click", async () => {
    setBusy(true);
    saveDeclined(); // first, so a reload after a 401 still lands on the declined state
    try {
      await logout();
    } catch (err) {
      if (err instanceof Unauthorized) return; // api() is already reloading
      forgetChoice(); // the cookie is still there, so no "no" was given
      showError("couldn't log out. try again.");
      return;
    }
    location.replace("/"); // the login page there shows the declined state (cookie spec 4.2)
  });

  return {
    open() {
      dialog.showModal();
    },
  };
}
```

Run: `node --check reels_api/static/cookie.js`
Expected: no output, exit 0.

- [ ] **Step 7: Hold back `start()` in `reels_api/static/app.js`**

After the line `import { createBoard } from "./board.js";`, add:

```js
import { createCookieAsk } from "./cookie.js";
```

Replace the bottom of the file, from `setInterval(() => {` through the final `start();`:

```js
setInterval(() => {
  if (document.visibilityState === "visible") refresh();
}, REFRESH_MS);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refresh();
});

async function start() {
  await refresh();
  if (consumeShareTarget()) return;
  const id = reelInUrl();
  if (id) openLinkedReel(id);
}

start();
```

with:

```js
// Runs once the page may use the cookie: at load, or after "allow cookie" (pop-up spec 6.2).
async function start() {
  setInterval(() => {
    if (document.visibilityState === "visible") refresh();
  }, REFRESH_MS);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") refresh();
  });
  await refresh();
  if (consumeShareTarget()) return;
  const id = reelInUrl();
  if (id) openLinkedReel(id);
}

// A cookie set before the login page asked: nothing loads, not even the pile, until the person agrees.
if (document.body.dataset.cookie === "ask") {
  createCookieAsk({ dialog: $("cookie-ask"), onAccepted: start }).open();
} else {
  start();
}
```

Run: `node --check reels_api/static/app.js`
Expected: no output, exit 0.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 236 passed, 1 deselected.

- [ ] **Step 9: Quick manual check**

Start the dev server (Global Constraints; restart it if it was running, because Tasks 1–3 changed Python). In Chrome at 390×844:

1. Use the old cookie. The pop-up shows over an empty board, the Network tab has no `/jobs` request, and the paste bar behind it cannot be tapped.
2. Press Esc twice: it stays up.
3. **allow cookie**: the pop-up closes and the pile loads. Reload: no pop-up.

If any of these fails, fix it before committing.

- [ ] **Step 10: Commit**

```bash
git add reels_api/static/cookie.js reels_api/static/app.html reels_api/static/app.js reels_api/static/api.js reels_api/static/style.css tests/test_web.py
git commit -m "feat: cookie pop-up on the board for phones that never agreed" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Docs

**Files:**
- Modify: `README.md` ("Getting in" paragraph, "Trying the board" section)
- Modify: `CLAUDE.md` (Commands, Auth, `GET /`, Frontend, Things we learned → Web page)
- Modify: `docs/superpowers/specs/2026-09-17-cookie-consent-design.md` (section 3)
- Modify: `docs/superpowers/specs/2026-09-17-invite-and-share-links-design.md` (5.1)

**Interfaces:**
- Consumes: the behaviour of Tasks 1–4.
- Produces: nothing code depends on.

- [ ] **Step 1: README, "Getting in"**

In `README.md`, replace the paragraph:

```markdown
**Getting in.** Set `INVITE_TOKEN` and pin `https://<site>/join/<token>` in
the group. Opening it explains the login cookie, and "allow cookie & join"
logs the phone in with nothing to type. The passcode still works as the
fallback, behind the same notice ("allow cookie & log in"). "no thanks" is
remembered in that browser only (`localStorage`), and shared reels still
open without the cookie. The login cookie lasts a year and is the only
cookie the page sets; "log out" at the bottom of the board deletes it on
that phone only. Changing `INVITE_TOKEN` stops the old link but keeps
everyone logged in; changing `API_KEY` or `WEB_PASSCODE` logs everyone out.
Ten wrong passcodes or invite tokens from one IP block it for up to 15
minutes. No page loads anything from another site: the font is served from
`reels_api/static/fonts/`.
```

with:

```markdown
**Getting in.** Set `INVITE_TOKEN` and pin `https://<site>/join/<token>` in
the group. Opening it explains the login cookie, and "allow cookie & join"
logs the phone in with nothing to type. The passcode still works as the
fallback, behind the same notice ("allow cookie & log in"). "no thanks" is
remembered in that browser only (`localStorage`), and shared reels still
open without the cookie. The login cookie lasts a year and is the only
cookie the page sets; "log out" at the bottom of the board deletes it on
that phone only. A phone that was logged in before the page asked gets a
pop-up on the board instead: "allow cookie" keeps it logged in and the
pop-up stops, "no thanks, log me out" logs that phone out. Shared reels
open on it without answering. Changing `INVITE_TOKEN` stops the old link
but keeps everyone logged in; changing `API_KEY` or `WEB_PASSCODE` logs
everyone out. Ten wrong passcodes or invite tokens from one IP block it for
up to 15 minutes. No page loads anything from another site: the font is
served from `reels_api/static/fonts/`.
```

- [ ] **Step 2: README, dev board**

In `README.md`, replace:

```markdown
On start it also prints an invite link and the newest reel's share link.
Open them in a private window to see what someone without the cookie sees.
```

with:

```markdown
On start it also prints an invite link and the newest reel's share link.
Open them in a private window to see what someone without the cookie sees.
It also prints an old cookie value: log in, paste it over the
`reels_session` value in DevTools (Application → Cookies) and reload to see
the cookie pop-up on the board.
```

- [ ] **Step 3: CLAUDE.md, Commands**

Replace:

```markdown
and prints an invite link and a share link (open those in a private window).
```

with:

```markdown
and prints an invite link and a share link (open those in a private window) and an old cookie value (paste it over `reels_session` in DevTools to see the cookie pop-up).
```

- [ ] **Step 4: CLAUDE.md, Auth**

Replace:

```markdown
The cookie value is one shared HMAC of `API_KEY` + `WEB_PASSCODE`, so there are no per-user sessions and changing either secret logs everyone out.
```

with:

```markdown
The cookie value is a shared HMAC of `API_KEY` + `WEB_PASSCODE`, so there are no per-user sessions and changing either secret logs everyone out. It has two values that both log in (`session_state`): *agreed*, which every login sets, and *unasked*, the value from before the login page asked. An unasked cookie gets a pop-up on the board it can't dismiss (`cookie.js`); "allow cookie" calls `POST /web/cookie`, which re-sets the agreed value, and "no thanks, log me out" logs out and saves the "no" (pop-up spec, `docs/superpowers/specs/2026-09-17-cookie-ask-on-board-design.md`).
```

In the same paragraph, replace `` `web.install(app)` (login, logout, `/`, `/join`, manifest, `/sw.js`, `/static`) `` with `` `web.install(app)` (login, logout, `/web/cookie`, `/`, `/join`, manifest, `/sw.js`, `/static`) ``.

- [ ] **Step 5: CLAUDE.md, `GET /`**

Replace:

```markdown
**`GET /` decides the page** (`web.index`, links spec 5.1): valid cookie → `app.html`; no `reel`+`k` → login; unknown reel → expired page; wrong key → login (deliberately the same as no key); reel not done or file gone → expired page; otherwise the view-only page. The view-only and expired pages are rendered by `pages.py` from `static/watch.html` and `static/expired.html`:
```

with:

```markdown
**`GET /` decides the page** (`web.index`, pop-up spec 4): agreed cookie → the board; no `reel`+`k` → login; unknown reel → expired page; wrong key → login (deliberately the same as no key); reel not done or file gone → expired page; otherwise the view-only page. Wherever it would serve login, an unasked cookie gets the board with `data-cookie="ask"` instead, so share links behave as without a cookie. The board, view-only and expired pages are rendered by `pages.py` from `static/app.html`, `static/watch.html` and `static/expired.html`:
```

- [ ] **Step 6: CLAUDE.md, Frontend**

Replace:

```markdown
`app.html` loads `app.js`, which wires `board.js`, `paste.js` and `player.js` together with callbacks. Those three never import each other;
```

with:

```markdown
`app.html` loads `app.js`, which wires `board.js`, `paste.js`, `player.js` and `cookie.js` together with callbacks. Those four never import each other;
```

- [ ] **Step 7: CLAUDE.md, Things we learned → Web page**

After the bullet that starts `- **The design handoff**`, add:

```markdown
- **`app.html` goes through `pages.fill`** (for `data-cookie`), so any other `{{name}}` in it raises `KeyError`.
- **`reels-cookie-choice` is spelled out twice**, in `login.js` (not a module, so it can't import) and `cookie.js`. Keep the key and the `declined` value identical.
```

- [ ] **Step 8: Spec pointers**

In `docs/superpowers/specs/2026-09-17-cookie-consent-design.md`, replace:

```markdown
access logs, remembering a "yes" before logging in, the server checking
consent, logging out other phones.
```

with:

```markdown
access logs, remembering a "yes" before logging in, the server checking
consent, logging out other phones. *(The server now tells an agreed cookie
from an older one: `2026-09-17-cookie-ask-on-board-design.md`.)*
```

In the same file, replace:

```markdown
- People already logged in when this ships keep their cookie. Nobody is
  logged out by the deploy.
```

with:

```markdown
- People already logged in when this ships keep their cookie. Nobody is
  logged out by the deploy. *(They are now asked on the board:
  `2026-09-17-cookie-ask-on-board-design.md`.)*
```

In `docs/superpowers/specs/2026-09-17-invite-and-share-links-design.md`, replace:

```markdown
### 5.1 `GET /`

Checked in order.
```

with:

```markdown
### 5.1 `GET /`

*(Superseded by `2026-09-17-cookie-ask-on-board-design.md` section 4: only
an agreed cookie gets the board in row 1, and in rows 2 and 4 a cookie set
before the login page asked gets the board with the cookie pop-up.)*

Checked in order.
```

- [ ] **Step 9: Commit**

```bash
git add README.md CLAUDE.md docs/superpowers/specs/2026-09-17-cookie-consent-design.md docs/superpowers/specs/2026-09-17-invite-and-share-links-design.md
git commit -m "docs: cookie pop-up on the board in README and CLAUDE.md" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: End-to-end check (pop-up spec 9.2)

**Files:** none, unless a check fails. Fix a failure in the file it points to, add a test when the failure is testable in pytest, and commit it as `fix: <what>`.

**Interfaces:**
- Consumes: everything above.
- Produces: a checked build ready for `.\scripts\deploy.ps1`.

- [ ] **Step 1: Full suite and syntax**

Run: `.venv/Scripts/python.exe -m pytest -q && for f in reels_api/static/*.js; do node --check "$f" || echo "FAIL $f"; done`
Expected: 236 passed, 1 deselected; no `FAIL` lines.

- [ ] **Step 2: Walk through spec 9.2**

Start the dev server (Global Constraints). At 390×844 and again at 1280×800:

1. Use the old cookie. The pop-up shows over an empty board; DevTools Network has no `/jobs` request. Esc twice leaves it up. Reload: still up.
2. **allow cookie**: the pile loads, and after 30 seconds it refreshes (a `/jobs` request). `reels_session` now has a different value. Reload: no pop-up.
3. Use the old cookie. Open the printed share link: view-only page, no pop-up. Open `/?reel=seed00` (no `k`): pop-up; after **allow cookie** that reel opens muted.
4. Use the old cookie. **no thanks, log me out**: login page in the declined state ("no cookie, no login"), no `reels_session` in DevTools. The printed share link still opens the view-only page.
5. Use the old cookie. DevTools Network → Offline. **allow cookie** shows "couldn't save that. try again." inside the pop-up and both buttons work again; **no thanks, log me out** shows "couldn't log out. try again." Back online, reload: the pop-up is still there, and `localStorage` has no `reels-cookie-choice`.
6. In a private window, log in with `dev`: no pop-up.

`docker stop reels-dev` when done.

- [ ] **Step 3: Report**

State which checks passed, and list any `fix:` commits made. Deploying (`.\scripts\deploy.ps1`) and the real-device checks in spec 9.3 are for the owner.
