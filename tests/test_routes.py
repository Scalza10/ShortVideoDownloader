import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reels_api.auth import SESSION_COOKIE, session_cookie_value, session_state, unasked_cookie_value
from reels_api.main import create_app
from reels_api.models import ErrorCode, Job, JobError, JobResult, JobStatus, Source
from reels_api.routes import slugify
from tests.conftest import make_settings

HEADERS = {"X-API-Key": "test-key"}


class FakePipeline:
    def __init__(self, settings, behaviour="ok"):
        self.settings = settings
        self.behaviour = behaviour
        self.gate = threading.Event()  # "block" behaviour waits on this

    def run(self, job, set_status):
        set_status(JobStatus.DOWNLOADING)
        if self.behaviour == "block":
            self.gate.wait(timeout=10)
        set_status(JobStatus.PROCESSING)
        if self.behaviour == "job_error":
            raise JobError(ErrorCode.LOGIN_REQUIRED)
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.storage_dir / f"{job.id}.mp4"
        path.write_bytes(b"0123456789")
        thumb = None
        if self.behaviour != "no_thumb":
            thumb = self.settings.storage_dir / f"{job.id}.jpg"
            thumb.write_bytes(b"\xff\xd8jpeg")
        return JobResult(path, "My Cool Reel!", job.source, 2.5, 10, 1080, 1920, thumbnail_path=thumb)


@pytest.fixture
def app_factory(tmp_path):
    def factory(behaviour="ok", **overrides):
        settings = make_settings(tmp_path, **overrides)
        return create_app(settings=settings, pipeline=FakePipeline(settings, behaviour))
    return factory


def poll_until_finished(client, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/jobs/{job_id}", headers=HEADERS).json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_slugify():
    assert slugify("My Cool Reel!") == "my-cool-reel"
    assert slugify("   ") == "video"
    assert len(slugify("a" * 200)) <= 60


def test_health_needs_no_key(app_factory):
    with TestClient(app_factory()) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["ytdlp_version"], str)
    assert isinstance(body["ffmpeg"], bool)


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
def test_missing_or_wrong_key(app_factory, headers):
    with TestClient(app_factory()) as client:
        r = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=headers)
        assert r.status_code == 401
        assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}
        assert client.get("/jobs/abc", headers=headers).status_code == 401
        assert client.get("/files/abc.mp4", headers=headers).status_code == 401


def test_create_job_unsupported_url(app_factory):
    with TestClient(app_factory()) as client:
        r = client.post("/jobs", json={"url": "https://youtube.com/watch?v=1"}, headers=HEADERS)
    assert r.status_code == 400
    assert r.json()["error"] == "unsupported_url"
    assert r.json()["message"]


def test_create_job_queue_full(app_factory):
    app = app_factory("block", max_queue=1, workers=1)
    gate = app.state.manager.pipeline.gate
    try:
        with TestClient(app) as client:
            # Job 1 is taken by the single worker and blocks on the gate.
            first = client.post("/jobs", json={"url": "https://vm.tiktok.com/1/"}, headers=HEADERS)
            assert first.status_code == 202
            deadline = time.monotonic() + 5
            while client.get(f"/jobs/{first.json()['id']}", headers=HEADERS).json()["status"] == "queued":
                assert time.monotonic() < deadline, "worker never picked up job 1"
                time.sleep(0.02)

            # Job 2 fills the queue (max_queue=1). Job 3 must be rejected.
            second = client.post("/jobs", json={"url": "https://vm.tiktok.com/2/"}, headers=HEADERS)
            assert second.status_code == 202
            third = client.post("/jobs", json={"url": "https://vm.tiktok.com/3/"}, headers=HEADERS)
            assert third.status_code == 429
            assert third.json() == {
                "error": "too_many_jobs",
                "message": "Too many downloads are queued. Try again in a minute.",
            }
            gate.set()
    finally:
        gate.set()


def test_full_happy_path(app_factory):
    with TestClient(app_factory()) as client:
        r = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS)
        assert r.status_code == 202
        job_id = r.json()["id"]
        assert r.json()["status"] == "queued"
        assert r.json()["ids"] == [job_id]

        body = poll_until_finished(client, job_id)
        assert body["status"] == "done"
        assert body["file_url"] == f"/files/{job_id}.mp4"
        assert body["title"] == "My Cool Reel!"
        assert body["source"] == "tiktok"
        assert body["size_bytes"] == 10
        assert body["whatsapp_ok"] is True
        assert body["expires_at"].endswith("Z")

        f = client.get(f"/files/{job_id}.mp4", headers=HEADERS)
        assert f.status_code == 200
        assert f.headers["content-type"] == "video/mp4"
        assert 'filename="my-cool-reel.mp4"' in f.headers["content-disposition"]
        assert f.content == b"0123456789"

        part = client.get(f"/files/{job_id}.mp4", headers={**HEADERS, "Range": "bytes=2-5"})
        assert part.status_code == 206
        assert part.content == b"2345"


def test_public_base_url(app_factory):
    with TestClient(app_factory(public_base_url="https://reels.example.com")) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
    assert body["file_url"] == f"https://reels.example.com/files/{job_id}.mp4"


def test_failed_job(app_factory):
    with TestClient(app_factory("job_error")) as client:
        job_id = client.post("/jobs", json={"url": "https://www.instagram.com/reel/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
        assert body == {
            "id": job_id,
            "status": "failed",
            "error": "login_required",
            "message": "The platform requires a login to view this post.",
        }
        assert client.get(f"/files/{job_id}.mp4", headers=HEADERS).status_code == 404


def test_unknown_job_404(app_factory):
    with TestClient(app_factory()) as client:
        r = client.get("/jobs/nope", headers=HEADERS)
        assert r.status_code == 404
        assert r.json()["error"] == "not_found"
        assert client.get("/files/nope.mp4", headers=HEADERS).status_code == 404


def test_invalid_body_422(app_factory):
    with TestClient(app_factory()) as client:
        assert client.post("/jobs", json={}, headers=HEADERS).status_code == 422


def test_cookie_values_are_hmacs_of_passcode(tmp_path):
    import hashlib
    import hmac

    settings = make_settings(tmp_path, web_passcode="letmein")
    agreed = hmac.new(b"test-key", b"reels-web-session-agreed:letmein", hashlib.sha256).hexdigest()
    unasked = hmac.new(b"test-key", b"reels-web-session:letmein", hashlib.sha256).hexdigest()
    assert session_cookie_value(settings) == agreed
    assert unasked_cookie_value(settings) == unasked
    other = make_settings(tmp_path, web_passcode="other")
    assert session_cookie_value(other) != agreed
    assert unasked_cookie_value(other) != unasked


def test_session_state(tmp_path):
    settings = make_settings(tmp_path, web_passcode="letmein")
    assert session_state(settings, session_cookie_value(settings)) == "agreed"
    assert session_state(settings, unasked_cookie_value(settings)) == "unasked"
    for bad in (None, "", "nope", "é", session_cookie_value(settings) + "x"):
        assert session_state(settings, bad) is None, bad
    disabled = make_settings(tmp_path)  # no web_passcode
    assert session_state(disabled, session_cookie_value(disabled)) is None
    assert session_state(disabled, unasked_cookie_value(disabled)) is None


@pytest.mark.parametrize("cookie_value", [session_cookie_value, unasked_cookie_value], ids=["agreed", "unasked"])
def test_valid_cookie_grants_access(app_factory, cookie_value):
    app = app_factory(web_passcode="letmein")
    with TestClient(app) as client:
        client.cookies.set(SESSION_COOKIE, cookie_value(app.state.settings))
        r = client.get("/jobs/nope")
        assert r.status_code == 404  # authenticated, job simply does not exist
        r = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"})
        assert r.status_code == 202
        reel = _done_reel(client, "https://vm.tiktok.com/y/")
        assert client.get(f"/files/{reel['id']}.mp4").status_code == 200  # no k: the cookie opens it


def test_wrong_or_stale_cookie_is_401(app_factory, tmp_path):
    app = app_factory(web_passcode="letmein")
    old = make_settings(tmp_path, web_passcode="old-passcode")
    with TestClient(app) as client:
        for bad in ("nope", session_cookie_value(old), unasked_cookie_value(old), ""):
            client.cookies.set(SESSION_COOKIE, bad)
            r = client.get("/jobs/nope")
            assert r.status_code == 401
            assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}


def test_cookie_rejected_when_web_disabled(app_factory, tmp_path):
    enabled = make_settings(tmp_path, web_passcode="letmein")
    cookie = session_cookie_value(enabled)
    with TestClient(app_factory()) as client:  # no web_passcode
        client.cookies.set(SESSION_COOKIE, cookie)
        assert client.get("/jobs/nope").status_code == 401


def test_list_jobs_requires_access_and_lists_done_jobs(app_factory):
    with TestClient(app_factory()) as client:
        assert client.get("/jobs").status_code == 401

        first = client.post("/jobs", json={"url": "https://vm.tiktok.com/1/"}, headers=HEADERS).json()["id"]
        poll_until_finished(client, first)
        second = client.post("/jobs", json={"url": "https://vm.tiktok.com/2/"}, headers=HEADERS).json()["id"]
        poll_until_finished(client, second)

        r = client.get("/jobs", headers=HEADERS)
        assert r.status_code == 200
        jobs = r.json()["jobs"]
        assert [j["id"] for j in jobs] == [second, first]
        assert jobs[0]["status"] == "done"
        assert jobs[0]["file_url"] == f"/files/{second}.mp4"
        assert jobs[0]["title"] == "My Cool Reel!"


def test_list_jobs_excludes_failed(app_factory):
    with TestClient(app_factory("job_error")) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/1/"}, headers=HEADERS).json()["id"]
        poll_until_finished(client, job_id)
        assert client.get("/jobs", headers=HEADERS).json() == {"jobs": []}


def test_thumbnail_route(app_factory):
    with TestClient(app_factory()) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
        assert body["thumbnail_url"] == f"/files/{job_id}.jpg"

        assert client.get(f"/files/{job_id}.jpg").status_code == 401
        r = client.get(f"/files/{job_id}.jpg", headers=HEADERS)
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"
        assert r.headers["cache-control"] == "private, max-age=21600"
        assert "content-disposition" not in r.headers
        assert r.content == b"\xff\xd8jpeg"

        assert client.get("/files/nope.jpg", headers=HEADERS).status_code == 404

        app = client.app
        job = app.state.store._jobs[job_id]
        job.result.thumbnail_path.unlink()
        assert client.get(f"/files/{job_id}.jpg", headers=HEADERS).status_code == 404


def test_thumbnail_route_404_when_job_has_none(app_factory):
    with TestClient(app_factory("no_thumb")) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
        assert body["thumbnail_url"] is None
        assert client.get(f"/files/{job_id}.jpg", headers=HEADERS).status_code == 404


def test_done_job_has_caption_and_finished_at(app_factory):
    with TestClient(app_factory()) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
        assert body["caption"] == "My Cool Reel!"
        assert body["finished_at"].endswith("Z")

        listed = client.get("/jobs", headers=HEADERS).json()["jobs"][0]
        assert listed["caption"] == "My Cool Reel!"
        assert listed["finished_at"] == body["finished_at"]


def test_create_job_same_url_returns_same_id(app_factory):
    with TestClient(app_factory()) as client:
        first = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS)
        poll_until_finished(client, first.json()["id"])

        second = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS)
        assert second.status_code == 202
        assert second.json() == {"id": first.json()["id"], "status": "done", "ids": [first.json()["id"]]}
        assert len(client.get("/jobs", headers=HEADERS).json()["jobs"]) == 1


class TwoVideoPipeline(FakePipeline):
    def count_videos(self, url):
        return 2


def test_create_job_for_a_two_video_tweet_answers_both_ids(tmp_path):
    settings = make_settings(tmp_path)
    app = create_app(settings=settings, pipeline=TwoVideoPipeline(settings))
    with TestClient(app) as client:
        r = client.post("/jobs", json={"url": "https://x.com/user/status/1"}, headers=HEADERS)
        assert r.status_code == 202
        body = r.json()
        assert len(body["ids"]) == 2
        assert body["id"] == body["ids"][0]
        for job_id in body["ids"]:
            done = poll_until_finished(client, job_id)
            assert done["status"] == "done"
            assert done["source"] == "x"
        assert len(client.get("/jobs", headers=HEADERS).json()["jobs"]) == 2


def test_list_jobs_returns_every_stored_reel(app_factory):
    with TestClient(app_factory()) as client:
        now = datetime.now(UTC)
        for i in range(60):
            job = Job(id=f"j{i:02d}", url=f"https://vm.tiktok.com/{i}/", source=Source.TIKTOK, status=JobStatus.DONE)
            job.finished_at = now - timedelta(minutes=i)
            job.result = JobResult(Path(f"j{i:02d}.mp4"), "T", Source.TIKTOK, 1.0, 1, 1, 1)
            client.app.state.store._jobs[job.id] = job
        jobs = client.get("/jobs", headers=HEADERS).json()["jobs"]
    assert len(jobs) == 60
    assert jobs[0]["id"] == "j00"


def test_share_key_in_job_json_and_stable_for_same_url(app_factory):
    with TestClient(app_factory()) as client:
        job_id = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()["id"]
        body = poll_until_finished(client, job_id)
        assert len(body["share_key"]) == 16

        again = client.post("/jobs", json={"url": "https://vm.tiktok.com/x/"}, headers=HEADERS).json()
        assert again["id"] == job_id
        assert client.get(f"/jobs/{job_id}", headers=HEADERS).json()["share_key"] == body["share_key"]
        assert client.get("/jobs", headers=HEADERS).json()["jobs"][0]["share_key"] == body["share_key"]


def _done_reel(client, url="https://vm.tiktok.com/x/"):
    job_id = client.post("/jobs", json={"url": url}, headers=HEADERS).json()["id"]
    return poll_until_finished(client, job_id)


def test_share_key_opens_that_reels_files_without_login(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        key = {"k": reel["share_key"]}

        video = client.get(f"/files/{reel['id']}.mp4", params=key)
        assert video.status_code == 200
        assert video.content == b"0123456789"
        assert 'filename="my-cool-reel.mp4"' in video.headers["content-disposition"]

        part = client.get(f"/files/{reel['id']}.mp4", params=key, headers={"Range": "bytes=0-0"})
        assert part.status_code == 206

        thumb = client.get(f"/files/{reel['id']}.jpg", params=key)
        assert thumb.status_code == 200
        assert thumb.headers["cache-control"] == "private, max-age=21600"


def test_wrong_share_key_is_401(app_factory):
    with TestClient(app_factory()) as client:
        first = _done_reel(client, "https://vm.tiktok.com/1/")
        second = _done_reel(client, "https://vm.tiktok.com/2/")
        for path in (f"/files/{first['id']}.mp4", f"/files/{first['id']}.jpg"):
            for bad in ("", "nope", second["share_key"]):
                r = client.get(path, params={"k": bad})
                assert r.status_code == 401, (path, bad)
                assert r.json() == {"error": "unauthorized", "message": "Missing or invalid API key."}
        assert client.get("/files/nope.mp4", params={"k": first["share_key"]}).status_code == 401
        assert client.get("/files/nope.jpg", params={"k": first["share_key"]}).status_code == 401


def test_share_key_does_not_open_the_api(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        key = {"k": reel["share_key"]}
        assert client.get("/jobs", params=key).status_code == 401
        assert client.get(f"/jobs/{reel['id']}", params=key).status_code == 401
        assert client.post("/jobs", params=key, json={"url": "https://vm.tiktok.com/z/"}).status_code == 401


def test_share_key_with_missing_files_is_404(app_factory):
    with TestClient(app_factory()) as client:
        reel = _done_reel(client)
        job = client.app.state.store._jobs[reel["id"]]
        job.result.file_path.unlink()
        job.result.thumbnail_path.unlink()
        key = {"k": reel["share_key"]}
        assert client.get(f"/files/{reel['id']}.mp4", params=key).status_code == 404
        assert client.get(f"/files/{reel['id']}.jpg", params=key).status_code == 404


def test_cookie_opens_files_without_share_key(app_factory):
    app = app_factory(web_passcode="letmein")
    with TestClient(app) as client:
        reel = _done_reel(client)
        client.cookies.set(SESSION_COOKIE, session_cookie_value(app.state.settings))
        assert client.get(f"/files/{reel['id']}.mp4").status_code == 200
        assert client.get(f"/files/{reel['id']}.jpg").status_code == 200
