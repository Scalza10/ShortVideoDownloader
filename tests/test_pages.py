import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest

from reels_api import pages
from reels_api.models import Job, JobResult, JobStatus, Source

BASE = "https://reels.example.com"


def _job(caption="wait for it", thumbnail=True, source=Source.TIKTOK, duration=19.7, nsfw=False) -> Job:
    job = Job(id="abc123", url="https://vm.tiktok.com/x/", source=source, status=JobStatus.DONE)
    job.finished_at = datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    job.expires_at = datetime(2026, 9, 17, 22, 0, tzinfo=UTC)
    job.result = JobResult(
        file_path=Path("abc123.mp4"),
        title="Video by someone",
        source=source,
        duration_seconds=duration,
        size_bytes=100,
        width=720,
        height=1280,
        thumbnail_path=Path("abc123.jpg") if thumbnail else None,
        caption=caption,
        nsfw=nsfw,
    )
    return job


def meta(page: str, prop: str) -> str | None:
    match = re.search(rf'<meta property="{prop}" content="([^"]*)">', page)
    return html.unescape(match.group(1)) if match else None


def reel_data(page: str) -> dict:
    match = re.search(r'<script type="application/json" id="reel-data">(.*?)</script>', page, re.S)
    return json.loads(match.group(1))


def page_title(page: str) -> str:
    return html.unescape(re.search(r"<title>(.*?)</title>", page).group(1))


# ---- helpers

def test_fill_escapes_values_and_inserts_raw_values_as_is():
    template = '<p title="{{a}}">{{b}}</p>{{c}}'
    out = pages.fill(template, {"a": '"x"', "b": "<b>&"}, raw={"c": "<i>ok</i>"})
    assert out == '<p title="&quot;x&quot;">&lt;b&gt;&amp;</p><i>ok</i>'


def test_fill_does_not_rescan_inserted_values():
    assert pages.fill("{{a}}", {"a": "{{b}}"}) == "{{b}}"


def test_fill_missing_value_raises():
    with pytest.raises(KeyError):
        pages.fill("{{nope}}", {})


def test_script_json_cannot_close_the_script():
    data = {"caption": "</script><b>&amp;"}
    text = pages.script_json(data)
    assert "<" not in text and ">" not in text and "&" not in text
    assert json.loads(text) == data


def test_preview_title():
    assert pages.preview_title("  wait\n\nfor   it ") == "wait for it"
    assert pages.preview_title(None) == "a reel"
    assert pages.preview_title("   ") == "a reel"
    assert pages.preview_title("x" * 100) == "x" * 100
    long = pages.preview_title("y" * 101)
    assert long == "y" * 99 + "…"
    assert len(long) == 100


def test_preview_description():
    assert pages.preview_description(Source.TIKTOK, 19.7) == "TikTok · 0:19"
    assert pages.preview_description(Source.INSTAGRAM, 125) == "Instagram · 2:05"
    assert pages.preview_description(Source.TIKTOK, None) == "TikTok"
    assert pages.preview_description(Source.TIKTOK, float("nan")) == "TikTok"
    assert pages.preview_description(Source.X, 7) == "X · 0:07"


def test_retention_text():
    assert pages.retention_text(12) == "12 hours"
    assert pages.retention_text(1) == "1 hour"
    assert pages.retention_text(1.5) == "1.5 hours"


# ---- view-only page

def test_render_watch_tags_and_reel_data():
    job = _job()
    key = job.share_key
    page = pages.render_watch(job, BASE)

    assert "{{" not in page
    assert page_title(page) == "wait for it"
    assert meta(page, "og:title") == "wait for it"
    assert meta(page, "og:description") == "TikTok · 0:19"
    assert meta(page, "og:image") == f"{BASE}/files/abc123.jpg?k={key}"
    assert meta(page, "og:url") == f"{BASE}/?reel=abc123&k={key}"
    assert meta(page, "og:type") == "video.other"
    assert meta(page, "og:site_name") == "reels"
    assert '<meta name="robots" content="noindex">' in page
    assert '<meta name="referrer" content="strict-origin-when-cross-origin">' in page
    assert '<script type="module" src="/static/watch.js"></script>' in page

    data = reel_data(page)
    assert data["id"] == "abc123"
    assert data["file_url"] == f"/files/abc123.mp4?k={key}"
    assert data["thumbnail_url"] == f"/files/abc123.jpg?k={key}"
    assert data["caption"] == "wait for it"
    assert data["source"] == "tiktok"


def test_render_watch_has_standalone_player_markup():
    page = pages.render_watch(_job(), BASE)
    assert 'id="player"' in page
    assert 'id="toast"' in page
    assert page.count('data-action="save"') == 2
    assert page.count('href="/?reel=abc123"') == 2
    assert "have the passcode? <u>log in</u>" in page
    assert "tap for options" in page
    for gone in ("close", "prev", "next", "share", "copy", "whatsapp"):
        assert f'data-action="{gone}"' not in page, gone


def test_both_players_have_the_nsfw_cover():
    # The player markup lives in app.html and watch.html; the cover must be in both.
    for page in (pages.render_app(False), pages.render_watch(_job(), BASE)):
        assert page.count('<div class="nsfw-cover" hidden>') == 1
        assert page.count('data-action="reveal"') == 1
        # Above the video, below the idle bar and the chrome: that order is the stacking.
        cover = page.index('class="nsfw-cover"')
        assert page.index("<video") < cover < page.index('class="idle-bar"') < page.index('class="chrome"')


def test_render_watch_nsfw_leaks_no_image_in_any_tag():
    page = pages.render_watch(_job(source=Source.X, nsfw=True), BASE)
    head = page[: page.index("</head>")]
    assert ".jpg" not in "".join(re.findall(r"<meta[^>]*>", head))


def test_render_watch_escapes_a_hostile_caption():
    caption = 'x</script><script>alert("hi")</script> & more'
    page = pages.render_watch(_job(caption=caption), BASE)
    assert "<script>alert" not in page
    assert page_title(page) == caption
    assert meta(page, "og:title") == caption
    assert reel_data(page)["caption"] == caption


def test_render_watch_without_thumbnail():
    page = pages.render_watch(_job(thumbnail=False), BASE)
    assert meta(page, "og:image") is None
    assert reel_data(page)["thumbnail_url"] is None


def test_render_watch_nsfw_has_no_picture_and_says_so():
    job = _job(source=Source.X, nsfw=True)
    page = pages.render_watch(job, BASE)
    assert meta(page, "og:image") is None
    assert meta(page, "og:description") == "NSFW · X · 0:19"
    assert meta(page, "og:title") == "wait for it"
    data = reel_data(page)
    assert data["nsfw"] is True
    assert data["thumbnail_url"] == f"/files/abc123.jpg?k={job.share_key}"  # the page's own cover blurs it


def test_render_watch_instagram_without_duration():
    page = pages.render_watch(_job(source=Source.INSTAGRAM, duration=None), BASE)
    assert meta(page, "og:description") == "Instagram"


# ---- expired page

def test_render_expired():
    page = pages.render_expired(12)
    assert "{{" not in page
    assert "this reel has expired" in page
    assert "reels only stay up for 12 hours" in page
    assert 'href="/"' in page
    assert "have the passcode? <u>log in</u>" in page
    assert meta(page, "og:title") == "reels"
    assert meta(page, "og:description") == "this reel has expired"
    assert '<meta name="robots" content="noindex">' in page
    assert "reels only stay up for 1 hour<" in pages.render_expired(1)


# ---- board (pop-up spec 4)

def test_render_app_marks_whether_to_ask():
    ask = pages.render_app(True)
    agreed = pages.render_app(False)
    assert '<body data-cookie="ask">' in ask
    assert '<body data-cookie="agreed">' in agreed
    for page in (ask, agreed):
        assert "{{" not in page
        assert 'id="grid"' in page
