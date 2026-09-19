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
