import pytest

from reels_api.models import ErrorCode, JobError, Source
from reels_api.urls import detect_source, extract_url, normalize_url


@pytest.mark.parametrize(
    "url,source",
    [
        ("https://www.instagram.com/reel/C1abc/", Source.INSTAGRAM),
        ("https://instagram.com/reel/C1abc/?igsh=x", Source.INSTAGRAM),
        ("https://www.tiktok.com/@user/video/7300000000000000000", Source.TIKTOK),
        ("https://tiktok.com/@user/video/1", Source.TIKTOK),
        ("https://vm.tiktok.com/ZMabc123/", Source.TIKTOK),
        ("https://vt.tiktok.com/ZSabc123/", Source.TIKTOK),
        ("https://m.tiktok.com/v/1.html", Source.TIKTOK),
        ("HTTPS://WWW.TIKTOK.COM/@user/video/1", Source.TIKTOK),
        ("https://x.com/user/status/1575560063510810624", Source.X),
        ("https://x.com/user/status/1575560063510810624?s=46&t=abc", Source.X),
        ("https://www.x.com/user/status/1", Source.X),
        ("https://mobile.x.com/user/status/1", Source.X),
        ("https://m.x.com/user/status/1", Source.X),
        ("https://twitter.com/user/status/1", Source.X),
        ("https://www.twitter.com/user/status/1/video/2", Source.X),
        ("https://mobile.twitter.com/i/status/1", Source.X),
        ("https://m.twitter.com/user/status/1", Source.X),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", Source.YOUTUBE),
        ("https://youtube.com/shorts/dQw4w9WgXcQ?si=abc", Source.YOUTUBE),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", Source.YOUTUBE),
        ("https://www.reddit.com/r/funny/comments/1abcde/a_title/", Source.REDDIT),
        ("https://reddit.com/r/funny/s/AbCdEf123", Source.REDDIT),
        ("https://old.reddit.com/r/funny/comments/1abcde/x/", Source.REDDIT),
        ("https://new.reddit.com/r/funny/comments/1abcde/x/", Source.REDDIT),
        ("https://m.reddit.com/r/funny/comments/1abcde/x/", Source.REDDIT),
        ("https://redd.it/1abcde", Source.REDDIT),
        ("https://v.redd.it/abc123xyz", Source.REDDIT),
        ("https://www.facebook.com/reel/1234567890", Source.FACEBOOK),
        ("https://facebook.com/share/r/1AbCdEfGh/", Source.FACEBOOK),
        ("https://m.facebook.com/watch/?v=1234567890", Source.FACEBOOK),
        ("https://web.facebook.com/reel/1234567890", Source.FACEBOOK),
        ("https://fb.watch/abcDEF123/", Source.FACEBOOK),
    ],
)
def test_supported_urls(url, source):
    assert detect_source(url) == source


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://youtu.be/dQw4w9WgXcQ",  # YouTube is Shorts only (more sources spec 2)
        "https://www.youtube.com/@someone/shorts",
        "https://www.youtube.com/shorts/",
        "https://www.youtube.com/playlist?list=PL123",
        "https://music.youtube.com/shorts/dQw4w9WgXcQ",
        "https://notreddit.com/r/funny/comments/1abcde/x/",
        "https://facebook.com.evil.org/reel/1",
        "https://evil.instagram.com.example.org/reel/x",
        "https://notinstagram.com/reel/x",
        "ftp://www.tiktok.com/@user/video/1",
        "www.tiktok.com/@user/video/1",
        "https://x.com.evil.org/user/status/1",
        "https://notx.com/user/status/1",
        "https://t.co/abc123",
        "https://fxtwitter.com/user/status/1",  # only after normalize_url
        "",
        "not a url at all",
    ],
)
def test_unsupported_urls(url):
    with pytest.raises(JobError) as exc:
        detect_source(url)
    assert exc.value.code == ErrorCode.UNSUPPORTED_URL


@pytest.mark.parametrize(
    "text,expected",
    [
        ("https://vm.tiktok.com/ZMabc123/", "https://vm.tiktok.com/ZMabc123/"),
        ("  https://vm.tiktok.com/ZMabc123/  ", "https://vm.tiktok.com/ZMabc123/"),
        ("Check this out! https://vm.tiktok.com/ZMabc123/ #fyp", "https://vm.tiktok.com/ZMabc123/"),
        (
            "Check out user's video! https://www.tiktok.com/t/ZTRabc/ ",
            "https://www.tiktok.com/t/ZTRabc/",
        ),
        (
            "https://www.instagram.com/reel/C1abc/?igsh=xyz",
            "https://www.instagram.com/reel/C1abc/?igsh=xyz",
        ),
        ("look: https://www.instagram.com/reel/C1abc/.", "https://www.instagram.com/reel/C1abc/"),
        ("(https://vm.tiktok.com/ZMabc123/)", "https://vm.tiktok.com/ZMabc123/"),
        ('"https://vm.tiktok.com/ZMabc123/",', "https://vm.tiktok.com/ZMabc123/"),
        ("no link here", "no link here"),
        ("   ", ""),
    ],
)
def test_extract_url(text, expected):
    assert extract_url(text) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://fxtwitter.com/user/status/1", "https://x.com/user/status/1"),
        ("https://vxtwitter.com/user/status/1?s=46", "https://x.com/user/status/1"),
        ("https://fixupx.com/user/status/1/video/2", "https://x.com/user/status/1/video/2"),
        ("https://fixvx.com/i/status/1", "https://x.com/i/status/1"),
        ("https://d.fxtwitter.com/user/status/1", "https://x.com/user/status/1"),
        ("https://www.vxtwitter.com/user/status/1", "https://x.com/user/status/1"),
        ("https://FXTWITTER.COM/user/status/1", "https://x.com/user/status/1"),
        ("http://fxtwitter.com/user/status/1", "https://x.com/user/status/1"),
    ],
)
def test_normalize_url_rewrites_fixer_links(url, expected):
    assert normalize_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://X.com/user/status/1",  # yt-dlp's twitter extractor only matches lowercase
        "https://x.com/user/status/1?s=46&t=abc",  # share tracking: same tweet, same jobs
        "https://twitter.com/user/status/1",
        "https://mobile.twitter.com/user/status/1#top",
        "http://www.x.com/user/status/1",
        "https://m.twitter.com/user/status/1?ref_src=twsrc",
    ],
)
def test_normalize_url_canonicalises_x_links(url):
    assert normalize_url(url) == "https://x.com/user/status/1"


@pytest.mark.parametrize(
    "url",
    [
        "https://x.com/user/status/1",
        "https://www.tiktok.com/@user/video/1",
        "https://notfxtwitter.com/user/status/1",
        "https://fxtwitter.com.evil.org/user/status/1",
        "ftp://x.com/user/status/1",  # left for detect_source to reject
        "ftp://fxtwitter.com/user/status/1",
        "not a url at all",
        "",
    ],
)
def test_normalize_url_leaves_other_urls(url):
    assert normalize_url(url) == url


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://youtube.com/shorts/dQw4w9WgXcQ?si=abc", "https://www.youtube.com/shorts/dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube.com/shorts/dQw4w9WgXcQ"),
        ("HTTP://WWW.YOUTUBE.COM/shorts/dQw4w9WgXcQ/", "https://www.youtube.com/shorts/dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "https://www.youtube.com/shorts/dQw4w9WgXcQ"),
        (
            "https://www.reddit.com/r/funny/comments/1abcde/x/?utm_source=share&utm_medium=web",
            "https://www.reddit.com/r/funny/comments/1abcde/x/",
        ),
        ("https://reddit.com/r/funny/s/AbCdEf123?share_id=x", "https://reddit.com/r/funny/s/AbCdEf123"),
        ("https://v.redd.it/abc123xyz#t", "https://v.redd.it/abc123xyz"),
    ],
)
def test_normalize_url_gives_shorts_and_reddit_one_spelling(url, expected):
    assert normalize_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://www.facebook.com/watch/?v=1234567890",  # Facebook's query is the video
        "https://www.facebook.com/reel/1234567890?mibextid=abc",
        "https://www.youtube.com/watch?v=abc",  # not a Short: left for detect_source to reject
    ],
)
def test_normalize_url_leaves_facebook_and_other_youtube_links(url):
    assert normalize_url(url) == url
