from pathlib import Path

import pytest
import yt_dlp
from yt_dlp.utils import DownloadError

from reels_api import downloader
from reels_api.models import ErrorCode, JobError


@pytest.mark.parametrize(
    "message,code",
    [
        ("ERROR: [Instagram] C1abc: Requested content is not available, rate-limit reached or login required", ErrorCode.LOGIN_REQUIRED),
        ("ERROR: [Instagram] login required to view this post", ErrorCode.LOGIN_REQUIRED),
        ("ERROR: You need to log in to access this content", ErrorCode.LOGIN_REQUIRED),
        ("ERROR: The provided cookies are invalid or expired", ErrorCode.LOGIN_REQUIRED),
        ("ERROR: [TikTok] 123: This video is private", ErrorCode.PRIVATE_OR_REMOVED),
        ("ERROR: [Instagram] C1abc: This post does not exist", ErrorCode.PRIVATE_OR_REMOVED),
        ("ERROR: Unable to download webpage: HTTP Error 404: Not Found", ErrorCode.PRIVATE_OR_REMOVED),
        ("ERROR: [TikTok] 123: Video not available", ErrorCode.PRIVATE_OR_REMOVED),
        ("ERROR: [TikTok] 123: Video unavailable", ErrorCode.PRIVATE_OR_REMOVED),
        ("ERROR: Unsupported URL: https://example.com/x", ErrorCode.UNSUPPORTED_URL),
        ("ERROR: [TikTok] Unable to extract webpage video data", ErrorCode.PLATFORM_BLOCKED),
        ("ERROR: HTTP Error 429: Too Many Requests", ErrorCode.PLATFORM_BLOCKED),
        ("ERROR: something completely new", ErrorCode.PLATFORM_BLOCKED),
        ("ERROR: [twitter] 20: No video could be found in this tweet", ErrorCode.NO_VIDEO),
        ("ERROR: [twitter] 1: Media #1 is not a video", ErrorCode.NO_VIDEO),
        ("ERROR: No suitable extractor found for URL https://example.com/article", ErrorCode.NO_VIDEO),
        ("ERROR: [twitter] 1: Twitter API says: This Post was deleted by the Post author", ErrorCode.PRIVATE_OR_REMOVED),
        ("ERROR: [twitter] 1: Twitter API says: This Post is from a suspended account", ErrorCode.PRIVATE_OR_REMOVED),
        ("ERROR: [twitter] 1: Requested tweet is unavailable", ErrorCode.PRIVATE_OR_REMOVED),
        (
            "ERROR: [twitter] 1: Twitter API says: This Post is from an account that no longer exists",
            ErrorCode.PRIVATE_OR_REMOVED,
        ),
        (
            "ERROR: [twitter] 1: NSFW tweet requires authentication. Use --cookies-from-browser or --cookies for the authentication",
            ErrorCode.LOGIN_REQUIRED,
        ),
    ],
)
def test_map_ytdlp_error(message, code):
    assert downloader.map_ytdlp_error(message) == code


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: writes a file and returns an info dict."""

    last_opts: dict = {}
    last_call: dict = {}
    info: dict = {"title": "Hello", "duration": 12.5, "width": 720, "height": 1280}
    raise_message: str | None = None

    def __init__(self, opts):
        FakeYDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True, process=True):
        FakeYDL.last_call = {"url": url, "download": download, "process": process}
        if FakeYDL.raise_message:
            raise DownloadError(FakeYDL.raise_message)
        if download:
            out = Path(self.__class__.last_opts["outtmpl"].replace("%(ext)s", "mp4"))
            out.write_bytes(b"\x00" * 10)
        return dict(self.__class__.info)


@pytest.fixture
def fake_ydl(monkeypatch):
    FakeYDL.raise_message = None
    FakeYDL.last_call = {}
    FakeYDL.info = {"title": "Hello", "duration": 12.5, "width": 720, "height": 1280}
    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def test_download_success(tmp_path, fake_ydl):
    result = downloader.download("https://vm.tiktok.com/x/", tmp_path)
    assert result.path == tmp_path / "source.mp4"
    assert result.path.exists()
    assert result.info.title == "Hello"
    assert result.info.duration_seconds == 12.5
    assert result.info.width == 720
    assert result.info.height == 1280
    assert fake_ydl.last_opts["format"] == downloader.FORMAT
    assert fake_ydl.last_opts["quiet"] is True
    assert "cookiefile" not in fake_ydl.last_opts


def test_download_passes_cookies(tmp_path, fake_ydl):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    downloader.download("https://www.instagram.com/reel/x/", tmp_path, cookies_file=cookies)
    assert fake_ydl.last_opts["cookiefile"] == str(cookies)


def test_download_missing_title_falls_back(tmp_path, fake_ydl):
    fake_ydl.info = {"id": "123"}
    result = downloader.download("https://vm.tiktok.com/x/", tmp_path)
    assert result.info.title == "video"
    assert result.info.duration_seconds is None


def test_download_maps_errors(tmp_path, fake_ydl):
    fake_ydl.raise_message = "ERROR: [TikTok] 123: This video is private"
    with pytest.raises(JobError) as exc:
        downloader.download("https://vm.tiktok.com/x/", tmp_path)
    assert exc.value.code == ErrorCode.PRIVATE_OR_REMOVED


def test_download_no_file_is_platform_blocked(tmp_path, monkeypatch):
    class NoFileYDL(FakeYDL):
        def extract_info(self, url, download=True):
            return {"title": "x"}

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", NoFileYDL)
    with pytest.raises(JobError) as exc:
        downloader.download("https://vm.tiktok.com/x/", tmp_path)
    assert exc.value.code == ErrorCode.PLATFORM_BLOCKED


def test_ytdlp_version_is_string():
    assert isinstance(downloader.ytdlp_version(), str)
    assert downloader.ytdlp_version()


def test_download_caption_from_description(tmp_path, fake_ydl):
    fake_ydl.info = {"title": "Video by someone", "description": "  Tag 1 Friend reverse this Video  ", "duration": 5}
    result = downloader.download("https://www.instagram.com/reel/x/", tmp_path)
    assert result.info.caption == "Tag 1 Friend reverse this Video"


@pytest.mark.parametrize("description", [None, "", "   "])
def test_download_caption_falls_back_to_title(tmp_path, fake_ydl, description):
    fake_ydl.info = {"title": "Hello", "description": description}
    result = downloader.download("https://vm.tiktok.com/x/", tmp_path)
    assert result.info.caption == "Hello"


def test_download_caption_without_title_or_description(tmp_path, fake_ydl):
    fake_ydl.info = {"id": "123"}
    result = downloader.download("https://vm.tiktok.com/x/", tmp_path)
    assert result.info.caption == "video"


X_URL = "https://x.com/user/status/1577719286659006464"


def test_download_takes_first_entry_by_default(tmp_path, fake_ydl):
    downloader.download(X_URL, tmp_path)
    assert fake_ydl.last_opts["playlist_items"] == "1"


def test_download_takes_the_given_entry(tmp_path, fake_ydl):
    downloader.download(X_URL, tmp_path, item=3)
    assert fake_ydl.last_opts["playlist_items"] == "3"


def test_x_download_is_limited_to_twitter_extractors(tmp_path, fake_ydl):
    downloader.download(X_URL, tmp_path)
    assert fake_ydl.last_opts["allowed_extractors"] == downloader.X_EXTRACTORS


@pytest.mark.parametrize("url", ["https://vm.tiktok.com/x/", "https://www.instagram.com/reel/x/"])
def test_other_downloads_keep_default_extractors(tmp_path, fake_ydl, url):
    downloader.download(url, tmp_path)
    assert "allowed_extractors" not in fake_ydl.last_opts


def test_x_extractors_load_twitter_and_not_generic():
    # A tweet that only links elsewhere must not be followed to that site (X links spec 5).
    ydl = yt_dlp.YoutubeDL({"quiet": True, "allowed_extractors": downloader.X_EXTRACTORS})
    assert "Twitter" in ydl._ies
    assert "Generic" not in ydl._ies
    assert "Youtube" not in ydl._ies


@pytest.mark.parametrize(
    "description,caption",
    [
        ("Test https://t.co/Y3KEZD7Dad", "Test"),
        ("FULL VIDEO - https://t.co/DOJJn2VThV https://t.co/iPBUyVKw4s", "FULL VIDEO - https://t.co/DOJJn2VThV"),
        ("see https://t.co/abc in here", "see https://t.co/abc in here"),
    ],
)
def test_download_caption_drops_the_trailing_tco_link(tmp_path, fake_ydl, description, caption):
    fake_ydl.info = {"title": "Name - Title", "description": description}
    result = downloader.download(X_URL, tmp_path)
    assert result.info.caption == caption


@pytest.mark.parametrize(
    "title,clean",
    [
        # yt-dlp only strips a link with a space before it, so a tweet that is just its video keeps it.
        ("Some User - https://t.co/zom968d0a0", "Some User"),
        ("Some User - https://t.co/zom968d0a0 #2", "Some User #2"),
        ("Ultima - Test #2", "Ultima - Test #2"),
        ("Video by someone", "Video by someone"),
    ],
)
def test_download_title_drops_tco_links(tmp_path, fake_ydl, title, clean):
    fake_ydl.info = {"title": title, "description": "https://t.co/zom968d0a0"}
    result = downloader.download(X_URL, tmp_path)
    assert result.info.title == clean
    assert result.info.caption == clean  # nothing left of the description: falls back to the title


def test_count_videos_counts_playlist_entries(fake_ydl):
    fake_ydl.info = {"_type": "playlist", "entries": [{"id": "a"}, None, {"id": "b"}, {"id": "c"}]}
    assert downloader.count_videos(X_URL) == 3
    assert fake_ydl.last_call == {"url": X_URL, "download": False, "process": False}
    assert fake_ydl.last_opts["allowed_extractors"] == downloader.X_EXTRACTORS


def test_count_videos_gives_up_on_a_slow_socket_before_the_count_cap(fake_ydl):
    # jobs.COUNT_TIMEOUT_SECONDS stops waiting at 20 s, but the thread runs on until yt-dlp gives up.
    fake_ydl.info = {"id": "a"}
    downloader.count_videos(X_URL)
    assert fake_ydl.last_opts["socket_timeout"] == downloader.COUNT_SOCKET_TIMEOUT_SECONDS < 20


def test_count_videos_single_video_is_one(fake_ydl):
    fake_ydl.info = {"id": "a", "formats": []}
    assert downloader.count_videos(X_URL) == 1


def test_count_videos_is_capped(fake_ydl):
    fake_ydl.info = {"_type": "playlist", "entries": [{"id": str(i)} for i in range(20)]}
    assert downloader.count_videos(X_URL) == downloader.MAX_VIDEOS_PER_POST


def test_count_videos_empty_playlist_is_one(fake_ydl):
    fake_ydl.info = {"_type": "playlist", "entries": []}
    assert downloader.count_videos(X_URL) == 1


def test_count_videos_error_is_one(fake_ydl):
    fake_ydl.raise_message = "ERROR: [twitter] 20: No video could be found in this tweet"
    assert downloader.count_videos(X_URL) == 1


def test_count_videos_passes_cookies(tmp_path, fake_ydl):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    downloader.count_videos(X_URL, cookies_file=cookies)
    assert fake_ydl.last_opts["cookiefile"] == str(cookies)


@pytest.mark.parametrize("age_limit,nsfw", [(18, True), (21, True), ("18", True), (0, False), (None, False), ("junk", False)])
def test_download_marks_adult_content_nsfw(tmp_path, fake_ydl, age_limit, nsfw):
    fake_ydl.info = {"title": "Hello", "age_limit": age_limit}
    result = downloader.download(X_URL, tmp_path)
    assert result.info.nsfw is nsfw
