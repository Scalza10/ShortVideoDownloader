# Mobile Web Page — Design

Date: 2026-09-16
Status: approved design, pre-implementation
Builds on: `2026-09-16-reels-download-api-design.md` (the "API spec")

## 1. Purpose

Friends use the service from their phones without curl, API keys or job
ids. They open a web page, enter a shared passcode once, paste a TikTok or
Instagram link, watch the result, and share the MP4 straight into a
WhatsApp chat. A shared "Recent" feed shows everything anyone downloaded
in the last few hours.

The page is served by the existing FastAPI app. The HTTP API keeps working
unchanged for curl and for the WhatsApp bot, which is a later project.

Out of scope: per-user accounts, deleting feed items, keeping the feed
across restarts, languages other than English, an iOS Shortcut, the
WhatsApp bot, translation.

## 2. Constraints

- **HTTPS is required.** Sharing files through the phone's share sheet
  (`navigator.share` with files), installing the page to the home screen
  and service workers only work in a secure context. Production runs
  behind Caddy with a Let's Encrypt certificate. `http://localhost` counts
  as secure in Chrome and Firefox, which is enough for development. Safari
  does not store a `Secure` cookie over plain http, so local development
  uses Chrome or Firefox.
- **iOS Safari needs a fresh tap for the share sheet.** `navigator.share`
  must be called directly in a tap handler, with no slow `await` before
  it. The video file is therefore fetched into memory before the Share
  button is enabled. Accepted trade-off: opening a player downloads the
  file twice, once streamed by the `<video>` element and once into memory
  for sharing. Clips are a few MB, so a one-tap share is worth it.
- **The Web Share Target API is Android-only.** On Android, an installed
  page appears in TikTok's share menu. iPhone users paste the link.
- **Job state is in memory.** The feed empties on container restart and
  entries disappear after `RETENTION_HOURS` (default 6).
- **Same origin.** The page, the API and the files share one host, so
  there is no CORS and the session cookie is first-party.

## 3. Configuration

New environment variables:

| variable       | default | read by  | meaning                                                  |
|----------------|---------|----------|----------------------------------------------------------|
| `WEB_PASSCODE` | unset   | app      | passcode for the web page; unset disables the web page   |
| `SITE_ADDRESS` | unset   | Caddy    | public host name, e.g. `reels.westeurope.cloudapp.azure.com` |

`Settings` gains `web_passcode: str | None = None`. `SITE_ADDRESS` is only
used by docker compose and Caddy, not by the app.

When `WEB_PASSCODE` is unset, `create_app` does not register the web
router or static files: `/`, `/web/login`, `/manifest.webmanifest`,
`/sw.js` and `/static/*` all return 404. Everything else behaves as it
does today.

## 4. Access control

### 4.1 Session cookie

- Name `reels_session`.
- Value: lowercase hex of `HMAC-SHA256(key=API_KEY, msg="reels-web-session:" + WEB_PASSCODE)`.
  Every phone gets the same value. Changing either `API_KEY` or
  `WEB_PASSCODE` invalidates all existing cookies.
- Attributes: `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`,
  `Max-Age=31536000` (one year).
- Compared with `secrets.compare_digest`. No server-side session storage.

### 4.2 `require_access` dependency

`auth.require_api_key` is replaced by `auth.require_access`, used by every
protected route. A request is allowed when either:

1. the `X-API-Key` header matches `API_KEY`, or
2. `WEB_PASSCODE` is set and the `reels_session` cookie equals the
   expected value.

Otherwise 401 with `{"error": "unauthorized", "message": "Missing or invalid API key."}`,
the same body as today.

CSRF: `SameSite=Lax` keeps the cookie off cross-site POSTs, and
`POST /jobs` takes a JSON body, which a cross-site form cannot send
without a CORS preflight. No extra token.

### 4.3 `POST /web/login`

Request body: `{"passcode": "..."}`.

- 204 with `Set-Cookie` when the passcode matches (compared with
  `secrets.compare_digest`).
- 401 `{"error": "wrong_passcode", "message": "That passcode is not right."}`
  when it does not.
- 429 `{"error": "too_many_attempts", "message": "Too many wrong tries. Wait 15 minutes and try again."}`
  when the client IP has 10 or more failed attempts in the last 15
  minutes. This check runs before the passcode is compared.
- 422 for a malformed body (FastAPI default).

The attempt limiter is an in-memory `dict[ip, list[timestamp]]`. On each
call it drops timestamps older than 15 minutes from **every** entry and
removes entries that become empty, so a scanner hitting from many
addresses cannot grow the dict without bound. A successful login clears
that IP's entry. The client IP is `request.client.host`, which is the
real phone IP because uvicorn runs with `--proxy-headers` behind Caddy
(section 8), and Caddy replaces any client-supplied `X-Forwarded-For`.

Accepted limitation: friends behind one home router or one mobile
carrier's NAT share a counter. Ten failures in 15 minutes is enough
slack for a small group.

There is no logout endpoint. Clearing site data on the phone logs out.
*(Superseded: `POST /web/logout` and a log out link on the board delete the
cookie, see `2026-09-17-cookie-consent-design.md` 5.3 and 6.)*

## 5. API changes

### 5.1 Share text in `POST /jobs`

New `urls.extract_url(text: str) -> str`: returns the first match of
`https?://\S+` with trailing `.,;:!?)]}>"'` characters stripped. If
there is no match it returns `text.strip()`, which then fails validation
as `unsupported_url` as before.

`JobManager.submit` calls `extract_url` before `detect_source` and
stores the extracted URL on the job. So
`{"url": "Check this out! https://vm.tiktok.com/ZMabc123/ #fyp"}` is
accepted. A bare URL behaves exactly as today.

### 5.2 `GET /jobs`

Protected by `require_access`. Response 200:

```json
{ "jobs": [ { ...same shape as GET /jobs/{id} when done... } ] }
```

- Only jobs with status `done` and a result.
- Sorted by `finished_at`, newest first.
- At most 50 entries.

`JobStore` gains `list_recent(limit: int = 50) -> list[Job]` implementing
the filter, sort and limit.

### 5.3 Thumbnails

- `media.build_thumbnail_command(src, dst, at_seconds)` builds
  `ffmpeg -y -hide_banner -loglevel error -ss <at> -i <src> -frames:v 1 -vf scale=360:-2 -q:v 4 <dst>`.
- `media.make_thumbnail(src, dst, duration_seconds, timeout)` picks
  `at = min(1.0, duration / 2)` (or `0` when the duration is unknown) and
  runs the command. It raises `JobError(processing_failed)` on a non-zero
  exit or timeout.
- `Pipeline` gets a new injectable field
  `thumbnailer: Callable[[Path, Path, float | None, float], None]`,
  default `media.make_thumbnail`. After the convert step it writes
  `<STORAGE_DIR>/<id>.jpg` with timeout `min(30, remaining)`.
- **A thumbnail failure never fails the job.** The exception is logged
  with the job id, the partial `.jpg` is deleted, and `thumbnail_path`
  stays `None`.
- If the job fails for any other reason, the `.jpg` is deleted along with
  the `.mp4`.
- `JobResult` gains `thumbnail_path: Path | None = None`.
- `job_to_dict` adds `"thumbnail_url"` for done jobs: `/files/<id>.jpg`,
  made absolute with `PUBLIC_BASE_URL` in the same way as `file_url`, or
  `null` when there is no thumbnail.
- New route `GET /files/{id}.jpg`, protected: `image/jpeg`, no
  `Content-Disposition`, `Cache-Control: private, max-age=21600`. 404 if
  the job is unknown, not done, has no thumbnail, or the file is missing.
- The sweeper deletes `thumbnail_path` along with `file_path`.

## 6. Web routes and static files

New module `reels_api/web.py`, after `routes.py` in the dependency order.
It holds the login route, the attempt limiter and page serving. The cookie
helpers live in `auth.py`.

| route                        | auth   | returns                                                   |
|------------------------------|--------|-----------------------------------------------------------|
| `GET /`                      | none   | `app.html` if the cookie is valid, else `login.html`      |
| `POST /web/login`            | none   | section 4.3                                               |
| `GET /manifest.webmanifest`  | none   | `application/manifest+json`                               |
| `GET /sw.js`                 | none   | `text/javascript`, served at the root so its scope is `/` |
| `GET /static/*`              | none   | CSS, JS, icons (Starlette `StaticFiles`)                  |

Query strings on `GET /` are ignored by the server and read by the page.
The static files hold no secrets; everything that returns data requires
access.

Caching: `GET /` sends `Cache-Control: no-store`, because which page it
returns depends on the cookie and an installed app must not show a stale
login or app page. `/static/*`, `/sw.js` and `/manifest.webmanifest`
send `Cache-Control: no-cache`, so browsers revalidate with the ETag that
Starlette already emits and pick up new JS right after a deploy.

Files in `reels_api/static/`:

```
login.html            passcode form
app.html              main screen shell
app.js                all page behaviour
login.js              login form behaviour
style.css             shared styles
manifest.webmanifest  name, icons, display: standalone, share_target
sw.js                 minimal service worker, no caching
icon-192.png
icon-512.png          plain generated icons
```

Manifest `share_target`:

```json
{ "action": "/", "method": "GET",
  "params": { "title": "title", "text": "text", "url": "url" } }
```

No new Python dependencies: login takes JSON rather than a form post, so
`python-multipart` is not needed.

## 7. Page behaviour

Plain HTML, CSS and JavaScript with no build step and no framework.
Mobile-first layout that follows the phone's light or dark setting. All
text in English.

### 7.1 Login screen

One password input and a **Continue** button. The page `fetch`es
`POST /web/login`. On 204 it calls `location.reload()`, which keeps the
query string, so a shared link still starts after logging in. On 401 or
429 it shows the returned `message` under the input.

### 7.2 Main screen: submitting a link

1. On load, if the query string has `url`, `text` or `title`, the page
   joins them with spaces, puts the result in the link box, submits it
   automatically, and removes the query string with
   `history.replaceState`.
2. The link box has a **Paste** button, shown only when
   `navigator.clipboard.readText` exists, and a **Get video** button.
   The button is disabled while a request is in flight.
3. **Get video** sends `POST /jobs` with the box contents. On 400 or 429
   it shows the returned `message`.
4. Otherwise it polls `GET /jobs/{id}` every 1.5 seconds and shows
   "Waiting in line…", "Downloading…" or "Processing…" for
   `queued`, `downloading` or `processing`. A network error keeps
   polling. A 401 anywhere reloads the page, which shows the login screen.
5. On `failed`, it shows the job's `message` and a **Try again** button
   that resubmits the same text.
6. On `done`, it shows the video player (section 7.4) at the top, and
   refreshes the feed.

### 7.3 Recent feed

- Loaded from `GET /jobs` when the page opens, when the user's own job
  finishes, and when the tab becomes visible again (`visibilitychange`).
- Each card shows the thumbnail (or a plain placeholder when
  `thumbnail_url` is null), the title, "TikTok" or "Instagram", the
  duration as `m:ss`, and the time left before the file is deleted,
  computed from `expires_at`, e.g. "gone in 4h".
- Tapping a card turns it into the video player (section 7.4). Only one
  player is open at a time; opening another closes the previous one and
  releases its memory.
- An empty feed shows "Nothing here yet."

### 7.4 Video player with Share and Download

- `<video controls playsinline preload="metadata">` with `src` set to
  `file_url` and `poster` set to `thumbnail_url`.
- **Download** is a normal link to `file_url`. The server already sends
  `Content-Disposition: attachment`.
- **Share to WhatsApp**:
  - When the player opens, the page `fetch`es `file_url` into a `Blob`
    and builds a `File` named `<title-slug>.mp4` with type `video/mp4`.
    The slug follows the same rules as the server's `slugify`.
  - Whether the button is shown at all is decided before the fetch, with
    a zero-byte probe: `navigator.canShare({files: [new File([""], "probe.mp4", {type: "video/mp4"})]})`.
    While the fetch runs the button is disabled with the label
    "Preparing…". When the fetch completes, `canShare` is checked again
    with the real file; if that fails the button is hidden.
  - Tapping it calls `navigator.share({files: [file]})` with no `await`
    before the call. An `AbortError` (the user closed the sheet) is
    ignored; other errors show "Sharing failed. Use Download instead."
- When `whatsapp_ok` is false, a note says "Over 16 MB. Older WhatsApp
  versions may refuse it."

### 7.5 Service worker

`app.html` registers `/sw.js`. The worker has install and activate
handlers only. It has no `fetch` handler: current Chrome does not need
one for installability and flags no-op fetch handlers as wasteful. The
registration exists for older Android Chrome versions and costs nothing.

## 8. Deployment

### 8.1 Docker Compose

- New service `caddy` from image `caddy:2`: ports `80:80` and `443:443`,
  `./Caddyfile:/etc/caddy/Caddyfile:ro`, named volumes `caddy_data` and
  `caddy_config`, `environment: SITE_ADDRESS: ${SITE_ADDRESS}` (compose
  reads `.env` for the substitution; Caddy must not receive `API_KEY` or
  `WEB_PASSCODE`, so no `env_file`), `depends_on: api`,
  `restart: unless-stopped`.
- `Caddyfile`:

  ```
  {$SITE_ADDRESS} {
      reverse_proxy api:8000
  }
  ```

- The `api` service port mapping becomes `127.0.0.1:8000:8000`, so the
  app is reachable from the VM itself but not from the internet.
- The Dockerfile `CMD` adds `--proxy-headers --forwarded-allow-ips=*`.
  That is safe because only Caddy can reach port 8000 from outside the
  VM.
- `.env.example` gains `WEB_PASSCODE=` and
  `SITE_ADDRESS=reels.example.cloudapp.azure.com`, and its `WORKERS`
  comment notes to use `1` on a 1 GiB VM.
- The `caddy:2`, `python:3.12-slim` and Debian `ffmpeg` images and
  packages are all available for both x86-64 and Arm64, so the same
  compose file works on any of the free VM sizes.

### 8.2 Azure free account (README section "Deploy on Azure")

The target is the Azure free account's 12-month allowance: 750 hours per
month each of B1s, B2pts v2 (Arm) and B2ats v2 (AMD) Linux VMs, and two
P6 (64 GiB) Premium SSD managed disks. One VM running all month fits in
750 hours.

Chosen size: **B2ats v2** (2 vCPU, 1 GiB RAM, x86-64). It has more CPU
than B1s for ffmpeg, and x86 avoids any Arm image surprises. Every free
size has 1 GiB of RAM, so the deployment runs with `WORKERS=1` and a 2 GiB
swap file.

Steps:

1. Create the VM from the portal's **Free services** page, which selects
   free-eligible options. Image Ubuntu Server LTS, size `Standard_B2ats_v2`,
   OS disk **Premium SSD, 64 GiB** (P6). A different disk type or size is
   billed.
2. On the VM's public IP, set a DNS name label. The host name becomes
   `<label>.<region>.cloudapp.azure.com`.
3. In the network security group, allow inbound TCP 80 and 443 from any
   source, and TCP 22 only from your own IP.
4. In Cost Management, create a budget of 1 unit of currency per month
   with an email alert, so any charge is noticed immediately.
5. SSH in and add swap:
   `sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile`,
   plus the matching `/etc/fstab` line so it survives reboots.
6. Install Docker Engine and the compose plugin, clone the repo, copy
   `.env.example` to `.env`, and set `API_KEY`, `WEB_PASSCODE`,
   `SITE_ADDRESS` and `WORKERS=1`.
7. `docker compose up -d --build`. Caddy obtains the certificate on first
   start. Open `https://<SITE_ADDRESS>/` on a phone.

Known cost caveats, stated in the README:

- The free allowance lasts 12 months from sign-up. After that the VM,
  disk and IP are billed at normal rates unless deleted.
- The public IPv4 address may not be covered: Azure now issues Standard
  SKU (static) addresses, and the free allowance has historically covered
  dynamic ones. Expect a few dollars per month for the address; the budget
  alert in step 4 shows the real figure.
- Outbound data beyond the monthly free bandwidth allowance is billed.
  Short clips of a few MB each stay far below it for a group of friends.

The README also covers local development without Caddy: set
`WEB_PASSCODE` in `.env`, run uvicorn, open `http://localhost:8000/`.

## 9. Code layout changes

```
reels_api/
  settings.py   + web_passcode
  auth.py       require_api_key -> require_access, session_cookie_value()
  models.py     + JobResult.thumbnail_path, thumbnail_url in job_to_dict
  urls.py       + extract_url
  media.py      + build_thumbnail_command, make_thumbnail
  pipeline.py   + thumbnailer stage (non-fatal)
  jobs.py       submit uses extract_url; JobStore.list_recent; sweeper deletes .jpg
  routes.py     + GET /jobs, GET /files/{id}.jpg; uses require_access
  web.py        new: GET /, POST /web/login, attempt limiter, manifest, sw.js, static mount
  main.py       includes web router and static files only when web_passcode is set
  static/       new: see section 6
Caddyfile       new
Dockerfile      CMD adds proxy headers
docker-compose.yml, .env.example, README.md   updated
tests/
  test_urls.py      + extract_url
  test_media.py     + thumbnail command
  test_pipeline.py  + thumbnail success, thumbnail failure is non-fatal, .jpg removed on job failure
  test_jobs.py      + list_recent, sweeper removes .jpg, submit extracts URL
  test_routes.py    + GET /jobs, GET /files/{id}.jpg, cookie access
  test_web.py       new: login, attempt limit, disabled mode, GET / page choice
```

The Dockerfile already copies the whole `reels_api` directory, so
`static/` ships without further changes.

## 10. Testing

Automated, with no network and no ffmpeg, using the existing fakes.
Tests that rely on the cookie round-trip create the client as
`TestClient(app, base_url="https://testserver")`: the cookie is `Secure`
and httpx's jar refuses to send Secure cookies over the default
`http://testserver`.

- `extract_url`: bare URL; URL inside TikTok and Instagram share text;
  trailing punctuation; no URL at all.
- Access: header works; valid cookie works; wrong cookie is 401; a cookie
  made with an old passcode is 401; a cookie is rejected when
  `WEB_PASSCODE` is unset.
- Login: correct passcode gives 204 and the cookie attributes from 4.1;
  wrong passcode gives 401; the 11th attempt within 15 minutes gives 429
  even with the right passcode; success clears the counter; entries older
  than 15 minutes no longer count.
- Disabled mode: with `WEB_PASSCODE` unset, `/`, `/web/login`,
  `/manifest.webmanifest`, `/sw.js` and `/static/app.js` return 404.
- `GET /` returns the login page without a cookie and the app page with
  a valid one.
- `GET /jobs`: excludes queued, running and failed jobs; newest first;
  capped at 50; requires access.
- Thumbnails: command construction and seek time; pipeline success sets
  `thumbnail_path`; thumbnailer exception still produces a done job with
  `thumbnail_url: null`; `.jpg` route serves `image/jpeg` and 404s when
  absent; sweeper deletes the `.jpg`.

Manual, in a desktop browser at phone width against a local run: login
with a wrong then the right passcode, paste a real TikTok link, watch
status changes, play the video, Download, check the feed, a failed link,
and a `/?text=...` share-target URL.

On real devices after deploying (done by the owner): Share to WhatsApp
on an iPhone and on an Android phone, and sharing from the TikTok app to
the installed page on Android.
