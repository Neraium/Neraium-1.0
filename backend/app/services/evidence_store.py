from __future__ import annotations

import json
import csv
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.runtime_db import list_evidence_runs_db, upsert_evidence_run_db


RUNTIME_DIR = get_settings().runtime_dir
EVIDENCE_DIR = RUNTIME_DIR / "evidence"
EVIDENCE_RUNS_PATH = EVIDENCE_DIR / "runs.json"
MAX_EVIDENCE_PAGE_SIZE = 100
DEFAULT_EVIDENCE_PAGE_SIZE = 50
EVIDENCE_HISTORY_CONTEXT = 500

FEEDBACK_CATEGORIES = [
    "confirmed_issue",
    "known_operational_change",
    "sensor_or_data_problem",
    "environmental_cause",
    "nothing_meaningful",
    "useful_warning",
    "expected_behavior",
    "false_positive",
    "maintenance_event",
    "ignore",
]


def ensure_evidence_dir() -> None:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)


def evidence_runs_path() -> Path:
    ensure_evidence_dir()
    return EVIDENCE_RUNS_PATH


def list_evidence_runs(limit: int = DEFAULT_EVIDENCE_PAGE_SIZE) -> list[dict[str, Any]]:
    return list_evidence_runs_page(limit=limit)["runs"]


def list_evidence_runs_page(*, limit: int = DEFAULT_EVIDENCE_PAGE_SIZE, offset: int = 0) -> dict[str, Any]:
    page_size = max(1, min(int(limit), MAX_EVIDENCE_PAGE_SIZE))
    page_offset = max(0, int(offset))
    raw_items = _load_raw_evidence_runs(
        limit=page_size + EVIDENCE_HISTORY_CONTEXT + 1,
        offset=page_offset,
    )
    page_items = raw_items[:page_size]
    page_ids = {str(item.get("run_id") or "") for item in page_items}
    annotated = _annotate_and_sort_evidence_runs(raw_items[: page_size + EVIDENCE_HISTORY_CONTEXT])
    runs = [item for item in annotated if str(item.get("run_id") or "") in page_ids]
    has_more = len(raw_items) > page_size
    return {
        "runs": runs,
        "limit": page_size,
        "offset": page_offset,
        "has_more": has_more,
        "next_offset": page_offset + page_size if has_more else None,
    }


def read_evidence_run(run_id: str) -> dict[str, Any] | None:
    raw_items = _load_raw_evidence_runs(limit=500)
    annotated_items = _annotate_and_sort_evidence_runs(raw_items)
    for item in annotated_items:
        if item.get("run_id") == run_id:
            return item
    return None


def latest_evidence_run() -> dict[str, Any] | None:
    items = list_evidence_runs(limit=1)
    return items[0] if items else None


def upsert_evidence_run(record: dict[str, Any]) -> dict[str, Any]:
    raw_items = _load_raw_evidence_runs(limit=500)
    prior_items = [item for item in raw_items if str(item.get("run_id") or "") != str(record.get("run_id") or "")]
    persisted = _annotate_evidence_record(record, prior_items)
    upsert_evidence_run_db(persisted)
    path = evidence_runs_path()
    items = [item for item in raw_items if str(item.get("run_id") or "") != str(record.get("run_id") or "")]
    updated = [persisted, *items]
    atomic_write_json_list(path, updated[:500])
    return persisted


def record_operator_feedback(
    run_id: str,
    category: str,
    note: str | None,
    actor: str,
    recorded_at: str,
    outcome: str | None = None,
    action_taken: str | None = None,
    intervention_at: str | None = None,
    followup_at: str | None = None,
) -> dict[str, Any]:
    if category not in FEEDBACK_CATEGORIES:
        raise ValueError("invalid_feedback_category")
    record = read_evidence_run(run_id)
    if record is None:
        raise ValueError("evidence_run_not_found")

    feedback_entry = {
        "category": category,
        "note": (note or "").strip() or None,
        "outcome": (outcome or "").strip() or validation_outcome_for_category(category),
        "action_taken": (action_taken or "").strip() or None,
        "intervention_at": (intervention_at or "").strip() or None,
        "followup_at": (followup_at or "").strip() or None,
        "actor": actor,
        "recorded_at": recorded_at,
    }
    history = [item for item in record.get("operator_feedback_history", []) if isinstance(item, dict)]
    updated_record = {
        **record,
        "latest_feedback_category": category,
        "operator_feedback_history": [feedback_entry, *history][:20],
    }
    return upsert_evidence_run(updated_record)


def build_evidence_export(record: dict[str, Any]) -> str:
    warnings = record.get("warnings") or []
    errors = record.get("errors") or []
    drivers = record.get("primary_drivers") or []
    evidence_summary = record.get("evidence_summary") or []
    archetypes = record.get("structural_archetypes") or []
    feedback_history = record.get("operator_feedback_history") or []
    validation_history = record.get("validation_event_history") or []
    before_after = record.get("before_after_intervention") or {}
    lines = [
        f"# Neraium Evidence Report",
        "",
        f"- Run ID: {record.get('run_id')}",
        f"- Source: {record.get('source_name') or record.get('source_type')}",
        f"- Source URL: {record.get('source_url')}",
        f"- Created At: {record.get('created_at')}",
        f"- Completed At: {record.get('completed_at')}",
        f"- Status: {record.get('status')}",
        f"- Rows Received: {record.get('rows_received')}",
        f"- Rows Accepted: {record.get('rows_accepted')}",
        f"- Rows Rejected: {record.get('rows_rejected')}",
        f"- Sensors Detected: {record.get('sensors_detected')}",
        f"- Room: {record.get('room')}",
        f"- Operating State: {record.get('operating_state')}",
        f"- Neraium Score: {record.get('neraium_score')}",
        f"- Drift Status: {record.get('drift_status')}",
        f"- Scenario: {record.get('scenario')}",
        f"- Tick: {record.get('tick')}",
        f"- Initiated By: {record.get('initiated_by')}",
        f"- Adaptive Site Key: {record.get('adaptive_site_key')}",
        f"- Latest Feedback Category: {record.get('latest_feedback_category')}",
        f"- Validation Status: {record.get('validation_status')}",
        f"- Validation Outcome: {record.get('validation_outcome')}",
        f"- Historical Fact: {record.get('historical_fact')}",
        f"- Observation Type: {record.get('observation_type')}",
        f"- Observation Status: {record.get('observation_status')}",
        f"- Structural State: {record.get('structural_state')}",
        f"- Regime Label: {record.get('regime_label')}",
        f"- Deformation Started At: {record.get('deformation_started_at')}",
        f"- Input Hash: {record.get('input_hash')}",
        f"- Result Hash: {record.get('result_hash')}",
        "",
        "## Variables",
    ]
    lines.extend([f"- {item}" for item in (record.get("variables") or [])] or ["- None recorded"])
    lines.extend(["", "## Drift Metrics"])
    drift_metrics = record.get("drift_metrics") or {}
    if isinstance(drift_metrics, dict) and drift_metrics:
        lines.extend([f"- {key}: {value}" for key, value in drift_metrics.items()])
    else:
        lines.append("- None recorded")
    lines.extend(["", "## Data Conditions"])
    lines.extend([f"- {item}" for item in (record.get("data_conditions") or [])] or ["- None recorded"])
    lines.extend([
        "",
        "## Primary Drivers",
    ])
    lines.extend([f"- {item}" for item in drivers] or ["- None recorded"])
    lines.extend(["", "## Interpretive Archetypes"])
    lines.extend([f"- {item}" for item in archetypes] or ["- None recorded"])
    lines.extend(["", "## Evidence Summary"])
    lines.extend([f"- {item}" for item in evidence_summary] or ["- None recorded"])
    lines.extend(["", "## Validation Event History"])
    lines.extend(
        [f"- {format_validation_history_item(item)}" for item in validation_history]
        or ["- No validation events recorded"]
    )
    lines.extend(["", "## Before/After Intervention"])
    lines.append(f"- {before_after.get('summary') or 'No prior reviewed intervention is available for comparison.'}")
    if before_after.get("available"):
        lines.append(f"- Before Run ID: {before_after.get('before_run_id')}")
        lines.append(f"- After Run ID: {before_after.get('after_run_id')}")
        lines.append(f"- Direction: {before_after.get('direction')}")
    lines.extend(["", "## Operator Feedback History"])
    lines.extend(
        [f"- {format_feedback_history_item(item)}" for item in feedback_history]
        or ["- No operator feedback recorded"]
    )
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {item}" for item in warnings] or ["- None"])
    lines.extend(["", "## Errors"])
    lines.extend([f"- {item}" for item in errors] or ["- None"])
    return "\n".join(lines)


def build_evidence_export_payload(record: dict[str, Any]) -> dict[str, Any]:
    return dict(record)


def build_evidence_export_csv(record: dict[str, Any]) -> str:
    flat = {
        "run_id": record.get("run_id"),
        "source_type": record.get("source_type"),
        "source_name": record.get("source_name"),
        "status": record.get("status"),
        "created_at": record.get("created_at"),
        "completed_at": record.get("completed_at"),
        "observation_type": record.get("observation_type"),
        "historical_fact": record.get("historical_fact"),
        "observation_status": record.get("observation_status"),
        "structural_state": record.get("structural_state"),
        "regime_label": record.get("regime_label"),
        "deformation_started_at": record.get("deformation_started_at"),
        "rows_received": record.get("rows_received"),
        "rows_accepted": record.get("rows_accepted"),
        "rows_rejected": record.get("rows_rejected"),
        "sensors_detected": record.get("sensors_detected"),
        "operating_state": record.get("operating_state"),
        "neraium_score": record.get("neraium_score"),
        "drift_status": record.get("drift_status"),
        "variables": "|".join(str(item) for item in (record.get("variables") or [])),
        "primary_drivers": "|".join(str(item) for item in (record.get("primary_drivers") or [])),
        "evidence_summary": "|".join(str(item) for item in (record.get("evidence_summary") or [])),
        "data_conditions": "|".join(str(item) for item in (record.get("data_conditions") or [])),
        "latest_feedback_category": record.get("latest_feedback_category"),
        "validation_status": record.get("validation_status"),
        "validation_outcome": record.get("validation_outcome"),
        "validation_event_history_json": json.dumps(record.get("validation_event_history") or [], sort_keys=True),
        "before_after_intervention_json": json.dumps(record.get("before_after_intervention") or {}, sort_keys=True),
        "drift_metrics_json": json.dumps(record.get("drift_metrics") or {}, sort_keys=True),
    }
    columns = list(flat.keys())
    values = [csv_escape(flat[column]) for column in columns]
    return ",".join(columns) + "\n" + ",".join(values) + "\n"


def digest_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def digest_payload(payload: Any) -> str:
    return digest_text(json.dumps(payload, sort_keys=True, default=str))


def atomic_write_json_list(path: Path, payload: list[dict[str, Any]]) -> None:
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(path)


def format_feedback_history_item(item: dict[str, Any]) -> str:
    recorded_at = item.get("recorded_at")
    category = item.get("category")
    actor = item.get("actor")
    note = item.get("note")
    note_suffix = f" - {note}" if note else ""
    return f"{recorded_at}: {category} ({actor}){note_suffix}"


def format_validation_history_item(item: dict[str, Any]) -> str:
    recorded_at = item.get("recorded_at")
    category = item.get("category_label") or item.get("category")
    status = item.get("status")
    action_taken = item.get("action_taken")
    note = item.get("note")
    details = [str(value) for value in [action_taken, note] if value]
    detail_suffix = " - " + " | ".join(details) if details else ""
    return f"{recorded_at}: {category} ({status}){detail_suffix}"


def csv_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    # CSV quoting does not stop spreadsheet applications from evaluating formulas.
    if text.startswith(("=", "+", "-", "@", "\t", "\r")):
        text = "'" + text
    if any(token in text for token in [",", "\"", "\n"]):
        return "\"" + text.replace("\"", "\"\"") + "\""
    return text


def _load_raw_evidence_runs(limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
    db_items = list_evidence_runs_db(limit=limit, offset=offset)
    if db_items:
        return [item for item in db_items if isinstance(item, dict)]
    # Only consult the legacy JSON store when SQLite has no evidence at all.
    # Otherwise an empty final DB page could incorrectly restart pagination.
    if offset > 0 and list_evidence_runs_db(limit=1, offset=0):
        return []
    path = evidence_runs_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    items = [item for item in payload if isinstance(item, dict)]
    return items[max(0, offset) : max(0, offset) + max(1, limit)]


def _annotate_and_sort_evidence_runs(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(items, key=_evidence_sort_key)
    annotated: list[dict[str, Any]] = []
    history_index = _new_annotation_history_index()
    for item in ordered:
        annotated.append(_annotate_evidence_record_indexed(item, history_index))
        _index_annotation_history(item, history_index)
    annotated.sort(key=_evidence_sort_key, reverse=True)
    return annotated


def _new_annotation_history_index() -> dict[str, Any]:
    return {
        "next_bit": 1,
        "historical_masks": {},
        "historical_category_masks": {},
        "historical_categories": {},
        "latest_reviewed": {},
    }


def _record_observation_keys(record: dict[str, Any]) -> tuple[str, set[str]]:
    observation_type = str(record.get("observation_type") or "").strip()
    variables = {str(variable).strip() for variable in (record.get("variables") or []) if str(variable).strip()}
    return observation_type, variables


def _index_annotation_history(record: dict[str, Any], index: dict[str, Any]) -> None:
    observation_type, variables = _record_observation_keys(record)
    if not observation_type or not variables:
        return

    category = str(record.get("latest_feedback_category") or "").strip()
    if category:
        bit = int(index["next_bit"])
        index["next_bit"] = bit << 1
        index["historical_categories"].setdefault(observation_type, set()).add(category)
        for variable in variables:
            key = (observation_type, variable)
            index["historical_masks"][key] = int(index["historical_masks"].get(key, 0)) | bit
            category_key = (observation_type, variable, category)
            index["historical_category_masks"][category_key] = int(index["historical_category_masks"].get(category_key, 0)) | bit

    if build_validation_event_history(record):
        for variable in variables:
            index["latest_reviewed"][(observation_type, variable)] = record


def _historical_fact_from_index(record: dict[str, Any], index: dict[str, Any]) -> str | None:
    observation_type, variables = _record_observation_keys(record)
    if not observation_type or not variables:
        return None

    match_mask = 0
    for variable in variables:
        match_mask |= int(index["historical_masks"].get((observation_type, variable), 0))
    match_count = match_mask.bit_count()
    if not match_count:
        return None

    category_counts: dict[str, int] = {}
    for category in index["historical_categories"].get(observation_type, set()):
        category_mask = 0
        for variable in variables:
            category_mask |= int(index["historical_category_masks"].get((observation_type, variable, category), 0))
        count = category_mask.bit_count()
        if count:
            category_counts[category] = count
    if not category_counts:
        return None

    dominant_category, dominant_count = sorted(category_counts.items(), key=lambda entry: (-entry[1], entry[0]))[0]
    category_label = _feedback_category_label(dominant_category)
    ordered_variables = [str(variable).strip() for variable in (record.get("variables") or []) if str(variable).strip()]
    variable_names = ", ".join(ordered_variables[:2])
    variable_phrase = variable_names if variable_names else "these variables"
    return (
        f"Similar {observation_type.replace('_', ' ')} observations involving {variable_phrase} "
        f"were later marked {category_label} in {dominant_count} of {match_count} previous investigations."
    )


def _before_after_from_index(record: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    observation_type, variables = _record_observation_keys(record)
    if not observation_type or not variables:
        return {"available": False, "summary": "No prior reviewed intervention is available for comparison."}
    candidates = {
        str(candidate.get("run_id") or ""): candidate
        for variable in variables
        if (candidate := index["latest_reviewed"].get((observation_type, variable))) is not None
    }
    if not candidates:
        return {"available": False, "summary": "No prior reviewed intervention is available for comparison."}
    before = sorted(candidates.values(), key=_evidence_sort_key)[-1]
    return _compare_intervention_records(record, before)


def _annotate_evidence_record_indexed(record: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    historical_fact = _historical_fact_from_index(record, index)
    validation_event_history = build_validation_event_history(record)
    latest_feedback = validation_event_history[0] if validation_event_history else {}
    latest_category = str(record.get("latest_feedback_category") or latest_feedback.get("category") or "").strip()
    validation_status = validation_status_for_category(latest_category) if latest_category else record.get("validation_status")
    validation_outcome = str(latest_feedback.get("outcome") or record.get("validation_outcome") or "").strip()
    if not validation_outcome and latest_category:
        validation_outcome = validation_outcome_for_category(latest_category)
    return {
        **record,
        "historical_fact": historical_fact or record.get("historical_fact") or None,
        "validation_event_history": validation_event_history,
        "validation_status": validation_status,
        "validation_outcome": validation_outcome,
        "before_after_intervention": _before_after_from_index(record, index),
    }


def _annotate_evidence_record(record: dict[str, Any], prior_records: list[dict[str, Any]]) -> dict[str, Any]:
    historical_fact = build_historical_fact(record, prior_records)
    validation_event_history = build_validation_event_history(record)
    latest_feedback = validation_event_history[0] if validation_event_history else {}
    latest_category = str(record.get("latest_feedback_category") or latest_feedback.get("category") or "").strip()
    validation_status = validation_status_for_category(latest_category) if latest_category else record.get("validation_status")
    validation_outcome = str(latest_feedback.get("outcome") or record.get("validation_outcome") or "").strip()
    if not validation_outcome and latest_category:
        validation_outcome = validation_outcome_for_category(latest_category)
    return {
        **record,
        "historical_fact": historical_fact or record.get("historical_fact") or None,
        "validation_event_history": validation_event_history,
        "validation_status": validation_status,
        "validation_outcome": validation_outcome,
        "before_after_intervention": build_before_after_intervention(record, prior_records),
    }


def validation_outcome_for_category(category: str) -> str | None:
    mapping = {
        "confirmed_issue": "confirmed",
        "useful_warning": "confirmed",
        "maintenance_event": "action_taken",
        "known_operational_change": "explained",
        "sensor_or_data_problem": "explained",
        "environmental_cause": "explained",
        "nothing_meaningful": "false_positive",
        "expected_behavior": "expected",
        "false_positive": "false_positive",
        "ignore": "ignored",
    }
    return mapping.get(str(category or "").strip())


def validation_status_for_category(category: str) -> str:
    normalized = str(category or "").strip()
    if normalized in {"confirmed_issue", "useful_warning", "maintenance_event"}:
        return "confirmed"
    if normalized in {"false_positive", "nothing_meaningful", "ignore", "expected_behavior"}:
        return "dismissed"
    if normalized in {"known_operational_change", "environmental_cause", "sensor_or_data_problem"}:
        return "explained"
    return "reviewed"


def build_validation_event_history(record: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for item in record.get("operator_feedback_history") or []:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        if not category:
            continue
        events.append({
            "type": "operator_feedback",
            "category": category,
            "category_label": _feedback_category_label(category),
            "status": validation_status_for_category(category),
            "outcome": str(item.get("outcome") or "").strip() or validation_outcome_for_category(category),
            "action_taken": item.get("action_taken"),
            "note": item.get("note"),
            "actor": item.get("actor"),
            "recorded_at": item.get("recorded_at"),
            "intervention_at": item.get("intervention_at"),
            "followup_at": item.get("followup_at"),
        })
    return events[:20]


def build_before_after_intervention(record: dict[str, Any], prior_records: list[dict[str, Any]]) -> dict[str, Any]:
    current_variables = {str(variable).strip() for variable in (record.get("variables") or []) if str(variable).strip()}
    current_type = str(record.get("observation_type") or "").strip()
    current_strength = _drift_strength(record)
    candidates: list[dict[str, Any]] = []
    for prior in prior_records:
        if str(prior.get("run_id") or "") == str(record.get("run_id") or ""):
            continue
        if current_type and str(prior.get("observation_type") or "").strip() != current_type:
            continue
        prior_variables = {str(variable).strip() for variable in (prior.get("variables") or []) if str(variable).strip()}
        if current_variables and prior_variables and current_variables.isdisjoint(prior_variables):
            continue
        if not build_validation_event_history(prior):
            continue
        candidates.append(prior)

    if not candidates:
        return {"available": False, "summary": "No prior reviewed intervention is available for comparison."}

    before = sorted(candidates, key=_evidence_sort_key)[-1]
    return _compare_intervention_records(record, before)


def _compare_intervention_records(record: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    current_variables = {str(variable).strip() for variable in (record.get("variables") or []) if str(variable).strip()}
    current_strength = _drift_strength(record)
    before_strength = _drift_strength(before)
    before_variables = {str(variable).strip() for variable in (before.get("variables") or []) if str(variable).strip()}
    shared_variables = sorted(current_variables.intersection(before_variables))
    direction = "unknown"
    delta = None
    if before_strength is not None and current_strength is not None:
        delta = round(current_strength - before_strength, 4)
        if delta < -0.05:
            direction = "improved"
        elif delta > 0.05:
            direction = "worsened"
        else:
            direction = "unchanged"
    label = direction if direction != "unknown" else "needs more comparable measurements"
    return {
        "available": True,
        "before_run_id": before.get("run_id"),
        "after_run_id": record.get("run_id"),
        "shared_variables": shared_variables,
        "before_strength": before_strength,
        "after_strength": current_strength,
        "delta": delta,
        "direction": direction,
        "summary": f"Compared with the prior reviewed event, the follow-up signal {label}.",
    }


def _drift_strength(record: dict[str, Any]) -> float | None:
    metrics = record.get("drift_metrics") if isinstance(record.get("drift_metrics"), dict) else {}
    value = metrics.get("baseline_distance") if isinstance(metrics, dict) else None
    if value is None and isinstance(metrics, dict):
        value = metrics.get("drift_index")
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return numeric if numeric == numeric else None


def _evidence_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    return (str(item.get("created_at") or ""), str(item.get("run_id") or ""))


def build_historical_fact(record: dict[str, Any], prior_records: list[dict[str, Any]]) -> str | None:
    current_type = str(record.get("observation_type") or "").strip()
    current_variables = [str(variable).strip() for variable in (record.get("variables") or []) if str(variable).strip()]
    if not current_type or len(current_variables) < 1:
        return None

    current_variable_set = set(current_variables)
    matches: list[dict[str, Any]] = []
    for prior in prior_records:
        if str(prior.get("run_id") or "") == str(record.get("run_id") or ""):
            continue
        if str(prior.get("observation_type") or "").strip() != current_type:
            continue
        prior_variables = {str(variable).strip() for variable in (prior.get("variables") or []) if str(variable).strip()}
        if not prior_variables or current_variable_set.isdisjoint(prior_variables):
            continue
        if not prior.get("latest_feedback_category"):
            continue
        matches.append(prior)

    if not matches:
        return None

    category_counts: dict[str, int] = {}
    for item in matches:
        category = str(item.get("latest_feedback_category") or "").strip()
        if not category:
            continue
        category_counts[category] = category_counts.get(category, 0) + 1

    if not category_counts:
        return None

    dominant_category, dominant_count = sorted(category_counts.items(), key=lambda entry: (-entry[1], entry[0]))[0]
    category_label = _feedback_category_label(dominant_category)
    variable_names = ", ".join(current_variables[:2])
    variable_phrase = variable_names if variable_names else "these variables"
    match_count = len(matches)
    return (
        f"Similar {current_type.replace('_', ' ')} observations involving {variable_phrase} "
        f"were later marked {category_label} in {dominant_count} of {match_count} previous investigations."
    )


def _feedback_category_label(category: str) -> str:
    return str(category).replace("_", " ").strip() or "unclassified"
