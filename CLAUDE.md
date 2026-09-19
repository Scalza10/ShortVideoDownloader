# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A FastAPI service that turns Instagram Reel / TikTok / X links into WhatsApp-friendly MP4s (yt-dlp → ffprobe → ffmpeg), plus a passcode-protected phone web page ("the pile", a shared board of reels) served by the same app. Small-group use, one Docker container behind Caddy on a single VM. README.md covers user-facing behaviour, the API and configuration.

## Commands

The dev machine is Windows; use the venv's interpreter. ffmpeg is **not** installed locally.

```powershell
.venv\Scripts\python.exe -m pytest                                  # all unit tests (~300, a few seconds)
.venv\Scripts\python.exe -m pytest tests/test_jobs.py::test_timeout # one test
.venv\Scripts\python.exe -m pytest -m network                       # real download; needs REELS_TEST_URL and ffmpeg
.venv\Scripts\python.exe -m uvicorn reels_api.main:create_app --factory --reload   # reads .env
.\scripts\deploy.ps1                                                # deploy last commit on master to production
```

- `pyproject.toml` sets `addopts = -m 'not network'`, so the network test is skipped unless `-m network` is passed.
- No linter or formatter is configured.
- To try the page by hand, `scripts/dev_board.py` runs the real app with passcode `dev`, 12 seeded reels and a fake pipeline, and prints an invite link and a share link (open those in a private window) and an old cookie value (paste it over `reels_session` in DevTools to see the cookie pop-up). It needs ffmpeg to make the seed clips, so run it in Docker (command in its docstring and in README). Pasted URLs containing `private`, `login`, `blocked`, `novideo` or `slow` fail with the matching error; an x.com URL containing `multi` counts as a post with 3 videos, and adding `partial` fails only the second. A URL containing `nsfw` gives an NSFW reel, and seed 3 is one.
- The network test also takes X links, including a multi-video tweet (it follows every id). The image has no pytest: run it in a throwaway `reels-dev` container that `pip install -r requirements-dev.txt` first, with the repo mounted.
- Production health: `https://<site>/health`, where `<site>` is the `$Site` default in `scripts/deploy.ps1`.

## Architecture

**Job flow.** `POST /jobs` → `JobManager.submit` (`jobs.py`): `extract_url` pulls the first URL out of share text, `normalize_url` turns every X or fixer link (fxtwitter.com etc.) into `https://x.com/<path>` with no query (yt-dlp needs the lowercase host; one spelling per tweet makes dedupe work), `detect_source` allow-lists hosts, and the non-failed jobs with the *exact same URL string* are returned instead of queuing duplicates. For X links only, `Pipeline.count_videos` (yt-dlp with `process=False`, in a thread, 20 s cap, any error counts 1) says how many videos the tweet has, and `submit` makes one job per video, all with the same URL and `Job.item` 1..n (yt-dlp's `playlist_items`). The jobs go onto a bounded `asyncio.Queue`, which must have room for all of them. `submit` returns a list; `POST /jobs` answers the first job's `id`/`status` plus `ids` (X links spec, `docs/superpowers/specs/2026-09-18-x-links-design.md`). `WORKERS` worker tasks run `Pipeline.run` (`pipeline.py`) in a thread via `asyncio.to_thread` under `asyncio.wait_for`. The pipeline calls `status` callbacks, downloads into `TEMP_DIR/<job id>/`, probes, remuxes (or transcodes if not H.264/AAC) to `STORAGE_DIR/<id>.mp4`, then makes `<id>.jpg`. Thumbnail failure never fails the job.

**State is in memory only.** `JobStore` is a dict. Files on disk are tied to jobs purely by filename stem (`<id>.mp4`, `<id>.jpg`; `STORED_SUFFIXES` in `jobs.py`). Three things delete files: the sweeper (hourly, `SWEEP_INTERVAL_SECONDS`, drops jobs past `RETENTION_HOURS`, default 12), `enforce_video_cap` (after each finished job, keeps newest `MAX_VIDEOS`), and `_remove_untracked_files` (on startup and each hourly sweep, immediately deletes any orphan, meaning a file or temp dir whose stem is not a known job; there is deliberately no age grace period, since `/files/` can't serve an orphan anyway). So **every restart or deploy wipes the whole pile**, including files in the persisted `data/` volume.

**Errors.** Everything reportable is `JobError(ErrorCode)` (`models.py`, messages in `ERROR_MESSAGES`). Raised inside the pipeline it marks the job failed; raised synchronously in a request it goes through the handler in `main.py`, which maps `unsupported_url`→400, `too_many_jobs`→429, anything else→500. All error bodies are `{"error": code, "message": text}`, including HTTP exceptions.

**App factory.** `create_app(settings=None, pipeline=None)` in `main.py`. Tests and `dev_board.py` inject their own `Settings` and a fake pipeline (anything with `run(job, set_status) -> JobResult`, and optionally `count_videos(url) -> int`; without it every X link is one video). `Pipeline`'s stages (`downloader`, `prober`, `converter`, `thumbnailer`, `counter`) are also injectable dataclass fields.

**Auth** (`auth.py`). `require_access` accepts either `X-API-Key` or the `reels_session` cookie (`has_access`). The cookie value is a shared HMAC of `API_KEY` + `WEB_PASSCODE`, so there are no per-user sessions and changing either secret logs everyone out. It has two values that both log in (`session_state`): *agreed*, which every login sets, and *unasked*, the value from before the login page asked. An unasked cookie gets a pop-up on the board it can't dismiss (`cookie.js`); "allow cookie" calls `POST /web/cookie`, which re-sets the agreed value, and "no thanks, log me out" logs out and saves the "no" (pop-up spec, `docs/superpowers/specs/2026-09-17-cookie-ask-on-board-design.md`). Two ways to get the cookie, both only after the person agrees on the login page (cookie spec, `docs/superpowers/specs/2026-09-17-cookie-consent-design.md`): the passcode form (`POST /web/login`, button "allow cookie & log in") and the invite link, where `GET /join/<INVITE_TOKEN>` only serves the login page in invite mode and `POST /join/<INVITE_TOKEN>` sets the cookie. Both share one per-IP attempt limiter. **A GET must never set the cookie** (WhatsApp's preview fetcher GETs invite links). "no thanks" is kept in `localStorage["reels-cookie-choice"]` and never reaches the server; a "yes" is the cookie itself. `POST /web/logout` deletes the cookie on that phone only (the value is shared, so nobody else is logged out). `web.install(app)` (login, logout, `/web/cookie`, `/`, `/join`, manifest, `/sw.js`, `/static`) is only called when `WEB_PASSCODE` is set; otherwise those routes 404. Every job also has a random `share_key` (in the job JSON when done): `?k=<share_key>` opens that reel's `/files/` and its view-only page, and nothing else. It must never open `/jobs` or the board.

**`GET /` decides the page** (`web.index`, pop-up spec 4): agreed cookie → the board; no `reel`+`k` → login; unknown reel → expired page; wrong key → login (deliberately the same as no key); reel not done or file gone → expired page; otherwise the view-only page. Wherever it would serve login, an unasked cookie gets the board with `data-cookie="ask"` instead, so share links behave as without a cookie. The board, view-only and expired pages are rendered by `pages.py` from `static/app.html`, `static/watch.html` and `static/expired.html`: `{{name}}` placeholders are HTML-escaped, `raw=` values are inserted as is, and the reel JSON goes through `script_json`. Open Graph tags are filled in on the server because WhatsApp's preview fetcher runs no JavaScript and has no cookie.

**Job JSON.** `job_to_dict` in `models.py` is the contract for curl clients and the page. Keep changes additive.

**Frontend** (`reels_api/static/`). Plain HTML/CSS/ES modules. No build step, no framework, no JS dependencies, no JS tests. `app.html` loads `app.js`, which wires `board.js`, `paste.js`, `player.js` and `cookie.js` together with callbacks. Those four never import each other; they share only `api.js`, `format.js`, `icons.js` and `toast.js`. One paste can bring several videos (an X post): the board keeps a list of pending tiles, and `paste.js` polls every id and runs `onDone`/`onFail` once per video, one at a time. A reel with `nsfw` (yt-dlp `age_limit` ≥ 18, i.e. X's sensitive flag) gets a blurred tile with a red NSFW label, opens in the player covered (`is-covered`: `play()` does nothing, and a `play` listener pauses anything else that starts it, until a tap or the `reveal` button), and `render_watch` leaves out its `og:image` (NSFW cover spec, `docs/superpowers/specs/2026-09-18-nsfw-cover-design.md`). `login.html`/`login.js` are a separate non-module page with two states (asking, declined) and an invite mode picked from the `/join/` path. The board's footer holds log out. `watch.html` + `watch.js` is the view-only page: it runs `player.js` with `standalone: true` (no history, no close, no swiping). **The player markup exists in both `app.html` and `watch.html`; mirror any change.** Share links are built by `reelPath(reel)`/`reelLink(reel)` in `player.js` and include `k` when the reel has a `share_key`. The page is dark only. Layout switches at 700px (full-screen swipe player below, overlay above). Comments like `(spec 7.4)` refer to `docs/superpowers/specs/2026-09-16-reels-board-ui-design.md`; `(web spec …)` refers to `…-mobile-web-page-design.md`.

**Deployment topology.** `docker-compose.yml`: `api` bound to `127.0.0.1:8000` on the host, and `caddy` on 80/443 reverse-proxying to it with `SITE_ADDRESS`. Production is an Oracle Cloud VM (DuckDNS host name), repo unpacked at `~/reels`, `.env` lives only on the VM.

## Things we learned

### Backend
- **A timed-out job's thread keeps running.** `asyncio.to_thread` can't be cancelled. `set_status` ignores updates once `finished_at` is set, and `_fail` sets `finished_at` *first*. `Pipeline.run` deletes its outputs on any exception. Preserve these orderings when touching job completion.
- **yt-dlp error mapping is ordered.** `_ERROR_PATTERNS` in `downloader.py` checks login before "not available", because Instagram's message ("…not available, rate-limit reached or login required") contains both. Unmatched errors become `platform_blocked`.
- **Instagram's yt-dlp `title` is "Video by \<user\>".** The real caption is `description`, with fallback to title. X's `description` is the tweet text ending in the media's own `t.co` link; the downloader drops only that last one. yt-dlp's X title keeps the link of a tweet that is only its video, so the title drops every `t.co` link.
- **X's `/video/N` counts photos too**, and can't reach a quoted tweet's or a card's video. So a tweet's videos are addressed with `playlist_items` on the tweet URL, whose entries are exactly its videos (then the quoted tweet's, then the card's).
- **NSFW tweets mostly need x.com cookies to download at all.** Logged out, X answers `NsfwLoggedOut`, which yt-dlp raises as a login error (`login_required`). With cookies they download and carry `age_limit` 18, which becomes `nsfw`. **A quoted tweet's video carries the outer tweet's flag**: yt-dlp reads `possibly_sensitive` only from the outer status and copies it into every entry, so an unflagged tweet quoting an NSFW video arrives uncovered. Fixing that needs the quoted status's own flag, which yt-dlp doesn't expose.
- **X links run with `allowed_extractors` = the twitter ones** (`X_EXTRACTORS`). A tweet without a video but with a link is otherwise followed to that site (YouTube, anything), around the allow-list. The guard's "No suitable extractor" error maps to `no_video`. Instagram and TikTok keep the default extractors.
- **Most download breakages are fixed by bumping `yt-dlp`** in `requirements.txt` (it's pinned) and redeploying.
- **`Settings` reads `.env` from the working directory.** Tests build settings with `tests/conftest.py::make_settings(tmp_path, **overrides)`, which passes `_env_file=None` so the local `.env` can't leak in. Use it.
- **Anything seeding jobs must add them before the app starts**, or startup cleanup deletes their files (see `dev_board.py`).
- **Adding a new stored file type** means adding its suffix to `STORED_SUFFIXES` and deleting it in `JobManager._discard`.
- **`secrets.compare_digest` rejects non-ASCII `str`.** The passcode check compares bytes.
- **`slugify` exists twice**, in `routes.py` (download filename) and `static/format.js` (iOS share-sheet filename). Keep them identical.

### Web page
- **Author `display` rules beat the `hidden` attribute.** `style.css` has `[hidden] { display: none !important; }`, and JS toggles visibility with `el.hidden`.
- **`.js` must be served as `text/javascript`, `.woff2` as `font/woff2`.** On Windows, `mimetypes` can say `application/javascript` from the registry, and Python 3.12 knows no type for `.woff2`. `NoCacheStaticFiles` forces both (`FORCED_CONTENT_TYPES`), and `test_web.py` asserts it for every module in `APP_MODULES` and every font in `FONT_FILES`. **Add new modules to that list.**
- **No requests to other sites.** The font is self-hosted in `static/fonts/` because a Google Fonts request sends every visitor's IP address to Google (GDPR). `test_no_page_loads_google_fonts` guards the font hosts; keep scripts, styles and fonts in `static/`.
- **Caching:** static files `no-cache` (ETag revalidation, so deploys show up without cache-busting), `/` is `no-store` (login vs app page), thumbnails `private, max-age=21600`.
- **iOS only opens the share sheet inside the tap itself**, with no `await` before `navigator.share`. So on iOS the player prefetches the MP4 into memory while the reel plays, and Save shares the file. A plain web download on iPhone lands in Files, not Photos. Other platforms download via `Content-Disposition: attachment`.
- **Autoplay with sound needs a user gesture.** A `?reel=` link opens muted, and `play()` falls back to muted on `NotAllowedError`.
- **Any 401 from `api.js` reloads the page**, which shows the login screen. `login.js` reloads on success, keeping the query string, so a shared `/?reel=<id>` link survives logging in.
- **`sw.js` is served from `/`** so its scope covers the page. It does nothing (no caching, no fetch handler) and exists only so older Android Chrome treats the page as installable. The manifest's `share_target` (Android only) sends `?url=&text=&title=` to `/`, which `app.js` feeds into the paste flow.
- **HTTPS matters.** The cookie is `Secure`, so FastAPI `TestClient` must use `base_url="https://testserver"` (`https_client` in `test_web.py`). For local dev use Chrome or Firefox on `http://localhost`, because Safari won't store the cookie over http. Share and install need HTTPS in production.
- **The design handoff** (`design_handoff_reels_dump/README.md`) holds the visual tokens. Where it and the board UI spec disagree, the spec wins (spec §9 lists the differences).
- **`app.html` goes through `pages.fill`** (for `data-cookie`), so any other `{{name}}` in it raises `KeyError`.
- **`reels-cookie-choice` is spelled out twice**, in `login.js` (not a module, so it can't import) and `cookie.js`. Keep the key and the `declined` value identical.

### Deploy / ops
- **`deploy.ps1` ships the last *commit* on `master` via `git archive`**, not the working tree, so commit first. It sets TLS 1.2 explicitly because Windows PowerShell 5.1 doesn't offer it by default.
- **`scripts/deploy.ps1` is gitignored and must stay out of the repo.** Its defaults are the production VM's IP and host name, so it exists only on the PC that deploys. Keep those details out of every committed file too (docs use `<site>` or `<name>.duckdns.org`).
- **Caddy deliberately has no `env_file`**, so it never sees `API_KEY` or `WEB_PASSCODE`; only `SITE_ADDRESS` is passed.
- **uvicorn runs with `--proxy-headers --forwarded-allow-ips=*`** so `request.client.host` is the real client behind Caddy. The per-IP login limiter depends on it.
- **1 GiB VMs need `WORKERS=1` and swap**, or the container restarts and jobs time out (`docs/DEPLOY-AZURE.md` troubleshooting table).
- **Seed clips use `testsrc2` + `hue`, not `drawtext`**, because the slim Docker image has no fonts.

## Process

Features were built spec-first: a design in `docs/superpowers/specs/`, then a task-by-task plan in `docs/superpowers/plans/`, then small commits prefixed `feat:`, `fix:` or `docs:`. `origin` is `github.com/Scalza10/ShortVideDownloader`; `master` is the only branch.
