from __future__ import annotations

import httpx
import pytest

from app.services import data_connections, evidence_store, runtime_db, upload_jobs


def telemetry_payload(timestamp: str, *, tick: int = 1) -> dict:
    return {
        "source_id": "rest-test",
        "source_type": "external_rest_api",
        "facility_id": "facility-1",
        "room_id": "flower-room-1",
        "scenario": "airflow_drift",
        "tick": tick,
        "timestamp": timestamp,
        "readings": [
            {
                "timestamp": timestamp,
                "sensor_id": "temp-1",
                "sensor_name": "temperature",
                "value": 75.2 + tick,
                "unit": "F",
                "quality": "good",
            },
            {
                "timestamp": timestamp,
                "sensor_id": "humidity-1",
                "sensor_name": "humidity",
                "value": 58.0,
                "unit": "%",
                "quality": "good",
            },
        ],
    }


@pytest.fixture()
def isolated_runtime(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir(exist_ok=True)

    monkeypatch.setattr(runtime_db, "RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(runtime_db, "DB_PATH", runtime_dir / "runtime.db")

    monkeypatch.setattr(upload_jobs, "RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(upload_jobs, "UPLOAD_DIR", runtime_dir / "uploads")
    monkeypatch.setattr(upload_jobs, "JOB_DIR", runtime_dir / "upload_jobs")
    monkeypatch.setattr(upload_jobs, "LEGACY_JOB_DIR", runtime_dir / "jobs")

    monkeypatch.setattr(evidence_store, "RUNTIME_DIR", runtime_dir)
    monkeypatch.setattr(evidence_store, "EVIDENCE_DIR", runtime_dir / "evidence")
    monkeypatch.setattr(evidence_store, "EVIDENCE_RUNS_PATH", runtime_dir / "evidence" / "runs.json")

    runtime_db.init_runtime_db()
    connection = data_connections.upsert_registered_data_connection(
        {
            "connection_id": data_connections.DEFAULT_CONNECTION_ID,
            "name": data_connections.DEFAULT_CONNECTION_NAME,
            "url": "https://telemetry.example.test/latest",
            "source_type": "external_rest_api",
            "facility_id": "facility-1",
            "room_id": "flower-room-1",
            "polling_enabled": False,
            "baseline_samples_required": 6,
        }
    )
    return connection


def mock_transport(payloads: list[dict]) -> httpx.MockTransport:
    remaining = list(payloads)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = remaining.pop(0)
        return httpx.Response(200, json=payload)

    return httpx.MockTransport(handler)


def test_result_from_connection_batch_uses_focused_live_upload_adapter(monkeypatch):
    calls: list[dict] = []

    def fake_build_live_upload_result(*, columns=None, rows=None, filename="telemetry.csv", **kwargs):
        delegated_rows = rows or kwargs.get("data_rows") or []
        calls.append({
            "columns": list(columns or []),
            "rows": list(delegated_rows),
            "filename": filename,
            "kwargs": dict(kwargs),
        })
        return {
            "processing_stats": {},
            "sii_intelligence": {},
        }

    monkeypatch.setattr(data_connections, "build_live_upload_result", fake_build_live_upload_result)

    connection = {
        "name": "Live Telemetry Intake",
        "url": "https://telemetry.example.test/latest",
        "source_type": "external_rest_api",
        "connection_id": "rest-telemetry-intake",
    }
    metadata = {
        "readings_received": 2,
        "readings_accepted": 2,
        "readings_rejected": 0,
        "sensors_detected": 2,
        "scenario": "airflow_drift",
        "tick": 4,
    }
    baseline_state = {
        "baseline_source": "live_rest",
        "baseline_status": "building",
        "samples_collected": 1,
        "samples_required": 6,
        "last_baseline_update": "2026-05-10T12:00:00Z",
    }

    result = data_connections.result_from_connection_batch(
        connection,
        [
            {"timestamp": "2026-05-10T12:00:00Z", "room_id": "flower-room-1", "facility_id": "facility-1", "sensor_name": "temperature", "value": 75.0},
            {"timestamp": "2026-05-10T12:00:00Z", "room_id": "flower-room-1", "facility_id": "facility-1", "sensor_name": "humidity", "value": 58.0},
        ],
        metadata,
        baseline_state=baseline_state,
    )

    assert len(calls) == 1
    assert calls[0]["filename"] == "Live Telemetry Intake"
    assert calls[0]["columns"][:3] == ["timestamp", "room", "facility_id"]
    assert calls[0]["rows"]
    assert result["source_name"] == "Live Telemetry Intake"
    assert result["source_type"] == "external_rest_api"


def test_reset_all_data_connections_clears_runtime_tables_without_upload_jobs_reset(monkeypatch, isolated_runtime):
    called = {"reset": 0, "clear": 0}

    monkeypatch.setattr(data_connections, "reset_upload_state", lambda: called.__setitem__("reset", called["reset"] + 1))
    monkeypatch.setattr(data_connections, "clear_upload_runtime_tables", lambda: called.__setitem__("clear", called["clear"] + 1))

    payload = data_connections.reset_all_data_connections()

    assert isinstance(payload, list)
    assert called == {"reset": 1, "clear": 1}


def test_successful_poll_persists_telemetry_and_increments_baseline(isolated_runtime):
    transport = mock_transport(
        [
            telemetry_payload("2026-05-10T12:00:00Z", tick=1),
            telemetry_payload("2026-05-10T12:01:00Z", tick=2),
        ]
    )

    first_result = data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID, transport=transport)
    first_connection = first_result["connection"]

    assert first_connection["status"] == "polling"
    assert first_connection["error_message"] == ""
    assert first_connection["readings_accepted"] == 2
    assert first_connection["baseline_status"] == "building"
    assert first_connection["baseline_samples_collected"] == 1
    assert len(data_connections.read_connection_buffer(data_connections.DEFAULT_CONNECTION_ID)) == 2
    assert len(data_connections.read_recent_records(data_connections.DEFAULT_CONNECTION_ID)) == 2

    second_result = data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID, transport=transport)
    second_connection = second_result["connection"]

    assert second_connection["baseline_status"] == "building"
    assert second_connection["baseline_samples_collected"] == 2
    assert len(data_connections.read_recent_records(data_connections.DEFAULT_CONNECTION_ID)) == 4


def test_baseline_failure_keeps_successful_telemetry_state(isolated_runtime, monkeypatch):
    transport = mock_transport([telemetry_payload("2026-05-10T13:00:00Z", tick=1)])

    def fail_baseline_append(connection_id, records):
        raise RuntimeError("baseline append exploded")

    monkeypatch.setattr(data_connections, "append_baseline_records", fail_baseline_append)

    result = data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID, transport=transport)
    connection = result["connection"]

    assert result["baseline_error"] == "baseline append exploded"
    assert "error" not in result
    assert connection["status"] == "polling"
    assert connection["error_message"] == ""
    assert connection["readings_accepted"] == 2
    assert connection["baseline_status"] == "building"
    assert connection["baseline_error_message"] == "baseline append exploded"
    assert len(data_connections.read_connection_buffer(data_connections.DEFAULT_CONNECTION_ID)) == 2
    assert len(data_connections.read_recent_records(data_connections.DEFAULT_CONNECTION_ID)) == 2


def test_health_update_recovers_baseline_from_buffer_when_state_missing(isolated_runtime):
    transport = mock_transport([telemetry_payload("2026-05-10T14:00:00Z", tick=7)])
    result = data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID, transport=transport)
    connection = result["connection"]
    connection_id = connection["connection_id"]

    runtime_db.upsert_latest_payload(data_connections.baseline_state_key(connection_id), [])
    runtime_db.upsert_latest_payload(data_connections.baseline_records_key(connection_id), [])
    runtime_db.upsert_latest_payload(data_connections.recent_records_key(connection_id), [])

    recovered = data_connections.update_connection_health_fields(
        connection,
        {
            "timestamp": "2026-05-10T14:00:00Z",
            "scenario": "airflow_drift",
            "tick": 7,
            "readings_received": 2,
            "readings_accepted": 2,
            "readings_rejected": 0,
            "sensors_detected": 2,
        },
        status="polling",
        baseline_state=None,
    )

    assert recovered["baseline_source"] == "live_rest"
    assert recovered["baseline_status"] in {"building", "active"}
    assert recovered["baseline_samples_collected"] > 0
    assert len(data_connections.read_baseline_records(connection_id)) > 0
    assert len(data_connections.read_recent_records(connection_id)) > 0


def test_reset_baseline_starts_clean_and_rebuilds_on_next_poll(isolated_runtime):
    transport = mock_transport(
        [
            telemetry_payload("2026-05-10T15:00:00Z", tick=1),
            telemetry_payload("2026-05-10T15:01:00Z", tick=2),
            telemetry_payload("2026-05-10T15:02:00Z", tick=3),
        ]
    )
    first = data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID, transport=transport)
    assert first["connection"]["baseline_samples_collected"] == 1
    second = data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID, transport=transport)
    assert second["connection"]["baseline_samples_collected"] == 2

    rebuilt = data_connections.reset_connection_live_baseline(data_connections.DEFAULT_CONNECTION_ID)
    assert rebuilt["baseline_source"] == "live_rest"
    assert rebuilt["baseline_status"] == "building"
    assert rebuilt["baseline_samples_collected"] == 0
    assert len(data_connections.read_baseline_records(data_connections.DEFAULT_CONNECTION_ID)) == 0
    assert len(data_connections.read_recent_records(data_connections.DEFAULT_CONNECTION_ID)) == 0

    rebuilt_poll = data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID, transport=transport)
    assert rebuilt_poll["connection"]["baseline_status"] == "building"
    assert rebuilt_poll["connection"]["baseline_samples_collected"] == 1


def test_timeout_error_clears_after_next_successful_poll(isolated_runtime, monkeypatch):
    warmup_transport = mock_transport([telemetry_payload("2026-05-10T16:00:00Z", tick=4)])
    data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID, transport=warmup_transport)
    data_connections.reset_connection_live_baseline(data_connections.DEFAULT_CONNECTION_ID)

    def raise_timeout(connection, transport=None):
        raise httpx.ReadTimeout("read timed out")

    monkeypatch.setattr(data_connections, "fetch_connection_payload", raise_timeout)
    timed_out = data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID)
    assert "timed out" in timed_out["error"].lower()
    assert timed_out["connection"]["status"] == "error"
    assert timed_out["connection"]["error_message"]

    monkeypatch.setattr(
        data_connections,
        "fetch_connection_payload",
        lambda connection, transport=None: telemetry_payload("2026-05-10T16:01:00Z", tick=5),
    )
    recovered = data_connections.poll_data_connection_once(data_connections.DEFAULT_CONNECTION_ID)
    assert recovered["connection"]["status"] == "polling"
    assert recovered["connection"]["error_message"] == ""
    assert recovered["connection"]["baseline_status"] == "building"
    assert recovered["connection"]["baseline_samples_collected"] == 1


def test_upsert_registered_data_connection_clears_stale_errors_when_recovered(isolated_runtime):
    normalized = data_connections.upsert_registered_data_connection(
        {
            "connection_id": data_connections.DEFAULT_CONNECTION_ID,
            "status": "polling",
            "error_message": "timed out",
            "baseline_status": "active",
            "baseline_error_message": "timed out",
        }
    )

    assert normalized["status"] == "polling"
    assert normalized["error_message"] == ""
    assert normalized["baseline_status"] == "active"
    assert normalized["baseline_error_message"] == ""
