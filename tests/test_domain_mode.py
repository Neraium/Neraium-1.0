from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.upload_jobs import write_latest_upload_result


def _write_detectable_upload(job_id: str, *, columns: list[str], room_names: list[str]) -> None:
    write_latest_upload_result(
        job_id,
        {
            "filename": f"{job_id}.csv",
            "row_count": 12,
            "column_count": len(columns),
            "columns": columns,
            "preview_rows": [],
            "detected_timestamp_column": "timestamp",
            "warnings": [],
            "numeric_profiles": [],
            "timestamp_profile": {"detected_timestamp_column": "timestamp", "warnings": []},
            "data_quality": {"row_count": 12, "column_count": len(columns), "numeric_column_count": 3, "timestamp_detected": True, "warnings": [], "readiness": "ready"},
            "baseline_analysis": {},
            "cultivation_mapping": {"categories": {"thermal": [], "moisture": [], "flow": [], "chemical": [], "energy": [], "timing": [], "network": [], "location": [], "unknown": []}},
            "schema_mapping": {"categories": {"thermal": [], "moisture": [], "flow": [], "chemical": [], "energy": [], "timing": [], "network": [], "location": [], "unknown": []}},
            "aquatic_schema": {"mapped_column_count": 0, "coverage_ratio": 0.0},
            "operator_report": {},
            "engine_result": {"overall_result": "stable", "signals": [], "evidence": []},
            "driver_attribution": {},
            "sii_intelligence": {
                "source": "uploaded",
                "mode": "live",
                "facility_state": "Monitoring active telemetry feed",
                "room_state": "Monitoring active telemetry feed",
                "urgency": "nominal",
                "intervention_window": "12 hours",
                "neraium_score": 90,
                "primary_room": room_names[0] if room_names else "Unknown",
                "priority_room": room_names[0] if room_names else "Unknown",
                "primary_driver": "Auto-detected from upload shape",
                "supporting_evidence": ["Auto-detected from upload shape"],
                "relationship_evidence": ["Auto-detected from upload shape"],
                "structural_explanation": ["Auto-detected from upload shape"],
                "confidence_basis": "Auto-detected from upload shape",
                "recommended_operator_review": "Continue monitoring",
                "what_to_check": ["Continue monitoring"],
                "why_flagged": "Auto-detected from upload shape",
                "baseline_comparison": "Auto-detected from upload shape",
                "observed_persistence": "Auto-detected from upload shape",
                "last_updated": "2026-05-10T00:00:00+00:00",
                "rooms": [{"room": room, "row_count": 4} for room in room_names],
                "replay_timeline": {"meta": {}, "timeline": []},
            },
            "sii_runner_result": {"runner_used": True, "runner_module": "runner", "core_engine": "engine", "errors": []},
            "processing_trace": {},
            "processing_stats": {},
            "room_summary": {"room_count": len(room_names), "rooms": [{"room": room, "row_count": 4} for room in room_names]},
            "ingestion_metadata": {},
            "validation_provenance": {},
            "adaptive_learning": {},
        },
    )


def test_domain_mode_detects_cultivation_from_room_and_sensor_shape() -> None:
    _write_detectable_upload(
        "cultivation-upload",
        columns=["timestamp", "room", "temperature", "humidity", "vpd", "irrigation_runtime"],
        room_names=["Flower Room 1", "Veg Room A"],
    )
    client = TestClient(create_app())

    status = client.get("/api/domain/mode")

    assert status.status_code == 200
    payload = status.json()
    assert payload["mode"] == "cultivation"
    assert payload["source"] == "upload_shape"
    assert payload["confidence"] >= 0.55
    assert payload["evidence"]

    facility = client.get("/api/facility/systems")
    assert facility.status_code == 200
    assert facility.json()["domain_mode"] == "cultivation"


def test_domain_mode_detects_aquatic_from_water_treatment_shape() -> None:
    _write_detectable_upload(
        "aquatic-upload",
        columns=["timestamp", "pool_water_temp", "spa_water_temp", "orp_mv", "chlorine_ppm", "heater_runtime", "circulation_pump_runtime"],
        room_names=["Pool Deck", "Spa Mechanical"],
    )
    client = TestClient(create_app())

    status = client.get("/api/domain/mode")

    assert status.status_code == 200
    payload = status.json()
    assert payload["mode"] == "aquatic"
    assert payload["source"] == "upload_shape"
    assert payload["confidence"] >= 0.55
    assert payload["evidence"]

    facility = client.get("/api/facility/systems")
    assert facility.status_code == 200
    assert facility.json()["domain_mode"] == "aquatic"


def test_domain_mode_reports_auto_detected_when_no_upload_exists(tmp_path) -> None:
    client = TestClient(
        create_app(
            Settings(
                app_env="test",
                backend_host="127.0.0.1",
                backend_port=8000,
                cors_origins=["http://localhost"],
                runtime_dir=tmp_path,
            )
        )
    )

    status = client.get("/api/domain/mode")

    assert status.status_code == 200
    payload = status.json()
    assert payload["source"] == "unclassified"
    assert payload["confidence"] == 0
    assert payload["evidence"] == []


def test_domain_mode_ignores_stale_latest_result_without_active_upload_marker(tmp_path) -> None:
    from app.services import upload_jobs

    upload_jobs.configure_runtime_dir(tmp_path)
    upload_jobs._write_json("latest_upload_result.json", {
        "job_id": "stale-upload",
        "columns": ["timestamp", "pool_water_temp", "chlorine_ppm"],
        "room_summary": {"rooms": [{"room": "Pool Deck", "row_count": 4}]},
    })
    client = TestClient(
        create_app(
            Settings(
                app_env="test",
                backend_host="127.0.0.1",
                backend_port=8000,
                cors_origins=["http://localhost"],
                runtime_dir=tmp_path,
            )
        )
    )

    status = client.get("/api/domain/mode")

    assert status.status_code == 200
    payload = status.json()
    assert payload["source"] == "unclassified"
    assert payload["confidence"] == 0
    assert payload["evidence"] == []
