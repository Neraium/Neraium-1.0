from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote
import uuid

from fastapi import Request
from fastapi.testclient import TestClient

from app.connectors.base import (
    ConnectorFailureKind,
    ConnectorPage,
    ConnectorProviderDescriptor,
    ConnectorValidationResult,
    DiscoveredSignal,
    ProviderHealthResult,
    TelemetryConnector,
    TelemetryConnectorError,
)
from app.core.config import Settings
from app.core.security import require_api_access
from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.main import create_app
from app.services.dataset_scope import build_dataset_scope
from app.services.phase4_scope import set_current_authenticated_phase4_scope
from app.services.telemetry_domain import ConnectorCapability, ConnectorType
from app.services.telemetry_runtime import (
    TelemetryProviderRegistry,
    TelemetryRuntime,
    TelemetryRuntimeUnavailable,
)
from app.services.telemetry_secrets import MemoryTelemetrySecretStore
from app.services.workspace_authorization import WorkspaceContext, set_current_workspace_context


class FakeProvider(TelemetryConnector):
    def __init__(self):
        self.validation_calls = 0
        self.validation_error: TelemetryConnectorError | None = None

    @classmethod
    def descriptor(cls):
        return ConnectorProviderDescriptor(
            connector_type=ConnectorType.HTTPS_TELEMETRY,
            display_name="HTTPS telemetry API",
            description="test retrieval provider",
            capabilities=frozenset({
                ConnectorCapability.VALIDATE,
                ConnectorCapability.HEALTH_CHECK,
                ConnectorCapability.BOUNDED_BACKFILL,
            }),
            production_available=True,
        )

    def validate(self, context):
        self.validation_calls += 1
        if self.validation_error is not None:
            raise self.validation_error
        return ConnectorValidationResult(True, True, True, 1, "validated")

    def discover_signals(self, context, *, checkpoint=None):
        return ConnectorPage(
            signals=(DiscoveredSignal("tag-1", "Pump power", reported_unit="kW"),)
        )

    def fetch_incremental(self, context, *, checkpoint=None):
        return ConnectorPage()

    def fetch_backfill(self, context, *, time_range, checkpoint=None):
        return ConnectorPage()

    def health(self, context):
        return ProviderHealthResult(True, True, True, datetime.now(UTC), "healthy")


class FakeRepository:
    def __init__(self):
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.bindings: dict[tuple[str, str], Any] = {}
        self.runs: dict[tuple[str, str], dict[str, Any]] = {}
        self.errors: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []

    def verify_readiness(self):
        return True

    @staticmethod
    def _key(scope, connection_id):
        return scope.resource_scope_id, str(connection_id)

    def create_connection(self, scope, *, connection_id, name, connector_type, safe_config, timezone_name, polling_interval_seconds, actor_id, audit_event_id=None, audit_safe_detail=None):
        now = datetime.now(UTC)
        record = {
            "id": connection_id,
            "tenant_scope_id": scope.tenant_scope_id,
            "workspace_id": scope.workspace_id,
            "resource_scope_id": scope.resource_scope_id,
            "facility_id": scope.facility_id,
            "name": name,
            "connector_type": str(connector_type),
            "lifecycle_status": "draft",
            "enabled": False,
            "safe_config": deepcopy(safe_config),
            "timezone": timezone_name,
            "polling_interval_seconds": polling_interval_seconds,
            "credentials_configured": False,
            "created_at": now,
            "updated_at": now,
        }
        self.records[self._key(scope, connection_id)] = record
        if audit_event_id is not None:
            self.audit.append({
                "event_id": audit_event_id,
                "connection_id": connection_id,
                "actor_id": actor_id,
                "action": "connection_created",
                "safe_detail": deepcopy(audit_safe_detail or {}),
            })
        return deepcopy(record)

    def get_connection(self, scope, connection_id):
        record = self.records.get(self._key(scope, connection_id))
        return deepcopy(record) if record else None

    def list_connections(self, scope, **kwargs):
        return [deepcopy(record) for (resource, _), record in self.records.items() if resource == scope.resource_scope_id and record.get("archived_at") is None]

    def get_connection_health(self, scope, *, connection_id):
        return None

    def update_connection_metadata(self, scope, *, connection_id, actor_id, name=None, safe_config=None, timezone_name=None, polling_interval_seconds=None):
        record = self.records[self._key(scope, connection_id)]
        if name is not None:
            record["name"] = name
        if safe_config is not None:
            record["safe_config"] = deepcopy(safe_config)
        if timezone_name is not None:
            record["timezone"] = timezone_name
        if polling_interval_seconds is not None:
            record["polling_interval_seconds"] = polling_interval_seconds
        return deepcopy(record)

    def set_connection_lifecycle(self, scope, *, connection_id, target_status, actor_id, enabled=None, **timestamps):
        record = self.records[self._key(scope, connection_id)]
        record["lifecycle_status"] = str(target_status)
        if enabled is not None:
            record["enabled"] = enabled
        record.update({key: value for key, value in timestamps.items() if value is not None})
        return deepcopy(record)

    def archive_connection(self, scope, *, connection_id, actor_id):
        record = self.records[self._key(scope, connection_id)]
        if record["lifecycle_status"] == "draft":
            raise ValueError("invalid_connection_lifecycle_transition:draft:archived")
        record.update(lifecycle_status="archived", enabled=False, archived_at=datetime.now(UTC))
        return deepcopy(record)

    def schedule_connection_now(self, scope, *, connection_id, requested_at):
        record = self.records.get(self._key(scope, connection_id))
        if record is None or record.get("archived_at") is not None:
            return False
        record["next_attempt_at"] = requested_at
        return True

    def create_backfill_run(self, scope, *, run_id, connection_id, range_start, range_end, actor_id, requested_at):
        from app.services.telemetry_repository import TelemetryRepositoryError

        active = any(
            run["connection_id"] == connection_id
            and run["mode"] == "backfill"
            and run["status"] in {"pending", "running"}
            for (resource, _), run in self.runs.items()
            if resource == scope.resource_scope_id
        )
        if active:
            raise TelemetryRepositoryError("telemetry_backfill_already_active")
        record = {
            "id": run_id,
            "connection_id": connection_id,
            "mode": "backfill",
            "status": "pending",
            "range_start": range_start,
            "range_end": range_end,
            "started_at": requested_at,
            "actor_id": actor_id,
        }
        self.runs[(scope.resource_scope_id, run_id)] = record
        self.records[self._key(scope, connection_id)]["next_attempt_at"] = requested_at
        self.audit.append({"action": "backfill_started", "actor_id": actor_id})
        return deepcopy(record)

    def list_ingestion_runs(self, scope, *, connection_id, limit, offset):
        records = [
            deepcopy(run)
            for (resource, _), run in self.runs.items()
            if resource == scope.resource_scope_id and run["connection_id"] == connection_id
        ]
        records.sort(key=lambda run: run["started_at"], reverse=True)
        return records[offset:offset + limit]

    def list_ingestion_errors(self, scope, *, connection_id, limit, offset):
        return [
            deepcopy(error)
            for error in self.errors
            if error["resource_scope_id"] == scope.resource_scope_id
            and error["connection_id"] == connection_id
        ][offset:offset + limit]

    def get_ingestion_run(self, scope, *, run_id):
        run = self.runs.get((scope.resource_scope_id, run_id))
        return deepcopy(run) if run is not None else None

    def retry_ingestion_run(self, scope, *, run_id, new_run_id, actor_id, requested_at):
        from app.services.telemetry_repository import TelemetryRepositoryError

        source = self.runs.get((scope.resource_scope_id, run_id))
        if source is None or source["status"] not in {"failed", "partial"}:
            raise ValueError("telemetry_ingestion_run_not_retryable")
        if any(
            resource == scope.resource_scope_id
            and run["connection_id"] == source["connection_id"]
            and run["mode"] == "retry"
            and run["status"] in {"pending", "running"}
            for (resource, _), run in self.runs.items()
        ):
            raise TelemetryRepositoryError("telemetry_retry_already_active")
        record = {
            **source,
            "id": new_run_id,
            "mode": "retry",
            "status": "pending",
            "started_at": requested_at,
            "finished_at": None,
            "error_code": None,
            "error_summary": None,
            "actor_id": actor_id,
            "retry_count": int(source.get("retry_count") or 0) + 1,
        }
        self.runs[(scope.resource_scope_id, new_run_id)] = record
        self.records[self._key(scope, source["connection_id"])]["next_attempt_at"] = requested_at
        return deepcopy(record)

    def record_audit_event(self, scope, **event):
        self.audit.append(deepcopy(event))

    def load_secret_binding(self, scope, *, connection_id):
        return self.bindings.get(self._key(scope, connection_id))

    def upsert_secret_binding(self, scope, *, connection_id, binding_id, provider, internal_reference, version_marker, actor_id=None, audit_event_id=None, audit_safe_detail=None):
        from app.services.telemetry_secrets import SecretBinding

        binding = SecretBinding.from_internal_persistence(
            binding_id=binding_id,
            provider=provider,
            resource_scope_id=scope.resource_scope_id,
            connection_id=connection_id,
            internal_reference=internal_reference,
            version_marker=version_marker,
        )
        self.bindings[self._key(scope, connection_id)] = binding
        self.records[self._key(scope, connection_id)]["credentials_configured"] = True
        if audit_event_id is not None:
            self.audit.append({
                "event_id": audit_event_id,
                "connection_id": connection_id,
                "actor_id": actor_id,
                "action": "credential_binding_changed",
                "safe_detail": deepcopy(audit_safe_detail or {}),
            })
        return {"credentials_configured": True}

    def list_canonical_signal_concepts(self):
        return [{
            "id": "b0bea7a6-5cce-5cf4-971b-bfcfeb47389c",
            "canonical_name": "power",
            "display_name": "Power",
            "physical_dimension": "power",
            "canonical_unit": "kW",
            "taxonomy_version": 1,
        }]


class FakeSignalRegistry:
    def __init__(self):
        self.signals: dict[tuple[str, str], dict[str, Any]] = {}

    def register_discovered_signals(self, scope, *, connection_id, signals):
        registered = []
        for raw in signals:
            signal_id = uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{scope.resource_scope_id}\0{connection_id}\0{raw['external_tag_id']}",
            )
            record = {
                "id": signal_id,
                "connection_id": uuid.UUID(connection_id),
                **raw,
                "sample_cadence_seconds": None,
                "enabled": False,
                "mapping_status": "unmapped",
                "last_observed_at": None,
                "quality_state": "mapping_required",
            }
            self.signals[(connection_id, str(signal_id))] = record
            registered.append(deepcopy(record))
        return registered

    def list_signals(self, scope, *, connection_id, mapping_status, limit, offset):
        records = [
            deepcopy(record)
            for (candidate, _), record in self.signals.items()
            if candidate == connection_id
        ]
        return records[offset:offset + limit]

    def get_signal(self, scope, *, connection_id, signal_id):
        return deepcopy(self.signals.get((connection_id, signal_id)))

    def map_signal(self, scope, *, connection_id, signal_id, canonical_concept_id, **kwargs):
        record = self.signals[(connection_id, signal_id)]
        record.update(
            mapping_status="mapped",
            enabled=True,
            mapping_id=uuid.uuid4(),
            canonical_signal_id=uuid.UUID(canonical_concept_id),
            canonical_signal_name="power",
            canonical_unit="kW",
            conversion_id="kw_to_kw",
            conversion_version="v1",
            mapping_revision=1,
            **{key: kwargs.get(key) for key in (
                "system_id", "asset_id", "source_timezone",
                "expected_cadence_seconds", "provenance",
            )},
        )
        return deepcopy(record)


class FakeHealthService:
    def __init__(self, repository):
        self.repository = repository
        self.refreshes: list[str] = []

    def get_health(self, scope, *, connection_id):
        return self.repository.get_connection_health(scope, connection_id=connection_id)

    def evaluate_and_persist(self, scope, *, connection_id, **probes):
        self.refreshes.append(connection_id)
        return {"aggregate_status": "unknown"}


def _context(tenant: str, workspace_id: str) -> tuple[WorkspaceContext, AuthenticatedPhase4Scope]:
    phase = AuthenticatedPhase4Scope(tenant_scope_id=tenant, workspace_id=workspace_id)
    workspace = WorkspaceContext(
        workspace_id=workspace_id,
        display_name="Synthetic facility",
        kind="facility",
        membership_active=True,
        dataset_scope=build_dataset_scope(tenant_id=tenant, user_id="authority", workspace_id=workspace_id),
    )
    return workspace, phase


def build_client(tmp_path):
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    app = create_app(settings)
    repository = FakeRepository()
    secrets = MemoryTelemetrySecretStore(allow_test_backend=True)
    registry = FakeSignalRegistry()
    health = FakeHealthService(repository)
    app.state.telemetry_runtime = TelemetryRuntime(
        repository=repository,
        secret_store=secrets,
        providers=TelemetryProviderRegistry({ConnectorType.HTTPS_TELEMETRY: FakeProvider()}),
        signal_registry=registry,
        health_service=health,
        scheduler=object(),
    )

    async def test_auth(request: Request):
        tenant = request.headers.get("X-Test-Tenant", "tenant-a")
        workspace_id = request.headers.get("X-Test-Workspace", "ws-facility-a")
        role = request.headers.get("X-Test-Role", "admin")
        workspace, phase = _context(tenant, workspace_id)
        request.state.auth_context = {
            "authenticated": True,
            "auth_subject": f"{role}@example.com",
            "auth_role": role,
        }
        set_current_workspace_context(workspace)
        set_current_authenticated_phase4_scope(phase)

    app.dependency_overrides[require_api_access] = test_auth
    return app, repository


def _connection_payload():
    return {
        "name": "Synthetic telemetry source",
        "connector_type": "https_telemetry",
        "configuration": {
            "base_url": "https://telemetry.example.test",
            "request_path": "/observations",
            "timestamp_field": "timestamp",
            "value_field": "value",
            "external_tag_id_field": "tag",
        },
        "timezone": "UTC",
        "polling_interval_seconds": 300,
    }


def test_production_api_is_scoped_and_enforces_lookup_before_roles(tmp_path):
    app, _repository = build_client(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        created = client.post("/api/data-connections", json=_connection_payload())
        assert created.status_code == 201, created.text
        connection_id = created.json()["connection"]["connection_id"]

        viewer = {"X-Test-Role": "viewer"}
        assert client.get("/api/data-connections", headers=viewer).status_code == 200
        assert client.patch(
            f"/api/data-connections/{connection_id}", headers=viewer, json={"name": "Denied"}
        ).status_code == 403

        foreign = {"X-Test-Role": "viewer", "X-Test-Tenant": "tenant-b", "X-Test-Workspace": "ws-facility-b"}
        missing = str(uuid.uuid4())
        cross = client.patch(f"/api/data-connections/{connection_id}", headers=foreign, json={"name": "Denied"})
        absent = client.patch(f"/api/data-connections/{missing}", headers=foreign, json={"name": "Denied"})
        assert cross.status_code == absent.status_code == 404
        assert cross.json() == absent.json()


def test_credentials_are_one_way_and_canary_never_reaches_response_log_or_audit(tmp_path, caplog):
    app, repository = build_client(tmp_path)
    canary = "SECRET-CANARY-never-return"
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post("/api/data-connections", json=_connection_payload()).json()["connection"]["connection_id"]
        stored = client.put(
            f"/api/data-connections/{connection_id}/credentials",
            json={"values": {"access_token": canary}},
        )
        assert stored.status_code == 200, stored.text
        assert canary not in stored.text
        listed = client.get("/api/data-connections")
        assert canary not in listed.text
        assert canary not in repr(repository.audit)
        assert canary not in caplog.text
        assert "internal_reference" not in stored.text


def test_secret_write_database_failure_is_sanitized_and_requests_reconciliation(
    tmp_path, caplog, monkeypatch
):
    app, repository = build_client(tmp_path)
    canary = "SECRET-CANARY-database-failure"

    def fail_binding_write(*_args, **_kwargs):
        raise RuntimeError(f"database unavailable after {canary}")

    monkeypatch.setattr(repository, "upsert_secret_binding", fail_binding_write)
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        response = client.put(
            f"/api/data-connections/{connection_id}/credentials",
            json={"values": {"access_token": canary}},
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "telemetry_repository_unavailable"
    assert "telemetry_secret_binding_reconciliation_required" in caplog.text
    assert any(getattr(record, "error_type", None) == "RuntimeError" for record in caplog.records)
    assert canary not in response.text
    assert canary not in caplog.text
    assert canary not in repr(repository.audit)


def test_operator_validate_viewer_denied_and_catalog_is_read_only(tmp_path):
    app, _repository = build_client(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post("/api/data-connections", json=_connection_payload()).json()["connection"]["connection_id"]
        viewer = client.post(f"/api/data-connections/{connection_id}/validate", headers={"X-Test-Role": "viewer"})
        operator = client.post(f"/api/data-connections/{connection_id}/validate", headers={"X-Test-Role": "operator"})
        catalog = client.get("/api/data-connections/signal-concepts", headers={"X-Test-Role": "viewer"})
        assert viewer.status_code == 403
        assert operator.status_code == 200, operator.text
        assert operator.json()["valid"] is True
        assert operator.json()["connection"]["lifecycle_status"] == "disconnected"
        assert operator.json()["connection"]["last_healthy_at"] is None
        assert catalog.status_code == 200
        assert catalog.json()["concepts"][0]["canonical_name"] == "power"


def test_production_legacy_reset_is_tombstoned_and_unsafe_urls_are_rejected(tmp_path):
    app, _repository = build_client(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        reset = client.post("/api/data-connections/reset-all")
        assert reset.status_code == 410
        assert reset.json()["code"] == "legacy_connection_operation_retired"

        payload = _connection_payload()
        payload["configuration"]["base_url"] = "https://telemetry.example.test/private?token=secret"
        unsafe = client.post("/api/data-connections", json=payload)
        assert unsafe.status_code == 422
        assert "secret" not in unsafe.text.lower()


def test_settings_repr_redacts_telemetry_database_url(tmp_path):
    settings = Settings(
        app_env="test",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://localhost:3010"],
        runtime_dir=tmp_path,
        telemetry_database_url="postgresql://user:canary-password@db.example.test/neraium",
    )
    assert "canary-password" not in repr(settings)


def test_production_runtime_rejects_non_tls_telemetry_database_url(tmp_path):
    from app.services.telemetry_runtime import build_telemetry_runtime

    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
        telemetry_database_url="postgresql://user:canary-password@db.example.test/neraium",
    )
    runtime = build_telemetry_runtime(settings)
    assert runtime.available is False
    assert runtime.unavailable_code == "telemetry_runtime_configuration_invalid"


def test_production_startup_never_seeds_or_starts_legacy_connection_runtime(monkeypatch, tmp_path):
    import app.main as main_module

    monkeypatch.setattr(
        main_module,
        "ensure_default_data_connection",
        lambda settings: (_ for _ in ()).throw(AssertionError("legacy seed called")),
    )
    monkeypatch.setattr(
        main_module,
        "start_data_connection_poller",
        lambda: (_ for _ in ()).throw(AssertionError("legacy poller called")),
    )
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
        start_data_connection_poller=True,
        telemetry_legacy_compat_enabled=True,
    )
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        assert client.post("/api/data-connections/reset-all").status_code in {401, 410}


def test_historian_configuration_accepts_only_server_owned_selection_and_bounded_parameters():
    from pydantic import ValidationError
    from app.models.telemetry_api_models import ConnectionCreateRequest

    safe = ConnectionCreateRequest.model_validate({
        "name": "Synthetic historian",
        "connector_type": "historian_template",
        "configuration": {
            "template_id": "approved-template",
            "network_profile_id": "approved-network",
            "parameters": {"lookback_hours": 24},
        },
    })
    assert safe.configuration["network_profile_id"] == "approved-network"
    for forbidden in (
        {"dsn": "postgresql://secret"},
        {"profile_id": "browser-alias"},
        {"parameters": {"raw_sql": "select * from telemetry"}},
    ):
        candidate = {
            "template_id": "approved-template",
            "network_profile_id": "approved-network",
            **forbidden,
        }
        try:
            ConnectionCreateRequest.model_validate({
                "name": "Rejected historian",
                "connector_type": "historian_template",
                "configuration": candidate,
            })
        except ValidationError:
            continue
        raise AssertionError(f"unsafe historian configuration accepted: {forbidden!r}")


def test_postgresql_shaped_catalog_and_mapped_signal_serialize_without_drift(tmp_path):
    app, _repository = build_client(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        catalog = client.get("/api/data-connections/signal-concepts")
        assert catalog.status_code == 200, catalog.text
        concept = catalog.json()["concepts"][0]
        assert concept["taxonomy_version"] == 1

        discovered = client.post(
            f"/api/data-connections/{connection_id}/discover",
            headers={"X-Test-Role": "operator"},
        )
        assert discovered.status_code == 200, discovered.text
        signal = client.get(
            f"/api/data-connections/{connection_id}/signals"
        ).json()["signals"][0]
        mapped = client.put(
            f"/api/data-connections/{connection_id}/signals/{signal['signal_id']}/mapping",
            headers={"X-Test-Role": "operator"},
            json={
                "system_id": "system-a",
                "canonical_signal_id": concept["canonical_signal_id"],
                "source_unit": "kW",
            },
        )
        assert mapped.status_code == 200, mapped.text
        assert mapped.json()["signal"]["canonical_signal_id"] == concept["canonical_signal_id"]


def test_credentials_pin_https_origin_and_authentication_scheme(tmp_path):
    app, _repository = build_client(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        payload = _connection_payload()
        payload["configuration"]["authentication_scheme"] = "bearer"
        connection_id = client.post(
            "/api/data-connections", json=payload
        ).json()["connection"]["connection_id"]
        assert client.put(
            f"/api/data-connections/{connection_id}/credentials",
            json={"values": {"access_token": "canary"}},
        ).status_code == 200

        safe_edit = deepcopy(payload["configuration"])
        safe_edit["request_path"] = "/v2/observations"
        assert client.patch(
            f"/api/data-connections/{connection_id}",
            json={"configuration": safe_edit},
        ).status_code == 200

        for key, value in (
            ("base_url", "https://other.example.test"),
            ("authentication_scheme", "api_key"),
        ):
            unsafe = deepcopy(safe_edit)
            unsafe[key] = value
            response = client.patch(
                f"/api/data-connections/{connection_id}",
                json={"configuration": unsafe},
            )
            assert response.status_code == 409, response.text
            assert response.json()["detail"]["code"] == "telemetry_credential_context_change_forbidden"


def test_archived_connection_is_opaque_and_draft_archive_is_stable_conflict(tmp_path):
    app, _repository = build_client(tmp_path)
    provider = app.state.telemetry_runtime.providers.known(
        ConnectorType.HTTPS_TELEMETRY
    )
    with TestClient(app, base_url="https://testserver") as client:
        draft_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        draft_archive = client.delete(f"/api/data-connections/{draft_id}")
        assert draft_archive.status_code == 409, draft_archive.text
        assert draft_archive.json()["detail"]["code"] == "telemetry_lifecycle_conflict"

        assert client.post(
            f"/api/data-connections/{draft_id}/validate",
            headers={"X-Test-Role": "operator"},
        ).status_code == 200
        assert client.delete(f"/api/data-connections/{draft_id}").status_code == 200
        validation_calls = provider.validation_calls
        for response in (
            client.get(f"/api/data-connections/{draft_id}"),
            client.patch(f"/api/data-connections/{draft_id}", json={"name": "hidden"}),
            client.put(
                f"/api/data-connections/{draft_id}/credentials",
                json={"values": {"access_token": "not-stored"}},
            ),
            client.post(
                f"/api/data-connections/{draft_id}/validate",
                headers={"X-Test-Role": "operator"},
            ),
        ):
            assert response.status_code == 404, response.text
            assert response.json()["detail"]["code"] == "telemetry_resource_not_found"
        assert provider.validation_calls == validation_calls


def test_runtime_requires_registry_and_health_and_refreshes_after_mutations(tmp_path):
    incomplete = TelemetryRuntime(
        repository=object(),
        secret_store=object(),
        providers=TelemetryProviderRegistry({ConnectorType.HTTPS_TELEMETRY: FakeProvider()}),
    )
    assert incomplete.available is False
    try:
        incomplete.require_available()
    except TelemetryRuntimeUnavailable:
        pass
    else:
        raise AssertionError("runtime accepted missing signal registry and health service")

    app, _repository = build_client(tmp_path)
    health = app.state.telemetry_runtime.health_service
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        assert client.post(
            f"/api/data-connections/{connection_id}/validate",
            headers={"X-Test-Role": "operator"},
        ).status_code == 200
        assert client.post(
            f"/api/data-connections/{connection_id}/discover",
            headers={"X-Test-Role": "operator"},
        ).status_code == 200
        assert client.post(f"/api/data-connections/{connection_id}/enable").status_code == 200
        assert client.post(f"/api/data-connections/{connection_id}/disable").status_code == 200
    assert health.refreshes.count(connection_id) >= 4


def test_staging_hard_disables_legacy_compatibility(tmp_path):
    settings = Settings(
        app_env="staging",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://staging.neraium.com"],
        runtime_dir=tmp_path,
        telemetry_legacy_compat_enabled=True,
    )
    assert settings.telemetry_legacy_compat_enabled is False


def test_historian_registry_is_available_only_for_configured_server_template():
    class ConfiguredTemplates:
        @staticmethod
        def configured_template_ids():
            return ("approved-template",)

    class ManagedHistorian(FakeProvider):
        def __init__(self):
            super().__init__()
            self._provider_registry = ConfiguredTemplates()

        @classmethod
        def descriptor(cls):
            return ConnectorProviderDescriptor(
                connector_type=ConnectorType.HISTORIAN_TEMPLATE,
                display_name="Managed historian",
                description="server-owned test template",
                capabilities=frozenset(
                    {ConnectorCapability.VALIDATE, ConnectorCapability.HEALTH_CHECK}
                ),
                production_available=False,
            )

    providers = TelemetryProviderRegistry(
        {ConnectorType.HISTORIAN_TEMPLATE: ManagedHistorian()}
    )
    assert providers.get(
        ConnectorType.HISTORIAN_TEMPLATE,
        configuration={"template_id": "approved-template"},
    )
    for configuration in ({}, {"template_id": "browser-invented"}):
        try:
            providers.get(
                ConnectorType.HISTORIAN_TEMPLATE,
                configuration=configuration,
            )
        except TelemetryRuntimeUnavailable as error:
            assert error.code == "telemetry_connector_not_available"
        else:
            raise AssertionError("unconfigured historian template became available")


def test_shared_environment_https_requires_controlled_egress_prerequisite():
    for app_env in ("staging", "production"):
        blocked = TelemetryProviderRegistry(
            {ConnectorType.HTTPS_TELEMETRY: FakeProvider()},
            app_env=app_env,
            controlled_egress_enabled=False,
        )
        try:
            blocked.get(ConnectorType.HTTPS_TELEMETRY)
        except TelemetryRuntimeUnavailable as error:
            assert error.code == "telemetry_controlled_egress_required"
        else:
            raise AssertionError("HTTPS connector bypassed controlled egress prerequisite")

        enabled = TelemetryProviderRegistry(
            {ConnectorType.HTTPS_TELEMETRY: FakeProvider()},
            app_env=app_env,
            controlled_egress_enabled=True,
        )
        assert enabled.get(ConnectorType.HTTPS_TELEMETRY)

    local = TelemetryProviderRegistry(
        {ConnectorType.HTTPS_TELEMETRY: FakeProvider()},
        app_env="test",
        controlled_egress_enabled=False,
    )
    assert local.get(ConnectorType.HTTPS_TELEMETRY)


def test_validation_refreshes_same_state_success_and_failure_without_transition_error(tmp_path):
    app, repository = build_client(tmp_path)
    provider = app.state.telemetry_runtime.providers.known(
        ConnectorType.HTTPS_TELEMETRY
    )
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        record = next(iter(repository.records.values()))

        for lifecycle_status, enabled in (
            ("connected", True),
            ("degraded", True),
            ("disabled", False),
        ):
            record.update(lifecycle_status=lifecycle_status, enabled=enabled)
            provider.validation_error = None
            response = client.post(
                f"/api/data-connections/{connection_id}/validate",
                headers={"X-Test-Role": "operator"},
            )
            assert response.status_code == 200, response.text
            assert response.json()["connection"]["lifecycle_status"] == lifecycle_status
            assert response.json()["connection"]["last_success_at"] is not None

        provider.validation_error = TelemetryConnectorError(
            "provider_rejected_payload",
            kind=ConnectorFailureKind.PAYLOAD,
            safe_message="Telemetry source returned an invalid payload.",
        )
        for lifecycle_status, enabled in (("degraded", True), ("disabled", False)):
            record.update(lifecycle_status=lifecycle_status, enabled=enabled)
            response = client.post(
                f"/api/data-connections/{connection_id}/validate",
                headers={"X-Test-Role": "operator"},
            )
            assert response.status_code == 200, response.text
            connection = response.json()["connection"]
            assert connection["lifecycle_status"] == lifecycle_status
            assert connection["last_error_code"] == "provider_rejected_payload"


def test_backfill_run_api_is_bounded_scoped_and_resumably_scheduled(tmp_path):
    app, repository = build_client(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        assert client.post(
            f"/api/data-connections/{connection_id}/validate",
            headers={"X-Test-Role": "operator"},
        ).status_code == 200
        enabled = client.post(f"/api/data-connections/{connection_id}/enable")
        assert enabled.status_code == 200, enabled.text
        connection_record = repository.records[next(iter(repository.records))]
        assert connection_record["next_attempt_at"] is not None
        connection_record["next_attempt_at"] = None
        assert client.post(f"/api/data-connections/{connection_id}/enable").status_code == 200
        assert connection_record["next_attempt_at"] is not None

        end = datetime.now(UTC).replace(microsecond=0)
        start = end - timedelta(days=7)
        denied = client.post(
            f"/api/data-connections/{connection_id}/backfills",
            headers={"X-Test-Role": "viewer"},
            json={"start_at": start.isoformat(), "end_at": end.isoformat()},
        )
        assert denied.status_code == 403
        created = client.post(
            f"/api/data-connections/{connection_id}/backfills",
            headers={"X-Test-Role": "operator"},
            json={"start_at": start.isoformat(), "end_at": end.isoformat()},
        )
        assert created.status_code == 202, created.text
        run = created.json()["run"]
        assert run["status"] == "pending"
        assert run["mode"] == "backfill"
        assert repository.audit[-1]["action"] == "backfill_started"

        overlap = client.post(
            f"/api/data-connections/{connection_id}/backfills",
            headers={"X-Test-Role": "operator"},
            json={"start_at": start.isoformat(), "end_at": end.isoformat()},
        )
        assert overlap.status_code == 409
        assert overlap.json()["detail"]["code"] == "telemetry_backfill_already_active"

        progress = client.get(
            f"/api/data-connections/{connection_id}/backfills/{run['run_id']}"
        )
        listed = client.get(f"/api/data-connections/{connection_id}/runs")
        assert progress.status_code == listed.status_code == 200
        assert listed.json()["runs"][0]["run_id"] == run["run_id"]
        for body in (progress.json(), listed.json()):
            rendered = repr(body).lower()
            assert "lease_token" not in rendered
            assert "cursor" not in rendered
            assert "safe_config" not in rendered

        foreign = {
            "X-Test-Tenant": "tenant-b",
            "X-Test-Workspace": "ws-facility-b",
        }
        cross = client.get(
            f"/api/data-connections/{connection_id}/backfills/{run['run_id']}",
            headers=foreign,
        )
        absent = client.get(
            f"/api/data-connections/{uuid.uuid4()}/backfills/{run['run_id']}",
            headers=foreign,
        )
        assert cross.status_code == absent.status_code == 404
        assert cross.json() == absent.json()


def test_backfill_rejects_non_utc_oversized_disabled_and_unsupported_requests(tmp_path):
    app, _repository = build_client(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        now = datetime.now(UTC).replace(microsecond=0)
        valid = {
            "start_at": (now - timedelta(hours=1)).isoformat(),
            "end_at": now.isoformat(),
        }
        disabled = client.post(
            f"/api/data-connections/{connection_id}/backfills",
            headers={"X-Test-Role": "operator"},
            json=valid,
        )
        assert disabled.status_code == 409
        assert disabled.json()["detail"]["code"] == "telemetry_connection_not_enabled"

        for invalid in (
            {"start_at": "2026-01-01T00:00:00", "end_at": "2026-01-02T00:00:00Z"},
            {"start_at": "2026-01-01T01:00:00+01:00", "end_at": "2026-01-02T01:00:00+01:00"},
            {
                "start_at": (now - timedelta(days=32)).isoformat(),
                "end_at": now.isoformat(),
            },
        ):
            response = client.post(
                f"/api/data-connections/{connection_id}/backfills",
                headers={"X-Test-Role": "operator"},
                json=invalid,
            )
            assert response.status_code == 422, response.text

        assert client.post(
            f"/api/data-connections/{connection_id}/validate",
            headers={"X-Test-Role": "operator"},
        ).status_code == 200
        assert client.post(f"/api/data-connections/{connection_id}/enable").status_code == 200
        provider = app.state.telemetry_runtime.providers.known(
            ConnectorType.HTTPS_TELEMETRY
        )
        original_descriptor = provider.descriptor
        provider.descriptor = lambda: ConnectorProviderDescriptor(
            connector_type=ConnectorType.HTTPS_TELEMETRY,
            display_name="HTTPS telemetry API",
            description="test retrieval provider",
            capabilities=frozenset({
                ConnectorCapability.VALIDATE,
                ConnectorCapability.HEALTH_CHECK,
            }),
            production_available=True,
        )
        try:
            unsupported = client.post(
                f"/api/data-connections/{connection_id}/backfills",
                headers={"X-Test-Role": "operator"},
                json=valid,
            )
        finally:
            provider.descriptor = original_descriptor
        assert unsupported.status_code == 409
        assert unsupported.json()["detail"]["code"] == "telemetry_backfill_not_supported"


def test_run_errors_are_sanitized_and_retry_is_operator_only(tmp_path):
    app, repository = build_client(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        assert client.post(
            f"/api/data-connections/{connection_id}/validate",
            headers={"X-Test-Role": "operator"},
        ).status_code == 200
        assert client.post(f"/api/data-connections/{connection_id}/enable").status_code == 200
        now = datetime.now(UTC).replace(microsecond=0)
        created = client.post(
            f"/api/data-connections/{connection_id}/backfills",
            headers={"X-Test-Role": "operator"},
            json={
                "start_at": (now - timedelta(days=1)).isoformat(),
                "end_at": now.isoformat(),
            },
        ).json()["run"]
        stored = repository.runs[(next(iter(repository.runs))[0], created["run_id"])]
        stored.update(
            status="failed",
            finished_at=now,
            error_code="network_timeout",
            error_summary="Bearer canary-token at https://private.example.test/raw",
            lease_token="never-public",
            cursor_payload={"provider_cursor": "never-public"},
        )
        repository.errors.append({
            "id": str(uuid.uuid4()),
            "resource_scope_id": next(iter(repository.records))[0],
            "connection_id": connection_id,
            "ingestion_run_id": created["run_id"],
            "external_signal_id": None,
            "external_tag_id": "tag-1",
            "quality_state": "format_invalid",
            "reason_code": "payload_invalid",
            "disposition": "duplicate",
            "occurrence_count": 1,
            "first_seen_at": now,
            "last_seen_at": now,
            "safe_context": {
                "url": "https://private.example.test/raw",
                "token": "canary-token",
            },
        })

        errors = client.get(f"/api/data-connections/{connection_id}/errors")
        runs = client.get(f"/api/data-connections/{connection_id}/runs")
        assert errors.status_code == 200, errors.text
        assert runs.status_code == 200, runs.text
        assert errors.json()["errors"][0]["reason_code"] == "payload_invalid"
        assert errors.json()["errors"][0]["disposition"] == "duplicate"
        assert "canary-token" not in errors.text
        assert "private.example" not in errors.text
        assert "never-public" not in errors.text
        assert "canary-token" not in runs.text
        assert "private.example" not in runs.text
        assert "never-public" not in runs.text

        viewer = client.post(
            f"/api/data-connections/{connection_id}/runs/{created['run_id']}/retry",
            headers={"X-Test-Role": "viewer"},
        )
        operator = client.post(
            f"/api/data-connections/{connection_id}/runs/{created['run_id']}/retry",
            headers={"X-Test-Role": "operator"},
        )
        assert viewer.status_code == 403
        assert operator.status_code == 202, operator.text
        assert operator.json()["run"]["mode"] == "retry"
        assert operator.json()["run"]["status"] == "pending"
        duplicate = client.post(
            f"/api/data-connections/{connection_id}/runs/{created['run_id']}/retry",
            headers={"X-Test-Role": "operator"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["detail"]["code"] == "telemetry_ingestion_run_not_retryable"


def test_canonical_result_routes_keep_exact_scoped_identity(
    tmp_path, monkeypatch
):
    from app.services.telemetry_result_service import TelemetryCanonicalResultService

    app, _repository = build_client(tmp_path)
    result_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    window_id = str(uuid.uuid4())
    system_id = "plant/" + ("s" * 154)
    calls: list[tuple[str, dict[str, Any]]] = []
    now = datetime.now(UTC).replace(microsecond=0)

    def summary(connection_id: str) -> dict[str, Any]:
        return {
            "result_id": result_id,
            "analysis_window_id": window_id,
            "connection_id": connection_id,
            "source_run_id": run_id,
            "facility_id": "ws-facility-a",
            "system_id": system_id,
            "asset_id": "asset-a",
            "window_start": now - timedelta(minutes=2),
            "window_end": now,
            "analytical_status": "stable",
            "artifact_schema_version": "telemetry-canonical-result-artifact.v1",
            "execution_contract_version": "analysis-window-execution.v1",
            "analysis_schema_version": "analysis-result-v1",
            "analysis_contract_version": "analysis-result-v1",
            "engine_name": "sii",
            "engine_version": "test",
            "observation_count": 2,
            "observation_lineage_digest": "a" * 64,
            "finding_count": 0,
            "evidence_count": 0,
            "payload_digest": "b" * 64,
            "payload_uncompressed_bytes": 1_024,
            "payload_stored_bytes": 512,
            "serialization_ms": 1.0,
            "created_at": now,
        }

    def fake_list(self, scope, **identity):
        calls.append(("list", identity))
        return [summary(identity["connection_id"])]

    def fake_get(self, scope, **identity):
        calls.append(("get", identity))
        return {
            **summary(identity["connection_id"]),
            "authority_digest": "c" * 64,
            "reference_metadata": {},
            "payload_encoding": "zlib+canonical-json.v1",
            "projection_bytes": 256,
            "shared_envelope_bytes": 128,
            "technical_channels_bytes": 64,
            "evidence_audit_bytes": 32,
            "projection_serialization_ms": 0.5,
            "retrieval_ms": 1.5,
            "lineage_verified": True,
            "product_result": {"result_id": result_id, "analysis_result": {}},
        }

    def fake_lineage(self, scope, **identity):
        calls.append(("lineage", identity))
        return {
            "result_id": result_id,
            "analysis_window_id": window_id,
            "observation_count": 2,
            "observation_lineage_digest": "a" * 64,
            "lineage_verified": True,
            "records": [],
            "next_cursor": None,
        }

    monkeypatch.setattr(TelemetryCanonicalResultService, "list_results", fake_list)
    monkeypatch.setattr(TelemetryCanonicalResultService, "get_result", fake_get)
    monkeypatch.setattr(
        TelemetryCanonicalResultService, "get_lineage_page", fake_lineage
    )

    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        base = f"/api/data-connections/{connection_id}/runs/{run_id}"
        listed = client.get(f"{base}/analysis-results")
        encoded_system_id = quote(system_id, safe="")
        exact = client.get(
            f"{base}/systems/{encoded_system_id}/analysis-results/{result_id}",
            params={"asset_id": "asset-a"},
        )
        lineage = client.get(
            f"{base}/systems/{encoded_system_id}/analysis-results/{result_id}/lineage",
            params={"asset_id": "asset-a", "limit": 50},
        )

        assert listed.status_code == exact.status_code == lineage.status_code == 200
        assert exact.json()["result_id"] == result_id
        assert lineage.json()["lineage_verified"] is True
        assert calls == [
            (
                "list",
                {
                    "connection_id": connection_id,
                    "source_run_id": run_id,
                    "limit": 100,
                },
            ),
            (
                "get",
                {
                    "connection_id": connection_id,
                    "source_run_id": run_id,
                    "system_id": system_id,
                    "asset_id": "asset-a",
                    "result_id": result_id,
                },
            ),
            (
                "lineage",
                {
                    "connection_id": connection_id,
                    "source_run_id": run_id,
                    "system_id": system_id,
                    "asset_id": "asset-a",
                    "result_id": result_id,
                    "limit": 50,
                    "cursor": None,
                },
            ),
        ]

        foreign = {
            "X-Test-Tenant": "tenant-b",
            "X-Test-Workspace": "ws-facility-b",
        }
        cross = client.get(f"{base}/analysis-results", headers=foreign)
        absent = client.get(
            f"/api/data-connections/{uuid.uuid4()}/runs/{run_id}/analysis-results",
            headers=foreign,
        )
        assert cross.status_code == absent.status_code == 404
        assert cross.json() == absent.json()


def test_backfill_progress_keeps_same_range_during_transient_retry_and_exhausts_terminally(tmp_path):
    app, repository = build_client(tmp_path)
    with TestClient(app, base_url="https://testserver") as client:
        connection_id = client.post(
            "/api/data-connections", json=_connection_payload()
        ).json()["connection"]["connection_id"]
        assert client.post(
            f"/api/data-connections/{connection_id}/validate",
            headers={"X-Test-Role": "operator"},
        ).status_code == 200
        assert client.post(f"/api/data-connections/{connection_id}/enable").status_code == 200
        end = datetime.now(UTC).replace(microsecond=0)
        start = end - timedelta(hours=12)
        created = client.post(
            f"/api/data-connections/{connection_id}/backfills",
            headers={"X-Test-Role": "operator"},
            json={"start_at": start.isoformat(), "end_at": end.isoformat()},
        ).json()["run"]
        run_key = (next(iter(repository.runs))[0], created["run_id"])
        stored = repository.runs[run_key]

        # Mirrors repository retry semantics after a transient provider error:
        # the leased run is requeued, not replaced or terminalized.
        stored.update(
            status="pending",
            retry_count=1,
            finished_at=None,
            error_code="provider_temporarily_unavailable",
            error_summary="Telemetry provider is temporarily unavailable.",
        )
        retrying = client.get(
            f"/api/data-connections/{connection_id}/backfills/{created['run_id']}"
        )
        assert retrying.status_code == 200, retrying.text
        retrying_run = retrying.json()
        assert retrying_run["run_id"] == created["run_id"]
        assert retrying_run["mode"] == "backfill"
        assert retrying_run["status"] == "pending"
        assert retrying_run["retry_count"] == 1
        assert retrying_run["range_start"] == created["range_start"]
        assert retrying_run["range_end"] == created["range_end"]
        assert len(repository.runs) == 1

        stored.update(status="failed", retry_count=10, finished_at=end)
        exhausted = client.get(
            f"/api/data-connections/{connection_id}/backfills/{created['run_id']}"
        )
        assert exhausted.status_code == 200, exhausted.text
        assert exhausted.json()["status"] == "failed"
        assert exhausted.json()["retry_count"] == 10
        assert exhausted.json()["finished_at"] == end.isoformat().replace("+00:00", "Z")
