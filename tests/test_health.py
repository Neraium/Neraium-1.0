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
