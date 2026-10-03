"""Customer V2 retrieval contract and authenticated route isolation."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.core.security import require_api_access
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_endpoint_execution_v2_repository import EndpointExecutionV2Error
from app.services.telemetry_endpoint_result_v2 import list_customer_executions_v2, read_customer_execution_v2
from test_telemetry_connection_api import _connection_payload, build_client
from test_telemetry_analysis_window_v2 import _scope


def test_customer_read_uses_server_row_identity_and_verified_context(monkeypatch) -> None:
    from app.services import telemetry_endpoint_result_v2 as module

    scope = _scope()
    connection_id, run_id = str(uuid4()), str(uuid4())
    ref = "telemetry-endpoint-execution.v2:" + "a" * 64
    rows = [{"system_id": "system-a", "asset_id": "pump-1", "connection_id": connection_id,
             "source_run_id": run_id}]
    seen = []

    class Executions:
        def load_execution_row(self, supplied_scope, *, execution_ref):
            seen.append((supplied_scope, execution_ref))
            return rows[0] if supplied_scope == scope else None

        def list_window_pairs(self, supplied_scope, *, window_id):
            return [{"artifact_ref": "artifact-a"}]

    class Lineage:
        artifact_ref = "artifact-a"

        def read(self, supplied_scope, *, window, pair):
            return {"ref": self.artifact_ref, "payload": {"evidence": "stored"}}

    class Item:
        def __init__(self, value):
            self.value = value

        def as_dict(self):
            return self.value

    class Window:
        window_id = str(uuid4())
        schema_fingerprint = "schema-v2"
        content_digest = "digest-v2"
        asset_id = "pump-1"
        system_identity = type("Identity", (), {"system_id": "system-a"})()
        series = [Item({"series_id": "endpoint-a", "canonical_concept_id": "concept-x"}),
                  Item({"series_id": "endpoint-b", "canonical_concept_id": "concept-x"})]
        observation_lineage = [Item({"observation_id": "observation-a"})]

    class Pair:
        def as_dict(self):
            return {"source_endpoint": "endpoint-a", "target_endpoint": "endpoint-b"}

    def verified(**kwargs):
        assert kwargs["system_id"] == "system-a" and kwargs["asset_id"] == "pump-1"
        assert kwargs["scope"] == scope
        return ({"ref": ref, "result_digest": "result-digest",
                 "payload": {"result": {"status": "complete", "score": 7}}}, Window(), (Pair(),))

    monkeypatch.setattr(module, "read_verified_execution_context_v2", verified)
    lineage = Lineage()
    args = dict(repository=object(), lineage_repository=lineage,
                execution_repository=Executions(), scope=scope,
                connection_id=connection_id, source_run_id=run_id, execution_ref=ref)
    first = read_customer_execution_v2(**args)
    assert read_customer_execution_v2(**args) == first
    assert first["product_result"] == {"status": "complete", "score": 7}
    assert first["physical_endpoints"][0]["canonical_concept_id"] == first["physical_endpoints"][1]["canonical_concept_id"]
    assert first["physical_endpoints"][0]["series_id"] != first["physical_endpoints"][1]["series_id"]
    assert first["relationships"][0]["artifact"]["payload"]["evidence"] == "stored"
    assert first["lineage_verified"] is True
    assert len(seen) == 2
    lineage.artifact_ref = "tampered-artifact"
    with pytest.raises(EndpointExecutionV2Error, match="lineage_mismatch"):
        read_customer_execution_v2(**args)
    lineage.artifact_ref = "artifact-a"
    rows[0]["source_run_id"] = str(uuid4())
    with pytest.raises(EndpointExecutionV2Error, match="not_found"):
        read_customer_execution_v2(**args)
    rows[0]["source_run_id"] = run_id
    with pytest.raises(EndpointExecutionV2Error, match="not_found"):
        read_customer_execution_v2(**{**args, "scope": type(scope)(
            tenant_scope_id="other-tenant", workspace_id=scope.workspace_id,
            resource_scope_id=canonical_phase4_resource_scope_id("other-tenant", scope.workspace_id),
            facility_id=scope.facility_id,
        )})


def test_v2_route_requires_auth_scope_and_supported_version(tmp_path, monkeypatch) -> None:
    from app.routers import data_connections as route
    from app.services.telemetry_runtime import telemetry_runtime_from_app

    app, _ = build_client(tmp_path)
    runtime = telemetry_runtime_from_app(app)
    runtime.execution_identity_version = "physical-endpoint-keyed.v2"
    monkeypatch.setattr(route, "PostgreSQLEndpointExecutionV2Repository", lambda factory: object())
    monkeypatch.setattr(route, "PostgreSQLEndpointLineageV2Repository", lambda factory: object())
    seen = []

    def read(**kwargs):
        seen.append(kwargs["scope"])
        return {"contract_version": "telemetry-customer-result.v2", "result_id": kwargs["execution_ref"]}

    monkeypatch.setattr(route, "read_customer_execution_v2", read)
    with TestClient(app, base_url="https://testserver") as client:
        runtime.repository._connection_factory = lambda: None
        created = client.post("/api/data-connections", json=_connection_payload())
        assert created.status_code == 201
        connection_id = created.json()["connection"]["connection_id"]
        run_id = str(uuid4())
        ref = "telemetry-endpoint-execution.v2:" + "a" * 64
        path = f"/api/data-connections/{connection_id}/runs/{run_id}/v2/analysis-results/{ref}"
        assert client.get(path).status_code == 200
        assert client.get(path + "?tenant_scope_id=forged&resource_scope_id=forged").status_code == 422
        assert len(seen) == 1
        assert client.get(path, headers={"X-Test-Workspace": "ws-other"}).status_code == 404
        assert len(seen) == 1
        runtime.execution_identity_version = "concept-keyed.v1"
        assert client.get(path).status_code == 404
        assert len(seen) == 1
        assert client.get(path.replace(".v2:", ".v1:")).status_code == 422
        app.dependency_overrides.pop(require_api_access)
        assert client.get(path).status_code in {401, 403}


def test_v2_list_verifies_each_execution_and_run_authority(monkeypatch) -> None:
    from app.services import telemetry_endpoint_result_v2 as module

    scope = _scope()
    connection_id, run_id = str(uuid4()), str(uuid4())
    ref = "telemetry-endpoint-execution.v2:" + "a" * 64

    class Repository:
        def get_ingestion_run(self, supplied_scope, *, run_id):
            assert supplied_scope == scope
            return {"connection_id": connection_id} if run_id == expected_run[0] else None

    class Executions:
        def list_execution_refs(self, supplied_scope, **kwargs):
            assert supplied_scope == scope
            assert kwargs == {"connection_id": connection_id, "source_run_id": run_id, "limit": 10}
            return [ref]

    expected_run = [run_id]
    details = []
    def read(**kwargs):
        details.append(kwargs)
        return {"contract_version": "telemetry-customer-result.v2", "result_id": ref,
                "execution_ref": ref, "connection_id": connection_id,
                "source_run_id": run_id, "system_id": "system-a", "asset_id": None,
                "lineage_verified": True}

    monkeypatch.setattr(module, "read_customer_execution_v2", read)
    args = dict(repository=Repository(), lineage_repository=object(), execution_repository=Executions(),
                scope=scope, connection_id=connection_id, source_run_id=run_id, limit=10)
    assert list_customer_executions_v2(**args)[0]["execution_ref"] == ref
    assert details[0]["scope"] == scope
    with pytest.raises(EndpointExecutionV2Error, match="run_not_found"):
        list_customer_executions_v2(**{**args, "connection_id": str(uuid4())})
    expected_run[0] = str(uuid4())
    with pytest.raises(EndpointExecutionV2Error, match="run_not_found"):
        list_customer_executions_v2(**args)
    expected_run[0] = run_id
    def unverifiable(**kwargs):
        raise EndpointExecutionV2Error("endpoint_execution_lineage_mismatch")
    monkeypatch.setattr(module, "read_customer_execution_v2", unverifiable)
    with pytest.raises(EndpointExecutionV2Error, match="lineage_mismatch"):
        list_customer_executions_v2(**args)
    monkeypatch.setattr(module, "read_customer_execution_v2", lambda **kwargs: {**read(**kwargs), "lineage_verified": False})
    with pytest.raises(EndpointExecutionV2Error, match="verification_mismatch"):
        list_customer_executions_v2(**args)


def test_v2_list_route_is_server_selected_and_scoped(tmp_path, monkeypatch, caplog) -> None:
    from app.routers import data_connections as route
    from app.services.telemetry_runtime import telemetry_runtime_from_app

    app, _ = build_client(tmp_path)
    runtime = telemetry_runtime_from_app(app)
    runtime.execution_identity_version = "physical-endpoint-keyed.v2"
    monkeypatch.setattr(route, "PostgreSQLEndpointExecutionV2Repository", lambda factory: object())
    monkeypatch.setattr(route, "PostgreSQLEndpointLineageV2Repository", lambda factory: object())
    seen = []
    def listed(**kwargs):
        seen.append(kwargs["scope"])
        return [{"contract_version": "telemetry-customer-result.v2", "result_id": "ref"}]
    monkeypatch.setattr(route, "list_customer_executions_v2", listed)
    with TestClient(app, base_url="https://testserver") as client:
        runtime.repository._connection_factory = lambda: None
        created = client.post("/api/data-connections", json=_connection_payload())
        connection_id = created.json()["connection"]["connection_id"]
        run_id = str(uuid4())
        base = f"/api/data-connections/{connection_id}/runs/{run_id}"
        for path in (f"{base}/analysis-results", f"{base}/v2/analysis-results"):
            assert client.get(path).json()["results"][0]["contract_version"] == "telemetry-customer-result.v2"
            assert client.get(path, headers={"X-Test-Workspace": "ws-other"}).status_code == 404
        assert len(seen) == 2
        monkeypatch.setattr(route, "list_customer_executions_v2", lambda **kwargs: (_ for _ in ()).throw(EndpointExecutionV2Error("corrupt")))
        assert client.get(f"{base}/analysis-results").status_code == 404
        assert client.get(f"{base}/v2/analysis-results").status_code == 404
        monkeypatch.setattr(route, "list_customer_executions_v2", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("db_unavailable")))
        with pytest.raises(RuntimeError, match="db_unavailable"):
            client.get(f"{base}/v2/analysis-results")
        assert "telemetry_v2_retrieval_failed" in caplog.text
        runtime.execution_identity_version = "concept-keyed.v1"
        assert client.get(f"{base}/v2/analysis-results").status_code == 404
        app.dependency_overrides.pop(require_api_access)
        assert client.get(f"{base}/v2/analysis-results").status_code in {401, 403}
