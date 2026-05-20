from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.connectors.rest_connector import RESTConnector
from app.core.config import Settings
from app.main import create_app


def build_client(tmp_path) -> TestClient:
    settings = Settings(
        app_env="development",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://localhost:5173"],
        runtime_dir=tmp_path,
    )
    return TestClient(create_app(settings))


def test_connector_types_endpoint_lists_supported_connectors(tmp_path) -> None:
    client = build_client(tmp_path)

    response = client.get("/api/connectors/types")

    assert response.status_code == 200
    payload = response.json()
    connector_types = {item["connector_type"] for item in payload["types"]}
    assert {
        "csv",
        "rest",
        "database",
        "mqtt",
        "opcua",
        "bacnet",
        "pentair",
        "hayward",
        "modbus",
        "nodered",
        "bas_bms",
    } <= connector_types


def test_csv_connector_upload_normalizes_records_and_updates_health(tmp_path) -> None:
    client = build_client(tmp_path)
    csv_content = (
        "timestamp,room,temperature,humidity\n"
        "2026-05-01T08:00:00Z,Flower 1,75.2,58\n"
        "2026-05-01T08:05:00Z,Flower 1,75.6,59\n"
    )

    response = client.post(
        "/api/connectors/csv/upload",
        files={"file": ("rooms.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["connector_type"] == "csv"
    assert payload["records_ingested"] == 4
    assert payload["sensors_detected"] == 2
    assert payload["normalized_preview"][0]["timestamp"] == "2026-05-01T08:00:00"

    health = client.get("/api/connectors/health")
    assert health.status_code == 200
    csv_status = next(item for item in health.json()["connectors"] if item["connector_type"] == "csv")
    assert csv_status["connection_status"] == "ready"
    assert csv_status["records_ingested"] == 4


def test_csv_connector_reports_invalid_rows_without_stack_trace(tmp_path) -> None:
    client = build_client(tmp_path)
    csv_content = (
        "timestamp,temperature\n"
        "2026-05-01T08:00:00Z,74\n"
        ",75\n"
        "2026-05-01T08:10:00Z,not-a-number\n"
    )

    response = client.post(
        "/api/connectors/csv/upload",
        files={"file": ("invalid.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["records_ingested"] == 1
    assert any("Timestamp is missing" in warning for warning in payload["warnings"])
    assert any("must be numeric" in warning for warning in payload["warnings"])


def test_csv_connector_rejects_empty_dataset(tmp_path) -> None:
    client = build_client(tmp_path)

    response = client.post(
        "/api/connectors/csv/upload",
        files={"file": ("empty.csv", "", "text/csv")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "CSV dataset is empty."


def test_rest_connector_normalizes_response_and_health_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "records": [
                    {"timestamp": "2026-05-01T08:00:00Z", "room": "Flower 1", "temperature": 75.5, "humidity": 58},
                    {"timestamp": "2026-05-01T08:05:00Z", "room": "Flower 1", "temperature": 75.7, "humidity": 59},
                ]
            },
        )

    connector = RESTConnector(
        {
            "endpoint": "https://customer.example.com/telemetry",
            "source_id": "customer-rest",
            "system_id": "facility-rest",
            "token": "super-secret-token",
        },
        transport=httpx.MockTransport(handler),
    )

    assert connector.validate_connection()["ok"] is True
    batch = connector.normalize(connector.fetch_historical())
    health = connector.health_check()

    assert batch.record_count == 4
    assert batch.sensor_count == 2
    assert batch.records[0].timestamp == "2026-05-01T08:00:00"
    assert health.masked_configuration["headers"]["token"].startswith("su")


def test_rest_connector_rejects_malformed_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    connector = RESTConnector(
        {"endpoint": "https://customer.example.com/telemetry"},
        transport=httpx.MockTransport(handler),
    )

    try:
        connector.fetch_historical()
    except ValueError as exc:
        assert str(exc) == "REST API response did not include a usable telemetry record list."
    else:
        raise AssertionError("Expected malformed REST response to raise ValueError.")
