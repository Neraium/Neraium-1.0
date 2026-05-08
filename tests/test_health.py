from fastapi.testclient import TestClient

from app.main import create_app


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
    assert payload["engine_version"] == "neraium-cultivation-v1"
    assert payload["engine_module"] == "app.engine.analysis"
    assert payload["engine_class_or_function"] == "run_engine_analysis"
    assert payload["git_commit"]
    assert payload["deployment_mode"] == "production"
    assert payload["validation_engine_path_present"] is True
    assert payload["cmapss_validation_supported"] is False
    assert payload["driver_attribution_supported"] is True
    assert payload["sii_pipeline_supported"] is True
    assert payload["actual_imports"]["upload_processing"]["module"] == "app.engine.analysis"
    assert payload["actual_imports"]["driver_attribution"]["callable"] == "build_driver_attribution"
    assert payload["actual_imports"]["validation_runner"] is None
    assert payload["validation_provenance"]["same_engine_family"] is True
    assert payload["validation_provenance"]["same_exact_validation_runner"] is False


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
