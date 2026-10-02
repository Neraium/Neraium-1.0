"""Customer read projection of verified, persisted physical-endpoint executions."""

from __future__ import annotations

from typing import Any

from app.services.telemetry_analysis_service_v2 import read_verified_execution_context_v2
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_endpoint_execution_v2_repository import EndpointExecutionV2Error


def list_customer_executions_v2(
    *, repository: Any, lineage_repository: Any, execution_repository: Any,
    scope: TelemetryScopeRef, connection_id: str, source_run_id: str, limit: int,
) -> list[dict[str, Any]]:
    """List only executions that pass the existing customer detail verification."""
    run = repository.get_ingestion_run(scope, run_id=source_run_id)
    if run is None or str(run.get("connection_id")) != connection_id:
        raise EndpointExecutionV2Error("endpoint_execution_run_not_found")
    results = []
    for ref in execution_repository.list_execution_refs(
        scope, connection_id=connection_id, source_run_id=source_run_id, limit=limit,
    ):
        detail = read_customer_execution_v2(
            repository=repository, lineage_repository=lineage_repository,
            execution_repository=execution_repository, scope=scope,
            connection_id=connection_id, source_run_id=source_run_id, execution_ref=ref,
        )
        if (detail.get("contract_version") != "telemetry-customer-result.v2"
                or detail.get("result_id") != ref or detail.get("execution_ref") != ref
                or detail.get("connection_id") != connection_id
                or detail.get("source_run_id") != source_run_id
                or detail.get("lineage_verified") is not True):
            raise EndpointExecutionV2Error("endpoint_execution_verification_mismatch")
        results.append({key: detail[key] for key in (
            "contract_version", "result_id", "execution_ref", "connection_id",
            "source_run_id", "system_id", "asset_id", "lineage_verified",
        )})
    return results


def read_customer_execution_v2(
    *, repository: Any, lineage_repository: Any, execution_repository: Any,
    scope: TelemetryScopeRef, connection_id: str, source_run_id: str,
    execution_ref: str,
) -> dict[str, Any]:
    """Use only server-scoped stored identity and Phase 5 historical verification."""
    row = execution_repository.load_execution_row(scope, execution_ref=execution_ref)
    if row is None or str(row.get("connection_id")) != connection_id or str(row.get("source_run_id")) != source_run_id:
        raise EndpointExecutionV2Error("endpoint_execution_not_found")
    execution, window, pairs = read_verified_execution_context_v2(
        repository=repository, lineage_repository=lineage_repository,
        execution_repository=execution_repository, scope=scope,
        connection_id=connection_id, source_run_id=source_run_id,
        system_id=row["system_id"], asset_id=row["asset_id"],
        execution_ref=execution_ref,
    )
    pair_rows = execution_repository.list_window_pairs(scope, window_id=window.window_id)
    if len(pair_rows) != len(pairs):
        raise EndpointExecutionV2Error("endpoint_execution_relationship_mismatch")
    relationships = []
    for pair, pair_row in zip(pairs, pair_rows, strict=True):
        artifact = lineage_repository.read(scope, window=window, pair=pair)
        if artifact is None or artifact["ref"] != pair_row["artifact_ref"]:
            raise EndpointExecutionV2Error("endpoint_execution_lineage_mismatch")
        relationships.append({"pair": pair.as_dict(), "artifact": artifact})
    payload = execution["payload"]
    return {
        "contract_version": "telemetry-customer-result.v2",
        "result_id": execution["ref"],
        "execution_ref": execution["ref"],
        "analysis_window_id": window.window_id,
        "connection_id": connection_id,
        "source_run_id": source_run_id,
        "facility_id": scope.facility_id,
        "system_id": window.system_identity.system_id,
        "asset_id": window.asset_id,
        "schema_fingerprint": window.schema_fingerprint,
        "window_content_digest": window.content_digest,
        "result_digest": execution["result_digest"],
        "lineage_verified": True,
        "product_result": payload["result"],
        "physical_endpoints": [item.as_dict() for item in window.series],
        "relationships": relationships,
        "observation_lineage": [item.as_dict() for item in window.observation_lineage],
    }
