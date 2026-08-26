"""Explicit, facility-authorized signal discovery and mapping workflow."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import math
import uuid
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.telemetry_domain import (
    TelemetryScopeRef,
    reject_sensitive_telemetry_fields,
)
from app.services.telemetry_repository import PostgreSQLTelemetryRepository
from app.services.telemetry_units import conversion_contract


class SignalRegistryError(ValueError):
    """Stable validation failure for discovery and mapping APIs."""


@dataclass(frozen=True, slots=True)
class AuthorizedSignalHierarchy:
    """Hierarchy identity returned by server-owned facility authority."""

    facility_id: str
    system_id: str
    asset_id: str | None
    authority_digest: str
    authority_snapshot: Mapping[str, Any] | None = None


class HierarchyAuthority(Protocol):
    def __call__(
        self,
        scope: TelemetryScopeRef,
        system_id: str,
        asset_id: str | None,
    ) -> AuthorizedSignalHierarchy: ...


class FacilityContextHierarchyAuthority:
    """Production hierarchy resolver backed by the scoped facility registry."""

    def __call__(
        self,
        scope: TelemetryScopeRef,
        system_id: str,
        asset_id: str | None,
    ) -> AuthorizedSignalHierarchy:
        # Imports are local to keep the pure mapping service straightforward to
        # test while production resolution still uses request-bound context.
        from app.services.dataset_scope import current_dataset_scope
        from app.services.facility_context import (
            read_facility_context,
            resolve_server_bound_system_identity,
        )
        from app.services.telemetry_scope import (
            TelemetryScopeUnavailableError,
            current_telemetry_scope,
        )

        dataset_scope = current_dataset_scope()
        try:
            attested_scope = current_telemetry_scope()
        except TelemetryScopeUnavailableError as error:
            raise SignalRegistryError(
                "telemetry_mapping_scope_authority_mismatch"
            ) from error
        if attested_scope != scope or dataset_scope.tenant_id != scope.tenant_scope_id:
            raise SignalRegistryError("telemetry_mapping_scope_authority_mismatch")
        resolution = resolve_server_bound_system_identity(
            requested_system_id=system_id
        )
        identity = resolution.identity
        if identity is None:
            raise SignalRegistryError(
                f"telemetry_mapping_system_unauthorized:{resolution.reason}"
            )
        if (
            identity.system_id != system_id
            or identity.dataset_scope_storage_id != dataset_scope.storage_id
        ):
            raise SignalRegistryError("telemetry_mapping_system_authority_mismatch")

        facility = read_facility_context()
        systems = facility.get("systems") if isinstance(facility, Mapping) else None
        equipment = facility.get("equipment") if isinstance(facility, Mapping) else None
        if not isinstance(systems, list) or not isinstance(equipment, list):
            raise SignalRegistryError("telemetry_mapping_facility_authority_invalid")
        selected_systems = [
            record
            for record in systems
            if isinstance(record, Mapping)
            and str(record.get("system_id") or "").strip() == system_id
        ]
        if len(selected_systems) != 1:
            raise SignalRegistryError("telemetry_mapping_system_authority_invalid")

        if asset_id is not None:
            selected_assets: list[Mapping[str, Any]] = []
            for record in equipment:
                if not isinstance(record, Mapping):
                    raise SignalRegistryError(
                        "telemetry_mapping_facility_authority_invalid"
                    )
                canonical_asset = str(record.get("asset_id") or "").strip()
                legacy_equipment = str(record.get("equipment_id") or "").strip()
                if canonical_asset and legacy_equipment and canonical_asset != legacy_equipment:
                    raise SignalRegistryError("telemetry_mapping_asset_identity_ambiguous")
                resolved_asset = canonical_asset or legacy_equipment
                if not resolved_asset:
                    raise SignalRegistryError("telemetry_mapping_asset_identity_invalid")
                if resolved_asset == asset_id:
                    selected_assets.append(record)
            if len(selected_assets) != 1:
                raise SignalRegistryError("telemetry_mapping_asset_unauthorized")
            asset_system_id = str(
                selected_assets[0].get("system_id") or ""
            ).strip()
            declared_equipment = selected_systems[0].get("equipment_ids")
            declared_assets = selected_systems[0].get("asset_ids")
            declared_ids = {
                str(item)
                for collection in (declared_equipment, declared_assets)
                if isinstance(collection, list)
                for item in collection
            }
            if asset_system_id != system_id or (
                declared_ids and asset_id not in declared_ids
            ):
                raise SignalRegistryError("telemetry_mapping_asset_system_mismatch")

        return AuthorizedSignalHierarchy(
            facility_id=scope.facility_id,
            system_id=identity.system_id,
            asset_id=asset_id,
            authority_digest=identity.authority_record_digest,
            authority_snapshot={
                "contract_version": "telemetry-analysis-authority-snapshot.v1",
                "facility_id": scope.facility_id,
                "system_id": identity.system_id,
                "asset_id": asset_id,
                "system_record": dict(selected_systems[0]),
                "asset_record": (
                    dict(selected_assets[0]) if asset_id is not None else None
                ),
            },
        )


UuidFactory = Callable[[], uuid.UUID]


def _text(value: Any, code: str, *, maximum: int = 512) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum or any(
        ord(character) < 32 for character in normalized
    ):
        raise SignalRegistryError(code)
    return normalized


def _timezone(value: Any) -> str:
    name = _text(value, "telemetry_mapping_timezone_invalid", maximum=128)
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as error:
        raise SignalRegistryError("telemetry_mapping_timezone_invalid") from error
    return name


def _supported_unit_identity(value: str) -> str | None:
    contract = conversion_contract(
        source_unit=value,
        canonical_unit=value,
        expected_dimension=None,
    )
    conversion_id = contract.get("conversion_id")
    if not contract.get("valid") or not isinstance(conversion_id, str):
        return None
    return conversion_id.partition("_to_")[0]


class SignalRegistryService:
    """Coordinates registry writes without treating client claims as authority."""

    def __init__(
        self,
        repository: PostgreSQLTelemetryRepository,
        hierarchy_authority: HierarchyAuthority,
        *,
        uuid_factory: UuidFactory = uuid.uuid4,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(hierarchy_authority):
            raise TypeError("telemetry_hierarchy_authority_required")
        self._repository = repository
        self._hierarchy_authority = hierarchy_authority
        self._uuid_factory = uuid_factory
        self._clock = clock

    def register_discovered_signals(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        signals: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Persist discovered tags as disabled and mapping-required.

        Signal UUIDs are derived from scoped source identity so repeated
        discovery is stable without making an external tag a tenancy key.
        """
        prepared: list[dict[str, Any]] = []
        for raw in signals:
            reject_sensitive_telemetry_fields(
                raw, code="telemetry_signal_metadata_invalid"
            )
            tag_id = _text(
                raw.get("external_tag_id"),
                "telemetry_external_tag_id_invalid",
                maximum=160,
            )
            tag_name = _text(
                raw.get("external_tag_name") or tag_id,
                "telemetry_external_tag_name_invalid",
            )
            stable_material = "\0".join(
                (scope.resource_scope_id, connection_id, tag_id)
            )
            signal_id = uuid.uuid5(uuid.NAMESPACE_URL, stable_material)
            metadata = raw.get("metadata") or {}
            if not isinstance(metadata, Mapping):
                raise SignalRegistryError("telemetry_signal_metadata_invalid")
            prepared.append(
                {
                    "signal_id": str(signal_id),
                    "external_tag_id": tag_id,
                    "external_tag_name": tag_name,
                    "display_label": raw.get("display_label"),
                    "source_unit": raw.get("source_unit"),
                    "sample_cadence_seconds": raw.get("sample_cadence_seconds"),
                    "metadata": dict(metadata),
                }
            )
        return self._repository.upsert_external_signals(
            scope, connection_id=connection_id, signals=prepared
        )

    def list_signals(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        mapping_status: str | None = None,
        limit: int = 250,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._repository.list_external_signals(
            scope,
            connection_id=connection_id,
            mapping_status=mapping_status,
            limit=limit,
            offset=offset,
        )

    def get_signal(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        signal_id: str,
    ) -> dict[str, Any] | None:
        return self._repository.get_external_signal(
            scope, connection_id=connection_id, signal_id=signal_id
        )

    def list_canonical_concepts(
        self, *, active_only: bool = True, limit: int = 500
    ) -> list[dict[str, Any]]:
        return self._repository.list_canonical_signal_concepts(
            active_only=active_only, limit=limit
        )

    def map_signal(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        signal_id: str,
        system_id: str,
        asset_id: str | None,
        canonical_concept_id: str,
        source_unit: str,
        source_timezone: str,
        actor_id: str,
        expected_cadence_seconds: float | None = None,
        provenance: str = "manual",
        provenance_reason: str | None = None,
        expected_revision: int | None = None,
    ) -> dict[str, Any]:
        """Approve an explicit mapping after hierarchy and unit validation."""
        actor = _text(actor_id, "telemetry_mapping_actor_required", maximum=320)
        explicit_source_unit = _text(
            source_unit, "telemetry_mapping_source_unit_required", maximum=64
        )
        timezone_name = _timezone(source_timezone)
        cadence = (
            float(expected_cadence_seconds)
            if expected_cadence_seconds is not None
            else None
        )
        if cadence is not None and (
            not math.isfinite(cadence) or cadence <= 0 or cadence > 86_400
        ):
            raise SignalRegistryError("telemetry_mapping_cadence_invalid")
        if provenance not in {"manual", "approved_suggestion", "imported_verified"}:
            raise SignalRegistryError("telemetry_mapping_provenance_invalid")
        requested_system = _text(
            system_id, "telemetry_mapping_system_required", maximum=160
        )
        requested_asset = (
            _text(asset_id, "telemetry_mapping_asset_invalid", maximum=160)
            if asset_id is not None
            else None
        )
        hierarchy = self._hierarchy_authority(
            scope, requested_system, requested_asset
        )
        if (
            hierarchy.facility_id != scope.facility_id
            or hierarchy.system_id != requested_system
            or hierarchy.asset_id != requested_asset
            or not hierarchy.authority_digest
        ):
            raise SignalRegistryError("telemetry_mapping_hierarchy_unauthorized")

        context = self._repository.get_mapping_context(
            scope,
            connection_id=connection_id,
            signal_id=signal_id,
            canonical_concept_id=canonical_concept_id,
        )
        if context is None:
            raise SignalRegistryError("telemetry_signal_or_concept_not_found")
        discovered_source_unit = str(context.get("source_unit") or "").strip()
        if discovered_source_unit and _supported_unit_identity(
            discovered_source_unit
        ) != _supported_unit_identity(explicit_source_unit):
            raise SignalRegistryError("telemetry_mapping_source_unit_mismatch")
        canonical_unit = _text(
            context.get("canonical_unit"),
            "telemetry_mapping_canonical_unit_missing",
            maximum=64,
        )
        unit_contract = conversion_contract(
            source_unit=explicit_source_unit,
            canonical_unit=canonical_unit,
            expected_dimension=str(context.get("physical_dimension") or ""),
        )
        if not unit_contract["valid"]:
            raise SignalRegistryError(
                f"telemetry_mapping_unit_invalid:{unit_contract['reason_code']}"
            )
        reason = (
            _text(
                provenance_reason,
                "telemetry_mapping_provenance_reason_invalid",
                maximum=500,
            )
            if provenance_reason is not None
            else None
        )
        mapped_at = self._clock()
        if mapped_at.tzinfo is None or mapped_at.utcoffset() is None:
            raise SignalRegistryError("telemetry_mapping_clock_invalid")
        return self._repository.save_signal_mapping(
            scope,
            mapping_id=str(self._uuid_factory()),
            event_id=str(self._uuid_factory()),
            connection_id=connection_id,
            signal_id=signal_id,
            system_id=hierarchy.system_id,
            asset_id=hierarchy.asset_id,
            canonical_concept_id=canonical_concept_id,
            canonical_signal_name=_text(
                context.get("canonical_name"),
                "telemetry_mapping_canonical_name_missing",
                maximum=160,
            ),
            source_unit=explicit_source_unit,
            canonical_unit=canonical_unit,
            conversion_id=str(unit_contract["conversion_id"]),
            conversion_version=str(unit_contract["conversion_version"]),
            expected_cadence_seconds=cadence,
            source_timezone=timezone_name,
            provenance=provenance,
            provenance_reason=reason,
            actor_id=actor,
            authority_digest=hierarchy.authority_digest,
            authority_snapshot=(
                dict(hierarchy.authority_snapshot)
                if isinstance(hierarchy.authority_snapshot, Mapping)
                else {
                    "contract_version": "telemetry-analysis-authority-snapshot.v1",
                    "facility_id": hierarchy.facility_id,
                    "system_id": hierarchy.system_id,
                    "asset_id": hierarchy.asset_id,
                }
            ),
            mapped_at=mapped_at,
            expected_revision=expected_revision,
        )

    def disable_mapping(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        signal_id: str,
        expected_revision: int,
        actor_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return self._repository.disable_signal_mapping(
            scope,
            connection_id=connection_id,
            signal_id=signal_id,
            expected_revision=expected_revision,
            actor_id=_text(
                actor_id, "telemetry_mapping_actor_required", maximum=320
            ),
            event_id=str(self._uuid_factory()),
            reason=(
                _text(reason, "telemetry_mapping_disable_reason_invalid", maximum=500)
                if reason is not None
                else None
            ),
        )
