# Handoff: Reels Dump — anonymous communal reel board

## Overview

A small web app where a closed group of friends drop links to reels (TikTok / Instagram) into one
shared pile. There are no accounts on display, no names, no likes, no comments, no counts per video.
Anyone can see everything anyone dropped, play it, share it on, or download it.

The product has exactly three surfaces:

1. **Board** — a grid of every reel in the pile, newest first, each tile labelled only with a
   relative time ("3h", "1d").
2. **Player** — one reel playing, full-bleed on mobile / centred overlay on desktop, with the source
   metadata, the reel's original caption, and Share / Save / Copy link.
3. **Paste** — a single input that accepts a link. On mobile it is a fixed bottom bar; on desktop it
   lives in the top bar.

Plus the states around them: empty pile, fetching a pasted link, bad link, saved confirmation.

## About the design files

`Reels Dump.dc.html` in this bundle is a **design reference written in HTML** — a prototype of the
intended look and behaviour, not production code to copy. The job is to **recreate these designs in
the target codebase's existing environment** (React, Vue, Svelte, native, whatever is already there)
using its established components, styling approach, and routing. If the project has no environment
yet, pick the framework that best fits and implement the designs there.

Two things in the reference file are scaffolding for the mockup only and must not be carried over:

- The `.dv-turn` / `.dv-opt` wrappers, id badges (`2a`, `3a`, `3b`) and the grey desk background —
  these exist to present options on a design canvas.
- The phone bezels (`.ph` / `.scr`), the simulated browser chrome (`browser-window.jsx`), and the
  `<image-slot>` elements. `<image-slot>` is a drag-and-drop placeholder standing in for real video
  poster frames; in the real app these are `<img>`/`<video>` poster sources from the scraped reel.

## Fidelity

**High fidelity.** Colors, typography, spacing, radii and copy are final and should be recreated
precisely. Layout is specified in px against a 390pt-wide mobile viewport and a ~1180px desktop
content width; translate to the codebase's spacing scale where one exists, otherwise use the values
as given.

Exception: icons in the reference are hand-drawn single-weight strokes standing in for a real icon
library. **Use Lucide** (or the codebase's existing icon set) — see Assets.

---

## Design tokens

### Color

| Token | Value | Use |
|---|---|---|
| `--bg` | `#0a0b0d` | app background, everywhere |
| `--surface` | `#14161a` | paste field, toast, raised chrome |
| `--tile` | `#14171c` | thumbnail placeholder before the poster loads |
| `--ink` | `#f2f0ea` | primary text, icons |
| `--ink-70` | `rgba(242,240,234,.7)` | secondary text on dark |
| `--ink-50` | `rgba(242,240,234,.5)` | metadata, status bar, counts |
| `--ink-42` | `rgba(242,240,234,.42)` | input placeholder |
| `--hairline` | `rgba(255,255,255,.1)` | 1px borders on surfaces |
| `--hairline-strong` | `rgba(255,255,255,.22)` | secondary button borders, scrubber track |
| `--accent` | `oklch(0.72 0.19 200)` ≈ `#0ec8de` | primary action fill, progress fill, focus ring |
| `--accent-ink` | `#08181c` | text/icon on accent fill |
| `--accent-bright` | `oklch(0.8 0.15 200)` | "now" label on the optimistic tile |
| `--danger-border` | `oklch(0.62 0.17 25)` | error field border |
| `--danger-icon` | `oklch(0.74 0.16 25)` | error icon stroke |
| `--danger-text` | `oklch(0.78 0.15 25)` | error message text |
| `--scrim-badge` | `rgba(0,0,0,.6)` | time badge behind text on a thumbnail |
| `--scrim-overlay` | `rgba(4,5,7,.82)` | desktop player backdrop over the board |

Only one accent. No second hue anywhere except the error state.

### Type

Display / UI: **Bricolage Grotesque** (Google Fonts), weights 400 / 600 / 700 / 800.
Metadata, timestamps, URLs, durations: **monospace** (`ui-monospace, Menlo, monospace`).

| Role | Spec |
|---|---|
| Wordmark "reels" (mobile) | 700 21px/1, letter-spacing −.03em |
| Wordmark "reels" (desktop) | 700 22px/1, letter-spacing −.03em |
| Empty-state heading | 700 22px/1.15, letter-spacing −.02em |
| Empty-state body | 400 14px/1.45 |
| Reel caption (mobile player) | 400 13.5px/1.42 |
| Reel caption (desktop player) | 400 15px/1.45 |
| Primary button label | 700 14.5px |
| Secondary button label | 600 14.5px (13.5px desktop) |
| Input placeholder | 400 15px (14px desktop) |
| Pile count / source line | 500 11px–11.5px mono |
| Thumbnail time badge | 500 9px mono (mobile), 500 10px mono (desktop) |
| Player timestamps | 500 10.5px–11px mono |
| Toast label | 600 13.5px |

Nothing below 9px, and nothing below 13px for anything the user has to read as a sentence.

### Spacing, radius, shadow

- Page padding: mobile 16px horizontal (grid gutter 6px), desktop 28px horizontal.
- Grid gap: mobile 4px, desktop 12px.
- Radii: thumbnails 4px mobile / 8px desktop; player frame 14px; toast 14px; empty-state icon box
  15px; all buttons and the paste field fully rounded (`999px`).
- Control heights: mobile paste field 50px, its submit button 38px circle; mobile action buttons
  48px; desktop paste field 42px with a 32px "add" pill; desktop primary 46px, secondary 44px.
- No shadows anywhere in the app UI. Depth comes from the scrims and hairlines only.
- Bottom gradient scrims: `linear-gradient(to top, #0a0b0d 55%, rgba(10,11,13,0))` behind the mobile
  paste bar; `linear-gradient(to top, rgba(0,0,0,.55), rgba(0,0,0,0))` over video for the idle
  progress bar; for the revealed player chrome,
  `linear-gradient(to bottom, rgba(0,0,0,.55) 0 18%, rgba(0,0,0,.15) 40%, rgba(0,0,0,.82) 78%)`
  across the whole frame.

---

## Screens / views

### 1. Board — mobile (reference: `2a`, tile captioned "feed")

**Purpose.** See everything in the pile; tap anything to play it; paste a new link.

**Layout.** Full-height column on `--bg`.
- Status bar row (device chrome in the mock; ignore in the app).
- Header row: wordmark "reels" left, pile count right ("47 in the pile", `--ink-50`, mono 11px),
  baseline-aligned, 16px side padding, 12px bottom padding.
- Grid: `grid-template-columns: repeat(3, 1fr)`, `gap: 4px`, 6px side padding, tiles
  `aspect-ratio: 9/16`, radius 4px, `overflow: hidden`, background `--tile` until the poster paints.
  Scrolls vertically; newest first, no pagination UI (infinite or "load more" is an implementation
  choice — nothing in the design depends on it).
- Time badge on each tile: bottom-left, 5px inset, mono 9px `--ink`, `--scrim-badge`, 2px 5px
  padding, radius 4px. The newest tile additionally shows a 8px play triangle before the time.
- Paste bar: fixed to the bottom, 14px side / 18px bottom padding, sitting on the scrim gradient.
  Pill: 50px tall, `--surface`, 1px `--hairline`, 14px left padding, 6px right; clipboard icon
  (17px, `--ink-50`), placeholder "paste a link" (`--ink-42`), then a 38px accent circle with a
  18px up-arrow (`--accent-ink`).

Tiles and the submit button are the only tap targets; both exceed 44px.

### 2. Player — mobile, chrome hidden (reference tile "player — chrome hidden")

**Purpose.** Watch. Nothing else competes for attention.

**Layout.** Video fills the viewport (`object-fit: cover`, 9:16 source). Over the bottom:
- 3px progress track, `rgba(255,255,255,.2)`, fill `--accent`, full width minus 18px side padding.
- 14px below it, centred hint row: 12px up-arrow icon + "swipe for the next one · tap for options",
  mono 10.5px, `--ink` at full opacity (it sits on a scrim, so keep it opaque).
- Both sit on the `rgba(0,0,0,.55) → transparent` bottom scrim, 40px top / 20px bottom padding.

Vertical swipe moves to the previous/next reel in the same order as the board.

### 3. Player — mobile, chrome revealed (reference tile "tapped — share & save")

**Purpose.** The share/download surface. Reached by **a single tap on the video**; a second tap (or
3s of inactivity, if you want it) hides the chrome again. This is a *state of the player*, not a
separate route.

**Layout.** Same video, plus the full-frame top-and-bottom scrim listed in Spacing, plus:
- Top row, 16px inset: 34px circular `rgba(0,0,0,.4)` close button with a 16px ✕ on the left; centred
  source line — 12px clock icon + "TikTok · 0:19 · gone in 6h" (mono 11px, `--ink`); 34px spacer
  right to keep the centre true.
- Bottom block, 16px side / 18px bottom padding:
  - Caption, 400 13.5px/1.42, `--ink`. The reel's own caption text, truncated with "…" — the mock
    uses "Tag 1 Friend reverse this Video and look what happens @skyandtami …". Two lines max.
  - 16px below: control row — elapsed "0:07" (mono 10.5px `--ink`), 3px scrubber
    (`rgba(255,255,255,.22)` track, `--accent` fill), duration "0:27" (mono 10.5px `--ink-70`),
    17px volume icon. Gap 10px.
  - 14px below: action row, gap 10px, three items at 48px tall:
    1. **Share** — flex 1.4, accent fill, `--accent-ink` text, 700 14.5px, 18px WhatsApp glyph +
       label. Opens the platform share sheet (`navigator.share`) with the reel URL; on a device with
       no Web Share API, fall back to a WhatsApp deep link (`https://wa.me/?text=<url>`).
    2. **Save** — flex 1, transparent `rgba(255,255,255,.06)` fill, 1px `--hairline-strong`,
       `--ink` text, 600 14.5px, download-tray icon. Downloads the video file.
    3. **Copy link** — 48px circle, same treatment as Save, link icon only.

### 4. Saved toast — mobile (reference tile "saved")

After Save completes, the chrome hides and a toast sits 88px above the bottom edge, 16px side
insets: `rgba(20,22,26,.94)`, 1px `--hairline-strong`, radius 14px, 13px/16px padding. Inside: a
24px accent circle with a 14px check (`--accent-ink`), then "saved to your camera roll" at 600
13.5px. Auto-dismisses after ~2.5s. The video keeps playing behind it.

Copy note: on desktop the same toast should read "saved to your downloads".

### 5. Empty pile — mobile (reference tile "empty")

Centred column, 40px side padding, 80px bottom padding to clear the paste bar, gap 12px:
- 54px square, radius 15px, 1px dashed `rgba(242,240,234,.24)`, containing a 22px
  clipboard-plus icon at `rgba(242,240,234,.5)`.
- "the pile is empty" — 700 22px/1.15, letter-spacing −.02em.
- "paste something in and it shows up for everyone." — 400 14px/1.45,
  `rgba(242,240,234,.55)`.

Paste bar stays exactly as on the board, minus the scrim gradient (nothing behind it).

### 6. Fetching a pasted link — mobile (reference tile "fetching")

Optimistic: the tile appears in the grid **immediately**, first position, before the scrape returns.
- Placeholder tile: `--tile`, 1px `rgba(255,255,255,.1)`, a 20px spinner centred (2px ring,
  `rgba(255,255,255,.14)`, top border `--accent`, 0.8s linear infinite), and "now" bottom-left in
  mono 9px `--accent-bright`.
- Pile count increments (47 → 48) at the same moment.
- Paste field swaps its clipboard icon for a 17px spinner and its value for "pulling it down…"
  (mono 14px, `--ink-70`); submit button is removed while in flight.
- Below the field, 10px down, the URL being fetched in mono 12px `--ink-50`, truncated.

On success the poster fades into the tile in place. On failure the tile is removed and screen 7
shows.

### 7. Bad link — mobile (reference tile "bad link")

- Grid dims to `opacity: .4` (not blurred) to push focus to the field.
- Paste field keeps the pasted URL (mono 14px, `rgba(242,240,234,.85)`, truncated), border becomes
  `--danger-border`, leading icon becomes a 17px alert circle in `--danger-icon`, and the submit
  button goes inert: `rgba(255,255,255,.08)` fill, `rgba(242,240,234,.55)` icon.
- Message row 10px below, 6px gap, wrapping: "couldn't grab that one." in `--danger-text` 500
  12.5px, then "try the share link." in `rgba(242,240,234,.55)` 400 12.5px.

Clearing or editing the field returns it to the default state.

### 8. Board — desktop (reference: `3a`)

Content width 1180px in the mock; the layout is fluid.
- Top bar, 16px/28px padding, 1px bottom border `rgba(255,255,255,.08)`, items baseline-aligned with
  22px gaps: wordmark "reels"; then "47 in the pile · no names, ever" (mono 11.5px, `--ink-50`);
  then a flexible spacer; then the paste field, 380px wide, 42px tall, `--surface`, 1px
  `rgba(255,255,255,.12)`, clipboard icon 16px, placeholder "paste a link, hit enter", and a 32px
  accent pill labelled "add" (700 12.5px, `--accent-ink`).
- Grid: `max-width: 1100px`, centred, `repeat(5, 1fr)`, gap 12px, 26px top padding, tiles
  `aspect-ratio: 9/16`, radius 8px. Below ~1100px drop to 4 then 3 columns; the mobile board is the
  3-column end of the same grid.
- Time badge: bottom-left 8px inset, mono 10px, `--scrim-badge`, 3px 7px, radius 5px.
- **Hover** on a tile: 2px `--accent` outline inset by 1px, plus a bottom-up scrim
  (`rgba(0,0,0,.62)` → transparent at 55%) carrying a 13px play triangle and "play · 5h ago"
  (600 11px, `--ink`) at 10px padding. The resting time badge is replaced by this row.

### 9. Player overlay — desktop (reference: `3b`)

Opens over the board; the board stays mounted underneath at `opacity: .28` behind a
`--scrim-overlay` wash.
- Close: 36px circle, `rgba(255,255,255,.1)`, 17px ✕, top 18px / right 22px of the window.
- Centred row, 34px vertical / 40px horizontal padding, `align-items: flex-start`, gap 28px:
  1. **Previous** — 40px circle, `rgba(255,255,255,.08)`, 1px `rgba(255,255,255,.14)`, 18px chevron;
     nudged down to sit level with the middle of the video frame.
  2. **Video column** — frame 293×520 (9:16), radius 14px, `overflow: hidden`, background `--tile`.
     12px below it the control row: "0:07" (mono 11px `--ink`), 3px scrubber, "0:27"
     (`--ink-70`), 17px volume icon, gap 12px.
  3. **Side panel** — 300px wide, top-aligned with the video frame, gap 18px:
     - Source line: 13px clock icon + "TikTok · 0:19 · gone in 6h", mono 11.5px,
       `rgba(242,240,234,.75)`.
     - Caption, 400 15px/1.45, `--ink`.
     - Action stack, gap 9px: full-width **Share to WhatsApp** (46px, accent fill, 700 14.5px, 18px
       glyph), then a 9px-gap row of **Download** and **Copy link** (44px each, transparent
       `rgba(255,255,255,.06)`, 1px `rgba(255,255,255,.2)`, 600 13.5px, 16px icons).
     - Keyboard hint: "← → to move through the pile · esc to close", mono 11px,
       `rgba(242,240,234,.5)`.
  4. **Next** — mirror of Previous.

Note the deliberate difference from mobile: desktop keeps the chrome and the caption permanently
visible in the side panel, so there is no tap-to-reveal state. The video frame must stay inside the
viewport with visible ground above and below — size it from available height (`min(520px, 74vh)`),
not a fixed value, when the window can be short.

---

## Interactions & behaviour

**Navigation.**
- Board tile → player. Mobile: full-screen route (push), back button / ✕ returns to the board at the
  same scroll position. Desktop: overlay route, board stays mounted; ✕ or `Esc` closes.
- Player → next/previous: mobile vertical swipe (and the hint says so); desktop `←`/`→` and the two
  arrow buttons. Order matches the board's order.

**Chrome reveal (mobile player).** Tap the video → chrome in; tap again → out. Fade + 4px rise over
~160ms, `ease-out`. Optional auto-hide after 3s of no interaction. Do not put the share actions
behind a "⋯" — the tap-anywhere reveal is the intended gesture.

**Paste.** Mobile: the bottom field is always mounted; submit on the arrow or the keyboard's Go.
Desktop: Enter in the field, or the "add" pill. On submit, optimistic tile + spinner in field
(screen 6), then success (poster fades in, 200ms) or failure (screen 7). A pasted link that already
exists in the pile should resolve to the existing tile rather than duplicating it.

**Share.** `navigator.share({ url })` where available; otherwise the WhatsApp web deep link. Copy
link writes the reel URL to the clipboard and shows the same toast pattern with "link copied".

**Save.** Triggers a download of the video file, then the toast. If the download can take more than
about a second, swap the Save button's icon for the spinner until it resolves.

**Expiry.** The source line carries "gone in 6h" — reels age out of the pile. Tiles whose expiry has
passed disappear on next load; nothing in the UI counts down per tile.

**Responsive.** One layout, two ends: the grid goes 5 → 4 → 3 columns; the paste field moves from the
top bar to a fixed bottom bar below ~700px; the player switches from centred overlay to full-bleed
with tap-to-reveal at the same breakpoint.

**Motion.** Sparse and short. Fades and small translations, 160–220ms, `ease-out`. The only looping
motion is the fetch spinner. No parallax, no tile entrance animations.

---

## State management

Global / route state:
- `reels: Reel[]` — `{ id, url, source: 'tiktok' | 'instagram', posterUrl, videoUrl, caption,
  durationSec, createdAt, expiresAt }`. Sorted by `createdAt` descending. No author field — do not
  store or render one.
- `pileCount` — derived from `reels.length`.
- `openReelId: string | null` — drives the player route/overlay.

Player-local:
- `chromeVisible: boolean` (mobile only), `playing`, `positionSec`, `muted`.
- `saveState: 'idle' | 'saving' | 'saved'`, `toast: string | null`.

Paste-local:
- `pasteValue: string`, `pasteState: 'idle' | 'fetching' | 'error'`, `pendingReel` (the optimistic
  tile, replaced by the server record on success and dropped on failure).

Data: a reads-mostly list endpoint plus a create endpoint that takes a URL, scrapes poster + video +
caption + duration server-side, and returns the record. Consider subscribing to new records so a
friend's drop appears without a refresh — the "47 in the pile" count is the natural place for that
to show.

---

## Assets

- **Font:** Bricolage Grotesque, Google Fonts, weights 400/600/700/800 (variable, `opsz 12..96`).
  Monospace is the system stack — no webfont.
- **Icons:** the reference draws its own 24×24 strokes at 1.75px, round caps and joins. Replace with
  **Lucide**: `clipboard`, `clipboard-plus`, `arrow-up`, `x`, `clock`, `volume-2`, `download`,
  `link-2`, `check`, `alert-circle`, `chevron-left`, `chevron-right`, `play`. The WhatsApp mark in
  the reference is a simplified glyph — use the official brand asset (or Simple Icons' `whatsapp`).
- **Imagery:** none shipped. Every thumbnail and player frame is a video poster from the scraped
  reel. In the reference these are `<image-slot>` drop targets; a dropped file persists in
  `.image-slots.state.json` beside the HTML. That file and `image-slot.js` are mockup plumbing, not
  part of the design.
- **No logo file.** The wordmark is live text: "reels", Bricolage Grotesque 700, −.03em.

## Files

- `Reels Dump.dc.html` — the design. Section `3` (top) holds the two desktop views; section `2`
  holds the seven mobile views. Ignore the `.dv-*` presentation wrappers, the phone bezels and the
  browser chrome.
- `image-slot.js`, `browser-window.jsx`, `support.js` — mockup runtime (drop-target placeholders,
  simulated browser chrome, the component runtime the HTML file needs to render). Not part of the
  product.
