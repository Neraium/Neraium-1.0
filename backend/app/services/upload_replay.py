from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def detect_timestamp_column(columns: list[str]) -> str | None:
    hints = ("timestamp", "time", "datetime", "date_time", "logged_at", "recorded_at")
    lowered = {c.lower().strip(): c for c in columns}
    for hint in hints:
        for key, original in lowered.items():
            if hint == key or hint in key:
                return original
    return columns[0] if columns else None


def to_float(value: Any) -> float | None:
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


def population_std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def detect_numeric_columns(rows: list[dict[str, Any]], columns: list[str], exclude: set[str | None]) -> list[str]:
    event_words = ("event", "status", "fault", "alarm", "override")
    numeric = []
    sample = rows[: min(len(rows), 1000)]
    for col in columns:
        if col in exclude:
            continue
        vals = [to_float(row.get(col)) for row in sample]
        count = sum(v is not None for v in vals)
        if count >= max(3, int(len(sample) * 0.15)):
            numeric.append(col)
    continuous = [c for c in numeric if not any(w in c.lower() for w in event_words)]
    return continuous if len(continuous) >= 3 else numeric


def parse_ts(value: Any, fallback_index: int) -> str:
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


def build_replay(
    rows: list[dict[str, Any]],
    timestamp_column: str,
    numeric_columns: list[str],
    job_id: str,
    relationship_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    frame_target = min(120, max(20, len(rows)))
    positions = sorted(set(round(i * (len(rows) - 1) / max(frame_target - 1, 1)) for i in range(frame_target)))
    baseline_rows = rows[: max(5, min(100, len(rows) // 10))]
    baseline = {}
    for col in numeric_columns:
        vals = [to_float(r.get(col)) for r in baseline_rows]
        vals = [v for v in vals if v is not None]
        baseline[col] = sum(vals) / len(vals) if vals else 0.0

    timeline = []
    prev_drift = 0.0
    for idx, pos in enumerate(positions):
        row = rows[pos]
        shifts = []
        for col in numeric_columns:
            val = to_float(row.get(col))
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
        ts = parse_ts(row.get(timestamp_column), pos)
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
    top_relationship_changes = (relationship_model or {}).get("top_relationship_changes")
    if timeline and isinstance(top_relationship_changes, list) and top_relationship_changes:
        timeline[-1]["relationship_changes"] = [item.get("summary", "") for item in top_relationship_changes if isinstance(item, dict)]
        timeline[-1]["relationship_change_evidence_refs"] = top_relationship_changes
    return {"meta": {"frame_count": len(timeline), "total_rows": len(rows), "job_id": job_id}, "timeline": timeline}


def minimal_replay(
    columns: list[str],
    rows: list[dict[str, Any]],
    timestamp_column: str | None,
    numeric_columns: list[str],
    job_id: str,
    relationship_model: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not rows:
        return {"meta": {"frame_count": 0}, "timeline": []}
    return build_replay(rows, timestamp_column or columns[0], numeric_columns or columns[1:4], job_id, relationship_model)
