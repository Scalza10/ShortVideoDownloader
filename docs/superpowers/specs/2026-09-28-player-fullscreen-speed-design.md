# Tap to Pause, Fullscreen and Speed in the Player — Design

Date: 2026-09-28
Status: approved design, pre-implementation
Builds on: `2026-09-16-reels-board-ui-design.md` (the "board spec", whose
section 7.2 this changes) and `2026-09-17-invite-and-share-links-design.md`
(the "links spec", for the view-only page)

## 1. Purpose

The pile now holds wide videos (16:9 from X and elsewhere) and longer ones
next to 9:16 reels. The player was built for short tall reels. This change
adds three things to it:

- **Tap to pause:** a tap on the video pauses and plays it.
- **Fullscreen:** a button that fills the screen with the reel and, for a
  wide reel on Android, turns the screen sideways.
- **Speed:** 1x, 1.5x and 2x, for the longer videos.

All three are in both players: the board's (`app.html`) and the view-only
page's (`watch.html`). The server and the API don't change.

Out of scope (section 9): automatic fullscreen on rotation, other speeds,
keyboard shortcuts.

## 2. Constraints

Everything in board spec section 2 still holds: no build step, no
framework, no JS dependencies, no JS tests, dark only, the layout switches
at 700px. Additionally:

- **The player markup exists in both `app.html` and `watch.html`**
  (CLAUDE.md). Every markup change here is made in both.
- **iPhone Safari has no element fullscreen.** Only a `<video>` can go
  fullscreen there, through Apple's own player
  (`video.webkitEnterFullscreen()`), with Apple's controls.
- **A page can't go fullscreen or lock the orientation without a user
  gesture.** Turning the phone is not a gesture, so fullscreen always
  starts from the button.

## 3. Behaviour

### 3.1 Tap to pause (phones, below 700px)

This replaces board spec 7.2's "tap: toggle chrome".

- **A tap** (movement under `TAP_SLOP_PX`, as today) on the video:
  - playing: pauses the reel and shows the options (`chrome-on`);
  - paused: plays the reel and hides the options;
  - covered NSFW reel: uncovers it, as today (NSFW cover spec).
- **The play icon:** while the video is paused, a large ▶ sits in the
  middle of the frame. It is a picture only (`pointer-events: none`), so
  a tap on it is a tap on the video. It follows the video's own `play`
  and `pause` events, not the tap. So a reel paused by something else (a
  phone call, the lock screen, an autoplay the browser refused even muted)
  shows the ▶ too, and a tap starts it. It is not shown while the reel is
  covered.
- **Moving to another reel** (swipe, delete, desktop arrows) plays it and
  hides the options.
- **Copy link, download and delete** hide the options, as today. A paused
  reel stays paused with its ▶, and one tap plays it.
- **Scrubbing** doesn't change paused or playing.
- **The hint** under the progress bar:
  - board: "swipe for the next one · tap for options" becomes
    "swipe for the next one · tap to pause";
  - view-only page: "tap for options" becomes "tap to pause".

### 3.2 Desktop click

A click on the video already plays and pauses it (and uncovers a covered
reel). It now also shows the ▶ while paused, as on phones.

### 3.3 Fullscreen

**The button** (`data-action="fullscreen"`) sits next to the volume
button in both controls rows: the phone's options (`.chrome .controls`)
and the desktop row (`.desk-controls`). It is on every reel. Its icon is
`maximize` with the label "fullscreen", or `minimize` with "exit
fullscreen" while fullscreen. It is hidden (`hidden`) only on a browser
with neither kind of fullscreen below.

**Pressing it, when not fullscreen:**

1. **Where element fullscreen exists** (Android, desktop, iPad):
   `.player-stage` goes fullscreen (`requestFullscreen`, falling back to
   `webkitRequestFullscreen`). The stage holds the frame and the desktop
   controls row, so our player stays in charge: tap to pause, the options
   and the speed button all keep working. Then, **on a phone with a wide
   reel** (width > height, from `video.videoWidth`/`videoHeight`, falling
   back to the job's `width`/`height`), it calls
   `screen.orientation.lock("landscape")`. A refused or missing lock is
   ignored and not shown to the viewer.
2. **Otherwise, where `video.webkitEnterFullscreen` exists** (iPhone):
   Apple's player takes over. It is the same `<video>`, so the speed and
   the paused state carry in and out. Leaving Apple's player comes back
   to our player. If the video came back paused, the ▶ shows (3.1).
3. **Neither:** the button is hidden, so it can't be pressed.

Entering fullscreen (1 or 2) also **plays the reel and hides the
options**: on a phone you pause to reach the button, and fullscreen is
for watching. A covered NSFW reel stays covered (`play()` refuses).
*(Added while planning.)*

**Pressing it while fullscreen** leaves fullscreen.

The icon and label follow `fullscreenchange` (and
`webkitfullscreenchange`), so leaving by Esc or the system back gesture
updates them too. Apple's player (2) doesn't change the button, because
our page isn't visible while it is up.

**While fullscreen (1):**

- The video fills the screen, whole (`object-fit: contain`, black bars),
  as everywhere else.
- **The layout still follows the width**, as everywhere (700px). *(Changed
  while planning: a phone turned sideways is wider than 700px, so it
  already gets the desktop layout, and a wide reel locked sideways always
  lands there.)*
- **Below 700px** (a phone held upright, i.e. a tall reel): tap to pause
  as in 3.1. The options, including the exit button, show while paused.
  **Swiping to another reel is off**: the frame doesn't move, as on the
  view-only page. The idle hint's text is hidden (it talks about
  swiping); the progress bar stays.
- **From 700px** (a desktop, or a phone turned sideways): the frame takes
  the whole screen but the desktop controls row (time, scrubber, volume,
  speed, exit fullscreen), which is pinned to the bottom. A click or tap
  plays and pauses, with the ▶. The caption, Share and the other panel
  buttons are not in fullscreen. **ArrowLeft/ArrowRight still move**
  between reels.
- **Turning the phone while fullscreen keeps fullscreen**; only the
  layout inside it switches.
- **Esc** leaves fullscreen only. The browser handles it. The player's
  own Esc handler must not also close the player: it returns without
  closing when `document.fullscreenElement` is set, or when fullscreen
  ended less than 500ms ago (`FULLSCREEN_ESC_GUARD_MS`, timed from
  `fullscreenchange`), in case a browser leaves fullscreen before it
  delivers the keydown.

**Leaving fullscreen** calls `screen.orientation.unlock()` (ignoring
errors). These also leave fullscreen first: closing the player and the
video failing to load (`error`). Crossing 700px does not (above).

**Turning the phone without the button** is unchanged: the full-bleed
player shows the wide reel bigger, with the browser's bars around it.

### 3.4 Speed

- **The button** (`data-action="speed"`) is a small text button showing
  `1x`, `1.5x` or `2x`, next to the volume button in both controls rows,
  in both pages. It is on every reel.
- **Each tap** moves to the next speed: 1x → 1.5x → 2x → 1x.
- **It carries from reel to reel** while the page is open, like mute. A
  reload starts at 1x.
- **It sets both `video.playbackRate` and `video.defaultPlaybackRate`**,
  since loading a new `src` resets the rate to the default. `show()`
  applies it to each reel.
- **Pitch stays natural** (the browser's default `preservesPitch`).
- **Its label** is "speed 1x" / "speed 1.5x" / "speed 2x".
- **Look:** at 1x the text is quiet (`--ink-70`, like the total time).
  At 1.5x and 2x it is highlighted (`--accent-bright`, like the on star),
  so a sped-up reel is obvious at a glance.

## 4. Layout

### 4.1 Markup (`app.html` and `watch.html`, mirrored)

In both `.controls` rows (the phone's inside `.chrome-bottom` and
`.desk-controls`), after the volume button:

```html
<button class="speed" type="button" data-action="speed" aria-label="speed 1x">1x</button>
<button class="fullscreen" type="button" data-action="fullscreen" aria-label="fullscreen"></button>
```

In `.player-frame`, after the `<video>`:

```html
<div class="play-hint" aria-hidden="true" data-icon="play"></div>
```

The idle hint's text changes as in 3.1.

### 4.2 Styles (`style.css`)

- `.speed`: a 28px-high text button in `--mono`, `--ink-70`;
  `.speed.is-fast` in `--accent-bright`.
- `.fullscreen`: sized like `.volume`.
- `.play-hint`: centred in the frame, about 64px, white at partial
  opacity with a soft shadow, `pointer-events: none`. Shown only while
  `.player.is-paused` and not `.is-covered`.
- Fullscreen styles hang off an `is-fullscreen` class that `player.js`
  puts on the player root from `fullscreenchange`, so they aren't written
  twice for `:fullscreen` and `:-webkit-full-screen`. The stage gets a
  black background. From 700px, it is a column with the frame taking the
  remaining height at full width (no `--frame-w`/`--frame-h`, no rounded
  corners) and the controls row at the bottom, padded clear of the safe
  areas. Below 700px, the frame fills it as today, and the idle hint's
  text is hidden.

### 4.3 Icons (`icons.js`)

`maximize` and `minimize` from Lucide (stroke). `play` already exists.

## 5. Code (`player.js`)

- **State:** `speed` (index into `SPEEDS = [1, 1.5, 2]`), kept across
  reels like `muted`.
- **`is-paused`** on the root, from the video's `play` and `pause`
  events, drives the ▶.
- **Phone tap** (`pointerup` under the slop): covered → `uncover()`;
  paused → `play()` and `setChrome(false)`; playing → `video.pause()`
  and `setChrome(true)`.
- **Swipes** are ignored while fullscreen, like `standalone`.
- **`move()`** hides the options after showing the next reel.
- **`show()`** applies the speed.
- **`fullscreenMode()`**, decided once: `"element"`, `"video"` (iPhone)
  or `null` (buttons hidden).
- **`toggleFullscreen()`** as in 3.3; `exitFullscreen()` is used by
  `close()` and the `error` handler.
- **`renderSpeed()`** and **`renderFullscreen()`** redraw every copy of
  their buttons, like `renderVolume()`.
- **Esc:** see 3.3.
- **New actions** in `actions`: `speed`, `fullscreen`.

`watch.js`, `app.js` and the server need no change.

## 6. Dev board

No change. `scripts/dev_board.py` already seeds 9:16, 16:9, 3:4 and 1:1
clips and an NSFW reel (seed 3), which covers all of this.

## 7. Docs

- **CLAUDE.md**, "Web page" under "Things we learned": iPhone has no
  element fullscreen, so fullscreen there is Apple's player
  (`webkitEnterFullscreen`), and a phone tap now pauses rather than only
  toggling the options.
- **README.md**, the "Play" bullet: "tap for the caption and the Share,
  Save and copy-link…" becomes tap to pause (which shows those), plus
  fullscreen and speed.

## 8. Testing

**Unit tests (`tests/test_web.py`)**, in the style of
`test_board_player_has_the_star`:

- The board page has `data-action="fullscreen"` and `data-action="speed"`
  twice each (phone row and desktop row).
- The view-only page has them twice each too.
- Neither page says "tap for options" any more.

- `/static/icons.js` defines `maximize` and `minimize` (`icon()` throws
  on an unknown name, which would break the whole player).

No new JS modules, so `APP_MODULES` doesn't change.

**By hand, with `scripts/dev_board.py`** (desktop Chrome and a phone):

- Tap to pause and play, the ▶, the options showing while paused.
- A swipe after pausing plays the next reel with the options hidden.
- The ▶ after a refused autoplay (e.g. iPhone Low Power Mode).
- Speed: 1x → 1.5x → 2x → 1x, carrying across a swipe, reset by reload.
- Fullscreen on desktop: the controls row at the bottom, arrows move, Esc
  leaves fullscreen but keeps the player open.
- Fullscreen on Android with the 16:9 seed: turns sideways and stays
  fullscreen; the controls row sits at the bottom; a tap pauses with the
  ▶; exit turns back.
- Fullscreen on a phone with the 9:16 seed: stays upright; tap to pause
  shows the options with the exit button; swiping does nothing.
- The NSFW seed (3): a tap still uncovers; no ▶ while covered.
- The view-only share link: tap to pause, speed and fullscreen work;
  still no swiping.
- **iPhone (Apple's player)** can't be tried on the dev machine. It needs
  a real iPhone against production, or the dev board over HTTPS.

## 9. Out of scope

- **Automatic fullscreen when the phone turns.** A page can't go
  fullscreen without a gesture.
- **Other speeds** (0.5x, 1.25x) and a speed menu. Three speeds on one
  button cover "this video is long".
- **Remembering the speed** across reloads.
- **Keyboard shortcuts** (Space, F) on desktop.
- **Double-tap to seek or to favorite.**
