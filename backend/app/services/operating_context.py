from __future__ import annotations

import math
from statistics import median
from typing import Any


SUMMARY_VERSION = "operating-context-input-v1"
SUMMARY_ROLES = {
    "process_demand",
    "control_command",
    "equipment_enable",
    "equipment_state",
    "setpoint",
    "environmental_temperature",
}


def build_operating_context_inputs(
    *,
    rows: list[dict[str, Any]],
    telemetry_signal_catalog: dict[str, dict[str, Any]],
    baseline_model: dict[str, Any],
    comparison_window: dict[str, Any],
) -> dict[str, Any]:
    """Persist generic context summaries while complete comparison rows are available."""
    baseline_catalog = ((baseline_model.get("telemetry_schema") or {}).get("signal_catalog") or {})
    baseline_characteristics = baseline_model.get("signal_characteristics") or {}
    baseline = _baseline_summaries(baseline_catalog, baseline_characteristics)
    comparison = _row_summaries(rows, telemetry_signal_catalog)
    baseline_timestamp = baseline_model.get("timestamp_quality") or {}
    return {
        "schema_version": SUMMARY_VERSION,
        "baseline": baseline,
        "comparison": comparison,
        "windows": {
            "baseline": {
                "start": baseline_timestamp.get("first_timestamp"),
                "end": baseline_timestamp.get("last_timestamp"),
            },
            "comparison": {
                "start": comparison_window.get("first_timestamp"),
                "end": comparison_window.get("last_timestamp"),
            },
        },
        "source": "analysis_metadata",
    }


def _signals_by_role(catalog: dict[str, dict[str, Any]]) -> dict[str, tuple[str, dict[str, Any]]]:
    candidates: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for source, metadata in catalog.items():
        role = str(metadata.get("canonical_role") or "")
        if role in SUMMARY_ROLES:
            candidates.setdefault(role, []).append((str(source), metadata))
    # Ambiguous roles are deliberately unavailable rather than selected by tag name.
    return {role: items[0] for role, items in candidates.items() if len(items) == 1}


def _baseline_summaries(
    catalog: dict[str, dict[str, Any]], characteristics: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for role, (source, metadata) in _signals_by_role(catalog).items():
        distribution = (characteristics.get(source) or {}).get("distribution") or {}
        if not distribution:
            continue
        summaries[role] = _summary(
            source=source,
            metadata=metadata,
            count=(characteristics.get(source) or {}).get("samples"),
            minimum=distribution.get("minimum"),
            maximum=distribution.get("maximum"),
            mean=distribution.get("mean"),
            context_source="baseline_model",
        )
    return summaries


def _row_summaries(
    rows: list[dict[str, Any]], catalog: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for role, (source, metadata) in _signals_by_role(catalog).items():
        values = [value for row in rows if (value := _finite(row.get(source))) is not None]
        if not values:
            continue
        early_size = max(1, len(values) // 10)
        summaries[role] = {
            **_summary(
                source=source,
                metadata=metadata,
                count=len(values),
                minimum=min(values),
                maximum=max(values),
                mean=sum(values) / len(values),
                context_source="telemetry",
            ),
            "early_median": round(median(values[:early_size]), 8),
            "late_median": round(median(values[-early_size:]), 8),
            "segment_medians": [
                round(median(values[start:end]), 8)
                for index in range(5)
                if (start := index * len(values) // 5) < (end := (index + 1) * len(values) // 5)
            ],
        }
    return summaries


def _summary(
    *, source: str, metadata: dict[str, Any], count: Any, minimum: Any, maximum: Any, mean: Any,
    context_source: str,
) -> dict[str, Any]:
    return {
        "canonical_role": metadata.get("canonical_role"),
        "source_variable": source,
        "unit": metadata.get("engineering_units") or None,
        "count": int(count or 0),
        "mean": _rounded(mean),
        "min": _rounded(minimum),
        "max": _rounded(maximum),
        "source": context_source,
    }


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _rounded(value: Any) -> float | None:
    number = _finite(value)
    return round(number, 8) if number is not None else None
