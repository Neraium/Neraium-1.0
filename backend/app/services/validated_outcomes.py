from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Sequence

from app.services.dataset_scope import DatasetScope
from app.services.runtime_db import db_connection, init_runtime_db, now_iso, record_audit_event


OUTCOME_SCHEMA_VERSION = "health-outcome.v1"
METADATA_SCHEMA_VERSION = "health-outcome-metadata.v1"
AUTHORITY_RULES_VERSION = "health-outcome-authority.v1"
DEDUP_RULES_VERSION = "health-outcome-dedup.v1"
MINIMUM_STABLE_SAMPLE_COVERAGE = 0.80

# A source name never grants authority. Tier A requires one of these explicit,
# versioned source-category/outcome-type pairs plus independent provenance and
# a stable external record identity. These are interface categories only; no
# connector or source-system approval is implied by this module.
AUTHORITATIVE_SOURCE_TYPE_RULES = {
    "maintenance": frozenset(
        {
            "confirmed_maintenance_event",
            "confirmed_fault",
            "confirmed_degraded_condition",
            "repair",
            "component_replacement",
        }
    ),
    "inspection": frozenset(
        {
            "inspection_result",
            "confirmed_fault",
            "confirmed_degraded_condition",
            "expected_no_fault_confirmation",
            "stable_operation_observation",
        }
    ),
    "fault_record": frozenset({"confirmed_fault", "confirmed_degraded_condition"}),
    "repair_record": frozenset({"repair", "component_replacement"}),
}

_OPERATIONAL_INCIDENT_FAMILIES = frozenset(
    {
        "degradation_or_fault",
        "inspection_confirmation",
        "maintenance_or_intervention",
        "repair_or_replacement",
        "recovery",
        "validated_explanation",
    }
)

PROVENANCE_CATEGORIES = frozenset(
    {
        "independently_documented_outcome",
        "maintenance_system_sourced",
        "inspection_sourced",
        "retrospective_label",
        "operator_confirmed_after_neraium_review",
        "other_explicitly_validated_human_outcome",
    }
)

OUTCOME_FAMILIES = {
    "confirmed_maintenance_event": "maintenance_or_intervention",
    "inspection_result": "inspection_confirmation",
    "confirmed_fault": "degradation_or_fault",
    "confirmed_degraded_condition": "degradation_or_fault",
    "repair": "repair_or_replacement",
    "component_replacement": "repair_or_replacement",
    "operator_confirmed_explanation": "validated_explanation",
    "return_toward_expected_behavior": "recovery",
    "expected_no_fault_confirmation": "expected_or_no_fault",
    "false_positive_not_useful": "not_useful_or_false_positive",
    "stable_operation_observation": "expected_or_no_fault",
}

HEALTH_DISPOSITIONS = frozenset(
    {
        "degraded",
        "fault_confirmed",
        "expected_behavior",
        "no_fault",
        "not_useful",
        "explained",
        "intervention_recorded",
        "recovery_observed",
        "unrelated_maintenance",
        "no_observed_behavior_change",
        "stable_observation",
        "indeterminate",
    }
)

VALIDATION_STATUSES = frozenset({"pending", "validated", "rejected", "retracted", "superseded"})
DEDUP_STATUSES = frozenset(
    {"canonical", "confirmed_distinct", "possible_duplicate", "confirmed_duplicate", "unadjudicated"}
)
SUBJECT_TYPES = frozenset({"signal", "relationship", "asset_equipment", "subsystem"})
TEMPORAL_ROLES = frozenset(
    {"pre_outcome", "outcome_period", "post_intervention", "recovery", "stable_comparison"}
)
SUBJECT_STATES = frozenset({"active_changed", "present_aligned", "absent_evaluable", "not_evaluable"})
LINK_STATUSES = frozenset({"pending", "active", "rejected", "retracted", "superseded"})
LINK_ORIGINS = frozenset({"direct_source", "human_reviewed", "deterministic_reference"})
LINK_CONFIDENCES = frozenset({"direct", "reviewed", "limited"})

_OUTCOME_JSON_FIELDS = frozenset(
    {
        "windows_json",
        "validation_basis_json",
        "provenance_categories_json",
        "reliability_basis_json",
        "possible_duplicate_of_json",
        "dedup_basis_json",
        "observation_protocol_json",
        "structured_metadata_json",
    }
)
_LINK_JSON_FIELDS = frozenset(
    {
        "context_json",
        "context_source_refs_json",
        "link_basis_json",
        "observation_basis_json",
    }
)


class HealthRelevanceAccessError(Exception):
    """Opaque response for unauthorized and nonexistent internal records."""


class HealthRelevanceValidationError(ValueError):
    pass


class HealthRelevanceConflictError(Exception):
    pass


def _policy_text(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise HealthRelevanceValidationError(f"{field}_required")
    return normalized


@dataclass(frozen=True)
class ApprovedOutcomeSourceRule:
    """One explicitly approved named source contract; never an integration."""

    rule_id: str
    source_system: str
    source_category: str
    allowed_outcome_types: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "rule_id", _policy_text(self.rule_id, "source_rule.rule_id"))
        object.__setattr__(
            self, "source_system", _policy_text(self.source_system, "source_rule.source_system")
        )
        category = _policy_text(self.source_category, "source_rule.source_category")
        object.__setattr__(self, "source_category", category)
        allowed = frozenset(self.allowed_outcome_types)
        semantic_types = AUTHORITATIVE_SOURCE_TYPE_RULES.get(category)
        if not allowed or semantic_types is None or not allowed <= semantic_types:
            raise HealthRelevanceValidationError("source_rule_outcome_types_invalid")
        object.__setattr__(self, "allowed_outcome_types", allowed)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "source_system": self.source_system,
            "source_category": self.source_category,
            "allowed_outcome_types": sorted(self.allowed_outcome_types),
        }


@dataclass(frozen=True)
class OutcomeSourceAuthorityPolicy:
    """Versioned allowlist supplied by an approved internal caller."""

    version: str
    rules: tuple[ApprovedOutcomeSourceRule, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "version", _policy_text(self.version, "source_policy.version"))
        normalized = tuple(self.rules)
        if any(not isinstance(rule, ApprovedOutcomeSourceRule) for rule in normalized):
            raise HealthRelevanceValidationError("source_policy_rule_invalid")
        identities = {(rule.source_system, rule.source_category) for rule in normalized}
        if len(identities) != len(normalized):
            raise HealthRelevanceValidationError("source_policy_rule_duplicate")
        object.__setattr__(self, "rules", normalized)

    def matching_rule(
        self, *, source_system: str | None, source_category: str, outcome_type: str
    ) -> ApprovedOutcomeSourceRule | None:
        if not source_system:
            return None
        return next(
            (
                rule
                for rule in self.rules
                if rule.source_system == source_system
                and rule.source_category == source_category
                and outcome_type in rule.allowed_outcome_types
            ),
            None,
        )

    def as_dict(self) -> dict[str, Any]:
        return {"version": self.version, "rules": [rule.as_dict() for rule in self.rules]}


DEFAULT_OUTCOME_SOURCE_AUTHORITY_POLICY = OutcomeSourceAuthorityPolicy(
    version="unconfigured-no-tier-a-sources",
    rules=(),
)


@dataclass(frozen=True)
class InternalHealthRelevanceAccess:
    """Previously authorized exact-scope envelope for the internal service.

    ``workspace_authorized`` is set only after the caller has resolved the
    workspace through the existing allowlisted service-token path. This class
    adds no identity, role, or permission store.
    """

    scope: DatasetScope
    facility_id: str
    system_id: str
    actor: str
    auth_source: str
    role: str
    workspace_authorized: bool


def authorize_internal_access(
    *,
    scope: DatasetScope,
    facility_id: str,
    system_id: str,
    actor: str,
    auth_source: str,
    role: str,
    workspace_authorized: bool,
) -> InternalHealthRelevanceAccess:
    access = InternalHealthRelevanceAccess(
        scope=scope,
        facility_id=_required_text(facility_id, "facility_id"),
        system_id=_required_text(system_id, "system_id"),
        actor=_required_text(actor, "actor"),
        auth_source=str(auth_source or "").strip(),
        role=str(role or "").strip().lower(),
        workspace_authorized=bool(workspace_authorized),
    )
    _require_access(access)
    return access


def _require_access(access: InternalHealthRelevanceAccess) -> None:
    if (
        not isinstance(access, InternalHealthRelevanceAccess)
        or not isinstance(access.scope, DatasetScope)
        or access.auth_source != "service_token"
        or access.role != "admin"
        or not access.workspace_authorized
        or not access.facility_id.strip()
        or not access.system_id.strip()
        or not access.actor.strip()
    ):
        raise HealthRelevanceAccessError("Health relevance record not found.")


def require_internal_access(
    access: InternalHealthRelevanceAccess,
) -> InternalHealthRelevanceAccess:
    """Validate and return an already resolved internal authorization envelope."""
    _require_access(access)
    return access


def _required_text(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise HealthRelevanceValidationError(f"{field}_required")
    return normalized


def _optional_text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _json_object(value: Any, field: str, *, default: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if value is None:
        return dict(default or {})
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HealthRelevanceValidationError(f"{field}_invalid") from exc
    if not isinstance(value, Mapping):
        raise HealthRelevanceValidationError(f"{field}_invalid")
    return dict(value)


def _json_array(value: Any, field: str, *, default: Sequence[Any] = ()) -> list[Any]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise HealthRelevanceValidationError(f"{field}_invalid") from exc
    if not isinstance(value, list):
        raise HealthRelevanceValidationError(f"{field}_invalid")
    return list(value)


def _parse_time(value: Any, field: str) -> datetime:
    normalized = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HealthRelevanceValidationError(f"{field}_invalid") from exc
    if parsed.tzinfo is None:
        raise HealthRelevanceValidationError(f"{field}_timezone_required")
    return parsed.astimezone(UTC)


def _iso(value: Any, field: str) -> str:
    return _parse_time(value, field).isoformat()


def _hash(parts: Any) -> str:
    return hashlib.sha256(_canonical_json(parts).encode("utf-8")).hexdigest()


def compute_request_fingerprint(
    operation: str, access: InternalHealthRelevanceAccess, payload: Mapping[str, Any]
) -> str:
    ignored = {
        "outcome_revision_id",
        "link_revision_id",
        "revision",
        "supersedes_revision_id",
        "recorded_at",
        "request_fingerprint",
        "authority_tier",
        "source_identity_hash",
    }
    intent = {key: value for key, value in payload.items() if key not in ignored}
    return _hash(
        {
            "operation": operation,
            "scope_storage_id": access.scope.storage_id,
            "tenant_id": access.scope.tenant_id,
            "facility_id": access.facility_id,
            "system_id": access.system_id,
            "actor": access.actor,
            "intent": intent,
        }
    )


def context_fingerprint(
    *, context_schema_version: str, context: Mapping[str, Any], system_configuration_fingerprint: str
) -> str:
    return _hash(
        {
            "context_schema_version": _required_text(context_schema_version, "context_schema_version"),
            "context": dict(context),
            "system_configuration_fingerprint": _required_text(
                system_configuration_fingerprint, "system_configuration_fingerprint"
            ),
        }
    )


def _row_dict(row: Any, json_fields: frozenset[str]) -> dict[str, Any]:
    result = dict(row)
    for field in json_fields:
        if result.get(field) is not None and isinstance(result[field], str):
            result[field] = json.loads(result[field])
    return result


def _audit(
    access: InternalHealthRelevanceAccess,
    *, action: str,
    resource_type: str,
    resource_id: str | None,
    request_id: str | None,
    detail: Mapping[str, Any],
) -> None:
    record_audit_event(
        actor=access.actor,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id,
        detail={
            "scope_storage_id": access.scope.storage_id,
            "tenant_id": access.scope.tenant_id,
            "facility_id": access.facility_id,
            "system_id": access.system_id,
            **dict(detail),
        },
    )


def _authority_tier(
    *,
    provenance: set[str],
    source_category: str,
    outcome_type: str,
    source_system: str | None,
    source_record_id: str | None,
    source_record_version: str | None,
    source_recorded_at: str | None,
    reported_by: str,
    validated_by: str | None,
    validation_basis: Mapping[str, Any],
    source_policy: OutcomeSourceAuthorityPolicy,
) -> tuple[str, ApprovedOutcomeSourceRule | None]:
    same_actor = bool(validated_by and reported_by.strip().lower() == validated_by.strip().lower())
    influenced = "operator_confirmed_after_neraium_review" in provenance
    independent_record_predates_review = False
    reviewed_at = validation_basis.get("neraium_reviewed_at")
    if influenced and source_recorded_at and reviewed_at:
        independent_record_predates_review = _parse_time(
            source_recorded_at, "source_recorded_at"
        ) < _parse_time(reviewed_at, "validation_basis.neraium_reviewed_at")
    if influenced and not independent_record_predates_review:
        return "D", None
    if "retrospective_label" in provenance or same_actor:
        return "C", None
    stable_external_identity = bool(source_system and source_record_id and source_record_version)
    approved_rule = source_policy.matching_rule(
        source_system=source_system,
        source_category=source_category,
        outcome_type=outcome_type,
    )
    required_source_provenance = {
        "maintenance": "maintenance_system_sourced",
        "inspection": "inspection_sourced",
    }.get(source_category)
    source_provenance_complete = (
        required_source_provenance is None or required_source_provenance in provenance
    )
    if (
        "independently_documented_outcome" in provenance
        and approved_rule is not None
        and stable_external_identity
        and source_provenance_complete
    ):
        return "A", approved_rule
    if "independently_documented_outcome" in provenance or (
        "other_explicitly_validated_human_outcome" in provenance
        and bool(validation_basis.get("independent_of_neraium"))
        and not same_actor
    ):
        return "B", None
    return "C", None


def _validate_stable_protocol(protocol: Mapping[str, Any], occurred_start: datetime) -> dict[str, Any]:
    normalized = dict(protocol)
    _required_text(normalized.get("protocol_id"), "observation_protocol.protocol_id")
    _required_text(normalized.get("protocol_version"), "observation_protocol.protocol_version")
    declared = _parse_time(
        normalized.get("window_declared_at"), "observation_protocol.window_declared_at"
    )
    if declared > occurred_start:
        raise HealthRelevanceValidationError("stable_observation_window_not_predeclared")
    expected = normalized.get("expected_sample_count")
    observed = normalized.get("observed_sample_count")
    if not isinstance(expected, int) or isinstance(expected, bool) or expected <= 0:
        raise HealthRelevanceValidationError("stable_observation_expected_samples_invalid")
    if not isinstance(observed, int) or isinstance(observed, bool) or observed < 0 or observed > expected:
        raise HealthRelevanceValidationError("stable_observation_observed_samples_invalid")
    computed_coverage = observed / expected
    provided_coverage = normalized.get("sample_coverage")
    if provided_coverage is not None and abs(float(provided_coverage) - computed_coverage) > 1e-9:
        raise HealthRelevanceValidationError("stable_observation_sample_coverage_mismatch")
    normalized["sample_coverage"] = computed_coverage
    if computed_coverage < MINIMUM_STABLE_SAMPLE_COVERAGE:
        raise HealthRelevanceValidationError("stable_observation_sample_coverage_below_minimum")
    scheduled_windows = normalized.get("scheduled_windows")
    completed_windows = normalized.get("completed_windows")
    if (
        not isinstance(scheduled_windows, int)
        or isinstance(scheduled_windows, bool)
        or scheduled_windows <= 0
    ):
        raise HealthRelevanceValidationError("stable_observation_scheduled_windows_invalid")
    if (
        not isinstance(completed_windows, int)
        or isinstance(completed_windows, bool)
        or completed_windows < 0
        or completed_windows > scheduled_windows
    ):
        raise HealthRelevanceValidationError("stable_observation_completed_windows_invalid")
    protocol_completion = completed_windows / scheduled_windows
    provided_completion = normalized.get("protocol_completion")
    if provided_completion is not None and abs(float(provided_completion) - protocol_completion) > 1e-9:
        raise HealthRelevanceValidationError("stable_observation_protocol_completion_mismatch")
    normalized["protocol_completion"] = protocol_completion
    if protocol_completion < MINIMUM_STABLE_SAMPLE_COVERAGE:
        raise HealthRelevanceValidationError("stable_observation_protocol_completion_below_minimum")
    if normalized.get("completed") is not True:
        raise HealthRelevanceValidationError("stable_observation_protocol_incomplete")
    if normalized.get("context_complete") is not True:
        raise HealthRelevanceValidationError("stable_observation_context_incomplete")
    expected_set = normalized.get("expected_signal_reference_set")
    if not isinstance(expected_set, list) or not expected_set:
        raise HealthRelevanceValidationError("stable_observation_reference_set_required")
    _required_text(normalized.get("sampling_cadence"), "observation_protocol.sampling_cadence")
    _required_text(
        normalized.get("subject_evaluability_rule"),
        "observation_protocol.subject_evaluability_rule",
    )
    basis = str(normalized.get("basis") or "").strip().lower()
    if basis in {"absence_of_findings", "no_finding", "silence"}:
        raise HealthRelevanceValidationError("stable_observation_cannot_be_inferred_from_silence")
    return normalized


def _canonical_incident(
    *,
    access: InternalHealthRelevanceAccess,
    payload: Mapping[str, Any],
    asset_equipment_id: str | None,
    possible_duplicates: list[Any],
) -> tuple[str | None, str, dict[str, Any]]:
    basis = _json_object(payload.get("dedup_basis_json", payload.get("dedup_basis")), "dedup_basis")
    external_incident_id = _optional_text(basis.get("external_incident_id"))
    adjudication_id = _optional_text(basis.get("adjudication_id"))
    duplicate_of = _optional_text(basis.get("confirmed_duplicate_of_outcome_id"))
    explicitly_distinct = bool(basis.get("confirmed_distinct"))
    if duplicate_of:
        return None, "confirmed_duplicate", basis
    exact_identity = external_incident_id or adjudication_id
    if exact_identity:
        incident_key = _hash(
            {
                "scope_storage_id": access.scope.storage_id,
                "tenant_id": access.scope.tenant_id,
                "facility_id": access.facility_id,
                "system_id": access.system_id,
                "asset_equipment_id": asset_equipment_id,
                "identity_kind": "external" if external_incident_id else "adjudicated",
                "identity": exact_identity,
            }
        )
        return incident_key, "confirmed_distinct" if explicitly_distinct else "canonical", basis
    if possible_duplicates:
        return None, "possible_duplicate", basis
    if explicitly_distinct:
        raise HealthRelevanceValidationError("confirmed_distinct_requires_adjudication_identity")
    return None, "unadjudicated", basis


def _merge_previous(previous: Mapping[str, Any] | None, payload: Mapping[str, Any]) -> dict[str, Any]:
    if previous is None:
        return dict(payload)
    merged = dict(previous)
    merged.update(payload)
    return merged


def append_outcome_revision(
    access: InternalHealthRelevanceAccess,
    payload: Mapping[str, Any],
    *,
    idempotency_key: str,
    request_fingerprint: str | None = None,
    request_id: str | None = None,
    source_authority_policy: OutcomeSourceAuthorityPolicy | None = None,
) -> dict[str, Any]:
    _require_access(access)
    key = _required_text(idempotency_key, "idempotency_key")
    provided = dict(payload)
    policy = source_authority_policy or DEFAULT_OUTCOME_SOURCE_AUTHORITY_POLICY
    if not isinstance(policy, OutcomeSourceAuthorityPolicy):
        raise HealthRelevanceValidationError("source_authority_policy_invalid")
    fingerprint = compute_request_fingerprint(
        "append_outcome_revision",
        access,
        {**provided, "_source_authority_policy": policy.as_dict()},
    )
    if request_fingerprint is not None and request_fingerprint != fingerprint:
        raise HealthRelevanceValidationError("request_fingerprint_mismatch")
    init_runtime_db()
    inserted: dict[str, Any] | None = None
    replay: dict[str, Any] | None = None
    try:
        with db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay_row = connection.execute(
                """
                SELECT * FROM validated_outcomes
                WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
                  AND system_id = ? AND idempotency_key = ?
                """,
                (
                    access.scope.storage_id,
                    access.scope.tenant_id,
                    access.facility_id,
                    access.system_id,
                    key,
                ),
            ).fetchone()
            if replay_row is not None:
                if replay_row["request_fingerprint"] != fingerprint:
                    raise HealthRelevanceConflictError("idempotency_key_reused")
                replay = _row_dict(replay_row, _OUTCOME_JSON_FIELDS)
            else:
                outcome_id = _optional_text(provided.get("outcome_id")) or uuid.uuid4().hex
                previous_row = connection.execute(
                    """
                    SELECT * FROM validated_outcomes
                    WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
                      AND system_id = ? AND outcome_id = ?
                    ORDER BY revision DESC LIMIT 1
                    """,
                    (
                        access.scope.storage_id,
                        access.scope.tenant_id,
                        access.facility_id,
                        access.system_id,
                        outcome_id,
                    ),
                ).fetchone()
                previous = _row_dict(previous_row, _OUTCOME_JSON_FIELDS) if previous_row else None
                values = _normalize_outcome(
                    access,
                    _merge_previous(previous, provided),
                    previous,
                    source_authority_policy=policy,
                )
                values.update(
                    {
                        "outcome_revision_id": uuid.uuid4().hex,
                        "outcome_id": outcome_id,
                        "revision": int(previous["revision"]) + 1 if previous else 1,
                        "supersedes_revision_id": previous["outcome_revision_id"] if previous else None,
                        "scope_storage_id": access.scope.storage_id,
                        "tenant_id": access.scope.tenant_id,
                        "facility_id": access.facility_id,
                        "system_id": access.system_id,
                        "actor": access.actor,
                        "recorded_at": _iso(provided.get("recorded_at") or now_iso(), "recorded_at"),
                        "idempotency_key": key,
                        "request_fingerprint": fingerprint,
                    }
                )
                _enforce_incident_reuse(connection, access, outcome_id, values)
                _validate_duplicate_references(connection, access, outcome_id, values)
                source_hash = values.get("source_identity_hash")
                if source_hash:
                    same_source = connection.execute(
                        """
                        SELECT * FROM validated_outcomes
                        WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
                          AND system_id = ? AND source_identity_hash = ? AND revision = 1
                        """,
                        (
                            access.scope.storage_id,
                            access.scope.tenant_id,
                            access.facility_id,
                            access.system_id,
                            source_hash,
                        ),
                    ).fetchone()
                    if same_source is not None:
                        if (
                            same_source["request_fingerprint"] == fingerprint
                            and same_source["idempotency_key"] == key
                        ):
                            replay = _row_dict(same_source, _OUTCOME_JSON_FIELDS)
                        elif same_source["outcome_id"] != outcome_id or previous is None:
                            raise HealthRelevanceConflictError("source_identity_reused")
                if replay is None:
                    columns = tuple(values)
                    connection.execute(
                        f"INSERT INTO validated_outcomes ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                        tuple(values[column] for column in columns),
                    )
                    inserted = _row_dict(values, _OUTCOME_JSON_FIELDS)
    except HealthRelevanceConflictError as exc:
        _audit(
            access,
            action="health_relevance.outcome_conflict",
            resource_type="validated_outcome",
            resource_id=_optional_text(provided.get("outcome_id")),
            request_id=request_id,
            detail={"reason": str(exc), "idempotency_key": key},
        )
        raise
    if replay is not None:
        return replay
    assert inserted is not None
    _audit(
        access,
        action="health_relevance.outcome_revision_appended",
        resource_type="validated_outcome",
        resource_id=str(inserted["outcome_id"]),
        request_id=request_id,
        detail={
            "outcome_revision_id": inserted["outcome_revision_id"],
            "revision": inserted["revision"],
            "validation_status": inserted["validation_status"],
            "authority_tier": inserted["authority_tier"],
            "dedup_status": inserted["dedup_status"],
        },
    )
    return inserted


def _normalize_outcome(
    access: InternalHealthRelevanceAccess,
    payload: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    *,
    source_authority_policy: OutcomeSourceAuthorityPolicy,
) -> dict[str, Any]:
    outcome_type = _required_text(payload.get("outcome_type"), "outcome_type")
    if outcome_type not in OUTCOME_FAMILIES:
        raise HealthRelevanceValidationError("outcome_type_invalid")
    supplied_family = _optional_text(payload.get("outcome_family"))
    family = OUTCOME_FAMILIES[outcome_type]
    if supplied_family is not None and supplied_family != family:
        raise HealthRelevanceValidationError("outcome_family_mismatch")
    disposition = _required_text(payload.get("health_disposition"), "health_disposition")
    if disposition not in HEALTH_DISPOSITIONS:
        raise HealthRelevanceValidationError("health_disposition_invalid")
    status = _required_text(payload.get("validation_status"), "validation_status")
    if status not in VALIDATION_STATUSES:
        raise HealthRelevanceValidationError("validation_status_invalid")
    if previous is not None:
        allowed = {
            "pending": {"pending", "validated", "rejected"},
            "validated": {"validated", "retracted", "superseded"},
            "rejected": set(),
            "retracted": set(),
            "superseded": set(),
        }[str(previous["validation_status"])]
        if status not in allowed:
            raise HealthRelevanceConflictError("invalid_outcome_status_transition")
    occurred_start = _parse_time(payload.get("occurred_start_at"), "occurred_start_at")
    occurred_end = _parse_time(payload.get("occurred_end_at"), "occurred_end_at")
    if occurred_end < occurred_start:
        raise HealthRelevanceValidationError("outcome_window_invalid")
    reported_by = _required_text(payload.get("reported_by"), "reported_by")
    validated_by = _optional_text(payload.get("validated_by"))
    validated_at = _optional_text(payload.get("validated_at"))
    if status == "pending":
        validated_by = None
        validated_at = None
    else:
        validated_by = validated_by or access.actor
        validated_at = _iso(validated_at or now_iso(), "validated_at")
    validation_basis = _json_object(
        payload.get("validation_basis_json", payload.get("validation_basis")), "validation_basis"
    )
    provenance_list = _json_array(
        payload.get("provenance_categories_json", payload.get("provenance_categories")),
        "provenance_categories",
    )
    provenance = {_required_text(item, "provenance_category") for item in provenance_list}
    if not provenance or not provenance <= PROVENANCE_CATEGORIES:
        raise HealthRelevanceValidationError("provenance_categories_invalid")
    source_system = _optional_text(payload.get("source_system"))
    source_record_id = _optional_text(payload.get("source_record_id"))
    source_record_version = _optional_text(payload.get("source_record_version"))
    source_recorded_at = _optional_text(payload.get("source_recorded_at"))
    if source_recorded_at:
        source_recorded_at = _iso(source_recorded_at, "source_recorded_at")
    source_category = _required_text(payload.get("source_category"), "source_category")
    tier, approved_source_rule = _authority_tier(
        provenance=provenance,
        source_category=source_category,
        outcome_type=outcome_type,
        source_system=source_system,
        source_record_id=source_record_id,
        source_record_version=source_record_version,
        source_recorded_at=source_recorded_at,
        reported_by=reported_by,
        validated_by=validated_by,
        validation_basis=validation_basis,
        source_policy=source_authority_policy,
    )
    source_identity_hash = None
    if source_system and source_record_id and source_record_version:
        source_identity_hash = _hash(
            {
                "scope_storage_id": access.scope.storage_id,
                "facility_id": access.facility_id,
                "system_id": access.system_id,
                "source_system": source_system,
                "source_record_id": source_record_id,
                "source_record_version": source_record_version,
            }
        )
    possible_duplicates = _json_array(
        payload.get("possible_duplicate_of_json", payload.get("possible_duplicate_of")),
        "possible_duplicate_of",
    )
    asset_equipment_id = _optional_text(payload.get("asset_equipment_id"))
    canonical_incident_key, dedup_status, dedup_basis = _canonical_incident(
        access=access,
        payload=payload,
        asset_equipment_id=asset_equipment_id,
        possible_duplicates=possible_duplicates,
    )
    metadata = _json_object(
        payload.get("structured_metadata_json", payload.get("structured_metadata")),
        "structured_metadata",
    )
    if bool(metadata.get("inferred_from_absence_of_findings")):
        raise HealthRelevanceValidationError("outcome_cannot_be_inferred_from_silence")
    protocol_raw = payload.get("observation_protocol_json", payload.get("observation_protocol"))
    protocol: dict[str, Any] | None = None
    if protocol_raw is not None:
        protocol = _validate_stable_protocol(
            _json_object(protocol_raw, "observation_protocol"), occurred_start
        )
    if outcome_type == "stable_operation_observation":
        if protocol is None:
            raise HealthRelevanceValidationError("stable_observation_protocol_required")
        if disposition != "stable_observation":
            raise HealthRelevanceValidationError("stable_observation_disposition_invalid")
    return {
        "asset_equipment_id": asset_equipment_id,
        "outcome_schema_version": _optional_text(payload.get("outcome_schema_version"))
        or OUTCOME_SCHEMA_VERSION,
        "outcome_type": outcome_type,
        "outcome_family": family,
        "health_disposition": disposition,
        "validation_status": status,
        "occurred_start_at": occurred_start.isoformat(),
        "occurred_end_at": occurred_end.isoformat(),
        "windows_json": _canonical_json(
            _json_object(payload.get("windows_json", payload.get("windows")), "windows")
        ),
        "source_category": source_category,
        "source_system": source_system,
        "source_record_id": source_record_id,
        "source_record_version": source_record_version,
        "source_recorded_at": source_recorded_at,
        "source_identity_hash": source_identity_hash,
        "reported_by": reported_by,
        "reported_at": _iso(payload.get("reported_at"), "reported_at"),
        "validated_by": validated_by,
        "validated_at": validated_at,
        "validation_basis_json": _canonical_json(validation_basis),
        "provenance_categories_json": _canonical_json(sorted(provenance)),
        "authority_tier": tier,
        "reliability_class": {
            "A": "authoritative_independent",
            "B": "independent_validated",
            "C": "limited_retrospective",
            "D": "neraium_influenced",
        }[tier],
        "reliability_basis_json": _canonical_json(
            {
                **_json_object(
                    payload.get("reliability_basis_json", payload.get("reliability_basis")),
                    "reliability_basis",
                ),
                "authority_rules_version": AUTHORITY_RULES_VERSION,
                "source_authority_policy_version": source_authority_policy.version,
                "source_authority_policy_hash": _hash(source_authority_policy.as_dict()),
                "approved_source_rule_id": (
                    approved_source_rule.rule_id if approved_source_rule is not None else None
                ),
                "named_source_system_approved": approved_source_rule is not None,
            }
        ),
        "canonical_incident_key": canonical_incident_key,
        "dedup_status": dedup_status,
        "possible_duplicate_of_json": _canonical_json(possible_duplicates),
        "dedup_basis_json": _canonical_json(
            {**dedup_basis, "dedup_rules_version": DEDUP_RULES_VERSION}
        ),
        "observation_protocol_json": _canonical_json(protocol) if protocol is not None else None,
        "structured_metadata_json": _canonical_json(metadata),
        "metadata_schema_version": _optional_text(payload.get("metadata_schema_version"))
        or METADATA_SCHEMA_VERSION,
    }


def _incident_families_compatible(left: str, right: str) -> bool:
    return left == right or (
        left in _OPERATIONAL_INCIDENT_FAMILIES and right in _OPERATIONAL_INCIDENT_FAMILIES
    )


def _enforce_incident_reuse(
    connection: Any,
    access: InternalHealthRelevanceAccess,
    outcome_id: str,
    values: dict[str, Any],
) -> None:
    incident_key = _optional_text(values.get("canonical_incident_key"))
    if incident_key is None or values.get("dedup_status") not in {"canonical", "confirmed_distinct"}:
        return
    existing_rows = connection.execute(
        """
        SELECT current.* FROM validated_outcomes AS current
        WHERE current.scope_storage_id = ? AND current.tenant_id = ?
          AND current.facility_id = ? AND current.system_id = ?
          AND current.canonical_incident_key = ? AND current.outcome_id <> ?
          AND current.revision = (
              SELECT MAX(latest.revision) FROM validated_outcomes AS latest
              WHERE latest.scope_storage_id = current.scope_storage_id
                AND latest.tenant_id = current.tenant_id
                AND latest.facility_id = current.facility_id
                AND latest.system_id = current.system_id
                AND latest.outcome_id = current.outcome_id
          )
        ORDER BY current.outcome_id
        """,
        (
            access.scope.storage_id,
            access.scope.tenant_id,
            access.facility_id,
            access.system_id,
            incident_key,
            outcome_id,
        ),
    ).fetchall()
    if not existing_rows:
        return

    dedup_basis = _json_object(values.get("dedup_basis_json"), "dedup_basis")
    explicit_links = {
        _required_text(item, "explicitly_linked_outcome_id")
        for item in _json_array(
            dedup_basis.get("explicitly_linked_outcome_ids"),
            "explicitly_linked_outcome_ids",
        )
    }
    explicit_basis = dedup_basis.get("explicit_occurrence_link_basis")
    if explicit_links and not (
        (isinstance(explicit_basis, str) and explicit_basis.strip())
        or (isinstance(explicit_basis, Mapping) and bool(explicit_basis))
    ):
        raise HealthRelevanceValidationError("explicit_occurrence_link_basis_required")

    new_start = _parse_time(values.get("occurred_start_at"), "occurred_start_at")
    new_end = _parse_time(values.get("occurred_end_at"), "occurred_end_at")
    new_family = str(values["outcome_family"])
    quarantined_ids: list[str] = []
    reasons: set[str] = set()
    checked_ids: list[str] = []
    for existing in existing_rows:
        existing_id = str(existing["outcome_id"])
        checked_ids.append(existing_id)
        existing_family = str(existing["outcome_family"])
        if not _incident_families_compatible(new_family, existing_family):
            quarantined_ids.append(existing_id)
            reasons.add("incident_identity_reuse_incompatible_family")
            continue
        old_start = _parse_time(existing["occurred_start_at"], "occurred_start_at")
        old_end = _parse_time(existing["occurred_end_at"], "occurred_end_at")
        overlaps = new_start <= old_end and old_start <= new_end
        if not overlaps and existing_id not in explicit_links:
            quarantined_ids.append(existing_id)
            reasons.add("incident_identity_reuse_nonoverlapping_window")

    dedup_basis["incident_reuse_evaluation"] = {
        "checked_outcome_ids": checked_ids,
        "family_rule": "same_or_approved_operational_lifecycle_family",
        "window_rule": "overlap_or_explicit_occurrence_link",
        "result": "possible_duplicate" if quarantined_ids else "compatible",
        "reason_codes": sorted(reasons),
    }
    values["dedup_basis_json"] = _canonical_json(dedup_basis)
    if quarantined_ids:
        prior_candidates = _json_array(
            values.get("possible_duplicate_of_json"), "possible_duplicate_of"
        )
        values["possible_duplicate_of_json"] = _canonical_json(
            sorted({str(item) for item in prior_candidates} | set(quarantined_ids))
        )
        values["canonical_incident_key"] = None
        values["dedup_status"] = "possible_duplicate"


def _validate_duplicate_references(
    connection: Any,
    access: InternalHealthRelevanceAccess,
    outcome_id: str,
    values: Mapping[str, Any],
) -> None:
    candidates = _json_array(values.get("possible_duplicate_of_json"), "possible_duplicate_of")
    dedup_basis = _json_object(values.get("dedup_basis_json"), "dedup_basis")
    confirmed_duplicate = _optional_text(dedup_basis.get("confirmed_duplicate_of_outcome_id"))
    explicit_links = _json_array(
        dedup_basis.get("explicitly_linked_outcome_ids"), "explicitly_linked_outcome_ids"
    )
    candidate_ids = [
        *candidates,
        *explicit_links,
        *([confirmed_duplicate] if confirmed_duplicate else []),
    ]
    for candidate in candidate_ids:
        candidate_id = _required_text(candidate, "duplicate_candidate_outcome_id")
        if candidate_id == outcome_id:
            raise HealthRelevanceValidationError("outcome_cannot_duplicate_itself")
        row = connection.execute(
            """
            SELECT 1 FROM validated_outcomes
            WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
              AND system_id = ? AND outcome_id = ?
            LIMIT 1
            """,
            (
                access.scope.storage_id,
                access.scope.tenant_id,
                access.facility_id,
                access.system_id,
                candidate_id,
            ),
        ).fetchone()
        if row is None:
            raise HealthRelevanceAccessError("Health relevance record not found.")


def get_outcome_revision(
    access: InternalHealthRelevanceAccess, *, outcome_id: str, outcome_revision_id: str
) -> dict[str, Any]:
    _require_access(access)
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM validated_outcomes
            WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
              AND system_id = ? AND outcome_id = ? AND outcome_revision_id = ?
            """,
            (
                access.scope.storage_id,
                access.scope.tenant_id,
                access.facility_id,
                access.system_id,
                _required_text(outcome_id, "outcome_id"),
                _required_text(outcome_revision_id, "outcome_revision_id"),
            ),
        ).fetchone()
    if row is None:
        raise HealthRelevanceAccessError("Health relevance record not found.")
    return _row_dict(row, _OUTCOME_JSON_FIELDS)


def get_latest_outcome_revision(
    access: InternalHealthRelevanceAccess, *, outcome_id: str
) -> dict[str, Any]:
    _require_access(access)
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM validated_outcomes
            WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
              AND system_id = ? AND outcome_id = ?
            ORDER BY revision DESC LIMIT 1
            """,
            (
                access.scope.storage_id,
                access.scope.tenant_id,
                access.facility_id,
                access.system_id,
                _required_text(outcome_id, "outcome_id"),
            ),
        ).fetchone()
    if row is None:
        raise HealthRelevanceAccessError("Health relevance record not found.")
    return _row_dict(row, _OUTCOME_JSON_FIELDS)


def list_latest_outcomes(
    access: InternalHealthRelevanceAccess, *, validation_status: str | None = None
) -> list[dict[str, Any]]:
    _require_access(access)
    if validation_status is not None and validation_status not in VALIDATION_STATUSES:
        raise HealthRelevanceValidationError("validation_status_invalid")
    params: list[Any] = [
        access.scope.storage_id,
        access.scope.tenant_id,
        access.facility_id,
        access.system_id,
    ]
    status_sql = ""
    if validation_status is not None:
        status_sql = " AND candidate.validation_status = ?"
        params.append(validation_status)
    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT candidate.* FROM validated_outcomes AS candidate
            WHERE candidate.scope_storage_id = ? AND candidate.tenant_id = ?
              AND candidate.facility_id = ? AND candidate.system_id = ?
              AND candidate.revision = (
                  SELECT MAX(latest.revision) FROM validated_outcomes AS latest
                  WHERE latest.scope_storage_id = candidate.scope_storage_id
                    AND latest.tenant_id = candidate.tenant_id
                    AND latest.facility_id = candidate.facility_id
                    AND latest.system_id = candidate.system_id
                    AND latest.outcome_id = candidate.outcome_id
              )
              {status_sql}
            ORDER BY candidate.occurred_start_at, candidate.outcome_id
            """,
            tuple(params),
        ).fetchall()
    return [_row_dict(row, _OUTCOME_JSON_FIELDS) for row in rows]


def append_outcome_link_revision(
    access: InternalHealthRelevanceAccess,
    payload: Mapping[str, Any],
    *,
    idempotency_key: str,
    request_fingerprint: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    _require_access(access)
    key = _required_text(idempotency_key, "idempotency_key")
    provided = dict(payload)
    fingerprint = compute_request_fingerprint("append_outcome_link_revision", access, provided)
    if request_fingerprint is not None and request_fingerprint != fingerprint:
        raise HealthRelevanceValidationError("request_fingerprint_mismatch")
    init_runtime_db()
    inserted: dict[str, Any] | None = None
    replay: dict[str, Any] | None = None
    try:
        with db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            replay_row = connection.execute(
                """
                SELECT * FROM validated_outcome_links
                WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
                  AND system_id = ? AND idempotency_key = ?
                """,
                (
                    access.scope.storage_id,
                    access.scope.tenant_id,
                    access.facility_id,
                    access.system_id,
                    key,
                ),
            ).fetchone()
            if replay_row is not None:
                if replay_row["request_fingerprint"] != fingerprint:
                    raise HealthRelevanceConflictError("idempotency_key_reused")
                replay = _row_dict(replay_row, _LINK_JSON_FIELDS)
            else:
                link_id = _optional_text(provided.get("link_id")) or uuid.uuid4().hex
                previous_row = connection.execute(
                    """
                    SELECT * FROM validated_outcome_links
                    WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
                      AND system_id = ? AND link_id = ?
                    ORDER BY revision DESC LIMIT 1
                    """,
                    (
                        access.scope.storage_id,
                        access.scope.tenant_id,
                        access.facility_id,
                        access.system_id,
                        link_id,
                    ),
                ).fetchone()
                previous = _row_dict(previous_row, _LINK_JSON_FIELDS) if previous_row else None
                values = _normalize_link(
                    access,
                    _merge_previous(previous, provided),
                    previous,
                    connection,
                )
                values.update(
                    {
                        "link_revision_id": uuid.uuid4().hex,
                        "link_id": link_id,
                        "revision": int(previous["revision"]) + 1 if previous else 1,
                        "supersedes_revision_id": previous["link_revision_id"] if previous else None,
                        "scope_storage_id": access.scope.storage_id,
                        "tenant_id": access.scope.tenant_id,
                        "facility_id": access.facility_id,
                        "system_id": access.system_id,
                        "actor": access.actor,
                        "recorded_at": _iso(provided.get("recorded_at") or now_iso(), "recorded_at"),
                        "idempotency_key": key,
                        "request_fingerprint": fingerprint,
                    }
                )
                columns = tuple(values)
                connection.execute(
                    f"INSERT INTO validated_outcome_links ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                    tuple(values[column] for column in columns),
                )
                inserted = _row_dict(values, _LINK_JSON_FIELDS)
    except HealthRelevanceConflictError as exc:
        _audit(
            access,
            action="health_relevance.outcome_link_conflict",
            resource_type="validated_outcome_link",
            resource_id=_optional_text(provided.get("link_id")),
            request_id=request_id,
            detail={"reason": str(exc), "idempotency_key": key},
        )
        raise
    if replay is not None:
        return replay
    assert inserted is not None
    _audit(
        access,
        action="health_relevance.outcome_link_revision_appended",
        resource_type="validated_outcome_link",
        resource_id=str(inserted["link_id"]),
        request_id=request_id,
        detail={
            "link_revision_id": inserted["link_revision_id"],
            "revision": inserted["revision"],
            "outcome_revision_id": inserted["outcome_revision_id"],
            "link_status": inserted["link_status"],
        },
    )
    return inserted


def _normalize_link(
    access: InternalHealthRelevanceAccess,
    payload: Mapping[str, Any],
    previous: Mapping[str, Any] | None,
    connection: Any,
) -> dict[str, Any]:
    outcome_id = _required_text(payload.get("outcome_id"), "outcome_id")
    outcome_revision_id = _required_text(payload.get("outcome_revision_id"), "outcome_revision_id")
    outcome_row = connection.execute(
        """
        SELECT * FROM validated_outcomes
        WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
          AND system_id = ? AND outcome_id = ? AND outcome_revision_id = ?
        """,
        (
            access.scope.storage_id,
            access.scope.tenant_id,
            access.facility_id,
            access.system_id,
            outcome_id,
            outcome_revision_id,
        ),
    ).fetchone()
    if outcome_row is None:
        raise HealthRelevanceAccessError("Health relevance record not found.")
    status = _required_text(payload.get("link_status"), "link_status")
    if status not in LINK_STATUSES:
        raise HealthRelevanceValidationError("link_status_invalid")
    if status == "active" and outcome_row["validation_status"] != "validated":
        raise HealthRelevanceValidationError("active_link_requires_validated_outcome")
    if previous is not None:
        allowed = {
            "pending": {"pending", "active", "rejected"},
            "active": {"active", "retracted", "superseded"},
            "rejected": set(),
            "retracted": set(),
            "superseded": set(),
        }[str(previous["link_status"])]
        if status not in allowed:
            raise HealthRelevanceConflictError("invalid_link_status_transition")
    asset_equipment_id = _optional_text(payload.get("asset_equipment_id"))
    if asset_equipment_id != _optional_text(outcome_row["asset_equipment_id"]):
        raise HealthRelevanceAccessError("Health relevance record not found.")
    finding_id = _optional_text(payload.get("finding_id"))
    evidence_run_id = _optional_text(payload.get("evidence_run_id"))
    if finding_id:
        finding = connection.execute(
            "SELECT source_snapshot_json FROM finding_cases WHERE finding_id = ? AND scope_storage_id = ?",
            (finding_id, access.scope.storage_id),
        ).fetchone()
        if finding is None or not _snapshot_matches_system(
            finding["source_snapshot_json"], access.facility_id, access.system_id
        ):
            raise HealthRelevanceAccessError("Health relevance record not found.")
    if evidence_run_id:
        evidence = connection.execute(
            "SELECT payload_json FROM evidence_runs WHERE run_id = ? AND scope_storage_id = ?",
            (evidence_run_id, access.scope.storage_id),
        ).fetchone()
        if evidence is None or not _snapshot_matches_system(
            evidence["payload_json"], access.facility_id, access.system_id
        ):
            raise HealthRelevanceAccessError("Health relevance record not found.")
    behavioral_snapshot_id = _optional_text(payload.get("behavioral_snapshot_id"))
    baseline_reference_id = _optional_text(payload.get("baseline_reference_id"))
    evidence_content_hash = _optional_text(payload.get("evidence_content_hash"))
    if not any((finding_id, evidence_run_id, evidence_content_hash, behavioral_snapshot_id, baseline_reference_id)):
        raise HealthRelevanceValidationError("immutable_evidence_or_reference_anchor_required")
    behavioral_model_id = _optional_text(payload.get("behavioral_model_id"))
    behavioral_model_version = _optional_text(payload.get("behavioral_model_version"))
    baseline_reference_version = _optional_text(payload.get("baseline_reference_version"))
    if behavioral_snapshot_id and not (behavioral_model_id and behavioral_model_version):
        raise HealthRelevanceValidationError("behavioral_model_binding_incomplete")
    if behavioral_model_id and not behavioral_model_version:
        raise HealthRelevanceValidationError("behavioral_model_binding_incomplete")
    if baseline_reference_id and not baseline_reference_version:
        raise HealthRelevanceValidationError("baseline_reference_binding_incomplete")
    if not behavioral_snapshot_id and not baseline_reference_id:
        raise HealthRelevanceValidationError("reference_binding_incomplete")
    compatibility_epoch = _required_text(payload.get("compatibility_epoch"), "compatibility_epoch")
    telemetry_schema = _required_text(
        payload.get("telemetry_schema_fingerprint"), "telemetry_schema_fingerprint"
    )
    system_config = _required_text(
        payload.get("system_configuration_fingerprint"), "system_configuration_fingerprint"
    )
    context_schema = _required_text(payload.get("context_schema_version"), "context_schema_version")
    context = _json_object(payload.get("context_json", payload.get("context")), "context")
    expected_context_hash = context_fingerprint(
        context_schema_version=context_schema,
        context=context,
        system_configuration_fingerprint=system_config,
    )
    supplied_context_hash = _optional_text(payload.get("context_fingerprint"))
    if supplied_context_hash and supplied_context_hash != expected_context_hash:
        raise HealthRelevanceValidationError("context_fingerprint_mismatch")
    temporal_role = _required_text(payload.get("temporal_role"), "temporal_role")
    if temporal_role not in TEMPORAL_ROLES:
        raise HealthRelevanceValidationError("temporal_role_invalid")
    outcome_type = str(outcome_row["outcome_type"])
    if temporal_role == "stable_comparison" and outcome_type not in {
        "stable_operation_observation",
        "expected_no_fault_confirmation",
    }:
        raise HealthRelevanceValidationError("stable_comparison_requires_explicit_stable_outcome")
    if temporal_role == "stable_comparison":
        protocol = outcome_row["observation_protocol_json"]
        if protocol is None:
            raise HealthRelevanceValidationError("stable_comparison_requires_observation_protocol")
        try:
            protocol_value = json.loads(protocol)
        except (TypeError, json.JSONDecodeError) as exc:
            raise HealthRelevanceValidationError(
                "stable_comparison_requires_observation_protocol"
            ) from exc
        if (
            protocol_value.get("completed") is not True
            or float(protocol_value.get("sample_coverage", 0.0)) < MINIMUM_STABLE_SAMPLE_COVERAGE
        ):
            raise HealthRelevanceValidationError("stable_comparison_protocol_ineligible")
    if outcome_type == "stable_operation_observation" and temporal_role != "stable_comparison":
        raise HealthRelevanceValidationError("stable_outcome_requires_stable_comparison_role")
    window_start = _parse_time(payload.get("window_start_at"), "window_start_at")
    window_end = _parse_time(payload.get("window_end_at"), "window_end_at")
    if window_end < window_start:
        raise HealthRelevanceValidationError("link_window_invalid")
    origin = _required_text(payload.get("link_origin"), "link_origin")
    confidence = _required_text(payload.get("link_confidence"), "link_confidence")
    subject_type = _required_text(payload.get("subject_type"), "subject_type")
    subject_state = _required_text(payload.get("subject_state"), "subject_state")
    if origin not in LINK_ORIGINS or confidence not in LINK_CONFIDENCES:
        raise HealthRelevanceValidationError("link_provenance_invalid")
    if subject_type not in SUBJECT_TYPES or subject_state not in SUBJECT_STATES:
        raise HealthRelevanceValidationError("link_subject_invalid")
    return {
        "outcome_id": outcome_id,
        "outcome_revision_id": outcome_revision_id,
        "asset_equipment_id": asset_equipment_id,
        "finding_id": finding_id,
        "evidence_run_id": evidence_run_id,
        "evidence_package_id": _optional_text(payload.get("evidence_package_id")),
        "evidence_package_revision": payload.get("evidence_package_revision"),
        "evidence_content_hash": evidence_content_hash,
        "subject_type": subject_type,
        "subject_id": _required_text(payload.get("subject_id"), "subject_id"),
        "subject_mapping_version": _required_text(
            payload.get("subject_mapping_version"), "subject_mapping_version"
        ),
        "behavioral_model_id": behavioral_model_id,
        "behavioral_model_version": behavioral_model_version,
        "behavioral_snapshot_id": behavioral_snapshot_id,
        "baseline_reference_id": baseline_reference_id,
        "baseline_reference_version": baseline_reference_version,
        "telemetry_schema_fingerprint": telemetry_schema,
        "system_configuration_fingerprint": system_config,
        "compatibility_epoch": compatibility_epoch,
        "context_schema_version": context_schema,
        "context_json": _canonical_json(context),
        "context_fingerprint": expected_context_hash,
        "context_episode_id": _required_text(payload.get("context_episode_id"), "context_episode_id"),
        "context_source_refs_json": _canonical_json(
            _json_array(
                payload.get("context_source_refs_json", payload.get("context_source_refs")),
                "context_source_refs",
            )
        ),
        "temporal_role": temporal_role,
        "window_start_at": window_start.isoformat(),
        "window_end_at": window_end.isoformat(),
        "link_origin": origin,
        "link_confidence": confidence,
        "link_basis_json": _canonical_json(
            _json_object(payload.get("link_basis_json", payload.get("link_basis")), "link_basis")
        ),
        "linked_by": _required_text(payload.get("linked_by") or access.actor, "linked_by"),
        "linked_at": _iso(payload.get("linked_at") or now_iso(), "linked_at"),
        "retrospective_window_selection": int(bool(payload.get("retrospective_window_selection", False))),
        "subject_state": subject_state,
        "observation_basis_json": _canonical_json(
            _json_object(
                payload.get("observation_basis_json", payload.get("observation_basis")),
                "observation_basis",
            )
        ),
        "link_status": status,
    }


def _snapshot_matches_system(snapshot_json: Any, facility_id: str, system_id: str) -> bool:
    try:
        snapshot = json.loads(snapshot_json) if isinstance(snapshot_json, str) else dict(snapshot_json)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    snapshot_system = _optional_text(snapshot.get("system_id"))
    snapshot_facility = _optional_text(snapshot.get("facility_id"))
    if snapshot_system != system_id:
        return False
    return snapshot_facility == facility_id


def get_link_revision(
    access: InternalHealthRelevanceAccess, *, link_id: str, link_revision_id: str
) -> dict[str, Any]:
    _require_access(access)
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM validated_outcome_links
            WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
              AND system_id = ? AND link_id = ? AND link_revision_id = ?
            """,
            (
                access.scope.storage_id,
                access.scope.tenant_id,
                access.facility_id,
                access.system_id,
                _required_text(link_id, "link_id"),
                _required_text(link_revision_id, "link_revision_id"),
            ),
        ).fetchone()
    if row is None:
        raise HealthRelevanceAccessError("Health relevance record not found.")
    return _row_dict(row, _LINK_JSON_FIELDS)


def get_latest_link_revision(
    access: InternalHealthRelevanceAccess, *, link_id: str
) -> dict[str, Any]:
    _require_access(access)
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT * FROM validated_outcome_links
            WHERE scope_storage_id = ? AND tenant_id = ? AND facility_id = ?
              AND system_id = ? AND link_id = ?
            ORDER BY revision DESC LIMIT 1
            """,
            (
                access.scope.storage_id,
                access.scope.tenant_id,
                access.facility_id,
                access.system_id,
                _required_text(link_id, "link_id"),
            ),
        ).fetchone()
    if row is None:
        raise HealthRelevanceAccessError("Health relevance record not found.")
    return _row_dict(row, _LINK_JSON_FIELDS)


def list_latest_links(
    access: InternalHealthRelevanceAccess,
    *,
    subject_type: str,
    subject_id: str,
    context_fingerprint: str,
    compatibility_epoch: str,
    link_status: str | None = None,
) -> list[dict[str, Any]]:
    _require_access(access)
    if subject_type not in SUBJECT_TYPES:
        raise HealthRelevanceValidationError("subject_type_invalid")
    if link_status is not None and link_status not in LINK_STATUSES:
        raise HealthRelevanceValidationError("link_status_invalid")
    params: list[Any] = [
        access.scope.storage_id,
        access.scope.tenant_id,
        access.facility_id,
        access.system_id,
        subject_type,
        _required_text(subject_id, "subject_id"),
        _required_text(context_fingerprint, "context_fingerprint"),
        _required_text(compatibility_epoch, "compatibility_epoch"),
    ]
    status_sql = ""
    if link_status is not None:
        status_sql = " AND candidate.link_status = ?"
        params.append(link_status)
    init_runtime_db()
    with db_connection() as connection:
        rows = connection.execute(
            f"""
            SELECT candidate.* FROM validated_outcome_links AS candidate
            WHERE candidate.scope_storage_id = ? AND candidate.tenant_id = ?
              AND candidate.facility_id = ? AND candidate.system_id = ?
              AND candidate.subject_type = ? AND candidate.subject_id = ?
              AND candidate.context_fingerprint = ? AND candidate.compatibility_epoch = ?
              AND candidate.revision = (
                  SELECT MAX(latest.revision) FROM validated_outcome_links AS latest
                  WHERE latest.scope_storage_id = candidate.scope_storage_id
                    AND latest.tenant_id = candidate.tenant_id
                    AND latest.facility_id = candidate.facility_id
                    AND latest.system_id = candidate.system_id
                    AND latest.link_id = candidate.link_id
              )
              {status_sql}
            ORDER BY candidate.window_start_at, candidate.link_id
            """,
            tuple(params),
        ).fetchall()
    return [_row_dict(row, _LINK_JSON_FIELDS) for row in rows]
