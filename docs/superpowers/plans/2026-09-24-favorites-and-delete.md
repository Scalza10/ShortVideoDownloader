# Favorites, Delete and a Pile That Survives Restarts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The pile survives restarts and deploys, a ★ keeps a reel past its 12 hours (up to 200, on their own tab), and anyone logged in can delete a reel, with a 5-second undo on the page.

**Architecture:** The in-memory `JobStore` stays the source of truth. A new `jobs_file.py` writes its done jobs to `STORAGE_DIR/jobs.json` (temp file + `os.replace`), and `JobManager.start` reads them back before the stray-file cleanup runs. `Job` gains `favorite`/`starred_at`; the sweep and the video cap skip favorites; `JobManager.set_favorite` and `JobManager.delete` back three new routes. On the page, `board.js` gets pile/favorites tabs, `player.js` gets star and delete buttons that report through callbacks, `toast.js` gets an optional action button, and `app.js` calls the API and runs the undo.

**Tech Stack:** Python 3.12, FastAPI, pytest (anyio); plain HTML/CSS/ES modules (no build, no JS tests).

**Spec:** `docs/superpowers/specs/2026-09-24-favorites-and-delete-design.md`

## Global Constraints

- The job JSON change is additive: `"favorite": true|false` and `"starred_at": "<ISO Z>"|null`, on done jobs only.
- `jobs.json` lives at `STORAGE_DIR/jobs.json`, format `{"version": 1, "jobs": [...]}`, done jobs only, no file paths.
- `MAX_FAVORITES` defaults to 200 and must be at least 1.
- Starring when full: `409`, body exactly `{"error": "favorites_full", "message": "Favorites are full (N). Remove one first."}` with N = `MAX_FAVORITES`.
- New routes: `PUT /jobs/{id}/favorite`, `DELETE /jobs/{id}/favorite` (both `200` + job JSON), `DELETE /jobs/{id}` (`204`). Anything that isn't a done job: `404 not_found`. API key or login cookie only; a share key (`?k=`) never opens them.
- Page text, exactly: tabs `pile` and `favorites`; toasts `added to favorites`, `un-starred`, `deleted`, `removed` (the last three with an `undo` button), `favorites are full (N). remove one first.`, `couldn't delete. try again.`, `couldn't save that. try again.`, `too late. it's deleted.`; empty favorites `no favorites yet` / `tap ★ on a reel to keep it after it leaves the pile.`; the player's info line ends `★ kept` for a favorite.
  - The spec's empty-state line said "past 12 hours". `RETENTION_HOURS` is configurable and `app.html` has no hours placeholder, so the line doesn't name a number.
- A toast with an action stays 5 seconds; every other toast keeps its 2.5 seconds.
- The view-only page (`watch.html`) gets neither the star nor the delete button.
- No new JS modules (`APP_MODULES` in `tests/test_web.py` stays as it is), no JS dependencies, no requests to other sites.
- Run the tests with `.venv\Scripts\python.exe -m pytest` (PowerShell) or `.venv/Scripts/python.exe -m pytest` (Git Bash). ffmpeg is not installed locally. The suite is 335 tests before this plan.
- JS syntax check (Git Bash; plain `node --check` ignores syntax errors in `.js` modules, `.mjs` catches them):
  `d=$(mktemp -d); for f in <files>; do cp "reels_api/static/$f" "$d/${f%.js}.mjs" && node --check "$d/${f%.js}.mjs" || echo "SYNTAX ERROR: $f"; done`
- Commits: small, prefixed `feat:` / `docs:`, message ending with a blank line and `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. Stage only the files the task names (`brag-output/` is untracked and stays that way).

## Review Focus

Inputs the spec implies that are most likely to bite, each pinned by a test in the task that owns the code:

1. **Two phones star the last free slot at the same moment.** Exactly one gets it and the other gets `favorites_full`. Task 4, `test_two_stars_for_the_last_slot_take_it_once`.
2. **A favorite un-starred through the API after its hours.** It disappears, files and all, at the next hourly sweep. Task 4, `test_an_unstarred_reel_past_its_time_goes_at_the_next_sweep`.
3. **Pasting a link again.** After a delete it downloads fresh (Task 5, `test_a_deleted_reels_link_downloads_again`). For an old favorite it returns the favorite and doesn't queue a new download (Task 4, `test_submit_of_an_old_favorites_link_returns_it`).
4. **A crash mid-save leaves `jobs.json.tmp` behind.** The next save writes over it and the stray-file cleanup ignores it. Task 2, `test_write_over_a_stale_temp_file`.
5. **A saved reel whose thumbnail file is gone** (its video is still there). It still comes back on restart. Task 3, `test_start_restores_a_reel_whose_thumbnail_is_gone`.

---

### Task 1: Favorite fields in the job and its JSON

**Files:**
- Modify: `reels_api/models.py` (`Job`, `job_to_dict`)
- Test: `tests/test_models.py`

**Interfaces:**
- Produces: `Job.favorite: bool = False`, `Job.starred_at: datetime | None = None` (the last two fields of `Job`); `job_to_dict(job)["favorite"]` and `["starred_at"]` for done jobs.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models.py`:

```python
def test_job_to_dict_favorite():
    job = Job(id="abc", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    job.result = _result(10)
    d = job_to_dict(job)
    assert d["favorite"] is False
    assert d["starred_at"] is None

    job.favorite = True
    job.starred_at = datetime(2026, 9, 24, 18, 2, 11, 500, tzinfo=UTC)
    d = job_to_dict(job)
    assert d["favorite"] is True
    assert d["starred_at"] == "2026-09-24T18:02:11Z"

    assert "favorite" not in job_to_dict(Job(id="q", url="u", source=Source.TIKTOK))
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_models.py::test_job_to_dict_favorite -q`
Expected: FAIL with `KeyError: 'favorite'`.

- [ ] **Step 3: Implement**

In `reels_api/models.py`, add two fields at the end of `Job`, after `item`:

```python
    item: int = 1  # which of the post's videos, 1-based (yt-dlp's playlist_items)
    favorite: bool = False  # starred: kept past expires_at until un-starred (favorites spec 3)
    starred_at: datetime | None = None
```

In `job_to_dict`'s done branch, after `"nsfw": r.nsfw,`:

```python
                "favorite": job.favorite,
                "starred_at": _iso_z(job.starred_at) if job.starred_at else None,
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass (336).

- [ ] **Step 5: Commit**

```bash
git add reels_api/models.py tests/test_models.py
git commit -m "feat: favorite and starred_at on jobs, in the job JSON"
```

---

### Task 2: `jobs_file`: the pile's copy on disk

**Files:**
- Create: `reels_api/jobs_file.py`
- Test: `tests/test_jobs_file.py` (new)

**Interfaces:**
- Consumes: `Job.favorite`, `Job.starred_at` (Task 1).
- Produces:
  - `jobs_file.FILE_NAME = "jobs.json"`, `jobs_file.VERSION = 1`
  - `jobs_file.dumps(jobs: list[Job]) -> str`: the file's text; only `done` jobs with a result.
  - `jobs_file.write(path: Path, text: str) -> None`: creates the parent dir, writes `<name>.tmp`, fsyncs, `os.replace`s. Raises `OSError` on failure.
  - `jobs_file.load(path: Path, storage_dir: Path) -> list[Job]`: `[]` without a file. An unusable file is moved to `<name>.bad` (replacing an older one) and gives `[]`. Loaded jobs are `done`, with `file_path = storage_dir/<id>.mp4` and `thumbnail_path = storage_dir/<id>.jpg` or `None`.

The spec named these `save` and `load`. `save` is split into `dumps` and `write` so the manager can take the snapshot in the event loop and write it in a thread (Task 3).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_jobs_file.py`:

```python
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reels_api import jobs_file
from reels_api.models import Job, JobResult, JobStatus, Source

STORAGE = Path("/data/files")


def _done(job_id: str, thumb: bool = True, **fields) -> Job:
    finished = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    job = Job(id=job_id, url=f"https://vm.tiktok.com/{job_id}/", source=Source.TIKTOK, status=JobStatus.DONE, item=2)
    job.finished_at = finished
    job.expires_at = finished + timedelta(hours=12)
    job.result = JobResult(
        STORAGE / f"{job_id}.mp4",
        "Title",
        Source.TIKTOK,
        12.5,
        1234,
        720,
        1280,
        thumbnail_path=STORAGE / f"{job_id}.jpg" if thumb else None,
        caption="a caption",
        nsfw=True,
    )
    for name, value in fields.items():
        setattr(job, name, value)
    return job


def test_write_then_load_gives_the_same_reels(tmp_path):
    starred = _done("fav1", favorite=True, starred_at=datetime(2026, 9, 24, 13, 0, tzinfo=UTC))
    plain = _done("plain1", thumb=False)
    path = tmp_path / "jobs.json"
    jobs_file.write(path, jobs_file.dumps([starred, plain]))
    assert jobs_file.load(path, STORAGE) == [starred, plain]


def test_only_done_reels_are_saved(tmp_path):
    queued = Job(id="q1", url="u", source=Source.TIKTOK)
    failed = Job(id="f1", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
    path = tmp_path / "jobs.json"
    jobs_file.write(path, jobs_file.dumps([queued, failed, _done("d1")]))
    assert [job.id for job in jobs_file.load(path, STORAGE)] == ["d1"]


def test_file_format(tmp_path):
    path = tmp_path / "jobs.json"
    jobs_file.write(path, jobs_file.dumps([_done("d1", thumb=False)]))
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["version"] == 1
    [entry] = body["jobs"]
    assert entry["id"] == "d1"
    assert entry["has_thumbnail"] is False
    assert entry["finished_at"] == "2026-09-24T12:00:00+00:00"
    assert entry["favorite"] is False
    assert entry["starred_at"] is None
    assert "file_path" not in entry
    assert "thumbnail_path" not in entry


def test_write_replaces_the_file_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("old", encoding="utf-8")
    jobs_file.write(path, "new")
    assert path.read_text(encoding="utf-8") == "new"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["jobs.json"]


def test_write_over_a_stale_temp_file(tmp_path):
    # A crash mid-write leaves jobs.json.tmp behind; the next save just writes over it.
    (tmp_path / "jobs.json.tmp").write_text("half a fi", encoding="utf-8")
    jobs_file.write(tmp_path / "jobs.json", "new")
    assert (tmp_path / "jobs.json").read_text(encoding="utf-8") == "new"
    assert not (tmp_path / "jobs.json.tmp").exists()


def test_write_creates_the_directory(tmp_path):
    path = tmp_path / "files" / "jobs.json"
    jobs_file.write(path, "x")
    assert path.read_text(encoding="utf-8") == "x"


def test_load_without_a_file_is_empty(tmp_path):
    assert jobs_file.load(tmp_path / "jobs.json", STORAGE) == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"jobs": []}',
        '{"version": 2, "jobs": []}',
        '{"version": 1}',
        '{"version": 1, "jobs": ["x"]}',
        '{"version": 1, "jobs": [{"id": "x"}]}',
    ],
)
def test_an_unusable_file_is_moved_aside(tmp_path, text):
    path = tmp_path / "jobs.json"
    path.write_text(text, encoding="utf-8")
    assert jobs_file.load(path, STORAGE) == []
    assert not path.exists()
    assert (tmp_path / "jobs.json.bad").read_text(encoding="utf-8") == text


def _edited(tmp_path, change) -> Path:
    body = json.loads(jobs_file.dumps([_done("d1")]))
    change(body["jobs"][0])
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


@pytest.mark.parametrize("bad_id", ["../d1", "a/b", "", 7])
def test_an_id_that_is_not_a_plain_name_makes_the_file_unusable(tmp_path, bad_id):
    path = _edited(tmp_path, lambda entry: entry.update(id=bad_id))
    assert jobs_file.load(path, STORAGE) == []
    assert (tmp_path / "jobs.json.bad").exists()


def test_a_time_without_a_time_zone_makes_the_file_unusable(tmp_path):
    path = _edited(tmp_path, lambda entry: entry.update(finished_at="2026-09-24T12:00:00"))
    assert jobs_file.load(path, STORAGE) == []
    assert (tmp_path / "jobs.json.bad").exists()


def test_an_older_bad_file_is_replaced(tmp_path):
    (tmp_path / "jobs.json.bad").write_text("older", encoding="utf-8")
    (tmp_path / "jobs.json").write_text("newer", encoding="utf-8")
    assert jobs_file.load(tmp_path / "jobs.json", STORAGE) == []
    assert (tmp_path / "jobs.json.bad").read_text(encoding="utf-8") == "newer"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_jobs_file.py -q`
Expected: FAIL with `ImportError: cannot import name 'jobs_file'`.

- [ ] **Step 3: Implement**

Create `reels_api/jobs_file.py`:

```python
"""The pile on disk: jobs.json next to the videos, so a restart or deploy keeps it (favorites spec 2).

Memory is the source of truth and this file is its copy. Only done reels are written. File paths
are not stored: a reel's files are always <storage_dir>/<id>.mp4 and <id>.jpg.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from reels_api.models import Job, JobResult, JobStatus, Source

log = logging.getLogger(__name__)

FILE_NAME = "jobs.json"
VERSION = 1
_PLAIN_ID = re.compile(r"[A-Za-z0-9_-]+")  # new_job_id's alphabet; also keeps paths out of other directories


def _time(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:  # the sweep compares with aware times
        raise ValueError(f"time without a time zone: {value!r}")
    return parsed


def _entry(job: Job) -> dict:
    r = job.result
    return {
        "id": job.id,
        "url": job.url,
        "item": job.item,
        "source": job.source.value,
        "share_key": job.share_key,
        "created_at": _time(job.created_at),
        "finished_at": _time(job.finished_at),
        "expires_at": _time(job.expires_at),
        "favorite": job.favorite,
        "starred_at": _time(job.starred_at),
        "title": r.title,
        "caption": r.caption,
        "duration_seconds": r.duration_seconds,
        "size_bytes": r.size_bytes,
        "width": r.width,
        "height": r.height,
        "nsfw": r.nsfw,
        "has_thumbnail": r.thumbnail_path is not None,
    }


def _job(entry: dict, storage_dir: Path) -> Job:
    job_id = entry["id"]
    if not isinstance(job_id, str) or not _PLAIN_ID.fullmatch(job_id):
        raise ValueError(f"bad job id {job_id!r}")
    source = Source(entry["source"])
    result = JobResult(
        file_path=storage_dir / f"{job_id}.mp4",
        title=entry["title"],
        source=source,
        duration_seconds=entry["duration_seconds"],
        size_bytes=entry["size_bytes"],
        width=entry["width"],
        height=entry["height"],
        thumbnail_path=storage_dir / f"{job_id}.jpg" if entry["has_thumbnail"] else None,
        caption=entry["caption"],
        nsfw=entry["nsfw"],
    )
    return Job(
        id=job_id,
        url=entry["url"],
        source=source,
        status=JobStatus.DONE,
        created_at=_parse_time(entry["created_at"]),
        finished_at=_parse_time(entry["finished_at"]),
        expires_at=_parse_time(entry["expires_at"]),
        result=result,
        share_key=entry["share_key"],
        item=entry["item"],
        favorite=entry["favorite"],
        starred_at=_parse_time(entry["starred_at"]),
    )


def dumps(jobs: list[Job]) -> str:
    """The file's text for these jobs: only the done ones."""
    done = [job for job in jobs if job.status == JobStatus.DONE and job.result is not None]
    return json.dumps({"version": VERSION, "jobs": [_entry(job) for job in done]}, ensure_ascii=False)


def write(path: Path, text: str) -> None:
    """Replace path with text in one step: a crash leaves the old file or the new one, never half of one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load(path: Path, storage_dir: Path) -> list[Job]:
    """The saved jobs; [] without a file. A file that can't be used is moved to <name>.bad and gives []."""
    if not path.exists():
        return []
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
        if body.get("version") != VERSION:
            raise ValueError(f"unknown version {body.get('version')!r}")
        return [_job(entry, storage_dir) for entry in body["jobs"]]
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        bad = path.with_name(path.name + ".bad")
        os.replace(path, bad)
        log.warning("could not read %s (%s): moved it to %s and started with an empty pile", path, exc, bad.name)
        return []
```

- [ ] **Step 4: Run the tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_jobs_file.py -q`, then `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add reels_api/jobs_file.py tests/test_jobs_file.py
git commit -m "feat: jobs_file writes and reads the pile as jobs.json"
```

---

### Task 3: The pile comes back after a restart

**Files:**
- Modify: `reels_api/jobs.py` (`JobStore` docstring, `JobManager.__init__`, `start`, `_run_job`, `sweep`; new `jobs_path`, `_restore`, `save`)
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `jobs_file.FILE_NAME`, `jobs_file.dumps`, `jobs_file.write`, `jobs_file.load` (Task 2).
- Produces:
  - `JobManager.jobs_path -> Path` (property: `storage_dir / "jobs.json"`).
  - `async JobManager.save() -> None`: never raises on a write failure; logs `"could not save <path>"`.
  - Startup order in `JobManager.start`: `_restore` → `sweep` → `enforce_video_cap` → `save` → start the workers and the sweeper.

- [ ] **Step 1: Write the failing tests**

In `tests/test_jobs.py`, add `from reels_api import jobs_file` to the imports. Append:

```python
def _saved_pile(settings, jobs):
    jobs_file.write(settings.storage_dir / "jobs.json", jobs_file.dumps(jobs))


async def wait_saved(settings, job_id, timeout=5.0):
    path = settings.storage_dir / "jobs.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if any(job.id == job_id for job in jobs_file.load(path, settings.storage_dir)):
            return
        await asyncio.sleep(0.02)
    raise AssertionError("job was not saved")


@pytest.mark.anyio
async def test_start_restores_the_saved_pile_and_keeps_its_files(tmp_path):
    settings = make_settings(tmp_path)
    saved = _stored_video(settings, "saved1", datetime.now(UTC) - timedelta(minutes=5))
    _saved_pile(settings, [saved])
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        assert await store.get("saved1") == saved
        assert saved.result.file_path.exists()
        assert saved.result.thumbnail_path.exists()
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_start_drops_a_saved_reel_whose_video_is_gone(tmp_path):
    settings = make_settings(tmp_path)
    gone = _stored_video(settings, "gone1", datetime.now(UTC))
    gone.result.file_path.unlink()
    _saved_pile(settings, [gone])
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        assert await store.get("gone1") is None
        assert not gone.result.thumbnail_path.exists()  # now a stray
        assert jobs_file.load(manager.jobs_path, settings.storage_dir) == []
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_start_restores_a_reel_whose_thumbnail_is_gone(tmp_path):
    settings = make_settings(tmp_path)
    saved = _stored_video(settings, "nothumb", datetime.now(UTC))
    saved.result.thumbnail_path.unlink()
    _saved_pile(settings, [saved])
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        assert await store.get("nothumb") is not None
        assert saved.result.file_path.exists()
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_start_sweeps_saved_reels_past_their_time(tmp_path):
    settings = make_settings(tmp_path, retention_hours=1)
    old = _stored_video(settings, "old1", datetime.now(UTC) - timedelta(hours=2))
    _saved_pile(settings, [old])
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        assert await store.get("old1") is None
        assert not old.result.file_path.exists()
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_start_keeps_jobs_already_in_the_store(tmp_path):
    settings = make_settings(tmp_path)
    now = datetime.now(UTC)
    saved = _stored_video(settings, "seed00", now - timedelta(minutes=30))
    _saved_pile(settings, [saved])
    seed = _stored_video(settings, "seed00", now)  # a dev-board seed, added before start
    store = JobStore()
    await store.add(seed)
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        assert await store.get("seed00") is seed
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_a_restart_keeps_the_pile(tmp_path):
    settings = make_settings(tmp_path)
    first = JobManager(settings, FakePipeline(settings), JobStore())
    await first.start()
    try:
        [job] = await first.submit("https://vm.tiktok.com/x/")
        await wait_finished(first.store, job.id)
        await wait_saved(settings, job.id)
    finally:
        await first.stop()

    store = JobStore()
    second = JobManager(settings, FakePipeline(settings), store)
    await second.start()
    try:
        again = await store.get(job.id)
        assert again is not None
        assert again.status == JobStatus.DONE
        assert again.result.file_path.exists()
        assert again.expires_at == job.expires_at
        assert await second.submit("https://vm.tiktok.com/x/") == [again]  # no new download
    finally:
        await second.stop()


@pytest.mark.anyio
async def test_sweep_saves_what_is_left(tmp_path):
    settings = make_settings(tmp_path, retention_hours=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    now = datetime.now(UTC)
    await store.add(_stored_video(settings, "old1", now - timedelta(hours=2)))
    await store.add(_stored_video(settings, "new1", now))
    await manager.sweep(now=now)
    assert [job.id for job in jobs_file.load(manager.jobs_path, settings.storage_dir)] == ["new1"]


@pytest.mark.anyio
async def test_a_failed_save_is_logged_and_ignored(tmp_path, monkeypatch, caplog):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())

    def full_disk(path, text):
        raise OSError("No space left on device")

    monkeypatch.setattr(jobs_file, "write", full_disk)
    await manager.save()
    assert "could not save" in caplog.text
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_jobs.py -q`
Expected: FAIL. The restore tests find nothing in the store (startup deletes the saved files as strays), and `manager.jobs_path` / `manager.save` don't exist.

- [ ] **Step 3: Implement**

In `reels_api/jobs.py`:

Imports: add `from pathlib import Path`, and `from reels_api import jobs_file` above the `reels_api.models` import.

`JobStore` docstring:

```python
class JobStore:
    """In-memory job registry, the source of truth. jobs.json (jobs_file) is its copy on disk."""
```

`JobManager.__init__`, after `self._tasks`:

```python
        self._save_lock = asyncio.Lock()  # one save at a time, so the last write holds the newest state
```

Replace `start`:

```python
    async def start(self) -> None:
        # The saved pile comes back first, so its files aren't taken for strays (favorites spec 2).
        await self._restore()
        await self.sweep()  # reels past their time, then files and temp dirs that belong to no job
        await self.enforce_video_cap()
        await self.save()
        for i in range(self.settings.workers):
            self._tasks.append(asyncio.create_task(self._worker(), name=f"worker-{i}"))
        self._tasks.append(asyncio.create_task(self._sweeper(), name="sweeper"))
```

Add after `stop`:

```python
    @property
    def jobs_path(self) -> Path:
        return self.settings.storage_dir / jobs_file.FILE_NAME

    async def _restore(self) -> None:
        """Add the saved reels to the store. Jobs already there (dev-board seeds) win; a reel whose video is gone is dropped."""
        for job in jobs_file.load(self.jobs_path, self.settings.storage_dir):
            if await self.store.get(job.id) is not None:
                continue
            if not job.result.file_path.is_file():
                log.info("dropped saved job %s: its video is gone", job.id)
                continue
            await self.store.add(job)

    async def save(self) -> None:
        """Write the done jobs to jobs.json. A failed write is logged: memory stays the source of truth."""
        async with self._save_lock:
            text = jobs_file.dumps(await self.store.all())  # the snapshot, taken inside the lock
            try:
                await asyncio.to_thread(jobs_file.write, self.jobs_path, text)
            except OSError:
                log.exception("could not save %s", self.jobs_path)
```

In `_run_job`, replace the last two lines:

```python
        if job.status == JobStatus.DONE:
            await self.enforce_video_cap()
            await self.save()
```

In `sweep`, after `await self._remove_untracked_files()`:

```python
        await self.save()
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add reels_api/jobs.py tests/test_jobs.py
git commit -m "feat: the pile is saved to jobs.json and comes back after a restart"
```

---

### Task 4: Favorites on the server

**Files:**
- Modify: `reels_api/settings.py`, `.env.example`, `reels_api/models.py` (`ErrorCode`, `ERROR_MESSAGES`), `reels_api/main.py` (`_JOB_ERROR_STATUS`), `reels_api/jobs.py` (`set_favorite`, `sweep`, `enforce_video_cap`), `reels_api/routes.py`
- Test: `tests/test_settings.py`, `tests/test_jobs.py`, `tests/test_routes.py`

**Interfaces:**
- Consumes: `Job.favorite`/`starred_at` (Task 1), `JobManager.save`/`jobs_path` (Task 3).
- Produces:
  - `Settings.max_favorites: int` (default 200, ≥ 1).
  - `ErrorCode.FAVORITES_FULL = "favorites_full"` → HTTP `409`.
  - `async JobManager.set_favorite(job_id: str, on: bool) -> Job | None`: `None` when there is no done job with that id. Raises `JobError(FAVORITES_FULL, "Favorites are full (N). Remove one first.")`.
  - Routes `PUT` and `DELETE /jobs/{job_id}/favorite`: `200` + `job_to_dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_settings.py`:

```python
def test_max_favorites_default_and_minimum(monkeypatch):
    monkeypatch.setenv("API_KEY", "abc")
    assert Settings(_env_file=None).max_favorites == 200
    monkeypatch.setenv("MAX_FAVORITES", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
```

Append to `tests/test_jobs.py`:

```python
def _favorite(job: Job) -> Job:
    job.favorite = True
    job.starred_at = datetime.now(UTC)
    return job


@pytest.mark.anyio
async def test_sweep_keeps_favorites_past_their_time(tmp_path):
    settings = make_settings(tmp_path, retention_hours=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    now = datetime.now(UTC)
    kept = _favorite(_stored_video(settings, "kept", now - timedelta(days=3)))
    old = _stored_video(settings, "old", now - timedelta(days=3))
    for job in (kept, old):
        await store.add(job)
    await manager.sweep(now=now)
    assert await store.get("kept") is kept
    assert kept.result.file_path.exists()
    assert await store.get("old") is None


@pytest.mark.anyio
async def test_video_cap_counts_and_evicts_only_non_favorites(tmp_path):
    settings = make_settings(tmp_path, max_videos=2)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    now = datetime.now(UTC)
    starred = [_favorite(_stored_video(settings, f"f{i}", now - timedelta(minutes=30 + i))) for i in range(3)]
    plain = [_stored_video(settings, f"p{i}", now - timedelta(minutes=i)) for i in range(3)]
    for job in (*starred, *plain):
        await store.add(job)
    await manager.enforce_video_cap()
    assert {job.id for job in await store.all()} == {"f0", "f1", "f2", "p0", "p1"}


@pytest.mark.anyio
async def test_star_and_unstar(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    job = _stored_video(settings, "v1", datetime.now(UTC))
    await store.add(job)

    assert await manager.set_favorite("v1", True) is job
    assert job.favorite is True
    starred_at = job.starred_at
    assert starred_at is not None
    assert await manager.set_favorite("v1", True) is job  # again: nothing changes
    assert job.starred_at == starred_at
    assert [j.favorite for j in jobs_file.load(manager.jobs_path, settings.storage_dir)] == [True]

    assert await manager.set_favorite("v1", False) is job
    assert (job.favorite, job.starred_at) == (False, None)
    assert await manager.set_favorite("v1", False) is job
    assert [j.favorite for j in jobs_file.load(manager.jobs_path, settings.storage_dir)] == [False]


@pytest.mark.anyio
async def test_star_needs_a_done_reel(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await store.add(Job(id="queued", url="u", source=Source.TIKTOK))
    await store.add(Job(id="failed", url="u", source=Source.TIKTOK, status=JobStatus.FAILED))
    for job_id in ("nope", "queued", "failed"):
        assert await manager.set_favorite(job_id, True) is None
        assert await manager.set_favorite(job_id, False) is None


@pytest.mark.anyio
async def test_starring_past_the_limit_is_refused(tmp_path):
    settings = make_settings(tmp_path, max_favorites=2)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    now = datetime.now(UTC)
    for i in range(3):
        await store.add(_stored_video(settings, f"v{i}", now))
    await manager.set_favorite("v0", True)
    await manager.set_favorite("v1", True)
    with pytest.raises(JobError) as exc:
        await manager.set_favorite("v2", True)
    assert exc.value.code == ErrorCode.FAVORITES_FULL
    assert exc.value.message == "Favorites are full (2). Remove one first."
    assert (await store.get("v2")).favorite is False
    assert await manager.set_favorite("v0", True) is not None  # already a favorite: never refused
    await manager.set_favorite("v0", False)
    assert (await manager.set_favorite("v2", True)).favorite is True


@pytest.mark.anyio
async def test_two_stars_for_the_last_slot_take_it_once(tmp_path):
    settings = make_settings(tmp_path, max_favorites=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    now = datetime.now(UTC)
    for job_id in ("a", "b"):
        await store.add(_stored_video(settings, job_id, now))
    results = await asyncio.gather(
        manager.set_favorite("a", True), manager.set_favorite("b", True), return_exceptions=True
    )
    assert sum(isinstance(r, JobError) for r in results) == 1
    assert sum(1 for job in await store.all() if job.favorite) == 1


@pytest.mark.anyio
async def test_a_lowered_limit_keeps_every_favorite(tmp_path):
    settings = make_settings(tmp_path, max_favorites=1, retention_hours=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    now = datetime.now(UTC)
    for i in range(3):
        await store.add(_favorite(_stored_video(settings, f"f{i}", now - timedelta(days=2))))
    await store.add(_stored_video(settings, "plain", now))
    await manager.sweep(now=now)
    await manager.enforce_video_cap()
    assert sum(1 for job in await store.all() if job.favorite) == 3
    with pytest.raises(JobError):
        await manager.set_favorite("plain", True)
    assert (await manager.set_favorite("f0", False)).favorite is False


@pytest.mark.anyio
async def test_an_unstarred_reel_past_its_time_goes_at_the_next_sweep(tmp_path):
    settings = make_settings(tmp_path, retention_hours=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    now = datetime.now(UTC)
    job = _favorite(_stored_video(settings, "f0", now - timedelta(days=2)))
    await store.add(job)
    await manager.sweep(now=now)
    assert await store.get("f0") is job
    await manager.set_favorite("f0", False)
    await manager.sweep(now=now)
    assert await store.get("f0") is None
    assert not job.result.file_path.exists()


@pytest.mark.anyio
async def test_a_star_survives_a_restart(tmp_path):
    settings = make_settings(tmp_path, retention_hours=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    job = _stored_video(settings, "f0", datetime.now(UTC) - timedelta(days=2))
    job.expires_at = job.finished_at + timedelta(hours=1)
    await store.add(job)
    await manager.set_favorite("f0", True)

    again = JobStore()
    second = JobManager(settings, FakePipeline(settings), again)
    await second.start()
    try:
        restored = await again.get("f0")
        assert restored is not None
        assert restored.favorite is True
        assert restored.starred_at == job.starred_at
        assert restored.result.file_path.exists()
    finally:
        await second.stop()


@pytest.mark.anyio
async def test_submit_of_an_old_favorites_link_returns_it(tmp_path):
    settings = make_settings(tmp_path, retention_hours=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    job = _favorite(_stored_video(settings, "f0", datetime.now(UTC) - timedelta(days=2)))
    job.url = "https://vm.tiktok.com/fav/"
    await store.add(job)
    assert await manager.submit("https://vm.tiktok.com/fav/") == [job]
    assert manager.queue.empty()
```

Append to `tests/test_routes.py` (add `from reels_api import jobs_file` to the imports):

```python
def test_star_and_unstar_answer_the_reel(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        assert reel["favorite"] is False
        assert reel["starred_at"] is None

        r = client.put(f"/jobs/{reel['id']}/favorite", headers=HEADERS)
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == reel["id"]
        assert body["favorite"] is True
        assert body["starred_at"].endswith("Z")
        assert client.get("/jobs", headers=HEADERS).json()["jobs"][0]["favorite"] is True
        manager = client.app.state.manager
        assert [j.favorite for j in jobs_file.load(manager.jobs_path, manager.settings.storage_dir)] == [True]

        r = client.delete(f"/jobs/{reel['id']}/favorite", headers=HEADERS)
        assert r.status_code == 200
        assert (r.json()["favorite"], r.json()["starred_at"]) == (False, None)


def test_star_unknown_or_unfinished_is_404(app_factory):
    app = app_factory("block")
    gate = app.state.manager.pipeline.gate
    try:
        with TestClient(app) as client:
            running = client.post("/jobs", json={"url": "https://vm.tiktok.com/1/"}, headers=HEADERS).json()["id"]
            for job_id in ("nope", running):
                for method in (client.put, client.delete):
                    r = method(f"/jobs/{job_id}/favorite", headers=HEADERS)
                    assert r.status_code == 404, (job_id, method)
                    assert r.json()["error"] == "not_found"
            gate.set()
    finally:
        gate.set()


def test_star_when_full_is_409(app_factory):
    with TestClient(app_factory(max_favorites=1)) as client:
        first = _done_reel(client, "https://vm.tiktok.com/1/")
        second = _done_reel(client, "https://vm.tiktok.com/2/")
        assert client.put(f"/jobs/{first['id']}/favorite", headers=HEADERS).status_code == 200
        r = client.put(f"/jobs/{second['id']}/favorite", headers=HEADERS)
        assert r.status_code == 409
        assert r.json() == {"error": "favorites_full", "message": "Favorites are full (1). Remove one first."}
        assert client.put(f"/jobs/{first['id']}/favorite", headers=HEADERS).status_code == 200


def test_share_key_does_not_open_favorites(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        key = {"k": reel["share_key"]}
        assert client.put(f"/jobs/{reel['id']}/favorite", params=key).status_code == 401
        assert client.delete(f"/jobs/{reel['id']}/favorite", params=key).status_code == 401
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_settings.py tests/test_jobs.py tests/test_routes.py -q`
Expected: FAIL (`Settings` has no `max_favorites`, `JobManager` has no `set_favorite`, the routes answer `405`).

- [ ] **Step 3: Implement**

`reels_api/settings.py`, after `max_videos`:

```python
    max_favorites: int = Field(200, ge=1)  # starred reels, kept past retention until un-starred
```

`.env.example`, after `MAX_VIDEOS=100`:

```
# Most starred reels (favorites). They stay past RETENTION_HOURS until un-starred and don't count toward MAX_VIDEOS.
MAX_FAVORITES=200
```

`reels_api/models.py`: add `FAVORITES_FULL = "favorites_full"` as the last `ErrorCode`, and to `ERROR_MESSAGES`:

```python
    ErrorCode.FAVORITES_FULL: "Favorites are full. Remove one first.",
```

`reels_api/main.py`, in `_JOB_ERROR_STATUS`:

```python
    ErrorCode.FAVORITES_FULL: 409,
```

`reels_api/jobs.py`:

Replace `enforce_video_cap`'s first two lines:

```python
    async def enforce_video_cap(self) -> None:
        """Keep at most max_videos finished videos that aren't favorites; delete the oldest first."""
        videos = [job for job in await self.store.list_recent(limit=None) if not job.favorite]  # newest first
```

In `sweep`, update the docstring and the condition:

```python
        """Delete finished jobs older than the retention window, except favorites, and untracked files."""
        now = now or utcnow()
        cutoff = now - self._retention()
        for job in await self.store.all():
            if job.finished_at is not None and job.finished_at < cutoff and not job.favorite:
```

Add after `enforce_video_cap`:

```python
    async def set_favorite(self, job_id: str, on: bool) -> Job | None:
        """Star or un-star a done reel (favorites spec 3). None when there is no such done reel."""
        job = await self.store.get(job_id)
        if job is None or job.status != JobStatus.DONE or job.result is None:
            return None
        if job.favorite == on:
            return job  # already so: nothing changes, not even starred_at
        if on:
            favorites = sum(1 for other in await self.store.all() if other.favorite)
            # No await from here to the star, so two phones can't both take the last slot.
            limit = self.settings.max_favorites
            if favorites >= limit:
                raise JobError(ErrorCode.FAVORITES_FULL, f"Favorites are full ({limit}). Remove one first.")
            job.starred_at = utcnow()
        else:
            job.starred_at = None
        job.favorite = on
        await self.save()
        return job
```

`reels_api/routes.py`, after `get_job`:

```python
async def _star(request: Request, job_id: str, on: bool) -> dict:
    """Star or un-star a done reel; answers the reel (favorites spec 5)."""
    job = await request.app.state.manager.set_favorite(job_id, on)
    if job is None:
        raise _not_found()
    return job_to_dict(job, request.app.state.settings.public_base_url)


@protected.put("/jobs/{job_id}/favorite")
async def star_job(job_id: str, request: Request) -> dict:
    return await _star(request, job_id, True)


@protected.delete("/jobs/{job_id}/favorite")
async def unstar_job(job_id: str, request: Request) -> dict:
    return await _star(request, job_id, False)
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add reels_api/settings.py .env.example reels_api/models.py reels_api/main.py reels_api/jobs.py reels_api/routes.py tests/test_settings.py tests/test_jobs.py tests/test_routes.py
git commit -m "feat: favorites are kept past retention, up to MAX_FAVORITES, via PUT/DELETE /jobs/{id}/favorite"
```

---

### Task 5: Delete on the server

**Files:**
- Modify: `reels_api/jobs.py` (`delete`), `reels_api/routes.py` (`delete_job`)
- Test: `tests/test_jobs.py`, `tests/test_routes.py`, `tests/test_web.py`

**Interfaces:**
- Consumes: `JobManager._discard`, `JobManager.save` (Task 3), `_favorite` test helper (Task 4).
- Produces: `async JobManager.delete(job_id: str) -> bool` (False when there is no done job with that id); route `DELETE /jobs/{job_id}` → `204`, or `404 not_found`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_jobs.py`:

```python
@pytest.mark.anyio
async def test_delete_removes_the_reel_and_its_files_and_saves(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    now = datetime.now(UTC)
    gone = _favorite(_stored_video(settings, "gone", now))  # deleting doesn't care about the star
    kept = _stored_video(settings, "kept", now)
    for job in (gone, kept):
        await store.add(job)

    assert await manager.delete("gone") is True
    assert await store.get("gone") is None
    assert not gone.result.file_path.exists()
    assert not gone.result.thumbnail_path.exists()
    assert kept.result.file_path.exists()
    assert [job.id for job in jobs_file.load(manager.jobs_path, settings.storage_dir)] == ["kept"]


@pytest.mark.anyio
async def test_delete_needs_a_done_reel(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    running = Job(id="running", url="u", source=Source.TIKTOK, status=JobStatus.DOWNLOADING)
    await store.add(running)
    assert await manager.delete("nope") is False
    assert await manager.delete("running") is False
    assert await store.get("running") is running


@pytest.mark.anyio
async def test_a_deleted_reels_link_downloads_again(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        [first] = await manager.submit("https://vm.tiktok.com/x/")
        await wait_finished(store, first.id)
        assert await manager.delete(first.id) is True
        [again] = await manager.submit("https://vm.tiktok.com/x/")
        assert again.id != first.id
        assert (await wait_finished(store, again.id)).status == JobStatus.DONE
    finally:
        await manager.stop()
```

Append to `tests/test_routes.py`:

```python
def test_delete_job(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        job = client.app.state.store._jobs[reel["id"]]
        r = client.delete(f"/jobs/{reel['id']}", headers=HEADERS)
        assert r.status_code == 204
        assert r.content == b""
        assert not job.result.file_path.exists()
        assert not job.result.thumbnail_path.exists()
        assert client.get(f"/jobs/{reel['id']}", headers=HEADERS).status_code == 404
        assert client.get(f"/files/{reel['id']}.mp4", headers=HEADERS).status_code == 404
        assert client.get("/jobs", headers=HEADERS).json()["jobs"] == []
        again = client.delete(f"/jobs/{reel['id']}", headers=HEADERS)
        assert again.status_code == 404
        assert again.json()["error"] == "not_found"


def test_share_key_cannot_delete(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        assert client.delete(f"/jobs/{reel['id']}", params={"k": reel["share_key"]}).status_code == 401
        assert client.get(f"/jobs/{reel['id']}", headers=HEADERS).status_code == 200


def test_cookie_can_star_and_delete(app_factory):
    app = app_factory(web_passcode="letmein")
    with TestClient(app) as client:
        reel = _done_reel(client)
        client.cookies.set(SESSION_COOKIE, session_cookie_value(app.state.settings))
        assert client.put(f"/jobs/{reel['id']}/favorite").status_code == 200
        assert client.delete(f"/jobs/{reel['id']}").status_code == 204
```

In `tests/test_web.py`, change the import line to `from tests.test_routes import HEADERS, FakePipeline, _done_reel` and append:

```python
def test_index_deleted_reel_is_expired(web_app):
    with TestClient(web_app()) as client:
        reel = _done_reel(client)
        assert client.delete(f"/jobs/{reel['id']}", headers=HEADERS).status_code == 204
        assert _is_expired(client.get("/", params={"reel": reel["id"], "k": reel["share_key"]}))
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_jobs.py tests/test_routes.py tests/test_web.py -q`
Expected: FAIL (`JobManager` has no `delete`; `DELETE /jobs/{id}` answers `405`).

- [ ] **Step 3: Implement**

`reels_api/jobs.py`, after `set_favorite`:

```python
    async def delete(self, job_id: str) -> bool:
        """Delete a done reel and its files now, starred or not (favorites spec 4). False when there is none."""
        job = await self.store.get(job_id)
        if job is None or job.status != JobStatus.DONE or job.result is None:
            return False
        await self._discard(job)
        log.info("deleted job %s", job.id)
        await self.save()
        return True
```

`reels_api/routes.py`: import `Response` (`from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response`) and add after `unstar_job`:

```python
@protected.delete("/jobs/{job_id}", status_code=204)
async def delete_job(job_id: str, request: Request) -> Response:
    """Delete a done reel for everyone, now and for good (favorites spec 4)."""
    if not await request.app.state.manager.delete(job_id):
        raise _not_found()
    return Response(status_code=204)
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add reels_api/jobs.py reels_api/routes.py tests/test_jobs.py tests/test_routes.py tests/test_web.py
git commit -m "feat: DELETE /jobs/{id} deletes a reel and its files for everyone"
```

---

### Task 6: Dev board: favorite seeds and `--dir`

**Files:**
- Modify: `scripts/dev_board.py` (docstring, `SEED_MINUTES_AGO`, new `FAVORITE_SEEDS`, `seed_jobs`, new `make_root`, `main`)
- Test: `tests/test_dev_board.py`

**Interfaces:**
- Consumes: `Job.favorite`/`starred_at` (Task 1), the startup merge (Task 3), the sweep skipping favorites (Task 4).
- Produces: `dev_board.FAVORITE_SEEDS = (1, 11)`; `dev_board.make_root(keep_dir: Path | None) -> Path`; `--dir <path>` on the command line.

- [ ] **Step 1: Write the failing tests**

In `tests/test_dev_board.py`, add to the imports:

```python
import asyncio
import shutil

from fastapi.testclient import TestClient

from reels_api.main import create_app
from reels_api.models import utcnow
```

(merge `utcnow` into the existing `reels_api.models` import line). Append:

```python
def test_seed_jobs_have_two_favorites_one_past_its_time(tmp_path):
    jobs = dev_board.seed_jobs(make_settings(tmp_path), fake_clips(tmp_path))
    favorites = [j for j in jobs if j.favorite]
    assert [j.id for j in favorites] == ["seed01", "seed11"]
    assert all(j.starred_at is not None for j in favorites)
    now = utcnow()
    assert [j.expires_at > now for j in favorites] == [True, False]
    assert all(j.expires_at > now for j in jobs if not j.favorite)


def test_seeds_survive_startup(tmp_path):
    settings = make_settings(tmp_path)
    clips = fake_clips(tmp_path)
    app = create_app(settings=settings, pipeline=dev_board.DevPipeline(settings, clips, delay=0))
    seeds = dev_board.seed_jobs(settings, clips)
    asyncio.run(dev_board._add_all(app.state.store, seeds))
    with TestClient(app) as client:
        jobs = client.get("/jobs", headers={"X-API-Key": "test-key"}).json()["jobs"]
    assert {j["id"] for j in jobs} == {j.id for j in seeds}  # the 3-day-old favorite too


def test_make_root_keeps_a_given_dir(tmp_path):
    kept = tmp_path / "pile"
    assert dev_board.make_root(kept) == kept
    assert kept.is_dir()
    fresh = dev_board.make_root(None)
    try:
        assert fresh.is_dir()
        assert fresh.name.startswith("reels-dev-")
    finally:
        shutil.rmtree(fresh)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dev_board.py -q`
Expected: FAIL (no favorites among the seeds; no `make_root`).

- [ ] **Step 3: Implement**

`scripts/dev_board.py`:

Docstring, after the `--empty` usage line:

```
    python scripts/dev_board.py --empty --dir data/dev-board   # a pile that survives restarts
```

and after the paragraph ending "…and the others show whole.":

```
Seeds 1 and 11 are favorites. Seed 11 is three days old, so it only shows on
the favorites tab. With --dir the pile is kept in that directory (jobs.json and
the videos) and comes back on the next run. Use --empty with it: seeds are made
fresh on every run and win over a saved reel with the same id. In Docker, mount
a directory for it, e.g. add -v "${PWD}/data/dev-board:/dev-board" and pass
--dir /dev-board.
```

Constants: replace `SEED_MINUTES_AGO` and add `FAVORITE_SEEDS` after `NO_THUMBNAIL_SEED`:

```python
SEED_MINUTES_AGO = [0.5, 4, 12, 35, 61, 95, 130, 180, 220, 260, 300, 3 * 24 * 60]
NO_THUMBNAIL_SEED = 7
FAVORITE_SEEDS = (1, 11)  # starred (favorites spec 9): seed 1 is in the pile too, seed 11 only on favorites
```

`seed_jobs`: docstring `"""Finished jobs, newest first: eleven within the retention window and a three-day-old favorite."""`, and after `job.expires_at = job.finished_at + retention`:

```python
        if i in FAVORITE_SEEDS:
            job.favorite = True
            job.starred_at = job.finished_at + timedelta(minutes=1)
```

Add after `_add_all`:

```python
def make_root(keep_dir: Path | None) -> Path:
    """Where this run keeps its files: keep_dir, kept on exit so the pile survives, or a fresh temp dir."""
    if keep_dir is None:
        return Path(tempfile.mkdtemp(prefix="reels-dev-"))
    keep_dir.mkdir(parents=True, exist_ok=True)
    return keep_dir
```

`main`: add the option after `--empty`:

```python
    parser.add_argument("--dir", type=Path, help="keep the pile in this directory across runs (use with --empty)")
```

replace `root = Path(tempfile.mkdtemp(prefix="reels-dev-"))` with `root = make_root(args.dir)`, replace `clips_dir.mkdir()` with `clips_dir.mkdir(exist_ok=True)`, and replace the `finally` block:

```python
    finally:
        if args.dir is None:
            shutil.rmtree(root, ignore_errors=True)
```

- [ ] **Step 4: Run the whole suite**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/dev_board.py tests/test_dev_board.py
git commit -m "feat: dev board seeds two favorites and keeps its pile with --dir"
```

---

### Task 7: Board tabs: pile and favorites

**Files:**
- Modify: `reels_api/static/app.html` (tabs, favorites empty state), `reels_api/static/board.js` (rewrite), `reels_api/static/app.js`, `reels_api/static/icons.js` (`star`, `starFilled`), `reels_api/static/style.css`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `favorite`, `starred_at`, `expires_at` in the job JSON (Task 1); the dev board's favorite seeds for the manual check (Task 6).
- Produces:
  - `createBoard({ grid, empty, emptyFavorites, count, tabs: { pile, favorites }, favoritesCount, onOpen })`, returning:
    - `setReels(list)`
    - `getReels()`: every reel, both tabs
    - `getShown()`: the open tab's reels in its order
    - `has(id)`, `remove(id)`
    - `update(reel)`: replaces the reel with that id
    - `favoriteCount() -> number`
    - `tabOf(id) -> "pile" | "favorites" | null`
    - `setTab(name)`
    - `addPending(n)` (switches to pile), `finishPending(list)`, `removePending()`, `setDimmed(dimmed)`
    - `reveal(id)`: switches to the reel's tab
  - `icon("star")` (outline) and `icon("starFilled")`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`:

```python
def test_board_has_pile_and_favorites_tabs(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        page = client.get("/").text
    assert '<nav class="tabs" role="tablist" aria-label="reels">' in page
    for element_id in ("tab-pile", "tab-favorites", "favorites-n", "empty-favorites"):
        assert f'id="{element_id}"' in page, element_id
    assert "no favorites yet" in page
    assert "tap ★ on a reel to keep it after it leaves the pile." in page
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_board_has_pile_and_favorites_tabs -q`
Expected: FAIL (no tabs in the page).

- [ ] **Step 3: Implement**

`reels_api/static/icons.js`: add to `STROKE` (after `link2`):

```js
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
```

and to `FILL` (after `play`):

```js
  starFilled: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
```

`reels_api/static/app.html`: the start of `<main class="board">` becomes:

```html
<main class="board">
  <nav class="tabs" role="tablist" aria-label="reels">
    <button id="tab-pile" class="tab" type="button" role="tab" aria-selected="true">pile</button>
    <button id="tab-favorites" class="tab" type="button" role="tab" aria-selected="false"><span data-icon="starFilled"></span>favorites<span id="favorites-n" class="tab-count"></span></button>
  </nav>
  <div id="grid" class="grid"></div>
```

and after the `<div id="empty" …>…</div>` block, before `<footer class="board-foot">`:

```html
  <div id="empty-favorites" class="empty-favorites" hidden>
    <p class="empty-title">no favorites yet</p>
    <p class="empty-body">tap ★ on a reel to keep it after it leaves the pile.</p>
  </div>
```

Replace `reels_api/static/board.js` entirely:

```js
import { fillsBox, formatAge } from "./format.js";
import { icon } from "./icons.js";

function fadeInOnLoad(img) {
  img.addEventListener("load", () => img.classList.add("loaded"), { once: true });
}

// The pile tab: every reel but the favorites past their time (favorites spec 6).
function inPile(reel, now) {
  return !(reel.favorite && Date.parse(reel.expires_at) <= now);
}

// The favorites tab: newest star first.
function byNewestStar(a, b) {
  return Date.parse(b.starred_at) - Date.parse(a.starred_at);
}

// The grid of reels, the pile count, the empty states, the optimistic tiles (spec 6.1-6.4)
// and the pile and favorites tabs (favorites spec 6).
export function createBoard({ grid, empty, emptyFavorites, count, tabs, favoritesCount, onOpen }) {
  let reels = []; // every reel from the server, newest first
  let tab = "pile";
  const pending = []; // optimistic tiles while a paste is in flight, one per video (X links spec 7)
  const tiles = new Map(); // job id -> tile element, kept across refreshes and tab switches so images never reload

  function shown(now = Date.now()) {
    if (tab === "pile") return reels.filter((reel) => inPile(reel, now));
    return reels.filter((reel) => reel.favorite).sort(byNewestStar);
  }

  function buildTile(reel) {
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "tile";
    if (reel.thumbnail_url) {
      const img = document.createElement("img");
      img.alt = "";
      img.loading = "lazy";
      img.decoding = "async";
      fadeInOnLoad(img);
      img.addEventListener(
        "load",
        () => {
          if (fillsBox(img.naturalWidth, img.naturalHeight, 9, 16)) return;
          // Too wide or square to fill the tile: the whole thumbnail, over a blurred copy (from the cache).
          const backdrop = img.cloneNode();
          backdrop.className = "tile-backdrop";
          fadeInOnLoad(backdrop);
          img.before(backdrop);
          tile.classList.add("whole");
        },
        { once: true },
      );
      img.src = reel.thumbnail_url;
      tile.append(img);
    }
    if (reel.nsfw) {
      // Covered, not locked: the thumbnail is blurred and labelled (NSFW cover spec 4).
      tile.classList.add("nsfw");
      const label = document.createElement("span");
      label.className = "nsfw-label";
      label.textContent = "NSFW";
      tile.append(label);
    }
    const badge = document.createElement("span");
    badge.className = "badge";
    const hover = document.createElement("span");
    hover.className = "hover-row";
    hover.innerHTML = `<span class="hover-inner">${icon("play")}<span class="hover-label"></span></span>`;
    const star = document.createElement("span");
    star.className = "tile-star";
    star.innerHTML = icon("starFilled");
    tile.append(badge, hover, star);
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
    tile.querySelector(".tile-star").hidden = !reel.favorite;
    const what = reel.nsfw ? "play NSFW reel" : "play";
    tile.setAttribute("aria-label", `${what}${reel.favorite ? ", favorite" : ""}, ${ago}`);
  }

  function render() {
    const now = Date.now();
    const list = shown(now);
    const known = new Set(reels.map((reel) => reel.id));
    const visible = new Set(list.map((reel) => reel.id));
    for (const [id, tile] of tiles) {
      if (!known.has(id)) {
        tile.remove();
        tiles.delete(id);
      } else if (!visible.has(id)) {
        tile.remove(); // the other tab's: off the page, kept for when it shows again
      }
    }
    const onPile = tab === "pile";
    for (const tile of pending) tile.hidden = !onPile;
    let previous = pending.at(-1) || null; // reels go after the pending tiles
    list.forEach((reel, i) => {
      let tile = tiles.get(reel.id);
      if (!tile) {
        tile = buildTile(reel);
        tiles.set(reel.id, tile);
      }
      updateTile(tile, reel, onPile && i === 0, now);
      const expected = previous ? previous.nextSibling : grid.firstChild;
      if (tile !== expected) grid.insertBefore(tile, expected);
      previous = tile;
    });
    const pileTotal = reels.filter((reel) => inPile(reel, now)).length + pending.length;
    const favoriteTotal = reels.filter((reel) => reel.favorite).length;
    count.textContent = String(pileTotal);
    favoritesCount.textContent = favoriteTotal ? String(favoriteTotal) : "";
    for (const [name, button] of Object.entries(tabs)) button.setAttribute("aria-selected", String(name === tab));
    const total = onPile ? pileTotal : favoriteTotal;
    grid.hidden = total === 0;
    empty.hidden = !onPile || total !== 0;
    emptyFavorites.hidden = onPile || total !== 0;
    document.body.classList.toggle("is-empty", onPile && total === 0);
  }

  function setTab(name) {
    if (name === tab) return;
    tab = name;
    render();
    window.scrollTo(0, 0);
  }

  // The tab that shows a reel: pile when it is in both.
  function tabOf(id) {
    const reel = reels.find((r) => r.id === id);
    if (!reel) return null;
    return inPile(reel, Date.now()) ? "pile" : "favorites";
  }

  function dropPending() {
    const tile = pending.pop();
    if (tile) tile.remove();
  }

  for (const [name, button] of Object.entries(tabs)) {
    button.addEventListener("click", () => setTab(name));
  }

  return {
    setReels(list) {
      reels = list.slice();
      render();
    },
    // Every reel, both tabs.
    getReels() {
      return reels.slice();
    },
    // The open tab's reels, in its order: the player's list.
    getShown() {
      return shown();
    },
    has(id) {
      return tiles.has(id);
    },
    remove(id) {
      reels = reels.filter((reel) => reel.id !== id);
      render();
    },
    // A reel starred or un-starred on this phone: the server's new JSON for it.
    update(reel) {
      reels = reels.map((r) => (r.id === reel.id ? reel : r));
      render();
    },
    favoriteCount() {
      return reels.filter((reel) => reel.favorite).length;
    },
    tabOf,
    setTab,
    // Add n optimistic tiles at the top, after any already there. A paste shows on the pile.
    addPending(n = 1) {
      setTab("pile");
      for (let i = 0; i < n; i++) {
        const tile = document.createElement("div");
        tile.className = "tile pending";
        tile.innerHTML = '<span class="spinner" aria-hidden="true"></span><span class="badge">now</span>';
        const last = pending.at(-1);
        grid.insertBefore(tile, last ? last.nextSibling : grid.firstChild);
        pending.push(tile);
      }
      render();
    },
    // Swap one optimistic tile for the fresh list in one render, so the count never flickers.
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
    // Scroll to a reel, on the tab that shows it.
    reveal(id) {
      const where = tabOf(id);
      if (where) setTab(where);
      const tile = tiles.get(id);
      if (tile && tile.isConnected) tile.scrollIntoView({ block: "nearest", behavior: "smooth" });
    },
  };
}
```

`reels_api/static/app.js`:

Replace the `createBoard` call:

```js
const board = createBoard({
  grid: $("grid"),
  empty: $("empty"),
  emptyFavorites: $("empty-favorites"),
  count: $("count-n"),
  tabs: { pile: $("tab-pile"), favorites: $("tab-favorites") },
  favoritesCount: $("favorites-n"),
  // The player gets the open tab's reels, so swiping stays in that tab (favorites spec 6).
  onOpen: (id, tile) => player.open(board.getShown(), id, { from: tile }),
});
```

In `onDone`, replace `player.addReels(jobs);` with `player.addReels(board.getShown());`.

In `refresh`, replace `player.addReels(jobs);` with `player.addReels(board.getShown());`.

Replace the first line of `openLinkedReel`'s body:

```js
async function openLinkedReel(id) {
  const where = board.tabOf(id);
  if (where) {
    board.setTab(where); // an old favorite opens on the favorites tab (favorites spec 6)
    if (player.open(board.getShown(), id, { gesture: false, push: false })) return;
  }
```

(the rest of the function stays as it is).

`reels_api/static/style.css`: after the `.tile.pending .badge` rule add:

```css
/* A favorite's mark (favorites spec 6). */
.tile-star {
  position: absolute;
  top: 5px;
  right: 5px;
  display: flex;
  padding: 3px;
  border-radius: 999px;
  background: var(--scrim-badge);
  color: var(--accent-bright);
  pointer-events: none;
}
.tile-star .icon { width: 10px; height: 10px; }

/* ---- tabs: pile and favorites (favorites spec 6) ---- */

.tabs { display: flex; gap: 6px; padding: 0 2px 10px; }
.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
  font: 600 13px var(--font);
  color: var(--ink-50);
}
.tab .icon { width: 12px; height: 12px; }
.tab[aria-selected="true"] { border-color: transparent; background: var(--ink); color: var(--bg); }
.tab-count { font: 500 11px var(--mono); }
.tab-count:empty { display: none; }
.empty-favorites {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 64px 40px;
  text-align: center;
}
```

and inside the first `@media (min-width: 700px)` block (the desktop board), after `.grid { max-width: 1100px; margin: 0 auto; gap: 12px; }`:

```css
  .tabs { max-width: 1100px; margin: 0 auto; padding: 0 0 16px; }
  .tile-star { top: 8px; right: 8px; }
```

- [ ] **Step 4: Run the tests and the syntax check**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.
Run the Global Constraints syntax check with `<files>` = `board.js app.js icons.js`.
Expected: no `SYNTAX ERROR` lines.

- [ ] **Step 5: Check by hand**

Start the dev board in Docker (PowerShell, repo root; `docker build -t reels-dev .` first if the image doesn't exist):

```powershell
docker run --rm -p 127.0.0.1:8000:8000 -e PYTHONPATH=/app `
  -v "${PWD}/reels_api:/app/reels_api:ro" -v "${PWD}/scripts:/app/scripts:ro" `
  reels-dev python scripts/dev_board.py --host 0.0.0.0
```

Open `http://localhost:8000/` in Chrome, log in with `dev`, and check at phone width (DevTools device mode) and at desktop width:
- **Tab labels:** `pile` is selected, and the favorites tab reads `favorites 2`.
- **Pile tab:** "11 in the pile", 11 tiles, seed 1's tile (second) has a ★ in its corner.
- **Favorites tab:** seed 1 then the 3-day-old seed 11 ("3d"), and no play icon on the first badge. Switching back and forth doesn't reload thumbnails.
- **Swiping stays in the tab:** open a reel from favorites and swipe (phone) or press → (desktop); only the 2 favorites come up.
- **Paste switches tabs:** on the favorites tab, paste `https://vm.tiktok.com/abc/`. The board switches to pile with the loading tile on top.
- **Link to an old favorite:** open `http://localhost:8000/?reel=seed11`. It opens on the favorites tab.
- **Empty favorites:** with the docker command plus `--empty`, the favorites tab shows "no favorites yet", and the pile tab shows the empty pile as before.

- [ ] **Step 6: Commit**

```bash
git add reels_api/static/app.html reels_api/static/board.js reels_api/static/app.js reels_api/static/icons.js reels_api/static/style.css tests/test_web.py
git commit -m "feat: the board has pile and favorites tabs, and starred tiles show a star"
```

---

### Task 8: Delete in the player, with undo

**Files:**
- Modify: `reels_api/static/toast.js` (action button), `reels_api/static/api.js` (`deleteJob`), `reels_api/static/player.js` (`onDelete`, `remove`), `reels_api/static/app.js` (pending deletes), `reels_api/static/app.html` (delete buttons), `reels_api/static/icons.js` (`trash`), `reels_api/static/style.css`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes: `DELETE /jobs/{id}` (Task 5); `board.remove`, `board.getReels`, `board.setReels` (Task 7).
- Produces:
  - `showToast(message, { error, action: { label, onClick, onEnd } })`. `onClick` runs on a tap. `onEnd` runs instead when the toast times out or another toast replaces it. A toast with an action stays 5 s.
  - `deleteJob(id, { keepalive }) -> Promise<void>`: resolves on `2xx` and on `404`, throws otherwise.
  - `createPlayer({ …, onDelete })`, where `onDelete(reel)` runs on the delete button; `player.remove(id)`.
  - In `app.js`: `deleteReel(reel, message)`, used by Task 9 for un-starring an old reel.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_web.py`:

```python
def test_board_player_has_delete(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        page = client.get("/").text
    assert page.count('data-action="delete"') == 2  # the phone's top bar and the desktop panel


def test_view_only_page_has_no_favorite_or_delete(web_app):
    with TestClient(web_app()) as client:
        reel = _done_reel(client)
        page = client.get("/", params={"reel": reel["id"], "k": reel["share_key"]}).text
    assert 'data-action="delete"' not in page
    assert 'data-action="favorite"' not in page
```

- [ ] **Step 2: Run them to verify the first fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py -q -k "delete"`
Expected: `test_board_player_has_delete` FAILS (count 0); `test_view_only_page_has_no_favorite_or_delete` passes and must keep passing.

- [ ] **Step 3: Implement**

`reels_api/static/icons.js`, add to `STROKE` after `link2`:

```js
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>',
```

Replace `reels_api/static/toast.js` entirely:

```js
import { icon } from "./icons.js";

const VISIBLE_MS = 2500;
const ACTION_MS = 5000; // long enough to reach "undo" (favorites spec 8)
let hideTimer = 0;
let active = null; // the action of the toast on screen, until it is tapped or its toast ends

// The toast on screen ended without its button being tapped: it timed out or was replaced.
function endActive() {
  const ended = active;
  active = null;
  if (ended && ended.onEnd) ended.onEnd();
}

// One toast at a time; a new one replaces the current one and restarts the timer (spec 8.1).
// action {label, onClick, onEnd}: a button, and 5 seconds instead of 2.5 (favorites spec 8).
// onClick runs on a tap; onEnd runs instead when the toast times out or another replaces it.
export function showToast(message, { error = false, action = null } = {}) {
  const root = document.getElementById("toast");
  endActive();
  const mark = document.createElement("span");
  mark.className = error ? "toast-mark error" : "toast-mark";
  mark.innerHTML = icon(error ? "circleAlert" : "check");
  const label = document.createElement("span");
  label.className = "toast-label";
  label.textContent = message;
  root.replaceChildren(mark, label);
  if (action) {
    active = action;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toast-action";
    button.textContent = action.label;
    button.addEventListener("click", () => {
      if (active !== action) return;
      active = null;
      clearTimeout(hideTimer);
      root.classList.remove("show");
      action.onClick();
    });
    root.append(button);
  }
  root.classList.add("show");
  clearTimeout(hideTimer);
  hideTimer = setTimeout(
    () => {
      root.classList.remove("show");
      endActive();
    },
    action ? ACTION_MS : VISIBLE_MS,
  );
}
```

`reels_api/static/api.js`, append:

```js
// Deletes a reel for everyone (favorites spec 4). A 404 means it is already gone, which is fine.
// keepalive: the request outlives the page (sent while the page is being left).
export async function deleteJob(id, { keepalive = false } = {}) {
  const response = await api(`/jobs/${encodeURIComponent(id)}`, { method: "DELETE", keepalive });
  if (!response.ok && response.status !== 404) throw new Error(`DELETE /jobs/${id} failed: ${response.status}`);
}
```

`reels_api/static/app.html`: in the phone chrome, replace `<span class="chrome-spacer"></span>` with:

```html
              <div class="chrome-end">
                <button class="round-btn" type="button" data-action="delete" aria-label="delete" data-icon="trash"></button>
              </div>
```

and in `<aside class="player-panel">`, after the existing `<div class="panel-row">…</div>` (Download / Copy link), inside `panel-actions`:

```html
          <div class="panel-row">
            <button class="btn" type="button" data-action="delete"><span data-icon="trash"></span>delete</button>
          </div>
```

`reels_api/static/player.js`:

Change the signature:

```js
export function createPlayer({ root, onGone, onDelete = null, standalone = false }) {
```

After `addReels`, add:

```js
  // A reel deleted on this phone: drop it and show the next one, or close when none are left (favorites spec 7).
  function remove(id) {
    if (!isOpen()) return;
    const i = reels.findIndex((reel) => reel.id === id);
    if (i === -1) return;
    const wasCurrent = i === index;
    reels.splice(i, 1);
    if (!reels.length) {
      close();
      return;
    }
    if (i < index) index -= 1;
    else if (wasCurrent && index >= reels.length) index = reels.length - 1;
    if (wasCurrent) {
      show(index);
      play();
      if (!standalone) history.replaceState({ reel: current().id }, "", reelPath(current()));
    } else {
      renderNav();
    }
  }
```

In `actions`, add after `reveal: uncover,`:

```js
    delete: () => {
      if (onDelete) onDelete(current());
    },
```

and return `{ open, close, isOpen, addReels, remove }`.

`reels_api/static/app.js`:

Imports: `import { Unauthorized, deleteJob, getJob, listJobs, logout } from "./api.js";`

`createPlayer` call:

```js
const player = createPlayer({
  root: $("player"),
  onGone: (id) => board.remove(id),
  onDelete: (reel) => deleteReel(reel, "deleted"),
});
```

Add after the `createPlayer` call:

```js
// ---- delete with undo (favorites spec 8)

// Reels deleted on this phone whose undo toast is up or whose DELETE is on its way.
// Every list from the server leaves them out.
const pendingDeletes = new Map(); // id -> {reel, sending}
const newestFirst = (a, b) => Date.parse(b.finished_at) - Date.parse(a.finished_at);

function putBack(reel) {
  board.setReels([...board.getReels().filter((r) => r.id !== reel.id), reel].sort(newestFirst));
}

// Gone from this phone now; the DELETE goes when the toast ends, unless undo is tapped first.
function deleteReel(reel, message) {
  pendingDeletes.set(reel.id, { reel, sending: false });
  board.remove(reel.id);
  player.remove(reel.id);
  showToast(message, {
    action: {
      label: "undo",
      onClick: () => {
        const entry = pendingDeletes.get(reel.id);
        if (!entry || entry.sending) {
          showToast("too late. it's deleted.", { error: true });
          return;
        }
        pendingDeletes.delete(reel.id);
        putBack(reel); // an open player gets it back next time it opens
      },
      onEnd: () => sendDelete(reel.id),
    },
  });
}

async function sendDelete(id, { keepalive = false } = {}) {
  const entry = pendingDeletes.get(id);
  if (!entry || entry.sending) return; // undone, or already on its way
  entry.sending = true;
  try {
    await deleteJob(id, { keepalive });
    pendingDeletes.delete(id);
  } catch (err) {
    pendingDeletes.delete(id);
    if (err instanceof Unauthorized) return; // api() is already reloading
    putBack(entry.reel);
    showToast("couldn't delete. try again.", { error: true });
  }
}

// Leaving the page ends the undo: send now, in requests that outlive the page.
function flushDeletes() {
  for (const id of pendingDeletes.keys()) sendDelete(id, { keepalive: true });
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") flushDeletes();
});
window.addEventListener("pagehide", flushDeletes);
```

Replace `loadJobs`:

```js
// The pile from the server without the reels being deleted here, or null when it could not be loaded.
async function loadJobs() {
  try {
    return (await listJobs()).filter((job) => !pendingDeletes.has(job.id));
  } catch (_) {
    return null;
  }
}
```

`reels_api/static/style.css`:

In the `.chrome-top` rule add `gap: 10px;`. Replace `.chrome-spacer { flex: none; width: 34px; }` with:

```css
.chrome-top .source { flex: 1; overflow: hidden; }
.chrome-top .js-source { overflow: hidden; text-overflow: ellipsis; }
.chrome-end { display: flex; flex: none; gap: 8px; }
```

After `.toast-mark.error .icon { … }` add:

```css
.toast-label { flex: 1; min-width: 0; }
.toast-action {
  flex: none;
  margin: -6px -8px -6px 0;
  padding: 6px 10px;
  border-radius: 999px;
  font: 700 13.5px var(--font);
  color: var(--accent-bright);
  pointer-events: auto; /* the toast itself lets taps through */
}
```

- [ ] **Step 4: Run the tests and the syntax check**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.
Syntax check with `<files>` = `toast.js api.js player.js app.js icons.js`.
Expected: no `SYNTAX ERROR` lines.

- [ ] **Step 5: Check by hand**

Dev board as in Task 7, Step 5. In Chrome at phone width and at desktop width:
- **Phone layout:** a reel's top bar shows ✕, the info line (left-aligned now), and a bin on the right. A long info line ends in "…" instead of pushing the bin off.
- **Delete, then wait:** tap the bin on a reel in the middle. The next reel plays, the tile is gone, and a toast "deleted" with "undo" stays about 5 s. Reload after it goes: the reel is still gone.
- **Delete, then undo:** delete another reel, tap undo within 5 s. Its tile is back in its old place. Close the player and reopen: it's in the swipe order again.
- **Deleting the last one:** delete the only reel of a tab's list (e.g. both favorites, one at a time, from the favorites tab). The player closes after the last.
- **Leaving the page:** delete a reel and switch to another browser tab within 5 s, then come back and reload. The reel is gone.
- **Undo after leaving:** delete, switch tabs and come back while the toast still shows, tap undo. "too late. it's deleted."
- **Offline:** DevTools Network → Offline, delete a reel, wait 5 s. "couldn't delete. try again." and the tile comes back. Back online.
- **Another browser:** with the same pile open in a second (private) window logged in, a delete disappears there within 30 s.
- **Share link:** the share link of a deleted reel shows "this reel has expired".
- **Other toasts:** "link copied" still disappears after about 2.5 s with no button.
- **Desktop:** the overlay's panel has a "delete" row that does the same.

- [ ] **Step 6: Commit**

```bash
git add reels_api/static/toast.js reels_api/static/api.js reels_api/static/player.js reels_api/static/app.js reels_api/static/app.html reels_api/static/icons.js reels_api/static/style.css tests/test_web.py
git commit -m "feat: delete a reel from the player, with a 5-second undo"
```

---

### Task 9: Star in the player

**Files:**
- Modify: `reels_api/static/player.js` (`onFavorite`, `renderStar`, `update`), `reels_api/static/format.js` (`sourceLine`), `reels_api/static/api.js` (`setFavorite`), `reels_api/static/app.js` (`toggleStar`, `star`), `reels_api/static/app.html` (star buttons), `reels_api/static/style.css`
- Test: `tests/test_web.py`

**Interfaces:**
- Consumes:
  - `PUT` / `DELETE /jobs/{id}/favorite` (Task 4)
  - `board.update`, `board.favoriteCount` (Task 7)
  - `deleteReel(reel, message)`, `showToast`'s `action`, `.chrome-end` (Task 8)
- Produces:
  - `createPlayer({ …, onFavorite })`, where `onFavorite(reel, on)` runs on the star button
  - `player.update(reel)`
  - `setFavorite(id, on) -> Promise<job | {error}>`
  - `sourceLine(reel)` ends `★ kept` for a favorite

- [ ] **Step 1: Write the failing test**

Append to `tests/test_web.py`:

```python
def test_board_player_has_the_star(web_app):
    with https_client(web_app()) as client:
        client.post("/web/login", json={"passcode": PASSCODE})
        page = client.get("/").text
    assert page.count('data-action="favorite"') == 2
    assert page.count('aria-label="add to favorites"') == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_web.py::test_board_player_has_the_star -q`
Expected: FAIL (count 0).

- [ ] **Step 3: Implement**

`reels_api/static/app.html`: inside `<div class="chrome-end">`, before the delete button:

```html
                <button class="round-btn star" type="button" data-action="favorite" aria-pressed="false" aria-label="add to favorites"><span class="star-icon"></span></button>
```

and in the panel's delete row, before the delete button:

```html
            <button class="btn star" type="button" data-action="favorite" aria-pressed="false" aria-label="add to favorites"><span class="star-icon"></span>favorite</button>
```

`reels_api/static/format.js`, replace `sourceLine`:

```js
// "TikTok · 0:19 · gone in 6h", or "… · ★ kept" for a favorite (favorites spec 7), leaving out parts that are unknown.
export function sourceLine(reel, now = Date.now()) {
  const life = reel.favorite ? "★ kept" : formatExpiry(reel.expires_at, now);
  return [SOURCE_NAME[reel.source] || reel.source, formatDuration(reel.duration_seconds), life]
    .filter(Boolean)
    .join(" · ");
}
```

`reels_api/static/api.js`, append:

```js
// Stars or un-stars a reel (favorites spec 5): the reel, or {error} with the server's error code.
export async function setFavorite(id, on) {
  const response = await api(`/jobs/${encodeURIComponent(id)}/favorite`, { method: on ? "PUT" : "DELETE" });
  const body = await response.json().catch(() => ({}));
  if (response.ok) return body;
  return { error: body.error || "processing_failed" };
}
```

`reels_api/static/player.js`:

Signature:

```js
export function createPlayer({ root, onGone, onDelete = null, onFavorite = null, standalone = false }) {
```

After `const cover = root.querySelector(".nsfw-cover");`:

```js
  const starButtons = [...root.querySelectorAll('[data-action="favorite"]')];
```

After `renderVolume`:

```js
  // Filled and pressed while the reel is a favorite (favorites spec 7).
  function renderStar() {
    const on = Boolean(current() && current().favorite);
    for (const button of starButtons) {
      button.classList.toggle("is-on", on);
      button.setAttribute("aria-pressed", String(on));
      button.setAttribute("aria-label", on ? "remove from favorites" : "add to favorites");
      button.querySelector(".star-icon").innerHTML = icon(on ? "starFilled" : "star");
    }
  }
```

In `show`, after `setText(".js-caption", reel.caption || reel.title || "");`:

```js
    renderStar();
```

After `remove`:

```js
  // A reel starred or un-starred on this phone: its new JSON, redrawn if it is showing.
  function update(reel) {
    const i = reels.findIndex((r) => r.id === reel.id);
    if (i === -1) return;
    reels[i] = reel;
    if (i === index && isOpen()) {
      setText(".js-source", sourceLine(reel));
      renderStar();
    }
  }
```

In `actions`, after `delete`:

```js
    favorite: () => {
      if (onFavorite) onFavorite(current(), !current().favorite);
    },
```

and return `{ open, close, isOpen, addReels, remove, update }`.

`reels_api/static/app.js`:

Imports: `import { Unauthorized, deleteJob, getJob, listJobs, logout, setFavorite } from "./api.js";`

`createPlayer` call gains `onFavorite: (reel, on) => toggleStar(reel, on),`.

After `flushDeletes`' listeners, add:

```js
// ---- star (favorites spec 8)

const starring = new Set(); // reels with a star or un-star on its way: another tap waits for it

// Un-starring a reel past its time is a delete: only the star kept it.
function toggleStar(reel, on) {
  if (!on && Date.parse(reel.expires_at) <= Date.now()) {
    deleteReel(reel, "removed");
    return;
  }
  star(reel, on);
}

async function star(reel, on) {
  if (starring.has(reel.id)) return;
  starring.add(reel.id);
  let job;
  try {
    job = await setFavorite(reel.id, on);
  } catch (err) {
    if (err instanceof Unauthorized) return; // api() is already reloading
    job = { error: "network" };
  } finally {
    starring.delete(reel.id);
  }
  if (job.error === "favorites_full") {
    showToast(`favorites are full (${board.favoriteCount()}). remove one first.`, { error: true });
    return;
  }
  if (job.error) {
    showToast("couldn't save that. try again.", { error: true });
    return;
  }
  board.update(job);
  player.update(job);
  if (on) showToast("added to favorites");
  else showToast("un-starred", { action: { label: "undo", onClick: () => star(job, true) } });
}
```

`reels_api/static/style.css`, after `.chrome-end { … }`:

```css
.star-icon { display: flex; }
.player .star.is-on { color: var(--accent-bright); }
```

- [ ] **Step 4: Run the tests and the syntax check**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.
Syntax check with `<files>` = `player.js format.js api.js app.js`.
Expected: no `SYNTAX ERROR` lines.

- [ ] **Step 5: Check by hand**

Dev board as in Task 7, Step 5. In Chrome at phone width and at desktop width:
- **Star:** open a pile reel that isn't starred and tap ☆. It turns into a filled ★ in the accent colour, the info line ends "★ kept", and the toast says "added to favorites". The favorites tab count goes up, and the tile shows a ★.
- **Un-star within its hours:** tap ★ on seed 1. The toast says "un-starred" with undo. Tap undo: starred again, now first on the favorites tab.
- **Un-star an old favorite:** tap ★ on seed 11 (favorites tab). The toast says "removed" with undo, and the player moves on. Undo brings it back; letting the toast end deletes it for good (reload).
- **Favorites full:** restart the dev board with `-e MAX_FAVORITES=2` added to `docker run`. Starring a third reel says "favorites are full (2). remove one first." and the star stays empty.
- **Survives a restart:** run with `--empty --dir /dev-board` and `-v "${PWD}/data/dev-board:/dev-board"`. Paste two links, star one, delete the other, then stop and start the same command. The starred reel is back and the deleted one isn't.
- **View-only page:** a share link opened in a private window has no star and no bin.

- [ ] **Step 6: Commit**

```bash
git add reels_api/static/player.js reels_api/static/format.js reels_api/static/api.js reels_api/static/app.js reels_api/static/app.html reels_api/static/style.css tests/test_web.py
git commit -m "feat: star and un-star a reel from the player"
```

---

### Task 10: Docs

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `scripts/deploy.ps1` (header comment)

**Interfaces:**
- Consumes: everything above. No code changes.

- [ ] **Step 1: README.md**

- **Intro (lines 11–12):** replace "Jobs live in memory; files live on disk for `RETENTION_HOURS`, and only the newest `MAX_VIDEOS` are kept." with:

  > Finished reels stay for `RETENTION_HOURS`, at most the newest `MAX_VIDEOS`, and survive restarts. Starred reels (favorites) stay until someone un-stars them.

- **Run locally (line 85):** replace "Videos are stored in `./data/`, and every restart empties the pile (see [The board](#the-board-phone-web-page))." with:

  > Videos and the list of reels (`jobs.json`) are stored in `./data/`, so the pile survives restarts.

- **The board:** add two bullets after **Save**:

  > - **Favorites**: the ☆ in the player (top right on a phone, under Download on a desktop) keeps a reel past `RETENTION_HOURS` until someone un-stars it, up to `MAX_FAVORITES` (default 200). Favorites have their own tab. The pile tab shows every reel still within its hours, starred ones with a ★. Un-starring a reel older than `RETENTION_HOURS` removes it. There is one list of favorites for everyone.
  > - **Delete**: the bin in the player deletes a reel for everyone, starred or not. "undo" in the toast takes it back for 5 seconds; after that it's gone, and its share links say "this reel has expired".

- **The board, restart paragraph:** replace the paragraph starting "Restarting the app empties the pile" with:

  > The pile survives restarts and deploys: the list of reels is saved to `jobs.json` next to the videos whenever it changes and read back on startup. Only downloads still running at the time are lost; paste those again. On startup and every hour the app also deletes stored files that belong to no reel, such as one left behind by a timed-out download. If `jobs.json` can't be read, it is renamed to `jobs.json.bad` and the pile starts empty.

- **JSON API table:** add rows after `GET /jobs/{id}`:

  > | `PUT /jobs/{id}/favorite` | Stars a done reel: it stays past `expires_at` until un-starred. `200` and the job. `409 favorites_full` when `MAX_FAVORITES` reels are starred. |
  > | `DELETE /jobs/{id}/favorite` | Un-stars it: `200` and the job. A reel already past its `expires_at` then goes at the next hourly check. |
  > | `DELETE /jobs/{id}` | Deletes a done reel and its files now, starred or not. `204`. |

  In the `GET /jobs/{id}` row, add `favorite` and `starred_at` to the list of done fields. After the table, add: "The three new routes answer `404 not_found` for anything that isn't a done reel, and never open with `?k=`."

- **Failure codes paragraph:** add the sentence "Starring can also answer `409 favorites_full`."

- **Configuration table:**
  - `RETENTION_HOURS`: "How long a finished reel is kept, unless starred. Checked hourly, so a reel can last up to an hour longer."
  - New row after `MAX_VIDEOS`: `` | `MAX_FAVORITES` | `200` | Most starred reels. They stay past `RETENTION_HOURS` and don't count toward `MAX_VIDEOS`. | ``

- **Trying the board:** after "…and one of the seeded reels is one.", add "Seeds 1 and 11 are favorites; seed 11 is three days old, so it only shows on the favorites tab." After "Add `--empty` to start with an empty pile.", add:

  > To keep the pile across runs, add `--dir /dev-board` and the mount `-v "${PWD}/data/dev-board:/dev-board"` (with `--empty`: seeds are made fresh each run and win over saved reels with the same id).

- **Deploy:** replace "The VM keeps its `.env`, `data/` and HTTPS certificate, but the restart empties the pile." with "The VM keeps its `.env`, `data/` (the videos and `jobs.json`, so the pile survives) and HTTPS certificate."

- [ ] **Step 2: CLAUDE.md**

- **Commands, dev_board bullet:** after "…and seed 3 is one.", add "Seeds 1 and 11 are favorites (11 is three days old, so only on the favorites tab). `--empty --dir <path>` keeps the pile across runs (in Docker, mount a directory for it)."

- **Architecture:** replace the "**State is in memory only.**" paragraph with:

  > **State: memory first, `jobs.json` second.** `JobStore` (a dict) is the source of truth. `jobs_file.py` writes its done jobs to `STORAGE_DIR/jobs.json` (temp file + `os.replace`, one save at a time under `JobManager._save_lock`) after a reel finishes, a star or un-star, a delete and every sweep. `JobManager.start` reads it back first, adding to what's already in the store (anything seeded wins), then sweeps, applies the cap and saves. A failed write is logged and ignored. An unreadable file becomes `jobs.json.bad` and the pile starts empty. Files on disk are tied to jobs purely by filename stem (`<id>.mp4`, `<id>.jpg`; `STORED_SUFFIXES` in `jobs.py`); `jobs.json` stores no paths. Four things delete files:
  > - the sweeper (hourly, `SWEEP_INTERVAL_SECONDS`, drops jobs past `RETENTION_HOURS`, default 12, but never favorites);
  > - `enforce_video_cap` (after each finished job, keeps the newest `MAX_VIDEOS` non-favorites);
  > - `JobManager.delete` (`DELETE /jobs/{id}`);
  > - `_remove_untracked_files` (on startup and each hourly sweep, immediately deletes any orphan, meaning a file or temp dir whose stem is not a known job; there is deliberately no age grace period, since `/files/` can't serve an orphan anyway).
  >
  > So a restart or deploy keeps the pile; only queued and running downloads are lost. **Favorites** (`Job.favorite`, `starred_at`; `JobManager.set_favorite`, at most `MAX_FAVORITES`) are one list for everyone (favorites spec, `docs/superpowers/specs/2026-09-24-favorites-and-delete-design.md`).

- **Errors:** "maps `unsupported_url`→400, `too_many_jobs`→429, `favorites_full`→409, anything else→500".

- **Frontend paragraph:** after the sentence about pending tiles, add:

  > The board has two tabs (`board.js`). **pile** is every reel except favorites past `expires_at`; **favorites** is newest `starred_at` first. The player gets the open tab's list (`board.getShown()`). Star and delete are in the player and report through `onFavorite`/`onDelete`; `app.js` calls the API. Delete, and un-starring a reel past its time, wait behind an "undo" toast (`showToast`'s `action`; its `onEnd` sends the `DELETE`), and leaving the page sends them at once with `keepalive`. The view-only page has neither button, a deliberate difference from `app.html`'s player.

- **Things we learned, "Anything seeding jobs…":** append "A seed also wins over a saved reel with the same id."
- **Things we learned, "Adding a new stored file type…":** append "`jobs.json` is not one: it's a single file for the whole pile, and its suffix is deliberately not in `STORED_SUFFIXES`."

- [ ] **Step 3: scripts/deploy.ps1**

In the header comment, replace "The VM keeps its .env, data/ and HTTPS certificate. Running jobs and the Recent feed are lost." with "The VM keeps its .env, data/ (videos and jobs.json, so the pile survives) and HTTPS certificate. Only running downloads are lost."

- [ ] **Step 4: Check nothing stale is left**

Run (Git Bash): `grep -n -i -E "empties the pile|wipes the whole pile|in memory only|Recent feed" README.md CLAUDE.md scripts/deploy.ps1`
Expected: no output.
Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md scripts/deploy.ps1
git commit -m "docs: favorites, delete and a pile that survives restarts in README and CLAUDE.md"
```
