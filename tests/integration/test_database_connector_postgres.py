from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
import pytest
from fastapi.testclient import TestClient

from app.connectors.database_connector import DatabaseConnector
from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_databases() -> Iterator[dict[str, str]]:
    admin_dsn = os.environ.get("NERAIUM_TEST_POSTGRES_DSN", "").strip()
    if not admin_dsn:
        pytest.fail("NERAIUM_TEST_POSTGRES_DSN is required for PostgreSQL integration tests.")

    parsed = urlsplit(admin_dsn)
    reader_dsn = (
        f"postgresql://neraium_reader:reader-password@{parsed.hostname}:{parsed.port}"
        f"{parsed.path or '/neraium'}"
    )
    with psycopg.connect(admin_dsn, sslmode="require", autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE ROLE neraium_reader LOGIN PASSWORD 'reader-password'")
            cursor.execute("CREATE SCHEMA telemetry AUTHORIZATION CURRENT_USER")
            cursor.execute("CREATE SCHEMA private AUTHORIZATION CURRENT_USER")
            cursor.execute(
                "CREATE TABLE telemetry.approved_readings "
                "(observed_at timestamptz NOT NULL, value double precision NOT NULL)"
            )
            cursor.execute(
                "INSERT INTO telemetry.approved_readings VALUES "
                "('2026-05-01T08:00:00Z', 1.0), "
                "('2026-05-01T08:05:00Z', 2.0), "
                "('2026-05-01T08:10:00Z', 3.0)"
            )
            cursor.execute("CREATE TABLE private.customer_secrets (secret text NOT NULL)")
            cursor.execute("INSERT INTO private.customer_secrets VALUES ('must-not-be-readable')")
            cursor.execute("REVOKE ALL ON SCHEMA telemetry, private FROM PUBLIC")
            cursor.execute("REVOKE ALL ON ALL TABLES IN SCHEMA telemetry, private FROM PUBLIC")
            cursor.execute("GRANT CONNECT ON DATABASE neraium TO neraium_reader")
            cursor.execute("GRANT USAGE ON SCHEMA telemetry TO neraium_reader")
            cursor.execute("GRANT SELECT ON telemetry.approved_readings TO neraium_reader")

    yield {"admin": admin_dsn, "reader": reader_dsn}


def connector_config(dsn: str, query: str, **overrides) -> dict:
    return {
        "database_url": dsn,
        "query": query,
        "source_id": "postgres-integration",
        "system_id": "postgres-system",
        "sslmode": "require",
        **overrides,
    }


def test_real_tls_connection_and_parameterized_values(postgres_databases) -> None:
    connector = DatabaseConnector(
        connector_config(
            postgres_databases["reader"],
            "SELECT observed_at AS timestamp, value FROM telemetry.approved_readings "
            "WHERE value > %s ORDER BY value",
            parameters=[1.0],
        )
    )

    assert connector.validate_connection() == {
        "ok": True,
        "message": "Database query validated with 2 rows.",
    }
    rows = connector.fetch_historical()
    assert [row["value"] for row in rows] == [2.0, 3.0]

    tls_connector = DatabaseConnector(
        connector_config(
            postgres_databases["reader"],
            "SELECT NOW() AS timestamp, CASE WHEN ssl THEN 1 ELSE 0 END AS tls_active "
            "FROM pg_stat_ssl WHERE pid = pg_backend_pid()",
        )
    )
    assert tls_connector.fetch_historical()[0]["tls_active"] == 1


def test_tls_verification_failure_is_sanitized(postgres_databases) -> None:
    connector = DatabaseConnector(
        connector_config(
            postgres_databases["reader"],
            "SELECT observed_at AS timestamp, value FROM telemetry.approved_readings",
            sslmode="verify-full",
        )
    )

    validation = connector.validate_connection()
    assert validation == {
        "ok": False,
        "message": "Database connection or query failed. Check the URL, credentials, and read-only query.",
    }
    assert "reader-password" not in str(validation)


def test_read_only_session_rejects_data_modifying_cte(postgres_databases) -> None:
    connector = DatabaseConnector(
        connector_config(
            postgres_databases["reader"],
            "WITH changed AS (DELETE FROM telemetry.approved_readings "
            "RETURNING observed_at AS timestamp, value) SELECT * FROM changed",
        )
    )

    assert connector.validate_connection()["ok"] is False
    with psycopg.connect(postgres_databases["admin"], sslmode="require") as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM telemetry.approved_readings")
            assert cursor.fetchone()[0] == 3


def test_direct_write_and_multi_statement_are_rejected_before_execution(postgres_databases) -> None:
    direct_write = DatabaseConnector(
        connector_config(postgres_databases["reader"], "DELETE FROM telemetry.approved_readings")
    )
    assert direct_write.validate_connection() == {
        "ok": False,
        "message": "Database connector only accepts SELECT or WITH queries.",
    }

    multiple = DatabaseConnector(
        connector_config(
            postgres_databases["reader"],
            "SELECT observed_at AS timestamp, value FROM telemetry.approved_readings; "
            "DELETE FROM telemetry.approved_readings",
        )
    )
    assert multiple.validate_connection() == {
        "ok": False,
        "message": "Database connector accepts exactly one read-only query.",
    }


def test_statement_timeout_cancels_real_postgres_query(postgres_databases) -> None:
    connector = DatabaseConnector(
        connector_config(
            postgres_databases["reader"],
            "SELECT NOW() AS timestamp, 1 AS value FROM pg_sleep(2)",
            query_timeout_seconds=1,
        )
    )

    assert connector.validate_connection() == {
        "ok": False,
        "message": "Database query exceeded the configured 1-second timeout.",
    }


def test_live_row_cap_rejects_more_than_configured_limit(postgres_databases) -> None:
    connector = DatabaseConnector(
        connector_config(
            postgres_databases["reader"],
            "SELECT NOW() AS timestamp, value FROM generate_series(1, 1000) AS value",
            max_rows=2,
        )
    )

    assert connector.validate_connection() == {
        "ok": False,
        "message": "Database query exceeded the configured 2-row limit.",
    }
    assert connector._bounded_query("SELECT 1", 2).endswith("LIMIT 3")


def test_least_privilege_role_cannot_access_unapproved_schema(postgres_databases) -> None:
    approved = DatabaseConnector(
        connector_config(
            postgres_databases["reader"],
            "SELECT observed_at AS timestamp, value FROM telemetry.approved_readings ORDER BY value",
        )
    )
    assert len(approved.fetch_historical()) == 3

    forbidden = DatabaseConnector(
        connector_config(
            postgres_databases["reader"],
            "SELECT NOW() AS timestamp, secret FROM private.customer_secrets",
        )
    )
    validation = forbidden.validate_connection()
    assert validation["ok"] is False
    assert "private" not in validation["message"]
    assert "customer_secrets" not in validation["message"]

    with psycopg.connect(postgres_databases["admin"], sslmode="require") as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT has_schema_privilege('neraium_reader', 'private', 'USAGE')")
            assert cursor.fetchone()[0] is False


def test_sanitized_failure_persists_offline_health(postgres_databases, tmp_path: Path) -> None:
    settings = Settings(
        app_env="development",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://localhost:5173"],
        runtime_dir=tmp_path,
    )
    client = TestClient(create_app(settings))
    response = client.post(
        "/api/connectors/database/ingest",
        json=connector_config(
            postgres_databases["reader"],
            "SELECT NOW() AS timestamp, secret FROM private.customer_secrets",
        ),
    )

    assert response.status_code == 400
    assert "reader-password" not in response.text
    assert "customer_secrets" not in response.text

    health_response = client.get("/api/connectors/health")
    database_health = next(
        item for item in health_response.json()["connectors"] if item["connector_type"] == "database"
    )
    assert database_health["connection_status"] == "offline"
    assert database_health["errors"] == [
        "Database connection or query failed. Check the URL, credentials, and read-only query."
    ]
    assert "reader-password" not in health_response.text
