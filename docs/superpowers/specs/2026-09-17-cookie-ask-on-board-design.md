# Cookie Pop-up on the Board — Design

Date: 2026-09-17
Status: approved design, pre-implementation
Builds on: `2026-09-17-cookie-consent-design.md` (the "cookie spec"),
`2026-09-17-invite-and-share-links-design.md` (the "links spec") and
`2026-09-16-mobile-web-page-design.md` (the "web spec")

## 1. Purpose

The cookie spec asks before the login cookie is set, but phones that were
already logged in kept their cookie (cookie spec 3) and only see the board
footer ("one cookie keeps you logged in · log out"). Close that gap:

- **Ask phones that never agreed.** A phone whose cookie was set before the
  login page asked gets a pop-up on the board that it cannot dismiss. It
  comes back on every visit until the person answers.
- **"allow cookie"** marks the cookie as agreed and loads the board.
- **"no thanks, log me out"** is today's "no": the cookie is deleted, the
  "no" is remembered in the browser and the login page shows its declined
  state (cookie spec 4.2).
- **Share links still work without agreeing.** A share link (`?reel=&k=`)
  opens the view-only page for such a phone, exactly as for a phone with no
  cookie. Only the board is behind the pop-up.

Out of scope (section 11): retiring the old cookie value, asking API-key
clients anything.

## 2. Constraints

Everything in cookie spec section 2 and links spec section 2 still holds
(HTTPS, in-memory jobs, no build step, no framework, no JS dependencies, dark
only, a GET never sets the cookie). Additionally:

- **The server cannot tell today who agreed.** Every cookie has the same
  value, one HMAC of `API_KEY` and `WEB_PASSCODE` (web spec 4.2), whether it
  was set before or after the login page started asking.
- **Browser storage is not reliable enough to hold a "yes".** iOS Safari may
  clear it after about seven days without a visit, and some private windows
  throw on every access. So the agreement is recorded in the cookie value.
- **Nobody is logged out by the deploy.**

## 3. Cookie values

`auth.py` knows two values. Both log a phone in.

| name | value | set by |
|------|-------|--------|
| agreed | HMAC-SHA256, key `API_KEY`, message `b"reels-web-session-agreed:" + WEB_PASSCODE` | `POST /web/login`, `POST /join/{token}`, `POST /web/cookie` (5.2) |
| unasked | HMAC-SHA256, key `API_KEY`, message `b"reels-web-session:" + WEB_PASSCODE` (today's value) | nothing any more |

- `session_cookie_value(settings)` returns the agreed value, so every place
  that sets the cookie sets the agreed value without changing.
- `unasked_cookie_value(settings)` (new) returns the unasked value.
- `session_state(settings, cookie)` (new) returns `"agreed"`, `"unasked"` or
  `None`. `None` when `WEB_PASSCODE` is unset, the cookie is missing or empty,
  or it matches neither value. Both comparisons use `secrets.compare_digest`
  on bytes (`cookie.encode()`), like the passcode check, so a non-ASCII
  cookie gives `None` instead of raising.
- `session_is_valid(settings, cookie)` becomes `session_state(...) is not
  None`. `has_access`, `require_access`, `/files/`, `POST /web/logout` and
  `GET /join/{token}` row 1 (cookie spec 5.1) therefore accept both values,
  unchanged.
- Changing `API_KEY` or `WEB_PASSCODE` still changes both values and logs
  everyone out.

## 4. `GET /`

Replaces links spec 5.1. The rule: **wherever the login page is served
today, an unasked cookie gets the board with the pop-up instead.** Checked in
order:

| # | case | response |
|---|------|----------|
| 1 | agreed cookie | the board, `data-cookie="agreed"` |
| 2 | no `reel` or no `k` | unasked cookie: the board, `data-cookie="ask"`; otherwise the login page |
| 3 | unknown reel | expired page |
| 4 | wrong key | same as row 2 |
| 5 | reel not done, or its file is gone | expired page |
| 6 | otherwise | view-only page |

"Otherwise" in rows 2 and 4 covers no cookie and an invalid cookie. Every
response keeps `Cache-Control: no-store`.

The board is no longer a plain file. `app.html`'s `<body>` becomes
`<body data-cookie="{{cookie}}">`, and `pages.render_app(ask: bool)` fills it
with `"ask"` or `"agreed"` using `pages.fill`. `app.html` has no other
`{{…}}`. The `pages.py` module docstring stops saying its pages are only for
people without the cookie.

An Android share (`/?url=&text=&title=`) and a `/?reel=<id>` link without a
key fall under row 2. For an unasked cookie they wait behind the pop-up and
run after "allow cookie" (6.2).

## 5. Server

### 5.1 Unchanged routes

- `POST /web/login` and `POST /join/{token}` set the agreed value (through
  `session_cookie_value`).
- `GET /join/{token}` row 1: an unasked cookie is a valid cookie, so it gets
  `303` to `/` with no failure recorded, and `/` shows the pop-up.
- `POST /web/logout` deletes either value.

### 5.2 `POST /web/cookie`

New, in the web router (so it exists only when `WEB_PASSCODE` is set). No
request body.

| # | case | response |
|---|------|----------|
| 1 | session cookie valid (agreed or unasked) | `204`, `_set_session_cookie` (agreed value, same attributes, a fresh one-year `Max-Age`) |
| 2 | otherwise, including a valid `X-API-Key` without the cookie | `401` with the existing `unauthorized` body, no `Set-Cookie` |

- It checks the cookie itself instead of using `require_access`: the route
  exists only to change a cookie, so an API key alone does not qualify.
- Every response sends `Cache-Control: no-store`.
- A cross-site POST carries no `SameSite=Lax` cookie, so it gets `401` and
  cannot agree on someone's behalf.

## 6. The pop-up

### 6.1 Markup and styles

`app.html` gains, just before `#toast`:

```html
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

- The three notice lines are the login page's (`NOTICE_LINES` in
  `test_web.py`).
- `watch.html` is not changed. The player markup is untouched, so the rule
  about mirroring it does not apply.

`style.css` gains, next to the login page styles:

- `.cookie-ask`: `width: min(340px, calc(100% - 32px))`, `max-width: none`,
  `padding: 24px`, `border: 1px solid var(--hairline)`, `border-radius:
  20px`, `background: var(--surface)`, `color: var(--ink)`. Centred by the
  browser's modal dialog margins.
- `.cookie-ask::backdrop`: `background: var(--scrim-overlay)`.
- `.cookie-ask-title`: `margin: 0`, 18px, weight 700, `--ink`.

The dialog sits in the top layer, above the sticky top bar, the fixed paste
bar and the player. It must be readable and tappable at 390×844 and at
1280×800.

### 6.2 Behaviour

New module `static/cookie.js`, wired by `app.js` like `board.js`, `paste.js`
and `player.js`. It imports only `api.js`.

```js
export function createCookieAsk({ dialog, onAccepted }) // → { open() }
```

- **open()** calls `dialog.showModal()`. The board, paste bar and footer
  behind it cannot be focused or tapped. `#cookie-allow` has focus.
- **Cannot be dismissed.** A `cancel` listener calls `preventDefault()` (Esc).
  Chrome still closes a dialog on a repeated Esc, so a `close` listener calls
  `showModal()` again unless the person agreed. A reload serves
  `data-cookie="ask"` again until `POST /web/cookie` succeeds.
- **allow cookie:** disables both buttons, hides `#cookie-error`, calls
  `agreeToCookie()`.
  - Success: marks it agreed, `dialog.close()`, `onAccepted()`.
  - `Unauthorized`: nothing; `api()` is already reloading, and `/` then
    serves the login page.
  - Anything else (other status, network error): shows "couldn't save that.
    try again." in `#cookie-error` and enables both buttons. Not a toast: the
    toast sits under the top layer.
- **no thanks, log me out:** disables both buttons, hides `#cookie-error`,
  saves `localStorage["reels-cookie-choice"] = "declined"`, calls `logout()`
  (`api.js`, cookie spec 6), then `location.replace("/")`, which serves the
  login page in its declined state.
  - `Unauthorized`: nothing; the reload lands on the declined state because
    the "no" is already saved.
  - Anything else: removes `reels-cookie-choice` again (the cookie is still
    there, so no "no" was given), shows "couldn't log out. try again." in
    `#cookie-error` and enables both buttons.
- Every `localStorage` access is wrapped in `try`/`catch`, as in `login.js`.
  When storage throws, logging out still works and the login page asks
  instead of showing the declined state.
- `"reels-cookie-choice"` and `"declined"` are the same strings as in
  `login.js`, which is not a module and cannot import them. Keep them
  identical.

`api.js` gains:

```js
// Marks this phone's login cookie as agreed (cookie pop-up spec 5.2). A 401 reloads through api().
export async function agreeToCookie()
```

`api("/web/cookie", { method: "POST" })`, throwing an `Error` when the
response is not ok.

`app.js`:

- The 30-second refresh interval and the `visibilitychange` refresh are
  registered inside `start()` instead of at module level, so nothing fetches
  `/jobs` before the person agrees.
- The last line becomes: when `document.body.dataset.cookie === "ask"`,
  `createCookieAsk({ dialog: $("cookie-ask"), onAccepted: start }).open()`;
  otherwise `start()`. The share target and `?reel=` handling already run
  inside `start()`, so they wait too.
- Until then the board is an empty shell: empty grid, no count, `#empty`
  hidden.

## 7. Dev board

`scripts/dev_board.py`'s `link_lines(port, seeds)` becomes
`link_lines(port, seeds, settings)` and always ends with

```
old cookie:  <unasked_cookie_value(settings)>
```

The module docstring says to paste it into DevTools → Application → Cookies
→ `reels_session` for `localhost` to see the pop-up.

## 8. Code layout

```
reels_api/
  auth.py             agreed and unasked values, session_state (3)
  web.py              GET / rows 1, 2, 4 (4), POST /web/cookie (5.2)
  pages.py            render_app (4)
  static/
    app.html          data-cookie placeholder (4), #cookie-ask dialog (6.1)
    app.js            start() owns the refreshes, opens the pop-up (6.2)
    cookie.js         new: createCookieAsk (6.2)
    api.js            agreeToCookie() (6.2)
    style.css         .cookie-ask, ::backdrop, .cookie-ask-title (6.1)
scripts/
  dev_board.py        old cookie line (7)
tests/
  test_routes.py      cookie value tests (9.1)
  test_web.py         section 9.1, cookie.js in APP_MODULES
  test_pages.py       render_app (9.1)
  test_dev_board.py   link_lines (9.1)
README.md             phones logged in earlier are asked once on the board
CLAUDE.md             auth: two values, POST /web/cookie, the GET / rule; frontend: cookie.js; the duplicated choice key
docs/superpowers/specs/
  2026-09-17-cookie-consent-design.md        pointer to this spec from section 1 (out of scope: "the server checking consent") and section 3 ("People already logged in…")
  2026-09-17-invite-and-share-links-design.md pointer to this spec from 5.1
```

## 9. Testing

### 9.1 Automated (pytest, no network, no ffmpeg)

- **Values:** `session_cookie_value` is the HMAC with the
  `reels-web-session-agreed:` prefix and `unasked_cookie_value` the one with
  `reels-web-session:` (replaces `test_cookie_value_is_hmac_of_passcode`);
  the two differ; `session_state` returns `"agreed"`, `"unasked"` and `None`
  (wrong value, empty, missing, a non-ASCII value without raising, and
  either value when `web_passcode` is unset).
- **Access:** both values open `GET /jobs/<id>` and a `/files/` file; a stale
  value (other passcode) of either kind gets `401`.
- **Setting:** `POST /web/login` and `POST /join/{token}` set the agreed value
  (the existing assertions, plus "not the unasked value").
- **`GET /` with an unasked cookie:** plain `/` → board with
  `data-cookie="ask"`, `id="cookie-ask"` and the three notice lines, `no-store`;
  `/?url=…` and `/?reel=<id>` without `k` → same; a right share link →
  view-only page with no `cookie-ask`; a wrong key → board with
  `data-cookie="ask"`; an unknown reel and a reel not done → expired page.
- **`GET /` with an agreed cookie:** board with `data-cookie="agreed"`. The
  existing no-cookie tests are unchanged.
- **`POST /web/cookie`:** unasked cookie → `204`, `Set-Cookie` with the agreed
  value and the attributes of `test_login_success_sets_cookie` (including
  `max-age=31536000`), `no-store`, and `GET /` afterwards has
  `data-cookie="agreed"`; agreed cookie → `204`; no cookie, a wrong cookie,
  and a valid `X-API-Key` without a cookie → `401` `unauthorized` body, no
  `Set-Cookie`, `no-store`; `404` when `web_passcode` is unset.
- **Unasked cookie elsewhere:** `POST /web/logout` → `204` and the cookie is
  deleted; `GET /join/<anything>` → `303` to `/`, no failure recorded.
- **Modules:** `cookie.js` is in `APP_MODULES` and served as `text/javascript`.
- **Pages:** `render_app(True)` has `data-cookie="ask"`, `render_app(False)`
  has `data-cookie="agreed"`, and neither has `{{`.
- **Dev board:** `link_lines` ends with the old cookie line for the given
  settings.

### 9.2 Manual, in Chrome, against `scripts/dev_board.py`

At 390×844 (device emulation, touch) and at 1280×800:

1. Set `reels_session` to the printed old cookie and open `/`. The pop-up
   shows over an empty board, and DevTools Network has no `/jobs` request.
   Esc twice leaves it up. Reload: still up.
2. **allow cookie**: the pile loads and refreshes. `reels_session` now has a
   different value. Reload: no pop-up.
3. Old cookie again. The printed share link → view-only page, no pop-up.
   `/?reel=<id>` without `k` → pop-up; after **allow cookie** that reel opens
   muted.
4. Old cookie again. **no thanks, log me out** → login page in the declined
   state, no `reels_session`. The share link still opens the view-only page.
5. Old cookie again, DevTools offline. **allow cookie** and **no thanks, log
   me out** each show their error text inside the pop-up, and the buttons
   work again. Back online, reload: the pop-up is still there.
6. A normal passcode login in a private window never shows the pop-up.

### 9.3 On real devices after deploy (owner)

- A phone that was logged in before the deploy sees the pop-up on the board,
  and after **allow cookie** does not see it again.
- A share link in WhatsApp still opens the view-only page on that phone
  before it answers.

## 10. Deploy

No new settings. Commit, then `.\scripts\deploy.ps1`. Nobody is logged out.
Every phone with an unasked cookie sees the pop-up on its next visit to the
board. The restart empties the pile, as every deploy does.

## 11. Notes and open items

- **Phones that already agreed on the login page are asked once more.**
  Anyone who logged in through the asking login page before this deploy has
  the unasked value; the server cannot tell them apart.
- **Reading the stored cookie to decide whether to ask** is part of asking.
  Nothing new is stored before "allow cookie", and the pile is not fetched.
- **The unasked value keeps logging phones in** until `API_KEY` or
  `WEB_PASSCODE` changes. Retiring it, so a phone that never answers is
  logged out, is a later change in `session_state`. Out of scope.
- **API-key clients** (`X-API-Key`, curl) are unaffected and never asked.
- **Not legal advice**, as in cookie spec 11.
