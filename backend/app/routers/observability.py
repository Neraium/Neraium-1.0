from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends

from app.core.security import require_api_access
from app.models.api_models import ObservabilitySummaryResponse
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
