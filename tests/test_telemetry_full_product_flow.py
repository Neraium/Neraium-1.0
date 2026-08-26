from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping
import uuid

from app.connectors.base import (
    ConnectorCapability,
    ConnectorPage,
    ConnectorProviderDescriptor,
    ConnectorValidationResult,
    DiscoveredSignal,
    ProviderHealthResult,
    RawObservationEnvelope,
    TelemetryConnector,
)
from app.engine.sii.behavioral_model_contract import (
    AuthenticatedPhase4Scope,
    canonical_phase4_resource_scope_id,
)
from app.engine.sii_engine import evaluate_sii as authoritative_evaluate_sii
from app.models.telemetry_api_models import (
    ConnectionCreateRequest,
    CredentialPutRequest,
    SignalMappingPutRequest,
)
from app.services.canonical_signal_catalog import CANONICAL_SIGNAL_CONCEPTS_V1
from app.services.facility_context import (
    facility_system_authority_digest,
    resolve_telemetry_analysis_authority,
    write_facility_context_for_scope,
)
from app.services.phase4_scope import ServerBoundSystemIdentityV2
from app.services.signal_registry import (
    AuthorizedSignalHierarchy,
    SignalRegistryService,
)
from app.services.telemetry_analysis_service import process_ingestion_run
from app.services.telemetry_connection_service import TelemetryConnectionService
from app.services.telemetry_domain import ConnectorType, TelemetryScopeRef
from app.services.telemetry_ingestion import prepare_connector_page
from app.services.telemetry_runtime import TelemetryProviderRegistry, TelemetryRuntime
from app.services.telemetry_scheduler import TelemetryScheduler
from app.services.telemetry_secrets import MemoryTelemetrySecretStore, SecretBinding
from app.services.telemetry_result_service import TelemetryCanonicalResultService
from app.services.upload_persistence import project_result_for_transport


NOW = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
ACTOR = "operator@customer.example"
SYSTEM_ID = "chilled-water-loop-a"
ASSET_ID = "primary-pump-a"
PRESSURE_CONCEPT_ID = "9fa5d454-6b13-5f59-99d1-7f6fb0a3e07f"
FLOW_CONCEPT_ID = "a19db5be-5ca1-5373-a9e4-6957e9f54c43"
POWER_CONCEPT_ID = "4385267d-f840-59c4-ba65-06a6726e3189"


def _scope() -> TelemetryScopeRef:
    tenant = "tenant-customer-a"
    facility = "ws-facility-central-plant"
    return TelemetryScopeRef(
        tenant_scope_id=tenant,
        workspace_id=facility,
        resource_scope_id=canonical_phase4_resource_scope_id(tenant, facility),
        facility_id=facility,
    )


class SyntheticReadOnlyConnector(TelemetryConnector):
    """Controlled source fake; all Neraium orchestration remains production code."""

    def __init__(self, secret_store: MemoryTelemetrySecretStore) -> None:
        self.secret_store = secret_store
        self.validation_count = 0
        self.discovery_count = 0
        self.fetch_count = 0
        self.received_valid_binding = False

    @classmethod
    def descriptor(cls) -> ConnectorProviderDescriptor:
        return ConnectorProviderDescriptor(
            connector_type=ConnectorType.HTTPS_TELEMETRY,
            display_name="Synthetic HTTPS telemetry",
            description="Retrieval-only test provider",
            capabilities=frozenset(
                {
                    ConnectorCapability.VALIDATE,
                    ConnectorCapability.DISCOVER_SIGNALS,
                    ConnectorCapability.INCREMENTAL_POLLING,
                    ConnectorCapability.HEALTH_CHECK,
                }
            ),
            production_available=True,
        )

    def validate(self, context: Any) -> ConnectorValidationResult:
        self.validation_count += 1
        assert context.secret_binding is not None
        secret = self.secret_store.resolve(context.secret_binding)
        self.received_valid_binding = (
            secret.get_required("bearer_token") == "opaque-test-canary"
        )
        return ConnectorValidationResult(
            valid=self.received_valid_binding,
            reachable=True,
            authenticated=self.received_valid_binding,
            observations_sampled=1,
            code="validated",
        )

    def discover_signals(self, context: Any, *, checkpoint: Any = None) -> ConnectorPage:
        assert checkpoint is None
        self.discovery_count += 1
        return ConnectorPage(
            signals=(
                DiscoveredSignal("PUMP-A.PRESSURE", "Pump discharge pressure", reported_unit="psi"),
                DiscoveredSignal("PUMP-A.FLOW", "Primary loop flow", reported_unit="GPM"),
                DiscoveredSignal("PUMP-A.POWER", "Pump active power", reported_unit="kW"),
                DiscoveredSignal("PUMP-A.VIBRATION", "Pump vibration", reported_unit="percent"),
            )
        )

    def fetch_incremental(self, context: Any, *, checkpoint: Any = None) -> ConnectorPage:
        assert context.secret_binding is not None
        self.fetch_count += 1
        observations: list[RawObservationEnvelope] = []
        for index in range(120):
            timestamp = NOW - timedelta(minutes=119 - index)
            flow = 500.0 + index * 2.0
            pressure = (
                25.0 + flow * 0.1
                if index < 84
                else 95.0 + ((index * 17) % 11)
            )
            power = (
                10.0 + flow * 0.05
                if index < 84
                else 35.0 + ((index * 29) % 23)
            )
            observations.extend(
                (
                    RawObservationEnvelope(
                        external_tag_id="PUMP-A.PRESSURE",
                        external_tag_name="Pump discharge pressure",
                        source_timestamp=timestamp,
                        raw_value=pressure,
                        reported_unit="psi",
                        reported_quality="good",
                        provider_event_id=f"pressure-{index}",
                    ),
                    RawObservationEnvelope(
                        external_tag_id="PUMP-A.FLOW",
                        external_tag_name="Primary loop flow",
                        source_timestamp=timestamp,
                        raw_value=flow,
                        reported_unit="GPM",
                        reported_quality="good",
                        provider_event_id=f"flow-{index}",
                    ),
                    RawObservationEnvelope(
                        external_tag_id="PUMP-A.POWER",
                        external_tag_name="Pump active power",
                        source_timestamp=timestamp,
                        raw_value=power,
                        reported_unit="kW",
                        reported_quality="good",
                        provider_event_id=f"power-{index}",
                    ),
                    RawObservationEnvelope(
                        external_tag_id="PUMP-A.VIBRATION",
                        external_tag_name="Pump vibration",
                        source_timestamp=timestamp,
                        raw_value=12.0 + index,
                        reported_unit="percent",
                        reported_quality="good",
                        provider_event_id=f"unmapped-{index}",
                    ),
                )
            )
        return ConnectorPage(observations=tuple(observations), pages_read=1)

    def fetch_backfill(
        self, context: Any, *, time_range: Any, checkpoint: Any = None
    ) -> ConnectorPage:
        raise AssertionError("incremental product flow must not invoke backfill")

    def health(self, context: Any) -> ProviderHealthResult:
        return ProviderHealthResult(True, True, True, NOW, "healthy")


class InMemoryHealthService:
    def __init__(self) -> None:
        self.refreshes: list[str] = []

    def get_health(self, scope: TelemetryScopeRef, *, connection_id: str) -> None:
        return None

    def evaluate_and_persist(
        self, scope: TelemetryScopeRef, *, connection_id: str, **probes: Any
    ) -> dict[str, Any]:
        self.refreshes.append(connection_id)
        return {"aggregate_status": "unknown", "probe_count": len(probes)}


class InMemoryProductFlowRepository:
    """Scoped persistence fake implementing the production repository protocols."""

    def __init__(self, scope: TelemetryScopeRef) -> None:
        self.scope = scope
        self.connections: dict[str, dict[str, Any]] = {}
        self.bindings: dict[str, SecretBinding] = {}
        self.signals: dict[str, dict[str, Any]] = {}
        self.mappings: dict[str, dict[str, Any]] = {}
        self.authority_snapshots: dict[tuple[str, str | None, str], dict[str, Any]] = {}
        self.runs: dict[str, dict[str, Any]] = {}
        self.observations: list[dict[str, Any]] = []
        self.rejections: list[dict[str, Any]] = []
        self.windows: dict[str, dict[str, Any]] = {}
        self.audit: list[dict[str, Any]] = []
        self.checkpoint = {
            "mode": "incremental",
            "cursor_payload": {},
            "high_water_at": None,
            "revision": 0,
        }
        self.active_claim: dict[str, Any] | None = None
        self.scope_checks = 0

    def _assert_scope(self, scope: TelemetryScopeRef) -> None:
        assert scope == self.scope
        self.scope_checks += 1

    def verify_readiness(self) -> bool:
        return True

    def create_connection(self, scope: TelemetryScopeRef, **values: Any) -> dict[str, Any]:
        self._assert_scope(scope)
        connection_id = values["connection_id"]
        now = NOW
        record = {
            "id": connection_id,
            **scope.as_public_dict(),
            "name": values["name"],
            "connector_type": str(values["connector_type"]),
            "safe_config": deepcopy(values["safe_config"]),
            "timezone": values["timezone_name"],
            "polling_interval_seconds": values["polling_interval_seconds"],
            "lifecycle_status": "draft",
            "enabled": False,
            "credentials_configured": False,
            "last_attempt_at": None,
            "last_success_at": None,
            "last_healthy_at": None,
            "last_telemetry_at": None,
            "last_error_code": None,
            "last_error_summary": None,
            "created_at": now,
            "updated_at": now,
            "next_attempt_at": None,
        }
        self.connections[connection_id] = record
        if values.get("audit_event_id"):
            self.audit.append(
                {
                    "event_id": values["audit_event_id"],
                    "connection_id": connection_id,
                    "actor_id": values["actor_id"],
                    "action": "connection_created",
                    "safe_detail": deepcopy(values.get("audit_safe_detail") or {}),
                    **scope.as_public_dict(),
                }
            )
        return deepcopy(record)

    def get_connection(self, scope: TelemetryScopeRef, connection_id: str) -> dict[str, Any] | None:
        self._assert_scope(scope)
        record = self.connections.get(connection_id)
        return deepcopy(record) if record is not None else None

    def list_connections(self, scope: TelemetryScopeRef) -> list[dict[str, Any]]:
        self._assert_scope(scope)
        return [deepcopy(item) for item in self.connections.values()]

    def get_connection_health(self, scope: TelemetryScopeRef, *, connection_id: str) -> None:
        self._assert_scope(scope)
        assert connection_id in self.connections
        return None

    def set_connection_lifecycle(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        target_status: Any,
        enabled: bool | None = None,
        **changes: Any,
    ) -> dict[str, Any]:
        self._assert_scope(scope)
        record = self.connections[connection_id]
        record["lifecycle_status"] = str(target_status)
        if enabled is not None:
            record["enabled"] = enabled
        record.update({key: value for key, value in changes.items() if key != "actor_id"})
        return deepcopy(record)

    def record_audit_event(self, scope: TelemetryScopeRef, **event: Any) -> None:
        self._assert_scope(scope)
        self.audit.append({**deepcopy(event), **scope.as_public_dict()})

    def load_secret_binding(
        self, scope: TelemetryScopeRef, *, connection_id: str
    ) -> SecretBinding | None:
        self._assert_scope(scope)
        return self.bindings.get(connection_id)

    def upsert_secret_binding(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        binding_id: str,
        provider: str,
        internal_reference: str,
        version_marker: str | None,
        actor_id: str | None = None,
        audit_event_id: str | None = None,
        audit_safe_detail: dict[str, Any] | None = None,
    ) -> dict[str, bool]:
        self._assert_scope(scope)
        self.bindings[connection_id] = SecretBinding.from_internal_persistence(
            binding_id=binding_id,
            provider=provider,
            resource_scope_id=scope.resource_scope_id,
            connection_id=connection_id,
            internal_reference=internal_reference,
            version_marker=version_marker,
        )
        self.connections[connection_id]["credentials_configured"] = True
        if audit_event_id is not None:
            self.audit.append(
                {
                    "event_id": audit_event_id,
                    "connection_id": connection_id,
                    "actor_id": actor_id,
                    "action": "credential_binding_changed",
                    "safe_detail": deepcopy(audit_safe_detail or {}),
                    **scope.as_public_dict(),
                }
            )
        return {"credentials_configured": True}

    def list_canonical_signal_concepts(self, **kwargs: Any) -> list[dict[str, Any]]:
        del kwargs
        return [
            {
                "id": item.concept_id,
                "canonical_name": item.canonical_name,
                "display_name": item.display_name,
                "physical_dimension": item.physical_dimension,
                "canonical_unit": item.canonical_unit,
                "taxonomy_version": item.taxonomy_version,
            }
            for item in CANONICAL_SIGNAL_CONCEPTS_V1
        ]

    def upsert_external_signals(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        signals: list[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        self._assert_scope(scope)
        returned = []
        for raw in signals:
            existing = next(
                (
                    item
                    for item in self.signals.values()
                    if item["connection_id"] == connection_id
                    and item["external_tag_id"] == raw["external_tag_id"]
                ),
                None,
            )
            if existing is None:
                existing = {
                    "id": raw["signal_id"],
                    "connection_id": connection_id,
                    "external_tag_id": raw["external_tag_id"],
                    "external_tag_name": raw["external_tag_name"],
                    "display_label": raw.get("display_label"),
                    "source_unit": raw.get("source_unit"),
                    "sample_cadence_seconds": raw.get("sample_cadence_seconds"),
                    "enabled": False,
                    "mapping_status": "unmapped",
                    "last_observed_at": None,
                    "quality_state": "mapping_required",
                    **scope.as_public_dict(),
                }
                self.signals[existing["id"]] = existing
            returned.append(deepcopy(existing))
        return returned

    def list_external_signals(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        mapping_status: str | None,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        self._assert_scope(scope)
        selected = [
            item
            for item in self.signals.values()
            if item["connection_id"] == connection_id
            and (mapping_status is None or item["mapping_status"] == mapping_status)
        ]
        return [deepcopy(item) for item in selected[offset : offset + limit]]

    def get_external_signal(
        self, scope: TelemetryScopeRef, *, connection_id: str, signal_id: str
    ) -> dict[str, Any] | None:
        self._assert_scope(scope)
        item = self.signals.get(signal_id)
        if item is None or item["connection_id"] != connection_id:
            return None
        return deepcopy(item)

    def get_mapping_context(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        signal_id: str,
        canonical_concept_id: str,
    ) -> dict[str, Any] | None:
        self._assert_scope(scope)
        signal = self.signals.get(signal_id)
        concept = next(
            (
                item
                for item in CANONICAL_SIGNAL_CONCEPTS_V1
                if item.concept_id == canonical_concept_id
            ),
            None,
        )
        if signal is None or signal["connection_id"] != connection_id or concept is None:
            return None
        return {
            "signal_id": signal_id,
            "connection_id": connection_id,
            "source_unit": signal["source_unit"],
            "external_tag_id": signal["external_tag_id"],
            "canonical_concept_id": concept.concept_id,
            "canonical_name": concept.canonical_name,
            "display_name": concept.display_name,
            "physical_dimension": concept.physical_dimension,
            "canonical_unit": concept.canonical_unit,
            "taxonomy_version": concept.taxonomy_version,
        }

    def save_signal_mapping(self, scope: TelemetryScopeRef, **values: Any) -> dict[str, Any]:
        self._assert_scope(scope)
        signal = self.signals[values["signal_id"]]
        revision = int(signal.get("mapping_revision") or 0) + 1
        mapping = {
            "id": values["mapping_id"],
            "mapping_id": values["mapping_id"],
            "connection_id": values["connection_id"],
            "external_signal_id": values["signal_id"],
            "external_tag_id": signal["external_tag_id"],
            "revision": revision,
            "mapped_by": values["actor_id"],
            "mapped_at": values["mapped_at"],
            "authority_digest": values["authority_digest"],
            "system_id": values["system_id"],
            "asset_id": values["asset_id"],
            "canonical_concept_id": values["canonical_concept_id"],
            "canonical_signal_id": values["canonical_concept_id"],
            "canonical_signal_name": values["canonical_signal_name"],
            "source_unit": values["source_unit"],
            "canonical_unit": values["canonical_unit"],
            "expected_dimension": self.get_mapping_context(
                scope,
                connection_id=values["connection_id"],
                signal_id=values["signal_id"],
                canonical_concept_id=values["canonical_concept_id"],
            )["physical_dimension"],
            "conversion_id": values["conversion_id"],
            "conversion_version": values["conversion_version"],
            "source_timezone": values["source_timezone"],
            "expected_cadence_seconds": values["expected_cadence_seconds"],
            "provenance": values["provenance"],
            "enabled": True,
        }
        self.mappings[values["signal_id"]] = mapping
        snapshot = dict(values["authority_snapshot"])
        self.authority_snapshots[
            (values["system_id"], values["asset_id"], values["authority_digest"])
        ] = snapshot
        signal.update(
            {
                "enabled": True,
                "mapping_status": "mapped",
                "quality_state": "unknown",
                "mapping_id": values["mapping_id"],
                "system_id": values["system_id"],
                "asset_id": values["asset_id"],
                "canonical_signal_id": values["canonical_concept_id"],
                "canonical_signal_name": values["canonical_signal_name"],
                "canonical_unit": values["canonical_unit"],
                "conversion_id": values["conversion_id"],
                "conversion_version": values["conversion_version"],
                "source_timezone": values["source_timezone"],
                "expected_cadence_seconds": values["expected_cadence_seconds"],
                "provenance": values["provenance"],
                "mapping_revision": revision,
            }
        )
        return deepcopy(mapping)

    def schedule_connection_now(
        self, scope: TelemetryScopeRef, *, connection_id: str, requested_at: datetime
    ) -> bool:
        self._assert_scope(scope)
        self.connections[connection_id]["next_attempt_at"] = requested_at
        return True

    def claim_next_due_work(
        self, *, worker_id: str, now: datetime, lease_seconds: int
    ) -> dict[str, Any] | None:
        del lease_seconds
        if self.active_claim is not None:
            return None
        connection = next(
            (
                item
                for item in self.connections.values()
                if item["enabled"] and item["next_attempt_at"] is not None
            ),
            None,
        )
        if connection is None:
            return None
        run_id = str(uuid.uuid4())
        lease_token = str(uuid.uuid4())
        self.active_claim = {
            "scope": self.scope,
            "connection_id": connection["id"],
            "run_id": run_id,
            "lease_token": lease_token,
            "run_mode": "incremental",
            "checkpoint_mode": "incremental",
        }
        self.runs[run_id] = {
            "id": run_id,
            "connection_id": connection["id"],
            "status": "running",
            "mode": "incremental",
            "worker_id": worker_id,
            "started_at": now,
            **self.scope.as_public_dict(),
        }
        return deepcopy(self.active_claim)

    def load_ingestion_snapshot(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        run_id: str,
        lease_token: str,
        checkpoint_mode: str,
    ) -> dict[str, Any]:
        self._assert_scope(scope)
        assert self.active_claim == {
            "scope": scope,
            "connection_id": connection_id,
            "run_id": run_id,
            "lease_token": lease_token,
            "run_mode": "incremental",
            "checkpoint_mode": checkpoint_mode,
        }
        return {
            "scope": scope,
            "connection": deepcopy(self.connections[connection_id]),
            "secret_binding": self.bindings.get(connection_id),
            "mappings": [deepcopy(item) for item in self.mappings.values()],
            "checkpoint": deepcopy(self.checkpoint),
            "existing_source_record_digests": tuple(
                item["source_record_digest"] for item in self.observations
            ),
        }

    def persist_ingestion_page(self, scope: TelemetryScopeRef, **values: Any) -> dict[str, int]:
        self._assert_scope(scope)
        assert values["expected_checkpoint_revision"] == self.checkpoint["revision"]
        connection_id = values["connection_id"]
        run_id = values["run_id"]
        for raw in values["observations"]:
            record = {
                **dict(raw),
                **scope.as_public_dict(),
                "connection_id": connection_id,
                "ingestion_run_id": run_id,
            }
            record["source_metadata"] = dict(record.get("source_metadata") or {})
            self.observations.append(record)
            self.signals[record["external_signal_id"]]["last_observed_at"] = record[
                "observed_at_utc"
            ]
            self.signals[record["external_signal_id"]]["quality_state"] = record[
                "quality_state"
            ]
        for raw in values["rejections"]:
            rejection = {
                **dict(raw),
                **scope.as_public_dict(),
                "connection_id": connection_id,
                "ingestion_run_id": run_id,
            }
            rejection["safe_context"] = dict(rejection.get("safe_context") or {})
            self.rejections.append(rejection)
        self.checkpoint = {
            "mode": values["checkpoint_mode"],
            "cursor_payload": deepcopy(values["cursor_payload"]),
            "high_water_at": values["high_water_at"],
            "revision": self.checkpoint["revision"] + 1,
        }
        if self.observations:
            self.connections[connection_id]["last_telemetry_at"] = max(
                item["observed_at_utc"] for item in self.observations
            )
        run = self.runs[run_id]
        run["observations_received"] = values["received_count"]
        run["observations_accepted"] = len(values["observations"])
        run["observations_rejected"] = len(values["rejections"])
        return {
            "checkpoint_revision": self.checkpoint["revision"],
            "accepted": len(values["observations"]),
            "rejected": len(values["rejections"]),
            "duplicate": 0,
            "out_of_order": 0,
        }

    def renew_lease(self, scope: TelemetryScopeRef, **values: Any) -> bool:
        self._assert_scope(scope)
        assert self.active_claim is not None
        assert values["lease_token"] == self.active_claim["lease_token"]
        return True

    def complete_ingestion_work(self, scope: TelemetryScopeRef, **values: Any) -> dict[str, Any]:
        self._assert_scope(scope)
        run = self.runs[values["run_id"]]
        run["status"] = "partial" if values["partial"] else "succeeded"
        run["finished_at"] = values["completed_at"]
        connection = self.connections[values["connection_id"]]
        connection["next_attempt_at"] = values["next_attempt_at"]
        connection["last_success_at"] = values["completed_at"]
        connection["lifecycle_status"] = "degraded" if values["partial"] else "connected"
        self.active_claim = None
        return deepcopy(run)

    def continue_ingestion_work(self, scope: TelemetryScopeRef, **values: Any) -> dict[str, Any]:
        raise AssertionError("single-page flow must not continue")

    def record_ingestion_failure(self, scope: TelemetryScopeRef, **values: Any) -> dict[str, Any]:
        raise AssertionError(f"full product flow unexpectedly failed: {values}")

    def list_analysis_eligible_observations(
        self, scope: TelemetryScopeRef, **filters: Any
    ) -> list[dict[str, Any]]:
        self._assert_scope(scope)
        selected = [
            item
            for item in self.observations
            if item["connection_id"] == filters["connection_id"]
            and item["analysis_eligible"] is True
            and item["quality_state"] == "good"
        ]
        if filters.get("source_run_id") is not None:
            selected = [
                item
                for item in selected
                if item["ingestion_run_id"] == filters["source_run_id"]
            ]
        if filters.get("system_id") is not None:
            selected = [item for item in selected if item["system_id"] == filters["system_id"]]
        if filters.get("asset_filter_applied"):
            selected = [
                item
                for item in selected
                if item.get("asset_id") == filters.get("asset_id")
            ]
        if filters.get("authority_digest") is not None:
            selected = [
                item
                for item in selected
                if item["mapping_authority_digest"] == filters["authority_digest"]
            ]
        if filters.get("window_start") is not None:
            selected = [
                item for item in selected if item["observed_at_utc"] >= filters["window_start"]
            ]
        if filters.get("window_end") is not None:
            selected = [
                item for item in selected if item["observed_at_utc"] < filters["window_end"]
            ]
        return [deepcopy(item) for item in selected[: filters["limit"]]]

    def resolve_analysis_authority_snapshot(
        self,
        scope: TelemetryScopeRef,
        *,
        system_id: str,
        asset_id: str | None,
        authority_digest: str,
    ) -> ServerBoundSystemIdentityV2 | None:
        self._assert_scope(scope)
        if (system_id, asset_id, authority_digest) not in self.authority_snapshots:
            return None
        return resolve_telemetry_analysis_authority(
            scope, system_id, asset_id, authority_digest
        ).identity

    def get_analysis_window(
        self, scope: TelemetryScopeRef, *, window_id: str
    ) -> dict[str, Any] | None:
        self._assert_scope(scope)
        record = self.windows.get(window_id)
        return deepcopy(record) if record is not None else None

    def persist_analysis_window(
        self,
        scope: TelemetryScopeRef,
        *,
        window_record: Mapping[str, Any],
        observation_links: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        self._assert_scope(scope)
        assert all(
            window_record[key] == scope.as_public_dict()[key]
            for key in ("tenant_scope_id", "workspace_id", "resource_scope_id", "facility_id")
        )
        stored = {
            **deepcopy(dict(window_record)),
            "observation_links": deepcopy(observation_links),
        }
        self.windows.setdefault(stored["id"], stored)
        return deepcopy(self.windows[stored["id"]])

    def update_analysis_window_status(
        self, scope: TelemetryScopeRef, **values: Any
    ) -> dict[str, Any]:
        self._assert_scope(scope)
        record = self.windows[values["window_id"]]
        assert record["status"] == values["expected_status"]
        record["status"] = values["target_status"]
        if values.get("reason_code"):
            record.setdefault("quality_summary", {})["status_reason_code"] = values["reason_code"]
        return deepcopy(record)

    def claim_analysis_window_execution(
        self, scope: TelemetryScopeRef, **values: Any
    ) -> dict[str, Any]:
        self._assert_scope(scope)
        record = self.windows[values["window_id"]]
        assert record["status"] == "eligible"
        record.update(
            status="running",
            execution_claim_token=values["claim_token"],
            execution_claim_expires_at=values["claim_expires_at"],
            execution_attempt_count=1,
        )
        return deepcopy(record)

    def recover_stale_analysis_window_execution(
        self, scope: TelemetryScopeRef, **values: Any
    ) -> None:
        self._assert_scope(scope)
        return None

    def finish_analysis_window_execution(
        self, scope: TelemetryScopeRef, **values: Any
    ) -> dict[str, Any]:
        self._assert_scope(scope)
        record = self.windows[values["window_id"]]
        assert record["status"] == "running"
        assert record["execution_claim_token"] == values["claim_token"]
        record.update(
            status=values["target_status"],
            completed_at=values["completed_at"],
            result_digest=values.get("result_digest"),
            result_metadata=deepcopy(values.get("result_metadata") or {}),
            evidence_lineage=deepcopy(values.get("evidence_lineage") or {}),
            result_artifact=values.get("result_artifact"),
        )
        if values.get("reason_code"):
            record.setdefault("quality_summary", {})["status_reason_code"] = values["reason_code"]
        return deepcopy(record)

    def get_ingestion_run(
        self, scope: TelemetryScopeRef, *, run_id: str
    ) -> dict[str, Any] | None:
        self._assert_scope(scope)
        record = self.runs.get(run_id)
        return deepcopy(record) if record is not None else None

    def _canonical_result_row(self, window: Mapping[str, Any]) -> dict[str, Any]:
        artifact = window["result_artifact"]
        run = self.runs[window["source_ingestion_run_id"]]
        return {
            "id": artifact.result_id,
            **self.scope.as_public_dict(),
            "analysis_window_id": window["id"],
            "connection_id": run["connection_id"],
            "source_ingestion_run_id": window["source_ingestion_run_id"],
            "system_id": window["system_id"],
            "asset_id": window["asset_id"],
            "window_start": window["window_start"],
            "window_end": window["window_end"],
            "authority_digest": window["authority_digest"],
            "artifact_schema_version": artifact.artifact_schema_version,
            "execution_contract_version": artifact.execution_contract_version,
            "analysis_schema_version": artifact.analysis_schema_version,
            "analysis_contract_version": artifact.analysis_contract_version,
            "engine_name": artifact.engine_name,
            "engine_version": artifact.engine_version,
            "reference_metadata": dict(artifact.reference_metadata),
            "observation_count": artifact.observation_count,
            "observation_lineage_digest": artifact.observation_lineage_digest,
            "finding_ids": dict(artifact.finding_ids),
            "evidence_ids": dict(artifact.evidence_ids),
            "payload_encoding": artifact.payload_encoding,
            "payload_digest": artifact.payload_digest,
            "payload_uncompressed_bytes": artifact.payload_uncompressed_bytes,
            "payload_stored_bytes": artifact.payload_stored_bytes,
            "serialization_ms": artifact.serialization_ms,
            "payload": artifact.payload,
            "created_at": window["completed_at"],
            "result_metadata": deepcopy(window["result_metadata"]),
        }

    def list_analysis_result_artifacts(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        source_run_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        self._assert_scope(scope)
        rows = []
        for window in self.windows.values():
            row = self._canonical_result_row(window)
            if (
                row["connection_id"] == connection_id
                and row["source_ingestion_run_id"] == source_run_id
            ):
                row.pop("payload")
                rows.append(row)
        return rows[:limit]

    def get_analysis_result_artifact(
        self, scope: TelemetryScopeRef, **identity: Any
    ) -> dict[str, Any] | None:
        self._assert_scope(scope)
        for window in self.windows.values():
            row = self._canonical_result_row(window)
            if all(
                identity[key] == row[column]
                for key, column in {
                    "connection_id": "connection_id",
                    "source_run_id": "source_ingestion_run_id",
                    "system_id": "system_id",
                    "asset_id": "asset_id",
                    "result_id": "id",
                }.items()
            ):
                return row
        return None

    def get_analysis_result_artifact_metadata(
        self, scope: TelemetryScopeRef, **identity: Any
    ) -> dict[str, Any] | None:
        row = self.get_analysis_result_artifact(scope, **identity)
        if row is not None:
            row.pop("payload")
        return row

    def list_analysis_result_lineage_records(
        self, scope: TelemetryScopeRef, **identity: Any
    ) -> list[dict[str, Any]]:
        row = self.get_analysis_result_artifact(scope, **identity)
        if row is None:
            return []
        window = self.windows[row["analysis_window_id"]]
        linked = {
            item["observation_id"] for item in window["observation_links"]
        }
        return [
            deepcopy(item)
            for item in sorted(self.observations, key=lambda item: item["id"])
            if item["id"] in linked
        ]


def test_full_telemetry_product_flow_reaches_one_system_scoped_sii_result() -> None:
    scope = _scope()
    system_record = {
        "system_id": SYSTEM_ID,
        "name": "Central plant chilled water loop",
        "asset_ids": [ASSET_ID],
    }
    equipment_record = {
        "asset_id": ASSET_ID,
        "system_id": SYSTEM_ID,
        "name": "Primary chilled water pump",
    }
    write_facility_context_for_scope(
        {
            "site_id": scope.facility_id,
            "site_name": "Central Plant",
            "timezone": "UTC",
            "systems": [system_record],
            "equipment": [equipment_record],
        },
        scope=scope,
        actor=ACTOR,
    )
    authority_digest = facility_system_authority_digest(system_record)

    def hierarchy_authority(
        requested_scope: TelemetryScopeRef, system_id: str, asset_id: str | None
    ) -> AuthorizedSignalHierarchy:
        resolution = resolve_telemetry_analysis_authority(
            requested_scope, system_id, asset_id, authority_digest
        )
        assert resolution.available
        return AuthorizedSignalHierarchy(
            facility_id=requested_scope.facility_id,
            system_id=system_id,
            asset_id=asset_id,
            authority_digest=authority_digest,
            authority_snapshot={
                "contract_version": "telemetry-analysis-authority-snapshot.v1",
                "facility_id": requested_scope.facility_id,
                "system_id": system_id,
                "asset_id": asset_id,
                "system_record": system_record,
                "asset_record": equipment_record,
            },
        )

    repository = InMemoryProductFlowRepository(scope)
    secret_store = MemoryTelemetrySecretStore(allow_test_backend=True)
    provider = SyntheticReadOnlyConnector(secret_store)
    providers = TelemetryProviderRegistry({ConnectorType.HTTPS_TELEMETRY: provider})
    registry = SignalRegistryService(repository, hierarchy_authority, clock=lambda: NOW)
    health = InMemoryHealthService()
    runtime = TelemetryRuntime(
        repository=repository,
        secret_store=secret_store,
        providers=providers,
        signal_registry=registry,
        health_service=health,
        scheduler=object(),
    )
    connections = TelemetryConnectionService(runtime)

    created = connections.create_connection(
        scope,
        ConnectionCreateRequest(
            name="Central plant telemetry",
            connector_type=ConnectorType.HTTPS_TELEMETRY,
            configuration={
                "base_url": "https://telemetry.customer.example",
                "request_path": "/v1/observations",
                "authentication_scheme": "bearer",
                "timestamp_field": "timestamp",
                "value_field": "value",
                "external_tag_id_field": "tag",
            },
            timezone="UTC",
            polling_interval_seconds=300,
        ),
        actor_id=ACTOR,
    )
    connection_id = created["connection_id"]
    credential_status = connections.put_credentials(
        scope,
        connection_id,
        CredentialPutRequest(values={"bearer_token": "opaque-test-canary"}),
        actor_id=ACTOR,
    )
    validated_connection, validation = connections.validate_connection(
        scope, connection_id, actor_id=ACTOR
    )
    discovery = connections.discover_signals(scope, connection_id)
    discovered = connections.list_signals(
        scope, connection_id, mapping_status=None, limit=20, offset=0
    )

    by_tag = {item["external_tag_id"]: item for item in discovered}
    mapped_pressure = connections.map_signal(
        scope,
        connection_id,
        by_tag["PUMP-A.PRESSURE"]["signal_id"],
        SignalMappingPutRequest(
            system_id=SYSTEM_ID,
            asset_id=ASSET_ID,
            canonical_signal_id=PRESSURE_CONCEPT_ID,
            source_unit="psi",
            source_timezone="UTC",
            expected_cadence_seconds=60,
            provenance="manual",
        ),
        actor_id=ACTOR,
    )
    mapped_flow = connections.map_signal(
        scope,
        connection_id,
        by_tag["PUMP-A.FLOW"]["signal_id"],
        SignalMappingPutRequest(
            system_id=SYSTEM_ID,
            asset_id=ASSET_ID,
            canonical_signal_id=FLOW_CONCEPT_ID,
            source_unit="GPM",
            source_timezone="UTC",
            expected_cadence_seconds=60,
            provenance="manual",
        ),
        actor_id=ACTOR,
    )
    mapped_power = connections.map_signal(
        scope,
        connection_id,
        by_tag["PUMP-A.POWER"]["signal_id"],
        SignalMappingPutRequest(
            system_id=SYSTEM_ID,
            asset_id=ASSET_ID,
            canonical_signal_id=POWER_CONCEPT_ID,
            source_unit="kW",
            source_timezone="UTC",
            expected_cadence_seconds=60,
            provenance="manual",
        ),
        actor_id=ACTOR,
    )
    enabled = connections.set_enabled(scope, connection_id, enabled=True, actor_id=ACTOR)

    sii_calls: list[dict[str, Any]] = []

    def evaluate_sii(**kwargs: Any) -> dict[str, Any]:
        engine_kwargs = {
            **kwargs,
            "sensor_health": {
                "signals": [
                    {"signal": signal_id, "health": "healthy", "conditions": []}
                    for signal_id in kwargs["config"]["numeric_columns"]
                ],
                "source_conditions": [],
                "population_rows": 120,
                "assessed_rows": 120,
                "sampled_for_signal_health": False,
                "assessment_method": "deterministic_acceptance_fixture",
            },
            "operating_mode": {
                "match": "strong",
                "baseline_mode": "mid_load",
                "recent_mode": "mid_load",
                "baseline_mode_label": "Mid load",
                "recent_mode_label": "Mid load",
                "confidence": "high",
                "reasons": ["The deterministic acceptance windows share one mode."],
            },
        }
        sii_calls.append(engine_kwargs)
        return authoritative_evaluate_sii(**engine_kwargs)

    analysis_results: list[Any] = []

    def analyze_run(**kwargs: Any) -> Any:
        result = process_ingestion_run(**kwargs, evaluator=evaluate_sii)
        analysis_results.append(result)
        return result

    scheduler = TelemetryScheduler(
        repository=repository,
        providers=providers,
        normalize_page=prepare_connector_page,
        analyze_run=analyze_run,
        worker_id="test-telemetry-worker",
        now=lambda: NOW,
        jitter=lambda: 0.5,
        heartbeat=lambda **kwargs: True,
    )
    scheduled = scheduler.run_once()

    assert credential_status == {
        "credentials_configured": True,
        "credential_version": "1",
        "credentials_updated_at": credential_status["credentials_updated_at"],
    }
    assert "opaque-test-canary" not in repr(credential_status)
    assert "opaque-test-canary" not in repr(repository.connections)
    assert "opaque-test-canary" not in repr(repository.bindings)
    assert "opaque-test-canary" not in repr(repository.audit)
    assert provider.received_valid_binding is True
    assert validation == {
        "valid": True,
        "reachable": True,
        "authenticated": True,
        "observations_sampled": 1,
        "code": "validated",
    }
    assert validated_connection["resource_scope_id"] == scope.resource_scope_id
    assert discovery["discovered_count"] == discovery["registered_count"] == 4
    assert {
        mapped_pressure["system_id"],
        mapped_flow["system_id"],
        mapped_power["system_id"],
    } == {SYSTEM_ID}
    assert {
        mapped_pressure["asset_id"],
        mapped_flow["asset_id"],
        mapped_power["asset_id"],
    } == {ASSET_ID}
    assert {
        mapped_pressure["provenance"],
        mapped_flow["provenance"],
        mapped_power["provenance"],
    } == {"manual"}
    assert by_tag["PUMP-A.VIBRATION"]["mapping_status"] == "unmapped"
    assert enabled["enabled"] is True

    assert scheduled.outcome == "processed"
    assert scheduled.analysis_status == "completed"
    assert provider.fetch_count == 1
    assert len(repository.observations) == 360
    assert len(repository.rejections) == 120
    assert {item["reason_code"] for item in repository.rejections} == {"mapping_not_approved"}
    assert all(item["external_tag_id"] != "PUMP-A.VIBRATION" for item in repository.observations)
    assert all(item["tenant_scope_id"] == scope.tenant_scope_id for item in repository.observations)
    assert all(item["facility_id"] == scope.facility_id for item in repository.observations)
    assert all(item["system_id"] == SYSTEM_ID for item in repository.observations)
    assert all(item["asset_id"] == ASSET_ID for item in repository.observations)
    assert {item["canonical_unit"] for item in repository.observations} == {"kPa", "L/s", "kW"}
    assert {item["original_unit"] for item in repository.observations} == {"psi", "GPM", "kW"}
    assert all(item["source_timezone"] == "UTC" for item in repository.observations)
    assert all(item["observed_at_utc"].tzinfo is UTC for item in repository.observations)

    assert len(sii_calls) == 1
    assert set(sii_calls[0]["config"]["numeric_columns"]) == {
        PRESSURE_CONCEPT_ID,
        FLOW_CONCEPT_ID,
        POWER_CONCEPT_ID,
    }
    assert "PUMP-A.VIBRATION" not in repr(sii_calls[0])
    assert sii_calls[0]["config"]["infrastructure_identity"] == {
        "tenant_id": scope.tenant_scope_id,
        "workspace_id": scope.workspace_id,
        "resource_scope_id": scope.resource_scope_id,
        "facility_id": scope.facility_id,
        "system_id": SYSTEM_ID,
        "asset_id": ASSET_ID,
    }

    assert len(analysis_results) == 1
    analysis = analysis_results[0]
    assert analysis.status == "completed"
    assert len(analysis.windows) == 1
    execution = analysis.windows[0].execution
    assert execution is not None
    assert execution.source_kind == "telemetry_connector"
    transport = project_result_for_transport(
        {
            "sii_result": dict(execution.sii_result),
            "analysis_result": dict(execution.analysis_result),
        }
    )
    assert transport is not None
    assert transport["analysis_result"]["sii_evidence"]["status"] == "complete"

    durable_window = repository.windows[analysis.windows[0].window_id]
    assert durable_window["status"] == "completed"
    assert durable_window["tenant_scope_id"] == scope.tenant_scope_id
    assert durable_window["facility_id"] == scope.facility_id
    assert durable_window["system_id"] == SYSTEM_ID
    assert durable_window["asset_id"] == ASSET_ID
    assert durable_window["source_ingestion_run_id"] == scheduled.run_id
    assert durable_window["execution_attempt_count"] == 1
    assert durable_window["result_metadata"]["finding_id_count"] >= 1
    assert durable_window["result_metadata"]["evidence_id_count"] >= 1
    assert durable_window["evidence_lineage"]["finding_ids"]
    assert durable_window["evidence_lineage"]["evidence_ids"]
    assert durable_window["evidence_lineage"]["contributing_ingestion_run_ids"] == [
        scheduled.run_id
    ]
    canonical_artifact = durable_window["result_artifact"]
    assert analysis.windows[0].result_id == canonical_artifact.result_id
    assert analysis.windows[0].artifact_digest == canonical_artifact.payload_digest
    linked_observation_ids = {
        item["observation_id"] for item in durable_window["observation_links"]
    }
    assert linked_observation_ids == {item["id"] for item in repository.observations}
    assert all(
        item["resource_scope_id"] == scope.resource_scope_id
        for item in durable_window["observation_links"]
    )
    assert repository.scope_checks > 20
    assert {item["action"] for item in repository.audit} >= {
        "connection_created",
        "credential_binding_changed",
        "validation_completed",
    }

    # Binding restart acceptance: discard every live analysis object, recreate
    # the retrieval service, and load only the durable canonical bytes/joins.
    persisted_result_id = canonical_artifact.result_id
    persisted_digest = canonical_artifact.payload_digest
    analysis_results.clear()
    execution = None
    sii_call_count = len(sii_calls)
    restarted_runtime = TelemetryRuntime(
        repository=repository,
        secret_store=secret_store,
        providers=providers,
        signal_registry=registry,
        health_service=health,
        scheduler=object(),
    )
    restarted_results = TelemetryCanonicalResultService(restarted_runtime)
    listed_results = restarted_results.list_results(
        scope,
        connection_id=connection_id,
        source_run_id=scheduled.run_id,
    )
    retrieved_result = restarted_results.get_result(
        scope,
        connection_id=connection_id,
        source_run_id=scheduled.run_id,
        system_id=SYSTEM_ID,
        asset_id=ASSET_ID,
        result_id=persisted_result_id,
    )
    retrieved_lineage = restarted_results.get_lineage_page(
        scope,
        connection_id=connection_id,
        source_run_id=scheduled.run_id,
        system_id=SYSTEM_ID,
        asset_id=ASSET_ID,
        result_id=persisted_result_id,
        limit=100,
        cursor=None,
    )

    assert len(sii_calls) == sii_call_count
    assert listed_results[0]["result_id"] == persisted_result_id
    assert retrieved_result["result_id"] == persisted_result_id
    assert retrieved_result["payload_digest"] == persisted_digest
    assert retrieved_result["lineage_verified"] is True
    assert retrieved_result["product_result"]["result_id"] == persisted_result_id
    assert retrieved_result["product_result"]["payload_digest"] == persisted_digest
    assert retrieved_result["product_result"]["analysis_window_id"] == durable_window["id"]
    assert retrieved_result["product_result"]["source_run_id"] == scheduled.run_id
    assert retrieved_lineage["result_id"] == persisted_result_id
    assert retrieved_lineage["observation_lineage_digest"] == (
        canonical_artifact.observation_lineage_digest
    )
    lineage_records = list(retrieved_lineage["records"])
    lineage_cursor = retrieved_lineage["next_cursor"]
    while lineage_cursor:
        lineage_page = restarted_results.get_lineage_page(
            scope,
            connection_id=connection_id,
            source_run_id=scheduled.run_id,
            system_id=SYSTEM_ID,
            asset_id=ASSET_ID,
            result_id=persisted_result_id,
            limit=100,
            cursor=lineage_cursor,
        )
        assert lineage_page["observation_lineage_digest"] == (
            canonical_artifact.observation_lineage_digest
        )
        lineage_records.extend(lineage_page["records"])
        lineage_cursor = lineage_page["next_cursor"]
    assert {item["observation_id"] for item in lineage_records} == linked_observation_ids

    # Cross-layer acceptance: feed the exact post-restart durable response to
    # the production frontend model and progressive-disclosure projectors.
    # This subprocess receives no Python analysis objects and cannot invoke SII.
    frontend_assertion = (
        Path(__file__).parents[1]
        / "frontend"
        / "scripts"
        / "assert-canonical-result-routing.mjs"
    )
    frontend_loader = frontend_assertion.with_name("extension-loader.mjs")
    projected = subprocess.run(
        [
            "node",
            "--no-warnings",
            "--experimental-loader",
            str(frontend_loader),
            str(frontend_assertion),
        ],
        cwd=frontend_assertion.parents[1],
        input=json.dumps(retrieved_result, default=str),
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert projected.returncode == 0, projected.stderr
    routing_proof = json.loads(projected.stdout)
    assert routing_proof["result_id"] == persisted_result_id
    assert routing_proof["payload_digest"] == persisted_digest
    assert routing_proof["observation_lineage_digest"] == (
        canonical_artifact.observation_lineage_digest
    )
    assert routing_proof["finding_id"] in durable_window["evidence_lineage"][
        "finding_ids"
    ]
    assert routing_proof["depths"] == [
        "results",
        "review",
        "investigation",
        "evidence",
    ]
    assert len(sii_calls) == sii_call_count
