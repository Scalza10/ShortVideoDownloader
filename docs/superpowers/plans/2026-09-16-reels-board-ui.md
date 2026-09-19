# Reels Board UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the phone page with the dark, anonymous "reels" board from the design handoff: a grid of every reel, a paste field with optimistic/fetching/error states, and a player (full-bleed swipe + tap-to-reveal on phones, centred overlay on desktop) whose Share hands out a link to the reel on this site.

**Architecture:** Three additive API changes (`caption`, `finished_at`, one job per URL). The frontend stays plain HTML/CSS/JS with no build step, rewritten as ES modules: `api.js`, `format.js`, `icons.js`, `toast.js`, `board.js`, `paste.js`, `player.js`, wired by `app.js`. A dev-only `scripts/dev_board.py` serves the real app with seeded reels and a fake pipeline so every UI task can be checked in Chrome without network access.

**Tech Stack:** Python 3.12, FastAPI, pytest + anyio (existing); plain HTML, CSS, ES modules; Lucide + Simple Icons SVG markup inlined; Bricolage Grotesque from Google Fonts; Docker (for ffmpeg in the dev server).

**Spec:** `docs/superpowers/specs/2026-09-16-reels-board-ui-design.md` (read it first; this plan argues from it). Visual reference: `design_handoff_reels_dump/README.md` and `design_handoff_reels_dump/Reels Dump.dc.html`.

## Global Constraints

- No new Python or JS dependencies. No build step, no framework, no JS test harness. JS files are ES modules loaded from `<script type="module" src="/static/app.js">`.
- Automated tests run with no network and no ffmpeg: `.venv/Scripts/python -m pytest -q` from the repo root (Git Bash) or `.venv\Scripts\python -m pytest -q` (PowerShell). The suite is green (141 passed) before Task 1.
- Dark only. Tokens and values from the handoff README "Design tokens" section; hex fallbacks in `:root`, the exact `oklch()` values inside `@supports (color: oklch(0 0 0))` (a custom property cannot fall back to an earlier declaration of itself).
- Breakpoints: `< 700px` phone layout (3 columns, bottom paste bar, full-bleed player); `≥ 700px` desktop layout (top-bar paste, overlay player); grid 4 columns from 900px, 5 from 1100px; player prev/next buttons hidden below 900px.
- Phone-width text inputs use `font-size: 16px` (handoff: 15px/14px). Anything smaller makes iOS Safari zoom the page on focus.
- UI copy is lowercase and exactly as written in the spec and this plan (e.g. `pulling it down…` uses the single `…` character).
- Reel link format: `<origin>/?reel=<job id>`.
- Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>` (use a second `-m`).
- Manual checks use the dev server from Task 3 and Chrome at 390×844 (DevTools device mode, touch) and 1280×800. Before tapping **Share** or **Save** in an automated browser, stub `navigator.share` (a native OS share dialog blocks browser automation): run `Object.defineProperty(navigator, "share", { configurable: true, value: (data) => { console.log("share", data); return Promise.resolve(); } })` in the page.

## File map

| file | change | responsibility |
|------|--------|----------------|
| `reels_api/models.py` | modify | `MediaInfo.caption`, `JobResult.caption`; `caption` + `finished_at` in `job_to_dict` |
| `reels_api/downloader.py` | modify | caption from yt-dlp `description`, falling back to title |
| `reels_api/pipeline.py` | modify | pass caption into `JobResult` |
| `reels_api/jobs.py` | modify | `JobStore.find_active_by_url`; `submit` returns an existing active job |
| `scripts/dev_board.py` | create | dev server: seeded reels, fake pipeline, passcode `dev` |
| `reels_api/static/app.html` | rewrite | page shell: header, paste form, grid, empty state, player, toast |
| `reels_api/static/style.css` | rewrite | tokens, base, header, board, paste, player, toast, login |
| `reels_api/static/app.js` | rewrite | entry: wiring, refresh timer, `?reel=` links, history, share target |
| `reels_api/static/api.js` | create | fetch wrapper (401 → reload), `listJobs`, `getJob`, `createJob` |
| `reels_api/static/format.js` | create | `formatAge`, `formatDuration`, `formatExpiry`, `sourceLine`, `slugify` |
| `reels_api/static/icons.js` | create | `icon(name)`, `hydrateIcons(root)` |
| `reels_api/static/board.js` | create | `createBoard`: keyed grid, count, empty state, optimistic tile |
| `reels_api/static/paste.js` | create | `createPaste`: idle / fetching / error, polling |
| `reels_api/static/toast.js` | create | `showToast(message, {error})` |
| `reels_api/static/player.js` | create | `createPlayer`: open/close/move, chrome, keys, gestures, actions |
| `reels_api/static/login.html` | rewrite | restyled passcode page (same element ids) |
| `reels_api/static/manifest.webmanifest` | modify | theme/background colour `#0a0b0d` |
| `README.md` | modify | "Phone web page" section describes the board; dev server |
| `tests/test_models.py`, `test_downloader.py`, `test_pipeline.py`, `test_jobs.py`, `test_routes.py`, `test_web.py` | modify | per task |
| `tests/test_dev_board.py` | create | dev pipeline and seeding |

`reels_api/static/login.js`, `sw.js` and the icons stay as they are.

---

### Task 1: `caption` and `finished_at` in the job JSON

**Files:**
- Modify: `reels_api/models.py` (`MediaInfo`, `JobResult`, `job_to_dict`)
- Modify: `reels_api/downloader.py` (end of `download`)
- Modify: `reels_api/pipeline.py` (`JobResult(...)` in `Pipeline.run`)
- Test: `tests/test_downloader.py`, `tests/test_pipeline.py`, `tests/test_models.py`, `tests/test_routes.py`

**Interfaces:**
- Produces: `MediaInfo.caption: str | None = None` (last field), `JobResult.caption: str | None = None` (last field, after `thumbnail_path`). Existing positional constructors keep working.
- Produces: done-job JSON gains `"caption": str` (`result.caption or result.title`) and `"finished_at": "YYYY-MM-DDTHH:MM:SSZ" | null`. Queued/running/failed JSON is unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_downloader.py`:

```python
def test_download_caption_from_description(tmp_path, fake_ydl):
    fake_ydl.info = {"title": "Video by someone", "description": "  Tag 1 Friend reverse this Video  ", "duration": 5}
    result = downloader.download("https://www.instagram.com/reel/x/", tmp_path)
    assert result.info.caption == "Tag 1 Friend reverse this Video"


@pytest.mark.parametrize("description", [None, "", "   "])
def test_download_caption_falls_back_to_title(tmp_path, fake_ydl, description):
    fake_ydl.info = {"title": "Hello", "description": description}
    result = downloader.download("https://vm.tiktok.com/x/", tmp_path)
    assert result.info.caption == "Hello"


def test_download_caption_without_title_or_description(tmp_path, fake_ydl):
    fake_ydl.info = {"id": "123"}
    result = downloader.download("https://vm.tiktok.com/x/", tmp_path)
    assert result.info.caption == "video"
```

Append to `tests/test_pipeline.py`:

```python
def test_pipeline_passes_caption(tmp_path):
    settings = make_settings(tmp_path)
    calls = []

    def download_with_caption(url, dest_dir, cookies_file=None):
        p = dest_dir / "source.mp4"
        p.write_bytes(b"\x00" * 10)
        return DownloadedMedia(p, MediaInfo("Title", 10.0, 720, 1280, caption="The real caption"))

    p = Pipeline(
        settings=settings,
        downloader=download_with_caption,
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    result = p.run(make_job(), lambda s: None)
    assert result.caption == "The real caption"
```

Append to `tests/test_models.py`:

```python
def test_job_to_dict_caption_and_finished_at():
    job = Job(id="abc", url="u", source=Source.INSTAGRAM, status=JobStatus.DONE)
    job.result = _result(100)
    job.finished_at = datetime(2026, 9, 16, 16, 15, 30, 123456, tzinfo=UTC)

    d = job_to_dict(job)
    assert d["caption"] == "Hello World"  # no caption: falls back to the title
    assert d["finished_at"] == "2026-09-16T16:15:30Z"

    job.result.caption = "Tag 1 Friend"
    assert job_to_dict(job)["caption"] == "Tag 1 Friend"


def test_job_to_dict_done_without_finished_at():
    job = Job(id="abc", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    job.result = _result(100)
    assert job_to_dict(job)["finished_at"] is None
```

(`test_job_to_dict_queued` and `test_job_to_dict_failed` already assert the exact dicts, so they prove the new keys stay out of non-done jobs.)

Append to `tests/test_routes.py`:

```python
def test_done_job_has_caption_and_finished_at(app_factory):
    with TestClient(app_factory()) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
        assert body["caption"] == "My Cool Reel!"
        assert body["finished_at"].endswith("Z")

        listed = client.get("/jobs", headers=HEADERS).json()["jobs"][0]
        assert listed["caption"] == "My Cool Reel!"
        assert listed["finished_at"] == body["finished_at"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest -q tests/test_downloader.py tests/test_pipeline.py tests/test_models.py tests/test_routes.py`
Expected: FAIL — `AttributeError: 'MediaInfo' object has no attribute 'caption'`, `TypeError: MediaInfo.__init__() got an unexpected keyword argument 'caption'`, `KeyError: 'caption'`, `KeyError: 'finished_at'`.

- [ ] **Step 3: Implement**

In `reels_api/models.py`, add the field to `MediaInfo`:

```python
@dataclass
class MediaInfo:
    title: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    caption: str | None = None
```

Add the field to `JobResult`, after `thumbnail_path`:

```python
    thumbnail_path: Path | None = None
    caption: str | None = None
```

In `job_to_dict`, extend the `body.update({...})` for done jobs — add these two entries after `"expires_at": ...`:

```python
                "caption": r.caption or r.title,
                "finished_at": _iso_z(job.finished_at) if job.finished_at else None,
```

In `reels_api/downloader.py`, replace the `media = MediaInfo(...)` block at the end of `download` with:

```python
    title = (info.get("title") or "video").strip() or "video"
    media = MediaInfo(
        title=title,
        duration_seconds=_to_float(info.get("duration")),
        width=_to_int(info.get("width")),
        height=_to_int(info.get("height")),
        # Instagram's title is "Video by <user>"; the real caption is the description.
        caption=(info.get("description") or "").strip() or title,
    )
    return DownloadedMedia(path=path, info=media)
```

In `reels_api/pipeline.py`, add `caption=info.caption,` as the last argument of `JobResult(...)` in `run`:

```python
                thumbnail_path=thumbnail_path,
                caption=info.caption,
            )
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (141 + 9 new = 150 passed, 1 deselected).

- [ ] **Step 5: Commit**

```bash
git add reels_api/models.py reels_api/downloader.py reels_api/pipeline.py tests/test_downloader.py tests/test_pipeline.py tests/test_models.py tests/test_routes.py
git commit -m "feat: caption and finished_at in the job JSON" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: One job per URL

**Files:**
- Modify: `reels_api/jobs.py` (`JobStore`, `JobManager.submit`)
- Test: `tests/test_jobs.py`, `tests/test_routes.py`

**Interfaces:**
- Produces: `JobStore.find_active_by_url(url: str) -> Job | None` — a job whose `url` equals `url` exactly and whose status is not `failed`.
- Changes: `JobManager.submit(text)` returns that existing job (unchanged, nothing queued) before the queue-full check. `POST /jobs` therefore answers `202 {"id", "status"}` with the existing job's id and current status.

- [ ] **Step 1: Fix the one existing test that submits the same URL three times**

In `tests/test_jobs.py`, `test_finishing_a_video_past_the_cap_drops_the_oldest` loops `for _ in range(3): job = await manager.submit("https://vm.tiktok.com/x/")`. With one job per URL that would return the same job each time. Change the loop to distinct URLs:

```python
        for i in range(3):
            job = await manager.submit(f"https://vm.tiktok.com/{i}/")
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_jobs.py`:

```python
@pytest.mark.anyio
async def test_find_active_by_url():
    store = JobStore()
    url = "https://vm.tiktok.com/x/"
    await store.add(Job(id="f", url=url, source=Source.TIKTOK, status=JobStatus.FAILED))
    assert await store.find_active_by_url(url) is None

    running = Job(id="r", url=url, source=Source.TIKTOK, status=JobStatus.DOWNLOADING)
    await store.add(running)
    assert await store.find_active_by_url(url) is running
    assert await store.find_active_by_url("https://vm.tiktok.com/y/") is None


@pytest.mark.anyio
async def test_submit_same_url_while_queued_returns_existing_job(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    # not started: the first job stays queued
    first = await manager.submit("https://vm.tiktok.com/x/")
    again = await manager.submit("https://vm.tiktok.com/x/")
    assert again is first
    assert manager.queue.qsize() == 1


@pytest.mark.anyio
async def test_submit_same_url_after_done_returns_existing_job(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        first = await manager.submit("https://vm.tiktok.com/x/")
        await wait_finished(store, first.id)
        again = await manager.submit("https://vm.tiktok.com/x/")
        assert again is first
        assert again.status == JobStatus.DONE
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_submit_same_url_after_failure_creates_new_job(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings, "job_error"), store)
    await manager.start()
    try:
        first = await manager.submit("https://vm.tiktok.com/x/")
        await wait_finished(store, first.id)
        again = await manager.submit("https://vm.tiktok.com/x/")
        assert again.id != first.id
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_submit_different_url_creates_new_job(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    first = await manager.submit("https://vm.tiktok.com/x/")
    second = await manager.submit("https://vm.tiktok.com/y/")
    assert second is not first
    assert manager.queue.qsize() == 2


@pytest.mark.anyio
async def test_submit_share_text_matches_existing_url(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    first = await manager.submit("https://vm.tiktok.com/ZMabc123/")
    again = await manager.submit("Check this out! https://vm.tiktok.com/ZMabc123/ #fyp")
    assert again is first


@pytest.mark.anyio
async def test_submit_returns_existing_job_even_when_queue_full(tmp_path):
    settings = make_settings(tmp_path, max_queue=1)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    first = await manager.submit("https://vm.tiktok.com/x/")
    assert await manager.submit("https://vm.tiktok.com/x/") is first
    with pytest.raises(JobError) as exc:
        await manager.submit("https://vm.tiktok.com/y/")
    assert exc.value.code == ErrorCode.TOO_MANY_JOBS
```

Append to `tests/test_routes.py`:

```python
def test_create_job_same_url_returns_same_id(app_factory):
    with TestClient(app_factory()) as client:
        first = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS)
        poll_until_finished(client, first.json()["id"])

        second = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS)
        assert second.status_code == 202
        assert second.json() == {"id": first.json()["id"], "status": "done"}
        assert len(client.get("/jobs", headers=HEADERS).json()["jobs"]) == 1
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest -q tests/test_jobs.py tests/test_routes.py`
Expected: FAIL — `AttributeError: 'JobStore' object has no attribute 'find_active_by_url'`, `assert again is first` failures, `test_submit_returns_existing_job_even_when_queue_full` raises `too_many_jobs` on the duplicate, and the route test sees a different id. (`test_submit_same_url_after_failure_creates_new_job` and `test_submit_different_url_creates_new_job` already pass; they guard against over-matching.)

- [ ] **Step 4: Implement**

In `reels_api/jobs.py`, add to `JobStore` after `list_recent`:

```python
    async def find_active_by_url(self, url: str) -> Job | None:
        """A job for exactly this URL that has not failed, if there is one."""
        async with self._lock:
            for job in self._jobs.values():
                if job.url == url and job.status != JobStatus.FAILED:
                    return job
        return None
```

Replace `JobManager.submit` with:

```python
    async def submit(self, text: str) -> Job:
        url = extract_url(text)
        source = detect_source(url)  # raises JobError(unsupported_url)
        # One job per link: pasting a link already in the pile resolves to that job.
        existing = await self.store.find_active_by_url(url)
        if existing is not None:
            return existing
        if self.queue.full():
            raise JobError(ErrorCode.TOO_MANY_JOBS)
        job = Job(id=new_job_id(), url=url, source=source)
        await self.store.add(job)
        self.queue.put_nowait(job)
        return job
```

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (158 passed, 1 deselected).

- [ ] **Step 6: Commit**

```bash
git add reels_api/jobs.py tests/test_jobs.py tests/test_routes.py
git commit -m "feat: pasting a link already in the pile returns the existing job" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Dev server with seeded reels

**Files:**
- Create: `scripts/dev_board.py`
- Test: `tests/test_dev_board.py`

**Interfaces:**
- Consumes: `JobResult(..., caption=...)` from Task 1.
- Produces: `python scripts/dev_board.py [--empty] [--host H] [--port P]` — serves the real app at `http://localhost:8000/`, passcode `dev`, API key `dev`. Seeded job ids are `seed00` … `seed11`; `seed07` has no thumbnail. Pasted links wait 3 s, then fail when the URL contains `private` (`private_or_removed`), `login` (`login_required`), `blocked` (`platform_blocked`) or `slow` (`timeout`); otherwise succeed with a copy of a seed clip and caption `pasted from <url>`.
- Produces (for tests): `Clip(video: Path, thumbnail: Path, seconds: int)`, `DevPipeline(settings, clips, delay=FAKE_DELAY_SECONDS)`, `seed_jobs(settings, clips) -> list[Job]`, `SEED_MINUTES_AGO`, `NO_THUMBNAIL_SEED`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dev_board.py`:

```python
import importlib.util
import sys
from pathlib import Path

import pytest

from reels_api.models import ErrorCode, Job, JobError, JobStatus, Source
from tests.conftest import make_settings

# scripts/ is not a package; load the dev server module from its path.
_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dev_board.py"
_spec = importlib.util.spec_from_file_location("dev_board", _PATH)
dev_board = importlib.util.module_from_spec(_spec)
sys.modules["dev_board"] = dev_board  # dataclasses look the module up while building Clip
_spec.loader.exec_module(dev_board)


def fake_clips(tmp_path: Path) -> list:
    clips = []
    for n in range(2):
        video = tmp_path / f"clip{n}.mp4"
        video.write_bytes(b"video" * (n + 1))
        thumbnail = tmp_path / f"clip{n}.jpg"
        thumbnail.write_bytes(b"\xff\xd8jpeg")
        clips.append(dev_board.Clip(video, thumbnail, 10 + n))
    return clips


@pytest.mark.parametrize(
    "url,code",
    [
        ("https://vm.tiktok.com/private/", ErrorCode.PRIVATE_OR_REMOVED),
        ("https://www.instagram.com/reel/login/", ErrorCode.LOGIN_REQUIRED),
        ("https://vm.tiktok.com/blocked/", ErrorCode.PLATFORM_BLOCKED),
        ("https://vm.tiktok.com/slow/", ErrorCode.TIMEOUT),
    ],
)
def test_dev_pipeline_fails_on_keywords(tmp_path, url, code):
    settings = make_settings(tmp_path)
    pipeline = dev_board.DevPipeline(settings, fake_clips(tmp_path), delay=0)
    with pytest.raises(JobError) as exc:
        pipeline.run(Job(id="j1", url=url, source=Source.TIKTOK), lambda s: None)
    assert exc.value.code == code


def test_dev_pipeline_success_copies_a_clip(tmp_path):
    settings = make_settings(tmp_path)
    pipeline = dev_board.DevPipeline(settings, fake_clips(tmp_path), delay=0)
    statuses = []
    result = pipeline.run(Job(id="j1", url="https://vm.tiktok.com/ok/", source=Source.TIKTOK), statuses.append)
    assert statuses == [JobStatus.DOWNLOADING, JobStatus.PROCESSING]
    assert result.file_path == settings.storage_dir / "j1.mp4"
    assert result.file_path.read_bytes() == b"video"
    assert result.thumbnail_path.read_bytes() == b"\xff\xd8jpeg"
    assert result.caption == "pasted from https://vm.tiktok.com/ok/"


def test_seed_jobs(tmp_path):
    settings = make_settings(tmp_path)
    jobs = dev_board.seed_jobs(settings, fake_clips(tmp_path))
    assert len(jobs) == len(dev_board.SEED_MINUTES_AGO)
    assert all(j.status == JobStatus.DONE and j.result.file_path.is_file() for j in jobs)
    assert jobs[dev_board.NO_THUMBNAIL_SEED].result.thumbnail_path is None
    assert {j.source for j in jobs} == {Source.TIKTOK, Source.INSTAGRAM}
    assert all(j.expires_at > j.finished_at for j in jobs)
    assert len({j.url for j in jobs}) == len(jobs)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/Scripts/python -m pytest -q tests/test_dev_board.py`
Expected: FAIL — `FileNotFoundError` (no `scripts/dev_board.py`).

- [ ] **Step 3: Implement**

Create `scripts/dev_board.py`:

```python
"""Local server for trying the board UI by hand. Development only.

Starts the real app with passcode "dev", a fake pipeline and a pile of
seeded reels. Making the seed clips needs ffmpeg on PATH. From the repo root:

    python scripts/dev_board.py            # 12 seeded reels
    python scripts/dev_board.py --empty    # empty pile

Without a local ffmpeg, run it in the project image (PowerShell). The mounts
make edits to reels_api/static show up on reload:

    docker build -t reels-dev .
    docker run --rm -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app `
      -v "${PWD}/reels_api:/app/reels_api:ro" -v "${PWD}/scripts:/app/scripts:ro" `
      reels-dev python scripts/dev_board.py --host 0.0.0.0

Open http://localhost:8000/ in Chrome and log in with "dev". Pasted links
wait 3 seconds, then fail if the URL contains "private", "login", "blocked"
or "slow", and otherwise succeed with a copy of a seed clip.
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import uvicorn

from reels_api.jobs import JobStore
from reels_api.main import create_app
from reels_api.models import ErrorCode, Job, JobError, JobResult, JobStatus, Source, utcnow
from reels_api.settings import Settings

PASSCODE = "dev"
FAKE_DELAY_SECONDS = 3.0
CLIP_COUNT = 6
FAILURE_WORDS: dict[str, ErrorCode] = {
    "private": ErrorCode.PRIVATE_OR_REMOVED,
    "login": ErrorCode.LOGIN_REQUIRED,
    "blocked": ErrorCode.PLATFORM_BLOCKED,
    "slow": ErrorCode.TIMEOUT,
}
CAPTIONS = [
    "Tag 1 Friend reverse this Video and look what happens @skyandtami",
    "wait for it",
    "POV: you finally found the good taco place and it is a gas station. This caption keeps going "
    "so that it wraps past two lines on a phone and has to be cut off with an ellipsis.",
    "cat vs cucumber, round 2",
    "",  # no caption: the page shows the title instead
    "how to fold a fitted sheet (it is not possible)",
]
SEED_MINUTES_AGO = [0.5, 4, 12, 35, 61, 95, 130, 180, 220, 260, 300, 330]
NO_THUMBNAIL_SEED = 7


@dataclass
class Clip:
    video: Path
    thumbnail: Path
    seconds: int


def make_clip(out_dir: Path, number: int) -> Clip:
    """A 720x1280 test pattern with a tone, tinted per clip, plus its thumbnail."""
    seconds = 8 + (number * 7) % 23  # 8..30 seconds
    video = out_dir / f"clip{number:02d}.mp4"
    thumbnail = out_dir / f"clip{number:02d}.jpg"
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"testsrc2=size=720x1280:rate=30:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency={220 + number * 40}:duration={seconds}",
            "-vf", f"hue=h={number * 60}",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", "-movflags", "+faststart", str(video),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-ss", "1", "-i", str(video),
            "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", str(thumbnail),
        ],
        check=True,
    )
    return Clip(video, thumbnail, seconds)


def store_clip(settings: Settings, clip: Clip, job: Job, caption: str, with_thumbnail: bool = True) -> JobResult:
    """Copy a clip into storage under the job's id, as the real pipeline would leave it."""
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    video = settings.storage_dir / f"{job.id}.mp4"
    shutil.copyfile(clip.video, video)
    thumbnail = None
    if with_thumbnail:
        thumbnail = settings.storage_dir / f"{job.id}.jpg"
        shutil.copyfile(clip.thumbnail, thumbnail)
    return JobResult(
        file_path=video,
        title=caption[:40] or f"reel {job.id}",
        source=job.source,
        duration_seconds=float(clip.seconds),
        size_bytes=video.stat().st_size,
        width=720,
        height=1280,
        thumbnail_path=thumbnail,
        caption=caption or None,
    )


class DevPipeline:
    """Stands in for the real pipeline: no network, failures chosen by words in the URL."""

    def __init__(self, settings: Settings, clips: list[Clip], delay: float = FAKE_DELAY_SECONDS) -> None:
        self.settings = settings
        self.delay = delay
        self._clips = itertools.cycle(clips)
        self._lock = threading.Lock()

    def run(self, job: Job, set_status) -> JobResult:
        set_status(JobStatus.DOWNLOADING)
        time.sleep(self.delay)
        set_status(JobStatus.PROCESSING)
        for word, code in FAILURE_WORDS.items():
            if word in job.url:
                raise JobError(code)
        with self._lock:
            clip = next(self._clips)
        return store_clip(self.settings, clip, job, f"pasted from {job.url}")


def seed_jobs(settings: Settings, clips: list[Clip]) -> list[Job]:
    """Finished jobs spread over the retention window, newest first."""
    now = utcnow()
    retention = timedelta(hours=settings.retention_hours)
    jobs = []
    for i, minutes in enumerate(SEED_MINUTES_AGO):
        source = Source.INSTAGRAM if i % 3 == 2 else Source.TIKTOK
        host = "www.instagram.com/reel" if source == Source.INSTAGRAM else "www.tiktok.com/@dev/video"
        job = Job(id=f"seed{i:02d}", url=f"https://{host}/{i}", source=source, status=JobStatus.DONE)
        job.finished_at = now - timedelta(minutes=minutes)
        job.expires_at = job.finished_at + retention
        job.result = store_clip(
            settings, clips[i % len(clips)], job, CAPTIONS[i % len(CAPTIONS)], with_thumbnail=i != NO_THUMBNAIL_SEED
        )
        jobs.append(job)
    return jobs


async def _add_all(store: JobStore, jobs: list[Job]) -> None:
    for job in jobs:
        await store.add(job)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--empty", action="store_true", help="start with an empty pile")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    root = Path(tempfile.mkdtemp(prefix="reels-dev-"))
    settings = Settings(
        _env_file=None,
        api_key="dev",
        web_passcode=PASSCODE,
        storage_dir=root / "files",
        temp_dir=root / "tmp",
        max_videos=50,
        workers=1,
    )
    clips_dir = root / "clips"
    clips_dir.mkdir()
    print("making seed clips with ffmpeg...", flush=True)
    clips = [make_clip(clips_dir, n) for n in range(CLIP_COUNT)]

    app = create_app(settings=settings, pipeline=DevPipeline(settings, clips))
    if not args.empty:
        # Before the app starts: startup deletes stored files that belong to no known job.
        asyncio.run(_add_all(app.state.store, seed_jobs(settings, clips)))
    print(f"open http://localhost:{args.port}/ and log in with passcode {PASSCODE!r}", flush=True)
    try:
        uvicorn.run(app, host=args.host, port=args.port)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (164 passed, 1 deselected).

- [ ] **Step 5: Start the dev server and check it serves the seeds**

Docker Desktop must be running. In PowerShell from the repo root (run in the background; it keeps running for later tasks):

```powershell
docker build -t reels-dev .
docker run --rm --name reels-dev -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app -v "${PWD}/reels_api:/app/reels_api:ro" -v "${PWD}/scripts:/app/scripts:ro" reels-dev python scripts/dev_board.py --host 0.0.0.0
```

When it prints `open http://localhost:8000/ ...`, run in Git Bash:

```bash
curl -s -H "X-API-Key: dev" http://localhost:8000/jobs | python -c "import json,sys; jobs=json.load(sys.stdin)['jobs']; print(len(jobs), jobs[0]['id'], jobs[0]['caption'][:20], jobs[7]['thumbnail_url'])"
curl -s -o /dev/null -w "%{http_code}\n" -H "X-API-Key: dev" http://localhost:8000/files/seed00.mp4
```

Expected: `12 seed00 Tag 1 Friend reverse None` and `200`. Stop it with `docker stop reels-dev`. To restart with an empty pile, run the same `docker run` command with `--empty` appended.

- [ ] **Step 6: Commit**

```bash
git add scripts/dev_board.py tests/test_dev_board.py
git commit -m "feat: dev server with seeded reels and a fake pipeline" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Page shell, shared modules and the board

**Files:**
- Rewrite: `reels_api/static/app.html`, `reels_api/static/style.css`, `reels_api/static/app.js`
- Create: `reels_api/static/api.js`, `reels_api/static/format.js`, `reels_api/static/icons.js`, `reels_api/static/board.js`
- Modify: `reels_api/static/manifest.webmanifest`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `caption`, `finished_at` in `GET /jobs` items (Task 1); the dev server (Task 3).
- Produces (`api.js`): `class Unauthorized extends Error`; `api(path, options) -> Promise<Response>` (on 401 calls `location.reload()` and throws `Unauthorized`); `listJobs() -> Promise<Job[]>` (throws on non-OK or network error); `getJob(id) -> Promise<Job | null>` (null on 404, throws otherwise); `createJob(text) -> Promise<{id, status} | {error: string}>` (throws on network error).
- Produces (`format.js`): `SOURCE_NAME`; `formatAge(iso, now = Date.now())` → `""`, `"now"`, `"12m"`, `"3h"`, `"1d"`; `formatDuration(seconds)` → `""` or floored `"m:ss"`; `formatExpiry(iso, now = Date.now())` → `""`, `"gone soon"`, `"gone in 40m"`, `"gone in 6h"`; `sourceLine(reel, now = Date.now())` → `"TikTok · 0:19 · gone in 6h"`; `slugify(title)`.
- Produces (`icons.js`): `icon(name) -> string` (SVG with class `icon`, `aria-hidden`), names `arrowUp check chevronLeft chevronRight circleAlert clipboard clipboardPlus clock download link2 volume2 volumeX x play whatsapp`; `hydrateIcons(root)` inserts the icon named by each `[data-icon]` element as its first child (the attribute stays; CSS styles `span[data-icon]`).
- Produces (`board.js`): `createBoard({ grid, empty, count, onOpen })` → `{ setReels(list), getReels(), has(id), remove(id), addPending(), finishPending(list), removePending(), setDimmed(bool), reveal(id) }`. `onOpen(id, tileElement)` is optional (wired in Task 6). Nothing renders until the first `setReels` or `addPending`.
- Produces (`app.html`): ids `count-n`, `grid`, `empty`; header element `<header class="topbar">`. Task 5 inserts the paste form into the header; Task 6 adds the player and toast before `</body>`.

- [ ] **Step 1: Update the web tests**

In `tests/test_web.py`, add below `PASSCODE = "letmein"`:

```python
APP_MODULES = ["app.js", "api.js", "format.js", "icons.js", "board.js"]
```

Replace the whole `test_app_js_is_served` function with:

```python
def test_app_modules_are_served(web_app):
    with TestClient(web_app()) as client:
        for name in APP_MODULES:
            r = client.get(f"/static/{name}")
            assert r.status_code == 200, name
            assert r.headers["content-type"].startswith("text/javascript"), name
            assert r.headers["cache-control"] == "no-cache", name


def test_app_page_loads_entry_module(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        html = client.get("/").text
    assert '<script type="module" src="/static/app.js"></script>' in html
```

In `test_index_serves_login_then_app`, replace `assert 'id="link"' in r.text` with:

```python
        assert 'id="grid"' in r.text
```

In `test_manifest_sw_and_static`, after `assert m.json()["share_target"]["action"] == "/"` add:

```python
        assert m.json()["theme_color"] == "#0a0b0d"
```

- [ ] **Step 2: Run the web tests to verify they fail**

Run: `.venv/Scripts/python -m pytest -q tests/test_web.py`
Expected: FAIL — 404 for `/static/api.js`, no module script tag, `'id="grid"'` missing, theme colour `#111827`.

- [ ] **Step 3: Write `reels_api/static/api.js`**

```js
// Every request goes through api(): a 401 anywhere means the session cookie is gone.
export class Unauthorized extends Error {}

export async function api(path, options) {
  const response = await fetch(path, options);
  if (response.status === 401) {
    location.reload();
    throw new Unauthorized();
  }
  return response;
}

export async function listJobs() {
  const response = await api("/jobs");
  if (!response.ok) throw new Error(`GET /jobs failed: ${response.status}`);
  const body = await response.json();
  return body.jobs || [];
}

// The job, or null when the server does not know the id.
export async function getJob(id) {
  const response = await api(`/jobs/${encodeURIComponent(id)}`);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`GET /jobs/${id} failed: ${response.status}`);
  return response.json();
}

// {id, status} when accepted, {error} with the server's error code otherwise.
export async function createJob(text) {
  const response = await api("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: text }),
  });
  const body = await response.json().catch(() => ({}));
  if (response.ok) return body;
  return { error: body.error || "processing_failed" };
}
```

- [ ] **Step 4: Write `reels_api/static/format.js` and sanity-check it**

```js
// Pure text helpers shared by the board and the player.

export const SOURCE_NAME = { tiktok: "TikTok", instagram: "Instagram" };

const MINUTE_MS = 60_000;

// Tile badge: "now", "12m", "3h", "1d" since an ISO time (spec 6.2).
export function formatAge(iso, now = Date.now()) {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const minutes = Math.floor((now - then) / MINUTE_MS);
  if (minutes < 1) return "now";
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

// m:ss, floored; "" when unknown.
export function formatDuration(seconds) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return "";
  const whole = Math.floor(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

// "gone in 6h", "gone in 40m", "gone soon" (spec 7.1).
export function formatExpiry(iso, now = Date.now()) {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return "";
  const ms = then - now;
  if (ms <= 0) return "gone soon";
  const minutes = Math.round(ms / MINUTE_MS);
  if (minutes < 60) return `gone in ${Math.max(1, minutes)}m`;
  return `gone in ${Math.round(minutes / 60)}h`;
}

// "TikTok · 0:19 · gone in 6h", leaving out parts that are unknown.
export function sourceLine(reel, now = Date.now()) {
  return [SOURCE_NAME[reel.source] || reel.source, formatDuration(reel.duration_seconds), formatExpiry(reel.expires_at, now)]
    .filter(Boolean)
    .join(" · ");
}

// Same rules as routes.slugify on the server.
export function slugify(title) {
  const slug = String(title || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return slug.slice(0, 60).replace(/-+$/g, "") || "video";
}
```

Sanity-check with Node (on the dev machine; not project tooling). Save this as `format-check.mjs` in your scratch directory (not in the repo) and run `node <scratch>/format-check.mjs` from the repo root:

```js
import * as f from "file:///C:/Project/ReelsTranslator/reels_api/static/format.js";
const now = Date.parse("2026-09-16T12:00:00Z");
console.log([
  f.formatAge("2026-09-16T11:59:30Z", now),
  f.formatAge("2026-09-16T11:48:00Z", now),
  f.formatAge("2026-09-16T07:00:00Z", now),
  f.formatAge("2026-09-14T12:00:00Z", now),
  f.formatAge(null, now),
  f.formatDuration(19.7),
  f.formatDuration(null),
  f.formatExpiry("2026-09-16T17:50:00Z", now),
  f.formatExpiry("2026-09-16T12:00:20Z", now),
  f.formatExpiry("2026-09-16T11:00:00Z", now),
  f.sourceLine({ source: "tiktok", duration_seconds: 19, expires_at: "2026-09-16T18:00:00Z" }, now),
  f.slugify("My Cool Reel!"),
].join(" | "));
```

Expected output: `now | 12m | 5h | 2d |  | 0:19 |  | gone in 6h | gone in 1m | gone soon | TikTok · 0:19 · gone in 6h | my-cool-reel`

- [ ] **Step 5: Write `reels_api/static/icons.js`**

```js
// Icon markup. Stroke icons are from Lucide (https://lucide.dev), ISC License,
// Copyright (c) Lucide Contributors. The WhatsApp mark is from Simple Icons
// (https://simpleicons.org), CC0 1.0. Sizes and stroke widths are set in style.css.

const STROKE = {
  arrowUp: '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
  chevronLeft: '<path d="m15 18-6-6 6-6"/>',
  chevronRight: '<path d="m9 18 6-6-6-6"/>',
  circleAlert: '<circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>',
  clipboard: '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>',
  clipboardPlus: '<rect width="8" height="4" x="8" y="2" rx="1" ry="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 14h6"/><path d="M12 17v-6"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
  link2: '<path d="M9 17H7A5 5 0 0 1 7 7h2"/><path d="M15 7h2a5 5 0 1 1 0 10h-2"/><line x1="8" x2="16" y1="12" y2="12"/>',
  volume2: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/>',
  volumeX: '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/><line x1="22" x2="16" y1="9" y2="15"/><line x1="16" x2="22" y1="9" y2="15"/>',
  x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
};

const FILL = {
  play: '<polygon points="6 3 20 12 6 21 6 3"/>',
  whatsapp:
    '<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z"/>',
};

export function icon(name) {
  const open = '<svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"';
  if (STROKE[name]) {
    return `${open} fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">${STROKE[name]}</svg>`;
  }
  if (FILL[name]) return `${open} fill="currentColor">${FILL[name]}</svg>`;
  throw new Error(`unknown icon: ${name}`);
}

// Put the icon named by data-icon="..." at the start of every such element. Call once per root.
export function hydrateIcons(root) {
  for (const el of root.querySelectorAll("[data-icon]")) {
    el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon));
  }
}
```

- [ ] **Step 6: Write `reels_api/static/board.js`**

```js
import { formatAge } from "./format.js";
import { icon } from "./icons.js";

// The grid of reels, the pile count, the empty state and the optimistic tile (spec 6.1-6.4).
export function createBoard({ grid, empty, count, onOpen }) {
  let reels = [];
  let pending = null; // the optimistic tile while a paste is in flight
  const tiles = new Map(); // job id -> tile element, kept across refreshes so images never reload

  function buildTile(reel) {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "tile";
    if (reel.thumbnail_url) {
      const img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      img.addEventListener("load", () => img.classList.add("loaded"), { once: true });
      img.src = reel.thumbnail_url;
      tile.append(img);
    }
    const badge = document.createElement("span");
    badge.className = "badge";
    const hover = document.createElement("span");
    hover.className = "hover-row";
    hover.innerHTML = `<span class="hover-inner">${icon("play")}<span class="hover-label"></span></span>`;
    tile.append(badge, hover);
    tile.addEventListener("click", () => {
      if (onOpen) onOpen(reel.id, tile);
    });
    return tile;
  }

  function updateTile(tile, reel, newest, now) {
    const age = formatAge(reel.finished_at, now);
    const ago = age === "now" ? "now" : `${age} ago`;
    const badge = tile.querySelector(".badge");
    badge.replaceChildren(age);
    if (newest) badge.insertAdjacentHTML("afterbegin", icon("play"));
    badge.hidden = !age;
    tile.querySelector(".hover-label").textContent = `play · ${ago}`;
    tile.setAttribute("aria-label", `play, ${ago}`);
  }

  function render() {
    const now = Date.now();
    const ids = new Set(reels.map((reel) => reel.id));
    for (const [id, tile] of tiles) {
      if (!ids.has(id)) {
        tile.remove();
        tiles.delete(id);
      }
    }
    let previous = pending;
    reels.forEach((reel, i) => {
      let tile = tiles.get(reel.id);
      if (!tile) {
        tile = buildTile(reel);
        tiles.set(reel.id, tile);
      }
      updateTile(tile, reel, i === 0, now);
      const expected = previous ? previous.nextSibling : grid.firstChild;
      if (tile !== expected) grid.insertBefore(tile, expected);
      previous = tile;
    });
    const total = reels.length + (pending ? 1 : 0);
    count.textContent = String(total);
    grid.hidden = total === 0;
    empty.hidden = total !== 0;
    document.body.classList.toggle("is-empty", total === 0);
  }

  function dropPending() {
    if (!pending) return;
    pending.remove();
    pending = null;
  }

  return {
    setReels(list) {
      reels = list.slice();
      render();
    },
    getReels() {
      return reels.slice();
    },
    has(id) {
      return tiles.has(id);
    },
    remove(id) {
      reels = reels.filter((reel) => reel.id !== id);
      render();
    },
    addPending() {
      dropPending();
      pending = document.createElement("div");
      pending.className = "tile pending";
      pending.innerHTML = '<span class="spinner" aria-hidden="true"></span><span class="badge">now</span>';
      grid.prepend(pending);
      render();
    },
    // Swap the optimistic tile for the fresh list in one render, so the count never flickers.
    finishPending(list) {
      dropPending();
      reels = list.slice();
      render();
    },
    removePending() {
      dropPending();
      render();
    },
    setDimmed(dimmed) {
      grid.classList.toggle("dimmed", dimmed);
    },
    reveal(id) {
      const tile = tiles.get(id);
      if (tile) tile.scrollIntoView({ block: "nearest", behavior: "smooth" });
    },
  };
}
```

- [ ] **Step 7: Write `reels_api/static/app.js`**

```js
import { listJobs } from "./api.js";
import { createBoard } from "./board.js";
import { hydrateIcons } from "./icons.js";

const REFRESH_MS = 30_000;
const $ = (id) => document.getElementById(id);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
hydrateIcons(document);

const board = createBoard({ grid: $("grid"), empty: $("empty"), count: $("count-n") });

// The pile from the server, or null when it could not be loaded.
async function loadJobs() {
  try {
    return await listJobs();
  } catch (_) {
    return null;
  }
}

async function refresh() {
  const jobs = await loadJobs();
  if (jobs) board.setReels(jobs); // on failure keep whatever is on screen
}

setInterval(() => {
  if (document.visibilityState === "visible") refresh();
}, REFRESH_MS);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refresh();
});

refresh();
```

- [ ] **Step 8: Write `reels_api/static/app.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0a0b0d">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="Reels">
<title>reels</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700;12..96,800&amp;display=swap">
<link rel="stylesheet" href="/static/style.css">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/static/icon-192.png">
<script type="module" src="/static/app.js"></script>
</head>
<body>
<header class="topbar">
  <span class="wordmark">reels</span>
  <span class="count"><span id="count-n"></span> in the pile<span class="count-extra"> · no names, ever</span></span>
</header>
<main class="board">
  <div id="grid" class="grid"></div>
  <div id="empty" class="empty" hidden>
    <span class="empty-box" data-icon="clipboardPlus"></span>
    <p class="empty-title">the pile is empty</p>
    <p class="empty-body">paste something in and it shows up for everyone.</p>
  </div>
</main>
</body>
</html>
```

- [ ] **Step 9: Write `reels_api/static/style.css`**

This replaces the old light/dark stylesheet. `login.html` still links it and keeps working, but looks plain until Task 8 restyles it.

```css
/* reels. Design values: design_handoff_reels_dump/README.md, "Design tokens". */

:root {
  --bg: #0a0b0d;
  --surface: #14161a;
  --tile: #14171c;
  --ink: #f2f0ea;
  --ink-70: rgba(242, 240, 234, 0.7);
  --ink-50: rgba(242, 240, 234, 0.5);
  --ink-42: rgba(242, 240, 234, 0.42);
  --hairline: rgba(255, 255, 255, 0.1);
  --hairline-strong: rgba(255, 255, 255, 0.22);
  --accent: #0ec8de;
  --accent-ink: #08181c;
  --accent-bright: #5ddcec;
  --danger-border: #cf4f48;
  --danger-icon: #f07f75;
  --danger-text: #f7978c;
  --scrim-badge: rgba(0, 0, 0, 0.6);
  --scrim-overlay: rgba(4, 5, 7, 0.82);
  --font: "Bricolage Grotesque", system-ui, sans-serif;
  --mono: ui-monospace, Menlo, Consolas, monospace;
  --header-h: 49px; /* phone header: 16 + 21 + 12 */
  --paste-bar: 94px; /* phone paste bar above the safe area: 26 + 50 + 18 */
}

/* The handoff's exact colours where oklch is understood; the hex values above are close stand-ins. */
@supports (color: oklch(0 0 0)) {
  :root {
    --accent: oklch(0.72 0.19 200);
    --accent-bright: oklch(0.8 0.15 200);
    --danger-border: oklch(0.62 0.17 25);
    --danger-icon: oklch(0.74 0.16 25);
    --danger-text: oklch(0.78 0.15 25);
  }
}

/* ---- base ---- */

*, *::before, *::after { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; color-scheme: dark; background: var(--bg); }
body {
  margin: 0;
  min-height: 100dvh;
  background: var(--bg);
  color: var(--ink);
  font: 400 15px/1.4 var(--font);
  -webkit-tap-highlight-color: transparent;
}
[hidden] { display: none !important; }
p { margin: 0; }
button { margin: 0; padding: 0; border: 0; background: none; color: inherit; font: inherit; cursor: pointer; }
button:disabled, button[aria-disabled="true"] { cursor: default; }
input { margin: 0; font: inherit; color: inherit; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
span[data-icon] { display: flex; }
.icon { display: block; flex: none; width: 18px; height: 18px; }
.spinner {
  display: block;
  flex: none;
  width: 20px;
  height: 20px;
  border-radius: 999px;
  border: 2px solid rgba(255, 255, 255, 0.14);
  border-top-color: var(--accent);
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ---- header (spec 6.1) ---- */

.topbar {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: calc(16px + env(safe-area-inset-top)) 16px 12px;
}
.wordmark { font: 700 21px/1 var(--font); letter-spacing: -0.03em; }
.count { font: 500 11px var(--mono); color: var(--ink-50); white-space: nowrap; }
.count-extra { display: none; }
.count:has(#count-n:empty), body.is-empty .count { visibility: hidden; }

/* ---- board (spec 6.2) ---- */

.board { padding: 0 6px calc(var(--paste-bar) + 24px + env(safe-area-inset-bottom)); }
body.is-empty .board { padding-bottom: 0; }
.grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  transition: opacity 160ms ease-out;
}
.grid.dimmed { opacity: 0.4; }
.tile {
  position: relative;
  display: block;
  width: 100%;
  aspect-ratio: 9 / 16;
  overflow: hidden;
  border-radius: 4px;
  background: var(--tile);
}
.tile:focus-visible { outline: 2px solid var(--accent); outline-offset: -1px; }
.tile img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0;
  transition: opacity 200ms ease-out;
}
.tile img.loaded { opacity: 1; }
.badge {
  position: absolute;
  left: 5px;
  bottom: 5px;
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px 5px;
  border-radius: 4px;
  background: var(--scrim-badge);
  font: 500 9px/1.2 var(--mono);
  color: var(--ink);
  pointer-events: none;
}
.badge .icon { width: 8px; height: 8px; }
.hover-row { display: none; }
.tile.pending {
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--hairline);
}
.tile.pending .badge { padding: 0; background: none; color: var(--accent-bright); }

/* ---- empty pile (spec 6.4) ---- */

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  min-height: calc(100dvh - var(--header-h) - env(safe-area-inset-top));
  padding: 0 40px calc(var(--paste-bar) + env(safe-area-inset-bottom));
  text-align: center;
}
.empty-box {
  width: 54px;
  height: 54px;
  align-items: center;
  justify-content: center;
  border-radius: 15px;
  border: 1px dashed rgba(242, 240, 234, 0.24);
  color: var(--ink-50);
}
.empty-box .icon { width: 22px; height: 22px; stroke-width: 1.7; }
.empty-title { font: 700 22px/1.15 var(--font); letter-spacing: -0.02em; }
.empty-body { font: 400 14px/1.45 var(--font); color: rgba(242, 240, 234, 0.55); }

/* ---- desktop board (spec 5.1, 6.1, 6.2) ---- */

@media (min-width: 700px) {
  .topbar {
    position: sticky;
    top: 0;
    z-index: 10;
    align-items: center;
    justify-content: flex-start;
    gap: 22px;
    padding: 16px 28px;
    background: var(--bg);
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  }
  .wordmark { font-size: 22px; }
  .count { flex: 1; font-size: 11.5px; }
  .count-extra { display: inline; }
  .board { padding: 26px 28px 48px; }
  body.is-empty .board { padding: 0 28px; }
  .grid { max-width: 1100px; margin: 0 auto; gap: 12px; }
  .tile { border-radius: 8px; }
  .badge { left: 8px; bottom: 8px; gap: 4px; padding: 3px 7px; border-radius: 5px; font-size: 10px; }
  .badge .icon { width: 9px; height: 9px; }
  .hover-row {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: flex-end;
    padding: 10px;
    background: linear-gradient(to top, rgba(0, 0, 0, 0.62), rgba(0, 0, 0, 0) 55%);
    opacity: 0;
    pointer-events: none;
  }
  .hover-inner { display: flex; align-items: center; gap: 6px; font: 600 11px var(--font); color: var(--ink); }
  .hover-inner .icon { width: 13px; height: 13px; }
  .tile:focus-visible .hover-row { opacity: 1; }
  .tile:focus-visible .badge { opacity: 0; }
  .empty { min-height: calc(100dvh - 75px); padding: 0 40px 75px; }
}

@media (min-width: 700px) and (hover: hover) {
  .tile:not(.pending):hover { outline: 2px solid var(--accent); outline-offset: -1px; }
  .tile:not(.pending):hover .hover-row { opacity: 1; }
  .tile:not(.pending):hover .badge { opacity: 0; }
}

@media (min-width: 900px) {
  .grid { grid-template-columns: repeat(4, 1fr); }
}

@media (min-width: 1100px) {
  .grid { grid-template-columns: repeat(5, 1fr); }
}
```

- [ ] **Step 10: Update the manifest colours**

In `reels_api/static/manifest.webmanifest`, change both `"background_color": "#111827"` and `"theme_color": "#111827"` to `"#0a0b0d"`.

- [ ] **Step 11: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (165 passed, 1 deselected).

- [ ] **Step 12: Check the board in Chrome**

Start the dev server as in Task 3 Step 5. The `reels_api` mount serves these files directly, so a page reload picks up edits. Open `http://localhost:8000/` and log in with `dev`. Compare with handoff screens 1, 5 and 8:

- 390×844: header "reels" / "12 in the pile" (mono, dim); 3-column 9:16 grid, 4px gap, 6px sides; every tile shows its test-pattern thumbnail and a time badge ("now", "4m", "12m", "35m", "1h", …, "5h"); the first badge has a small play triangle; `seed07` is a plain dark tile. No console errors.
- 1280×800: sticky top bar with "12 in the pile · no names, ever"; 5 columns capped at 1100px, 12px gap, 8px radius; hovering a tile shows the accent outline and the "play · 4m ago" row and hides the badge; Tab gives the same look via focus. At 1000px wide: 4 columns; at 800px: 3.
- Restart the dev server with `--empty`: the "the pile is empty" block is centred with its dashed clipboard-plus box, and no count shows, at both widths.
- Leave the page open 30 s with DevTools Network open: `GET /jobs` repeats and no thumbnail is fetched again.

- [ ] **Step 13: Commit**

```bash
git add reels_api/static/app.html reels_api/static/style.css reels_api/static/app.js reels_api/static/api.js reels_api/static/format.js reels_api/static/icons.js reels_api/static/board.js reels_api/static/manifest.webmanifest tests/test_web.py
git commit -m "feat: dark board page shell with the reels grid" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Paste field

**Files:**
- Create: `reels_api/static/paste.js`
- Rewrite: `reels_api/static/app.js`
- Modify: `reels_api/static/app.html` (form inside the header), `reels_api/static/style.css` (append)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `createJob`, `getJob`, `Unauthorized` (`api.js`); `icon` (`icons.js`); board methods `addPending`, `finishPending`, `removePending`, `setDimmed`, `has`, `reveal`, `getReels` (Task 4); one job per URL (Task 2).
- Produces (`paste.js`): `createPaste({ form, onStart, onDone, onFail, onStateChange })` → `{ submit(text) }`. Callbacks: `onStart()` when a paste begins; `onDone(job)` (async, awaited, must not throw) with the finished job; `onFail()` before the error state shows; `onStateChange(state)` with `"idle" | "fetching" | "error"` on every change (also once at start with `"idle"`). The form's `data-state` attribute mirrors the state for CSS.
- Produces (`app.html`): ids `paste`, `paste-input`, `paste-submit`, `paste-icon`, `paste-url`, `paste-error`, `paste-error-hint`.

- [ ] **Step 1: Extend the module test**

In `tests/test_web.py`, change the `APP_MODULES` line to:

```python
APP_MODULES = ["app.js", "api.js", "format.js", "icons.js", "board.js", "paste.js"]
```

Run: `.venv/Scripts/python -m pytest -q tests/test_web.py`
Expected: FAIL — `/static/paste.js` returns 404.

- [ ] **Step 2: Add the form to `reels_api/static/app.html`**

Replace:

```html
  <span class="count"><span id="count-n"></span> in the pile<span class="count-extra"> · no names, ever</span></span>
</header>
```

with:

```html
  <span class="count"><span id="count-n"></span> in the pile<span class="count-extra"> · no names, ever</span></span>
  <form id="paste" class="paste" autocomplete="off" novalidate>
    <div class="paste-field">
      <span id="paste-icon" class="paste-icon"></span>
      <input id="paste-input" type="text" inputmode="url" enterkeyhint="go" autocapitalize="off" autocorrect="off" spellcheck="false" aria-label="paste a link" placeholder="paste a link">
      <button id="paste-submit" class="paste-submit" type="submit" aria-label="add"><span class="paste-submit-icon" data-icon="arrowUp"></span><span class="paste-submit-label">add</span></button>
    </div>
    <p id="paste-url" class="paste-url" hidden></p>
    <p id="paste-error" class="paste-error" role="alert" hidden><span class="paste-error-lead">couldn't grab that one.</span><span id="paste-error-hint" class="paste-error-hint"></span></p>
  </form>
</header>
```

- [ ] **Step 3: Write `reels_api/static/paste.js`**

```js
import { Unauthorized, createJob, getJob } from "./api.js";
import { icon } from "./icons.js";

const POLL_MS = 1500;
const desktop = matchMedia("(min-width: 700px)");

// The grey half of the error message, by the server's error code (spec 6.5).
const HINTS = {
  unsupported_url: "try the share link.",
  private_or_removed: "it's private or gone.",
  login_required: "instagram wants a login for that one.",
  platform_blocked: "got blocked. try again in a bit.",
  too_many_jobs: "too busy right now. try again in a minute.",
  network: "no connection. try again.",
};
const DEFAULT_HINT = "try again.";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Poll until the job settles: the done job, or {error: code}.
async function waitForJob(id) {
  for (;;) {
    try {
      const job = await getJob(id);
      if (job === null) return { error: "processing_failed" };
      if (job.status === "done") return job;
      if (job.status === "failed") return { error: job.error || "processing_failed" };
    } catch (err) {
      if (err instanceof Unauthorized) throw err;
      // network error: keep polling
    }
    await sleep(POLL_MS);
  }
}

// The paste field: idle, fetching and error (spec 6.5). One paste at a time.
export function createPaste({ form, onStart, onDone, onFail, onStateChange }) {
  const input = form.querySelector("#paste-input");
  const submitButton = form.querySelector("#paste-submit");
  const iconSlot = form.querySelector("#paste-icon");
  const urlLine = form.querySelector("#paste-url");
  const errorRow = form.querySelector("#paste-error");
  const hint = form.querySelector("#paste-error-hint");
  let state = "idle";
  let submitted = "";

  function setState(next, code) {
    state = next;
    form.dataset.state = next;
    const fetching = next === "fetching";
    const error = next === "error";
    input.readOnly = fetching;
    submitButton.hidden = fetching;
    submitButton.disabled = error;
    iconSlot.innerHTML = fetching ? '<span class="spinner" aria-hidden="true"></span>' : icon(error ? "circleAlert" : "clipboard");
    if (fetching) input.value = "pulling it down…";
    if (error) input.value = submitted;
    urlLine.textContent = fetching ? submitted : "";
    urlLine.hidden = !fetching;
    hint.textContent = error ? HINTS[code] || DEFAULT_HINT : "";
    errorRow.hidden = !error;
    onStateChange(next);
  }

  async function run(text) {
    submitted = text;
    setState("fetching");
    input.blur(); // drop the phone keyboard
    onStart();
    let result;
    try {
      const created = await createJob(text);
      result = created.error ? created : await waitForJob(created.id);
    } catch (err) {
      if (err instanceof Unauthorized) return; // the page is reloading to the login screen
      result = { error: "network" };
    }
    if (result.error) {
      onFail();
      setState("error", result.error);
      return;
    }
    await onDone(result);
    input.value = "";
    setState("idle");
  }

  function updatePlaceholder() {
    input.placeholder = desktop.matches ? "paste a link, hit enter" : "paste a link";
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = input.value.trim();
    if (state !== "idle" || !text) return;
    run(text);
  });
  input.addEventListener("input", () => {
    if (state === "error") setState("idle"); // keeps what the user typed
  });
  desktop.addEventListener("change", updatePlaceholder);
  updatePlaceholder();
  setState("idle");

  return {
    // Start a paste from outside the form (the Android share target).
    submit(text) {
      const trimmed = text.trim();
      if (state === "fetching" || !trimmed) return;
      input.value = trimmed;
      run(trimmed);
    },
  };
}
```

- [ ] **Step 4: Rewrite `reels_api/static/app.js`**

```js
import { listJobs } from "./api.js";
import { createBoard } from "./board.js";
import { hydrateIcons } from "./icons.js";
import { createPaste } from "./paste.js";

const REFRESH_MS = 30_000;
const $ = (id) => document.getElementById(id);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
hydrateIcons(document);

const board = createBoard({ grid: $("grid"), empty: $("empty"), count: $("count-n") });

const paste = createPaste({
  form: $("paste"),
  onStart: () => board.addPending(),
  onFail: () => board.removePending(),
  onStateChange: (state) => board.setDimmed(state === "error"),
  onDone: async (job) => {
    const existed = board.has(job.id); // one job per URL: the link was already in the pile
    const jobs = (await loadJobs()) || [job, ...board.getReels().filter((reel) => reel.id !== job.id)];
    board.finishPending(jobs);
    if (existed) board.reveal(job.id);
  },
});

// The pile from the server, or null when it could not be loaded.
async function loadJobs() {
  try {
    return await listJobs();
  } catch (_) {
    return null;
  }
}

async function refresh() {
  const jobs = await loadJobs();
  if (jobs) board.setReels(jobs); // on failure keep whatever is on screen
}

// Android share target: /?url=...&text=...&title=... starts a paste (web spec 7.2).
function consumeShareTarget() {
  const params = new URLSearchParams(location.search);
  const parts = ["url", "text", "title"].map((key) => params.get(key)).filter(Boolean);
  if (!parts.length) return false;
  history.replaceState(null, "", location.pathname);
  paste.submit(parts.join(" "));
  return true;
}

setInterval(() => {
  if (document.visibilityState === "visible") refresh();
}, REFRESH_MS);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refresh();
});

async function start() {
  await refresh();
  consumeShareTarget();
}

start();
```

- [ ] **Step 5: Append the paste styles to `reels_api/static/style.css`**

```css

/* ---- paste (spec 6.5) ---- */

.paste {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 10;
  padding: 26px 14px calc(18px + env(safe-area-inset-bottom));
  background: linear-gradient(to top, var(--bg) 55%, rgba(10, 11, 13, 0));
}
body.is-empty .paste { background: none; }
.paste-field {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 50px;
  padding: 0 6px 0 14px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  background: var(--surface);
}
.paste[data-state="idle"] .paste-field:focus-within { border-color: var(--accent); }
.paste-icon { display: flex; color: var(--ink-50); }
.paste-icon .icon, .paste-icon .spinner { width: 17px; height: 17px; }
.paste-field input {
  flex: 1;
  min-width: 0;
  height: 100%;
  padding: 0;
  border: 0;
  outline: none;
  background: transparent;
  font: 400 16px var(--font); /* 16px: iOS zooms into smaller inputs */
  color: var(--ink);
  text-overflow: ellipsis;
}
.paste-field input::placeholder { color: var(--ink-42); opacity: 1; }
.paste-submit {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--accent-ink);
}
.paste-submit .icon { width: 18px; height: 18px; stroke-width: 2.1; }
.paste-submit-label { display: none; }
.paste-submit:disabled { background: rgba(255, 255, 255, 0.08); color: rgba(242, 240, 234, 0.55); }
.paste[data-state="fetching"] input { font-family: var(--mono); color: var(--ink-70); }
.paste[data-state="error"] input { font-family: var(--mono); color: rgba(242, 240, 234, 0.85); }
.paste[data-state="error"] .paste-field { border-color: var(--danger-border); }
.paste[data-state="error"] .paste-icon { color: var(--danger-icon); }
.paste[data-state="error"] .paste-icon .icon { stroke-width: 1.85; }
.paste-url {
  margin-top: 10px;
  padding: 0 6px;
  font: 500 12px var(--mono);
  color: var(--ink-50);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.paste-error {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding: 0 6px;
  font: 400 12.5px var(--font);
}
.paste-error-lead { font-weight: 500; color: var(--danger-text); }
.paste-error-hint { color: rgba(242, 240, 234, 0.55); }

@media (min-width: 700px) {
  .paste {
    position: relative;
    left: auto;
    right: auto;
    bottom: auto;
    z-index: auto;
    width: 380px;
    padding: 0;
    background: none;
  }
  .paste-field { height: 42px; padding: 0 5px 0 14px; border-color: rgba(255, 255, 255, 0.12); }
  .paste-icon .icon, .paste-icon .spinner { width: 16px; height: 16px; }
  .paste-field input { font-size: 14px; }
  .paste-submit { width: auto; height: 32px; padding: 0 14px; font: 700 12.5px var(--font); }
  .paste-submit-icon { display: none; }
  .paste-submit-label { display: inline; }
  .paste-url { display: none; }
  .paste-error {
    position: absolute;
    top: 100%;
    right: 0;
    justify-content: flex-end;
    margin-top: 8px;
    white-space: nowrap;
  }
}
```

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (165 passed, 1 deselected).

- [ ] **Step 7: Check the paste flow in Chrome**

Dev server running (Task 3 Step 5), logged in. Compare with handoff screens 1, 6, 7 and 8. At 390×844 unless stated:

- Idle: the bottom bar sits on the fade to black; pill with clipboard icon, "paste a link" placeholder, accent circle with an up arrow.
- Paste `https://vm.tiktok.com/works1/` and tap the arrow: a spinner tile with "now" (accent) appears first, the count goes 12 → 13, the field shows a spinner and "pulling it down…" in mono, the submit button disappears, and the link shows under the field. After ~3 s the tile becomes a real thumbnail that fades in, and the field is empty again.
- Paste `https://vm.tiktok.com/works1/` again: after the spinner, no new tile appears; the count returns to 13.
- Paste `https://vm.tiktok.com/private1/`: after ~3 s the placeholder tile goes, the count goes back, the grid dims to 40%, the field has a red border, alert icon, the link in mono, a grey disabled arrow, and "couldn't grab that one. it's private or gone." Type one character: dimming, red border and message go away.
- Check the hints: `https://www.instagram.com/reel/login1/` → "instagram wants a login for that one."; `https://vm.tiktok.com/blocked1/` → "got blocked. try again in a bit."; `https://vm.tiktok.com/slow1/` → "try again."; `https://youtube.com/watch?v=1` → "try the share link." at once, with no 3 s wait.
- Stop the dev server, paste anything → "no connection. try again." Start it again.
- 1280×800: the field sits in the top bar (380px, "paste a link, hit enter", "add" pill); Enter submits; the fetching state shows inside the field with no link line; the error message appears right-aligned under the field.
- Open `http://localhost:8000/?text=Look%20https://vm.tiktok.com/share1/` → a paste starts by itself and the address bar becomes `/`.

- [ ] **Step 8: Commit**

```bash
git add reels_api/static/paste.js reels_api/static/app.js reels_api/static/app.html reels_api/static/style.css tests/test_web.py
git commit -m "feat: paste field with optimistic tile, fetching and error states" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Player, links to a reel, and toasts

**Files:**
- Create: `reels_api/static/toast.js`, `reels_api/static/player.js`
- Rewrite: `reels_api/static/app.js`
- Modify: `reels_api/static/app.html` (player and toast markup), `reels_api/static/style.css` (append)
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `formatDuration`, `sourceLine` (`format.js`); `icon` (`icons.js`); `getJob`, `listJobs`, `Unauthorized` (`api.js`); board `getReels`, `remove`, and the `onOpen(id, tile)` option (Task 4); paste (Task 5).
- Produces (`toast.js`): `showToast(message, { error = false } = {})`.
- Produces (`player.js`): `createPlayer({ root, onGone })` → `{ open(list, id, { gesture = true, push = true, from = null } = {}) -> boolean, close({ fromHistory = false } = {}), isOpen() -> boolean, addReels(list) }`. `open` returns false when `id` is not in `list`. `gesture: false` starts muted (a `?reel=` link on load). `push: true` adds a history entry; `false` replaces the current one. `from` is the element to refocus on close. `onGone(id)` is called when the open reel's video fails to load.
- Produces (`app.html`): the player root `#player` with the markup below (class hooks `.js-source`, `.js-caption`, `.js-elapsed`, `.js-duration`, `.scrubber`, `.idle-fill`, `.player-frame`, `.player-close-desktop`, `[data-action]` with actions `close prev next share whatsapp copy save volume`); `#toast`.

Phone swipes and the iPhone Save share sheet come in Task 7. In this task a tap on the phone player simply toggles the chrome, and Save always downloads.

- [ ] **Step 1: Extend the module test**

In `tests/test_web.py`, change the `APP_MODULES` line to:

```python
APP_MODULES = ["app.js", "api.js", "format.js", "icons.js", "board.js", "paste.js", "toast.js", "player.js"]
```

Run: `.venv/Scripts/python -m pytest -q tests/test_web.py`
Expected: FAIL — `/static/toast.js` returns 404.

- [ ] **Step 2: Write `reels_api/static/toast.js`**

```js
import { icon } from "./icons.js";

const VISIBLE_MS = 2500;
let hideTimer = 0;

// One toast at a time; a new one replaces the current one and restarts the timer (spec 8.1).
export function showToast(message, { error = false } = {}) {
  const root = document.getElementById("toast");
  const mark = document.createElement("span");
  mark.className = error ? "toast-mark error" : "toast-mark";
  mark.innerHTML = icon(error ? "circleAlert" : "check");
  const label = document.createElement("span");
  label.textContent = message;
  root.replaceChildren(mark, label);
  root.classList.add("show");
  clearTimeout(hideTimer);
  hideTimer = setTimeout(() => root.classList.remove("show"), VISIBLE_MS);
}
```

- [ ] **Step 3: Write `reels_api/static/player.js`**

```js
import { formatDuration, sourceLine } from "./format.js";
import { icon } from "./icons.js";
import { showToast } from "./toast.js";

const desktopQuery = matchMedia("(min-width: 700px)");

function reelPath(id) {
  return `/?reel=${encodeURIComponent(id)}`;
}

// The link that Share and Copy link hand out (spec 4).
function reelLink(id) {
  return location.origin + reelPath(id);
}

// Full-bleed with tap-to-reveal chrome below 700px, a centred overlay from 700px (spec 7).
export function createPlayer({ root, onGone }) {
  const video = root.querySelector("video");
  const frame = root.querySelector(".player-frame");
  const idleFill = root.querySelector(".idle-fill");
  const scrubbers = [...root.querySelectorAll(".scrubber")];
  const volumeButtons = [...root.querySelectorAll('[data-action="volume"]')];
  const prevButton = root.querySelector('[data-action="prev"]');
  const nextButton = root.querySelector('[data-action="next"]');
  const desktopClose = root.querySelector(".player-close-desktop");

  let reels = []; // snapshot of the board's order, taken on open
  let index = -1;
  let pushed = false; // open() added a history entry that close() must pop
  let opener = null;
  let muted = false; // the viewer's choice carries from reel to reel
  let frameRequest = 0;

  const current = () => reels[index];
  const isOpen = () => !root.hidden;

  function setText(selector, text) {
    for (const el of root.querySelectorAll(selector)) el.textContent = text;
  }

  function setChrome(visible) {
    root.classList.toggle("chrome-on", visible);
  }

  function renderVolume() {
    for (const button of volumeButtons) {
      button.innerHTML = icon(muted ? "volumeX" : "volume2");
      button.setAttribute("aria-label", muted ? "unmute" : "mute");
    }
  }

  function renderNav() {
    prevButton.disabled = index <= 0;
    nextButton.disabled = index >= reels.length - 1;
  }

  function renderProgress() {
    const reel = current();
    const duration = Number.isFinite(video.duration) ? video.duration : (reel && reel.duration_seconds) || 0;
    const time = video.currentTime || 0;
    const percent = duration > 0 ? Math.min(100, (time / duration) * 100) : 0;
    for (const range of scrubbers) {
      range.max = String(duration || 1);
      range.value = String(time);
      range.style.setProperty("--progress", `${percent}%`);
    }
    idleFill.style.width = `${percent}%`;
    setText(".js-elapsed", formatDuration(time) || "0:00");
    setText(".js-duration", formatDuration(duration) || "0:00");
  }

  // Redraw the progress every frame while open, so the 3px bar moves smoothly.
  function tick() {
    renderProgress();
    frameRequest = requestAnimationFrame(tick);
  }

  function play() {
    video.muted = muted;
    const attempt = video.play();
    if (!attempt) return;
    attempt.catch((err) => {
      if (err.name !== "NotAllowedError" || video.muted) return;
      // No sound allowed without a fresh tap: play muted and show it.
      muted = true;
      renderVolume();
      video.muted = true;
      video.play().catch(() => {});
    });
  }

  function show(i) {
    index = i;
    const reel = current();
    video.pause();
    if (reel.thumbnail_url) video.poster = reel.thumbnail_url;
    else video.removeAttribute("poster");
    video.src = reel.file_url;
    setText(".js-source", sourceLine(reel));
    setText(".js-caption", reel.caption || reel.title || "");
    renderNav();
    renderProgress();
  }

  function open(list, id, { gesture = true, push = true, from = null } = {}) {
    const i = list.findIndex((reel) => reel.id === id);
    if (i === -1) return false;
    reels = list.slice();
    opener = from;
    if (!gesture) muted = true;
    root.hidden = false;
    document.body.classList.add("player-open");
    setChrome(false);
    renderVolume();
    show(i);
    play();
    if (push) history.pushState({ reel: id }, "", reelPath(id));
    else history.replaceState({ reel: id }, "", reelPath(id));
    pushed = push;
    cancelAnimationFrame(frameRequest);
    tick();
    if (desktopQuery.matches) desktopClose.focus();
    return true;
  }

  function move(step) {
    const next = index + step;
    if (!isOpen() || next < 0 || next >= reels.length) return false;
    show(next);
    play();
    history.replaceState({ reel: current().id }, "", reelPath(current().id));
    return true;
  }

  function close({ fromHistory = false } = {}) {
    if (!isOpen()) return;
    cancelAnimationFrame(frameRequest);
    root.hidden = true;
    document.body.classList.remove("player-open");
    video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    video.load(); // release the stream
    if (!fromHistory) {
      if (pushed) history.back();
      else history.replaceState(null, "", location.pathname);
    }
    pushed = false;
    if (opener && opener.isConnected) opener.focus({ preventScroll: true });
    opener = null;
  }

  // A refresh while open: new reels join the front; nothing is removed or reordered (spec 7.1).
  function addReels(list) {
    if (!isOpen()) return;
    const known = new Set(reels.map((reel) => reel.id));
    const fresh = list.filter((reel) => !known.has(reel.id));
    if (!fresh.length) return;
    reels = [...fresh, ...reels];
    index += fresh.length;
    renderNav();
  }

  // ---- actions (spec 7.4)

  function openWhatsApp(url) {
    window.open(`https://wa.me/?text=${encodeURIComponent(url)}`, "_blank", "noopener");
  }

  function share() {
    const url = reelLink(current().id);
    if (typeof navigator.share !== "function") {
      openWhatsApp(url);
      return;
    }
    navigator.share({ url }).catch((err) => {
      if (err && err.name === "AbortError") return; // the viewer closed the sheet
      openWhatsApp(url);
    });
  }

  async function copyLink() {
    setChrome(false);
    try {
      await navigator.clipboard.writeText(reelLink(current().id));
      showToast("link copied");
    } catch (_) {
      showToast("couldn't copy the link", { error: true });
    }
  }

  function download() {
    const link = document.createElement("a");
    link.href = current().file_url; // the server sends Content-Disposition: attachment
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
    setChrome(false);
    showToast("saved to your downloads");
  }

  function save() {
    download();
  }

  function togglePlay() {
    if (video.paused) play();
    else video.pause();
  }

  function toggleMute() {
    muted = !muted;
    video.muted = muted;
    renderVolume();
  }

  const actions = {
    close: () => close(),
    prev: () => move(-1),
    next: () => move(1),
    share,
    whatsapp: () => openWhatsApp(reelLink(current().id)),
    copy: copyLink,
    save,
    volume: toggleMute,
  };

  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button || !root.contains(button)) return;
    if (button.getAttribute("aria-disabled") === "true") return;
    actions[button.dataset.action]();
  });

  // Tap on the video: chrome in/out on phones, play/pause on desktop.
  function onFrameClick(event) {
    if (event.target.closest("button, input")) return;
    if (desktopQuery.matches) togglePlay();
    else setChrome(!root.classList.contains("chrome-on"));
  }
  frame.addEventListener("click", onFrameClick);

  for (const range of scrubbers) {
    range.addEventListener("input", () => {
      video.currentTime = Number(range.value);
      renderProgress();
    });
  }

  video.addEventListener("error", () => {
    if (!isOpen()) return;
    const gone = current();
    close();
    onGone(gone.id);
    showToast("that one's gone", { error: true });
  });

  function trapFocus(event) {
    const focusable = [...root.querySelectorAll("button, input")].filter(
      (el) => !el.disabled && el.getClientRects().length > 0,
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!root.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  document.addEventListener("keydown", (event) => {
    if (!isOpen()) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (!desktopQuery.matches) return;
    if (event.key === "Tab") {
      trapFocus(event);
      return;
    }
    if (event.target instanceof HTMLInputElement) return; // arrows seek inside the scrubber
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1);
    }
  });

  // Crossing 700px while open: CSS switches the layout; reset what only one layout uses.
  desktopQuery.addEventListener("change", () => {
    if (!isOpen()) return;
    frame.style.transform = "";
    setChrome(false);
  });

  return { open, close, isOpen, addReels };
}
```

- [ ] **Step 4: Rewrite `reels_api/static/app.js`**

```js
import { Unauthorized, getJob, listJobs } from "./api.js";
import { createBoard } from "./board.js";
import { hydrateIcons } from "./icons.js";
import { createPaste } from "./paste.js";
import { createPlayer } from "./player.js";
import { showToast } from "./toast.js";

const REFRESH_MS = 30_000;
const $ = (id) => document.getElementById(id);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}
hydrateIcons(document);

const board = createBoard({
  grid: $("grid"),
  empty: $("empty"),
  count: $("count-n"),
  onOpen: (id, tile) => player.open(board.getReels(), id, { from: tile }),
});

const player = createPlayer({
  root: $("player"),
  onGone: (id) => board.remove(id),
});

const paste = createPaste({
  form: $("paste"),
  onStart: () => board.addPending(),
  onFail: () => board.removePending(),
  onStateChange: (state) => board.setDimmed(state === "error"),
  onDone: async (job) => {
    const existed = board.has(job.id); // one job per URL: the link was already in the pile
    const jobs = (await loadJobs()) || [job, ...board.getReels().filter((reel) => reel.id !== job.id)];
    board.finishPending(jobs);
    player.addReels(jobs);
    if (existed) board.reveal(job.id);
  },
});

// The pile from the server, or null when it could not be loaded.
async function loadJobs() {
  try {
    return await listJobs();
  } catch (_) {
    return null;
  }
}

async function refresh() {
  const jobs = await loadJobs();
  if (!jobs) return; // keep whatever is on screen
  board.setReels(jobs);
  player.addReels(jobs);
}

function reelInUrl() {
  return new URLSearchParams(location.search).get("reel");
}

// A ?reel= link: open that reel muted, or say it is gone (spec 4).
async function openLinkedReel(id) {
  if (player.open(board.getReels(), id, { gesture: false, push: false })) return;
  let job = null;
  try {
    job = await getJob(id);
  } catch (err) {
    if (err instanceof Unauthorized) return;
  }
  if (job && job.status === "done" && player.open([job], id, { gesture: false, push: false })) return;
  history.replaceState(null, "", location.pathname);
  showToast("that one's gone", { error: true });
}

// Android share target: /?url=...&text=...&title=... starts a paste (web spec 7.2).
function consumeShareTarget() {
  const params = new URLSearchParams(location.search);
  const parts = ["url", "text", "title"].map((key) => params.get(key)).filter(Boolean);
  if (!parts.length) return false;
  history.replaceState(null, "", location.pathname);
  paste.submit(parts.join(" "));
  return true;
}

// Back closes the player; Forward to a reel opens it again.
window.addEventListener("popstate", () => {
  const id = reelInUrl();
  if (!id) player.close({ fromHistory: true });
  else if (!player.isOpen()) openLinkedReel(id);
});

setInterval(() => {
  if (document.visibilityState === "visible") refresh();
}, REFRESH_MS);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refresh();
});

async function start() {
  await refresh();
  if (consumeShareTarget()) return;
  const id = reelInUrl();
  if (id) openLinkedReel(id);
}

start();
```

- [ ] **Step 5: Add the player and toast to `reels_api/static/app.html`**

Replace:

```html
</main>
</body>
```

with:

```html
</main>

<div id="player" class="player" hidden>
  <div class="player-backdrop"></div>
  <button class="player-close-desktop" type="button" data-action="close" aria-label="close" data-icon="x"></button>
  <div class="player-row">
    <div class="player-inner">
      <button class="player-nav" type="button" data-action="prev" aria-label="previous reel" data-icon="chevronLeft"></button>
      <div class="player-stage">
        <div class="player-frame">
          <video playsinline loop preload="auto"></video>
          <div class="idle-bar">
            <div class="idle-track"><div class="idle-fill"></div></div>
            <p class="idle-hint"><span data-icon="arrowUp"></span>swipe for the next one · tap for options</p>
          </div>
          <div class="chrome">
            <div class="chrome-top">
              <button class="round-btn" type="button" data-action="close" aria-label="close" data-icon="x"></button>
              <span class="source"><span data-icon="clock"></span><span class="js-source"></span></span>
              <span class="chrome-spacer"></span>
            </div>
            <div class="chrome-bottom">
              <p class="caption js-caption"></p>
              <div class="controls">
                <span class="time js-elapsed">0:00</span>
                <input class="scrubber" type="range" min="0" max="1" step="0.1" value="0" aria-label="seek">
                <span class="time total js-duration">0:00</span>
                <button class="volume" type="button" data-action="volume" aria-label="mute"></button>
              </div>
              <div class="actions">
                <button class="btn btn-primary share" type="button" data-action="share"><span data-icon="whatsapp"></span>Share</button>
                <button class="btn save" type="button" data-action="save"><span data-icon="download"></span><span class="spinner" aria-hidden="true"></span>Save</button>
                <button class="btn copy" type="button" data-action="copy" aria-label="copy link"><span data-icon="link2"></span></button>
              </div>
            </div>
          </div>
        </div>
        <div class="controls desk-controls">
          <span class="time js-elapsed">0:00</span>
          <input class="scrubber" type="range" min="0" max="1" step="0.1" value="0" aria-label="seek">
          <span class="time total js-duration">0:00</span>
          <button class="volume" type="button" data-action="volume" aria-label="mute"></button>
        </div>
      </div>
      <aside class="player-panel">
        <span class="source"><span data-icon="clock"></span><span class="js-source"></span></span>
        <p class="caption js-caption"></p>
        <div class="panel-actions">
          <button class="btn btn-primary" type="button" data-action="whatsapp"><span data-icon="whatsapp"></span>Share to WhatsApp</button>
          <div class="panel-row">
            <button class="btn save" type="button" data-action="save"><span data-icon="download"></span><span class="spinner" aria-hidden="true"></span>Download</button>
            <button class="btn" type="button" data-action="copy"><span data-icon="link2"></span>Copy link</button>
          </div>
        </div>
        <p class="panel-hint">← → to move through the pile · esc to close</p>
      </aside>
      <button class="player-nav" type="button" data-action="next" aria-label="next reel" data-icon="chevronRight"></button>
    </div>
  </div>
</div>

<div id="toast" class="toast" role="status" aria-live="polite"></div>
</body>
```

- [ ] **Step 6: Append the player, button and toast styles to `reels_api/static/style.css`**

```css

/* ---- buttons (player and login) ---- */

.btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 48px;
  padding: 0 18px;
  border-radius: 999px;
  border: 1px solid var(--hairline-strong);
  background: rgba(255, 255, 255, 0.06);
  font: 600 14.5px var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.btn .icon { width: 17px; height: 17px; stroke-width: 1.85; }
.btn-primary { border-color: transparent; background: var(--accent); color: var(--accent-ink); font-weight: 700; }
.btn-primary .icon { width: 18px; height: 18px; }
.btn .spinner { display: none; width: 17px; height: 17px; }
.btn.is-loading .spinner { display: block; }
.btn.is-loading span[data-icon] { display: none; }

/* ---- toast (spec 8.1) ---- */

.toast {
  position: fixed;
  left: 16px;
  right: 16px;
  bottom: calc(88px + env(safe-area-inset-bottom));
  z-index: 40;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 16px;
  border-radius: 14px;
  border: 1px solid var(--hairline-strong);
  background: rgba(20, 22, 26, 0.94);
  font: 600 13.5px var(--font);
  color: var(--ink);
  opacity: 0;
  visibility: hidden;
  transform: translateY(4px);
  pointer-events: none;
  transition: opacity 160ms ease-out, transform 160ms ease-out, visibility 0s linear 160ms;
}
.toast.show { opacity: 1; visibility: visible; transform: none; transition-delay: 0s; }
.toast-mark {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 999px;
  background: var(--accent);
  color: var(--accent-ink);
}
.toast-mark .icon { width: 14px; height: 14px; stroke-width: 2.6; }
.toast-mark.error { background: none; color: var(--danger-icon); }
.toast-mark.error .icon { width: 22px; height: 22px; stroke-width: 1.85; }

/* ---- player, phone (spec 7.2) ---- */

body.player-open { overflow: hidden; }
.player { position: fixed; inset: 0; z-index: 30; overflow: hidden; background: #000; }
.player-backdrop, .player-close-desktop, .player-nav, .player-panel, .desk-controls { display: none; }
.player-row, .player-inner, .player-stage { position: absolute; inset: 0; }
.player-frame {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: #000;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
}
.player-frame video { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; background: #000; }

.idle-bar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  padding: 40px 18px calc(20px + env(safe-area-inset-bottom));
  background: linear-gradient(to top, rgba(0, 0, 0, 0.55), rgba(0, 0, 0, 0));
  pointer-events: none;
  transition: opacity 160ms ease-out;
}
.idle-track { height: 3px; overflow: hidden; border-radius: 2px; background: rgba(255, 255, 255, 0.2); }
.idle-fill { width: 0; height: 100%; background: var(--accent); }
.idle-hint {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 14px;
  font: 500 10.5px var(--mono);
  color: var(--ink);
}
.idle-hint .icon { width: 12px; height: 12px; stroke-width: 2; }
.player.chrome-on .idle-bar { opacity: 0; }

.chrome {
  position: absolute;
  inset: 0;
  background: linear-gradient(to bottom, rgba(0, 0, 0, 0.55) 0 18%, rgba(0, 0, 0, 0.15) 40%, rgba(0, 0, 0, 0.82) 78%);
  opacity: 0;
  visibility: hidden;
  transform: translateY(4px);
  transition: opacity 160ms ease-out, transform 160ms ease-out, visibility 0s linear 160ms;
}
.player.chrome-on .chrome { opacity: 1; visibility: visible; transform: none; transition-delay: 0s; }
.chrome-top {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: calc(16px + env(safe-area-inset-top)) 16px 0;
}
.round-btn {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.4);
  color: var(--ink);
}
.round-btn .icon { width: 16px; height: 16px; stroke-width: 2; }
.chrome-spacer { flex: none; width: 34px; }
.source {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  font: 500 11px var(--mono);
  color: var(--ink);
  white-space: nowrap;
}
.source .icon { width: 12px; height: 12px; stroke-width: 1.9; }
.chrome-bottom { position: absolute; left: 0; right: 0; bottom: 0; padding: 0 16px calc(18px + env(safe-area-inset-bottom)); }
.caption {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  font: 400 13.5px/1.42 var(--font);
  color: var(--ink);
  overflow-wrap: anywhere;
}
.controls { display: flex; align-items: center; gap: 10px; margin: 16px 0 14px; }
.time { flex: none; font: 500 10.5px var(--mono); color: var(--ink); font-variant-numeric: tabular-nums; }
.time.total { color: var(--ink-70); }
.volume { display: flex; flex: none; align-items: center; justify-content: center; width: 28px; height: 28px; color: var(--ink); }
.volume .icon { width: 17px; height: 17px; stroke-width: 1.8; }
.scrubber {
  --progress: 0%;
  flex: 1;
  min-width: 0;
  height: 44px; /* hit area; the visible track is 3px */
  margin: -20px 0;
  background: transparent;
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
}
.scrubber::-webkit-slider-runnable-track {
  height: 3px;
  border-radius: 2px;
  background: linear-gradient(to right, var(--accent) var(--progress), rgba(255, 255, 255, 0.22) var(--progress));
}
.scrubber::-webkit-slider-thumb {
  width: 11px;
  height: 11px;
  margin-top: -4px;
  border-radius: 999px;
  background: var(--ink);
  opacity: 0;
  -webkit-appearance: none;
}
.scrubber:active::-webkit-slider-thumb, .scrubber:focus-visible::-webkit-slider-thumb { opacity: 1; }
.scrubber::-moz-range-track { height: 3px; border-radius: 2px; background: rgba(255, 255, 255, 0.22); }
.scrubber::-moz-range-progress { height: 3px; border-radius: 2px; background: var(--accent); }
.scrubber::-moz-range-thumb { width: 11px; height: 11px; border: 0; border-radius: 999px; background: var(--ink); opacity: 0; }
.actions { display: flex; gap: 10px; }
.actions .share { flex: 1.4 1 0; }
.actions .save { flex: 1 1 0; }
.actions .copy { flex: none; width: 48px; padding: 0; }

/* ---- player, desktop overlay (spec 7.3) ---- */

@media (min-width: 700px) {
  .player { --frame-h: min(520px, 74vh); background: transparent; }
  body.player-open .topbar, body.player-open .board { opacity: 0.28; }
  .player-backdrop { display: block; position: absolute; inset: 0; background: var(--scrim-overlay); }
  .idle-bar, .chrome { display: none; }
  .player-close-desktop {
    position: absolute;
    top: 18px;
    right: 22px;
    z-index: 2;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.1);
  }
  .player-close-desktop .icon { width: 17px; height: 17px; stroke-width: 2; }
  .player-row { display: flex; align-items: center; justify-content: center; padding: 34px 40px; }
  .player-inner { position: relative; inset: auto; display: flex; align-items: flex-start; gap: 28px; }
  .player-stage { position: relative; inset: auto; display: flex; flex-direction: column; gap: 12px; }
  .player-frame {
    position: relative;
    inset: auto;
    width: calc(var(--frame-h) * 9 / 16);
    height: var(--frame-h);
    border-radius: 14px;
    background: var(--tile);
    touch-action: auto;
    cursor: pointer;
  }
  .player-frame video { background: var(--tile); }
  .desk-controls { display: flex; gap: 12px; margin: 0; }
  .desk-controls .time { font-size: 11px; }
  .player-nav {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    margin-top: calc((var(--frame-h) - 40px) / 2);
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    background: rgba(255, 255, 255, 0.08);
  }
  .player-nav .icon { width: 18px; height: 18px; stroke-width: 2; }
  .player-nav:disabled { opacity: 0.35; }
  .player-panel { display: flex; flex: 0 1 300px; flex-direction: column; gap: 18px; min-width: 220px; }
  .player-panel .source { gap: 8px; font-size: 11.5px; color: rgba(242, 240, 234, 0.75); }
  .player-panel .source .icon { width: 13px; height: 13px; }
  .player-panel .caption { font-size: 15px; line-height: 1.45; -webkit-line-clamp: 8; }
  .panel-actions { display: flex; flex-direction: column; gap: 9px; }
  .panel-actions > .btn-primary { height: 46px; gap: 9px; }
  .panel-row { display: flex; gap: 9px; }
  .panel-row .btn {
    flex: 1 1 0;
    height: 44px;
    padding: 0 12px;
    gap: 7px;
    border-color: rgba(255, 255, 255, 0.2);
    font-size: 13.5px;
  }
  .panel-row .btn .icon, .panel-row .btn .spinner { width: 16px; height: 16px; }
  .panel-hint { font: 500 11px var(--mono); color: var(--ink-50); }
  .toast { left: 50%; right: auto; bottom: 32px; width: max-content; max-width: 360px; transform: translate(-50%, 4px); }
  .toast.show { transform: translate(-50%, 0); }
}

@media (min-width: 700px) and (max-width: 899px) {
  .player-nav { display: none; }
}
```

- [ ] **Step 7: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (165 passed, 1 deselected).

- [ ] **Step 8: Check the player in Chrome**

Dev server running (Task 3 Step 5), logged in. Compare with handoff screens 2, 3, 4 and 9.

At 1280×800:
- Click the third tile: the overlay opens with the board faded behind a dark wash; the 9:16 frame (520px tall) plays with sound, the control row sits under it, the side panel shows the source line "Instagram · 0:22 · gone in 6h", the long caption, **Share to WhatsApp**, **Download** / **Copy link** and the keyboard hint; the round close button is top-right; prev/next buttons sit level with the middle of the frame. The address bar shows `/?reel=seed02`.
- → and ← move through the pile (URL follows, no new history entries); prev is disabled on the first reel and next on the last. Esc closes, focus returns to the tile, the address bar is `/`. Open again, press the browser Back button: it closes.
- Drag the scrubber: the video seeks and the elapsed time follows. Click the speaker: muted icon; the next reel stays muted.
- Click the video: pause; again: play. Tab cycles only through the overlay's buttons and scrubber.
- **Copy link** → toast "link copied" (bottom centre); the clipboard holds `http://localhost:8000/?reel=seed02`. **Download** → the MP4 downloads and the toast reads "saved to your downloads". **Share to WhatsApp** opens `https://wa.me/?text=http%3A%2F%2Flocalhost%3A8000%2F%3Freel%3Dseed02` in a new tab (close it).
- At 800×800: prev/next buttons are hidden, ←/→ still work. At 1280×600: the frame shrinks (74vh) and stays fully visible.
- Open `http://localhost:8000/?reel=seed04` in a new tab: the player opens muted on that reel. Close → `/`. Open `http://localhost:8000/?reel=nope`: the board shows with the toast "that one's gone" and the address bar is `/`.

At 390×844 (device mode, touch):
- Tap a tile: full-screen video, 3px progress bar and "swipe for the next one · tap for options" at the bottom.
- Tap the video: chrome fades in (close button, centred source line, two-line caption with "…" on `seed02`, scrubber row, **Share** / **Save** / link button). Tap again: it hides.
- With the chrome shown, stub `navigator.share` (Global Constraints) and tap **Share**: the console logs `share {url: "http://localhost:8000/?reel=…"}`. Tap the link button: chrome hides and the toast "link copied" shows 88px above the bottom. **Save**: download + "saved to your downloads".
- ✕ closes and the board is at the same scroll position as before (scroll down first to check).

- [ ] **Step 9: Commit**

```bash
git add reels_api/static/toast.js reels_api/static/player.js reels_api/static/app.js reels_api/static/app.html reels_api/static/style.css tests/test_web.py
git commit -m "feat: player overlay and full-screen player with share, save and reel links" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Phone swipes and the iPhone Save share sheet

**Files:**
- Rewrite: `reels_api/static/player.js`

**Interfaces:**
- Consumes: everything `player.js` used in Task 6, plus `api` (`api.js`) and `slugify` (`format.js`).
- Produces: the same `createPlayer` interface as Task 6 (`open`, `close`, `isOpen`, `addReels`); no caller changes.

What changes compared with Task 6's `player.js` (spec 7.2 and 7.4):
- Below 700px, pointer handlers on `.player-frame` replace the click toggle: a movement under 10px is a tap (toggle chrome); a vertical drag moves the frame with the finger; release past 20% of the viewport height or faster than 0.5 px/ms slides to the next reel (drag up) or previous (drag down) over 200ms; otherwise it springs back over 160ms; past either end the frame follows at one third and always springs back. From 700px, a click on the video still toggles play/pause.
- On iPhone/iPad (user agent, or `MacIntel` with touch) where the zero-byte `canShare` probe passes: each reel's MP4 is fetched when it becomes current (aborted on move/close); Save shows a spinner and does nothing until it is ready, then opens the share sheet with the file and no toast. If the fetch fails or `canShare` rejects the real file, Save downloads as before. Everywhere else Save downloads, as in Task 6.

- [ ] **Step 1: Replace `reels_api/static/player.js`**

```js
import { api } from "./api.js";
import { formatDuration, slugify, sourceLine } from "./format.js";
import { icon } from "./icons.js";
import { showToast } from "./toast.js";

const desktopQuery = matchMedia("(min-width: 700px)");

// Phone gestures (spec 7.2).
const TAP_SLOP_PX = 10;
const SWIPE_FRACTION = 0.2;
const FLICK_PX_PER_MS = 0.5;
const SLIDE_MS = 200;
const SPRING_MS = 160;

// A web download on iPhone lands in Files, never Photos; the share sheet's "Save Video" does (spec 7.4).
const isIOS =
  /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
// Decided once, before any file exists (web spec 7.4).
const canShareFiles =
  typeof navigator.canShare === "function" &&
  navigator.canShare({ files: [new File([""], "probe.mp4", { type: "video/mp4" })] });
const saveWithShareSheet = isIOS && canShareFiles;

function reelPath(id) {
  return `/?reel=${encodeURIComponent(id)}`;
}

// The link that Share and Copy link hand out (spec 4).
function reelLink(id) {
  return location.origin + reelPath(id);
}

// Full-bleed with tap-to-reveal chrome below 700px, a centred overlay from 700px (spec 7).
export function createPlayer({ root, onGone }) {
  const video = root.querySelector("video");
  const frame = root.querySelector(".player-frame");
  const idleFill = root.querySelector(".idle-fill");
  const scrubbers = [...root.querySelectorAll(".scrubber")];
  const volumeButtons = [...root.querySelectorAll('[data-action="volume"]')];
  const saveButtons = [...root.querySelectorAll('[data-action="save"]')];
  const prevButton = root.querySelector('[data-action="prev"]');
  const nextButton = root.querySelector('[data-action="next"]');
  const desktopClose = root.querySelector(".player-close-desktop");

  let reels = []; // snapshot of the board's order, taken on open
  let index = -1;
  let pushed = false; // open() added a history entry that close() must pop
  let opener = null;
  let muted = false; // the viewer's choice carries from reel to reel
  let frameRequest = 0;
  let drag = null; // {id, x, y, time, dy} while a finger is down on the frame
  let sliding = false;
  let prefetch = null; // {id, controller, state: "loading" | "ready" | "failed", file}

  const current = () => reels[index];
  const isOpen = () => !root.hidden;

  function setText(selector, text) {
    for (const el of root.querySelectorAll(selector)) el.textContent = text;
  }

  function setChrome(visible) {
    root.classList.toggle("chrome-on", visible);
  }

  function renderVolume() {
    for (const button of volumeButtons) {
      button.innerHTML = icon(muted ? "volumeX" : "volume2");
      button.setAttribute("aria-label", muted ? "unmute" : "mute");
    }
  }

  function renderNav() {
    prevButton.disabled = index <= 0;
    nextButton.disabled = index >= reels.length - 1;
  }

  function renderProgress() {
    const reel = current();
    const duration = Number.isFinite(video.duration) ? video.duration : (reel && reel.duration_seconds) || 0;
    const time = video.currentTime || 0;
    const percent = duration > 0 ? Math.min(100, (time / duration) * 100) : 0;
    for (const range of scrubbers) {
      range.max = String(duration || 1);
      range.value = String(time);
      range.style.setProperty("--progress", `${percent}%`);
    }
    idleFill.style.width = `${percent}%`;
    setText(".js-elapsed", formatDuration(time) || "0:00");
    setText(".js-duration", formatDuration(duration) || "0:00");
  }

  // Redraw the progress every frame while open, so the 3px bar moves smoothly.
  function tick() {
    renderProgress();
    frameRequest = requestAnimationFrame(tick);
  }

  function renderSave() {
    const loading = Boolean(prefetch && prefetch.state === "loading");
    for (const button of saveButtons) {
      button.classList.toggle("is-loading", loading);
      button.setAttribute("aria-disabled", String(loading));
    }
  }

  function abortPrefetch() {
    if (prefetch) prefetch.controller.abort();
    prefetch = null;
    renderSave();
  }

  // iPhone only: fetch the file while the reel plays, so Save can open the share sheet on the tap itself.
  async function startPrefetch(reel) {
    const entry = { id: reel.id, controller: new AbortController(), state: "loading", file: null };
    prefetch = entry;
    renderSave();
    try {
      const response = await api(reel.file_url, { signal: entry.controller.signal });
      if (!response.ok) throw new Error(`fetch failed: ${response.status}`);
      const blob = await response.blob();
      const file = new File([blob], `${slugify(reel.title)}.mp4`, { type: "video/mp4" });
      entry.file = file;
      entry.state = navigator.canShare({ files: [file] }) ? "ready" : "failed";
    } catch (_) {
      entry.state = "failed"; // aborted, network error or 404: Save falls back to a download
    }
    if (prefetch === entry) renderSave();
  }

  function play() {
    video.muted = muted;
    const attempt = video.play();
    if (!attempt) return;
    attempt.catch((err) => {
      if (err.name !== "NotAllowedError" || video.muted) return;
      // No sound allowed without a fresh tap: play muted and show it.
      muted = true;
      renderVolume();
      video.muted = true;
      video.play().catch(() => {});
    });
  }

  function show(i) {
    abortPrefetch();
    index = i;
    const reel = current();
    video.pause();
    if (reel.thumbnail_url) video.poster = reel.thumbnail_url;
    else video.removeAttribute("poster");
    video.src = reel.file_url;
    setText(".js-source", sourceLine(reel));
    setText(".js-caption", reel.caption || reel.title || "");
    renderNav();
    renderProgress();
    if (saveWithShareSheet) startPrefetch(reel);
  }

  function open(list, id, { gesture = true, push = true, from = null } = {}) {
    const i = list.findIndex((reel) => reel.id === id);
    if (i === -1) return false;
    reels = list.slice();
    opener = from;
    if (!gesture) muted = true;
    root.hidden = false;
    document.body.classList.add("player-open");
    setChrome(false);
    setFrame(0, 0);
    renderVolume();
    show(i);
    play();
    if (push) history.pushState({ reel: id }, "", reelPath(id));
    else history.replaceState({ reel: id }, "", reelPath(id));
    pushed = push;
    cancelAnimationFrame(frameRequest);
    tick();
    if (desktopQuery.matches) desktopClose.focus();
    return true;
  }

  function move(step) {
    const next = index + step;
    if (!isOpen() || next < 0 || next >= reels.length) return false;
    show(next);
    play();
    history.replaceState({ reel: current().id }, "", reelPath(current().id));
    return true;
  }

  function close({ fromHistory = false } = {}) {
    if (!isOpen()) return;
    cancelAnimationFrame(frameRequest);
    abortPrefetch();
    drag = null;
    root.hidden = true;
    document.body.classList.remove("player-open");
    video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    video.load(); // release the stream
    if (!fromHistory) {
      if (pushed) history.back();
      else history.replaceState(null, "", location.pathname);
    }
    pushed = false;
    if (opener && opener.isConnected) opener.focus({ preventScroll: true });
    opener = null;
  }

  // A refresh while open: new reels join the front; nothing is removed or reordered (spec 7.1).
  function addReels(list) {
    if (!isOpen()) return;
    const known = new Set(reels.map((reel) => reel.id));
    const fresh = list.filter((reel) => !known.has(reel.id));
    if (!fresh.length) return;
    reels = [...fresh, ...reels];
    index += fresh.length;
    renderNav();
  }

  // ---- actions (spec 7.4)

  function openWhatsApp(url) {
    window.open(`https://wa.me/?text=${encodeURIComponent(url)}`, "_blank", "noopener");
  }

  function share() {
    const url = reelLink(current().id);
    if (typeof navigator.share !== "function") {
      openWhatsApp(url);
      return;
    }
    navigator.share({ url }).catch((err) => {
      if (err && err.name === "AbortError") return; // the viewer closed the sheet
      openWhatsApp(url);
    });
  }

  async function copyLink() {
    setChrome(false);
    try {
      await navigator.clipboard.writeText(reelLink(current().id));
      showToast("link copied");
    } catch (_) {
      showToast("couldn't copy the link", { error: true });
    }
  }

  function download() {
    const link = document.createElement("a");
    link.href = current().file_url; // the server sends Content-Disposition: attachment
    link.download = "";
    document.body.append(link);
    link.click();
    link.remove();
    setChrome(false);
    showToast("saved to your downloads");
  }

  function save() {
    const entry = prefetch && prefetch.id === current().id ? prefetch : null;
    if (entry && entry.state === "loading") return;
    if (entry && entry.state === "ready") {
      // No await before share(): iOS only opens the sheet inside the tap itself.
      navigator.share({ files: [entry.file] }).catch((err) => {
        if (err && err.name === "AbortError") return;
        showToast("couldn't save that one", { error: true });
      });
      return; // no toast: the sheet's choice is unknown
    }
    download();
  }

  function togglePlay() {
    if (video.paused) play();
    else video.pause();
  }

  function toggleMute() {
    muted = !muted;
    video.muted = muted;
    renderVolume();
  }

  const actions = {
    close: () => close(),
    prev: () => move(-1),
    next: () => move(1),
    share,
    whatsapp: () => openWhatsApp(reelLink(current().id)),
    copy: copyLink,
    save,
    volume: toggleMute,
  };

  root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button || !root.contains(button)) return;
    if (button.getAttribute("aria-disabled") === "true") return;
    actions[button.dataset.action]();
  });

  // ---- desktop: click on the video plays and pauses

  frame.addEventListener("click", (event) => {
    if (!desktopQuery.matches || event.target.closest("button, input")) return;
    togglePlay();
  });

  // ---- phone: tap toggles the chrome, vertical swipes move through the pile (spec 7.2)

  function setFrame(offset, ms) {
    frame.style.transition = ms ? `transform ${ms}ms ease-out` : "none";
    frame.style.transform = offset ? `translateY(${offset}px)` : "";
  }

  // Slide the current reel out, swap in the next one, slide it in from the other side.
  function slide(step) {
    const height = frame.offsetHeight;
    sliding = true;
    setFrame(-step * height, SLIDE_MS);
    setTimeout(() => {
      if (!isOpen()) {
        sliding = false;
        return;
      }
      move(step);
      setFrame(step * height, 0);
      frame.getBoundingClientRect(); // commit the start position before animating from it
      setFrame(0, SLIDE_MS);
      setTimeout(() => {
        sliding = false;
      }, SLIDE_MS);
    }, SLIDE_MS);
  }

  frame.addEventListener("pointerdown", (event) => {
    if (desktopQuery.matches || sliding || drag || event.target.closest("button, input")) return;
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, time: performance.now(), dy: 0 };
    frame.setPointerCapture(event.pointerId);
    setFrame(0, 0);
  });

  frame.addEventListener("pointermove", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const dy = event.clientY - drag.y;
    const pastEnd = (dy < 0 && index >= reels.length - 1) || (dy > 0 && index <= 0);
    drag.dy = dy;
    setFrame(pastEnd ? dy / 3 : dy, 0);
  });

  frame.addEventListener("pointerup", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    const { x, y, time, dy } = drag;
    drag = null;
    if (Math.hypot(event.clientX - x, event.clientY - y) < TAP_SLOP_PX) {
      setFrame(0, 0);
      setChrome(!root.classList.contains("chrome-on"));
      return;
    }
    const step = dy < 0 ? 1 : -1; // finger up: next reel
    const target = index + step;
    const far = Math.abs(dy) > window.innerHeight * SWIPE_FRACTION;
    const flick = Math.abs(dy) / Math.max(1, performance.now() - time) > FLICK_PX_PER_MS;
    if ((far || flick) && target >= 0 && target < reels.length) slide(step);
    else setFrame(0, SPRING_MS);
  });

  frame.addEventListener("pointercancel", (event) => {
    if (!drag || event.pointerId !== drag.id) return;
    drag = null;
    setFrame(0, SPRING_MS);
  });

  // ---- scrubbers, errors, keys

  for (const range of scrubbers) {
    range.addEventListener("input", () => {
      video.currentTime = Number(range.value);
      renderProgress();
    });
  }

  video.addEventListener("error", () => {
    if (!isOpen()) return;
    const gone = current();
    close();
    onGone(gone.id);
    showToast("that one's gone", { error: true });
  });

  function trapFocus(event) {
    const focusable = [...root.querySelectorAll("button, input")].filter(
      (el) => !el.disabled && el.getClientRects().length > 0,
    );
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (!root.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  document.addEventListener("keydown", (event) => {
    if (!isOpen()) return;
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (!desktopQuery.matches) return;
    if (event.key === "Tab") {
      trapFocus(event);
      return;
    }
    if (event.target instanceof HTMLInputElement) return; // arrows seek inside the scrubber
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      move(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      move(1);
    }
  });

  // Crossing 700px while open: CSS switches the layout; reset what only one layout uses.
  desktopQuery.addEventListener("change", () => {
    if (!isOpen()) return;
    drag = null;
    setFrame(0, 0);
    setChrome(false);
  });

  return { open, close, isOpen, addReels };
}
```

- [ ] **Step 2: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (165 passed, 1 deselected).

- [ ] **Step 3: Check swipes in Chrome**

Dev server running, logged in, 390×844 device mode with touch (e.g. "iPhone 12 Pro" preset, which also sets an iPhone user agent — reload after choosing it). Open the second tile.

- Drag up slowly by a quarter of the screen and release: the frame follows the finger, slides out upwards, the third reel slides in from below and plays; the address bar shows `?reel=seed02`.
- Drag down a little (under 20%) slowly and release: springs back, same reel.
- A short fast flick down: previous reel.
- On the first reel drag down, and on the last (`seed11`) drag up: the frame moves at a third of the finger distance and springs back; no move.
- Tap (no movement): the chrome toggles; with the chrome shown, swipe up: the next reel shows with the chrome still shown. Tapping buttons and dragging the scrubber never toggles the chrome or swipes.
- Browser Back after several swipes: closes the player straight to the board.

- [ ] **Step 4: Check Save on an iPhone user agent and on Android**

Still on the iPhone preset. Stub `navigator.share` (Global Constraints) with a version that also logs the file: `Object.defineProperty(navigator, "share", { configurable: true, value: (data) => { console.log("share", data.files ? data.files[0].name + " " + data.files[0].size : data.url); return Promise.resolve(); } })`.

- First run `navigator.canShare({ files: [new File([""], "probe.mp4", { type: "video/mp4" })] })` in the console. If it returns `false`, this Chrome cannot take the iPhone path: skip to the Android check below and record that iPhone Save is only verifiable on a real device (spec 11.3).
- Open a reel and show the chrome right away: **Save** shows a spinner in place of its icon and tapping it does nothing; within a second or two the download icon returns (DevTools Network shows one extra `GET /files/<id>.mp4` made by `fetch`).
- Tap **Save**: the console logs `share <slug>.mp4 <size>` and no toast appears.
- Swipe to another reel while its file is still loading (throttle the network to "Slow 4G" to see it): the earlier request shows as cancelled.

Switch the preset to "Pixel 7" (Android user agent) and reload. Open a reel: no extra MP4 fetch; **Save** downloads and the toast reads "saved to your downloads". At 1280×800 **Download** behaves the same.

- [ ] **Step 5: Commit**

```bash
git add reels_api/static/player.js
git commit -m "feat: swipe between reels on phones; Save opens the share sheet on iPhone" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Login page, README and the full manual pass

**Files:**
- Rewrite: `reels_api/static/login.html`
- Modify: `reels_api/static/style.css` (append), `README.md` ("Phone web page" section)

**Interfaces:**
- Consumes: `.wordmark`, `.btn`, `.btn-primary` styles (Tasks 4 and 6). `login.js` is unchanged and still needs the ids `login-form`, `passcode`, `continue`, `login-error`.

- [ ] **Step 1: Replace `reels_api/static/login.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="theme-color" content="#0a0b0d">
<title>reels</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,400;12..96,600;12..96,700;12..96,800&amp;display=swap">
<link rel="stylesheet" href="/static/style.css">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/static/icon-192.png">
</head>
<body class="login">
<main class="login-box">
  <h1 class="wordmark">reels</h1>
  <p class="login-lead">enter the passcode</p>
  <form id="login-form" class="login-form" autocomplete="off">
    <input id="passcode" class="field" type="password" autocomplete="current-password" placeholder="passcode" aria-label="passcode" required autofocus>
    <button id="continue" class="btn btn-primary" type="submit">continue</button>
    <p id="login-error" class="login-error" role="alert" hidden></p>
  </form>
</main>
<script src="/static/login.js"></script>
</body>
</html>
```

- [ ] **Step 2: Append the login styles to `reels_api/static/style.css`**

```css

/* ---- login page (spec 8.2) ---- */

body.login { display: flex; align-items: center; justify-content: center; padding: 24px 16px; }
.login-box { display: flex; flex-direction: column; gap: 14px; width: 100%; max-width: 340px; }
.login-box .wordmark { margin: 0; font-size: 28px; }
.login-lead { font-size: 14px; color: var(--ink-70); }
.login-form { display: flex; flex-direction: column; gap: 10px; }
.field {
  width: 100%;
  height: 50px;
  padding: 0 18px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  background: var(--surface);
  font: 400 16px var(--font);
  color: var(--ink);
  outline: none;
}
.field::placeholder { color: var(--ink-42); opacity: 1; }
.field:focus { border-color: var(--accent); }
.login-form .btn { width: 100%; }
.btn:disabled { opacity: 0.6; }
.login-error { font: 500 12.5px var(--font); color: var(--danger-text); }
```

- [ ] **Step 3: Update `README.md`**

Replace the whole `## Phone web page` section — from that heading up to, but not including, `## Configuration` — with:

```markdown
## Phone web page

Set `WEB_PASSCODE` in `.env` and the app serves a web page at `/`. Friends
enter the passcode once and land on **the pile**: a grid of every reel
anyone pasted in the last `RETENTION_HOURS`, up to `MAX_VIDEOS` (default
10; past that the oldest video is deleted to make room). No names are
stored or shown. Leave `WEB_PASSCODE` empty to disable the page; the JSON
API is unaffected either way.

- **Paste** a TikTok or Instagram link (or the whole share text) into the
  field. The reel shows up for everyone. Pasting a link that is already in
  the pile resolves to the existing reel.
- **Play**: tap a reel. On a phone it fills the screen: swipe up or down
  for the next one, tap for the caption and the Share, Save and copy-link
  buttons. On a desktop it opens as an overlay; ← → move, Esc closes.
- **Share** and **Copy link** hand out `https://<site>/?reel=<id>`, which
  opens that reel (after the passcode, for someone new) until it ages out.
- **Save** downloads the MP4. On iPhone it opens the share sheet instead,
  where **Save Video** puts it in Photos.

The page needs HTTPS for sharing and for the home-screen install. In
production that is Caddy (below). For local development set
`WEB_PASSCODE` in `.env`, run uvicorn, and open `http://localhost:8000/`
in Chrome or Firefox (Safari refuses the `Secure` cookie over plain http).

To try the page without downloading anything, `scripts/dev_board.py`
serves it with a pile of generated test clips and a fake downloader
(passcode `dev`); its docstring shows how to run it in Docker when ffmpeg
is not installed locally.

On Android, **Add to Home screen** installs the page and it then appears
in TikTok's share menu. On iPhone, paste the link.

```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass (165 passed, 1 deselected).

- [ ] **Step 5: Full manual pass (spec 11.2)**

Restart the dev server (Task 3 Step 5) so the session starts clean, and clear the site's cookies for `localhost` in DevTools (Application → Storage → Clear site data). Go through every item at 390×844 (touch) and 1280×800, and fix anything that fails before committing:

- Login: dark page, "reels" wordmark, round passcode field, accent **continue**. A wrong passcode shows "That passcode is not right." in the red text colour; `dev` lands on the board.
- Board: full pile with badges; `--empty` restart shows the empty state; desktop hover and keyboard focus; 3 / 4 / 5 columns at 800 / 1000 / 1280px.
- Paste: success (tile fades in, count), each error hint from Task 5 Step 7, editing clears the error, an unsupported URL, the same URL twice resolves to one tile.
- Phone player: tap shows and hides chrome, swipe next/previous, bounce at both ends, scrubber seek, mute toggle, ✕ and browser Back both return to the board at the same scroll position.
- Desktop player: overlay layout at 800px and 1280px wide and in a 600px-tall window, ← / → / Esc, prev/next disabled at the ends.
- Copy link toast; Share falls back to `wa.me` when `navigator.share` is missing (desktop **Share to WhatsApp**); Download toast.
- `/?reel=seed03` opens the player muted; `/?reel=nope` shows the board and "that one's gone".
- Open `/?reel=seed03` in a private window: the login page shows; after `dev` the player opens on `seed03`.
- `/?text=https://vm.tiktok.com/sharetarget/` starts a paste.
- DevTools console: no errors on any of the above.

Stop the dev server when done: `docker stop reels-dev`.

- [ ] **Step 6: Commit**

```bash
git add reels_api/static/login.html reels_api/static/style.css README.md
git commit -m "feat: dark login page; README describes the board" -m "Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>"
```

---

## After the plan

On real devices after deploying (owner, spec 11.3): iPhone Save → Save Video reaches Photos; Share opens the sheet with the link; swipe feel; sound on the first tap. Android: Save lands in Downloads and shows in the gallery; Share opens the sheet; sharing from the TikTok app still starts a paste. A friend without the cookie opens a shared `/?reel=` link, logs in and lands on the reel.
