from pathlib import Path

import pytest

from reels_api.downloader import DownloadedMedia
from reels_api.media import ProbeResult
from reels_api.models import ErrorCode, Job, JobError, JobStatus, MediaInfo, Source
from reels_api.pipeline import Pipeline
from tests.conftest import make_settings


def fake_download_factory(calls, size=100):
    def fake_download(url, dest_dir, cookies_file=None, item=1):
        calls.append(("download", url, dest_dir, cookies_file, item))
        p = dest_dir / "source.mp4"
        p.write_bytes(b"\x00" * size)
        return DownloadedMedia(p, MediaInfo("Title", 10.0, 720, 1280))
    return fake_download


def fake_probe_factory(calls, video="h264", audio="aac"):
    def fake_probe(path):
        calls.append(("probe", path))
        return ProbeResult(video, audio, 9.5, 1080, 1920)
    return fake_probe


def fake_convert_factory(calls):
    def fake_convert(src, dst, transcode, timeout):
        calls.append(("convert", src, dst, transcode, timeout))
        dst.write_bytes(src.read_bytes() + b"\x01")
    return fake_convert


def fake_thumbnail_factory(calls, behaviour="ok"):
    def fake_thumbnail(src, dst, duration_seconds, timeout):
        calls.append(("thumbnail", src, dst, duration_seconds, timeout))
        if behaviour == "raise":
            dst.write_bytes(b"partial")
            raise JobError(ErrorCode.PROCESSING_FAILED, "thumbnail failed")
        dst.write_bytes(b"\xff\xd8jpeg")
    return fake_thumbnail


def make_job() -> Job:
    return Job(id="job1", url="https://vm.tiktok.com/x/", source=Source.TIKTOK)


def test_pipeline_success(tmp_path):
    settings = make_settings(tmp_path, job_timeout_seconds=100)
    calls = []
    statuses = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    result = p.run(make_job(), statuses.append)

    assert statuses == [JobStatus.DOWNLOADING, JobStatus.PROCESSING]
    assert result.file_path == settings.storage_dir / "job1.mp4"
    assert result.file_path.exists()
    assert result.size_bytes == 101
    assert result.title == "Title"
    assert result.source == Source.TIKTOK
    assert result.duration_seconds == 9.5   # probe wins over yt-dlp metadata
    assert result.width == 1080
    assert result.height == 1920
    assert result.nsfw is False

    kinds = [c[0] for c in calls]
    assert kinds == ["download", "probe", "convert", "thumbnail"]
    assert calls[0][2] == settings.temp_dir / "job1"
    assert calls[0][3] is None
    assert calls[2][3] is False           # h264+aac -> copy
    assert 0 < calls[2][4] <= 100         # timeout is the remaining budget
    assert not (settings.temp_dir / "job1").exists()


def test_pipeline_transcodes_when_needed(tmp_path):
    settings = make_settings(tmp_path)
    calls = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls, video="hevc"),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    p.run(make_job(), lambda s: None)
    assert calls[2][3] is True


def test_pipeline_passes_cookies(tmp_path):
    cookies = tmp_path / "c.txt"
    settings = make_settings(tmp_path, cookies_file=cookies)
    calls = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    p.run(make_job(), lambda s: None)
    assert calls[0][3] == cookies


def test_pipeline_falls_back_to_download_metadata(tmp_path):
    settings = make_settings(tmp_path)
    calls = []

    def probe_nothing(path):
        return ProbeResult("h264", "aac", None, None, None)

    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=probe_nothing,
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    result = p.run(make_job(), lambda s: None)
    assert result.duration_seconds == 10.0
    assert result.width == 720
    assert result.height == 1280


def test_pipeline_cleans_temp_on_failure(tmp_path):
    settings = make_settings(tmp_path)
    calls = []

    def failing_download(url, dest_dir, cookies_file=None, item=1):
        (dest_dir / "source.mp4.part").write_bytes(b"x")
        raise JobError(ErrorCode.LOGIN_REQUIRED)

    p = Pipeline(
        settings=settings,
        downloader=failing_download,
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
    )
    with pytest.raises(JobError) as exc:
        p.run(make_job(), lambda s: None)
    assert exc.value.code == ErrorCode.LOGIN_REQUIRED
    assert not (settings.temp_dir / "job1").exists()
    assert not (settings.storage_dir / "job1.mp4").exists()


def test_pipeline_writes_thumbnail(tmp_path):
    settings = make_settings(tmp_path, job_timeout_seconds=100)
    calls = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    result = p.run(make_job(), lambda s: None)
    assert [c[0] for c in calls] == ["download", "probe", "convert", "thumbnail"]
    thumb = calls[3]
    assert thumb[1] == settings.storage_dir / "job1.mp4"     # frame taken from the converted file
    assert thumb[2] == settings.storage_dir / "job1.jpg"
    assert thumb[3] == 9.5                                    # duration passed through
    assert 0 < thumb[4] <= 30
    assert result.thumbnail_path == settings.storage_dir / "job1.jpg"
    assert result.thumbnail_path.exists()


def test_pipeline_thumbnail_failure_is_non_fatal(tmp_path):
    settings = make_settings(tmp_path)
    calls = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls, behaviour="raise"),
    )
    result = p.run(make_job(), lambda s: None)
    assert result.file_path.exists()
    assert result.thumbnail_path is None
    assert not (settings.storage_dir / "job1.jpg").exists()   # partial file removed


def test_pipeline_removes_thumbnail_when_job_fails(tmp_path):
    settings = make_settings(tmp_path)
    calls = []
    settings.storage_dir.mkdir(parents=True)
    stale_thumb = settings.storage_dir / "job1.jpg"
    stale_thumb.write_bytes(b"old")

    def failing_convert(src, dst, transcode, timeout):
        dst.write_bytes(b"half")
        raise JobError(ErrorCode.PROCESSING_FAILED)

    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=failing_convert,
        thumbnailer=fake_thumbnail_factory(calls),
    )
    with pytest.raises(JobError):
        p.run(make_job(), lambda s: None)
    assert not (settings.storage_dir / "job1.mp4").exists()
    assert not stale_thumb.exists()


def test_pipeline_passes_caption(tmp_path):
    settings = make_settings(tmp_path)
    calls = []

    def download_with_caption(url, dest_dir, cookies_file=None, item=1):
        p = dest_dir / "source.mp4"
        p.write_bytes(b"\x00" * 10)
        return DownloadedMedia(p, MediaInfo("Title", 10.0, 720, 1280, caption="The real caption"))

    p = Pipeline(
        settings=settings,
        downloader=download_with_caption,
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    result = p.run(make_job(), lambda s: None)
    assert result.caption == "The real caption"


def test_pipeline_passes_nsfw(tmp_path):
    settings = make_settings(tmp_path)
    calls = []

    def download_nsfw(url, dest_dir, cookies_file=None, item=1):
        p = dest_dir / "source.mp4"
        p.write_bytes(b"\x00" * 10)
        return DownloadedMedia(p, MediaInfo("Title", 10.0, 720, 1280, nsfw=True))

    p = Pipeline(
        settings=settings,
        downloader=download_nsfw,
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    assert p.run(make_job(), lambda s: None).nsfw is True


def test_pipeline_downloads_the_jobs_item(tmp_path):
    settings = make_settings(tmp_path)
    calls = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
        thumbnailer=fake_thumbnail_factory(calls),
    )
    job = Job(id="job1", url="https://x.com/u/status/1", source=Source.X, item=3)
    p.run(job, lambda s: None)
    assert calls[0][4] == 3


def test_pipeline_count_videos_uses_counter_with_cookies(tmp_path):
    cookies = tmp_path / "c.txt"
    settings = make_settings(tmp_path, cookies_file=cookies)
    seen = []

    def counter(url, cookies_file=None):
        seen.append((url, cookies_file))
        return 3

    p = Pipeline(settings=settings, counter=counter)
    assert p.count_videos("https://x.com/u/status/1") == 3
    assert seen == [("https://x.com/u/status/1", cookies)]
