import re
from urllib.parse import urlparse

from reels_api.models import ErrorCode, JobError, Source

ALLOWED_HOSTS: dict[str, Source] = {
    "instagram.com": Source.INSTAGRAM,
    "www.instagram.com": Source.INSTAGRAM,
    "tiktok.com": Source.TIKTOK,
    "www.tiktok.com": Source.TIKTOK,
    "vm.tiktok.com": Source.TIKTOK,
    "vt.tiktok.com": Source.TIKTOK,
    "m.tiktok.com": Source.TIKTOK,
    "x.com": Source.X,
    "www.x.com": Source.X,
    "m.x.com": Source.X,
    "mobile.x.com": Source.X,
    "twitter.com": Source.X,
    "www.twitter.com": Source.X,
    "m.twitter.com": Source.X,
    "mobile.twitter.com": Source.X,
    "youtube.com": Source.YOUTUBE,
    "www.youtube.com": Source.YOUTUBE,
    "m.youtube.com": Source.YOUTUBE,
    "reddit.com": Source.REDDIT,
    "www.reddit.com": Source.REDDIT,
    "old.reddit.com": Source.REDDIT,
    "new.reddit.com": Source.REDDIT,
    "m.reddit.com": Source.REDDIT,
    "redd.it": Source.REDDIT,
    "v.redd.it": Source.REDDIT,
    "facebook.com": Source.FACEBOOK,
    "www.facebook.com": Source.FACEBOOK,
    "m.facebook.com": Source.FACEBOOK,
    "web.facebook.com": Source.FACEBOOK,
    "fb.watch": Source.FACEBOOK,
}

# YouTube is Shorts only (more sources spec 2): /shorts/<id>, perhaps with a trailing slash.
_SHORTS_PATH_RE = re.compile(r"/shorts/([A-Za-z0-9_-]{6,})/?")

# Sites that mirror x.com's paths so WhatsApp shows a preview. Their links are
# rewritten to x.com, subdomains included (d.fxtwitter.com is the direct link).
FIXER_HOSTS = ("fxtwitter.com", "vxtwitter.com", "fixupx.com", "fixvx.com")

_URL_RE = re.compile(r"https?://\S+")
_TRAILING_PUNCTUATION = ".,;:!?)]}>\"'"


def extract_url(text: str) -> str:
    """Pull the first http(s) URL out of share text.

    Returns the stripped text unchanged when there is no URL, so that
    detect_source can reject it with unsupported_url as before.
    """
    match = _URL_RE.search(text)
    if match is None:
        return text.strip()
    return match.group(0).rstrip(_TRAILING_PUNCTUATION)


def normalize_url(url: str) -> str:
    """One spelling per video, so a re-paste finds the same jobs; anything not named here is unchanged.

    - every X or fixer link becomes https://x.com/<path>: yt-dlp's twitter extractor only
      matches a lowercase host, and dropping the query (?s=46&t=… share tracking) lets the
      same tweet resolve to the same jobs;
    - a YouTube Short becomes https://www.youtube.com/shorts/<id> (drops ?si=);
    - a Reddit link loses its query (?utm_source=share…). Facebook keeps it: watch/?v= needs it.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if parsed.scheme.lower() not in ("http", "https"):
        return url
    host = (parsed.hostname or "").lower()
    source = ALLOWED_HOSTS.get(host)
    if source == Source.X or any(host == h or host.endswith("." + h) for h in FIXER_HOSTS):
        return f"https://x.com{parsed.path}"
    if source == Source.YOUTUBE and (short := _SHORTS_PATH_RE.fullmatch(parsed.path)):
        return f"https://www.youtube.com/shorts/{short.group(1)}"
    if source == Source.REDDIT:
        return f"https://{host}{parsed.path}"
    return url


def detect_source(url: str) -> Source:
    """Return which platform a share link belongs to, or raise unsupported_url."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        raise JobError(ErrorCode.UNSUPPORTED_URL)
    if parsed.scheme.lower() not in ("http", "https"):
        raise JobError(ErrorCode.UNSUPPORTED_URL)
    host = (parsed.hostname or "").lower()
    source = ALLOWED_HOSTS.get(host)
    if source is None or (source == Source.YOUTUBE and not _SHORTS_PATH_RE.fullmatch(parsed.path)):
        raise JobError(ErrorCode.UNSUPPORTED_URL)
    return source
