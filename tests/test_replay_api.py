from fastapi.testclient import TestClient

from app.main import create_app
from app.services.sii_intelligence import build_sample_intelligence
from app.services.sii_runner import write_latest_sii_state
from app.services.upload_jobs import write_job
from app.services.upload_state_repository import reset_upload_state, write_latest_upload_result


def _seed_canonical_replay(job_id: str = "live-replay-job", frame_count: int = 6) -> None:
    timeline = [
        {
            "timestamp": f"2026-01-01T00:00:0{index}Z",
            "timestamp_end": f"2026-01-01T00:00:0{index}Z",
            "topology_state": {"phase": "relationship_weakening", "drift_index": 0.25 + index * 0.05},
            "subsystem_pressure": {"score": round(0.2 + index * 0.1, 3)},
            "active_archetypes": ["relationship_shift"],
            "propagation_state": {"dominant_paths": ["loop_a"]},
            "evidence_state": {"corroboration_strength": "moderate"},
            "cognition_state": {"canonical_phase": "relationship_weakening"},
        }
        for index in range(frame_count)
    ]
    write_latest_upload_result(
        job_id,
        {
            "filename": "telemetry.csv",
            "row_count": 120,
            "column_count": 4,
            "columns": ["timestamp", "flow", "pressure", "power"],
            "preview_rows": [],
            "data_quality": {"readiness": "ready"},
            "engine_result": {"overall_result": "stable"},
            "cultivation_mapping": {"categories": {}},
            "sii_intelligence": {
                "source": "uploaded",
                "replay_timeline": {
                    "meta": {"frame_count": frame_count},
                    "timeline": timeline,
                },
            },
            "driver_attribution": {},
            "processing_trace": {},
            "processing_stats": {},
            "room_summary": {"room_count": 1, "rooms": [{"room": "Loop A", "row_count": 120}]},
        },
    )


def test_replay_timeline_returns_structural_frames() -> None:
    reset_upload_state()
    _seed_canonical_replay(frame_count=6)
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
    reset_upload_state()
    _seed_canonical_replay(frame_count=12)
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


def test_production_live_replay_does_not_return_synthetic_fallback(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_API_TOKEN", "expected-secret")
    client = TestClient(create_app())

    response = client.get(
        "/api/replay/timeline?mode=live&intervals=12",
        headers={"X-Neraium-Access-Code": "expected-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "empty"
    assert payload["meta"]["frame_count"] == 0
    assert payload["timeline"] == []


def test_live_causal_mode_replay_includes_lookahead_free_metadata() -> None:
    reset_upload_state()
    _seed_canonical_replay(frame_count=12)
    client = TestClient(create_app())

    response = client.get("/api/replay/timeline?mode=live_causal&intervals=12")

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("meta", {}).get("mode") == "live_causal"
    assert payload.get("meta", {}).get("lookahead_free") is True
    assert isinstance(payload.get("timeline"), list)
    if payload["timeline"]:
        assert payload["timeline"][0].get("live_causal", {}).get("lookahead_free") is True


def test_replay_timeline_does_not_fall_back_to_stale_global_state_when_current_upload_is_only_queued() -> None:
    write_latest_sii_state(build_sample_intelligence())
    write_job({
        "job_id": "queued-job",
        "filename": "queued.csv",
        "status": "PENDING",
        "processing_state": "queued",
        "message": "Upload accepted. Processing is queued.",
    })
    client = TestClient(create_app())

    response = client.get("/api/replay/timeline?mode=live&intervals=12")

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "empty"
    assert payload["timeline"] == []


def test_replay_timeline_falls_back_to_latest_persisted_replay_frames() -> None:
    write_latest_upload_result(
        "fallback-upload-job",
        {
            "filename": "telemetry.csv",
            "row_count": 120,
            "column_count": 4,
            "columns": ["timestamp", "flow", "pressure", "power"],
            "preview_rows": [],
            "data_quality": {"readiness": "ready"},
            "engine_result": {"overall_result": "stable"},
            "cultivation_mapping": {"categories": {}},
            # Intentionally minimal intelligence object (missing required fields),
            # to validate replay fallback for large persisted uploads.
            "sii_intelligence": {
                "source": "uploaded",
                "replay_timeline": {
                    "meta": {"frame_count": 2},
                    "timeline": [
                        {"timestamp": "2026-05-21T08:00:00+00:00", "timestamp_end": "2026-05-21T08:05:00+00:00"},
                        {"timestamp": "2026-05-21T08:05:00+00:00", "timestamp_end": "2026-05-21T08:10:00+00:00"},
                    ],
                },
            },
            "driver_attribution": {},
            "processing_trace": {},
            "processing_stats": {},
            "room_summary": {"room_count": 1, "rooms": [{"room": "Loop A", "row_count": 120}]},
        },
    )
    client = TestClient(create_app())

    response = client.get("/api/replay/timeline?mode=live&intervals=24")

    assert response.status_code == 200
    payload = response.json()
    assert payload.get("source") == "uploaded"
    assert len(payload.get("timeline", [])) == 2
