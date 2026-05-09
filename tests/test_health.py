from fastapi.testclient import TestClient

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


def test_facility_systems_endpoint_returns_placeholder_systems() -> None:
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
    assert payload["intelligence"]["source"] == "sii_engine"
    assert payload["intelligence"]["mode"] == "sample"
    assert payload["intelligence"]["neraium_score"] > 0
    assert payload["intelligence"]["rooms"]
    required_fields = {
        "facility_state",
        "room_state",
        "urgency",
        "intervention_window",
        "neraium_score",
        "primary_driver",
        "supporting_evidence",
        "relationship_evidence",
        "structural_explanation",
        "confidence_basis",
        "recommended_operator_review",
        "what_to_check",
        "why_flagged",
        "baseline_comparison",
        "observed_persistence",
        "last_updated",
    }
    assert required_fields <= set(payload["intelligence"])


def test_intelligence_status_endpoint_returns_sii_mode() -> None:
    client = TestClient(create_app())

    response = client.get("/api/intelligence/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["engine_loaded"] is True
    assert payload["source"] == "sii_engine"
    assert payload["mode"] == "sample"
    assert payload["active_rooms_count"] > 0
    assert "primary_driver" in payload["evidence_fields_present"]


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
    assert payload["source"] == "sample"


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


def test_facility_systems_uses_sample_when_latest_sii_state_is_corrupt() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text("{not-valid-json", encoding="utf-8")
    client = TestClient(create_app())

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intelligence"]["source"] == "sii_engine"
    assert payload["intelligence"]["mode"] == "sample"


def test_facility_systems_uses_sample_when_latest_sii_state_is_incomplete() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text('{"source": "uploaded"}', encoding="utf-8")
    client = TestClient(create_app())

    response = client.get("/api/facility/systems")

    assert response.status_code == 200
    payload = response.json()
    assert payload["intelligence"]["source"] == "sii_engine"
    assert payload["intelligence"]["mode"] == "sample"


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
