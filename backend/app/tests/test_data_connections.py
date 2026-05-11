from __future__ import annotations

import httpx
import pytest

from app.services import data_connections, evidence_store, runtime_db, upload_jobs


def telemetry_payload(timestamp: str, *, tick: int = 1) -> dict:
    return {
        "source_id": "node-red-test",
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
    runtime_dir.mkdir()

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
            "url": "https://node-red.test/telemetry/latest",
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
