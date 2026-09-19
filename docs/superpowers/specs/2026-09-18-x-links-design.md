# X Links — Design

Date: 2026-09-18
Status: approved design, pre-implementation
Builds on: `2026-09-16-reels-download-api-design.md` (the "API spec") and
`2026-09-16-reels-board-ui-design.md` (the "board spec")

## 1. Purpose

The pile only takes Instagram and TikTok links. People also want to paste X
(Twitter) links and get the video. On X the video sits inside a tweet, so it
has to be pulled out of the tweet.

- **x.com and twitter.com links work** like Instagram and TikTok links:
  paste the link or the whole share text.
- **A tweet with several videos adds each video as its own reel.** That
  includes the video of a quoted tweet.
- **"Fixer" links work too.** People share fxtwitter.com, vxtwitter.com,
  fixupx.com and fixvx.com links so WhatsApp shows a preview. They are
  rewritten to x.com.
- **A tweet with no video says so** ("there's no video in that one.")
  instead of "got blocked".

Out of scope (section 8): several reels for Instagram carousels, t.co links,
keeping a tweet's videos in order on the pile.

## 2. What yt-dlp already does

Checked against the pinned yt-dlp 2026.8.19, and in a spike against real
tweets without logging in:

- `TwitterIE` handles `x.com` and `twitter.com` with `www.`, `m.` and
  `mobile.`: `/<user>/status/<id>`, `/<user>/status/<id>/video/<n>` and
  `/i/status/<id>`.
- The tweet's videos and GIFs, then the quoted tweet's, then card videos,
  become the entries. One entry gives a plain video, several a playlist.
- Public tweets work without logging in (guest token). NSFW and protected
  tweets raise a login error whose text mentions `--cookies`, so it already
  maps to `login_required`.
- A tweet without a video raises "No video could be found in this tweet".
  `/photo/1`-style picks raise "Media #1 is not a video". Deleted and
  suspended tweets raise "Twitter API says: This Post was deleted…" and
  "…from a suspended account".
- **A tweet without a video but with a link is followed to the linked
  site.** Without a guard, a tweet linking to YouTube would download the
  YouTube video, which gets around the allow-list (API spec).
- The `description` is the tweet text. It ends with the media's `t.co`
  link, and may have more `t.co` links before it that the author wrote.
- **X's `/video/<n>` counts photos too** and can't reach a quoted tweet's
  video or a card video. So the videos of a tweet are addressed by yt-dlp's
  `playlist_items` on the tweet URL, which indexes exactly the entries
  above. The spike downloaded entry 2 of a 4-video tweet this way.

## 3. Links

- New `Source.X`, value `"x"`. The job JSON's `source` can now be `"x"`, an
  additive change.
- `ALLOWED_HOSTS` gains `x.com` and `twitter.com`, each with `www.`, `m.`
  and `mobile.`.
- `t.co` stays unsupported: it can redirect anywhere.
- `normalize_url(url)` in `urls.py` gives every tweet one spelling. An
  http(s) link to an X host or a fixer host (`fxtwitter.com`,
  `vxtwitter.com`, `fixupx.com`, `fixvx.com`, or any subdomain of one, such
  as `d.fxtwitter.com`) becomes `https://x.com/<path>`, dropping query and
  fragment. Every other URL comes back unchanged. `submit` runs it between
  `extract_url` and `detect_source`, so the job stores the x.com link.
  - yt-dlp's twitter extractor only matches a lowercase host, so `X.com`
    would otherwise fail.
  - Dropping the query (`?s=46&t=…` share tracking) and mapping twitter.com
    to x.com make the same tweet shared by different people resolve to the
    same jobs.

## 4. Errors

- New `ErrorCode.NO_VIDEO`, `"no_video"`, message "This post has no video."
- The yt-dlp error patterns, first match wins:
  1. `no_video`: "no video could be found", "is not a video", "no suitable
     extractor" (what the guard in section 5 produces for a tweet that only
     links elsewhere, and for a profile or home link).
  2. `login_required`, unchanged. It must still come before "not available".
  3. `private_or_removed` also matches "deleted" and "suspended".
  4. `unsupported_url`, then the `platform_blocked` fallback, unchanged.
- The `unsupported_url` message becomes "Only Instagram, TikTok and X video
  links are supported."

## 5. Downloading

- Both yt-dlp calls share their options. **For X links only** these add
  `allowed_extractors: ["twitter", "twitter:card", "twitter:amplify"]`, so
  yt-dlp never follows a tweet's link to another site. Instagram and TikTok
  keep the default extractors.
- `download(url, dest_dir, cookies_file=None, item=1)` downloads entry
  `item` (`playlist_items`). Today's handling of `entries` already covers a
  one-entry playlist.
- `count_videos(url, cookies_file=None)` asks yt-dlp for the tweet without
  downloading or processing it (`process=False`). A playlist counts its
  entries, at most 9 (a tweet and its quoted tweet have 4 media each, plus a
  card). Anything else counts 1. **Any error counts 1**, so the job itself
  fails and reports the error the usual way. Its socket timeout is 8
  seconds, so a thread abandoned by the 20-second cap (section 6) doesn't
  run on much longer.
- The caption drops the last trailing `t.co` link, the media's own. Links
  the author wrote before it stay.
- The title drops every `t.co` link. yt-dlp keeps the link of a tweet that
  is only its video ("\<user\> - https://t.co/…"), and the title becomes the
  caption when the description is empty, and the download's file name.
- `COOKIES_FILE` already goes to both calls. It can hold x.com cookies next
  to the Instagram ones, for NSFW and protected tweets.

## 6. Jobs

- `Job.item` (default 1) is the entry to download. It is not in the job
  JSON.
- `Pipeline` gets an injectable `counter` (default `count_videos`) and a
  `count_videos(url)` method. `run` passes `item=job.item` to the
  downloader.
- `JobStore.find_active_by_url(url)` returns every job for that URL that has
  not failed, by `item`.
- `JobManager.submit(text)` returns a list of jobs:
  1. extract, normalize and check the URL;
  2. if jobs for that URL are active, return them (a repeat paste, no
     network);
  3. if the queue is full, raise `too_many_jobs` before asking X anything;
  4. count the videos for X links only, in a thread, for at most 20 seconds.
     A timeout or an error counts 1. A pipeline without `count_videos` (most
     fakes in the tests) counts 1;
  5. check for active jobs again, since a second paste may have arrived
     during the count;
  6. raise `too_many_jobs` unless the queue has room for all of them. A
     `MAX_QUEUE` below 9 can therefore refuse a big tweet every time; the
     default is 20;
  7. make one job per video (`item` 1 to n, same URL) and queue them.
- A tweet whose videos partly failed returns only the rest on a repeat
  paste. The failed ones are not retried, which keeps the one rule "failed
  jobs don't block".
- `POST /jobs` answers `{"id", "status", "ids"}`. `id` and `status` are the
  first job's, as before. `ids` lists every job of the paste, an additive
  change.

## 7. The page

- The board line and the link preview name the source "X" ("X · 0:19 · gone
  in 6h").
- Paste hints: `no_video` is "there's no video in that one.";
  `login_required` becomes "that one needs a login." since it is no longer
  always Instagram.
- After `POST /jobs` the paste field adds a pending tile for every extra
  video and polls every job at once. Each finished video replaces one
  pending tile with its reel. Each failed one removes a pending tile.
- When all of them are settled: if all failed, the paste field shows the
  error of the first one, as today. If some failed, a toast says "1 of 3
  didn't come through" and the field goes back to idle. Otherwise it goes
  back to idle.
- The board keeps a list of pending tiles instead of one. The pile count
  includes them.
- "Already in the pile" (scroll to it instead of adding it) is judged
  against the reels on the board when the paste started. An earlier video's
  pile reload may already show a later one, and that must not scroll the
  board.
- No new modules and no markup changes.

## 8. Out of scope

- **Instagram carousels** still give one reel, the first entry.
- **t.co links** stay unsupported (section 3).
- **Order on the pile.** The pile is newest first, so a tweet's videos
  appear in the reverse of the order they finished.
- **Retrying part of a tweet.** A repeat paste doesn't retry a failed video
  (section 6). X's own "copy link" on that video (`/video/<n>`) is a new URL
  and does.
- **A pile count one too high for a moment.** If a reload (an earlier
  video's, or the 30-second refresh) shows a video before its own poll
  sees it done, that video has both a reel and a pending tile for up to
  1.5 seconds.
- **The paste field stays busy until every video has settled**, which can
  take minutes for a 4-video tweet with `WORKERS=1`.

## 9. Testing

Unit tests, no network:

- X hosts are allowed, fixer links are rewritten, and look-alikes are
  rejected (`x.com.evil.org`, `notx.com`, `t.co`).
- Each new yt-dlp message maps to its code.
- `playlist_items` is the job's `item`.
- `allowed_extractors` is set for X links only, and a real `YoutubeDL`
  with those options loads the twitter extractor and not the generic one.
- `count_videos` with a playlist, a single video, an error and more than 8
  entries.
- The trailing `t.co` link is dropped from captions, and only the last one.
- `submit` makes n jobs with items 1 to n. A repeat paste doesn't count
  again. The queue must have room for all of them. No counter, a timeout or
  an error gives one job. Non-X links are never counted.
- `POST /jobs` answers `ids`.

By hand, with `scripts/dev_board.py`:
- an x.com link containing `multi` gives 3 pending tiles that fill one by
  one;
- `multi` plus `partial` fails only the second video and shows the toast;
- `novideo` shows the no-video hint;
- a fxtwitter link goes through;
- the board line says "X".

With ffmpeg, `pytest -m network` with an X link in `REELS_TEST_URL`. The
test follows every id and checks that each job got a different video.
