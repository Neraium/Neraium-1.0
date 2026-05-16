"""Tests for API health endpoints."""

import pytest


@pytest.mark.unit
def test_root_endpoint(client):
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "neraium-api"
    assert data["status"] == "ok"


@pytest.mark.unit
def test_health_endpoint(client):
    """Test /health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.unit
def test_api_health_endpoint(client):
    """Test /api/health endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.unit
def test_startup_status(client):
    """Test /api/startup-status."""
    response = client.get("/api/startup-status")
    assert response.status_code == 200
    data = response.json()
    assert "startup_complete" in data
    assert "failed_modules" in data


@pytest.mark.unit
def test_routes_debug(client):
    """Test /api/routes/debug."""
    response = client.get("/api/routes/debug")
    assert response.status_code == 200
    data = response.json()
    assert data["mounted"] is True
    assert data["route_count"] > 0


@pytest.mark.unit
def test_security_headers(client):
    """Test security headers."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
