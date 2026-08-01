from __future__ import annotations

import hashlib
import html
import io
import json
import math
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.core.config import get_settings
from app.services.runtime_db import (
    list_latest_payloads_prefix,
    mutate_latest_payload,
    now_iso,
    read_latest_payload,
    upsert_latest_payload,
)


ASSESSMENT_PREFIX = "pilot_assessment:"
CONTRACT_VERSION = "golden-nugget-assessment.v1"
FEEDBACK_CATEGORIES = {
    "useful",
    "not_useful",
    "known_operational_change",
    "possible_sensor_issue",
    "needs_investigation",
}
MIN_BASELINE_ROWS = 48
MIN_BASELINE_HOURS = 12
MIN_MODE_SAMPLES = 18
MAX_SIGNAL_MAPPINGS = 40
MAX_RELATIONSHIPS = 160
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
LEGACY_PUMP_FLOW_TITLE = "Pump demand no longer matches hydraulic response"
PUMP_FLOW_TITLE = "Pump demand no longer matches expected flow response"
PUMP_FLOW_OPERATIONAL_SUMMARY = (
    "The system required a different level of pump demand to produce the hydraulic response "
    "learned during the baseline period."
)
METHODOLOGY_LIMITATION = (
    "Neraium identifies persistent changes in learned operating relationships. "
    "It does not independently diagnose equipment failure or replace engineering judgment."
)


class AssessmentError(ValueError):
    pass


def _assessment_key(assessment_id: str) -> str:
    if not _SAFE_ID.fullmatch(str(assessment_id or "")):
        raise AssessmentError("invalid_assessment_id")
    return f"{ASSESSMENT_PREFIX}{assessment_id}"


def _assessment_dir(assessment_id: str) -> Path:
    target = get_settings().runtime_dir / "pilot_assessments" / assessment_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def _presentation_title(value: Any) -> str:
    title = str(value or "")
    return PUMP_FLOW_TITLE if title == LEGACY_PUMP_FLOW_TITLE else title


def _presentation_quality_note(value: Any) -> str:
    note = str(value or "").strip().rstrip(".")
    comparison_match = re.fullmatch(
        r"Comparison-period quality is limited for:\s*(.+)",
        note,
        flags=re.IGNORECASE,
    )
    if not comparison_match:
        return note
    signals = []
    for signal in comparison_match.group(1).split(","):
        words = re.sub(r"\s+(?:status|signal)$", "", signal.strip(), flags=re.IGNORECASE).split()
        signals.append(
            f"{words[0]}-{' '.join(words[1:]).lower()}"
            if len(words) >= 2
            else "".join(words)
        )
    subject = (
        f"{', '.join(signals[:-1])} and {signals[-1]}"
        if len(signals) > 1
        else signals[0]
    )
    return f"{subject} coverage was limited during the comparison period"


def _apply_presentation_fields(result: dict[str, Any]) -> dict[str, Any]:
    gate = result.get("quality_gate")
    if isinstance(gate, dict):
        gate["data_quality_notes"] = [
            _presentation_quality_note(item)
            for item in gate.get("warnings", [])
            if str(item or "").strip()
        ]
    for finding in (result.get("analysis") or {}).get("findings", []):
        finding["title"] = _presentation_title(finding.get("title"))
        if finding["title"] == PUMP_FLOW_TITLE:
            finding["operational_summary"] = PUMP_FLOW_OPERATIONAL_SUMMARY
    return result


def _public_assessment(record: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(record))
    for dataset in result.get("datasets", {}).values():
        dataset.pop("storage_name", None)
    return _apply_presentation_fields(result)


def read_assessment(assessment_id: str) -> dict[str, Any] | None:
    record = read_latest_payload(_assessment_key(assessment_id))
    return _public_assessment(record) if isinstance(record, dict) else None


def _read_private_assessment(assessment_id: str) -> dict[str, Any]:
    record = read_latest_payload(_assessment_key(assessment_id))
    if not isinstance(record, dict):
        raise AssessmentError("assessment_not_found")
    return record


def list_assessments(limit: int = 20, *, actor: str | None = None) -> list[dict[str, Any]]:
    records = [
        _public_assessment(item)
        for item in list_latest_payloads_prefix(ASSESSMENT_PREFIX, limit=500)
        if isinstance(item, dict)
        and (actor is None or str(item.get("created_by") or "") == actor)
    ]
    return records[: max(1, min(int(limit), 100))]


def _clean_filename(filename: str | None, fallback: str) -> str:
    name = Path(str(filename or fallback)).name
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return (cleaned or fallback)[-180:]


def _read_csv_bytes(data: bytes) -> pd.DataFrame:
    if not data:
        raise AssessmentError("empty_dataset")
    try:
        frame = pd.read_csv(
            io.BytesIO(data),
            sep=None,
            engine="python",
            dtype=object,
            keep_default_na=True,
            na_values=["", "NA", "N/A", "null", "None"],
        )
    except Exception as error:
        raise AssessmentError("csv_parse_failed") from error
    if frame.empty:
        raise AssessmentError("dataset_has_no_rows")
    if not len(frame.columns):
        raise AssessmentError("dataset_has_no_columns")
    frame.columns = [str(column).strip() or f"unnamed_column_{index + 1}" for index, column in enumerate(frame.columns)]
    return frame


def _timestamp_values(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce", utc=True, format="mixed")


def _numeric_values(series: pd.Series) -> pd.Series:
    normalized = series.astype(str).str.replace(",", "", regex=False).str.replace("%", "", regex=False)
    return pd.to_numeric(normalized, errors="coerce")


def _infer_unit(column: str) -> str:
    token = re.sub(r"[^a-z0-9]+", "_", column.lower())
    hints = (
        ("gpm", "gpm"), ("lps", "L/s"), ("psi", "psi"), ("kpa", "kPa"),
        ("kw", "kW"), ("kwh", "kWh"), ("amps", "A"), ("amp", "A"),
        ("hz", "Hz"), ("rpm", "rpm"), ("pct", "%"), ("percent", "%"),
        ("degf", "°F"), ("degc", "°C"), ("temp", "°F"), ("flow", "gpm"),
        ("pressure", "psi"), ("speed", "%"), ("power", "kW"),
    )
    for hint, unit in hints:
        if re.search(rf"(^|_){re.escape(hint)}($|_)", token) or hint in token:
            return unit
    return ""


def _display_name(column: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_-]+", " ", column)).strip().title()


def _infer_role(column: str) -> str:
    token = column.lower()
    if any(item in token for item in ("mode", "stage", "status", "enable", "command", "on_off")):
        return "mode"
    if any(item in token for item in ("load", "demand", "power", "speed", "current", "command")):
        return "input"
    if any(item in token for item in ("flow", "pressure", "temperature", "temp", "response", "delta")):
        return "response"
    return "signal"


def _profile_frame(frame: pd.DataFrame) -> dict[str, Any]:
    row_count = len(frame)
    columns: list[dict[str, Any]] = []
    timestamp_scores: list[tuple[float, str]] = []
    for index, column in enumerate(frame.columns):
        series = frame[column]
        observed = int(series.notna().sum())
        missing = row_count - observed
        numeric = _numeric_values(series)
        numeric_valid = int(numeric.notna().sum())
        numeric_ratio = numeric_valid / max(1, observed)
        timestamp = _timestamp_values(series)
        timestamp_valid = int(timestamp.notna().sum())
        timestamp_ratio = timestamp_valid / max(1, observed)
        name_hint = 0.35 if re.search(r"timestamp|date.?time|recorded.?at|(^|_)time($|_)", column, re.I) else 0
        timestamp_score = timestamp_ratio + name_hint
        if observed >= 3:
            timestamp_scores.append((timestamp_score, column))
        usable_signal = numeric_ratio >= 0.8 and numeric_valid >= min(MIN_BASELINE_ROWS, max(12, row_count // 4))
        reasons = []
        if observed == 0:
            reasons.append("Column is entirely missing.")
        elif numeric_ratio < 0.8:
            reasons.append(f"Only {numeric_ratio:.0%} of populated values are numeric.")
        elif numeric_valid < min(MIN_BASELINE_ROWS, max(12, row_count // 4)):
            reasons.append(f"Only {numeric_valid} usable numeric records are available.")
        columns.append(
            {
                "name": column,
                "position": index,
                "row_count": row_count,
                "non_null_count": observed,
                "missing_count": missing,
                "missing_percent": round(missing / max(1, row_count) * 100, 2),
                "numeric_valid_count": numeric_valid,
                "numeric_valid_percent": round(numeric_ratio * 100, 2),
                "distinct_count": int(series.nunique(dropna=True)),
                "usable_as_signal": usable_signal,
                "reasons": reasons,
                "suggested_name": _display_name(column),
                "suggested_unit": _infer_unit(column),
                "suggested_role": _infer_role(column),
            }
        )
    timestamp_scores.sort(reverse=True)
    inferred_timestamp = timestamp_scores[0][1] if timestamp_scores and timestamp_scores[0][0] >= 0.8 else None
    if inferred_timestamp:
        for item in columns:
            if item["name"] == inferred_timestamp:
                item["usable_as_signal"] = False
                item["reasons"] = ["Mapped as the timestamp column."]
                break
    unusable = [
        {"column": item["name"], "reasons": item["reasons"]}
        for item in columns
        if not item["usable_as_signal"] and item["name"] != inferred_timestamp
    ]
    return {
        "row_count": row_count,
        "column_count": len(columns),
        "columns": columns,
        "inferred_timestamp_column": inferred_timestamp,
        "unusable_columns": unusable,
    }


def _suggest_mapping(baseline: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    comparison_by_normalized = {
        re.sub(r"[^a-z0-9]+", "", item["name"].lower()): item
        for item in comparison["columns"]
    }
    signals = []
    for item in baseline["columns"]:
        if not item["usable_as_signal"]:
            continue
        match = comparison_by_normalized.get(re.sub(r"[^a-z0-9]+", "", item["name"].lower()))
        signals.append(
            {
                "id": f"signal_{len(signals) + 1}",
                "name": item["suggested_name"],
                "baseline_column": item["name"],
                "comparison_column": match["name"] if match and match["usable_as_signal"] else "",
                "unit": item["suggested_unit"],
                "system_name": "Tower system",
                "role": item["suggested_role"],
                "include": bool(match and match["usable_as_signal"]),
            }
        )
    return {
        "baseline_timestamp_column": baseline["inferred_timestamp_column"] or "",
        "comparison_timestamp_column": comparison["inferred_timestamp_column"] or "",
        "signals": signals[:MAX_SIGNAL_MAPPINGS],
    }


def _mapping_validation(mapping: dict[str, Any], schemas: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    baseline_columns = {item["name"]: item for item in schemas["baseline"]["columns"]}
    comparison_columns = {item["name"]: item for item in schemas["comparison"]["columns"]}
    baseline_timestamp = str(mapping.get("baseline_timestamp_column") or "")
    comparison_timestamp = str(mapping.get("comparison_timestamp_column") or "")
    if baseline_timestamp not in baseline_columns:
        errors.append("Select a usable baseline timestamp column.")
    if comparison_timestamp not in comparison_columns:
        errors.append("Select a usable comparison timestamp column.")
    included = [item for item in mapping.get("signals", []) if item.get("include", True)]
    if len(included) < 2:
        errors.append("Map at least two signals in both periods.")
    if len(included) > MAX_SIGNAL_MAPPINGS:
        errors.append(f"Map no more than {MAX_SIGNAL_MAPPINGS} signals in one assessment.")
    identities: set[str] = set()
    for index, signal in enumerate(included, start=1):
        name = str(signal.get("name") or "").strip()
        system = str(signal.get("system_name") or "").strip()
        baseline_column = str(signal.get("baseline_column") or "")
        comparison_column = str(signal.get("comparison_column") or "")
        identity = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if not name:
            errors.append(f"Signal {index} needs a signal name.")
        elif identity in identities:
            errors.append(f"Signal name “{name}” is duplicated.")
        identities.add(identity)
        if not system:
            errors.append(f"Signal “{name or index}” needs a system name.")
        if baseline_column not in baseline_columns:
            errors.append(f"Signal “{name or index}” is missing a baseline column.")
        elif not baseline_columns[baseline_column]["usable_as_signal"]:
            errors.append(f"Baseline column “{baseline_column}” is not usable as a numeric signal.")
        if comparison_column not in comparison_columns:
            errors.append(f"Signal “{name or index}” is missing a comparison column.")
        elif not comparison_columns[comparison_column]["usable_as_signal"]:
            errors.append(f"Comparison column “{comparison_column}” is not usable as a numeric signal.")
        if not str(signal.get("unit") or "").strip():
            warnings.append(f"No engineering unit was supplied for “{name or baseline_column}”.")
    return {"ready": not errors, "errors": list(dict.fromkeys(errors)), "warnings": list(dict.fromkeys(warnings))}


def create_assessment(
    *,
    baseline_filename: str,
    baseline_bytes: bytes,
    comparison_filename: str,
    comparison_bytes: bytes,
    actor: str,
) -> dict[str, Any]:
    settings = get_settings()
    if len(baseline_bytes) > settings.max_upload_size_bytes or len(comparison_bytes) > settings.max_upload_size_bytes:
        raise AssessmentError("dataset_too_large")
    baseline_frame = _read_csv_bytes(baseline_bytes)
    comparison_frame = _read_csv_bytes(comparison_bytes)
    assessment_id = f"pilot-{uuid.uuid4().hex[:16]}"
    target = _assessment_dir(assessment_id)
    baseline_storage = "baseline.csv"
    comparison_storage = "comparison.csv"
    (target / baseline_storage).write_bytes(baseline_bytes)
    (target / comparison_storage).write_bytes(comparison_bytes)
    schemas = {
        "baseline": _profile_frame(baseline_frame),
        "comparison": _profile_frame(comparison_frame),
    }
    mapping = _suggest_mapping(schemas["baseline"], schemas["comparison"])
    created_at = now_iso()
    record = {
        "contract_version": CONTRACT_VERSION,
        "assessment_id": assessment_id,
        "status": "mapping_required",
        "created_at": created_at,
        "updated_at": created_at,
        "created_by": actor,
        "datasets": {
            "baseline": {
                "filename": _clean_filename(baseline_filename, "baseline.csv"),
                "storage_name": baseline_storage,
                "sha256": hashlib.sha256(baseline_bytes).hexdigest(),
                "rows": len(baseline_frame),
            },
            "comparison": {
                "filename": _clean_filename(comparison_filename, "comparison.csv"),
                "storage_name": comparison_storage,
                "sha256": hashlib.sha256(comparison_bytes).hexdigest(),
                "rows": len(comparison_frame),
            },
        },
        "schemas": schemas,
        "mapping": mapping,
        "mapping_validation": _mapping_validation(mapping, schemas),
        "quality_gate": None,
        "operating_modes": [],
        "analysis": None,
        "event_backtest": None,
        "feedback_history": [],
    }
    upsert_latest_payload(_assessment_key(assessment_id), record)
    return _public_assessment(record)


def update_mapping(assessment_id: str, mapping: dict[str, Any]) -> dict[str, Any]:
    def mutate(record: Any) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise AssessmentError("assessment_not_found")
        if record.get("status") not in {"mapping_required", "ready_to_analyze"}:
            raise AssessmentError("mapping_locked_after_analysis")
        normalized = {
            "baseline_timestamp_column": str(mapping.get("baseline_timestamp_column") or "").strip(),
            "comparison_timestamp_column": str(mapping.get("comparison_timestamp_column") or "").strip(),
            "signals": [
                {
                    "id": str(item.get("id") or f"signal_{index + 1}")[:80],
                    "name": str(item.get("name") or "").strip()[:120],
                    "baseline_column": str(item.get("baseline_column") or "").strip(),
                    "comparison_column": str(item.get("comparison_column") or "").strip(),
                    "unit": str(item.get("unit") or "").strip()[:40],
                    "system_name": str(item.get("system_name") or "").strip()[:120],
                    "role": str(item.get("role") or "signal").strip().lower(),
                    "include": bool(item.get("include", True)),
                }
                for index, item in enumerate(mapping.get("signals", []))
                if isinstance(item, dict)
            ],
        }
        validation = _mapping_validation(normalized, record["schemas"])
        return {
            **record,
            "status": "ready_to_analyze" if validation["ready"] else "mapping_required",
            "updated_at": now_iso(),
            "mapping": normalized,
            "mapping_validation": validation,
        }

    return _public_assessment(mutate_latest_payload(_assessment_key(assessment_id), mutate))


def _load_sources(record: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    target = _assessment_dir(record["assessment_id"])
    return (
        _read_csv_bytes((target / record["datasets"]["baseline"]["storage_name"]).read_bytes()),
        _read_csv_bytes((target / record["datasets"]["comparison"]["storage_name"]).read_bytes()),
    )


def _longest_missing_run(mask: pd.Series) -> int:
    longest = current = 0
    for missing in mask.tolist():
        current = current + 1 if bool(missing) else 0
        longest = max(longest, current)
    return longest


def _signal_quality(series: pd.Series) -> dict[str, Any]:
    numeric = _numeric_values(series)
    count = len(numeric)
    valid = numeric.dropna()
    coverage = len(valid) / max(1, count)
    unique = int(valid.nunique())
    reasons: list[str] = []
    flags: list[str] = []
    if coverage < 0.8:
        flags.append("sparse")
        reasons.append(f"Excluded as sparse: {coverage:.1%} baseline coverage is below 80%.")
    if len(valid) and (unique <= 2 or unique / len(valid) < 0.01 or float(valid.std(ddof=0) or 0) <= 1e-12):
        flags.append("flatlined")
        reasons.append(f"Excluded as flatlined: only {unique} distinct values were observed.")
    longest_gap = _longest_missing_run(numeric.isna())
    if longest_gap > max(6, int(count * 0.1)):
        flags.append("misaligned")
        reasons.append(f"Excluded as misaligned: the longest missing run was {longest_gap} records.")
    spike_ratio = 0.0
    if len(valid) >= 12:
        differences = valid.diff().dropna()
        median_difference = float(differences.median())
        mad = float((differences - median_difference).abs().median())
        if mad > 1e-12:
            spike_ratio = float(((differences - median_difference).abs() > 10 * 1.4826 * mad).mean())
            if spike_ratio > 0.12:
                flags.append("noisy")
                reasons.append(f"Excluded as noisy: {spike_ratio:.1%} of changes were extreme spikes.")
    return {
        "coverage": round(coverage, 6),
        "valid_records": len(valid),
        "missing_records": count - len(valid),
        "distinct_values": unique,
        "longest_missing_run": longest_gap,
        "spike_ratio": round(spike_ratio, 6),
        "flags": flags,
        "reasons": reasons,
        "included": not flags,
    }


def _prepare_period(
    frame: pd.DataFrame,
    *,
    timestamp_column: str,
    signals: list[dict[str, Any]],
    period: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    timestamp = _timestamp_values(frame[timestamp_column])
    prepared = pd.DataFrame(
        {
            "__timestamp": timestamp,
            "__source_row": np.arange(2, len(frame) + 2),
        }
    )
    for signal in signals:
        source = signal[f"{period}_column"]
        prepared[signal["id"]] = _numeric_values(frame[source])
    invalid_timestamps = int(prepared["__timestamp"].isna().sum())
    prepared = prepared.dropna(subset=["__timestamp"]).sort_values("__timestamp", kind="stable")
    duplicate_timestamps = int(prepared["__timestamp"].duplicated(keep="first").sum())
    prepared = prepared.drop_duplicates(subset=["__timestamp"], keep="first").reset_index(drop=True)
    diffs = prepared["__timestamp"].diff().dropna().dt.total_seconds()
    median_interval = float(diffs[diffs > 0].median()) if bool((diffs > 0).any()) else None
    span_hours = (
        float((prepared["__timestamp"].iloc[-1] - prepared["__timestamp"].iloc[0]).total_seconds() / 3600)
        if len(prepared) >= 2
        else 0.0
    )
    expected_records = (
        int(round(span_hours * 3600 / median_interval)) + 1
        if median_interval and span_hours > 0
        else len(prepared)
    )
    time_coverage = min(1.0, len(prepared) / max(1, expected_records))
    return prepared, {
        "source_rows": len(frame),
        "usable_timestamp_rows": len(prepared),
        "invalid_timestamps": invalid_timestamps,
        "duplicate_timestamps": duplicate_timestamps,
        "duplicate_timestamp_percent": round(duplicate_timestamps / max(1, len(frame)) * 100, 3),
        "start": prepared["__timestamp"].min().isoformat() if len(prepared) else None,
        "end": prepared["__timestamp"].max().isoformat() if len(prepared) else None,
        "span_hours": round(span_hours, 3),
        "median_interval_seconds": round(median_interval, 3) if median_interval else None,
        "time_coverage": round(time_coverage, 6),
    }


def _quality_gate(
    baseline_frame: pd.DataFrame,
    comparison_frame: pd.DataFrame,
    baseline: pd.DataFrame,
    comparison: pd.DataFrame,
    signals: list[dict[str, Any]],
    baseline_time: dict[str, Any],
    comparison_time: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    blocking: list[str] = []
    warnings: list[str] = []
    if baseline_time["usable_timestamp_rows"] < MIN_BASELINE_ROWS:
        blocking.append(f"Baseline has {baseline_time['usable_timestamp_rows']} usable timestamped records; at least {MIN_BASELINE_ROWS} are required.")
    if baseline_time["span_hours"] < MIN_BASELINE_HOURS:
        blocking.append(f"Baseline spans {baseline_time['span_hours']:.1f} hours; at least {MIN_BASELINE_HOURS} hours are required.")
    if baseline_time["time_coverage"] < 0.8:
        blocking.append(f"Baseline timestamp coverage is {baseline_time['time_coverage']:.1%}; at least 80% is required.")
    if baseline_time["duplicate_timestamp_percent"] > 5:
        blocking.append(f"{baseline_time['duplicate_timestamp_percent']:.1f}% of baseline timestamps are duplicated.")
    elif baseline_time["duplicate_timestamps"]:
        warnings.append(f"{baseline_time['duplicate_timestamps']} duplicate baseline timestamps were excluded.")
    signal_rows: list[dict[str, Any]] = []
    baseline_column_by_id = {item["id"]: item["baseline_column"] for item in signals}
    comparison_column_by_id = {item["id"]: item["comparison_column"] for item in signals}
    for signal in signals:
        baseline_quality = _signal_quality(baseline_frame[baseline_column_by_id[signal["id"]]])
        comparison_quality = _signal_quality(comparison_frame[comparison_column_by_id[signal["id"]]])
        signal_rows.append(
            {
                "id": signal["id"],
                "name": signal["name"],
                "unit": signal["unit"],
                "system_name": signal["system_name"],
                "role": signal["role"],
                "included": baseline_quality["included"],
                "exclusion_reasons": baseline_quality["reasons"],
                "baseline": baseline_quality,
                "comparison": comparison_quality,
            }
        )
    included = [item for item in signal_rows if item["included"]]
    for left_index, left in enumerate(included):
        for right in included[left_index + 1:]:
            paired = baseline[[left["id"], right["id"]]].dropna()
            if len(paired) >= 12 and np.allclose(
                paired[left["id"]].to_numpy(dtype=float),
                paired[right["id"]].to_numpy(dtype=float),
                rtol=1e-8,
                atol=1e-10,
            ):
                right["included"] = False
                right["baseline"]["included"] = False
                right["baseline"]["flags"].append("duplicated")
                reason = f"Excluded as duplicated: values match “{left['name']}” across the baseline."
                right["baseline"]["reasons"].append(reason)
                right["exclusion_reasons"].append(reason)
    included = [item for item in signal_rows if item["included"] and item["role"] not in {"mode", "context"}]
    if len(included) < 2:
        blocking.append("Fewer than two independent, usable baseline signals remain after quality checks.")
    if comparison_time["usable_timestamp_rows"] < MIN_BASELINE_ROWS:
        warnings.append("The comparison period has fewer than 48 usable timestamped records.")
    comparison_limited = [
        item["name"]
        for item in signal_rows
        if item["comparison"]["flags"]
    ]
    if comparison_limited:
        warnings.append(f"Comparison-period quality is limited for: {', '.join(comparison_limited)}.")
    gate = {
        "passed": not blocking,
        "decision": "baseline_accepted" if not blocking else "baseline_withheld",
        "summary": (
            f"Baseline accepted with {len(included)} usable signals."
            if not blocking
            else "Neraium refused to build a confident baseline."
        ),
        "blocking_reasons": blocking,
        "warnings": warnings,
        "baseline_period": baseline_time,
        "comparison_period": comparison_time,
        "signals": signal_rows,
        "included_signal_count": len(included),
        "excluded_signal_count": len(signal_rows) - len(included),
    }
    return gate, signal_rows


def _driver_signal(signals: list[dict[str, Any]], baseline: pd.DataFrame) -> str:
    candidates = [item for item in signals if item["role"] in {"mode", "input"} and item["included"]]
    if not candidates:
        candidates = [item for item in signals if item["included"]]
    return max(
        candidates,
        key=lambda item: float(baseline[item["id"]].std(ddof=0) or 0),
    )["id"]


def _assign_modes(values: pd.Series, reference: tuple[float, float]) -> pd.Series:
    low, high = reference
    scale = max(high - low, 1e-9)
    normalized = ((values - low) / scale).clip(-0.2, 1.4)
    smoothed = normalized.rolling(3, center=True, min_periods=1).median()
    delta = smoothed.diff().fillna(0)
    has_observed_off_state = low <= max(1e-9, abs(high) * 0.1)
    active = smoothed > 0.03 if has_observed_off_state else pd.Series(True, index=values.index)
    prior_active = active.shift(1, fill_value=False)
    labels = pd.Series("stable operation", index=values.index, dtype=object)
    labels[(~prior_active) & active] = "startup"
    labels[prior_active & (~active)] = "shutdown"
    labels[active & (delta.abs() > 0.16) & (labels == "stable operation")] = "staging"
    stable = labels == "stable operation"
    labels[stable & (smoothed <= 0.42)] = "stable low load"
    labels[stable & (smoothed >= 0.68)] = "stable high load"
    return labels


def _mode_summary(baseline: pd.DataFrame, comparison: pd.DataFrame) -> list[dict[str, Any]]:
    ordered = ["startup", "stable operation", "shutdown", "staging", "stable low load", "stable high load"]
    return [
        {
            "mode": mode,
            "baseline_records": int((baseline["__mode"] == mode).sum()),
            "comparison_records": int((comparison["__mode"] == mode).sum()),
            "comparable": int((baseline["__mode"] == mode).sum()) >= MIN_MODE_SAMPLES
            and int((comparison["__mode"] == mode).sum()) >= MIN_MODE_SAMPLES,
            "used_for_findings": mode.startswith("stable"),
        }
        for mode in ordered
    ]


def _fit_relationship(rows: pd.DataFrame, left: str, right: str) -> dict[str, float] | None:
    paired = rows[[left, right]].dropna()
    if len(paired) < MIN_MODE_SAMPLES:
        return None
    x = paired[left].to_numpy(dtype=float)
    y = paired[right].to_numpy(dtype=float)
    if float(np.std(x)) <= 1e-12 or float(np.std(y)) <= 1e-12:
        return None
    slope, intercept = np.polyfit(x, y, 1)
    predicted = slope * x + intercept
    residual = y - predicted
    median = float(np.median(residual))
    mad = float(np.median(np.abs(residual - median)))
    scale = max(1.4826 * mad, float(np.std(y)) * 0.05, 1e-9)
    return {
        "correlation": float(np.corrcoef(x, y)[0, 1]),
        "slope": float(slope),
        "intercept": float(intercept),
        "residual_scale": scale,
        "sample_count": len(paired),
    }


def _persistence_windows(
    rows: pd.DataFrame,
    left: str,
    right: str,
    baseline_fit: dict[str, float],
) -> dict[str, Any]:
    paired = rows[["__timestamp", "__source_row", "__mode", left, right]].dropna().sort_values("__timestamp")
    if len(paired) < MIN_MODE_SAMPLES:
        return {"persistent": False, "windows": [], "first_surfaced_at": None, "support_fraction": 0}
    window_size = max(8, min(32, len(paired) // 3))
    windows = []
    for start in range(0, len(paired) - window_size + 1, window_size):
        window = paired.iloc[start:start + window_size]
        predicted = baseline_fit["slope"] * window[left].to_numpy(dtype=float) + baseline_fit["intercept"]
        score = float(np.median(np.abs(window[right].to_numpy(dtype=float) - predicted)) / baseline_fit["residual_scale"])
        windows.append(
            {
                "start": window["__timestamp"].iloc[0].isoformat(),
                "end": window["__timestamp"].iloc[-1].isoformat(),
                "records": len(window),
                "deviation_score": round(score, 4),
                "supports_change": score >= 3.0,
            }
        )
    support_indexes = [index for index, item in enumerate(windows) if item["supports_change"]]
    if not support_indexes:
        return {"persistent": False, "windows": windows, "first_surfaced_at": None, "support_fraction": 0}
    first = support_indexes[0]
    later = windows[first:]
    fraction = sum(item["supports_change"] for item in later) / max(1, len(later))
    return {
        "persistent": len(support_indexes) >= 2 and fraction >= 0.6,
        "windows": windows,
        "first_surfaced_at": windows[first]["start"],
        "support_fraction": round(fraction, 4),
    }


def evaluate_relationship_against_baseline(
    rows: pd.DataFrame,
    left: str,
    right: str,
    baseline_fit: dict[str, float],
) -> dict[str, Any]:
    """Apply the production relationship-change and persistence rules."""

    current_fit = _fit_relationship(rows, left, right)
    if current_fit is None:
        return {
            "evaluated": False,
            "changed": False,
            "current_fit": None,
            "correlation_delta": None,
            "slope_change": None,
            "persistence": {
                "persistent": False,
                "windows": [],
                "first_surfaced_at": None,
                "support_fraction": 0,
            },
        }
    correlation_delta = current_fit["correlation"] - baseline_fit["correlation"]
    slope_change = (
        abs((current_fit["slope"] - baseline_fit["slope"]) / baseline_fit["slope"])
        if abs(baseline_fit["slope"]) > 1e-9
        else math.inf
    )
    persistence = _persistence_windows(rows, left, right, baseline_fit)
    return {
        "evaluated": True,
        "changed": bool(abs(correlation_delta) >= 0.25 or slope_change >= 0.3),
        "current_fit": current_fit,
        "correlation_delta": correlation_delta,
        "slope_change": slope_change,
        "persistence": persistence,
    }


def _write_exact_records(
    record: dict[str, Any],
    relationship_id: str,
    baseline_rows: pd.DataFrame,
    comparison_rows: pd.DataFrame,
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any]:
    frames = []
    for period, rows in (("baseline", baseline_rows), ("comparison", comparison_rows)):
        selected = rows[["__source_row", "__timestamp", "__mode", left["id"], right["id"]]].dropna().copy()
        selected.insert(0, "period", period)
        selected = selected.rename(
            columns={
                "__source_row": "source_row",
                "__timestamp": "timestamp",
                "__mode": "operating_mode",
                left["id"]: f"{left['name']} ({left['unit'] or 'unit not supplied'})",
                right["id"]: f"{right['name']} ({right['unit'] or 'unit not supplied'})",
            }
        )
        frames.append(selected)
    exact = pd.concat(frames, ignore_index=True)
    path = _assessment_dir(record["assessment_id"]) / "records"
    path.mkdir(parents=True, exist_ok=True)
    file_path = path / f"{relationship_id}.csv"
    csv_bytes = exact.to_csv(index=False).encode("utf-8")
    file_path.write_bytes(csv_bytes)
    return {
        "record_count": len(exact),
        "sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "download_url": f"/api/pilot-assessments/{record['assessment_id']}/records/{relationship_id}.csv",
        "columns": list(exact.columns),
    }


def _relationship_title(left: dict[str, Any], right: dict[str, Any]) -> str:
    return f"{left['name']} ↔ {right['name']}"


def _finding_title(system: str, relationships: list[dict[str, Any]]) -> str:
    text = f"{system} {' '.join(item['relationship'] for item in relationships)}".lower()
    if "pump" in text and any(token in text for token in ("flow", "pressure", "hydraulic")):
        return PUMP_FLOW_TITLE
    if "flow" in text and "pressure" in text:
        return "Flow no longer matches pressure response"
    return f"{system} relationships changed"


def _analyze_relationships(
    record: dict[str, Any],
    baseline: pd.DataFrame,
    comparison: pd.DataFrame,
    signals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    usable = [item for item in signals if item["included"] and item["role"] not in {"mode", "context"}]
    pairs_seen = 0
    for mode in ("stable operation", "stable low load", "stable high load"):
        baseline_mode = baseline[baseline["__mode"] == mode]
        comparison_mode = comparison[comparison["__mode"] == mode]
        if len(baseline_mode) < MIN_MODE_SAMPLES or len(comparison_mode) < MIN_MODE_SAMPLES:
            continue
        for left_index, left in enumerate(usable):
            for right in usable[left_index + 1:]:
                if left["system_name"] != right["system_name"]:
                    continue
                if left["role"] == right["role"] == "input":
                    continue
                pairs_seen += 1
                if pairs_seen > MAX_RELATIONSHIPS:
                    break
                baseline_fit = _fit_relationship(baseline_mode, left["id"], right["id"])
                if baseline_fit is None or abs(baseline_fit["correlation"]) < 0.35:
                    continue
                evaluation = evaluate_relationship_against_baseline(
                    comparison_mode,
                    left["id"],
                    right["id"],
                    baseline_fit,
                )
                if not evaluation["evaluated"]:
                    continue
                current_fit = evaluation["current_fit"]
                correlation_delta = evaluation["correlation_delta"]
                slope_change = evaluation["slope_change"]
                persistence = evaluation["persistence"]
                if not evaluation["changed"] or not persistence["persistent"]:
                    continue
                relationship_id = f"rel-{uuid.uuid4().hex[:12]}"
                exact_records = _write_exact_records(
                    record,
                    relationship_id,
                    baseline_mode,
                    comparison_mode,
                    left,
                    right,
                )
                support_windows = [item for item in persistence["windows"] if item["supports_change"]]
                changes.append(
                    {
                        "relationship_id": relationship_id,
                        "relationship": _relationship_title(left, right),
                        "system_name": left["system_name"],
                        "operating_mode": mode,
                        "what_changed": f"The mode-matched relationship between {left['name']} and {right['name']} moved outside its baseline behavior.",
                        "before_behavior": {
                            "correlation": round(baseline_fit["correlation"], 4),
                            "slope": round(baseline_fit["slope"], 6),
                            "records": baseline_fit["sample_count"],
                        },
                        "after_behavior": {
                            "correlation": round(current_fit["correlation"], 4),
                            "slope": round(current_fit["slope"], 6),
                            "records": current_fit["sample_count"],
                        },
                        "magnitude": {
                            "correlation_delta": round(correlation_delta, 4),
                            "absolute_correlation_change": round(abs(correlation_delta), 4),
                            "slope_change_percent": (
                                round(slope_change * 100, 2) if math.isfinite(slope_change) else None
                            ),
                            "method": "mode-matched linear response and residual deviation",
                        },
                        "persistence": {
                            "persistent": True,
                            "supporting_windows": len(support_windows),
                            "assessed_windows": len(persistence["windows"]),
                            "support_fraction": persistence["support_fraction"],
                            "last_supported_at": support_windows[-1]["end"],
                            "windows": persistence["windows"],
                        },
                        "start_time": persistence["first_surfaced_at"],
                        "data_quality_limitations": [
                            reason
                            for item in (left, right)
                            for reason in item["comparison"]["reasons"]
                        ],
                        "exact_records": exact_records,
                        "signal_ids": [left["id"], right["id"]],
                        "signal_names": [left["name"], right["name"]],
                        "units": [left["unit"], right["unit"]],
                    }
                )
            if pairs_seen > MAX_RELATIONSHIPS:
                break
    return changes


def analyze_assessment(assessment_id: str, *, actor: str) -> dict[str, Any]:
    record = _read_private_assessment(assessment_id)
    if record.get("status") not in {"ready_to_analyze", "mapping_required"}:
        if record.get("status") in {"analysis_complete", "baseline_withheld"}:
            return _public_assessment(record)
        raise AssessmentError("assessment_not_ready")
    validation = _mapping_validation(record["mapping"], record["schemas"])
    if not validation["ready"]:
        raise AssessmentError("mapping_incomplete")
    baseline_source, comparison_source = _load_sources(record)
    signals = [item for item in record["mapping"]["signals"] if item.get("include", True)]
    baseline, baseline_time = _prepare_period(
        baseline_source,
        timestamp_column=record["mapping"]["baseline_timestamp_column"],
        signals=signals,
        period="baseline",
    )
    comparison, comparison_time = _prepare_period(
        comparison_source,
        timestamp_column=record["mapping"]["comparison_timestamp_column"],
        signals=signals,
        period="comparison",
    )
    gate, signal_quality = _quality_gate(
        baseline_source,
        comparison_source,
        baseline,
        comparison,
        signals,
        baseline_time,
        comparison_time,
    )
    completed_at = now_iso()
    if not gate["passed"]:
        updated = {
            **record,
            "status": "baseline_withheld",
            "updated_at": completed_at,
            "analysis_completed_at": completed_at,
            "analysis_completed_by": actor,
            "quality_gate": gate,
            "operating_modes": [],
            "analysis": {
                "finding_count": 0,
                "findings": [],
                "conclusion": "No confident baseline was built, so no outage precursor claim was produced.",
            },
        }
        upsert_latest_payload(_assessment_key(assessment_id), updated)
        return _public_assessment(updated)
    quality_by_id = {item["id"]: item for item in signal_quality}
    analysis_signals = [{**item, **quality_by_id[item["id"]]} for item in signals]
    driver = _driver_signal(analysis_signals, baseline)
    driver_values = baseline[driver].dropna()
    q05 = float(driver_values.quantile(0.05))
    q95 = float(driver_values.quantile(0.95))
    if q95 - q05 <= 1e-9:
        q05 = float(driver_values.min())
        q95 = float(driver_values.max()) + 1e-9
    baseline["__mode"] = _assign_modes(baseline[driver], (q05, q95))
    comparison["__mode"] = _assign_modes(comparison[driver], (q05, q95))
    modes = _mode_summary(baseline, comparison)
    changes = _analyze_relationships(record, baseline, comparison, analysis_signals)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for change in changes:
        grouped.setdefault(change["system_name"], []).append(change)
    findings = []
    for index, (system, evidence) in enumerate(grouped.items(), start=1):
        first = min(item["start_time"] for item in evidence if item["start_time"])
        last = max(item["persistence"]["last_supported_at"] for item in evidence)
        limitations = list(dict.fromkeys(
            item
            for relationship in evidence
            for item in relationship["data_quality_limitations"]
        ))
        findings.append(
            {
                "finding_id": f"finding-{index}",
                "title": _finding_title(system, evidence),
                "system_name": system,
                "summary": f"{len(evidence)} supporting mode-matched relationship changes were persistent in the comparison period.",
                "evidence_count": len(evidence),
                "first_surfaced_at": first,
                "last_observed_at": last,
                "persisted": True,
                "data_quality_limitations": limitations,
                "relationships": evidence,
            }
        )
    updated = {
        **record,
        "status": "analysis_complete",
        "updated_at": completed_at,
        "analysis_completed_at": completed_at,
        "analysis_completed_by": actor,
        "quality_gate": gate,
        "operating_modes": modes,
        "analysis": {
            "method": "blinded mode-matched relationship assessment v1",
            "event_timestamp_used": False,
            "driver_signal_id": driver,
            "relationship_candidates_assessed": min(MAX_RELATIONSHIPS, len(analysis_signals) * max(0, len(analysis_signals) - 1) // 2),
            "finding_count": len(findings),
            "findings": findings,
            "conclusion": (
                f"Neraium surfaced {len(findings)} evidence-backed system finding{'s' if len(findings) != 1 else ''} before any event timestamp was supplied."
                if findings
                else "No persistent, mode-matched relationship change met the evidence threshold."
            ),
        },
    }
    upsert_latest_payload(_assessment_key(assessment_id), updated)
    return _public_assessment(updated)


def reveal_event(
    assessment_id: str,
    *,
    event_timestamp: str,
    event_label: str,
    repair_timestamp: str | None,
    actor: str,
) -> dict[str, Any]:
    try:
        event = pd.Timestamp(event_timestamp)
    except Exception as error:
        raise AssessmentError("invalid_event_timestamp") from error
    if event.tzinfo is None:
        raise AssessmentError("event_timestamp_timezone_required")
    repair = None
    if repair_timestamp:
        try:
            repair = pd.Timestamp(repair_timestamp)
        except Exception as error:
            raise AssessmentError("invalid_repair_timestamp") from error
        if repair.tzinfo is None:
            raise AssessmentError("repair_timestamp_timezone_required")

    def mutate(record: Any) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise AssessmentError("assessment_not_found")
        if record.get("status") not in {"analysis_complete", "baseline_withheld"}:
            raise AssessmentError("analysis_must_finish_before_event_reveal")
        findings = (record.get("analysis") or {}).get("findings") or []
        comparison_end = pd.Timestamp(record["quality_gate"]["comparison_period"]["end"])
        results = []
        for finding in findings:
            first = pd.Timestamp(finding["first_surfaced_at"])
            lead_hours = (event - first).total_seconds() / 3600
            last = pd.Timestamp(finding["last_observed_at"])
            if event <= comparison_end:
                persisted_to_event: bool | None = last >= event
                persisted_note = "Observable in the supplied comparison period."
            else:
                persisted_to_event = None
                persisted_note = "The supplied data ends before the event, so persistence through the event is not observable."
            if repair is None:
                disappeared = None
                recovery_note = "No repair or recovery timestamp was supplied."
            elif repair > comparison_end:
                disappeared = None
                recovery_note = "The supplied data ends before the repair or recovery timestamp."
            else:
                post_repair_windows = [
                    window
                    for relationship in finding["relationships"]
                    for window in relationship["persistence"]["windows"]
                    if pd.Timestamp(window["start"]) >= repair
                ]
                if not post_repair_windows:
                    disappeared = None
                    recovery_note = "No complete assessed relationship window exists after the repair timestamp."
                else:
                    supported_after_repair = any(window["supports_change"] for window in post_repair_windows)
                    disappeared = not supported_after_repair
                    recovery_note = (
                        "No supporting relationship window remained after the repair timestamp."
                        if disappeared
                        else "At least one supporting relationship window remained after the repair timestamp."
                    )
            results.append(
                {
                    "finding_id": finding["finding_id"],
                    "first_surfaced_at": finding["first_surfaced_at"],
                    "lead_time_hours": round(lead_hours, 2),
                    "surfaced_before_event": lead_hours > 0,
                    "persisted_through_event": persisted_to_event,
                    "persistence_note": persisted_note,
                    "disappeared_after_repair": disappeared,
                    "recovery_note": recovery_note,
                }
            )
        revealed_at = now_iso()
        return {
            **record,
            "updated_at": revealed_at,
            "event_backtest": {
                "event_label": str(event_label or "Known event").strip()[:160] or "Known event",
                "event_timestamp": event.isoformat(),
                "repair_timestamp": repair.isoformat() if repair is not None else None,
                "revealed_at": revealed_at,
                "revealed_by": actor,
                "analysis_completed_at": record.get("analysis_completed_at"),
                "analysis_was_blinded": bool(
                    record.get("analysis_completed_at")
                    and pd.Timestamp(record["analysis_completed_at"]) <= pd.Timestamp(revealed_at)
                    and not (record.get("analysis") or {}).get("event_timestamp_used")
                ),
                "findings": results,
            },
        }

    return _public_assessment(mutate_latest_payload(_assessment_key(assessment_id), mutate))


def append_feedback(
    assessment_id: str,
    *,
    category: str,
    note: str | None,
    finding_id: str | None,
    actor: str,
) -> dict[str, Any]:
    if category not in FEEDBACK_CATEGORIES:
        raise AssessmentError("invalid_feedback_category")

    def mutate(record: Any) -> dict[str, Any]:
        if not isinstance(record, dict):
            raise AssessmentError("assessment_not_found")
        if record.get("status") not in {"analysis_complete", "baseline_withheld"}:
            raise AssessmentError("analysis_must_finish_before_feedback")
        entry = {
            "feedback_id": f"feedback-{uuid.uuid4().hex}",
            "category": category,
            "note": str(note or "").strip()[:4000] or None,
            "finding_id": str(finding_id or "").strip()[:128] or None,
            "recorded_at": now_iso(),
            "recorded_by": actor,
        }
        history = [item for item in record.get("feedback_history", []) if isinstance(item, dict)]
        return {**record, "updated_at": entry["recorded_at"], "feedback_history": [*history, entry]}

    return _public_assessment(mutate_latest_payload(_assessment_key(assessment_id), mutate))


def exact_records_path(assessment_id: str, relationship_id: str) -> Path:
    record = _read_private_assessment(assessment_id)
    relationships = [
        relationship
        for finding in (record.get("analysis") or {}).get("findings", [])
        for relationship in finding.get("relationships", [])
    ]
    if relationship_id not in {item.get("relationship_id") for item in relationships}:
        raise AssessmentError("relationship_not_found")
    path = _assessment_dir(assessment_id) / "records" / f"{relationship_id}.csv"
    if not path.is_file():
        raise AssessmentError("exact_records_not_found")
    return path


def _repair_deviation_comparison(
    finding: dict[str, Any],
    repair_timestamp: Any,
) -> dict[str, float] | None:
    if not repair_timestamp:
        return None
    try:
        repair = pd.Timestamp(repair_timestamp)
    except Exception:
        return None
    before_scores: list[float] = []
    after_scores: list[float] = []
    for relationship in finding.get("relationships", []):
        for window in (relationship.get("persistence") or {}).get("windows", []):
            try:
                start = pd.Timestamp(window.get("start"))
                score = float(window.get("deviation_score"))
            except (TypeError, ValueError):
                continue
            if start < repair and window.get("supports_change"):
                before_scores.append(score)
            elif start >= repair:
                after_scores.append(score)
    if not before_scores or not after_scores:
        return None
    before = round(float(np.median(before_scores)), 2)
    after = round(float(np.median(after_scores)), 2)
    reduction = ((before - after) / before) * 100 if before > 0 else None
    return {"before": before, "after": after, "reduction": reduction}


def build_report_html(record: dict[str, Any]) -> str:
    safe = lambda value: html.escape(str(value if value is not None else "Not available"))
    metric = lambda value: f"{float(value):.2f}" if value is not None else "Not available"
    gate = record.get("quality_gate") or {}
    analysis = record.get("analysis") or {}
    backtest = record.get("event_backtest") or {}
    baseline = gate.get("baseline_period") or {}
    comparison = gate.get("comparison_period") or {}
    backtest_by_finding = {
        item.get("finding_id"): item
        for item in backtest.get("findings", [])
        if isinstance(item, dict)
    }
    findings = []
    for source in analysis.get("findings", []):
        finding = dict(source)
        finding["title"] = _presentation_title(finding.get("title"))
        if finding["title"] == PUMP_FLOW_TITLE:
            finding["operational_summary"] = PUMP_FLOW_OPERATIONAL_SUMMARY
        findings.append(finding)

    finding_blocks = []
    change_blocks = []
    timeline_rows = []
    credibility_blocks = []
    relationship_rows = []
    comparison_blocks = []
    for finding in findings:
        finding_id = finding.get("finding_id")
        validation = backtest_by_finding.get(finding_id) or {}
        title = finding.get("title")
        operational_summary = finding.get("operational_summary") or finding.get("summary")
        finding_blocks.append(
            f"<article><h3>{safe(title)}</h3>"
            f"<p class=\"operational-summary\">{safe(operational_summary)}</p>"
            f"<p><strong>System:</strong> {safe(finding.get('system_name'))}</p></article>"
        )
        change_blocks.append(
            f"<article><h3>{safe(title)}</h3><p>{safe(finding.get('summary'))}</p>"
            f"<p><strong>{safe(finding.get('evidence_count'))} supporting relationship changes</strong></p></article>"
        )
        lead_time = validation.get("lead_time_hours")
        lead_description = (
            f"{metric(abs(float(lead_time)))} hours "
            f"{'before' if validation.get('surfaced_before_event') else 'after'} the recorded event"
            if lead_time is not None
            else "Not available"
        )
        timeline_rows.append(
            f"<tr><td>{safe(title)}</td><td>{safe(finding.get('first_surfaced_at'))}</td>"
            f"<td>{safe(backtest.get('event_timestamp'))}</td><td>{safe(backtest.get('repair_timestamp'))}</td>"
            f"<td>{safe(lead_description)}</td></tr>"
        )
        persistence_text = (
            "Persistence through the event was not observable"
            if validation.get("persisted_through_event") is None
            else "Persisted through the event"
            if validation.get("persisted_through_event")
            else "Did not persist through the event"
        )
        recovery_text = (
            "Post-repair behavior was not observable"
            if validation.get("disappeared_after_repair") is None
            else "Disappeared after repair"
            if validation.get("disappeared_after_repair")
            else "Remained after repair"
        )
        detection_text = (
            f"Detected {metric(abs(float(lead_time)))} hours "
            f"{'before' if validation.get('surfaced_before_event') else 'after'} the recorded event"
            if lead_time is not None
            else "Lead time was not available"
        )
        credibility_blocks.append(
            f"<article><h3>{safe(title)}</h3><ul class=\"credibility\">"
            f"<li>{safe(detection_text)}</li><li>{safe(persistence_text)}</li>"
            f"<li>Supported by {safe(finding.get('evidence_count'))} changed relationships</li>"
            f"<li>{safe(recovery_text)}</li></ul></article>"
        )
        for relationship in finding.get("relationships", []):
            relationship_rows.append(
                f"<tr><td>{safe(title)}</td><td>{safe(relationship.get('relationship'))}</td>"
                f"<td>{safe(relationship.get('operating_mode'))}</td>"
                f"<td>{safe(relationship.get('before_behavior', {}).get('correlation'))}</td>"
                f"<td>{safe(relationship.get('after_behavior', {}).get('correlation'))}</td>"
                f"<td>{safe(relationship.get('magnitude', {}).get('absolute_correlation_change'))}</td>"
                f"<td>{safe(relationship.get('start_time'))}</td>"
                f"<td>{safe(relationship.get('exact_records', {}).get('record_count'))}</td>"
                f"<td>{safe(relationship.get('exact_records', {}).get('sha256'))}</td></tr>"
            )
        repair_comparison = _repair_deviation_comparison(finding, backtest.get("repair_timestamp"))
        if repair_comparison:
            before = repair_comparison["before"]
            after = repair_comparison["after"]
            decreased = after <= before
            comparison_blocks.append(
                f"<article><h3>{safe(title)}</h3>"
                f"<p>Median behavioral deviation {'decreased' if decreased else 'increased'} "
                f"from {metric(before)} before repair to {metric(after)} after repair.</p>"
                + (
                    f"<p class=\"reduction\"><strong>{metric(repair_comparison['reduction'])}% reduction</strong></p>"
                    if decreased and repair_comparison["reduction"] is not None
                    else ""
                )
                + "</article>"
            )
        else:
            comparison_blocks.append(
                f"<article><h3>{safe(title)}</h3>"
                "<p>A before-and-after repair comparison was not observable in the supplied windows.</p></article>"
            )

    signal_rows = "".join(
        f"<tr><td>{safe(item.get('name'))}</td><td>{safe(item.get('system_name'))}</td>"
        f"<td>{'Included' if item.get('included') else 'Excluded'}</td>"
        f"<td>{safe('; '.join(item.get('exclusion_reasons') or ['No blocking issue']))}</td></tr>"
        for item in gate.get("signals", [])
    )
    data_quality_notes = [
        *[_presentation_quality_note(item) for item in gate.get("warnings", [])],
        *[
            _presentation_quality_note(item)
            for finding in findings
            for item in finding.get("data_quality_limitations", [])
        ],
    ]
    data_quality_notes = list(dict.fromkeys(item for item in data_quality_notes if item))
    data_quality_html = (
        "".join(f"<li>{safe(item)}</li>" for item in data_quality_notes)
        or "<li>No data quality note was recorded.</li>"
    )
    methodology_limitations = list(dict.fromkeys(gate.get("blocking_reasons", [])))
    methodology_limitations_html = (
        "".join(f"<li>{safe(item)}</li>" for item in methodology_limitations)
        or "<li>No additional methodology limitation was recorded for this assessment.</li>"
    )
    feedback_rows = "".join(
        f"<tr><td>{safe(item.get('recorded_at'))}</td><td>{safe(item.get('category'))}</td>"
        f"<td>{safe(item.get('finding_id'))}</td><td>{safe(item.get('note'))}</td><td>{safe(item.get('recorded_by'))}</td></tr>"
        for item in record.get("feedback_history", [])
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Neraium historical assessment</title>
<style>body{{font:14px/1.5 Arial,sans-serif;color:#17202a;max-width:1100px;margin:36px auto;padding:0 24px}}h1,h2,h3{{color:#10243d}}section{{margin:28px 0;page-break-inside:avoid}}article{{margin:16px 0}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{border:1px solid #ccd5df;padding:7px;text-align:left;vertical-align:top}}th{{background:#edf3f8}}.decision,.quality-notes,.methodology-note{{padding:14px;border-left:5px solid #356fa8;background:#f2f7fb}}.quality-notes{{border-left-color:#7893ab;background:#f5f8fa}}.operational-summary{{max-width:780px;font-size:16px}}.credibility{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:0;list-style:none}}.credibility li{{padding:10px;border:1px solid #c9ded7;background:#f4faf8}}.reduction{{color:#174f82}}@media print{{body{{margin:0}}}}</style></head>
<body><header><p>Neraium Golden Nugget historical assessment</p><h1>{safe(record.get('assessment_id'))}</h1>
<p>Generated {safe(now_iso())}. Event timestamps were not used by the analysis.</p></header>
<section><h2>Finding</h2>{''.join(finding_blocks) or '<p>No qualifying finding was produced.</p>'}</section>
<section><h2>What changed</h2>{''.join(change_blocks) or '<p>No persistent behavioral change met the evidence threshold.</p>'}</section>
<section><h2>Detection timeline</h2><p><strong>Recorded event:</strong> {safe(backtest.get('event_label'))}</p>
<table><thead><tr><th>Finding</th><th>First detection</th><th>Recorded event</th><th>Recorded repair</th><th>Lead time</th></tr></thead><tbody>{''.join(timeline_rows) or '<tr><td colspan="5">No finding timeline was available.</td></tr>'}</tbody></table></section>
<section><h2>Why this finding is credible</h2>{''.join(credibility_blocks) or '<p>No finding was available for validation.</p>'}</section>
<section><h2>Supporting relationship evidence</h2>
<table><thead><tr><th>Finding</th><th>Relationship</th><th>Mode</th><th>Before</th><th>After</th><th>Magnitude</th><th>Start</th><th>Exact records</th><th>Record SHA-256</th></tr></thead>
<tbody>{''.join(relationship_rows) or '<tr><td colspan="9">No supporting relationship evidence was available.</td></tr>'}</tbody></table></section>
<section><h2>Before-and-after repair comparison</h2>{''.join(comparison_blocks) or '<p>No repair comparison was available.</p>'}</section>
<section class="quality-notes"><h2>Data quality notes</h2><ul>{data_quality_html}</ul></section>
<section><h2>Methodology and limitations</h2><p class="methodology-note">{safe(METHODOLOGY_LIMITATION)}</p>
<p><strong>Method:</strong> {safe(analysis.get('method'))}. The recorded event timestamp was not used to produce the finding.</p>
<p class="decision"><strong>{safe(gate.get('decision'))}:</strong> {safe(gate.get('summary'))}</p>
<p><strong>Baseline dataset:</strong> {safe(record.get('datasets', {}).get('baseline', {}).get('filename'))}, {safe(baseline.get('start'))} to {safe(baseline.get('end'))} ({safe(baseline.get('usable_timestamp_rows'))} records)</p>
<p><strong>Comparison dataset:</strong> {safe(record.get('datasets', {}).get('comparison', {}).get('filename'))}, {safe(comparison.get('start'))} to {safe(comparison.get('end'))} ({safe(comparison.get('usable_timestamp_rows'))} records)</p>
<ul>{methodology_limitations_html}</ul>
<table><thead><tr><th>Signal</th><th>System</th><th>Decision</th><th>Reason</th></tr></thead><tbody>{signal_rows}</tbody></table></section>
<section><h2>Engineer feedback (append-only)</h2><table><thead><tr><th>Timestamp</th><th>Response</th><th>Finding</th><th>Notes</th><th>Engineer</th></tr></thead><tbody>{feedback_rows or '<tr><td colspan="5">No feedback recorded.</td></tr>'}</tbody></table></section>
</body></html>"""


def report_html(assessment_id: str) -> str:
    return build_report_html(_read_private_assessment(assessment_id))
