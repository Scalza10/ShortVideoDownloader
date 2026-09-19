# Reels Download API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An HTTP API that accepts an Instagram Reel or TikTok share link, downloads it, and serves a WhatsApp-compatible MP4.

**Architecture:** One FastAPI process. POST /jobs enqueues a job; N asyncio workers run a blocking pipeline (yt-dlp download, ffprobe, ffmpeg remux) in threads; GET /jobs/{id} reports status; GET /files/{id}.mp4 streams the result. Job state is in memory, files on local disk, a sweeper deletes expired files. Packaged as one Docker container.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, pydantic-settings, yt-dlp (library), ffmpeg/ffprobe (subprocess), pytest + anyio + httpx for tests, Docker.

**Spec:** `docs/superpowers/specs/2026-09-16-reels-download-api-design.md`

## Global Constraints

- Python 3.12. Package name `reels_api`, tests in `tests/`.
- `fastapi>=0.115` (brings starlette>=0.40, whose `FileResponse` handles HTTP Range).
- yt-dlp is used as a library, never as a subprocess. ffmpeg and ffprobe are subprocesses.
- Every environment variable, default, endpoint path, JSON field name and error code is exactly as written in the spec sections 4 and 7. Do not rename.
- WhatsApp size limit constant: `WHATSAPP_MAX_BYTES = 16 * 1024 * 1024`.
- Error JSON body shape everywhere: `{"error": "<code>", "message": "<text>"}`.
- Modules depend only on modules listed above them in spec section 8: settings → auth → models → urls → downloader → media → pipeline → jobs → routes → main.
- Tests never touch the network or require ffmpeg, except `tests/test_integration.py` which is marked `network` and skipped by default.
- Commit after every task. Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Development machine is Windows; run commands from PowerShell or Git Bash in `C:\Project\ReelsTranslator`. Use `python -m pytest`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | pytest config (markers, default `-m "not network"`) |
| `requirements.txt` | runtime deps, pinned |
| `requirements-dev.txt` | test deps |
| `reels_api/settings.py` | `Settings` from env vars |
| `reels_api/models.py` | enums, `JobError`, `Job`, `JobResult`, request models, `job_to_dict` |
| `reels_api/urls.py` | `detect_source(url)` |
| `reels_api/downloader.py` | yt-dlp wrapper, `map_ytdlp_error` |
| `reels_api/media.py` | ffprobe parsing, ffmpeg command building and execution |
| `reels_api/pipeline.py` | `Pipeline.run(job, set_status)` with injectable stages |
| `reels_api/jobs.py` | `JobStore`, `JobManager` (queue, workers, sweeper) |
| `reels_api/auth.py` | `require_api_key` dependency |
| `reels_api/routes.py` | the four endpoints |
| `reels_api/main.py` | `create_app()` factory, exception handlers |
| `tests/conftest.py` | `anyio_backend`, `make_settings` helper |
| `Dockerfile`, `docker-compose.yml`, `.env.example`, `README.md` | packaging and docs |

---

### Task 1: Project scaffolding and Settings

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `.env.example`
- Create: `reels_api/__init__.py`, `reels_api/settings.py`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/test_settings.py`

**Interfaces:**
- Produces: `reels_api.settings.Settings` (pydantic-settings `BaseSettings`) with fields `api_key: str`, `storage_dir: Path`, `temp_dir: Path`, `retention_hours: float`, `workers: int`, `max_queue: int`, `job_timeout_seconds: int`, `cookies_file: Path | None`, `public_base_url: str | None`, `log_level: str`.
- Produces: test helper `make_settings(tmp_path, **overrides) -> Settings` in `tests/conftest.py`.

- [ ] **Step 1: Create a virtual environment and dependency files**

`requirements.txt` (unpinned for now; pinned in step 3):

```
fastapi
uvicorn[standard]
pydantic-settings
yt-dlp
```

`requirements-dev.txt`:

```
-r requirements.txt
pytest
anyio
httpx
```

`pyproject.toml`:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-m 'not network'"
markers = [
    "network: hits the real internet and needs ffmpeg; run with `pytest -m network`",
]
```

`.env.example`:

```
API_KEY=change-me
STORAGE_DIR=./data/files
TEMP_DIR=./data/tmp
RETENTION_HOURS=6
WORKERS=2
MAX_QUEUE=20
JOB_TIMEOUT_SECONDS=180
# COOKIES_FILE=./cookies.txt
# PUBLIC_BASE_URL=https://reels.example.com
LOG_LEVEL=info
```

- [ ] **Step 2: Install**

Run (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Expected: installs without error.

- [ ] **Step 3: Pin runtime versions**

Run: `python -m pip freeze | Select-String -Pattern "^(fastapi|uvicorn|pydantic-settings|yt-dlp)=="`

Replace the four lines in `requirements.txt` with the exact `name==version` lines printed. yt-dlp changes often; this pin is what you bump when TikTok breaks.

- [ ] **Step 4: Write the failing settings test**

`tests/__init__.py`: empty file.

`tests/conftest.py`:

```python
from pathlib import Path

import pytest

from reels_api.settings import Settings


@pytest.fixture
def anyio_backend():
    return "asyncio"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values = {
        "api_key": "test-key",
        "storage_dir": tmp_path / "files",
        "temp_dir": tmp_path / "tmp",
        "retention_hours": 6,
        "workers": 1,
        "max_queue": 5,
        "job_timeout_seconds": 30,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)
```

`tests/test_settings.py`:

```python
from pathlib import Path

import pytest

from reels_api.settings import Settings


def test_defaults_applied(monkeypatch):
    monkeypatch.setenv("API_KEY", "abc")
    s = Settings(_env_file=None)
    assert s.api_key == "abc"
    assert s.storage_dir == Path("/data/files")
    assert s.temp_dir == Path("/data/tmp")
    assert s.retention_hours == 6
    assert s.workers == 2
    assert s.max_queue == 20
    assert s.job_timeout_seconds == 180
    assert s.cookies_file is None
    assert s.public_base_url is None
    assert s.log_level == "info"


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("API_KEY", "abc")
    monkeypatch.setenv("WORKERS", "4")
    monkeypatch.setenv("COOKIES_FILE", "/secrets/cookies.txt")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://x.example")
    s = Settings(_env_file=None)
    assert s.workers == 4
    assert s.cookies_file == Path("/secrets/cookies.txt")
    assert s.public_base_url == "https://x.example"


def test_api_key_required(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    with pytest.raises(Exception):
        Settings(_env_file=None)
```

- [ ] **Step 5: Run to verify it fails**

Run: `python -m pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reels_api'`

- [ ] **Step 6: Implement Settings**

`reels_api/__init__.py`: empty file.

`reels_api/settings.py`:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration, read from environment variables (or a .env file)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    api_key: str
    storage_dir: Path = Path("/data/files")
    temp_dir: Path = Path("/data/tmp")
    retention_hours: float = 6
    workers: int = 2
    max_queue: int = 20
    job_timeout_seconds: int = 180
    cookies_file: Path | None = None
    public_base_url: str | None = None
    log_level: str = "info"
```

- [ ] **Step 7: Run to verify it passes**

Run: `python -m pytest tests/test_settings.py -v`
Expected: 3 passed

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml requirements.txt requirements-dev.txt .env.example reels_api tests
git commit -m "feat: project scaffolding and Settings

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Models and URL validation

**Files:**
- Create: `reels_api/models.py`, `reels_api/urls.py`
- Test: `tests/test_models.py`, `tests/test_urls.py`

**Interfaces:**
- Produces (models): `Source` enum (`instagram`, `tiktok`); `JobStatus` enum (`queued`, `downloading`, `processing`, `done`, `failed`); `ErrorCode` enum (`unsupported_url`, `private_or_removed`, `login_required`, `platform_blocked`, `processing_failed`, `timeout`, `too_many_jobs`); `ERROR_MESSAGES: dict[ErrorCode, str]`; `WHATSAPP_MAX_BYTES`; `class JobError(Exception)` with `.code` and `.message`; `@dataclass MediaInfo(title, duration_seconds, width, height)`; `@dataclass JobResult(file_path, title, source, duration_seconds, size_bytes, width, height)` with property `whatsapp_ok`; `@dataclass Job(id, url, source, status, created_at, finished_at, expires_at, result, error, message)`; `class CreateJobRequest(BaseModel)` with `url: str`; `job_to_dict(job, public_base_url=None) -> dict`.
- Produces (urls): `detect_source(url: str) -> Source`, raises `JobError(ErrorCode.UNSUPPORTED_URL)`.

- [ ] **Step 1: Write the failing model tests**

`tests/test_models.py`:

```python
from datetime import UTC, datetime
from pathlib import Path

from reels_api.models import (
    WHATSAPP_MAX_BYTES,
    ErrorCode,
    Job,
    JobError,
    JobResult,
    JobStatus,
    Source,
    job_to_dict,
)


def _result(size: int) -> JobResult:
    return JobResult(
        file_path=Path("/data/files/abc.mp4"),
        title="Hello World",
        source=Source.TIKTOK,
        duration_seconds=23.4,
        size_bytes=size,
        width=1080,
        height=1920,
    )


def test_job_error_default_message():
    err = JobError(ErrorCode.LOGIN_REQUIRED)
    assert err.code == ErrorCode.LOGIN_REQUIRED
    assert "log" in err.message.lower()
    assert str(err) == err.message


def test_job_error_custom_message():
    err = JobError(ErrorCode.PROCESSING_FAILED, "ffmpeg exploded")
    assert err.message == "ffmpeg exploded"


def test_whatsapp_ok_threshold():
    assert _result(WHATSAPP_MAX_BYTES).whatsapp_ok is True
    assert _result(WHATSAPP_MAX_BYTES + 1).whatsapp_ok is False


def test_job_to_dict_queued():
    job = Job(id="abc", url="https://www.tiktok.com/@a/video/1", source=Source.TIKTOK)
    assert job_to_dict(job) == {"id": "abc", "status": "queued"}


def test_job_to_dict_done_relative_and_absolute_url():
    job = Job(id="abc", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    job.result = _result(4812390)
    job.expires_at = datetime(2026, 9, 16, 22, 15, tzinfo=UTC)

    d = job_to_dict(job)
    assert d["status"] == "done"
    assert d["file_url"] == "/files/abc.mp4"
    assert d["title"] == "Hello World"
    assert d["source"] == "tiktok"
    assert d["duration_seconds"] == 23.4
    assert d["size_bytes"] == 4812390
    assert d["width"] == 1080
    assert d["height"] == 1920
    assert d["whatsapp_ok"] is True
    assert d["expires_at"] == "2026-09-16T22:15:00Z"

    d2 = job_to_dict(job, public_base_url="https://reels.example.com/")
    assert d2["file_url"] == "https://reels.example.com/files/abc.mp4"


def test_job_to_dict_failed():
    job = Job(id="abc", url="u", source=Source.INSTAGRAM, status=JobStatus.FAILED)
    job.error = ErrorCode.PRIVATE_OR_REMOVED
    job.message = "gone"
    assert job_to_dict(job) == {
        "id": "abc",
        "status": "failed",
        "error": "private_or_removed",
        "message": "gone",
    }
```

- [ ] **Step 2: Write the failing URL tests**

`tests/test_urls.py`:

```python
import pytest

from reels_api.models import ErrorCode, JobError, Source
from reels_api.urls import detect_source


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
        "",
        "not a url at all",
    ],
)
def test_unsupported_urls(url):
    with pytest.raises(JobError) as exc:
        detect_source(url)
    assert exc.value.code == ErrorCode.UNSUPPORTED_URL
```

- [ ] **Step 3: Run to verify they fail**

Run: `python -m pytest tests/test_models.py tests/test_urls.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reels_api.models'`

- [ ] **Step 4: Implement models.py**

`reels_api/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

WHATSAPP_MAX_BYTES = 16 * 1024 * 1024


class Source(StrEnum):
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ErrorCode(StrEnum):
    UNSUPPORTED_URL = "unsupported_url"
    PRIVATE_OR_REMOVED = "private_or_removed"
    LOGIN_REQUIRED = "login_required"
    PLATFORM_BLOCKED = "platform_blocked"
    PROCESSING_FAILED = "processing_failed"
    TIMEOUT = "timeout"
    TOO_MANY_JOBS = "too_many_jobs"


ERROR_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.UNSUPPORTED_URL: "Only Instagram and TikTok video links are supported.",
    ErrorCode.PRIVATE_OR_REMOVED: "This post is private or no longer exists.",
    ErrorCode.LOGIN_REQUIRED: "The platform requires a login to view this post.",
    ErrorCode.PLATFORM_BLOCKED: "The platform blocked the download. Try again later.",
    ErrorCode.PROCESSING_FAILED: "The video could not be processed.",
    ErrorCode.TIMEOUT: "The download took too long and was cancelled.",
    ErrorCode.TOO_MANY_JOBS: "Too many downloads are queued. Try again in a minute.",
}


class JobError(Exception):
    """Any failure that should be reported to the client with an ErrorCode."""

    def __init__(self, code: ErrorCode, message: str | None = None):
        self.code = code
        self.message = message or ERROR_MESSAGES[code]
        super().__init__(self.message)


@dataclass
class MediaInfo:
    title: str
    duration_seconds: float | None
    width: int | None
    height: int | None


@dataclass
class JobResult:
    file_path: Path
    title: str
    source: Source
    duration_seconds: float | None
    size_bytes: int
    width: int | None
    height: int | None

    @property
    def whatsapp_ok(self) -> bool:
        return self.size_bytes <= WHATSAPP_MAX_BYTES


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class Job:
    id: str
    url: str
    source: Source
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime = field(default_factory=utcnow)
    finished_at: datetime | None = None
    expires_at: datetime | None = None
    result: JobResult | None = None
    error: ErrorCode | None = None
    message: str | None = None


class CreateJobRequest(BaseModel):
    url: str


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def job_to_dict(job: Job, public_base_url: str | None = None) -> dict:
    """The JSON body for GET /jobs/{id}, exactly as in the spec."""
    body: dict = {"id": job.id, "status": job.status.value}
    if job.status == JobStatus.DONE and job.result is not None:
        r = job.result
        file_url = f"/files/{job.id}.mp4"
        if public_base_url:
            file_url = public_base_url.rstrip("/") + file_url
        body.update(
            {
                "file_url": file_url,
                "title": r.title,
                "source": r.source.value,
                "duration_seconds": r.duration_seconds,
                "size_bytes": r.size_bytes,
                "width": r.width,
                "height": r.height,
                "whatsapp_ok": r.whatsapp_ok,
                "expires_at": _iso_z(job.expires_at) if job.expires_at else None,
            }
        )
    elif job.status == JobStatus.FAILED:
        body["error"] = job.error.value if job.error else ErrorCode.PROCESSING_FAILED.value
        body["message"] = job.message or ERROR_MESSAGES[job.error or ErrorCode.PROCESSING_FAILED]
    return body
```

- [ ] **Step 5: Implement urls.py**

`reels_api/urls.py`:

```python
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
}


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
    if source is None:
        raise JobError(ErrorCode.UNSUPPORTED_URL)
    return source
```

- [ ] **Step 6: Run to verify they pass**

Run: `python -m pytest tests/test_models.py tests/test_urls.py -v`
Expected: all passed (6 model tests, 15 URL cases)

- [ ] **Step 7: Commit**

```bash
git add reels_api/models.py reels_api/urls.py tests/test_models.py tests/test_urls.py
git commit -m "feat: job models, error codes and URL validation

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: yt-dlp downloader with error mapping

**Files:**
- Create: `reels_api/downloader.py`
- Test: `tests/test_downloader.py`

**Interfaces:**
- Consumes: `MediaInfo`, `JobError`, `ErrorCode` from `reels_api.models`.
- Produces: `FORMAT: str`; `@dataclass DownloadedMedia(path: Path, info: MediaInfo)`; `map_ytdlp_error(message: str) -> ErrorCode`; `download(url: str, dest_dir: Path, cookies_file: Path | None = None) -> DownloadedMedia`; `ytdlp_version() -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_downloader.py`:

```python
from pathlib import Path

import pytest
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
    ],
)
def test_map_ytdlp_error(message, code):
    assert downloader.map_ytdlp_error(message) == code


class FakeYDL:
    """Stands in for yt_dlp.YoutubeDL: writes a file and returns an info dict."""

    last_opts: dict = {}
    info: dict = {"title": "Hello", "duration": 12.5, "width": 720, "height": 1280}
    raise_message: str | None = None

    def __init__(self, opts):
        FakeYDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def extract_info(self, url, download=True):
        if FakeYDL.raise_message:
            raise DownloadError(FakeYDL.raise_message)
        out = Path(self.__class__.last_opts["outtmpl"].replace("%(ext)s", "mp4"))
        out.write_bytes(b"\x00" * 10)
        return dict(self.__class__.info)


@pytest.fixture
def fake_ydl(monkeypatch):
    FakeYDL.raise_message = None
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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_downloader.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reels_api.downloader'`

- [ ] **Step 3: Implement downloader.py**

`reels_api/downloader.py`:

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yt_dlp
from yt_dlp.utils import DownloadError
from yt_dlp.version import __version__ as _ytdlp_version

from reels_api.models import ErrorCode, JobError, MediaInfo

log = logging.getLogger(__name__)

# Prefer H.264 video + AAC audio so ffmpeg can copy instead of re-encode.
FORMAT = "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/b[ext=mp4]/b"

_OUTPUT_STEM = "source"
_PARTIAL_SUFFIXES = {".part", ".ytdl", ".temp"}

# Ordered: first match wins. Login must precede "not available", because
# Instagram's message "Requested content is not available, rate-limit reached
# or login required" mentions both.
_ERROR_PATTERNS: list[tuple[ErrorCode, tuple[str, ...]]] = [
    (ErrorCode.LOGIN_REQUIRED, ("login required", "log in", "login", "cookies")),
    (
        ErrorCode.PRIVATE_OR_REMOVED,
        ("private", "does not exist", "not exist", "404", "not available", "unavailable", "not found", "removed"),
    ),
    (ErrorCode.UNSUPPORTED_URL, ("unsupported url",)),
]


@dataclass
class DownloadedMedia:
    path: Path
    info: MediaInfo


def map_ytdlp_error(message: str) -> ErrorCode:
    """Translate a yt-dlp error message into one of our error codes."""
    text = message.lower()
    for code, needles in _ERROR_PATTERNS:
        if any(n in text for n in needles):
            return code
    return ErrorCode.PLATFORM_BLOCKED


def ytdlp_version() -> str:
    return _ytdlp_version


def _find_output(dest_dir: Path) -> Path | None:
    candidates = [
        p
        for p in dest_dir.glob(f"{_OUTPUT_STEM}.*")
        if p.is_file() and p.suffix.lower() not in _PARTIAL_SUFFIXES
    ]
    if not candidates:
        return None
    # If a merged .mp4 exists prefer it; otherwise the largest file.
    for p in candidates:
        if p.suffix.lower() == ".mp4":
            return p
    return max(candidates, key=lambda p: p.stat().st_size)


def _to_float(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _to_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def download(url: str, dest_dir: Path, cookies_file: Path | None = None) -> DownloadedMedia:
    """Download one video into dest_dir as source.<ext>. Raises JobError on failure."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    opts: dict = {
        "format": FORMAT,
        "outtmpl": str(dest_dir / f"{_OUTPUT_STEM}.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "playlist_items": "1",
        "socket_timeout": 30,
        "retries": 2,
    }
    if cookies_file:
        opts["cookiefile"] = str(cookies_file)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as exc:
        log.info("yt-dlp failed for %s: %s", url, exc)
        raise JobError(map_ytdlp_error(str(exc))) from exc

    if info is None:
        raise JobError(ErrorCode.PLATFORM_BLOCKED)
    if "entries" in info:  # Instagram carousel or similar: take the first entry
        entries = [e for e in info["entries"] if e]
        info = entries[0] if entries else info

    path = _find_output(dest_dir)
    if path is None:
        raise JobError(ErrorCode.PLATFORM_BLOCKED, "The download produced no file.")

    media = MediaInfo(
        title=(info.get("title") or "video").strip() or "video",
        duration_seconds=_to_float(info.get("duration")),
        width=_to_int(info.get("width")),
        height=_to_int(info.get("height")),
    )
    return DownloadedMedia(path=path, info=media)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_downloader.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add reels_api/downloader.py tests/test_downloader.py
git commit -m "feat: yt-dlp downloader with error code mapping

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: ffprobe and ffmpeg media layer

**Files:**
- Create: `reels_api/media.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Consumes: `JobError`, `ErrorCode`.
- Produces: `@dataclass ProbeResult(video_codec, audio_codec, duration_seconds, width, height)`; `parse_probe(data: dict) -> ProbeResult`; `probe(path: Path, timeout: float = 60) -> ProbeResult`; `needs_transcode(p: ProbeResult) -> bool`; `build_ffmpeg_command(src: Path, dst: Path, transcode: bool) -> list[str]`; `convert(src: Path, dst: Path, transcode: bool, timeout: float) -> None`; `ffmpeg_available() -> bool`.

- [ ] **Step 1: Write the failing tests**

`tests/test_media.py`:

```python
import subprocess
from pathlib import Path

import pytest

from reels_api import media
from reels_api.models import ErrorCode, JobError

PROBE_JSON = {
    "streams": [
        {"codec_type": "video", "codec_name": "h264", "width": 1080, "height": 1920},
        {"codec_type": "audio", "codec_name": "aac"},
    ],
    "format": {"duration": "23.400000"},
}


def test_parse_probe():
    p = media.parse_probe(PROBE_JSON)
    assert p.video_codec == "h264"
    assert p.audio_codec == "aac"
    assert p.duration_seconds == 23.4
    assert p.width == 1080
    assert p.height == 1920


def test_parse_probe_no_audio_no_duration():
    p = media.parse_probe({"streams": [{"codec_type": "video", "codec_name": "hevc"}], "format": {}})
    assert p.video_codec == "hevc"
    assert p.audio_codec is None
    assert p.duration_seconds is None
    assert p.width is None


@pytest.mark.parametrize(
    "video,audio,expected",
    [
        ("h264", "aac", False),
        ("h264", None, False),
        ("hevc", "aac", True),
        ("h264", "opus", True),
        ("vp9", "opus", True),
        (None, "aac", True),
    ],
)
def test_needs_transcode(video, audio, expected):
    p = media.ProbeResult(video_codec=video, audio_codec=audio, duration_seconds=None, width=None, height=None)
    assert media.needs_transcode(p) is expected


def test_build_ffmpeg_command_copy():
    cmd = media.build_ffmpeg_command(Path("in.mp4"), Path("out.mp4"), transcode=False)
    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert cmd[cmd.index("-i") + 1] == "in.mp4"
    assert cmd[cmd.index("-c") + 1] == "copy"
    assert "libx264" not in cmd
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert cmd[-1] == "out.mp4"


def test_build_ffmpeg_command_transcode():
    cmd = media.build_ffmpeg_command(Path("in.webm"), Path("out.mp4"), transcode=True)
    assert cmd[cmd.index("-c:v") + 1] == "libx264"
    assert cmd[cmd.index("-preset") + 1] == "veryfast"
    assert cmd[cmd.index("-crf") + 1] == "23"
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv420p"
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-b:a") + 1] == "128k"
    assert cmd[cmd.index("-movflags") + 1] == "+faststart"
    assert "copy" not in cmd


def test_convert_success(monkeypatch, tmp_path):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    media.convert(tmp_path / "in.mp4", tmp_path / "out.mp4", transcode=False, timeout=42)
    assert calls[0][1]["timeout"] == 42
    assert calls[0][0][0] == "ffmpeg"


def test_convert_failure(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Invalid data found when processing input")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    with pytest.raises(JobError) as exc:
        media.convert(tmp_path / "in.mp4", tmp_path / "out.mp4", transcode=False, timeout=10)
    assert exc.value.code == ErrorCode.PROCESSING_FAILED
    assert "Invalid data" in exc.value.message


def test_convert_timeout(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs["timeout"])

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    with pytest.raises(JobError) as exc:
        media.convert(tmp_path / "in.mp4", tmp_path / "out.mp4", transcode=True, timeout=1)
    assert exc.value.code == ErrorCode.TIMEOUT


def test_probe_failure(monkeypatch, tmp_path):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="in.mp4: No such file")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    with pytest.raises(JobError) as exc:
        media.probe(tmp_path / "in.mp4")
    assert exc.value.code == ErrorCode.PROCESSING_FAILED


def test_probe_success(monkeypatch, tmp_path):
    import json

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "ffprobe"
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(PROBE_JSON), stderr="")

    monkeypatch.setattr(media.subprocess, "run", fake_run)
    assert media.probe(tmp_path / "in.mp4").video_codec == "h264"


def test_ffmpeg_available_is_bool():
    assert isinstance(media.ffmpeg_available(), bool)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_media.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reels_api.media'`

- [ ] **Step 3: Implement media.py**

`reels_api/media.py`:

```python
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from reels_api.models import ErrorCode, JobError

log = logging.getLogger(__name__)


@dataclass
class ProbeResult:
    video_codec: str | None
    audio_codec: str | None
    duration_seconds: float | None
    width: int | None
    height: int | None


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def parse_probe(data: dict) -> ProbeResult:
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration_raw = (data.get("format") or {}).get("duration")
    try:
        duration = float(duration_raw) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration = None
    return ProbeResult(
        video_codec=video.get("codec_name") if video else None,
        audio_codec=audio.get("codec_name") if audio else None,
        duration_seconds=duration,
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
    )


def probe(path: Path, timeout: float = 60) -> ProbeResult:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise JobError(ErrorCode.TIMEOUT) from exc
    if proc.returncode != 0:
        raise JobError(ErrorCode.PROCESSING_FAILED, "ffprobe failed: " + proc.stderr.strip()[-300:])
    try:
        return parse_probe(json.loads(proc.stdout or "{}"))
    except json.JSONDecodeError as exc:
        raise JobError(ErrorCode.PROCESSING_FAILED, "ffprobe returned invalid JSON") from exc


def needs_transcode(p: ProbeResult) -> bool:
    """WhatsApp wants H.264 + AAC. A file with no audio track can still be copied."""
    return not (p.video_codec == "h264" and p.audio_codec in ("aac", None))


def build_ffmpeg_command(src: Path, dst: Path, transcode: bool) -> list[str]:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src)]
    if transcode:
        cmd += [
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
        ]
    else:
        cmd += ["-c", "copy"]
    cmd += ["-movflags", "+faststart", str(dst)]
    return cmd


def convert(src: Path, dst: Path, transcode: bool, timeout: float) -> None:
    """Run ffmpeg. subprocess.run kills the child if the timeout expires."""
    cmd = build_ffmpeg_command(src, dst, transcode)
    log.debug("ffmpeg: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise JobError(ErrorCode.TIMEOUT) from exc
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise JobError(ErrorCode.PROCESSING_FAILED, "ffmpeg failed: " + stderr[-300:])
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_media.py -v`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add reels_api/media.py tests/test_media.py
git commit -m "feat: ffprobe parsing and ffmpeg remux/transcode

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Pipeline

**Files:**
- Create: `reels_api/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Settings`; `Job`, `JobResult`, `JobStatus`, `JobError`, `ErrorCode`; `downloader.download`, `downloader.DownloadedMedia`; `media.probe`, `media.convert`, `media.needs_transcode`, `media.ProbeResult`.
- Produces: `@dataclass Pipeline(settings, downloader=download, prober=probe, converter=convert)` with method `run(job: Job, set_status: Callable[[JobStatus], None]) -> JobResult`. Raises `JobError` or any other exception; always removes the job's temp directory.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:

```python
from pathlib import Path

import pytest

from reels_api.downloader import DownloadedMedia
from reels_api.media import ProbeResult
from reels_api.models import ErrorCode, Job, JobError, JobStatus, MediaInfo, Source
from reels_api.pipeline import Pipeline
from tests.conftest import make_settings


def fake_download_factory(calls, size=100):
    def fake_download(url, dest_dir, cookies_file=None):
        calls.append(("download", url, dest_dir, cookies_file))
        p = dest_dir / "source.mp4"
        p.write_bytes(b"\x00" * size)
        return DownloadedMedia(p, MediaInfo("Title", 10.0, 720, 1280))
    return fake_download


def fake_probe_factory(calls, video="h264", audio="aac"):
    def fake_probe(path):
        calls.append(("probe", path))
        return ProbeResult(video, audio, 9.5, 1080, 1920)
    return fake_probe


def fake_convert_factory(calls):
    def fake_convert(src, dst, transcode, timeout):
        calls.append(("convert", src, dst, transcode, timeout))
        dst.write_bytes(src.read_bytes() + b"\x01")
    return fake_convert


def make_job() -> Job:
    return Job(id="job1", url="https://vm.tiktok.com/x/", source=Source.TIKTOK)


def test_pipeline_success(tmp_path):
    settings = make_settings(tmp_path, job_timeout_seconds=100)
    calls = []
    statuses = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
    )
    result = p.run(make_job(), statuses.append)

    assert statuses == [JobStatus.DOWNLOADING, JobStatus.PROCESSING]
    assert result.file_path == settings.storage_dir / "job1.mp4"
    assert result.file_path.exists()
    assert result.size_bytes == 101
    assert result.title == "Title"
    assert result.source == Source.TIKTOK
    assert result.duration_seconds == 9.5   # probe wins over yt-dlp metadata
    assert result.width == 1080
    assert result.height == 1920

    kinds = [c[0] for c in calls]
    assert kinds == ["download", "probe", "convert"]
    assert calls[0][2] == settings.temp_dir / "job1"
    assert calls[0][3] is None
    assert calls[2][3] is False           # h264+aac -> copy
    assert 0 < calls[2][4] <= 100         # timeout is the remaining budget
    assert not (settings.temp_dir / "job1").exists()


def test_pipeline_transcodes_when_needed(tmp_path):
    settings = make_settings(tmp_path)
    calls = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls, video="hevc"),
        converter=fake_convert_factory(calls),
    )
    p.run(make_job(), lambda s: None)
    assert calls[2][3] is True


def test_pipeline_passes_cookies(tmp_path):
    cookies = tmp_path / "c.txt"
    settings = make_settings(tmp_path, cookies_file=cookies)
    calls = []
    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
    )
    p.run(make_job(), lambda s: None)
    assert calls[0][3] == cookies


def test_pipeline_falls_back_to_download_metadata(tmp_path):
    settings = make_settings(tmp_path)
    calls = []

    def probe_nothing(path):
        return ProbeResult("h264", "aac", None, None, None)

    p = Pipeline(
        settings=settings,
        downloader=fake_download_factory(calls),
        prober=probe_nothing,
        converter=fake_convert_factory(calls),
    )
    result = p.run(make_job(), lambda s: None)
    assert result.duration_seconds == 10.0
    assert result.width == 720
    assert result.height == 1280


def test_pipeline_cleans_temp_on_failure(tmp_path):
    settings = make_settings(tmp_path)
    calls = []

    def failing_download(url, dest_dir, cookies_file=None):
        (dest_dir / "source.mp4.part").write_bytes(b"x")
        raise JobError(ErrorCode.LOGIN_REQUIRED)

    p = Pipeline(
        settings=settings,
        downloader=failing_download,
        prober=fake_probe_factory(calls),
        converter=fake_convert_factory(calls),
    )
    with pytest.raises(JobError) as exc:
        p.run(make_job(), lambda s: None)
    assert exc.value.code == ErrorCode.LOGIN_REQUIRED
    assert not (settings.temp_dir / "job1").exists()
    assert not (settings.storage_dir / "job1.mp4").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reels_api.pipeline'`

- [ ] **Step 3: Implement pipeline.py**

`reels_api/pipeline.py`:

```python
from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from reels_api import downloader, media
from reels_api.downloader import DownloadedMedia
from reels_api.media import ProbeResult
from reels_api.models import Job, JobResult, JobStatus
from reels_api.settings import Settings

log = logging.getLogger(__name__)

Downloader = Callable[[str, Path, Path | None], DownloadedMedia]
Prober = Callable[[Path], ProbeResult]
Converter = Callable[[Path, Path, bool, float], None]
StatusSetter = Callable[[JobStatus], None]


@dataclass
class Pipeline:
    """Runs the blocking stages for one job. Call from a worker thread."""

    settings: Settings
    downloader: Downloader = field(default=downloader.download)
    prober: Prober = field(default=media.probe)
    converter: Converter = field(default=media.convert)

    def run(self, job: Job, set_status: StatusSetter) -> JobResult:
        deadline = time.monotonic() + self.settings.job_timeout_seconds
        temp_dir = self.settings.temp_dir / job.id
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        dst = self.settings.storage_dir / f"{job.id}.mp4"
        try:
            set_status(JobStatus.DOWNLOADING)
            downloaded = self.downloader(job.url, temp_dir, self.settings.cookies_file)

            set_status(JobStatus.PROCESSING)
            probed = self.prober(downloaded.path)
            remaining = max(1.0, deadline - time.monotonic())
            self.converter(downloaded.path, dst, media.needs_transcode(probed), remaining)

            info = downloaded.info
            return JobResult(
                file_path=dst,
                title=info.title,
                source=job.source,
                duration_seconds=probed.duration_seconds if probed.duration_seconds is not None else info.duration_seconds,
                size_bytes=dst.stat().st_size,
                width=probed.width if probed.width is not None else info.width,
                height=probed.height if probed.height is not None else info.height,
            )
        except BaseException:
            dst.unlink(missing_ok=True)
            raise
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add reels_api/pipeline.py tests/test_pipeline.py
git commit -m "feat: download/probe/convert pipeline with injectable stages

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Job store, worker pool and sweeper

**Files:**
- Create: `reels_api/jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `Settings`; `Job`, `JobResult`, `JobStatus`, `JobError`, `ErrorCode`, `utcnow`; `detect_source`; `Pipeline` (only its `run(job, set_status)` method).
- Produces: `new_job_id() -> str`; `class JobStore` with `async add(job)`, `async get(job_id) -> Job | None`, `async all() -> list[Job]`, `async remove(job_id)`; `class JobManager(settings, pipeline, store)` with `async start()`, `async stop()`, `async submit(url) -> Job`, `async sweep(now=None)`; module constant `TIMEOUT_GRACE_SECONDS = 5`, `SWEEP_INTERVAL_SECONDS = 300`.

- [ ] **Step 1: Write the failing tests**

`tests/test_jobs.py`:

```python
import asyncio
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from reels_api import jobs as jobs_module
from reels_api.jobs import JobManager, JobStore, new_job_id
from reels_api.models import ErrorCode, Job, JobError, JobResult, JobStatus, Source
from tests.conftest import make_settings

# Every `async def` test below carries @pytest.mark.anyio; the anyio pytest
# plugin (installed with the anyio package) runs them on the asyncio backend
# chosen by the `anyio_backend` fixture in conftest.py.


class FakePipeline:
    def __init__(self, settings, behaviour="ok", delay=0.0):
        self.settings = settings
        self.behaviour = behaviour
        self.delay = delay

    def run(self, job, set_status):
        set_status(JobStatus.DOWNLOADING)
        if self.delay:
            time.sleep(self.delay)
        set_status(JobStatus.PROCESSING)
        if self.behaviour == "job_error":
            raise JobError(ErrorCode.PRIVATE_OR_REMOVED)
        if self.behaviour == "crash":
            raise RuntimeError("boom")
        self.settings.storage_dir.mkdir(parents=True, exist_ok=True)
        path = self.settings.storage_dir / f"{job.id}.mp4"
        path.write_bytes(b"\x00" * 50)
        return JobResult(path, "T", job.source, 1.0, 50, 10, 20)


async def wait_finished(store: JobStore, job_id: str, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = await store.get(job_id)
        if job and job.status in (JobStatus.DONE, JobStatus.FAILED):
            return job
        await asyncio.sleep(0.02)
    raise AssertionError("job did not finish")


def test_new_job_id_shape():
    ids = {new_job_id() for _ in range(50)}
    assert len(ids) == 50
    for i in ids:
        assert 8 <= len(i) <= 12
        assert all(c.isalnum() or c in "-_" for c in i)


@pytest.mark.anyio
async def test_store_roundtrip():
    store = JobStore()
    job = Job(id="a", url="u", source=Source.TIKTOK)
    await store.add(job)
    assert await store.get("a") is job
    assert await store.all() == [job]
    await store.remove("a")
    assert await store.get("a") is None
    await store.remove("a")  # idempotent


@pytest.mark.anyio
async def test_submit_and_complete(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    await manager.start()
    try:
        job = await manager.submit("https://vm.tiktok.com/x/")
        assert job.status == JobStatus.QUEUED
        assert job.source == Source.TIKTOK
        done = await wait_finished(store, job.id)
        assert done.status == JobStatus.DONE
        assert done.result.file_path.exists()
        assert done.finished_at is not None
        assert done.expires_at - done.finished_at == timedelta(hours=settings.retention_hours)
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_submit_rejects_bad_url(tmp_path):
    settings = make_settings(tmp_path)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    with pytest.raises(JobError) as exc:
        await manager.submit("https://youtube.com/watch?v=1")
    assert exc.value.code == ErrorCode.UNSUPPORTED_URL


@pytest.mark.anyio
async def test_submit_rejects_when_queue_full(tmp_path):
    settings = make_settings(tmp_path, max_queue=2)
    manager = JobManager(settings, FakePipeline(settings), JobStore())
    # not started: nothing drains the queue
    await manager.submit("https://vm.tiktok.com/1/")
    await manager.submit("https://vm.tiktok.com/2/")
    with pytest.raises(JobError) as exc:
        await manager.submit("https://vm.tiktok.com/3/")
    assert exc.value.code == ErrorCode.TOO_MANY_JOBS


@pytest.mark.anyio
async def test_job_error_is_recorded(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings, "job_error"), store)
    await manager.start()
    try:
        job = await manager.submit("https://vm.tiktok.com/x/")
        done = await wait_finished(store, job.id)
        assert done.status == JobStatus.FAILED
        assert done.error == ErrorCode.PRIVATE_OR_REMOVED
        assert done.message
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_crash_is_processing_failed_and_worker_survives(tmp_path):
    settings = make_settings(tmp_path)
    store = JobStore()
    pipeline = FakePipeline(settings, "crash")
    manager = JobManager(settings, pipeline, store)
    await manager.start()
    try:
        job1 = await manager.submit("https://vm.tiktok.com/x/")
        done1 = await wait_finished(store, job1.id)
        assert done1.status == JobStatus.FAILED
        assert done1.error == ErrorCode.PROCESSING_FAILED

        pipeline.behaviour = "ok"
        job2 = await manager.submit("https://vm.tiktok.com/y/")
        done2 = await wait_finished(store, job2.id)
        assert done2.status == JobStatus.DONE
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_module, "TIMEOUT_GRACE_SECONDS", 0)
    settings = make_settings(tmp_path, job_timeout_seconds=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings, delay=3.0), store)
    await manager.start()
    try:
        job = await manager.submit("https://vm.tiktok.com/x/")
        done = await wait_finished(store, job.id, timeout=4)
        assert done.status == JobStatus.FAILED
        assert done.error == ErrorCode.TIMEOUT
    finally:
        await manager.stop()


@pytest.mark.anyio
async def test_sweep_removes_expired_and_stray_dirs(tmp_path):
    settings = make_settings(tmp_path, retention_hours=1)
    store = JobStore()
    manager = JobManager(settings, FakePipeline(settings), store)
    settings.storage_dir.mkdir(parents=True)
    settings.temp_dir.mkdir(parents=True)

    now = datetime.now(UTC)
    old_file = settings.storage_dir / "old.mp4"
    old_file.write_bytes(b"x")
    old = Job(id="old", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    old.finished_at = now - timedelta(hours=2)
    old.result = JobResult(old_file, "T", Source.TIKTOK, 1.0, 1, 1, 1)

    fresh_file = settings.storage_dir / "fresh.mp4"
    fresh_file.write_bytes(b"x")
    fresh = Job(id="fresh", url="u", source=Source.TIKTOK, status=JobStatus.DONE)
    fresh.finished_at = now - timedelta(minutes=10)
    fresh.result = JobResult(fresh_file, "T", Source.TIKTOK, 1.0, 1, 1, 1)

    failed = Job(id="failed", url="u", source=Source.TIKTOK, status=JobStatus.FAILED)
    failed.finished_at = now - timedelta(hours=2)

    running = Job(id="running", url="u", source=Source.TIKTOK, status=JobStatus.DOWNLOADING)

    for j in (old, fresh, failed, running):
        await store.add(j)

    (settings.temp_dir / "running").mkdir()
    (settings.temp_dir / "stray").mkdir()
    (settings.temp_dir / "stray" / "source.mp4.part").write_bytes(b"x")

    await manager.sweep(now=now)

    assert await store.get("old") is None
    assert not old_file.exists()
    assert await store.get("failed") is None
    assert await store.get("fresh") is not None
    assert fresh_file.exists()
    assert await store.get("running") is not None
    assert (settings.temp_dir / "running").exists()
    assert not (settings.temp_dir / "stray").exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reels_api.jobs'`

- [ ] **Step 3: Implement jobs.py**

`reels_api/jobs.py`:

```python
from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
from datetime import datetime, timedelta

from reels_api.models import ErrorCode, Job, JobError, JobStatus, utcnow
from reels_api.pipeline import Pipeline
from reels_api.settings import Settings
from reels_api.urls import detect_source

log = logging.getLogger(__name__)

TIMEOUT_GRACE_SECONDS = 5
SWEEP_INTERVAL_SECONDS = 300


def new_job_id() -> str:
    return secrets.token_urlsafe(6)  # 8 URL-safe characters


class JobStore:
    """In-memory job registry. Lost on restart; that is acceptable for v1."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def add(self, job: Job) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def get(self, job_id: str) -> Job | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def all(self) -> list[Job]:
        async with self._lock:
            return list(self._jobs.values())

    async def remove(self, job_id: str) -> None:
        async with self._lock:
            self._jobs.pop(job_id, None)


class JobManager:
    """Owns the queue, the worker tasks and the sweeper."""

    def __init__(self, settings: Settings, pipeline: Pipeline, store: JobStore) -> None:
        self.settings = settings
        self.pipeline = pipeline
        self.store = store
        self.queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=settings.max_queue)
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        for i in range(self.settings.workers):
            self._tasks.append(asyncio.create_task(self._worker(), name=f"worker-{i}"))
        self._tasks.append(asyncio.create_task(self._sweeper(), name="sweeper"))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def submit(self, url: str) -> Job:
        source = detect_source(url)  # raises JobError(unsupported_url)
        if self.queue.full():
            raise JobError(ErrorCode.TOO_MANY_JOBS)
        job = Job(id=new_job_id(), url=url.strip(), source=source)
        await self.store.add(job)
        self.queue.put_nowait(job)
        return job

    async def _worker(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                await self._run_job(job)
            except Exception:  # never let a worker die
                log.exception("worker crashed on job %s", job.id)
            finally:
                self.queue.task_done()

    async def _run_job(self, job: Job) -> None:
        def set_status(status: JobStatus) -> None:
            job.status = status

        budget = self.settings.job_timeout_seconds + TIMEOUT_GRACE_SECONDS
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self.pipeline.run, job, set_status), timeout=budget
            )
            job.result = result
            job.status = JobStatus.DONE
        except asyncio.TimeoutError:
            self._fail(job, ErrorCode.TIMEOUT)
        except JobError as exc:
            self._fail(job, exc.code, exc.message)
        except Exception:
            log.exception("job %s failed unexpectedly", job.id)
            self._fail(job, ErrorCode.PROCESSING_FAILED)
        finally:
            job.finished_at = utcnow()
            job.expires_at = job.finished_at + self._retention()
            log.info("job %s finished: %s", job.id, job.status.value)

    def _fail(self, job: Job, code: ErrorCode, message: str | None = None) -> None:
        job.status = JobStatus.FAILED
        job.error = code
        job.message = message or JobError(code).message

    def _retention(self) -> timedelta:
        return timedelta(hours=self.settings.retention_hours)

    async def _sweeper(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
            try:
                await self.sweep()
            except Exception:
                log.exception("sweep failed")

    async def sweep(self, now: datetime | None = None) -> None:
        """Delete finished jobs older than the retention window and stray temp dirs."""
        now = now or utcnow()
        cutoff = now - self._retention()
        for job in await self.store.all():
            if job.finished_at is not None and job.finished_at < cutoff:
                if job.result is not None:
                    job.result.file_path.unlink(missing_ok=True)
                await self.store.remove(job.id)
                log.info("swept job %s", job.id)

        temp_dir = self.settings.temp_dir
        if temp_dir.is_dir():
            for entry in temp_dir.iterdir():
                if entry.is_dir() and await self.store.get(entry.name) is None:
                    shutil.rmtree(entry, ignore_errors=True)
                    log.info("removed stray temp dir %s", entry.name)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests/test_jobs.py -v`
Expected: 9 passed (the timeout test takes about 3 seconds)

- [ ] **Step 5: Commit**

```bash
git add reels_api/jobs.py tests/test_jobs.py
git commit -m "feat: in-memory job store, worker pool and sweeper

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: HTTP layer: auth, routes, app factory

**Files:**
- Create: `reels_api/auth.py`, `reels_api/routes.py`, `reels_api/main.py`
- Test: `tests/test_routes.py`

**Interfaces:**
- Consumes: `Settings`; `JobStore`, `JobManager`; `Pipeline`; `job_to_dict`, `CreateJobRequest`, `JobStatus`, `JobError`, `ErrorCode`; `downloader.ytdlp_version`; `media.ffmpeg_available`.
- Produces: `auth.require_api_key` FastAPI dependency; `routes.router`; `routes.slugify(title) -> str`; `main.create_app(settings: Settings | None = None, pipeline: Pipeline | None = None) -> FastAPI`. The app stores `settings`, `store`, `manager` on `app.state`.

- [ ] **Step 1: Write the failing tests**

`tests/test_routes.py`:

```python
import threading
import time

import pytest
from fastapi.testclient import TestClient

from reels_api.main import create_app
from reels_api.models import ErrorCode, JobError, JobResult, JobStatus
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
        return JobResult(path, "My Cool Reel!", job.source, 2.5, 10, 1080, 1920)


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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_routes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reels_api.main'`

- [ ] **Step 3: Implement auth.py**

`reels_api/auth.py`:

```python
import secrets

from fastapi import Header, HTTPException, Request


async def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    expected: str = request.app.state.settings.api_key
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Missing or invalid API key."},
        )
```

- [ ] **Step 4: Implement routes.py**

`reels_api/routes.py`:

```python
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from reels_api import media
from reels_api.auth import require_api_key
from reels_api.downloader import ytdlp_version
from reels_api.models import CreateJobRequest, JobStatus, job_to_dict

router = APIRouter()
protected = APIRouter(dependencies=[Depends(require_api_key)])


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:60].strip("-") or "video"


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"error": "not_found", "message": "Unknown or expired job."})


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "ytdlp_version": ytdlp_version(), "ffmpeg": media.ffmpeg_available()}


@protected.post("/jobs", status_code=202)
async def create_job(body: CreateJobRequest, request: Request) -> dict:
    job = await request.app.state.manager.submit(body.url)
    return {"id": job.id, "status": job.status.value}


@protected.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    job = await request.app.state.store.get(job_id)
    if job is None:
        raise _not_found()
    return job_to_dict(job, request.app.state.settings.public_base_url)


@protected.get("/files/{job_id}.mp4")
async def get_file(job_id: str, request: Request) -> FileResponse:
    job = await request.app.state.store.get(job_id)
    if job is None or job.status != JobStatus.DONE or job.result is None:
        raise _not_found()
    if not job.result.file_path.is_file():
        raise _not_found()
    return FileResponse(
        job.result.file_path,
        media_type="video/mp4",
        filename=f"{slugify(job.result.title)}.mp4",
    )


router.include_router(protected)
```

- [ ] **Step 5: Implement main.py**

`reels_api/main.py`:

```python
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from reels_api.jobs import JobManager, JobStore
from reels_api.models import ErrorCode, JobError
from reels_api.pipeline import Pipeline
from reels_api.routes import router
from reels_api.settings import Settings

_JOB_ERROR_STATUS = {
    ErrorCode.UNSUPPORTED_URL: 400,
    ErrorCode.TOO_MANY_JOBS: 429,
}


def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None) -> FastAPI:
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level.upper())
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    store = JobStore()
    manager = JobManager(settings, pipeline or Pipeline(settings=settings), store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await manager.start()
        try:
            yield
        finally:
            await manager.stop()

    app = FastAPI(title="Reels Download API", version="1.0.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.store = store
    app.state.manager = manager
    app.include_router(router)

    @app.exception_handler(JobError)
    async def job_error_handler(request: Request, exc: JobError) -> JSONResponse:
        status = _JOB_ERROR_STATUS.get(exc.code, 500)
        return JSONResponse(status_code=status, content={"error": exc.code.value, "message": exc.message})

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        content = detail if isinstance(detail, dict) else {"error": "http_error", "message": str(detail)}
        return JSONResponse(status_code=exc.status_code, content=content, headers=exc.headers)

    return app
```

- [ ] **Step 6: Run to verify they pass**

Run: `python -m pytest tests/test_routes.py -v`
Expected: all passed. If `test_full_happy_path` fails only on the 206 assertion, check `python -m pip show starlette`; Range support needs starlette 0.36 or newer, which fastapi>=0.115 guarantees.

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest -v`
Expected: all passed, `test_integration.py` not present yet.

- [ ] **Step 8: Commit**

```bash
git add reels_api/auth.py reels_api/routes.py reels_api/main.py tests/test_routes.py
git commit -m "feat: HTTP API with API-key auth and app factory

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Packaging, README and integration test

**Files:**
- Create: `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `README.md`
- Create: `tests/test_integration.py`
- Modify: `.gitignore` (add `.venv/`, `data/`, `cookies.txt`, `.env` if missing)

**Interfaces:**
- Consumes: `create_app`, `Settings`, `media.ffmpeg_available`.
- Produces: a runnable container listening on port 8000.

- [ ] **Step 1: Write the integration test (skipped by default)**

`tests/test_integration.py`:

```python
"""End-to-end against the real internet. Run with:

    REELS_TEST_URL=https://www.tiktok.com/@scout2015/video/6718335390845095173 python -m pytest -m network

Needs ffmpeg and ffprobe on PATH. Any public TikTok URL works; pick a short one.
"""
import os
import time

import pytest
from fastapi.testclient import TestClient

from reels_api import media
from reels_api.main import create_app
from tests.conftest import make_settings

pytestmark = pytest.mark.network

TEST_URL = os.environ.get("REELS_TEST_URL")


@pytest.mark.skipif(not TEST_URL, reason="set REELS_TEST_URL to a public TikTok link")
@pytest.mark.skipif(not media.ffmpeg_available(), reason="ffmpeg/ffprobe not on PATH")
def test_real_download(tmp_path):
    settings = make_settings(tmp_path, job_timeout_seconds=180)
    headers = {"X-API-Key": settings.api_key}
    with TestClient(create_app(settings=settings)) as client:
        job_id = client.post("/jobs", json={"url": TEST_URL}, headers=headers).json()["id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            body = client.get(f"/jobs/{job_id}", headers=headers).json()
            if body["status"] in ("done", "failed"):
                break
            time.sleep(1)
        assert body["status"] == "done", body
        assert body["size_bytes"] > 0
        assert body["source"] == "tiktok"
        f = client.get(body["file_url"], headers=headers)
        assert f.status_code == 200
        assert f.content[4:8] == b"ftyp"  # MP4 magic
```

- [ ] **Step 2: Verify it is skipped by default and selectable**

Run: `python -m pytest -v`
Expected: `test_integration.py` does not appear (deselected by `-m 'not network'`).

Run: `python -m pytest -m network -v`
Expected: `test_real_download SKIPPED (set REELS_TEST_URL ...)` (or runs, if you set the env var and have ffmpeg).

- [ ] **Step 3: Write Docker files**

`.dockerignore`:

```
.venv
.git
data
tests
docs
__pycache__
*.pyc
.env
cookies.txt
```

`Dockerfile`:

```dockerfile
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY reels_api ./reels_api

RUN mkdir -p /data/files /data/tmp
ENV STORAGE_DIR=/data/files \
    TEMP_DIR=/data/tmp \
    PYTHONUNBUFFERED=1

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

CMD ["uvicorn", "reels_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

`docker-compose.yml`:

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      STORAGE_DIR: /data/files
      TEMP_DIR: /data/tmp
    volumes:
      - ./data:/data
      # Uncomment to enable Instagram downloads, and set COOKIES_FILE=/cookies.txt in .env
      # - ./cookies.txt:/cookies.txt:ro
    restart: unless-stopped
```

Append to `.gitignore` if not already present: `cookies.txt`.

- [ ] **Step 4: Build and smoke test the container**

Run:

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
Start-Sleep -Seconds 5
curl.exe -s http://localhost:8000/health
curl.exe -s -X POST http://localhost:8000/jobs -H "X-API-Key: change-me" -H "Content-Type: application/json" -d "{\"url\":\"https://youtube.com/watch?v=1\"}"
docker compose down
```

Expected: health returns `{"status":"ok","ytdlp_version":"...","ffmpeg":true}`; the POST returns 400 with `{"error":"unsupported_url",...}`.

- [ ] **Step 5: Write README.md**

`README.md`:

````markdown
# Reels Download API

Turns an Instagram Reel or TikTok share link into a WhatsApp-friendly MP4.

## Run with Docker

```bash
cp .env.example .env        # set API_KEY
docker compose up -d --build
curl http://localhost:8000/health
```

## Use

```bash
# 1. create a job
curl -X POST http://localhost:8000/jobs \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"url":"https://vm.tiktok.com/ZMabc123/"}'
# -> {"id":"k7f3q9x2","status":"queued"}

# 2. poll until status is done or failed
curl -H "X-API-Key: $API_KEY" http://localhost:8000/jobs/k7f3q9x2

# 3. download the file
curl -H "X-API-Key: $API_KEY" -o video.mp4 http://localhost:8000/files/k7f3q9x2.mp4
```

Job statuses: `queued`, `downloading`, `processing`, `done`, `failed`.
Failure codes: `unsupported_url`, `private_or_removed`, `login_required`,
`platform_blocked`, `processing_failed`, `timeout`. `whatsapp_ok` is false
when the file is over 16 MB.

## Configuration

See `.env.example`. All values are environment variables.

## Instagram cookies

Instagram usually refuses anonymous downloads. Export cookies from a
throwaway account with a browser extension that writes the Netscape
format, save as `cookies.txt`, uncomment the volume line in
`docker-compose.yml`, and set `COOKIES_FILE=/cookies.txt` in `.env`.

## When downloads start failing

Bump `yt-dlp` in `requirements.txt` and rebuild. That fixes most breakages.

## Development

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m pytest                      # unit tests, no network
REELS_TEST_URL=<tiktok url> python -m pytest -m network   # needs ffmpeg
uvicorn reels_api.main:create_app --factory --reload      # needs .env
```
````

- [ ] **Step 6: Run the full suite one last time**

Run: `python -m pytest -v`
Expected: all passed.

- [ ] **Step 7: Commit**

```bash
git add Dockerfile docker-compose.yml .dockerignore README.md .gitignore tests/test_integration.py
git commit -m "feat: Docker packaging, README and network integration test

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes

- Spec section 4 endpoints: Task 7. Error codes and messages: Task 2. Range requests: Task 7 test. Content-Disposition: Task 7.
- Spec section 5 pipeline stages: validate (Task 2 + Task 6 `submit`), download (Task 3), probe and remux/transcode (Task 4), finalize and temp cleanup (Task 5), timeout (Task 4 `convert` timeout, Task 6 `wait_for`).
- Spec section 6 store, workers, sweeper, 429 on full queue: Task 6.
- Spec section 7 configuration: Task 1.
- Spec section 10 testing: unit tests in Tasks 2 to 6, route tests in Task 7, network test and Docker smoke test in Task 8.
- One deliberate deviation from spec section 5 step 4: a file with H.264 video and no audio track is copied rather than transcoded. Noted in `needs_transcode`.
- The `wait_for` timeout cannot kill a thread. The pipeline's own deadline bounds ffmpeg via `subprocess.run(timeout=...)`, and yt-dlp is bounded by `socket_timeout` and `retries`. A pathological download can still linger in the thread after the job is marked `timeout`; the worker moves on regardless.
