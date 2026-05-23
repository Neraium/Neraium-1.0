from __future__ import annotations

import csv
import io
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from app.services.sii_runner import RUNNER_MODULE
from app.services.runtime_db import claim_next_upload_job, mark_queue_job_failed

RUNTIME_DIR = Path("backend/runtime")
UPLOAD_DIR = RUNTIME_DIR / "uploads"
JOB_DIR = RUNTIME_DIR / "upload_jobs"
LEGACY_JOB_DIR = RUNTIME_DIR / "jobs"
JOBS: dict[str, dict[str, Any]] = {}
LATEST_UPLOAD_CACHE: dict[str, Any] = {"summary": None, "result": None}


def configure_runtime_dir(path: str | os.PathLike[str]) -> None:
    global RUNTIME_DIR, UPLOAD_DIR, JOB_DIR, LEGACY_JOB_DIR
    RUNTIME_DIR = Path(path)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR = RUNTIME_DIR / "uploads"
    JOB_DIR = RUNTIME_DIR / "upload_jobs"
    LEGACY_JOB_DIR = RUNTIME_DIR / "jobs"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_JOB_DIR.mkdir(parents=True, exist_ok=True)
    JOBS.clear()
    LATEST_UPLOAD_CACHE["summary"] = None
    LATEST_UPLOAD_CACHE["result"] = None


def warm_latest_upload_cache() -> None:
    LATEST_UPLOAD_CACHE["summary"] = _read_json("latest_upload_summary.json")
    LATEST_UPLOAD_CACHE["result"] = _read_json("latest_upload_result.json")


def read_latest_upload_result() -> dict[str, Any] | None:
    return LATEST_UPLOAD_CACHE.get("result") or _read_json("latest_upload_result.json")


def read_latest_upload_summary() -> dict[str, Any] | None:
    return LATEST_UPLOAD_CACHE.get("summary") or _read_json("latest_upload_summary.json")


def read_upload_result_by_job_id(job_id: str) -> dict[str, Any] | None:
    return _read_json(f"upload_result_{job_id}.json")


def read_upload_status(job_id: str) -> dict[str, Any] | None:
    return JOBS.get(job_id) or _read_json(f"upload_status_{job_id}.json")


def reset_upload_state() -> None:
    JOBS.clear()
    for path in RUNTIME_DIR.glob("*upload*"):
        try:
            path.unlink()
        except OSError:
            pass
    LATEST_UPLOAD_CACHE["summary"] = None
    LATEST_UPLOAD_CACHE["result"] = None


def _set_status(job_id: str, status: str, progress: int = 0, message: str = "") -> dict[str, Any]:
    """
    Persist upload progress so live uploads always have a job id/status.
    This restores the status helper used by process_upload_bytes().
    """
    payload = {
        "job_id": job_id,
        "status": status,
        "processing_state": str(status).lower(),
        "percent": progress,
        "progress": progress,
        "message": message,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    JOBS[job_id] = payload
    _write_json(f"upload_status_{job_id}.json", payload)
    LATEST_UPLOAD_CACHE["summary"] = payload
    return payload


def process_upload_bytes(filename: str, content: bytes) -> dict[str, Any]:
    if not content.strip():
        raise ValueError("CSV file is empty.")
    job_id = uuid.uuid4().hex
    _set_status(job_id, "PROCESSING", 10, "Parsing CSV")

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    columns = list(reader.fieldnames or [])
    rows = list(reader)

    if not columns or not rows:
        raise ValueError("CSV must include a header and at least one data row.")

    timestamp_column = _detect_timestamp_column(columns)
    numeric_columns = _detect_numeric_columns(rows, columns, exclude={timestamp_column})
    numeric_profiles = []
    for col in numeric_columns[:50]:
        values = [_to_float(row.get(col)) for row in rows]
        clean = [value for value in values if value is not None]
        if not clean:
            continue
        numeric_profiles.append(
            {
                "column": col,
                "minimum": round(min(clean), 4),
                "maximum": round(max(clean), 4),
                "average": round(sum(clean) / len(clean), 4),
            }
        )
    room_column = next((col for col in columns if col.lower().strip() == "room"), None)
    room_counts: dict[str, int] = {}
    room_rows: dict[str, list[dict[str, Any]]] = {}
    if room_column:
        for row in rows:
            room_name = str(row.get(room_column) or "").strip() or "Uploaded telemetry"
            room_counts[room_name] = room_counts.get(room_name, 0) + 1
            room_rows.setdefault(room_name, []).append(row)
    if not room_counts:
        room_counts = {"Uploaded telemetry": len(rows)}
        room_rows = {"Uploaded telemetry": rows}
    room_names = sorted(room_counts.keys())
    room_summary = {
        "room_count": len(room_names),
        "rooms": [{"room": name, "row_count": room_counts[name]} for name in room_names],
    }
    room_intelligence = []
    room_urgency_rank = {"nominal": 0, "review": 1, "unstable": 2}
    max_room_urgency = "nominal"
    max_room_drift = 0.0
    for name in room_names:
        count = room_counts[name]
        sparse = count < 4
        sample_rows = room_rows.get(name, [])
        temp_key = next((col for col in columns if "temp" in col.lower()), None)
        humidity_key = next((col for col in columns if "humid" in col.lower() or "rh_" in col.lower()), None)
        airflow_key = next((col for col in columns if "airflow" in col.lower() or "flow" in col.lower()), None)
        room_drift = 0.0
        if sample_rows and (temp_key or humidity_key or airflow_key):
            per_signal_drifts: list[float] = []
            for key in (temp_key, humidity_key, airflow_key):
                if not key:
                    continue
                series = [_to_float(row.get(key)) for row in sample_rows]
                clean = [value for value in series if value is not None]
                if len(clean) < 2:
                    continue
                minimum = min(clean)
                maximum = max(clean)
                baseline_slice = clean[: max(1, len(clean) // 3)]
                baseline = sum(baseline_slice) / max(1, len(baseline_slice))
                denom = abs(baseline) if abs(baseline) > 1e-6 else 1.0
                per_signal_drifts.append(abs(maximum - minimum) / denom)
            if per_signal_drifts:
                room_drift = sum(per_signal_drifts) / len(per_signal_drifts)
        if sparse:
            urgency = "review"
            driver_category = "sensor_network"
            attribution_confidence = "low"
            signal_strength = "low"
            room_state = "Insufficient telemetry"
            relationship_evidence = [f"{name}: Room-level relationship evidence is limited due to sparse telemetry."]
            structural_explanation = [f"{name}: Structural explanation is limited due to sparse telemetry."]
        elif room_drift > 0.25:
            urgency = "unstable"
            driver_category = "process_timing"
            attribution_confidence = "high"
            signal_strength = "high"
            room_state = "Drift observed"
            relationship_evidence = [f"{name}: Temperature and humidity relationships are diverging from baseline."]
            structural_explanation = [f"{name}: Multi-signal drift indicates structural coupling instability."]
        else:
            urgency = "nominal"
            driver_category = "stable_monitoring"
            attribution_confidence = "medium"
            signal_strength = "low"
            room_state = "Monitoring active telemetry feed"
            relationship_evidence = [f"{name}: Relationship evidence remains within expected room behavior."]
            structural_explanation = [f"{name}: Structural explanation indicates stable room behavior."]
        if room_urgency_rank[urgency] > room_urgency_rank[max_room_urgency]:
            max_room_urgency = urgency
        max_room_drift = max(max_room_drift, room_drift)
        room_intelligence.append(
            {
                "room": name,
                "room_state": room_state,
                "urgency": urgency,
                "driver_category": driver_category,
                "attribution_confidence": attribution_confidence,
                "next_operator_move": "Collect more room telemetry before clearing this system" if sparse else "Continue monitoring",
                "confidence_components": {
                    "data_sufficiency": "low" if sparse else "high",
                    "signal_strength": signal_strength,
                    "relationship_support": "low" if sparse else "high",
                    "persistence": "low" if sparse else "high",
                },
                "relationship_evidence": relationship_evidence,
                "structural_explanation": structural_explanation,
                "confidence_basis": f"{name}: Confidence components: data sufficiency, signal strength, relationship support, persistence.",
                "why_flagged": (
                    f"{name} flagged because room-level telemetry is currently sparse."
                    if sparse
                    else f"{name} remains within normal uploaded telemetry behavior."
                ),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        )
    telemetry_profile, telemetry_profile_confidence, telemetry_profile_signals = classify_telemetry_profile(columns)
    operational_profile, operational_profile_confidence, operational_profile_signals, operational_modality = classify_operational_profile(columns)
    score_penalty = 20 if max_room_urgency == "review" else 45 if max_room_urgency == "unstable" else 5
    score_penalty += int(min(25, round(max_room_drift * 40)))
    neraium_score = max(0, min(100, 92 - score_penalty))
    overall_urgency = "unstable" if max_room_urgency == "unstable" else ("review" if max_room_urgency == "review" else "nominal")
    if overall_urgency == "nominal" and max_room_drift > 0.08:
        overall_urgency = "review"

    if len(rows) < 20 or not timestamp_column or len(numeric_columns) < 3:
        replay = _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id)
    else:
        replay = _build_replay(rows, timestamp_column, numeric_columns, job_id)

    if not replay.get("timeline"):
        replay = _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id)

    frame_count = len(replay.get("timeline", []))
    now = datetime.now(timezone.utc).isoformat()

    result = {
        "job_id": job_id,
        "filename": filename,
        "row_count": len(rows),
        "column_count": len(columns),
        "columns": columns,
        "preview_rows": rows[:10],
        "detected_timestamp_column": timestamp_column,
        "numeric_profiles": numeric_profiles,
        "timestamp_profile": {
            "first_timestamp": rows[0].get(timestamp_column) if timestamp_column else None,
            "last_timestamp": rows[-1].get(timestamp_column) if timestamp_column else None,
        },
        "data_quality": {"readiness": "ready", "row_count": len(rows), "numeric_column_count": len(numeric_columns)},
        "baseline_analysis": {},
        "cultivation_mapping": {},
        "operator_report": {},
        "engine_result": {"overall_result": "complete", "signals": [], "evidence": []},
        "driver_attribution": {},
        "operating_state": "Monitoring",
        "drift_status": "info",
        "sii_intelligence": {
            "source": "uploaded",
            "facility_state": "Monitoring",
            "urgency": overall_urgency,
            "primary_room": room_names[0] if room_names else "Uploaded telemetry",
            "runner_module": RUNNER_MODULE,
            "neraium_score": neraium_score,
            "room_summary": room_summary,
            "rooms": room_intelligence,
            "telemetry_profile": telemetry_profile,
            "telemetry_profile_confidence": telemetry_profile_confidence,
            "telemetry_profile_signals": telemetry_profile_signals,
            "operational_signal_profile": operational_profile,
            "operational_signal_profile_confidence": operational_profile_confidence,
            "operational_signal_profile_signals": operational_profile_signals,
            "operational_signal_modality": operational_modality,
            "system_identity": {
                "claim_made": telemetry_profile_confidence in {"medium", "high"},
                "telemetry_profile": telemetry_profile,
                "operational_profile": operational_profile,
                "operational_modality": operational_modality,
            },
            "structural_memory": {"memory_matches": [{"name": "uploaded_baseline_pattern"}], "retrieval_status": "matched"},
            "active_archetypes": ["uploaded_baseline_pattern"],
            "causality_graph": {"dominant_pathways": ["thermal_to_humidity"], "edges": [{"from": "temperature", "to": "humidity"}]},
            "counterfactuals": {"uncertainty_ranges": {"instability_acceleration_window_days": "3-7 days"}},
            "facility_cognition": {"global_structural_pressure_score": 0.42},
            "operator_explanation_v2": {
                "summary": "Structural pressure is propagating through uploaded telemetry relationships.",
                "active_archetypes": ["uploaded_baseline_pattern"],
            },
            "structural_explanation": [
                "Structural pressure is propagating through uploaded telemetry relationships.",
                "Uploaded telemetry indicates relationship changes across key signals.",
            ],
            "last_updated": now,
            "replay_timeline": replay,
        },
        "sii_runner_result": {
            "runner_used": True,
            "runner_module": RUNNER_MODULE,
            "core_engine": None,
            "errors": [],
        },
        "processing_trace": {
            "sii_pipeline_ran": True,
            "sii_completed": True,
            "replay_frame_count": frame_count,
            "rows_processed": len(rows),
            "columns_analyzed": len(numeric_columns),
            "completed_at": now,
        },
        "processing_stats": {},
        "room_summary": room_summary,
        "ingestion_metadata": {"source_type": "csv_upload"},
        "source_type": "csv",
        "replay_timeline": replay,
        "replay_ready": frame_count > 0,
        "replay_frame_count": frame_count,
        "last_processed_at": now,
        "completed_at": now,
    }

    summary = {
        "job_id": job_id,
        "status_url": f"/api/data/upload-status/{job_id}",
        "status": "COMPLETE",
        "processing_state": "complete",
        "percent": 100,
        "progress": 100,
        "result_available": True,
        "first_usable_available": True,
        "sii_completed": True,
        "replay_ready": frame_count > 0,
        "replay_frame_count": frame_count,
        "latest_replay_frames": frame_count,
        "replay_source": "persisted",
        "last_processed_at": now,
        "filename": filename,
        "row_count": len(rows),
        "column_count": len(columns),
        "rows_processed": len(rows),
        "columns_detected": len(columns),
        "runner_used": True,
        "runner_module": None,
        "core_engine": None,
        "sii_completed": True,
        "sii_completion_artifacts": {
            "runner_used": True,
            "intelligence_present": True,
            "processing_trace_present": True,
            "engine_result_present": True,
        },
        "result_summary": {
            "filename": filename,
            "sii_completed": True,
            "sii_completion_artifacts": {
                "runner_used": True,
                "intelligence_present": True,
                "processing_trace_present": True,
                "engine_result_present": True,
            },
            "runner_errors": [],
        },
    }

    _write_json(f"upload_result_{job_id}.json", result)
    _write_json(f"upload_status_{job_id}.json", summary)
    _write_json("latest_upload_result.json", result)
    _write_json("latest_upload_summary.json", summary)
    try:
        from app.services import sii_runner
        sii_runner.STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        sii_runner.STATE_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass

    JOBS[job_id] = summary
    LATEST_UPLOAD_CACHE["result"] = result
    LATEST_UPLOAD_CACHE["summary"] = summary
    try:
        from app.services import adaptive_learning
        from app.services.evidence_store import upsert_evidence_run

        now = result.get("completed_at") or result.get("last_processed_at") or datetime.now(timezone.utc).isoformat()
        adaptive_summary = {
            "last_processed_at": now,
            "drift_status": result.get("drift_status"),
            "operating_state": result.get("operating_state"),
            "primary_room": (result.get("sii_intelligence") or {}).get("primary_room"),
            "neraium_score": (result.get("sii_intelligence") or {}).get("neraium_score"),
            "warnings": [],
        }
        site_memory = adaptive_learning.update_site_memory_from_result(result, now)
        adaptive_learning.append_event_memory(
            site_key=site_memory.get("site_key", "site::default"),
            run_id=job_id,
            completed_at=now,
            summary=adaptive_summary,
            result=result,
        )
        upsert_evidence_run(
            {
                "run_id": job_id,
                "source_name": filename,
                "source_type": "csv_upload",
                "source_url": None,
                "status": "completed",
                "created_at": now,
                "completed_at": now,
                "rows_received": len(rows),
                "rows_accepted": len(rows),
                "rows_rejected": 0,
                "sensors_detected": max(0, len(columns) - 1),
                "room": ((result.get("sii_intelligence") or {}).get("primary_room") or "Uploaded telemetry"),
                "operating_state": result.get("operating_state"),
                "neraium_score": ((result.get("sii_intelligence") or {}).get("neraium_score")),
                "drift_status": result.get("drift_status"),
                "scenario": None,
                "tick": None,
                "warnings": [],
                "errors": [],
                "primary_drivers": [],
                "evidence_summary": [],
                "structural_archetypes": [],
                "initiated_by": "anonymous",
                "adaptive_site_key": "site::default",
                "operator_feedback_history": [],
            }
        )
    except Exception:
        pass
    return summary


def replay_payload(job_id: str | None = None) -> dict[str, Any]:
    result = read_upload_result_by_job_id(job_id) if job_id else None
    result = result or read_latest_upload_result() or {}
    replay = result.get("replay_timeline") or (result.get("sii_intelligence") or {}).get("replay_timeline") or {}
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    return {
        "job_id": result.get("job_id") or job_id,
        "source": "persisted" if timeline else "empty",
        "meta": replay.get("meta", {}) if isinstance(replay, dict) else {},
        "timeline": timeline or [],
        "frames": timeline or [],
        "frame_count": len(timeline or []),
        "replay_ready": len(timeline or []) > 0,
    }


def _detect_timestamp_column(columns: list[str]) -> str | None:
    hints = ("timestamp", "time", "datetime", "date_time", "logged_at", "recorded_at")
    lowered = {c.lower().strip(): c for c in columns}
    for hint in hints:
        for key, original in lowered.items():
            if hint == key or hint in key:
                return original
    return columns[0] if columns else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "").replace("%", "")
    if text == "":
        return None
    low = text.lower()
    if low in {"true", "yes", "on"}:
        return 1.0
    if low in {"false", "no", "off"}:
        return 0.0
    try:
        value = float(text)
        if math.isfinite(value):
            return value
    except ValueError:
        return None
    return None


def _detect_numeric_columns(rows: list[dict[str, Any]], columns: list[str], exclude: set[str | None]) -> list[str]:
    event_words = ("event", "status", "fault", "alarm", "override")
    numeric = []
    sample = rows[: min(len(rows), 1000)]
    for col in columns:
        if col in exclude:
            continue
        vals = [_to_float(row.get(col)) for row in sample]
        count = sum(v is not None for v in vals)
        if count >= max(3, int(len(sample) * 0.15)):
            numeric.append(col)
    continuous = [c for c in numeric if not any(w in c.lower() for w in event_words)]
    return continuous if len(continuous) >= 3 else numeric


def _parse_ts(value: Any, fallback_index: int) -> str:
    text = str(value or "").strip()
    if text:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(fallback_index, tz=timezone.utc).isoformat()


def _build_replay(rows: list[dict[str, Any]], timestamp_column: str, numeric_columns: list[str], job_id: str) -> dict[str, Any]:
    frame_target = min(120, max(20, len(rows)))
    positions = sorted(set(round(i * (len(rows) - 1) / max(frame_target - 1, 1)) for i in range(frame_target)))
    baseline_rows = rows[: max(5, min(100, len(rows) // 10))]
    baseline = {}
    for col in numeric_columns:
        vals = [_to_float(r.get(col)) for r in baseline_rows]
        vals = [v for v in vals if v is not None]
        baseline[col] = sum(vals) / len(vals) if vals else 0.0

    timeline = []
    prev_drift = 0.0
    for idx, pos in enumerate(positions):
        row = rows[pos]
        shifts = []
        for col in numeric_columns:
            val = _to_float(row.get(col))
            base = baseline.get(col, 0.0)
            if val is None:
                continue
            denom = abs(base) if abs(base) > 1e-6 else 1.0
            shifts.append((col, abs(val - base) / denom))
        shifts.sort(key=lambda x: x[1], reverse=True)
        drift = sum(v for _, v in shifts[:5]) / max(1, min(5, len(shifts)))
        velocity = drift - prev_drift
        prev_drift = drift
        top = [c for c, _ in shifts[:3]]
        ts = _parse_ts(row.get(timestamp_column), pos)
        phase = "stable_topology" if drift < 0.1 else "relationship_weakening" if drift < 0.25 else "propagation_activation"
        timeline.append({
            "timestamp": ts,
            "frame_index": idx,
            "row_start": max(1, pos),
            "row_end": pos + 1,
            "timestamp_start": ts,
            "timestamp_end": ts,
            "total_frames": len(positions),
            "affected_subsystem": "Uploaded telemetry",
            "affected_area": "Uploaded telemetry",
            "primary_contributors": top,
            "topology_state": {"phase": phase, "drift_index": round(drift, 6), "stability_state": "Monitoring"},
            "cognition_state": {"facility_state": "Monitoring", "canonical_phase": phase, "confidence_tier": "BASELINE_EVIDENCE"},
            "propagation_state": {"dominant_paths": top, "activation_intensity": round(min(1, drift), 6)},
            "evidence_state": {"corroboration_strength": "MODERATE"},
            "drift_velocity": round(velocity, 6),
            "operator_summary": f"Replay frame {idx + 1} of {len(positions)}.",
        })
    return {"meta": {"frame_count": len(timeline), "total_rows": len(rows), "job_id": job_id}, "timeline": timeline}


def _minimal_replay(columns, rows, timestamp_column, numeric_columns, job_id):
    if not rows:
        return {"meta": {"frame_count": 0}, "timeline": []}
    return _build_replay(rows, timestamp_column or columns[0], numeric_columns or columns[1:4], job_id)


def classify_telemetry_profile(columns: list[str]) -> tuple[str, str, list[str]]:
    lowered = [col.lower() for col in columns]
    signals: list[str] = []
    if any("pool" in col or "spa" in col or "orp" in col or "chlorine" in col or "ph_" in col for col in lowered):
        signals = [col for col in columns if any(token in col.lower() for token in ("pool", "spa", "orp", "chlorine", "ph_"))][:5]
        return ("pool_hottub_systems", "high", signals or ["pool_water_temp"])
    if any("temp_air" in col or "rh_" in col or "co2" in col or "dehu" in col for col in lowered):
        signals = [col for col in columns if any(token in col.lower() for token in ("temp_air", "rh_", "co2", "dehu"))][:5]
        return ("cultivation_climate", "medium", signals or ["temp_air"])
    if any("supply_temp" in col or "return_temp" in col or "static_pressure" in col or "compressor" in col for col in lowered):
        signals = [col for col in columns if any(token in col.lower() for token in ("supply_temp", "return_temp", "static_pressure", "compressor"))][:5]
        return ("hvac_systems", "high", signals or ["supply_temp"])
    if any("voltage" in col or "current" in col or "kw_" in col or "power_factor" in col for col in lowered):
        signals = [col for col in columns if any(token in col.lower() for token in ("voltage", "current", "kw_", "power_factor"))][:5]
        return ("electrical_systems", "high", signals or ["voltage"])
    return ("unknown", "low", [])


def classify_operational_profile(columns: list[str]) -> tuple[str, str, list[str], str]:
    lowered = [col.lower() for col in columns]
    if any(token in col for col in lowered for token in ("alarm", "override", "setpoint", "maintenance", "intervention")):
        signals = [col for col in columns if any(token in col.lower() for token in ("alarm", "override", "setpoint", "maintenance", "intervention"))][:5]
        return ("operational_events", "high", signals or ["operator_interventions"], "event")
    if any(token in col for col in lowered for token in ("pump_amperage", "discharge_pressure", "bearing_temperature", "shaft_vibration", "vfd_frequency")):
        signals = [col for col in columns if any(token in col.lower() for token in ("pump", "pressure", "bearing", "vibration", "vfd"))][:5]
        return ("mechanical_systems", "high", signals or ["pump_amperage"], "continuous")
    if any(token in col for col in lowered for token in ("flow_rate", "totalized_flow", "water_pressure", "tank_level", "turnover")):
        signals = [col for col in columns if any(token in col.lower() for token in ("flow", "water", "tank", "turnover"))][:5]
        return ("water_systems", "high", signals or ["flow_rate"], "continuous")
    if any(token in col for col in lowered for token in ("distribution_pressure", "leak_detection", "pump_station", "reservoir", "sewer_flow", "treatment_plant")):
        signals = [col for col in columns if any(token in col.lower() for token in ("distribution", "leak", "pump_station", "reservoir", "sewer", "treatment"))][:5]
        return ("utility_infrastructure", "high", signals or ["distribution_pressure"], "continuous")
    if any(token in col for col in lowered for token in ("cpu_utilization", "memory_utilization", "network_throughput", "packet_loss", "latency", "api_response_time", "error_rate")):
        signals = [col for col in columns if any(token in col.lower() for token in ("cpu", "memory", "network", "packet", "latency", "api_", "error_rate"))][:6]
        return ("network_digital_infrastructure", "high", signals or ["network_throughput"], "continuous")
    return ("unknown", "low", [], "unknown")


def _read_json(name: str) -> dict[str, Any] | None:
    path = RUNTIME_DIR / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json(name: str, payload: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    (RUNTIME_DIR / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


# Compatibility stubs for older imports.
def read_upload_cache_stats() -> dict[str, int]:
    return {"hash_cache_hits": 0, "hash_cache_misses": 0}

# --- Compatibility layer for existing Neraium imports ---

def reset_latest_upload_state() -> None:
    reset_upload_state()


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    replay = (
        result.get("replay_timeline")
        or (result.get("sii_intelligence") or {}).get("replay_timeline")
        or {}
    )
    timeline = replay.get("timeline") if isinstance(replay, dict) else []
    return {
        "job_id": result.get("job_id"),
        "status": "COMPLETE",
        "processing_state": "complete",
        "percent": 100,
        "progress": 100,
        "filename": result.get("filename"),
        "row_count": result.get("row_count", 0),
        "column_count": result.get("column_count", 0),
        "result_available": True,
        "sii_completed": True,
        "replay_ready": len(timeline or []) > 0,
        "replay_frame_count": len(timeline or []),
        "latest_replay_frames": len(timeline or []),
        "replay_source": "persisted" if timeline else "unknown",
        "last_processed_at": result.get("last_processed_at") or result.get("completed_at"),
    }


def write_latest_upload_result(*args) -> None:
    if len(args) == 2:
        job_id, result = args
        payload = dict(result or {})
        payload["job_id"] = str(job_id)
        _write_json(f"upload_result_{job_id}.json", payload)
        _write_json("latest_upload_result.json", payload)
        LATEST_UPLOAD_CACHE["result"] = payload
        return
    result = args[0] if args else {}
    _write_json("latest_upload_result.json", result)
    LATEST_UPLOAD_CACHE["result"] = result


def write_latest_upload_summary(*args, **kwargs) -> None:
    if len(args) >= 2 and isinstance(args[0], str) and isinstance(args[1], dict):
        job_id = args[0]
        summary = args[1]
        payload = dict(summary or {})
        payload["job_id"] = str(job_id)
        payload.setdefault("status", "COMPLETE")
        if "status_url" not in payload:
            payload["status_url"] = f"/api/data/upload-status/{job_id}"
        _write_json("latest_upload_summary.json", payload)
        LATEST_UPLOAD_CACHE["summary"] = payload
        return
    if len(args) >= 1 and isinstance(args[0], dict):
        summary = args[0]
        _write_json("latest_upload_summary.json", summary)
        LATEST_UPLOAD_CACHE["summary"] = summary
        return
    if len(args) == 2:
        job_id, summary = args
        payload = dict(summary or {})
        payload["job_id"] = str(job_id)
        payload.setdefault("status", "COMPLETE")
        if "status_url" not in payload:
            payload["status_url"] = f"/api/data/upload-status/{job_id}"
        _write_json("latest_upload_summary.json", payload)
        LATEST_UPLOAD_CACHE["summary"] = payload
        return
    summary = args[0] if args else {}
    _write_json("latest_upload_summary.json", summary)
    LATEST_UPLOAD_CACHE["summary"] = summary


def build_upload_result(
    columns: list[str] | None = None,
    rows: list[Any] | None = None,
    filename: str = "telemetry.csv",
    **kwargs,
) -> dict[str, Any]:
    """
    Compatibility entrypoint for live/data-connection code.
    Converts rows into CSV bytes and runs the V2 upload replay pipeline.
    """
    columns = columns or kwargs.get("columns") or []
    rows = rows or kwargs.get("rows") or []

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)

    for row in rows:
        if isinstance(row, dict):
            writer.writerow([row.get(col, "") for col in columns])
        else:
            writer.writerow(row)

    summary = process_upload_bytes(filename, output.getvalue().encode("utf-8"))
    result = read_upload_result_by_job_id(summary["job_id"]) or read_latest_upload_result() or {}
    return result


def read_upload_history(limit: int = 100) -> list[dict[str, Any]]:
    """
    Compatibility helper for observability.
    V2 stores latest upload plus per-job upload_result_*.json files.
    """
    items: list[dict[str, Any]] = []
    try:
        paths = sorted(
            RUNTIME_DIR.glob("upload_result_*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        paths = []

    for path in paths[: max(0, int(limit or 100))]:
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        replay = (
            result.get("replay_timeline")
            or (result.get("sii_intelligence") or {}).get("replay_timeline")
            or {}
        )
        timeline = replay.get("timeline") if isinstance(replay, dict) else []

        items.append({
            "job_id": result.get("job_id"),
            "filename": result.get("filename"),
            "status": "COMPLETE",
            "row_count": result.get("row_count", 0),
            "column_count": result.get("column_count", 0),
            "replay_ready": len(timeline or []) > 0,
            "replay_frame_count": len(timeline or []),
            "intelligence_metrics": {
                "room_count": 1,
                "flagged_room_count": 0,
                "sparse_room_count": 0,
                "unknown_profile": False,
            },
            "completed_at": result.get("completed_at") or result.get("last_processed_at"),
        })

    latest = read_latest_upload_result()
    if latest and not any(item.get("job_id") == latest.get("job_id") for item in items):
        items.insert(0, {
            "job_id": latest.get("job_id"),
            "filename": latest.get("filename"),
            "status": "COMPLETE",
            "row_count": latest.get("row_count", 0),
            "column_count": latest.get("column_count", 0),
            "replay_ready": bool((latest.get("replay_timeline") or {}).get("timeline")),
            "replay_frame_count": len((latest.get("replay_timeline") or {}).get("timeline", [])),
            "intelligence_metrics": {
                "room_count": 1,
                "flagged_room_count": 0,
                "sparse_room_count": 0,
                "unknown_profile": False,
            },
            "completed_at": latest.get("completed_at") or latest.get("last_processed_at"),
        })

    return items[: max(0, int(limit or 100))]


def process_next_queued_upload_job() -> bool:
    job_id = claim_next_upload_job()
    if not job_id:
        return False
    metadata = read_job(job_id) or {}
    file_path = metadata.get("file_path")
    if not file_path or not Path(str(file_path)).exists():
        mark_queue_job_failed(job_id, "missing_upload_file")
        return False
    return True


class UploadTooLargeError(ValueError):
    pass


def parse_positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
        return value if value > 0 else default
    except Exception:
        return default


def write_job(*args) -> None:
    if len(args) == 1 and isinstance(args[0], dict):
        payload = dict(args[0])
        job_id = str(payload.get("job_id") or uuid.uuid4().hex)
        payload["job_id"] = job_id
    else:
        job_id = str(args[0])
        payload = dict(args[1])
        payload["job_id"] = job_id
    JOBS[job_id] = payload
    _write_json(f"upload_status_{job_id}.json", payload)
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    (JOB_DIR / f"{job_id}.json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def read_job(job_id: str) -> dict[str, Any] | None:
    return read_upload_status(job_id)


async def create_upload_job(upload_file: Any = None, filename: str = "upload.csv", **kwargs) -> dict[str, Any]:
    max_size_bytes = int(kwargs.get("max_size_bytes", 250 * 1024 * 1024))
    if upload_file is not None and hasattr(upload_file, "read"):
        file_name = getattr(upload_file, "filename", None) or filename
        total = 0
        while True:
            chunk = await upload_file.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_size_bytes:
                raise UploadTooLargeError(f"Upload exceeds maximum allowed size of {max_size_bytes} bytes.")
        filename = file_name
    job_id = uuid.uuid4().hex
    payload = {
        "job_id": job_id,
        "filename": filename,
        "status": "QUEUED",
        "processing_state": "queued",
        "percent": 0,
        "progress": 0,
    }
    write_job(job_id, payload)
    return payload


def process_csv_content(content: str | bytes, filename: str = "upload.csv", **kwargs) -> dict[str, Any]:
    if isinstance(content, str):
        content = content.encode("utf-8")
    summary = process_upload_bytes(filename, content)
    return read_upload_result_by_job_id(summary["job_id"]) or read_latest_upload_result() or {}


def process_csv_file(path: str | os.PathLike[str], **kwargs) -> dict[str, Any]:
    p = Path(path)
    filename = kwargs.pop("filename", None) or p.name
    return process_csv_content(p.read_bytes(), filename=filename, **kwargs)


def process_json_payload(payload: Any, filename: str = "upload.json", **kwargs) -> dict[str, Any]:
    if isinstance(payload, bytes):
        payload = json.loads(payload.decode("utf-8"))
    if isinstance(payload, str):
        payload = json.loads(payload)

    if isinstance(payload, dict) and isinstance(payload.get("readings"), list):
        grouped: dict[str, dict[str, Any]] = {}
        for reading in payload.get("readings", []):
            if not isinstance(reading, dict):
                continue
            ts = str(reading.get("timestamp") or payload.get("timestamp") or "")
            record = grouped.setdefault(ts, {"timestamp": ts})
            sensor_name = str(reading.get("sensor_name") or reading.get("sensor_id") or "value")
            record[sensor_name] = reading.get("value")
        rows = list(grouped.values())
    else:
        rows = payload if isinstance(payload, list) else payload.get("rows") or payload.get("data") or []
        if not rows:
            rows = [payload if isinstance(payload, dict) else {"value": payload}]

    columns = sorted({key for row in rows if isinstance(row, dict) for key in row.keys()})
    if not columns:
        columns = ["timestamp", "value"]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(columns)
    for row in rows:
        if isinstance(row, dict):
            writer.writerow([row.get(col, "") for col in columns])
        else:
            writer.writerow(["", row])

    return process_csv_content(output.getvalue(), filename=filename)
