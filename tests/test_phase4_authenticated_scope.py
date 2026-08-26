from __future__ import annotations

import json
from pathlib import Path

from app.engine.sii.behavioral_model_contract import (
    AuthenticatedPhase4Scope,
    canonical_phase4_resource_scope_id,
)
from app.services import runtime_db
from app.services.dataset_scope import (
    DatasetScope,
    build_dataset_scope,
    dataset_scope_context,
    dataset_scope_from_queue_routing,
)
from app.services.phase4_scope import (
    authenticated_phase4_scope_context,
    authenticated_phase4_scope_from_queue_routing,
    authenticated_phase4_scope_from_request_context,
    build_upload_queue_phase4_scope_envelope,
    current_authenticated_phase4_scope,
)
from app.services.upload_queue_lifecycle import UploadQueueLifecycleService
from app.services.upload_runtime_state import UploadRuntimeState
from app.services.workspace_authorization import WorkspaceContext


def _workspace_context(
    *,
    workspace_id: str,
    kind: str,
    tenant_id: str = "tenant-a",
    resource_workspace_id: str = "default",
    membership_active: bool = True,
) -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id=workspace_id,
        display_name="Authorized workspace",
        kind=kind,
        membership_active=membership_active,
        dataset_scope=build_dataset_scope(
            tenant_id=tenant_id,
            user_id="operator@example.com",
            workspace_id=resource_workspace_id,
        ),
    )


def test_request_scope_uses_authenticated_tenant_and_outer_explicit_workspace() -> None:
    context = _workspace_context(
        workspace_id="ws-plant-a",
        kind="facility",
        resource_workspace_id="default",
    )

    scope = authenticated_phase4_scope_from_request_context(
        auth_context={"authenticated": True, "auth_subject": "operator@example.com"},
        workspace_context=context,
    )

    assert scope == AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a",
        workspace_id="ws-plant-a",
        resource_scope_id=canonical_phase4_resource_scope_id("tenant-a", "ws-plant-a"),
    )
    assert scope.workspace_id != context.dataset_scope.workspace_id
    assert scope.resource_scope_id != context.dataset_scope.storage_id


def test_request_scope_allows_authenticated_personal_default_only() -> None:
    personal_default = _workspace_context(workspace_id="default", kind="personal")
    legacy_label = _workspace_context(workspace_id="plant-a", kind="personal")

    assert authenticated_phase4_scope_from_request_context(
        auth_context={"authenticated": True},
        workspace_context=personal_default,
    ) == AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a",
        workspace_id="default",
        resource_scope_id=canonical_phase4_resource_scope_id("tenant-a", "default"),
    )
    assert authenticated_phase4_scope_from_request_context(
        auth_context={"authenticated": True},
        workspace_context=legacy_label,
    ) is None
    assert authenticated_phase4_scope_from_request_context(
        auth_context={"authenticated": False},
        workspace_context=personal_default,
    ) is None


def test_request_scope_fails_closed_for_missing_tenant_or_inactive_membership() -> None:
    missing_tenant = WorkspaceContext(
        workspace_id="ws-plant-a",
        display_name="Plant A",
        kind="facility",
        membership_active=True,
        dataset_scope=DatasetScope(
            tenant_id="",
            user_id="operator@example.com",
            workspace_id="default",
        ),
    )
    inactive = _workspace_context(
        workspace_id="ws-plant-a",
        kind="facility",
        membership_active=False,
    )

    assert authenticated_phase4_scope_from_request_context(
        auth_context={"authenticated": True},
        workspace_context=missing_tenant,
    ) is None
    assert authenticated_phase4_scope_from_request_context(
        auth_context={"authenticated": True},
        workspace_context=inactive,
    ) is None


def test_request_scope_derives_distinct_canonical_resource_scope_per_workspace() -> None:
    workspace_a = authenticated_phase4_scope_from_request_context(
        auth_context={"authenticated": True},
        workspace_context=_workspace_context(
            workspace_id="ws-plant-a",
            kind="facility",
            resource_workspace_id="default",
        ),
    )
    workspace_b = authenticated_phase4_scope_from_request_context(
        auth_context={"authenticated": True},
        workspace_context=_workspace_context(
            workspace_id="ws-plant-b",
            kind="facility",
            resource_workspace_id="default",
        ),
    )

    assert workspace_a is not None and workspace_b is not None
    assert workspace_a.tenant_scope_id == workspace_b.tenant_scope_id == "tenant-a"
    assert workspace_a.resource_scope_id != workspace_b.resource_scope_id


def test_queue_phase4_envelope_is_bound_to_dataset_scope_and_detects_tampering() -> None:
    dataset_scope = build_dataset_scope(
        tenant_id="tenant-a",
        user_id="operator@example.com",
        workspace_id="default",
    )
    phase4_scope = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a",
        workspace_id="ws-plant-a",
    )
    envelope = build_upload_queue_phase4_scope_envelope(
        dataset_scope=dataset_scope,
        phase4_scope=phase4_scope,
    )
    queue_record = {"routing": {"phase4_scope": envelope}}

    assert authenticated_phase4_scope_from_queue_routing(
        queue_record,
        dataset_scope=dataset_scope,
    ) == phase4_scope

    tampered = json.loads(json.dumps(queue_record))
    tampered["routing"]["phase4_scope"]["authenticated_scope"]["workspace_id"] = "ws-other"
    assert authenticated_phase4_scope_from_queue_routing(
        tampered,
        dataset_scope=dataset_scope,
    ) is None

    other_dataset_scope = build_dataset_scope(
        tenant_id="tenant-a",
        user_id="operator@example.com",
        workspace_id="other-resource",
    )
    assert authenticated_phase4_scope_from_queue_routing(
        queue_record,
        dataset_scope=other_dataset_scope,
    ) is None

    other_tenant_scope = build_dataset_scope(
        tenant_id="tenant-b",
        user_id="operator@example.com",
        workspace_id="default",
    )
    assert build_upload_queue_phase4_scope_envelope(
        dataset_scope=other_tenant_scope,
        phase4_scope=phase4_scope,
    ) is None
    assert authenticated_phase4_scope_from_queue_routing(
        queue_record,
        dataset_scope=other_tenant_scope,
    ) is None


def test_sqlite_queue_roundtrip_preserves_internal_phase4_scope(
    tmp_path: Path,
) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    dataset_scope = build_dataset_scope(
        tenant_id="tenant-a",
        user_id="operator@example.com",
        workspace_id="default",
    )
    phase4_scope = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a",
        workspace_id="ws-plant-a",
    )
    runtime_db.upsert_upload_job(
        {
            "job_id": "phase4-routed-job",
            "status": "PENDING",
            # A client/job field with the same name is not queue authority.
            "phase4_scope": {"workspace_id": "ws-attacker"},
        }
    )

    with dataset_scope_context(dataset_scope), authenticated_phase4_scope_context(phase4_scope):
        runtime_db.enqueue_upload_job("phase4-routed-job")
        queued = runtime_db.read_upload_queue_job("phase4-routed-job")
        claimed = runtime_db.claim_next_upload_job_record()

    assert queued is not None
    assert claimed is not None
    assert dataset_scope_from_queue_routing(claimed) == dataset_scope
    assert authenticated_phase4_scope_from_queue_routing(
        claimed,
        dataset_scope=dataset_scope,
    ) == phase4_scope


def test_sqlite_queue_without_authenticated_phase4_scope_keeps_dataset_routing(
    tmp_path: Path,
) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    dataset_scope = build_dataset_scope(
        tenant_id="tenant-a",
        user_id="operator@example.com",
        workspace_id="default",
    )
    runtime_db.upsert_upload_job({"job_id": "limited-phase4-job", "status": "PENDING"})

    with dataset_scope_context(dataset_scope), authenticated_phase4_scope_context(None):
        runtime_db.enqueue_upload_job("limited-phase4-job")
        claimed = runtime_db.claim_next_upload_job_record()

    assert claimed is not None
    assert dataset_scope_from_queue_routing(claimed) == dataset_scope
    assert authenticated_phase4_scope_from_queue_routing(
        claimed,
        dataset_scope=dataset_scope,
    ) is None


def test_tampered_phase4_queue_scope_limits_phase4_without_blocking_worker(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    dataset_scope = build_dataset_scope(
        tenant_id="tenant-a",
        user_id="operator@example.com",
        workspace_id="default",
    )
    phase4_scope = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a",
        workspace_id="ws-plant-a",
    )
    runtime_db.upsert_upload_job({"job_id": "tampered-phase4-job", "status": "PENDING"})
    with dataset_scope_context(dataset_scope), authenticated_phase4_scope_context(phase4_scope):
        runtime_db.enqueue_upload_job("tampered-phase4-job")
    with runtime_db.db_connection() as connection:
        row = connection.execute(
            "SELECT routing_json FROM upload_queue_routing WHERE job_id = ?",
            ("tampered-phase4-job",),
        ).fetchone()
        routing = json.loads(row["routing_json"])
        routing["phase4_scope"]["authenticated_scope"]["workspace_id"] = "ws-attacker"
        connection.execute(
            "UPDATE upload_queue_routing SET routing_json = ? WHERE job_id = ?",
            (json.dumps(routing), "tampered-phase4-job"),
        )

    captured: dict[str, object] = {}
    service = UploadQueueLifecycleService(
        runtime_state=UploadRuntimeState(runtime_dir=tmp_path),
        logger=runtime_db.logger,
        read_job=lambda _job_id: None,
        read_upload_result_by_job_id=lambda _job_id: None,
        read_baseline_result=lambda _job_id: None,
        read_upload_status=lambda _job_id: None,
        write_job=lambda _payload: None,
        process_json_payload=lambda *_args, **_kwargs: {},
        process_csv_file=lambda *_args, **_kwargs: {},
        restore_upload_source=lambda *_args, **_kwargs: tmp_path / "unused",
        delete_upload_source=lambda _key: None,
    )

    def process_claimed(
        job_id: str,
        _started_at: float,
        **_kwargs,
    ) -> bool:
        captured["job_id"] = job_id
        captured["phase4_scope"] = current_authenticated_phase4_scope()
        return True

    monkeypatch.setattr(service, "_process_claimed_upload_job", process_claimed)

    assert service.process_next_queued_upload_job() is True
    assert captured == {"job_id": "tampered-phase4-job", "phase4_scope": None}
