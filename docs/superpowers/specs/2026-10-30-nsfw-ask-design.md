# NSFW Ask — Design

Date: 2026-10-30
Status: approved, implemented
Replaces sections 4 and 5 of `2026-09-18-nsfw-cover-design.md` (the "NSFW
cover spec"); its sections 2 (where the flag comes from) and 3's WhatsApp
preview still hold.

## 1. Purpose

X flags many videos as sensitive that the group doesn't mind. A blurred tile
and a covered player for every one of them gets in the way. Instead, the person
who pastes one is asked once whether it should go on the pile, and from then on
it is a reel like any other.

## 2. The flag

Unchanged: `JobResult.nsfw` is yt-dlp's `age_limit` ≥ 18 (NSFW cover spec 2).
Logged out, X still refuses most NSFW tweets (`login_required`); this design
does not change that, `COOKIES_FILE` does.

## 3. Held until a yes

- A job whose result is NSFW finishes with `Job.held = True`.
- `GET /jobs` (the pile) leaves held jobs out. `GET /jobs/{id}` shows them,
  with `"held": true` in the done job's JSON (additive; `false` otherwise), so
  API clients still get `file_url`.
- `PUT /jobs/{id}/ok` releases one: `held` becomes false, the pile is saved,
  and the reel comes back. 404 when there is no such done job. It needs the key
  or the cookie, like every other `/jobs` route; a share key is not enough.
- "no" is the existing `DELETE /jobs/{id}`.
- `jobs.json` never holds a held job. After a restart its files are strays and
  the startup cleanup deletes them. One nobody answers is otherwise swept after
  `RETENTION_HOURS`. The video cap counts held jobs.
- Pasting a link that is still held returns the held job (the usual dedupe), so
  that person is asked too.

## 4. The page

- The paste flow (`paste.js`) hands a held job to `onHeld`, which `app.js`
  answers with a dialog (`#nsfw-ask`, `nsfw.js`): "this one's marked NSFW",
  **yes, add it** / **no, skip it**. Esc counts as no.
- Yes → `PUT /jobs/{id}/ok`, then the reel is added as after any paste. If that
  fails: the pending tile goes and a toast says "couldn't add that. try again."
- No → `DELETE`, and the pending tile goes. A skipped video is neither a
  failure nor a reel: an all-skipped paste returns the field to idle, with no
  error.
- An X post with several NSFW videos asks once per video, one at a time.
- No blur and no cover anywhere: the tile keeps a small red "NSFW" label in its
  top-left corner, for information only, and the player plays it like any
  other reel (both `app.html` and `watch.html`).
- The WhatsApp preview still has no picture and says "NSFW ·" (NSFW cover
  spec 3). It shows in chats of people who never saw the question.
