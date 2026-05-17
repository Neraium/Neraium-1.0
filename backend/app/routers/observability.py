from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.core.security import require_api_access
from app.models.api_models import ObservabilitySummaryResponse
from app.services.aletheia_governance import list_evp_records
from app.services.evidence_store import list_evidence_runs
from app.services.runtime_db import audit_events_count, queue_metrics


router = APIRouter(tags=["observability"], dependencies=[Depends(require_api_access)])


@router.get("/observability/summary", response_model=ObservabilitySummaryResponse)
def get_observability_summary() -> ObservabilitySummaryResponse:
    queue = queue_metrics()
    evidence_runs = list_evidence_runs(limit=100)
    status_counts = Counter(run.get("status", "unknown") for run in evidence_runs)
    alerts: list[dict[str, str | int]] = []
    if queue.get("pending", 0) > 0:
        alerts.append({"level": "warning", "message": "Upload queue has pending jobs.", "count": queue["pending"]})
    if status_counts.get("failed", 0) > 0:
        alerts.append({"level": "warning", "message": "Evidence trail includes failed runs.", "count": status_counts["failed"]})
    return ObservabilitySummaryResponse(
        queue=queue,
        evidence_runs={
            "total": len(evidence_runs),
            "status_counts": dict(status_counts),
            "latest_completed_at": evidence_runs[0].get("completed_at") if evidence_runs else None,
        },
        audit={"event_count": audit_events_count()},
        alerts=alerts,
    )


@router.get("/observability/metrics", response_class=PlainTextResponse)
def get_observability_metrics() -> PlainTextResponse:
    queue = queue_metrics()
    evidence_runs = list_evidence_runs(limit=100)
    status_counts = Counter(run.get("status", "unknown") for run in evidence_runs)
    lines = [
        "# HELP neraium_queue_pending Pending upload jobs in queue.",
        "# TYPE neraium_queue_pending gauge",
        f"neraium_queue_pending {queue.get('pending', 0)}",
        "# HELP neraium_queue_in_progress Upload jobs currently running.",
        "# TYPE neraium_queue_in_progress gauge",
        f"neraium_queue_in_progress {queue.get('in_progress', 0)}",
        "# HELP neraium_evidence_runs_total Total recent evidence runs.",
        "# TYPE neraium_evidence_runs_total gauge",
        f"neraium_evidence_runs_total {len(evidence_runs)}",
        "# HELP neraium_evidence_runs_failed Failed evidence runs in sample window.",
        "# TYPE neraium_evidence_runs_failed gauge",
        f"neraium_evidence_runs_failed {status_counts.get('failed', 0)}",
        "# HELP neraium_audit_events_total Runtime audit event count.",
        "# TYPE neraium_audit_events_total gauge",
        f"neraium_audit_events_total {audit_events_count()}",
    ]
    return PlainTextResponse("\n".join(lines) + "\n")


@router.get("/observability/evp-governance")
def get_evp_governance_records(limit: int = 200) -> dict:
    records = list_evp_records(limit=limit, operator_visible=None)
    pass_records = [item for item in records if str(item.get("gate_outcome", "")).upper() == "PASS"]
    no_pass_records = [item for item in records if str(item.get("gate_outcome", "")).upper() == "NO_PASS"]
    return {
        "total": len(records),
        "pass_count": len(pass_records),
        "no_pass_count": len(no_pass_records),
        "records": records,
    }
