from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.auth_store import workflow_member, workspace_assignment_member
from app.services.dataset_scope import current_dataset_scope, dataset_scope_context, dataset_scope_from_payload
from app.services.runtime_db import db_connection, init_runtime_db, now_iso
from app.services.workspace_authorization import current_workspace_context


SOURCE_KINDS = {"evidence_run", "live_finding"}
WORKFLOW_STATUSES = {
    "open", "acknowledged", "investigating", "waiting", "escalated",
    "awaiting_review", "monitoring", "resolved", "dismissed",
}
PRIORITIES = {"low", "medium", "high", "critical"}
WORKFLOW_FIELDS = {
    "status", "user_priority", "assignment", "due_at", "manager_note",
    "work_order_reference", "external_reference", "validation_outcome", "validation_note",
}


class FindingNotFoundError(LookupError):
    pass


class FindingWorkflowConflictError(RuntimeError):
    def __init__(self, reason: str, *, current_version: int):
        super().__init__(reason)
        self.reason = reason
        self.current_version = current_version


class FindingWorkflowValidationError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


_VIEWER_STATUSES = {"acknowledged", "investigating", "waiting", "escalated", "awaiting_review"}
_STATUS_TRANSITIONS = {
    "open": {"acknowledged", "investigating", "monitoring", "escalated", "resolved", "dismissed"},
    "acknowledged": {"investigating", "waiting", "escalated", "monitoring", "resolved", "dismissed"},
    "investigating": {"waiting", "escalated", "awaiting_review", "monitoring", "resolved", "dismissed"},
    "waiting": {"investigating", "escalated", "awaiting_review", "resolved", "dismissed"},
    "escalated": {"investigating", "waiting", "awaiting_review", "monitoring", "resolved", "dismissed"},
    "awaiting_review": {"investigating", "waiting", "escalated", "monitoring", "resolved", "dismissed"},
    "monitoring": {"open", "investigating", "awaiting_review", "resolved", "dismissed"},
    "resolved": {"open", "monitoring"},
    "dismissed": {"open", "monitoring"},
}


def evidence_finding_id(run_id: str, source_finding_key: str) -> str:
    material = f"evidence_run\0{run_id}\0{source_finding_key}".encode("utf-8")
    return f"evidence-finding-{hashlib.sha256(material).hexdigest()[:32]}"


def _json(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, default=str)


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _source_finding_candidates(record: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    snapshot = record.get("finding_identity_snapshot")
    candidates: list[tuple[str, dict[str, Any]]] = []
    if isinstance(snapshot, list):
        for index, item in enumerate(snapshot):
            if not isinstance(item, dict):
                continue
            finding = item.get("finding") if isinstance(item.get("finding"), dict) else item
            key = _clean(
                item.get("source_finding_id")
                or finding.get("condition_id")
                or finding.get("finding_id")
                or finding.get("id")
            ) or f"finding-{index}"
            candidates.append((key, dict(finding)))
        if candidates:
            return _dedupe_candidates(candidates)

    # Older records stored at most the primary condition. Do not infer missing
    # siblings from run-level status or assignment history.
    condition = record.get("condition")
    if isinstance(condition, dict) and condition:
        key = _clean(
            condition.get("condition_id")
            or condition.get("finding_id")
            or condition.get("id")
            or record.get("condition_id")
        ) or "primary-condition"
        return [(key, dict(condition))]
    if _clean(record.get("condition_id")):
        key = str(record["condition_id"]).strip()
        return [(key, {"condition_id": key, "headline": record.get("finding_title")})]

    # Legacy observations without an analytical condition remain addressable as
    # one compatibility case. This is an identity fallback, not a diagnosis.
    return [
        (
            "run-observation",
            {
                "object_type": "observation",
                "id": "run-observation",
                "title": record.get("finding_title") or (record.get("primary_drivers") or [None])[0],
                "observation_type": record.get("observation_type"),
                "variables": list(record.get("variables") or []),
            },
        )
    ]


def _dedupe_candidates(candidates: list[tuple[str, dict[str, Any]]]) -> list[tuple[str, dict[str, Any]]]:
    seen: set[str] = set()
    result: list[tuple[str, dict[str, Any]]] = []
    for key, finding in candidates:
        if key in seen:
            continue
        seen.add(key)
        result.append((key, finding))
    return result


def _evidence_source_snapshot(
    record: dict[str, Any], source_finding_key: str, finding: dict[str, Any]
) -> dict[str, Any]:
    return {
        "source_run_id": str(record.get("run_id") or ""),
        "source_type": record.get("source_type"),
        "source_name": record.get("source_name"),
        "created_at": record.get("created_at"),
        "completed_at": record.get("completed_at"),
        "source_finding_key": source_finding_key,
        "evidence_hash": record.get("evidence_hash"),
        "input_hash": record.get("input_hash"),
        "result_hash": record.get("result_hash"),
        "provenance": dict(record.get("provenance") or {}),
        "recommended_priority": _recommended_priority(finding),
        "initial_status": _initial_evidence_status(record),
        "finding": finding,
    }


def _recommended_priority(finding: dict[str, Any]) -> str | None:
    values = (
        finding.get("recommended_priority"),
        finding.get("priority"),
        (finding.get("classification") or {}).get("recommended_priority")
        if isinstance(finding.get("classification"), dict) else None,
        (finding.get("classification") or {}).get("severity")
        if isinstance(finding.get("classification"), dict) else None,
        finding.get("severity"),
    )
    for value in values:
        normalized = str(value or "").strip().lower()
        if normalized in PRIORITIES:
            return normalized
        if normalized in {"moderate", "review"}:
            return "medium"
        if normalized in {"elevated"}:
            return "high"
    return None


def _initial_evidence_status(record: dict[str, Any]) -> str:
    status = str(record.get("observation_status") or "open").strip().lower()
    return status if status in WORKFLOW_STATUSES else "open"


def materialize_evidence_finding_cases(record: dict[str, Any]) -> list[str]:
    run_id = _clean(record.get("run_id"))
    if not run_id:
        return []
    explicit_snapshot = isinstance(record.get("finding_identity_snapshot"), list) and bool(
        record.get("finding_identity_snapshot")
    )
    explicit_condition = bool(record.get("condition_id")) or (
        isinstance(record.get("condition"), dict) and bool(record.get("condition"))
    )
    evidence_status = str(record.get("status") or "").strip().lower()
    if not (explicit_snapshot or explicit_condition) and evidence_status not in {
        "complete", "completed", "completed_compatibility",
    }:
        # Uploads persist pending/processing evidence records before analytical
        # finding identity is final. Materializing that provisional run shell
        # would permanently claim the later immutable finding identity/scope.
        return []
    init_runtime_db()
    created_at = str(record.get("created_at") or now_iso())
    dataset_scope = dataset_scope_from_payload(record)
    scope_storage_id = dataset_scope.storage_id if dataset_scope is not None else None
    dataset_scope_json = _json(dataset_scope.as_dict()) if dataset_scope is not None else None
    identifiers: list[str] = []
    with db_connection() as connection:
        for source_key, finding in _source_finding_candidates(record):
            finding_id = evidence_finding_id(run_id, source_key)
            identifiers.append(finding_id)
            connection.execute(
                """
                INSERT OR IGNORE INTO finding_cases (
                    finding_id, source_kind, source_id, source_finding_key,
                    scope_storage_id, dataset_scope_json, source_snapshot_json, created_at
                ) VALUES (?, 'evidence_run', ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding_id, run_id, source_key, scope_storage_id, dataset_scope_json,
                    _json(_evidence_source_snapshot(record, source_key, finding)), created_at,
                ),
            )
            existing = connection.execute(
                "SELECT scope_storage_id FROM finding_cases WHERE finding_id = ?", (finding_id,)
            ).fetchone()
            existing_scope = existing["scope_storage_id"] if existing else None
            if existing_scope != scope_storage_id and (existing_scope is not None or scope_storage_id is not None):
                raise ValueError("finding_case_scope_conflict")
    _migrate_legacy_events_if_unambiguous(run_id)
    return identifiers


def _live_snapshot(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "source_run_id": str(row["source_live_analysis_run_id"]),
        "source_type": "live_analysis",
        "source_finding_key": str(row["finding_id"]),
        "created_at": row["created_at"],
        "recommended_priority": None,
        "initial_status": "resolved" if str(row["current_state"]) == "resolved" else "open",
        "finding": {
            "finding_id": str(row["finding_id"]),
            "system_id": row["system_id"],
            "relationship_identity": row["relationship_identity"],
            "classification": json.loads(row["finding_classification_json"]),
            "first_detected_at": row["first_detected_at"],
            "last_observed_at": row["last_observed_at"],
            "latest_evidence": json.loads(row["latest_evidence_json"]),
            "baseline_reference": row["baseline_reference"],
        },
    }


def materialize_live_finding_cases(
    finding_id: str | None = None, *, source_run_id: str | None = None
) -> list[str]:
    init_runtime_db()
    query = "SELECT * FROM live_findings WHERE scope_storage_id = ?"
    params: tuple[Any, ...] = (current_dataset_scope().storage_id,)
    if finding_id:
        query += " AND finding_id = ?"
        params = (*params, finding_id)
    elif source_run_id:
        query += " AND source_live_analysis_run_id = ?"
        params = (*params, source_run_id)
    with db_connection() as connection:
        rows = connection.execute(query, params).fetchall()
        scope = current_dataset_scope()
        scope_json = _json(scope.as_dict())
        for row in rows:
            live_id = str(row["finding_id"])
            connection.execute(
                """
                INSERT OR IGNORE INTO finding_cases (
                    finding_id, source_kind, source_id, source_finding_key,
                    scope_storage_id, dataset_scope_json, source_snapshot_json, created_at
                ) VALUES (?, 'live_finding', ?, ?, ?, ?, ?, ?)
                """,
                (
                    live_id, live_id, live_id, scope.storage_id, scope_json,
                    _json(_live_snapshot(row)), row["created_at"],
                ),
            )
    return [str(row["finding_id"]) for row in rows]


def materialize_existing_finding_cases(
    *, source_run_id: str | None = None, source_kind: str | None = None
) -> None:
    init_runtime_db()
    if source_kind != "live_finding":
        query = "SELECT payload_json FROM evidence_runs WHERE scope_storage_id = ?"
        params: tuple[Any, ...] = (current_dataset_scope().storage_id,)
        if source_run_id:
            query += " AND run_id = ?"
            params = (*params, source_run_id)
        query += " ORDER BY created_at DESC LIMIT 1001"
        with db_connection() as connection:
            records = [json.loads(row["payload_json"]) for row in connection.execute(query, params).fetchall()]
        for record in records:
            materialize_evidence_finding_cases(record)
    if source_kind != "evidence_run":
        materialize_live_finding_cases(source_run_id=source_run_id)


def _raw_case(finding_id: str) -> dict[str, Any] | None:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM finding_cases
            WHERE finding_id = ? AND scope_storage_id = ?
            """,
            (finding_id, current_dataset_scope().storage_id),
        ).fetchone()
    if row is None:
        return None
    return {
        "finding_id": str(row["finding_id"]),
        "source_kind": str(row["source_kind"]),
        "source_id": str(row["source_id"]),
        "source_finding_key": str(row["source_finding_key"]),
        "scope_storage_id": row["scope_storage_id"],
        "source_snapshot": json.loads(row["source_snapshot_json"]),
        "created_at": str(row["created_at"]),
    }


def _events(finding_id: str) -> list[dict[str, Any]]:
    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT payload_json FROM finding_workflow_events
            WHERE finding_id = ? ORDER BY version ASC
            """,
            (finding_id,),
        ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def _default_workflow(case: dict[str, Any]) -> dict[str, Any]:
    snapshot = case["source_snapshot"]
    recommended = snapshot.get("recommended_priority")
    return {
        "version": 0,
        "status": snapshot.get("initial_status") or "open",
        "recommended_priority": recommended,
        "user_priority": None,
        "effective_priority": recommended,
        "assignment": None,
        "assigned_by": None,
        "assignment_history": [],
        "due_at": None,
        "manager_note": None,
        "work_order_reference": None,
        "external_reference": None,
        "validation_outcome": None,
        "validation_note": None,
        "latest_feedback": None,
        "latest_field_report": None,
        "field_reports": [],
        "resolution": None,
        "updated_at": None,
        "updated_by": None,
    }


def _project(case: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    workflow = _default_workflow(case)
    for event in events:
        event_type = str(event.get("event_type") or "")
        changes = event.get("changes") if isinstance(event.get("changes"), dict) else {}
        if event_type in {"workflow_updated", "legacy_status_imported"}:
            prior_assignment = workflow.get("assignment")
            for field in WORKFLOW_FIELDS:
                if field in changes:
                    workflow[field] = changes[field]
            if "assignment" in changes:
                assignment = changes.get("assignment")
                workflow["assigned_by"] = event.get("actor") if assignment else None
                workflow["assignment_history"].append({
                    "action": "reassigned" if prior_assignment and assignment else (
                        "assigned" if assignment else "unassigned"
                    ),
                    "from": prior_assignment,
                    "to": assignment,
                    "actor": event.get("actor"),
                    "recorded_at": event.get("recorded_at"),
                    "version": event.get("version"),
                })
        elif event_type in {"feedback_recorded", "legacy_feedback_imported"}:
            feedback = event.get("feedback") if isinstance(event.get("feedback"), dict) else {}
            workflow["latest_feedback"] = feedback or None
            if feedback.get("outcome"):
                workflow["validation_outcome"] = feedback["outcome"]
            if feedback.get("note"):
                workflow["validation_note"] = feedback["note"]
        elif event_type == "field_report_recorded":
            report = event.get("field_report") if isinstance(event.get("field_report"), dict) else {}
            if report:
                workflow["latest_field_report"] = report
                workflow["field_reports"].append(report)
                if report.get("needs_escalation"):
                    workflow["status"] = "escalated"
                elif report.get("investigation_complete"):
                    workflow["status"] = "awaiting_review"
        elif event_type == "resolution_recorded":
            workflow["status"] = "resolved"
            workflow["resolution"] = event.get("resolution")
            workflow["validation_outcome"] = (event.get("resolution") or {}).get("outcome")
            workflow["validation_note"] = (event.get("resolution") or {}).get("note")
        workflow["version"] = int(event.get("version") or workflow["version"])
        workflow["updated_at"] = event.get("recorded_at")
        workflow["updated_by"] = event.get("actor")
    workflow["effective_priority"] = workflow["user_priority"] or workflow["recommended_priority"]
    return workflow


def _normalized_person_assignment(assignment: Any) -> Any:
    """Validate directory-backed person assignments without rewriting legacy references."""
    if not isinstance(assignment, dict) or assignment.get("target_type") != "person":
        return assignment
    member_id = _clean(assignment.get("external_ref"))
    if member_id is None:
        # Existing events remain projectable, but assignment is authorization-
        # independent and every new person assignment must name an account.
        raise FindingWorkflowValidationError("assignment_member_required")
    workspace = current_workspace_context()
    if workspace.is_explicit:
        member = workspace_assignment_member(
            workspace.workspace_id, member_id, include_inactive=True
        )
    elif member_id.strip().lower() == workspace.dataset_scope.user_id:
        member = workflow_member(member_id, include_inactive=True)
    else:
        member = None
    if member is None:
        raise FindingWorkflowValidationError("unknown_assignment_member")
    if not member["is_active"]:
        raise FindingWorkflowValidationError("inactive_assignment_member")
    return {
        "target_type": "person",
        "label": member["display_name"],
        "external_ref": member["member_id"],
    }


def _is_exact_active_member_assignment(workflow: dict[str, Any], actor: str) -> bool:
    assignment = workflow.get("assignment")
    if not isinstance(assignment, dict) or assignment.get("target_type") != "person":
        return False
    member_id = _clean(assignment.get("external_ref"))
    normalized_actor = str(actor or "").strip().lower()
    if member_id is None or member_id.strip().lower() != normalized_actor:
        return False
    workspace = current_workspace_context()
    if workspace.is_explicit:
        member = workspace_assignment_member(
            workspace.workspace_id, member_id, include_inactive=False
        )
    elif member_id.strip().lower() == workspace.dataset_scope.user_id:
        member = workflow_member(member_id, include_inactive=False)
    else:
        member = None
    return bool(member and member["member_id"] == normalized_actor)


def authorize_finding_action(
    finding_id: str, *, actor: str, role: str, strict: bool,
    action: str, changes: dict[str, Any] | None = None,
) -> None:
    """Apply the small production workflow policy at the authoritative boundary."""
    # Resolve the resource boundary before action policy so foreign and missing
    # identifiers have the same opaque result for every role.
    case = read_finding_case(finding_id)
    if not strict:
        return
    normalized_role = str(role or "viewer").strip().lower()
    if normalized_role in {"operator", "admin"}:
        return
    if normalized_role != "viewer":
        raise FindingWorkflowValidationError("workflow_action_forbidden")
    if not _is_exact_active_member_assignment(case["workflow"], actor):
        raise FindingWorkflowValidationError("workflow_action_forbidden")
    if action == "field_report":
        return
    if action != "workflow" or not changes or set(changes) != {"status"}:
        raise FindingWorkflowValidationError("workflow_action_forbidden")
    target = changes.get("status")
    if target not in _VIEWER_STATUSES:
        raise FindingWorkflowValidationError("workflow_action_forbidden")


def validate_status_transition(
    current_status: str, target_status: str, *, strict: bool,
) -> None:
    if target_status not in WORKFLOW_STATUSES:
        raise FindingWorkflowValidationError("unsupported_workflow_status")
    if not strict or current_status == target_status:
        return
    if target_status not in _STATUS_TRANSITIONS.get(current_status, set()):
        raise FindingWorkflowValidationError(
            f"invalid_status_transition:{current_status}:{target_status}"
        )


def _case_response(case: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    snapshot = case["source_snapshot"]
    latest_at = events[-1].get("recorded_at") if events else None
    return {
        "finding_id": case["finding_id"],
        "source": {
            "kind": case["source_kind"],
            "id": case["source_id"],
            "finding_key": case["source_finding_key"],
            "run_id": snapshot.get("source_run_id"),
        },
        "evidence": snapshot,
        "workflow": _project(case, events),
        "activity": {
            "count": len(events),
            "latest_event_at": latest_at,
            "url": f"/api/findings/{case['finding_id']}/activity",
        },
        "created_at": case["created_at"],
    }


def read_finding_case(finding_id: str) -> dict[str, Any]:
    case = _raw_case(finding_id)
    if case is None and finding_id.startswith("live-finding-"):
        materialize_live_finding_cases(finding_id)
        case = _raw_case(finding_id)
    if case is None:
        raise FindingNotFoundError("Finding not found.")
    if case["source_kind"] == "evidence_run":
        _migrate_legacy_events_if_unambiguous(case["source_id"])
    return _case_response(case, _events(finding_id))


def list_finding_cases(
    *, source_kind: str | None = None, source_run_id: str | None = None,
    workflow_status: str | None = None, priority: str | None = None,
    system: str | None = None, assigned_to_me: bool = False,
    assignee: str | None = None, unassigned: bool = False, overdue: bool = False,
    in_progress: bool = False, awaiting_review: bool = False,
    recently_resolved: bool = False, active: bool = False,
    actor: str | None = None, limit: int = 50, offset: int = 0,
) -> dict[str, Any]:
    materialize_existing_finding_cases(source_run_id=source_run_id, source_kind=source_kind)
    init_runtime_db()
    conditions: list[str] = []
    params: list[Any] = []
    if source_kind:
        conditions.append("source_kind = ?")
        params.append(source_kind)
    if source_run_id:
        conditions.append("json_extract(source_snapshot_json, '$.source_run_id') = ?")
        params.append(source_run_id)
    conditions.append("scope_storage_id = ?")
    params.append(current_dataset_scope().storage_id)
    query = "SELECT finding_id FROM finding_cases"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY created_at DESC, finding_id DESC LIMIT 1001"
    with db_connection() as connection:
        identifiers = [str(row["finding_id"]) for row in connection.execute(query, tuple(params)).fetchall()]
    cases = [read_finding_case(identifier) for identifier in identifiers]
    if workflow_status:
        cases = [item for item in cases if item["workflow"]["status"] == workflow_status]
    if priority:
        cases = [item for item in cases if item["workflow"]["effective_priority"] == priority]
    if system:
        wanted_system = system.strip().lower()
        cases = [
            item for item in cases
            if wanted_system in {
                str((item["evidence"].get("finding") or {}).get("system_id") or "").strip().lower(),
                str((item["evidence"].get("finding") or {}).get("system_name") or "").strip().lower(),
            }
        ]

    def assignment_id(item: dict[str, Any]) -> str | None:
        assignment = item["workflow"].get("assignment")
        if not isinstance(assignment, dict):
            return None
        return _clean(assignment.get("external_ref"))

    if assigned_to_me:
        normalized_actor = str(actor or "").strip().lower()
        cases = [
            item for item in cases
            if (assignment_id(item) or "").strip().lower() == normalized_actor
        ]
    if assignee:
        normalized_assignee = assignee.strip().lower()
        cases = [
            item for item in cases
            if (assignment_id(item) or "").strip().lower() == normalized_assignee
        ]
    if unassigned:
        cases = [item for item in cases if item["workflow"].get("assignment") is None]
    terminal_statuses = {"resolved", "dismissed"}
    if active:
        cases = [item for item in cases if item["workflow"]["status"] not in terminal_statuses]
    if in_progress:
        cases = [
            item for item in cases
            if item["workflow"]["status"] in {"acknowledged", "investigating", "waiting", "escalated"}
        ]
    if awaiting_review:
        cases = [item for item in cases if item["workflow"]["status"] == "awaiting_review"]
    now = datetime.now(timezone.utc)
    if overdue:
        def is_overdue(item: dict[str, Any]) -> bool:
            due_at = item["workflow"].get("due_at")
            if not due_at or item["workflow"]["status"] in terminal_statuses:
                return False
            try:
                parsed = datetime.fromisoformat(str(due_at).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc) < now
            except ValueError:
                return False
        cases = [item for item in cases if is_overdue(item)]
    if recently_resolved:
        cutoff = now - timedelta(days=30)
        def is_recently_resolved(item: dict[str, Any]) -> bool:
            if item["workflow"]["status"] not in terminal_statuses:
                return False
            timestamp = item["workflow"].get("updated_at")
            if not timestamp:
                return False
            try:
                parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc) >= cutoff
            except ValueError:
                return False
        cases = [item for item in cases if is_recently_resolved(item)]
    bounded_offset = max(0, int(offset))
    bounded_limit = max(1, min(int(limit), 100))
    page = cases[bounded_offset:bounded_offset + bounded_limit]
    has_more = bounded_offset + bounded_limit < len(cases)
    return {
        "findings": page, "limit": bounded_limit, "offset": bounded_offset,
        "has_more": has_more,
        "next_offset": bounded_offset + bounded_limit if has_more else None,
    }


def finding_activity(finding_id: str) -> dict[str, Any]:
    case = read_finding_case(finding_id)
    chronological_events = _events(finding_id)
    activity_groups: list[list[dict[str, Any]]] = []
    current_assignment: dict[str, Any] | None = None
    for event in chronological_events:
        entries, current_assignment = _human_activity_entries(
            event, current_assignment=current_assignment,
        )
        activity_groups.append(entries)
    events = list(reversed(chronological_events))
    activity = [entry for group in reversed(activity_groups) for entry in group]
    activity.append({
        "activity_type": "detected",
        "label": "Finding detected",
        "summary": "Neraium surfaced this persistent behavioral change for review.",
        "actor": "Neraium",
        "recorded_at": case["created_at"],
        "version": 0,
    })
    return {
        "finding_id": finding_id, "events": events, "activity": activity,
        "version": case["workflow"]["version"],
    }


def _activity_entry(event: dict[str, Any], *, label: str, summary: str) -> dict[str, Any]:
    return {
        "activity_type": str(event.get("event_type") or "workflow_updated"),
        "label": label,
        "summary": summary,
        "actor": event.get("actor"),
        "recorded_at": event.get("recorded_at"),
        "version": event.get("version"),
    }


def _human_activity_entries(
    event: dict[str, Any], *, current_assignment: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    event_type = str(event.get("event_type") or "")
    entries: list[dict[str, Any]] = []
    if event_type in {"workflow_updated", "legacy_status_imported"}:
        changes = event.get("changes") if isinstance(event.get("changes"), dict) else {}
        if "assignment" in changes:
            assignment = changes.get("assignment")
            label = (
                "Finding reassigned" if current_assignment and assignment else
                "Finding assigned" if assignment else "Assignment removed"
            )
            summary = (
                f"Assigned to {assignment.get('label')}." if isinstance(assignment, dict)
                else "The finding is no longer assigned."
            )
            entries.append(_activity_entry(event, label=label, summary=summary))
            current_assignment = assignment if isinstance(assignment, dict) else None
        if "status" in changes:
            status = str(changes["status"]).replace("_", " ")
            status_label = {
                "acknowledged": "Work acknowledged",
                "investigating": "Investigation started",
                "waiting": "Work marked waiting",
                "escalated": "Finding escalated",
                "awaiting review": "Investigation submitted for review",
                "monitoring": "Monitoring started",
                "resolved": "Finding resolved",
                "dismissed": "Finding dismissed",
            }.get(status, "Status changed")
            entries.append(_activity_entry(
                event, label=status_label, summary=f"Status changed to {status}.",
            ))
        if "user_priority" in changes:
            priority = changes.get("user_priority")
            entries.append(_activity_entry(
                event, label="Priority changed",
                summary=f"Priority changed to {priority}." if priority else "Priority override removed.",
            ))
        if "due_at" in changes:
            entries.append(_activity_entry(
                event, label="Due date changed",
                summary="Due date updated." if changes.get("due_at") else "Due date removed.",
            ))
        if "manager_note" in changes:
            entries.append(_activity_entry(
                event, label="Guidance updated",
                summary="Technical or maintenance guidance was updated.",
            ))
    elif event_type in {"feedback_recorded", "legacy_feedback_imported"}:
        entries.append(_activity_entry(
            event, label="Note added",
            summary="A finding note or validation result was recorded.",
        ))
    elif event_type == "field_report_recorded":
        report = event.get("field_report") or {}
        label = "Investigation completed" if report.get("investigation_complete") else "Field report added"
        summary = "The technician submitted field findings."
        if report.get("needs_escalation"):
            label, summary = "Escalation requested", "The technician submitted findings and requested help."
        entries.append(_activity_entry(event, label=label, summary=summary))
    elif event_type == "resolution_recorded":
        entries.append(_activity_entry(
            event, label="Finding resolved",
            summary="The review outcome was recorded and the finding was resolved.",
        ))
    if not entries:
        entries.append(_activity_entry(
            event, label="Finding updated", summary="Workflow details were updated.",
        ))
    return entries, current_assignment


def _fingerprint(event_type: str, payload: dict[str, Any]) -> str:
    def client_intent(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: client_intent(item)
                for key, item in value.items()
                if key not in {"actor", "recorded_at", "resolved_at"}
            }
        if isinstance(value, list):
            return [client_intent(item) for item in value]
        return value

    return hashlib.sha256(
        _json({"event_type": event_type, **client_intent(payload)}).encode("utf-8")
    ).hexdigest()


def _append_event(
    finding_id: str, *, event_type: str, actor: str, payload: dict[str, Any],
    expected_version: int | None, idempotency_key: str | None,
    recorded_at: str | None = None,
) -> dict[str, Any]:
    init_runtime_db()
    request_fingerprint = _fingerprint(event_type, {"actor_identity": actor, **payload})
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        exists = connection.execute(
            """
            SELECT 1 FROM finding_cases
            WHERE finding_id = ? AND scope_storage_id = ?
            """,
            (finding_id, current_dataset_scope().storage_id),
        ).fetchone()
        if exists is None:
            raise FindingNotFoundError("Finding not found.")
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) AS version FROM finding_workflow_events WHERE finding_id = ?",
            (finding_id,),
        ).fetchone()
        current_version = int(row["version"] if row else 0)
        normalized_key = _clean(idempotency_key)
        if normalized_key:
            replay = connection.execute(
                "SELECT payload_json FROM finding_workflow_events WHERE finding_id = ? AND idempotency_key = ?",
                (finding_id, normalized_key),
            ).fetchone()
            if replay is not None:
                prior = json.loads(replay["payload_json"])
                if prior.get("request_fingerprint") != request_fingerprint:
                    raise FindingWorkflowConflictError(
                        "idempotency_key_reused", current_version=current_version
                    )
                return prior
        if expected_version is not None and int(expected_version) != current_version:
            raise FindingWorkflowConflictError("stale_workflow_version", current_version=current_version)
        event = {
            "event_id": uuid.uuid4().hex,
            "finding_id": finding_id,
            "version": current_version + 1,
            "event_type": event_type,
            "recorded_at": recorded_at or now_iso(),
            "actor": actor,
            "idempotency_key": normalized_key,
            "request_fingerprint": request_fingerprint,
            **payload,
        }
        connection.execute(
            """
            INSERT INTO finding_workflow_events (
                event_id, finding_id, version, event_type, recorded_at, actor,
                idempotency_key, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"], finding_id, event["version"], event_type,
                event["recorded_at"], actor, normalized_key, _json(event),
            ),
        )
    return event


def update_finding_workflow(
    finding_id: str, *, changes: dict[str, Any], expected_version: int,
    actor: str, idempotency_key: str | None = None, recorded_at: str | None = None,
    enforce_transitions: bool = False,
) -> dict[str, Any]:
    invalid = set(changes) - WORKFLOW_FIELDS
    if invalid:
        raise ValueError(f"unsupported_workflow_fields:{','.join(sorted(invalid))}")
    normalized_changes = dict(changes)
    if "assignment" in normalized_changes:
        normalized_changes["assignment"] = _normalized_person_assignment(
            normalized_changes["assignment"]
        )
    if "status" in normalized_changes:
        current = read_finding_case(finding_id)["workflow"]["status"]
        validate_status_transition(
            current, str(normalized_changes["status"]), strict=enforce_transitions,
        )
    _append_event(
        finding_id, event_type="workflow_updated", actor=actor,
        payload={"changes": normalized_changes}, expected_version=expected_version,
        idempotency_key=idempotency_key, recorded_at=recorded_at,
    )
    return read_finding_case(finding_id)


def record_finding_field_report(
    finding_id: str, *, field_report: dict[str, Any], expected_version: int,
    actor: str, idempotency_key: str | None = None, recorded_at: str | None = None,
) -> dict[str, Any]:
    current_status = read_finding_case(finding_id)["workflow"]["status"]
    if current_status in {"resolved", "dismissed"}:
        raise FindingWorkflowValidationError("field_report_not_allowed_for_terminal_finding")
    timestamp = recorded_at or now_iso()
    normalized = {
        "note": _clean(field_report.get("note")),
        "inspected": _clean(field_report.get("inspected")),
        "found": _clean(field_report.get("found")),
        "action_taken": _clean(field_report.get("action_taken")),
        "problem_found": field_report.get("problem_found"),
        "needs_escalation": bool(field_report.get("needs_escalation")),
        "investigation_complete": bool(field_report.get("investigation_complete")),
        "actor": actor,
        "recorded_at": timestamp,
    }
    if normalized["problem_found"] not in {"yes", "no", "uncertain"}:
        raise FindingWorkflowValidationError("invalid_problem_found")
    _append_event(
        finding_id, event_type="field_report_recorded", actor=actor,
        payload={"field_report": normalized}, expected_version=expected_version,
        idempotency_key=idempotency_key, recorded_at=timestamp,
    )
    return read_finding_case(finding_id)


def record_finding_feedback(
    finding_id: str, *, feedback: dict[str, Any], expected_version: int | None,
    actor: str, idempotency_key: str | None = None, recorded_at: str | None = None,
    event_type: str = "feedback_recorded",
) -> dict[str, Any]:
    normalized = {**feedback, "actor": actor, "recorded_at": recorded_at or now_iso()}
    _append_event(
        finding_id, event_type=event_type, actor=actor,
        payload={"feedback": normalized}, expected_version=expected_version,
        idempotency_key=idempotency_key, recorded_at=normalized["recorded_at"],
    )
    return read_finding_case(finding_id)


def resolve_finding(
    finding_id: str, *, outcome: str, note: str | None, expected_version: int,
    actor: str, idempotency_key: str | None = None, recorded_at: str | None = None,
) -> dict[str, Any]:
    timestamp = recorded_at or now_iso()
    _append_event(
        finding_id, event_type="resolution_recorded", actor=actor,
        payload={"resolution": {"outcome": outcome, "note": _clean(note), "resolved_at": timestamp, "actor": actor}},
        expected_version=expected_version, idempotency_key=idempotency_key,
        recorded_at=timestamp,
    )
    return read_finding_case(finding_id)


def _legacy_history(run_id: str) -> list[tuple[str, dict[str, Any]]]:
    with db_connection() as connection:
        record_row = connection.execute(
            "SELECT payload_json FROM evidence_runs WHERE run_id = ? AND scope_storage_id = ?",
            (run_id, current_dataset_scope().storage_id),
        ).fetchone()
        record = json.loads(record_row["payload_json"]) if record_row else {}
        events: list[tuple[str, dict[str, Any]]] = []
        for table, event_type in (
            ("finding_status_events", "status"),
            ("operator_feedback_events", "feedback"),
        ):
            rows = connection.execute(
                f"SELECT event_id, payload_json FROM {table} WHERE run_id = ?", (run_id,)
            ).fetchall()
            for row in rows:
                payload = json.loads(row["payload_json"])
                payload.setdefault("event_id", str(row["event_id"]))
                events.append((event_type, payload))
    for index, payload in enumerate(record.get("finding_status_history") or []):
        if isinstance(payload, dict):
            events.append(("status", {**payload, "event_id": payload.get("event_id") or f"embedded-status-{index}"}))
    for index, payload in enumerate(record.get("operator_feedback_history") or []):
        if isinstance(payload, dict):
            events.append(("feedback", {**payload, "event_id": payload.get("event_id") or f"embedded-feedback-{index}"}))
    ordered = sorted(
        events,
        key=lambda item: (str(item[1].get("recorded_at") or ""), str(item[1].get("event_id") or "")),
    )
    deduped: list[tuple[str, dict[str, Any]]] = []
    seen_ids: set[tuple[str, str]] = set()
    seen_content: set[tuple[str, str]] = set()
    for legacy_type, event in ordered:
        event_id = _clean(event.get("event_id"))
        content = {key: value for key, value in event.items() if key not in {"event_id", "run_id"}}
        content_key = (legacy_type, hashlib.sha256(_json(content).encode()).hexdigest())
        id_key = (legacy_type, event_id or "")
        if (event_id and id_key in seen_ids) or content_key in seen_content:
            continue
        if event_id:
            seen_ids.add(id_key)
        seen_content.add(content_key)
        deduped.append((legacy_type, event))
    return deduped


def _migrate_legacy_events_if_unambiguous(run_id: str) -> None:
    init_runtime_db()
    with db_connection() as connection:
        cases = connection.execute(
            """
            SELECT finding_id FROM finding_cases
            WHERE source_kind = 'evidence_run' AND source_id = ?
              AND scope_storage_id = ?
            """,
            (run_id, current_dataset_scope().storage_id),
        ).fetchall()
    if len(cases) != 1:
        return
    finding_id = str(cases[0]["finding_id"])
    for legacy_type, event in _legacy_history(run_id):
        legacy_id = str(event.get("event_id") or hashlib.sha256(_json(event).encode()).hexdigest())
        actor = str(event.get("actor") or event.get("owner") or "legacy-operator")
        timestamp = str(event.get("recorded_at") or now_iso())
        if legacy_type == "status":
            changes = {
                "status": event.get("state") or event.get("status") or "open",
                "manager_note": event.get("note"),
                "work_order_reference": event.get("work_order_reference"),
            }
            assignee = _clean(event.get("assignee"))
            if assignee:
                changes["assignment"] = {"target_type": "person", "label": assignee, "external_ref": None}
            _append_event(
                finding_id, event_type="legacy_status_imported", actor=actor,
                payload={"changes": changes, "compatibility": {"run_id": run_id, "legacy_event_id": legacy_id}},
                expected_version=None, idempotency_key=f"legacy-status:{legacy_id}", recorded_at=timestamp,
            )
        else:
            record_finding_feedback(
                finding_id, feedback=event, expected_version=None, actor=actor,
                idempotency_key=f"legacy-feedback:{legacy_id}", recorded_at=timestamp,
                event_type="legacy_feedback_imported",
            )


def compatibility_write_status(
    run_id: str, *, state: str, actor: str, recorded_at: str,
    note: str | None = None, owner: str | None = None, assignee: str | None = None,
    work_order_reference: str | None = None, idempotency_key: str | None = None,
) -> str:
    from app.services.runtime_db import append_finding_status_event_db, read_evidence_run_db

    record = read_evidence_run_db(run_id)
    if record is None:
        raise ValueError("evidence_run_not_found")
    record_scope = dataset_scope_from_payload(record)
    if record_scope is None or record_scope != current_dataset_scope():
        raise ValueError("evidence_run_not_found")
    with dataset_scope_context(record_scope):
        cases = materialize_evidence_finding_cases(record)
        event = {
            "state": state, "actor": actor, "recorded_at": recorded_at,
            "note": _clean(note), "owner": _clean(owner) or actor,
            "assignee": _clean(assignee), "work_order_reference": _clean(work_order_reference),
        }
        if len(cases) != 1 or _raw_case(cases[0]) is None:
            append_finding_status_event_db(run_id, event)
            return "legacy_ambiguous_run"
        changes: dict[str, Any] = {
            "status": state,
            "manager_note": _clean(note),
            "work_order_reference": _clean(work_order_reference),
        }
        if assignee is not None:
            if str(assignee).strip():
                raise FindingWorkflowValidationError("assignment_member_required")
            changes["assignment"] = None
        _append_event(
            cases[0], event_type="workflow_updated", actor=actor,
            payload={"changes": changes, "compatibility": {"run_id": run_id}},
            expected_version=None, idempotency_key=idempotency_key, recorded_at=recorded_at,
        )
    return "canonical_finding"


def compatibility_write_feedback(
    run_id: str, *, feedback: dict[str, Any], actor: str, recorded_at: str,
    idempotency_key: str | None = None,
) -> str:
    from app.services.runtime_db import append_operator_feedback_event_db, read_evidence_run_db

    record = read_evidence_run_db(run_id)
    if record is None:
        raise ValueError("evidence_run_not_found")
    record_scope = dataset_scope_from_payload(record)
    if record_scope is None or record_scope != current_dataset_scope():
        raise ValueError("evidence_run_not_found")
    with dataset_scope_context(record_scope):
        cases = materialize_evidence_finding_cases(record)
        event = {**feedback, "actor": actor, "recorded_at": recorded_at}
        if len(cases) != 1 or _raw_case(cases[0]) is None:
            append_operator_feedback_event_db(run_id, event)
            return "legacy_ambiguous_run"
        record_finding_feedback(
            cases[0], feedback=feedback, expected_version=None, actor=actor,
            idempotency_key=idempotency_key, recorded_at=recorded_at,
        )
    return "canonical_finding"


def compatibility_events_for_run(run_id: str) -> dict[str, list[dict[str, Any]]]:
    init_runtime_db()
    with db_connection() as connection:
        cases = connection.execute(
            """
            SELECT finding_id FROM finding_cases
            WHERE source_kind = 'evidence_run' AND source_id = ?
              AND scope_storage_id = ?
            """,
            (run_id, current_dataset_scope().storage_id),
        ).fetchall()
    if len(cases) != 1:
        return {"status": [], "feedback": []}
    events = _events(str(cases[0]["finding_id"]))
    statuses: list[dict[str, Any]] = []
    feedback: list[dict[str, Any]] = []
    for event in reversed(events):
        if event["event_type"] in {"workflow_updated", "resolution_recorded"}:
            if event["event_type"] == "resolution_recorded":
                resolution = event.get("resolution") or {}
                statuses.append({
                    "event_id": event["event_id"], "state": "resolved",
                    "note": resolution.get("note"), "actor": event.get("actor"),
                    "owner": event.get("actor"), "recorded_at": event.get("recorded_at"),
                })
                category = {
                    "issue_found": "confirmed_issue",
                    "no_issue_found": "false_positive",
                    "operational_change": "known_operational_change",
                    "sensor_issue": "sensor_or_data_problem",
                    "maintenance_performed": "maintenance_event",
                }.get(str(resolution.get("outcome") or ""))
                if category:
                    feedback.append({
                        "category": category,
                        "note": resolution.get("note"),
                        "outcome": resolution.get("outcome"),
                        "action_taken": (
                            resolution.get("note")
                            if resolution.get("outcome") == "maintenance_performed" else None
                        ),
                        "actor": event.get("actor"),
                        "recorded_at": event.get("recorded_at"),
                        "resolution_event_id": event.get("event_id"),
                    })
            else:
                changes = event.get("changes") or {}
                assignment = changes.get("assignment") if isinstance(changes.get("assignment"), dict) else {}
                if "status" in changes or "assignment" in changes or "work_order_reference" in changes:
                    statuses.append({
                        "event_id": event["event_id"], "state": changes.get("status"),
                        "note": changes.get("manager_note"), "actor": event.get("actor"),
                        "owner": event.get("actor"), "assignee": assignment.get("label"),
                        "work_order_reference": changes.get("work_order_reference"),
                        "recorded_at": event.get("recorded_at"),
                    })
        if event["event_type"] == "feedback_recorded":
            feedback.append(dict(event.get("feedback") or {}))
    return {"status": statuses, "feedback": feedback}
