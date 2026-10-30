# Side Rail for the Phone Player's Buttons — Design

Date: 2026-09-30
Status: approved design, pre-implementation
Builds on: `2026-09-28-player-fullscreen-speed-design.md` (the "fullscreen
spec", whose section 4.1 put the speed and fullscreen buttons in the
phone's controls row) and `2026-09-16-reels-board-ui-design.md` (the
"board spec", section 7.2)

## 1. Purpose

On a phone, the options row holds the elapsed time, the scrubber, the total
time, volume (28px), speed (34px) and fullscreen (28px), 10px apart. A tap
meant for volume keeps landing on speed.

This change moves volume, speed and fullscreen out of that row into a
column on the right edge of the video, reels-style (design mock-up "1b Side
rail"). Each button gets its own row and a bigger target, and the scrubber
gets the full width.

**What the buttons do doesn't change.** Volume mutes and unmutes, speed
steps 1x → 1.5x → 2x → 1x, fullscreen enters and leaves (fullscreen spec
3.3, 3.4). Only where they sit changes. The mock-up's caption talks of
panels opening sideways (a volume slider, a speed picker); that is out of
scope (section 7).

## 2. Scope

- **Phones only** (below 700px): the options in `.chrome`. The desktop
  controls row under the frame (`.desk-controls`) is unchanged, and so is
  fullscreen from 700px, which uses that row.
- **Both players:** the board's (`app.html`) and the view-only page's
  (`watch.html`), mirrored (CLAUDE.md).
- **No change** to `player.js`, the other modules, the server or the API.
  `player.js` already finds every copy of the volume, speed and fullscreen
  buttons by `data-action` and redraws them all (`renderVolume`,
  `renderSpeed`, `renderFullscreen`), wherever they sit.

## 3. Behaviour

- **The rail shows and hides with the options.** A tap pauses the reel and
  shows the top bar, the caption, the rail, the scrubber and the actions
  (fullscreen spec 3.1); a tap while paused hides them all. The rail is
  never shown on its own.
- **Fullscreen on a phone held upright** (below 700px) works the same way:
  the options, rail included, show while paused, and the rail's fullscreen
  button leaves fullscreen.
- **A browser with no fullscreen** hides the fullscreen button (as today),
  and the rail just has two circles.
- Everything else (icons, labels, `is-fast` at 1.5x and 2x, mute carrying
  from reel to reel) is as in the fullscreen spec.

## 4. Layout

### 4.1 Markup (`app.html` and `watch.html`, mirrored)

In `.chrome-bottom`, the caption and a new rail share a row above the
controls row. The three buttons move from `.controls` into `.rail`,
unchanged, in this order from the top:

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
    <input class="scrubber" …>
    <span class="time total js-duration">0:00</span>
  </div>
  <div class="actions">…</div>   <!-- unchanged -->
</div>
```

`.desk-controls` keeps its own volume, speed and fullscreen buttons, so
each page still has exactly two of each.

### 4.2 Styles (`style.css`)

- `.chrome-meta`: a row (`display: flex`), `align-items: flex-end`, gap
  12px. The caption takes the rest (`flex: 1; min-width: 0`), so a long
  caption wraps (still two lines at most) and never runs under the rail.
  An empty caption leaves the rail on the right.
- `.rail`: a column (`display: flex; flex-direction: column`), gap 12px,
  `flex: none`.
- `.rail > button`: 44px circles, `border-radius: 999px`, background
  `rgba(0, 0, 0, 0.4)` like `.round-btn`. Icons stay at their current sizes
  (volume 17px, fullscreen 16px). Speed keeps its mono text, `--ink-70` at
  1x and `--accent-bright` with `.is-fast`; in the rail it is 44px wide
  (`min-width: 0`), so `1.5x` fits inside the circle.
- `.rail > button[hidden]` still hides (the global `[hidden]` rule
  already wins).
- The desktop's `.volume`, `.speed` and `.fullscreen` sizes are unchanged:
  the new rules are scoped to `.rail`.
- `.controls` in the phone keeps its margins; with only the time, the
  scrubber and the total in it, the scrubber stretches to the full width.

## 5. Testing

**Unit tests (`tests/test_web.py`)**, for both pages (`_player_pages`):

- Each page has one `<div class="rail">`, and the volume, speed and
  fullscreen buttons sit inside it (the markup between `<div class="rail">`
  and its `</div>` holds all three `data-action`s).
- The phone's controls row no longer holds them: the markup of
  `.chrome-bottom`'s `<div class="controls">` has no `data-action`.
- The existing counts (two speed and two fullscreen buttons per page) still
  pass unchanged.

**By hand, with `scripts/dev_board.py`** (Chrome DevTools at phone width,
and a real phone):

- Tap to pause: the rail shows at the right edge, bottom level with the
  caption; volume, speed and fullscreen each do what they did, and a tap on
  one never hits another.
- The scrubber spans the full width.
- A long caption stays clear of the rail; a reel with no caption still shows
  the rail on the right.
- The 9:16 and 16:9 seeds; the NSFW seed (3) covered and uncovered.
- Fullscreen held upright: the rail shows while paused, and its button
  leaves fullscreen.
- The view-only share link: the same rail, with Save below.
- Desktop (and a phone turned sideways) still has the controls row under
  the frame, unchanged.

## 6. Docs

- **CLAUDE.md**, Frontend: the phone's volume, speed and fullscreen sit in
  a side rail (`.rail`) next to the caption, and the desktop keeps them in
  `.desk-controls`.
- **README.md**: no change; it doesn't say where the buttons sit.

## 7. Out of scope

- **Panels that open sideways** from the rail (a volume slider, a speed
  picker). iPhone Safari ignores `video.volume`, so a slider wouldn't work
  there anyway.
- **A rail that stays visible while playing** (as on TikTok).
- **Moving star, delete or Share into the rail.**
- **Any change to the desktop layout.**
