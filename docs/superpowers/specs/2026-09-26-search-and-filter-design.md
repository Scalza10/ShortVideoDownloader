# Search and Filter on the Board — Design

Date: 2026-09-26
Status: approved design, pre-implementation
Builds on: `2026-09-16-reels-board-ui-design.md` (the "board spec") and
`2026-09-24-favorites-and-delete-design.md` (the "favorites spec", whose
section 12 named this as the next change)

## 1. Purpose

The board keeps up to 100 pile reels and 200 favorites. Finding "that cat
one from yesterday" means scrolling past all of them. This change adds:

- **Caption search:** type words, and the open tab shows only the reels
  whose caption or title has all of them.
- **Source chips:** `all · tiktok · instagram · x`, one at a time.

Everything happens in the page. The board already holds every reel from
`GET /jobs`, so filtering is instant, and the server and the API don't
change.

Out of scope (section 9): account names for TikTok, searching on the
server, remembering the filter.

## 2. Constraints

Everything in board spec section 2 still holds: no build step, no
framework, no JS dependencies, no JS tests, dark only, the layout switches
at 700px. Additionally:

- **The board looks exactly as today until someone opens search** (on a
  phone). Closing search gives back the same board.
- **`board.js`, `paste.js`, `player.js`, `cookie.js` and the new
  `search.js` don't import each other.** `app.js` wires them together with
  callbacks (CLAUDE.md, "Frontend").

## 3. Behaviour

### 3.1 Opening and closing

- **Phone (< 700px):** a round ⌕ button at the right end of the tabs row.
  Tapping it opens the search row under the tabs (field, then the chips
  on the line below) and focuses the field, so the keyboard comes up. The
  ⌕ becomes ✕ (`aria-expanded="true"`, label "close search").
- **✕** clears the text, sets the chip back to `all`, closes the row and
  gives back the ⌕. The board is then exactly as before.
- **Desktop (≥ 700px):** the field and the chips are always shown, on the
  right of the tabs row. There is no ⌕ or ✕ button.
- **A filter always opens the row** (`is-open`), in either layout. The
  desktop shows the row anyway, but a page that narrows below 700px with a
  filter on (a phone rotated from landscape back to portrait) must still
  show the field and ✕, not hide an active filter. *(Added after the final
  review.)*
- **Enter / the keyboard's "search" key** in the field only blurs it, so
  the phone keyboard goes away. The filter stays.
- The field is `type="search"`, so browsers that draw their own clear
  button inside it keep it. It fires `input` like typing does.

### 3.2 Matching

- The filter updates on every `input` event and every chip tap.
- **Text:** the typed text is folded (below) and split on whitespace. A
  reel matches when every word is in the folded `caption + " " + title`.
  Order doesn't matter, and a word may be part of a longer one (`cat`
  finds `cats` and `#catsofinstagram`).
- **Folding:** `String(s || "").normalize("NFD").replace(/\p{M}/gu, "")
  .toLowerCase()`: case and accents are ignored, so `cafe` finds `Café`.
  `#` and `@` get no special treatment.
- **Chips:** `all` (the default) matches every source; `tiktok`,
  `instagram` and `x` match `reel.source`. Exactly one chip is pressed
  (`aria-pressed="true"`). Tapping the pressed one does nothing.
- **No filter** means no words and `all`. Only spaces counts as no words.
- The caption is what the player shows: Instagram's description, TikTok's
  text, the tweet text. The title adds "Video by <user>" for Instagram and
  "<name> - <text>" for X, so their account names are searchable too.
  TikTok's title is its text, so TikTok account names are not (section 9).

### 3.3 What a filter changes

- **The open tab shows only matching reels,** in the tab's usual order.
  Switching tabs keeps the filter, so it applies to whichever tab is open.
- **Counts don't change:** "N in the pile" and the favorites tab's number
  still count everything, as today.
- **The player gets the filtered list** (`board.getShown()`), so swiping
  and ← → move only through the matches. A refresh while the player is
  open adds only new matching reels (`player.addReels(board.getShown())`,
  unchanged).
- **The 30-second refresh** adds a new reel's tile only when it matches.
- **The ▶ newest marker** (board spec 6.2) is left out while a filter is
  on: it would mark the newest match, not the newest reel.
- **Pending tiles** (a paste in flight) are hidden while a filter is on and
  come back when it's cleared. They have no caption to match.
- **The player covers the board,** so the filter can't change while it's
  open.
- Star, un-star and delete work as before. Un-starring on the favorites tab
  still takes the reel off that tab.
- A browser Forward to a reel the filter hides opens that reel on its own:
  `player.open(board.getShown(), id)` finds nothing, and `openLinkedReel`'s
  existing fallback fetches the job. Rare, and acceptable.

### 3.4 No matches

When the open tab has reels but none match: the grid hides and
`#empty-search` shows "nothing matches" and a "clear search" button.
"clear search" clears the text and sets the chip to `all`. The row stays
open and the field gets focus (the button hides itself, and focus must not
fall to the page), so the next search is right there.

When the tab itself is empty, its usual empty state shows ("the pile is
empty", "no favorites yet"), filter or not, and `body.is-empty` works as
today.

### 3.5 Pasting clears the filter

A paste start (`paste.js`'s `onStart`) clears the filter and, on a phone,
closes the row, before the pending tile is added. Otherwise the new tile,
the new reel or the scroll to an existing one (`board.reveal`) could be
hidden by the filter. Android's share target starts a paste the same way,
so it clears it too.

### 3.6 Not remembered

The filter lives in memory only. A reload, a new visit or a `?reel=` link
starts with no filter and the row closed, as the board always opens on
pile (favorites spec 6). The field has `autocomplete="off"`: a page loaded
from history without the back/forward cache would otherwise get its old
text back while the board is unfiltered.

## 4. Layout

### 4.1 Markup (`app.html`)

The tabs row becomes a bar that holds the tabs, the toggle and the search
row. The toggle can't go inside the `<nav role="tablist">`, which may only
hold tabs.

```html
<div class="board-bar">
  <nav class="tabs" role="tablist" aria-label="reels">…unchanged…</nav>
  <button id="search-toggle" class="search-toggle" type="button"
          aria-expanded="false" aria-controls="search" aria-label="search"></button>
  <div id="search" class="search" role="search">
    <div class="search-field">
      <span class="search-icon" data-icon="search"></span>
      <input id="search-input" type="search" enterkeyhint="search" autocapitalize="off"
             autocorrect="off" spellcheck="false" placeholder="search captions"
             aria-label="search captions">
    </div>
    <div class="chips" role="group" aria-label="source">
      <button class="chip" type="button" data-source="" aria-pressed="true">all</button>
      <button class="chip" type="button" data-source="tiktok" aria-pressed="false">tiktok</button>
      <button class="chip" type="button" data-source="instagram" aria-pressed="false">instagram</button>
      <button class="chip" type="button" data-source="x" aria-pressed="false">x</button>
    </div>
  </div>
</div>
```

The toggle's icon (`search` or `x`) is set by `search.js`. After
`#empty-favorites`:

```html
<div id="empty-search" class="empty-search" hidden>
  <p class="empty-title">nothing matches</p>
  <button id="search-clear" class="btn" type="button">clear search</button>
</div>
```

`watch.html` has no board, so nothing is mirrored there. `app.html` goes
through `pages.fill`, so the new markup must not contain `{{`.

### 4.2 Styles (`style.css`)

- `.board-bar` takes over the tabs row's spacing: `.tabs`' bottom padding
  moves to it, and so do its desktop `max-width: 1100px` and centring.
  It's a wrapping flex row, `align-items: center`.
- **Toggle:** 32px round, the same height as a tab, `--hairline` border,
  `--ink-50` icon of 16px, `margin-left: auto`.
- **Search row, phone:** `flex-basis: 100%`, shown only with `.is-open`
  (a class, not `hidden`: on desktop it must show while "closed", and
  `[hidden]` is `!important`). The field is 40px high, a pill with a
  `--hairline` border and the 14px search icon at its left, full width.
  The chips sit on the line below it, 8px apart.
- **Chips:** pills 28px high, `0 12px` padding, 600 12px, `--hairline`
  border, `--ink-50` text. Pressed: `--ink` border and `--ink` text. That's
  an outline, so it doesn't read as a selected tab, which is filled.
  Only one accent in the page (handoff), so no colour.
- **Desktop:** the toggle is `display: none`. The search row is always
  shown, on the same line as the tabs, with `margin-left: auto`: field
  (220px) then chips, 10px apart.
- `.empty-search`: the favorites empty state's layout (`.empty-favorites`),
  with the button under the title.

### 4.3 Icons (`icons.js`)

Adds Lucide's `search` (ISC, like the others):
`<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>`.

## 5. Code

### 5.1 `search.js` (new)

```js
export function createSearch({ row, toggle, input, chips, clearButton, onChange })
// -> { clear() }
```

- Keeps `open` (the phone row), `text` and `source` (`""` for all).
- Toggle click: closed → open, focus the field. Open → `clear()`.
- `input` event: new text, `onChange`. Enter in the field: `input.blur()`.
- Chip click: that chip's `data-source`, updates every chip's
  `aria-pressed`, `onChange`.
- `clearButton` click: text and chip reset, row stays as it is, `onChange`.
- `clear()`: text and chip reset, row closed, `onChange`. `app.js` calls
  it when a paste starts.
- `onChange(match)`: `match` is `null` for no filter, otherwise a function
  `reel => boolean` built from the current text and source (3.2).
- Opening and closing toggle `.is-open` on `row`, `aria-expanded` and the
  label on `toggle`, and swap the toggle's icon.
- The folding and matching are plain functions in this file. It imports
  only `icons.js`.

### 5.2 `board.js`

- `createBoard` also takes `emptySearch` (the `#empty-search` element).
- New `setFilter(match)`: stores it and renders. It doesn't scroll: the
  page would jump while someone types.
- `shown()`: the tab's list as today, then `.filter(match)` when there is
  one. `getShown()` and the player therefore get only matches.
- `render()`:
  - pending tiles are hidden unless it's the pile tab and there is no
    filter;
  - the ▶ newest marker only when there is no filter;
  - `pileTotal`, `favoriteTotal` and `total` stay unfiltered, so the counts,
    the two empty states and `body.is-empty` are as today;
  - `total > 0` with an empty filtered list: the grid hides and
    `emptySearch` shows. Otherwise `emptySearch` is hidden.
- `tabOf` and `reveal` ignore the filter (a paste has already cleared it).

### 5.3 `app.js`

```js
const search = createSearch({
  row: $("search"),
  toggle: $("search-toggle"),
  input: $("search-input"),
  chips: [...document.querySelectorAll("#search .chip")],
  clearButton: $("search-clear"),
  onChange: (match) => board.setFilter(match),
});
```

`createBoard` gets `emptySearch: $("empty-search")`. The paste `onStart`
calls `search.clear()` before `board.addPending()`.

## 6. Dev board

`scripts/dev_board.py` gets one more caption with an accent, "café au lait,
but make it iced", so accent folding can be tried by hand. The seeds
already cover all three sources, a caption-less seed (title only) and a
long caption.

## 7. Docs

- **README**, "The board": a **Search** bullet: ⌕ on a phone, always shown
  on a desktop; every word must be in the caption or title; accents and
  case ignored; the chips; the player swipes through matches only; pasting
  clears it.
- **CLAUDE.md**, "Frontend": `app.js` wires five modules (add `search.js`);
  the filter lives in `board.js` as a match function from `search.js`, and
  `getShown()` is the filtered list. Add "(search spec …)" to the spec
  pointers.

## 8. Testing

pytest, no network:

- `test_web.py`: add `search.js` to `APP_MODULES`, so it's served as
  `text/javascript`.
- `test_web.py`: the board page has `search-toggle`, `search`,
  `search-input`, `empty-search` and `search-clear`, and one chip for each
  of `data-source=""`, `"tiktok"`, `"instagram"` and `"x"`.
- The view-only page has no `search-input`.

By hand with `dev_board.py` in Chrome, at phone width (DevTools) and
desktop width (no JS tests, per the board spec):

- phone: ⌕ opens the row and focuses the field; ✕ gives back the same
  board;
- desktop: field and chips always shown, no toggle;
- each chip, alone and with text;
- two words in either order (`taco gas`, `gas taco`);
- `cafe` finds the café seed; `CAT` finds "cat vs cucumber";
- the caption-less seed is found by its title;
- switching tabs keeps the filter; the counts don't change;
- the player swipes only through matches, on both tabs;
- nothing matches: the message, then "clear search";
- a paste while filtered clears the filter and shows the pending tile;
- a paste of a link already in the pile, while filtered, scrolls to it;
- Enter hides the keyboard (on a real phone after deploy) and keeps the
  filter;
- a 30-second refresh while filtered doesn't bring back hidden reels.

## 9. Out of scope

- **TikTok account names.** It would need an `uploader` field from yt-dlp
  in the job JSON; reels already in the pile wouldn't have it.
- **Searching on the server** (`GET /jobs?q=`). The page has every reel.
- **Remembering the filter** across reloads (3.6).
- **Highlighting the matched words** on tiles or in the player.
- **Several chips at once.**
