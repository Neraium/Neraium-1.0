from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.connectors.database_connector import DatabaseConnector
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


def create_telemetry_database(tmp_path) -> tuple[str, Path]:
    database_path = tmp_path / "telemetry.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE telemetry (timestamp TEXT, room TEXT, temperature REAL, humidity REAL)"
        )
        connection.executemany(
            "INSERT INTO telemetry VALUES (?, ?, ?, ?)",
            [
                ("2026-05-01T08:00:00Z", "Mechanical 1", 75.5, 58),
                ("2026-05-01T08:05:00Z", "Mechanical 1", 75.7, 59),
            ],
        )
    return f"sqlite:///{database_path.as_posix()}", database_path


def test_database_connector_executes_read_only_query_and_normalizes(tmp_path) -> None:
    database_url, _ = create_telemetry_database(tmp_path)
    connector = DatabaseConnector(
        {
            "database_url": database_url,
            "query": "SELECT timestamp, room, temperature, humidity FROM telemetry ORDER BY timestamp",
            "source_id": "customer-db",
            "system_id": "facility-db",
        }
    )

    assert connector.validate_connection()["ok"] is True
    batch = connector.normalize(connector.fetch_historical())
    health = connector.health_check()

    assert batch.connector_type == "database"
    assert batch.record_count == 4
    assert batch.sensor_count == 2
    assert batch.records[0].source_id == "customer-db"
    assert batch.records[0].timestamp == "2026-05-01T08:00:00"
    assert health.functional is True
    assert health.masked_configuration["database"]["database"] == "telemetry.db"
    assert "database_url" not in health.model_dump_json()


def test_database_connector_rejects_writes_and_enforces_row_limit(tmp_path) -> None:
    database_url, database_path = create_telemetry_database(tmp_path)
    write_connector = DatabaseConnector(
        {"database_url": database_url, "query": "DELETE FROM telemetry"}
    )

    validation = write_connector.validate_connection()
    assert validation["ok"] is False
    assert validation["message"] == "Database connector only accepts SELECT or WITH queries."
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0] == 2

    limited_connector = DatabaseConnector(
        {"database_url": database_url, "query": "SELECT * FROM telemetry", "max_rows": 1}
    )
    limited_validation = limited_connector.validate_connection()
    assert limited_validation["ok"] is False
    assert limited_validation["message"] == "Database query exceeded the configured 1-row limit."


def test_database_connector_ingest_endpoint_updates_health(tmp_path) -> None:
    database_url, _ = create_telemetry_database(tmp_path)
    client = build_client(tmp_path / "runtime")

    response = client.post(
        "/api/connectors/database/ingest",
        json={
            "database_url": database_url,
            "query": "SELECT timestamp, room, temperature, humidity FROM telemetry ORDER BY timestamp",
            "source_id": "customer-db",
            "system_id": "facility-db",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["connector_type"] == "database"
    assert payload["records_ingested"] == 4
    assert payload["sensors_detected"] == 2
    assert payload["masked_configuration"]["database"]["driver"] == "sqlite"
    assert database_url not in response.text

    health = client.get("/api/connectors/health")
    database_status = next(
        item for item in health.json()["connectors"] if item["connector_type"] == "database"
    )
    assert database_status["functional"] is True
    assert database_status["connection_status"] == "ready"
    assert database_status["records_ingested"] == 4


def test_database_connector_generic_test_rejects_invalid_configuration(tmp_path) -> None:
    client = build_client(tmp_path)

    response = client.post(
        "/api/connectors/test",
        json={
            "connector_type": "database",
            "config": {
                "database_url": "postgresql://operator:secret@localhost:not-a-port/telemetry",
                "query": "SELECT * FROM telemetry",
                "max_rows": "invalid",
            },
        },
    )

    assert response.status_code == 400
    assert "max_rows must be an integer" in response.json()["detail"]
    assert "secret" not in response.text
