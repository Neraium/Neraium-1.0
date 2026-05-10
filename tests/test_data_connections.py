from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

BASELINE_SAMPLE_COUNT = 6


def build_client(tmp_path) -> TestClient:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://localhost:3010"],
        cors_origin_regex=None,
        runtime_dir=tmp_path,
    )
    return TestClient(create_app(settings))


def payload_for(*, tick: int, timestamp: str, temperature: float, humidity: float, airflow: float, scenario: str = "airflow_drift") -> dict:
    return {
        "source_id": "node-red-sim-api-001",
        "source_type": "external_rest_api",
        "facility_id": "cultivation-facility-001",
        "room_id": "flower-room-1",
        "scenario": scenario,
        "tick": tick,
        "timestamp": timestamp,
        "readings": [
            {
                "timestamp": timestamp,
                "sensor_id": "temp-001",
                "sensor_name": "temperature",
                "value": temperature,
                "unit": "F",
                "quality": "good",
            },
            {
                "timestamp": timestamp,
                "sensor_id": "humidity-001",
                "sensor_name": "humidity",
                "value": humidity,
                "unit": "%",
                "quality": "good",
            },
            {
                "timestamp": timestamp,
                "sensor_id": "airflow-001",
                "sensor_name": "airflow",
                "value": airflow,
                "unit": "cfm",
                "quality": "good",
            },
        ],
    }


def test_data_connections_endpoint_lists_default_node_red_connection(tmp_path) -> None:
    client = build_client(tmp_path)

    response = client.get("/api/data-connections")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connections"]
    assert payload["connections"][0]["name"] == "Node-RED Cultivation Telemetry"
    assert payload["connections"][0]["url"] == "http://18.216.253.180:1880/telemetry/latest"


def test_poll_once_builds_live_baseline_before_updating_facility(monkeypatch, tmp_path) -> None:
    client = build_client(tmp_path)
    payloads = [
        payload_for(
            tick=10 + index,
            timestamp=f"2026-05-10T16:{42 + index:02d}:54.590Z",
            temperature=74.0 + index,
            humidity=56.0 + index,
            airflow=100.0 - index,
            scenario="airflow_drift" if index < BASELINE_SAMPLE_COUNT else "airflow_instability",
        )
        for index in range(BASELINE_SAMPLE_COUNT + 1)
    ]
    payload_iter = iter(payloads)
    monkeypatch.setattr("app.services.data_connections.fetch_connection_payload", lambda connection, transport=None: next(payload_iter))

    for _ in range(BASELINE_SAMPLE_COUNT - 1):
        response = client.post("/api/data-connections/node-red-cultivation-telemetry/poll-once")
        assert response.status_code == 200

    building_latest = client.get("/api/data/latest-upload")
    building_status = client.get("/api/data-connections/node-red-cultivation-telemetry/status")
    facility_before_active = client.get("/api/facility/systems")

    assert building_latest.status_code == 200
    assert building_latest.json()["status"] == "building_baseline"
    assert building_latest.json()["baseline_status"] == "building"
    assert building_latest.json()["baseline_samples_collected"] == BASELINE_SAMPLE_COUNT - 1
    assert building_latest.json()["latest_result"] is None
    assert building_status.json()["baseline_status"] == "building"
    assert facility_before_active.json()["intelligence_status"]["status"] == "no_data"

    activation = client.post("/api/data-connections/node-red-cultivation-telemetry/poll-once")
    activation_latest = client.get("/api/data/latest-upload")
    active_poll = client.post("/api/data-connections/node-red-cultivation-telemetry/poll-once")
    latest = client.get("/api/data/latest-upload")
    facility = client.get("/api/facility/systems")
    evidence = client.get("/api/evidence/latest")
    status = client.get("/api/data-connections/node-red-cultivation-telemetry/status")

    assert activation.status_code == 200
    assert active_poll.status_code == 200
    assert activation_latest.json()["status"] == "baseline_active"
    assert activation_latest.json()["baseline_status"] == "active"
    assert latest.status_code == 200

    latest_payload = latest.json()
    assert latest_payload["result_source"] == "rest_poll"
    assert latest_payload["source"] == "rest_poll"
    assert latest_payload["baseline_status"] == "active"
    assert latest_payload["baseline_source"] == "live_rest"
    assert latest_payload["latest_result"]["sii_intelligence"]["source"] == "rest_poll"
    assert latest_payload["latest_result"]["ingestion_metadata"]["tick"] == 16
    assert latest_payload["latest_result"]["ingestion_metadata"]["scenario"] == "airflow_instability"

    facility_payload = facility.json()
    assert facility_payload["intelligence"]["source"] == "rest_poll"
    assert facility_payload["intelligence"]["primary_room"] == "flower-room-1"

    evidence_payload = evidence.json()
    assert evidence_payload["run"]["source_name"] == "Node-RED Cultivation Telemetry"
    assert evidence_payload["run"]["source_type"] == "external_rest_api"

    status_payload = status.json()
    assert status_payload["current_tick"] == 16
    assert status_payload["status"] == "polling"
    assert status_payload["baseline_status"] == "active"
    assert status_payload["readings_received"] == 3
    assert status_payload["sensors_detected"] == 3


def test_failed_poll_marks_connection_error_and_preserves_last_valid_state(monkeypatch, tmp_path) -> None:
    client = build_client(tmp_path)
    payloads = [
        payload_for(
            tick=12 + index,
            timestamp=f"2026-05-10T17:{10 + index:02d}:04.590Z",
            temperature=75.1 + index,
            humidity=57.2 + index,
            airflow=99.4 - index,
        )
        for index in range(BASELINE_SAMPLE_COUNT + 1)
    ]
    payload_iter = iter(payloads)
    monkeypatch.setattr("app.services.data_connections.fetch_connection_payload", lambda connection, transport=None: next(payload_iter))
    for _ in range(BASELINE_SAMPLE_COUNT + 1):
        success = client.post("/api/data-connections/node-red-cultivation-telemetry/poll-once")
        assert success.status_code == 200

    monkeypatch.setattr(
        "app.services.data_connections.fetch_connection_payload",
        lambda connection, transport=None: (_ for _ in ()).throw(ValueError("REST API could not be reached. Check the endpoint and network path.")),
    )

    failed = client.post("/api/data-connections/node-red-cultivation-telemetry/poll-once")
    facility = client.get("/api/facility/systems")
    evidence_runs = client.get("/api/evidence/runs")
    status = client.get("/api/data-connections/node-red-cultivation-telemetry/status")

    assert failed.status_code == 200
    assert failed.json()["connection"]["status"] == "error"
    assert facility.status_code == 200
    assert facility.json()["intelligence"]["source"] == "rest_poll"
    assert evidence_runs.status_code == 200
    assert any(run["status"] == "failed" for run in evidence_runs.json()["runs"])
    assert status.json()["error_message"] == "REST API could not be reached. Check the endpoint and network path."
    assert status.json()["baseline_status"] == "active"


def test_reset_baseline_clears_live_baseline_state(monkeypatch, tmp_path) -> None:
    client = build_client(tmp_path)
    payloads = [
        payload_for(
            tick=30 + index,
            timestamp=f"2026-05-10T18:{10 + index:02d}:04.590Z",
            temperature=73.5 + index,
            humidity=55.2 + index,
            airflow=101.4 - index,
        )
        for index in range(BASELINE_SAMPLE_COUNT)
    ]
    payload_iter = iter(payloads)
    monkeypatch.setattr("app.services.data_connections.fetch_connection_payload", lambda connection, transport=None: next(payload_iter))
    for _ in range(BASELINE_SAMPLE_COUNT):
        response = client.post("/api/data-connections/node-red-cultivation-telemetry/poll-once")
        assert response.status_code == 200

    reset = client.post("/api/data-connections/node-red-cultivation-telemetry/reset-baseline")
    latest = client.get("/api/data/latest-upload")
    status = client.get("/api/data-connections/node-red-cultivation-telemetry/status")

    assert reset.status_code == 200
    assert reset.json()["connection"]["baseline_status"] == "none"
    assert latest.json()["baseline_status"] == "none"
    assert status.json()["baseline_samples_collected"] == 0
