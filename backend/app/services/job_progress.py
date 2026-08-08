from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable


CONTRACT_VERSION = "job-progress.v1"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
ACTIVE_STATUSES = {"processing", "retrying"}

UPLOAD_OPERATIONS = (
    ("receiving", "upload", "Receiving file"),
    ("source_persisted", "upload", "Source persisted"),
)

VALIDATION_OPERATIONS = (
    ("parse_source", "validate", "Parse source"),
    ("schema_detection", "validate", "Schema detection"),
    ("timestamp_detection", "validate", "Timestamp detection"),
    ("timestamp_quality", "validate", "Timestamp quality"),
    ("signal_inventory", "validate", "Signal inventory"),
    ("unit_detection", "validate", "Unit detection"),
    ("semantic_mapping", "validate", "Semantic mapping"),
    ("data_quality_profiling", "validate", "Data-quality profiling"),
    ("unit_normalization", "validate", "Unit normalization"),
    ("canonical_dataset_build", "validate", "Canonical dataset build"),
    ("configuration_awareness", "validate", "Configuration awareness"),
    ("readiness_evaluation", "validate", "Readiness evaluation"),
    ("analysis_snapshot_build", "validate", "Analysis snapshot build"),
)

BASELINE_OPERATIONS = (
    ("select_usable_signals", "learn", "Select usable signals"),
    ("build_operating_context", "learn", "Build operating context"),
    ("compute_baseline_statistics", "learn", "Compute baseline statistics"),
    ("learn_relationships", "learn", "Learn relationships"),
    ("fit_expected_models", "learn", "Fit expected-behavior models"),
    ("persistence_checks", "learn", "Persistence checks"),
    ("finalize_baseline", "ready", "Finalize baseline"),
)

ANALYSIS_OPERATIONS = (
    ("prepare_inputs", "analysis", "Prepare analysis inputs"),
    ("signal_drift", "analysis", "Signal drift analysis"),
    ("relationship_analysis", "analysis", "Relationship analysis"),
    ("operating_modes", "analysis", "Operating-context analysis"),
    ("data_conditions", "analysis", "Data-condition checks"),
    ("sensor_health", "analysis", "Signal-health analysis"),
    ("empirical_thresholds", "analysis", "Empirical thresholds"),
    ("mode_conditioned_baseline", "analysis", "Mode-conditioned comparison"),
    ("relationship_graph_analysis", "analysis", "Relationship graph analysis"),
    ("fixed_persistence", "analysis", "Persistence analysis"),
    ("adaptive_persistence", "analysis", "Adaptive persistence"),
    ("temporal_analysis", "analysis", "Lag and temporal analysis"),
    ("multiscale_analysis", "analysis", "Multi-scale analysis"),
    ("covariance_analysis", "analysis", "Covariance analysis"),
    ("physics_reasoning", "analysis", "Physics evidence"),
    ("behavioral_model", "analysis", "Behavioral fingerprinting"),
    ("evidence_fusion", "analysis", "Evidence generation"),
    ("finalize_analysis", "ready", "Finalize analysis"),
)

_WORKFLOW_LABELS = {
    "upload": "Upload",
    "validate": "Validate",
    "learn": "Learn",
    "analysis": "Analyze",
    "ready": "Baseline Ready",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _is_baseline_workflow(workflow: str | None) -> bool:
    return str(workflow or "").strip().lower() in {"create_baseline", "extend_baseline"}


def operation_definitions(workflow: str | None) -> tuple[tuple[str, str, str], ...]:
    if str(workflow or "").strip().lower() == "historical_review":
        return UPLOAD_OPERATIONS + tuple(
            item for item in VALIDATION_OPERATIONS if item[0] != "analysis_snapshot_build"
        )
    return UPLOAD_OPERATIONS + VALIDATION_OPERATIONS + (
        BASELINE_OPERATIONS if _is_baseline_workflow(workflow) else ANALYSIS_OPERATIONS
    )


def _final_substage(workflow: str | None) -> str:
    if str(workflow or "").strip().lower() == "historical_review":
        return "readiness_evaluation"
    return "finalize_baseline" if _is_baseline_workflow(workflow) else "finalize_analysis"


def _bounded_units(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _unit_percent(completed: int | None, total: int | None, status: str) -> int | None:
    if status == "completed":
        return 100
    if completed is None or total is None or total <= 0:
        return None
    return max(0, min(100, int(completed * 100 / total)))


def _operation(
    operation_id: str,
    stage: str,
    label: str,
    *,
    status: str = "pending",
) -> dict[str, Any]:
    return {
        "id": operation_id,
        "stage": stage,
        "label": label,
        "status": status,
        "completed_units": None,
        "total_units": None,
        "percent_complete": 100 if status == "completed" else None,
        "unit_type": None,
        "message": None,
        "started_at": None,
        "updated_at": None,
        "completed_at": None,
        "metadata": {},
    }


def _workflow_steps(operations: list[dict[str, Any]], workflow: str | None) -> list[dict[str, Any]]:
    stage_order: list[str] = []
    for item in operations:
        if item["stage"] not in stage_order:
            stage_order.append(item["stage"])
    steps: list[dict[str, Any]] = []
    for stage in stage_order:
        items = [item for item in operations if item["stage"] == stage]
        completed = sum(item["status"] == "completed" for item in items)
        active = next((item for item in items if item["status"] in ACTIVE_STATUSES), None)
        failed = next((item for item in items if item["status"] == "failed"), None)
        partial = 0.0
        measured = active or failed
        if measured is not None and measured.get("percent_complete") is not None:
            partial = float(measured["percent_complete"]) / 100.0
        percent = int((completed + partial) * 100 / max(1, len(items)))
        if completed == len(items):
            status = "completed"
            percent = 100
        elif failed is not None:
            status = "failed"
        elif active is not None:
            status = active["status"]
        elif completed:
            status = "pending"
        else:
            status = "pending"
        label = _WORKFLOW_LABELS.get(stage, stage.replace("_", " ").title())
        if stage == "ready":
            label = (
                "Canonical Dataset Ready"
                if str(workflow or "").strip().lower() == "historical_review"
                else "Baseline Ready"
                if _is_baseline_workflow(workflow)
                else "Results Ready"
            )
        steps.append({
            "id": stage,
            "label": label,
            "status": status,
            "completed_work_units": completed,
            "total_work_units": len(items),
            "percent_complete": percent,
        })
    return steps


def _overall_percent(operations: list[dict[str, Any]]) -> int:
    completed = sum(item["status"] == "completed" for item in operations)
    active = next(
        (
            item for item in operations
            if item["status"] in ACTIVE_STATUSES | {"failed", "cancelled"}
            and item.get("percent_complete") is not None
        ),
        None,
    )
    partial = 0.0
    if active is not None and active.get("percent_complete") is not None:
        partial = float(active["percent_complete"]) / 100.0
    return max(0, min(100, int((completed + partial) * 100 / max(1, len(operations)))))


def initialize_progress(
    *,
    job_id: str,
    workflow: str | None,
    status: str = "queued",
    message: str = "Waiting for a worker to claim this job.",
    started_at: str | None = None,
    source_persisted: bool = True,
) -> dict[str, Any]:
    now = _now()
    operations = [_operation(*definition) for definition in operation_definitions(workflow)]
    if source_persisted:
        for item in operations[:2]:
            item.update({
                "status": "completed",
                "completed_units": 1,
                "total_units": 1,
                "percent_complete": 100,
                "unit_type": "operation",
                "message": "File transfer completed." if item["id"] == "receiving" else "Source persisted for processing.",
                "started_at": started_at or _iso(now),
                "updated_at": _iso(now),
                "completed_at": _iso(now),
            })
    snapshot = {
        "contract_version": CONTRACT_VERSION,
        "job_id": str(job_id),
        "workflow": str(workflow or "legacy_analysis"),
        "status": status,
        "stage": "queue" if status == "queued" else None,
        "substage": None,
        "completed_units": None,
        "total_units": None,
        "percent_complete": None,
        "unit_type": None,
        "message": message,
        "started_at": started_at or _iso(now),
        "updated_at": _iso(now),
        "elapsed_seconds": 0,
        "last_worker_heartbeat_at": None,
        "seconds_since_worker_heartbeat": None,
        "seconds_since_update": 0,
        "stalled": False,
        "retryable": None,
        "error": None,
        "metadata": {},
        "workflow_steps": _workflow_steps(operations, workflow),
        "operations": operations,
        "overall_percent_complete": _overall_percent(operations),
        "overall_basis": "equal_completed_declared_substages",
    }
    return snapshot


def update_progress(
    existing: dict[str, Any] | None,
    *,
    job_id: str,
    workflow: str | None,
    stage: str,
    substage: str,
    status: str = "processing",
    completed_units: Any = None,
    total_units: Any = None,
    unit_type: str | None = None,
    message: str | None = None,
    metadata: dict[str, Any] | None = None,
    retryable: bool | None = None,
    error: str | None = None,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    now = observed_at or _now()
    base = dict(existing or initialize_progress(job_id=job_id, workflow=workflow))
    definitions = operation_definitions(workflow)
    definition_by_id = {item[0]: item for item in definitions}
    if substage not in definition_by_id:
        raise ValueError(f"unsupported_progress_substage:{substage}")
    # The contract owns the stage/substage relationship.  Worker callers name
    # the substage; they cannot persist a contradictory stage label.
    stage = definition_by_id[substage][1]
    operations_by_id = {
        str(item.get("id")): dict(item)
        for item in base.get("operations", [])
        if isinstance(item, dict) and item.get("id")
    }
    operations = [
        operations_by_id.get(operation_id, _operation(operation_id, operation_stage, label))
        for operation_id, operation_stage, label in definitions
    ]
    target_index = next(index for index, item in enumerate(operations) if item["id"] == substage)
    furthest_started = max(
        (index for index, item in enumerate(operations) if item.get("status") != "pending"),
        default=-1,
    )
    if status not in TERMINAL_STATUSES and target_index < furthest_started:
        return enrich_progress_timing(base, observed_at=now)

    for index, item in enumerate(operations):
        if index >= target_index:
            break
        if item["status"] not in {"failed", "cancelled"}:
            item["status"] = "completed"
            item["percent_complete"] = 100
            item["completed_at"] = item.get("completed_at") or _iso(now)
            item["updated_at"] = item.get("updated_at") or _iso(now)

    target = operations[target_index]
    prior_completed = _bounded_units(target.get("completed_units"))
    prior_total = _bounded_units(target.get("total_units"))
    completed = _bounded_units(completed_units)
    total = _bounded_units(total_units)
    if prior_total is not None:
        total = prior_total
    if prior_completed is not None and completed is not None:
        completed = max(prior_completed, completed)
    if total is not None and prior_completed is not None:
        total = max(total, prior_completed)
    if total is not None and completed is not None:
        completed = min(completed, total)
    operation_status = status if status in {"processing", "retrying", "completed", "failed", "cancelled"} else "processing"
    target.update({
        "stage": stage,
        "status": operation_status,
        "completed_units": completed,
        "total_units": total,
        "percent_complete": _unit_percent(completed, total, operation_status),
        "unit_type": str(unit_type or "").strip() or None,
        "message": str(message or target.get("message") or "").strip() or None,
        "started_at": target.get("started_at") or _iso(now),
        "updated_at": _iso(now),
        "completed_at": _iso(now) if operation_status == "completed" else None,
        "metadata": {**dict(target.get("metadata") or {}), **dict(metadata or {})},
    })
    if operation_status in {"failed", "cancelled"}:
        for item in operations[target_index + 1 :]:
            if item["status"] not in TERMINAL_STATUSES:
                item["status"] = "pending"

    started = _parse_datetime(base.get("started_at")) or now
    final_substage = substage == _final_substage(workflow)
    job_status = (
        "completed"
        if operation_status == "completed" and final_substage
        else "processing"
        if operation_status == "completed"
        else operation_status
    )
    base.update({
        "contract_version": CONTRACT_VERSION,
        "job_id": str(job_id),
        "workflow": str(workflow or base.get("workflow") or "legacy_analysis"),
        "status": job_status,
        "stage": stage,
        "substage": substage,
        "completed_units": completed,
        "total_units": total,
        "percent_complete": target["percent_complete"],
        "unit_type": target["unit_type"],
        "message": target["message"] or str(base.get("message") or "Backend processing is active."),
        "started_at": _iso(started),
        "updated_at": _iso(now),
        "last_worker_heartbeat_at": _iso(now) if operation_status in ACTIVE_STATUSES | {"completed"} else base.get("last_worker_heartbeat_at"),
        "retryable": retryable,
        "error": str(error or "").strip() or None,
        "metadata": {**dict(base.get("metadata") or {}), **dict(metadata or {})},
        "operations": operations,
        "workflow_steps": _workflow_steps(operations, workflow),
        "overall_percent_complete": _overall_percent(operations),
        "overall_basis": "equal_completed_declared_substages",
    })
    if final_substage and operation_status == "completed":
        base["status"] = "completed"
        base["overall_percent_complete"] = 100
    return enrich_progress_timing(base, observed_at=now)


def fail_progress(
    existing: dict[str, Any] | None,
    *,
    job_id: str,
    workflow: str | None,
    message: str,
    retryable: bool | None,
) -> dict[str, Any]:
    base = dict(existing or initialize_progress(job_id=job_id, workflow=workflow))
    substage = str(base.get("substage") or "parse_source")
    stage = str(base.get("stage") or "validate")
    return update_progress(
        base,
        job_id=job_id,
        workflow=workflow,
        stage=stage,
        substage=substage,
        status="failed",
        completed_units=base.get("completed_units"),
        total_units=base.get("total_units"),
        unit_type=base.get("unit_type"),
        message=message,
        retryable=retryable,
        error=message,
    )


def complete_progress(existing: dict[str, Any] | None, *, job_id: str, workflow: str | None, message: str) -> dict[str, Any]:
    substage = _final_substage(workflow)
    stage = "validate" if substage == "readiness_evaluation" else "ready"
    return update_progress(
        existing,
        job_id=job_id,
        workflow=workflow,
        stage=stage,
        substage=substage,
        status="completed",
        completed_units=1,
        total_units=1,
        unit_type="operation",
        message=message,
    )


def retry_progress(existing: dict[str, Any] | None, *, job_id: str, workflow: str | None, message: str) -> dict[str, Any]:
    previous = dict(existing or initialize_progress(job_id=job_id, workflow=workflow))
    retried = initialize_progress(
        job_id=job_id,
        workflow=workflow,
        status="queued",
        message=message,
        started_at=_iso(_now()),
        source_persisted=True,
    )
    retried["metadata"] = {
        **dict(previous.get("metadata") or {}),
        "retry_count": int((previous.get("metadata") or {}).get("retry_count") or 0) + 1,
        "previous_attempt_completed_operations": [
            str(item.get("id"))
            for item in previous.get("operations", [])
            if isinstance(item, dict) and item.get("status") == "completed"
        ],
        "previous_attempt_failed_substage": previous.get("substage") if previous.get("status") == "failed" else None,
    }
    return retried


def enrich_progress_timing(progress: dict[str, Any], *, observed_at: datetime | None = None) -> dict[str, Any]:
    now = observed_at or _now()
    enriched = dict(progress or {})
    started = _parse_datetime(enriched.get("started_at")) or now
    updated = _parse_datetime(enriched.get("updated_at")) or started
    heartbeat = _parse_datetime(enriched.get("last_worker_heartbeat_at"))
    seconds_since_update = max(0, int((now - updated).total_seconds()))
    threshold = max(1, int(os.getenv("NERAIUM_PROGRESS_STALL_SECONDS", "120")))
    enriched["elapsed_seconds"] = max(0, int((now - started).total_seconds()))
    enriched["seconds_since_update"] = seconds_since_update
    enriched["seconds_since_worker_heartbeat"] = (
        max(0, int((now - heartbeat).total_seconds())) if heartbeat else None
    )
    enriched["stalled"] = bool(
        enriched.get("status") in ACTIVE_STATUSES | {"queued", "waiting"}
        and seconds_since_update >= threshold
    )
    return enriched


class ProgressReporter:
    """Throttle durable progress writes while retaining the newest in-process counters."""

    def __init__(
        self,
        *,
        job_id: str,
        workflow: str | None,
        persist: Callable[..., dict[str, Any]],
        minimum_interval_seconds: float | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.job_id = str(job_id)
        self.workflow = str(workflow or "legacy_analysis")
        self.persist = persist
        self.minimum_interval_seconds = max(
            0.0,
            float(
                minimum_interval_seconds
                if minimum_interval_seconds is not None
                else os.getenv("NERAIUM_PROGRESS_WRITE_INTERVAL_SECONDS", "2")
            ),
        )
        self.monotonic = monotonic
        self._last_write = 0.0
        self._last_substage: str | None = None
        self._last_status: str | None = None
        self._lock = threading.RLock()
        self.write_count = 0

    def report(self, *, stage: str, substage: str, status: str = "processing", force: bool = False, **values: Any) -> dict[str, Any] | None:
        with self._lock:
            now = self.monotonic()
            transition = substage != self._last_substage or status != self._last_status
            terminal = status in TERMINAL_STATUSES
            if not (force or transition or terminal) and now - self._last_write < self.minimum_interval_seconds:
                return None
            persisted = self.persist(
                job_id=self.job_id,
                workflow=self.workflow,
                stage=stage,
                substage=substage,
                status=status,
                **values,
            )
            self._last_write = now
            self._last_substage = substage
            self._last_status = status
            self.write_count += 1
            return persisted
