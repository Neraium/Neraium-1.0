from __future__ import annotations

from fastapi import Request
from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.core.security import require_api_access
from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.main import create_app
from app.services.dataset_scope import build_dataset_scope, set_current_dataset_scope
from app.services.phase4_scope import set_current_authenticated_phase4_scope
from app.services.workspace_authorization import WorkspaceContext, set_current_workspace_context


def _client(tmp_path, *, app_env: str, role: str) -> TestClient:
    settings = Settings(
        app_env=app_env,
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=(
            ["https://app.neraium.com"] if app_env == "production" else ["*"]
        ),
        runtime_dir=tmp_path,
    )
    app = create_app(settings)

    async def authorize(request: Request) -> None:
        dataset_scope = build_dataset_scope(
            tenant_id="tenant-a",
            user_id=f"{role}@example.com",
            workspace_id="ws-facility-a",
        )
        workspace = WorkspaceContext(
            workspace_id="ws-facility-a",
            display_name="Facility A",
            kind="facility",
            membership_active=True,
            dataset_scope=dataset_scope,
        )
        request.state.auth_context = {
            "authenticated": True,
            "auth_subject": f"{role}@example.com",
            "auth_role": role,
        }
        set_current_dataset_scope(dataset_scope)
        set_current_workspace_context(workspace)
        set_current_authenticated_phase4_scope(
            AuthenticatedPhase4Scope(
                tenant_scope_id=dataset_scope.tenant_id,
                workspace_id=workspace.workspace_id,
            )
        )

    app.dependency_overrides[require_api_access] = authorize
    return TestClient(app, base_url="https://testserver")


@pytest.mark.parametrize(
    ("path", "request_kwargs"),
    [
        (
            "/api/data/upload-session",
            {
                "json": {
                    "filename": "historical.csv",
                    "size_bytes": 128,
                    "content_type": "text/csv",
                }
            },
        ),
        (
            "/api/data/upload-session/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/complete",
            {"json": {}},
        ),
        (
            "/api/data/upload",
            {
                "files": {
                    "file": (
                        "historical.csv",
                        "timestamp,value\n2026-01-01T00:00:00Z,1\n",
                        "text/csv",
                    )
                }
            },
        ),
        ("/api/data/upload/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/retry", {}),
        ("/api/data/reset", {}),
    ],
)
def test_production_operator_cannot_mutate_historical_upload_state(
    tmp_path, path: str, request_kwargs: dict
) -> None:
    with _client(tmp_path, app_env="production", role="operator") as client:
        response = client.post(path, **request_kwargs)

    assert response.status_code == 403


def test_production_admin_retains_explicit_historical_import_compatibility(tmp_path) -> None:
    with _client(tmp_path, app_env="production", role="admin") as client:
        response = client.post(
            "/api/data/upload-session",
            json={
                "filename": "not-telemetry.txt",
                "size_bytes": 128,
                "content_type": "text/plain",
            },
        )

    # The request crossed the permission boundary and reached normal validation.
    assert response.status_code == 400
    assert response.json()["error_type"] == "unsupported_file_type"


def test_production_operator_cannot_review_or_rebuild_historical_dataset(tmp_path) -> None:
    with _client(tmp_path, app_env="production", role="operator") as client:
        response = client.patch(
            "/api/data/ingestion/v1/datasets/historical-dataset/review",
            json={
                "decisions": [
                    {
                        "signal_id": "sig_temperature_01234567",
                        "mapping_action": "exclude",
                    }
                ]
            },
        )

    assert response.status_code == 403


def test_production_admin_review_reaches_historical_dataset_boundary(tmp_path) -> None:
    with _client(tmp_path, app_env="production", role="admin") as client:
        response = client.patch(
            "/api/data/ingestion/v1/datasets/missing-dataset/review",
            json={
                "decisions": [
                    {
                        "signal_id": "sig_temperature_01234567",
                        "mapping_action": "exclude",
                    }
                ]
            },
        )

    assert response.status_code == 404


def test_nonproduction_historical_import_keeps_existing_role_compatibility(tmp_path) -> None:
    with _client(tmp_path, app_env="test", role="viewer") as client:
        response = client.post(
            "/api/data/upload-session",
            json={
                "filename": "not-telemetry.txt",
                "size_bytes": 128,
                "content_type": "text/plain",
            },
        )

    assert response.status_code == 400
    assert response.json()["error_type"] == "unsupported_file_type"
