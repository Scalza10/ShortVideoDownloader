# Favorites, Delete and a Pile That Survives Restarts — Design

Date: 2026-09-24
Status: approved design, pre-implementation
Builds on: `2026-09-16-reels-download-api-design.md` (the "API spec"),
`2026-09-16-reels-board-ui-design.md` (the "board spec") and
`2026-09-17-invite-and-share-links-design.md` (the "links spec")

## 1. Purpose

Three things people want from the pile:

- **It survives deploys and restarts.** Today every restart empties it: the
  videos are still in `data/`, but the list of which file is which reel
  lives only in memory, so startup deletes them as strays.
- **Favorites.** A ★ keeps a reel past its 12 hours, until someone
  un-stars it, up to 200 favorites. They have their own tab on the board.
- **Delete.** Anyone logged in can delete a reel right away instead of
  waiting for it to age out. A mistaken tap is undone from a toast.

Favorites belong to the whole group, like the pile: there are no accounts,
so there is one list of favorites, and anyone logged in can star, un-star
or delete anything.

Sizing: production is an Oracle A1.Flex VM with 2 OCPU, 12 GB RAM and a
~47 GB boot disk, going by `docs/DEPLOY-ORACLE.md` (not checked on the VM).
Reels are estimated at 5–15 MB each, so the most this keeps at once, 100
pile reels plus 200 favorites, is about 3 GB.

Out of scope (section 12): search and filter (a separate change), telling
a deleted reel from an expired one, a disk-space guard.

## 2. Saving the pile: `jobs.json`

**Where:** `STORAGE_DIR/jobs.json` (production: `/data/files/jobs.json`).
`_remove_untracked_files` only looks at `STORED_SUFFIXES` (`.mp4`, `.jpg`),
so it leaves the file alone. No new setting.

**Module:** `reels_api/jobs_file.py`, two plain functions, so they can be
tested without the app:

- `save(path, jobs)` writes the jobs.
- `load(path, storage_dir) -> list[Job]` reads them back.

**Format:**

```json
{"version": 1, "jobs": [ { ...one reel... } ]}
```

Each reel holds `id`, `url`, `item`, `source`, `share_key`, `created_at`,
`finished_at`, `expires_at`, `favorite`, `starred_at`, and from its result
`title`, `caption`, `duration_seconds`, `size_bytes`, `width`, `height`,
`nsfw` and `has_thumbnail`. Times are ISO 8601 in UTC.

- File paths are not stored. `load` rebuilds them from the id:
  `storage_dir/<id>.mp4`, and `storage_dir/<id>.jpg` when `has_thumbnail`.
- Only `done` reels are saved. Queued, running and failed jobs are not, so a
  restart loses them as today.

**Writing:**

- The manager saves after:
  - a reel finishes (after `enforce_video_cap`);
  - star, un-star and delete;
  - every sweep.
- The write goes to `jobs.json.tmp`, is flushed and `fsync`ed, and then
  `os.replace`s `jobs.json`. A crash leaves the old file or the new one,
  never half of one.
- One save at a time, under an `asyncio.Lock`. The snapshot of the jobs is
  taken inside the lock, so the last write always holds the newest state.
  The write itself runs in a thread (`asyncio.to_thread`).
- A failed write (disk full, permissions) is logged and ignored. Memory
  stays the source of truth, and the next change writes again.

**Startup** (`JobManager.start`), in this order:

1. `load` the file. Loaded reels are *added* to the store, and a loaded id
   that the store already has is skipped. Anything seeding jobs before
   startup, such as `dev_board.py`, keeps its seeds.
2. Reels whose `.mp4` is missing are dropped (logged).
3. `sweep` removes reels past their 12 hours, skipping favorites (section
   3), and deletes untracked files as today.
4. `enforce_video_cap` applies the 100-video limit to non-favorites.
5. Save, so the file matches what survived.
6. Start the workers and the hourly sweeper.

**A file that can't be used** (not JSON, a missing field, an unknown
`version`): it is renamed to `jobs.json.bad`, overwriting an older `.bad`,
with a warning in the log. The app starts with an empty pile, as it does
today. No file at all is normal: an empty pile, with no warning.

## 3. Favorites (server)

**`Job`** gains `favorite: bool = False` and
`starred_at: datetime | None = None`.

**`expires_at` keeps its meaning:** when the reel leaves the pile
(`finished_at` + `RETENTION_HOURS`). A favorite is kept past it. Starring
and un-starring never change it.

**Kept:**

- `sweep` skips favorites.
- `enforce_video_cap` counts and evicts only non-favorites.

So at most `MAX_VIDEOS` + `MAX_FAVORITES` reels are kept (100 + 200).

**Starring:** `JobManager.set_favorite(job_id, on)`.

- Only a `done` job can be starred or un-starred. Anything else is not
  found.
- Starring sets `favorite` and `starred_at` = now. Starring a favorite
  changes nothing, not even `starred_at`, and is never refused, even when
  favorites are full.
- Starring when `MAX_FAVORITES` favorites exist raises
  `JobError(FAVORITES_FULL)`. The count and the set happen with no `await`
  in between, so two phones can't both take the last slot.
- Un-starring clears `favorite` and `starred_at`. Un-starring a reel that
  isn't a favorite changes nothing.
- An un-starred reel past its `expires_at` is removed by the next hourly
  sweep. The page doesn't wait for that; it deletes (section 8).
- Lowering `MAX_FAVORITES` below the current count keeps every favorite.
  Only new stars are refused until there's room.

**New error:** `ErrorCode.FAVORITES_FULL`, `"favorites_full"`. Its message
names the limit: "Favorites are full (200). Remove one first." `main.py`
maps it to `409`.

**New setting:** `MAX_FAVORITES`, default 200, at least 1. It goes in
`.env.example` next to `MAX_VIDEOS`.

**Share links** to a favorite keep working while it is kept. `web.index`
needs no change, because it only checks that the job exists and its file
is there.

## 4. Delete (server)

`JobManager.delete(job_id)`:

- Only a `done` job can be deleted. Anything else is not found.
- It runs `_discard`, which deletes `<id>.mp4`, `<id>.jpg` and the store
  entry, then saves `jobs.json`.
- It works the same on favorites.
- After it:
  - the reel's share links show the expired page (`web.index`: unknown
    job);
  - its `/files/` URLs are `404`;
  - pasting its link again queues a fresh download, because
    `find_active_by_url` no longer finds it.

## 5. The API and the job JSON

| Endpoint | Returns |
|---|---|
| `PUT /jobs/{id}/favorite` | `200` and the job JSON. `404 not_found` unless done, `409 favorites_full` when full. |
| `DELETE /jobs/{id}/favorite` | `200` and the job JSON. `404 not_found` unless done. |
| `DELETE /jobs/{id}` | `204`. `404 not_found` unless done. |

- All three need the API key or the login cookie (`protected` router). A
  share key never opens them.
- Deleting through the API is immediate and final; the undo exists only
  on the page.
- `GET /jobs` still lists every done reel, favorites included, newest first
  by `finished_at`.

The done job JSON gains two fields. This is additive:

```json
"favorite": true,
"starred_at": "2026-09-24T18:02:11Z"
```

`starred_at` is `null` when not a favorite.

## 6. The page: tabs

Tabs go under the top bar, above the grid, in `app.html`:

```
reels            42 in the pile
[ paste a link           ][add]

[ pile ]  [ ★ favorites 12 ]
```

- Markup: `<nav class="tabs" role="tablist">` with two `role="tab"`
  buttons that use `aria-selected`. Switching tabs doesn't touch history.
- The board keeps the whole list from `GET /jobs` and shows one tab of it:
  - **pile:** every reel except favorites past their `expires_at`. This
    is what the pile shows today, plus a ★ on starred tiles. The top bar's
    "N in the pile" counts this tab, pending tiles included, as today.
  - **favorites:** every reel with `favorite`, newest `starred_at` first.
    The tab label shows their number.
- **A starred tile** gets a small ★ in its top-right corner, in both tabs.
  The age badge stays as it is ("3d" for an old favorite; `formatAge`
  already does days).
- **Empty favorites tab:** its own empty state, "no favorites yet" and
  "tap ★ on a reel to keep it past 12 hours."
- **The board always opens on pile.**
- **Pasting while on favorites** switches to pile, where the pending tile
  appears. When the paste resolves to an existing reel (`existed` in
  `app.js`), the board switches to the tab that shows it and scrolls to it.
- **The player gets the list of the tab it was opened from.** Swiping stays
  in that tab, and a refresh while it is open adds only reels of that tab
  (`addReels`).
- **A `?reel=` link** opens in the tab that holds the reel: favorites for
  an old favorite, otherwise pile.

## 7. The page: the player's buttons

**On the phone**, the chrome's top row gains two round buttons after the
spacer, away from Share and Save:

```
(x)  TikTok · 0:19 · gone in 6h      (☆) (🗑)
```

**On the desktop**, the side panel gains a third row under
Download / Copy link: `☆ favorite` and `delete`.

- The star is outlined when not a favorite, filled in the accent colour
  when it is. It uses `aria-pressed`, and its label is "add to favorites"
  or "remove from favorites".
- Delete's label is "delete".
- For a favorite, the info line (`sourceLine`) ends "★ kept" instead of
  "gone in 6h".
- `icons.js` gains `star`, `starFilled` and `trash`, in the style of the
  existing icons.
- `player.js` doesn't call the server. It reports taps through two new
  callbacks, `onFavorite(reel, on)` and `onDelete(reel)`, and `app.js` does
  the rest.
- New player methods:
  - `update(reel)` redraws the current reel's star and info line;
  - `remove(id)` drops a reel from the player's list and moves to the next
    one, or closes when none are left.
- **The view-only page (`watch.html`) gets neither button.** This is a
  deliberate exception to "mirror the player markup in both pages". A
  visitor there has no cookie, so the calls would fail anyway. `player.js`
  treats both buttons as optional, as it does `prev`/`next`.

## 8. The page: undo and toasts

**`showToast`** gains an optional action,
`showToast(message, { error, action: { label, onClick } })`:

- With an action, the toast shows the button and stays up 5 seconds.
- The existing toasts don't change (2.5 seconds, no button).
- A new toast still replaces the current one. A replaced toast's action
  can no longer be tapped, which matters for pending deletes (below).

**Delete** (from the delete button, and from un-starring an old reel):

1. The reel leaves the board and the player (`player.remove`) at once.
   The toast says "deleted · undo", or "removed · undo" for an un-star.
2. `app.js` keeps it in a map of pending deletes, with a 5-second timer.
   Refreshes during the wait hide every reel in that map.
3. Undo in time: the timer is cancelled, nothing was sent, and the reel
   is back in its place on the board. An open player doesn't get it back;
   it is there again the next time the player opens.
4. When the timer ends, `DELETE /jobs/{id}` is sent.
5. The delete is also sent at once, not after the timer, when:
   - the page is hidden (`visibilitychange` to hidden, or `pagehide`),
     sent with `fetch(…, { keepalive: true })` so it survives the page
     closing;
   - another toast replaces its toast, since its undo is then gone.
6. Success, or a `404` (someone else deleted it first): done.
   Any other failure: the reel comes back, with the error toast
   "couldn't delete. try again."

**Star and un-star** send at once:

| Tap | What happens |
|---|---|
| Star | Toast "added to favorites", no undo. |
| Star when full (`409`) | Error toast "favorites are full (N). remove one first.", with N the favorites the page has. The star stays off. |
| Un-star, reel within its 12 hours (`expires_at` in the future) | Toast "un-starred · undo". Undo stars it again (it goes to the top of favorites, as `starred_at` is new). |
| Un-star, reel past its 12 hours | Not sent at all. It is a delete: steps 1–6 above. |
| Star or un-star fails (network, `404`) | Error toast "couldn't save that. try again.", and the star shows the old state. |

After a successful star or un-star, the board takes the job JSON from the
response and redraws that reel, and `player.update` redraws the player.

**`api.js`** gains:

- `setFavorite(id, on)`, which returns the job, or `{ error }` with the
  server's code;
- `deleteJob(id, { keepalive })`.

Both go through `api()`, so a `401` reloads to the login page as
everywhere else.

## 9. Dev board

- Two seeds are favorites:
  - one within its 12 hours, so the pile shows it with ★;
  - one finished 3 days ago, so it shows only on the favorites tab.
- The seeds are still added before the app starts. Section 2's merge keeps
  them, and the startup sweep skips the old one because it is a favorite.
- New option `--dir <path>`: use that directory instead of a fresh temp
  one, and keep it on exit. Today every run starts in a new temp dir and
  deletes it, so nothing could survive a restart. With `--empty --dir`,
  reels pasted and starred in one run are back in the next. Seeds would get
  in the way: a seed id already in the store wins over the saved one, so a
  seed's star from the last run is lost.

## 10. Docs

- **README:**
  - The pile survives restarts and deploys. Rewrite the "Restarting the
    app empties the pile" paragraph and the Deploy section's "the restart
    empties the pile".
  - Favorites, the tabs and delete, in "The board".
  - The three endpoints and `favorite`/`starred_at` in "JSON API".
  - `favorites_full` in the failure codes.
  - `MAX_FAVORITES` in "Configuration".
- **CLAUDE.md:**
  - Rewrite "State is in memory only": memory is the source of truth,
    `jobs.json` is its copy on disk, and a restart keeps the pile. Keep the
    three deleters, plus `delete`.
  - Point to this spec.
  - `jobs.json` is not a per-reel file, so "Adding a new stored file type"
    doesn't apply to it.
- **`scripts/deploy.ps1`**: its header says running jobs "and the Recent
  feed" are lost. Only running jobs are now.

## 11. Testing

Unit tests, no network:

- `jobs_file`:
  - `save` then `load` gives the same reels, favorites, times and paths;
  - a reel without a thumbnail has no `.jpg` path;
  - only `done` jobs are saved;
  - the write replaces the file in one step (no `.tmp` left behind);
  - garbage, a missing field or an unknown version: renamed to `.bad`,
    empty result;
  - no file: empty result, no `.bad`.
- Startup:
  - a saved pile comes back, and its files are not deleted as strays;
  - an entry whose `.mp4` is gone is dropped;
  - an expired non-favorite is swept, an expired favorite is kept;
  - jobs already in the store (seeds) are kept, not overwritten.
- Favorites:
  - sweep and `enforce_video_cap` skip favorites, and the cap counts only
    non-favorites;
  - star and un-star are idempotent;
  - starring the 201st raises `favorites_full`;
  - a lowered `MAX_FAVORITES` keeps existing favorites.
- Routes:
  - `PUT` and `DELETE /jobs/{id}/favorite` return the job JSON with
    `favorite` and `starred_at`;
  - `409` when full; `404` for unknown and not-done jobs;
  - `DELETE /jobs/{id}` deletes both files and answers `204`, then
    `GET /jobs/{id}` is `404`;
  - all three answer `401` with only a share key;
  - each change is in `jobs.json` afterwards.
- `web.index`: a deleted reel's share link shows the expired page.
- `test_web.py`:
  - the view-only page has no favorite or delete button;
  - `APP_MODULES` still lists every module (no new module is planned).

By hand with `dev_board.py`, in the browser (no JS tests, per the board
spec):

- the tabs and their counts;
- the ★ on tiles in both tabs;
- the old favorite only in favorites;
- starring and un-starring, including undo;
- deleting with undo, and deleting then leaving the page before 5 seconds;
- the favorites-full toast: run with the environment variable
  `MAX_FAVORITES=2` (`-e MAX_FAVORITES=2` in the Docker command), and the
  two starred seeds fill it;
- with `--empty --dir <path>`: paste, star and delete, then restart, and
  the pile and favorites come back;
- a share link to a deleted reel shows "expired".

## 12. Out of scope

- **Search and filter** (source chips, caption search): the next change,
  on its own.
- **Telling "deleted" from "expired".** A share link to a deleted reel
  shows "this reel has expired". That would need a record of deleted ids.
- **Per-person favorites.** There are no accounts. One shared list.
- **A disk-space guard.** 300 reels is about 3 GB of a ~47 GB disk. Old
  Docker images from deploys are the likelier way to fill it, and pruning
  them is a separate ops change.
- **Keeping queued or running downloads across a restart.**
- **Deleting from a tile** (long press or swipe). Delete lives in the
  player.
- **Undo for API deletes.**
