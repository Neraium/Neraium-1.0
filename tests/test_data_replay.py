from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.routers.data import rebuild_upload_replay_from_source
from app.services.upload_jobs import write_job, write_latest_upload_result


def test_rebuild_upload_replay_from_source(tmp_path: Path) -> None:
    csv_path = tmp_path / "telemetry.csv"
    rows = "\n".join(
        f"2026-05-21T08:{minute:02d}:00Z,{72 + (minute % 5)},{48 + (minute % 7)}"
        for minute in range(60)
    )
    csv_path.write_text(f"timestamp,temperature,humidity\n{rows}\n", encoding="utf-8")

    payload = rebuild_upload_replay_from_source({
        "job_id": "job-123",
        "file_path": str(csv_path),
        "filename": "telemetry.csv",
    })

    assert payload is not None
    assert payload["job_id"] == "job-123"
    assert payload["frame_count"] > 0
    assert payload["timeline"]
    assert payload["message"] == "Replay reconstructed from the retained source CSV."


def test_persisted_upload_result_exposes_replay_without_source_file(tmp_path: Path) -> None:
    job_id = "persisted-replay-job"
    write_job(
        {
            "job_id": job_id,
            "filename": "telemetry.csv",
            "file_path": str(tmp_path / "telemetry.csv"),
            "status": "COMPLETE",
            "result_available": True,
            "first_usable_available": True,
        }
    )
    write_latest_upload_result(
        job_id,
        {
            "filename": "telemetry.csv",
            "row_count": 12,
            "column_count": 3,
            "columns": ["timestamp", "temperature", "humidity"],
            "preview_rows": [],
            "data_quality": {"readiness": "ready"},
            "engine_result": {"overall_result": "stable"},
            "cultivation_mapping": {"categories": {}},
            "sii_intelligence": {
                "source": "uploaded",
                "mode": "live",
                "facility_state": "Monitoring active telemetry feed",
                "urgency": "nominal",
                "primary_room": "Thermal Loop",
                "replay_timeline": {
                    "meta": {"frame_count": 2},
                    "timeline": [
                        {"timestamp": "2026-05-21T08:00:00+00:00", "timestamp_end": "2026-05-21T08:01:00+00:00"},
                        {"timestamp": "2026-05-21T08:01:00+00:00", "timestamp_end": "2026-05-21T08:02:00+00:00"},
                    ],
                },
            },
            "driver_attribution": {},
            "processing_trace": {},
            "processing_stats": {},
            "room_summary": {"room_count": 1, "rooms": [{"room": "Thermal Loop", "row_count": 12}]},
        },
    )

    client = TestClient(create_app())
    payload = client.get(f"/api/data/replay/{job_id}").json()

    assert payload["frame_count"] == 2
    assert len(payload["timeline"]) == 2
    assert payload["meta"]["frame_count"] == 2


def test_replay_endpoint_uses_latest_persisted_frames_when_job_metadata_missing() -> None:
    write_latest_upload_result(
        "latest-job",
        {
            "filename": "telemetry.csv",
            "row_count": 12,
            "column_count": 3,
            "columns": ["timestamp", "temperature", "humidity"],
            "preview_rows": [],
            "data_quality": {"readiness": "ready"},
            "engine_result": {"overall_result": "stable"},
            "cultivation_mapping": {"categories": {}},
            "sii_intelligence": {
                "source": "uploaded",
                "mode": "live",
                "facility_state": "Monitoring active telemetry feed",
                "urgency": "nominal",
                "primary_room": "Thermal Loop",
                "replay_timeline": {
                    "meta": {"frame_count": 1},
                    "timeline": [{"timestamp": "2026-05-21T08:00:00+00:00", "timestamp_end": "2026-05-21T08:01:00+00:00"}],
                },
            },
            "driver_attribution": {},
            "processing_trace": {},
            "processing_stats": {},
            "room_summary": {"room_count": 1, "rooms": [{"room": "Thermal Loop", "row_count": 12}]},
        },
    )

    client = TestClient(create_app())
    payload = client.get("/api/data/replay/missing-job-id").json()

    assert payload["frame_count"] == 1
    assert len(payload["timeline"]) == 1
