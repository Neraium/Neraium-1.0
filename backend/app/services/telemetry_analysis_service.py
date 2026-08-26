"""Operational post-ingestion orchestration for canonical telemetry analysis.

This service is deliberately scheduler-neutral.  A worker supplies only
persisted server values and a scoped repository; the service selects canonical
observations, persists durable lineage, and invokes the authoritative SII seam
at most once for a deterministic window identity.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import re
from typing import Any, Protocol
import uuid

from app.services.telemetry_analysis_window import (
    AnalysisWindowExecution,
    AnalysisWindowExecutionError,
    AnalysisWindowValidationError,
    build_canonical_analysis_window,
    project_window_persistence,
    run_analysis_window,
)
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_lineage import project_analysis_window_persistence
from app.services.telemetry_lineage import build_durable_result_lineage
from app.services.phase4_scope import ServerBoundSystemIdentityV2


ANALYSIS_SERVICE_CONTRACT_VERSION = "telemetry-analysis-service.v1"
ANALYSIS_OBSERVATION_LIMIT = 5_000
ANALYSIS_ROLLING_WINDOW = timedelta(hours=24)
ANALYSIS_EXECUTION_CLAIM_TTL = timedelta(minutes=10)
_SAFE_REASON = re.compile(r"^[a-z0-9_.:-]{1,160}$")
_WINDOW_NAMESPACE = uuid.UUID("1a77b935-9e8c-59a8-b8a6-5282f13b6c91")
_TERMINAL_STATUSES = frozenset({"completed", "failed", "ineligible"})


class TelemetryAnalysisRepository(Protocol):
    def resolve_analysis_authority_snapshot(
        self,
        scope: TelemetryScopeRef,
        *,
        system_id: str,
        asset_id: str | None,
        authority_digest: str,
    ) -> ServerBoundSystemIdentityV2 | None: ...

    def get_analysis_window(
        self, scope: TelemetryScopeRef, *, window_id: str
    ) -> Mapping[str, Any] | None: ...

    def list_analysis_eligible_observations(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        source_run_id: str | None,
        system_id: str | None,
        asset_id: str | None,
        asset_filter_applied: bool = False,
        window_start: datetime | None,
        window_end: datetime | None,
        authority_digest: str | None = None,
        limit: int = ANALYSIS_OBSERVATION_LIMIT,
    ) -> list[dict[str, Any]]: ...

    def persist_analysis_window(
        self,
        scope: TelemetryScopeRef,
        *,
        window_record: Mapping[str, Any],
        observation_links: Sequence[Mapping[str, Any]],
    ) -> Mapping[str, Any]: ...

    def update_analysis_window_status(
        self,
        scope: TelemetryScopeRef,
        *,
        window_id: str,
        expected_status: str,
        target_status: str,
        reason_code: str | None = None,
    ) -> Mapping[str, Any]: ...

    def claim_analysis_window_execution(self, scope: TelemetryScopeRef, **kwargs: Any) -> Mapping[str, Any]: ...

    def recover_stale_analysis_window_execution(self, scope: TelemetryScopeRef, **kwargs: Any) -> Mapping[str, Any] | None: ...

    def finish_analysis_window_execution(self, scope: TelemetryScopeRef, **kwargs: Any) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class TelemetryAnalysisServiceResult:
    window_id: str
    status: str
    execution: AnalysisWindowExecution | None = None
    reason_code: str | None = None
    reused_existing: bool = False
    persisted: bool = True
    contract_version: str = ANALYSIS_SERVICE_CONTRACT_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "window_id": self.window_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "reused_existing": self.reused_existing,
            "persisted": self.persisted,
            "execution": self.execution.as_dict() if self.execution is not None else None,
        }


@dataclass(frozen=True, slots=True)
class IngestionRunAnalysisResult:
    source_run_id: str
    status: str
    windows: tuple[TelemetryAnalysisServiceResult, ...]
    reason_code: str | None = None
    contract_version: str = ANALYSIS_SERVICE_CONTRACT_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "source_run_id": self.source_run_id,
            "status": self.status,
            "reason_code": self.reason_code,
            "window_count": len(self.windows),
            "windows": [item.as_dict() for item in self.windows],
        }


def _required_text(value: Any, code: str, *, maximum: int = 512) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(code)
    return normalized


def _optional_text(value: Any, *, maximum: int = 512) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) > maximum:
        raise ValueError("telemetry_analysis_asset_id_invalid")
    return normalized


def _aware_utc(value: Any, code: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(code)
    return value.astimezone(UTC)


def deterministic_analysis_window_id(
    *,
    scope: TelemetryScopeRef,
    connection_id: str,
    source_run_id: str,
    system_id: str,
    asset_id: str | None,
    window_start: datetime,
    window_end: datetime,
    authority_digest: str,
) -> str:
    """Return the idempotency identity for one persisted analysis request."""
    if not isinstance(scope, TelemetryScopeRef):
        raise TypeError("telemetry_analysis_scope_required")
    start = _aware_utc(window_start, "telemetry_analysis_window_start_invalid")
    end = _aware_utc(window_end, "telemetry_analysis_window_end_invalid")
    if end <= start:
        raise ValueError("telemetry_analysis_window_range_invalid")
    payload = {
        "contract_version": ANALYSIS_SERVICE_CONTRACT_VERSION,
        "resource_scope_id": scope.resource_scope_id,
        "facility_id": scope.facility_id,
        "connection_id": _required_text(
            connection_id, "telemetry_analysis_connection_id_invalid"
        ),
        "source_run_id": _required_text(
            source_run_id, "telemetry_analysis_source_run_id_invalid"
        ),
        "system_id": _required_text(system_id, "telemetry_analysis_system_id_invalid"),
        "asset_id": _optional_text(asset_id),
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "authority_digest": _required_text(
            authority_digest, "telemetry_analysis_authority_digest_invalid"
        ).lower(),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    # UUIDv5 gives the PostgreSQL schema a native UUID while preserving a
    # transparent canonical preimage and stable idempotency behavior.
    return str(uuid.uuid5(_WINDOW_NAMESPACE, encoded))


def _status(record: Mapping[str, Any] | None) -> str:
    return str((record or {}).get("status") or "").strip().lower()


def _safe_reason(error: BaseException, fallback: str) -> str:
    candidate = str(error or "").strip().lower()
    return candidate if _SAFE_REASON.fullmatch(candidate) else fallback


def _existing_result(
    window_id: str, record: Mapping[str, Any] | None
) -> TelemetryAnalysisServiceResult | None:
    status = _status(record)
    if status in _TERMINAL_STATUSES:
        return TelemetryAnalysisServiceResult(
            window_id=window_id,
            status=status,
            reason_code=(record or {}).get("reason_code"),
            reused_existing=True,
        )
    return None


def _running_result(
    repository: TelemetryAnalysisRepository,
    scope: TelemetryScopeRef,
    window_id: str,
    record: Mapping[str, Any],
    *,
    now: datetime,
) -> TelemetryAnalysisServiceResult | None:
    if _status(record) != "running":
        return None
    recovered = repository.recover_stale_analysis_window_execution(
        scope, window_id=window_id, recovered_at=now
    )
    if recovered is not None:
        return TelemetryAnalysisServiceResult(
            window_id=window_id,
            status="failed",
            reason_code="telemetry_analysis_execution_claim_expired",
            reused_existing=True,
        )
    return TelemetryAnalysisServiceResult(
        window_id=window_id,
        status="running",
        reused_existing=True,
    )


def _read_existing(
    repository: TelemetryAnalysisRepository,
    scope: TelemetryScopeRef,
    window_id: str,
) -> Mapping[str, Any] | None:
    return repository.get_analysis_window(scope, window_id=window_id)


def _persist_ineligible(
    repository: TelemetryAnalysisRepository,
    *,
    scope: TelemetryScopeRef,
    window_id: str,
    source_run_id: str,
    system_id: str,
    asset_id: str | None,
    window_start: datetime,
    window_end: datetime,
    authority_digest: str,
    reason_code: str,
) -> TelemetryAnalysisServiceResult:
    try:
        record = project_analysis_window_persistence(
            window_id=window_id,
            tenant_scope_id=scope.tenant_scope_id,
            workspace_id=scope.workspace_id,
            resource_scope_id=scope.resource_scope_id,
            facility_id=scope.facility_id,
            system_id=system_id,
            asset_id=asset_id,
            source_run_id=source_run_id,
            window_start=window_start,
            window_end=window_end,
            authority_digest=authority_digest,
            quality_summary={"status": "ineligible", "reason_code": reason_code},
            status="ineligible",
        )
    except (TypeError, ValueError):
        # Invalid persisted authority is denied before analysis. It cannot be
        # represented by the strict durable contract and is never normalized
        # into invented authority merely to create a row.
        return TelemetryAnalysisServiceResult(
            window_id=window_id,
            status="ineligible",
            reason_code=reason_code,
            persisted=False,
        )
    try:
        persisted = repository.persist_analysis_window(
            scope, window_record=record, observation_links=()
        )
    except Exception:
        existing = _read_existing(repository, scope, window_id)
        result = _existing_result(window_id, existing)
        if result is not None:
            return result
        raise
    return TelemetryAnalysisServiceResult(
        window_id=window_id,
        status=_status(persisted) or "ineligible",
        reason_code=reason_code,
    )


def run_post_ingestion_analysis(
    *,
    repository: TelemetryAnalysisRepository,
    scope: TelemetryScopeRef,
    connection_id: str,
    source_run_id: str,
    system_id: str,
    asset_id: str | None,
    window_start: datetime,
    window_end: datetime,
    persisted_authority_digest: str,
    evaluator: Callable[..., dict[str, Any]] | None = None,
    progress_reporter: Any | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> TelemetryAnalysisServiceResult:
    """Persist and execute one deterministic post-ingestion analysis window."""
    if not isinstance(scope, TelemetryScopeRef):
        raise TypeError("telemetry_analysis_scope_required")
    connection_id = _required_text(
        connection_id, "telemetry_analysis_connection_id_invalid"
    )
    source_run_id = _required_text(
        source_run_id, "telemetry_analysis_source_run_id_invalid"
    )
    system_id = _required_text(system_id, "telemetry_analysis_system_id_invalid")
    asset_id = _optional_text(asset_id)
    start = _aware_utc(window_start, "telemetry_analysis_window_start_invalid")
    end = _aware_utc(window_end, "telemetry_analysis_window_end_invalid")
    if end <= start:
        raise ValueError("telemetry_analysis_window_range_invalid")
    authority_digest = _required_text(
        persisted_authority_digest, "telemetry_analysis_authority_digest_invalid"
    ).lower()
    window_id = deterministic_analysis_window_id(
        scope=scope,
        connection_id=connection_id,
        source_run_id=source_run_id,
        system_id=system_id,
        asset_id=asset_id,
        window_start=start,
        window_end=end,
        authority_digest=authority_digest,
    )

    existing = _read_existing(repository, scope, window_id)
    existing_result = _existing_result(window_id, existing)
    if existing_result is not None:
        return existing_result
    now = _aware_utc(clock(), "telemetry_analysis_clock_invalid")
    if existing is not None:
        running_result = _running_result(
            repository, scope, window_id, existing, now=now
        )
        if running_result is not None:
            return running_result

    identity = repository.resolve_analysis_authority_snapshot(
        scope,
        system_id=system_id,
        asset_id=asset_id,
        authority_digest=authority_digest,
    )
    if not isinstance(identity, ServerBoundSystemIdentityV2):
        return _persist_ineligible(
            repository,
            scope=scope,
            window_id=window_id,
            source_run_id=source_run_id,
            system_id=system_id,
            asset_id=asset_id,
            window_start=start,
            window_end=end,
            authority_digest=authority_digest,
            reason_code="telemetry_analysis_shared_authority_snapshot_unavailable",
        )

    try:
        observations = repository.list_analysis_eligible_observations(
            scope,
            connection_id=connection_id,
            source_run_id=None,
            system_id=system_id,
            asset_id=asset_id,
            asset_filter_applied=True,
            window_start=start,
            window_end=end,
            authority_digest=authority_digest,
            limit=ANALYSIS_OBSERVATION_LIMIT,
        )
    except Exception as error:
        if str(error) == "telemetry_analysis_observation_limit_exceeded":
            return _persist_ineligible(
                repository,
                scope=scope,
                window_id=window_id,
                source_run_id=source_run_id,
                system_id=system_id,
                asset_id=asset_id,
                window_start=start,
                window_end=end,
                authority_digest=authority_digest,
                reason_code="telemetry_analysis_observation_limit_exceeded",
            )
        raise
    try:
        window = build_canonical_analysis_window(
            window_id=window_id,
            source_run_id=source_run_id,
            scope=scope,
            system_id=system_id,
            asset_id=asset_id,
            persisted_authority_digest=authority_digest,
            phase4_system_identity=identity,
            observations=observations,
            source_kind="telemetry_connector",
            window_start=start,
            window_end=end,
            ingestion_report={
                "observation_count": len(observations),
                "window_start": start.isoformat(),
                "window_end": end.isoformat(),
            },
        )
    except AnalysisWindowValidationError as error:
        reason = _safe_reason(error, "telemetry_analysis_window_ineligible")
        return _persist_ineligible(
            repository,
            scope=scope,
            window_id=window_id,
            source_run_id=source_run_id,
            system_id=system_id,
            asset_id=asset_id,
            window_start=start,
            window_end=end,
            authority_digest=authority_digest,
            reason_code=reason,
        )

    window_record, observation_links = project_window_persistence(window)
    try:
        persisted = repository.persist_analysis_window(
            scope,
            window_record=window_record,
            observation_links=observation_links,
        )
    except Exception:
        raced = _read_existing(repository, scope, window_id)
        raced_result = _existing_result(window_id, raced)
        if raced_result is not None:
            return raced_result
        if raced is not None:
            running_result = _running_result(
                repository, scope, window_id, raced, now=now
            )
            if running_result is not None:
                return running_result
        raise
    persisted_result = _existing_result(window_id, persisted)
    if persisted_result is not None:
        return persisted_result

    claim_token = str(uuid.uuid4())
    try:
        running = repository.claim_analysis_window_execution(
            scope,
            window_id=window_id,
            claim_token=claim_token,
            claimed_at=now,
            claim_expires_at=now + ANALYSIS_EXECUTION_CLAIM_TTL,
        )
    except Exception:
        raced = _read_existing(repository, scope, window_id)
        raced_result = _existing_result(window_id, raced)
        if raced_result is not None:
            return raced_result
        if raced is not None:
            running_result = _running_result(
                repository, scope, window_id, raced, now=now
            )
            if running_result is not None:
                return running_result
        raise
    if _status(running) != "running":
        raise RuntimeError("telemetry_analysis_running_transition_invalid")

    try:
        execution = run_analysis_window(
            window,
            progress_reporter=progress_reporter,
            evaluator=evaluator,
        )
    except AnalysisWindowValidationError as error:
        repository.finish_analysis_window_execution(
            scope,
            window_id=window_id,
            claim_token=claim_token,
            completed_at=_aware_utc(clock(), "telemetry_analysis_clock_invalid"),
            target_status="ineligible",
            reason_code=_safe_reason(
                error, "telemetry_analysis_authority_became_ineligible"
            ),
        )
        return TelemetryAnalysisServiceResult(
            window_id=window_id,
            status="ineligible",
            reason_code=_safe_reason(error, "telemetry_analysis_authority_became_ineligible"),
        )
    except AnalysisWindowExecutionError:
        repository.finish_analysis_window_execution(
            scope,
            window_id=window_id,
            claim_token=claim_token,
            completed_at=_aware_utc(clock(), "telemetry_analysis_clock_invalid"),
            target_status="failed",
            reason_code="telemetry_analysis_execution_failed",
        )
        return TelemetryAnalysisServiceResult(
            window_id=window_id,
            status="failed",
            reason_code="telemetry_analysis_execution_failed",
        )
    except Exception:
        repository.finish_analysis_window_execution(
            scope,
            window_id=window_id,
            claim_token=claim_token,
            completed_at=_aware_utc(clock(), "telemetry_analysis_clock_invalid"),
            target_status="failed",
            reason_code="telemetry_analysis_execution_failed",
        )
        return TelemetryAnalysisServiceResult(
            window_id=window_id,
            status="failed",
            reason_code="telemetry_analysis_execution_failed",
        )

    result_metadata, evidence_lineage, result_digest = build_durable_result_lineage(
        window_id=window_id,
        source_run_id=source_run_id,
        lineage=window.observation_lineage,
        sii_result=execution.sii_result,
        analysis_result=execution.analysis_result,
    )
    completed = repository.finish_analysis_window_execution(
        scope,
        window_id=window_id,
        claim_token=claim_token,
        completed_at=_aware_utc(clock(), "telemetry_analysis_clock_invalid"),
        target_status="completed",
        result_digest=result_digest,
        result_metadata=result_metadata,
        evidence_lineage=evidence_lineage,
    )
    if _status(completed) != "completed":
        raise RuntimeError("telemetry_analysis_completed_transition_invalid")
    return TelemetryAnalysisServiceResult(
        window_id=window_id,
        status="completed",
        execution=execution,
    )


def _run_status(results: Sequence[TelemetryAnalysisServiceResult]) -> str:
    statuses = {item.status for item in results}
    if not statuses:
        return "ineligible"
    if statuses == {"completed"}:
        return "completed"
    if statuses == {"ineligible"}:
        return "ineligible"
    if "failed" in statuses:
        return "failed" if statuses == {"failed"} else "partial"
    return "partial"


def process_ingestion_run(
    *,
    repository: TelemetryAnalysisRepository,
    scope: TelemetryScopeRef,
    connection_id: str,
    source_run_id: str,
    evaluator: Callable[..., dict[str, Any]] | None = None,
    progress_reporter: Any | None = None,
) -> IngestionRunAnalysisResult:
    """Derive and process every system/asset group from one persisted run.

    No hierarchy selector, time range, or authority digest is accepted from the
    scheduler.  All are derived from repository rows already constrained by the
    authoritative resource scope, connection and ingestion run.
    """
    if not isinstance(scope, TelemetryScopeRef):
        raise TypeError("telemetry_analysis_scope_required")
    connection_id = _required_text(
        connection_id, "telemetry_analysis_connection_id_invalid"
    )
    source_run_id = _required_text(
        source_run_id, "telemetry_analysis_source_run_id_invalid"
    )
    try:
        observations = repository.list_analysis_eligible_observations(
            scope,
            connection_id=connection_id,
            source_run_id=source_run_id,
            system_id=None,
            asset_id=None,
            asset_filter_applied=False,
            window_start=None,
            window_end=None,
            authority_digest=None,
            limit=ANALYSIS_OBSERVATION_LIMIT,
        )
    except Exception as error:
        if str(error) == "telemetry_analysis_observation_limit_exceeded":
            return IngestionRunAnalysisResult(
                source_run_id=source_run_id,
                status="ineligible",
                windows=(),
                reason_code="telemetry_analysis_observation_limit_exceeded",
            )
        raise
    if not observations:
        return IngestionRunAnalysisResult(
            source_run_id=source_run_id,
            status="ineligible",
            windows=(),
            reason_code="telemetry_analysis_no_eligible_observations",
        )

    grouped: dict[tuple[str, str | None, str], list[dict[str, Any]]] = {}
    for raw in observations:
        item = dict(raw)
        system_id = str(item.get("system_id") or "").strip()
        asset_id = _optional_text(item.get("asset_id"))
        authority_digest = str(item.get("mapping_authority_digest") or "").strip().lower()
        observed_at = item.get("observed_at_utc")
        if not system_id or not re.fullmatch(r"[0-9a-f]{64}", authority_digest):
            continue
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
            continue
        grouped.setdefault((system_id, asset_id, authority_digest), []).append(item)
    if not grouped:
        return IngestionRunAnalysisResult(
            source_run_id=source_run_id,
            status="ineligible",
            windows=(),
            reason_code="telemetry_analysis_persisted_lineage_invalid",
        )

    results: list[TelemetryAnalysisServiceResult] = []
    for (system_id, asset_id, authority_digest), group in sorted(
        grouped.items(), key=lambda item: (item[0][0], item[0][1] or "", item[0][2])
    ):
        timestamps = sorted(
            _aware_utc(item["observed_at_utc"], "telemetry_analysis_observation_timestamp_invalid")
            for item in group
        )
        group_end = timestamps[-1] + timedelta(microseconds=1)
        group_start = group_end - ANALYSIS_ROLLING_WINDOW
        results.append(
            run_post_ingestion_analysis(
                repository=repository,
                scope=scope,
                connection_id=connection_id,
                source_run_id=source_run_id,
                system_id=system_id,
                asset_id=asset_id,
                window_start=group_start,
                window_end=group_end,
                persisted_authority_digest=authority_digest,
                evaluator=evaluator,
                progress_reporter=progress_reporter,
            )
        )
    return IngestionRunAnalysisResult(
        source_run_id=source_run_id,
        status=_run_status(results),
        windows=tuple(results),
    )


__all__ = [
    "ANALYSIS_SERVICE_CONTRACT_VERSION",
    "IngestionRunAnalysisResult",
    "TelemetryAnalysisRepository",
    "TelemetryAnalysisServiceResult",
    "deterministic_analysis_window_id",
    "process_ingestion_run",
    "run_post_ingestion_analysis",
]
