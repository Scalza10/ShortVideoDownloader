from pathlib import Path

import pytest
import yt_dlp
from yt_dlp.networking.exceptions import TransportError
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


SHORT_URL = "https://www.youtube.com/shorts/dQw4w9WgXcQ"
REDDIT_URL = "https://www.reddit.com/r/funny/comments/1abcde/a_title/"
FACEBOOK_URL = "https://www.facebook.com/reel/1234567890"


@pytest.mark.parametrize(
    "url,names",
    [
        (X_URL, downloader.X_EXTRACTORS),
        (SHORT_URL, ["youtube"]),
        (REDDIT_URL, ["Reddit"]),
        (FACEBOOK_URL, ["facebook", "facebook:reel"]),
    ],
)
def test_guarded_sources_are_limited_to_their_own_extractors(tmp_path, fake_ydl, url, names):
    downloader.download(url, tmp_path)
    assert fake_ydl.last_opts["allowed_extractors"] == names


@pytest.mark.parametrize("names", list(downloader.ALLOWED_EXTRACTORS.values()))
def test_allowed_extractors_load_and_never_generic(names):
    # A post that only links elsewhere must not be followed to that site (more sources spec 4).
    ydl = yt_dlp.YoutubeDL({"quiet": True, "allowed_extractors": names})
    assert sorted(ie.IE_NAME for ie in ydl._ies.values()) == sorted(names)
    assert "Generic" not in ydl._ies


@pytest.mark.parametrize(
    "url",
    [
        SHORT_URL,
        "https://m.youtube.com/shorts/dQw4w9WgXcQ",
        REDDIT_URL,
        "https://old.reddit.com/r/funny/comments/1abcde/x/",
        FACEBOOK_URL,
        "https://www.facebook.com/watch/?v=1234567890",
        "https://www.facebook.com/somepage/videos/1234567890/",
    ],
)
def test_full_links_need_no_redirect(tmp_path, fake_ydl, monkeypatch, url):
    monkeypatch.setattr(downloader, "_follow_redirects", lambda url, opts: pytest.fail("followed a redirect"))
    downloader.download(url, tmp_path)
    assert fake_ydl.last_call["url"] == url


@pytest.mark.parametrize(
    "share,final",
    [
        ("https://www.reddit.com/r/funny/s/AbCdEf123", REDDIT_URL + "?share_id=x"),
        ("https://redd.it/1abcde", REDDIT_URL),
        ("https://v.redd.it/abc123xyz", REDDIT_URL),
        ("https://www.facebook.com/share/r/1AbCdEfGh/", FACEBOOK_URL + "/?mibextid=x"),
        ("https://www.facebook.com/share/v/1AbCdEfGh/", "https://www.facebook.com/watch/?v=1234567890"),
        ("https://fb.watch/abcDEF123/", "https://m.facebook.com/watch/?v=1234567890"),
    ],
)
def test_share_links_download_where_they_lead(tmp_path, fake_ydl, monkeypatch, share, final):
    followed = []
    monkeypatch.setattr(downloader, "_follow_redirects", lambda url, opts: followed.append(url) or final)
    downloader.download(share, tmp_path)
    assert followed == [share]
    assert fake_ydl.last_call["url"] == final


@pytest.mark.parametrize(
    "final,code",
    [
        ("https://www.youtube.com/watch?v=abc", ErrorCode.NO_VIDEO),  # off the source's own hosts
        ("https://example.com/video", ErrorCode.NO_VIDEO),
        ("https://www.facebook.com/login/?next=x", ErrorCode.LOGIN_REQUIRED),
        ("https://www.facebook.com/", ErrorCode.NO_VIDEO),
    ],
)
def test_share_links_that_lead_nowhere_useful_fail(tmp_path, fake_ydl, monkeypatch, final, code):
    monkeypatch.setattr(downloader, "_follow_redirects", lambda url, opts: final)
    with pytest.raises(JobError) as exc:
        downloader.download("https://fb.watch/abcDEF123/", tmp_path)
    assert exc.value.code == code
    assert fake_ydl.last_call == {}


@pytest.mark.parametrize(
    "message,code",
    [("HTTP Error 404: Not Found", ErrorCode.PRIVATE_OR_REMOVED), ("HTTP Error 403: Forbidden", ErrorCode.PLATFORM_BLOCKED)],
)
def test_following_a_share_link_maps_its_errors(tmp_path, monkeypatch, message, code):
    class FailingYDL:
        def __init__(self, opts):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def urlopen(self, url):
            raise TransportError(message)

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", FailingYDL)
    with pytest.raises(JobError) as exc:
        downloader.download("https://redd.it/1abcde", tmp_path)
    assert exc.value.code == code


def test_following_a_share_link_returns_the_final_url(monkeypatch):
    class Response:
        url = REDDIT_URL

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class RedirectYDL:
        opts = None

        def __init__(self, opts):
            RedirectYDL.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def urlopen(self, url):
            return Response()

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", RedirectYDL)
    assert downloader._follow_redirects("https://redd.it/1abcde", {"quiet": True}) == REDDIT_URL


def test_download_without_a_limit_has_no_length_filter(tmp_path, fake_ydl):
    downloader.download("https://vm.tiktok.com/x/", tmp_path)
    assert "match_filter" not in fake_ydl.last_opts


@pytest.mark.parametrize("duration,skipped", [(181, True), (180, False), (12.5, False), (None, False), ("junk", False)])
def test_length_filter_skips_long_videos_before_downloading(tmp_path, fake_ydl, duration, skipped):
    downloader.download("https://vm.tiktok.com/x/", tmp_path, max_duration=180)
    check = fake_ydl.last_opts["match_filter"]
    assert bool(check({"duration": duration}, incomplete=False)) is skipped


def test_a_video_over_the_limit_is_too_long(tmp_path, fake_ydl):
    fake_ydl.info = {"title": "Long", "duration": 600}
    with pytest.raises(JobError) as exc:
        downloader.download(SHORT_URL, tmp_path, max_duration=180)
    assert exc.value.code == ErrorCode.TOO_LONG
    assert exc.value.message == "Videos longer than 3 minutes aren't supported."


def test_a_long_video_skipped_by_the_filter_is_too_long_not_blocked(tmp_path, monkeypatch):
    class SkippingYDL(FakeYDL):
        def extract_info(self, url, download=True, process=True):
            return {"title": "Long", "duration": 600}  # match_filter said no: no file

    monkeypatch.setattr(downloader.yt_dlp, "YoutubeDL", SkippingYDL)
    with pytest.raises(JobError) as exc:
        downloader.download("https://vm.tiktok.com/x/", tmp_path, max_duration=180)
    assert exc.value.code == ErrorCode.TOO_LONG


def test_youtube_caption_is_the_title(tmp_path, fake_ydl):
    fake_ydl.info = {"title": "cat vs cucumber #shorts", "description": "Subscribe! https://example.com #cats"}
    result = downloader.download(SHORT_URL, tmp_path)
    assert result.info.caption == "cat vs cucumber #shorts"


@pytest.mark.parametrize(
    "title,clean",
    [
        (
            "9.9K views · 340 reactions | When your trying to help | Beast Camp Training",
            "When your trying to help",
        ),
        ("1M views · 2.1K reactions | a | b | Some Page", "a | b"),  # a caption may hold " | " itself
        ("12 views | short one | Some Page", "short one"),
        ("A plain title", "A plain title"),
        ("A plain title | Some Page", "A plain title"),
    ],
)
def test_facebook_title_drops_its_counts_and_page_name(tmp_path, fake_ydl, title, clean):
    # Facebook's title is "<views> · <reactions> | <caption> | <page>" (more sources spec 6).
    fake_ydl.info = {"title": title, "uploader": "Some Page" if "Some Page" in title else "Beast Camp Training"}
    result = downloader.download(FACEBOOK_URL, tmp_path)
    assert result.info.title == clean


def test_other_titles_keep_their_pipes(tmp_path, fake_ydl):
    fake_ydl.info = {"title": "1M views | a | b", "uploader": "b"}
    assert downloader.download("https://vm.tiktok.com/x/", tmp_path).info.title == "1M views | a | b"
