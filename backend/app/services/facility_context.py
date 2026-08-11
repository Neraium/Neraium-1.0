from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from app.services.dataset_scope import current_dataset_scope
from app.services.runtime_db import read_latest_payload, upsert_latest_payload


CONTRACT_VERSION = "facility-context.v1"


def read_facility_context() -> dict[str, Any]:
    scope = current_dataset_scope()
    payload = read_latest_payload(_storage_key())
    if isinstance(payload, dict):
        return {**payload, "equipment": list(payload.get("equipment") or [])}
    return {
        "contract_version": CONTRACT_VERSION,
        "site_id": scope.workspace_id,
        "site_name": scope.workspace_id,
        "timezone": "UTC",
        "systems": [],
        "equipment": [],
        "signal_mappings": [],
        "updated_at": None,
        "updated_by": None,
    }


def write_facility_context(payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
    scope = current_dataset_scope()
    normalized = {
        "contract_version": CONTRACT_VERSION,
        "site_id": str(payload.get("site_id") or scope.workspace_id),
        "site_name": str(payload.get("site_name") or payload.get("site_id") or scope.workspace_id),
        "timezone": str(payload.get("timezone") or "UTC"),
        "systems": list(payload.get("systems") or []),
        "equipment": list(payload.get("equipment") or []),
        "signal_mappings": list(payload.get("signal_mappings") or []),
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": actor,
    }
    upsert_latest_payload(_storage_key(), normalized)
    return normalized


def _storage_key() -> str:
    scope = current_dataset_scope()
    facility_scope = f"facility-context.v1:{scope.tenant_id}:{scope.workspace_id}"
    return f"facility_context:{sha256(facility_scope.encode('utf-8')).hexdigest()[:32]}"
