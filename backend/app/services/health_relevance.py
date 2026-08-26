from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Mapping, Sequence

from app.services.health_relevance_methods import (
    BAYESIAN_METHOD_ID,
    INFORMATION_METHOD_ID,
    METHOD_REGISTRY,
    evaluate_health_relevance_method,
)
from app.services.runtime_db import db_connection, init_runtime_db


OUTCOME_SCHEMA_VERSION = "health-relevance-outcome.v1"
THRESHOLD_CONFIG_VERSION = "health-relevance-thresholds.v1"
METHOD_CONFIG_VERSION = "health-relevance-methods.v1"
AUTHORITY_RULES_VERSION = "health-relevance-authority.v1"
DEDUP_RULES_VERSION = "health-relevance-dedup.v1"
COMPATIBILITY_RULES_VERSION = "health-relevance-compatibility.v1"
DEFAULT_CODE_BUILD_VERSION = "internal-health-relevance.v1"

_METHOD_IDS = (BAYESIAN_METHOD_ID, INFORMATION_METHOD_ID)
_PRIMARY_TIERS = frozenset({"A", "B"})
_POSITIVE_DISPOSITIONS = frozenset(
    {"degraded", "fault_confirmed", "explained", "recovery_observed"}
)
_NEGATIVE_DISPOSITIONS = frozenset(
    {
        "expected_behavior",
        "no_fault",
        "not_useful",
        "unrelated_maintenance",
        "no_observed_behavior_change",
        "stable_observation",
    }
)
_COMPARISON_DISPOSITIONS = frozenset(
    {
        "expected_behavior",
        "no_fault",
        "not_useful",
        "unrelated_maintenance",
        "no_observed_behavior_change",
        "stable_observation",
    }
)


class HealthRelevanceNotFoundError(LookupError):
    """Opaque exact-scope failure for internal Health Relevance reads."""


class HealthRelevanceInputError(ValueError):
    """Raised when an internal state-key or configuration is invalid."""


@dataclass(frozen=True)
class ThresholdConfig:
    """Initial conservative experimental thresholds; not field calibrated."""

    emerging_min_outcomes: int = 3
    emerging_min_incidents: int = 2
    supported_min_outcomes: int = 5
    supported_min_incidents: int = 3
    supported_positive_balance: float = 0.75
    contradictory_min_balance: float = 0.40
    contradictory_max_balance: float = 0.60
    contradictory_min_positive: int = 2
    contradictory_min_negative: int = 2
    contradictory_min_directional: int = 5
    unsupported_max_positive_balance: float = 0.25
    unsupported_min_negative: int = 4
    unsupported_min_incidents: int = 3
    min_context_completeness: float = 0.80
    min_context_episodes: int = 2
    min_protocol_completion: float = 0.80
    min_comparison_windows: int = 2
    min_positive_families: int = 2
    min_independent_outcomes: int = 2
    min_tier_a_outcomes: int = 1
    bayesian_min_lower_bound_90: float = 0.60
    information_min_adjusted_normalized: float = 0.10
    stale_after_days: int = 180


DEFAULT_THRESHOLDS = ThresholdConfig()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _parse_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if value is None:
        return fallback
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _parse_time(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def freshness_status(
    last_evidence_at: str | datetime | None,
    *,
    as_of: str | datetime | None = None,
    stale_after_days: int = 180,
) -> str:
    """Return a non-decaying freshness qualifier at the inclusive 180-day boundary."""

    last = _parse_time(last_evidence_at)
    if last is None:
        return "current"
    current = _parse_time(as_of) or datetime.now(UTC)
    return "current" if current - last <= timedelta(days=stale_after_days) else "stale"


def _access_parts(access: Any) -> tuple[str, str, str, str]:
    try:
        scope = access.scope
        scope_storage_id = str(scope.storage_id)
        tenant_id = str(scope.tenant_id)
        facility_id = str(access.facility_id).strip()
        system_id = str(access.system_id).strip()
    except AttributeError as error:
        raise HealthRelevanceInputError("authorized exact scope is required") from error
    if not all((scope_storage_id, tenant_id, facility_id, system_id)):
        raise HealthRelevanceInputError("authorized exact scope is required")
    return scope_storage_id, tenant_id, facility_id, system_id


def _authorize(access: Any) -> None:
    # Authorization remains owned by the validated-outcome boundary. Importing
    # lazily avoids creating any production-service dependency on this sidecar.
    from app.services.validated_outcomes import require_internal_access

    try:
        require_internal_access(access)
    except Exception as error:
        raise HealthRelevanceNotFoundError("Health Relevance state not found.") from error


def _validate_state_key(
    *,
    subject_type: str,
    subject_id: str,
    subject_mapping_version: str,
    context_fingerprint: str,
    compatibility_epoch: str,
) -> None:
    if subject_type not in {"signal", "relationship", "asset_equipment", "subsystem"}:
        raise HealthRelevanceInputError("invalid subject type")
    if not all(
        str(value or "").strip()
        for value in (
            subject_id,
            subject_mapping_version,
            context_fingerprint,
            compatibility_epoch,
        )
    ):
        raise HealthRelevanceInputError("exact subject, context, and compatibility epoch are required")


def _latest_rows(
    connection: sqlite3.Connection,
    table: str,
    logical_id: str,
    *,
    scope_storage_id: str,
    tenant_id: str,
    facility_id: str,
    system_id: str,
    extra_sql: str = "",
    extra_params: Sequence[Any] = (),
) -> list[dict[str, Any]]:
    if table not in {"validated_outcomes", "validated_outcome_links"}:
        raise ValueError("unsupported revision table")
    query = f"""
        SELECT current.*
        FROM {table} AS current
        WHERE current.scope_storage_id = ?
          AND current.tenant_id = ?
          AND current.facility_id = ?
          AND current.system_id = ?
          AND current.revision = (
              SELECT MAX(candidate.revision)
              FROM {table} AS candidate
              WHERE candidate.scope_storage_id = current.scope_storage_id
                AND candidate.tenant_id = current.tenant_id
                AND candidate.facility_id = current.facility_id
                AND candidate.system_id = current.system_id
                AND candidate.{logical_id} = current.{logical_id}
          )
          {extra_sql}
        ORDER BY current.{logical_id}, current.revision
    """
    rows = connection.execute(
        query,
        (scope_storage_id, tenant_id, facility_id, system_id, *extra_params),
    ).fetchall()
    return [dict(row) for row in rows]


def _context_complete(context: Mapping[str, Any], required_dimensions: Sequence[str]) -> bool:
    return all(str(context.get(dimension) or "").strip() for dimension in required_dimensions)


def _stable_protocol_eligibility(outcome: Mapping[str, Any]) -> tuple[bool, str | None, float | None]:
    if str(outcome.get("outcome_type")) not in {
        "stable_operation_observation",
        "expected_no_fault_confirmation",
    }:
        return True, None, None
    protocol = _parse_json(outcome.get("observation_protocol_json"), {})
    if not isinstance(protocol, Mapping):
        return False, "stable_observation_protocol_missing", None
    if not all(
        str(protocol.get(field) or "").strip()
        for field in (
            "protocol_id",
            "protocol_version",
            "window_declared_at",
            "sampling_cadence",
            "subject_evaluability_rule",
        )
    ):
        return False, "stable_observation_protocol_identity_missing", None
    if protocol.get("completed") is not True or protocol.get("context_complete") is not True:
        return False, "stable_observation_protocol_incomplete", None
    reference_set = protocol.get("expected_signal_reference_set")
    if not isinstance(reference_set, list) or not reference_set:
        return False, "stable_observation_reference_set_missing", None
    try:
        completeness = float(protocol.get("sample_coverage"))
    except (TypeError, ValueError):
        expected = int(protocol.get("expected_sample_count") or 0)
        observed = int(protocol.get("observed_sample_count") or 0)
        completeness = observed / expected if expected > 0 else -1.0
    if completeness < DEFAULT_THRESHOLDS.min_protocol_completion:
        return False, "stable_observation_data_incomplete", completeness
    return True, None, min(completeness, 1.0)


def _reference_complete(link: Mapping[str, Any]) -> bool:
    model_complete = bool(link.get("behavioral_model_id") and link.get("behavioral_model_version"))
    baseline_complete = bool(link.get("baseline_reference_id") and link.get("baseline_reference_version"))
    return bool(
        link.get("compatibility_epoch")
        and link.get("telemetry_schema_fingerprint")
        and link.get("system_configuration_fingerprint")
        and (model_complete or baseline_complete)
    )


def _classify_row(
    outcome: Mapping[str, Any],
    link: Mapping[str, Any],
    *,
    required_context_dimensions: Sequence[str],
) -> dict[str, Any]:
    context = _parse_json(link.get("context_json"), {})
    provenance = _parse_json(outcome.get("provenance_categories_json"), [])
    if not isinstance(context, Mapping):
        context = {}
    if not isinstance(provenance, list):
        provenance = []
    disposition = str(outcome.get("health_disposition") or "")
    subject_state = str(link.get("subject_state") or "")
    stable_ok, stable_reason, telemetry_completeness = _stable_protocol_eligibility(outcome)
    context_ok = _context_complete(context, required_context_dimensions)
    reason: str | None = None
    treatment = "neutral"
    outcome_class: str | None = None

    if str(outcome.get("validation_status")) != "validated":
        reason = "outcome_not_validated"
    elif str(link.get("link_status")) != "active":
        reason = "link_not_active"
    elif str(link.get("outcome_revision_id")) != str(outcome.get("outcome_revision_id")):
        reason = "outcome_revision_not_effective"
    elif str(outcome.get("dedup_status")) in {"possible_duplicate", "unadjudicated"}:
        reason = "possible_duplicate_unresolved"
    elif str(outcome.get("dedup_status")) == "confirmed_duplicate":
        reason = "confirmed_duplicate_suppressed"
        treatment = "duplicate_suppressed"
    elif not outcome.get("canonical_incident_key"):
        reason = "canonical_incident_identity_missing"
    elif not outcome.get("validated_by") or not outcome.get("validated_at"):
        reason = "validation_provenance_incomplete"
    elif str(outcome.get("authority_tier")) not in {"A", "B", "C", "D"}:
        reason = "authority_tier_incomplete"
    elif not _reference_complete(link):
        reason = "reference_binding_incomplete"
    elif not context_ok:
        reason = "context_metadata_incomplete"
    elif subject_state == "not_evaluable":
        reason = "subject_not_evaluable"
    elif not stable_ok:
        reason = stable_reason
    elif str(link.get("link_confidence")) == "limited":
        reason = "limited_link_confidence"

    if reason is None:
        if disposition in _POSITIVE_DISPOSITIONS:
            outcome_class = "validated_health_outcome"
            treatment = "positive" if subject_state == "active_changed" else "comparison"
        elif disposition in _COMPARISON_DISPOSITIONS:
            outcome_class = "explicit_comparison"
            treatment = "negative" if subject_state == "active_changed" else "comparison"
        elif disposition in _NEGATIVE_DISPOSITIONS:
            treatment = "negative" if subject_state == "active_changed" else "comparison"
        else:
            treatment = "neutral"

    eligible = reason is None
    if not eligible and treatment != "duplicate_suppressed":
        treatment = "excluded"
    information_cell = None
    if eligible and outcome_class:
        if subject_state == "active_changed":
            information_cell = "a" if outcome_class == "validated_health_outcome" else "b"
        elif subject_state in {"present_aligned", "absent_evaluable"}:
            information_cell = "c" if outcome_class == "validated_health_outcome" else "d"

    return {
        "eligible": eligible,
        "evidence_treatment": treatment,
        "treatment": treatment,
        "exclusion_reason": reason,
        "reason_code": reason or f"eligible_{treatment}",
        "outcome_class": outcome_class,
        "information_cell": information_cell,
        "context_complete": context_ok,
        "telemetry_completeness": telemetry_completeness,
        "provenance_categories": sorted(str(item) for item in provenance),
    }


def _protocol_counts(outcome: Mapping[str, Any]) -> tuple[int, int]:
    protocol = _parse_json(outcome.get("observation_protocol_json"), {})
    if not isinstance(protocol, Mapping) or not protocol:
        return 0, 0
    try:
        scheduled = max(0, int(protocol.get("scheduled_windows") or 1))
        completed = max(
            0,
            int(
                protocol.get("completed_windows")
                if protocol.get("completed_windows") is not None
                else int(protocol.get("completed") is True)
            ),
        )
    except (TypeError, ValueError):
        return 0, 0
    return scheduled, min(completed, scheduled) if scheduled else completed


def _protocol_identity(outcome: Mapping[str, Any]) -> str | None:
    protocol = _parse_json(outcome.get("observation_protocol_json"), {})
    if not isinstance(protocol, Mapping) or not protocol:
        return None
    protocol_id = str(protocol.get("protocol_id") or "").strip()
    protocol_version = str(protocol.get("protocol_version") or "").strip()
    if not protocol_id or not protocol_version:
        return None
    return f"{protocol_id}:{protocol_version}"


def _windows_overlap(
    first_start: datetime,
    first_end: datetime,
    second_start: datetime,
    second_end: datetime,
) -> bool:
    # Observation windows are half-open. Adjacent windows are independent;
    # identical and partially/nested overlapping windows are not.
    return first_start < second_end and second_start < first_end


def _build_frozen_manifest_in_connection(
    connection: sqlite3.Connection,
    access: Any,
    *,
    subject_type: str,
    subject_id: str,
    subject_mapping_version: str,
    context_fingerprint: str,
    compatibility_epoch: str,
    required_context_dimensions: Sequence[str],
) -> dict[str, Any]:
    scope_storage_id, tenant_id, facility_id, system_id = _access_parts(access)
    links = _latest_rows(
        connection,
        "validated_outcome_links",
        "link_id",
        scope_storage_id=scope_storage_id,
        tenant_id=tenant_id,
        facility_id=facility_id,
        system_id=system_id,
        extra_sql="""
          AND current.subject_type = ?
          AND current.subject_id = ?
          AND current.subject_mapping_version = ?
          AND current.context_fingerprint = ?
          AND current.compatibility_epoch = ?
        """,
        extra_params=(
            subject_type,
            subject_id,
            subject_mapping_version,
            context_fingerprint,
            compatibility_epoch,
        ),
    )
    outcomes = _latest_rows(
        connection,
        "validated_outcomes",
        "outcome_id",
        scope_storage_id=scope_storage_id,
        tenant_id=tenant_id,
        facility_id=facility_id,
        system_id=system_id,
    )
    outcomes_by_id = {str(row["outcome_id"]): row for row in outcomes}
    links.sort(
        key=lambda row: (
            _parse_time(row.get("window_start_at")) or datetime.max.replace(tzinfo=UTC),
            _parse_time(row.get("window_end_at")) or datetime.max.replace(tzinfo=UTC),
            str(row.get("link_id") or ""),
            str(row.get("link_revision_id") or ""),
        )
    )
    contributions: list[dict[str, Any]] = []
    seen_observations: set[tuple[str, str, str]] = set()
    seen_method_units: set[tuple[str, str]] = set()
    scheduled_protocols: dict[str, tuple[int, int]] = {}
    accepted_protocol_windows: dict[str, list[tuple[datetime, datetime]]] = {}

    for link in links:
        outcome = outcomes_by_id.get(str(link["outcome_id"]))
        if outcome is None:
            continue
        classification = _classify_row(
            outcome,
            link,
            required_context_dimensions=required_context_dimensions,
        )
        protocol_identity = _protocol_identity(outcome)
        if (
            classification["eligible"]
            and classification.get("outcome_class") == "explicit_comparison"
            and protocol_identity is not None
        ):
            window_start = _parse_time(link.get("window_start_at"))
            window_end = _parse_time(link.get("window_end_at"))
            if window_start is None or window_end is None:
                classification.update(
                    eligible=False,
                    evidence_treatment="excluded",
                    treatment="excluded",
                    exclusion_reason="comparison_window_invalid",
                    reason_code="comparison_window_invalid",
                )
            else:
                accepted_windows = accepted_protocol_windows.setdefault(protocol_identity, [])
                if any(
                    _windows_overlap(window_start, window_end, accepted_start, accepted_end)
                    for accepted_start, accepted_end in accepted_windows
                ):
                    classification.update(
                        eligible=False,
                        evidence_treatment="duplicate_suppressed",
                        treatment="duplicate_suppressed",
                        exclusion_reason="overlapping_comparison_window_suppressed",
                        reason_code="overlapping_comparison_window_suppressed",
                    )
                else:
                    accepted_windows.append((window_start, window_end))
        observation_key = (
            str(outcome.get("outcome_revision_id")),
            str(outcome.get("canonical_incident_key") or outcome.get("outcome_id")),
            str(classification.get("information_cell") or classification["evidence_treatment"]),
        )
        classification["state_eligible"] = classification["eligible"]
        classification["state_evidence_treatment"] = classification["evidence_treatment"]
        if classification["eligible"] and observation_key in seen_observations:
            classification.update(
                eligible=False,
                state_eligible=False,
                evidence_treatment="duplicate_suppressed",
                treatment="duplicate_suppressed",
                exclusion_reason="duplicate_subject_observation",
                reason_code="duplicate_subject_observation",
            )
        elif classification["eligible"]:
            seen_observations.add(observation_key)
            method_unit = (
                str(outcome.get("canonical_incident_key") or outcome.get("outcome_id")),
                str(classification.get("information_cell") or classification["evidence_treatment"]),
            )
            if method_unit in seen_method_units:
                classification.update(
                    eligible=False,
                    evidence_treatment="duplicate_suppressed",
                    treatment="duplicate_suppressed",
                    exclusion_reason="same_incident_method_unit_suppressed",
                    reason_code="same_incident_method_unit_suppressed",
                )
            else:
                seen_method_units.add(method_unit)

        if classification["eligible"] and protocol_identity is not None:
            scheduled_protocols[protocol_identity] = _protocol_counts(outcome)

        contribution = {
            **classification,
            "contribution_id": f"manifest-{link['link_revision_id']}",
            "outcome_id": outcome["outcome_id"],
            "outcome_revision_id": outcome["outcome_revision_id"],
            "link_id": link["link_id"],
            "link_revision_id": link["link_revision_id"],
            "canonical_incident_key": outcome.get("canonical_incident_key"),
            "outcome_family": outcome["outcome_family"],
            "health_disposition": outcome["health_disposition"],
            "outcome_type": outcome["outcome_type"],
            "authority_tier": outcome["authority_tier"],
            "subject_state": link["subject_state"],
            "temporal_role": link["temporal_role"],
            "context_episode_id": link["context_episode_id"],
            "occurred_start_at": outcome["occurred_start_at"],
            "occurred_end_at": outcome["occurred_end_at"],
            "window_start_at": link["window_start_at"],
            "window_end_at": link["window_end_at"],
            "reported_by": outcome["reported_by"],
            "validated_by": outcome.get("validated_by"),
            "same_actor_validation": bool(
                outcome.get("validated_by")
                and str(outcome.get("reported_by")) == str(outcome.get("validated_by"))
            ),
            "finding_id": link.get("finding_id"),
            "evidence_run_id": link.get("evidence_run_id"),
            "evidence_package_id": link.get("evidence_package_id"),
            "evidence_content_hash": link.get("evidence_content_hash"),
            "behavioral_model_id": link.get("behavioral_model_id"),
            "behavioral_model_version": link.get("behavioral_model_version"),
            "behavioral_snapshot_id": link.get("behavioral_snapshot_id"),
            "baseline_reference_id": link.get("baseline_reference_id"),
            "baseline_reference_version": link.get("baseline_reference_version"),
            "telemetry_schema_fingerprint": link.get("telemetry_schema_fingerprint"),
            "system_configuration_fingerprint": link.get("system_configuration_fingerprint"),
            "asset_equipment_id": link.get("asset_equipment_id") or outcome.get("asset_equipment_id"),
        }
        contributions.append(contribution)

    contributions.sort(
        key=lambda row: (
            str(row["outcome_id"]),
            str(row["outcome_revision_id"]),
            str(row["link_id"]),
            str(row["link_revision_id"]),
        )
    )
    manifest_core = {
        "schema_version": "health-relevance-frozen-manifest.v1",
        "scope": {
            "scope_storage_id": scope_storage_id,
            "tenant_id": tenant_id,
            "facility_id": facility_id,
            "system_id": system_id,
        },
        "state_key": {
            "subject_type": subject_type,
            "subject_id": subject_id,
            "subject_mapping_version": subject_mapping_version,
            "context_fingerprint": context_fingerprint,
            "compatibility_epoch": compatibility_epoch,
        },
        "required_context_dimensions": list(required_context_dimensions),
        "protocol_schedules": scheduled_protocols,
        "contributions": contributions,
        "outcome_watermark": max(
            (str(row.get("recorded_at") or "") for row in outcomes), default="none"
        ),
        "link_watermark": max(
            (str(row.get("recorded_at") or "") for row in links), default="none"
        ),
    }
    manifest_hash = _stable_hash(manifest_core)
    return {
        **manifest_core,
        "input_snapshot_id": f"hrsnap-{manifest_hash[:24]}",
        "input_manifest_hash": manifest_hash,
    }


def build_frozen_manifest(
    access: Any,
    *,
    subject_type: str,
    subject_id: str,
    subject_mapping_version: str,
    context_fingerprint: str,
    compatibility_epoch: str,
    required_context_dimensions: Sequence[str] = ("operating_mode",),
) -> dict[str, Any]:
    """Build one immutable, exact-scope input consumed unchanged by both methods."""

    _authorize(access)
    _validate_state_key(
        subject_type=subject_type,
        subject_id=subject_id,
        subject_mapping_version=subject_mapping_version,
        context_fingerprint=context_fingerprint,
        compatibility_epoch=compatibility_epoch,
    )
    init_runtime_db()
    with db_connection() as connection:
        return _build_frozen_manifest_in_connection(
            connection,
            access,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_mapping_version=subject_mapping_version,
            context_fingerprint=context_fingerprint,
            compatibility_epoch=compatibility_epoch,
            required_context_dimensions=tuple(required_context_dimensions),
        )


def summarize_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    rows = list(manifest.get("contributions") or [])
    eligible = [row for row in rows if row.get("state_eligible", row.get("eligible")) is True]
    directional = [
        row
        for row in eligible
        if row.get("state_evidence_treatment", row.get("evidence_treatment"))
        in {"positive", "negative"}
    ]
    incidents = {str(row["canonical_incident_key"]) for row in eligible if row.get("canonical_incident_key")}
    positive_incidents = {
        str(row["canonical_incident_key"])
        for row in directional
        if row.get("state_evidence_treatment", row.get("evidence_treatment")) == "positive"
    }
    negative_incidents = {
        str(row["canonical_incident_key"])
        for row in directional
        if row.get("state_evidence_treatment", row.get("evidence_treatment")) == "negative"
    }
    primary_positive = {
        str(row["canonical_incident_key"])
        for row in directional
        if row.get("state_evidence_treatment", row.get("evidence_treatment")) == "positive"
        and row.get("authority_tier") in _PRIMARY_TIERS
    }
    primary_negative = {
        str(row["canonical_incident_key"])
        for row in directional
        if row.get("state_evidence_treatment", row.get("evidence_treatment")) == "negative"
        and row.get("authority_tier") in _PRIMARY_TIERS
    }
    tiers: Counter[str] = Counter()
    distinct_tier_outcomes: set[tuple[str, str]] = set()
    for row in eligible:
        key = (str(row.get("outcome_revision_id")), str(row.get("authority_tier")))
        if key not in distinct_tier_outcomes:
            distinct_tier_outcomes.add(key)
            tiers[str(row.get("authority_tier"))] += 1
    eligible_outcomes = {str(row["outcome_revision_id"]) for row in eligible}
    positive_families = {
        str(row["outcome_family"])
        for row in eligible
        if row.get("state_evidence_treatment", row.get("evidence_treatment")) == "positive"
    }
    family_counts = Counter(
        str(row["outcome_family"])
        for row in eligible
        if row.get("outcome_family")
    )
    comparison_windows = {
        (str(row["canonical_incident_key"]), str(row["window_start_at"]), str(row["window_end_at"]))
        for row in eligible
        if row.get("outcome_class") == "explicit_comparison"
    }
    context_candidates = [row for row in rows if row.get("evidence_treatment") != "duplicate_suppressed"]
    context_complete = sum(bool(row.get("context_complete")) for row in context_candidates)
    context_completeness = (
        context_complete / len(context_candidates) if context_candidates else 0.0
    )
    episodes = {str(row["context_episode_id"]) for row in eligible if row.get("context_episode_id")}
    schedules = manifest.get("protocol_schedules") or {}
    scheduled = sum(int(values[0]) for values in schedules.values()) if schedules else 0
    completed = sum(int(values[1]) for values in schedules.values()) if schedules else 0
    protocol_completion = completed / scheduled if scheduled > 0 else None
    positive = len(positive_incidents)
    negative = len(negative_incidents)
    primary_p = len(primary_positive)
    primary_n = len(primary_negative)
    last_times = [
        parsed
        for row in eligible
        for parsed in (_parse_time(row.get("window_end_at") or row.get("occurred_end_at")),)
        if parsed is not None
    ]
    first_times = [
        parsed
        for row in eligible
        for parsed in (_parse_time(row.get("window_start_at") or row.get("occurred_start_at")),)
        if parsed is not None
    ]
    return {
        "raw_outcome_count": len({str(row.get("outcome_id")) for row in rows}),
        "eligible_outcome_count": len(eligible_outcomes),
        "canonical_incident_count": len(incidents),
        "recurrence_count": len(incidents),
        "positive_count": positive,
        "negative_count": negative,
        "neutral_count": sum(
            row.get("state_evidence_treatment", row.get("evidence_treatment")) == "neutral"
            for row in eligible
        ),
        "comparison_window_count": len(comparison_windows),
        "excluded_count": sum(row.get("evidence_treatment") == "excluded" for row in rows),
        "duplicate_suppressed_count": sum(
            row.get("evidence_treatment") == "duplicate_suppressed" for row in rows
        ),
        "outcome_family_counts": dict(sorted(family_counts.items())),
        "positive_family_count": len(positive_families),
        "context_metadata_completeness": context_completeness,
        "context_episode_count": len(episodes),
        "protocol_completion": protocol_completion,
        "tier_a_count": tiers["A"],
        "tier_b_count": tiers["B"],
        "tier_c_count": tiers["C"],
        "tier_d_count": tiers["D"],
        "independent_count": tiers["A"] + tiers["B"],
        "neraium_influenced_count": tiers["D"],
        "same_actor_validation_count": len(
            {
                str(row["outcome_revision_id"])
                for row in eligible
                if row.get("same_actor_validation")
            }
        ),
        "positive_balance_all": positive / (positive + negative) if positive + negative else None,
        "positive_balance_primary": primary_p / (primary_p + primary_n)
        if primary_p + primary_n
        else None,
        "primary_positive_count": primary_p,
        "primary_negative_count": primary_n,
        "hard_eligibility_failure": any(
            row.get("exclusion_reason")
            in {
                "validation_provenance_incomplete",
                "authority_tier_incomplete",
                "reference_binding_incomplete",
                "context_metadata_incomplete",
            }
            for row in rows
        ),
        "limited_link_count": sum(
            row.get("exclusion_reason") == "limited_link_confidence" for row in rows
        ),
        "first_evidence_at": _iso(min(first_times)) if first_times else None,
        "last_evidence_at": _iso(max(last_times)) if last_times else None,
    }


def _stratum_is_contradictory(
    positive: int,
    negative: int,
    balance: float | None,
    config: ThresholdConfig,
) -> bool:
    total = positive + negative
    if (
        positive < config.contradictory_min_positive
        or negative < config.contradictory_min_negative
        or total < config.contradictory_min_directional
    ):
        return False
    resolved_balance = positive / total if balance is None else float(balance)
    return (
        config.contradictory_min_balance
        <= resolved_balance
        <= config.contradictory_max_balance
    )


def _stratum_is_negative_dominant(
    positive: int,
    negative: int,
    incidents: int,
    balance: float | None,
    config: ThresholdConfig,
) -> bool:
    total = positive + negative
    resolved_balance = positive / total if total and balance is None else balance
    return bool(
        total
        and resolved_balance is not None
        and float(resolved_balance) <= config.unsupported_max_positive_balance
        and negative >= config.unsupported_min_negative
        and incidents >= config.unsupported_min_incidents
    )


def _method_gate(method_id: str, result: Mapping[str, Any], config: ThresholdConfig) -> tuple[bool, str]:
    components = result.get("components") or {}
    primary = components.get("primary_view") or {}
    if method_id == BAYESIAN_METHOD_ID:
        lower = (((primary.get("posterior") or {}).get("credible_interval_90") or {}).get("lower"))
        return bool(lower is not None and float(lower) >= config.bayesian_min_lower_bound_90), "bayesian_strength_below_threshold"
    if method_id == INFORMATION_METHOD_ID:
        adjusted = primary.get("adjusted_normalized_information")
        observed = primary.get("observed_normalized_information")
        null_95 = (primary.get("permutation_reference") or {}).get("null_percentile_95")
        passed = bool(
            adjusted is not None
            and observed is not None
            and null_95 is not None
            and float(adjusted) >= config.information_min_adjusted_normalized
            and float(observed) > float(null_95)
        )
        return passed, "information_strength_below_threshold"
    raise HealthRelevanceInputError("unapproved relevance method")


def evaluate_evidence_state(
    summary: Mapping[str, Any],
    method_id: str,
    method_result: Mapping[str, Any],
    *,
    thresholds: ThresholdConfig = DEFAULT_THRESHOLDS,
) -> dict[str, Any]:
    """Apply the shared fail-closed state machine after a pure method evaluation."""

    p_all = int(summary.get("positive_count") or 0)
    n_all = int(summary.get("negative_count") or 0)
    p_primary = int(summary.get("primary_positive_count") or 0)
    n_primary = int(summary.get("primary_negative_count") or 0)
    incidents = int(summary.get("canonical_incident_count") or 0)
    balance_all = summary.get("positive_balance_all")
    balance_primary = summary.get("positive_balance_primary")
    if p_all + n_all == 0:
        direction = "indeterminate"
    elif balance_all is not None and float(balance_all) >= thresholds.supported_positive_balance:
        direction = "positive_dominant"
    elif balance_all is not None and float(balance_all) <= thresholds.unsupported_max_positive_balance:
        direction = "negative_dominant"
    else:
        direction = "mixed"

    reasons: list[str] = []
    if summary.get("hard_eligibility_failure"):
        reasons.append("identity_context_or_provenance_incomplete")
    if int(summary.get("eligible_outcome_count") or 0) < thresholds.emerging_min_outcomes:
        reasons.append("emerging_outcome_minimum_not_met")
    if incidents < thresholds.emerging_min_incidents:
        reasons.append("emerging_recurrence_minimum_not_met")
    if reasons:
        return {
            "evidence_state": "insufficient_outcome_evidence",
            "evidence_direction": direction,
            "state_reason_codes": reasons,
        }

    primary_contradiction = _stratum_is_contradictory(
        p_primary, n_primary, balance_primary, thresholds
    )
    all_contradiction = _stratum_is_contradictory(p_all, n_all, balance_all, thresholds)
    if primary_contradiction or all_contradiction:
        return {
            "evidence_state": "contradictory_evidence",
            "evidence_direction": "mixed",
            "state_reason_codes": [
                "primary_evidence_in_contradictory_band"
                if primary_contradiction
                else "all_evidence_in_contradictory_band"
            ],
        }

    primary_negative = _stratum_is_negative_dominant(
        p_primary, n_primary, incidents, balance_primary, thresholds
    )
    all_negative = _stratum_is_negative_dominant(
        p_all, n_all, incidents, balance_all, thresholds
    )
    if primary_negative or all_negative:
        return {
            "evidence_state": "not_supported_by_outcomes",
            "evidence_direction": "negative_dominant",
            "state_reason_codes": [
                "primary_negative_evidence_dominant"
                if primary_negative
                else "all_negative_evidence_dominant"
            ],
        }

    support_gates = (
        (int(summary.get("eligible_outcome_count") or 0) >= thresholds.supported_min_outcomes, "supported_outcome_minimum_not_met"),
        (incidents >= thresholds.supported_min_incidents, "supported_recurrence_minimum_not_met"),
        (balance_primary is not None and float(balance_primary) >= thresholds.supported_positive_balance, "primary_positive_balance_not_met"),
        (balance_all is not None and float(balance_all) >= thresholds.supported_positive_balance, "all_positive_balance_not_met"),
        (float(summary.get("context_metadata_completeness") or 0.0) >= thresholds.min_context_completeness, "context_completeness_not_met"),
        (int(summary.get("context_episode_count") or 0) >= thresholds.min_context_episodes, "context_episode_coverage_not_met"),
        (summary.get("protocol_completion") is None or float(summary["protocol_completion"]) >= thresholds.min_protocol_completion, "stable_protocol_completion_not_met"),
        (int(summary.get("comparison_window_count") or 0) >= thresholds.min_comparison_windows, "explicit_comparison_denominator_not_met"),
        (int(summary.get("positive_family_count") or 0) >= thresholds.min_positive_families, "outcome_diversity_not_met"),
        (int(summary.get("independent_count") or 0) >= thresholds.min_independent_outcomes, "independent_evidence_not_met"),
        (int(summary.get("tier_a_count") or 0) >= thresholds.min_tier_a_outcomes, "tier_a_evidence_not_met"),
        (int(summary.get("limited_link_count") or 0) == 0, "limited_link_prevents_support"),
    )
    reasons.extend(reason for passed, reason in support_gates if not passed)
    method_passed, method_reason = _method_gate(method_id, method_result, thresholds)
    if not method_passed:
        reasons.append(method_reason)
    return {
        "evidence_state": "emerging_relevance" if reasons else "supported_relevance",
        "evidence_direction": direction,
        "state_reason_codes": reasons or ["all_experimental_support_gates_met"],
    }


def _state_key_hash(manifest: Mapping[str, Any], method_id: str) -> str:
    return _stable_hash(
        {
            "scope": manifest["scope"],
            "state_key": manifest["state_key"],
            "method_class": method_id,
            "method_version": method_id,
            "threshold_config_version": THRESHOLD_CONFIG_VERSION,
        }
    )


def _configuration(method_id: str, thresholds: ThresholdConfig, method_config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "threshold_config_version": THRESHOLD_CONFIG_VERSION,
        "thresholds": asdict(thresholds),
        "method_config_version": METHOD_CONFIG_VERSION,
        "method_id": method_id,
        "method_config": dict(method_config),
        "authority_rules_version": AUTHORITY_RULES_VERSION,
        "dedup_rules_version": DEDUP_RULES_VERSION,
        "compatibility_rules_version": COMPATIBILITY_RULES_VERSION,
    }


def _insert_version_and_contributions(
    connection: sqlite3.Connection,
    access: Any,
    manifest: Mapping[str, Any],
    summary: Mapping[str, Any],
    method_id: str,
    method_result: Mapping[str, Any],
    state: Mapping[str, Any],
    *,
    thresholds: ThresholdConfig,
    method_config: Mapping[str, Any],
    computed_at: datetime,
    code_build_version: str,
) -> dict[str, Any]:
    scope = manifest["scope"]
    state_key = manifest["state_key"]
    state_key_hash = _state_key_hash(manifest, method_id)
    config = _configuration(method_id, thresholds, method_config)
    config_hash = _stable_hash(config)
    existing = connection.execute(
        """
        SELECT * FROM health_relevance_versions
        WHERE state_key_hash = ? AND input_snapshot_id = ? AND input_manifest_hash = ?
          AND method_class = ? AND method_version = ? AND configuration_hash = ?
          AND code_build_version = ?
        """,
        (
            state_key_hash,
            manifest["input_snapshot_id"],
            manifest["input_manifest_hash"],
            method_id,
            method_id,
            config_hash,
            code_build_version,
        ),
    ).fetchone()
    if existing is not None:
        return {**_decode_row(existing, _VERSION_JSON_FIELDS), "created": False}

    previous = connection.execute(
        "SELECT * FROM health_relevance_versions WHERE state_key_hash = ? ORDER BY version DESC LIMIT 1",
        (state_key_hash,),
    ).fetchone()
    version = int(previous["version"]) + 1 if previous is not None else 1
    previous_id = str(previous["relevance_version_id"]) if previous is not None else None
    relevance_version_id = f"hrv-{uuid.uuid4()}"
    actor = str(getattr(access, "actor", "internal-health-relevance"))
    latest = summary.get("last_evidence_at")
    freshness = freshness_status(
        latest,
        as_of=computed_at,
        stale_after_days=thresholds.stale_after_days,
    )
    values = {
        "relevance_version_id": relevance_version_id,
        "state_key_hash": state_key_hash,
        "version": version,
        **scope,
        "asset_equipment_id": next(
            (row.get("asset_equipment_id") for row in manifest["contributions"] if row.get("asset_equipment_id")),
            None,
        ),
        **state_key,
        "context_schema_version": "health-relevance-context.v1",
        "context_json": _canonical_json({"fingerprint": state_key["context_fingerprint"]}),
        "method_class": method_id,
        "method_version": method_id,
        "method_config_version": METHOD_CONFIG_VERSION,
        "input_snapshot_id": manifest["input_snapshot_id"],
        "input_manifest_hash": manifest["input_manifest_hash"],
        "outcome_watermark": manifest["outcome_watermark"],
        "link_watermark": manifest["link_watermark"],
        "previous_version_id": previous_id,
        "raw_outcome_count": summary["raw_outcome_count"],
        "eligible_outcome_count": summary["eligible_outcome_count"],
        "canonical_incident_count": summary["canonical_incident_count"],
        "recurrence_count": summary["recurrence_count"],
        "positive_count": summary["positive_count"],
        "negative_count": summary["negative_count"],
        "neutral_count": summary["neutral_count"],
        "comparison_window_count": summary["comparison_window_count"],
        "excluded_count": summary["excluded_count"],
        "duplicate_suppressed_count": summary["duplicate_suppressed_count"],
        "outcome_family_counts_json": _canonical_json(summary["outcome_family_counts"]),
        "context_metadata_completeness": summary["context_metadata_completeness"],
        "context_episode_count": summary["context_episode_count"],
        "protocol_completion": summary["protocol_completion"],
        "temporal_consistency": None,
        "tier_a_count": summary["tier_a_count"],
        "tier_b_count": summary["tier_b_count"],
        "tier_c_count": summary["tier_c_count"],
        "tier_d_count": summary["tier_d_count"],
        "independent_count": summary["independent_count"],
        "neraium_influenced_count": summary["neraium_influenced_count"],
        "same_actor_validation_count": summary["same_actor_validation_count"],
        "evidence_state": state["evidence_state"],
        "evidence_direction": state["evidence_direction"],
        "state_reason_codes_json": _canonical_json(state["state_reason_codes"]),
        "freshness_status": freshness,
        "method_components_json": _canonical_json(method_result["components"]),
        "uncertainty_json": _canonical_json(method_result["uncertainty"]),
        "outcome_schema_version": OUTCOME_SCHEMA_VERSION,
        "threshold_config_version": THRESHOLD_CONFIG_VERSION,
        "threshold_config_json": _canonical_json(asdict(thresholds)),
        "authority_rules_version": AUTHORITY_RULES_VERSION,
        "dedup_rules_version": DEDUP_RULES_VERSION,
        "compatibility_rules_version": COMPATIBILITY_RULES_VERSION,
        "configuration_hash": config_hash,
        "first_evidence_at": summary["first_evidence_at"],
        "last_evidence_at": latest,
        "computed_at": _iso(computed_at),
        "created_by": actor,
        "code_build_version": code_build_version,
    }
    columns = tuple(values)
    connection.execute(
        f"INSERT INTO health_relevance_versions ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
        tuple(values[column] for column in columns),
    )
    method_contributions = {
        str(item.get("contribution_id")): item for item in method_result.get("contributions") or []
    }
    for row in manifest["contributions"]:
        method_detail = method_contributions.get(str(row["contribution_id"]), {})
        cell = str(row.get("information_cell") or "not_applicable")
        treatment = str(row["evidence_treatment"])
        contribution_id = "hrc-" + _stable_hash(
            {
                "relevance_version_id": relevance_version_id,
                "outcome_revision_id": row["outcome_revision_id"],
                "link_revision_id": row["link_revision_id"],
                "evidence_treatment": treatment,
                "method_input_cell": cell,
            }
        )[:32]
        contribution_values = {
            "contribution_id": contribution_id,
            "relevance_version_id": relevance_version_id,
            "outcome_id": row["outcome_id"],
            "outcome_revision_id": row["outcome_revision_id"],
            "link_id": row["link_id"],
            "link_revision_id": row["link_revision_id"],
            **scope,
            "asset_equipment_id": row.get("asset_equipment_id"),
            "subject_type": state_key["subject_type"],
            "subject_id": state_key["subject_id"],
            "subject_mapping_version": state_key["subject_mapping_version"],
            "context_fingerprint": state_key["context_fingerprint"],
            "compatibility_epoch": state_key["compatibility_epoch"],
            "canonical_incident_key": row.get("canonical_incident_key"),
            "outcome_family": row["outcome_family"],
            "evidence_treatment": treatment,
            "subject_state": row["subject_state"],
            "temporal_role": row["temporal_role"],
            "authority_tier": row["authority_tier"],
            "provenance_categories_json": _canonical_json(row["provenance_categories"]),
            "method_input_cell": cell,
            "method_component_json": _canonical_json(method_detail),
            "reason_code": row["reason_code"],
            "finding_id": row.get("finding_id"),
            "evidence_run_id": row.get("evidence_run_id"),
            "evidence_package_id": row.get("evidence_package_id"),
            "evidence_content_hash": row.get("evidence_content_hash"),
            "behavioral_model_id": row.get("behavioral_model_id"),
            "behavioral_model_version": row.get("behavioral_model_version"),
            "behavioral_snapshot_id": row.get("behavioral_snapshot_id"),
            "baseline_reference_id": row.get("baseline_reference_id"),
            "baseline_reference_version": row.get("baseline_reference_version"),
            "telemetry_schema_fingerprint": row.get("telemetry_schema_fingerprint"),
            "system_configuration_fingerprint": row.get("system_configuration_fingerprint"),
            "input_manifest_hash": manifest["input_manifest_hash"],
            "configuration_hash": config_hash,
            "created_by": actor,
            "created_at": _iso(computed_at),
        }
        contribution_columns = tuple(contribution_values)
        connection.execute(
            f"INSERT INTO health_relevance_contributions ({', '.join(contribution_columns)}) VALUES ({', '.join('?' for _ in contribution_columns)})",
            tuple(contribution_values[column] for column in contribution_columns),
        )
    connection.execute(
        """
        INSERT INTO audit_events (
            created_at, request_id, actor, action, resource_type, resource_id, detail_json
        ) VALUES (?, NULL, ?, ?, 'health_relevance_version', ?, ?)
        """,
        (
            _iso(computed_at),
            actor,
            "health_relevance.version_created",
            relevance_version_id,
            _canonical_json(
                {
                    "scope_storage_id": scope["scope_storage_id"],
                    "facility_id": scope["facility_id"],
                    "system_id": scope["system_id"],
                    "state_key_hash": state_key_hash,
                    "method_class": method_id,
                    "input_manifest_hash": manifest["input_manifest_hash"],
                }
            ),
        ),
    )
    return {**_decode_row(values, _VERSION_JSON_FIELDS), "created": True}


def compute_health_relevance(
    access: Any,
    *,
    subject_type: str,
    subject_id: str,
    subject_mapping_version: str,
    context_fingerprint: str,
    compatibility_epoch: str,
    required_context_dimensions: Sequence[str] = ("operating_mode",),
    thresholds: ThresholdConfig = DEFAULT_THRESHOLDS,
    method_config: Mapping[str, Any] | None = None,
    computed_at: datetime | None = None,
    code_build_version: str = DEFAULT_CODE_BUILD_VERSION,
) -> dict[str, Any]:
    """Evaluate and append both approved methods over one identical frozen manifest."""

    _authorize(access)
    _validate_state_key(
        subject_type=subject_type,
        subject_id=subject_id,
        subject_mapping_version=subject_mapping_version,
        context_fingerprint=context_fingerprint,
        compatibility_epoch=compatibility_epoch,
    )
    if tuple(METHOD_REGISTRY) != _METHOD_IDS or len(METHOD_REGISTRY) != 2:
        raise RuntimeError("exactly two approved Health Relevance methods are required")
    now = (computed_at or datetime.now(UTC)).astimezone(UTC)
    configs = dict(method_config or {})
    init_runtime_db()
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        manifest = _build_frozen_manifest_in_connection(
            connection,
            access,
            subject_type=subject_type,
            subject_id=subject_id,
            subject_mapping_version=subject_mapping_version,
            context_fingerprint=context_fingerprint,
            compatibility_epoch=compatibility_epoch,
            required_context_dimensions=tuple(required_context_dimensions),
        )
        summary = summarize_manifest(manifest)
        versions: dict[str, dict[str, Any]] = {}
        for method_id in _METHOD_IDS:
            approved_config = configs.get(method_id) or {}
            result = evaluate_health_relevance_method(method_id, manifest, approved_config)
            state = evaluate_evidence_state(summary, method_id, result, thresholds=thresholds)
            versions[method_id] = _insert_version_and_contributions(
                connection,
                access,
                manifest,
                summary,
                method_id,
                result,
                state,
                thresholds=thresholds,
                method_config=approved_config,
                computed_at=now,
                code_build_version=code_build_version,
            )
    return {
        "input_snapshot_id": manifest["input_snapshot_id"],
        "input_manifest_hash": manifest["input_manifest_hash"],
        "summary": summary,
        "versions": versions,
    }


_VERSION_JSON_FIELDS = frozenset(
    {
        "context_json",
        "outcome_family_counts_json",
        "state_reason_codes_json",
        "method_components_json",
        "uncertainty_json",
        "threshold_config_json",
    }
)
_CONTRIBUTION_JSON_FIELDS = frozenset(
    {"provenance_categories_json", "method_component_json"}
)


def _decode_row(row: sqlite3.Row, json_fields: Sequence[str]) -> dict[str, Any]:
    decoded = dict(row)
    for field in json_fields:
        if field in decoded:
            decoded[field] = _parse_json(decoded[field], None)
    return decoded


def inspect_health_relevance(
    access: Any,
    *,
    subject_type: str,
    subject_id: str,
    subject_mapping_version: str,
    context_fingerprint: str,
    compatibility_epoch: str,
    method_class: str,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    """Return the latest exact-scope state and complete provenance; never list/discover."""

    _authorize(access)
    _validate_state_key(
        subject_type=subject_type,
        subject_id=subject_id,
        subject_mapping_version=subject_mapping_version,
        context_fingerprint=context_fingerprint,
        compatibility_epoch=compatibility_epoch,
    )
    if method_class not in _METHOD_IDS:
        raise HealthRelevanceNotFoundError("Health Relevance state not found.")
    scope_storage_id, tenant_id, facility_id, system_id = _access_parts(access)
    init_runtime_db()
    with db_connection() as connection:
        version = connection.execute(
            """
            SELECT * FROM health_relevance_versions
            WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ? AND system_id = ?
              AND subject_type = ? AND subject_id = ? AND subject_mapping_version = ?
              AND context_fingerprint = ? AND compatibility_epoch = ? AND method_class = ?
            ORDER BY version DESC LIMIT 1
            """,
            (
                scope_storage_id,
                tenant_id,
                facility_id,
                system_id,
                subject_type,
                subject_id,
                subject_mapping_version,
                context_fingerprint,
                compatibility_epoch,
                method_class,
            ),
        ).fetchone()
        if version is None:
            raise HealthRelevanceNotFoundError("Health Relevance state not found.")
        contributions = connection.execute(
            """
            SELECT * FROM health_relevance_contributions
            WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ? AND system_id = ?
              AND relevance_version_id = ?
            ORDER BY outcome_revision_id, link_revision_id, contribution_id
            """,
            (
                scope_storage_id,
                tenant_id,
                facility_id,
                system_id,
                version["relevance_version_id"],
            ),
        ).fetchall()
    decoded_version = _decode_row(version, _VERSION_JSON_FIELDS)
    effective_freshness = freshness_status(
        decoded_version.get("last_evidence_at"),
        as_of=as_of,
        stale_after_days=int(
            (decoded_version.get("threshold_config_json") or {}).get("stale_after_days", 180)
        ),
    )
    return {
        "internal_only": True,
        "non_causal": True,
        "state": decoded_version,
        "stored_freshness_status": decoded_version["freshness_status"],
        "effective_freshness_status": effective_freshness,
        "staleness_warning": (
            "Historical association evidence is stale and is not a statement of current health."
            if effective_freshness == "stale"
            else None
        ),
        "contributions": [
            _decode_row(row, _CONTRIBUTION_JSON_FIELDS) for row in contributions
        ],
    }


__all__ = [
    "AUTHORITY_RULES_VERSION",
    "COMPATIBILITY_RULES_VERSION",
    "DEDUP_RULES_VERSION",
    "DEFAULT_THRESHOLDS",
    "HealthRelevanceInputError",
    "HealthRelevanceNotFoundError",
    "ThresholdConfig",
    "build_frozen_manifest",
    "compute_health_relevance",
    "evaluate_evidence_state",
    "freshness_status",
    "inspect_health_relevance",
    "summarize_manifest",
]
