from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from reels_api.models import ErrorCode, JobError

log = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    video_codec: str | None
    audio_codec: str | None
    duration_seconds: float | None
    width: int | None
    height: int | None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def parse_probe(data: dict) -> ProbeResult:
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration_raw = (data.get("format") or {}).get("duration")
    try:
        duration = float(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration = None
    return ProbeResult(
        video_codec=video.get("codec_name") if video else None,
        audio_codec=audio.get("codec_name") if audio else None,
        duration_seconds=duration,
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
    )


def probe(path: Path, timeout: float = 60) -> ProbeResult:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise JobError(ErrorCode.TIMEOUT) from exc
    if proc.returncode != 0:
        raise JobError(ErrorCode.PROCESSING_FAILED, "ffprobe failed: " + proc.stderr.strip()[-300:])
    try:
        return parse_probe(json.loads(proc.stdout or "{}"))
    except json.JSONDecodeError as exc:
        raise JobError(ErrorCode.PROCESSING_FAILED, "ffprobe returned invalid JSON") from exc


def needs_transcode(p: ProbeResult) -> bool:
    """WhatsApp wants H.264 + AAC. A file with no audio track can still be copied."""
    return not (p.video_codec == "h264" and p.audio_codec in ("aac", None))


def build_ffmpeg_command(src: Path, dst: Path, transcode: bool) -> list[str]:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if transcode:
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
        ]
    else:
        cmd += ["-c", "copy"]
    cmd += ["-movflags", "+faststart", str(dst)]
    return cmd


def convert(src: Path, dst: Path, transcode: bool, timeout: float) -> None:
    """Run ffmpeg. subprocess.run kills the child if the timeout expires."""
    cmd = build_ffmpeg_command(src, dst, transcode)
    log.debug("ffmpeg: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise JobError(ErrorCode.TIMEOUT) from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise JobError(ErrorCode.PROCESSING_FAILED, "ffmpeg failed: " + stderr[-300:])


def thumbnail_seek(duration_seconds: float | None) -> float:
    """Grab the frame one second in, or halfway through very short clips."""
    if not duration_seconds or duration_seconds <= 0:
        return 0.0
    return min(1.0, duration_seconds / 2)


def build_thumbnail_command(src: Path, dst: Path, at_seconds: float) -> list[str]:
    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{at_seconds:.3f}", "-i", str(src),
        "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4",
        str(dst),
    ]


def make_thumbnail(src: Path, dst: Path, duration_seconds: float | None, timeout: float) -> None:
    """Write one JPEG frame of src to dst. Raises JobError(processing_failed) on any failure."""
    cmd = build_thumbnail_command(src, dst, thumbnail_seek(duration_seconds))
    log.debug("ffmpeg thumbnail: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise JobError(ErrorCode.PROCESSING_FAILED, "thumbnail timed out") from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise JobError(ErrorCode.PROCESSING_FAILED, "thumbnail failed: " + stderr[-300:])
