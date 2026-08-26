from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.telemetry_domain import HealthFacetStatus
from app.services.telemetry_health import ProbeFacet, evaluate_connection_health


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def _facts(**changes: object) -> dict[str, object]:
    facts: dict[str, object] = {
        "enabled": True,
        "lifecycle_status": "connected",
        "polling_interval_seconds": 300,
        "last_telemetry_at": NOW - timedelta(seconds=100),
        "checkpoint_updated_at": NOW - timedelta(seconds=100),
        "last_healthy_at": None,
        "discovered_signal_count": 10,
        "mapped_signal_count": 10,
        "healthy_signal_count": 10,
        "stale_signal_count": 0,
        "reachability_state": "unknown",
        "authentication_state": "unknown",
        "previous_details": {},
    }
    facts.update(changes)
    return facts


def _good_probe() -> ProbeFacet:
    return ProbeFacet(HealthFacetStatus.HEALTHY, NOW)


def test_all_independent_facets_are_required_for_healthy() -> None:
    result = evaluate_connection_health(
        _facts(), now=NOW, reachability=_good_probe(), authentication=_good_probe()
    )
    assert result["aggregate_status"] == "healthy"
    assert result["last_healthy_at"] == NOW
    assert {
        result[f"{name}_state"]
        for name in (
            "reachability",
            "authentication",
            "telemetry_freshness",
            "mapping_completeness",
            "data_quality",
            "worker_checkpoint",
        )
    } == {"healthy"}


def test_authenticated_once_is_not_connected_when_no_telemetry_arrives() -> None:
    result = evaluate_connection_health(
        _facts(last_telemetry_at=None),
        now=NOW,
        reachability=_good_probe(),
        authentication=_good_probe(),
    )
    assert result["authentication_state"] == "healthy"
    assert result["telemetry_freshness_state"] == "unhealthy"
    assert result["aggregate_status"] == "degraded"


def test_authentication_or_reachability_failure_is_disconnected() -> None:
    failed_auth = ProbeFacet(
        HealthFacetStatus.UNHEALTHY, NOW, "authentication_rejected"
    )
    result = evaluate_connection_health(
        _facts(), now=NOW, reachability=_good_probe(), authentication=failed_auth
    )
    assert result["aggregate_status"] == "disconnected"
    assert result["details"]["authentication"]["reason_code"] == "authentication_rejected"


def test_partial_mapping_and_stale_signal_are_distinct_degraded_facets() -> None:
    result = evaluate_connection_health(
        _facts(
            mapped_signal_count=8,
            healthy_signal_count=7,
            stale_signal_count=1,
        ),
        now=NOW,
        reachability=_good_probe(),
        authentication=_good_probe(),
    )
    assert result["mapping_completeness_state"] == "degraded"
    assert result["data_quality_state"] == "degraded"
    assert result["telemetry_freshness_state"] == "healthy"
    assert result["aggregate_status"] == "degraded"


def test_expired_worker_checkpoint_degrades_fresh_telemetry() -> None:
    result = evaluate_connection_health(
        _facts(checkpoint_updated_at=NOW - timedelta(hours=1)),
        now=NOW,
        reachability=_good_probe(),
        authentication=_good_probe(),
    )
    assert result["worker_checkpoint_state"] == "unhealthy"
    assert result["telemetry_freshness_state"] == "healthy"
    assert result["aggregate_status"] == "degraded"


def test_disabled_connection_has_non_applicable_runtime_facets() -> None:
    result = evaluate_connection_health(
        _facts(enabled=False, lifecycle_status="disabled"),
        now=NOW,
        reachability=_good_probe(),
        authentication=_good_probe(),
    )
    assert result["telemetry_freshness_state"] == "not_applicable"
    assert result["worker_checkpoint_state"] == "not_applicable"
    assert result["aggregate_status"] == "unknown"
