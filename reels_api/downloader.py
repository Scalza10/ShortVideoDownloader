from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError
from yt_dlp.version import __version__ as _ytdlp_version

from reels_api.models import ErrorCode, JobError, MediaInfo, Source
from reels_api.urls import detect_source

log = logging.getLogger(__name__)

# Prefer H.264 video + AAC audio so ffmpeg can copy instead of re-encode.
FORMAT = "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]/b"

# X links may only use X's tweet extractors: a tweet without a video but with a
# link is otherwise followed to the linked site, around our allow-list.
X_EXTRACTORS = ["twitter", "twitter:card", "twitter:amplify"]
MAX_VIDEOS_PER_POST = 9  # a tweet and its quoted tweet have at most 4 media each, plus a card's
# Counting runs inside POST /jobs, which stops waiting after jobs.COUNT_TIMEOUT_SECONDS (20);
# a shorter socket timeout keeps the abandoned thread from running on much longer.
COUNT_SOCKET_TIMEOUT_SECONDS = 8

_OUTPUT_STEM = "source"
_PARTIAL_SUFFIXES = {".part", ".ytdl", ".temp"}
# X's description ends with the media's own t.co link; links the author wrote come before it.
_TRAILING_TCO_RE = re.compile(r"\s*https?://t\.co/\S+\s*$")
_TCO_RE = re.compile(r"https?://t\.co/\S+")
# The "<user> -" left once a text-less tweet's link is gone, before an optional " #2".
_DANGLING_DASH_RE = re.compile(r"\s+-(?=\s+#\d+$)|\s+-$")

# Ordered: first match wins. Login must precede "not available", because
# Instagram's message "Requested content is not available, rate-limit reached
# or login required" mentions both. "No suitable extractor" is what X's
# extractor limit gives for a tweet that only links to another site.
_ERROR_PATTERNS: list[tuple[ErrorCode, tuple[str, ...]]] = [
    (ErrorCode.NO_VIDEO, ("no video could be found", "is not a video", "no suitable extractor")),
    (ErrorCode.LOGIN_REQUIRED, ("login required", "log in", "login", "cookies")),
    (
        ErrorCode.PRIVATE_OR_REMOVED,
        (
            "private", "does not exist", "not exist", "404", "not available", "unavailable", "not found",
            "removed", "deleted", "suspended", "no longer exist",
        ),
    ),
    (ErrorCode.UNSUPPORTED_URL, ("unsupported url",)),
]


@dataclass
class DownloadedMedia:
    path: Path
    info: MediaInfo


def map_ytdlp_error(message: str) -> ErrorCode:
    """Translate a yt-dlp error message into one of our error codes."""
    text = message.lower()
    for code, needles in _ERROR_PATTERNS:
        if any(n in text for n in needles):
            return code
    return ErrorCode.PLATFORM_BLOCKED


def ytdlp_version() -> str:
    return _ytdlp_version


def _find_output(dest_dir: Path) -> Path | None:
    candidates = [
        p
        for p in dest_dir.glob(f"{_OUTPUT_STEM}.*")
        if p.is_file() and p.suffix.lower() not in _PARTIAL_SUFFIXES
    ]
    if not candidates:
        return None
    # If a merged .mp4 exists prefer it; otherwise the largest file.
    for p in candidates:
        if p.suffix.lower() == ".mp4":
            return p
    return max(candidates, key=lambda p: p.stat().st_size)


def _clean_title(title: str) -> str:
    """Drop t.co links: yt-dlp keeps the one of a tweet that is only its video ("<user> - https://t.co/…")."""
    title = " ".join(_TCO_RE.sub("", title).split())
    return _DANGLING_DASH_RE.sub("", title)


def _to_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _is_nsfw(age_limit) -> bool:
    """X's "sensitive content" flag arrives as yt-dlp's age_limit 18 (NSFW cover spec 2)."""
    limit = _to_int(age_limit)
    return limit is not None and limit >= 18


def _is_x(url: str) -> bool:
    try:
        return detect_source(url) == Source.X
    except JobError:
        return False


def _base_opts(url: str, cookies_file: Path | None) -> dict:
    """What every yt-dlp call shares: quiet, cookies, and X's extractor limit."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "socket_timeout": 30,
    }
    if cookies_file:
        opts["cookiefile"] = str(cookies_file)
    if _is_x(url):
        opts["allowed_extractors"] = X_EXTRACTORS
    return opts


def count_videos(url: str, cookies_file: Path | None = None) -> int:
    """How many videos the post has, without downloading. Any error counts 1: the job reports it."""
    try:
        opts = _base_opts(url, cookies_file) | {"socket_timeout": COUNT_SOCKET_TIMEOUT_SECONDS}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False, process=False)
    except Exception as exc:
        log.info("counting videos failed for %s: %s", url, exc)
        return 1
    if not info or info.get("_type") != "playlist":
        return 1
    entries = [e for e in info.get("entries") or [] if e]
    return max(1, min(len(entries), MAX_VIDEOS_PER_POST))


def download(url: str, dest_dir: Path, cookies_file: Path | None = None, item: int = 1) -> DownloadedMedia:
    """Download entry `item` of the post into dest_dir as source.<ext>. Raises JobError on failure."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = _base_opts(url, cookies_file) | {
        "format": FORMAT,
        "outtmpl": str(dest_dir / f"{_OUTPUT_STEM}.%(ext)s"),
        "merge_output_format": "mp4",
        "playlist_items": str(item),
        "retries": 2,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as exc:
        log.info("yt-dlp failed for %s: %s", url, exc)
        raise JobError(map_ytdlp_error(str(exc))) from exc

    if info is None:
        raise JobError(ErrorCode.PLATFORM_BLOCKED)
    if "entries" in info:  # Instagram carousel or similar: take the first entry
        entries = [e for e in info["entries"] if e]
        info = entries[0] if entries else info

    path = _find_output(dest_dir)
    if path is None:
        raise JobError(ErrorCode.PLATFORM_BLOCKED, "The download produced no file.")

    title = _clean_title(info.get("title") or "") or "video"
    media = MediaInfo(
        title=title,
        duration_seconds=_to_float(info.get("duration")),
        width=_to_int(info.get("width")),
        height=_to_int(info.get("height")),
        # Instagram's title is "Video by <user>"; the real caption is the description.
        caption=_TRAILING_TCO_RE.sub("", info.get("description") or "").strip() or title,
        nsfw=_is_nsfw(info.get("age_limit")),
    )
    return DownloadedMedia(path=path, info=media)
