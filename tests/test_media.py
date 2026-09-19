import subprocess
from pathlib import Path

import pytest

from reels_api import media
from reels_api.models import ErrorCode, JobError

PROBE_JSON = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
        {"codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "23.400000"},
}


def test_parse_probe():
    p = media.parse_probe(PROBE_JSON)
    assert p.video_codec == "h264"
    assert p.audio_codec == "aac"
    assert p.duration_seconds == 23.4
    assert p.width == 1080
    assert p.height == 1920


def test_parse_probe_no_audio_no_duration():
    p = media.parse_probe({"streams": [{"codec_type": "video", "codec_name": "hevc"}], "format": {}})
    assert p.video_codec == "hevc"
    assert p.audio_codec is None
    assert p.duration_seconds is None
    assert p.width is None


@pytest.mark.parametrize(
    "video,audio,expected",
    [
        ("h264", "aac", False),
        ("h264", None, False),
        ("hevc", "aac", True),
        ("h264", "opus", True),
        ("vp9", "opus", True),
        (None, "aac", True),
    ],
)
def test_needs_transcode(video, audio, expected):
    p = media.ProbeResult(video_codec=video, audio_codec=audio, duration_seconds=None, width=None, height=None)
    assert media.needs_transcode(p) is expected


def test_build_ffmpeg_command_copy():
    cmd = media.build_ffmpeg_command(Path("in.mp4"), Path("out.mp4"), transcode=False)
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert cmd[cmd.index("-i") + 1] == "in.mp4"
    assert cmd[cmd.index("-c") + 1] == "copy"
    assert "libx264" not in cmd
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert cmd[-1] == "out.mp4"


def test_build_ffmpeg_command_transcode():
    cmd = media.build_ffmpeg_command(Path("in.webm"), Path("out.mp4"), transcode=True)
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-preset") + 1] == "veryfast"
    assert cmd[cmd.index("-crf") + 1] == "23"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-b:a") + 1] == "128k"
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert "copy" not in cmd


def test_convert_success(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    media.convert(tmp_path / "in.mp4", tmp_path / "out.mp4", transcode=False, timeout=42)
    assert calls[0][1]["timeout"] == 42
    assert calls[0][0][0] == "ffmpeg"


def test_convert_failure(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Invalid data found when processing input")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    with pytest.raises(JobError) as exc:
        media.convert(tmp_path / "in.mp4", tmp_path / "out.mp4", transcode=False, timeout=10)
    assert exc.value.code == ErrorCode.PROCESSING_FAILED
    assert "Invalid data" in exc.value.message


def test_convert_timeout(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    with pytest.raises(JobError) as exc:
        media.convert(tmp_path / "in.mp4", tmp_path / "out.mp4", transcode=True, timeout=1)
    assert exc.value.code == ErrorCode.TIMEOUT


def test_probe_failure(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="in.mp4: No such file")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    with pytest.raises(JobError) as exc:
        media.probe(tmp_path / "in.mp4")
    assert exc.value.code == ErrorCode.PROCESSING_FAILED


def test_probe_success(monkeypatch, tmp_path):
    import json

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "ffprobe"
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(PROBE_JSON), stderr="")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    assert media.probe(tmp_path / "in.mp4").video_codec == "h264"


def test_ffmpeg_available_is_bool():
    assert isinstance(media.ffmpeg_available(), bool)


def test_build_thumbnail_command():
    cmd = media.build_thumbnail_command(Path("in.mp4"), Path("out.jpg"), 1.0)
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert cmd.index("-ss") < cmd.index("-i")          # seek before input: fast
    assert cmd[cmd.index("-ss") + 1] == "1.000"
    assert cmd[cmd.index("-i") + 1] == "in.mp4"
    assert cmd[cmd.index("-frames:v") + 1] == "1"
    assert cmd[cmd.index("-vf") + 1] == "scale=360:-2"
    assert cmd[cmd.index("-q:v") + 1] == "4"
    assert cmd[-1] == "out.jpg"


@pytest.mark.parametrize(
    "duration,expected",
    [(None, 0.0), (0, 0.0), (-3, 0.0), (0.5, 0.25), (1.5, 0.75), (2.0, 1.0), (60.0, 1.0)],
)
def test_thumbnail_seek(duration, expected):
    assert media.thumbnail_seek(duration) == expected


def test_make_thumbnail_success(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    media.make_thumbnail(tmp_path / "in.mp4", tmp_path / "out.jpg", 20.0, timeout=7)
    assert calls[0][1]["timeout"] == 7
    assert calls[0][0][calls[0][0].index("-ss") + 1] == "1.000"


def test_make_thumbnail_failure_and_timeout(monkeypatch, tmp_path):
    def fail_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Output file is empty")

    monkeypatch.setattr(media.subprocess, "run", fail_run)
    with pytest.raises(JobError) as exc:
        media.make_thumbnail(tmp_path / "in.mp4", tmp_path / "out.jpg", 5.0, timeout=7)
    assert exc.value.code == ErrorCode.PROCESSING_FAILED
    assert "Output file is empty" in exc.value.message

    def slow_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(media.subprocess, "run", slow_run)
    with pytest.raises(JobError) as exc:
        media.make_thumbnail(tmp_path / "in.mp4", tmp_path / "out.jpg", 5.0, timeout=1)
    assert exc.value.code == ErrorCode.PROCESSING_FAILED
