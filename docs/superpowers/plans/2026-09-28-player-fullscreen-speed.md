# Tap to Pause, Fullscreen and Speed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In both players (board and view-only page), a phone tap pauses and shows the options (tap again plays and hides them) with a ▶ while paused, a fullscreen button fills the screen (turning a wide reel sideways on Android, Apple's player on iPhone), and a speed button steps 1x → 1.5x → 2x.

**Architecture:** Page only; the server and the API don't change. All behaviour goes into `player.js`, which both pages already run. Markup goes into the player block of `app.html` and is mirrored into `watch.html`. Visual state is classes on the player root (`is-paused`, `is-fullscreen`), styled in `style.css`. Fullscreen targets `.player-stage` (the frame plus the desktop controls row) with the Fullscreen API, or falls back to `video.webkitEnterFullscreen()` on iPhone.

**Tech Stack:** plain HTML/CSS/ES modules (no build, no framework, no JS tests); pytest for the page markup; Node 22 only for `node --check` syntax checks.

**Spec:** `docs/superpowers/specs/2026-09-28-player-fullscreen-speed-design.md`

## Global Constraints

- **Page text, exactly:**
  - idle hint on the board: `swipe for the next one · tap to pause`; on the view-only page: `tap to pause`;
  - speed button text `1x` / `1.5x` / `2x`, `aria-label` `speed 1x` / `speed 1.5x` / `speed 2x`;
  - fullscreen button `aria-label` `fullscreen`, or `exit fullscreen` while fullscreen.
- **Speeds are exactly `[1, 1.5, 2]`**, stepped in that order and wrapping. They carry from reel to reel while the page is open, and a reload starts at 1x.
- **The player markup exists in both `app.html` and `watch.html`.** Every markup change is made in both, identically.
- **Layout switches at 700px.** A phone turned sideways is over 700px wide and gets the desktop layout, inside fullscreen too. **Crossing 700px must never leave fullscreen.**
- **Only a user gesture may enter fullscreen.** There is no automatic fullscreen on rotation.
- **No new JS modules, dependencies or requests to other sites.** `APP_MODULES` in `tests/test_web.py` does not change.
- **`app.html` goes through `pages.fill`,** so it must contain no `{{` in new markup. `watch.html` has its own placeholders; add none.
- **`[hidden]` is `display: none !important`** in `style.css`; JS hides the fullscreen button with `el.hidden`.
- **Running things:**
  - Tests: `.venv/Scripts/python.exe -m pytest` (Git Bash) or `.venv\Scripts\python.exe -m pytest` (PowerShell). ffmpeg is not installed locally. The suite is 402 passed, 1 deselected before this plan.
  - JS syntax: `node --check reels_api/static/<file>.js`.
- **Commits** are prefixed `feat:` or `docs:` and end with the `Co-Authored-By` line given in the session.

## Review Focus

- **A phone turned sideways while fullscreen stays fullscreen.** Android's landscape lock makes the viewport cross 700px; nothing on that path may call `exitFullscreen()`. Owned by Task 3 (manual check step).
- **A pause the viewer didn't make shows the ▶.** Examples: a refused autoplay (iPhone Low Power Mode), a phone call, the lock screen. `is-paused` must come from the video's own `play`/`pause` events and the `play()` rejections, not from the tap. Owned by Task 1 (manual check step).
- **Speed survives moving to another reel.** Setting `video.src` resets `playbackRate` to `defaultPlaybackRate`, so both must be set after `src`. Owned by Task 2 (manual check step).
- **Esc in desktop fullscreen leaves fullscreen but not the player.** Owned by Task 3 (manual check step).
- **A covered NSFW reel:** a tap uncovers it, no ▶ shows while covered, and entering fullscreen doesn't start it. Owned by Tasks 1 and 3 (manual check steps).

---

## Manual checks: how to run the dev board

Tasks 1–3 end with manual checks in the real page. Build and run the dev board in Docker (PowerShell, from the repo root; the mounts make edits in `reels_api/static` show up on reload):

```powershell
docker build -t reels-dev .
docker run --rm -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app `
  -v "${PWD}/reels_api:/app/reels_api:ro" -v "${PWD}/scripts:/app/scripts:ro" `
  reels-dev python scripts/dev_board.py --host 0.0.0.0
```

- **Logging in:** open `http://localhost:8000/` in Chrome and log in with `dev`.
- **Phone layout:** DevTools device toolbar (e.g. "Pixel 7", touch emulation on), portrait. Rotating the device in the toolbar makes the width cross 700px.
- **Seeds to use:** 9:16, 16:9, 3:4 and 1:1 clips. Seed 3 is NSFW.
- **The view-only page:** the dev board prints a share link on start. Open it in a private window.
- **Real phones** (Android orientation lock, iPhone's Apple player) can't be emulated. List those checks for the user rather than claiming them.

---

### Task 1: Tap to pause and the ▶

**Files:**
- Modify: `reels_api/static/app.html` (player frame: after the `<video>`; the idle hint)
- Modify: `reels_api/static/watch.html` (the same two places)
- Modify: `reels_api/static/style.css` (after the `.player-frame video` rule, about line 609)
- Modify: `reels_api/static/player.js` (`setChrome`, `play`, `move`, the phone `pointerup`, the video listeners)
- Test: `tests/test_web.py`

**Interfaces:**
- Produces:
  - `_player_pages(web_app) -> dict[str, str]` in `tests/test_web.py`, with keys `"board"` and `"view-only"`. Tasks 2 and 3 use it.
  - `renderPaused()` inside `createPlayer`.
  - The `is-paused` class on the player root.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py`, after `test_board_player_has_the_star`:

```python
def _player_pages(web_app):
    # The board's player and the view-only page's copy of it (CLAUDE.md: mirror any change).
    with https_client(web_app()) as client:
        reel = _done_reel(client)
        view_only = client.get("/", params={"reel": reel["id"], "k": reel["share_key"]}).text
        client.post("/web/login", json={"passcode": PASSCODE})
        board = client.get("/").text
    assert 'id="reel-data"' in view_only and 'id="grid"' in board  # the pages we meant
    return {"board": board, "view-only": view_only}


def test_player_says_tap_to_pause(web_app):
    for name, page in _player_pages(web_app).items():
        assert "tap for options" not in page, name
        assert "tap to pause" in page, name
        assert page.count('<div class="play-hint" aria-hidden="true" data-icon="play"></div>') == 1, name
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py::test_player_says_tap_to_pause -v`
Expected: FAIL on `assert "tap for options" not in page, board`.

- [ ] **Step 3: Markup, in both pages**

In `reels_api/static/app.html` and in `reels_api/static/watch.html`, directly after
`<video playsinline loop preload="auto"></video>` add, at the same indentation:

```html
          <div class="play-hint" aria-hidden="true" data-icon="play"></div>
```

In `app.html`, change the idle hint to:

```html
            <p class="idle-hint"><span data-icon="arrowUp"></span>swipe for the next one · tap to pause</p>
```

In `watch.html`, change the idle hint to:

```html
            <p class="idle-hint">tap to pause</p>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py::test_player_says_tap_to_pause -v`
Expected: PASS

- [ ] **Step 5: Style the ▶**

In `reels_api/static/style.css`, directly after the rule
`.player-frame video { position: absolute; inset: 0; ... }` (the one with the "Never cropped" comment), add:

```css
/* The ▶ while paused (fullscreen spec 3.1). A picture only: a tap on it is a tap on the video. */
.play-hint {
  position: absolute;
  top: 50%;
  left: 50%;
  display: none;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  margin: -36px 0 0 -36px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.4);
  color: rgba(255, 255, 255, 0.92);
  pointer-events: none;
}
.play-hint .icon { width: 28px; height: 28px; margin-left: 4px; } /* the triangle looks centred */
.player.is-paused:not(.is-covered) .play-hint { display: flex; }
```

- [ ] **Step 6: `player.js`, add `renderPaused` and call it from `play()`**

In `reels_api/static/player.js`, directly after the `setChrome` function, add:

```js
  // The ▶ while paused (fullscreen spec 3.1). Read from the video, not the tap, so a pause from
  // elsewhere (a call, the lock screen, an autoplay refused even muted) shows it too.
  function renderPaused() {
    root.classList.toggle("is-paused", video.paused);
  }
```

Replace the whole `play` function with:

```js
  function play() {
    if (isCovered()) return; // an NSFW reel waits for a tap
    video.muted = muted;
    const attempt = video.play();
    renderPaused(); // now, not on the "play" event, so the ▶ never flashes between reels
    if (!attempt) return;
    attempt.catch((err) => {
      if (err.name !== "NotAllowedError" || video.muted) {
        renderPaused(); // refused even muted, or cut short: the ▶ offers a tap
        return;
      }
      // No sound allowed without a fresh tap: play muted and show it.
      muted = true;
      renderVolume();
      video.muted = true;
      video.play().catch(renderPaused);
    });
  }
```

- [ ] **Step 7: `player.js`, the phone tap, `move()` and the listeners**

Change the section comment
`// ---- phone: tap toggles the chrome, vertical swipes move through the pile (spec 7.2)` to:

```js
  // ---- phone: a tap pauses and shows the options, or plays and hides them (fullscreen spec 3.1);
  // vertical swipes move through the pile (spec 7.2)
```

In the `pointerup` handler, replace

```js
      if (isCovered()) uncover();
      else setChrome(!root.classList.contains("chrome-on"));
      return;
```

with

```js
      if (isCovered()) uncover();
      else if (video.paused) {
        play();
        setChrome(false);
      } else {
        video.pause();
        setChrome(true);
      }
      return;
```

In `move()`, directly after `play();`, add:

```js
    setChrome(false); // the next reel plays, so its options stay hidden (fullscreen spec 3.1)
```

Directly after the existing listener

```js
  video.addEventListener("play", () => {
    if (isCovered()) video.pause();
  });
```

add:

```js
  video.addEventListener("play", renderPaused);
  video.addEventListener("pause", renderPaused);
```

- [ ] **Step 8: Syntax check and the whole suite**

Run: `node --check reels_api/static/player.js && .venv/Scripts/python.exe -m pytest -q`
Expected: no output from node; `403 passed, 1 deselected`.

- [ ] **Step 9: Manual check** (dev board, see "Manual checks" above)

Phone layout (portrait):
- A tap pauses: the ▶ appears and the options show.
- A tap again plays: the ▶ and the options go.
- Pause, then swipe up: the next reel plays with no options and no ▶.
- Pause, then Copy link: the options hide, and the ▶ stays until a tap.
- The NSFW seed (3): a tap uncovers it, with no ▶ while it's covered.

Desktop:
- A click pauses with the ▶, and a click plays.

Autoplay refusal:
- In the console, run `document.querySelector("#player video").pause()` while a reel plays. The ▶ appears (a pause the viewer didn't make).

- [ ] **Step 10: Commit**

```bash
git add reels_api/static/app.html reels_api/static/watch.html reels_api/static/style.css reels_api/static/player.js tests/test_web.py
git commit -m "feat: a tap pauses the reel and shows the options, with a play icon while paused"
```

---

### Task 2: Speed button

**Files:**
- Modify: `reels_api/static/app.html` and `reels_api/static/watch.html` (both controls rows in each)
- Modify: `reels_api/static/style.css` (after `.volume .icon`, about line 697)
- Modify: `reels_api/static/player.js`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `_player_pages(web_app)` from Task 1.
- Produces:
  - `SPEEDS` (module constant).
  - `renderSpeed()` and `applySpeed()` inside `createPlayer`.
  - The `speed` action.
  - The `.speed` button, placed right after each `.volume` button. Task 3 inserts after it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_web.py`, after `test_player_says_tap_to_pause`:

```python
def test_player_has_the_speed_button(web_app):
    for name, page in _player_pages(web_app).items():
        assert page.count('data-action="speed"') == 2, name  # the phone's controls and the desktop row
        assert page.count('<button class="speed" type="button" data-action="speed" aria-label="speed 1x">1x</button>') == 2, name
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py::test_player_has_the_speed_button -v`
Expected: FAIL (`0 == 2`).

- [ ] **Step 3: Markup, four places**

`app.html` and `watch.html` each have two lines

```html
<button class="volume" type="button" data-action="volume" aria-label="mute"></button>
```

One is in `.chrome-bottom .controls`, the other in `.desk-controls`. Directly after each of the four, at the same indentation, add:

```html
<button class="speed" type="button" data-action="speed" aria-label="speed 1x">1x</button>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py::test_player_has_the_speed_button -v`
Expected: PASS

- [ ] **Step 5: Style**

In `reels_api/static/style.css`, directly after `.volume .icon { ... }`, add:

```css
/* 1x is quiet like the total time; a sped-up reel is obvious at a glance (fullscreen spec 3.4). */
.speed { flex: none; min-width: 34px; height: 28px; font: 500 11px var(--mono); color: var(--ink-70); font-variant-numeric: tabular-nums; }
.speed.is-fast { color: var(--accent-bright); }
```

- [ ] **Step 6: `player.js`**

After the `DELETE_GUARD_MS` constant (module top), add:

```js
// The speed button steps through these (fullscreen spec 3.4).
const SPEEDS = [1, 1.5, 2];
```

Inside `createPlayer`, directly after the `starButtons` line, add:

```js
  const speedButtons = [...root.querySelectorAll('[data-action="speed"]')];
```

After `let muted = false; // the viewer's choice carries from reel to reel`, add:

```js
  let speed = 0; // index into SPEEDS; carries from reel to reel like muted
```

Directly after the `renderVolume` function, add:

```js
  function renderSpeed() {
    const rate = SPEEDS[speed];
    for (const button of speedButtons) {
      button.textContent = `${rate}x`;
      button.setAttribute("aria-label", `speed ${rate}x`);
      button.classList.toggle("is-fast", rate !== 1);
    }
  }

  // Both rates: loading a new src resets playbackRate to defaultPlaybackRate.
  function applySpeed() {
    video.defaultPlaybackRate = SPEEDS[speed];
    video.playbackRate = SPEEDS[speed];
  }

  function nextSpeed() {
    speed = (speed + 1) % SPEEDS.length;
    applySpeed();
    renderSpeed();
  }
```

The other changes:
- In `show()`, directly after `video.src = reel.file_url;`, add `applySpeed();`.
- In `open()`, directly after `renderVolume();`, add `renderSpeed();`.
- In the `actions` object, after `volume: toggleMute,`, add `speed: nextSpeed,`.

- [ ] **Step 7: Syntax check and the whole suite**

Run: `node --check reels_api/static/player.js && .venv/Scripts/python.exe -m pytest -q`
Expected: `404 passed, 1 deselected`.

- [ ] **Step 8: Manual check** (dev board)

- **Stepping:** the button reads 1x (quiet), then 1.5x (highlighted), then 2x, then 1x. The video visibly speeds up.
- **Carrying:** at 2x, swipe to the next reel (phone) or press → (desktop). The new reel plays at 2x and the button says 2x.
- **Both rows:** in the phone layout it's in the options row; on desktop, in the row under the video.
- **Reload:** the page starts at 1x again.
- **The view-only link:** the button works the same.

- [ ] **Step 9: Commit**

```bash
git add reels_api/static/app.html reels_api/static/watch.html reels_api/static/style.css reels_api/static/player.js tests/test_web.py
git commit -m "feat: speed button in the player, 1x, 1.5x and 2x"
```

---

### Task 3: Fullscreen

**Files:**
- Modify: `reels_api/static/icons.js` (the `STROKE` map, after `link2`)
- Modify: `reels_api/static/app.html` and `reels_api/static/watch.html` (both controls rows in each)
- Modify: `reels_api/static/style.css` (new block before `/* ---- login page (spec 8.2) ---- */`, and the `.volume` rules)
- Modify: `reels_api/static/player.js`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes:
  - From Task 1: `_player_pages(web_app)`, `renderPaused()`, `play()` (refuses while covered).
  - From Task 2: the `.speed` buttons, after which the new buttons go.
- Produces:
  - The `fullscreen` action, `isFullscreen()`, `exitFullscreen()`.
  - The `is-fullscreen` class on the player root.
  - The `maximize` and `minimize` icons.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_web.py`, after `test_player_has_the_speed_button`:

```python
def test_player_has_the_fullscreen_button(web_app):
    for name, page in _player_pages(web_app).items():
        assert page.count('<button class="fullscreen" type="button" data-action="fullscreen" aria-label="fullscreen"></button>') == 2, name


def test_icons_has_maximize_and_minimize(web_app):
    # icon() throws on an unknown name, which would break the whole player.
    with TestClient(web_app()) as client:
        source = client.get("/static/icons.js").text
    assert "  maximize: '" in source
    assert "  minimize: '" in source
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py -k "fullscreen_button or maximize" -v`
Expected: both FAIL.

- [ ] **Step 3: Icons**

In `reels_api/static/icons.js`, in `STROKE`, directly after the `link2:` line, add (Lucide `maximize` and `minimize`):

```js
  maximize: '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
  minimize: '<path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/><path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/>',
```

- [ ] **Step 4: Markup, four places**

In `app.html` and `watch.html`, directly after each of the four
`<button class="speed" type="button" data-action="speed" aria-label="speed 1x">1x</button>` lines from Task 2, at the same indentation, add:

```html
<button class="fullscreen" type="button" data-action="fullscreen" aria-label="fullscreen"></button>
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py -k "fullscreen_button or maximize" -v`
Expected: both PASS.

- [ ] **Step 6: Style**

In `reels_api/static/style.css`, change the two `.volume` rules to cover the new button too:

```css
.volume, .fullscreen { display: flex; flex: none; align-items: center; justify-content: center; width: 28px; height: 28px; color: var(--ink); }
.volume .icon { width: 17px; height: 17px; stroke-width: 1.8; }
.fullscreen .icon { width: 16px; height: 16px; stroke-width: 1.8; }
```

Directly before `/* ---- login page (spec 8.2) ---- */`, add:

```css
/* ---- fullscreen (fullscreen spec 3.3, 4.2) ---- */

/* is-fullscreen comes from fullscreenchange, so :fullscreen and :-webkit-full-screen aren't both needed.
   The browser already makes the fullscreen stage fixed and full-size. */
.player.is-fullscreen .player-stage { background: #000; }
.player.is-fullscreen .idle-hint { display: none; } /* it talks about swiping, which is off */

/* A desktop, or a phone turned sideways: the video above the controls row. */
@media (min-width: 700px) {
  .player.is-fullscreen .player-stage {
    padding: env(safe-area-inset-top) calc(16px + env(safe-area-inset-right)) calc(12px + env(safe-area-inset-bottom))
      calc(16px + env(safe-area-inset-left));
  }
  .player.is-fullscreen .player-frame { flex: 1; width: 100%; height: auto; min-height: 0; border-radius: 0; background: #000; }
  .player.is-fullscreen .player-frame video { background: #000; }
}
```

- [ ] **Step 7: `player.js`: constants, elements, state, mode**

After the `SPEEDS` constant, add:

```js
// Esc leaves fullscreen, not the player; a browser may deliver the key just after leaving (fullscreen spec 3.3).
const FULLSCREEN_ESC_GUARD_MS = 500;
```

Inside `createPlayer`, directly after the `speedButtons` line, add:

```js
  const stage = root.querySelector(".player-stage");
  const fullscreenButtons = [...root.querySelectorAll('[data-action="fullscreen"]')];
  // Decided once. iPhone has no element fullscreen, only Apple's own player for a <video> (fullscreen spec 3.3).
  const fullscreenMode =
    document.fullscreenEnabled || document.webkitFullscreenEnabled
      ? "element"
      : typeof video.webkitEnterFullscreen === "function"
        ? "video"
        : null;
```

After `let speed = 0; ...`, add:

```js
  let fullscreenEndedAt = -Infinity; // performance.now() when fullscreen last ended, for FULLSCREEN_ESC_GUARD_MS
```

After `const isCovered = () => ...;`, add:

```js
  const isFullscreen = () => (document.fullscreenElement || document.webkitFullscreenElement) === stage;
```

- [ ] **Step 8: `player.js`, the fullscreen functions**

Directly after the `nextSpeed` function (Task 2), add:

```js
  function renderFullscreen() {
    const on = isFullscreen();
    root.classList.toggle("is-fullscreen", on);
    for (const button of fullscreenButtons) {
      button.hidden = !fullscreenMode;
      button.innerHTML = icon(on ? "minimize" : "maximize");
      button.setAttribute("aria-label", on ? "exit fullscreen" : "fullscreen");
    }
  }

  // The video's own size first; a rotated file can differ from the job's.
  function isWide() {
    const reel = current();
    const width = video.videoWidth || reel.width || 0;
    const height = video.videoHeight || reel.height || 0;
    return width > height;
  }

  // Fullscreen is for watching: it plays (a covered reel stays covered) and hides the options (fullscreen spec 3.3).
  async function enterFullscreen() {
    setChrome(false);
    play();
    if (fullscreenMode === "video") {
      try {
        video.webkitEnterFullscreen();
      } catch (_) {
        // not ready yet (InvalidStateError): the next tap works
      }
      return;
    }
    try {
      await (stage.requestFullscreen ? stage.requestFullscreen() : stage.webkitRequestFullscreen());
    } catch (_) {
      return; // refused: stay as we are
    }
    // A wide reel turns sideways. Desktops and many browsers refuse the lock; that's fine.
    if (isWide() && screen.orientation && typeof screen.orientation.lock === "function") {
      screen.orientation.lock("landscape").catch(() => {});
    }
  }

  function exitFullscreen() {
    if (!isFullscreen()) return;
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    Promise.resolve(exit.call(document)).catch(() => {});
  }

  function toggleFullscreen() {
    if (isFullscreen()) exitFullscreen();
    else enterFullscreen();
  }

  // Also runs when Esc or the system back gesture ends fullscreen. Crossing 700px never does.
  function onFullscreenChange() {
    const was = root.classList.contains("is-fullscreen");
    renderFullscreen();
    if (!was || isFullscreen()) return;
    fullscreenEndedAt = performance.now();
    try {
      screen.orientation.unlock();
    } catch (_) {
      // nothing was locked, or no Screen Orientation API
    }
  }
```

- [ ] **Step 9: `player.js`, wiring**

1. In `open()`, directly after `renderSpeed();`, add `renderFullscreen();`.
2. In `close()`, directly after `if (!isOpen()) return;`, add `exitFullscreen();`.
3. In the `actions` object, after `speed: nextSpeed,`, add `fullscreen: toggleFullscreen,`.
4. In the `pointermove` handler, change the guard to:

   ```js
       if (!drag || event.pointerId !== drag.id || standalone || isFullscreen()) return;
   ```

5. In the `pointerup` handler, change `if (standalone) return; // the frame never moved` to:

   ```js
       if (standalone || isFullscreen()) return; // the frame never moved; no swiping in fullscreen (fullscreen spec 3.3)
   ```

6. In the video `error` listener, directly after `if (!isOpen()) return;`, add `exitFullscreen();`.
7. In `trapFocus`, scope to the stage while fullscreen (the panel outside it is still laid out but not visible). Replace its first line and the `root.contains` check:

   ```js
     function trapFocus(event) {
       const scope = isFullscreen() ? stage : root;
       const focusable = [...scope.querySelectorAll("button, input")].filter(
         (el) => !el.disabled && el.getClientRects().length > 0,
       );
       if (!focusable.length) return;
       const first = focusable[0];
       const last = focusable[focusable.length - 1];
       if (!scope.contains(document.activeElement)) {
   ```

   The rest of the function is unchanged.
8. In the `keydown` listener, change the Escape branch to:

   ```js
       if (event.key === "Escape") {
         if (standalone) return;
         // Esc leaves fullscreen, not the player (fullscreen spec 3.3).
         if (isFullscreen() || performance.now() - fullscreenEndedAt < FULLSCREEN_ESC_GUARD_MS) return;
         event.preventDefault();
         close();
         return;
       }
   ```

9. Directly before `// Crossing 700px while open: ...`, add:

   ```js
     document.addEventListener("fullscreenchange", onFullscreenChange);
     document.addEventListener("webkitfullscreenchange", onFullscreenChange);
   ```

   Do **not** add `exitFullscreen()` to the 700px `change` handler. A phone turned sideways crosses 700px.

- [ ] **Step 10: Syntax check and the whole suite**

Run: `node --check reels_api/static/player.js && node --check reels_api/static/icons.js && .venv/Scripts/python.exe -m pytest -q`
Expected: `406 passed, 1 deselected`.

- [ ] **Step 11: Manual check** (dev board)

Desktop Chrome, 16:9 seed:
- The ⤢ button fills the screen, with the video above the controls row (time, scrubber, volume, speed, exit).
- A click pauses with the ▶.
- → moves to the next reel, still fullscreen.
- Esc leaves fullscreen and **the player stays open**. A second Esc closes it.

Desktop Chrome, closing while fullscreen:
- Enter fullscreen, then press the exit button. The icon goes back to ⤢.
- Enter fullscreen, then close with Esc twice. The page is not left fullscreen.

Phone layout, 9:16 seed:
- Tap to pause, then fullscreen: the reel plays with the options hidden.
- A tap pauses and shows the options with the exit button.
- Swiping does nothing.

Phone layout, rotating while fullscreen:
- With a reel fullscreen, rotate the emulated device to landscape. It **stays fullscreen** and switches to the video-above-controls layout.

NSFW seed (3):
- On desktop, fullscreen while covered: it stays covered and doesn't play.
- A click uncovers it.

The view-only link:
- Fullscreen works; there is no swiping.

For the user, on real phones (can't be emulated):
- **Android Chrome:** the 16:9 seed turns sideways and stays fullscreen, and exit turns back.
- **iPhone Safari:** fullscreen opens Apple's player at the chosen speed. Closing it comes back to our player, and a ▶ shows if it came back paused.

- [ ] **Step 12: Commit**

```bash
git add reels_api/static/icons.js reels_api/static/app.html reels_api/static/watch.html reels_api/static/style.css reels_api/static/player.js tests/test_web.py
git commit -m "feat: fullscreen button in the player; wide reels turn sideways on Android"
```

---

### Task 4: Docs

**Files:**
- Modify: `README.md` (the "**Play**" bullet, about line 122)
- Modify: `CLAUDE.md` ("Things we learned" → "Web page", and the "Frontend" paragraph)

**Interfaces:**
- Consumes: the finished behaviour of Tasks 1–3.

- [ ] **Step 1: README**

Replace the "**Play**" bullet in `README.md`:

```markdown
- **Play**: tap a reel. On a phone it fills the screen: swipe up or down
  for the next one, tap to pause, which also shows the caption and the
  Share, Save and copy-link buttons (tap again to play). On a desktop it
  opens as an overlay; click the video to pause, ← → move, Esc closes.
  Both have a speed button (1x, 1.5x, 2x, kept from reel to reel) and a
  fullscreen button. On Android a wide video turns the screen sideways;
  on iPhone fullscreen is Apple's own player.
```

- [ ] **Step 2: CLAUDE.md**

In the "Frontend" paragraph, directly after the sentence ending `…(\`board.getShown()\`).`, add:

```markdown
On a phone a tap on the video pauses it and shows the options, and a tap while paused plays and hides them; `is-paused` (the ▶) follows the video's own events, so a pause from elsewhere shows it too. The speed button (1x/1.5x/2x) and fullscreen are in both players (fullscreen spec, `docs/superpowers/specs/2026-09-28-player-fullscreen-speed-design.md`).
```

Under "Things we learned" → "### Web page", add a bullet at the end of that list:

```markdown
- **iPhone has no element fullscreen.** There, fullscreen is Apple's player (`video.webkitEnterFullscreen()`, Apple's controls); everywhere else `.player-stage` goes fullscreen and a wide reel asks for `screen.orientation.lock("landscape")`. A phone turned sideways is over 700px wide, so it gets the desktop layout, inside fullscreen too: **crossing 700px must never leave fullscreen**. Setting `video.src` resets `playbackRate`, so `show()` re-applies the speed (both `playbackRate` and `defaultPlaybackRate`).
```

- [ ] **Step 3: The whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: `406 passed, 1 deselected`.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: tap to pause, speed and fullscreen in README and CLAUDE.md"
```
