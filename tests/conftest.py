from pathlib import Path
import shutil
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings
from app.main import create_app
from app.services.runtime_db import init_runtime_db


@pytest.fixture(autouse=True)
def isolate_runtime(monkeypatch):
    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "all")
    runtime_dir = get_settings().runtime_dir
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir, ignore_errors=True)
    init_runtime_db()
    yield


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client
