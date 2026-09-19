# NSFW Cover — Design

Date: 2026-09-18
Status: approved design, pre-implementation
Builds on: `2026-09-18-x-links-design.md` (the "X links spec"),
`2026-09-16-reels-board-ui-design.md` (the "board spec") and
`2026-09-17-invite-and-share-links-design.md` (the "links spec")

## 1. Purpose

X videos can be NSFW. People on the board should know before one plays:

- **An NSFW reel is marked**, from X's own "sensitive content" flag.
- **Its tile is covered**: the thumbnail blurred and darkened, "NSFW" in red
  over it.
- **The player opens it covered**: paused, blurred, "NSFW · tap to watch".
  A tap uncovers and plays it.
- **Its WhatsApp preview shows no picture** and says "NSFW".

Out of scope (section 8): marking by hand, TikTok and Instagram, image
classifiers.

## 2. Where the flag comes from

yt-dlp's twitter extractor sets `age_limit` to 18 when the tweet is
`possibly_sensitive`, and 0 otherwise. X sets that flag per tweet, so every
video of a flagged tweet is NSFW. yt-dlp's TikTok and Instagram extractors
set no `age_limit`.

yt-dlp reads the flag only from the outer tweet and copies it into every
entry. A quoted tweet's video therefore carries the outer tweet's flag: an
unflagged tweet quoting an NSFW video arrives uncovered (section 8).

Logged out, X mostly refuses NSFW tweets altogether ("NSFW tweet requires
authentication", which maps to `login_required`). So NSFW reels mostly
appear once `COOKIES_FILE` holds x.com cookies (X links spec 5).

## 3. Server

- `MediaInfo.nsfw` is true when yt-dlp's `age_limit` is 18 or more. A
  missing or non-numeric `age_limit` is false.
- `JobResult.nsfw` (default false) carries it. The pipeline copies it from
  the download.
- The job JSON of a done job gains `"nsfw": true | false`. This is additive:
  curl clients and older pages ignore it.
- `render_watch` for an NSFW reel:
  - leaves out `og:image`, so link previews show no picture;
  - makes `og:description` "NSFW · X · 0:19";
  - keeps the caption as `og:title`.
  The view-only page itself gets the cover from the player (section 5).

## 4. The board tile

- An NSFW tile gets the class `nsfw` and a label `<span class="nsfw-label">NSFW</span>`
  in the middle.
- Its thumbnail is blurred and darkened with CSS
  (`filter: blur(…) brightness(…)`), scaled up well past the blur's reach so
  it has no soft edge. A tile without a thumbnail shows just the label.
- The image takes no pointer events and no iOS touch callout. A long press
  or a drag would otherwise offer the unblurred image. The tile is the
  button, so a tap still opens it.
- The label is red (`--danger-text`), bold, letter-spaced.
- The age badge and the hover row stay as they are.
- The tile stays covered after the reel has been watched: it is a label,
  not a lock.

## 5. The player

The player markup exists in `app.html` and `watch.html`; both gain the
same cover inside `.player-frame`, after the video:

```html
<div class="nsfw-cover" hidden>
  <span class="nsfw-label">NSFW</span>
  <button type="button" class="nsfw-reveal" data-action="reveal">tap to watch</button>
</div>
```

- `show()` covers the reel when `reel.nsfw` and it has not been uncovered
  on this page yet. Covered means:
  - the cover is visible;
  - the root has the class `is-covered`, which blurs the video and its
    poster with CSS;
  - `play()` does nothing, so opening, swiping onto it and the
    view-only page never start it;
  - a `play` listener pauses the video if anything else starts it while
    covered (media keys, the lock screen);
  - the chrome closes, so the cover is what shows.
- **Uncovering**: a tap on the frame (phone), a click on the frame
  (desktop) or the "tap to watch" button. It hides the cover, remembers
  the reel's id, and plays with the viewer's sound setting.
  - A reel opened from a link starts muted, like any link-opened reel, and
    so does its uncover.
  - When the button had keyboard focus on desktop, focus moves to the
    overlay's own first control, because the button hides.
- **The phone's other gestures still work while covered.** Swiping moves
  to the next reel, because the cover is not a button. Only its small
  button is, and a tap there uncovers too. The chrome (Share, Save, Copy
  link, caption) still opens: tapping uncovers first, and the next tap
  toggles the chrome as usual.
- The uncovered ids live in memory for as long as the page is open. A
  reload covers them again.
- On iPhone, the prefetch for Save starts in `show()` as today. It is not
  playback, so it doesn't wait for the uncover.

## 6. Dev board

- One seeded X reel is NSFW, so the cover shows on start.
- A pasted URL containing `nsfw` gives an NSFW reel.

## 7. Testing

Unit tests:
- `age_limit` 18 → `nsfw` true; 0, missing or junk → false.
- The pipeline copies `nsfw` into the result.
- The job JSON has `nsfw` when done.
- `render_watch` for an NSFW reel has no `og:image` and a description
  starting "NSFW · ", while a normal reel keeps both.
- dev_board's `nsfw` word and NSFW seed.

By hand with `dev_board.py`, in the browser:
- the NSFW seed's tile is blurred with red "NSFW";
- opening it shows it paused and covered, and a tap uncovers and plays it;
- swiping over a covered reel moves on;
- going back to an uncovered reel keeps it uncovered;
- a pasted `nsfw` link lands covered;
- the view-only page (share link) opens covered.

## 8. Out of scope

- **Marking by hand** and **TikTok/Instagram**: they have no flag, and the
  decision was X's flag only.
- **Image classifiers**: too heavy for the VM, and they have false
  positives.
- **Remembering uncovered reels across reloads.** The cover is a warning,
  and it is cheap to tap again.
- **A quoted tweet's own flag** (section 2). yt-dlp doesn't expose it.
  Reading it would mean replacing part of yt-dlp's twitter extractor.
