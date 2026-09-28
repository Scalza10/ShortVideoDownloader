# Reels

Paste an Instagram Reel, TikTok or X (Twitter) link and get back a
WhatsApp-friendly MP4.
Friends share one passcode-protected board, **the pile**, where every reel
anyone pasted plays, shares and saves. The same service has a JSON API.

How it works: [yt-dlp](https://github.com/yt-dlp/yt-dlp) downloads the
video, ffprobe checks the codecs, and ffmpeg copies the streams into an MP4
(or re-encodes to H.264 + AAC when they aren't already) and grabs a
thumbnail. Finished reels stay for `RETENTION_HOURS`, at most the newest
`MAX_VIDEOS`, and survive restarts. Starred reels (favorites) stay until
someone un-stars them.

## Run locally with Docker

You need Docker Desktop (Windows, macOS) or Docker Engine with the compose
plugin (Linux). Python and ffmpeg come inside the image, so nothing else
has to be installed.

1. **Get the code** and open a terminal in it:

   ```bash
   git clone https://github.com/Scalza10/ShortVideoDownloader.git
   cd ShortVideoDownloader
   ```

2. **Create `.env`** from the example:

   ```bash
   cp .env.example .env               # PowerShell: Copy-Item .env.example .env
   ```

   Open `.env` and set:
   - `API_KEY`: any long random string, for example from
     `openssl rand -hex 24`. The JSON API needs it and it signs the login
     cookie.
   - `WEB_PASSCODE`: the passcode you type to open the board. Left empty,
     there is no board, only the JSON API.

   Leave the rest as it is. Compose sets `STORAGE_DIR` and `TEMP_DIR` to
   `/data/...` inside the container itself.

3. **Build and start the app:**

   ```bash
   docker network create web          # once; the compose file expects it
   docker compose up -d --build
   ```

   The first build takes a few minutes (Python image, ffmpeg, yt-dlp).
   The `web` network is how Caddy reaches the app on a server; locally
   nothing else uses it.

4. **Check it runs.** Open <http://localhost:8000/health>, or:

   ```bash
   curl http://localhost:8000/health    # PowerShell: curl.exe
   ```

   It answers `{"status":"ok","ytdlp_version":"...","ffmpeg":true}`.

5. **Open the board** at <http://localhost:8000/> in Chrome or Firefox,
   choose "allow cookie & log in" and enter your `WEB_PASSCODE`. Safari
   won't keep the login cookie over plain http, so use it only with HTTPS.
   Paste a TikTok or public X link to try it. Instagram usually needs
   cookies (see [Instagram and X cookies](#instagram-and-x-cookies)).

6. **Use the JSON API** with the key from `.env` (see [JSON API](#json-api)):

   ```bash
   curl -X POST http://localhost:8000/jobs \
     -H "X-API-Key: <your API_KEY>" -H "Content-Type: application/json" \
     -d '{"url":"https://vm.tiktok.com/ZMabc123/"}'
   ```

Day to day:

| To | Run |
|---|---|
| Follow the logs | `docker compose logs -f api` |
| Apply a code change or a `.env` change | `docker compose up -d --build` |
| Stop and remove the container | `docker compose down` |

`docker compose restart` does not re-read `.env`; use `up -d` instead.
Videos and the list of reels (`jobs.json`) are stored in `./data/`, so the
pile survives restarts.

To try the board with generated clips and no real downloads, see
[Trying the board without downloading anything](#trying-the-board-without-downloading-anything).

On a server, HTTPS comes from Caddy, which is not in this compose file:
it runs on its own from `proxy/` (see [Deploy](#deploy)), serves ports 80
and 443 with a Let's Encrypt certificate for every site in
`proxy/Caddyfile`, and reaches the app as `reels-api:8000` over the `web`
network. The app itself listens only on `127.0.0.1:8000`.

## The board (phone web page)

Set `WEB_PASSCODE` in `.env` and the app serves a web page at `/`. Friends
enter the passcode once and land on the pile: a grid of every reel anyone
pasted in the last `RETENTION_HOURS`, up to `MAX_VIDEOS` (default 100; past
that the oldest video is deleted to make room). No names are stored or
shown. Leave `WEB_PASSCODE` empty to disable the page; the JSON API is
unaffected either way.

- **Paste** a TikTok, Instagram or X link (or the whole share text) into
  the field. The reel shows up for everyone. Pasting a link that is already
  in the pile resolves to the existing reel.
- **X links**: the video is pulled out of the tweet, including the video of
  a quoted tweet. A tweet with several videos adds each as its own reel.
  fxtwitter.com, vxtwitter.com, fixupx.com and fixvx.com links work too.
  Every X link counts as its plain x.com link, so the same tweet shared as
  twitter.com or with a different `?s=` resolves to the same reels. A tweet
  without a video says so.
- **NSFW**: X videos that X marks as sensitive show blurred with a red NSFW
  label, open paused until tapped, and their link preview in WhatsApp has
  no picture. Logged out, X mostly refuses NSFW tweets altogether, so they
  need x.com cookies (below). TikTok and Instagram reels are never marked,
  and a quoted tweet's video only counts as NSFW when the quoting tweet is
  marked.
- **Play**: tap a reel. On a phone it fills the screen: swipe up or down
  for the next one, tap for the caption and the Share, Save and copy-link
  buttons. On a desktop it opens as an overlay; ← → move, Esc closes.
- **Share** and **Copy link** hand out `https://<site>/?reel=<id>&k=<key>`.
  Friends with the login cookie land on the board with that reel playing.
  Anyone else gets a view-only page with just that reel: they can watch and
  save it, never see the pile, and get a "have the passcode? log in" link.
  In WhatsApp the link shows the reel's thumbnail and caption. When the
  reel has aged out, the link shows "this reel has expired".
- **Save** downloads the MP4. On iPhone it opens the share sheet instead,
  where **Save Video** puts it in Photos.
- **Favorites**: the ☆ in the player (top right on a phone, under Download
  on a desktop) keeps a reel past `RETENTION_HOURS` until someone
  un-stars it, up to `MAX_FAVORITES` (default 200). Favorites have their
  own tab. The pile tab shows every reel still within its hours, starred
  ones with a ★. Un-starring a reel older than `RETENTION_HOURS` removes
  it. There is one list of favorites for everyone.
- **Delete**: the bin in the player deletes a reel for everyone, starred
  or not. "undo" in the toast takes it back for 5 seconds; after that it's
  gone, and its share links say "this reel has expired". For an X post
  with several videos, pasting the post again after deleting one of them
  brings back only the others, not the deleted one, while they are still
  in the pile.
- **Search**: on a phone, ⌕ next to the tabs opens a search field and the
  source chips (all, tiktok, instagram, x); on a desktop they are always
  there. The open tab then shows only the reels from that source whose
  caption or title has every word typed, in any order, ignoring case and
  accents, and the player swipes through those only. The counts stay as
  they are. ✕ closes it and shows everything again, pasting a link clears
  it, and a reload starts without it. Instagram and X account names are
  found through the title; TikTok's aren't.

On Android, **Add to Home screen** installs the page and it then appears
in TikTok's share menu. On iPhone, paste the link.

**Getting in.** Set `INVITE_TOKEN` and pin `https://<site>/join/<token>` in
the group. Opening it explains the login cookie, and "allow cookie & join"
logs the phone in with nothing to type. The passcode still works as the
fallback, behind the same notice ("allow cookie & log in"). "no thanks" is
remembered in that browser only (`localStorage`), and shared reels still
open without the cookie. The login cookie lasts a year and is the only
cookie the page sets; "log out" at the bottom of the board deletes it on
that phone only. A phone that was logged in before the page asked gets a
pop-up on the board instead: "allow cookie" keeps it logged in and the
pop-up stops, "no thanks, log me out" logs that phone out. Shared reels
open on it without answering. Changing `INVITE_TOKEN` stops the old link
but keeps everyone logged in; changing `API_KEY` or `WEB_PASSCODE` logs
everyone out. Ten wrong passcodes or invite tokens from one IP block it for
up to 15 minutes. No page loads anything from another site: the font is
served from `reels_api/static/fonts/`.

The page needs HTTPS for sharing and for the home-screen install; in
production that is Caddy. The pile survives restarts and deploys: the
list of reels is saved to `jobs.json` next to the videos whenever it
changes and read back on startup. Only downloads still running at the
time are lost; paste those again. On startup and every hour the app also
deletes stored files that belong to no reel, such as one left behind by a
timed-out download. If `jobs.json` can't be read, it is renamed to
`jobs.json.bad` and the pile starts empty: that same startup deletes the
stored videos, favorites included, as files that belong to no reel, so
the `.bad` file is a record, not a way to get them back.

## JSON API

Every endpoint except `/health` needs the `X-API-Key` header (or the
board's login cookie).

```bash
# 1. create a job; the url field also accepts whole share text
curl -X POST http://localhost:8000/jobs \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://vm.tiktok.com/ZMabc123/"}'
# -> {"id":"k7f3q9x2","status":"queued","ids":["k7f3q9x2"]}

# 2. poll until status is done or failed
curl -H "X-API-Key: $API_KEY" http://localhost:8000/jobs/k7f3q9x2

# 3. download the file
curl -H "X-API-Key: $API_KEY" -o video.mp4 http://localhost:8000/files/k7f3q9x2.mp4
```

| Endpoint | Returns |
|---|---|
| `GET /health` | `status`, `ytdlp_version`, and whether `ffmpeg` is on the path. No key needed. With the key or the login cookie it adds `recent`: `{"hours", "done", "failed"}`, the jobs that finished in the last `RETENTION_HOURS`, with the failures counted per code. Failures aren't saved, so they count from the last restart. `status` stays `ok` whatever they are. |
| `POST /jobs` | `202 {"id", "status", "ids"}`. `ids` has one job per video: several for an X post with several videos, otherwise just `id`. For a new X link it asks X how many videos there are first, which can take up to about 20 seconds. A link that matches jobs that haven't failed returns those jobs. `400 unsupported_url` for anything but Instagram, TikTok or X, `429 too_many_jobs` when the queue has no room for all of them. |
| `GET /jobs` | `{"jobs": [...]}`: finished reels, newest first. |
| `GET /jobs/{id}` | The job. When done it adds `file_url`, `thumbnail_url`, `title`, `caption`, `source`, `duration_seconds`, `size_bytes`, `width`, `height`, `whatsapp_ok`, `finished_at`, `expires_at`, `share_key`, `nsfw`, `favorite` and `starred_at`. When failed it adds `error` and `message`. |
| `GET /files/{id}.mp4` | The video, as a download named after the title. |
| `GET /files/{id}.jpg` | The thumbnail. `404` if thumbnailing failed. |
| `PUT /jobs/{id}/favorite` | Stars a done reel: it stays past `expires_at` until un-starred. `200` and the job. `409 favorites_full` when `MAX_FAVORITES` reels are starred. |
| `DELETE /jobs/{id}/favorite` | Un-stars it: `200` and the job. A reel already past its `expires_at` then goes at the next hourly check. |
| `DELETE /jobs/{id}` | Deletes a done reel and its files now, starred or not. `204`. |

The two `/files/` routes also open with `?k=<share_key>` instead of the key
or cookie, for that reel only. The favorite and delete routes answer
`404 not_found` for anything that isn't a done reel, and never open with
`?k=`.

Job statuses: `queued`, `downloading`, `processing`, `done`, `failed`.
Failure codes: `unsupported_url`, `private_or_removed`, `no_video`,
`login_required`, `platform_blocked`, `processing_failed`, `timeout`.
`source` is `instagram`, `tiktok` or `x`. `whatsapp_ok` is false
when the file is over 16 MB. Unknown or expired jobs return `404 not_found`.
Starring can also answer `409 favorites_full`.

## Configuration

All values are environment variables, read from `.env`. See `.env.example`.

| Variable | Default | Meaning |
|---|---|---|
| `API_KEY` | required | Key for the JSON API. Also signs the login cookie. |
| `WEB_PASSCODE` | empty | Passcode for the board. Empty disables the page. |
| `INVITE_TOKEN` | empty | Secret in the invite link `/join/<token>`, at least 16 characters. Empty disables it. |
| `RETENTION_HOURS` | `12` | How long a finished reel is kept, unless starred. Checked hourly, so a reel can last up to an hour longer. |
| `MAX_VIDEOS` | `100` | Most videos kept at once; the oldest goes first. |
| `MAX_FAVORITES` | `200` | Most starred reels. They stay past `RETENTION_HOURS` and don't count toward `MAX_VIDEOS`. |
| `WORKERS` | `2` | Concurrent downloads. Use `1` on a 1 GiB VM. |
| `MAX_QUEUE` | `20` | Jobs waiting before `POST /jobs` answers 429. |
| `JOB_TIMEOUT_SECONDS` | `180` | Download plus conversion budget per job. |
| `COOKIES_FILE` | empty | Netscape cookies file for Instagram and X (below). |
| `PUBLIC_BASE_URL` | empty | Makes `file_url` and `thumbnail_url` absolute. |
| `STORAGE_DIR`, `TEMP_DIR` | `/data/files`, `/data/tmp` | Where videos and in-progress downloads go. |
| `LOG_LEVEL` | `info` | |

### Instagram and X cookies

Instagram usually refuses anonymous downloads. Export cookies from a
throwaway account with a browser extension that writes the Netscape
format, save as `cookies.txt`, uncomment the volume line in
`docker-compose.yml`, and set `COOKIES_FILE=/cookies.txt` in `.env`.

Public tweets download without cookies. NSFW and protected tweets fail
with `login_required`; to allow them, export x.com cookies from a throwaway
account into the same file (one file can hold cookies for both sites).

### When downloads start failing

Bump `yt-dlp` in `requirements.txt` and redeploy. That fixes most
breakages; `/health` shows the version that is running.

To see whether it's time, open `https://<site>/health` on a phone that is
logged in to the board. `recent.failed` counts the failed downloads of the
last `RETENTION_HOURS` per code: a run of `platform_blocked` usually means
yt-dlp is out of date, and a run of `login_required` that the Instagram or
X cookies have expired.

## Development

On Windows, in PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

python -m pytest                                    # unit tests: no network, no ffmpeg
python -m pytest tests/test_jobs.py::test_timeout   # one test
$env:REELS_TEST_URL = "<tiktok, instagram or x url>"; python -m pytest -m network   # real download, needs ffmpeg

uvicorn reels_api.main:create_app --factory --reload   # needs .env
python scripts/make_icons.py                           # regenerate the PWA icons (already committed)
```

With `WEB_PASSCODE` set, open `http://localhost:8000/` in Chrome or
Firefox. Safari refuses the `Secure` login cookie over plain http.

### Trying the board without downloading anything

`scripts/dev_board.py` serves the real page with a pile of 12 generated
test clips and a fake downloader. Log in with passcode `dev`. Pasted links
wait 3 seconds, then fail if the URL contains `private`, `login`,
`blocked`, `novideo` or `slow`, and otherwise succeed with a copy of a test
clip. An x.com link containing `multi` is a post with 3 videos and adds 3
reels; add `partial` and only the second one fails. A link containing
`nsfw` gives an NSFW reel, and one of the seeded reels is one. Seeds 1 and
11 are favorites; seed 11 is three days old, so it only shows on the
favorites tab.
One seed's caption has an accent ("café au lait…"), to try search with.

On start it also prints an invite link and the newest reel's share link.
Open them in a private window to see what someone without the cookie sees.
It also prints an old cookie value: log in, paste it over the
`reels_session` value in DevTools (Application → Cookies) and reload to see
the cookie pop-up on the board.

Making the clips needs ffmpeg. Without a local ffmpeg, run it in the
project image; the mounts make edits to `reels_api/static` show up on
reload:

```powershell
docker build -t reels-dev .
docker run --rm -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app `
  -v "${PWD}/reels_api:/app/reels_api:ro" -v "${PWD}/scripts:/app/scripts:ro" `
  reels-dev python scripts/dev_board.py --host 0.0.0.0
```

Add `--empty` to start with an empty pile.

To keep the pile across runs, add `--dir /dev-board` and the mount
`-v "${PWD}/data/dev-board:/dev-board"` (with `--empty`: seeds are made
fresh each run and win over saved reels with the same id).

## Deploy

Production is an Oracle Cloud VM with a DuckDNS host name. It runs two
separate Compose projects, so the VM can host other apps too:

- `~/proxy`: Caddy, copied once from this repo's `proxy/` folder. It owns
  ports 80 and 443, holds the HTTPS certificates, and sends each host name
  in `~/proxy/Caddyfile` to its app over the shared Docker network `web`.
  Deploys never touch it.
- `~/reels`: this app, from `docker-compose.yml`, joined to `web` as
  `reels-api`.

To ship the last commit on `master`:

```powershell
.\scripts\deploy.ps1
```

The script is not in the repository (it is in `.gitignore`), because its
defaults are the production VM's IP address and host name. It lives only
on the PC that deploys.

The script packs the commit with `git archive`, copies it to `~/reels` on
the VM with the SSH key `~\.ssh\reels_oci`, rebuilds with
`docker compose up -d --build` (creating the `web` network first if it's
missing), deletes the image the build replaced (`docker image prune -f`,
which leaves Caddy's image, other apps' images and the build cache alone),
and waits up to a minute for `/health` to report ok. Uncommitted changes are
not deployed. It restarts only this app: Caddy and any other app keep
running. The VM keeps its `.env` and `data/` (the videos and `jobs.json`,
so the pile survives). `proxy/` is left out of the archive
(`.gitattributes`), so a deploy can't overwrite the VM's Caddyfile. Pass
`-VmHost`, `-Site`, `-Branch`, `-KeyFile` or `-User` to deploy elsewhere.

On the VM, `docker compose logs -f api` shows the app's logs.

To change a setting, edit `~/reels/.env` on the VM and run
`docker compose up -d`. The app reads `.env` only at startup, and
`docker compose restart` would keep the old values.

Adding another app to the VM, and moving a VM from the older setup (Caddy
inside this compose file) to `~/proxy`: see "More apps on the same VM" in
`docs/DEPLOY-ORACLE.md`.

### A new VM

Any Ubuntu VM with Docker works. Two click-by-click walkthroughs, each with
costs and a troubleshooting table: `docs/DEPLOY-ORACLE.md` for Oracle Cloud,
which is what production runs on and is free indefinitely, and
`docs/DEPLOY-AZURE.md` for Azure's free account, which is free for 12
months. Their VM steps apply to other providers too. The essentials:

- Open TCP 80 and 443 to everyone (Let's Encrypt needs 80) and 22 only to
  yourself. Point a DNS name at the VM and put it in `~/proxy/Caddyfile`.
- With 1 GiB of RAM, add swap and set `WORKERS=1`.
- Create `~/reels/.env` from `.env.example` before the first deploy, with
  `API_KEY` (for example `openssl rand -hex 24`), `WEB_PASSCODE`,
  `INVITE_TOKEN` (`openssl rand -hex 16`).
- Create the `web` network and start `~/proxy` (copied from `proxy/`).

## Docs

- `docs/superpowers/specs/`: the design for the API, the phone page and
  the board UI. `docs/superpowers/plans/`: how each was built.
- `design_handoff_reels_dump/`: the visual design for the board (colours,
  type, screens). Where it and the board UI spec disagree, the spec wins.
