from __future__ import annotations

import json
import csv
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.runtime_db import list_evidence_runs_db, read_evidence_run_db, upsert_evidence_run_db


RUNTIME_DIR = get_settings().runtime_dir
EVIDENCE_DIR = RUNTIME_DIR / "evidence"
EVIDENCE_RUNS_PATH = EVIDENCE_DIR / "runs.json"
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


def list_evidence_runs(limit: int = 50) -> list[dict[str, Any]]:
    db_items = list_evidence_runs_db(limit=limit)
    if db_items:
        return db_items
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
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]


def read_evidence_run(run_id: str) -> dict[str, Any] | None:
    db_item = read_evidence_run_db(run_id)
    if db_item is not None:
        return db_item
    for item in list_evidence_runs(limit=500):
        if item.get("run_id") == run_id:
            return item
    return None


def latest_evidence_run() -> dict[str, Any] | None:
    items = list_evidence_runs(limit=1)
    return items[0] if items else None


def upsert_evidence_run(record: dict[str, Any]) -> dict[str, Any]:
    upsert_evidence_run_db(record)
    path = evidence_runs_path()
    items = list_evidence_runs(limit=500)
    filtered = [item for item in items if item.get("run_id") != record.get("run_id")]
    updated = [record, *filtered]
    atomic_write_json_list(path, updated[:500])
    return record


def record_operator_feedback(run_id: str, category: str, note: str | None, actor: str, recorded_at: str) -> dict[str, Any]:
    if category not in FEEDBACK_CATEGORIES:
        raise ValueError("invalid_feedback_category")
    record = read_evidence_run(run_id)
    if record is None:
        raise ValueError("evidence_run_not_found")

    feedback_entry = {
        "category": category,
        "note": (note or "").strip() or None,
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


def csv_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    if any(token in text for token in [",", "\"", "\n"]):
        return "\"" + text.replace("\"", "\"\"") + "\""
    return text
