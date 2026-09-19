"""End-to-end against the real internet. Run with:

    REELS_TEST_URL=https://www.tiktok.com/@scout2015/video/6718335390845095173 python -m pytest -m network

Needs ffmpeg and ffprobe on PATH. Any public TikTok, Instagram or X link
works; pick a short one. A tweet with several videos checks that every video
becomes its own reel, e.g. https://x.com/UltimaShadowX/status/1577719286659006464
"""
import os
import time

import pytest
from fastapi.testclient import TestClient

from reels_api import media
from reels_api.main import create_app
from reels_api.urls import detect_source, normalize_url
from tests.conftest import make_settings

pytestmark = pytest.mark.network

TEST_URL = os.environ.get("REELS_TEST_URL")


def _wait_until_finished(client, job_id, headers, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/jobs/{job_id}", headers=headers).json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(1)
    raise AssertionError(f"job {job_id} did not finish")


@pytest.mark.skipif(not TEST_URL, reason="set REELS_TEST_URL to a public TikTok, Instagram or X link")
@pytest.mark.skipif(not media.ffmpeg_available(), reason="ffmpeg/ffprobe not on PATH")
def test_real_download(tmp_path):
    settings = make_settings(tmp_path, job_timeout_seconds=180)
    headers = {"X-API-Key": settings.api_key}
    source = detect_source(normalize_url(TEST_URL)).value
    with TestClient(create_app(settings=settings)) as client:
        created = client.post("/jobs", json={"url": TEST_URL}, headers=headers).json()
        assert created["ids"][0] == created["id"]
        titles = []
        for job_id in created["ids"]:
            body = _wait_until_finished(client, job_id, headers)
            assert body["status"] == "done", body
            assert body["size_bytes"] > 0
            assert body["source"] == source
            f = client.get(body["file_url"], headers=headers)
            assert f.status_code == 200
            assert f.content[4:8] == b"ftyp"  # MP4 magic
            titles.append(body["title"])
        # yt-dlp numbers a post's videos ("… #2"): each job must have downloaded a different one.
        assert len(set(titles)) == len(titles), titles
        print(f"{len(created['ids'])} video(s) from {TEST_URL}: {titles}")
