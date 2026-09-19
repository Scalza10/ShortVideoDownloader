from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
from datetime import datetime, timedelta

from reels_api.models import ErrorCode, Job, JobError, JobStatus, Source, utcnow
from reels_api.pipeline import Pipeline
from reels_api.settings import Settings
from reels_api.urls import detect_source, extract_url, normalize_url

log = logging.getLogger(__name__)

TIMEOUT_GRACE_SECONDS = 5
COUNT_TIMEOUT_SECONDS = 20  # asking X how many videos a tweet has, inside POST /jobs
SWEEP_INTERVAL_SECONDS = 3600  # expired reels and orphan files are both checked hourly
STORED_SUFFIXES = (".mp4", ".jpg")  # what the pipeline writes into storage_dir


def new_job_id() -> str:
    return secrets.token_urlsafe(6)  # 8 URL-safe characters


class JobStore:
    """In-memory job registry. Lost on restart; that is acceptable for v1."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def add(self, job: Job) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def all(self) -> list[Job]:
        async with self._lock:
            return list(self._jobs.values())

    async def list_recent(self, limit: int | None = None) -> list[Job]:
        """Finished jobs with a file, newest first, for the web feed."""
        async with self._lock:
            done = [
                j for j in self._jobs.values()
                if j.status == JobStatus.DONE and j.result is not None and j.finished_at is not None
            ]
        done.sort(key=lambda j: j.finished_at, reverse=True)
        return done[:limit]

    async def find_active_by_url(self, url: str) -> list[Job]:
        """The jobs for exactly this URL that have not failed, one per video, by item."""
        async with self._lock:
            active = [j for j in self._jobs.values() if j.url == url and j.status != JobStatus.FAILED]
        return sorted(active, key=lambda j: j.item)

    async def remove(self, job_id: str) -> None:
        async with self._lock:
            self._jobs.pop(job_id, None)


class JobManager:
    """Owns the queue, the worker tasks and the sweeper."""

    def __init__(self, settings: Settings, pipeline: Pipeline, store: JobStore) -> None:
        self.settings = settings
        self.pipeline = pipeline
        self.store = store
        self.queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=settings.max_queue)
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        # Jobs live only in memory, so anything on disk now is from a previous run.
        await self._remove_untracked_files()
        for i in range(self.settings.workers):
            self._tasks.append(asyncio.create_task(self._worker(), name=f"worker-{i}"))
        self._tasks.append(asyncio.create_task(self._sweeper(), name="sweeper"))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def submit(self, text: str) -> list[Job]:
        """Queue one job per video of the linked post (only X posts can have several)."""
        url = normalize_url(extract_url(text))
        source = detect_source(url)  # raises JobError(unsupported_url)
        # One set of jobs per link: pasting a link already in the pile resolves to its jobs.
        existing = await self.store.find_active_by_url(url)
        if existing:
            return existing
        if self.queue.full():  # before counting: don't ask X about a paste we can't take
            raise JobError(ErrorCode.TOO_MANY_JOBS)
        count = await self._count_videos(url) if source == Source.X else 1
        # A second paste of the same link may have arrived while we were counting.
        existing = await self.store.find_active_by_url(url)
        if existing:
            return existing
        if self.queue.maxsize > 0 and self.queue.maxsize - self.queue.qsize() < count:
            raise JobError(ErrorCode.TOO_MANY_JOBS)
        jobs = [Job(id=new_job_id(), url=url, source=source, item=i) for i in range(1, count + 1)]
        for job in jobs:
            await self.store.add(job)
            self.queue.put_nowait(job)
        return jobs

    async def _count_videos(self, url: str) -> int:
        """Ask the pipeline how many videos the post has. Fakes without count_videos, errors and timeouts: 1."""
        count_videos = getattr(self.pipeline, "count_videos", None)
        if count_videos is None:
            return 1
        try:
            count = await asyncio.wait_for(asyncio.to_thread(count_videos, url), timeout=COUNT_TIMEOUT_SECONDS)
        except Exception:
            log.warning("counting videos failed for %s, queuing one job", url, exc_info=True)
            return 1
        return max(1, count)

    async def _worker(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                await self._run_job(job)
            except Exception:  # never let a worker die
                log.exception("worker crashed on job %s", job.id)
            finally:
                self.queue.task_done()

    async def _run_job(self, job: Job) -> None:
        def set_status(status: JobStatus) -> None:
            # A timed-out pipeline thread keeps running; ignore its late updates.
            if job.finished_at is None:
                job.status = status

        budget = self.settings.job_timeout_seconds + TIMEOUT_GRACE_SECONDS
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self.pipeline.run, job, set_status), timeout=budget
            )
            job.result = result
            job.status = JobStatus.DONE
        except asyncio.TimeoutError:
            self._fail(job, ErrorCode.TIMEOUT)
        except JobError as exc:
            self._fail(job, exc.code, exc.message)
        except Exception:
            log.exception("job %s failed unexpectedly", job.id)
            self._fail(job, ErrorCode.PROCESSING_FAILED)
        finally:
            if job.finished_at is None:
                job.finished_at = utcnow()
            job.expires_at = job.finished_at + self._retention()
            log.info("job %s finished: %s", job.id, job.status.value)
        if job.status == JobStatus.DONE:
            await self.enforce_video_cap()

    def _fail(self, job: Job, code: ErrorCode, message: str | None = None) -> None:
        job.finished_at = utcnow()  # first, so late set_status calls are ignored
        job.status = JobStatus.FAILED
        job.error = code
        job.message = message or JobError(code).message

    async def enforce_video_cap(self) -> None:
        """Keep at most max_videos finished videos; delete the oldest first."""
        videos = await self.store.list_recent(limit=None)  # newest first
        for job in videos[self.settings.max_videos:]:
            await self._discard(job)
            log.info("evicted job %s: over %d videos", job.id, self.settings.max_videos)

    async def _discard(self, job: Job) -> None:
        if job.result is not None:
            job.result.file_path.unlink(missing_ok=True)
            if job.result.thumbnail_path is not None:
                job.result.thumbnail_path.unlink(missing_ok=True)
        await self.store.remove(job.id)

    def _retention(self) -> timedelta:
        return timedelta(hours=self.settings.retention_hours)

    async def _sweeper(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            try:
                await self.sweep()
            except Exception:
                log.exception("sweep failed")

    async def sweep(self, now: datetime | None = None) -> None:
        """Delete finished jobs older than the retention window and untracked files."""
        now = now or utcnow()
        cutoff = now - self._retention()
        for job in await self.store.all():
            if job.finished_at is not None and job.finished_at < cutoff:
                await self._discard(job)
                log.info("swept job %s", job.id)
        await self._remove_untracked_files()

    async def _remove_untracked_files(self) -> None:
        """Delete temp dirs and stored videos/thumbnails that belong to no known job."""
        temp_dir = self.settings.temp_dir
        if temp_dir.is_dir():
            for entry in temp_dir.iterdir():
                if entry.is_dir() and await self.store.get(entry.name) is None:
                    shutil.rmtree(entry, ignore_errors=True)
                    log.info("removed stray temp dir %s", entry.name)

        storage_dir = self.settings.storage_dir
        if storage_dir.is_dir():
            for entry in storage_dir.iterdir():
                if (
                    entry.is_file()
                    and entry.suffix in STORED_SUFFIXES
                    and await self.store.get(entry.stem) is None
                ):
                    entry.unlink(missing_ok=True)
                    log.info("removed stray file %s", entry.name)
