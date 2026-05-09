from __future__ import annotations

import json
import os
import inspect
import sys
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np


RUNNER_MODULE = "neraium_core.sii_engine_adapter.SIIEngineAdapter"
RUNNER_CALLABLE = "neraium_core.sii_engine_adapter.SIIEngineAdapter.ingest"
CORE_ENGINE = "neraium_core.sii_engine_unified.SIIEngine"
VALIDATION_RUNNER = "neraium_core.sii_fd004_validation.FD004ValidationRunner"
STATE_PATH = Path(__file__).resolve().parents[1] / "runtime" / "latest_sii_state.json"

_IMPORT_ERROR: str | None = None
_SII_ENGINE_ADAPTER: Any = None
_FD004_VALIDATION_RUNNER: Any = None


def _try_import_runner() -> None:
    global _IMPORT_ERROR, _SII_ENGINE_ADAPTER, _FD004_VALIDATION_RUNNER
    if _SII_ENGINE_ADAPTER is not None or _IMPORT_ERROR is not None:
        return

    local_core_path = os.getenv("NERAIUM_CORE_PATH")
    if local_core_path and local_core_path not in sys.path:
        sys.path.insert(0, local_core_path)

    try:
        from neraium_core.sii_engine_adapter import SIIEngineAdapter
        from neraium_core.sii_fd004_validation import FD004ValidationRunner
    except Exception as exc:  # pragma: no cover - exercised through status payloads
        _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
        return

    _SII_ENGINE_ADAPTER = SIIEngineAdapter
    _FD004_VALIDATION_RUNNER = FD004ValidationRunner
    _IMPORT_ERROR = None


def runner_available() -> bool:
    _try_import_runner()
    return _SII_ENGINE_ADAPTER is not None


def runner_import_error() -> str | None:
    _try_import_runner()
    return _IMPORT_ERROR


def build_runner_status() -> dict[str, Any]:
    state = read_latest_sii_state()
    identity = runner_identity()
    return {
        "runner_available": runner_available(),
        "runner_module": identity["runner_module"],
        "runner_file": identity["runner_file"],
        "core_engine": identity["core_engine"],
        "core_engine_file": identity["core_engine_file"],
        "validation_runner": identity["validation_runner"],
        "validation_runner_file": identity["validation_runner_file"],
        "state_available": state is not None,
        "last_processed_at": state.get("last_processed_at") if state else None,
        "source": state.get("source") if state else "sample",
        "same_engine_family_as_validation": True,
        "same_exact_fd004_validation_runner": False,
        "note": (
            "Production uploads use SIIEngineAdapter backed by SIIEngine. "
            "FD004ValidationRunner remains a validation harness."
        ),
        "import_error": runner_import_error(),
    }


def runner_identity() -> dict[str, str | None]:
    _try_import_runner()
    core_file = validation_file = runner_file = None
    if _SII_ENGINE_ADAPTER is not None:
        runner_file = inspect.getsourcefile(_SII_ENGINE_ADAPTER)
        try:
            from neraium_core.sii_engine_unified import SIIEngine

            core_file = inspect.getsourcefile(SIIEngine)
        except Exception:
            core_file = None
    if _FD004_VALIDATION_RUNNER is not None:
        validation_file = inspect.getsourcefile(_FD004_VALIDATION_RUNNER)
    return {
        "runner_module": RUNNER_MODULE,
        "runner_callable": RUNNER_CALLABLE,
        "runner_file": runner_file,
        "core_engine": CORE_ENGINE,
        "core_engine_file": core_file,
        "validation_runner": VALIDATION_RUNNER,
        "validation_runner_file": validation_file,
    }


def run_sii_runner(
    *,
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
    timestamp_column: str | None,
    primary_room: str,
    driver_attribution: dict[str, Any],
    engine_result: dict[str, Any],
    processing_trace: dict[str, Any],
) -> dict[str, Any]:
    _try_import_runner()
    base_result: dict[str, Any] = {
        "runner_used": False,
        "runner_module": RUNNER_MODULE,
        "core_engine": CORE_ENGINE,
        "rows_processed": 0,
        "columns_used": [],
        "sensor_vector_count": 0,
        "output_summary": {},
        "latest_state": None,
        "evidence": [],
        "errors": [],
    }
    if _SII_ENGINE_ADAPTER is None:
        base_result["errors"].append(runner_import_error() or "SII runner is not importable.")
        return base_result

    vector_rows = build_sensor_vectors(columns, rows, numeric_profiles)
    base_result["columns_used"] = vector_rows["columns_used"]
    base_result["sensor_vector_count"] = len(vector_rows["vectors"])
    if not vector_rows["vectors"]:
        base_result["errors"].append("No complete numeric sensor vectors were available for SII runner ingestion.")
        return base_result

    baseline_window = min(50, max(2, min(12, len(vector_rows["vectors"]) // 2 or 2)))
    adapter = _SII_ENGINE_ADAPTER(baseline_window=baseline_window, recent_window=baseline_window)
    states: list[dict[str, Any]] = []
    run_id = f"upload-{datetime.now(UTC).timestamp()}"

    try:
        for index, vector in enumerate(vector_rows["vectors"]):
            timestamp = parse_timestamp(columns, rows[vector_rows["row_indexes"][index]], timestamp_column, index)
            state = adapter.ingest(
                sensor_vector=np.asarray(vector, dtype=float),
                timestamp=timestamp,
                asset_id=primary_room or "uploaded_facility",
                run_id=run_id,
            )
            states.append(to_plain_dict(state))
    except Exception as exc:
        base_result["errors"].append(f"{type(exc).__name__}: {exc}")
        return base_result

    latest_state = states[-1]
    evidence = build_runner_evidence(latest_state, vector_rows["columns_used"], driver_attribution, engine_result)
    output_summary = summarize_runner_outputs(states)
    processing_trace = {
        **processing_trace,
        "sii_runner_ran": True,
        "sii_runner_module": RUNNER_MODULE,
        "sii_core_engine": CORE_ENGINE,
        "sensor_vector_count": len(states),
    }

    base_result.update(
        {
            "runner_used": True,
            "rows_processed": len(rows),
            "output_summary": output_summary,
            "latest_state": latest_state,
            "evidence": evidence,
        }
    )
    write_latest_sii_state(
        build_runtime_state(
            latest_state=latest_state,
            primary_room=primary_room,
            evidence=evidence,
            driver_attribution=driver_attribution,
            processing_trace=processing_trace,
            output_summary=output_summary,
        )
    )
    return base_result


def build_sensor_vectors(
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    numeric_columns = [
        profile["column"]
        for profile in numeric_profiles
        if profile.get("column") in columns
    ]
    column_indexes = [columns.index(column) for column in numeric_columns]
    vectors: list[list[float]] = []
    row_indexes: list[int] = []
    for row_index, row in enumerate(rows):
        values: list[float] = []
        for column_index in column_indexes:
            raw_value = row[column_index].strip() if column_index < len(row) else ""
            try:
                values.append(float(raw_value))
            except ValueError:
                values.append(float("nan"))
        if values and not all(np.isnan(value) for value in values):
            vectors.append(values)
            row_indexes.append(row_index)
    return {
        "columns_used": numeric_columns,
        "vectors": vectors,
        "row_indexes": row_indexes,
    }


def parse_timestamp(columns: list[str], row: list[str], timestamp_column: str | None, fallback_index: int) -> float:
    if timestamp_column and timestamp_column in columns:
        column_index = columns.index(timestamp_column)
        raw_value = row[column_index].strip() if column_index < len(row) else ""
        if raw_value:
            try:
                return float(raw_value)
            except ValueError:
                try:
                    parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=UTC)
                    return parsed.timestamp()
                except ValueError:
                    pass
    return float(fallback_index + 1)


def summarize_runner_outputs(states: list[dict[str, Any]]) -> dict[str, Any]:
    latest = states[-1] if states else {}
    scores = [float(state.get("instability_score", 0.0)) for state in states]
    return {
        "frames_processed": len(states),
        "latest_regime": latest.get("regime"),
        "latest_urgency": latest.get("urgency"),
        "latest_instability_score": latest.get("instability_score"),
        "max_instability_score": round(max(scores), 6) if scores else 0.0,
        "latest_structural_drift": latest.get("structural_drift"),
        "latest_confidence": latest.get("confidence"),
    }


def build_runtime_state(
    *,
    latest_state: dict[str, Any],
    primary_room: str,
    evidence: list[str],
    driver_attribution: dict[str, Any],
    processing_trace: dict[str, Any],
    output_summary: dict[str, Any],
) -> dict[str, Any]:
    urgency = normalize_urgency(str(latest_state.get("urgency", "NOMINAL")))
    score = max(0, min(100, round(100 - float(latest_state.get("instability_score", 0.0)) * 100)))
    room_state = room_state_from_regime(str(latest_state.get("regime", "WARMUP")))
    primary_driver = driver_attribution.get("likely_driver") or "SII structural telemetry pattern"
    structural_explanation = [
        f"SII regime is {latest_state.get('regime', 'unknown')} with urgency {latest_state.get('urgency', 'unknown')}.",
        f"Structural drift score is {round(float(latest_state.get('structural_drift', 0.0)), 4)}.",
        f"Transition pressure is {round(float(latest_state.get('transition_pressure', 0.0)), 4)}.",
    ]
    room = {
        "room": primary_room,
        "room_state": room_state,
        "urgency": urgency,
        "intervention_window": window_from_urgency(urgency),
        "primary_driver": primary_driver,
        "supporting_evidence": evidence,
        "relationship_evidence": evidence[:2],
        "structural_explanation": structural_explanation,
        "confidence_basis": confidence_basis(latest_state),
        "recommended_operator_review": driver_attribution.get("next_operator_move") or next_move_from_urgency(urgency),
        "what_to_check": driver_attribution.get("what_to_check", []) or [next_move_from_urgency(urgency)],
        "why_flagged": evidence[0] if evidence else "SII runner processed uploaded telemetry.",
        "baseline_comparison": f"SII latest structural drift: {output_summary.get('latest_structural_drift', 0.0)}",
        "observed_persistence": f"SII processed {output_summary.get('frames_processed', 0)} telemetry frames.",
        "last_updated": now_iso(),
        "confidence": round(float(latest_state.get("confidence", 0.0)) * 100),
    }
    return {
        "source": "uploaded",
        "mode": "live",
        "facility_state": room_state,
        "room_state": room_state,
        "urgency": urgency,
        "rooms": [room],
        "priority_room": primary_room,
        "primary_room": primary_room,
        "neraium_score": score,
        "primary_driver": primary_driver,
        "structural_explanation": structural_explanation,
        "supporting_evidence": evidence,
        "relationship_evidence": evidence[:2],
        "intervention_window": room["intervention_window"],
        "confidence_basis": room["confidence_basis"],
        "recommended_operator_review": room["recommended_operator_review"],
        "next_operator_move": room["recommended_operator_review"],
        "what_to_check": room["what_to_check"],
        "why_flagged": room["why_flagged"],
        "baseline_comparison": room["baseline_comparison"],
        "observed_persistence": room["observed_persistence"],
        "runner_module": RUNNER_MODULE,
        "core_engine": CORE_ENGINE,
        "latest_state": latest_state,
        "last_updated": room["last_updated"],
        "last_processed_at": room["last_updated"],
        "processing_trace": processing_trace,
    }


def build_runner_evidence(
    latest_state: dict[str, Any],
    columns_used: list[str],
    driver_attribution: dict[str, Any],
    engine_result: dict[str, Any],
) -> list[str]:
    evidence = [
        f"SIIEngineAdapter ingested {len(columns_used)} numeric telemetry channels.",
        f"Unified SII core reported {latest_state.get('regime', 'unknown')} regime and {latest_state.get('urgency', 'unknown')} urgency.",
        f"Instability score {round(float(latest_state.get('instability_score', 0.0)), 4)} with structural drift {round(float(latest_state.get('structural_drift', 0.0)), 4)}.",
    ]
    if driver_attribution.get("driver_category"):
        evidence.append(f"Driver attribution category: {driver_attribution['driver_category']}.")
    for item in engine_result.get("evidence", [])[:2]:
        if item.get("type"):
            evidence.append(f"Existing upload engine evidence: {item['type']}.")
    return evidence


def read_latest_sii_state() -> dict[str, Any] | None:
    if not STATE_PATH.exists():
        return None
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_latest_sii_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def to_plain_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return dict(value)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_urgency(urgency: str) -> str:
    normalized = urgency.lower()
    if normalized == "critical":
        return "unstable"
    if normalized == "alert":
        return "elevated"
    if normalized == "watch":
        return "review"
    return "nominal"


def room_state_from_regime(regime: str) -> str:
    return {
        "LOCK_IN": "Needs action",
        "UNSTABLE": "Needs action",
        "TRANSITION": "Drift observed",
        "STABLE": "Stable",
        "WARMUP": "Monitoring",
    }.get(regime, "Monitoring")


def window_from_urgency(urgency: str) -> str:
    return {
        "unstable": "8 hours",
        "elevated": "2 days",
        "review": "6 days",
        "nominal": "3 weeks",
    }.get(urgency, "Monitoring")


def next_move_from_urgency(urgency: str) -> str:
    if urgency == "unstable":
        return "Escalate room review"
    if urgency in {"elevated", "review"}:
        return "Review SII runner evidence"
    return "Continue monitoring"


def confidence_basis(latest_state: dict[str, Any]) -> str:
    confidence = round(float(latest_state.get("confidence", 0.0)) * 100)
    return f"Unified SII core confidence {confidence}% from baseline and telemetry history depth."
