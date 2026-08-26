from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.auth_store import create_user
from app.services.rate_limiter import clear_rate_limits


EVIDENCE_PACKAGE_OPERATIONS = {
    ("get", "/api/data/analyses/{comparison_analysis_id}/evidence-package"):
        "evidence_package_by_analysis_id_api_data_analyses__comparison_analysis_id__evidence_package_get",
    ("get", "/api/data/evidence-packages/{package_id}"):
        "evidence_package_by_id_api_data_evidence_packages__package_id__get",
    ("post", "/api/data/evidence-packages/{package_id}/lifecycle-events"):
        "record_evidence_package_lifecycle_event_api_data_evidence_packages__package_id__lifecycle_events_post",
}
FINGERPRINT_OPERATIONS = {
    ("get", "/api/data/evidence-packages/{package_id}/fingerprint"):
        ("evidence_package_fingerprint_by_id", "EvidencePackageFingerprint"),
    ("get", "/api/data/evidence-packages/{package_id}/exact-matches"):
        ("evidence_package_exact_matches_by_id", "ExactMatchResult"),
    ("get", "/api/data/evidence-packages/{package_id}/approximate-similarity"):
        ("evidence_package_approximate_similarity_by_id", "ApproximateSimilarityResponse"),
    ("get", "/api/data/evidence-packages/{package_id}/historical-pattern"):
        ("evidence_package_historical_pattern_by_id", "HistoricalPatternResponse"),
}
CORRELATION_OPERATIONS = {
    ("get", "/api/data/evidence-packages/{package_id}/related-packages"):
        ("getEvidencePackageRelatedPackagesV1", "RelatedPackageSetResponse"),
}
HISTORICAL_INGESTION_OPERATIONS = {
    ("get", "/api/data/ingestion/v1/datasets/{dataset_id}"): "getHistoricalIngestionProfileV1",
    ("get", "/api/data/ingestion/v1/datasets/{dataset_id}/canonical"): "getHistoricalCanonicalDatasetV1",
    ("patch", "/api/data/ingestion/v1/datasets/{dataset_id}/review"): "reviewHistoricalIngestionDatasetV1",
}
FINDING_WORKFLOW_OPERATIONS = {
    ("get", "/api/findings"),
    ("get", "/api/findings/members"),
    ("get", "/api/findings/{finding_id}"),
    ("get", "/api/findings/{finding_id}/activity"),
    ("patch", "/api/findings/{finding_id}/workflow"),
    ("post", "/api/findings/{finding_id}/field-reports"),
    ("post", "/api/findings/{finding_id}/feedback"),
    ("post", "/api/findings/{finding_id}/resolution"),
}
WORKSPACE_AUTHORIZATION_OPERATIONS = {
    ("get", "/api/workspaces"),
    ("post", "/api/workspaces"),
    ("get", "/api/workspaces/current/members"),
    ("post", "/api/workspaces/{workspace_id}/members"),
    ("post", "/api/workspaces/{workspace_id}/members/{email}/disable"),
}
UPLOAD_PROGRESS_OPERATION = (
    "get",
    "/api/data/upload-status/{job_id}",
    "getUploadJobStatusV1",
    "UploadStatusResponse",
)
PRODUCTION_DATA_CONNECTION_OPERATIONS = {
    ("get", "/api/data-connections"): (
        "read_data_connections_api_data_connections_get",
        "200",
        "ConnectionsListResponse",
    ),
    ("post", "/api/data-connections"): (
        "create_data_connection_api_data_connections_post",
        "201",
        "ConnectionActionResponse",
    ),
    ("get", "/api/data-connections/providers"): (
        "list_data_connection_providers_api_data_connections_providers_get",
        "200",
        "ConnectorProvidersResponse",
    ),
    ("get", "/api/data-connections/signal-concepts"): (
        "list_signal_concepts_api_data_connections_signal_concepts_get",
        "200",
        "CanonicalSignalConceptsResponse",
    ),
    ("get", "/api/data-connections/{connection_id}"): (
        "read_data_connection_api_data_connections__connection_id__get",
        "200",
        "ConnectionPublicResponse",
    ),
    ("patch", "/api/data-connections/{connection_id}"): (
        "update_data_connection_api_data_connections__connection_id__patch",
        "200",
        "ConnectionActionResponse",
    ),
    ("delete", "/api/data-connections/{connection_id}"): (
        "archive_data_connection_api_data_connections__connection_id__delete",
        "200",
        "ConnectionActionResponse",
    ),
    ("put", "/api/data-connections/{connection_id}/credentials"): (
        "put_data_connection_credentials_api_data_connections__connection_id__credentials_put",
        "200",
        "CredentialStatusResponse",
    ),
    ("post", "/api/data-connections/{connection_id}/validate"): (
        "validate_data_connection_api_data_connections__connection_id__validate_post",
        "200",
        "ValidationResponse",
    ),
    ("post", "/api/data-connections/{connection_id}/discover"): (
        "discover_data_connection_signals_api_data_connections__connection_id__discover_post",
        "200",
        "DiscoveryResponse",
    ),
    ("get", "/api/data-connections/{connection_id}/signals"): (
        "list_data_connection_signals_api_data_connections__connection_id__signals_get",
        "200",
        "SignalsListResponse",
    ),
    ("put", "/api/data-connections/{connection_id}/signals/{signal_id}/mapping"): (
        "update_signal_mapping_api_data_connections__connection_id__signals__signal_id__mapping_put",
        "200",
        "MappingResponse",
    ),
    ("post", "/api/data-connections/{connection_id}/enable"): (
        "enable_data_connection_api_data_connections__connection_id__enable_post",
        "200",
        "ConnectionActionResponse",
    ),
    ("post", "/api/data-connections/{connection_id}/disable"): (
        "disable_data_connection_api_data_connections__connection_id__disable_post",
        "200",
        "ConnectionActionResponse",
    ),
    ("get", "/api/data-connections/{connection_id}/runs"): (
        "list_data_connection_runs_api_data_connections__connection_id__runs_get",
        "200",
        "IngestionRunsListResponse",
    ),
    ("get", "/api/data-connections/{connection_id}/errors"): (
        "list_data_connection_errors_api_data_connections__connection_id__errors_get",
        "200",
        "IngestionErrorsListResponse",
    ),
    ("post", "/api/data-connections/{connection_id}/runs/{run_id}/retry"): (
        "retry_data_connection_run_api_data_connections__connection_id__runs__run_id__retry_post",
        "202",
        "IngestionRunActionResponse",
    ),
    ("post", "/api/data-connections/{connection_id}/backfills"): (
        "start_data_connection_backfill_api_data_connections__connection_id__backfills_post",
        "202",
        "IngestionRunActionResponse",
    ),
    ("get", "/api/data-connections/{connection_id}/backfills/{run_id}"): (
        "read_data_connection_backfill_api_data_connections__connection_id__backfills__run_id__get",
        "200",
        "IngestionRunPublicResponse",
    ),
}


def production_client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    return TestClient(create_app(settings), base_url="https://testserver")


def test_unknown_body_and_query_fields_are_rejected(client: TestClient) -> None:
    body_response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "password123", "is_admin": True},
    )
    assert body_response.status_code == 422
    assert body_response.json()["error_type"] == "validation_error"
    assert body_response.json()["errors"][0]["type"] == "extra_forbidden"

    query_response = client.get("/api/evidence/runs?limit=10&sort=password_hash")
    assert query_response.status_code == 422
    assert query_response.json()["error_type"] == "http_422"
    assert query_response.json()["detail"]["fields"] == ["sort"]


def test_boundary_and_malformed_requests_use_consistent_errors(client: TestClient) -> None:
    cases = [
        client.get("/api/evidence/runs?limit=101"),
        client.get("/api/evidence/runs?offset=1000001"),
        client.get("/api/replay/timeline?intervals=1001"),
        client.get("/api/replay/timeline?mode=unapproved"),
        client.get("/api/evidence/export/missing?format=xml"),
        client.get(
            "/api/replay/range?start_timestamp=2026-01-02T00:00:00Z"
            "&end_timestamp=2026-01-01T00:00:00Z"
        ),
    ]
    for response in cases:
        assert response.status_code == 422
        payload = response.json()
        assert payload["error_type"] in {"validation_error", "http_422"}
        assert payload["detail"]
        assert payload["message"]

    malformed = client.post(
        "/api/auth/login",
        content=b'{"email":',
        headers={"content-type": "application/json"},
    )
    assert malformed.status_code == 422
    assert malformed.json()["error_type"] == "validation_error"


def test_payload_header_path_and_filename_limits(client: TestClient) -> None:
    oversized = client.post(
        "/api/auth/login",
        content=b"x" * (1_048_576 + 1),
        headers={"content-type": "application/json"},
    )
    assert oversized.status_code == 413
    assert oversized.json()["error_type"] == "payload_too_large"

    oversized_header = client.get("/api/health", headers={"X-Request-Id": "x" * 129})
    assert oversized_header.status_code == 400
    assert oversized_header.json()["error_type"] == "invalid_header"

    invalid_path = client.get(f"/api/evidence/runs/{'x' * 129}")
    assert invalid_path.status_code == 422

    invalid_filename = client.post(
        "/api/connectors/csv/upload",
        files={"file": ("x" * 252 + ".csv", "timestamp,value\n2026-01-01T00:00:00Z,1", "text/csv")},
    )
    assert invalid_filename.status_code == 410
    assert invalid_filename.json()["detail"]["code"] == "legacy_connection_operation_retired"


def test_unauthorized_forbidden_not_found_and_conflict_contracts(monkeypatch, tmp_path: Path) -> None:
    clear_rate_limits()
    client = production_client(monkeypatch, tmp_path)

    unauthorized = client.get("/api/observability/summary")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error_type"] == "auth"
    assert unauthorized.json()["detail"]

    create_user("operator@example.com", "password123", role="operator")
    login = client.post(
        "/api/auth/login",
        json={"email": "operator@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    forbidden = client.get("/api/observability/summary")
    assert forbidden.status_code == 403
    assert forbidden.json()["error_type"] == "auth"

    assert client.get("/api/evidence/runs/missing-run").status_code == 404
    assert client.get("/api/replay/missing-run").status_code == 404
    assert client.get("/api/data/intake/missing-run/result").status_code == 404
    assert client.get("/api/replay/frame/2099-01-01T00:00:00Z").status_code == 404

    create_user("admin@example.com", "password123", role="admin")
    admin_login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "password123"},
    )
    assert admin_login.status_code == 200
    first = client.post(
        "/api/auth/users",
        json={"email": "duplicate@example.com", "password": "password123", "role": "viewer"},
    )
    duplicate = client.post(
        "/api/auth/users",
        json={"email": "duplicate@example.com", "password": "password123", "role": "viewer"},
    )
    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error_type"] == "http_409"


def test_openapi_covers_runtime_routes_and_contract_metadata(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    schema_operations = {
        (method, path): operation
        for path, item in schema["paths"].items()
        for method, operation in item.items()
        if method in {"get", "post", "put", "patch", "delete"}
    }
    runtime_operation_keys = [
        (method.lower(), route.path)
        for route in client.app.routes
        if getattr(route, "methods", None)
        and getattr(route, "include_in_schema", False)
        for method in route.methods - {"HEAD", "OPTIONS"}
    ]
    runtime_operations = [
        route
        for route in client.app.routes
        if getattr(route, "methods", None)
        and getattr(route, "include_in_schema", False)
    ]
    assert len(runtime_operation_keys) == len(set(runtime_operation_keys))
    assert set(schema_operations) == set(runtime_operation_keys)
    operation_ids = [
        operation["operationId"] for operation in schema_operations.values()
    ]
    assert len(operation_ids) == len(set(operation_ids))
    for (method, path), (
        operation_id,
        success_status,
        response_model,
    ) in PRODUCTION_DATA_CONNECTION_OPERATIONS.items():
        operation = schema_operations[(method, path)]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["data-connections"]
        assert operation["responses"][success_status]["content"]["application/json"][
            "schema"
        ] == {"$ref": f"#/components/schemas/{response_model}"}
        matching_routes = [
            route
            for route in runtime_operations
            if route.path == path and route.methods == {method.upper()}
        ]
        assert len(matching_routes) == 1
        assert "require_api_access" in {
            dependency.call.__name__
            for dependency in matching_routes[0].dependant.dependencies
        }
    operations = list(schema_operations.values())
    for (method, path), operation_id in EVIDENCE_PACKAGE_OPERATIONS.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["data"]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/EvidencePackage"
        }
        matching_routes = [
            route for route in runtime_operations
            if route.path == path and route.methods == {method.upper()}
        ]
        assert len(matching_routes) == 1
        assert "require_api_access" in {
            dependency.call.__name__ for dependency in matching_routes[0].dependant.dependencies
        }
    for (method, path), (operation_id, model) in FINGERPRINT_OPERATIONS.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}"
        }
    for (method, path), (operation_id, model) in CORRELATION_OPERATIONS.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["data"]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": f"#/components/schemas/{model}"
        }
        matching_routes = [
            route for route in runtime_operations
            if route.path == path and route.methods == {method.upper()}
        ]
        assert len(matching_routes) == 1
        assert "require_api_access" in {
            dependency.call.__name__ for dependency in matching_routes[0].dependant.dependencies
        }
    for (method, path), operation_id in HISTORICAL_INGESTION_OPERATIONS.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        assert operation["tags"] == ["historical-ingestion"]
        matching_routes = [
            route for route in runtime_operations
            if route.path == path and route.methods == {method.upper()}
        ]
        assert len(matching_routes) == 1
        dependency_names = {
            dependency.call.__name__ for dependency in matching_routes[0].dependant.dependencies
        }
        assert "require_api_access" in dependency_names
        if method == "patch":
            assert "require_historical_upload_access" in dependency_names
    for method, path in FINDING_WORKFLOW_OPERATIONS:
        operation = schema["paths"][path][method]
        assert operation["tags"] == ["findings"]
        matching_routes = [
            route for route in runtime_operations
            if route.path == path and route.methods == {method.upper()}
        ]
        assert len(matching_routes) == 1
        dependency_names = {
            dependency.call.__name__ for dependency in matching_routes[0].dependant.dependencies
        }
        assert "require_api_access" in dependency_names
        if (method, path) in {
            ("post", "/api/findings/{finding_id}/feedback"),
            ("post", "/api/findings/{finding_id}/resolution"),
        }:
            # These handlers intentionally resolve the workspace-scoped
            # finding before applying the operator policy, so foreign IDs stay
            # an opaque 404 even for a viewer.  The role check therefore lives
            # inside the endpoint rather than in FastAPI's pre-handler graph.
            assert matching_routes[0].endpoint.__name__ in {
                "submit_finding_feedback",
                "submit_finding_resolution",
            }
    progress_method, progress_path, progress_operation_id, progress_model = UPLOAD_PROGRESS_OPERATION
    progress_operation = schema["paths"][progress_path][progress_method]
    assert progress_operation["operationId"] == progress_operation_id
    assert progress_operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": f"#/components/schemas/{progress_model}"
    }
    progress_schema = schema["components"]["schemas"]["JobProgress"]
    assert progress_schema["additionalProperties"] is False
    assert progress_schema["properties"]["contract_version"]["const"] == "job-progress.v1"
    lifecycle_operation = schema["paths"]["/api/data/evidence-packages/{package_id}/lifecycle-events"]["post"]
    assert lifecycle_operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/LifecycleTransitionRequest"
    }
    lifecycle_route = next(
        route for route in runtime_operations
        if route.path == "/api/data/evidence-packages/{package_id}/lifecycle-events" and route.methods == {"POST"}
    )
    assert "require_operator_role" in {
        dependency.call.__name__ for dependency in lifecycle_route.dependant.dependencies
    }
    assert "/api/infrastructure/health" in schema["paths"]
    assert "/api/telemetry/ingest" in schema["paths"]
    assert "/api/telemetry/signal-mappings" in schema["paths"]
    assert "/api/telemetry/ingestion-health" in schema["paths"]
    assert "/api/live-analysis/configurations" in schema["paths"]
    assert "/api/live-analysis/systems/{system_id}/runs" in schema["paths"]
    assert "/api/live-analysis/findings" in schema["paths"]
    assert "/api/live-analysis/health" in schema["paths"]
    assert "/api/data/jobs/{job_id}/result" in schema["paths"]
    assert "/api/data/datasets/{dataset_id}/baseline" in schema["paths"]
    assert "/api/data/portfolios/{portfolio_id}/baselines/{model_id}" in schema["paths"]
    assert "/api/data/portfolios/{portfolio_id}/systems/{system_id}/baselines/{baseline_id}/analyses/{analysis_run_id}" in schema["paths"]
    assert "/api/data/analyses/{comparison_analysis_id}" in schema["paths"]
    assert "/api/data/analyses/{comparison_analysis_id}/findings" in schema["paths"]
    for operation in operations:
        assert operation.get("operationId")
        assert operation.get("tags") or operation["operationId"] in {
            "read_root__get", "health_check_alias_health_get",
            "latest_upload_alias_latest_upload_get", "systems_alias_systems_get",
            "read_startup_status_api_startup_status_get", "read_route_debug_api_routes_debug_get",
        }
        for status_code in ("400", "401", "403", "404", "409", "413", "422", "500"):
            assert status_code in operation["responses"]

    assert schema["paths"]["/latest-upload"]["get"]["deprecated"] is True
    assert schema["paths"]["/systems"]["get"]["deprecated"] is True
    login_schema = schema["components"]["schemas"]["LoginRequest"]
    assert login_schema["additionalProperties"] is False
    assert login_schema["properties"]["email"]["maxLength"] == 320
