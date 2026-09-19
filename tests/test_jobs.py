import asyncio
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reels_api import jobs as jobs_module
from reels_api.jobs import JobManager, JobStore, new_job_id
from reels_api.models import ErrorCode, Job, JobError, JobResult, JobStatus, Source
from tests.conftest import make_settings

# Every `async def` test below carries @pytest.mark.anyio; the anyio pytest
# plugin (installed with the anyio package) runs them on the asyncio backend
# chosen by the `anyio_backend` fixture in conftest.py.


class FakePipeline:
    def __init__(self, settings, behaviour="ok", delay=0.0):
        self.settings = settings
        self.behaviour = behaviour
        self.delay = delay
        self.finished = threading.Event()

    def run(self, job, set_status):
        try:
            return self._run(job, set_status)
        finally:
            self.finished.set()

    def _run(self, job, set_status):
        set_status(JobStatus.DOWNLOADING)
        if self.delay:
            time.sleep(self.delay)
        set_status(JobStatus.PROCESSING)
        if self.behaviour == "job_error":
            raise JobError(ErrorCode.PRIVATE_OR_REMOVED)
        if self.behaviour == "crash":
            raise RuntimeError("boom")
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.storage_dir / f"{job.id}.mp4"
        path.write_bytes(b"\x00" * 50)
        return JobResult(path, "T", job.source, 1.0, 50, 10, 20)


async def wait_finished(store: JobStore, job_id: str, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = await store.get(job_id)
        if job and job.status in (JobStatus.DONE, JobStatus.FAILED):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("job did not finish")


def test_new_job_id_shape():
    ids = {new_job_id() for _ in range(50)}
    assert len(ids) == 50
    for i in ids:
        assert 8 <= len(i) <= 12
        assert all(c.isalnum() or c in "-_" for c in i)


@pytest.mark.anyio
async def test_store_roundtrip():
    store = JobStore()
    job = Job(id="a", url="u", source=Source.TIKTOK)
    await store.add(job)
    assert await store.get("a") is job
    assert await store.all() == [job]
    await store.remove("a")
    assert await store.get("a") is None
    await store.remove("a")  # idempotent


@pytest.mark.anyio
async def test_submit_and_complete(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        [job] = await manager.submit("https://vm.tiktok.com/x/")
        assert job.status == JobStatus.QUEUED
        assert job.source == Source.TIKTOK
        done = await wait_finished(store, job.id)
        assert done.status == JobStatus.DONE
        assert done.result.file_path.exists()
        assert done.finished_at is not None
        assert done.expires_at - done.finished_at == timedelta(hours=settings.retention_hours)
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_submit_rejects_bad_url(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    with pytest.raises(JobError) as exc:
        await manager.submit("https://youtube.com/watch?v=1")
    assert exc.value.code == ErrorCode.UNSUPPORTED_URL


@pytest.mark.anyio
async def test_submit_rejects_when_queue_full(tmp_path):
    settings = make_settings(tmp_path, max_queue=2)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    # not started: nothing drains the queue
    await manager.submit("https://vm.tiktok.com/1/")
    await manager.submit("https://vm.tiktok.com/2/")
    with pytest.raises(JobError) as exc:
        await manager.submit("https://vm.tiktok.com/3/")
    assert exc.value.code == ErrorCode.TOO_MANY_JOBS


@pytest.mark.anyio
async def test_job_error_is_recorded(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings, "job_error"), store)
    await manager.start()
    try:
        [job] = await manager.submit("https://vm.tiktok.com/x/")
        done = await wait_finished(store, job.id)
        assert done.status == JobStatus.FAILED
        assert done.error == ErrorCode.PRIVATE_OR_REMOVED
        assert done.message
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_crash_is_processing_failed_and_worker_survives(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    pipeline = FakePipeline(settings, "crash")
    manager = JobManager(settings, pipeline, store)
    await manager.start()
    try:
        [job1] = await manager.submit("https://vm.tiktok.com/x/")
        done1 = await wait_finished(store, job1.id)
        assert done1.status == JobStatus.FAILED
        assert done1.error == ErrorCode.PROCESSING_FAILED

        pipeline.behaviour = "ok"
        [job2] = await manager.submit("https://vm.tiktok.com/y/")
        done2 = await wait_finished(store, job2.id)
        assert done2.status == JobStatus.DONE
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_module, "TIMEOUT_GRACE_SECONDS", 0)
    settings = make_settings(tmp_path, job_timeout_seconds=1)
    store = JobStore()
    pipeline = FakePipeline(settings, delay=3.0)
    manager = JobManager(settings, pipeline, store)
    await manager.start()
    try:
        [job] = await manager.submit("https://vm.tiktok.com/x/")
        done = await wait_finished(store, job.id, timeout=4)
        assert done.status == JobStatus.FAILED
        assert done.error == ErrorCode.TIMEOUT

        # The abandoned thread finishes later; it must not overwrite the outcome.
        assert await asyncio.to_thread(pipeline.finished.wait, 5)
        assert done.status == JobStatus.FAILED
        assert done.error == ErrorCode.TIMEOUT
        assert done.result is None
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_sweep_removes_expired_and_stray_dirs(tmp_path):
    settings = make_settings(tmp_path, retention_hours=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    settings.storage_dir.mkdir(parents=True)
    settings.temp_dir.mkdir(parents=True)

    now = datetime.now(UTC)
    old_file = settings.storage_dir / "old.mp4"
    old_file.write_bytes(b"x")
    old_thumb = settings.storage_dir / "old.jpg"
    old_thumb.write_bytes(b"x")
    old = Job(id="old", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    old.finished_at = now - timedelta(hours=2)
    old.result = JobResult(old_file, "T", Source.TIKTOK, 1.0, 1, 1, 1, thumbnail_path=old_thumb)

    fresh_file = settings.storage_dir / "fresh.mp4"
    fresh_file.write_bytes(b"x")
    fresh = Job(id="fresh", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    fresh.finished_at = now - timedelta(minutes=10)
    fresh.result = JobResult(fresh_file, "T", Source.TIKTOK, 1.0, 1, 1, 1)

    failed = Job(id="failed", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
    failed.finished_at = now - timedelta(hours=2)

    running = Job(id="running", url="u", source=Source.TIKTOK, status=JobStatus.DOWNLOADING)

    for j in (old, fresh, failed, running):
        await store.add(j)

    (settings.temp_dir / "running").mkdir()
    (settings.temp_dir / "stray").mkdir()
    (settings.temp_dir / "stray" / "source.mp4.part").write_bytes(b"x")

    await manager.sweep(now=now)

    assert await store.get("old") is None
    assert not old_file.exists()
    assert not old_thumb.exists()
    assert await store.get("failed") is None
    assert await store.get("fresh") is not None
    assert fresh_file.exists()
    assert await store.get("running") is not None
    assert (settings.temp_dir / "running").exists()
    assert not (settings.temp_dir / "stray").exists()


@pytest.mark.anyio
async def test_submit_extracts_url_from_share_text(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    [job] = await manager.submit("Check this out! https://vm.tiktok.com/ZMabc123/ #fyp")
    assert job.url == "https://vm.tiktok.com/ZMabc123/"
    assert job.source == Source.TIKTOK


@pytest.mark.anyio
async def test_submit_rewrites_fixer_link_to_x(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    [job] = await manager.submit("look https://fxtwitter.com/user/status/123?s=46")
    assert job.url == "https://x.com/user/status/123"
    assert job.source == Source.X


@pytest.mark.anyio
async def test_submit_same_tweet_shared_differently_returns_same_jobs(tmp_path):
    settings = make_settings(tmp_path)
    pipeline = CountingPipeline(settings, videos=2)
    manager = JobManager(settings, pipeline, JobStore())
    first = await manager.submit("https://x.com/user/status/123?s=46&t=abc")
    again = await manager.submit("https://twitter.com/user/status/123?s=20")
    assert again == first
    assert len(pipeline.counted) == 1


@pytest.mark.anyio
async def test_submit_rejects_share_text_without_url(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    with pytest.raises(JobError) as exc:
        await manager.submit("just some words")
    assert exc.value.code == ErrorCode.UNSUPPORTED_URL


def _done_job(job_id: str, finished_minutes_ago: int, now: datetime) -> Job:
    job = Job(id=job_id, url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    job.finished_at = now - timedelta(minutes=finished_minutes_ago)
    job.result = JobResult(Path(f"{job_id}.mp4"), "T", Source.TIKTOK, 1.0, 1, 1, 1)
    return job


@pytest.mark.anyio
async def test_list_recent_filters_sorts_and_caps():
    store = JobStore()
    now = datetime.now(UTC)
    await store.add(_done_job("older", 30, now))
    await store.add(_done_job("newest", 1, now))
    await store.add(_done_job("middle", 10, now))
    failed = Job(id="failed", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
    failed.finished_at = now
    await store.add(failed)
    await store.add(Job(id="queued", url="u", source=Source.TIKTOK))
    await store.add(Job(id="running", url="u", source=Source.TIKTOK, status=JobStatus.DOWNLOADING))

    recent = await store.list_recent()
    assert [j.id for j in recent] == ["newest", "middle", "older"]
    assert [j.id for j in await store.list_recent(limit=2)] == ["newest", "middle"]


@pytest.mark.anyio
async def test_list_recent_returns_every_done_job_by_default():
    store = JobStore()
    now = datetime.now(UTC)
    for i in range(60):
        await store.add(_done_job(f"j{i}", i, now))
    recent = await store.list_recent()
    assert len(recent) == 60
    assert recent[0].id == "j0"


def _stored_video(settings, job_id, finished_at):
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    video = settings.storage_dir / f"{job_id}.mp4"
    video.write_bytes(b"x")
    thumb = settings.storage_dir / f"{job_id}.jpg"
    thumb.write_bytes(b"x")
    job = Job(id=job_id, url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    job.finished_at = finished_at
    job.result = JobResult(video, "T", Source.TIKTOK, 1.0, 1, 1, 1, thumbnail_path=thumb)
    return job


@pytest.mark.anyio
async def test_enforce_video_cap_evicts_oldest_first(tmp_path):
    settings = make_settings(tmp_path, max_videos=3)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)

    now = datetime.now(UTC)
    done = [_stored_video(settings, f"v{i}", now - timedelta(minutes=10 - i)) for i in range(5)]
    failed = Job(id="failed", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
    failed.finished_at = now - timedelta(hours=1)
    running = Job(id="running", url="u", source=Source.TIKTOK, status=JobStatus.DOWNLOADING)
    for j in (*done, failed, running):
        await store.add(j)

    await manager.enforce_video_cap()

    for job in done[:2]:  # the two oldest
        assert await store.get(job.id) is None
        assert not job.result.file_path.exists()
        assert not job.result.thumbnail_path.exists()
    for job in done[2:]:
        assert await store.get(job.id) is job
        assert job.result.file_path.exists()
    assert await store.get("failed") is not None
    assert await store.get("running") is not None


@pytest.mark.anyio
async def test_enforce_video_cap_under_limit_keeps_everything(tmp_path):
    settings = make_settings(tmp_path, max_videos=3)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    now = datetime.now(UTC)
    for i in range(3):
        await store.add(_stored_video(settings, f"v{i}", now - timedelta(minutes=i)))

    await manager.enforce_video_cap()

    assert len(await store.all()) == 3


@pytest.mark.anyio
async def test_finishing_a_video_past_the_cap_drops_the_oldest(tmp_path):
    settings = make_settings(tmp_path, max_videos=2)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        finished = []
        for i in range(3):
            [job] = await manager.submit(f"https://vm.tiktok.com/{i}/")
            finished.append(await wait_finished(store, job.id))
            await asyncio.sleep(0.01)  # distinct finished_at
        first = finished[0]
        assert await store.get(first.id) is None
        assert not first.result.file_path.exists()
        assert [j.id for j in await store.list_recent()] == [finished[2].id, finished[1].id]
    finally:
        await manager.stop()


def test_max_videos_must_be_positive(tmp_path):
    with pytest.raises(ValueError):
        make_settings(tmp_path, max_videos=0)


@pytest.mark.anyio
async def test_start_removes_video_files_left_by_a_previous_run(tmp_path):
    settings = make_settings(tmp_path)
    settings.storage_dir.mkdir(parents=True)
    settings.temp_dir.mkdir(parents=True)
    leftovers = [settings.storage_dir / name for name in ("old1.mp4", "old1.jpg", "old2.mp4")]
    for path in leftovers:
        path.write_bytes(b"x")
    unrelated = settings.storage_dir / "notes.txt"
    unrelated.write_bytes(b"x")
    (settings.temp_dir / "old1").mkdir()

    manager = JobManager(settings, FakePipeline(settings), JobStore())
    await manager.start()
    try:
        assert not any(path.exists() for path in leftovers)
        assert not (settings.temp_dir / "old1").exists()
        assert unrelated.exists()
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_sweeper_runs_once_an_hour(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    waits = []
    sweeps = []

    class StopLoop(Exception):
        pass

    async def fake_sleep(seconds):
        waits.append(seconds)
        if len(waits) == 3:
            raise StopLoop

    async def fake_sweep():
        sweeps.append(len(waits))

    monkeypatch.setattr(jobs_module.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(manager, "sweep", fake_sweep)
    with pytest.raises(StopLoop):
        await manager._sweeper()

    assert waits == [3600, 3600, 3600]
    assert sweeps == [1, 2]  # one sweep after each full wait


@pytest.mark.anyio
async def test_sweep_removes_untracked_video_files_but_keeps_tracked_ones(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    kept = _stored_video(settings, "kept", datetime.now(UTC))
    await store.add(kept)
    running = Job(id="running", url="u", source=Source.TIKTOK, status=JobStatus.PROCESSING)
    await store.add(running)
    in_progress = settings.storage_dir / "running.mp4"
    in_progress.write_bytes(b"x")
    orphan = settings.storage_dir / "timedout.mp4"  # written after its job was dropped
    orphan.write_bytes(b"x")

    await manager.sweep()

    assert kept.result.file_path.exists()
    assert kept.result.thumbnail_path.exists()
    assert in_progress.exists()
    assert not orphan.exists()


@pytest.mark.anyio
async def test_find_active_by_url():
    store = JobStore()
    url = "https://vm.tiktok.com/x/"
    await store.add(Job(id="f", url=url, source=Source.TIKTOK, status=JobStatus.FAILED))
    assert await store.find_active_by_url(url) == []

    running = Job(id="r", url=url, source=Source.TIKTOK, status=JobStatus.DOWNLOADING)
    await store.add(running)
    assert await store.find_active_by_url(url) == [running]
    assert await store.find_active_by_url("https://vm.tiktok.com/y/") == []


@pytest.mark.anyio
async def test_submit_same_url_while_queued_returns_existing_job(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    # not started: the first job stays queued
    [first] = await manager.submit("https://vm.tiktok.com/x/")
    [again] = await manager.submit("https://vm.tiktok.com/x/")
    assert again is first
    assert manager.queue.qsize() == 1


@pytest.mark.anyio
async def test_submit_same_url_after_done_returns_existing_job(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        [first] = await manager.submit("https://vm.tiktok.com/x/")
        await wait_finished(store, first.id)
        [again] = await manager.submit("https://vm.tiktok.com/x/")
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
        [first] = await manager.submit("https://vm.tiktok.com/x/")
        await wait_finished(store, first.id)
        [again] = await manager.submit("https://vm.tiktok.com/x/")
        assert again.id != first.id
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_submit_different_url_creates_new_job(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    [first] = await manager.submit("https://vm.tiktok.com/x/")
    [second] = await manager.submit("https://vm.tiktok.com/y/")
    assert second is not first
    assert manager.queue.qsize() == 2


@pytest.mark.anyio
async def test_submit_share_text_matches_existing_url(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    [first] = await manager.submit("https://vm.tiktok.com/ZMabc123/")
    [again] = await manager.submit("Check this out! https://vm.tiktok.com/ZMabc123/ #fyp")
    assert again is first


@pytest.mark.anyio
async def test_submit_returns_existing_job_even_when_queue_full(tmp_path):
    settings = make_settings(tmp_path, max_queue=1)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    [first] = await manager.submit("https://vm.tiktok.com/x/")
    assert await manager.submit("https://vm.tiktok.com/x/") == [first]
    with pytest.raises(JobError) as exc:
        await manager.submit("https://vm.tiktok.com/y/")
    assert exc.value.code == ErrorCode.TOO_MANY_JOBS


X_URL = "https://x.com/user/status/1577719286659006464"


class CountingPipeline(FakePipeline):
    """A fake pipeline that also knows how many videos a post has (X links spec 6)."""

    def __init__(self, settings, videos=3, count_behaviour="ok", count_delay=0.0):
        super().__init__(settings)
        self.videos = videos
        self.count_behaviour = count_behaviour
        self.count_delay = count_delay
        self.counted: list[str] = []
        self.items: list[int] = []

    def count_videos(self, url):
        self.counted.append(url)
        if self.count_delay:
            time.sleep(self.count_delay)
        if self.count_behaviour == "crash":
            raise RuntimeError("boom")
        return self.videos

    def _run(self, job, set_status):
        self.items.append(job.item)
        return super()._run(job, set_status)


@pytest.mark.anyio
async def test_submit_x_makes_one_job_per_video(tmp_path):
    settings = make_settings(tmp_path)
    pipeline = CountingPipeline(settings, videos=3)
    manager = JobManager(settings, pipeline, JobStore())
    jobs = await manager.submit(X_URL)
    assert [job.item for job in jobs] == [1, 2, 3]
    assert {job.url for job in jobs} == {X_URL}
    assert {job.source for job in jobs} == {Source.X}
    assert len({job.id for job in jobs}) == 3
    assert manager.queue.qsize() == 3
    assert pipeline.counted == [X_URL]


@pytest.mark.anyio
async def test_x_jobs_download_their_own_video(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    pipeline = CountingPipeline(settings, videos=2)
    manager = JobManager(settings, pipeline, store)
    await manager.start()
    try:
        jobs = await manager.submit(X_URL)
        for job in jobs:
            assert (await wait_finished(store, job.id)).status == JobStatus.DONE
        assert sorted(pipeline.items) == [1, 2]
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_submit_x_again_returns_its_jobs_without_counting(tmp_path):
    settings = make_settings(tmp_path)
    pipeline = CountingPipeline(settings, videos=3)
    manager = JobManager(settings, pipeline, JobStore())
    first = await manager.submit(X_URL)
    again = await manager.submit(X_URL)
    assert again == first
    assert pipeline.counted == [X_URL]
    assert manager.queue.qsize() == 3


@pytest.mark.anyio
async def test_submit_x_twice_at_once_makes_one_set_of_jobs(tmp_path):
    settings = make_settings(tmp_path)
    pipeline = CountingPipeline(settings, videos=2, count_delay=0.1)
    manager = JobManager(settings, pipeline, JobStore())
    first, second = await asyncio.gather(manager.submit(X_URL), manager.submit(X_URL))
    assert first == second
    assert manager.queue.qsize() == 2


@pytest.mark.anyio
async def test_submit_counts_only_x_links(tmp_path):
    settings = make_settings(tmp_path)
    pipeline = CountingPipeline(settings, videos=3)
    manager = JobManager(settings, pipeline, JobStore())
    [job] = await manager.submit("https://vm.tiktok.com/x/")
    assert job.item == 1
    assert pipeline.counted == []


@pytest.mark.anyio
async def test_submit_x_without_a_counter_makes_one_job(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    [job] = await manager.submit(X_URL)
    assert job.item == 1


@pytest.mark.anyio
async def test_submit_x_count_error_makes_one_job(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, CountingPipeline(settings, count_behaviour="crash"), JobStore())
    [job] = await manager.submit(X_URL)
    assert job.item == 1


@pytest.mark.anyio
async def test_submit_x_count_timeout_makes_one_job(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_module, "COUNT_TIMEOUT_SECONDS", 0.05)
    settings = make_settings(tmp_path)
    manager = JobManager(settings, CountingPipeline(settings, videos=3, count_delay=0.5), JobStore())
    [job] = await manager.submit(X_URL)
    assert job.item == 1


@pytest.mark.anyio
async def test_submit_x_needs_queue_room_for_every_video(tmp_path):
    settings = make_settings(tmp_path, max_queue=2)
    store = JobStore()
    manager = JobManager(settings, CountingPipeline(settings, videos=3), store)
    with pytest.raises(JobError) as exc:
        await manager.submit(X_URL)
    assert exc.value.code == ErrorCode.TOO_MANY_JOBS
    assert manager.queue.qsize() == 0
    assert await store.all() == []


@pytest.mark.anyio
async def test_submit_x_does_not_count_when_the_queue_is_full(tmp_path):
    settings = make_settings(tmp_path, max_queue=1)
    pipeline = CountingPipeline(settings, videos=1)
    manager = JobManager(settings, pipeline, JobStore())
    await manager.submit("https://vm.tiktok.com/x/")  # not started: fills the queue
    with pytest.raises(JobError) as exc:
        await manager.submit(X_URL)
    assert exc.value.code == ErrorCode.TOO_MANY_JOBS
    assert pipeline.counted == []


@pytest.mark.anyio
async def test_find_active_by_url_returns_every_video_in_order():
    store = JobStore()
    url = X_URL
    await store.add(Job(id="c", url=url, source=Source.X, item=3))
    await store.add(Job(id="b", url=url, source=Source.X, item=2, status=JobStatus.FAILED))
    await store.add(Job(id="a", url=url, source=Source.X, item=1, status=JobStatus.DONE))
    assert [job.id for job in await store.find_active_by_url(url)] == ["a", "c"]
