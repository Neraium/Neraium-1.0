from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.auth_store import create_user
from app.services.dataset_scope import build_dataset_scope, set_current_dataset_scope
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE
from app.services import upload_state_repository
from app.services.upload_session_service import SESSION_STATE_EMPTY, resolve_latest_upload_session
from app.services.upload_state_repository import (
    read_latest_upload_record,
    reset_upload_state,
    warm_latest_upload_cache,
    write_latest_upload_result,
)


USER_A = "alice@example.com"
USER_B = "bob@example.com"
WORKSPACE_A = "central-plant"
WORKSPACE_B = "north-plant"
JOB_A = "a" * 32
JOB_B = "b" * 32


def _scope(user: str, workspace: str):
    return build_dataset_scope(user_id=user, tenant_id=user, workspace_id=workspace)


def _select_scope(user: str, workspace: str) -> None:
    set_current_dataset_scope(_scope(user, workspace))


def _result(job_id: str, *, filename: str, rows: int, processed_at: str) -> dict:
    return {
        "job_id": job_id,
        "run_id": job_id,
        "upload_id": job_id,
        "filename": filename,
        "result_source": filename,
        "row_count": rows,
        "rows_processed": rows,
        "column_count": 3,
        "columns": ["timestamp", "flow", "temperature"],
        "last_processed_at": processed_at,
        "completed_at": processed_at,
        "sii_completed": True,
        "engine_result": {"overall_result": "stable"},
        "analysis_result": {"status": "complete", "insights": []},
        "room_summary": {"room_count": 1, "rooms": []},
        "sii_intelligence": {"facility_state": "Monitoring", "last_updated": processed_at},
        "replay_timeline": {"timeline": []},
    }


def _seed(user: str, workspace: str, job_id: str, *, rows: int, filename: str) -> None:
    _select_scope(user, workspace)
    write_latest_upload_result(
        job_id,
        _result(
            job_id,
            filename=filename,
            rows=rows,
            processed_at="2026-07-20T06:32:53.260378+00:00",
        ),
    )


def _latest(client: TestClient, user: str, workspace: str):
    return client.get(
        "/api/data/latest-upload?include_persisted=true",
        headers={"X-Neraium-User": user, "X-Neraium-Workspace-Id": workspace},
    )


@pytest.fixture(autouse=True)
def reset_dataset_scope_context():
    _select_scope("anonymous", "default")
    yield
    _select_scope("anonymous", "default")


def test_empty_workspace_has_no_dataset_metadata() -> None:
    client = TestClient(create_app())

    response = _latest(client, USER_A, WORKSPACE_A)

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_state"] == SESSION_STATE_EMPTY
    assert payload["latest_result"] is None
    assert payload["rows_processed"] == 0
    assert payload["last_filename"] is None
    assert payload["current_upload"]["dataset_id"] is None
    assert payload["current_upload"]["dataset_scope"]["workspace_id"] == WORKSPACE_A
    assert payload["current_upload"]["dataset_scope"]["user_id"] == USER_A


def test_imported_dataset_is_restored_only_for_its_user_workspace_and_dataset() -> None:
    _seed(USER_A, WORKSPACE_A, JOB_A, rows=120, filename="central.csv")
    _seed(USER_A, WORKSPACE_B, JOB_B, rows=240, filename="north.csv")
    client = TestClient(create_app())

    workspace_a = _latest(client, USER_A, WORKSPACE_A).json()
    workspace_b = _latest(client, USER_A, WORKSPACE_B).json()
    other_user = _latest(client, USER_B, WORKSPACE_A).json()
    workspace_a_again = _latest(client, USER_A, WORKSPACE_A).json()

    assert workspace_a["latest_result"]["dataset_id"] == JOB_A
    assert workspace_a["rows_processed"] == 120
    assert workspace_a["last_filename"] == "central.csv"
    assert workspace_a["latest_result"]["last_processed_at"] == "2026-07-20T06:32:53.260378+00:00"
    assert workspace_b["latest_result"]["dataset_id"] == JOB_B
    assert workspace_b["rows_processed"] == 240
    assert workspace_b["last_filename"] == "north.csv"
    assert other_user["session_state"] == SESSION_STATE_EMPTY
    assert other_user["latest_result"] is None
    assert workspace_a_again["latest_result"]["dataset_id"] == JOB_A
    assert workspace_a_again["rows_processed"] == 120


def test_scoped_reset_does_not_remove_another_workspace_dataset() -> None:
    _seed(USER_A, WORKSPACE_A, JOB_A, rows=120, filename="central.csv")
    _seed(USER_A, WORKSPACE_B, JOB_B, rows=240, filename="north.csv")

    _select_scope(USER_A, WORKSPACE_A)
    reset_upload_state()

    client = TestClient(create_app())
    assert _latest(client, USER_A, WORKSPACE_A).json()["session_state"] == SESSION_STATE_EMPTY
    preserved = _latest(client, USER_A, WORKSPACE_B).json()
    assert preserved["latest_result"]["dataset_id"] == JOB_B
    assert preserved["rows_processed"] == 240


def test_stale_unscoped_cache_and_legacy_files_are_not_restored() -> None:
    legacy_result = _result(
        "c" * 32,
        filename="resort chw hvac synthetic fouling.csv",
        rows=4032,
        processed_at="2026-07-20T06:32:53.260378+00:00",
    )
    legacy_record = {
        "job_id": legacy_result["job_id"],
        "status": "complete",
        "result": legacy_result,
        "summary": {"job_id": legacy_result["job_id"], "row_count": 4032},
    }
    UPLOAD_RUNTIME_STATE.latest_upload_cache["canonical"] = legacy_record
    UPLOAD_RUNTIME_STATE.latest_upload_cache["result"] = legacy_result
    (UPLOAD_RUNTIME_STATE.runtime_dir / "latest_upload.json").write_text(json.dumps(legacy_record), encoding="utf-8")
    (UPLOAD_RUNTIME_STATE.runtime_dir / "latest_upload_result.json").write_text(json.dumps(legacy_result), encoding="utf-8")

    client = TestClient(create_app())
    payload = _latest(client, USER_A, WORKSPACE_A).json()

    assert payload["session_state"] == SESSION_STATE_EMPTY
    assert payload["latest_result"] is None
    assert payload["rows_processed"] == 0
    assert "4032" not in json.dumps(payload)


def test_shared_database_and_object_keys_are_namespaced_by_dataset_scope(monkeypatch) -> None:
    scope = _scope(USER_A, WORKSPACE_A)
    _select_scope(USER_A, WORKSPACE_A)
    database_writes = []
    object_writes = []

    class FakeS3:
        def put_object(self, **kwargs):
            object_writes.append(kwargs)

    monkeypatch.setattr(upload_state_repository, "upsert_latest_payload", lambda key, payload: database_writes.append((key, payload)))
    monkeypatch.setattr(upload_state_repository, "_upload_state_bucket", lambda: "dataset-state")
    monkeypatch.setattr(upload_state_repository, "_get_s3_client", lambda: FakeS3())

    upload_state_repository.write_shared_state(
        "latest_upload",
        {
            "job_id": JOB_A,
            "dataset_id": JOB_A,
            "dataset_scope": scope.as_dict(),
        },
    )

    expected_name = f"scopes/{scope.storage_id}/latest_upload"
    assert database_writes[0][0] == expected_name
    assert database_writes[0][1]["dataset_scope"] == scope.as_dict()
    assert object_writes[0]["Bucket"] == "dataset-state"
    assert object_writes[0]["Key"] == f"upload-state/{expected_name}.json"
    assert WORKSPACE_A not in object_writes[0]["Key"]
    assert USER_A not in object_writes[0]["Key"]


def test_invalid_workspace_header_is_rejected() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/api/data/latest-upload",
        headers={"X-Neraium-User": USER_A, "X-Neraium-Workspace-Id": "../../other-tenant"},
    )

    assert response.status_code == 400
    assert response.json()["error_type"] == "invalid_header"


def test_backend_restart_restores_only_the_requesting_scope() -> None:
    _seed(USER_A, WORKSPACE_A, JOB_A, rows=120, filename="central.csv")
    UPLOAD_RUNTIME_STATE.jobs.clear()
    UPLOAD_RUNTIME_STATE.latest_upload_cache.clear()
    UPLOAD_RUNTIME_STATE.latest_upload_cache.update({"summary": None, "result": None, "canonical": None})

    warm_latest_upload_cache()

    _select_scope(USER_A, WORKSPACE_A)
    restored = resolve_latest_upload_session(include_persisted=True)
    _select_scope(USER_A, WORKSPACE_B)
    empty = resolve_latest_upload_session(include_persisted=True)
    assert restored["latest_result"]["dataset_id"] == JOB_A
    assert restored["rows_processed"] == 120
    assert empty["session_state"] == SESSION_STATE_EMPTY
    assert empty["latest_result"] is None


def test_production_logout_and_login_cannot_cross_users(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    runtime_dir = UPLOAD_RUNTIME_STATE.runtime_dir
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(runtime_dir))
    create_user(USER_A, "password123", role="operator")
    create_user(USER_B, "password123", role="operator")
    _seed(USER_A, WORKSPACE_A, JOB_A, rows=120, filename="central.csv")
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=runtime_dir,
    )
    client = TestClient(create_app(settings), base_url="https://testserver")
    headers = {"X-Neraium-Workspace-Id": WORKSPACE_A}

    assert client.get("/api/data/latest-upload", headers=headers).status_code == 401
    assert client.post("/api/auth/login", json={"email": USER_A, "password": "password123"}).status_code == 200
    assert client.get("/api/data/latest-upload", headers=headers).json()["rows_processed"] == 120
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/data/latest-upload", headers=headers).status_code == 401

    assert client.post("/api/auth/login", json={"email": USER_B, "password": "password123"}).status_code == 200
    bob = client.get("/api/data/latest-upload", headers=headers).json()
    assert bob["session_state"] == SESSION_STATE_EMPTY
    assert bob["latest_result"] is None
    assert client.post("/api/auth/logout").status_code == 200

    assert client.post("/api/auth/login", json={"email": USER_A, "password": "password123"}).status_code == 200
    assert client.get("/api/data/latest-upload", headers=headers).json()["latest_result"]["dataset_id"] == JOB_A


def test_job_artifacts_are_not_visible_outside_their_scope() -> None:
    _seed(USER_A, WORKSPACE_A, JOB_A, rows=120, filename="central.csv")
    client = TestClient(create_app())

    owner = client.get(
        f"/api/data/upload-status/{JOB_A}",
        headers={"X-Neraium-User": USER_A, "X-Neraium-Workspace-Id": WORKSPACE_A},
    )
    other_workspace = client.get(
        f"/api/data/upload-status/{JOB_A}",
        headers={"X-Neraium-User": USER_A, "X-Neraium-Workspace-Id": WORKSPACE_B},
    )
    other_user = client.get(
        f"/api/data/intake/{JOB_A}/result",
        headers={"X-Neraium-User": USER_B, "X-Neraium-Workspace-Id": WORKSPACE_A},
    )

    assert owner.status_code == 200
    assert other_workspace.status_code == 404
    assert other_user.status_code == 404


def test_read_latest_record_rejects_another_scope_even_if_cached() -> None:
    _seed(USER_A, WORKSPACE_A, JOB_A, rows=120, filename="central.csv")
    _select_scope(USER_A, WORKSPACE_B)

    assert read_latest_upload_record() is None
