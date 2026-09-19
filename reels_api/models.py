from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

WHATSAPP_MAX_BYTES = 16 * 1024 * 1024


class Source(StrEnum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    X = "x"


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ErrorCode(StrEnum):
    UNSUPPORTED_URL = "unsupported_url"
    PRIVATE_OR_REMOVED = "private_or_removed"
    NO_VIDEO = "no_video"
    LOGIN_REQUIRED = "login_required"
    PLATFORM_BLOCKED = "platform_blocked"
    PROCESSING_FAILED = "processing_failed"
    TIMEOUT = "timeout"
    TOO_MANY_JOBS = "too_many_jobs"


ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNSUPPORTED_URL: "Only Instagram, TikTok and X video links are supported.",
    ErrorCode.PRIVATE_OR_REMOVED: "This post is private or no longer exists.",
    ErrorCode.NO_VIDEO: "This post has no video.",
    ErrorCode.LOGIN_REQUIRED: "The platform requires a login to view this post.",
    ErrorCode.PLATFORM_BLOCKED: "The platform blocked the download. Try again later.",
    ErrorCode.PROCESSING_FAILED: "The video could not be processed.",
    ErrorCode.TIMEOUT: "The download took too long and was cancelled.",
    ErrorCode.TOO_MANY_JOBS: "Too many downloads are queued. Try again in a minute.",
}


class JobError(Exception):
    """Any failure that should be reported to the client with an ErrorCode."""

    def __init__(self, code: ErrorCode, message: str | None = None):
        self.code = code
        self.message = message or ERROR_MESSAGES[code]
        super().__init__(self.message)


@dataclass
class MediaInfo:
    title: str
    duration_seconds: float | None
    width: int | None
    height: int | None
    caption: str | None = None
    nsfw: bool = False


@dataclass
class JobResult:
    file_path: Path
    title: str
    source: Source
    duration_seconds: float | None
    size_bytes: int
    width: int | None
    height: int | None
    thumbnail_path: Path | None = None
    caption: str | None = None
    nsfw: bool = False  # X marks the tweet sensitive; the page covers it (NSFW cover spec 3)

    @property
    def whatsapp_ok(self) -> bool:
        return self.size_bytes <= WHATSAPP_MAX_BYTES


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_share_key() -> str:
    """The secret half of a reel's share link: 16 URL-safe characters (links spec 4.1)."""
    return secrets.token_urlsafe(12)


@dataclass
class Job:
    id: str
    url: str
    source: Source
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    expires_at: datetime | None = None
    result: JobResult | None = None
    error: ErrorCode | None = None
    message: str | None = None
    share_key: str = field(default_factory=new_share_key)
    item: int = 1  # which of the post's videos, 1-based (yt-dlp's playlist_items)


class CreateJobRequest(BaseModel):
    url: str


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def job_to_dict(job: Job, public_base_url: str | None = None) -> dict:
    """The JSON body for GET /jobs/{id}, exactly as in the spec."""
    body: dict = {"id": job.id, "status": job.status.value}
    if job.status == JobStatus.DONE and job.result is not None:
        r = job.result
        file_url = f"/files/{job.id}.mp4"
        thumbnail_url = f"/files/{job.id}.jpg" if r.thumbnail_path is not None else None
        if public_base_url:
            base = public_base_url.rstrip("/")
            file_url = base + file_url
            if thumbnail_url:
                thumbnail_url = base + thumbnail_url
        body.update(
            {
                "file_url": file_url,
                "thumbnail_url": thumbnail_url,
                "title": r.title,
                "source": r.source.value,
                "duration_seconds": r.duration_seconds,
                "size_bytes": r.size_bytes,
                "width": r.width,
                "height": r.height,
                "whatsapp_ok": r.whatsapp_ok,
                "expires_at": _iso_z(job.expires_at) if job.expires_at else None,
                "caption": r.caption or r.title,
                "finished_at": _iso_z(job.finished_at) if job.finished_at else None,
                "share_key": job.share_key,
                "nsfw": r.nsfw,
            }
        )
    elif job.status == JobStatus.FAILED:
        body["error"] = job.error.value if job.error else ErrorCode.PROCESSING_FAILED.value
        body["message"] = job.message or ERROR_MESSAGES[job.error or ErrorCode.PROCESSING_FAILED]
    return body
