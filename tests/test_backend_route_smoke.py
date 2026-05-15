from fastapi.testclient import TestClient

from app.main import app


def test_backend_route_smoke() -> None:
    client = TestClient(app)

    endpoints = [
        "/health",
        "/api/ready",
        "/api/startup-status",
        "/api/routes/debug",
        "/api/facility/systems",
        "/api/facility/cognition-state?mode=live",
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
