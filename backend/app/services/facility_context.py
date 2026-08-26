from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from typing import Any

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.services.dataset_scope import current_dataset_scope
from app.services.phase4_scope import (
    ServerBoundSystemIdentity,
    ServerBoundSystemIdentityV2,
    build_telemetry_server_bound_system_identity,
    current_authenticated_phase4_scope,
)
from app.services.runtime_db import read_latest_payload, upsert_latest_payload
from app.services.telemetry_domain import TelemetryScopeRef


CONTRACT_VERSION = "facility-context.v1"


@dataclass(frozen=True, slots=True)
class SystemIdentityResolution:
    identity: ServerBoundSystemIdentity | None
    reason: str

    @property
    def available(self) -> bool:
        return self.identity is not None


@dataclass(frozen=True, slots=True)
class TelemetryAnalysisAuthorityResolution:
    """Fail-closed result of revalidating persisted telemetry hierarchy."""

    identity: ServerBoundSystemIdentityV2 | None
    reason: str

    @property
    def available(self) -> bool:
        return self.identity is not None


def _authority_record_digest(system: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"authority": CONTRACT_VERSION, "system": system},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(encoded.encode("utf-8")).hexdigest()


def facility_system_authority_digest(system: dict[str, Any]) -> str:
    """Canonical digest persisted with mappings and rechecked for analysis."""
    if not isinstance(system, dict):
        raise TypeError("facility_system_authority_record_required")
    return _authority_record_digest(system)


def facility_context_storage_key(
    *, tenant_scope_id: Any, workspace_id: Any
) -> str:
    """Return the stable facility registry key without consulting user scope."""
    tenant = str(tenant_scope_id or "").strip()
    workspace = str(workspace_id or "").strip()
    if not tenant or not workspace:
        raise ValueError("facility_context_scope_invalid")
    facility_scope = f"facility-context.v1:{tenant}:{workspace}"
    return f"facility_context:{sha256(facility_scope.encode('utf-8')).hexdigest()[:32]}"


def _authenticated_scope_for_telemetry(
    scope: TelemetryScopeRef | AuthenticatedPhase4Scope,
) -> AuthenticatedPhase4Scope | None:
    if isinstance(scope, TelemetryScopeRef):
        try:
            resolved = AuthenticatedPhase4Scope(
                tenant_scope_id=scope.tenant_scope_id,
                workspace_id=scope.workspace_id,
                resource_scope_id=scope.resource_scope_id,
            )
        except (TypeError, ValueError):
            return None
        if scope.facility_id != resolved.workspace_id:
            return None
    elif isinstance(scope, AuthenticatedPhase4Scope):
        try:
            resolved = AuthenticatedPhase4Scope(
                tenant_scope_id=scope.tenant_scope_id,
                workspace_id=scope.workspace_id,
                resource_scope_id=scope.resource_scope_id,
                version=scope.version,
            )
        except (TypeError, ValueError):
            return None
    else:
        return None
    # Personal/default and legacy free-form scopes remain upload-only.
    if not resolved.workspace_id.startswith("ws-"):
        return None
    return resolved


def read_facility_context_for_scope(
    scope: TelemetryScopeRef | AuthenticatedPhase4Scope,
) -> dict[str, Any] | None:
    """Read facility authority using only stable server-attested scope fields."""
    resolved = _authenticated_scope_for_telemetry(scope)
    if resolved is None:
        return None
    payload = read_latest_payload(
        facility_context_storage_key(
            tenant_scope_id=resolved.tenant_scope_id,
            workspace_id=resolved.workspace_id,
        )
    )
    if not isinstance(payload, dict):
        return None
    return {**payload, "equipment": list(payload.get("equipment") or [])}


def write_facility_context_for_scope(
    payload: dict[str, Any],
    *,
    scope: TelemetryScopeRef | AuthenticatedPhase4Scope,
    actor: str,
) -> dict[str, Any]:
    """Persist the server facility registry at its stable resource scope key."""
    resolved = _authenticated_scope_for_telemetry(scope)
    if resolved is None:
        raise ValueError("telemetry_facility_context_scope_unauthorized")
    normalized = {
        "contract_version": CONTRACT_VERSION,
        "site_id": str(payload.get("site_id") or resolved.workspace_id),
        "site_name": str(
            payload.get("site_name")
            or payload.get("site_id")
            or resolved.workspace_id
        ),
        "timezone": str(payload.get("timezone") or "UTC"),
        "systems": list(payload.get("systems") or []),
        "equipment": list(payload.get("equipment") or []),
        "signal_mappings": list(payload.get("signal_mappings") or []),
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": actor,
    }
    upsert_latest_payload(
        facility_context_storage_key(
            tenant_scope_id=resolved.tenant_scope_id,
            workspace_id=resolved.workspace_id,
        ),
        normalized,
    )
    return normalized


def resolve_telemetry_analysis_authority(
    scope: TelemetryScopeRef | AuthenticatedPhase4Scope,
    system_id: Any,
    asset_id: Any,
    persisted_authority_digest: Any,
) -> TelemetryAnalysisAuthorityResolution:
    """Revalidate an analysis window against current facility hierarchy.

    The system, asset and digest are selectors/comparators only. Authority is
    always re-read from the server-owned facility registry for ``scope``.
    """
    resolved_scope = _authenticated_scope_for_telemetry(scope)
    if resolved_scope is None:
        return TelemetryAnalysisAuthorityResolution(None, "telemetry_scope_unauthorized")
    requested_system = str(system_id or "").strip()
    requested_asset = str(asset_id or "").strip() or None
    persisted_digest = str(persisted_authority_digest or "").strip().lower()
    if not requested_system:
        return TelemetryAnalysisAuthorityResolution(None, "system_id_required")
    if len(persisted_digest) != 64 or any(
        character not in "0123456789abcdef" for character in persisted_digest
    ):
        return TelemetryAnalysisAuthorityResolution(None, "authority_digest_invalid")

    facility = read_facility_context_for_scope(resolved_scope)
    if not isinstance(facility, dict) or facility.get("contract_version") != CONTRACT_VERSION:
        return TelemetryAnalysisAuthorityResolution(
            None, "facility_context_authority_unavailable"
        )
    systems = facility.get("systems")
    equipment = facility.get("equipment")
    if not isinstance(systems, list) or not isinstance(equipment, list):
        return TelemetryAnalysisAuthorityResolution(None, "facility_context_hierarchy_invalid")

    records_by_id: dict[str, list[dict[str, Any]]] = {}
    for record in systems:
        if not isinstance(record, dict):
            return TelemetryAnalysisAuthorityResolution(
                None, "facility_context_hierarchy_invalid"
            )
        registered_id = str(record.get("system_id") or "").strip()
        if not registered_id:
            return TelemetryAnalysisAuthorityResolution(
                None, "facility_context_hierarchy_invalid"
            )
        records_by_id.setdefault(registered_id, []).append(record)
    if any(len(records) != 1 for records in records_by_id.values()):
        return TelemetryAnalysisAuthorityResolution(None, "system_id_not_unique")
    selected_systems = records_by_id.get(requested_system)
    if selected_systems is None:
        return TelemetryAnalysisAuthorityResolution(None, "system_id_not_registered")
    selected_system = selected_systems[0]

    if requested_asset is not None:
        selected_assets: list[dict[str, Any]] = []
        for record in equipment:
            if not isinstance(record, dict):
                return TelemetryAnalysisAuthorityResolution(
                    None, "facility_context_hierarchy_invalid"
                )
            canonical_asset = str(record.get("asset_id") or "").strip()
            legacy_equipment = str(record.get("equipment_id") or "").strip()
            if canonical_asset and legacy_equipment and canonical_asset != legacy_equipment:
                return TelemetryAnalysisAuthorityResolution(None, "asset_identity_ambiguous")
            registered_asset = canonical_asset or legacy_equipment
            if not registered_asset:
                return TelemetryAnalysisAuthorityResolution(None, "asset_identity_invalid")
            if registered_asset == requested_asset:
                selected_assets.append(record)
        if len(selected_assets) != 1:
            return TelemetryAnalysisAuthorityResolution(None, "asset_not_unique_or_registered")
        if str(selected_assets[0].get("system_id") or "").strip() != requested_system:
            return TelemetryAnalysisAuthorityResolution(None, "asset_system_mismatch")
        declared_ids = {
            str(item).strip()
            for field in ("asset_ids", "equipment_ids")
            for item in (
                selected_system.get(field)
                if isinstance(selected_system.get(field), list)
                else []
            )
            if str(item).strip()
        }
        if declared_ids and requested_asset not in declared_ids:
            return TelemetryAnalysisAuthorityResolution(None, "asset_system_mismatch")

    current_digest = _authority_record_digest(selected_system)
    if persisted_digest != current_digest:
        return TelemetryAnalysisAuthorityResolution(None, "authority_digest_stale")
    return TelemetryAnalysisAuthorityResolution(
        build_telemetry_server_bound_system_identity(
            scope=resolved_scope,
            system_id=requested_system,
            authority_record_digest=current_digest,
        ),
        "resolved_current_facility_authority",
    )


def resolve_server_bound_system_identity(
    *,
    requested_system_id: Any = None,
    baseline_system_id: Any = None,
) -> SystemIdentityResolution:
    """Resolve a business system only from this scope's persisted registry.

    Request and baseline values are selectors/comparators. Neither can create
    an identity that is absent from ``facility-context.v1.systems``.
    """
    scope = current_dataset_scope()
    facility = read_facility_context()
    if not isinstance(facility, dict) or facility.get("contract_version") != CONTRACT_VERSION:
        return SystemIdentityResolution(None, "facility_context_authority_unavailable")
    raw_systems = facility.get("systems")
    if not isinstance(raw_systems, list):
        return SystemIdentityResolution(None, "facility_context_systems_invalid")

    records_by_id: dict[str, list[dict[str, Any]]] = {}
    for raw_system in raw_systems:
        if not isinstance(raw_system, dict):
            return SystemIdentityResolution(None, "facility_context_systems_invalid")
        system_id = str(raw_system.get("system_id") or "").strip()
        if not system_id:
            return SystemIdentityResolution(None, "facility_context_systems_invalid")
        records_by_id.setdefault(system_id, []).append(raw_system)

    duplicate_ids = {system_id for system_id, records in records_by_id.items() if len(records) != 1}
    if duplicate_ids:
        return SystemIdentityResolution(None, "facility_context_system_id_not_unique")

    requested = str(requested_system_id or "").strip()
    baseline = str(baseline_system_id or "").strip()
    if baseline and baseline not in records_by_id:
        return SystemIdentityResolution(None, "baseline_system_id_not_registered")
    registered_baseline = baseline or None
    if requested:
        selected = records_by_id.get(requested)
        if selected is None:
            return SystemIdentityResolution(None, "requested_system_id_not_registered")
        if registered_baseline is not None and registered_baseline != requested:
            return SystemIdentityResolution(None, "baseline_system_id_mismatch")
        reason = "resolved_explicit_registered_system"
        selected_system_id = requested
    else:
        if not records_by_id:
            return SystemIdentityResolution(None, "no_registered_system")
        if len(records_by_id) != 1:
            return SystemIdentityResolution(None, "explicit_system_assignment_required")
        selected_system_id, selected = next(iter(records_by_id.items()))
        if registered_baseline is not None and registered_baseline != selected_system_id:
            return SystemIdentityResolution(None, "baseline_system_id_mismatch")
        reason = "resolved_unique_registered_system"

    return SystemIdentityResolution(
        ServerBoundSystemIdentity(
            system_id=selected_system_id,
            dataset_scope_storage_id=scope.storage_id,
            authority_record_digest=_authority_record_digest(selected[0]),
        ),
        reason,
    )


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
    telemetry_scope = current_authenticated_phase4_scope()
    if _authenticated_scope_for_telemetry(telemetry_scope) is not None:
        # Keep the upload-era dataset record untouched while also publishing
        # the same registry under stable facility authority for telemetry.
        upsert_latest_payload(
            facility_context_storage_key(
                tenant_scope_id=telemetry_scope.tenant_scope_id,
                workspace_id=telemetry_scope.workspace_id,
            ),
            normalized,
        )
    return normalized


def _storage_key() -> str:
    scope = current_dataset_scope()
    facility_scope = f"facility-context.v1:{scope.tenant_id}:{scope.workspace_id}"
    return f"facility_context:{sha256(facility_scope.encode('utf-8')).hexdigest()[:32]}"
