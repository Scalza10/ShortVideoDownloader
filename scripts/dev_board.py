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
wait 3 seconds, then fail if the URL contains "private", "login", "blocked",
"novideo" or "slow", and otherwise succeed with a copy of a seed clip. An
x.com link containing "multi" is a post with 3 videos, so it adds 3 reels;
with "partial" too, only the second of them fails. A link containing "nsfw"
gives an NSFW reel, and seed 3 is one.

On start it prints the invite link and the newest seeded reel's share link.
Open them in a private window to see what someone without the cookie sees.
It also prints an old cookie value, from before the login page asked: log
in, paste it over the reels_session value in DevTools (Application >
Cookies) and reload to see the cookie pop-up on the board.
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

from reels_api.auth import unasked_cookie_value
from reels_api.jobs import JobStore
from reels_api.main import create_app
from reels_api.models import ErrorCode, Job, JobError, JobResult, JobStatus, Source, utcnow
from reels_api.settings import Settings

PASSCODE = "dev"
INVITE_TOKEN = "dev-invite-token-0000"
FAKE_DELAY_SECONDS = 3.0
CLIP_COUNT = 6
FAILURE_WORDS: dict[str, ErrorCode] = {
    "private": ErrorCode.PRIVATE_OR_REMOVED,
    "login": ErrorCode.LOGIN_REQUIRED,
    "blocked": ErrorCode.PLATFORM_BLOCKED,
    "novideo": ErrorCode.NO_VIDEO,
    "slow": ErrorCode.TIMEOUT,
}
MULTI_WORD = "multi"  # an X post with MULTI_VIDEOS videos (X links spec 6)
MULTI_VIDEOS = 3
PARTIAL_WORD = "partial"  # with "multi": only video 2 fails, for the "1 of 3" toast
NSFW_WORD = "nsfw"  # a pasted link with this word gives an NSFW reel (NSFW cover spec 6)
NSFW_SEED = 3  # the first X seed
SEED_SOURCES = [
    (Source.TIKTOK, "www.tiktok.com/@dev/video"),
    (Source.TIKTOK, "www.tiktok.com/@dev/video"),
    (Source.INSTAGRAM, "www.instagram.com/reel"),
    (Source.X, "x.com/dev/status"),
]
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


def store_clip(
    settings: Settings, clip: Clip, job: Job, caption: str, with_thumbnail: bool = True, nsfw: bool = False
) -> JobResult:
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
        nsfw=nsfw,
    )


class DevPipeline:
    """Stands in for the real pipeline: no network, failures chosen by words in the URL."""

    def __init__(self, settings: Settings, clips: list[Clip], delay: float = FAKE_DELAY_SECONDS) -> None:
        self.settings = settings
        self.delay = delay
        self._clips = itertools.cycle(clips)
        self._lock = threading.Lock()

    def count_videos(self, url: str) -> int:
        return MULTI_VIDEOS if MULTI_WORD in url else 1

    def run(self, job: Job, set_status) -> JobResult:
        set_status(JobStatus.DOWNLOADING)
        time.sleep(self.delay)
        set_status(JobStatus.PROCESSING)
        for word, code in FAILURE_WORDS.items():
            if word in job.url:
                raise JobError(code)
        if PARTIAL_WORD in job.url and job.item == 2:
            raise JobError(ErrorCode.PLATFORM_BLOCKED)
        with self._lock:
            clip = next(self._clips)
        return store_clip(self.settings, clip, job, f"pasted from {job.url}", nsfw=NSFW_WORD in job.url)


def seed_jobs(settings: Settings, clips: list[Clip]) -> list[Job]:
    """Finished jobs spread over the retention window, newest first."""
    now = utcnow()
    retention = timedelta(hours=settings.retention_hours)
    jobs = []
    for i, minutes in enumerate(SEED_MINUTES_AGO):
        source, host = SEED_SOURCES[i % len(SEED_SOURCES)]
        job = Job(id=f"seed{i:02d}", url=f"https://{host}/{i}", source=source, status=JobStatus.DONE)
        job.finished_at = now - timedelta(minutes=minutes)
        job.expires_at = job.finished_at + retention
        job.result = store_clip(
            settings,
            clips[i % len(clips)],
            job,
            CAPTIONS[i % len(CAPTIONS)],
            with_thumbnail=i != NO_THUMBNAIL_SEED,
            nsfw=i == NSFW_SEED,
        )
        jobs.append(job)
    return jobs


def link_lines(port: int, seeds: list[Job], settings: Settings) -> list[str]:
    """The invite link, the newest seeded reel's share link (links spec 9) and an old cookie (pop-up spec 7)."""
    base = f"http://localhost:{port}"
    lines = [f"invite link: {base}/join/{INVITE_TOKEN}"]
    if seeds:
        newest = seeds[0]
        lines.append(f"share link:  {base}/?reel={newest.id}&k={newest.share_key}")
    lines.append(f"old cookie:  {unasked_cookie_value(settings)}")
    return lines


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
        invite_token=INVITE_TOKEN,
        storage_dir=root / "files",
        temp_dir=root / "tmp",
        workers=1,
    )
    clips_dir = root / "clips"
    clips_dir.mkdir()
    print("making seed clips with ffmpeg...", flush=True)
    clips = [make_clip(clips_dir, n) for n in range(CLIP_COUNT)]

    app = create_app(settings=settings, pipeline=DevPipeline(settings, clips))
    seeds: list[Job] = []
    if not args.empty:
        # Before the app starts: startup deletes stored files that belong to no known job.
        seeds = seed_jobs(settings, clips)
        asyncio.run(_add_all(app.state.store, seeds))
    print(f"open http://localhost:{args.port}/ and log in with passcode {PASSCODE!r}", flush=True)
    for line in link_lines(args.port, seeds, settings):
        print(line, flush=True)
    try:
        uvicorn.run(app, host=args.host, port=args.port)
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    main()
