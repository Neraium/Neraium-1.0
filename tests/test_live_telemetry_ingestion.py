from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.live_telemetry import (
    list_ingestion_health,
    list_normalized_telemetry,
    list_rejected_telemetry,
)


SYSTEM_ID = "resort-chilled-water"
SOURCE = "historian-rest"


def _timestamp(offset_seconds: int = -10) -> str:
    return (datetime.now(UTC) + timedelta(seconds=offset_seconds)).replace(microsecond=0).isoformat()


def _mapping_payload(
    source_tag: str = "CHWP-1-KW",
    canonical_signal: str = "pump_power",
) -> dict[str, object]:
    return {
        "system_id": SYSTEM_ID,
        "source_tag": source_tag,
        "canonical_signal": canonical_signal,
        "unit": "kW",
        "enabled": True,
    }


def _create_mapping(
    client: TestClient,
    source_tag: str = "CHWP-1-KW",
    canonical_signal: str = "pump_power",
) -> dict[str, object]:
    response = client.post(
        "/api/telemetry/signal-mappings",
        json=_mapping_payload(source_tag, canonical_signal),
    )
    assert response.status_code == 201
    return response.json()


def _ingestion_payload(
    *,
    readings: list[dict[str, object]],
    batch_id: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "system_id": SYSTEM_ID,
        "source": SOURCE,
        "readings": readings,
    }
    if batch_id:
        payload["batch_id"] = batch_id
    return payload


def test_mapping_crud_and_disable_follow_existing_auth_api_patterns(client: TestClient) -> None:
    mapping = _create_mapping(client)
    mapping_id = str(mapping["mapping_id"])
    assert mapping["created_at"] == mapping["updated_at"]

    listed = client.get(
        "/api/telemetry/signal-mappings",
        params={"system_id": SYSTEM_ID},
    )
    assert listed.status_code == 200
    assert listed.json()["mappings"] == [mapping]

    updated = client.put(
        f"/api/telemetry/signal-mappings/{mapping_id}",
        json={"canonical_signal": "pump_input_power", "unit": "W"},
    )
    assert updated.status_code == 200
    assert updated.json()["canonical_signal"] == "pump_input_power"
    assert updated.json()["unit"] == "W"

    duplicate = client.post(
        "/api/telemetry/signal-mappings",
        json=_mapping_payload(),
    )
    assert duplicate.status_code == 409

    disabled = client.post(
        f"/api/telemetry/signal-mappings/{mapping_id}/disable"
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert client.get(
        "/api/telemetry/signal-mappings",
        params={"system_id": SYSTEM_ID},
    ).json()["mappings"] == []
    assert client.get(
        "/api/telemetry/signal-mappings",
        params={"system_id": SYSTEM_ID, "include_disabled": True},
    ).json()["mappings"][0]["mapping_id"] == mapping_id


def test_valid_batch_supports_multiple_timestamps_and_persists_normalized_values(
    client: TestClient,
) -> None:
    _create_mapping(client, "CHWP-1-KW", "pump_power")
    _create_mapping(client, "FLOW-101", "flow")
    first = _timestamp(-30)
    second = _timestamp(-20)

    response = client.post(
        "/api/telemetry/ingest",
        json=_ingestion_payload(
            readings=[
                {"timestamp": first, "signals": {"CHWP-1-KW": 42.8, "FLOW-101": 1185}},
                {"timestamp": second, "signals": {"CHWP-1-KW": "43.1", "FLOW-101": 1192}},
            ],
        ),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["accepted_reading_count"] == 2
    assert result["rejected_reading_count"] == 0
    assert result["accepted_signal_value_count"] == 4
    assert result["rejected_signal_value_count"] == 0
    assert result["warnings"] == []
    assert datetime.fromisoformat(result["processing_timestamp"]).utcoffset() is not None

    rows = list_normalized_telemetry(batch_id=result["batch_id"])
    assert [(row["canonical_signal"], row["value"]) for row in rows] == [
        ("pump_power", 42.8),
        ("flow", 1185.0),
        ("pump_power", 43.1),
        ("flow", 1192.0),
    ]
    assert {row["quality_status"] for row in rows} == {"good"}
    assert {row["source_tag"] for row in rows} == {"CHWP-1-KW", "FLOW-101"}
    assert {row["source"] for row in rows} == {SOURCE}

    health = client.get(
        "/api/telemetry/ingestion-health",
        params={"system_id": SYSTEM_ID, "source": SOURCE},
    )
    assert health.status_code == 200
    state = health.json()["health"][0]
    assert state["status"] == "healthy"
    assert state["accepted_count"] == 4
    assert state["rejected_count"] == 0
    assert state["last_successful_ingestion_at"] == result["processing_timestamp"]
    assert state["last_telemetry_timestamp"] == second


def test_timestamp_failures_are_quarantined_with_durable_reasons(
    client: TestClient,
) -> None:
    _create_mapping(client)
    future = _timestamp(601)
    response = client.post(
        "/api/telemetry/ingest",
        json=_ingestion_payload(
            readings=[
                {"signals": {"CHWP-1-KW": 1}},
                {"timestamp": "2026-08-01T17:00:00", "signals": {"CHWP-1-KW": 2}},
                {"timestamp": future, "signals": {"CHWP-1-KW": 3}},
            ]
        ),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["accepted_reading_count"] == 0
    assert result["rejected_reading_count"] == 3
    assert result["accepted_signal_value_count"] == 0
    assert result["rejected_signal_value_count"] == 3
    assert result["warnings"] == [
        "future_timestamp",
        "invalid_timestamp",
        "missing_timestamp",
    ]
    rejected = list_rejected_telemetry(batch_id=result["batch_id"])
    assert [item["rejection_reason"] for item in rejected] == [
        "missing_timestamp",
        "invalid_timestamp",
        "future_timestamp",
    ]
    assert rejected[0]["telemetry_timestamp"] is None
    assert rejected[1]["telemetry_timestamp"] == "2026-08-01T17:00:00"
    assert list_normalized_telemetry(batch_id=result["batch_id"]) == []


def test_values_are_validated_without_treating_booleans_as_numbers(
    client: TestClient,
) -> None:
    _create_mapping(client)
    timestamp = _timestamp()
    payload = _ingestion_payload(
        readings=[
            {
                "timestamp": timestamp,
                "signals": {
                    "CHWP-1-KW": "42.75",
                    "UNKNOWN": 4.2,
                },
            },
            {"timestamp": _timestamp(-9), "signals": {"CHWP-1-KW": True}},
            {"timestamp": _timestamp(-8), "signals": {"CHWP-1-KW": None}},
            {"timestamp": _timestamp(-7), "signals": {"CHWP-1-KW": "not-a-number"}},
        ]
    )
    response = client.post("/api/telemetry/ingest", json=payload)

    assert response.status_code == 200
    result = response.json()
    assert result["accepted_reading_count"] == 1
    assert result["rejected_reading_count"] == 3
    assert result["accepted_signal_value_count"] == 1
    assert result["rejected_signal_value_count"] == 4
    assert set(result["warnings"]) == {"non_numeric_value", "unmapped_signal"}
    assert list_normalized_telemetry(batch_id=result["batch_id"])[0]["value"] == 42.75
    rejected = list_rejected_telemetry(batch_id=result["batch_id"])
    assert [item["rejection_reason"] for item in rejected].count("non_numeric_value") == 3
    assert any(item["rejection_reason"] == "unmapped_signal" for item in rejected)


def test_nan_and_infinity_are_quarantined(client: TestClient) -> None:
    _create_mapping(client)
    timestamp = _timestamp()
    raw_payload = (
        "{"
        f'"system_id":"{SYSTEM_ID}","source":"{SOURCE}","readings":['
        f'{{"timestamp":"{timestamp}","signals":{{"CHWP-1-KW":NaN}}}},'
        f'{{"timestamp":"{_timestamp(-9)}","signals":{{"CHWP-1-KW":Infinity}}}},'
        f'{{"timestamp":"{_timestamp(-8)}","signals":{{"CHWP-1-KW":-Infinity}}}}'
        "]}"
    )
    response = client.post(
        "/api/telemetry/ingest",
        content=raw_payload,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["accepted_signal_value_count"] == 0
    assert result["rejected_signal_value_count"] == 3
    assert result["warnings"] == ["infinite_value", "nan_value"]
    rejected = list_rejected_telemetry(batch_id=result["batch_id"])
    assert [item["rejection_reason"] for item in rejected] == [
        "nan_value",
        "infinite_value",
        "infinite_value",
    ]
    assert all(item["submitted_value"] is None for item in rejected)


def test_duplicate_batches_are_idempotent_and_new_duplicate_batches_are_recorded(
    client: TestClient,
) -> None:
    _create_mapping(client)
    timestamp = _timestamp()
    payload = _ingestion_payload(
        batch_id="customer-batch-001",
        readings=[{"timestamp": timestamp, "signals": {"CHWP-1-KW": 42.8}}],
    )

    first = client.post("/api/telemetry/ingest", json=payload)
    retry = client.post("/api/telemetry/ingest", json=payload)

    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert len(list_normalized_telemetry(system_id=SYSTEM_ID)) == 1
    assert list_rejected_telemetry(batch_id="customer-batch-001") == []

    duplicate = client.post(
        "/api/telemetry/ingest",
        json=_ingestion_payload(
            batch_id="customer-batch-002",
            readings=[{"timestamp": timestamp, "signals": {"CHWP-1-KW": 42.8}}],
        ),
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["accepted_signal_value_count"] == 0
    assert duplicate.json()["rejected_signal_value_count"] == 1
    assert duplicate.json()["warnings"] == ["duplicate_record"]
    assert list_rejected_telemetry(batch_id="customer-batch-002")[0]["rejection_reason"] == "duplicate_record"
    assert len(list_normalized_telemetry(system_id=SYSTEM_ID)) == 1


def test_mildly_late_data_is_marked_and_older_data_is_quarantined(
    client: TestClient,
) -> None:
    _create_mapping(client)
    newest = datetime.now(UTC).replace(microsecond=0) - timedelta(seconds=10)
    initial = client.post(
        "/api/telemetry/ingest",
        json=_ingestion_payload(
            readings=[{"timestamp": newest.isoformat(), "signals": {"CHWP-1-KW": 40}}],
        ),
    )
    assert initial.status_code == 200

    mild = client.post(
        "/api/telemetry/ingest",
        json=_ingestion_payload(
            readings=[
                {
                    "timestamp": (newest - timedelta(seconds=60)).isoformat(),
                    "signals": {"CHWP-1-KW": 39},
                }
            ],
        ),
    )
    assert mild.status_code == 200
    assert mild.json()["warnings"] == ["out_of_order_accepted"]
    mild_row = list_normalized_telemetry(batch_id=mild.json()["batch_id"])[0]
    assert mild_row["quality_status"] == "out_of_order"

    old = client.post(
        "/api/telemetry/ingest",
        json=_ingestion_payload(
            readings=[
                {
                    "timestamp": (newest - timedelta(seconds=301)).isoformat(),
                    "signals": {"CHWP-1-KW": 38},
                }
            ],
        ),
    )
    assert old.status_code == 200
    assert old.json()["warnings"] == ["out_of_order_record"]
    assert list_normalized_telemetry(batch_id=old.json()["batch_id"]) == []
    assert list_rejected_telemetry(batch_id=old.json()["batch_id"])[0]["rejection_reason"] == "out_of_order_record"


def test_disabled_mapping_quarantines_values_as_unmapped(client: TestClient) -> None:
    mapping = _create_mapping(client)
    client.post(f"/api/telemetry/signal-mappings/{mapping['mapping_id']}/disable")

    response = client.post(
        "/api/telemetry/ingest",
        json=_ingestion_payload(
            readings=[{"timestamp": _timestamp(), "signals": {"CHWP-1-KW": 42.8}}],
        ),
    )

    assert response.status_code == 200
    assert response.json()["warnings"] == ["unmapped_signal"]
    rejected = list_rejected_telemetry(batch_id=response.json()["batch_id"])
    assert rejected[0]["source_tag"] == "CHWP-1-KW"
    assert rejected[0]["submitted_value"] == 42.8


def test_ingestion_health_reports_never_received_and_error_states(
    client: TestClient,
) -> None:
    never = client.get(
        "/api/telemetry/ingestion-health",
        params={"system_id": SYSTEM_ID, "source": SOURCE},
    )
    assert never.status_code == 200
    assert never.json()["health"][0]["status"] == "never_received"

    _create_mapping(client)
    rejected = client.post(
        "/api/telemetry/ingest",
        json=_ingestion_payload(
            readings=[{"timestamp": "invalid", "signals": {"CHWP-1-KW": 1}}],
        ),
    )
    assert rejected.status_code == 200
    state = list_ingestion_health(
        settings=client.app.state.settings,
        system_id=SYSTEM_ID,
        source=SOURCE,
    )[0]
    assert state["status"] == "error"
    assert state["accepted_count"] == 0
    assert state["rejected_count"] == 1
    assert state["latest_error_or_warning"] == "invalid_timestamp"


def test_stale_but_valid_initial_telemetry_sets_delayed_health(
    client: TestClient,
) -> None:
    _create_mapping(client)
    response = client.post(
        "/api/telemetry/ingest",
        json=_ingestion_payload(
            readings=[
                {
                    "timestamp": _timestamp(-901),
                    "signals": {"CHWP-1-KW": 42.8},
                }
            ],
        ),
    )
    assert response.status_code == 200
    state = client.get(
        "/api/telemetry/ingestion-health",
        params={"system_id": SYSTEM_ID, "source": SOURCE},
    ).json()["health"][0]
    assert state["status"] == "delayed"
    assert state["accepted_count"] == 1


def test_legacy_global_telemetry_endpoints_are_retired_after_authentication_in_production(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("NERAIUM_API_TOKEN", "telemetry-secret")
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    with TestClient(create_app(settings), base_url="https://testserver") as production_client:
        mapping = production_client.post(
            "/api/telemetry/signal-mappings",
            json=_mapping_payload(),
        )
        ingestion = production_client.post(
            "/api/telemetry/ingest",
            json=_ingestion_payload(
                readings=[{"timestamp": _timestamp(), "signals": {"CHWP-1-KW": 1}}]
            ),
        )
        assert mapping.status_code == ingestion.status_code == 401

        headers = {"Authorization": "Bearer telemetry-secret"}
        assert production_client.post(
            "/api/telemetry/signal-mappings",
            json=_mapping_payload(),
            headers=headers,
        ).status_code == 410
        assert production_client.post(
            "/api/telemetry/ingest",
            json=_ingestion_payload(
                readings=[{"timestamp": _timestamp(), "signals": {"CHWP-1-KW": 1}}]
            ),
            headers=headers,
        ).status_code == 410
        assert production_client.get(
            "/api/telemetry/signal-mappings",
            headers=headers,
        ).status_code == 410
        assert production_client.get(
            "/api/telemetry/ingestion-health",
            headers=headers,
        ).status_code == 410


def test_configurable_reading_signal_and_request_size_limits(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    settings = Settings(
        app_env="development",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://localhost:3010"],
        runtime_dir=tmp_path,
        telemetry_max_request_size_bytes=10_000,
        telemetry_max_readings_per_batch=1,
        telemetry_max_signals_per_reading=1,
    )
    with TestClient(create_app(settings)) as limited_client:
        _create_mapping(limited_client)
        too_many_readings = limited_client.post(
            "/api/telemetry/ingest",
            json=_ingestion_payload(
                readings=[
                    {"timestamp": _timestamp(-20), "signals": {"CHWP-1-KW": 1}},
                    {"timestamp": _timestamp(-10), "signals": {"CHWP-1-KW": 2}},
                ]
            ),
        )
        too_many_signals = limited_client.post(
            "/api/telemetry/ingest",
            json=_ingestion_payload(
                readings=[
                    {
                        "timestamp": _timestamp(),
                        "signals": {"CHWP-1-KW": 1, "OTHER": 2},
                    }
                ]
            ),
        )
        assert too_many_readings.status_code == 413
        assert too_many_signals.status_code == 413

    body_limited_settings = Settings(
        app_env="development",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://localhost:3010"],
        runtime_dir=tmp_path,
        telemetry_max_request_size_bytes=256,
    )
    with TestClient(create_app(body_limited_settings)) as body_limited_client:
        oversized_payload = _ingestion_payload(
            readings=[
                {
                    "timestamp": _timestamp(),
                    "signals": {"CHWP-1-KW": "9" * 400},
                }
            ]
        )
        response = body_limited_client.post(
            "/api/telemetry/ingest",
            content=json.dumps(oversized_payload),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 413
        assert response.json()["error_type"] == "payload_too_large"
