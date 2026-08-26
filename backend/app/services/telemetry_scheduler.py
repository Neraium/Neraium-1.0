"""Lease-backed scheduler for one bounded telemetry retrieval page at a time."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
import hashlib
import json
import logging
import os
import random
import re
import socket
import threading
from typing import Any
import uuid

from app.connectors.base import (
    BoundedBackfillRange,
    ConnectorCheckpoint,
    ConnectorExecutionContext,
    TelemetryConnectorError,
)
from app.services.telemetry_domain import CheckpointMode, IngestionRunMode, TelemetryScopeRef
from app.services.telemetry_repository import (
    TelemetryCheckpointConflict,
    TelemetryLeaseLost,
    TelemetryRepositoryError,
)
from app.services.telemetry_runtime import TelemetryRuntimeUnavailable
from app.services.telemetry_secrets import SecretBinding
from app.services.worker_heartbeat import publish_telemetry_worker_heartbeat


logger = logging.getLogger(__name__)
_SAFE_CODE = re.compile(r"^[a-z][a-z0-9_]{0,127}$")
_SAFE_MESSAGE_CODE_PREFIXES = (
    "backfill_",
    "checkpoint_",
    "connector_",
    "ingestion_",
    "mapping_",
    "source_",
    "telemetry_",
)


@dataclass(frozen=True, slots=True)
class SchedulerRunResult:
    outcome: str
    connection_id: str | None = None
    run_id: str | None = None
    error_code: str | None = None
    analysis_status: str | None = None


class TelemetryScheduler:
    """Coordinate repository, provider, and pure normalization boundaries.

    The repository owns scope, leases, checkpoints, retry state, and atomic
    persistence. This service never derives scope or configuration from a
    provider response (or from browser input).
    """

    def __init__(
        self,
        *,
        repository: Any,
        providers: Any,
        normalize_page: Callable[..., Any],
        analyze_run: Callable[..., Any] | None = None,
        worker_id: str | None = None,
        lease_seconds: int = 120,
        poll_interval_seconds: float = 2.0,
        heartbeat_interval_seconds: float = 30.0,
        lease_heartbeat_interval_seconds: float | None = None,
        now: Callable[[], datetime] | None = None,
        jitter: Callable[[], float] | None = None,
        heartbeat: Callable[..., bool] = publish_telemetry_worker_heartbeat,
    ) -> None:
        self.repository = repository
        self.providers = providers
        self.normalize_page = normalize_page
        self.analyze_run = analyze_run
        self.worker_id = worker_id or _default_worker_id()
        self.lease_seconds = min(max(int(lease_seconds), 30), 3600)
        self.poll_interval_seconds = min(max(float(poll_interval_seconds), 0.1), 60.0)
        self.heartbeat_interval_seconds = min(
            max(float(heartbeat_interval_seconds), 1.0), 300.0
        )
        default_lease_heartbeat = min(self.lease_seconds / 3.0, 30.0)
        self.lease_heartbeat_interval_seconds = min(
            max(
                float(
                    default_lease_heartbeat
                    if lease_heartbeat_interval_seconds is None
                    else lease_heartbeat_interval_seconds
                ),
                0.1,
            ),
            max(self.lease_seconds / 2.0, 0.1),
        )
        self._now = now or (lambda: datetime.now(UTC))
        self._jitter = jitter or random.random
        self._heartbeat = heartbeat
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._thread_lock = threading.Lock()

    @property
    def running(self) -> bool:
        thread = self._thread
        return bool(thread and thread.is_alive())

    def start(self) -> bool:
        with self._thread_lock:
            if self.running:
                return False
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run_loop,
                name="telemetry-ingestion-scheduler",
                daemon=True,
            )
            self._thread.start()
        self._publish_heartbeat(status="starting", force=True)
        return True

    def stop(self, *, timeout_seconds: float = 30.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is None:
            return True
        thread.join(timeout=max(float(timeout_seconds), 0.0))
        stopped = not thread.is_alive()
        if stopped:
            with self._thread_lock:
                if self._thread is thread:
                    self._thread = None
            self._publish_heartbeat(status="stopped", force=True)
        else:
            logger.error(
                "telemetry_scheduler_shutdown_timeout",
                extra={"event": "telemetry_scheduler_shutdown_timeout"},
            )
        return stopped

    def run_once(self) -> SchedulerRunResult:
        claimed_at = _aware_utc(self._now(), code="telemetry_scheduler_clock_invalid")
        work = self.repository.claim_next_due_work(
            worker_id=self.worker_id,
            now=claimed_at,
            lease_seconds=self.lease_seconds,
        )
        if work is None:
            self._publish_heartbeat(status="healthy")
            return SchedulerRunResult("idle")
        if not isinstance(work, Mapping):
            raise RuntimeError("telemetry_claim_contract_invalid")

        connection_id = _required_text(work, "connection_id", fallback="id")
        run_id = _required_text(work, "run_id")
        lease_token = _required_text(work, "lease_token")
        scope = work.get("scope")
        if not isinstance(scope, TelemetryScopeRef):
            return self._fail_claimed(
                work=work,
                scope=None,
                connection_id=connection_id,
                run_id=run_id,
                lease_token=lease_token,
                error=ValueError("telemetry_persisted_scope_invalid"),
            )

        checkpoint_mode = _checkpoint_mode(work.get("checkpoint_mode"))
        try:
            snapshot = self.repository.load_ingestion_snapshot(
                scope,
                connection_id=connection_id,
                run_id=run_id,
                lease_token=lease_token,
                checkpoint_mode=checkpoint_mode.value,
            )
            if not isinstance(snapshot, Mapping):
                raise ValueError("telemetry_ingestion_snapshot_invalid")
            connection = snapshot.get("connection")
            if not isinstance(connection, Mapping):
                raise ValueError("telemetry_ingestion_connection_invalid")
            self._validate_persisted_scope(scope, snapshot, connection)

            # Disable can race a due-work claim. The repository completion call
            # releases the lease without scheduling another attempt.
            if not bool(connection.get("enabled", True)):
                completed_at = _aware_utc(
                    self._now(), code="telemetry_scheduler_clock_invalid"
                )
                self.repository.complete_ingestion_work(
                    scope,
                    connection_id=connection_id,
                    run_id=run_id,
                    lease_token=lease_token,
                    completed_at=completed_at,
                    next_attempt_at=None,
                    partial=True,
                )
                self._publish_heartbeat(status="healthy")
                return SchedulerRunResult("disabled", connection_id, run_id)

            context = self._provider_context(scope, connection_id, connection, snapshot)
            provider = self.providers.get(
                _required_text(connection, "connector_type"),
                configuration=context.configuration,
            )
            checkpoint = _connector_checkpoint(snapshot.get("checkpoint"))
            run_mode = _run_mode(work.get("run_mode"))
            if run_mode is IngestionRunMode.BACKFILL or (
                run_mode is IngestionRunMode.RETRY
                and _has_backfill_bounds(work, snapshot)
            ):
                time_range = _backfill_range(work, snapshot)
                page = provider.fetch_backfill(
                    context,
                    time_range=time_range,
                    checkpoint=checkpoint,
                )
            else:
                page = provider.fetch_incremental(context, checkpoint=checkpoint)

            mappings = _mapping_snapshots(
                snapshot.get("mappings"),
                scope=scope,
                connection_id=connection_id,
            )
            checkpoint_high_water = _field(snapshot.get("checkpoint"), "high_water_at")
            normalized = self.normalize_page(
                page=page,
                scope=scope,
                connection_id=connection_id,
                ingestion_run_id=run_id,
                mappings_by_external_tag=mappings,
                existing_source_record_digests=tuple(
                    snapshot.get("existing_source_record_digests") or ()
                ),
                high_watermark_utc=checkpoint_high_water,
                now=claimed_at,
            )
            observations = [
                _observation_record(item)
                for item in _sequence_field(normalized, "observations")
            ]
            rejections = [
                _rejection_record(item)
                for item in _sequence_field(normalized, "rejections")
            ]
            checkpoint_record = snapshot.get("checkpoint") or {}
            expected_revision = int(_field(checkpoint_record, "revision", 0) or 0)
            next_checkpoint = _field(normalized, "next_checkpoint") or checkpoint
            has_more = bool(_field(normalized, "has_more", page.has_more))
            if has_more:
                prior_cursor = checkpoint.cursor if checkpoint is not None else None
                continuation_cursor = (
                    next_checkpoint.cursor if next_checkpoint is not None else None
                )
                if continuation_cursor is None or continuation_cursor == prior_cursor:
                    raise ValueError("telemetry_continuation_checkpoint_invalid")
            cursor_payload = (
                {"cursor": next_checkpoint.cursor}
                if next_checkpoint is not None and next_checkpoint.cursor is not None
                else {}
            )
            high_water_at = _field(normalized, "high_watermark_utc")
            if high_water_at is None and next_checkpoint is not None:
                high_water_at = next_checkpoint.high_water_at
            self.repository.persist_ingestion_page(
                scope,
                connection_id=connection_id,
                run_id=run_id,
                lease_token=lease_token,
                checkpoint_mode=checkpoint_mode.value,
                expected_checkpoint_revision=expected_revision,
                cursor_payload=cursor_payload,
                high_water_at=high_water_at,
                observations=observations,
                rejections=rejections,
                received_count=int(
                    _field(
                        normalized,
                        "received_count",
                        len(page.observations) + len(page.issues),
                    )
                ),
                checkpoint_before_digest=_checkpoint_digest(checkpoint_record),
                checkpoint_after_digest=_checkpoint_digest(
                    {
                        "mode": checkpoint_mode.value,
                        "cursor_payload": cursor_payload,
                        "high_water_at": high_water_at,
                        "revision": expected_revision + 1,
                    }
                ),
            )

            if has_more:
                continued_at = _aware_utc(
                    self._now(), code="telemetry_scheduler_clock_invalid"
                )
                self.repository.continue_ingestion_work(
                    scope,
                    connection_id=connection_id,
                    run_id=run_id,
                    lease_token=lease_token,
                    continued_at=continued_at,
                    next_attempt_at=continued_at,
                )
                self._publish_heartbeat(status="healthy", processed_page=True)
                return SchedulerRunResult("continued", connection_id, run_id)

            renewed_at = _aware_utc(
                self._now(), code="telemetry_scheduler_clock_invalid"
            )
            if not self.repository.renew_lease(
                scope,
                connection_id=connection_id,
                lease_token=lease_token,
                lease_seconds=self.lease_seconds,
                now=renewed_at,
            ):
                raise TelemetryLeaseLost("telemetry_connection_lease_lost")
            analysis_status = self._analyze_final_run_with_lease_heartbeat(
                scope=scope,
                connection_id=connection_id,
                run_id=run_id,
                lease_token=lease_token,
            )
            completed_at = _aware_utc(
                self._now(), code="telemetry_scheduler_clock_invalid"
            )
            cadence = _polling_cadence_seconds(connection)
            # Persist a small bounded success jitter so many connections do not
            # become due in the same instant.
            delay = cadence * (0.9 + 0.2 * self._unit_jitter())
            self.repository.complete_ingestion_work(
                scope,
                connection_id=connection_id,
                run_id=run_id,
                lease_token=lease_token,
                completed_at=completed_at,
                next_attempt_at=completed_at + timedelta(seconds=max(delay, 0.1)),
                partial=bool(rejections),
            )
            self._publish_heartbeat(status="healthy", processed_page=True)
            return SchedulerRunResult(
                "processed",
                connection_id,
                run_id,
                analysis_status=analysis_status,
            )
        except TelemetryLeaseLost:
            self._publish_heartbeat(
                status="degraded", error_code="telemetry_connection_lease_lost"
            )
            return SchedulerRunResult(
                "lease_lost", connection_id, run_id, "telemetry_connection_lease_lost"
            )
        except Exception as error:
            return self._fail_claimed(
                work=work,
                scope=scope,
                connection_id=connection_id,
                run_id=run_id,
                lease_token=lease_token,
                error=error,
            )

    def _fail_claimed(
        self,
        *,
        work: Mapping[str, Any],
        scope: TelemetryScopeRef | None,
        connection_id: str,
        run_id: str,
        lease_token: str,
        error: Exception,
    ) -> SchedulerRunResult:
        del work
        error_code = _stable_error_code(error)
        if isinstance(error, TelemetryConnectorError):
            retryable = error.retryable
        elif isinstance(error, TelemetryCheckpointConflict):
            retryable = True
        elif isinstance(
            error,
            (
                KeyError,
                TelemetryRepositoryError,
                TelemetryRuntimeUnavailable,
                TypeError,
                ValueError,
            ),
        ):
            retryable = False
        else:
            retryable = True
        retry_after = (
            error.retry_after_seconds
            if isinstance(error, TelemetryConnectorError)
            else None
        )
        failure_status = "failed"
        if scope is not None:
            try:
                failure_result = self.repository.record_ingestion_failure(
                    scope,
                    connection_id=connection_id,
                    run_id=run_id,
                    lease_token=lease_token,
                    failed_at=_aware_utc(
                        self._now(), code="telemetry_scheduler_clock_invalid"
                    ),
                    error_code=error_code,
                    error_summary=None,
                    retryable=retryable,
                    retry_after_seconds=retry_after,
                    retry_jitter=self._unit_jitter(),
                )
                if isinstance(failure_result, Mapping):
                    failure_status = str(failure_result.get("status") or "failed")
            except TelemetryLeaseLost:
                return SchedulerRunResult(
                    "lease_lost",
                    connection_id,
                    run_id,
                    "telemetry_connection_lease_lost",
                )
        logger.warning(
            "telemetry_ingestion_page_failed",
            extra={
                "event": "telemetry_ingestion_page_failed",
                "connection_id": connection_id,
                "run_id": run_id,
                "error_code": error_code,
                "retryable": retryable,
            },
        )
        self._publish_heartbeat(status="degraded", error_code=error_code)
        outcome = "retry_scheduled" if failure_status == "pending" else "failed"
        return SchedulerRunResult(outcome, connection_id, run_id, error_code)

    @staticmethod
    def _validate_persisted_scope(
        scope: TelemetryScopeRef,
        snapshot: Mapping[str, Any],
        connection: Mapping[str, Any],
    ) -> None:
        if snapshot.get("scope") != scope:
            raise ValueError("telemetry_persisted_scope_mismatch")
        expected = {
            "tenant_scope_id": scope.tenant_scope_id,
            "workspace_id": scope.workspace_id,
            "resource_scope_id": scope.resource_scope_id,
            "facility_id": scope.facility_id,
        }
        for key, value in expected.items():
            if key in connection and str(connection.get(key) or "") != str(value):
                raise ValueError("telemetry_persisted_scope_mismatch")

    @staticmethod
    def _provider_context(
        scope: TelemetryScopeRef,
        connection_id: str,
        connection: Mapping[str, Any],
        snapshot: Mapping[str, Any],
    ) -> ConnectorExecutionContext:
        configuration = connection.get("safe_config")
        if not isinstance(configuration, Mapping):
            raise ValueError("telemetry_persisted_configuration_invalid")
        secret_binding = snapshot.get("secret_binding", connection.get("secret_binding"))
        if secret_binding is not None and not isinstance(secret_binding, SecretBinding):
            raise ValueError("telemetry_persisted_secret_binding_invalid")
        return ConnectorExecutionContext(
            connection_id=connection_id,
            resource_scope_id=scope.resource_scope_id,
            configuration=configuration,
            secret_binding=secret_binding,
        )

    def _unit_jitter(self) -> float:
        try:
            return min(max(float(self._jitter()), 0.0), 1.0)
        except (TypeError, ValueError):
            return 0.5

    def _analyze_final_run(
        self,
        *,
        scope: TelemetryScopeRef,
        connection_id: str,
        run_id: str,
    ) -> str | None:
        """Run the idempotent analysis handoff without coupling ingestion retry.

        Analysis owns its deterministic window state. Any analysis result, or a
        local invocation failure, still allows the durably persisted ingestion
        run to complete and therefore cannot cause a second connector fetch.
        """
        if self.analyze_run is None:
            return None
        try:
            result = self.analyze_run(
                repository=self.repository,
                scope=scope,
                connection_id=connection_id,
                source_run_id=run_id,
            )
            status = str(
                _field(result, "status", _field(result, "outcome", "failed"))
                or "failed"
            ).strip().lower()
            if status not in {"completed", "failed", "ineligible", "partial"}:
                status = "failed"
            return status
        except Exception as error:
            logger.error(
                "telemetry_analysis_handoff_failed",
                extra={
                    "event": "telemetry_analysis_handoff_failed",
                    "connection_id": connection_id,
                    "run_id": run_id,
                    "error_type": type(error).__name__,
                },
            )
            return "failed"

    def _analyze_final_run_with_lease_heartbeat(
        self,
        *,
        scope: TelemetryScopeRef,
        connection_id: str,
        run_id: str,
        lease_token: str,
    ) -> str | None:
        """Keep the connection lease live for the full synchronous analysis call."""
        if self.analyze_run is None:
            return None
        stop_renewal = threading.Event()
        lease_lost = threading.Event()

        def renew_until_stopped() -> None:
            while not stop_renewal.wait(self.lease_heartbeat_interval_seconds):
                try:
                    renewed = self.repository.renew_lease(
                        scope,
                        connection_id=connection_id,
                        lease_token=lease_token,
                        lease_seconds=self.lease_seconds,
                        now=_aware_utc(
                            self._now(), code="telemetry_scheduler_clock_invalid"
                        ),
                    )
                except Exception:
                    renewed = False
                if not renewed:
                    lease_lost.set()
                    return

        guardian = threading.Thread(
            target=renew_until_stopped,
            name="telemetry-analysis-lease-guardian",
            daemon=True,
        )
        guardian.start()
        try:
            status = self._analyze_final_run(
                scope=scope,
                connection_id=connection_id,
                run_id=run_id,
            )
        finally:
            stop_renewal.set()
            guardian.join(
                timeout=min(self.lease_heartbeat_interval_seconds + 1.0, 5.0)
            )
        if guardian.is_alive() or lease_lost.is_set():
            raise TelemetryLeaseLost("telemetry_connection_lease_lost")
        return status

    def _publish_heartbeat(self, **kwargs: Any) -> None:
        try:
            self._heartbeat(
                minimum_interval_seconds=self.heartbeat_interval_seconds,
                **kwargs,
            )
        except Exception as error:
            logger.warning(
                "telemetry_worker_heartbeat_publish_failed",
                extra={
                    "event": "telemetry_worker_heartbeat_publish_failed",
                    "error_type": type(error).__name__,
                },
            )

    def _run_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as error:
                logger.error(
                    "telemetry_scheduler_iteration_failed",
                    extra={
                        "event": "telemetry_scheduler_iteration_failed",
                        "error_type": type(error).__name__,
                    },
                )
                self._publish_heartbeat(
                    status="degraded",
                    error_code="telemetry_scheduler_iteration_failed",
                )
            self._stop.wait(self.poll_interval_seconds)


def _default_worker_id() -> str:
    host = re.sub(r"[^A-Za-z0-9_.-]", "-", socket.gethostname())[:64] or "worker"
    return f"telemetry-{host}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _required_text(
    value: Mapping[str, Any], name: str, *, fallback: str | None = None
) -> str:
    raw = value.get(name)
    if raw is None and fallback:
        raw = value.get(fallback)
    normalized = str(raw or "").strip()
    if not normalized:
        raise ValueError(f"telemetry_scheduler_{name}_missing")
    return normalized


def _aware_utc(value: datetime, *, code: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(code)
    return value.astimezone(UTC)


def _checkpoint_mode(value: Any) -> CheckpointMode:
    try:
        return CheckpointMode(str(value or CheckpointMode.INCREMENTAL.value))
    except ValueError:
        raise ValueError("telemetry_checkpoint_mode_invalid") from None


def _run_mode(value: Any) -> IngestionRunMode:
    try:
        return IngestionRunMode(str(value or IngestionRunMode.INCREMENTAL.value))
    except ValueError:
        raise ValueError("telemetry_ingestion_run_mode_invalid") from None


def _connector_checkpoint(value: Any) -> ConnectorCheckpoint | None:
    if value is None:
        return None
    cursor_payload = _field(value, "cursor_payload", {})
    if not isinstance(cursor_payload, Mapping):
        raise ValueError("telemetry_checkpoint_cursor_invalid")
    cursor = cursor_payload.get("cursor")
    high_water_at = _field(value, "high_water_at")
    if cursor is None and high_water_at is None:
        return None
    return ConnectorCheckpoint(cursor=cursor, high_water_at=high_water_at)


def _backfill_range(
    work: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> BoundedBackfillRange:
    backfill = snapshot.get("backfill")
    start = (
        work.get("backfill_start_at")
        or work.get("range_start")
        or snapshot.get("range_start")
        or _field(backfill, "start_at")
    )
    end = (
        work.get("backfill_end_at")
        or work.get("range_end")
        or snapshot.get("range_end")
        or _field(backfill, "end_at")
    )
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise ValueError("telemetry_backfill_bounds_missing")
    return BoundedBackfillRange(start_at=start, end_at=end)


def _has_backfill_bounds(
    work: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> bool:
    backfill = snapshot.get("backfill")
    start = (
        work.get("backfill_start_at")
        or work.get("range_start")
        or snapshot.get("range_start")
        or _field(backfill, "start_at")
    )
    end = (
        work.get("backfill_end_at")
        or work.get("range_end")
        or snapshot.get("range_end")
        or _field(backfill, "end_at")
    )
    return start is not None and end is not None


def _sequence_field(value: Any, name: str) -> Sequence[Any]:
    result = _field(value, name)
    if not isinstance(result, Sequence) or isinstance(result, (str, bytes, bytearray)):
        raise ValueError(f"telemetry_normalized_{name}_invalid")
    return result


def _mapping_snapshots(
    value: Any, *, scope: TelemetryScopeRef, connection_id: str
) -> dict[str, Any]:
    from app.services.telemetry_ingestion import MappingSnapshot

    if isinstance(value, Mapping):
        rows = list(value.values())
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        rows = list(value)
    else:
        raise ValueError("telemetry_mapping_snapshot_invalid")
    result: dict[str, MappingSnapshot] = {}
    for raw in rows:
        if isinstance(raw, MappingSnapshot):
            mapping = raw
        elif isinstance(raw, Mapping):
            mapping = MappingSnapshot(
                scope=scope,
                connection_id=connection_id,
                external_tag_id=raw.get("external_tag_id"),
                external_signal_id=raw.get("external_signal_id"),
                mapping_id=raw.get("mapping_id") or raw.get("id"),
                revision=int(raw.get("revision") or 0),
                actor_id=raw.get("actor_id") or raw.get("mapped_by"),
                mapped_at=raw.get("mapped_at"),
                authority_digest=raw.get("authority_digest"),
                facility_id=scope.facility_id,
                system_id=raw.get("system_id"),
                canonical_signal_id=(
                    raw.get("canonical_signal_id") or raw.get("canonical_concept_id")
                ),
                canonical_signal_name=raw.get("canonical_signal_name"),
                source_unit=raw.get("source_unit"),
                canonical_unit=raw.get("canonical_unit"),
                expected_dimension=raw.get("expected_dimension"),
                conversion_id=raw.get("conversion_id"),
                conversion_version=raw.get("conversion_version"),
                source_timezone=raw.get("source_timezone"),
                asset_id=raw.get("asset_id"),
                provenance=raw.get("provenance") or "manual",
                enabled=bool(raw.get("enabled", True)),
            )
        else:
            raise ValueError("telemetry_mapping_snapshot_invalid")
        if mapping.external_tag_id in result:
            raise ValueError("telemetry_mapping_snapshot_duplicate")
        result[mapping.external_tag_id] = mapping
    return result


def _dataclass_record(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not is_dataclass(value) or isinstance(value, type):
        raise ValueError("telemetry_normalized_record_invalid")
    return {
        item.name: getattr(value, item.name)
        for item in fields(value)
        if item.name != "scope"
    }


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _observation_record(value: Any) -> dict[str, Any]:
    record = _dataclass_record(value)
    record["id"] = str(record.get("id") or uuid.uuid4())
    record["canonical_concept_id"] = record.pop(
        "canonical_concept_id", record.pop("canonical_signal_id", None)
    )
    record.pop("ingestion_run_id", None)
    for key in ("quality_state", "ingestion_disposition"):
        record[key] = _enum_value(record.get(key))
    return record


def _rejection_record(value: Any) -> dict[str, Any]:
    record = _dataclass_record(value)
    record["id"] = str(record.get("id") or uuid.uuid4())
    record["disposition"] = _enum_value(
        record.pop("disposition", record.pop("ingestion_disposition", "rejected"))
    )
    record["quality_state"] = _enum_value(record.get("quality_state"))
    record.pop("ingestion_run_id", None)
    return record


def _polling_cadence_seconds(connection: Mapping[str, Any]) -> float:
    try:
        value = float(connection.get("polling_interval_seconds") or 60.0)
    except (TypeError, ValueError):
        raise ValueError("telemetry_polling_interval_invalid") from None
    if not 1.0 <= value <= 86_400.0:
        raise ValueError("telemetry_polling_interval_invalid")
    return value


def _checkpoint_digest(value: Any) -> str:
    """Hash a bounded checkpoint projection without exposing its opaque cursor."""
    cursor_payload = _field(value, "cursor_payload", {})
    if not isinstance(cursor_payload, Mapping):
        cursor_payload = {}
    high_water_at = _field(value, "high_water_at")
    projection = {
        "mode": str(_field(value, "mode", "") or ""),
        "cursor_payload": dict(cursor_payload),
        "high_water_at": (
            high_water_at.astimezone(UTC).isoformat()
            if isinstance(high_water_at, datetime)
            and high_water_at.tzinfo is not None
            and high_water_at.utcoffset() is not None
            else None
        ),
        "revision": max(int(_field(value, "revision", 0) or 0), 0),
    }
    encoded = json.dumps(
        projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if len(encoded) > 65_536:
        raise ValueError("telemetry_checkpoint_digest_input_invalid")
    return hashlib.sha256(encoded).hexdigest()


def _stable_error_code(error: Exception) -> str:
    raw = str(getattr(error, "code", "") or "").strip().lower()
    if _SAFE_CODE.fullmatch(raw):
        return raw
    message = str(error).strip().lower()
    if _SAFE_CODE.fullmatch(message) and message.startswith(_SAFE_MESSAGE_CODE_PREFIXES):
        return message
    if isinstance(error, ValueError):
        return "telemetry_ingestion_contract_invalid"
    return "telemetry_scheduler_internal_error"


__all__ = ["SchedulerRunResult", "TelemetryScheduler"]
