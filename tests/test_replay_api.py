from fastapi.testclient import TestClient

from app.main import create_app
from app.services.sii_intelligence import build_sample_intelligence
from app.services.sii_runner import write_latest_sii_state


def test_replay_timeline_returns_structural_frames() -> None:
    write_latest_sii_state(build_sample_intelligence())
    client = TestClient(create_app())

    response = client.get("/api/replay/timeline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["meta"]["frame_count"] >= 6
    assert payload["meta"]["canonical_flow"]
    assert len(payload["timeline"]) >= 6
    first = payload["timeline"][0]
    assert "topology_state" in first
    assert "subsystem_pressure" in first
    assert "active_archetypes" in first
    assert "propagation_state" in first
    assert "evidence_state" in first
    assert "cognition_state" in first
    assert "canonical_phase" in first["cognition_state"]


def test_replay_frame_and_range_endpoints() -> None:
    write_latest_sii_state(build_sample_intelligence())
    client = TestClient(create_app())
    timeline_response = client.get("/api/replay/timeline?intervals=12")
    assert timeline_response.status_code == 200
    timeline = timeline_response.json()["timeline"]
    middle = timeline[len(timeline) // 2]["timestamp"]
    start = timeline[2]["timestamp"]
    end = timeline[8]["timestamp"]

    frame_response = client.get(f"/api/replay/frame/{middle}?intervals=12")
    assert frame_response.status_code == 200
    assert frame_response.json()["frame"]["timestamp"]

    range_response = client.get(
        f"/api/replay/range?start_timestamp={start}&end_timestamp={end}&intervals=12"
    )
    assert range_response.status_code == 200
    range_payload = range_response.json()
    assert range_payload["frame_count"] >= 1
    assert len(range_payload["frames"]) == range_payload["frame_count"]


def test_aquatic_demo_mode_replay_timeline_available() -> None:
    client = TestClient(create_app())

    response = client.get("/api/replay/timeline?mode=aquatic_demo&intervals=18")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "aquatic_demo"
    assert payload["meta"]["domain"] == "commercial_aquatic_hospitality"
    assert payload["meta"]["frame_count"] >= 18
