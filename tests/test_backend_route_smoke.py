from fastapi.testclient import TestClient

from app.main import app


def test_backend_route_smoke() -> None:
    with TestClient(app) as client:
        endpoints = [
            "/health",
            "/latest-upload?include_persisted=1",
            "/systems?include_persisted=1",
            "/api/ready",
            "/api/startup-status",
            "/api/routes/debug",
            "/api/facility/systems",
            "/api/facility/cognition-state",
            "/api/data/latest-upload",
            "/api/intelligence/status",
        ]

        for endpoint in endpoints:
            response = client.get(endpoint)
            assert response.status_code == 200, f"{endpoint} returned {response.status_code}"
            payload = response.json()
            assert payload is not None

        debug_payload = client.get("/api/routes/debug").json()
        routes = debug_payload.get("routes", [])
        paths = {route.get("path") for route in routes if isinstance(route, dict)}
        assert "/api/facility/cognition-state" in paths
