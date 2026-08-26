"""Scoped API-side scheduling for durable telemetry runs and backfills.

This service never fetches provider data.  It creates/reads durable work that
the telemetry scheduler executes through the same normalization and
persistence path as incremental ingestion.
"""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any, Mapping
import uuid

from app.models.telemetry_api_models import BackfillCreateRequest
from app.services.telemetry_domain import ConnectorCapability
from app.services.telemetry_repository import TelemetryRepositoryError


class TelemetryRunServiceError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        message: str,
        status_code: int,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.status_code = status_code
        self.retryable = retryable


_UNSAFE_ERROR_TEXT = re.compile(
    r"https?://|authorization|bearer|api[_-]?key|secret|token|dsn|"
    r"\bsql\b|select\s|insert\s|update\s|delete\s|traceback|stack trace|"
    r"(?:^|\s)/(?:etc|home|var|tmp)/",
    re.IGNORECASE,
)


def _safe_error_summary(value: Any) -> str:
    summary = str(value or "").strip()
    if not summary or _UNSAFE_ERROR_TEXT.search(summary):
        return "Telemetry ingestion did not complete."
    return summary[:500]


def _repository_failure(error: TelemetryRepositoryError) -> TelemetryRunServiceError:
    code = str(error)
    if code in {
        "telemetry_backfill_already_active",
        "telemetry_active_backfill_exists",
    }:
        return TelemetryRunServiceError(
            "telemetry_backfill_already_active",
            message="A backfill is already active for this connection.",
            status_code=409,
        )
    if code in {
        "telemetry_ingestion_run_not_retryable",
        "telemetry_retry_already_active",
    }:
        return TelemetryRunServiceError(
            "telemetry_ingestion_run_not_retryable",
            message="This telemetry run cannot be retried.",
            status_code=409,
        )
    if code in {"telemetry_connection_not_found", "telemetry_ingestion_run_not_found"}:
        return TelemetryRunServiceError(
            "telemetry_resource_not_found",
            message="Telemetry resource not found.",
            status_code=404,
        )
    return TelemetryRunServiceError(
        "telemetry_repository_unavailable",
        message="Telemetry runs are temporarily unavailable.",
        status_code=503,
        retryable=True,
    )


class TelemetryBackfillService:
    """Schedule and inspect API-visible telemetry work without executing it."""

    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime.require_available()
        self.repository = self.runtime.repository

    @staticmethod
    def public_run(record: Mapping[str, Any]) -> dict[str, Any]:
        """Enumerate the public run contract, excluding worker-private state."""
        error_code = str(record.get("error_code") or "")
        if error_code and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", error_code
        ):
            error_code = "telemetry_ingestion_failed"
        return {
            "run_id": str(record.get("run_id") or record["id"]),
            "connection_id": str(record["connection_id"]),
            "mode": str(record["mode"]),
            "status": str(record["status"]),
            "range_start": record.get("range_start"),
            "range_end": record.get("range_end"),
            "started_at": record["started_at"],
            "finished_at": record.get("finished_at"),
            "attempt_count": int(record.get("attempt_count") or 0),
            "retry_count": int(record.get("retry_count") or 0),
            "pages_processed": int(
                record.get("pages_processed", record.get("pages", 0)) or 0
            ),
            "observations_received": int(record.get("observations_received") or 0),
            "observations_accepted": int(record.get("observations_accepted") or 0),
            "observations_rejected": int(record.get("observations_rejected") or 0),
            "observations_duplicate": int(record.get("observations_duplicate") or 0),
            "observations_out_of_order": int(
                record.get("observations_out_of_order") or 0
            ),
            "error_code": error_code or None,
            "error_summary": (
                _safe_error_summary(record.get("error_summary"))
                if record.get("error_summary") is not None
                else None
            ),
            "actor_id": (
                str(record["actor_id"])[:320]
                if record.get("actor_id") is not None
                else None
            ),
        }

    @staticmethod
    def public_error(record: Mapping[str, Any]) -> dict[str, Any]:
        reason_code = str(record.get("reason_code") or "telemetry_record_rejected")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", reason_code):
            reason_code = "telemetry_record_rejected"
        quality_state = str(record.get("quality_state") or "format_invalid")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,159}", quality_state):
            quality_state = "format_invalid"
        disposition = str(record.get("disposition") or "rejected")
        if disposition not in {"duplicate", "quarantined", "rejected"}:
            disposition = "rejected"
        external_tag_id = str(record.get("external_tag_id") or "")
        if external_tag_id and not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}", external_tag_id
        ):
            external_tag_id = ""
        return {
            "error_id": str(record["id"]),
            "run_id": str(record["ingestion_run_id"]),
            "external_signal_id": (
                str(record["external_signal_id"])
                if record.get("external_signal_id") is not None
                else None
            ),
            "external_tag_id": external_tag_id or None,
            "quality_state": quality_state,
            "reason_code": reason_code,
            "disposition": disposition,
            "occurrence_count": max(int(record.get("occurrence_count") or 1), 1),
            "first_seen_at": record["first_seen_at"],
            "last_seen_at": record["last_seen_at"],
        }

    def start_backfill(
        self,
        scope: Any,
        connection: Mapping[str, Any],
        payload: BackfillCreateRequest,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        if not bool(connection.get("enabled")):
            raise TelemetryRunServiceError(
                "telemetry_connection_not_enabled",
                message="Enable the telemetry connection before starting a backfill.",
                status_code=409,
            )
        capabilities = self.runtime.providers.capabilities(connection["connector_type"])
        if ConnectorCapability.BOUNDED_BACKFILL.value not in capabilities:
            raise TelemetryRunServiceError(
                "telemetry_backfill_not_supported",
                message="This telemetry connector does not support bounded backfill.",
                status_code=409,
            )
        now = datetime.now(UTC)
        try:
            record = self.repository.create_backfill_run(
                scope,
                run_id=str(uuid.uuid4()),
                connection_id=str(connection["id"]),
                range_start=payload.start_at,
                range_end=payload.end_at,
                actor_id=actor_id,
                requested_at=now,
            )
        except TelemetryRepositoryError as error:
            raise _repository_failure(error) from None
        except ValueError:
            raise TelemetryRunServiceError(
                "telemetry_backfill_invalid",
                message="The backfill request is invalid.",
                status_code=400,
            ) from None
        return self.public_run(record)

    def list_runs(
        self, scope: Any, *, connection_id: str, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        try:
            records = self.repository.list_ingestion_runs(
                scope, connection_id=connection_id, limit=limit, offset=offset
            )
        except TelemetryRepositoryError as error:
            raise _repository_failure(error) from None
        return [self.public_run(record) for record in records]

    def list_errors(
        self, scope: Any, *, connection_id: str, limit: int, offset: int
    ) -> list[dict[str, Any]]:
        try:
            records = self.repository.list_ingestion_errors(
                scope, connection_id=connection_id, limit=limit, offset=offset
            )
        except TelemetryRepositoryError as error:
            raise _repository_failure(error) from None
        return [self.public_error(record) for record in records]

    def get_run(
        self, scope: Any, *, connection_id: str, run_id: str
    ) -> dict[str, Any]:
        try:
            record = self.repository.get_ingestion_run(
                scope, run_id=run_id
            )
        except TelemetryRepositoryError as error:
            raise _repository_failure(error) from None
        if record is None or str(record.get("connection_id")) != str(connection_id):
            raise TelemetryRunServiceError(
                "telemetry_resource_not_found",
                message="Telemetry resource not found.",
                status_code=404,
            )
        return self.public_run(record)

    def retry_run(
        self,
        scope: Any,
        *,
        connection_id: str,
        run_id: str,
        actor_id: str,
    ) -> dict[str, Any]:
        source = self.get_run(scope, connection_id=connection_id, run_id=run_id)
        if source["status"] not in {"failed", "partial"}:
            raise TelemetryRunServiceError(
                "telemetry_ingestion_run_not_retryable",
                message="Only failed or partially completed telemetry runs can be retried.",
                status_code=409,
            )
        try:
            record = self.repository.retry_ingestion_run(
                scope,
                run_id=run_id,
                new_run_id=str(uuid.uuid4()),
                actor_id=actor_id,
                requested_at=datetime.now(UTC),
            )
        except TelemetryRepositoryError as error:
            raise _repository_failure(error) from None
        except ValueError:
            raise TelemetryRunServiceError(
                "telemetry_ingestion_run_not_retryable",
                message="This telemetry run cannot be retried.",
                status_code=409,
            ) from None
        return self.public_run(record)


__all__ = ["TelemetryBackfillService", "TelemetryRunServiceError"]
