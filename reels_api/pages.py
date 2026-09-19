"""Pages filled in on the server: the board, a shared reel and an expired one (links spec 6, 7; pop-up spec 4).

The HTML lives in static/ with {{name}} placeholders. Link-preview fetchers run no
JavaScript, so everything a preview needs is filled in here, on the server.
"""
from __future__ import annotations

import html
import json
import math
import re
from pathlib import Path

from reels_api.models import Job, Source, job_to_dict

STATIC_DIR = Path(__file__).parent / "static"
TITLE_MAX = 100
SOURCE_NAMES = {Source.TIKTOK: "TikTok", Source.INSTAGRAM: "Instagram", Source.X: "X"}
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def fill(template: str, values: dict[str, str], raw: dict[str, str] | None = None) -> str:
    """Replace each {{name}}: from raw as is, otherwise from values, HTML-escaped. Unknown names raise KeyError."""
    raw = raw or {}

    def replace(match: re.Match) -> str:
        name = match.group(1)
        if name in raw:
            return raw[name]
        return html.escape(values[name], quote=True)

    return _PLACEHOLDER.sub(replace, template)


def script_json(data: dict) -> str:
    """JSON that is safe inside <script type="application/json">: <, > and & become \\u escapes."""
    return json.dumps(data).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def preview_title(caption: str | None) -> str:
    """The caption on one line, at most 100 characters; "a reel" when there is none."""
    text = " ".join((caption or "").split())
    if not text:
        return "a reel"
    if len(text) > TITLE_MAX:
        return text[: TITLE_MAX - 1] + "…"
    return text


def _duration(seconds: float | None) -> str:
    """m:ss, floored; "" when unknown. Same rules as formatDuration in format.js."""
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return ""
    whole = int(seconds)
    return f"{whole // 60}:{whole % 60:02d}"


def preview_description(source: Source, duration_seconds: float | None) -> str:
    """ "TikTok · 0:19", without the duration when it is unknown. No expiry: previews are cached."""
    return " · ".join(part for part in (SOURCE_NAMES[source], _duration(duration_seconds)) if part)


def retention_text(hours: float) -> str:
    return f"{hours:g} hour" + ("" if hours == 1 else "s")


def render_watch(job: Job, base_url: str) -> str:
    """The view-only page for a done job. base_url has no trailing slash (links spec 6.1, 7.1)."""
    result = job.result
    key = job.share_key
    reel = job_to_dict(job)
    reel["file_url"] = f"/files/{job.id}.mp4?k={key}"
    if reel["thumbnail_url"]:
        reel["thumbnail_url"] = f"/files/{job.id}.jpg?k={key}"

    description = preview_description(result.source, result.duration_seconds)
    image_tag = ""
    if result.nsfw:
        description = f"NSFW · {description}"  # and no picture in the chat (NSFW cover spec 3)
    elif result.thumbnail_path is not None:
        image_url = html.escape(f"{base_url}/files/{job.id}.jpg?k={key}", quote=True)
        image_tag = f'<meta property="og:image" content="{image_url}">'

    template = (STATIC_DIR / "watch.html").read_text(encoding="utf-8")
    return fill(
        template,
        {
            "id": job.id,
            "title": preview_title(reel["caption"]),
            "description": description,
            "url": f"{base_url}/?reel={job.id}&k={key}",
        },
        raw={"image_tag": image_tag, "reel_json": script_json(reel)},
    )


def render_expired(retention_hours: float) -> str:
    """The page for a share link whose reel is gone (links spec 6.2)."""
    template = (STATIC_DIR / "expired.html").read_text(encoding="utf-8")
    return fill(template, {"hours": retention_text(retention_hours)})


def render_app(ask: bool) -> str:
    """The board. ask=True when the phone's cookie was set before the login page asked (pop-up spec 4)."""
    template = (STATIC_DIR / "app.html").read_text(encoding="utf-8")
    return fill(template, {"cookie": "ask" if ask else "agreed"})
