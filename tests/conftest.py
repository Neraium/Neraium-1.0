from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import get_settings
from app.main import create_app
from app.routers.data import wait_for_upload_workers
from app.services.runtime_db import configure_runtime_dir as configure_runtime_db_dir
from app.services.sii_runner import configure_runtime_dir as configure_sii_runner_dir
from app.services.upload_jobs import configure_runtime_dir as configure_upload_jobs_dir
from app.services.runtime_db import init_runtime_db
from app.services.dataset_scope import build_dataset_scope, set_current_dataset_scope


@pytest.fixture(autouse=True)
def isolate_runtime(monkeypatch, tmp_path):
    set_current_dataset_scope(build_dataset_scope(user_id="anonymous"))
    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "all")
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(runtime_dir))

    # Keep service module globals aligned with per-test runtime isolation.
    configure_runtime_db_dir(runtime_dir)
    configure_upload_jobs_dir(runtime_dir)
    configure_sii_runner_dir(runtime_dir)

    # Warm config from the current environment to avoid stale cross-test paths.
    get_settings()
    init_runtime_db()
    yield
    # Prevent an old test's daemon worker from reconfiguring the next test's runtime path.
    wait_for_upload_workers()
    set_current_dataset_scope(build_dataset_scope(user_id="anonymous"))


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client
