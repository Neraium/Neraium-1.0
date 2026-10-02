"""Opt-in PostgreSQL storage/readback for immutable V2 endpoint lineage."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.services.authority_contract_common import canonical_json_bytes
from app.services.relationship_lineage_v2 import (
    ARTIFACT_CONTRACT,
    RelationshipLineageV2Error,
    build_artifact,
    issue,
    readback,
)
from app.services.telemetry_analysis_window_v2 import EndpointAnalysisWindowV2, EndpointRelationshipPairV2
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_repository import PostgreSQLTelemetryRepository, _row_dict, _scope_parameters


class EndpointLineageV2Conflict(RelationshipLineageV2Error):
    """An immutable lineage key names different bytes or authority."""


class PostgreSQLEndpointLineageV2Repository(PostgreSQLTelemetryRepository):
    """Separate V2 adapter; the V1 artifact repository is unchanged."""

    def persist(
        self, scope: TelemetryScopeRef, *, window: EndpointAnalysisWindowV2,
        pair: EndpointRelationshipPairV2, result: Mapping[str, Any],
        evidence: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(scope, TelemetryScopeRef) or not isinstance(window, EndpointAnalysisWindowV2) or scope != window.scope:
            raise EndpointLineageV2Conflict("relationship_v2_scope_mismatch")
        artifact = build_artifact(window, pair, result=result, evidence=evidence)
        readback(artifact, window=window, pair=pair)
        lineage = artifact["payload"]["lineage"]
        descriptor = lineage["payload"]
        payload_json = canonical_json_bytes(artifact).decode("utf-8")
        with self._connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO telemetry.relationship_lineage_artifacts_v2 (
                    artifact_ref, lineage_ref, contract_version,
                    resource_scope_id, tenant_scope_id, workspace_id, facility_id,
                    system_id, asset_id, window_id, source_run_id,
                    schema_fingerprint, window_content_digest, pair_ref,
                    source_endpoint_id, target_endpoint_id, artifact_payload
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s::JSONB
                ) ON CONFLICT DO NOTHING
                """,
                (
                    artifact["ref"], lineage["ref"], ARTIFACT_CONTRACT,
                    *_scope_parameters(scope), descriptor["scope"]["system_id"],
                    descriptor["scope"]["asset_id"], window.window_id,
                    window.source_run_id, window.schema_fingerprint,
                    window.content_digest, pair.ref, pair.source.endpoint_id,
                    pair.target.endpoint_id, payload_json,
                ),
            )
            stored = self._read_cursor(cursor, scope, lineage["ref"])
            if stored is None or stored.get("artifact_ref") != artifact["ref"]:
                raise EndpointLineageV2Conflict("relationship_v2_immutable_conflict")
            self._verify_row(stored, window, pair, artifact)
        return artifact

    def read(
        self, scope: TelemetryScopeRef, *, window: EndpointAnalysisWindowV2,
        pair: EndpointRelationshipPairV2,
    ) -> dict[str, Any] | None:
        if not isinstance(scope, TelemetryScopeRef) or not isinstance(window, EndpointAnalysisWindowV2) or scope != window.scope:
            raise EndpointLineageV2Conflict("relationship_v2_scope_mismatch")
        lineage = issue(window, pair)
        with self._connection() as connection, connection.cursor() as cursor:
            stored = self._read_cursor(cursor, scope, lineage["ref"])
        if stored is None:
            return None
        return self._verify_row(stored, window, pair)

    @staticmethod
    def _read_cursor(cursor: Any, scope: TelemetryScopeRef, lineage_ref: str) -> dict[str, Any] | None:
        cursor.execute(
            """
            SELECT artifact_ref, lineage_ref, contract_version,
                   resource_scope_id, tenant_scope_id, workspace_id, facility_id,
                   system_id, asset_id, window_id, source_run_id,
                   schema_fingerprint, window_content_digest, pair_ref,
                   source_endpoint_id, target_endpoint_id, artifact_payload
            FROM telemetry.relationship_lineage_artifacts_v2
            WHERE resource_scope_id = %s AND tenant_scope_id = %s
              AND workspace_id = %s AND facility_id = %s AND lineage_ref = %s
            """,
            (*_scope_parameters(scope), lineage_ref),
        )
        return _row_dict(cursor, cursor.fetchone())

    @staticmethod
    def _verify_row(
        row: Mapping[str, Any], window: EndpointAnalysisWindowV2,
        pair: EndpointRelationshipPairV2, expected: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        descriptor = issue(window, pair)
        scope = window.scope
        checks = {
            "artifact_ref": expected["ref"] if expected is not None else row.get("artifact_ref"),
            "lineage_ref": descriptor["ref"],
            "contract_version": ARTIFACT_CONTRACT,
            "resource_scope_id": scope.resource_scope_id,
            "tenant_scope_id": scope.tenant_scope_id,
            "workspace_id": scope.workspace_id,
            "facility_id": scope.facility_id,
            "system_id": window.system_identity.system_id,
            "asset_id": window.asset_id,
            "window_id": window.window_id,
            "source_run_id": window.source_run_id,
            "schema_fingerprint": window.schema_fingerprint,
            "window_content_digest": window.content_digest,
            "pair_ref": pair.ref,
            "source_endpoint_id": pair.source.endpoint_id,
            "target_endpoint_id": pair.target.endpoint_id,
        }
        if any(row.get(key) != value for key, value in checks.items()):
            raise EndpointLineageV2Conflict("relationship_v2_stored_authority_mismatch")
        artifact = readback(row.get("artifact_payload"), window=window, pair=pair)
        if artifact["ref"] != row["artifact_ref"] or (
            expected is not None and artifact != expected
        ):
            raise EndpointLineageV2Conflict("relationship_v2_stored_digest_mismatch")
        return artifact
