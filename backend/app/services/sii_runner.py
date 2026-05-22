from __future__ import annotations

import inspect
import json
import time
from collections import deque
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.data_quality import parse_numeric_value

import numpy as np


RUNNER_MODULE = "app.services.sii_runner.BackendSiiRunner"
RUNNER_CALLABLE = "app.services.sii_runner.BackendSiiRunner.ingest"
CORE_ENGINE = "app.engine.analysis.run_engine_analysis"
VALIDATION_RUNNER = "legacy.validation.fd004.FD004ValidationRunner"
STATE_PATH = get_settings().runtime_dir / "latest_sii_state.json"
LEGACY_VALIDATION_FILE = next(
    (path for path in Path(__file__).resolve().parents[2].glob("*/sii_fd004_validation.py") if path.is_file()),
    None,
)
STATE_REQUIRED_FIELDS = {
    "facility_state",
    "rooms",
    "priority_room",
    "neraium_score",
    "primary_driver",
    "supporting_evidence",
    "structural_explanation",
    "confidence_basis",
    "last_processed_at",
    "source",
}

_IMPORT_ERROR: str | None = None
_SII_ENGINE_ADAPTER: Any = None

def configure_runtime_dir(runtime_dir: Path) -> None:
    global STATE_PATH
    STATE_PATH = runtime_dir / "latest_sii_state.json"


class BackendSiiRunner:
    """Backend-native telemetry runner used by production uploads and readiness checks."""

    def __init__(self, *, baseline_window: int = 12, recent_window: int = 12) -> None:
        self.baseline_window = max(2, baseline_window)
        self.recent_window = max(2, recent_window)
        self._history: list[np.ndarray] = []
        self._instability_history: deque[float] = deque(maxlen=20)
        self._velocity_history: deque[float] = deque(maxlen=20)
        self._regime_history: deque[str] = deque(maxlen=20)

    def ingest(
        self,
        *,
        sensor_vector: np.ndarray,
        timestamp: float,
        asset_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        vector = np.asarray(sensor_vector, dtype=float)
        self._history.append(vector)

        baseline_vectors, recent_vectors = self._windowed_history()
        baseline_mean = np.nan_to_num(np.nanmean(baseline_vectors, axis=0), nan=0.0)
        recent_mean = np.nan_to_num(np.nanmean(recent_vectors, axis=0), nan=0.0)
        safe_baseline = np.where(np.abs(baseline_mean) < 1e-6, 1.0, np.abs(baseline_mean))
        normalized_delta = np.abs(recent_mean - baseline_mean) / safe_baseline
        structural_drift = float(np.clip(np.nan_to_num(np.nanmean(normalized_delta), nan=0.0), 0.0, 1.5))

        if len(self._history) >= 2:
            last_step = np.abs(self._history[-1] - self._history[-2]) / safe_baseline
            transition_pressure = float(np.clip(np.nan_to_num(np.nanmean(last_step), nan=0.0), 0.0, 1.5))
        else:
            transition_pressure = 0.0

        variability = float(np.nan_to_num(np.nanstd(recent_vectors), nan=0.0)) if recent_vectors.size else 0.0
        variability_pressure = float(np.clip(variability / max(float(np.nanmean(safe_baseline)), 1.0), 0.0, 1.0))
        instability_score = float(
            np.clip(structural_drift * 0.55 + transition_pressure * 0.3 + variability_pressure * 0.15, 0.0, 1.0)
        )
        instability_components = {
            "drift": round(float(np.clip(structural_drift, 0.0, 1.0)), 6),
            "relationship_degradation": round(float(np.clip(transition_pressure, 0.0, 1.0)), 6),
            "entropy_growth": round(float(np.clip(variability_pressure, 0.0, 1.0)), 6),
        }
        velocity = instability_score - (self._instability_history[-1] if self._instability_history else instability_score)

        regime, urgency = classify_state(len(self._history), instability_score, transition_pressure)
        confidence = confidence_from_history(len(self._history), vector)

        self._instability_history.append(instability_score)
        self._velocity_history.append(float(velocity))
        self._regime_history.append(regime)

        return {
            "asset_id": asset_id,
            "run_id": run_id,
            "timestamp": timestamp,
            "regime": regime,
            "urgency": urgency,
            "instability_score": round(instability_score, 6),
            "instability_components": instability_components,
            "structural_drift": round(structural_drift, 6),
            "transition_pressure": round(transition_pressure, 6),
            "confidence": round(confidence, 6),
            "instability_history": [round(value, 6) for value in self._instability_history],
            "velocity_history": [round(value, 6) for value in self._velocity_history],
            "regime_history": list(self._regime_history),
        }

    def _windowed_history(self) -> tuple[np.ndarray, np.ndarray]:
        if len(self._history) == 1:
            only = np.vstack(self._history)
            return only, only

        recent_count = min(self.recent_window, len(self._history))
        recent_vectors = np.vstack(self._history[-recent_count:])
        baseline_source = self._history[:-recent_count]
        if not baseline_source:
            split_index = max(1, len(self._history) // 2)
            baseline_source = self._history[:split_index]
        baseline_vectors = np.vstack(baseline_source[-self.baseline_window :])
        return baseline_vectors, recent_vectors


def _try_import_runner() -> None:
    global _IMPORT_ERROR, _SII_ENGINE_ADAPTER
    if _SII_ENGINE_ADAPTER is not None or _IMPORT_ERROR is not None:
        return

    _SII_ENGINE_ADAPTER = BackendSiiRunner
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
    last_processed_at = state.get("last_processed_at") if state else None
    parsed_last_processed_at = parse_state_timestamp(last_processed_at)
    state_age_seconds = None
    if parsed_last_processed_at is not None:
        state_age_seconds = max(0, int((datetime.now(UTC) - parsed_last_processed_at).total_seconds()))
    return {
        "runner_available": runner_available(),
        "runner_module": identity["runner_module"],
        "runner_file": identity["runner_file"],
        "core_engine": identity["core_engine"],
        "core_engine_file": identity["core_engine_file"],
        "validation_runner": identity["validation_runner"],
        "validation_runner_file": identity["validation_runner_file"],
        "state_available": state is not None,
        "last_processed_at": last_processed_at,
        "state_timestamp_valid": last_processed_at is None or parsed_last_processed_at is not None,
        "state_age_seconds": state_age_seconds,
        "source": state.get("source") if state else "none",
        "same_engine_family_as_validation": True,
        "same_exact_fd004_validation_runner": False,
        "note": (
            "Production uploads use the backend-native SII runner. "
            "Legacy FD004 validation remains isolated from production imports."
        ),
        "import_error": runner_import_error(),
    }


def runner_identity() -> dict[str, str | None]:
    _try_import_runner()
    core_file = validation_file = runner_file = None
    if _SII_ENGINE_ADAPTER is not None:
        runner_file = inspect.getsourcefile(_SII_ENGINE_ADAPTER)
        try:
            core_file = inspect.getsourcefile(BackendSiiRunner)
        except Exception:
            core_file = None
    if LEGACY_VALIDATION_FILE is not None and LEGACY_VALIDATION_FILE.exists():
        validation_file = str(LEGACY_VALIDATION_FILE)
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
    projected_hours = project_time_to_failure_hours_from_state(latest_state)
    instability_index = build_instability_index(latest_state)
    latest_state = {
        **latest_state,
        "instability_index": instability_index,
        "projected_time_to_failure_hours": projected_hours,
        "projected_time_to_failure": format_projected_time_to_failure_hours(projected_hours),
    }
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
            parsed_value = parse_numeric_value(raw_value)
            if parsed_value is None:
                values.append(float("nan"))
            else:
                values.append(parsed_value)
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
            numeric_value = parse_numeric_value(raw_value)
            if numeric_value is not None:
                return numeric_value
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
        "latest_instability_components": latest.get("instability_components", {}),
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
        "projected_time_to_failure": format_projected_time_to_failure_hours(
            project_time_to_failure_hours_from_state(latest_state)
        ),
        "projected_time_to_failure_hours": project_time_to_failure_hours_from_state(latest_state),
        "last_updated": now_iso(),
        "confidence": round(float(latest_state.get("confidence", 0.0)) * 100),
    }
    instability_index = (
        latest_state.get("instability_index")
        if isinstance(latest_state.get("instability_index"), dict)
        else build_instability_index(latest_state)
    )
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
        "projected_time_to_failure": room["projected_time_to_failure"],
        "projected_time_to_failure_hours": room["projected_time_to_failure_hours"],
        "runner_module": RUNNER_MODULE,
        "core_engine": CORE_ENGINE,
        "latest_state": latest_state,
        "instability_index": instability_index,
        "last_updated": room["last_updated"],
        "last_processed_at": room["last_updated"],
        "processing_trace": processing_trace,
    }


def build_instability_index(latest_state: dict[str, Any]) -> dict[str, Any]:
    components = latest_state.get("instability_components", {}) if isinstance(latest_state, dict) else {}
    drift = float(components.get("drift", latest_state.get("structural_drift", 0.0)))
    relationship = float(components.get("relationship_degradation", latest_state.get("transition_pressure", 0.0)))
    entropy = float(components.get("entropy_growth", 0.0))
    causal = float(latest_state.get("confidence", 0.0))
    topology = float(np.clip((drift * 0.6) + (relationship * 0.4), 0.0, 1.0))
    score = float(np.clip((drift * 0.35) + (relationship * 0.25) + (entropy * 0.15) + (causal * 0.15) + (topology * 0.10), 0.0, 1.0))
    return {
        "score": round(score, 6),
        "components": {
            "drift": round(float(np.clip(drift, 0.0, 1.0)), 6),
            "relationship_degradation": round(float(np.clip(relationship, 0.0, 1.0)), 6),
            "entropy_growth": round(float(np.clip(entropy, 0.0, 1.0)), 6),
            "causal_evidence": round(float(np.clip(causal, 0.0, 1.0)), 6),
            "topology_propagation": round(float(np.clip(topology, 0.0, 1.0)), 6),
        },
        "model": {"name": "sii_instability_index", "version": "phase1-v1"},
    }


def build_runner_evidence(
    latest_state: dict[str, Any],
    columns_used: list[str],
    driver_attribution: dict[str, Any],
    engine_result: dict[str, Any],
) -> list[str]:
    evidence = [
        f"Backend SII runner ingested {len(columns_used)} numeric telemetry channels.",
        f"Backend SII runner reported {latest_state.get('regime', 'unknown')} regime and {latest_state.get('urgency', 'unknown')} urgency.",
        f"Instability score {round(float(latest_state.get('instability_score', 0.0)), 4)} with structural drift {round(float(latest_state.get('structural_drift', 0.0)), 4)}.",
    ]
    if driver_attribution.get("driver_category"):
        evidence.append(f"Driver attribution category: {driver_attribution['driver_category']}.")
    for item in engine_result.get("evidence", [])[:2]:
        if item.get("type"):
            evidence.append("Environmental coupling is less consistent than the room's recent baseline.")
    return evidence


def read_latest_sii_state() -> dict[str, Any] | None:
    if not STATE_PATH.exists():
        return None
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return state if is_valid_latest_sii_state(state) else None


def write_latest_sii_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = STATE_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    last_error: OSError | None = None
    for attempt in range(6):
        try:
            temp_path.replace(STATE_PATH)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.02 * (attempt + 1))
    if last_error is not None:
        raise last_error


def reset_latest_sii_state() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        STATE_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def is_valid_latest_sii_state(state: Any) -> bool:
    if not isinstance(state, dict):
        return False
    if not STATE_REQUIRED_FIELDS <= set(state):
        return False
    if not isinstance(state.get("rooms"), list):
        return False
    if not isinstance(state.get("supporting_evidence"), list):
        return False
    if not isinstance(state.get("structural_explanation"), list):
        return False
    return True


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
 
 
def parse_state_timestamp(raw_value: Any) -> datetime | None: 
    if not raw_value: 
        return None 
    try: 
        parsed = datetime.fromisoformat(str(raw_value).replace("Z", "+00:00")) 
    except ValueError: 
        return None 
    if parsed.tzinfo is None: 
        parsed = parsed.replace(tzinfo=UTC) 
    return parsed.astimezone(UTC) 


def classify_state(history_length: int, instability_score: float, transition_pressure: float) -> tuple[str, str]: 
    if history_length < 3: 
        return "WARMUP", "NOMINAL" 
    if instability_score >= 0.72 or transition_pressure >= 0.9: 
        return "LOCK_IN", "CRITICAL" 
    if instability_score >= 0.52 or transition_pressure >= 0.62:
        return "UNSTABLE", "ALERT"
    if instability_score >= 0.24 or transition_pressure >= 0.28:
        return "TRANSITION", "WATCH"
    return "STABLE", "NOMINAL"


def confidence_from_history(history_length: int, vector: np.ndarray) -> float: 
    completeness = float(np.mean(~np.isnan(vector))) if vector.size else 0.0 
    history_factor = min(history_length / 12, 1.0) 
    return max(0.35, min(0.94, 0.4 + history_factor * 0.35 + completeness * 0.19)) 
 
 
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
    return f"Backend SII runner confidence {confidence}% from baseline and telemetry history depth."


def project_time_to_failure_hours_from_state(latest_state: dict[str, Any]) -> int:
    urgency = normalize_urgency(str(latest_state.get("urgency", "NOMINAL")))
    base_hours = {"unstable": 8, "elevated": 36, "review": 72, "nominal": 504}.get(urgency, 72)
    instability_score = float(latest_state.get("instability_score", 0.0))
    structural_drift = float(latest_state.get("structural_drift", 0.0))
    transition_pressure = float(latest_state.get("transition_pressure", 0.0))
    risk_factor = instability_score * 0.5 + structural_drift * 0.3 + transition_pressure * 0.2
    scaled = int(base_hours * max(0.25, 1.0 - min(max(risk_factor, 0.0), 0.9)))
    return max(4, scaled)


def format_projected_time_to_failure_hours(hours: int) -> str:
    if hours <= 12:
        return f"Approximately {hours} hours at current trajectory"
    if hours <= 72:
        return f"Approximately {max(1, round(hours / 24))} days at current trajectory"
    return f"More than {max(1, round(hours / 168))} weeks at current trajectory"
