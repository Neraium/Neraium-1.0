from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.routers import data as data_router
from app.services import upload_state_repository, upload_validator


AUTH_HEADERS = {"X-Neraium-Access-Code": "large-upload-test-token"}
LARGE_FILE_SIZE = round(409.5 * 1024 * 1024)


def production_settings(tmp_path, *, max_large_upload_size_bytes=512 * 1024 * 1024):
    return Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
        process_role="api",
        max_upload_size_bytes=250 * 1024 * 1024,
        max_large_upload_size_bytes=max_large_upload_size_bytes,
    )


def install_large_upload_fakes(monkeypatch, *, object_size=LARGE_FILE_SIZE):
    sessions = {}
    jobs = {}
    enqueued = []
    presigned = []

    def create_target(session_id, *, filename, content_type, expires_in_seconds):
        presigned.append((session_id, filename, content_type, expires_in_seconds))
        return {
            "object_key": f"upload-state/scopes/test/upload-sources/{session_id}.csv",
            "upload_url": f"https://upload.example.test/{session_id}?signature=redacted",
            "upload_headers": {
                "Content-Type": content_type,
                "x-amz-tagging": "neraium-upload-source=true",
                "If-None-Match": "*",
            },
        }

    def write_session(session_id, payload):
        sessions[session_id] = dict(payload)
        return sessions[session_id]

    monkeypatch.setattr(data_router, "shared_state_configured", lambda: True)
    monkeypatch.setattr(data_router, "create_presigned_upload_target", create_target)
    monkeypatch.setattr(data_router, "write_large_upload_session", write_session)
    monkeypatch.setattr(data_router, "read_large_upload_session", lambda session_id: sessions.get(session_id))
    monkeypatch.setattr(data_router, "inspect_upload_source", lambda _key: {
        "content_length": object_size,
        "content_type": "text/csv",
        "etag": "large-etag",
    })
    monkeypatch.setattr(data_router, "queue_metrics", lambda: {"pending": 0, "processing": 0})
    monkeypatch.setattr(data_router, "enqueue_upload_job", lambda job_id: enqueued.append(job_id))
    monkeypatch.setattr(data_router.upload_jobs, "write_job", lambda payload: jobs.__setitem__(payload["job_id"], dict(payload)))
    monkeypatch.setattr(data_router.upload_jobs, "read_upload_status", lambda job_id: jobs.get(job_id))
    monkeypatch.setattr(data_router, "record_audit_event", lambda **_kwargs: None)
    monkeypatch.setattr(data_router, "upsert_evidence_run", lambda _payload: None)
    monkeypatch.setattr(data_router, "_dispatch_upload_worker_for_runtime", lambda _runtime_dir: None)
    return sessions, jobs, enqueued, presigned


def test_409_5_mib_csv_creates_presigned_session_and_exact_analysis_job(monkeypatch, tmp_path):
    monkeypatch.setenv("NERAIUM_API_TOKEN", AUTH_HEADERS["X-Neraium-Access-Code"])
    sessions, jobs, enqueued, presigned = install_large_upload_fakes(monkeypatch)
    client = TestClient(create_app(production_settings(tmp_path)))

    session_response = client.post(
        "/api/data/upload-session",
        headers=AUTH_HEADERS,
        json={
            "filename": "ChillerPlant.csv",
            "size_bytes": LARGE_FILE_SIZE,
            "content_type": "text/csv",
        },
    )

    assert session_response.status_code == 201
    session_payload = session_response.json()
    session_id = session_payload["upload_session_id"]
    assert session_payload["upload_method"] == "PUT"
    assert session_payload["max_upload_size_bytes"] == 512 * 1024 * 1024
    assert session_payload["upload_headers"] == {
        "Content-Type": "text/csv",
        "x-amz-tagging": "neraium-upload-source=true",
        "If-None-Match": "*",
    }
    assert sessions[session_id]["filename"] == "ChillerPlant.csv"
    assert sessions[session_id]["size_bytes"] == LARGE_FILE_SIZE
    assert presigned == [(session_id, "ChillerPlant.csv", "text/csv", 3600)]

    complete_response = client.post(
        f"/api/data/upload-session/{session_id}/complete",
        headers=AUTH_HEADERS,
        json={"etag": "large-etag"},
    )

    assert complete_response.status_code == 202
    complete_payload = complete_response.json()
    assert complete_payload["job_id"] == session_id
    assert complete_payload["status_url"] == f"/api/data/upload-status/{session_id}"
    assert complete_payload["filename"] == "ChillerPlant.csv"
    assert complete_payload["upload_transport"] == "presigned_s3_put"
    assert enqueued == [session_id]
    assert jobs[session_id]["shared_upload_source_key"].endswith(f"/{session_id}.csv")
    assert jobs[session_id]["file_path"] is None
    assert sessions[session_id]["state"] == "job_created"

    idempotent_response = client.post(
        f"/api/data/upload-session/{session_id}/complete",
        headers=AUTH_HEADERS,
        json={"etag": "large-etag"},
    )
    assert idempotent_response.status_code == 202
    assert idempotent_response.json()["job_id"] == session_id
    assert enqueued == [session_id]


def test_large_baseline_upload_preserves_workflow_without_creating_evidence(monkeypatch, tmp_path):
    monkeypatch.setenv("NERAIUM_API_TOKEN", AUTH_HEADERS["X-Neraium-Access-Code"])
    sessions, jobs, enqueued, _presigned = install_large_upload_fakes(monkeypatch)

    def fail_if_evidence_is_created(_payload):
        raise AssertionError("baseline construction must not create an SII evidence run")

    monkeypatch.setattr(data_router, "upsert_evidence_run", fail_if_evidence_is_created)
    client = TestClient(create_app(production_settings(tmp_path)))
    session_response = client.post(
        "/api/data/upload-session",
        headers=AUTH_HEADERS,
        json={
            "filename": "HistoricalPlant.csv",
            "size_bytes": LARGE_FILE_SIZE,
            "content_type": "text/csv",
            "workflow": "create_baseline",
            "approval_required": True,
        },
    )

    assert session_response.status_code == 201
    session_id = session_response.json()["upload_session_id"]
    assert sessions[session_id]["workflow"] == "create_baseline"
    assert sessions[session_id]["approval_required"] is True

    complete_response = client.post(
        f"/api/data/upload-session/{session_id}/complete",
        headers=AUTH_HEADERS,
        json={"etag": "large-etag"},
    )

    assert complete_response.status_code == 202
    assert complete_response.json()["workflow"] == "create_baseline"
    assert complete_response.json()["sii_engine_invoked"] is False
    assert jobs[session_id]["workflow"] == "create_baseline"
    assert jobs[session_id]["runner_used"] is False
    assert jobs[session_id]["sii_engine_invoked"] is False
    assert enqueued == [session_id]


def test_large_upload_session_rejects_file_above_supported_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("NERAIUM_API_TOKEN", AUTH_HEADERS["X-Neraium-Access-Code"])
    _sessions, _jobs, _enqueued, presigned = install_large_upload_fakes(monkeypatch)
    client = TestClient(create_app(production_settings(tmp_path)))

    response = client.post(
        "/api/data/upload-session",
        headers=AUTH_HEADERS,
        json={
            "filename": "too-large.csv",
            "size_bytes": (512 * 1024 * 1024) + 1,
            "content_type": "text/csv",
        },
    )

    assert response.status_code == 413
    assert response.json()["error_type"] == "upload_too_large"
    assert response.json()["message"] == "File is larger than the supported upload limit of 512 MB."
    assert presigned == []


def test_large_upload_completion_rejects_incomplete_object_without_creating_job(monkeypatch, tmp_path):
    monkeypatch.setenv("NERAIUM_API_TOKEN", AUTH_HEADERS["X-Neraium-Access-Code"])
    _sessions, jobs, enqueued, _presigned = install_large_upload_fakes(monkeypatch, object_size=LARGE_FILE_SIZE - 1)
    client = TestClient(create_app(production_settings(tmp_path)))
    session = client.post(
        "/api/data/upload-session",
        headers=AUTH_HEADERS,
        json={"filename": "ChillerPlant.csv", "size_bytes": LARGE_FILE_SIZE, "content_type": "text/csv"},
    ).json()

    response = client.post(
        f"/api/data/upload-session/{session['upload_session_id']}/complete",
        headers=AUTH_HEADERS,
        json={"etag": "large-etag"},
    )

    assert response.status_code == 409
    assert response.json()["error_type"] == "upload_size_mismatch"
    assert jobs == {}
    assert enqueued == []


def test_job_creation_failure_is_visible_and_retry_reuses_the_same_upload(monkeypatch, tmp_path):
    monkeypatch.setenv("NERAIUM_API_TOKEN", AUTH_HEADERS["X-Neraium-Access-Code"])
    sessions, jobs, enqueued, _presigned = install_large_upload_fakes(monkeypatch)
    client = TestClient(create_app(production_settings(tmp_path)))
    session = client.post(
        "/api/data/upload-session",
        headers=AUTH_HEADERS,
        json={"filename": "ChillerPlant.csv", "size_bytes": LARGE_FILE_SIZE, "content_type": "text/csv"},
    ).json()
    session_id = session["upload_session_id"]

    def fail_enqueue(_job_id):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(data_router, "enqueue_upload_job", fail_enqueue)
    failed = client.post(
        f"/api/data/upload-session/{session_id}/complete",
        headers=AUTH_HEADERS,
        json={"etag": "large-etag"},
    )

    assert failed.status_code == 503
    assert failed.json()["error_type"] == "upload_enqueue_failed"
    assert failed.json()["message"] == "Upload completed, but analysis could not be started."
    assert jobs[session_id]["status"] == "FAILED"
    assert sessions[session_id]["state"] == "awaiting_upload"

    monkeypatch.setattr(data_router, "enqueue_upload_job", lambda job_id: enqueued.append(job_id))
    retried = client.post(
        f"/api/data/upload-session/{session_id}/complete",
        headers=AUTH_HEADERS,
        json={"etag": "large-etag"},
    )

    assert retried.status_code == 202
    assert retried.json()["job_id"] == session_id
    assert enqueued == [session_id]
    assert sessions[session_id]["state"] == "job_created"


def test_large_upload_endpoints_require_authentication_in_production(monkeypatch, tmp_path):
    monkeypatch.setenv("NERAIUM_API_TOKEN", AUTH_HEADERS["X-Neraium-Access-Code"])
    install_large_upload_fakes(monkeypatch)
    client = TestClient(create_app(production_settings(tmp_path)))

    response = client.post(
        "/api/data/upload-session",
        json={"filename": "ChillerPlant.csv", "size_bytes": LARGE_FILE_SIZE, "content_type": "text/csv"},
    )

    assert response.status_code == 401
    assert response.json()["error_type"] == "auth"


def test_presigned_target_signs_required_headers_without_reading_file_content(monkeypatch):
    calls = []

    class FakeS3Client:
        def generate_presigned_url(self, operation, **kwargs):
            calls.append((operation, kwargs))
            return "https://upload.example.test/signed"

    monkeypatch.setenv("NERAIUM_UPLOAD_STATE_BUCKET", "upload-state-test")
    monkeypatch.setattr(upload_state_repository, "_get_s3_client", lambda: FakeS3Client())

    target = upload_state_repository.create_presigned_upload_target(
        "session-id",
        filename="ChillerPlant.csv",
        content_type="text/csv",
    )

    assert target["upload_url"] == "https://upload.example.test/signed"
    assert target["upload_headers"] == {
        "Content-Type": "text/csv",
        "x-amz-tagging": "neraium-upload-source=true",
        "If-None-Match": "*",
    }
    operation, kwargs = calls[0]
    assert operation == "put_object"
    assert kwargs["HttpMethod"] == "PUT"
    assert kwargs["Params"]["Bucket"] == "upload-state-test"
    assert kwargs["Params"]["ContentType"] == "text/csv"
    assert kwargs["Params"]["Tagging"] == "neraium-upload-source=true"
    assert kwargs["Params"]["IfNoneMatch"] == "*"
    assert "Body" not in kwargs["Params"]


def test_large_csv_duplicate_index_switches_to_bounded_memory(monkeypatch):
    monkeypatch.setattr(upload_validator, "DEDUPLICATION_EXACT_HASH_LIMIT", 2)
    tracker = upload_validator.BoundedHashTracker()
    first = b"a" * 16
    second = b"b" * 16
    third = b"c" * 16

    assert tracker.contains_or_add(first) is False
    assert tracker.contains_or_add(second) is False
    assert tracker.contains_or_add(third) is False
    assert tracker.bounded_mode is True
    assert len(tracker._exact) == 2
    assert tracker.contains_or_add(first) is True
    assert tracker.contains_or_add(b"d" * 16) is False
    assert len(tracker._exact) == 2
