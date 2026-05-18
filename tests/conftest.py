from pathlib import Path
import shutil
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings


@pytest.fixture(autouse=True)
def isolate_runtime(monkeypatch):
    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "all")
    runtime_dir = get_settings().runtime_dir
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    yield
