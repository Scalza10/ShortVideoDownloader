# More Sources — Design

Date: 2026-10-30
Status: approved, implemented

## 1. Purpose

Friends also send YouTube Shorts, Reddit videos and Facebook Reels. yt-dlp
already downloads all three; the allow-list, the extractor guard and the page's
source labels are what keep them out. Opening the door to longer sites also
needs a length limit, which the app has never had: a 40-minute video would
download until the job timeout cuts it off.

## 2. Which links

| Source | `source` | Hosts | Accepted |
|---|---|---|---|
| YouTube | `youtube` | `youtube.com`, `www.`, `m.` | `/shorts/<id>` only |
| Reddit | `reddit` | `reddit.com`, `www.`, `old.`, `new.`, `m.`, `redd.it`, `v.redd.it` | any path |
| Facebook | `facebook` | `facebook.com`, `www.`, `m.`, `web.`, `fb.watch` | any path |

- YouTube is **Shorts only**: `watch?v=`, `youtu.be`, channels and playlists are
  `unsupported_url`. The Shorts path is checked in `detect_source`.
- `unsupported_url`'s message names every site.
- `Source` gains the three values. This is additive in the job JSON, but the
  `jobs.json` caveat holds: once a reel from a new source is saved, rolling
  back to an older build wipes the pile.

## 3. One spelling per video

`normalize_url`, so a re-paste finds the same jobs:
- a Short becomes `https://www.youtube.com/shorts/<id>` (drops `?si=`, the host
  variant and anything after the id);
- a Reddit link loses its query (`?utm_source=share…`, `?share_id=`);
- Facebook is left alone: `watch/?v=` needs its query.

## 4. The extractor guard, for every new source

X already runs with only the twitter extractors, so a post that merely links
elsewhere can't be followed off the allow-list. The new sources get the same,
from one table (`ALLOWED_EXTRACTORS` in `downloader.py`):

| Source | yt-dlp extractors |
|---|---|
| X | `twitter`, `twitter:card`, `twitter:amplify` |
| YouTube | `youtube` |
| Reddit | `Reddit` |
| Facebook | `facebook`, `facebook:reel` |

Instagram and TikTok keep the default extractors, as before. A Reddit post
linking to another site ends as "No suitable extractor", which maps to
`no_video`.

**Share links.** The phone apps share short links that none of these
extractors match: Reddit's `/r/<sub>/s/<code>`, `redd.it/<id>`,
`v.redd.it/<id>`, Facebook's `/share/r/…`, `/share/v/…` and `fb.watch/…`.
yt-dlp normally reaches them through its generic extractor, which the guard
shuts out (and which would follow anything). So when no allowed extractor
matches a link, the downloader follows its redirects itself (yt-dlp's
`urlopen`, with the cookies) and goes on with the final URL, but only if that
URL is still on the same source's hosts. Otherwise:
- a final URL on another site, or on the same site with no matching
  extractor: `no_video`, or `login_required` when the path mentions login
  (Facebook sends logged-out visitors to its login page);
- an HTTP error while following: mapped like a yt-dlp error (404 →
  `private_or_removed`, else usually `platform_blocked`).

The job keeps the pasted URL; only the download uses the final one.

## 5. Length limit

- `MAX_DURATION_SECONDS`, default 180 (3 minutes), for every source, X included.
- yt-dlp gets a `match_filter` that skips a video longer than that before
  anything is downloaded; the downloader then fails the job with the new
  `too_long` code ("Videos longer than 3 minutes aren't supported.", the
  number following the setting). Without that check a skipped video would end
  as "the download produced no file", `platform_blocked`.
- Some extractors don't report a duration, so the pipeline checks ffprobe's
  duration as well and fails with `too_long` there too (its usual cleanup
  deletes the outputs). That check allows one second over: a 3:00 Short's file
  is often a fraction longer than the 180 YouTube reports.
- `too_long` is only ever raised inside a job, so it needs no HTTP mapping.
  `/health`'s `recent` counts it like any other code.

## 6. Captions

- YouTube: the title is the caption. A Short's description is mostly links and
  hashtags.
- Reddit: the post title (no description, so the existing fallback).
- Facebook: description, then title, like Instagram. Facebook's title is
  "9.9K views · 340 reactions | <caption> | <page>"; the counts and the page
  name (yt-dlp's `uploader`) are dropped, so the title is the caption too.

## 7. YouTube needs a JavaScript runtime

Current yt-dlp solves YouTube's player challenges with Deno and the
`yt-dlp-ejs` scripts; without them YouTube downloads mostly fail.
`requirements.txt` pins both (`yt-dlp-ejs` at the version yt-dlp's `default`
extra names, `deno` from PyPI, which ships the binary for x86-64 and aarch64).
Bump them with yt-dlp.

## 8. Expected failures

**Reddit needs cookies.** yt-dlp's Reddit extractor refuses every video
without a logged-in account ("Account authentication is required"), from any
address, so Reddit links fail with `login_required` until `COOKIES_FILE` holds
reddit.com cookies (one file holds every site's cookies).

YouTube often refuses datacenter addresses (an Oracle VM is one): expect some
`platform_blocked` or `login_required` there. `COOKIES_FILE` can hold its
cookies too, as it does for Instagram and X.

## 9. The page

- `SOURCE_NAME` in `format.js` gets "YouTube", "Reddit" and "Facebook" (the
  player's and tiles' source line).
- The search row's source chips get `youtube`, `reddit` and `facebook`. Seven
  chips don't fit a phone, so the chip row scrolls sideways.
- `too_long` needs nothing new: the paste flow shows the job's message.

## 10. Dev board

Seeds include YouTube and Reddit reels, and a pasted URL containing `long`
fails with `too_long`.
