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
