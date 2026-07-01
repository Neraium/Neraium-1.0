from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.service_status import STARTUP_STATUS, reset_startup_status
from app.services.sii_runner import CORE_ENGINE, RUNNER_CALLABLE, RUNNER_MODULE, STATE_PATH, VALIDATION_RUNNER, write_latest_sii_state


def test_root_endpoint_returns_service_metadata() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "neraium-api"
    assert payload["status"] == "ok"
    assert payload["docs"] == "/docs"
    assert payload["health"] == "/health"


def test_health_endpoint_returns_ok() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "neraium-api"
    assert payload["startup_complete"] is True
    assert payload["failed_modules"] == []
    assert payload["upload_session_state"] == "not_checked"
    assert payload["upload_session_metrics"] == {}
    assert payload["diagnostics"]["upload"]["latest_upload_session_id"] is None
    assert payload["diagnostics"]["upload"]["latest_upload_state"] is None


def test_health_endpoint_does_not_resolve_upload_session(monkeypatch) -> None:
    def fail_upload_session_lookup(*args, **kwargs):
        raise AssertionError("health endpoint should not resolve upload session state")

    monkeypatch.setattr("app.routers.health.resolve_latest_upload_session", fail_upload_session_lookup)
    monkeypatch.setattr("app.services.service_status.resolve_latest_upload_session", fail_upload_session_lookup)

    with TestClient(create_app()) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["upload_session_state"] == "not_checked"
    assert payload["diagnostics"]["upload"]["latest_upload_session_id"] is None


def test_health_endpoint_returns_degraded_when_startup_failed() -> None:
    with TestClient(create_app()) as client:
        STARTUP_STATUS["startup_complete"] = True
        STARTUP_STATUS["failed_modules"] = ["runtime_db: unavailable"]

        response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["failed_modules"] == ["runtime_db: unavailable"]


def test_ready_endpoint_exposes_upload_state_backend_metadata() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/ready")
    assert response.status_code == 200
    payload = response.json()
    assert "upload_state_backend" in payload
    assert "upload_state_shared_configured" in payload
    assert payload["details"]["mode"] == "lightweight"
    assert "queue_operational_metrics" not in payload["details"]
    assert "upload_session_metrics" not in payload["details"]
    assert payload["checks"]["startup"] == "ok"




def test_ready_endpoint_exposes_runtime_upload_diagnostics(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
        process_role="api",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/ready?verbose=true")

    assert response.status_code == 503
    payload = response.json()
    diagnostics = payload["diagnostics"]
    assert diagnostics["api"]["upload_endpoint"] == "/api/data/upload"
    assert diagnostics["upload"]["queue_backend"] in {"runtime_db", "s3"}
    assert diagnostics["upload"]["upload_state_backend"] in {"local", "runtime_db", "s3"}
    assert diagnostics["worker"]["configured_start_background_workers"] is False
    assert diagnostics["deployment"]["build_sha"]
    assert payload["status"] == "not_ready"
    assert payload["checks"]["shared_upload_state"] == "error"
    assert payload["details"]["mode"] == "verbose"
    assert "split_role_shared_upload_state_not_configured" in payload["config_warnings"]


def test_health_endpoint_exposes_last_upload_failure_diagnostic(tmp_path) -> None:
    settings = Settings(
        app_env="development",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["*"],
        runtime_dir=tmp_path,
    )
    with TestClient(create_app(settings)) as client:
        from app.services.upload_jobs import write_job

        write_job({
            "job_id": "diagnostic-failure",
            "status": "FAILED",
            "processing_state": "failed",
            "error_type": "csv_validation_error",
            "message": "CSV file is empty.",
        })
        response = client.get("/api/ready?verbose=true")

    assert response.status_code == 503
    upload = response.json()["diagnostics"]["upload"]
    assert upload["latest_upload_session_id"] == "diagnostic-failure"
    assert upload["latest_upload_error_type"] == "csv_validation_error"
    assert upload["latest_upload_message"] == "CSV file is empty."

def test_ready_endpoint_returns_not_ready_when_startup_failed() -> None:
    with TestClient(create_app()) as client:
        STARTUP_STATUS["startup_complete"] = True
        STARTUP_STATUS["failed_modules"] = ["upload_worker: unavailable"]

        response = client.get("/api/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["startup"] == "error"
    assert payload["failed_modules"] == ["upload_worker: unavailable"]


def test_facility_systems_endpoint_returns_empty_state_without_upload() -> None:
    client = TestClient(create_app())

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["systems"] == []
    assert payload["intelligence"] is None
    assert payload["intelligence_status"]["source"] == "none"
    assert payload["intelligence_status"]["mode"] == "empty"
    assert payload["intelligence_status"]["status"] == "no_data"


def test_intelligence_status_endpoint_returns_empty_state_without_upload() -> None:
    client = TestClient(create_app())

    response = client.get("/api/intelligence/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["engine_loaded"] is True
    assert payload["source"] == "none"
    assert payload["mode"] == "empty"
    assert payload["active_rooms_count"] == 0
    assert payload["status"] == "no_data"


def test_engine_identity_endpoint_returns_actual_engine_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/api/intelligence/engine-identity")

    assert response.status_code == 200
    payload = response.json()
    assert payload["engine_name"] == "Neraium SII"
    assert payload["engine_version"] == "neraium-cultivation-v1"
    assert payload["engine_module"] == RUNNER_MODULE
    assert payload["engine_class_or_function"] == RUNNER_CALLABLE
    assert payload["git_commit"]
    assert payload["deployment_mode"] == "production"
    assert payload["validation_engine_path_present"] is False
    assert payload["cmapss_validation_supported"] is False
    assert payload["driver_attribution_supported"] is True
    assert payload["sii_pipeline_supported"] is True
    assert payload["production_runner"] == RUNNER_CALLABLE
    assert payload["core_engine"] == CORE_ENGINE
    assert payload["validation_runner"] == VALIDATION_RUNNER
    assert payload["same_engine_family_as_validation"] is False
    assert payload["same_exact_fd004_validation_runner"] is False
    assert payload["actual_imports"]["upload_processing"]["module"] == RUNNER_MODULE
    assert payload["actual_imports"]["driver_attribution"]["callable"] == "build_driver_attribution"
    assert payload["validation_provenance"]["same_engine_family"] is False
    assert payload["validation_provenance"]["same_exact_validation_runner"] is False


def test_runner_status_endpoint_reports_real_adapter() -> None:
    client = TestClient(create_app())

    response = client.get("/api/intelligence/runner-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runner_available"] is True
    assert payload["runner_module"] == RUNNER_MODULE
    assert payload["core_engine"] == CORE_ENGINE
    assert payload["validation_runner"] == VALIDATION_RUNNER
    assert payload["same_engine_family_as_validation"] is False
    assert payload["same_exact_fd004_validation_runner"] is False
    assert payload["source"] == "none"
    assert payload["state_available"] is False
    assert payload["state_timestamp_valid"] is True
    assert payload["state_age_seconds"] is None


def test_runner_status_endpoint_reports_state_age_when_latest_state_exists() -> None:
    write_latest_sii_state(
        {
            "source": "uploaded",
            "mode": "live",
            "facility_state": "Runner facility state",
            "room_state": "Runner room state",
            "urgency": "review",
            "intervention_window": "6 days",
            "neraium_score": 91,
            "primary_room": "Runner Room",
            "priority_room": "Runner Room",
            "primary_driver": "Runner driver",
            "supporting_evidence": ["Runner evidence"],
            "relationship_evidence": ["Runner relationship"],
            "structural_explanation": ["Runner explanation"],
            "confidence_basis": "Runner confidence",
            "recommended_operator_review": "Runner move",
            "what_to_check": ["Runner check"],
            "why_flagged": "Runner reason",
            "baseline_comparison": "Runner baseline",
            "observed_persistence": "Runner persistence",
            "last_updated": datetime.now(UTC).isoformat(),
            "last_processed_at": datetime.now(UTC).isoformat(),
            "rooms": [],
        }
    )
    client = TestClient(create_app())

    payload = client.get("/api/intelligence/runner-status").json()

    assert payload["state_available"] is True
    assert payload["state_timestamp_valid"] is True
    assert isinstance(payload["state_age_seconds"], int)
    assert payload["state_age_seconds"] >= 0


def test_facility_systems_suppresses_latest_sii_state_without_active_upload() -> None:
    write_latest_sii_state(
        {
            "source": "uploaded",
            "mode": "live",
            "facility_state": "Runner facility state",
            "room_state": "Runner room state",
            "urgency": "review",
            "intervention_window": "6 days",
            "neraium_score": 91,
            "primary_room": "Runner Room",
            "priority_room": "Runner Room",
            "primary_driver": "Runner driver",
            "supporting_evidence": ["Runner evidence"],
            "relationship_evidence": ["Runner relationship"],
            "structural_explanation": ["Runner explanation"],
            "confidence_basis": "Runner confidence",
            "recommended_operator_review": "Runner move",
            "what_to_check": ["Runner check"],
            "why_flagged": "Runner reason",
            "baseline_comparison": "Runner baseline",
            "observed_persistence": "Runner persistence",
            "last_updated": "2026-05-08T00:00:00+00:00",
            "last_processed_at": "2026-05-08T00:00:00+00:00",
            "rooms": [],
        }
    )
    client = TestClient(create_app())

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intelligence"] is None
    assert payload["intelligence_status"]["mode"] == "empty"


def test_facility_systems_returns_empty_state_when_latest_sii_state_is_corrupt() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text("{not-valid-json", encoding="utf-8")
    client = TestClient(create_app())

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intelligence"] is None
    assert payload["intelligence_status"]["mode"] == "empty"


def test_facility_systems_returns_empty_state_when_latest_sii_state_is_incomplete() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text('{"source": "uploaded"}', encoding="utf-8")
    client = TestClient(create_app())

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intelligence"] is None
    assert payload["intelligence_status"]["mode"] == "empty"


def test_latest_sii_state_write_replaces_atomically() -> None:
    write_latest_sii_state(
        {
            "source": "uploaded",
            "facility_state": "Atomic state",
            "rooms": [],
            "priority_room": "Runner Room",
            "neraium_score": 88,
            "primary_driver": "Runner driver",
            "supporting_evidence": ["Runner evidence"],
            "structural_explanation": ["Runner explanation"],
            "confidence_basis": "Runner confidence",
            "last_processed_at": "2026-05-08T00:00:00+00:00",
        }
    )

    assert STATE_PATH.exists()
    assert not STATE_PATH.with_suffix(".json.tmp").exists()


def test_health_endpoint_returns_cors_header_for_production_frontend() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://app.neraium.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.neraium.com"


def test_facility_systems_endpoint_returns_cors_header_for_production_frontend() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/api/facility/systems",
        headers={
            "Origin": "https://app.neraium.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.neraium.com"


def test_latest_upload_endpoint_returns_cors_header_for_production_frontend() -> None:
    client = TestClient(create_app())

    response = client.options(
        "/api/data/latest-upload",
        headers={
            "Origin": "https://app.neraium.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.neraium.com"


def test_api_errors_return_json_with_cors_header_for_production_frontend(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.latest_upload_state.read_latest_upload_record",
        lambda: (_ for _ in ()).throw(RuntimeError("runtime state unavailable")),
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get(
        "/api/data/latest-upload",
        headers={"Origin": "https://app.neraium.com"},
    )

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "https://app.neraium.com"
    assert response.json()["error_type"] == "api_request_error"


def test_upload_preflight_succeeds_without_auth_for_production_frontend(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))

    response = client.options(
        "/api/data/upload",
        headers={
            "Origin": "https://app.neraium.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-neraium-access-code",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.neraium.com"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_upload_status_preflight_succeeds_without_auth_for_local_vite(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://127.0.0.1:5173"],
        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))

    response = client.options(
        "/api/data/upload-status/example-job",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-neraium-access-code",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_facility_systems_allows_requests_without_shared_secret_in_production(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    assert response.json()["systems"] == []


def test_facility_systems_ignores_bearer_secret_in_production(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))

    response = client.get(
        "/api/facility/systems",
        headers={"Authorization": "Bearer expected-secret"},
    )

    assert response.status_code == 200
    assert response.json()["systems"] == []


def test_access_header_is_ignored_without_refreshing_auth_cookie(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))

    response = client.get(
        "/api/facility/systems",
        headers={"X-Neraium-Access-Code": "expected-secret"},
    )

    assert response.status_code == 200
    assert "set-cookie" not in response.headers


def test_engine_identity_accepts_access_header_in_production(tmp_path) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))

    response = client.get(
        "/api/intelligence/engine-identity",
        headers={"X-Neraium-Access-Code": "expected-secret"},
    )

    assert response.status_code == 200
    assert response.json()["engine_name"] == "Neraium SII"


def test_wrong_bearer_code_does_not_block_production_requests(tmp_path, caplog) -> None:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))

    response = client.get(
        "/api/facility/systems",
        headers={
            "Origin": "https://app.neraium.com",
            "Authorization": "Bearer wrong-secret",
        },
    )

    assert response.status_code == 200
    assert response.json()["systems"] == []
    log_text = caplog.text
    assert "wrong-secret" not in log_text
    assert "expected-secret" not in log_text
