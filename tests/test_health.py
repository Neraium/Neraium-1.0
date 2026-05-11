from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.sii_runner import RUNNER_MODULE, STATE_PATH, write_latest_sii_state


def test_root_endpoint_returns_service_metadata() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "service": "neraium-api",
        "status": "ok",
        "docs": "/docs",
        "health": "/health",
    }


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "neraium-api"}


def test_facility_systems_endpoint_returns_empty_state_without_upload() -> None:
    client = TestClient(create_app())

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert [system["name"] for system in payload["systems"]] == [
        "HVAC",
        "Humidity control",
        "Airflow",
        "Irrigation",
        "Lighting",
        "Sensor network",
    ]
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
    assert payload["engine_version"] == "neraium-core 0.1.0"
    assert payload["engine_module"] == RUNNER_MODULE
    assert payload["engine_class_or_function"] == "neraium_core.sii_engine_adapter.SIIEngineAdapter.ingest"
    assert payload["git_commit"]
    assert payload["deployment_mode"] == "production"
    assert payload["validation_engine_path_present"] is True
    assert payload["cmapss_validation_supported"] is True
    assert payload["driver_attribution_supported"] is True
    assert payload["sii_pipeline_supported"] is True
    assert payload["production_runner"] == "neraium_core.sii_engine_adapter.SIIEngineAdapter.ingest"
    assert payload["core_engine"] == "neraium_core.sii_engine_unified.SIIEngine"
    assert payload["validation_runner"] == "neraium_core.sii_fd004_validation.FD004ValidationRunner"
    assert payload["same_engine_family_as_validation"] is True
    assert payload["same_exact_fd004_validation_runner"] is False
    assert payload["actual_imports"]["upload_processing"]["module"] == RUNNER_MODULE
    assert payload["actual_imports"]["driver_attribution"]["callable"] == "build_driver_attribution"
    assert payload["validation_provenance"]["same_engine_family"] is True
    assert payload["validation_provenance"]["same_exact_validation_runner"] is False


def test_runner_status_endpoint_reports_real_adapter() -> None:
    client = TestClient(create_app())

    response = client.get("/api/intelligence/runner-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["runner_available"] is True
    assert payload["runner_module"] == RUNNER_MODULE
    assert payload["core_engine"] == "neraium_core.sii_engine_unified.SIIEngine"
    assert payload["validation_runner"] == "neraium_core.sii_fd004_validation.FD004ValidationRunner"
    assert payload["same_engine_family_as_validation"] is True
    assert payload["same_exact_fd004_validation_runner"] is False
    assert payload["source"] == "none"


def test_facility_systems_prefers_latest_sii_state_when_present() -> None:
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
    assert payload["intelligence"]["source"] == "uploaded"
    assert payload["intelligence"]["facility_state"] == "Runner facility state"
    assert payload["intelligence"]["primary_driver"] == "Runner driver"


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
    assert response.json()["systems"]


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
    assert response.json()["systems"]


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
    assert response.json()["systems"]
    log_text = caplog.text
    assert "wrong-secret" not in log_text
    assert "expected-secret" not in log_text
