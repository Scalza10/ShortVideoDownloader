# Cookie Consent — Design

Date: 2026-09-17
Status: approved design, pre-implementation
Builds on: `2026-09-16-mobile-web-page-design.md` (the "web spec"),
`2026-09-16-reels-board-ui-design.md` (the "board spec") and
`2026-09-17-invite-and-share-links-design.md` (the "links spec")

## 1. Purpose

Aim for EU/GDPR compliance on the phone page:

- **Ask before the login cookie is set.** The login page and the invite link
  explain the one cookie and set it only after the person agrees.
- **Remember the answer.** A "yes" is the login cookie itself. A "no" is
  remembered in the browser, so the person is not asked on every visit.
- **Declining still works.** Someone who says no can open any share link on
  the view-only page, which stores nothing.
- **Withdrawing is as easy as agreeing.** The board gets a log out that
  deletes the cookie.
- **No requests to other sites.** The font is served by the app instead of
  Google Fonts, so no page sends the visitor's IP address to Google.

Out of scope (section 11): a privacy policy page, IP addresses in the app's
access logs, remembering a "yes" before logging in, the server checking
consent, logging out other phones. *(The server now tells an agreed cookie
from an older one: `2026-09-17-cookie-ask-on-board-design.md`.)*

## 2. Constraints

Everything in web spec section 2, board spec section 2 and links spec
section 2 still holds (HTTPS, iOS fresh-tap rule, in-memory jobs, same
origin, no build step, no framework, no JS dependencies, dark only).
Additionally:

- **What is stored today.** One cookie, `reels_session`, set only by
  `POST /web/login` and `GET /join/{token}`. No page script uses
  `localStorage`, `sessionStorage` or `document.cookie`. The view-only and
  expired pages set nothing.
- **The login cookie is shared.** Its value is one HMAC of `API_KEY` and
  `WEB_PASSCODE` (web spec 4.2). Deleting it on one phone cannot log out any
  other phone.
- **Link preview fetchers only GET.** WhatsApp fetches the invite link to
  build its preview. A GET must not log anything in.
- **iOS Safari may clear script storage** after about seven days without a
  visit. A remembered "no" can be forgotten, and the person is asked again.
  That errs toward asking, which is acceptable.

## 3. Saving the choice

| answer | where it is kept | set by | removed by |
|--------|------------------|--------|------------|
| yes | the `reels_session` cookie (unchanged value and attributes, one year) | `POST /web/login`, `POST /join/{token}` | log out (section 6), clearing site data |
| no | `localStorage["reels-cookie-choice"] = "declined"` | "no thanks" (4.1, 4.3) | "changed my mind" (4.2), a successful login or join, clearing site data |

- The "no" is never sent to the server. Only the login page script reads it.
- Every `localStorage` access is wrapped in `try`/`catch`. When storage
  throws (private windows, blocked site data), "no thanks" still shows the
  declined state for this visit, and the page otherwise behaves as if
  nothing is saved.
- The server does not check consent. Pressing "allow cookie & log in" or
  "allow cookie & join" is the agreement. Clients using `X-API-Key` are
  unaffected.
- People already logged in when this ships keep their cookie. Nobody is
  logged out by the deploy. *(They are now asked on the board:
  `2026-09-17-cookie-ask-on-board-design.md`.)*

## 4. Login page

`login.html` and `login.js` stay a separate non-module page (web spec
section 8). The page has two states, **asking** and **declined**, and two
modes, **passcode** (served at `/`) and **invite** (served at
`/join/{token}`). `login.js` runs at the end of `<body>` and sets the state
and mode before the first paint.

### 4.1 Asking, passcode mode

Shown at `/` (web spec 4.1, links spec 5.1 rows 2 and 4) when no "no" is
saved.

```
reels
enter the passcode
[ passcode              ]
one cookie keeps this phone logged in for a year.
nothing else is stored. no tracking, no ads.
you can log out from the board any time.
[ allow cookie & log in ]
<error text, when there is one>
no thanks
```

- The notice sits between the field and the button, so it is read before
  agreeing.
- **allow cookie & log in** submits the form: `POST /web/login` as today,
  same error handling (wrong passcode, rate limit, network error). On `204`
  it removes `reels-cookie-choice`, then `location.reload()`, keeping the
  query string (web spec 4.1).
- **no thanks** saves `"declined"` and switches to the declined state
  (4.2). It is a `type="button"`, so it never submits the form.
- The passcode field loses its `autofocus` attribute. `login.js` focuses it
  when it shows the asking state, so a hidden field never takes focus.

### 4.2 Declined

Shown at `/` when `reels-cookie-choice` is `"declined"`, and after "no
thanks" in passcode mode.

```
reels
no cookie, no login
reels friends share with you still open without one.
changed my mind
```

- **changed my mind** removes `reels-cookie-choice`, switches to the asking
  state and focuses the passcode field.
- The view-only page's "have the passcode? log in" link and the expired
  page's link lead to `/`, which shows this state when a "no" is saved.

### 4.3 Invite mode

Used when `location.pathname` starts with `/join/`. The server only serves
the page there for a right token (5.1). Always starts in the asking state,
even when a "no" is saved: opening an invite link is a fresh request.

```
reels
you're invited
one cookie keeps this phone logged in for a year.
nothing else is stored. no tracking, no ads.
you can log out from the board any time.
[ allow cookie & join ]
<error text, when there is one>
no thanks
```

- The passcode field is hidden and `disabled`, so the form submits without
  it.
- **allow cookie & join** sends `POST <location.pathname>` with no body.
  - `204`: removes `reels-cookie-choice`, then `location.replace("/")`. The
    token leaves the address bar and the history entry.
  - Any other status: shows the response's `message` under the button, or
    "Something went wrong. Try again." when the body is not JSON. A network
    error shows "Network error. Try again."
- **no thanks** saves `"declined"`, then `location.replace("/")`, which
  shows the declined state (4.2).

### 4.4 Markup and styles

`login.html` body:

- `.login-box` holds the wordmark and two sections: `#ask` and `#declined`
  (`hidden`). Visibility is toggled with `el.hidden`.
- `#ask`: `<p id="login-lead" class="login-lead">enter the passcode</p>`,
  then `#login-form` with `#passcode`, a `<p class="login-note">` with the
  three notice lines, `#continue` (text "allow cookie & log in"),
  `#login-error`, and `<button id="decline" class="login-hint"
  type="button"><u>no thanks</u></button>`.
- `#declined`: `<p class="login-lead">no cookie, no login</p>`,
  `<p class="login-note">reels friends share with you still open without
  one.</p>` and `<button id="reconsider" class="login-hint"
  type="button"><u>changed my mind</u></button>`.
- Invite mode changes `#login-lead` to "you're invited" and `#continue` to
  "allow cookie & join".

`style.css`:

- `.login-note`: 13px, `--ink-50`, line-height 1.45. It replaces
  `.expired-note`, which `expired.html` switches to (same size and colour).
- `button.login-hint`: no background, no border, no padding, inherits the
  `.login-hint` font and colour, `cursor: pointer`, left-aligned in
  `.login-box`.
- `#ask` and `#declined` are flex columns with the same 14px gap as
  `.login-box`.

The preview tags of `login.html` (links spec 7.2) are unchanged. An invite
link's WhatsApp preview therefore looks as it does today.

## 5. Server

### 5.1 `GET /join/{token}`

Replaces links spec 5.4. Registered by `web.install` only when
`INVITE_TOKEN` is set; `404` otherwise and when `WEB_PASSCODE` is unset, as
today. Checked in order:

| # | case | response |
|---|------|----------|
| 1 | session cookie valid | `303` to `/`. The token is not checked, no failure is recorded. |
| 2 | IP is blocked | `303` to `/`, token not checked |
| 3 | token is wrong | `303` to `/`, records a failure for the IP |
| 4 | token is right (`secrets.compare_digest` on bytes) | `200` `login.html` |

No response sets a cookie. Every response sends `Cache-Control: no-store`.
Row 4 does not clear the IP's failures; only a successful POST does.

### 5.2 `POST /join/{token}`

New, registered next to the GET under the same conditions. No request body.
Uses the same limiter:

| # | case | response |
|---|------|----------|
| 1 | IP is blocked | `429 {"error": "too_many_attempts", "message": "Too many wrong tries. Wait 15 minutes and try again."}`, token not checked |
| 2 | token is wrong | `401 {"error": "invalid_invite", "message": "That invite link is not right."}`, no cookie, records a failure |
| 3 | token is right | `204` with the session cookie (`_set_session_cookie`, same as `POST /web/login`), clears the IP's failures |

Every response sends `Cache-Control: no-store`. Wrong passcodes and wrong
tokens, by GET or POST, count toward the one per-IP limit.

A cross-site POST cannot log a phone in without knowing the token, so no
extra CSRF check is needed.

### 5.3 `POST /web/logout`

New, in the web router (so it exists only when `WEB_PASSCODE` is set).
Depends on `require_access`.

- With a valid cookie (or API key): `204`, and
  `response.delete_cookie(SESSION_COOKIE, path="/", secure=True,
  httponly=True, samesite="lax")`, which sends the cookie with an empty
  value and `Max-Age=0`.
- Without access: `401` with the existing `unauthorized` body and no
  `Set-Cookie`. A cross-site POST carries no `SameSite=Lax` cookie, so it
  gets this `401` and cannot log a phone out.

The cookie value is shared, so this only removes the cookie from the phone
that asked. Everyone else stays logged in. Replaces the web spec's "There is
no logout endpoint" line.

## 6. Board footer

`app.html` gains, as the last child of `main.board` after `#empty`:

```html
<footer class="board-foot">
  <span>one cookie keeps you logged in</span>
  <span aria-hidden="true">·</span>
  <button id="logout" class="login-hint" type="button"><u>log out</u></button>
</footer>
```

- `api.js` gains `logout()`: `api("/web/logout", { method: "POST" })`. A
  `401` already reloads the page through `api()`.
- `app.js` wires `#logout`: disable the button, call `logout()`, then
  `location.replace("/")`, which serves the login page in the asking state.
  Logging out does not save a "no". On a network error it re-enables the
  button and shows the error toast "couldn't log out. try again."
- Styles: `.board-foot` is a centred row of 12.5px `--ink-50` text with a
  small gap, 24px above it. It must be readable and tappable on the full
  board and on the empty board, on phones (above the fixed paste bar,
  clear of the safe area) and on desktop.

## 7. Self-hosted font

- Add `reels_api/static/fonts/` with Bricolage Grotesque as served today by
  the Google Fonts request in the pages (variable, `opsz` 12..96, `wght`
  400..800), downloaded once as woff2:
  - `bricolage-grotesque-latin.woff2`
  - `bricolage-grotesque-latin-ext.woff2`
  - `OFL.txt`, the SIL Open Font License the font ships under.

  Google splits the variable font by character set. The files and their
  `unicode-range` values are copied from the Google CSS response for the
  `latin` and `latin-ext` blocks (requested with a browser user agent so it
  returns woff2). Other character sets (Vietnamese) are left out. If Google
  returns a single file for both, ship that one file with one rule and no
  `unicode-range`.
- `style.css` gains two `@font-face` rules at the top, one per file:
  `font-family: "Bricolage Grotesque"`, `font-style: normal`,
  `font-weight: 400 800`, `font-display: swap`, the `unicode-range` from
  Google, and `src: url("/static/fonts/<file>") format("woff2")`. `--font` is
  unchanged. Optical sizing stays automatic (`font-optical-sizing: auto`
  is the default).
- Remove the two `preconnect` links and the Google stylesheet link from
  `app.html`, `login.html`, `watch.html` and `expired.html`.
- `NoCacheStaticFiles` forces `Content-Type: font/woff2` for `.woff2`, as it
  does `text/javascript` for `.js`. The venv's Python 3.12 `mimetypes`
  returns no type for `.woff2`.
- The design handoff names Google Fonts as the source. The font is the same;
  only where it is served from changes, so this spec wins (CLAUDE.md).

After this, no page requests anything from another site.

## 8. Code layout

```
reels_api/
  web.py              GET /join (5.1), POST /join (5.2), POST /web/logout (5.3), .woff2 content type (7)
  static/
    login.html        #ask / #declined sections, notice, no thanks, changed my mind (4.4)
    login.js          states, invite mode, reels-cookie-choice (3, 4)
    app.html          board footer (6)
    app.js            log out button (6)
    api.js            logout() (6)
    style.css         @font-face, .login-note, button.login-hint, .board-foot (4.4, 6, 7)
    expired.html      .login-note, no Google Fonts
    watch.html        no Google Fonts
    fonts/            two woff2 files and OFL.txt (7)
tests/
  test_web.py         section 9.1
README.md             getting in, the cookie notice, log out, self-hosted font
CLAUDE.md             auth (GET/POST invite, reels-cookie-choice, log out), .woff2 content type
docs/superpowers/specs/
  2026-09-16-mobile-web-page-design.md       pointer to this spec where it says there is no logout
  2026-09-17-invite-and-share-links-design.md pointer to this spec from 5.4 and from the Google Fonts note in 13
```

## 9. Testing

### 9.1 Automated (pytest, no network, no ffmpeg)

- **Invite GET:** right token → `200`, login page (`id="passcode"`),
  `no-store`, no `Set-Cookie`; valid cookie plus any token → `303` to `/`
  and no failure recorded; wrong token → `303` to `/`, no cookie, failure
  counted; blocked IP with the right token → `303`, no cookie.
- **Invite POST:** right token → `204`, `Set-Cookie` with the same value and
  attributes as `test_login_success_sets_cookie`, and that cookie opens
  `GET /jobs`; it clears failures (nine wrong, right, nine wrong still
  `401`); wrong token → `401` `invalid_invite` body, no cookie; ten wrong
  then right → `429` `too_many_attempts`, no cookie; `no-store` on every
  response.
- **Shared limit:** wrong passcodes, wrong GET tokens and wrong POST tokens
  count toward one limit.
- **404s:** `GET` and `POST /join/{token}` return `404` when `invite_token`
  is unset and when `web_passcode` is unset.
- **Log out:** with the cookie → `204` and a `Set-Cookie` for
  `reels_session` with `Max-Age=0`, `Path=/`, `Secure`, `HttpOnly`,
  `SameSite=Lax`, after which `GET /` serves the login page; without the
  cookie → `401`, no `Set-Cookie`; `404` when `web_passcode` is unset.
- **Pages:** the login page contains the three notice lines, `id="decline"`,
  `id="declined"` and `id="reconsider"`; `app.html` contains
  `id="logout"`.
- **No Google Fonts:** `app.html`, `login.html`, a rendered view-only page
  and a rendered expired page contain neither `fonts.googleapis.com` nor
  `fonts.gstatic.com`.
- **Font files:** both woff2 files are served with `font/woff2` and
  `no-cache`; `OFL.txt` is served; `style.css` references both files.

### 9.2 Manual, in Chrome, against `scripts/dev_board.py`

In a private window, at 390×844 (device emulation, touch) and 1280×800:

1. `/` asks. **no thanks** → declined. Reload → still declined.
   **changed my mind** → asks, with the passcode field focused.
2. Log in with `dev` → board. The footer is visible at the end of the grid
   and on the empty board (`--empty`), clear of the paste bar on phones.
   **log out** → login page asking; DevTools shows no `reels_session`.
3. The printed invite link → invite mode, no passcode field, no cookie yet.
   **allow cookie & join** → board, address bar `/`, Back does not return to
   the invite page.
4. **no thanks** in step 1, then the invite link → it asks. **no thanks** →
   `/` in the declined state.
5. The printed share link → view-only page with no notice.
6. On every page, DevTools Network shows only requests to the dev server,
   and the text renders in Bricolage Grotesque.

### 9.3 On real devices after deploy (owner)

- iPhone and Android: log in with the passcode, the pinned invite link and
  log out.
- A share link in WhatsApp still shows its thumbnail and caption, and the
  invite link's preview still shows "reels".

## 10. Deploy

No new settings. `.\scripts\deploy.ps1` after committing. The restart
empties the pile, as every deploy does. Logged-in phones stay logged in.

## 11. Notes and open items

- **The login cookie is strictly necessary.** Under the ePrivacy rules a
  cookie needed for a service the person asked for (logging in) does not
  require consent; informing them is enough. This design asks anyway.
  Remembering a refusal is also a necessary use of storage.
- **Not legal advice.** Have the notice wording checked if compliance
  matters.
- **Open, out of scope:**
  - A privacy policy page (who runs the site, what is processed, how long,
    contact).
  - IP addresses in logs: uvicorn's access log records client IPs (and share
    keys in URLs, links spec 13). Caddy has no `log` directive, so it keeps
    no access log.
  - The per-IP login limiter holds IPs in memory for 15 minutes.
