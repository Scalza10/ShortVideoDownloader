from datetime import UTC, datetime
from pathlib import Path

from reels_api.models import (
    WHATSAPP_MAX_BYTES,
    ErrorCode,
    Job,
    JobError,
    JobResult,
    JobStatus,
    Source,
    job_to_dict,
    new_share_key,
)


def _result(size: int) -> JobResult:
    return JobResult(
        file_path=Path("/data/files/abc.mp4"),
        title="Hello World",
        source=Source.TIKTOK,
        duration_seconds=23.4,
        size_bytes=size,
        width=1080,
        height=1920,
    )


def test_job_error_default_message():
    err = JobError(ErrorCode.LOGIN_REQUIRED)
    assert err.code == ErrorCode.LOGIN_REQUIRED
    assert "log" in err.message.lower()
    assert str(err) == err.message


def test_unsupported_url_message_names_every_source():
    message = JobError(ErrorCode.UNSUPPORTED_URL).message
    assert message == "Only Instagram, TikTok and X video links are supported."


def test_job_error_custom_message():
    err = JobError(ErrorCode.PROCESSING_FAILED, "ffmpeg exploded")
    assert err.message == "ffmpeg exploded"


def test_whatsapp_ok_threshold():
    assert _result(WHATSAPP_MAX_BYTES).whatsapp_ok is True
    assert _result(WHATSAPP_MAX_BYTES + 1).whatsapp_ok is False


def test_job_to_dict_queued():
    job = Job(id="abc", url="https://www.tiktok.com/@a/video/1", source=Source.TIKTOK)
    assert job_to_dict(job) == {"id": "abc", "status": "queued"}


def test_job_to_dict_done_relative_and_absolute_url():
    job = Job(id="abc", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    job.result = _result(4812390)
    job.expires_at = datetime(2026, 9, 16, 22, 15, tzinfo=UTC)

    d = job_to_dict(job)
    assert d["status"] == "done"
    assert d["file_url"] == "/files/abc.mp4"
    assert d["title"] == "Hello World"
    assert d["source"] == "tiktok"
    assert d["duration_seconds"] == 23.4
    assert d["size_bytes"] == 4812390
    assert d["width"] == 1080
    assert d["height"] == 1920
    assert d["whatsapp_ok"] is True
    assert d["expires_at"] == "2026-09-16T22:15:00Z"

    d2 = job_to_dict(job, public_base_url="https://reels.example.com/")
    assert d2["file_url"] == "https://reels.example.com/files/abc.mp4"


def test_job_to_dict_failed():
    job = Job(id="abc", url="u", source=Source.INSTAGRAM, status=JobStatus.FAILED)
    job.error = ErrorCode.PRIVATE_OR_REMOVED
    job.message = "gone"
    assert job_to_dict(job) == {
        "id": "abc",
        "status": "failed",
        "error": "private_or_removed",
        "message": "gone",
    }


def test_job_to_dict_thumbnail_url():
    job = Job(id="abc", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    job.result = _result(100)
    assert job.result.thumbnail_path is None
    assert job_to_dict(job)["thumbnail_url"] is None

    job.result.thumbnail_path = Path("/data/files/abc.jpg")
    assert job_to_dict(job)["thumbnail_url"] == "/files/abc.jpg"
    assert job_to_dict(job, "https://reels.example.com/")["thumbnail_url"] == "https://reels.example.com/files/abc.jpg"


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


def test_new_share_key_shape():
    keys = {new_share_key() for _ in range(50)}
    assert len(keys) == 50
    for key in keys:
        assert len(key) == 16
        assert all(c.isalnum() or c in "-_" for c in key)


def test_every_job_gets_its_own_share_key():
    a = Job(id="a", url="u", source=Source.TIKTOK)
    b = Job(id="b", url="u", source=Source.TIKTOK)
    assert len(a.share_key) == 16
    assert a.share_key != b.share_key


def test_job_to_dict_share_key_only_when_done():
    job = Job(id="abc", url="u", source=Source.TIKTOK)
    assert "share_key" not in job_to_dict(job)

    job.status = JobStatus.FAILED
    job.error = ErrorCode.TIMEOUT
    assert "share_key" not in job_to_dict(job)

    job.status = JobStatus.DONE
    job.result = _result(100)
    assert job_to_dict(job)["share_key"] == job.share_key


def test_job_to_dict_nsfw():
    job = Job(id="abc", url="u", source=Source.X, status=JobStatus.DONE)
    job.result = _result(10)
    assert job_to_dict(job)["nsfw"] is False
    job.result.nsfw = True
    assert job_to_dict(job)["nsfw"] is True
    assert "nsfw" not in job_to_dict(Job(id="q", url="u", source=Source.X))
