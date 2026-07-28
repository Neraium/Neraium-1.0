from __future__ import annotations

import json
from datetime import datetime, timedelta

import httpx
import pytest
from app.connectors.csv_connector import CSVConnector
from app.connectors.database_connector import SQLITE_URI_PREFIX, DatabaseConnector
from app.connectors.models import RestConnectorRequest
from app.connectors.rest_connector import RESTConnector
from pydantic import ValidationError


def test_csv_normalization_preserves_exact_result_structure_and_uses_aware_utc() -> None:
    connector = CSVConnector(
        {
            "filename": "room-readings.csv",
            "source_id": "customer-csv",
            "system_id": "facility-csv",
        }
    )

    batch = connector.normalize(
        [
            {
                "timestamp": "2026-05-01T08:00:00Z",
                "room": "Flower 1",
                "quality": "GOOD",
                "temperature": "75.2",
            }
        ]
    )
    result = batch.model_dump()

    assert result.keys() == {
        "connector_type",
        "source_id",
        "system_id",
        "records",
        "sensor_count",
        "record_count",
        "warnings",
        "errors",
        "duplicate_records_removed",
        "last_sync_time",
        "metadata",
    }
    assert result["records"] == [
        {
            "source_id": "customer-csv",
            "facility_id": None,
            "room_id": None,
            "system_id": "facility-csv",
            "sensor_id": "facility-csv-temperature",
            "sensor_name": "temperature",
            "value": 75.2,
            "unit": "F",
            "timestamp": "2026-05-01T08:00:00",
            "quality_status": "good",
            "metadata": {
                "row_number": 2,
                "filename": "room-readings.csv",
                "room": "Flower 1",
                "quality": "GOOD",
            },
        }
    ]
    assert result | {"metadata": None} == {
        "connector_type": "csv",
        "source_id": "customer-csv",
        "system_id": "facility-csv",
        "records": result["records"],
        "sensor_count": 1,
        "record_count": 1,
        "warnings": [],
        "errors": [],
        "duplicate_records_removed": 0,
        "last_sync_time": "2026-05-01T08:00:00",
        "metadata": None,
    }
    assert result["metadata"].keys() == {"filename", "timestamp_column", "ingested_at"}
    assert result["metadata"]["filename"] == "room-readings.csv"
    assert result["metadata"]["timestamp_column"] == "timestamp"

    ingested_at = datetime.fromisoformat(result["metadata"]["ingested_at"])
    assert ingested_at.tzinfo is not None
    assert ingested_at.utcoffset() == timedelta(0)
    assert batch.model_dump(mode="json")["metadata"]["ingested_at"] == result["metadata"]["ingested_at"]


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([], "CSV dataset is empty. Upload a file with timestamped telemetry rows."),
        (
            [{"recorded_when": "2026-05-01T08:00:00Z", "temperature": "75"}],
            "CSV dataset is missing a timestamp column. Add a column like timestamp or recorded_at.",
        ),
    ],
)
def test_csv_normalization_preserves_empty_and_missing_timestamp_errors(
    rows: list[dict[str, str]],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        CSVConnector().normalize(rows)


def test_csv_invalid_delimiter_preserves_validation_error() -> None:
    connector = CSVConnector(
        {
            "filename": "semicolon.csv",
            "content": "timestamp;temperature\n2026-05-01T08:00:00Z;74\n",
        }
    )

    assert connector.fetch_historical() == [
        {"timestamp;temperature": "2026-05-01T08:00:00Z;74"}
    ]
    with pytest.raises(
        ValueError,
        match="^No valid telemetry records were found after validation. Check timestamps, units, and sensor values.$",
    ):
        connector.normalize(connector.fetch_historical())


def test_csv_duplicate_columns_keep_dict_reader_last_value() -> None:
    connector = CSVConnector(
        {
            "filename": "duplicate.csv",
            "content": (
                "timestamp,temperature,temperature\n"
                "2026-05-01T08:00:00Z,74,75\n"
            ),
        }
    )

    rows = connector.fetch_historical()
    batch = connector.normalize(rows)

    assert rows == [{"timestamp": "2026-05-01T08:00:00Z", "temperature": "75"}]
    assert batch.record_count == 1
    assert batch.records[0].value == 75.0
    assert batch.warnings == []


def test_csv_invalid_values_missing_values_and_duplicates_keep_warning_contract() -> None:
    connector = CSVConnector({"filename": "quality.csv"})

    batch = connector.normalize(
        [
            {"timestamp": "2026-05-01T08:00:00Z", "temperature": "74", "humidity": ""},
            {"timestamp": "bad-time", "temperature": "75", "humidity": "50"},
            {"timestamp": "2026-05-01T08:10:00Z", "temperature": "bad", "humidity": "51"},
            {"timestamp": "2026-05-01T08:10:00Z", "temperature": "76", "humidity": "52"},
        ]
    )

    assert batch.record_count == 3
    assert batch.duplicate_records_removed == 1
    assert [issue.model_dump() for issue in batch.errors] == [
        {
            "row_number": 3,
            "field": "timestamp",
            "message": "Timestamp is missing or could not be parsed.",
        },
        {
            "row_number": 4,
            "field": "temperature",
            "message": "Sensor value for temperature must be numeric.",
        },
    ]
    assert batch.warnings == [
        "1 duplicate telemetry records were ignored.",
        "Row 3: Timestamp is missing or could not be parsed.",
        "Row 4: Sensor value for temperature must be numeric.",
    ]


def test_rest_post_preserves_headers_query_auth_body_and_timeout() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(
            method=request.method,
            url=str(request.url),
            headers=dict(request.headers),
            body=json.loads(request.content),
            timeout=request.extensions["timeout"],
        )
        return httpx.Response(
            200,
            json=[{"timestamp": "2026-05-01T08:00:00Z", "temperature": 75}],
        )

    connector = RESTConnector(
        {
            "endpoint": "https://telemetry.example.test/readings?site=north",
            "method": "POST",
            "headers": {"X-Tenant": "customer"},
            "token": "secret-token",
            "sample_payload": {"window": "latest"},
        },
        transport=httpx.MockTransport(handler),
    )

    assert connector.fetch_historical() == [
        {"timestamp": "2026-05-01T08:00:00Z", "temperature": 75}
    ]
    assert captured == {
        "method": "POST",
        "url": "https://telemetry.example.test/readings?site=north",
        "headers": {
            "host": "telemetry.example.test",
            "accept": "*/*",
            "accept-encoding": "gzip, deflate",
            "connection": "keep-alive",
            "user-agent": "python-httpx/0.28.1",
            "x-tenant": "customer",
            "authorization": "Bearer secret-token",
            "content-length": "19",
            "content-type": "application/json",
        },
        "body": {"window": "latest"},
        "timeout": {"connect": 10.0, "read": 10.0, "write": 10.0, "pool": 10.0},
    }


def test_rest_explicit_authorization_header_is_not_overridden() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Basic explicit-value"
        return httpx.Response(200, json=[{"timestamp": "2026-05-01", "temperature": 75}])

    connector = RESTConnector(
        {
            "endpoint": "https://telemetry.example.test/readings",
            "headers": {"Authorization": "Basic explicit-value"},
            "token": "unused-bearer-token",
        },
        transport=httpx.MockTransport(handler),
    )

    assert len(connector.fetch_historical()) == 1


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(503, text="unavailable"), "REST API returned status 503."),
        (httpx.Response(200, content=b"not-json"), "REST API response was not valid JSON."),
        (httpx.Response(200, json=[]), "REST API returned an empty dataset."),
        (
            httpx.Response(200, headers={"content-length": "invalid"}, content=b"[]"),
            "REST API returned an invalid Content-Length header.",
        ),
    ],
)
def test_rest_response_errors_preserve_messages(response: httpx.Response, message: str) -> None:
    connector = RESTConnector(
        {"endpoint": "https://telemetry.example.test/readings"},
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(ValueError, match=f"^{message}$"):
        connector.fetch_historical()


def test_rest_network_exception_preserves_sanitized_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("secret network detail", request=request)

    connector = RESTConnector(
        {"endpoint": "https://telemetry.example.test/readings"},
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(
        ValueError,
        match="^REST API could not be reached. Check the endpoint and network path.$",
    ):
        connector.fetch_historical()


def test_rest_valid_json_is_parsed_without_changing_content_type_behavior() -> None:
    connector = RESTConnector(
        {"endpoint": "https://telemetry.example.test/readings"},
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/plain"},
                json=[{"timestamp": "2026-05-01", "temperature": 75}],
            )
        ),
    )

    assert connector.fetch_historical() == [
        {"timestamp": "2026-05-01", "temperature": 75}
    ]


def test_rest_records_path_and_pagination_metadata_preserve_single_request_behavior() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            200,
            json={
                "payload": {
                    "readings": [{"timestamp": "2026-05-01", "temperature": 75}],
                },
                "next": "https://telemetry.example.test/readings?page=2",
            },
        )

    connector = RESTConnector(
        {
            "endpoint": "https://telemetry.example.test/readings?page=1",
            "records_path": "payload.readings",
        },
        transport=httpx.MockTransport(handler),
    )

    assert connector.fetch_historical() == [
        {"timestamp": "2026-05-01", "temperature": 75}
    ]
    assert request_count == 1


def test_rest_record_extraction_preserves_invalid_shape_errors_and_fallback_order() -> None:
    connector = RESTConnector({})

    with pytest.raises(ValueError, match="^REST API response list must contain objects.$"):
        connector._extract_records([{"timestamp": "2026-05-01"}, "invalid"])
    with pytest.raises(
        ValueError,
        match="^REST API response did not include records_path payload.readings.$",
    ):
        RESTConnector({"records_path": "payload.readings"})._extract_records({"payload": {}})

    assert connector._extract_records(
        {
            "records": ["invalid"],
            "data": [{"timestamp": "2026-05-01", "temperature": 75}],
        }
    ) == [{"timestamp": "2026-05-01", "temperature": 75}]


def test_rest_does_not_follow_redirects() -> None:
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(
            302,
            headers={"location": "https://redirected.example.test/readings"},
        )

    connector = RESTConnector(
        {"endpoint": "https://telemetry.example.test/readings"},
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValueError, match="^REST API returned status 302.$"):
        connector.fetch_historical()
    assert request_count == 1


def test_rest_normalization_preserves_exact_result_structure() -> None:
    connector = RESTConnector(
        {
            "endpoint": "https://telemetry.example.test/readings",
            "source_id": "customer-rest",
            "system_id": "facility-rest",
        }
    )

    result = connector.normalize(
        [
            {
                "timestamp": "2026-05-01T08:00:00Z",
                "zone": "north",
                "temperature": 75,
                "nested": {"ignored": True},
            }
        ]
    ).model_dump()

    assert result == {
        "connector_type": "rest",
        "source_id": "customer-rest",
        "system_id": "facility-rest",
        "records": [
            {
                "source_id": "customer-rest",
                "facility_id": None,
                "room_id": None,
                "system_id": "facility-rest",
                "sensor_id": "facility-rest-temperature",
                "sensor_name": "temperature",
                "value": 75.0,
                "unit": "F",
                "timestamp": "2026-05-01T08:00:00",
                "quality_status": "good",
                "metadata": {"row_number": 1, "zone": "north"},
            }
        ],
        "sensor_count": 1,
        "record_count": 1,
        "warnings": [],
        "errors": [],
        "duplicate_records_removed": 0,
        "last_sync_time": "2026-05-01T08:00:00",
        "metadata": {"endpoint": "https://telemetry.example.test/readings"},
    }


def test_rest_request_model_keeps_blocked_url_validation() -> None:
    with pytest.raises(ValidationError, match=r"HTTP\(S\) URL without embedded credentials"):
        RestConnectorRequest(endpoint="file:///etc/passwd")


def test_database_sqlite_prefix_preserves_file_memory_and_non_sqlite_behavior(tmp_path) -> None:
    database_path = tmp_path / "telemetry.db"
    database_path.touch()
    database_url = f"{SQLITE_URI_PREFIX}{database_path.as_posix()}"

    connector = DatabaseConnector({"database_url": database_url, "query": "SELECT 1"})
    assert connector._masked_database_configuration() == {
        "driver": "sqlite",
        "database": "telemetry.db",
    }

    memory_connector = DatabaseConnector(
        {"database_url": f"{SQLITE_URI_PREFIX}:memory:", "query": "SELECT 1"}
    )
    with pytest.raises(
        ValueError,
        match="^SQLite connector requires an existing database file.$",
    ):
        memory_connector.fetch_historical()

    unsupported_connector = DatabaseConnector(
        {"database_url": "mysql://db.example.test/telemetry", "query": "SELECT 1"}
    )
    with pytest.raises(
        ValueError,
        match="^Database URL must use a supported sqlite:/// or postgresql:// scheme.$",
    ):
        unsupported_connector.fetch_historical()
