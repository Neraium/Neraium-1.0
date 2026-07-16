from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.connectors import database_connector as database_connector_module
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


def test_database_connector_parameterizes_values_and_rejects_multiple_statements(tmp_path) -> None:
    database_url, _ = create_telemetry_database(tmp_path)
    connector = DatabaseConnector(
        {
            "database_url": database_url,
            "query": "SELECT timestamp, temperature FROM telemetry WHERE temperature > ?",
            "parameters": [75.5],
        }
    )

    rows = connector.fetch_historical()
    assert rows == [{"timestamp": "2026-05-01T08:05:00Z", "temperature": 75.7}]

    connector.config["query"] = "SELECT * FROM telemetry; DELETE FROM telemetry"
    validation = connector.validate_connection()
    assert validation == {
        "ok": False,
        "message": "Database connector accepts exactly one read-only query.",
    }


def test_database_connector_blocks_sqlite_catalog_and_write_cte(tmp_path) -> None:
    database_url, database_path = create_telemetry_database(tmp_path)

    catalog_connector = DatabaseConnector(
        {"database_url": database_url, "query": "SELECT name FROM sqlite_master"}
    )
    assert catalog_connector.validate_connection() == {
        "ok": False,
        "message": "Database connection or query failed. Check the file, parameters, and read-only query.",
    }

    cte_connector = DatabaseConnector(
        {
            "database_url": database_url,
            "query": "WITH selected AS (SELECT 1) DELETE FROM telemetry",
        }
    )
    assert cte_connector.validate_connection()["ok"] is False
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM telemetry").fetchone()[0] == 2


def test_database_connector_interrupts_expired_sqlite_query(monkeypatch, tmp_path) -> None:
    database_url, _ = create_telemetry_database(tmp_path)
    clock_reads = 0

    def monotonic() -> float:
        nonlocal clock_reads
        clock_reads += 1
        return 0.0 if clock_reads == 1 else 2.0

    monkeypatch.setattr(database_connector_module.time, "monotonic", monotonic)
    connector = DatabaseConnector(
        {
            "database_url": database_url,
            "query": (
                "WITH RECURSIVE counter(value) AS "
                "(SELECT 1 UNION ALL SELECT value + 1 FROM counter WHERE value < 1000000) "
                "SELECT value AS timestamp FROM counter"
            ),
            "query_timeout_seconds": 1,
        }
    )

    validation = connector.validate_connection()
    assert validation == {
        "ok": False,
        "message": "Database query exceeded the configured 1-second timeout.",
    }


def test_database_connector_configures_postgres_read_only_timeout_and_row_cap(monkeypatch) -> None:
    class FakeCursor:
        description = [("timestamp",), ("temperature",)]

        def __init__(self) -> None:
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, parameters=None) -> None:
            self.calls.append((query, parameters))

        def fetchmany(self, size):
            assert size == 3
            return [("2026-05-01T08:00:00Z", 75.5)]

    class FakeConnection:
        def __init__(self, cursor) -> None:
            self._cursor = cursor

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def cursor(self):
            return self._cursor

    cursor = FakeCursor()
    connect_calls = []

    def connect(database_url, **kwargs):
        connect_calls.append((database_url, kwargs))
        return FakeConnection(cursor)

    monkeypatch.setattr(database_connector_module.psycopg, "connect", connect)
    connector = DatabaseConnector(
        {
            "database_url": "postgresql://operator:secret@db.example/telemetry",
            "query": "SELECT timestamp, temperature FROM approved.telemetry WHERE temperature > %s",
            "parameters": [70],
            "max_rows": 2,
            "query_timeout_seconds": 7,
        }
    )

    rows = connector.fetch_historical()

    assert rows == [{"timestamp": "2026-05-01T08:00:00Z", "temperature": 75.5}]
    assert connect_calls == [
        (
            "postgresql://operator:secret@db.example/telemetry",
            {"connect_timeout": 7, "sslmode": "require"},
        )
    ]
    assert cursor.calls[0] == ("SET TRANSACTION READ ONLY", None)
    assert cursor.calls[1] == (
        "SELECT set_config('statement_timeout', %s, true)",
        ("7000ms",),
    )
    assert cursor.calls[2] == (
        "SELECT * FROM (SELECT timestamp, temperature FROM approved.telemetry WHERE temperature > %s) "
        "AS neraium_telemetry_query LIMIT 3",
        [70],
    )


def test_database_connector_failure_updates_sanitized_health(tmp_path) -> None:
    database_url, _ = create_telemetry_database(tmp_path)
    client = build_client(tmp_path / "runtime")

    response = client.post(
        "/api/connectors/database/ingest",
        json={
            "database_url": database_url,
            "query": "SELECT timestamp FROM private_customer_table",
        },
    )

    assert response.status_code == 400
    assert "private_customer_table" not in response.text
    health_response = client.get("/api/connectors/health")
    database_health = next(
        item for item in health_response.json()["connectors"] if item["connector_type"] == "database"
    )
    assert database_health["connection_status"] == "offline"
    assert database_health["errors"] == [
        "Database connection or query failed. Check the file, parameters, and read-only query."
    ]
    assert database_url not in health_response.text


def test_database_connector_rejects_insecure_postgres_transport() -> None:
    connector = DatabaseConnector(
        {
            "database_url": "postgresql://operator:secret@db.example/telemetry",
            "query": "SELECT timestamp FROM telemetry",
            "sslmode": "disable",
        }
    )

    validation = connector.validate_connection()
    assert validation == {
        "ok": False,
        "message": "sslmode must be require, verify-ca, or verify-full.",
    }
    health = connector.health_check()
    assert health.masked_configuration["sslmode"] == "invalid"
    assert "secret" not in health.model_dump_json()
