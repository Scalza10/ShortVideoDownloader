import importlib.util
import sys
from pathlib import Path

import pytest

from reels_api.auth import unasked_cookie_value
from reels_api.models import ErrorCode, Job, JobError, JobStatus, Source
from tests.conftest import make_settings

# scripts/ is not a package; load the dev server module from its path.
_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dev_board.py"
_spec = importlib.util.spec_from_file_location("dev_board", _PATH)
dev_board = importlib.util.module_from_spec(_spec)
sys.modules["dev_board"] = dev_board  # dataclasses look the module up while building Clip
_spec.loader.exec_module(dev_board)


def fake_clips(tmp_path: Path) -> list:
    clips = []
    for n in range(2):
        video = tmp_path / f"clip{n}.mp4"
        video.write_bytes(b"video" * (n + 1))
        thumbnail = tmp_path / f"clip{n}.jpg"
        thumbnail.write_bytes(b"\xff\xd8jpeg")
        clips.append(dev_board.Clip(video, thumbnail, 10 + n))
    return clips


@pytest.mark.parametrize(
    "url,code",
    [
        ("https://vm.tiktok.com/private/", ErrorCode.PRIVATE_OR_REMOVED),
        ("https://www.instagram.com/reel/login/", ErrorCode.LOGIN_REQUIRED),
        ("https://vm.tiktok.com/blocked/", ErrorCode.PLATFORM_BLOCKED),
        ("https://vm.tiktok.com/slow/", ErrorCode.TIMEOUT),
        ("https://x.com/dev/status/novideo", ErrorCode.NO_VIDEO),
    ],
)
def test_dev_pipeline_fails_on_keywords(tmp_path, url, code):
    settings = make_settings(tmp_path)
    pipeline = dev_board.DevPipeline(settings, fake_clips(tmp_path), delay=0)
    with pytest.raises(JobError) as exc:
        pipeline.run(Job(id="j1", url=url, source=Source.TIKTOK), lambda s: None)
    assert exc.value.code == code


def test_dev_pipeline_success_copies_a_clip(tmp_path):
    settings = make_settings(tmp_path)
    pipeline = dev_board.DevPipeline(settings, fake_clips(tmp_path), delay=0)
    statuses = []
    result = pipeline.run(Job(id="j1", url="https://vm.tiktok.com/ok/", source=Source.TIKTOK), statuses.append)
    assert statuses == [JobStatus.DOWNLOADING, JobStatus.PROCESSING]
    assert result.file_path == settings.storage_dir / "j1.mp4"
    assert result.file_path.read_bytes() == b"video"
    assert result.thumbnail_path.read_bytes() == b"\xff\xd8jpeg"
    assert result.caption == "pasted from https://vm.tiktok.com/ok/"


@pytest.mark.parametrize(
    "url,videos",
    [("https://x.com/dev/status/multi", 3), ("https://x.com/dev/status/1", 1)],
)
def test_dev_pipeline_counts_multi_as_three_videos(tmp_path, url, videos):
    pipeline = dev_board.DevPipeline(make_settings(tmp_path), fake_clips(tmp_path), delay=0)
    assert pipeline.count_videos(url) == videos


def test_dev_pipeline_partial_fails_only_the_second_video(tmp_path):
    settings = make_settings(tmp_path)
    pipeline = dev_board.DevPipeline(settings, fake_clips(tmp_path), delay=0)
    url = "https://x.com/dev/status/multi-partial"
    assert pipeline.count_videos(url) == 3
    assert pipeline.run(Job(id="j1", url=url, source=Source.X, item=1), lambda s: None).file_path.is_file()
    with pytest.raises(JobError) as exc:
        pipeline.run(Job(id="j2", url=url, source=Source.X, item=2), lambda s: None)
    assert exc.value.code == ErrorCode.PLATFORM_BLOCKED
    assert pipeline.run(Job(id="j3", url=url, source=Source.X, item=3), lambda s: None).file_path.is_file()


def test_dev_pipeline_nsfw_word_marks_the_reel(tmp_path):
    pipeline = dev_board.DevPipeline(make_settings(tmp_path), fake_clips(tmp_path), delay=0)
    nsfw = pipeline.run(Job(id="j1", url="https://x.com/dev/status/nsfw", source=Source.X), lambda s: None)
    plain = pipeline.run(Job(id="j2", url="https://x.com/dev/status/1", source=Source.X), lambda s: None)
    assert nsfw.nsfw is True
    assert plain.nsfw is False


def test_seed_jobs_have_one_nsfw_x_reel(tmp_path):
    jobs = dev_board.seed_jobs(make_settings(tmp_path), fake_clips(tmp_path))
    nsfw = [j for j in jobs if j.result.nsfw]
    assert [j.id for j in nsfw] == [f"seed{dev_board.NSFW_SEED:02d}"]
    assert nsfw[0].source == Source.X


def test_seed_jobs(tmp_path):
    settings = make_settings(tmp_path)
    jobs = dev_board.seed_jobs(settings, fake_clips(tmp_path))
    assert len(jobs) == len(dev_board.SEED_MINUTES_AGO)
    assert all(j.status == JobStatus.DONE and j.result.file_path.is_file() for j in jobs)
    assert jobs[dev_board.NO_THUMBNAIL_SEED].result.thumbnail_path is None
    assert {j.source for j in jobs} == {Source.TIKTOK, Source.INSTAGRAM, Source.X}
    assert all(j.expires_at > j.finished_at for j in jobs)
    assert len({j.url for j in jobs}) == len(jobs)


def test_seed_jobs_have_share_keys(tmp_path):
    jobs = dev_board.seed_jobs(make_settings(tmp_path), fake_clips(tmp_path))
    assert all(len(j.share_key) == 16 for j in jobs)
    assert len({j.share_key for j in jobs}) == len(jobs)


def test_link_lines(tmp_path):
    settings = make_settings(tmp_path, web_passcode="dev")
    jobs = dev_board.seed_jobs(settings, fake_clips(tmp_path))
    old_cookie = f"old cookie:  {unasked_cookie_value(settings)}"
    assert dev_board.link_lines(8000, jobs, settings) == [
        "invite link: http://localhost:8000/join/dev-invite-token-0000",
        f"share link:  http://localhost:8000/?reel=seed00&k={jobs[0].share_key}",
        old_cookie,
    ]
    assert dev_board.link_lines(9000, [], settings) == [
        "invite link: http://localhost:9000/join/dev-invite-token-0000",
        old_cookie,
    ]
