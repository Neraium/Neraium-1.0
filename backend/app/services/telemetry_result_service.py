"""Authorized durable retrieval for canonical connector analysis results."""

from __future__ import annotations

import base64
from collections.abc import Mapping
import json
import logging
import time
from typing import Any

from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_lineage import (
    ObservationLineage,
    observation_lineage_digest,
)
from app.services.telemetry_repository import TelemetryRepositoryError
from app.services.telemetry_result_artifact import (
    CanonicalResultArtifact,
    CanonicalResultArtifactError,
    decode_canonical_result_artifact,
)
from app.services.telemetry_result_projection import (
    CanonicalResultProjectionError,
    build_canonical_result_projection,
)


logger = logging.getLogger(__name__)


class TelemetryCanonicalResultServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int,
        message: str,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.safe_message = message
        self.retryable = retryable


def _not_found() -> TelemetryCanonicalResultServiceError:
    return TelemetryCanonicalResultServiceError(
        "telemetry_analysis_result_not_found",
        status_code=404,
        message="Analysis result not found.",
    )


def _unavailable() -> TelemetryCanonicalResultServiceError:
    return TelemetryCanonicalResultServiceError(
        "telemetry_analysis_result_unavailable",
        status_code=503,
        message="The completed analysis result is temporarily unavailable.",
        retryable=True,
    )


class TelemetryCanonicalResultService:
    """Read and verify immutable results without invoking analysis code."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime.require_available()
        self.repository = self.runtime.repository

    def _require_run(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        source_run_id: str,
    ) -> Mapping[str, Any]:
        try:
            run = self.repository.get_ingestion_run(scope, run_id=source_run_id)
        except (TelemetryRepositoryError, ValueError):
            raise _not_found() from None
        if run is None or str(run.get("connection_id") or "") != connection_id:
            logger.warning(
                "telemetry_canonical_result_authorization_rejected",
                extra={
                    "event": "telemetry_canonical_result_authorization_rejected",
                    "reason": "scoped_run_mismatch",
                },
            )
            raise _not_found()
        return run

    def list_results(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        source_run_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._require_run(
            scope, connection_id=connection_id, source_run_id=source_run_id
        )
        try:
            rows = self.repository.list_analysis_result_artifacts(
                scope,
                connection_id=connection_id,
                source_run_id=source_run_id,
                limit=limit,
            )
        except (TelemetryRepositoryError, ValueError):
            raise _unavailable() from None
        return [self._summary(row) for row in rows]

    def get_result(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        source_run_id: str,
        system_id: str,
        asset_id: str | None,
        result_id: str,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        row, artifact, execution, _lineage = self._load_verified(
            scope,
            connection_id=connection_id,
            source_run_id=source_run_id,
            system_id=system_id,
            asset_id=asset_id,
            result_id=result_id,
        )
        metadata = self._artifact_metadata(row, artifact)
        try:
            projection = build_canonical_result_projection(
                execution,
                artifact_metadata=metadata,
                scope={
                    "tenant_scope_id": scope.tenant_scope_id,
                    "workspace_id": scope.workspace_id,
                    "resource_scope_id": scope.resource_scope_id,
                    "facility_id": scope.facility_id,
                    "analysis_window_id": str(row["analysis_window_id"]),
                    "connection_id": connection_id,
                    "source_ingestion_run_id": source_run_id,
                    "source_run_id": source_run_id,
                    "system_id": system_id,
                    "asset_id": asset_id,
                    "window_start": row.get("window_start"),
                    "window_end": row.get("window_end"),
                    "authority_digest": row.get("authority_digest"),
                },
                lineage_verified=True,
            )
        except CanonicalResultProjectionError as error:
            logger.error(
                "telemetry_canonical_result_projection_failed",
                extra={
                    "event": "telemetry_canonical_result_projection_failed",
                    "result_id": result_id,
                    "window_id": str(row.get("analysis_window_id") or ""),
                    "error_code": str(error)[:160],
                },
            )
            raise _unavailable() from None
        retrieval_ms = round((time.perf_counter() - started) * 1000, 3)
        response = {
            **self._summary(row),
            "authority_digest": str(row["authority_digest"]),
            "reference_metadata": dict(artifact.reference_metadata),
            "payload_encoding": artifact.payload_encoding,
            "projection_bytes": projection.projection_bytes,
            "shared_envelope_bytes": projection.shared_envelope_bytes,
            "technical_channels_bytes": projection.technical_channels_bytes,
            "evidence_audit_bytes": projection.evidence_audit_bytes,
            "projection_serialization_ms": projection.serialization_ms,
            "retrieval_ms": retrieval_ms,
            "lineage_verified": True,
            "product_result": projection.product_result,
        }
        logger.info(
            "telemetry_canonical_result_retrieved",
            extra={
                "event": "telemetry_canonical_result_retrieved",
                "result_id": result_id,
                "window_id": str(row.get("analysis_window_id") or ""),
                "payload_digest": artifact.payload_digest,
                "projection_bytes": projection.projection_bytes,
                "retrieval_ms": retrieval_ms,
            },
        )
        return response

    def get_lineage_page(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        source_run_id: str,
        system_id: str,
        asset_id: str | None,
        result_id: str,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        row = self._lineage_metadata(
            scope,
            connection_id=connection_id,
            source_run_id=source_run_id,
            system_id=system_id,
            asset_id=asset_id,
            result_id=result_id,
        )
        bounded_limit = min(max(int(limit), 1), 5_000)
        try:
            records = self.repository.list_analysis_result_lineage_records(
                scope,
                connection_id=connection_id,
                source_run_id=source_run_id,
                system_id=system_id,
                asset_id=asset_id,
                result_id=result_id,
            )
            lineage = tuple(
                ObservationLineage.from_observation(item) for item in records
            )
            self._verify_lineage(
                lineage,
                row=row,
                connection_id=connection_id,
                system_id=system_id,
                asset_id=asset_id,
            )
            start = 0
            if cursor is not None:
                cursor_identity = self._decode_cursor(cursor)
                expected_cursor_identity = {
                    "result_id": str(row["id"]),
                    "payload_digest": str(row["payload_digest"]),
                    "lineage_digest": str(row["observation_lineage_digest"]),
                }
                if any(
                    cursor_identity.get(key) != value
                    for key, value in expected_cursor_identity.items()
                ):
                    raise _not_found()
                positions = [
                    index
                    for index, item in enumerate(lineage)
                    if item.observation_id == cursor_identity["observation_id"]
                ]
                if len(positions) != 1:
                    raise _not_found()
                start = positions[0] + 1
            page = lineage[start : start + bounded_limit]
            has_more = start + len(page) < len(lineage)
        except TelemetryCanonicalResultServiceError:
            raise
        except (
            CanonicalResultArtifactError,
            TelemetryRepositoryError,
            KeyError,
            TypeError,
            ValueError,
        ):
            raise _unavailable() from None
        next_cursor = (
            self._encode_cursor(
                page[-1].observation_id,
                result_id=str(row["id"]),
                payload_digest=str(row["payload_digest"]),
                lineage_digest=str(row["observation_lineage_digest"]),
            )
            if has_more and page
            else None
        )
        return {
            "result_id": str(row["id"]),
            "analysis_window_id": str(row["analysis_window_id"]),
            "observation_count": int(row["observation_count"]),
            "observation_lineage_digest": str(row["observation_lineage_digest"]),
            "lineage_verified": True,
            "records": [item.as_dict() for item in page],
            "next_cursor": next_cursor,
        }

    def _lineage_metadata(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        source_run_id: str,
        system_id: str,
        asset_id: str | None,
        result_id: str,
    ) -> Mapping[str, Any]:
        self._require_run(
            scope, connection_id=connection_id, source_run_id=source_run_id
        )
        try:
            row = self.repository.get_analysis_result_artifact_metadata(
                scope,
                connection_id=connection_id,
                source_run_id=source_run_id,
                system_id=system_id,
                asset_id=asset_id,
                result_id=result_id,
            )
        except (TelemetryRepositoryError, ValueError):
            row = None
        if row is None:
            logger.warning(
                "telemetry_canonical_result_authorization_rejected",
                extra={
                    "event": "telemetry_canonical_result_authorization_rejected",
                    "reason": "scoped_lineage_mismatch",
                },
            )
            raise _not_found()
        return row

    @staticmethod
    def _verify_lineage_scope(
        lineage: tuple[ObservationLineage, ...],
        *,
        row: Mapping[str, Any],
        connection_id: str,
        system_id: str,
        asset_id: str | None,
    ) -> None:
        if any(
            item.connection_id != connection_id
            or item.system_id != system_id
            or item.asset_id != asset_id
            or item.mapping_authority_digest
            != str(row.get("authority_digest") or "")
            for item in lineage
        ):
            raise CanonicalResultArtifactError(
                "canonical_result_lineage_scope_mismatch"
            )

    @classmethod
    def _verify_lineage(
        cls,
        lineage: tuple[ObservationLineage, ...],
        *,
        row: Mapping[str, Any],
        connection_id: str,
        system_id: str,
        asset_id: str | None,
    ) -> None:
        if (
            len(lineage) != int(row["observation_count"])
            or observation_lineage_digest(lineage)
            != str(row["observation_lineage_digest"])
        ):
            raise CanonicalResultArtifactError(
                "canonical_result_lineage_integrity_mismatch"
            )
        cls._verify_lineage_scope(
            lineage,
            row=row,
            connection_id=connection_id,
            system_id=system_id,
            asset_id=asset_id,
        )

    def _load_verified(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        source_run_id: str,
        system_id: str,
        asset_id: str | None,
        result_id: str,
    ) -> tuple[
        Mapping[str, Any],
        CanonicalResultArtifact,
        dict[str, Any],
        tuple[ObservationLineage, ...],
    ]:
        self._require_run(
            scope, connection_id=connection_id, source_run_id=source_run_id
        )
        try:
            row = self.repository.get_analysis_result_artifact(
                scope,
                connection_id=connection_id,
                source_run_id=source_run_id,
                system_id=system_id,
                asset_id=asset_id,
                result_id=result_id,
            )
        except (TelemetryRepositoryError, ValueError):
            row = None
        if row is None:
            logger.warning(
                "telemetry_canonical_result_authorization_rejected",
                extra={
                    "event": "telemetry_canonical_result_authorization_rejected",
                    "reason": "scoped_result_mismatch",
                },
            )
            raise _not_found()
        try:
            artifact = self._artifact(row)
            execution = decode_canonical_result_artifact(artifact)
            if (
                str(execution.get("window_id") or "")
                != str(row.get("analysis_window_id") or "")
                or str(execution.get("source_run_id") or "") != source_run_id
            ):
                raise CanonicalResultArtifactError(
                    "canonical_result_scoped_identity_mismatch"
                )
            records = self.repository.list_analysis_result_lineage_records(
                scope,
                connection_id=connection_id,
                source_run_id=source_run_id,
                system_id=system_id,
                asset_id=asset_id,
                result_id=result_id,
            )
            lineage = tuple(ObservationLineage.from_observation(item) for item in records)
            self._verify_lineage(
                lineage,
                row=row,
                connection_id=connection_id,
                system_id=system_id,
                asset_id=asset_id,
            )
        except (
            CanonicalResultArtifactError,
            TelemetryRepositoryError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            error_code = str(error)[:160]
            logger.error(
                "telemetry_canonical_result_schema_mismatch"
                if any(
                    marker in error_code
                    for marker in ("schema", "contract", "version")
                )
                else "telemetry_canonical_result_integrity_failed",
                extra={
                    "event": (
                        "telemetry_canonical_result_schema_mismatch"
                        if any(
                            marker in error_code
                            for marker in ("schema", "contract", "version")
                        )
                        else "telemetry_canonical_result_integrity_failed"
                    ),
                    "result_id": result_id,
                    "error_code": error_code,
                },
            )
            raise _unavailable() from None
        return row, artifact, execution, lineage

    @staticmethod
    def _artifact(row: Mapping[str, Any]) -> CanonicalResultArtifact:
        payload = row.get("payload")
        if isinstance(payload, memoryview):
            payload = payload.tobytes()
        if not isinstance(payload, bytes):
            raise CanonicalResultArtifactError("canonical_result_payload_missing")
        return CanonicalResultArtifact(
            result_id=str(row["id"]),
            analysis_window_id=str(row["analysis_window_id"]),
            source_run_id=str(row["source_ingestion_run_id"]),
            artifact_schema_version=str(row["artifact_schema_version"]),
            execution_contract_version=str(row["execution_contract_version"]),
            analysis_schema_version=str(row["analysis_schema_version"]),
            analysis_contract_version=str(row["analysis_contract_version"]),
            engine_name=(str(row["engine_name"]) if row.get("engine_name") else None),
            engine_version=(
                str(row["engine_version"]) if row.get("engine_version") else None
            ),
            reference_metadata=dict(row.get("reference_metadata") or {}),
            observation_count=int(row["observation_count"]),
            observation_lineage_digest=str(row["observation_lineage_digest"]),
            finding_ids=dict(row.get("finding_ids") or {}),
            evidence_ids=dict(row.get("evidence_ids") or {}),
            payload_encoding=str(row["payload_encoding"]),
            payload_digest=str(row["payload_digest"]),
            payload_uncompressed_bytes=int(row["payload_uncompressed_bytes"]),
            payload_stored_bytes=int(row["payload_stored_bytes"]),
            serialization_ms=float(row["serialization_ms"]),
            payload=payload,
        )

    @staticmethod
    def _artifact_metadata(
        row: Mapping[str, Any], artifact: CanonicalResultArtifact
    ) -> dict[str, Any]:
        return {
            "result_id": artifact.result_id,
            "analysis_window_id": str(row["analysis_window_id"]),
            "artifact_schema_version": artifact.artifact_schema_version,
            "execution_contract_version": artifact.execution_contract_version,
            "analysis_schema_version": artifact.analysis_schema_version,
            "analysis_contract_version": artifact.analysis_contract_version,
            "engine_name": artifact.engine_name,
            "engine_version": artifact.engine_version,
            "reference_metadata": dict(artifact.reference_metadata),
            "finding_ids": dict(artifact.finding_ids),
            "evidence_ids": dict(artifact.evidence_ids),
            "payload_digest": artifact.payload_digest,
            "payload_uncompressed_bytes": artifact.payload_uncompressed_bytes,
            "payload_stored_bytes": artifact.payload_stored_bytes,
            "serialization_ms": artifact.serialization_ms,
            "observation_count": artifact.observation_count,
            "observation_lineage_digest": artifact.observation_lineage_digest,
        }

    @staticmethod
    def _summary(row: Mapping[str, Any]) -> dict[str, Any]:
        finding_ids = row.get("finding_ids")
        evidence_ids = row.get("evidence_ids")
        completion = row.get("result_metadata")
        completion = completion if isinstance(completion, Mapping) else {}
        return {
            "result_id": str(row["id"]),
            "analysis_window_id": str(row["analysis_window_id"]),
            "connection_id": str(row["connection_id"]),
            "source_run_id": str(row["source_ingestion_run_id"]),
            "facility_id": str(row["facility_id"]),
            "system_id": str(row["system_id"]),
            "asset_id": str(row["asset_id"]) if row.get("asset_id") else None,
            "window_start": row["window_start"],
            "window_end": row["window_end"],
            "analytical_status": str(completion.get("status") or "completed"),
            "artifact_schema_version": str(row["artifact_schema_version"]),
            "execution_contract_version": str(row["execution_contract_version"]),
            "analysis_schema_version": str(row["analysis_schema_version"]),
            "analysis_contract_version": str(row["analysis_contract_version"]),
            "engine_name": str(row["engine_name"]) if row.get("engine_name") else None,
            "engine_version": (
                str(row["engine_version"]) if row.get("engine_version") else None
            ),
            "observation_count": int(row["observation_count"]),
            "observation_lineage_digest": str(row["observation_lineage_digest"]),
            "finding_count": int(
                (finding_ids or {}).get("total", 0)
                if isinstance(finding_ids, Mapping)
                else 0
            ),
            "evidence_count": int(
                (evidence_ids or {}).get("total", 0)
                if isinstance(evidence_ids, Mapping)
                else 0
            ),
            "payload_digest": str(row["payload_digest"]),
            "payload_uncompressed_bytes": int(row["payload_uncompressed_bytes"]),
            "payload_stored_bytes": int(row["payload_stored_bytes"]),
            "serialization_ms": float(row["serialization_ms"]),
            "created_at": row.get("created_at"),
        }

    @staticmethod
    def _encode_cursor(
        observation_id: str,
        *,
        result_id: str,
        payload_digest: str,
        lineage_digest: str,
    ) -> str:
        value = json.dumps(
            {
                "lineage_digest": lineage_digest,
                "observation_id": observation_id,
                "payload_digest": payload_digest,
                "result_id": result_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> dict[str, str]:
        try:
            padding = "=" * (-len(cursor) % 4)
            decoded = base64.b64decode(
                (cursor + padding).encode("ascii"), altchars=b"-_", validate=True
            )
            value = json.loads(decoded.decode("ascii"))
        except (
            UnicodeDecodeError,
            UnicodeEncodeError,
            ValueError,
            json.JSONDecodeError,
        ):
            raise _not_found() from None
        if not isinstance(value, Mapping) or set(value) != {
            "lineage_digest",
            "observation_id",
            "payload_digest",
            "result_id",
        }:
            raise _not_found()
        normalized = {key: str(item) for key, item in value.items()}
        if any(not item or len(item) > 128 for item in normalized.values()):
            raise _not_found()
        return normalized


__all__ = [
    "TelemetryCanonicalResultService",
    "TelemetryCanonicalResultServiceError",
]
