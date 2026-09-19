from pathlib import Path

import pytest
from pydantic import ValidationError

from reels_api.settings import Settings


def test_defaults_applied(monkeypatch):
    monkeypatch.setenv("API_KEY", "abc")
    s = Settings(_env_file=None)
    assert s.api_key == "abc"
    assert s.storage_dir == Path("/data/files")
    assert s.temp_dir == Path("/data/tmp")
    assert s.retention_hours == 12
    assert s.workers == 2
    assert s.max_queue == 20
    assert s.job_timeout_seconds == 180
    assert s.max_videos == 100
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


def test_web_passcode_default_and_override(monkeypatch):
    monkeypatch.setenv("API_KEY", "abc")
    assert Settings(_env_file=None).web_passcode is None
    monkeypatch.setenv("WEB_PASSCODE", "letmein")
    assert Settings(_env_file=None).web_passcode == "letmein"


def test_invite_token_unset_empty_short_and_valid(monkeypatch):
    monkeypatch.setenv("API_KEY", "abc")
    monkeypatch.delenv("INVITE_TOKEN", raising=False)
    assert Settings(_env_file=None).invite_token is None

    monkeypatch.setenv("INVITE_TOKEN", "")
    assert Settings(_env_file=None).invite_token is None

    monkeypatch.setenv("INVITE_TOKEN", "a" * 15)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    monkeypatch.setenv("INVITE_TOKEN", "a" * 16)
    assert Settings(_env_file=None).invite_token == "a" * 16
