# Reels Download API — Design

Date: 2026-09-16
Status: approved design, pre-implementation

## 1. Purpose

A small HTTP service that takes a share link for an Instagram Reel or a
TikTok video and produces an MP4 file that plays in WhatsApp, so the video
can be forwarded to people who do not have Instagram or TikTok.

Version 1 is the API only. A WhatsApp bot (official Cloud API or an
unofficial library) is a later project that will call this API. The API is
designed so either route can plug in without changes here.

Out of scope for version 1: translation, subtitles, dubbing, user accounts,
a web UI, any platform other than Instagram and TikTok.

## 2. Constraints and known risks

- **Platform terms.** Instagram and TikTok forbid scraping. This service is
  for personal and small-group use. Expect periodic breakage; the fix is
  usually bumping yt-dlp.
- **Instagram needs cookies.** Anonymous Instagram downloads are
  rate-limited and often refused. The service accepts an optional Netscape
  cookies file exported from a throwaway account.
- **WhatsApp limits.** WhatsApp plays H.264 video with AAC audio in an MP4
  container and caps videos at 16 MB. Files above that still download but
  are flagged.
- **Long requests.** A download plus remux takes 5 to 60 seconds. Requests
  must not block for that long, which is why jobs are asynchronous.

## 3. Stack and deployment

- Python 3.12, FastAPI, uvicorn.
- yt-dlp used as a library (not a subprocess) for downloading.
- ffmpeg and ffprobe invoked as subprocesses for probing and remuxing.
- Runs as one Docker container on a VPS or cloud VM. A docker compose file
  is provided. yt-dlp is pinned in requirements and expected to be bumped
  often.
- No database, no Redis. Job state lives in process memory; files live on
  local disk. Restarting the container loses in-flight jobs, which is
  acceptable for version 1.

## 4. HTTP API

All endpoints except `/health` require the header `X-API-Key` matching the
configured key. A missing or wrong key returns 401.

### POST /jobs

Request body:

```json
{ "url": "https://vm.tiktok.com/ZMabc123/" }
```

Response 202:

```json
{ "id": "k7f3q9x2", "status": "queued" }
```

Errors:

- 400 `unsupported_url` — host is not Instagram or TikTok, or the URL does
  not parse.
- 429 `too_many_jobs` — the queue is at its configured limit.

Job ids are short random strings (8 to 12 URL-safe characters). Posting the
same URL twice creates two jobs; there is no deduplication in version 1.

### GET /jobs/{id}

Response 200 while running (one of):

```json
{ "id": "k7f3q9x2", "status": "queued" }
{ "id": "k7f3q9x2", "status": "downloading" }
{ "id": "k7f3q9x2", "status": "processing" }
```

Response 200 when done:

```json
{
  "id": "k7f3q9x2",
  "status": "done",
  "file_url": "/files/k7f3q9x2.mp4",
  "title": "...",
  "source": "tiktok",
  "duration_seconds": 23.4,
  "size_bytes": 4812390,
  "width": 1080,
  "height": 1920,
  "whatsapp_ok": true,
  "expires_at": "2026-09-16T22:15:00Z"
}
```

`whatsapp_ok` is false when `size_bytes` exceeds 16 MB (16 * 1024 * 1024).

Response 200 when failed:

```json
{ "id": "k7f3q9x2", "status": "failed", "error": "private_or_removed",
  "message": "This post is private or no longer exists." }
```

Error codes, each with a human-readable message the bot can relay:

| code                  | meaning                                               |
|-----------------------|-------------------------------------------------------|
| `unsupported_url`     | not an Instagram or TikTok video link                 |
| `private_or_removed`  | platform says the post does not exist or is private   |
| `login_required`      | Instagram refused without cookies, or cookies expired |
| `platform_blocked`    | rate limit, captcha, or extractor failure             |
| `processing_failed`   | ffmpeg failed or an unexpected exception occurred     |
| `timeout`             | job exceeded the configured time limit                |

404 if the id is unknown or the job has expired.

### GET /files/{id}.mp4

Streams the file with `Content-Type: video/mp4` and
`Content-Disposition: attachment; filename="<title-slug>.mp4"`. Supports
HTTP range requests so players can seek. 404 if unknown, not yet done, or
expired.

### GET /health

Returns 200 with `{ "status": "ok", "ytdlp_version": "...", "ffmpeg": true }`.
No API key. Used by the docker compose healthcheck.

## 5. Pipeline

Each job passes through these stages in a worker task:

1. **Validate.** Parse the URL at POST time. Accept hosts `instagram.com`,
   `www.instagram.com`, `tiktok.com`, `www.tiktok.com`, `vm.tiktok.com`,
   `vt.tiktok.com`, and `m.tiktok.com`. Only `http` and `https` schemes.
   Anything else fails immediately with `unsupported_url`. Short TikTok
   links are left to yt-dlp, which follows redirects itself.
2. **Download.** Call yt-dlp with format selection
   `bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]/b`, a per-job temp
   directory, quiet logging, and the cookies file if configured. Capture
   title, duration, width, height, and the extractor name. Map yt-dlp
   exceptions to the error codes above by matching known message
   fragments; anything unmatched becomes `platform_blocked`.
3. **Probe.** Run `ffprobe` on the downloaded file to read video and audio
   codec names.
4. **Remux or transcode.** If video is `h264` and audio is `aac`, run
   ffmpeg with `-c copy -movflags +faststart`. Otherwise transcode video to
   `libx264 -preset veryfast -crf 23 -pix_fmt yuv420p` and audio to
   `aac -b:a 128k`, with `+faststart`. Output goes to `<STORAGE_DIR>/<id>.mp4`.
5. **Finalize.** Record size, mark the job done, set `expires_at` to now
   plus the retention window, and delete the temp directory.

The whole pipeline for one job runs under a timeout; exceeding it marks
the job `timeout` and kills any running ffmpeg process.

## 6. Job store and workers

- `JobStore`: an in-memory dict of job id to `Job` dataclass, guarded by
  an asyncio lock. `Job` holds id, url, status, created and finished
  timestamps, result metadata, error code, and message.
- Worker pool: an `asyncio.Queue` fed by POST /jobs and drained by N
  worker tasks started on app startup. Each worker runs the pipeline for
  one job at a time. yt-dlp and ffmpeg are blocking, so the pipeline runs
  in a thread via `asyncio.to_thread`.
- Sweeper: a background task that every five minutes deletes files and
  job records older than the retention window, and removes stray temp
  directories.
- The queue has a maximum length; when full, POST returns 429.

## 7. Configuration

All via environment variables, read once at startup into a `Settings`
object:

| variable              | default       | meaning                             |
|-----------------------|---------------|-------------------------------------|
| `API_KEY`             | required      | value expected in `X-API-Key`       |
| `STORAGE_DIR`         | `/data/files` | where finished MP4s are written     |
| `TEMP_DIR`            | `/data/tmp`   | per-job download scratch            |
| `RETENTION_HOURS`     | `6`           | how long finished files are kept    |
| `WORKERS`             | `2`           | concurrent downloads                |
| `MAX_QUEUE`           | `20`          | queued jobs before 429              |
| `JOB_TIMEOUT_SECONDS` | `180`         | per-job limit                       |
| `COOKIES_FILE`        | unset         | Netscape cookies file for Instagram |
| `PUBLIC_BASE_URL`     | unset         | if set, `file_url` becomes absolute |
| `LOG_LEVEL`           | `info`        | uvicorn and app log level           |

## 8. Code layout

```
reels_api/
  __init__.py
  settings.py      Settings from environment
  auth.py          API key dependency
  models.py        Pydantic request/response models, Job dataclass, enums
  urls.py          URL validation and source detection
  downloader.py    yt-dlp wrapper, exception-to-error-code mapping
  media.py         ffprobe and ffmpeg command building and execution
  pipeline.py      runs the stages for one job
  jobs.py          JobStore, worker pool, sweeper
  routes.py        the four endpoints
  main.py          FastAPI app, startup/shutdown, routes wiring
tests/
  test_urls.py
  test_downloader_errors.py
  test_media.py
  test_pipeline.py     fake downloader and fake media layer
  test_routes.py       FastAPI TestClient, fake pipeline
  test_integration.py  marked `network`, real TikTok link, skipped by default
Dockerfile
docker-compose.yml
requirements.txt
requirements-dev.txt
README.md
```

Each module has one job and depends only on modules above it in the
list. `pipeline.py` takes the downloader and media functions as injected
callables so tests can substitute fakes.

## 9. Error handling summary

- Client mistakes (bad URL, bad key, full queue) fail at request time with
  4xx and a JSON body `{ "error": code, "message": text }`.
- Anything that happens inside a job is recorded on the job and surfaced
  through GET /jobs/{id}; the HTTP status there is always 200.
- Unexpected exceptions in a worker are logged with the job id and the job
  is marked `processing_failed`; the worker keeps running.
- The temp directory for a job is always removed, success or failure.

## 10. Testing

- Unit tests for URL validation, yt-dlp exception mapping, and ffmpeg
  command construction run with no network and no ffmpeg binary.
- Pipeline and route tests use fakes for the downloader and media layer
  and assert on job state transitions and JSON shapes.
- One integration test, marked `network`, runs a known public TikTok link
  end to end. It requires ffmpeg and internet and is skipped unless
  `pytest -m network` is requested.
- `docker build` plus `curl /health` is the deployment smoke test.

## 11. Future hooks (not built now)

- WhatsApp bot: a separate service that receives a message, POSTs the URL
  here, polls the job, then uploads the MP4 to WhatsApp. `PUBLIC_BASE_URL`
  exists so the bot can hand WhatsApp a direct file link if that turns out
  easier than uploading.
- Translation: would become extra stages after step 4 in the pipeline.
- Scaling: swap `JobStore` for Redis and `STORAGE_DIR` for object storage
  behind the same interfaces.
