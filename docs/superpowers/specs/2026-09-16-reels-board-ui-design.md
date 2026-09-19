# Reels Board UI — Design

Date: 2026-09-16
Status: approved design, pre-implementation
Builds on: `2026-09-16-mobile-web-page-design.md` (the "web spec") and
`2026-09-16-reels-download-api-design.md` (the "API spec")
Visual reference: `design_handoff_reels_dump/README.md` and
`design_handoff_reels_dump/Reels Dump.dc.html` (the "handoff")

## 1. Purpose

Replace the current phone page (link box, status line, "Recent" list) with
the design in the handoff: a dark, anonymous, communal board of reels.
Three surfaces — **board**, **player**, **paste** — plus the states around
them (empty pile, fetching, bad link, toasts). One responsive page covers
phones and desktop browsers.

The handoff is high fidelity: colours, type, spacing, radii and copy are
final. Where this spec and the handoff disagree, this spec wins; every
such difference is listed in section 9.

Out of scope: accounts or names of any kind, live push updates
(WebSocket/SSE), a JS build step or framework, a JS test harness, new
home-screen icons, Open Graph link previews, keeping the pile across
restarts.

## 2. Constraints

Everything in web spec section 2 still holds (HTTPS, iOS fresh-tap rule
for `navigator.share`, Android-only share target, in-memory jobs, same
origin). Additionally:

- **Plain HTML, CSS and JavaScript**, no build step, no framework, no new
  Python or JS dependencies. JavaScript is split into ES modules loaded
  with `<script type="module">`. `NoCacheStaticFiles` already serves every
  `.js` file as `text/javascript`, which modules require.
- **Imagery is the real reel.** Every "drop a still" slot in the handoff
  is the job's `thumbnail_url` JPEG (tiles) or the MP4 at `file_url` with
  the thumbnail as `poster` (player).
- **Dark only.** The page no longer follows the phone's light/dark setting.
- **Icons** are Lucide SVG markup copied into `icons.js` (`clipboard`,
  `clipboard-plus`, `arrow-up`, `x`, `clock`, `volume-2`, `volume-x`,
  `download`, `link-2`, `check`, `circle-alert`, `chevron-left`,
  `chevron-right`, `play`), plus the Simple Icons `whatsapp` mark. Lucide
  is ISC-licensed, Simple Icons CC0; `icons.js` carries both notices.
- **Font:** Bricolage Grotesque from Google Fonts (weights 400/600/700/800,
  `opsz 12..96`) with `system-ui, sans-serif` fallback. Monospace is
  `ui-monospace, Menlo, Consolas, monospace`.

## 3. API changes

All additive. Existing clients (curl, the future WhatsApp bot) are
unaffected.

### 3.1 Caption

- `MediaInfo` gains `caption: str | None = None` (defaulted so existing
  constructors keep working).
- `downloader.download` sets it to yt-dlp's `description`, stripped; when
  that is missing or blank, to the resolved `title` (which already falls
  back to `"video"`). Reason: for Instagram yt-dlp's `title` is
  "Video by <user>" and the real caption is in `description`.
- `JobResult` gains `caption: str | None = None` (defaulted so existing
  constructors keep working). `Pipeline.run` passes `info.caption`.
- `job_to_dict` adds `"caption"` for done jobs: `r.caption or r.title`.

### 3.2 Finish time

`job_to_dict` adds `"finished_at"` for done jobs: `job.finished_at` in the
same `...Z` format as `expires_at`, or `null` if unset.

### 3.3 One job per URL

`JobManager.submit`, after `extract_url` and `detect_source` and before the
queue-full check, looks for an existing job whose `url` equals the
extracted URL and whose status is not `failed`. If one exists it is
returned unchanged: nothing is queued, `POST /jobs` answers
`202 {"id", "status"}` for that job. The comparison is exact string
equality — a `vm.tiktok.com` short link and the canonical
`tiktok.com/@…/video/…` URL are different reels. A failed job does not
block a retry of the same URL.

`JobStore` gains `find_active_by_url(url: str) -> Job | None` implementing
the lookup under the store lock.

## 4. Links to a reel

- A reel's link is `<origin>/?reel=<job id>`. `GET /` already ignores the
  query string, and `login.js` calls `location.reload()`, which keeps it,
  so a friend without the cookie logs in and lands on the reel.
- **Opening** the player calls `history.pushState` with `?reel=<id>`.
  **Moving** to another reel calls `history.replaceState`. **Closing**
  (✕, Esc) calls `history.back()` when the page pushed the entry, else
  `replaceState` to `/`. A `popstate` without `reel` closes the player;
  with `reel` opens it. So Back always returns to the board, at the same
  scroll position (the board stays mounted underneath).
- **On load** with `?reel=<id>`: the page loads the pile, finds the reel in
  it, else asks `GET /jobs/{id}`. Done → open the player on it (muted
  autoplay, since there was no tap; section 7.1). Any other outcome →
  `replaceState` to `/` and toast "that one's gone".
- The Android share-target parameters `url`, `text`, `title` keep their
  current behaviour (web spec 7.2 step 1), now feeding the paste flow.

## 5. Page structure

### 5.1 Breakpoints

| width        | board columns | paste field        | player                         |
|--------------|---------------|--------------------|--------------------------------|
| < 700px      | 3             | fixed bottom bar   | full-bleed, tap-to-reveal      |
| 700–899px    | 3             | top bar            | desktop overlay, no prev/next buttons |
| 900–1099px   | 4             | top bar            | desktop overlay                |
| ≥ 1100px     | 5             | top bar            | desktop overlay                |

The player mode is read from `matchMedia("(min-width: 700px)")` when it
opens; a change while open re-renders the open reel in the new mode.

### 5.2 `app.html`

Static shell, no inline script:

- `<header>`: wordmark "reels", pile count, and the paste `<form>`.
  One form element; CSS pins it to the bottom below 700px and places it
  in the top bar above.
- `<main>`: the grid and the empty state.
- The player root (`hidden` until opened).
- The toast root.
- `<script type="module" src="/static/app.js">`.

`<meta name="theme-color" content="#0a0b0d">`, `color-scheme: dark`,
Google Fonts `<link>` with `preconnect`. The manifest's `theme_color` and
`background_color` become `#0a0b0d`.

### 5.3 Tokens

`style.css` declares the handoff's tokens as custom properties on `:root`
with the handoff's names and values (`--bg`, `--surface`, `--tile`,
`--ink`, `--ink-70`, `--ink-50`, `--ink-42`, `--hairline`,
`--hairline-strong`, `--accent`, `--accent-ink`, `--accent-bright`,
`--danger-border`, `--danger-icon`, `--danger-text`, `--scrim-badge`,
`--scrim-overlay`). `--accent` uses the `oklch()` value with the hex
fallback declared first. Type roles, radii, control heights and scrims are
exactly as in the handoff's "Design tokens" section. No shadows.

## 6. Board and paste

### 6.1 Header

- Below 700px: "reels" (700 21px, −.03em) left, "N in the pile" (mono
  11px, `--ink-50`) right, baseline-aligned, 16px sides, 12px below.
  Top padding respects `env(safe-area-inset-top)`.
- 700px and up: top bar per handoff screen 8 — wordmark (22px), "N in the
  pile · no names, ever", spacer, paste field 380px × 42px with the 32px
  "add" pill; 1px bottom border `rgba(255,255,255,.08)`.
- N counts done reels plus a pending optimistic tile.

### 6.2 Grid and tiles

- Grid per handoff screens 1 and 8: mobile gap 4px, 6px side padding,
  radius 4px; desktop gap 12px, max-width 1100px centred, 26px top
  padding, radius 8px. Tiles are `aspect-ratio: 9/16`.
- Mobile bottom padding clears the paste bar (50px field + 18px +
  `env(safe-area-inset-bottom)` + 24px).
- Each tile is a `<button type="button" aria-label="play, <age> ago">`
  holding `<img loading="lazy" alt="">` with `object-fit: cover` on
  `--tile`. A job with `thumbnail_url: null` shows the bare `--tile`.
- **Time badge** bottom-left: mobile mono 9px, 5px inset, 2px 5px padding,
  radius 4px; desktop mono 10px, 8px inset, 3px 7px, radius 5px. The
  newest tile shows the play triangle (8px) before the time.
- **Age format** from `finished_at`: under 1 minute "now"; under 1 hour
  "<m>m"; under 24 hours "<h>h"; else "<d>d" (floored).
- **Desktop hover and `:focus-visible`**: 2px `--accent` outline, offset
  −1px; bottom-up scrim `rgba(0,0,0,.62)` → transparent at 55% carrying the
  13px play triangle and "play · 5h ago" (600 11px); the badge hides.
- Tap/click opens the player on that reel.

### 6.3 Loading and refreshing

- `GET /jobs` on start, every 30 seconds while
  `document.visibilityState === "visible"`, and on `visibilitychange` to
  visible.
- Rendering is keyed by job id: existing tile elements are kept (their
  image never reloads), new ones are inserted in order, missing ones
  removed. Only the badge text is refreshed on existing tiles.
- A failed refresh leaves the board as it is.
- The open player keeps working on its own copy of the list; a refresh
  does not move the player (section 7.1, "order").

### 6.4 Empty state

When there are no done reels and no pending tile: the grid hides and the
handoff's screen 5 shows (54px dashed box with `clipboard-plus`, "the pile
is empty", "paste something in and it shows up for everyone."). On mobile
the paste bar loses its scrim gradient. On desktop the same block is
centred in the space below the top bar.

### 6.5 Paste field states

`paste.js` owns one state: `idle | fetching | error`.

**idle** — per handoff: clipboard icon (decorative, `aria-hidden`),
`<input type="text" inputmode="url" enterkeyhint="go">` with placeholder
"paste a link" (desktop: "paste a link, hit enter"), submit button (mobile
38px accent circle with `arrow-up`, `aria-label="add"`; desktop 32px
"add" pill). Empty or whitespace-only input does nothing on submit.

**fetching** — entered on submit:
1. An optimistic tile is inserted first in the grid: `--tile`, 1px
   `--hairline`, centred 20px spinner (2px ring `rgba(255,255,255,.14)`,
   top `--accent`, 0.8s linear), "now" bottom-left mono 9px
   `--accent-bright` (desktop 10px). The count increments.
2. The field's icon becomes a 17px spinner, the input is `readonly` and
   shows "pulling it down…" (mono 14px, `--ink-70`), the submit button is
   hidden.
3. Mobile only: the submitted text shows 10px below the field, mono 12px
   `--ink-50`, single line, ellipsis.
4. `POST /jobs {url: text}`. 400/429 → **error** with the body's `error`
   code. Network failure → **error** with `network`.
5. Poll `GET /jobs/{id}` every 1.5s. A network error keeps polling; a 404
   → **error** with `processing_failed`; `failed` → **error** with the
   job's `error` code; `done` → success.
6. **Success:** the pile is reloaded (6.3). The optimistic tile is
   replaced by the real tile in place; its image fades in over 200ms
   `ease-out` once loaded. If the job id was already on the board (3.3),
   the optimistic tile is simply removed and the existing tile is
   scrolled into view. The field returns to **idle**, cleared. The player
   does not open.

**error**:
- The optimistic tile is removed and the count restored.
- The grid dims to `opacity: .4`.
- The input shows the submitted text (mono 14px, `rgba(242,240,234,.85)`,
  ellipsis), the border becomes `--danger-border`, the icon becomes
  `circle-alert` in `--danger-icon`, the submit button goes inert
  (`rgba(255,255,255,.08)` fill, `rgba(242,240,234,.55)` icon, `disabled`).
- A message row 10px below, wrapping, gap 6px: "couldn't grab that one."
  (500 12.5px `--danger-text`) then the hint (400 12.5px
  `rgba(242,240,234,.55)`):

  | error code                          | hint                                       |
  |-------------------------------------|--------------------------------------------|
  | `unsupported_url`                   | try the share link.                        |
  | `private_or_removed`                | it's private or gone.                      |
  | `login_required`                    | instagram wants a login for that one.      |
  | `platform_blocked`                  | got blocked. try again in a bit.           |
  | `timeout`, `processing_failed`, any other | try again.                           |
  | `too_many_jobs`                     | too busy right now. try again in a minute. |
  | `network`                           | no connection. try again.                  |

  On desktop the message row sits under the field inside the top bar,
  right-aligned to the field.
- Any `input` event (edit, clear, paste) returns to **idle**, keeping the
  new value and un-dimming the grid.

Only one paste is in flight at a time. A 401 anywhere reloads the page
(unchanged behaviour of the `api` wrapper).

## 7. Player

### 7.1 Common behaviour

- One `<video playsinline loop preload="auto">`, `src = file_url`,
  `poster = thumbnail_url`.
- **Playback start.** When opened or moved by a user gesture, `play()` is
  called inside that gesture's handler, unmuted. If it rejects, the video
  is muted and `play()` retried. When opened from a `?reel=` link on load
  it starts muted. The volume button toggles `muted` and swaps
  `volume-2` / `volume-x`; the choice carries to the next reel.
- **Scrubber:** `<input type="range" min=0 max=duration step=0.1>`, styled
  as the handoff's 3px track (`rgba(255,255,255,.22)`) with `--accent`
  fill up to the value (via a `--progress` custom property), 44px tall hit
  area. Input seeks; `timeupdate` moves it. Elapsed time (`m:ss`) left,
  duration right.
- **Source line:** `clock` icon + "TikTok · 0:19 · gone in 6h" —
  `SOURCE_NAME[source]`, `duration_seconds` as `m:ss`, and the expiry
  (`expires_at` − now: under 1 hour "gone in <m>m" with a minimum of 1,
  else "gone in <h>h" rounded; past → "gone soon"). Parts that are null
  are dropped.
- **Caption:** `caption` from the job.
- **Order:** the player takes a snapshot of the board's reel list when it
  opens and moves through that snapshot. A refresh while open adds new
  reels to the snapshot's front but never removes or reorders the rest.
- **Moving** to a reel: pause, abort that reel's prefetch (7.4), swap
  `src`/`poster`/metadata, `play()`, `replaceState`.
- **Video error** (`error` event on the element, e.g. the reel expired
  while open): close the player, remove the tile, toast "that one's gone".
- **Closing:** pause, remove `src` and call `load()` to release the
  stream, abort any prefetch, unlock body scroll, restore focus to the
  tile that opened it.

### 7.2 Mobile (< 700px)

Full-screen fixed layer over the board, `background: #000`, video
`object-fit: cover`. `body` gets `overflow: hidden` while open.

**Chrome hidden** (default) — handoff screen 2: bottom scrim
`rgba(0,0,0,.55)` → transparent, 40px top / 20px + safe-area bottom
padding, 3px progress bar (read-only view of the scrubber value) and the
hint row "swipe for the next one · tap for options" with a 12px
`arrow-up`, mono 10.5px, `--ink`. `pointer-events: none`.

**Chrome revealed** — handoff screen 3: full-frame scrim
`linear-gradient(to bottom, rgba(0,0,0,.55) 0 18%, rgba(0,0,0,.15) 40%, rgba(0,0,0,.82) 78%)`;
top row (34px ✕ button, centred source line, 34px spacer; top inset
16px + safe-area); bottom block (caption 400 13.5px/1.42 clamped to two
lines; control row with elapsed, scrubber, duration, volume button;
action row: **Share** flex 1.4, **Save** flex 1, **Copy link** 48px
circle `aria-label="copy link"`; 16px sides, 18px + safe-area bottom).
Transition in and out: opacity plus `translateY(4px)` over 160ms
`ease-out`. No auto-hide.

**Gestures** on the video layer (pointer events, `touch-action: none`):
- Movement under 10px between down and up → **tap**: toggle chrome.
  Taps on buttons and the scrubber do not toggle.
- Vertical drag moves the frame with the finger (`translateY`). On
  release, if the distance is over 20% of the viewport height or the
  velocity is over 0.5 px/ms, animate the frame out over 200ms `ease-out`
  and move to the next reel (drag up) or previous (drag down); the new
  frame enters from the opposite side over 200ms. Otherwise spring back
  over 160ms. At either end of the snapshot the frame follows the finger
  at one third of the distance and always springs back.
- Chrome state (revealed or hidden) carries to the next reel.

### 7.3 Desktop (≥ 700px)

Handoff screen 9:
- The board stays visible underneath at `opacity: .28`, under a
  `--scrim-overlay` fixed layer. `body` scroll is locked.
- Close button 36px, top 18px, right 22px, `aria-label="close"`.
- Centred row, `align-items: flex-start`, gap 28px, 34px/40px padding:
  prev button (40px, hidden below 900px), video column, side panel
  (300px), next button. Prev/next are `disabled` (opacity .35) at the ends.
  The buttons are vertically centred on the video frame.
- Video frame: height `min(520px, 74vh)`, width height × 9/16, radius
  14px, `object-fit: cover`, `--tile` background. Control row 12px below:
  elapsed (mono 11px), scrubber, duration (`--ink-70`), volume button.
  Click on the video toggles play/pause.
- Side panel, gap 18px: source line (mono 11.5px, `rgba(242,240,234,.75)`,
  13px clock), caption (400 15px/1.45, clamped to 8 lines), action stack
  (gap 9px: **Share to WhatsApp** 46px full-width; row of **Download** and
  **Copy link**, 44px each), keyboard hint
  "← → to move through the pile · esc to close" (mono 11px, `--ink-50`).
- Keys while open: `ArrowLeft`/`ArrowRight` move, `Escape` closes. Keys
  are ignored while focus is in the scrubber (so arrows seek there).
  Focus moves to the close button on open and is trapped inside the
  overlay while it is open.
- Clicking the scrim outside the row does nothing.

### 7.4 Actions

The reel link is `location.origin + "/?reel=" + id` (section 4).

**Share (mobile)** — if `navigator.share` exists:
`navigator.share({ url })`, called directly in the tap handler. An
`AbortError` is ignored; any other error falls back to the WhatsApp link.
Without `navigator.share`: `window.open("https://wa.me/?text=" + encodeURIComponent(url), "_blank", "noopener")`.

**Share to WhatsApp (desktop)** — always the `wa.me` link above.

**Copy link** — `navigator.clipboard.writeText(url)` → toast "link copied".
If it rejects → toast "couldn't copy the link".

**Save (mobile) / Download (desktop)** — depends on the device:
- **iOS/iPadOS** — `/iPad|iPhone|iPod/.test(navigator.userAgent)`, or
  `navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1` —
  *and* the zero-byte `navigator.canShare({files: [...]})` probe from web
  spec 7.4 passes:
  - When a reel becomes current, its `file_url` is fetched into a `Blob`
    with an `AbortController`, and a `File` named
    `<slugify(title)>.mp4` (`video/mp4`) is built. Moving to another reel
    or closing aborts the fetch and drops the blob.
  - While the fetch runs, Save shows a 17px spinner in place of its icon
    and is `aria-disabled` (a tap does nothing).
  - When ready, `canShare({files: [file]})` is checked; if it fails, Save
    falls back to the download behaviour below. Otherwise a tap calls
    `navigator.share({ files: [file] })` with no `await` before it. No
    toast on success (the sheet's target is unknown). `AbortError` is
    ignored; other errors → toast "couldn't save that one".
  - If the fetch fails, Save falls back to the download behaviour.
- **Everything else** (Android, desktop): no prefetch. A tap clicks a
  temporary `<a href="file_url" download>` (the server already sends
  `Content-Disposition: attachment` with the slugified name) and shows the
  toast "saved to your downloads".

The `whatsapp_ok` "Over 16 MB" note from the current page is dropped:
shares are links now.

## 8. Toast and login page

### 8.1 Toast

- One toast at a time; a new one replaces the current one and restarts its
  timer. Visible 2.5s, fade in/out 160ms.
- Look per handoff screen 4: `rgba(20,22,26,.94)`, 1px
  `--hairline-strong`, radius 14px, 13px/16px padding, 24px accent circle
  with a 14px `check`, label 600 13.5px. `role="status"`,
  `aria-live="polite"`.
- Error toasts ("that one's gone", "couldn't copy the link", "couldn't save
  that one") use the same look with `circle-alert` in `--danger-icon`
  instead of the accent circle.
- Position: mobile `left/right: 16px`, `bottom: 88px + safe-area`;
  showing it hides the player chrome. Desktop: centred, `bottom: 32px`,
  `max-width: 360px`, above the overlay.

### 8.2 Login page

`login.html` restyled with the same tokens and font; `login.js` and its
behaviour are unchanged. Centred column, max-width 340px, gap 14px:
wordmark "reels" (700 28px, −.03em), line "enter the passcode" (400 14px
`--ink-70`), passcode input styled as the paste field (50px pill,
`--surface`, `--hairline`), full-width **continue** button (48px accent
pill, 700 14.5px), error text below in `--danger-text` 500 12.5px.
Element ids stay the same (`login-form`, `passcode`, `continue`,
`login-error`).

## 9. Deliberate differences from the handoff

| handoff | this design | why |
|---|---|---|
| Share sends the reel's source URL | Share sends our own `/?reel=<id>` link | owner's decision |
| Save downloads, toast "saved to your camera roll" | iOS: share sheet with the file, no toast; others: download, toast "saved to your downloads" | a web download on iPhone lands in Files, not Photos; the sheet's "Save Video" reaches Photos |
| Clipboard icon unspecified | decorative; today's separate Paste button is dropped | handoff: tiles and submit are the only tap targets |
| Desktop paste-in-progress not drawn | same states as mobile inside the top-bar field, no URL line | nothing drawn; reuse |
| Board breakpoints "~1100px" and "~700px" | 700 / 900 / 1100px (section 5.1) | make them exact |
| Optional 3s chrome auto-hide | no auto-hide | buttons should not vanish while deciding |
| Tile ages "1d", "2d" | same format, but reels live `RETENTION_HOURS` (default 6) | server retention unchanged |

## 10. Code layout

```
reels_api/
  downloader.py   caption from description, fallback title
  models.py       MediaInfo.caption, JobResult.caption; caption + finished_at in job_to_dict
  pipeline.py     passes caption into JobResult
  jobs.py         JobStore.find_active_by_url; submit returns an existing active job
  static/
    app.html               rewritten shell (5.2)
    login.html             restyled (8.2)
    style.css              rewritten (5.3, 6, 7, 8)
    app.js                 entry: wiring, ?reel= links, history, share-target params
    api.js                 fetch wrapper (401 → reload), listJobs, getJob, createJob
    format.js              formatAge, formatDuration, formatExpiry, slugify
    board.js               header count, keyed grid, optimistic tile, empty state, refresh timer
    paste.js               paste form states and polling (6.5)
    player.js              open/close/move, mobile gestures and chrome, desktop overlay and keys, actions (7)
    toast.js               showToast(message, {error})
    icons.js               Lucide + Simple Icons SVG strings
    manifest.webmanifest   theme/background colour #0a0b0d
    login.js, sw.js, icon-*.png   unchanged
scripts/
  dev_board.py    local manual-testing server (section 11.2)
```

Module dependencies point one way: `app.js` → `board.js`, `paste.js`,
`player.js` → `api.js`, `format.js`, `toast.js`, `icons.js`. `board`,
`paste` and `player` do not import each other; `app.js` passes callbacks
(`onOpen(id)`, `onPending()`, `onSettled(job | null)`).

## 11. Testing

### 11.1 Automated (pytest, no network, no ffmpeg)

- **Downloader:** caption is the stripped `description`; missing, `None`
  or whitespace-only description falls back to the title; a missing title
  and description give caption `"video"`.
- **Pipeline:** `JobResult.caption` equals the downloader's caption.
- **`job_to_dict`:** done job has `caption` and `finished_at` (Z format);
  `caption` falls back to `title` when the result's caption is `None`;
  queued and failed jobs have neither key.
- **`JobManager.submit`:** same URL while the first job is queued returns
  the same job and does not grow the queue; same URL after it is done
  returns it; same URL after it failed creates a new job; a different URL
  creates a new job; share text containing an already-submitted URL
  returns the existing job; a duplicate is returned even when the queue
  is full.
- **Routes:** `POST /jobs` twice with the same URL returns the same id;
  `GET /jobs` items include `caption` and `finished_at`.
- **Web:** `test_app_js_is_served` no longer asserts `navigator.share` in
  `app.js`; instead every module (`app.js`, `api.js`, `format.js`,
  `board.js`, `paste.js`, `player.js`, `toast.js`, `icons.js`) is served
  with `text/javascript` and `no-cache`, and `app.html` references
  `/static/app.js` with `type="module"`.

### 11.2 Manual, in Chrome, against `scripts/dev_board.py`

`scripts/dev_board.py` (dev only, not shipped in the image) starts the
real app via `create_app` with `WEB_PASSCODE=dev`, `MAX_VIDEOS=50`,
storage in a temp directory, and:
- **Seeds** the store with 12 done jobs (`--empty` seeds none): mixed
  TikTok/Instagram sources, captions of varying length (one over two
  lines), `finished_at` spread from 30 seconds to 5.5 hours ago, one with
  no thumbnail. Six clips and thumbnails are generated once with ffmpeg
  (`testsrc2` 720×1280 with a sine tone, 8–30s, each tinted with a
  different `hue` so tiles are told apart; `drawtext` is avoided because
  the slim image has no fonts) and reused across the 12 seeds, so ffmpeg
  must be on `PATH`. Seeding happens before the manager starts so the
  startup cleanup keeps the files.
- Uses a **fake pipeline** for pasted links: sleeps 3 seconds, then fails
  with `private_or_removed` if the URL contains `private`, `login_required`
  if it contains `login`, `platform_blocked` if it contains `blocked`,
  `timeout` if it contains `slow`; otherwise copies a seeded clip and
  thumbnail under the new job id and succeeds.

Run it inside the project image, which has ffmpeg:
`docker build -t reels-dev . && docker run --rm -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app -v "$PWD/reels_api:/app/reels_api:ro" -v "$PWD/scripts:/app/scripts:ro" reels-dev python scripts/dev_board.py --host 0.0.0.0`,
or directly with a local ffmpeg. The `reels_api` mount makes static-file
edits show up on reload. The script binds `127.0.0.1:8000` by default
(`--host`/`--port` override it) and sets `API_KEY=dev` itself. Chrome treats `http://localhost` as
secure, so the `Secure` cookie works.

Checklist, at 390×844 (device emulation, touch) and 1280×800:
- login page look; wrong then right passcode
- full board, empty board (`--empty`), badges, desktop hover and keyboard focus, 3/4/5 columns
- paste: success (tile fades in, count), each error hint, editing clears the error, unsupported URL, same URL twice resolves to one tile
- mobile player: tap reveals and hides chrome, swipe next/previous, rubber band at both ends, scrubber seek, mute toggle, ✕ and browser Back return to the same scroll position
- desktop player: overlay layout at 800px and 1280px widths and a short (600px) window, ←/→/Esc, prev/next disabled at ends
- Copy link toast; Share falls back to `wa.me` where `navigator.share` is missing; Download toast
- `/?reel=<live id>` opens the player muted; `/?reel=nope` shows the board and "that one's gone"
- `/?text=https://vm.tiktok.com/x` starts a paste

### 11.3 On real devices after deploy (owner)

- iPhone: Save opens the sheet and "Save Video" lands in Photos; Share
  opens the sheet with the link; swipe feel; unmuted start.
- Android: Save lands in Downloads and shows in the gallery; Share opens
  the sheet; sharing from the TikTok app still pastes.
- A friend without the cookie opens a shared `/?reel=` link, logs in and
  lands on the reel.
