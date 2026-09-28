import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reels_api import jobs_file
from reels_api.models import Job, JobResult, JobStatus, Source

STORAGE = Path("/data/files")


def _done(job_id: str, thumb: bool = True, **fields) -> Job:
    finished = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    job = Job(id=job_id, url=f"https://vm.tiktok.com/{job_id}/", source=Source.TIKTOK, status=JobStatus.DONE, item=2)
    job.finished_at = finished
    job.expires_at = finished + timedelta(hours=12)
    job.result = JobResult(
        STORAGE / f"{job_id}.mp4",
        "Title",
        Source.TIKTOK,
        12.5,
        1234,
        720,
        1280,
        thumbnail_path=STORAGE / f"{job_id}.jpg" if thumb else None,
        caption="a caption",
        nsfw=True,
    )
    for name, value in fields.items():
        setattr(job, name, value)
    return job


def test_write_then_load_gives_the_same_reels(tmp_path):
    starred = _done("fav1", favorite=True, starred_at=datetime(2026, 9, 24, 13, 0, tzinfo=UTC))
    plain = _done("plain1", thumb=False)
    path = tmp_path / "jobs.json"
    jobs_file.write(path, jobs_file.dumps([starred, plain]))
    assert jobs_file.load(path, STORAGE) == [starred, plain]


def test_only_done_reels_are_saved(tmp_path):
    queued = Job(id="q1", url="u", source=Source.TIKTOK)
    failed = Job(id="f1", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
    path = tmp_path / "jobs.json"
    jobs_file.write(path, jobs_file.dumps([queued, failed, _done("d1")]))
    assert [job.id for job in jobs_file.load(path, STORAGE)] == ["d1"]


def test_file_format(tmp_path):
    path = tmp_path / "jobs.json"
    jobs_file.write(path, jobs_file.dumps([_done("d1", thumb=False)]))
    body = json.loads(path.read_text(encoding="utf-8"))
    assert body["version"] == 1
    [entry] = body["jobs"]
    assert entry["id"] == "d1"
    assert entry["has_thumbnail"] is False
    assert entry["finished_at"] == "2026-09-24T12:00:00+00:00"
    assert entry["favorite"] is False
    assert entry["starred_at"] is None
    assert "file_path" not in entry
    assert "thumbnail_path" not in entry


def test_write_replaces_the_file_and_leaves_no_temp_file(tmp_path):
    path = tmp_path / "jobs.json"
    path.write_text("old", encoding="utf-8")
    jobs_file.write(path, "new")
    assert path.read_text(encoding="utf-8") == "new"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["jobs.json"]


def test_write_over_a_stale_temp_file(tmp_path):
    # A crash mid-write leaves jobs.json.tmp behind; the next save just writes over it.
    (tmp_path / "jobs.json.tmp").write_text("half a fi", encoding="utf-8")
    jobs_file.write(tmp_path / "jobs.json", "new")
    assert (tmp_path / "jobs.json").read_text(encoding="utf-8") == "new"
    assert not (tmp_path / "jobs.json.tmp").exists()


def test_write_creates_the_directory(tmp_path):
    path = tmp_path / "files" / "jobs.json"
    jobs_file.write(path, "x")
    assert path.read_text(encoding="utf-8") == "x"


def test_load_without_a_file_is_empty(tmp_path):
    assert jobs_file.load(tmp_path / "jobs.json", STORAGE) == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        '{"jobs": []}',
        '{"version": 2, "jobs": []}',
        '{"version": 1}',
        '{"version": 1, "jobs": ["x"]}',
        '{"version": 1, "jobs": [{"id": "x"}]}',
    ],
)
def test_an_unusable_file_is_moved_aside(tmp_path, text):
    path = tmp_path / "jobs.json"
    path.write_text(text, encoding="utf-8")
    assert jobs_file.load(path, STORAGE) == []
    assert not path.exists()
    assert (tmp_path / "jobs.json.bad").read_text(encoding="utf-8") == text


def _edited(tmp_path, change) -> Path:
    body = json.loads(jobs_file.dumps([_done("d1")]))
    change(body["jobs"][0])
    path = tmp_path / "jobs.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


@pytest.mark.parametrize("bad_id", ["../d1", "a/b", "", 7])
def test_an_id_that_is_not_a_plain_name_makes_the_file_unusable(tmp_path, bad_id):
    path = _edited(tmp_path, lambda entry: entry.update(id=bad_id))
    assert jobs_file.load(path, STORAGE) == []
    assert (tmp_path / "jobs.json.bad").exists()


def test_a_time_without_a_time_zone_makes_the_file_unusable(tmp_path):
    path = _edited(tmp_path, lambda entry: entry.update(finished_at="2026-09-24T12:00:00"))
    assert jobs_file.load(path, STORAGE) == []
    assert (tmp_path / "jobs.json.bad").exists()


def test_an_older_bad_file_is_replaced(tmp_path):
    (tmp_path / "jobs.json.bad").write_text("older", encoding="utf-8")
    (tmp_path / "jobs.json").write_text("newer", encoding="utf-8")
    assert jobs_file.load(tmp_path / "jobs.json", STORAGE) == []
    assert (tmp_path / "jobs.json.bad").read_text(encoding="utf-8") == "newer"
