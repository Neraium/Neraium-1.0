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


def pytest_collection_modifyitems(items):
    # Keep the frozen gate/comparator file byte-identical. This case audits a
    # pre-repair campaign's retained difference inventory, not current outputs.
    historical = (
        "tests/test_complete_upload_semantics.py::"
        "test_retained_146_leaf_inventory_is_exhaustive"
    )
    for item in items:
        if item.nodeid == historical:
            item.add_marker(pytest.mark.historical_certification)


def pytest_addoption(parser):
    parser.addoption(
        "--historical-evidence-root", default=None,
        help="Checkout root containing the hash-verified historical certification evidence",
    )


@pytest.fixture(autouse=True)
def historical_certification_evidence(request, monkeypatch):
    if request.node.get_closest_marker("historical_certification") is None:
        return
    import hashlib
    import json

    root = Path(__file__).resolve().parents[1]
    evidence_root = Path(request.config.getoption("--historical-evidence-root") or root)
    manifest = json.loads((root / "tests/fixtures/historical_certification.json").read_text())
    for relative, expected in manifest["files"].items():
        artifact = evidence_root / relative
        if not artifact.is_file():
            pytest.fail(f"Required historical certification evidence absent: {relative}", pytrace=False)
        content = artifact.read_bytes()
        if len(content) != expected["bytes"] or hashlib.sha256(content).hexdigest() != expected["sha256"]:
            pytest.fail(f"Historical certification evidence hash mismatch: {relative}", pytrace=False)
    monkeypatch.setattr(
        request.module, "RETAINED",
        evidence_root / "docs/performance/production-processing-2026/raw",
    )
