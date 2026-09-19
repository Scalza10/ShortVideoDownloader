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
    ],
)
def test_supported_urls(url, source):
    assert detect_source(url) == source


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
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
