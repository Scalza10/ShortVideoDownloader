# Cookie Consent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ask before the login cookie is set, remember a "no" in the browser, let people log out from the board, and stop loading the font from Google.

**Architecture:** The login page (`login.html` + `login.js`, a non-module script) gets two states, asking and declined, and an invite mode picked from the URL path. A "yes" is the existing `reels_session` cookie; a "no" is `localStorage["reels-cookie-choice"] = "declined"` and never reaches the server. `GET /join/{token}` stops setting the cookie and serves the login page; a new `POST /join/{token}` sets it. A new `POST /web/logout` deletes it, called from a footer on the board. Bricolage Grotesque moves into `reels_api/static/fonts/`.

**Tech Stack:** Python 3.12, FastAPI, pytest (existing); plain HTML, CSS and JS; Node 22 only for `node --check`; Docker for the manual checks (the dev server needs ffmpeg).

**Spec:** `docs/superpowers/specs/2026-09-17-cookie-consent-design.md` (the "cookie spec"). Read it first; this plan argues from it. It builds on `2026-09-16-mobile-web-page-design.md` (the "web spec") and `2026-09-17-invite-and-share-links-design.md` (the "links spec").

## Global Constraints

- No new Python or JS dependencies. No build step, no framework, no JS test harness.
- Automated tests run with no network and no ffmpeg: `.venv/Scripts/python.exe -m pytest -q` from the repo root (Git Bash) or `.venv\Scripts\python.exe -m pytest -q` (PowerShell). The suite is green (209 passed, 1 deselected) before Task 1.
- JS syntax check after every JS edit: `node --check reels_api/static/<file>.js`.
- Storage key `reels-cookie-choice`, value `declined`. Every `localStorage` access is inside `try`/`catch`.
- Toggle visibility with `el.hidden` (`style.css` has `[hidden] { display: none !important; }`).
- The session cookie keeps its value and attributes: `max_age=31536000`, `path="/"`, `secure=True`, `httponly=True`, `samesite="lax"`. It is deleted with the same path, secure, httponly and samesite.
- No `GET` ever sets the session cookie.
- Every response from `GET /join/{token}` and `POST /join/{token}` sends `Cache-Control: no-store`.
- Error bodies, exactly: `{"error": "invalid_invite", "message": "That invite link is not right."}`, `{"error": "too_many_attempts", "message": "Too many wrong tries. Wait 15 minutes and try again."}`, `{"error": "unauthorized", "message": "Missing or invalid API key."}`.
- UI copy, exactly (lowercase):
  - notice: `one cookie keeps this phone logged in for a year.` / `nothing else is stored. no tracking, no ads.` / `you can log out from the board any time.`
  - `enter the passcode`, `allow cookie & log in`, `no thanks`
  - `no cookie, no login`, `reels friends share with you still open without one.`, `changed my mind`
  - `you're invited`, `allow cookie & join`
  - footer: `one cookie keeps you logged in`, `·`, `log out`; log out error toast: `couldn't log out. try again.`
- No page requests anything from another origin.
- Every commit message ends with a second `-m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"`.
- ffmpeg is not installed locally. Manual checks use the dev server in Docker and Chrome at 390×844 (DevTools device mode, touch) and 1280×800. Build the image once (`docker build -t reels-dev .`), then run it from the repo root in PowerShell:

  ```powershell
  docker run --rm --name reels-dev -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app `
    -v "${PWD}/reels_api:/app/reels_api:ro" -v "${PWD}/scripts:/app/scripts:ro" `
    reels-dev python scripts/dev_board.py --host 0.0.0.0
  ```

  Static file edits show up on reload; Python edits need `docker stop reels-dev` and a new `docker run`. Add `--empty` after `dev_board.py` for an empty pile. It prints the invite link (`http://localhost:8000/join/dev-invite-token-0000`) and a share link. "Fresh visitor" below means: DevTools → Application → Storage → **Clear site data** for `localhost:8000`, then reload.

## File map

| file | change | responsibility |
|------|--------|----------------|
| `reels_api/static/fonts/bricolage-grotesque-latin.woff2` | create | font, Latin |
| `reels_api/static/fonts/bricolage-grotesque-latin-ext.woff2` | create | font, Latin Extended |
| `reels_api/static/fonts/OFL.txt` | create | font license |
| `.gitattributes` | create | keep woff2 files binary through `git archive` (deploy) |
| `reels_api/web.py` | modify | forced content types; `GET`/`POST /join/{token}`; `POST /web/logout`; cookie attribute constant |
| `reels_api/static/style.css` | modify | `@font-face`; `.login-step`, `.login-note`; `.board-foot` and the empty-board layout |
| `reels_api/static/login.html` | modify | `#ask` / `#declined` sections, notice, buttons; no Google Fonts |
| `reels_api/static/login.js` | modify | states, invite mode, saved choice |
| `reels_api/static/app.html` | modify | board footer; no Google Fonts |
| `reels_api/static/app.js` | modify | log out button |
| `reels_api/static/api.js` | modify | `logout()` |
| `reels_api/static/watch.html` | modify | no Google Fonts |
| `reels_api/static/expired.html` | modify | `.login-note`; no Google Fonts |
| `tests/test_web.py` | modify | per task |
| `README.md`, `CLAUDE.md` | modify | document the feature (Task 5) |
| `docs/superpowers/specs/2026-09-16-mobile-web-page-design.md`, `2026-09-17-invite-and-share-links-design.md` | modify | pointers to the cookie spec (Task 5) |

Deviation from the cookie spec 4.4: it asks for a `button.login-hint` rule. The base `button` rule in `style.css` already removes background, border and padding and sets `cursor: pointer`, and `.login-hint` sets the font and colour, so no new rule is needed. Spec 6 asks the footer to stay clear of the paste bar on the empty board; Task 4 does that by making the empty board a flex column.

---

### Task 1: Serve the font from the app

**Files:**
- Create: `reels_api/static/fonts/bricolage-grotesque-latin.woff2`, `reels_api/static/fonts/bricolage-grotesque-latin-ext.woff2`, `reels_api/static/fonts/OFL.txt`, `.gitattributes`
- Modify: `reels_api/web.py:71-81` (`NoCacheStaticFiles`)
- Modify: `reels_api/static/style.css:1-3` (top of file)
- Modify: `reels_api/static/app.html:17-19`, `login.html:14-16`, `watch.html:17-19`, `expired.html:14-16`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `web.FORCED_CONTENT_TYPES: dict[str, str]` (suffix → Content-Type). Font URLs `/static/fonts/bricolage-grotesque-latin.woff2` and `/static/fonts/bricolage-grotesque-latin-ext.woff2`. Test constant `FONT_FILES` in `tests/test_web.py`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web.py`, below the `APP_MODULES = [...]` line, add:

```python
FONT_FILES = ["bricolage-grotesque-latin.woff2", "bricolage-grotesque-latin-ext.woff2"]
GOOGLE_FONT_HOSTS = ("fonts.googleapis.com", "fonts.gstatic.com")
```

Below `test_app_modules_are_served`, add:

```python
def test_font_files_are_served(web_app):
    with TestClient(web_app()) as client:
        for name in FONT_FILES:
            r = client.get(f"/static/fonts/{name}")
            assert r.status_code == 200, name
            assert r.headers["content-type"] == "font/woff2", name
            assert r.headers["cache-control"] == "no-cache", name
            assert r.content[:4] == b"wOF2", name
        license_text = client.get("/static/fonts/OFL.txt")
        assert license_text.status_code == 200
        assert "SIL OPEN FONT LICENSE" in license_text.text.upper()
        css = client.get("/static/style.css").text
    for name in FONT_FILES:
        assert f'url("/static/fonts/{name}") format("woff2")' in css, name


def test_no_page_loads_google_fonts(web_app):
    with https_client(web_app()) as client:
        reel = _done_reel(client)
        pages = {
            "login": client.get("/").text,
            "view-only": client.get("/", params={"reel": reel["id"], "k": reel["share_key"]}).text,
            "expired": client.get("/", params={"reel": "nope", "k": "x"}).text,
        }
        client.post("/web/login", json={"passcode": PASSCODE})
        pages["board"] = client.get("/").text
    assert 'id="reel-data"' in pages["view-only"]
    assert "this reel has expired" in pages["expired"]
    assert 'id="grid"' in pages["board"]
    for name, page in pages.items():
        for host in GOOGLE_FONT_HOSTS:
            assert host not in page, (name, host)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py -q -k "font"`
Expected: 2 failed. `test_font_files_are_served` gets 404 for the font; `test_no_page_loads_google_fonts` finds `fonts.googleapis.com` in the login page.

- [ ] **Step 3: Download the font files**

From the repo root in Git Bash:

```bash
mkdir -p reels_api/static/fonts
curl -fsSL -o reels_api/static/fonts/bricolage-grotesque-latin.woff2 \
  "https://fonts.gstatic.com/s/bricolagegrotesque/v9/3y9K6as8bTXq_nANBjzKo3IeZx8z6up5BeSl9D4dj_x9PpZBMlGIInE.woff2"
curl -fsSL -o reels_api/static/fonts/bricolage-grotesque-latin-ext.woff2 \
  "https://fonts.gstatic.com/s/bricolagegrotesque/v9/3y9K6as8bTXq_nANBjzKo3IeZx8z6up5BeSl9D4dj_x9PpZBMlGGInHEVA.woff2"
curl -fsSL -o reels_api/static/fonts/OFL.txt \
  "https://raw.githubusercontent.com/google/fonts/main/ofl/bricolagegrotesque/OFL.txt"
wc -c reels_api/static/fonts/*
head -c 4 reels_api/static/fonts/bricolage-grotesque-latin.woff2; echo
```

Expected: the latin file is 76888 bytes, latin-ext 30736 bytes, `OFL.txt` a few KB, and the first four bytes print `wOF2`.

If a gstatic URL returns 404 (Google bumped the version), get the current URLs from the CSS and use the `/* latin */` and `/* latin-ext */` `src` URLs (every weight lists the same file per character set):

```bash
curl -s -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36" \
  "https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700;12..96,800&display=swap"
```

Create `.gitattributes` in the repo root:

```
*.woff2 binary
```

- [ ] **Step 4: Force the woff2 content type**

In `reels_api/web.py`, replace:

```python
class NoCacheStaticFiles(StaticFiles):
    """StaticFiles that asks browsers to revalidate on every load (ETag makes that cheap)."""

    def file_response(self, full_path, *args, **kwargs) -> Response:
        response = super().file_response(full_path, *args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        if str(full_path).endswith(".js"):
            # mimetypes may say application/javascript (Windows registry); be the same everywhere.
            response.headers["Content-Type"] = "text/javascript; charset=utf-8"
        return response
```

with:

```python
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
```

Add `from pathlib import PurePath` to the imports at the top of `web.py`, after `import time`:

```python
import secrets
import time
from pathlib import PurePath
from typing import Callable
```

- [ ] **Step 5: Add the font faces**

In `reels_api/static/style.css`, replace:

```css
/* reels. Design values: design_handoff_reels_dump/README.md, "Design tokens". */

:root {
```

with:

```css
/* reels. Design values: design_handoff_reels_dump/README.md, "Design tokens". */

/* Bricolage Grotesque, served from here rather than Google Fonts so no page sends the visitor's
   IP address to another site (cookie spec 7). Variable font (opsz, wght); files and unicode
   ranges as Google serves them. License: fonts/OFL.txt. */
@font-face {
  font-family: "Bricolage Grotesque";
  font-style: normal;
  font-weight: 400 800;
  font-display: swap;
  src: url("/static/fonts/bricolage-grotesque-latin-ext.woff2") format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}
@font-face {
  font-family: "Bricolage Grotesque";
  font-style: normal;
  font-weight: 400 800;
  font-display: swap;
  src: url("/static/fonts/bricolage-grotesque-latin.woff2") format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD;
}

:root {
```

If Step 3 had to take new URLs from Google's CSS, copy the `unicode-range` values from that response instead.

- [ ] **Step 6: Remove Google Fonts from the four pages**

In each of `reels_api/static/app.html`, `login.html`, `watch.html` and `expired.html`, delete these three lines (identical in all four files):

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700;12..96,800&amp;display=swap">
```

Then confirm nothing is left:

Run: `grep -rn "fonts.g" reels_api/`
Expected: no output.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 211 passed, 1 deselected.

- [ ] **Step 8: Check it by hand**

Build the image and start the dev server (Global Constraints). In Chrome at `http://localhost:8000/`:

1. The login page wordmark and text render in Bricolage Grotesque: DevTools → Elements → select the `h1` → Computed → **Rendered Fonts** shows `Bricolage Grotesque` (network resource).
2. DevTools → Network, reload with "Disable cache" on: every request goes to `localhost:8000`. The font request is `bricolage-grotesque-latin.woff2`, type `font/woff2`.
3. Log in with `dev`: the board looks as before (wordmark 700 weight, captions). Open the printed share link: same font, no request to another host.

`docker stop reels-dev` when done.

- [ ] **Step 9: Commit**

```bash
git add .gitattributes reels_api/static/fonts reels_api/web.py reels_api/static/style.css \
  reels_api/static/app.html reels_api/static/login.html reels_api/static/watch.html \
  reels_api/static/expired.html tests/test_web.py
git commit -m "feat: serve the font from the app instead of Google Fonts" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Login page asks before setting the cookie

**Files:**
- Modify: `reels_api/static/login.html` (body)
- Modify: `reels_api/static/login.js` (whole file)
- Modify: `reels_api/static/style.css` (login page section, view-only section)
- Modify: `reels_api/static/expired.html` (`.expired-note` → `.login-note`)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `POST /web/login` (unchanged).
- Produces: element ids `ask`, `declined`, `login-lead`, `login-form`, `passcode`, `continue`, `login-error`, `decline`, `reconsider`. CSS classes `.login-step`, `.login-note`. Invite mode in `login.js`: when `location.pathname` starts with `/join/`, the form sends `POST <location.pathname>` with no body and expects `204`, or an error body with `message` (Task 3 adds that route). Test constant `NOTICE_LINES` in `tests/test_web.py`.

- [ ] **Step 1: Write the failing test**

In `tests/test_web.py`, below `GOOGLE_FONT_HOSTS`, add:

```python
NOTICE_LINES = (
    "one cookie keeps this phone logged in for a year.",
    "nothing else is stored. no tracking, no ads.",
    "you can log out from the board any time.",
)
```

Below `test_index_ignores_bad_cookie`, add:

```python
def test_login_page_asks_before_the_cookie(web_app):
    with TestClient(web_app()) as client:
        page = client.get("/").text
    for line in NOTICE_LINES:
        assert line in page, line
    assert "allow cookie &amp; log in" in page
    assert "no thanks" in page
    assert "no cookie, no login" in page
    assert "changed my mind" in page
    for element_id in ("ask", "declined", "login-lead", "decline", "reconsider"):
        assert f'id="{element_id}"' in page, element_id
    assert "autofocus" not in page
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py::test_login_page_asks_before_the_cookie -q`
Expected: FAIL on the first notice line.

- [ ] **Step 3: Replace the login page body**

In `reels_api/static/login.html`, replace:

```html
<main class="login-box">
  <h1 class="wordmark">reels</h1>
  <p class="login-lead">enter the passcode</p>
  <form id="login-form" class="login-form" autocomplete="off">
    <input id="passcode" class="field" type="password" autocomplete="current-password" placeholder="passcode" aria-label="passcode" required autofocus>
    <button id="continue" class="btn btn-primary" type="submit">continue</button>
    <p id="login-error" class="login-error" role="alert" hidden></p>
  </form>
</main>
```

with:

```html
<!-- Asks before the one cookie is set; login.js picks the state and the invite mode (cookie spec 4). -->
<main class="login-box">
  <h1 class="wordmark">reels</h1>
  <section id="ask" class="login-step">
    <p id="login-lead" class="login-lead">enter the passcode</p>
    <form id="login-form" class="login-form" autocomplete="off">
      <input id="passcode" class="field" type="password" autocomplete="current-password" placeholder="passcode" aria-label="passcode" required>
      <p class="login-note">one cookie keeps this phone logged in for a year.<br>nothing else is stored. no tracking, no ads.<br>you can log out from the board any time.</p>
      <button id="continue" class="btn btn-primary" type="submit">allow cookie &amp; log in</button>
      <p id="login-error" class="login-error" role="alert" hidden></p>
      <button id="decline" class="login-hint" type="button"><u>no thanks</u></button>
    </form>
  </section>
  <section id="declined" class="login-step" hidden>
    <p class="login-lead">no cookie, no login</p>
    <p class="login-note">reels friends share with you still open without one.</p>
    <button id="reconsider" class="login-hint" type="button"><u>changed my mind</u></button>
  </section>
</main>
```

- [ ] **Step 4: Replace `login.js`**

Replace the whole of `reels_api/static/login.js` with:

```js
(() => {
  "use strict";
  // Asks before the one cookie is set (cookie spec 4). A "yes" is the login cookie itself;
  // a "no" is remembered in this browser only and never sent to the server.
  const CHOICE_KEY = "reels-cookie-choice";
  const DECLINED = "declined";
  const GENERIC_ERROR = "Something went wrong. Try again.";
  const $ = (id) => document.getElementById(id);
  const ask = $("ask");
  const declined = $("declined");
  const lead = $("login-lead");
  const form = $("login-form");
  const input = $("passcode");
  const button = $("continue");
  const error = $("login-error");
  // The server only serves this page at /join/<token> for the right token (cookie spec 5.1).
  const inviteMode = location.pathname.startsWith("/join/");

  // Storage throws in some private windows and when site data is blocked: then nothing is remembered.
  function savedChoice() {
    try {
      return localStorage.getItem(CHOICE_KEY);
    } catch (_) {
      return null;
    }
  }

  function saveDeclined() {
    try {
      localStorage.setItem(CHOICE_KEY, DECLINED);
    } catch (_) {
      // declined for this visit only
    }
  }

  function forgetChoice() {
    try {
      localStorage.removeItem(CHOICE_KEY);
    } catch (_) {
      // nothing was saved
    }
  }

  function showAsk() {
    declined.hidden = true;
    ask.hidden = false;
    if (!inviteMode) input.focus();
  }

  function showDeclined() {
    ask.hidden = true;
    declined.hidden = false;
  }

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
  }

  async function errorMessage(response) {
    try {
      return (await response.json()).message || GENERIC_ERROR;
    } catch (_) {
      return GENERIC_ERROR; // non-JSON body
    }
  }

  function sendAgreement() {
    if (inviteMode) return fetch(location.pathname, { method: "POST" });
    return fetch("/web/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ passcode: input.value }),
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    button.disabled = true;
    try {
      const r = await sendAgreement();
      if (r.status === 204) {
        forgetChoice();
        if (inviteMode) {
          location.replace("/"); // the token leaves the address bar and the history entry
        } else {
          location.reload(); // keeps the query string, so a shared link still starts after login
        }
        return;
      }
      showError(await errorMessage(r));
    } catch (_) {
      showError("Network error. Try again.");
    } finally {
      button.disabled = false;
    }
  });

  $("decline").addEventListener("click", () => {
    saveDeclined();
    if (inviteMode) {
      location.replace("/"); // the login page there shows the declined state
    } else {
      showDeclined();
    }
  });

  $("reconsider").addEventListener("click", () => {
    forgetChoice();
    showAsk();
  });

  if (inviteMode) {
    // Opening an invite link is a fresh request: always ask, even after an earlier "no".
    lead.textContent = "you're invited";
    button.textContent = "allow cookie & join";
    input.hidden = true;
    input.disabled = true; // a disabled field is skipped by form validation
    showAsk();
  } else if (savedChoice() === DECLINED) {
    showDeclined();
  } else {
    showAsk();
  }
})();
```

Run: `node --check reels_api/static/login.js`
Expected: no output.

- [ ] **Step 5: Styles**

In `reels_api/static/style.css`, replace:

```css
.login-form .btn { width: 100%; }
.btn:disabled { opacity: 0.6; }
.login-error { font: 500 12.5px var(--font); color: var(--danger-text); }
```

with:

```css
.login-form .btn { width: 100%; }
.btn:disabled { opacity: 0.6; }
.login-error { font: 500 12.5px var(--font); color: var(--danger-text); }
.login-step { display: flex; flex-direction: column; gap: 14px; }
.login-step .login-hint { align-self: flex-start; }
.login-note { font-size: 13px; line-height: 1.45; color: var(--ink-50); }
```

and replace:

```css
.login-box .login-hint { justify-content: flex-start; margin-top: 0; }
.expired-note { font-size: 13px; color: var(--ink-50); }
```

with:

```css
.login-box .login-hint { justify-content: flex-start; margin-top: 0; }
```

In `reels_api/static/expired.html`, replace:

```html
  <p class="expired-note">reels only stay up for {{hours}}</p>
```

with:

```html
  <p class="login-note">reels only stay up for {{hours}}</p>
```

Run: `grep -rn "expired-note" reels_api/`
Expected: no output.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 212 passed, 1 deselected.

- [ ] **Step 7: Check it by hand**

Start the dev server (Global Constraints). In Chrome at 390×844, as a fresh visitor, at `http://localhost:8000/`:

1. The page shows, top to bottom: `reels`, `enter the passcode`, the passcode field (focused on desktop), the three notice lines, the `allow cookie & log in` button, `no thanks` (underlined, left-aligned). DevTools → Application → Cookies: none.
2. Tap `no thanks` → `no cookie, no login`, `reels friends share with you still open without one.`, `changed my mind`. Application → Local Storage → `reels-cookie-choice` = `declined`. Still no cookies.
3. Reload → still declined.
4. Tap `changed my mind` → asking state, `reels-cookie-choice` gone.
5. Type `wrong` and tap the button → `That passcode is not right.` under the button, above `no thanks`.
6. Type `dev`, press Enter → the board. Cookie `reels_session` present; `reels-cookie-choice` absent.
7. Fresh visitor, `no thanks`, then open the printed share link → view-only page, no notice. Its `have the passcode? log in` link → `/?reel=…` showing the declined state.
8. `/?reel=nope&k=x` → expired page, `reels only stay up for 12 hours` looks as before (13px, dim).
9. Repeat 1–2 at 1280×800.

`docker stop reels-dev` when done.

- [ ] **Step 8: Commit**

```bash
git add reels_api/static/login.html reels_api/static/login.js reels_api/static/style.css \
  reels_api/static/expired.html tests/test_web.py
git commit -m "feat: login page explains the cookie and remembers no thanks" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Invite link asks before setting the cookie

**Files:**
- Modify: `reels_api/web.py` (`login`, `join`, new `accept_invite`, `install`, new constants)
- Test: `tests/test_web.py` (the `# ---- GET /join/{token}` block)

**Interfaces:**
- Consumes: `login.html` invite mode from Task 2; `_login_page()`, `_set_session_cookie(response, settings)`, `_client_ip(request)`, `AttemptLimiter` in `web.py`; `session_is_valid(settings, cookie)` from `auth.py`.
- Produces: `GET /join/{token}` → `303` to `/` or `200` login page, never a cookie. `POST /join/{token}` → `204` + cookie, `401 invalid_invite`, `429 too_many_attempts`. Constants `web.TOO_MANY_ATTEMPTS` and `web.INVALID_INVITE` (error body dicts).

- [ ] **Step 1: Write the failing tests**

In `tests/test_web.py`, replace everything from the line `# ---- GET /join/{token}` down to (not including) the line `# ---- GET / with a share link (links spec 5.1)` with:

```python
# ---- GET /join/{token}: asks first, never sets the cookie (cookie spec 5.1)

def test_join_with_right_token_shows_invite_page_without_cookie(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        r = client.get(f"/join/{INVITE}", follow_redirects=False)
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        assert r.headers["cache-control"] == "no-store"
        assert 'id="login-form"' in r.text
        assert "set-cookie" not in r.headers
        assert client.get("/jobs").status_code == 401


def test_join_with_cookie_goes_to_board_without_counting(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        for _ in range(10):
            r = client.get("/join/wrong", follow_redirects=False)
            assert r.status_code == 303
            assert r.headers["location"] == "/"
            assert r.headers["cache-control"] == "no-store"
        client.cookies.clear()
        assert client.post("/web/login", json={"passcode": PASSCODE}).status_code == 204   # not blocked


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
        assert r.headers["location"] == "/"
        assert "set-cookie" not in r.headers


def test_join_page_does_not_clear_counter(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(9):
            client.post("/join/wrong")
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 200
        client.post("/join/wrong")
        assert client.post(f"/join/{INVITE}").status_code == 429


# ---- POST /join/{token}: allow cookie & join (cookie spec 5.2)

def test_accept_invite_with_right_token_sets_cookie(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        r = client.post(f"/join/{INVITE}")
        assert r.status_code == 204
        assert r.content == b""
        assert r.headers["cache-control"] == "no-store"
        cookie = r.headers["set-cookie"]
        assert cookie.startswith(f"{SESSION_COOKIE}={session_cookie_value(client.app.state.settings)};")
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=31536000"):
            assert attr in lowered, attr
        assert client.get("/jobs").status_code == 200


def test_accept_invite_with_wrong_token(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        r = client.post("/join/wrong-token-0123456789")
        assert r.status_code == 401
        assert r.json() == {"error": "invalid_invite", "message": "That invite link is not right."}
        assert r.headers["cache-control"] == "no-store"
        assert "set-cookie" not in r.headers


def test_accept_invite_blocked_after_ten_wrong_tokens(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(10):
            assert client.post("/join/wrong").status_code == 401
        r = client.post(f"/join/{INVITE}")                   # right token, still blocked
        assert r.status_code == 429
        assert r.json() == {
            "error": "too_many_attempts",
            "message": "Too many wrong tries. Wait 15 minutes and try again.",
        }
        assert r.headers["cache-control"] == "no-store"
        assert "set-cookie" not in r.headers


def test_accept_invite_clears_counter(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(9):
            client.post("/join/wrong")
        assert client.post(f"/join/{INVITE}").status_code == 204
        client.cookies.clear()
        for _ in range(9):
            assert client.post("/join/wrong").status_code == 401


def test_wrong_passcodes_and_wrong_tokens_share_one_limit(web_app):
    with https_client(web_app(invite_token=INVITE)) as client:
        for _ in range(3):
            client.post("/web/login", json={"passcode": "nope"})
            client.get("/join/wrong", follow_redirects=False)
            client.post("/join/wrong")
        client.post("/web/login", json={"passcode": "nope"})                          # tenth failure
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 303
        assert client.post("/web/login", json={"passcode": PASSCODE}).status_code == 429


def test_join_404_without_invite_token(web_app):
    with TestClient(web_app()) as client:
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 404
        assert client.post(f"/join/{INVITE}").status_code == 404


def test_join_404_when_web_disabled(tmp_path):
    settings = make_settings(tmp_path, invite_token=INVITE)
    app = create_app(settings=settings, pipeline=FakePipeline(settings))
    with TestClient(app) as client:
        assert client.get(f"/join/{INVITE}", follow_redirects=False).status_code == 404
        assert client.post(f"/join/{INVITE}").status_code == 404


```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py -q -k "join or invite or share_one_limit"`
Expected: failures. `test_join_with_right_token_shows_invite_page_without_cookie` gets `303`; the `POST /join` tests get `405`.

- [ ] **Step 3: Implement the routes**

In `reels_api/web.py`, below `NO_STORE = {"Cache-Control": "no-store"}`, add:

```python
TOO_MANY_ATTEMPTS = {"error": "too_many_attempts", "message": "Too many wrong tries. Wait 15 minutes and try again."}
INVALID_INVITE = {"error": "invalid_invite", "message": "That invite link is not right."}
```

In `login`, replace:

```python
    if limiter.is_blocked(ip):
        raise HTTPException(
            status_code=429,
            detail={"error": "too_many_attempts", "message": "Too many wrong tries. Wait 15 minutes and try again."},
        )
```

with:

```python
    if limiter.is_blocked(ip):
        raise HTTPException(status_code=429, detail=TOO_MANY_ATTEMPTS)
```

Replace the whole `join` function:

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

with:

```python
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
```

In `install`, replace:

```python
    if app.state.settings.invite_token:
        app.add_api_route("/join/{token}", join, methods=["GET"], include_in_schema=False)
```

with:

```python
    if app.state.settings.invite_token:
        app.add_api_route("/join/{token}", join, methods=["GET"], include_in_schema=False)
        app.add_api_route("/join/{token}", accept_invite, methods=["POST"], include_in_schema=False)
```

The error handler in `main.py` passes `exc.headers` through, so the `401` and `429` keep `no-store`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 218 passed, 1 deselected.

- [ ] **Step 5: Check it by hand**

Start the dev server (Global Constraints). In Chrome at 390×844, as a fresh visitor:

1. Open `http://localhost:8000/join/dev-invite-token-0000` → `reels`, `you're invited`, the three notice lines, `allow cookie & join`, `no thanks`. No passcode field, no cookies.
2. Tap `allow cookie & join` → the board. Address bar `http://localhost:8000/`. Cookie `reels_session` present. Browser Back does not show the invite page.
3. Open the invite link again while logged in → straight to the board.
4. Fresh visitor. On `/` tap `no thanks`. Open the invite link → it asks (not declined). Tap `no thanks` → `/` in the declined state, address bar `/`, no cookie.
5. Fresh visitor. Open `/join/dev-invite-token-0000`, then in the DevTools console run `history.replaceState(null, "", "/join/wrong")` and tap `allow cookie & join` → `That invite link is not right.` under the button, no cookie.
6. `http://localhost:8000/join/wrong` → the login page at `/` (asking state).

`docker stop reels-dev` when done.

- [ ] **Step 6: Commit**

```bash
git add reels_api/web.py tests/test_web.py
git commit -m "feat: invite link asks before setting the cookie" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Log out from the board

**Files:**
- Modify: `reels_api/web.py` (cookie attribute constant, `_set_session_cookie`, new `logout` route, imports)
- Modify: `reels_api/static/api.js` (new `logout`)
- Modify: `reels_api/static/app.js` (import, click handler)
- Modify: `reels_api/static/app.html` (footer)
- Modify: `reels_api/static/style.css` (board and empty-pile sections, desktop board block)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `require_access` from `auth.py`; `api(path, options)`, `Unauthorized` from `api.js`; `showToast(message, { error })` from `toast.js`.
- Produces: `POST /web/logout` → `204` deleting `reels_session`, or `401 unauthorized`. `export async function logout(): Promise<void>` in `api.js` (throws on a non-2xx other than 401; on 401 `api()` reloads and throws `Unauthorized`). `web.SESSION_COOKIE_ATTRS: dict`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_web.py`, below `test_login_success_clears_counter`, add:

```python
# ---- POST /web/logout (cookie spec 5.3)

def test_logout_deletes_the_cookie(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        r = client.post("/web/logout")
        assert r.status_code == 204
        cookie = r.headers["set-cookie"]
        assert cookie.startswith(f'{SESSION_COOKIE}="";')
        lowered = cookie.lower()
        for attr in ("httponly", "secure", "samesite=lax", "path=/", "max-age=0"):
            assert attr in lowered, attr
        assert _is_login(client.get("/"))
        assert client.get("/jobs").status_code == 401


def test_logout_without_cookie_is_401(web_app):
    with https_client(web_app()) as client:
        r = client.post("/web/logout")
        assert r.status_code == 401
        assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}
        assert "set-cookie" not in r.headers


def test_board_has_log_out(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        page = client.get("/").text
    assert '<footer class="board-foot">' in page
    assert "one cookie keeps you logged in" in page
    assert 'id="logout"' in page
```

In `test_web_disabled_when_passcode_unset`, replace:

```python
        assert client.post("/web/login", json={"passcode": "x"}).status_code == 404
```

with:

```python
        assert client.post("/web/login", json={"passcode": "x"}).status_code == 404
        assert client.post("/web/logout").status_code == 404
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py -q -k "logout or log_out or disabled"`
Expected: 3 failed. `test_logout_deletes_the_cookie` gets 404 instead of 204, `test_logout_without_cookie_is_401` gets 404 instead of 401, and `test_board_has_log_out` finds no footer. `test_web_disabled_when_passcode_unset` already passes.

- [ ] **Step 3: Implement the route**

In `reels_api/web.py`, change the imports:

```python
from fastapi import APIRouter, FastAPI, HTTPException, Request, Response
```

to:

```python
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
```

and:

```python
from reels_api.auth import SESSION_COOKIE, session_cookie_value, session_is_valid, share_key_matches
```

to:

```python
from reels_api.auth import SESSION_COOKIE, require_access, session_cookie_value, session_is_valid, share_key_matches
```

Below `COOKIE_MAX_AGE_SECONDS = 365 * 24 * 3600`, add:

```python
# Set and deleted with the same attributes; a different path would leave the cookie in place.
SESSION_COOKIE_ATTRS = {"path": "/", "secure": True, "httponly": True, "samesite": "lax"}
```

Replace `_set_session_cookie`:

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

with:

```python
def _set_session_cookie(response: Response, settings) -> None:
    """The one login cookie, set by the passcode form and by the invite link."""
    response.set_cookie(
        SESSION_COOKIE,
        session_cookie_value(settings),
        max_age=COOKIE_MAX_AGE_SECONDS,
        **SESSION_COOKIE_ATTRS,
    )
```

Directly below the `login` function, add:

```python
@router.post("/web/logout", status_code=204, dependencies=[Depends(require_access)])
async def logout(response: Response) -> None:
    """Deletes this phone's login cookie (cookie spec 5.3).

    The cookie value is shared, so other phones stay logged in. Requiring access means a
    cross-site POST, which carries no SameSite=Lax cookie, gets 401 and deletes nothing.
    """
    response.delete_cookie(SESSION_COOKIE, **SESSION_COOKIE_ATTRS)
```

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py -q -k "logout"`
Expected: 2 passed.

- [ ] **Step 4: Add the footer**

In `reels_api/static/app.html`, replace:

```html
  <div id="empty" class="empty" hidden>
    <span class="empty-box" data-icon="clipboardPlus"></span>
    <p class="empty-title">the pile is empty</p>
    <p class="empty-body">paste something in and it shows up for everyone.</p>
  </div>
</main>
```

with:

```html
  <div id="empty" class="empty" hidden>
    <span class="empty-box" data-icon="clipboardPlus"></span>
    <p class="empty-title">the pile is empty</p>
    <p class="empty-body">paste something in and it shows up for everyone.</p>
  </div>
  <footer class="board-foot">
    <span>one cookie keeps you logged in</span>
    <span aria-hidden="true">·</span>
    <button id="logout" class="login-hint" type="button"><u>log out</u></button>
  </footer>
</main>
```

In `reels_api/static/api.js`, after the `api` function, add:

```js
// Deletes this phone's login cookie (cookie spec 5.3). A 401 means it is already gone; api() reloads.
export async function logout() {
  const response = await api("/web/logout", { method: "POST" });
  if (!response.ok) throw new Error(`POST /web/logout failed: ${response.status}`);
}
```

In `reels_api/static/app.js`, replace:

```js
import { Unauthorized, getJob, listJobs } from "./api.js";
```

with:

```js
import { Unauthorized, getJob, listJobs, logout } from "./api.js";
```

and replace:

```js
setInterval(() => {
  if (document.visibilityState === "visible") refresh();
}, REFRESH_MS);
```

with:

```js
// Log out deletes the cookie; the login page then asks again (cookie spec 6).
const logoutButton = $("logout");
logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  try {
    await logout();
    location.replace("/");
  } catch (err) {
    if (err instanceof Unauthorized) return; // api() is already reloading
    logoutButton.disabled = false;
    showToast("couldn't log out. try again.", { error: true });
  }
});

setInterval(() => {
  if (document.visibilityState === "visible") refresh();
}, REFRESH_MS);
```

Run: `node --check reels_api/static/api.js && node --check reels_api/static/app.js`
Expected: no output.

- [ ] **Step 5: Styles**

In `reels_api/static/style.css`, replace:

```css
body.is-empty .board { padding-bottom: 0; }
```

with:

```css
/* Empty pile: the board fills the window so the footer sits just above the paste bar. */
body.is-empty .board {
  display: flex;
  flex-direction: column;
  min-height: calc(100dvh - var(--header-h) - env(safe-area-inset-top));
  padding-bottom: calc(var(--paste-bar) + env(safe-area-inset-bottom));
}
```

Replace:

```css
.empty-body { font: 400 14px/1.45 var(--font); color: rgba(242, 240, 234, 0.55); }
```

with:

```css
.empty-body { font: 400 14px/1.45 var(--font); color: rgba(242, 240, 234, 0.55); }
body.is-empty .empty { flex: 1; min-height: 0; padding-bottom: 0; }

/* ---- log out (cookie spec 6) ---- */

.board-foot {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 24px;
  font: 500 12.5px var(--font);
  color: var(--ink-50);
}
.board-foot .login-hint { margin-top: 0; }
body.is-empty .board-foot { margin-top: 0; }
```

In the desktop block (`@media (min-width: 700px)` that starts with `.topbar {`), replace:

```css
  body.is-empty .board { padding: 0 28px; }
```

with:

```css
  body.is-empty .board { min-height: calc(100dvh - 75px); padding: 0 28px 24px; }
```

and replace:

```css
  .empty { min-height: calc(100dvh - 75px); padding: 0 40px 75px; }
```

with:

```css
  .empty { min-height: calc(100dvh - 75px); padding: 0 40px 75px; }
  /* 75px minus the 36px footer and the board's 24px: the message stays centred in the window. */
  body.is-empty .empty { min-height: 0; padding-bottom: 15px; }
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 221 passed, 1 deselected.

- [ ] **Step 7: Check it by hand**

Start the dev server (Global Constraints), log in with `dev`.

1. 390×844, 12 reels: scroll to the bottom. `one cookie keeps you logged in · log out` is centred below the grid and fully above the paste bar; nothing overlaps it.
2. 1280×800: the footer is centred below the grid.
3. Tap `log out` → the login page in the asking state. DevTools → Application → Cookies: no `reels_session`. Back → the login page again (`/` is `no-store`).
4. Log in again. DevTools → Network → set **Offline**, tap `log out` → toast `couldn't log out. try again.`, the button works again. Set **No throttling**.
5. `docker stop reels-dev`, start again with `--empty`, log in: at 390×844 the empty message is centred, the footer sits just above the paste field with no scrolling needed, and `log out` is tappable. At 1280×800 the empty message is centred in the window and the footer is at the bottom without scrolling.
6. Paste a link on the empty board (`https://vm.tiktok.com/abc/`): once the reel lands, the board switches to the grid layout and the footer moves below the grid.

`docker stop reels-dev` when done.

- [ ] **Step 8: Commit**

```bash
git add reels_api/web.py reels_api/static/api.js reels_api/static/app.js reels_api/static/app.html \
  reels_api/static/style.css tests/test_web.py
git commit -m "feat: log out from the board" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Docs

**Files:**
- Modify: `README.md` ("Getting in" paragraph)
- Modify: `CLAUDE.md` (Commands, Auth, Frontend, Things we learned)
- Modify: `docs/superpowers/specs/2026-09-16-mobile-web-page-design.md:114`
- Modify: `docs/superpowers/specs/2026-09-17-invite-and-share-links-design.md` (5.4, 13)

**Interfaces:**
- Consumes: the behaviour of Tasks 1–4.
- Produces: nothing code depends on.

- [ ] **Step 1: README**

In `README.md`, replace the paragraph:

```markdown
**Getting in.** Set `INVITE_TOKEN` and pin `https://<site>/join/<token>` in
the group: tapping it logs a phone in with nothing to type. The passcode
still works as the fallback. The login cookie lasts a year. Changing
`INVITE_TOKEN` stops the old link but keeps everyone logged in; changing
`API_KEY` or `WEB_PASSCODE` logs everyone out. Ten wrong passcodes or invite
tokens from one IP block it for up to 15 minutes.
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
that phone only. Changing `INVITE_TOKEN` stops the old link but keeps
everyone logged in; changing `API_KEY` or `WEB_PASSCODE` logs everyone out.
Ten wrong passcodes or invite tokens from one IP block it for up to 15
minutes. No page loads anything from another site: the font is served from
`reels_api/static/fonts/`.
```

- [ ] **Step 2: CLAUDE.md**

In `CLAUDE.md`, replace:

```markdown
.venv\Scripts\python.exe -m pytest                                  # all unit tests (~165, a few seconds)
```

with:

```markdown
.venv\Scripts\python.exe -m pytest                                  # all unit tests (~220, a few seconds)
```

Replace:

```markdown
Two ways to get the cookie: the passcode form (`POST /web/login`) and the invite link `GET /join/<INVITE_TOKEN>`; both share one per-IP attempt limiter. `web.install(app)` (login, `/`, `/join`, manifest, `/sw.js`, `/static`) is only called when `WEB_PASSCODE` is set; otherwise those routes 404.
```

with:

```markdown
Two ways to get the cookie, both only after the person agrees on the login page (cookie spec, `docs/superpowers/specs/2026-09-17-cookie-consent-design.md`): the passcode form (`POST /web/login`, button "allow cookie & log in") and the invite link, where `GET /join/<INVITE_TOKEN>` only serves the login page in invite mode and `POST /join/<INVITE_TOKEN>` sets the cookie. Both share one per-IP attempt limiter. **A GET must never set the cookie** (WhatsApp's preview fetcher GETs invite links). "no thanks" is kept in `localStorage["reels-cookie-choice"]` and never reaches the server; a "yes" is the cookie itself. `POST /web/logout` deletes the cookie on that phone only (the value is shared, so nobody else is logged out). `web.install(app)` (login, logout, `/`, `/join`, manifest, `/sw.js`, `/static`) is only called when `WEB_PASSCODE` is set; otherwise those routes 404.
```

Replace:

```markdown
`login.html`/`login.js` are a separate non-module page.
```

with:

```markdown
`login.html`/`login.js` are a separate non-module page with two states (asking, declined) and an invite mode picked from the `/join/` path. The board's footer holds log out.
```

Replace:

```markdown
- **`.js` must be served as `text/javascript`.** On Windows, `mimetypes` can say `application/javascript` from the registry. `NoCacheStaticFiles` forces the header, and `test_web.py` asserts it for every module in `APP_MODULES`. **Add new modules to that list.**
```

with:

```markdown
- **`.js` must be served as `text/javascript`, `.woff2` as `font/woff2`.** On Windows, `mimetypes` can say `application/javascript` from the registry, and Python 3.12 knows no type for `.woff2`. `NoCacheStaticFiles` forces both (`FORCED_CONTENT_TYPES`), and `test_web.py` asserts it for every module in `APP_MODULES` and every font in `FONT_FILES`. **Add new modules to that list.**
- **No requests to other sites.** The font is self-hosted in `static/fonts/` because a Google Fonts request sends every visitor's IP address to Google (GDPR). `test_no_page_loads_google_fonts` guards the font hosts; keep scripts, styles and fonts in `static/`.
```

- [ ] **Step 3: Pointers in the earlier specs**

In `docs/superpowers/specs/2026-09-16-mobile-web-page-design.md`, replace:

```markdown
There is no logout endpoint. Clearing site data on the phone logs out.
```

with:

```markdown
There is no logout endpoint. Clearing site data on the phone logs out.
*(Superseded: `POST /web/logout` and a log out link on the board delete the
cookie, see `2026-09-17-cookie-consent-design.md` 5.3 and 6.)*
```

In `docs/superpowers/specs/2026-09-17-invite-and-share-links-design.md`, replace:

```markdown
### 5.4 `GET /join/{token}`

```

with:

```markdown
### 5.4 `GET /join/{token}`

*(Superseded by `2026-09-17-cookie-consent-design.md` 5.1 and 5.2: `GET`
serves the login page in invite mode and never sets the cookie;
`POST /join/{token}` sets it.)*

```

and replace:

```markdown
- The referrer policy keeps the key out of requests to Google Fonts.
```

with:

```markdown
- The referrer policy keeps the key out of requests to Google Fonts.
  *(The font is now served by the app, cookie spec 7, so no page makes
  such requests.)*
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 221 passed, 1 deselected.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md docs/superpowers/specs/2026-09-16-mobile-web-page-design.md \
  docs/superpowers/specs/2026-09-17-invite-and-share-links-design.md
git commit -m "docs: cookie notice, invite link and log out in README and CLAUDE.md" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: End-to-end check (cookie spec 9.2)

**Files:** none, unless a check fails. Fix a failure in the file it points to, add a test when the failure is testable in pytest, and commit it as `fix: <what>`.

**Interfaces:**
- Consumes: everything above.
- Produces: a checked build ready for `.\scripts\deploy.ps1`.

- [ ] **Step 1: Full suite and syntax**

Run: `.venv/Scripts/python.exe -m pytest -q && for f in reels_api/static/*.js; do node --check "$f" || echo "FAIL $f"; done`
Expected: 221 passed, 1 deselected; no `FAIL` lines.

- [ ] **Step 2: Walk through spec 9.2**

Start the dev server (Global Constraints). As a fresh visitor, at 390×844 and again at 1280×800:

1. `/` asks. `no thanks` → declined. Reload → still declined. `changed my mind` → asks, passcode field focused (desktop).
2. Log in with `dev` → board. The footer is at the end of the grid. `log out` → login page asking; no `reels_session` in DevTools.
3. Restart with `--empty`, log in: the footer is visible without scrolling and clear of the paste bar. Restart without `--empty`.
4. Fresh visitor, the printed invite link → invite mode, no passcode field, no cookie. `allow cookie & join` → board, address bar `/`, Back does not return to the invite page.
5. Fresh visitor, `no thanks` on `/`, then the invite link → it asks. `no thanks` → `/` in the declined state.
6. Fresh visitor, the printed share link → view-only page with no notice; Save still downloads.
7. On the login page, the invite page, the board, the view-only page and the expired page (`/?reel=nope&k=x`): DevTools → Network with "Disable cache" shows only `localhost:8000` requests, and the text renders in Bricolage Grotesque.

`docker stop reels-dev` when done.

- [ ] **Step 3: Report**

State which checks passed, and list any `fix:` commits made. Deploying (`.\scripts\deploy.ps1`) and the real-device checks in spec 9.3 are for the owner.
