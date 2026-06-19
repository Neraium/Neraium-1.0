from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.core.security import require_admin_role, require_api_access
from app.models.api_models import ObservabilitySummaryResponse
from app.services.aletheia_governance import list_evp_records
from app.services.auth_store import auth_summary
from app.services.evidence_store import list_evidence_runs
from app.services.runtime_db import audit_events_count, queue_metrics, upload_duration_samples
from app.services.upload_jobs import read_upload_cache_stats
from app.services.upload_persistence import read_upload_history
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE
from app.services.upload_state_repository import read_current_upload_result


router = APIRouter(tags=["observability"], dependencies=[Depends(require_api_access), Depends(require_admin_role)])


def percentile(values: list[float], point: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * point))
    index = max(0, min(index, len(ordered) - 1))
    return round(ordered[index], 3)


@router.get("/observability/summary", response_model=ObservabilitySummaryResponse)
def get_observability_summary() -> ObservabilitySummaryResponse:
    queue = queue_metrics()
    evidence_runs = list_evidence_runs(limit=100)
    upload_history = read_upload_history(UPLOAD_RUNTIME_STATE.runtime_dir, limit=100, current_result=read_current_upload_result())
    status_counts = Counter(run.get("status", "unknown") for run in evidence_runs)
    upload_count = len(upload_history)
    sparse_upload_count = 0
    unknown_profile_upload_count = 0
    total_room_count = 0
    total_flagged_room_count = 0
    for item in upload_history:
        metrics = item.get("intelligence_metrics", {}) if isinstance(item, dict) else {}
        room_count = int(metrics.get("room_count", 0) or 0)
        sparse_room_count = int(metrics.get("sparse_room_count", 0) or 0)
        flagged_room_count = int(metrics.get("flagged_room_count", 0) or 0)
        unknown_profile = bool(metrics.get("unknown_profile"))
        if sparse_room_count > 0:
            sparse_upload_count += 1
        if unknown_profile:
            unknown_profile_upload_count += 1
        total_room_count += max(room_count, 0)
        total_flagged_room_count += max(flagged_room_count, 0)
    sparse_upload_rate = round(sparse_upload_count / upload_count, 4) if upload_count > 0 else None
    unknown_profile_rate = round(unknown_profile_upload_count / upload_count, 4) if upload_count > 0 else None
    flagged_room_rate = round(total_flagged_room_count / total_room_count, 4) if total_room_count > 0 else None
    alerts: list[dict[str, str | int]] = []
    if queue.get("pending", 0) > 0:
        alerts.append({"level": "warning", "message": "Upload queue has pending jobs.", "count": queue["pending"]})
    if status_counts.get("failed", 0) > 0:
        alerts.append({"level": "warning", "message": "Evidence trail includes failed runs.", "count": status_counts["failed"]})
    if sparse_upload_rate is not None and sparse_upload_rate > 0.2:
        alerts.append({"level": "warning", "message": "Sparse telemetry appears in a high share of uploads.", "count": sparse_upload_count})
    if unknown_profile_rate is not None and unknown_profile_rate > 0.15:
        alerts.append({"level": "warning", "message": "Unknown-profile uploads are above threshold.", "count": unknown_profile_upload_count})
    if flagged_room_rate is not None and flagged_room_rate > 0.35:
        alerts.append({"level": "warning", "message": "Review/unstable room share is elevated.", "count": total_flagged_room_count})
    return ObservabilitySummaryResponse(
        queue=queue,
        evidence_runs={
            "total": len(evidence_runs),
            "status_counts": dict(status_counts),
            "latest_completed_at": evidence_runs[0].get("completed_at") if evidence_runs else None,
            "intelligence_metrics": {
                "upload_count": upload_count,
                "sparse_upload_count": sparse_upload_count,
                "sparse_upload_rate": sparse_upload_rate,
                "unknown_profile_upload_count": unknown_profile_upload_count,
                "unknown_profile_rate": unknown_profile_rate,
                "room_count": total_room_count,
                "flagged_room_count": total_flagged_room_count,
                "flagged_room_rate": flagged_room_rate,
            },
        },
        audit={"event_count": audit_events_count()},
        auth=auth_summary(),
        alerts=alerts,
    )


@router.get("/observability/metrics", response_class=PlainTextResponse)
def get_observability_metrics() -> PlainTextResponse:
    queue = queue_metrics()
    evidence_runs = list_evidence_runs(limit=100)
    upload_history = read_upload_history(UPLOAD_RUNTIME_STATE.runtime_dir, limit=100, current_result=read_current_upload_result())
    status_counts = Counter(run.get("status", "unknown") for run in evidence_runs)
    upload_count = len(upload_history)
    sparse_upload_count = 0
    unknown_profile_upload_count = 0
    total_room_count = 0
    total_flagged_room_count = 0
    for item in upload_history:
        metrics = item.get("intelligence_metrics", {}) if isinstance(item, dict) else {}
        room_count = int(metrics.get("room_count", 0) or 0)
        sparse_room_count = int(metrics.get("sparse_room_count", 0) or 0)
        flagged_room_count = int(metrics.get("flagged_room_count", 0) or 0)
        unknown_profile = bool(metrics.get("unknown_profile"))
        if sparse_room_count > 0:
            sparse_upload_count += 1
        if unknown_profile:
            unknown_profile_upload_count += 1
        total_room_count += max(room_count, 0)
        total_flagged_room_count += max(flagged_room_count, 0)
    sparse_upload_rate = (sparse_upload_count / upload_count) if upload_count > 0 else 0.0
    unknown_profile_rate = (unknown_profile_upload_count / upload_count) if upload_count > 0 else 0.0
    flagged_room_rate = (total_flagged_room_count / total_room_count) if total_room_count > 0 else 0.0
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
        "# HELP neraium_auth_users_active Active authenticated users.",
        "# TYPE neraium_auth_users_active gauge",
        f"neraium_auth_users_active {auth_summary().get("active_users", 0)}",
        "# HELP neraium_auth_sessions_active Active authenticated sessions.",
        "# TYPE neraium_auth_sessions_active gauge",
        f"neraium_auth_sessions_active {auth_summary().get("active_sessions", 0)}",
        "# HELP neraium_sparse_upload_rate Share of recent uploads containing at least one sparse-telemetry room.",
        "# TYPE neraium_sparse_upload_rate gauge",
        f"neraium_sparse_upload_rate {round(sparse_upload_rate, 4)}",
        "# HELP neraium_flagged_room_rate Share of recent rooms flagged review/unstable.",
        "# TYPE neraium_flagged_room_rate gauge",
        f"neraium_flagged_room_rate {round(flagged_room_rate, 4)}",
        "# HELP neraium_unknown_profile_rate Share of recent uploads with unknown telemetry profile.",
        "# TYPE neraium_unknown_profile_rate gauge",
        f"neraium_unknown_profile_rate {round(unknown_profile_rate, 4)}",
    ]
    return PlainTextResponse("\n".join(lines) + "\n") 


@router.get("/observability/performance")
def get_observability_performance(window: int = 200) -> dict:
    queue = queue_metrics()
    durations = upload_duration_samples(limit=max(10, min(window, 1000)))
    cache_stats = read_upload_cache_stats()
    hits = cache_stats.get("hash_cache_hits", 0)
    misses = cache_stats.get("hash_cache_misses", 0)
    total = hits + misses
    hit_rate = (hits / total) if total > 0 else None
    return {
        "queue_depth": queue.get("pending", 0) + queue.get("processing", 0),
        "queue": queue,
        "upload_duration_seconds": {
            "samples": len(durations),
            "p50": percentile(durations, 0.50),
            "p95": percentile(durations, 0.95),
            "max": round(max(durations), 3) if durations else None,
        },
        "cache": {
            "hash_cache_hits": hits,
            "hash_cache_misses": misses,
            "hash_cache_hit_rate": round(hit_rate, 4) if hit_rate is not None else None,
        },
    }


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
