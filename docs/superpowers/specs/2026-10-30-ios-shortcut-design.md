# iPhone Shortcut — Design

Date: 2026-10-30
Status: approved, implemented

## 1. Purpose

On Android the installed page is in the share menu (`share_target` in the
manifest, web spec 7.2). iOS has no share targets for web pages, so iPhone
users copy a link and paste it. An Apple Shortcut can sit in the share sheet
instead.

## 2. The shortcut

It only opens the board with the link, the same `/?url=` the Android share
target uses, so it carries no secret and the server needs no new route:

1. Receive **URLs and Text** from the **Share Sheet**; if there's no input,
   **Get Clipboard** (so tapping it from the home screen pastes the clipboard).
2. **URL Encode** the Shortcut Input.
3. **Text**: `https://<host>/?url=` followed by the URL Encoded Text.
4. **Open URLs** with that text.

Safari opens the board and `consumeShareTarget` (`app.js`) starts the paste.
What already exists covers the rest:
- logged out, the login page shows, and `login.js` reloads with the query
  string, so the paste still happens after logging in;
- an unasked cookie gets the cookie pop-up first, and the paste runs after
  "allow cookie".

**Cookies:** a page added to the home screen keeps its own cookies, apart from
Safari's. The shortcut opens Safari, so each phone logs in there once.

## 3. Handing it out

Apple only signs `.shortcut` files on a Mac, so the shortcut is built once on
an iPhone (README has the steps) and shared as an iCloud link. That link goes
in a new optional setting, `IOS_SHORTCUT_URL`.

- When it is set, the board's footer has an "add to iPhone share sheet" link to
  it, on its own line under "log out" (it doesn't fit beside it on a phone), on
  iPhone and iPad only (the same check the player uses for its iOS
  share sheet, moved to `format.js` so `app.js` can use it too).
- When it is empty, or on any other device, the link stays hidden.
- The value is filled into `app.html` on the server (`pages.render_app`),
  HTML-escaped like every `{{name}}`.
- It is not a secret: anyone with the link gets a shortcut that opens the
  board, which still asks for the passcode.
