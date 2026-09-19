from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from reels_api import downloader, media
from reels_api.downloader import DownloadedMedia, count_videos
from reels_api.media import ProbeResult
from reels_api.models import Job, JobResult, JobStatus
from reels_api.settings import Settings

log = logging.getLogger(__name__)

Downloader = Callable[..., DownloadedMedia]  # (url, dest_dir, cookies_file, item=1)
Counter = Callable[[str, Path | None], int]
Prober = Callable[[Path], ProbeResult]
Converter = Callable[[Path, Path, bool, float], None]
Thumbnailer = Callable[[Path, Path, float | None, float], None]
StatusSetter = Callable[[JobStatus], None]

THUMBNAIL_TIMEOUT_SECONDS = 30.0


@dataclass
class Pipeline:
    """Runs the blocking stages for one job. Call from a worker thread."""

    settings: Settings
    downloader: Downloader = field(default=downloader.download)
    prober: Prober = field(default=media.probe)
    converter: Converter = field(default=media.convert)
    thumbnailer: Thumbnailer = field(default=media.make_thumbnail)
    counter: Counter = field(default=count_videos)

    def count_videos(self, url: str) -> int:
        """How many videos the post at url has. Blocking: call from a worker thread."""
        return self.counter(url, self.settings.cookies_file)

    def run(self, job: Job, set_status: StatusSetter) -> JobResult:
        deadline = time.monotonic() + self.settings.job_timeout_seconds
        temp_dir = self.settings.temp_dir / job.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        dst = self.settings.storage_dir / f"{job.id}.mp4"
        thumb = self.settings.storage_dir / f"{job.id}.jpg"
        try:
            set_status(JobStatus.DOWNLOADING)
            downloaded = self.downloader(job.url, temp_dir, self.settings.cookies_file, item=job.item)

            set_status(JobStatus.PROCESSING)
            probed = self.prober(downloaded.path)
            remaining = max(1.0, deadline - time.monotonic())
            self.converter(downloaded.path, dst, media.needs_transcode(probed), remaining)

            info = downloaded.info
            duration = probed.duration_seconds if probed.duration_seconds is not None else info.duration_seconds
            thumbnail_path = self._make_thumbnail(job, dst, thumb, duration, deadline)

            return JobResult(
                file_path=dst,
                title=info.title,
                source=job.source,
                duration_seconds=duration,
                size_bytes=dst.stat().st_size,
                width=probed.width if probed.width is not None else info.width,
                height=probed.height if probed.height is not None else info.height,
                thumbnail_path=thumbnail_path,
                caption=info.caption,
                nsfw=info.nsfw,
            )
        except BaseException:
            dst.unlink(missing_ok=True)
            thumb.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _make_thumbnail(
        self, job: Job, src: Path, dst: Path, duration: float | None, deadline: float
    ) -> Path | None:
        """A thumbnail failure never fails the job."""
        remaining = max(1.0, deadline - time.monotonic())
        try:
            self.thumbnailer(src, dst, duration, min(THUMBNAIL_TIMEOUT_SECONDS, remaining))
        except Exception:
            log.warning("job %s: thumbnail failed, continuing without one", job.id, exc_info=True)
            dst.unlink(missing_ok=True)
            return None
        return dst if dst.is_file() else None
