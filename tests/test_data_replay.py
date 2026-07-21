from pathlib import Path
import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.routers.data import rebuild_upload_replay_from_source
from app.services import upload_jobs
from app.services.upload_jobs import read_job, write_job, write_latest_upload_result


def test_rebuild_upload_replay_from_source(tmp_path: Path) -> None:
    csv_path = upload_jobs.UPLOAD_DIR / "telemetry.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"2026-05-21T08:{minute:02d}:00Z,{72 + (minute % 5)},{48 + (minute % 7)}"
        for minute in range(60)
    )
    csv_path.write_text(f"timestamp,temperature,humidity\n{rows}\n", encoding="utf-8")

    payload = rebuild_upload_replay_from_source({
        "job_id": "job-123",
        "file_path": csv_path.name,
        "filename": "telemetry.csv",
    })

    assert payload is not None
    assert payload["job_id"] == "job-123"
    assert payload["frame_count"] > 0
    assert payload["timeline"]
    assert payload["message"] == "Replay reconstructed from the retained source CSV."


def test_rebuild_upload_replay_from_source_uses_minimal_fallback_when_numeric_signal_is_sparse(tmp_path: Path) -> None:
    csv_path = upload_jobs.UPLOAD_DIR / "events.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"2026-05-21T08:{minute:02d}:00Z,phaseA,statusON"
        for minute in range(40)
    )
    csv_path.write_text(f"timestamp,phase,status\n{rows}\n", encoding="utf-8")

    payload = rebuild_upload_replay_from_source({
        "job_id": "job-fallback",
        "file_path": csv_path.name,
        "filename": "events.csv",
    })

    assert payload is not None
    assert payload["job_id"] == "job-fallback"
    assert payload["frame_count"] > 0
    assert payload["timeline"]
    assert payload["meta"].get("replay_mode") == "minimal_timestamp_fallback"


def test_rebuild_upload_replay_from_source_parses_mixed_numeric_formats_and_non_hint_timestamp(tmp_path: Path) -> None:
    csv_path = upload_jobs.UPLOAD_DIR / "plant.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    rows = "\n".join(
        f"2026-05-21 08:{minute:02d}:00,\"{1200 + minute * 0.5:.1f} kW\",\"{45 + (minute % 5):.1f}%\""
        for minute in range(50)
    )
    csv_path.write_text(f"logged_at,power_draw,efficiency\n{rows}\n", encoding="utf-8")

    payload = rebuild_upload_replay_from_source({
        "job_id": "job-mixed-numeric",
        "file_path": csv_path.name,
        "filename": "plant.csv",
    })

    assert payload is not None
    assert payload["frame_count"] > 0
    assert payload["timeline"]
    assert payload["meta"].get("replay_mode") != "minimal_timestamp_fallback"


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


def test_replay_endpoint_uses_canonical_per_job_persisted_frames() -> None:
    job_id = "missing-job-id"
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
    payload = client.get(f"/api/data/replay/{job_id}").json()

    assert payload["frame_count"] == 1
    assert len(payload["timeline"]) == 1


def test_replay_payload_with_missing_job_does_not_fall_back_to_latest_result() -> None:
    write_latest_upload_result(
        "latest-visible-job",
        {
            "filename": "latest.csv",
            "row_count": 12,
            "column_count": 3,
            "columns": ["timestamp", "x", "y"],
            "preview_rows": [],
            "data_quality": {"readiness": "ready"},
            "engine_result": {"overall_result": "stable"},
            "cultivation_mapping": {"categories": {}},
            "sii_intelligence": {
                "source": "uploaded",
                "mode": "live",
                "replay_timeline": {
                    "meta": {"frame_count": 1},
                    "timeline": [{"timestamp": "2026-05-21T08:00:00+00:00"}],
                },
            },
            "driver_attribution": {},
            "processing_trace": {},
            "processing_stats": {},
            "room_summary": {"room_count": 0, "rooms": []},
        },
    )

    payload = read_job("latest-visible-job")
    assert payload is None or payload.get("job_id") != "missing-job"

    replay = upload_jobs.replay_payload("missing-job")

    assert replay["job_id"] == "missing-job"
    assert replay["timeline"] == []
    assert replay["source"] == "empty"
    assert "requested upload job" in replay["message"].lower()


def test_intake_result_reads_canonical_per_job_artifact_not_just_latest() -> None:
    first_job_id = "job-one"
    second_job_id = "job-two"
    for job_id in (first_job_id, second_job_id):
        write_job(
            {
                "job_id": job_id,
                "filename": f"{job_id}.csv",
                "file_path": f"/tmp/{job_id}.csv",
                "status": "COMPLETE",
                "result_available": True,
                "first_usable_available": True,
                "result_summary": {"rows_processed": 10},
            }
        )

    write_latest_upload_result(
        first_job_id,
        {
            "filename": "job-one.csv",
            "row_count": 10,
            "column_count": 3,
            "columns": ["timestamp", "x", "y"],
            "preview_rows": [],
            "data_quality": {"readiness": "ready"},
            "engine_result": {"overall_result": "stable"},
            "cultivation_mapping": {"categories": {}},
            "sii_intelligence": {"source": "uploaded", "mode": "live", "rooms": []},
            "driver_attribution": {},
            "processing_trace": {},
            "processing_stats": {},
            "room_summary": {"room_count": 0, "rooms": []},
        },
    )
    # Make another job latest to ensure intake lookup is job-scoped.
    write_latest_upload_result(
        second_job_id,
        {
            "filename": "job-two.csv",
            "row_count": 20,
            "column_count": 3,
            "columns": ["timestamp", "x", "y"],
            "preview_rows": [],
            "data_quality": {"readiness": "ready"},
            "engine_result": {"overall_result": "stable"},
            "cultivation_mapping": {"categories": {}},
            "sii_intelligence": {"source": "uploaded", "mode": "live", "rooms": []},
            "driver_attribution": {},
            "processing_trace": {},
            "processing_stats": {},
            "room_summary": {"room_count": 0, "rooms": []},
        },
    )

    client = TestClient(create_app())
    response = client.get(f"/api/data/intake/{first_job_id}/result")
    payload = response.json()

    assert response.status_code == 200
    assert payload["result_available"] is True
    assert payload["result"]["job_id"] == first_job_id
    assert payload["result"]["filename"] == "job-one.csv"


def _wait_for_terminal_status(client: TestClient, job_id: str, timeout_seconds: float = 120.0) -> dict:
    deadline = time.time() + timeout_seconds
    last_payload: dict | None = None
    while time.time() < deadline:
        response = client.get(f"/api/data/upload-status/{job_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload.get("status") in {"COMPLETE", "FAILED"}:
            return last_payload
        time.sleep(0.05)
    raise AssertionError(f"Upload did not complete. Last payload: {last_payload}")


def test_historian_style_csv_upload_persists_replay_after_source_removed() -> None:
    client = TestClient(create_app())
    row_count = 50_000
    rows = []
    for index in range(row_count):
        rows.append(
            ",".join(
                [
                    f"2026-05-01 {index % 24:02d}:{(index // 24) % 60:02d}:{index % 60:02d}",
                    f"{42.0 + ((index % 37) * 0.07):.3f}",
                    f"{49.5 + ((index % 41) * 0.06):.3f}",
                    f"{850 + (index % 120)}",
                    f"{210 + ((index * 3) % 140)}",
                    f"{18.0 + ((index % 25) * 0.09):.3f}",
                    f"{55 + (index % 35)}%",
                    f"{300 + ((index * 5) % 170)}",
                    f"{40 + (index % 45)}",
                    str(index % 4),
                    "filter_inspection" if index % 9000 == 0 else "",
                    "manual" if index % 7000 == 0 else "",
                ]
            )
        )
    csv_content = (
        "timestamp,chilled_water_supply_temp_f,chilled_water_return_temp_f,flow_gpm,pump_power_kw,"
        "differential_pressure_psi,chiller_load_pct,compressor_power_kw,building_cooling_demand_pct,"
        "alarm_count,maintenance_event,operator_override\n"
        + "\n".join(rows)
    )

    upload_response = client.post(
        "/api/data/upload",
        files={"file": ("chilled_water_system_data.csv", csv_content, "text/csv")},
    )
    assert upload_response.status_code == 202
    job_id = upload_response.json()["job_id"]

    status_payload = _wait_for_terminal_status(client, job_id, timeout_seconds=180.0)
    assert status_payload["status"] == "COMPLETE"
    assert status_payload["replay_ready"] is True
    assert int(status_payload["replay_frame_count"]) > 0

    latest_payload = client.get("/api/data/latest-upload?include_persisted=1").json()
    latest_result = latest_payload.get("latest_result") or {}
    latest_timeline = (
        ((latest_result.get("replay_timeline") or {}).get("timeline"))
        or (((latest_result.get("sii_intelligence") or {}).get("replay_timeline") or {}).get("timeline"))
        or []
    )
    assert isinstance(latest_timeline, list)
    assert len(latest_timeline) > 0

    replay_before_delete = client.get(f"/api/data/replay/{job_id}")
    assert replay_before_delete.status_code == 200
    replay_before_delete_payload = replay_before_delete.json()
    assert replay_before_delete_payload["frame_count"] > 0
    assert len(replay_before_delete_payload["timeline"]) > 0

    job_metadata = read_job(job_id)
    assert isinstance(job_metadata, dict)
    source_path = Path(str(job_metadata.get("file_path")))
    if not source_path.is_absolute():
        source_path = upload_jobs.UPLOAD_DIR / source_path
    if source_path.exists():
        source_path.unlink()

    replay_after_delete = client.get(f"/api/data/replay/{job_id}")
    assert replay_after_delete.status_code == 200
    replay_after_delete_payload = replay_after_delete.json()
    assert replay_after_delete_payload["frame_count"] > 0
    assert len(replay_after_delete_payload["timeline"]) > 0
