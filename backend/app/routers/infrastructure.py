from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.core.security import require_admin_role, require_api_access
from app.services.production_health import production_health_snapshot

router = APIRouter(
    tags=["infrastructure"],
    dependencies=[Depends(require_api_access), Depends(require_admin_role)],
)


@router.get("/infrastructure/health")
def infrastructure_health(request: Request, incident_limit: int = Query(50, ge=1, le=100)) -> dict:
    snapshot = production_health_snapshot(request.app.state.settings)
    snapshot["incidents"] = list(snapshot.get("incidents") or [])[:incident_limit]
    snapshot["notification_history"] = list(snapshot.get("notification_history") or [])[:incident_limit]
    return snapshot
