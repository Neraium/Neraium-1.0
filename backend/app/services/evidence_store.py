from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.runtime_db import list_evidence_runs_db, read_evidence_run_db, upsert_evidence_run_db


RUNTIME_DIR = get_settings().runtime_dir
EVIDENCE_DIR = RUNTIME_DIR / "evidence"
EVIDENCE_RUNS_PATH = EVIDENCE_DIR / "runs.json"


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
        f"- Input Hash: {record.get('input_hash')}",
        f"- Result Hash: {record.get('result_hash')}",
        "",
        "## Primary Drivers",
    ]
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
