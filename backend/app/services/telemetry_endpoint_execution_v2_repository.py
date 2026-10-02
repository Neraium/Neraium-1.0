"""Immutable V2 run result and authorized endpoint-lineage readback."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from app.services.authority_contract_common import canonical_json_bytes
from app.services.relationship_evidence_binding import digest
from app.services.telemetry_analysis_window_v2 import EndpointAnalysisWindowV2, EndpointRelationshipPairV2
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_repository import PostgreSQLTelemetryRepository, _row_dict, _scope_parameters
from app.services.telemetry_result_artifact import _canonical_json_bytes as canonical_result_json_bytes

CONTRACT = "telemetry-endpoint-execution.v2"
MAX_EXECUTION_BYTES = 256 * 1024 * 1024


class EndpointExecutionV2Error(ValueError):
    """An execution or its stored endpoint authority is inconsistent."""


def _record(window: EndpointAnalysisWindowV2, result: Mapping[str, Any],
            pairs: Sequence[EndpointRelationshipPairV2]) -> dict[str, Any]:
    if not isinstance(window, EndpointAnalysisWindowV2) or not isinstance(result, Mapping):
        raise EndpointExecutionV2Error("endpoint_execution_contract_invalid")
    if not pairs or len({pair.ref for pair in pairs}) != len(pairs):
        raise EndpointExecutionV2Error("endpoint_execution_relationships_invalid")
    for pair in pairs:
        if not isinstance(pair, EndpointRelationshipPairV2) or window.relationship_pair(
            pair.source.endpoint_id, pair.target.endpoint_id
        ) != pair:
            raise EndpointExecutionV2Error("endpoint_execution_pair_mismatch")
    payload = {
        "contract_version": CONTRACT,
        "window": window.as_dict(),
        "result": json.loads(canonical_result_json_bytes(result)),
        "relationship_refs": sorted(pair.ref for pair in pairs),
    }
    encoded = canonical_json_bytes(payload)
    if len(encoded) > MAX_EXECUTION_BYTES:
        raise EndpointExecutionV2Error("endpoint_execution_too_large")
    return {
        "ref": digest(CONTRACT, {
            "window": payload["window"],
            "relationship_refs": payload["relationship_refs"],
        }),
        "result_digest": digest("telemetry-endpoint-result.v2", payload["result"]),
        "payload": payload,
    }


class PostgreSQLEndpointExecutionV2Repository(PostgreSQLTelemetryRepository):
    """Separate V2 table; V1 result artifacts and readback remain untouched."""

    def persist_execution(
        self, scope: TelemetryScopeRef, *, window: EndpointAnalysisWindowV2,
        result: Mapping[str, Any], pairs: Sequence[EndpointRelationshipPairV2],
        lineage_repository: Any,
    ) -> dict[str, Any]:
        if scope != window.scope:
            raise EndpointExecutionV2Error("endpoint_execution_scope_mismatch")
        record = _record(window, result, pairs)
        self._verify_lineage(scope, window, pairs, lineage_repository)
        payload = record["payload"]
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO telemetry.endpoint_analysis_executions_v2 (
                    execution_ref, contract_version, resource_scope_id, tenant_scope_id,
                    workspace_id, facility_id, system_id, asset_id, connection_id,
                    window_id, source_run_id, schema_fingerprint, window_content_digest,
                    window_payload, result_payload, result_digest, relationship_refs
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s::UUID, %s::UUID,
                    %s::UUID, %s, %s, %s::JSONB, %s, %s, %s::JSONB
                ) ON CONFLICT DO NOTHING
                """,
                (
                    record["ref"], CONTRACT, *_scope_parameters(scope),
                    window.system_identity.system_id, window.asset_id,
                    window.series[0].identity.connection_id, window.window_id,
                    window.source_run_id, window.schema_fingerprint,
                    window.content_digest,
                    canonical_json_bytes(payload["window"]).decode("utf-8"),
                    canonical_json_bytes(payload["result"]).decode("utf-8"),
                    record["result_digest"],
                    canonical_json_bytes(payload["relationship_refs"]).decode("utf-8"),
                ),
            )
        stored = self.read_execution(
            scope, window=window, pairs=pairs, lineage_repository=lineage_repository,
        )
        if stored is None:
            raise EndpointExecutionV2Error("endpoint_execution_missing")
        return stored

    def read_execution(
        self, scope: TelemetryScopeRef, *, window: EndpointAnalysisWindowV2,
        pairs: Sequence[EndpointRelationshipPairV2], lineage_repository: Any,
    ) -> dict[str, Any] | None:
        if scope != window.scope:
            raise EndpointExecutionV2Error("endpoint_execution_scope_mismatch")
        with self._connection() as connection, connection.cursor() as cursor:
            stored = self._read_cursor(cursor, scope, window.window_id)
        if stored is None:
            return None
        try:
            result = json.loads(stored.get("result_payload"))
        except (TypeError, ValueError) as exc:
            raise EndpointExecutionV2Error("endpoint_execution_result_corrupt") from exc
        if not isinstance(result, Mapping):
            raise EndpointExecutionV2Error("endpoint_execution_result_corrupt")
        expected = _record(window, result, pairs)
        return self._verify_row(stored, expected, scope, window, pairs, lineage_repository)

    def load_execution_row(self, scope: TelemetryScopeRef, *, execution_ref: str) -> dict[str, Any] | None:
        if not isinstance(execution_ref, str) or not execution_ref.startswith(CONTRACT + ":"):
            raise EndpointExecutionV2Error("endpoint_execution_ref_invalid")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT execution_ref, contract_version, resource_scope_id, tenant_scope_id,
                       workspace_id, facility_id, system_id, asset_id, connection_id,
                       window_id, source_run_id, schema_fingerprint, window_content_digest,
                       window_payload, result_payload, result_digest, relationship_refs
                FROM telemetry.endpoint_analysis_executions_v2
                WHERE resource_scope_id = %s AND tenant_scope_id = %s
                  AND workspace_id = %s AND facility_id = %s AND execution_ref = %s
                """,
                (*_scope_parameters(scope), execution_ref),
            )
            return _row_dict(cursor, cursor.fetchone())

    def list_execution_refs(self, scope: TelemetryScopeRef, *, connection_id: str,
                            source_run_id: str, limit: int) -> list[str]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT execution_ref FROM telemetry.endpoint_analysis_executions_v2
                WHERE resource_scope_id = %s AND tenant_scope_id = %s
                  AND workspace_id = %s AND facility_id = %s
                  AND connection_id = %s::UUID AND source_run_id = %s::UUID
                ORDER BY created_at DESC, execution_ref DESC LIMIT %s
                """,
                (*_scope_parameters(scope), connection_id, source_run_id, limit),
            )
            return [str(row[0]) for row in cursor.fetchall()]

    def load_window_row(self, scope: TelemetryScopeRef, *, window_id: str) -> dict[str, Any] | None:
        with self._connection() as connection, connection.cursor() as cursor:
            return self._read_cursor(cursor, scope, window_id)

    def list_window_pairs(self, scope: TelemetryScopeRef, *, window_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT pair_ref, source_endpoint_id, target_endpoint_id, artifact_ref
                FROM telemetry.relationship_lineage_artifacts_v2
                WHERE resource_scope_id = %s AND tenant_scope_id = %s
                  AND workspace_id = %s AND facility_id = %s AND window_id = %s
                ORDER BY pair_ref
                """,
                (*_scope_parameters(scope), window_id),
            )
            return [_row_dict(cursor, row) or {} for row in cursor.fetchall()]

    @staticmethod
    def _read_cursor(cursor: Any, scope: TelemetryScopeRef, window_id: str) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT execution_ref, contract_version, resource_scope_id, tenant_scope_id,
                   workspace_id, facility_id, system_id, asset_id, connection_id,
                   window_id, source_run_id, schema_fingerprint, window_content_digest,
                   window_payload, result_payload, result_digest, relationship_refs
            FROM telemetry.endpoint_analysis_executions_v2
            WHERE resource_scope_id = %s AND tenant_scope_id = %s
              AND workspace_id = %s AND facility_id = %s AND window_id = %s::UUID
            """,
            (*_scope_parameters(scope), window_id),
        )
        return _row_dict(cursor, cursor.fetchone())

    @staticmethod
    def _verify_lineage(scope: TelemetryScopeRef, window: EndpointAnalysisWindowV2,
                        pairs: Sequence[EndpointRelationshipPairV2], repository: Any) -> None:
        if repository is None or not callable(getattr(repository, "read", None)):
            raise EndpointExecutionV2Error("endpoint_execution_lineage_repository_required")
        for pair in pairs:
            artifact = repository.read(scope, window=window, pair=pair)
            if artifact is None:
                raise EndpointExecutionV2Error("endpoint_execution_lineage_missing")

    def _verify_row(self, row: Mapping[str, Any] | None, record: Mapping[str, Any],
                    scope: TelemetryScopeRef, window: EndpointAnalysisWindowV2,
                    pairs: Sequence[EndpointRelationshipPairV2], lineage_repository: Any) -> dict[str, Any]:
        if row is None:
            raise EndpointExecutionV2Error("endpoint_execution_missing")
        expected = {
            "execution_ref": record["ref"], "contract_version": CONTRACT,
            "resource_scope_id": scope.resource_scope_id,
            "tenant_scope_id": scope.tenant_scope_id,
            "workspace_id": scope.workspace_id, "facility_id": scope.facility_id,
            "system_id": window.system_identity.system_id, "asset_id": window.asset_id,
            "connection_id": window.series[0].identity.connection_id,
            "window_id": window.window_id, "source_run_id": window.source_run_id,
            "schema_fingerprint": window.schema_fingerprint,
            "window_content_digest": window.content_digest,
            "window_payload": record["payload"]["window"],
            "result_payload": canonical_json_bytes(record["payload"]["result"]).decode("utf-8"),
            "result_digest": record["result_digest"],
            "relationship_refs": record["payload"]["relationship_refs"],
        }
        for key, value in expected.items():
            actual = row.get(key)
            if (str(actual) != str(value) if key in {"connection_id", "window_id", "source_run_id"}
                    else actual != value):
                raise EndpointExecutionV2Error(f"endpoint_execution_stored_authority_mismatch:{key}")
        self._verify_lineage(scope, window, pairs, lineage_repository)
        return dict(record)
