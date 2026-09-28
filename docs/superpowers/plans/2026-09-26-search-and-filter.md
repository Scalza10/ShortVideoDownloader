# Search and Filter on the Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The board gets a caption search and `all · tiktok · instagram · x` source chips: behind a ⌕ button on a phone, always shown on a desktop. The open tab shows only the matches, and the player swipes through those only.

**Architecture:** Everything is in the page; the server and the API don't change. A new `search.js` owns the search row (toggle, field, chips, "clear search") and turns it into a match function, `reel => boolean` or `null`. `app.js` hands that to a new `board.setFilter(match)`, and `board.js` applies it after picking the tab, so `getShown()` (which the player already uses) is the filtered list. A paste start calls `search.clear()`.

**Tech Stack:** plain HTML/CSS/ES modules (no build, no framework, no JS tests); pytest for the page markup and static serving; Node 22 only for throwaway syntax and logic checks.

**Spec:** `docs/superpowers/specs/2026-09-26-search-and-filter-design.md`

## Global Constraints

- Page text, exactly: placeholder `search captions` (also the field's `aria-label`); toggle `aria-label` `search` when closed, `close search` when open; chips `all`, `tiktok`, `instagram`, `x` with `data-source` `""`, `"tiktok"`, `"instagram"`, `"x"`; no-matches title `nothing matches`; its button `clear search`.
- Matching: the query and `caption + " " + title` are folded with `String(s || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase()`; the query is split on whitespace; every word must be a substring of the folded text; the chip must equal `reel.source` unless it is `all` (`""`). No words and `all` is no filter (`null`).
- Layout switches at 700px. Below it: ⌕ toggle, the row shows only with the `is-open` class. At 700px and up: no toggle, the row is always shown on the tabs' line.
- The search field's font is 16px: iOS Safari zooms the page into any input under 16px.
- Visibility of the search row uses a class, not the `hidden` attribute (`[hidden]` is `display: none !important`, and the desktop must show the row while "closed").
- The toggle goes outside `<nav role="tablist">`, which may only hold tabs.
- Counts ("N in the pile", the favorites number) and the pile/favorites empty states stay unfiltered.
- `board.js`, `paste.js`, `player.js`, `cookie.js` and `search.js` never import each other. `search.js` imports only `icons.js`.
- `watch.html` is not changed (it has no board). `app.html` goes through `pages.fill`, so no `{{` in the new markup.
- No new Python or JS dependencies, no requests to other sites. `search.js` goes into `APP_MODULES` in `tests/test_web.py`.
- Run the tests with `.venv/Scripts/python.exe -m pytest` (Git Bash) or `.venv\Scripts\python.exe -m pytest` (PowerShell). ffmpeg is not installed locally. The suite is 399 passed, 1 deselected before this plan.
- JS syntax check (Git Bash; plain `node --check` ignores syntax errors in `.js` modules, `.mjs` catches them):
  `d=$(mktemp -d); for f in <files>; do cp "reels_api/static/$f" "$d/${f%.js}.mjs" && node --check "$d/${f%.js}.mjs" || echo "SYNTAX ERROR: $f"; done`
- Commits: small, prefixed `feat:` / `docs:`, message ending with a blank line and `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Stage only the files the task names (`brag-output/` is untracked and stays that way).

## Review Focus

Inputs the spec implies that no task's pytest can reach (the matching is JS), each pinned by a check in the task that owns the code:

1. **The field on an iPhone.** Under 16px, iOS zooms the whole page when the field gets focus and doesn't zoom back. Task 2, `test_search_field_is_16px_so_ios_does_not_zoom`.
2. **A query of only spaces, or with spaces around it.** It must be no filter, not "match nothing". Task 1, the Node check (`makeMatch("   ", "")` is `null`, `makeMatch("  cat  ", "")` matches).
3. **A reel with a null caption or title.** No exception, just no match on the missing text. Task 1, the Node check (`reel(null, null)`).
4. **Accents in the query as well as in the caption** (`CAFÉ` finds `cafe au lait`, `cafe` finds `Café`). Task 1, the Node check.
5. **A paste still downloading when someone starts searching.** The pending tile hides while the filter is on, and when the paste finishes the new reel shows only if it matches. Task 3, manual check 11.

---

### Task 1: `search.js`: the search row and the match function

**Files:**
- Create: `reels_api/static/search.js`
- Modify: `reels_api/static/icons.js` (the `STROKE` table)
- Test: `tests/test_web.py` (`APP_MODULES`)

**Interfaces:**
- Produces:
  - `export function makeMatch(text: string, source: string): null | ((reel) => boolean)`: `source` is `""` for all.
  - `export function createSearch({ row, toggle, input, chips, clearButton, onChange }) -> { clear() }`:
    - `row`: the `#search` element, whose `is-open` class `search.js` toggles;
    - `toggle`: the `#search-toggle` button; `search.js` fills its icon;
    - `input`: `#search-input`;
    - `chips`: an array of the chip buttons, each with `data-source`;
    - `clearButton`: `#search-clear`;
    - `onChange(match)`: called with `makeMatch(...)` after every change, never at creation.
  - `icon("search")` in `icons.js`.

- [ ] **Step 1: Add `search.js` to the served modules (failing test)**

In `tests/test_web.py`, line 13, add `"search.js"` to the end of `APP_MODULES`:

```python
APP_MODULES = ["app.js", "api.js", "format.js", "icons.js", "board.js", "paste.js", "toast.js", "player.js", "watch.js", "cookie.js", "search.js"]
```

- [ ] **Step 2: Run it to see it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py::test_app_modules_are_served -q`
Expected: FAIL, `AssertionError: search.js` (the file doesn't exist, so `/static/search.js` is 404).

- [ ] **Step 3: Add the search icon**

In `reels_api/static/icons.js`, in `STROKE`, after the `link2` line add:

```js
  search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
```

- [ ] **Step 4: Write `search.js`**

Create `reels_api/static/search.js`:

```js
import { icon } from "./icons.js";

// Case and accents don't count: "cafe" finds "Café" (search spec 3.2).
function fold(text) {
  return String(text || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}

// null when there is nothing to filter by; otherwise true for a reel from that source ("" is all)
// whose caption or title has every word, in any order (search spec 3.2).
export function makeMatch(text, source) {
  const words = fold(text).split(/\s+/).filter(Boolean);
  if (!words.length && !source) return null;
  return (reel) => {
    if (source && reel.source !== source) return false;
    const haystack = fold(`${reel.caption || ""} ${reel.title || ""}`);
    return words.every((word) => haystack.includes(word));
  };
}

// The search row under the tabs: behind a toggle on a phone, always shown on a desktop (search spec 3.1, 5.1).
// It never touches the board: every change goes out through onChange(match).
export function createSearch({ row, toggle, input, chips, clearButton, onChange }) {
  let source = "";

  function changed() {
    onChange(makeMatch(input.value, source));
  }

  function setOpen(open) {
    row.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "close search" : "search");
    toggle.innerHTML = icon(open ? "x" : "search");
  }

  function setSource(next) {
    source = next;
    for (const chip of chips) chip.setAttribute("aria-pressed", String(chip.dataset.source === next));
  }

  function reset() {
    input.value = "";
    setSource("");
  }

  // Everything back as it was, row closed: the ✕, and a paste starting (search spec 3.5).
  function clear() {
    reset();
    setOpen(false);
    changed();
  }

  toggle.addEventListener("click", () => {
    if (row.classList.contains("is-open")) {
      clear();
      return;
    }
    setOpen(true);
    input.focus(); // inside the tap, so a phone brings up its keyboard
  });
  input.addEventListener("input", changed);
  input.addEventListener("search", changed); // the field's own clear button, in browsers that have one
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") input.blur(); // drops the phone keyboard; the filter stays
  });
  for (const chip of chips) {
    chip.addEventListener("click", () => {
      if (chip.dataset.source === source) return;
      setSource(chip.dataset.source);
      changed();
    });
  }
  // "clear search" under "nothing matches": the row stays open for the next try (search spec 3.4).
  clearButton.addEventListener("click", () => {
    reset();
    changed();
  });

  setOpen(false);
  return { clear };
}
```

- [ ] **Step 5: Run the served-modules test**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py::test_app_modules_are_served -q`
Expected: PASS.

- [ ] **Step 6: Check the syntax and the matching in Node (throwaway, nothing committed)**

Run (Git Bash, repo root):

```bash
d=$(mktemp -d); for f in search.js icons.js; do cp "reels_api/static/$f" "$d/${f%.js}.mjs" && node --check "$d/${f%.js}.mjs" || echo "SYNTAX ERROR: $f"; done
d=$(mktemp -d) && cp reels_api/static/search.js reels_api/static/icons.js "$d/" && echo '{"type":"module"}' > "$d/package.json" && cat > "$d/check.mjs" <<'EOF'
import assert from "node:assert/strict";
import { makeMatch } from "./search.js";

const reel = (caption, title = "", source = "tiktok") => ({ caption, title, source });
const cat = reel("cat vs cucumber, round 2");

assert.equal(makeMatch("", ""), null);                         // nothing typed, all: no filter
assert.equal(makeMatch("   ", ""), null);                      // only spaces: no filter
assert.ok(makeMatch("  cat  ", "")(cat));                      // spaces around a word
assert.ok(makeMatch("CAT", "")(cat));                          // case
assert.ok(makeMatch("cucumber cat", "")(cat));                 // any order
assert.ok(!makeMatch("cat dog", "")(cat));                     // every word must be there
assert.ok(makeMatch("cafe", "")(reel("Café au lait")));        // accent in the caption
assert.ok(makeMatch("CAFÉ", "")(reel("cafe au lait")));        // accent in the query
assert.ok(makeMatch("cats", "")(reel("#catsofinstagram")));    // part of a longer word, # ignored
assert.ok(makeMatch("skyandtami", "")(reel("look @skyandtami")));
assert.ok(makeMatch("nasa", "")(reel("", "Video by nasa", "instagram"))); // the title counts
assert.equal(makeMatch("x", "")(reel(null, null)), false);     // null fields: no match, no throw
assert.ok(makeMatch("", "x")(reel("a", "", "x")));             // a chip alone
assert.ok(!makeMatch("", "x")(reel("a", "", "tiktok")));
assert.ok(!makeMatch("cat", "instagram")(cat));                // chip and words together
assert.ok(makeMatch("cat", "tiktok")(cat));
console.log("search.js matching: ok");
EOF
node "$d/check.mjs"
```

Expected: no `SYNTAX ERROR` lines, then `search.js matching: ok`.

- [ ] **Step 7: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 399 passed, 1 deselected.

- [ ] **Step 8: Commit**

```bash
git add reels_api/static/search.js reels_api/static/icons.js tests/test_web.py
git commit -F - <<'EOF'
feat: search.js turns the search row into a match on caption, title and source

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 2: The search row on the board

**Files:**
- Modify: `reels_api/static/app.html` (the tabs `<nav>`, after `#empty-favorites`)
- Modify: `reels_api/static/style.css` (the tabs section, `.empty-favorites`, the desktop block)
- Modify: `reels_api/static/board.js` (`createBoard`, `shown`, `render`, the returned object)
- Modify: `reels_api/static/app.js` (imports, `createBoard` call, a `createSearch` call, paste `onStart`)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `createSearch({ row, toggle, input, chips, clearButton, onChange }) -> { clear() }` from Task 1.
- Produces:
  - `createBoard({ ..., emptySearch })`: the `#empty-search` element.
  - `board.setFilter(match: null | (reel => boolean))`: filters the open tab, renders, doesn't scroll.
  - `board.getShown()` is now the open tab filtered by the match (the player's list).
  - Element ids in `app.html`: `search-toggle`, `search`, `search-input`, `empty-search`, `search-clear`.

- [ ] **Step 1: Write the failing page tests**

In `tests/test_web.py`, add `import re` to the imports at the top (before `import pytest`), then append at the end of the file:

```python
def test_board_has_the_search_row(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        page = client.get("/").text
    for element_id in ("search-toggle", "search", "search-input", "empty-search", "search-clear"):
        assert f'id="{element_id}"' in page, element_id
    for source in ("", "tiktok", "instagram", "x"):
        assert f'<button class="chip" type="button" data-source="{source}"' in page, source
    assert 'data-source="" aria-pressed="true">all</button>' in page  # all is pressed at first
    assert 'placeholder="search captions"' in page
    assert "nothing matches" in page
    assert ">clear search</button>" in page
    # The toggle is not a tab, so it must be outside the tablist.
    assert page.index('id="search-toggle"') > page.index("</nav>")


def test_view_only_page_has_no_search(web_app):
    with TestClient(web_app()) as client:
        reel = _done_reel(client)
        page = client.get("/", params={"reel": reel["id"], "k": reel["share_key"]}).text
    assert 'id="search-input"' not in page


def test_search_field_is_16px_so_ios_does_not_zoom(web_app):
    with TestClient(web_app()) as client:
        css = client.get("/static/style.css").text
    rule = re.search(r"\.search-field input \{([^}]*)\}", css)
    assert rule, "no .search-field input rule"
    assert re.search(r"font: \d+ 16px", rule.group(1))
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py -q -k "search"`
Expected: `test_board_has_the_search_row` FAILS (`AssertionError: search-toggle`), `test_search_field_is_16px_so_ios_does_not_zoom` FAILS (`no .search-field input rule`), `test_view_only_page_has_no_search` passes (a guard: `watch.html` must never get it).

- [ ] **Step 3: The markup**

In `reels_api/static/app.html`, replace:

```html
  <nav class="tabs" role="tablist" aria-label="reels">
    <button id="tab-pile" class="tab" type="button" role="tab" aria-selected="true">pile</button>
    <button id="tab-favorites" class="tab" type="button" role="tab" aria-selected="false"><span data-icon="starFilled"></span>favorites<span id="favorites-n" class="tab-count"></span></button>
  </nav>
```

with:

```html
  <div class="board-bar">
    <nav class="tabs" role="tablist" aria-label="reels">
      <button id="tab-pile" class="tab" type="button" role="tab" aria-selected="true">pile</button>
      <button id="tab-favorites" class="tab" type="button" role="tab" aria-selected="false"><span data-icon="starFilled"></span>favorites<span id="favorites-n" class="tab-count"></span></button>
    </nav>
    <button id="search-toggle" class="search-toggle" type="button" aria-expanded="false" aria-controls="search" aria-label="search"></button>
    <div id="search" class="search" role="search">
      <div class="search-field">
        <span class="search-icon" data-icon="search"></span>
        <input id="search-input" type="search" enterkeyhint="search" autocapitalize="off" autocorrect="off" spellcheck="false" placeholder="search captions" aria-label="search captions">
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

Then, after the `#empty-favorites` block (after its closing `</div>`, before `<footer class="board-foot">`), add:

```html
  <div id="empty-search" class="empty-search" hidden>
    <p class="empty-title">nothing matches</p>
    <button id="search-clear" class="btn" type="button">clear search</button>
  </div>
```

- [ ] **Step 4: The styles**

In `reels_api/static/style.css`:

(a) Replace the tabs section header and the `.tabs` rule:

```css
/* ---- tabs: pile and favorites (favorites spec 6) ---- */

.tabs { display: flex; gap: 6px; padding: 0 2px 10px; }
```

with:

```css
/* ---- tabs: pile and favorites (favorites spec 6), and search (search spec 4.2) ---- */

/* The tabs, the search toggle and, on its own line on a phone, the search row. */
.board-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 6px; padding: 0 2px 10px; }
.tabs { display: flex; gap: 6px; }
```

(b) Replace the selector line `.empty-favorites {` with `.empty-favorites, .empty-search {` (the rule's body stays as it is).

(c) Directly after the `.tab-count:empty { display: none; }` line, add:

```css
.search-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  margin-left: auto;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  color: var(--ink-50);
}
.search-toggle .icon { width: 16px; height: 16px; }
/* A class, not [hidden]: the desktop shows the row while it's "closed". */
.search { display: none; flex-basis: 100%; flex-direction: column; gap: 8px; }
.search.is-open { display: flex; }
.search-field {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  background: var(--surface);
}
.search-field:focus-within { border-color: var(--accent); }
.search-icon { color: var(--ink-50); }
.search-icon .icon { width: 14px; height: 14px; }
.search-field input {
  flex: 1;
  min-width: 0;
  height: 100%;
  padding: 0;
  border: 0;
  outline: none;
  background: transparent;
  -webkit-appearance: none;
  appearance: none;
  font: 400 16px var(--font); /* 16px: iOS zooms into smaller inputs */
  color: var(--ink);
}
.search-field input::placeholder { color: var(--ink-42); opacity: 1; }
.chips { display: flex; gap: 8px; }
/* Pressed is an outline, so it doesn't read as the selected tab, which is filled. */
.chip {
  height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  font: 600 12px var(--font);
  color: var(--ink-50);
}
.chip[aria-pressed="true"] { border-color: var(--ink); color: var(--ink); }
```

(d) In the desktop block (`@media (min-width: 700px)`), replace:

```css
  .tabs { max-width: 1100px; margin: 0 auto; padding: 0 0 16px; }
```

with:

```css
  .board-bar { max-width: 1100px; margin: 0 auto; padding: 0 0 16px; }
  .search-toggle { display: none; }
  .search { display: flex; flex-basis: auto; flex-direction: row; align-items: center; gap: 10px; margin-left: auto; }
  .search-field { width: 220px; height: 32px; }
```

- [ ] **Step 5: Run the page tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_web.py -q -k "search"`
Expected: 3 passed.

- [ ] **Step 6: The board applies the filter**

In `reels_api/static/board.js`:

(a) Change the `createBoard` signature and add the `match` state. Replace:

```js
export function createBoard({ grid, empty, emptyFavorites, count, tabs, favoritesCount, onOpen }) {
  let reels = []; // every reel from the server, newest first
  let tab = "pile";
```

with:

```js
export function createBoard({ grid, empty, emptyFavorites, emptySearch, count, tabs, favoritesCount, onOpen }) {
  let reels = []; // every reel from the server, newest first
  let tab = "pile";
  let match = null; // the search: null, or reel => true for the reels to show (search spec 5.2)
```

(b) Replace `shown`:

```js
  function shown(now = Date.now()) {
    if (tab === "pile") return reels.filter((reel) => inPile(reel, now));
    return reels.filter((reel) => reel.favorite).sort(byNewestStar);
  }
```

with:

```js
  // The open tab's reels, then only the ones the search matches.
  function shown(now = Date.now()) {
    const list = tab === "pile"
      ? reels.filter((reel) => inPile(reel, now))
      : reels.filter((reel) => reel.favorite).sort(byNewestStar);
    return match ? list.filter(match) : list;
  }
```

(c) In `render()`, replace:

```js
    const onPile = tab === "pile";
    for (const tile of pending) tile.hidden = !onPile;
```

with:

```js
    const onPile = tab === "pile";
    // A paste in flight has no caption to match, so it hides while searching (search spec 3.3).
    for (const tile of pending) tile.hidden = !onPile || match !== null;
```

(d) In `render()`, replace:

```js
      updateTile(tile, reel, onPile && i === 0, now);
```

with:

```js
      updateTile(tile, reel, onPile && !match && i === 0, now); // ▶ marks the newest reel, not the newest match
```

(e) In `render()`, replace:

```js
    const total = onPile ? pileTotal : favoriteTotal;
    grid.hidden = total === 0;
```

with:

```js
    const total = onPile ? pileTotal : favoriteTotal;
    // The tab has reels but the search matches none of them (search spec 3.4).
    const noMatches = match !== null && total !== 0 && list.length === 0;
    grid.hidden = total === 0 || noMatches;
    emptySearch.hidden = !noMatches;
```

(f) In the returned object, directly after the `setReels(list) { ... },` entry, add:

```js
    // The search's match, or null for none. No scrolling: the page would jump while someone types.
    setFilter(next) {
      match = next;
      render();
    },
```

(g) Update the comment above `getShown()` from `// The open tab's reels, in its order: the player's list.` to:

```js
    // The open tab's reels that match the search, in its order: the player's list.
```

- [ ] **Step 7: Wire it in `app.js`**

In `reels_api/static/app.js`:

(a) After `import { createPlayer } from "./player.js";` add:

```js
import { createSearch } from "./search.js";
```

(b) In the `createBoard({...})` call, after `emptyFavorites: $("empty-favorites"),` add:

```js
  emptySearch: $("empty-search"),
```

(c) Directly after the `createBoard({...});` statement (before `const player = createPlayer(`), add:

```js
// Search filters the board; the player gets the filtered list through board.getShown() (search spec 5.3).
const search = createSearch({
  row: $("search"),
  toggle: $("search-toggle"),
  input: $("search-input"),
  chips: [...document.querySelectorAll("#search .chip")],
  clearButton: $("search-clear"),
  onChange: (match) => board.setFilter(match),
});
```

(d) In `createPaste({...})`, replace:

```js
  onStart: () => {
    pastedOver = new Set(board.getReels().map((reel) => reel.id));
```

with:

```js
  onStart: () => {
    search.clear(); // the new tile, or the reel it turns out to be, must not be hidden (search spec 3.5)
    pastedOver = new Set(board.getReels().map((reel) => reel.id));
```

- [ ] **Step 8: Syntax check**

Run (Git Bash, repo root):

```bash
d=$(mktemp -d); for f in app.js board.js search.js; do cp "reels_api/static/$f" "$d/${f%.js}.mjs" && node --check "$d/${f%.js}.mjs" || echo "SYNTAX ERROR: $f"; done
```

Expected: no output.

- [ ] **Step 9: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 402 passed, 1 deselected.

- [ ] **Step 10: Commit**

```bash
git add reels_api/static/app.html reels_api/static/style.css reels_api/static/board.js reels_api/static/app.js tests/test_web.py
git commit -F - <<'EOF'
feat: search and source chips on the board, behind a toggle on phones

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

---

### Task 3: Dev board caption and the check by hand

**Files:**
- Modify: `scripts/dev_board.py` (`CAPTIONS`)

**Interfaces:**
- Consumes: the working board from Task 2.
- Produces: a seed whose caption is `café au lait, but make it iced`. With 7 captions and `CAPTIONS[i % 7]`, it is seed 6 (source `SEED_SOURCES[6 % 4]` = Instagram). The caption-less seeds are 4 and 11; their title is `reel seed04` / `reel seed11` (`store_clip`: `caption[:40] or f"reel {job.id}"`).

- [ ] **Step 1: Add the caption**

In `scripts/dev_board.py`, in `CAPTIONS`, after the line `"how to fold a fitted sheet (it is not possible)",` add:

```python
    "café au lait, but make it iced",  # an accent, to try search's accent folding
```

- [ ] **Step 2: Run the dev board tests and the suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 402 passed, 1 deselected (`tests/test_dev_board.py` doesn't depend on the captions).

- [ ] **Step 3: Start the dev board (Docker; ffmpeg isn't installed locally)**

Run (PowerShell, repo root):

```powershell
docker build -t reels-dev .
docker run --rm -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app `
  -v "${PWD}/reels_api:/app/reels_api:ro" -v "${PWD}/scripts:/app/scripts:ro" `
  reels-dev python scripts/dev_board.py --host 0.0.0.0
```

Open `http://localhost:8000/` in Chrome, choose "allow cookie & log in" and log in with `dev`. If this session has no browser tools, stop here and hand the checklist below to the user.

- [ ] **Step 4: Check by hand, phone width** (DevTools device toolbar, e.g. iPhone 12 Pro, 390px)

1. The board looks as before, plus a round ⌕ at the right of the tabs row. Tapping it opens the field and the four chips under the tabs, the field has focus, and the ⌕ is now ✕.
2. `CAT` shows only the two "cat vs cucumber, round 2" seeds (3, the NSFW X one, and 10). `gas taco` and `taco gas` both show only the two taco seeds (2 and 9).
3. `cafe` shows the café seed; so does `CAFÉ`.
4. `seed04` shows the caption-less seed 4 (found by its title).
5. Chip `x` with no text: only the X seeds (3, 7). Type `cat`: seed 3 only. Chip `tiktok` with `cat`: nothing matches (the cat seeds are X and Instagram), so "nothing matches" and "clear search" show. "clear search" gives back every reel, `all` is pressed again, the field is empty, and the row stays open.
6. The counts ("N in the pile", the favorites number) show the same numbers with and without a filter.
7. With `cat` typed, switch to favorites and back: the filter stays on both tabs.
8. Filter to two or three reels, open one: swiping up and down moves only through the matches. On the favorites tab (seeds 1 and 11), chip `tiktok` leaves only seed 1, and swiping in the player never reaches seed 11.
9. ✕ closes the row and gives back exactly the board from before, the ▶ on the newest tile included.
10. With `cat` typed, paste `https://www.tiktok.com/@dev/video/1234567890123`: the filter clears, the row closes, and the pending tile shows at the top.
11. Paste `https://www.tiktok.com/@dev/video/9876543210987` and, while it is still fetching (3 seconds), open search and type `zzz`: the pending tile hides. Clear the search: the new reel is there.
12. With a filter on, wait 30 seconds (or switch tabs away and back to the browser): no hidden reel comes back.
13. Type `cat` (seed 5 is hidden), scroll down a little, then paste seed 5's own link, `https://www.tiktok.com/@dev/video/5`: the filter clears and the board scrolls to seed 5 (a link already in the pile, spec 3.5).
14. Enter / "search" on the keyboard only hides the keyboard and keeps the filter. DevTools can't show a phone keyboard: check this one on a real phone after deploy.

- [ ] **Step 5: Check by hand, desktop width** (DevTools toolbar off, window over 700px wide)

15. There's no ⌕. The field (220px) and the chips sit on the right of the tabs row, on one line.
16. Typing filters. The player overlay's ← → move only through the matches, and Esc closes it.
17. Pasting in the top bar while filtered clears the field and puts the chip back on `all`.

- [ ] **Step 6: Stop the dev board**

Ctrl+C in its terminal (the `--rm` container removes itself).

- [ ] **Step 7: Commit**

```bash
git add scripts/dev_board.py
git commit -F - <<'EOF'
feat: dev board has a caption with an accent, to try search with

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```

If any manual check failed, fix it in the task that owns the code (Task 1 for matching and the row's behaviour, Task 2 for layout and the board), rerun the suite and its syntax check, and commit the fix as `fix: ...` before this task's commit.

---

### Task 4: Docs

**Files:**
- Modify: `README.md` ("The board", "Trying the board without downloading anything")
- Modify: `CLAUDE.md` ("Frontend")

**Interfaces:**
- Consumes: the behaviour from Tasks 1–3, as described in the spec.

- [ ] **Step 1: README, "The board"**

In `README.md`, after the **Delete** bullet (it ends "…while they are still in the pile."), add:

```markdown
- **Search**: on a phone, ⌕ next to the tabs opens a search field and the
  source chips (all, tiktok, instagram, x); on a desktop they are always
  there. The open tab then shows only the reels from that source whose
  caption or title has every word typed, in any order, ignoring case and
  accents, and the player swipes through those only. The counts stay as
  they are. ✕ closes it and shows everything again, pasting a link clears
  it, and a reload starts without it. Instagram and X account names are
  found through the title; TikTok's aren't.
```

- [ ] **Step 2: README, dev board**

In `README.md`, in "Trying the board without downloading anything", after the sentence ending "…so it only shows on the favorites tab." add:

```markdown
One seed's caption has an accent ("café au lait…"), to try search with.
```

- [ ] **Step 3: CLAUDE.md, "Frontend"**

In `CLAUDE.md`, in the **Frontend** paragraph:

(a) Replace this text:

```markdown
which wires `board.js`, `paste.js`, `player.js` and `cookie.js` together with callbacks. Those four never import each other;
```

with:

```markdown
which wires `board.js`, `paste.js`, `player.js`, `cookie.js` and `search.js` together with callbacks. Those five never import each other;
```

(b) Replace this text:

```markdown
The player gets the open tab's list (`board.getShown()`).
```

with:

```markdown
The player gets the open tab's list (`board.getShown()`). **Search** (`search.js`, search spec `docs/superpowers/specs/2026-09-26-search-and-filter-design.md`) turns the search row into a match function, `reel => boolean` or `null`, and `app.js` hands it to `board.setFilter`; `getShown()` is the open tab filtered by it, so the player swipes through matches only, while the counts and the tabs' empty states stay unfiltered. A paste start calls `search.clear()`. The row is a class (`is-open`), not `hidden`, because the desktop always shows it.
```

(c) At the end of the paragraph, replace this text:

```markdown
; `(web spec …)` refers to `…-mobile-web-page-design.md`.
```

with:

```markdown
; `(web spec …)` refers to `…-mobile-web-page-design.md`, and `(search spec …)` to `…-search-and-filter-design.md`.
```

- [ ] **Step 4: Check the docs name only what exists**

Run (Git Bash):

```bash
grep -n "setFilter\|search.clear\|is-open" reels_api/static/*.js | head
```

Expected: `board.js` has `setFilter`, `app.js` calls `search.clear()` and `board.setFilter`, `search.js` toggles `is-open`, matching what CLAUDE.md now says.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md
git commit -F - <<'EOF'
docs: search and filter in README and CLAUDE.md

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>
EOF
```
