from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.main import create_app

BASELINE_SAMPLE_COUNT = 6
TEST_DEFAULT_TELEMETRY_URL = ""


def build_client(tmp_path) -> TestClient:
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://localhost:3010"],
        default_telemetry_url=TEST_DEFAULT_TELEMETRY_URL,
        cors_origin_regex=None,
        runtime_dir=tmp_path,
    )
    return TestClient(create_app(settings))


def payload_for(*, tick: int, timestamp: str, temperature: float, humidity: float, airflow: float, scenario: str = "airflow_drift") -> dict:
    return {
        "source_id": "rest-sim-api-001",
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


def test_data_connections_endpoint_lists_default_rest_connection(tmp_path) -> None:
    client = build_client(tmp_path)

    response = client.get("/api/data-connections")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connections"]
    assert payload["connections"][0]["name"] in {"REST Telemetry Intake", "Live Telemetry Intake"}
    assert payload["connections"][0]["url"] == TEST_DEFAULT_TELEMETRY_URL


def test_connection_test_failure_returns_clean_json(monkeypatch, tmp_path) -> None:
    client = build_client(tmp_path)
    monkeypatch.setattr(
        "app.services.data_connections.fetch_connection_payload",
        lambda connection, transport=None: (_ for _ in ()).throw(ValueError("External telemetry response did not include any readings.")),
    )

    response = client.post("/api/data-connections/rest-telemetry-intake/test")

    assert response.status_code == 200
    payload = response.json()
    assert payload["connection"]["status"] == "error"
    assert payload["connection"]["error_message"] == "External telemetry response did not include any readings."
    assert payload["normalized_preview"] == []


@pytest.mark.slow
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
        response = client.post("/api/data-connections/rest-telemetry-intake/poll-once")
        assert response.status_code == 200

    building_latest = client.get("/api/data/latest-upload")
    building_status = client.get("/api/data-connections/rest-telemetry-intake/status")
    facility_before_active = client.get("/api/facility/systems")

    assert building_latest.status_code == 200
    assert building_latest.json()["baseline_status"] == "building"
    assert building_latest.json()["baseline_samples_collected"] == BASELINE_SAMPLE_COUNT - 1
    assert building_status.json()["baseline_status"] == "building"
    if building_latest.json()["latest_result"] is None:
        assert facility_before_active.json()["intelligence_status"]["status"] == "no_data"

    activation = client.post("/api/data-connections/rest-telemetry-intake/poll-once")
    activation_latest = client.get("/api/data/latest-upload")
    active_poll = client.post("/api/data-connections/rest-telemetry-intake/poll-once")
    latest = client.get("/api/data/latest-upload")
    facility = client.get("/api/facility/systems")
    evidence = client.get("/api/evidence/latest")
    status = client.get("/api/data-connections/rest-telemetry-intake/status")

    assert activation.status_code == 200
    assert active_poll.status_code == 200
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
    assert evidence_payload["run"]["source_name"] in {"REST Telemetry Intake", "Live Telemetry Intake"}
    assert evidence_payload["run"]["source_type"] == "external_rest_api"

    status_payload = status.json()
    assert status_payload["current_tick"] == 16
    assert status_payload["status"] == "polling"
    assert status_payload["baseline_status"] == "active"
    assert status_payload["readings_received"] == 3
    assert status_payload["sensors_detected"] == 3


@pytest.mark.slow
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
        success = client.post("/api/data-connections/rest-telemetry-intake/poll-once")
        assert success.status_code == 200

    monkeypatch.setattr(
        "app.services.data_connections.fetch_connection_payload",
        lambda connection, transport=None: (_ for _ in ()).throw(ValueError("REST API could not be reached. Check the endpoint and network path.")),
    )

    failed = client.post("/api/data-connections/rest-telemetry-intake/poll-once")
    facility = client.get("/api/facility/systems")
    evidence_runs = client.get("/api/evidence/runs")
    status = client.get("/api/data-connections/rest-telemetry-intake/status")

    assert failed.status_code == 200
    assert failed.json()["connection"]["status"] == "error"
    assert facility.status_code == 200
    assert facility.json()["intelligence"]["source"] == "rest_poll"
    assert evidence_runs.status_code == 200
    assert any(run["status"] == "failed" for run in evidence_runs.json()["runs"])
    assert status.json()["error_message"] == "REST API could not be reached. Check the endpoint and network path."
    assert status.json()["baseline_status"] == "active"


@pytest.mark.slow
def test_reset_baseline_restarts_build_and_increments_on_poll(monkeypatch, tmp_path) -> None:
    client = build_client(tmp_path)
    payloads = [
        payload_for(
            tick=30 + index,
            timestamp=f"2026-05-10T18:{10 + index:02d}:04.590Z",
            temperature=73.5 + index,
            humidity=55.2 + index,
            airflow=101.4 - index,
        )
        for index in range(BASELINE_SAMPLE_COUNT + 1)
    ]
    payload_iter = iter(payloads)
    monkeypatch.setattr("app.services.data_connections.fetch_connection_payload", lambda connection, transport=None: next(payload_iter))
    for _ in range(BASELINE_SAMPLE_COUNT):
        response = client.post("/api/data-connections/rest-telemetry-intake/poll-once")
        assert response.status_code == 200

    reset = client.post("/api/data-connections/rest-telemetry-intake/reset-baseline")
    latest = client.get("/api/data/latest-upload")
    status = client.get("/api/data-connections/rest-telemetry-intake/status")
    post_reset_poll = client.post("/api/data-connections/rest-telemetry-intake/poll-once")
    post_reset_status = client.get("/api/data-connections/rest-telemetry-intake/status")

    assert reset.status_code == 200
    assert reset.json()["connection"]["baseline_source"] == "live_rest"
    assert reset.json()["connection"]["baseline_status"] == "building"
    assert reset.json()["connection"]["baseline_samples_collected"] == 0
    assert latest.json()["baseline_status"] == "building"
    assert status.json()["baseline_samples_collected"] == 0
    assert post_reset_poll.status_code == 200
    assert post_reset_status.status_code == 200
    assert post_reset_status.json()["baseline_status"] == "building"
    assert post_reset_status.json()["baseline_samples_collected"] == 1


@pytest.mark.slow
def test_reset_all_connections_clears_active_source_state(monkeypatch, tmp_path) -> None:
    client = build_client(tmp_path)
    payload = payload_for(
        tick=71,
        timestamp="2026-05-10T20:11:04.590Z",
        temperature=74.8,
        humidity=57.3,
        airflow=99.2,
    )
    monkeypatch.setattr("app.services.data_connections.fetch_connection_payload", lambda connection, transport=None: payload)

    for _ in range(BASELINE_SAMPLE_COUNT + 1):
        response = client.post("/api/data-connections/rest-telemetry-intake/poll-once")
        assert response.status_code == 200

    before_latest = client.get("/api/data/latest-upload")
    assert before_latest.status_code == 200
    assert before_latest.json()["status"] != "empty"

    reset = client.post("/api/data-connections/reset-all")
    assert reset.status_code == 200
    reset_payload = reset.json()
    assert reset_payload["connections"]
    assert all(connection["status"] == "offline" for connection in reset_payload["connections"])
    assert all(connection["baseline_status"] == "none" for connection in reset_payload["connections"])
    assert all(connection["last_ingestion_source"] is None for connection in reset_payload["connections"])

    latest = client.get("/api/data/latest-upload")
    assert latest.status_code == 200
    latest_payload = latest.json()
    assert latest_payload["status"] == "empty"
    assert latest_payload["latest_result"] is None
    assert latest_payload["result_source"] is None
