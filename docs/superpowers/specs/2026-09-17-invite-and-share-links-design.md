# Invite Link and Share Links — Design

Date: 2026-09-17
Status: approved design, pre-implementation
Builds on: `2026-09-16-reels-download-api-design.md` (the "API spec"),
`2026-09-16-mobile-web-page-design.md` (the "web spec") and
`2026-09-16-reels-board-ui-design.md` (the "board spec")

## 1. Purpose

Make the board easier to get into without making it public.

- **Invite link.** The owner pins one link in the friends' WhatsApp group.
  Tapping it logs a phone in, the same as typing the passcode. The
  passcode stays as the fallback.
- **Share links.** A reel shared out of the board opens for anyone who
  taps it, including people with no cookie. They see that one reel on a
  view-only page and can save it. They never see the pile.
- **Link previews.** A shared reel shows its thumbnail and caption in
  WhatsApp.
- **Bigger pile.** The board keeps up to 100 reels.

People who already have the cookie go straight to the board, as today.

Out of scope: per-person invites or removing one person, an invite button
on the board, Share or Copy link on the view-only page, a preview image for
the invite link, changing the invite token without a restart, keeping the
pile across restarts, new Python or JS dependencies.

## 2. Constraints

Everything in web spec section 2 and board spec section 2 still holds
(HTTPS, iOS fresh-tap rule, in-memory jobs, same origin, no build step, no
framework, dark only). Additionally:

- **Link preview fetchers do not run JavaScript and carry no cookie.**
  WhatsApp builds the preview on the sender's phone with its own HTTP
  client. The preview tags must therefore be in the HTML the server sends
  to a request without a cookie.
- **A share link must never grant access to the pile.** Otherwise anyone
  holding one shared reel gets the board, and the passcode and invite link
  protect nothing.
- **Jobs live in memory.** A reel's share key disappears with the reel. A
  restart ends every share link, which is acceptable because reels only
  live `RETENTION_HOURS` anyway.

## 3. Configuration

| variable       | default | meaning |
|----------------|---------|---------|
| `INVITE_TOKEN` | unset   | Secret part of the invite link. Unset or empty disables `/join`. At least 16 characters when set. |
| `MAX_VIDEOS`   | `100`   | Was `10`. Most finished reels kept at once; the oldest is deleted first. |

`Settings` gains `invite_token: str | None = None`. An empty string is
turned into `None` before validation, so `INVITE_TOKEN=` in `.env` means
unset. A set value shorter than 16 characters fails validation, so the app
refuses to start. `.env.example` gains:

```
# Secret for the invite link https://<site>/join/<token>. Empty disables it.
# Generate one with: openssl rand -hex 16
INVITE_TOKEN=
```

and changes `MAX_VIDEOS=10` to `MAX_VIDEOS=100`.

The invite link, like the rest of the web page, exists only when
`WEB_PASSCODE` is set (web spec section 3).

## 4. Share keys

### 4.1 Key per reel

`Job` gains `share_key: str`, filled at creation by `new_share_key()` in
`models.py`: `secrets.token_urlsafe(12)`, 16 URL-safe characters (96 bits).
Every job gets one; it is never changed. A pasted link that resolves to an
existing job (board spec 3.3) returns that job, so it keeps its key.

### 4.2 Job JSON

`job_to_dict` adds `"share_key"` for done jobs only. Queued, downloading,
processing and failed jobs do not include it. The JSON is only served to
requests with the API key or the cookie, so the key is only visible to
people already inside.

### 4.3 Share link

A reel's share link is `<origin>/?reel=<id>&k=<share_key>`. It replaces
`/?reel=<id>` (board spec section 4) everywhere the board produces a link:
Share, Copy link, and the address bar while the player is open. A reel
object without `share_key` falls back to `/?reel=<id>`.

The keyless form keeps working for people with the cookie and is what the
view-only page's login hint uses (section 6.1).

## 5. Server

### 5.1 `GET /`

*(Superseded by `2026-09-17-cookie-ask-on-board-design.md` section 4: only
an agreed cookie gets the board in row 1, and in rows 2 and 4 a cookie set
before the login page asked gets the board with the cookie pop-up.)*

Checked in order. `reel` and `k` are the query parameters.

| # | condition | response |
|---|-----------|----------|
| 1 | cookie valid | `app.html`, unchanged. The page reads `?reel=` as today and ignores `k`. |
| 2 | `reel` or `k` missing or empty | `login.html` |
| 3 | no job with id `reel` | expired page (section 6.2) |
| 4 | `k` does not equal the job's `share_key` (`secrets.compare_digest` on bytes) | `login.html` |
| 5 | job is not done, has no result, or its video file is missing | expired page |
| 6 | otherwise | view-only page (section 6.1) |

All responses are `200` with `Cache-Control: no-store`, as `GET /` is
today. Row 4 deliberately shows the login page rather than the expired
page, so a guessed key gets no different answer from no key.

### 5.2 Files

`GET /files/{id}.mp4` and `GET /files/{id}.jpg` accept access in any of
these forms:

1. a valid `X-API-Key` header,
2. a valid session cookie,
3. a query parameter `k` equal to that job's `share_key`.

These two routes move out of the `protected` router and check access
themselves. Order of checks:

- No valid key or cookie, and `k` missing, empty, for an unknown job or not
  equal to the job's key: `401` with the existing `unauthorized` body.
- Access granted but the job is not done, has no result or the file is
  missing: `404 not_found`, as today.

`k` is accepted on these two routes only. `GET /jobs`, `GET /jobs/{id}` and
`POST /jobs` ignore it and still require the key or the cookie.

Response headers are unchanged: the video is an attachment named after the
title, the thumbnail has `Cache-Control: private, max-age=21600`.

### 5.3 `GET /jobs`

Returns every done job in the store, newest first, instead of the newest
50. `enforce_video_cap` already limits this to `MAX_VIDEOS`.

### 5.4 `GET /join/{token}`

*(Superseded by `2026-09-17-cookie-consent-design.md` 5.1 and 5.2: `GET`
serves the login page in invite mode and never sets the cookie;
`POST /join/{token}` sets it.)*

Registered by `web.install` only when `INVITE_TOKEN` is set. When
`INVITE_TOKEN` is unset, or `WEB_PASSCODE` is unset (so `web.install` is not
called), the route returns `404`.

Uses the login attempt limiter (web spec 4.3) keyed by client IP:

| case | response |
|------|----------|
| IP is blocked | `303` to `/`, no cookie. The token is not checked. |
| token equals `INVITE_TOKEN` (`secrets.compare_digest` on bytes) | `303` to `/` with the session cookie, same value and attributes as `POST /web/login` sets. Clears the IP's failures. |
| token is wrong | `303` to `/`, no cookie. Records a failure for the IP. |

Every response sends `Cache-Control: no-store`. The redirect removes the
token from the address bar. The cookie-setting code in `POST /web/login`
moves into one helper that both routes use.

Changing `INVITE_TOKEN` needs a restart, which empties the pile. People
already logged in stay logged in, because the cookie value depends only on
`API_KEY` and `WEB_PASSCODE`. Changing `WEB_PASSCODE` still logs everyone
out.

## 6. Pages

Both new pages are HTML files in `reels_api/static/` with `{{name}}`
placeholders. `web.py` reads the file, replaces each placeholder with an
HTML-escaped value (`html.escape` with `quote=True`), and returns it. No
template engine. A test checks that no `{{` is left in a rendered page.

Both pages include `<meta name="referrer" content="strict-origin-when-cross-origin">`,
so the Google Fonts request never carries the key, and
`<meta name="robots" content="noindex">`.

Absolute URLs (preview tags) use `PUBLIC_BASE_URL` without a trailing
slash when set, otherwise the request's base URL. Behind Caddy that is
`https://<site>` because uvicorn runs with `--proxy-headers`.

### 6.1 View-only page: `watch.html`

Rendered for row 6 of section 5.1.

**Head.** Same fonts, stylesheet, `color-scheme`, `theme-color` and viewport
as `app.html`. No manifest, no service worker, no Apple web-app tags.
`<title>` and the preview tags of section 7.1. Loads
`<script type="module" src="/static/watch.js">`.

**Reel data.** One `<script type="application/json" id="reel-data">` holding
`job_to_dict(job)` with `file_url` and `thumbnail_url` rewritten to carry
`?k=<share_key>` (`thumbnail_url` stays `null` when there is no thumbnail).
The URLs are relative. The JSON is written with `<`, `>` and `&` replaced by
`<`, `>` and `&`, so a caption cannot close the script tag.

**Body.** The player block from `app.html` (board spec 5.2), with these
differences:

- Removed: `.player-close-desktop`, both `.player-nav` buttons, the phone
  close button in `.chrome-top`, the Share and Copy link buttons in
  `.actions`, and the "Share to WhatsApp" and "Copy link" buttons in
  `.player-panel`.
- Kept: video, idle bar, source line, caption, scrubbers, volume buttons,
  Save (phone) and Download (desktop panel).
- The idle hint reads "tap for options", without the arrow icon.
- A login hint below Save in `.actions` and below the panel actions:
  `<a class="login-hint" href="/?reel={{id}}">have the passcode? <u>log in</u></a>`.
  Logging in reloads with `?reel=<id>`, so the board opens on this reel.
- `#toast` as in `app.html`, for the Save toasts.

The removed elements are absent from the markup, not hidden.

**Behaviour.** `watch.js` reads `#reel-data`, hydrates icons, creates the
player with `standalone: true` (section 8) and opens the reel with
`gesture: false`, so it starts muted (board spec 7.1).

If the video fails to load, `watch.js` checks whether the reel still exists
with `fetch(file_url, { headers: { Range: "bytes=0-0" } })`:

- `401` or `404`: the reel was deleted while open. The page reloads and the
  server answers with the expired page.
- Any other status, or a network error: the page stays and shows the error
  toast "couldn't play that one". It does not reload, so a clip the browser
  cannot play never causes a reload loop.

**Styles.** `style.css` gains `.login-hint`: 12.5px, `--ink-50`, centred on
phones and left-aligned in the desktop panel, underline on "log in", tap
target at least 36px high. The desktop layout otherwise uses the existing
overlay styles; with nothing behind it the backdrop sits on `--bg`.

### 6.2 Expired page: `expired.html`

Rendered for rows 3 and 5 of section 5.1. Uses the login page's layout and
styles (`body.login`, `.login-box`, `.wordmark`, `.login-lead`):

- wordmark "reels"
- "this reel has expired"
- "reels only stay up for {{hours}}", where `hours` is `RETENTION_HOURS`
  formatted with `:g` plus " hour" or " hours" (`12` → "12 hours",
  `1` → "1 hour", `1.5` → "1.5 hours")
- a link "have the passcode? log in" to `/`

Preview tags as in section 7.2. No JavaScript.

## 7. Link previews

### 7.1 View-only page

| tag | value |
|-----|-------|
| `og:title` | The caption (`caption` from the job JSON) with runs of whitespace collapsed to one space and trimmed. Over 100 characters: the first 99 plus "…". Empty: "a reel". |
| `og:description` | Source name and duration: "TikTok · 0:19". "Instagram" for Instagram. Duration as `m:ss`, floored; left out with its separator when unknown. No expiry, because WhatsApp caches previews. |
| `og:image` | `<base>/files/<id>.jpg?k=<share_key>`. The tag is left out when the reel has no thumbnail. |
| `og:url` | `<base>/?reel=<id>&k=<share_key>` |
| `og:type` | `video.other` |
| `og:site_name` | `reels` |

`<title>` has the same text as `og:title`. The thumbnail is a 360px-wide
JPEG of a few tens of KB, within WhatsApp's preview limits.

### 7.2 Other pages

- `expired.html`: `og:title` "reels", `og:description` "this reel has
  expired", `og:site_name` "reels".
- `login.html` and `app.html` (the invite link redirects to one of them):
  static tags `og:title` "reels", `og:description` "reels your friends
  pasted. no names, ever.", `og:type` "website", `og:site_name` "reels".
  No image. `login.html` and `app.html` also get `robots` `noindex`.

## 8. Player

`createPlayer({ root, onGone, standalone = false })`.

**Board mode** (`standalone: false`) behaves as board spec section 7, except
links: the path pushed or replaced in history, Share, Copy link and the
WhatsApp button all use the share link of section 4.3, built from the
current reel's `share_key`.

**Standalone mode** (`standalone: true`):

- No history calls. `open` does not `pushState` or `replaceState`; the
  address keeps `k`.
- Escape does nothing. `close` is not reachable from the page.
- Vertical drags do not move the frame and never change reel. A tap still
  toggles the chrome.
- ← and → do nothing (there is one reel).
- Missing elements are tolerated: no close, nav, share, copy or WhatsApp
  buttons. On desktop, `open` focuses the Download button instead of the
  missing close button.
- Save works as in board spec 7.4: on iOS the file is fetched while the reel
  plays and Save opens the share sheet; elsewhere Save downloads and shows
  "saved to your downloads". Both use the `?k=` URLs from the reel data.
- `onGone` is called on a video error as in board mode, without closing the
  player; `watch.js` passes the check described in section 6.1.

## 9. Dev server

`scripts/dev_board.py`:

- Sets `invite_token="dev-invite-token-0000"`.
- After seeding, prints the invite link
  `http://localhost:<port>/join/dev-invite-token-0000` and, unless
  `--empty`, the share link of the newest seeded reel.

## 10. Code layout

```
reels_api/
  settings.py     invite_token (empty → None, min 16); max_videos default 100
  models.py       new_share_key(); Job.share_key; share_key in job_to_dict for done jobs
  jobs.py         list_recent returns all done jobs by default
  routes.py       file routes check key, cookie or k (5.2); GET /jobs returns all (5.3)
  auth.py         shared helper for "valid API key or cookie" used by require_access and the file routes
  web.py          GET / routing (5.1), GET /join (5.4), page rendering (6, 7), set-cookie helper
  static/
    watch.html    view-only page (6.1)
    expired.html  expired page (6.2)
    watch.js      reads reel data, opens the standalone player
    player.js     standalone option; share links with k (8)
    app.html      static preview tags, robots noindex
    login.html    static preview tags, robots noindex
    style.css     .login-hint
scripts/
  dev_board.py    invite token, prints links (9)
.env.example      INVITE_TOKEN, MAX_VIDEOS=100
README.md         invite link, share links, previews, new settings
CLAUDE.md         GET / routing, share_key, server-rendered previews, player markup in two pages
```

The player markup now lives in both `app.html` and `watch.html`. A change
to one must be mirrored in the other; CLAUDE.md says so.

## 11. Testing

### 11.1 Automated (pytest, no network, no ffmpeg)

- **Keys:** every new job has a 16-character URL-safe `share_key`; two jobs
  get different keys; a done job's JSON includes it; queued and failed jobs'
  JSON do not; submitting the same URL twice returns the same key.
- **Files:** with `k` equal to the reel's key and no cookie or API key,
  `/files/<id>.mp4` and `/files/<id>.jpg` return 200; a wrong `k`, an empty
  `k`, another reel's key, and a `k` for an unknown id return 401; the API
  key and the cookie still work without `k`; with a valid key but a missing
  file the response is 404.
- **`k` stays narrow:** `GET /jobs`, `GET /jobs/{id}` and `POST /jobs` with a
  valid `k` and no key or cookie return 401.
- **`GET /jobs`:** with 60 done jobs and `max_videos=100`, returns 60.
- **`GET /` routing,** one test per row of section 5.1:
  - cookie plus `reel` and `k` → `app.html`;
  - no `k`, empty `k` → login page;
  - unknown reel with a `k` → expired page containing "12 hours" for the
    default retention and "1 hour" with `retention_hours=1`;
  - wrong `k` → login page;
  - failed job with its key, and done job whose file was deleted → expired
    page;
  - right `k` → view-only page, `no-store`, containing the reel data JSON
    with `?k=` in `file_url` and `thumbnail_url`, and loading `watch.js` as a
    module.
- **Escaping:** a caption containing `<script>`, `</script>`, `"` and `&`
  appears escaped in `<title>`, `og:title` and the reel data JSON, and the
  JSON parses back to the original caption. No `{{` remains.
- **Preview tags:** `og:title` truncation at 100 characters and "a reel"
  fallback; `og:description` for TikTok and Instagram, with and without a
  duration; no `og:image` when there is no thumbnail; `og:image` and
  `og:url` use `PUBLIC_BASE_URL` when set (a trailing slash is not
  doubled) and the test client's base URL otherwise.
- **Invite link:** right token → 303 to `/` with a cookie matching
  `test_login_success_sets_cookie`'s attributes, and that cookie opens
  `GET /jobs`; wrong token → 303 without a cookie; ten wrong tokens then the
  right one → 303 without a cookie; a wrong passcode and a wrong token count
  toward the same limit; route 404 when `invite_token` is unset and when
  `web_passcode` is unset.
- **Settings:** `max_videos` defaults to 100; `invite_token` defaults to
  `None`; `INVITE_TOKEN=""` gives `None`; a 15-character token raises; a
  16-character token is kept.
- **Static:** `watch.js` is added to `APP_MODULES` (served as
  `text/javascript`, `no-cache`); `login.html` and `app.html` contain the
  static `og:title`.
- **Dev server:** seeded jobs have share keys.

### 11.2 Manual, in Chrome, against `scripts/dev_board.py`

At 390×844 (device emulation, touch) and 1280×800:

- Invite link in a private window → board. A wrong token → login page.
- Newest reel's share link in a private window → view-only page: starts
  muted, unmute works, tap toggles the chrome, dragging does not move the
  frame, Esc does nothing, scrubber seeks, Save shows the download toast, the
  login hint leads to the login page and after `dev` the board opens on that
  reel.
- `/?reel=nope&k=x` → expired page.
- In the logged-in window: Share (with `navigator.share` missing, the
  `wa.me` fallback), Copy link and the address bar with a reel open all
  contain `&k=`.
- View source of the share link page: preview tags present and filled.

### 11.3 On real devices after deploy (owner)

- In WhatsApp, a shared reel shows its thumbnail and caption.
- A phone that has never logged in opens a shared reel on the view-only
  page; on iPhone, Save → "Save Video" puts it in Photos.
- The pinned invite link logs a new phone in.

## 12. Deploy

On the VM, in `~/reels/.env`:

- `INVITE_TOKEN=<openssl rand -hex 16>`
- `MAX_VIDEOS=100`
- `RETENTION_HOURS=12` (from the hourly-sweep change, not yet on the VM)

Then `.\scripts\deploy.ps1` from the PC. The restart empties the pile. Pin
`https://<site>/join/<token>` in the group.

Disk: 100 reels at about 5 MB each is about 500 MB.

## 13. Security notes

- A share key is 96 random bits and only works for one reel's page, video
  and thumbnail, for as long as that reel exists. Anyone the link is
  forwarded to can watch and save that reel, by design.
- The invite link grants the same access as the passcode. Anyone it is
  forwarded to gets in. Guessing is limited by the shared attempt limiter,
  and a 16-character minimum makes it impractical anyway.
- Keys and tokens appear in the app's access logs as part of request URLs.
  The logs stay on the VM.
- The referrer policy keeps the key out of requests to Google Fonts.
  *(The font is now served by the app, cookie spec 7, so no page makes
  such requests.)*
