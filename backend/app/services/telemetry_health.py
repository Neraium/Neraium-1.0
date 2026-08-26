"""Deterministic multidimensional health policy for telemetry connections."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.telemetry_domain import (
    ConnectionHealthState,
    HealthFacetStatus,
    TelemetryScopeRef,
)
from app.services.telemetry_repository import (
    PostgreSQLTelemetryRepository,
    TelemetryRepositoryError,
)


@dataclass(frozen=True, slots=True)
class ProbeFacet:
    """A sanitized provider observation, never a credential or payload."""

    status: HealthFacetStatus
    observed_at: datetime
    reason_code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", HealthFacetStatus(self.status))
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("telemetry_health_probe_timestamp_invalid")
        if self.reason_code is not None:
            reason = str(self.reason_code).strip()
            if not reason or len(reason) > 160 or not reason.replace("_", "").isalnum():
                raise ValueError("telemetry_health_probe_reason_invalid")
            object.__setattr__(self, "reason_code", reason)


def _timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None and value.utcoffset() is not None else None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    return None


def _facet(
    status: HealthFacetStatus,
    *,
    observed_at: datetime | None,
    reason_code: str | None,
) -> dict[str, Any]:
    return {
        "status": status.value,
        "observed_at": observed_at.astimezone(UTC).isoformat() if observed_at else None,
        "reason_code": reason_code,
    }


class TelemetryHealthService:
    """Evaluates independent facets; validation success alone is insufficient."""

    def __init__(
        self,
        repository: PostgreSQLTelemetryRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._clock = clock

    def evaluate_and_persist(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
        reachability: ProbeFacet | None = None,
        authentication: ProbeFacet | None = None,
    ) -> dict[str, Any]:
        facts = self._repository.load_connection_health_inputs(
            scope, connection_id=connection_id
        )
        if facts is None:
            raise TelemetryRepositoryError("telemetry_connection_not_found")
        evaluation = evaluate_connection_health(
            facts,
            now=self._clock(),
            reachability=reachability,
            authentication=authentication,
        )
        return self._repository.save_connection_health(
            scope, connection_id=connection_id, health=evaluation
        )

    def get_health(
        self,
        scope: TelemetryScopeRef,
        *,
        connection_id: str,
    ) -> dict[str, Any] | None:
        return self._repository.get_connection_health(
            scope, connection_id=connection_id
        )


def evaluate_connection_health(
    facts: Mapping[str, Any],
    *,
    now: datetime,
    reachability: ProbeFacet | None = None,
    authentication: ProbeFacet | None = None,
) -> dict[str, Any]:
    """Apply the stable v1 precedence and freshness policy."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("telemetry_health_clock_invalid")
    now = now.astimezone(UTC)
    cadence = max(int(facts.get("polling_interval_seconds") or 300), 30)
    enabled = bool(facts.get("enabled"))
    lifecycle = str(facts.get("lifecycle_status") or "draft")
    discovered = max(int(facts.get("discovered_signal_count") or 0), 0)
    mapped = max(int(facts.get("mapped_signal_count") or 0), 0)
    healthy = max(int(facts.get("healthy_signal_count") or 0), 0)
    stale = max(int(facts.get("stale_signal_count") or 0), 0)
    if mapped > discovered or healthy > mapped or stale > mapped:
        raise ValueError("telemetry_health_counts_invalid")

    previous_details = facts.get("previous_details") or {}
    if not isinstance(previous_details, Mapping):
        previous_details = {}

    def resolved_probe(name: str, supplied: ProbeFacet | None) -> dict[str, Any]:
        if supplied is not None:
            return _facet(
                supplied.status,
                observed_at=supplied.observed_at,
                reason_code=supplied.reason_code,
            )
        previous_status = facts.get(f"{name}_state") or "unknown"
        try:
            status = HealthFacetStatus(previous_status)
        except ValueError:
            status = HealthFacetStatus.UNKNOWN
        prior = previous_details.get(name) or {}
        if not isinstance(prior, Mapping):
            prior = {}
        observed_at = _timestamp(prior.get("observed_at"))
        # A reachability result cannot remain current forever. Authentication
        # may remain valid, but still cannot make the aggregate healthy without
        # fresh telemetry and worker progress.
        if (
            name == "reachability"
            and status is HealthFacetStatus.HEALTHY
            and (observed_at is None or now - observed_at > timedelta(seconds=cadence * 3))
        ):
            status = HealthFacetStatus.UNKNOWN
            return _facet(
                status,
                observed_at=observed_at,
                reason_code="reachability_probe_expired",
            )
        return _facet(
            status,
            observed_at=observed_at,
            reason_code=str(prior.get("reason_code") or "") or None,
        )

    reach = resolved_probe("reachability", reachability)
    auth = resolved_probe("authentication", authentication)

    if not enabled or lifecycle in {"draft", "disabled", "archived"}:
        freshness = _facet(
            HealthFacetStatus.NOT_APPLICABLE,
            observed_at=_timestamp(facts.get("last_telemetry_at")),
            reason_code="connection_not_enabled",
        )
        checkpoint = _facet(
            HealthFacetStatus.NOT_APPLICABLE,
            observed_at=_timestamp(facts.get("checkpoint_updated_at")),
            reason_code="connection_not_enabled",
        )
    else:
        last_telemetry = _timestamp(facts.get("last_telemetry_at"))
        telemetry_age = (now - last_telemetry).total_seconds() if last_telemetry else None
        if telemetry_age is None:
            freshness_status = HealthFacetStatus.UNHEALTHY
            freshness_reason = "telemetry_never_received"
        elif telemetry_age <= cadence * 2:
            freshness_status = HealthFacetStatus.HEALTHY
            freshness_reason = None
        elif telemetry_age <= cadence * 4:
            freshness_status = HealthFacetStatus.DEGRADED
            freshness_reason = "telemetry_delayed"
        else:
            freshness_status = HealthFacetStatus.UNHEALTHY
            freshness_reason = "telemetry_stale"
        freshness = _facet(
            freshness_status,
            observed_at=last_telemetry,
            reason_code=freshness_reason,
        )

        checkpoint_at = _timestamp(facts.get("checkpoint_updated_at"))
        checkpoint_age = (now - checkpoint_at).total_seconds() if checkpoint_at else None
        if checkpoint_age is None:
            checkpoint_status = HealthFacetStatus.UNHEALTHY
            checkpoint_reason = "worker_checkpoint_missing"
        elif checkpoint_age <= cadence * 3:
            checkpoint_status = HealthFacetStatus.HEALTHY
            checkpoint_reason = None
        elif checkpoint_age <= cadence * 6:
            checkpoint_status = HealthFacetStatus.DEGRADED
            checkpoint_reason = "worker_checkpoint_delayed"
        else:
            checkpoint_status = HealthFacetStatus.UNHEALTHY
            checkpoint_reason = "worker_checkpoint_stale"
        checkpoint = _facet(
            checkpoint_status,
            observed_at=checkpoint_at,
            reason_code=checkpoint_reason,
        )

    if discovered == 0:
        mapping = _facet(
            HealthFacetStatus.UNKNOWN,
            observed_at=now,
            reason_code="signals_not_discovered",
        )
    elif mapped == 0:
        mapping = _facet(
            HealthFacetStatus.UNHEALTHY,
            observed_at=now,
            reason_code="signals_unmapped",
        )
    elif mapped < discovered:
        mapping = _facet(
            HealthFacetStatus.DEGRADED,
            observed_at=now,
            reason_code="signals_partially_mapped",
        )
    else:
        mapping = _facet(HealthFacetStatus.HEALTHY, observed_at=now, reason_code=None)

    if mapped == 0:
        quality = _facet(
            HealthFacetStatus.UNKNOWN,
            observed_at=now,
            reason_code="mapped_signals_unavailable",
        )
    elif stale >= mapped:
        quality = _facet(
            HealthFacetStatus.UNHEALTHY,
            observed_at=now,
            reason_code="mapped_signals_stale",
        )
    elif stale > 0 or healthy < mapped:
        quality = _facet(
            HealthFacetStatus.DEGRADED,
            observed_at=now,
            reason_code="mapped_signal_quality_degraded",
        )
    else:
        quality = _facet(HealthFacetStatus.HEALTHY, observed_at=now, reason_code=None)

    facets = {
        "reachability": reach,
        "authentication": auth,
        "telemetry_freshness": freshness,
        "mapping_completeness": mapping,
        "data_quality": quality,
        "worker_checkpoint": checkpoint,
    }
    statuses = {name: HealthFacetStatus(value["status"]) for name, value in facets.items()}
    if lifecycle == "error":
        aggregate = ConnectionHealthState.ERROR
    elif statuses["reachability"] is HealthFacetStatus.UNHEALTHY or statuses[
        "authentication"
    ] is HealthFacetStatus.UNHEALTHY:
        aggregate = ConnectionHealthState.DISCONNECTED
    elif not enabled or lifecycle in {"draft", "disabled", "archived"}:
        aggregate = ConnectionHealthState.UNKNOWN
    elif any(status is HealthFacetStatus.UNHEALTHY for status in statuses.values()):
        aggregate = ConnectionHealthState.DEGRADED
    elif any(status is HealthFacetStatus.DEGRADED for status in statuses.values()):
        aggregate = ConnectionHealthState.DEGRADED
    elif any(status is HealthFacetStatus.UNKNOWN for status in statuses.values()):
        aggregate = ConnectionHealthState.UNKNOWN
    else:
        aggregate = ConnectionHealthState.HEALTHY

    prior_healthy = _timestamp(facts.get("last_healthy_at"))
    last_healthy_at = now if aggregate is ConnectionHealthState.HEALTHY else prior_healthy
    return {
        "aggregate_status": aggregate.value,
        **{f"{name}_state": value["status"] for name, value in facets.items()},
        "discovered_signal_count": discovered,
        "mapped_signal_count": mapped,
        "healthy_signal_count": healthy,
        "stale_signal_count": stale,
        "last_healthy_at": last_healthy_at,
        "last_evaluated_at": now,
        "details": facets,
    }
