from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.main import create_app
from app.routers import data as data_router
from app.services import auth_store
from app.services import runtime_db
from app.services.dataset_scope import (
    build_dataset_scope,
    dataset_scope_context,
)
from app.services.facility_context import resolve_server_bound_system_identity
from app.services.phase4_scope import (
    ServerBoundSystemIdentity,
    authenticated_phase4_scope_context,
    authenticated_phase4_scope_from_queue_routing,
    current_server_bound_system_identity,
    server_bound_system_identity_from_queue_routing,
)
from app.services.upload_queue_lifecycle import UploadQueueLifecycleService
from app.services.upload_runtime_state import UploadRuntimeState


def _production_app(monkeypatch: pytest.MonkeyPatch, runtime_dir: Path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(runtime_dir))
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("NERAIUM_BOOTSTRAP_ADMIN_PASSWORD", "password123")
    auth_store._AUTH_BACKEND = None
    auth_store._AUTH_BACKEND_KEY = None
    monkeypatch.setattr(data_router, "consume_rate_limit", lambda *_args, **_kwargs: (True, 0))
    return create_app(
        Settings(
            app_env="production",
            backend_host="127.0.0.1",
            backend_port=8010,
            cors_origins=["https://app.neraium.com"],
            runtime_dir=runtime_dir,
        )
    )


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert response.status_code == 200, response.text


def _configure_systems(
    client: TestClient,
    *system_ids: str,
    headers: dict[str, str] | None = None,
) -> None:
    response = client.put(
        "/api/facility/context",
        headers=headers,
        json={
            "site_id": "test-facility",
            "site_name": "Test Facility",
            "timezone": "UTC",
            "systems": [
                {
                    "system_id": system_id,
                    "name": system_id,
                    "system_type": "chilled_water_loop",
                    "equipment_ids": [],
                }
                for system_id in system_ids
            ],
            "equipment": [],
            "signal_mappings": [],
        },
    )
    assert response.status_code == 200, response.text


def _csv() -> str:
    rows = [
        f"2026-08-01T00:{index:02d}:00Z,{40 + index % 5},{80 + (index % 5) * 2}"
        for index in range(48)
    ]
    return "timestamp,flow,pressure\n" + "\n".join(rows)


def _upload(
    client: TestClient,
    *,
    system_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    data = {"workflow": "legacy_analysis"}
    if system_id is not None:
        data["system_id"] = system_id
    accepted = client.post(
        "/api/data/upload",
        data=data,
        headers=headers,
        files={"file": ("telemetry.csv", _csv(), "text/csv")},
    )
    assert accepted.status_code == 202, accepted.text
    job_id = accepted.json()["job_id"]
    deadline = time.time() + 30
    terminal: dict = {}
    while time.time() < deadline:
        response = client.get(f"/api/data/upload-status/{job_id}", headers=headers)
        assert response.status_code == 200, response.text
        terminal = response.json()
        if terminal.get("status") in {"COMPLETE", "FAILED"}:
            break
        time.sleep(0.05)
    assert terminal.get("status") == "COMPLETE", terminal
    result_response = client.get(f"/api/data/intake/{job_id}/result", headers=headers)
    assert result_response.status_code == 200, result_response.text
    return result_response.json()["result"]


def _v2_keys() -> list[str]:
    with runtime_db.db_connection() as connection:
        return [
            str(row["key"])
            for row in connection.execute(
                "SELECT key FROM latest_payloads WHERE key LIKE 'sii_behavioral_model_ledger_v2::%' ORDER BY key"
            ).fetchall()
        ]


def _facility(*system_ids: str) -> dict[str, object]:
    return {
        "contract_version": "facility-context.v1",
        "systems": [
            {
                "system_id": system_id,
                "name": f"System {system_id}",
                "system_type": "chilled_water_loop",
                "equipment_ids": [],
            }
            for system_id in system_ids
        ],
    }


def _identity(scope, system_id: str) -> ServerBoundSystemIdentity:
    with dataset_scope_context(scope), patch(
        "app.services.facility_context.read_facility_context",
        return_value=_facility(system_id),
    ):
        resolution = resolve_server_bound_system_identity(requested_system_id=system_id)
    assert resolution.identity is not None
    return resolution.identity


def test_registry_resolution_requires_exact_server_owned_membership() -> None:
    scope = build_dataset_scope(
        tenant_id="tenant-a",
        user_id="operator@example.com",
        workspace_id="ws-plant-a",
    )

    with dataset_scope_context(scope), patch(
        "app.services.facility_context.read_facility_context",
        return_value=_facility("chw-loop-1", "chw-loop-2"),
    ):
        explicit = resolve_server_bound_system_identity(requested_system_id="chw-loop-2")
        payload_override = resolve_server_bound_system_identity(
            requested_system_id="attacker-system"
        )
        ambiguous = resolve_server_bound_system_identity()

    assert explicit.identity is not None
    assert explicit.identity.system_id == "chw-loop-2"
    assert explicit.reason == "resolved_explicit_registered_system"
    assert payload_override.identity is None
    assert payload_override.reason == "requested_system_id_not_registered"
    assert ambiguous.identity is None
    assert ambiguous.reason == "explicit_system_assignment_required"


def test_unique_system_auto_resolution_is_stable_and_workspace_bound() -> None:
    scope_a = build_dataset_scope(
        tenant_id="tenant-a", user_id="operator@example.com", workspace_id="ws-a"
    )
    scope_b = build_dataset_scope(
        tenant_id="tenant-a", user_id="operator@example.com", workspace_id="ws-b"
    )
    with patch(
        "app.services.facility_context.read_facility_context",
        return_value=_facility("shared-business-id"),
    ):
        with dataset_scope_context(scope_a):
            first = resolve_server_bound_system_identity()
            repeated = resolve_server_bound_system_identity()
        with dataset_scope_context(scope_b):
            other_workspace = resolve_server_bound_system_identity()

    assert first.identity == repeated.identity
    assert first.reason == "resolved_unique_registered_system"
    assert first.identity is not None and other_workspace.identity is not None
    assert first.identity.system_id == other_workspace.identity.system_id
    assert first.identity.dataset_scope_storage_id != other_workspace.identity.dataset_scope_storage_id


def test_registered_baseline_mismatch_fails_closed() -> None:
    scope = build_dataset_scope(user_id="operator@example.com", workspace_id="ws-a")
    with dataset_scope_context(scope), patch(
        "app.services.facility_context.read_facility_context",
        return_value=_facility("system-a", "system-b"),
    ):
        resolution = resolve_server_bound_system_identity(
            requested_system_id="system-a",
            baseline_system_id="system-b",
        )

    assert resolution.identity is None
    assert resolution.reason == "baseline_system_id_mismatch"


def test_unregistered_server_baseline_cannot_be_rebound_to_unique_registry_system() -> None:
    scope = build_dataset_scope(user_id="operator@example.com", workspace_id="ws-a")
    with dataset_scope_context(scope), patch(
        "app.services.facility_context.read_facility_context",
        return_value=_facility("system-a"),
    ):
        resolution = resolve_server_bound_system_identity(
            baseline_system_id="legacy-unregistered-system",
        )

    assert resolution.identity is None
    assert resolution.reason == "baseline_system_id_not_registered"


def test_queue_binding_roundtrip_and_tamper_detection(tmp_path: Path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    scope = build_dataset_scope(
        tenant_id="tenant-a", user_id="operator@example.com", workspace_id="ws-a"
    )
    phase4_scope = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a", workspace_id="ws-a"
    )
    identity = _identity(scope, "system-a")
    runtime_db.upsert_upload_job({"job_id": "job-a", "status": "PENDING"})
    with dataset_scope_context(scope), authenticated_phase4_scope_context(phase4_scope):
        runtime_db.enqueue_upload_job(
            "job-a",
            system_identity=identity,
            dataset_id="dataset-a",
            upload_session_id="session-a",
        )
        queued = runtime_db.read_upload_queue_job("job-a")

    assert queued is not None
    assert server_bound_system_identity_from_queue_routing(
        queued,
        dataset_scope=scope,
        phase4_scope=phase4_scope,
        job_id="job-a",
        dataset_id="dataset-a",
        upload_session_id="session-a",
    ) == identity

    tampered = json.loads(json.dumps(queued))
    tampered["routing"]["phase4_scope"]["system_identity"]["system_id"] = "system-b"
    assert authenticated_phase4_scope_from_queue_routing(tampered, dataset_scope=scope) is None
    assert server_bound_system_identity_from_queue_routing(
        tampered,
        dataset_scope=scope,
        phase4_scope=phase4_scope,
        job_id="job-a",
    ) is None

    runtime_db.upsert_upload_job({"job_id": "job-b", "status": "PENDING"})
    with dataset_scope_context(scope), authenticated_phase4_scope_context(phase4_scope):
        runtime_db.enqueue_upload_job(
            "job-b",
            system_identity=identity,
            dataset_id="dataset-b",
            upload_session_id="session-b",
        )
    swapped = runtime_db.read_upload_queue_job("job-b")
    assert swapped is not None
    swapped["routing"] = queued["routing"]
    assert server_bound_system_identity_from_queue_routing(
        swapped,
        dataset_scope=scope,
        phase4_scope=phase4_scope,
        job_id="job-b",
    ) is None


def test_legacy_authenticated_scope_envelope_remains_readable_without_system_authority() -> None:
    scope = build_dataset_scope(
        tenant_id="tenant-a", user_id="operator@example.com", workspace_id="ws-a"
    )
    phase4_scope = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a", workspace_id="ws-a"
    )
    binding = {
        "version": "upload-queue-phase4-scope.v1",
        "authenticated_scope": phase4_scope.as_dict(),
        "authenticated_scope_digest": phase4_scope.scope_digest,
        "dataset_scope_storage_id": scope.storage_id,
    }
    encoded = json.dumps(binding, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    envelope = {
        **binding,
        "binding_digest": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }
    queued = {"job_id": "legacy-job", "routing": {"phase4_scope": envelope}}

    assert authenticated_phase4_scope_from_queue_routing(
        queued, dataset_scope=scope
    ) == phase4_scope
    assert server_bound_system_identity_from_queue_routing(
        queued,
        dataset_scope=scope,
        phase4_scope=phase4_scope,
        job_id="legacy-job",
    ) is None


def test_retry_preserves_original_queue_system_identity(tmp_path: Path) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    scope = build_dataset_scope(
        tenant_id="tenant-a", user_id="operator@example.com", workspace_id="ws-a"
    )
    phase4_scope = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a", workspace_id="ws-a"
    )
    original_identity = _identity(scope, "system-a")
    redirect_identity = _identity(scope, "system-b")
    runtime_db.upsert_upload_job({"job_id": "retry-job", "status": "PENDING"})
    with dataset_scope_context(scope), authenticated_phase4_scope_context(phase4_scope):
        runtime_db.enqueue_upload_job(
            "retry-job",
            system_identity=original_identity,
            dataset_id="dataset-a",
            upload_session_id="session-a",
        )
        runtime_db.claim_next_upload_job_record()
        runtime_db.complete_upload_queue_job("retry-job", "failed", "test_failure")
        with pytest.raises(RuntimeError, match="upload_queue_phase4_scope_conflict"):
            runtime_db.enqueue_upload_job(
                "retry-job",
                system_identity=redirect_identity,
                dataset_id="attacker-dataset",
                upload_session_id="attacker-session",
            )
        runtime_db.enqueue_upload_job(
            "retry-job",
            system_identity=redirect_identity,
            dataset_id="attacker-dataset",
            upload_session_id="attacker-session",
            preserve_existing_routing=True,
        )
        retried = runtime_db.read_upload_queue_job("retry-job")

    assert retried is not None
    assert server_bound_system_identity_from_queue_routing(
        retried,
        dataset_scope=scope,
        phase4_scope=phase4_scope,
        job_id="retry-job",
        dataset_id="dataset-a",
        upload_session_id="session-a",
    ) == original_identity


def test_worker_restores_identity_before_reading_job_payload(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runtime_db.configure_runtime_dir(tmp_path)
    scope = build_dataset_scope(
        tenant_id="tenant-a", user_id="operator@example.com", workspace_id="ws-a"
    )
    phase4_scope = AuthenticatedPhase4Scope(
        tenant_scope_id="tenant-a", workspace_id="ws-a"
    )
    identity = _identity(scope, "system-a")
    runtime_db.upsert_upload_job({"job_id": "worker-job", "status": "PENDING"})
    with dataset_scope_context(scope), authenticated_phase4_scope_context(phase4_scope):
        runtime_db.enqueue_upload_job(
            "worker-job",
            system_identity=identity,
            dataset_id="dataset-a",
            upload_session_id="session-a",
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

    def process_claimed(*_args, **_kwargs) -> bool:
        captured["identity"] = current_server_bound_system_identity()
        return True

    monkeypatch.setattr(service, "_process_claimed_upload_job", process_claimed)

    assert service.process_next_queued_upload_job() is True
    assert captured["identity"] == identity
    assert current_server_bound_system_identity() is None


def test_ordinary_authorized_upload_writes_scoped_phase4_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _production_app(monkeypatch, tmp_path)

    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        _configure_systems(client, "chw-loop-1")
        result = _upload(client, system_id="chw-loop-1")

    identity = result.get("phase4_system_identity") or {}
    behavioral_model = (result.get("sii_result") or {}).get("behavioral_model") or {}
    assert identity["system_id"] == "chw-loop-1"
    assert identity["authority"] == "facility-context.v1"
    assert behavioral_model["processing_trace"]["phase_4_active"] is True
    assert "authenticated_scope_unavailable" not in behavioral_model["limitations"]
    assert behavioral_model["identity"]["system_id"] == "chw-loop-1"
    assert len(_v2_keys()) == 1


def test_upload_model_identity_is_stable_per_system_and_distinct_within_workspace(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _production_app(monkeypatch, tmp_path)

    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        _configure_systems(client, "system-a", "system-b")
        first = _upload(client, system_id="system-a")
        repeated = _upload(client, system_id="system-a")
        other = _upload(client, system_id="system-b")

    first_model = first["sii_result"]["behavioral_model"]["model_id"]
    repeated_model = repeated["sii_result"]["behavioral_model"]["model_id"]
    other_model = other["sii_result"]["behavioral_model"]["model_id"]
    assert first_model == repeated_model
    assert first_model != other_model
    assert len(_v2_keys()) == 2


def test_same_business_system_id_is_distinct_across_authorized_workspaces(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _production_app(monkeypatch, tmp_path)

    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        workspace_ids: list[str] = []
        models: list[str] = []
        job_ids: list[str] = []
        for label in ("Plant A", "Plant B"):
            created = client.post(
                "/api/workspaces",
                json={"display_name": label, "adopt_current_scope": False},
            )
            assert created.status_code == 201, created.text
            workspace_id = created.json()["workspace_id"]
            workspace_ids.append(workspace_id)
            headers = {"X-Neraium-Workspace-Id": workspace_id}
            _configure_systems(client, "shared-system", headers=headers)
            result = _upload(client, system_id="shared-system", headers=headers)
            models.append(result["sii_result"]["behavioral_model"]["model_id"])
            job_ids.append(result["job_id"])

        assert workspace_ids[0] != workspace_ids[1]
        assert models[0] != models[1]
        assert len(_v2_keys()) == 2
        denied = client.get(
            f"/api/data/intake/{job_ids[0]}/result",
            headers={"X-Neraium-Workspace-Id": workspace_ids[1]},
        )
        assert denied.status_code == 404


@pytest.mark.parametrize("configured_systems, requested_system_id, expected_reason", [
    (("system-a",), "payload-redirect", "requested_system_id_not_registered"),
    ((), None, "no_registered_system"),
])
def test_unresolved_upload_system_limits_only_phase4_and_writes_no_ledger(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    configured_systems: tuple[str, ...],
    requested_system_id: str | None,
    expected_reason: str,
) -> None:
    app = _production_app(monkeypatch, tmp_path)

    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        _configure_systems(client, *configured_systems)
        result = _upload(client, system_id=requested_system_id)

    assert result.get("phase4_system_identity") is None
    trace = result["processing_trace"]["phase4_system_identity"]
    assert trace["status"] == "unavailable"
    assert result["sii_result"]["signal_drift"]["status"] == "complete"
    assert result["sii_result"]["relationship_analysis"]["status"] == "complete"
    assert result["sii_result"]["covariance_analysis"]["status"] == "complete"
    behavioral_model = result["sii_result"]["behavioral_model"]
    assert behavioral_model["status"] == "limited"
    assert behavioral_model["processing_trace"]["storage_writes"] == []
    assert not _v2_keys()
    status = result.get("phase4_system_identity_status")
    reason = result.get("phase4_system_identity_reason")
    if status is not None:
        assert status == "unavailable"
    if reason is not None:
        assert reason == expected_reason


def test_replay_reuses_original_system_identity_without_phase4_write(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _production_app(monkeypatch, tmp_path)

    with TestClient(app, base_url="https://testserver") as client:
        _login(client)
        _configure_systems(client, "replay-system")
        result = _upload(client, system_id="replay-system")

    job_id = str(result["job_id"])
    before_keys = _v2_keys()
    replay = data_router.rebuild_upload_replay_from_source(job_id)
    after_keys = _v2_keys()

    assert replay["job_id"] == job_id
    assert replay["meta"]["phase4_system_identity"] == result["phase4_system_identity"]
    assert replay["frame_count"] >= 0
    assert before_keys == after_keys
