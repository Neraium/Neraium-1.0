from __future__ import annotations

from datetime import UTC, datetime, timedelta
import inspect
from types import SimpleNamespace
import uuid

import pytest
from pydantic import ValidationError

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.models.telemetry_api_models import BackfillCreateRequest
from app.services.telemetry_backfill import TelemetryBackfillService
from app.services.telemetry_domain import ConnectorCapability, TelemetryScopeRef


class Repository:
    def __init__(self) -> None:
        self.created: dict | None = None

    def create_backfill_run(self, scope, **values):
        self.created = {"scope": scope, **values}
        return {
            "id": values["run_id"],
            "connection_id": values["connection_id"],
            "mode": "backfill",
            "status": "pending",
            "range_start": values["range_start"],
            "range_end": values["range_end"],
            "started_at": values["requested_at"],
            "actor_id": values["actor_id"],
            "lease_token": "private-lease",
            "cursor_payload": {"cursor": "private-cursor"},
        }


class Providers:
    @staticmethod
    def capabilities(_connector_type):
        return [ConnectorCapability.BOUNDED_BACKFILL.value]


class Runtime(SimpleNamespace):
    def require_available(self):
        return self


def _scope() -> TelemetryScopeRef:
    tenant_scope_id = "tenant-a"
    workspace_id = "workspace-a"
    return TelemetryScopeRef(
        tenant_scope_id=tenant_scope_id,
        workspace_id=workspace_id,
        resource_scope_id=canonical_phase4_resource_scope_id(
            tenant_scope_id, workspace_id
        ),
        facility_id=workspace_id,
    )


def test_backfill_contract_requires_strict_utc_order_and_maximum_span() -> None:
    valid = BackfillCreateRequest(
        start_at=datetime(2026, 1, 1, tzinfo=UTC),
        end_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    assert valid.start_at.tzinfo is UTC

    invalid_ranges = (
        (datetime(2026, 1, 1), datetime(2026, 1, 2, tzinfo=UTC)),
        (
            datetime.fromisoformat("2026-01-01T01:00:00+01:00"),
            datetime.fromisoformat("2026-01-02T01:00:00+01:00"),
        ),
        (datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)),
        (
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 3, tzinfo=UTC),
        ),
    )
    for start_at, end_at in invalid_ranges:
        with pytest.raises(ValidationError):
            BackfillCreateRequest(start_at=start_at, end_at=end_at)


def test_api_backfill_only_schedules_durable_worker_work_and_redacts_private_state() -> None:
    repository = Repository()
    service = TelemetryBackfillService(
        Runtime(repository=repository, providers=Providers())
    )
    payload = BackfillCreateRequest(
        start_at=datetime.now(UTC) - timedelta(hours=2),
        end_at=datetime.now(UTC) - timedelta(hours=1),
    )
    connection_id = str(uuid.uuid4())
    public = service.start_backfill(
        _scope(),
        {
            "id": connection_id,
            "enabled": True,
            "connector_type": "https_telemetry",
        },
        payload,
        actor_id="operator@example.test",
    )

    assert repository.created is not None
    assert repository.created["scope"] == _scope()
    assert repository.created["range_start"] == payload.start_at
    assert repository.created["range_end"] == payload.end_at
    assert public["connection_id"] == connection_id
    assert "lease_token" not in public
    assert "cursor_payload" not in public

    implementation = inspect.getsource(TelemetryBackfillService.start_backfill).lower()
    assert "upload" not in implementation
    assert "csv" not in implementation
    assert "fetch_backfill" not in implementation


def test_public_rejection_preserves_duplicate_disposition_without_raw_context() -> None:
    now = datetime.now(UTC)
    public = TelemetryBackfillService.public_error({
        "id": str(uuid.uuid4()),
        "ingestion_run_id": str(uuid.uuid4()),
        "external_signal_id": None,
        "external_tag_id": "tag-1",
        "quality_state": "good",
        "reason_code": "duplicate_record",
        "disposition": "duplicate",
        "occurrence_count": 2,
        "first_seen_at": now,
        "last_seen_at": now,
        "safe_context": {"raw_payload": "must-not-escape"},
    })

    assert public["disposition"] == "duplicate"
    assert public["occurrence_count"] == 2
    assert "safe_context" not in public
    assert "raw_payload" not in repr(public)
