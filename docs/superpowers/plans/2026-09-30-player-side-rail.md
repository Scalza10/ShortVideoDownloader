# Side Rail for the Phone Player's Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On phones, move the player's volume, speed and fullscreen buttons out of the crowded controls row into a column on the right edge of the video, so a tap meant for one never hits another.

**Architecture:** Markup and CSS only. In both player copies (`app.html`, `watch.html`), the three buttons move from `.chrome-bottom .controls` into a new `.rail` inside a new `.chrome-meta` row next to the caption. `player.js` already redraws every copy of these buttons by `data-action`, so it doesn't change. The desktop row (`.desk-controls`) keeps its own copies.

**Tech Stack:** Plain HTML/CSS (no build step), pytest + FastAPI `TestClient` for markup tests.

**Spec:** `docs/superpowers/specs/2026-09-30-player-side-rail-design.md`

## Global Constraints

- Phones only (below 700px); `.desk-controls` and fullscreen from 700px unchanged.
- The player markup exists in both `app.html` and `watch.html`; mirror every change.
- No change to `player.js`, other modules, the server or the API.
- Button markup moves unchanged (same classes, `data-action`s, `aria-label`s); each page keeps exactly two volume, two speed and two fullscreen buttons.
- Rail order from the top: volume, speed, fullscreen. Circles 44px, gap 12px, background `rgba(0, 0, 0, 0.4)`.
- Commit prefixes `feat:` / `docs:`; run tests with `.venv\Scripts\python.exe -m pytest`.

## Review Focus

No JS/CSS tests exist in this project, so these are checked by hand in Task 2 Step 3:

- A long caption (two clamped lines) must wrap beside the rail, never under it.
- A reel with an empty caption must still show the rail on the right edge, not the left.
- A browser without fullscreen (button `hidden`) must show a two-circle rail with no gap where the third was.
- `1.5x` must fit inside the 44px speed circle and keep its accent colour.
- A phone turned sideways (over 700px) must show the desktop controls row, with no rail.

---

### Task 1: The rail (markup, styles, tests)

**Files:**
- Modify: `reels_api/static/app.html` (the `.chrome-bottom` block, around lines 105-118)
- Modify: `reels_api/static/watch.html` (the `.chrome-bottom` block, around lines 44-53)
- Modify: `reels_api/static/style.css` (after `.speed.is-fast`, around line 720)
- Test: `tests/test_web.py` (after `test_player_has_the_fullscreen_button`, around line 748)

**Interfaces:**
- Consumes: `_player_pages(web_app)` in `tests/test_web.py`, which returns `{"board": html, "view-only": html}`.
- Produces: classes `.chrome-meta` and `.rail`, used by the docs in Task 2.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_web.py` after `test_player_has_the_fullscreen_button`:

```python
def _between(page, start, end):
    # The markup from `start` up to the first `end` after it.
    i = page.index(start)
    return page[i:page.index(end, i)]


def test_phone_player_has_the_side_rail(web_app):
    # Volume, speed and fullscreen stack on the right of the video, so a tap can't hit a neighbour (side rail spec).
    for name, page in _player_pages(web_app).items():
        assert page.count('<div class="rail">') == 1, name
        rail = _between(page, '<div class="rail">', "</div>")
        assert rail.index('data-action="volume"') < rail.index('data-action="speed"') < rail.index('data-action="fullscreen"'), name


def test_phone_controls_row_is_only_the_scrubber(web_app):
    for name, page in _player_pages(web_app).items():
        chrome_bottom = page[page.index('<div class="chrome-bottom">'):]
        row = _between(chrome_bottom, '<div class="controls">', "</div>")
        assert 'class="scrubber"' in row, name
        assert "data-action" not in row, name
        desk = _between(page, '<div class="controls desk-controls">', "</div>")
        for action in ("volume", "speed", "fullscreen"):
            assert f'data-action="{action}"' in desk, (name, action)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py -k "side_rail or only_the_scrubber" -v`
Expected: both FAIL (`'<div class="rail">'` count is 0; the phone row contains `data-action`).

- [ ] **Step 3: Move the buttons in `app.html`**

Replace:

```html
            <div class="chrome-bottom">
              <p class="caption js-caption"></p>
              <div class="controls">
                <span class="time js-elapsed">0:00</span>
                <input class="scrubber" type="range" min="0" max="1" step="0.1" value="0" aria-label="seek">
                <span class="time total js-duration">0:00</span>
                <button class="volume" type="button" data-action="volume" aria-label="mute"></button>
                <button class="speed" type="button" data-action="speed" aria-label="speed 1x">1x</button>
                <button class="fullscreen" type="button" data-action="fullscreen" aria-label="fullscreen"></button>
              </div>
```

with:

```html
            <div class="chrome-bottom">
              <div class="chrome-meta">
                <p class="caption js-caption"></p>
                <div class="rail">
                  <button class="volume" type="button" data-action="volume" aria-label="mute"></button>
                  <button class="speed" type="button" data-action="speed" aria-label="speed 1x">1x</button>
                  <button class="fullscreen" type="button" data-action="fullscreen" aria-label="fullscreen"></button>
                </div>
              </div>
              <div class="controls">
                <span class="time js-elapsed">0:00</span>
                <input class="scrubber" type="range" min="0" max="1" step="0.1" value="0" aria-label="seek">
                <span class="time total js-duration">0:00</span>
              </div>
```

- [ ] **Step 4: Make the identical replacement in `watch.html`**

The `watch.html` block is the same text at the same indentation (its `.actions` below holds only Save; leave it as is). Replace it with the same new block as Step 3.

- [ ] **Step 5: Add the styles**

In `reels_api/static/style.css`, directly after `.speed.is-fast { color: var(--accent-bright); }`:

```css
/* Phone: volume, speed and fullscreen stack on the right of the video, each on its own row, so a tap
   can't hit a neighbour; the scrubber keeps the full width (side rail spec 4.2). */
.chrome-meta { display: flex; align-items: flex-end; gap: 12px; }
.chrome-meta .caption { flex: 1; min-width: 0; }
.rail { display: flex; flex: none; flex-direction: column; gap: 12px; }
.rail > button { width: 44px; min-width: 0; height: 44px; border-radius: 999px; background: rgba(0, 0, 0, 0.4); }
```

(`.rail > button` outranks `.volume`, `.speed` and `.fullscreen`, so only the rail's copies change. `.volume`/`.fullscreen` already centre their icons with flex; a plain button centres the speed text. The global `[hidden] { display: none !important; }` still hides a fullscreen button the browser can't use.)

- [ ] **Step 6: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest`
Expected: all PASS, including the two new tests and the unchanged `test_player_has_the_speed_button` / `test_player_has_the_fullscreen_button` counts.

- [ ] **Step 7: Commit**

```bash
git add reels_api/static/app.html reels_api/static/watch.html reels_api/static/style.css tests/test_web.py
git commit -m "feat: phone player's volume, speed and fullscreen move to a side rail"
```

### Task 2: Docs and hand check

**Files:**
- Modify: `CLAUDE.md` (Architecture → Frontend paragraph)

**Interfaces:**
- Consumes: `.rail`, `.chrome-meta`, `.desk-controls` from Task 1.

- [ ] **Step 1: Update CLAUDE.md**

In the Frontend paragraph, after the sentence ending "…(fullscreen spec, `docs/superpowers/specs/2026-09-28-player-fullscreen-speed-design.md`).", insert:

```
On a phone, volume, speed and fullscreen sit in a side rail (`.rail`) beside the caption, one per row, so a tap can't hit a neighbour; the desktop keeps them in `.desk-controls` (side rail spec, `docs/superpowers/specs/2026-09-30-player-side-rail-design.md`).
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: side rail in CLAUDE.md"
```

- [ ] **Step 3: Check by hand with the dev board**

Run the dev board in Docker (command in the docstring of `scripts/dev_board.py`), open the printed invite link, and in Chrome DevTools pick a phone size (e.g. 390×844). Check each Review Focus line, plus:
- tap to pause shows the rail bottom-right, level with the caption; volume, speed and fullscreen each work as before;
- the scrubber spans the full width;
- the 9:16 and 16:9 seeds, and the NSFW seed (3) covered and uncovered;
- fullscreen at phone width: the rail shows while paused, and its button leaves fullscreen;
- the printed share link (view-only page): the same rail, Save below;
- the desktop width (over 700px): the controls row under the frame is unchanged.

Report anything that looks off before calling the work done.
