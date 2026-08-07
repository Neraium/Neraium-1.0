from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field

from app.services.dataset_scope import (
    DatasetScope,
    attach_dataset_scope,
    current_dataset_scope,
    payload_matches_dataset_scope,
)
from app.services.upload_state_repository import (
    insert_shared_state_strict,
    list_shared_state_prefix,
    list_shared_state_prefix_pure,
    read_local_json,
    read_shared_state,
    read_shared_state_pure,
    write_local_json,
    write_shared_state_strict,
)
from app.services import runtime_db


logger = logging.getLogger(__name__)

SOURCE_SCHEMA_VERSION = "neraium.evidence-package-correlation-source.v1"
RELATIONSHIP_SCHEMA_VERSION = "neraium.evidence-package-relationship.v1"
RESPONSE_SCHEMA_VERSION = "neraium.evidence-package-related-set.v1"
PROJECTOR_VERSION = "evidence-package-correlation-projector/1.0.0"
RULE_VERSION = "evidence-package-correlation-rules/1.0.0"
MAX_TEMPORAL_ADJACENCY_SECONDS = 86_400
CORRELATION_NAMESPACE = uuid5(
    NAMESPACE_URL,
    "https://neraium.com/schema/evidence-package-correlation/v1",
)

RELATIONSHIP_PRIORITY = (
    "shared_canonical_signal",
    "overlapping_observation_window",
    "temporally_adjacent",
    "related_analytical_pattern",
    "compatible_operating_context",
    "same_system",
)

LIMITATION_PRIORITY = (
    "package_lifecycle_ineligible",
    "legacy_package_without_correlation_projection",
    "missing_required_scope",
    "observation_window_unavailable",
    "operating_context_unavailable",
    "canonical_signal_identity_unavailable",
    "analytical_pattern_identity_unavailable",
    "related_package_projection_missing",
    "stale_or_corrupt_correlation_sidecar",
    "no_relationship_anchor",
)

_PERSISTENCE_LOCK = threading.RLock()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorrelationStatus(str, Enum):
    unavailable = "unavailable"
    insufficient_evidence = "insufficient_evidence"
    no_supported_relationship = "no_supported_relationship"
    related_packages_found = "related_packages_found"


class PackageRelationshipType(str, Enum):
    evidence_supported_association = "evidence_supported_association"


class SupportedRelationship(str, Enum):
    shared_canonical_signal = "shared_canonical_signal"
    overlapping_observation_window = "overlapping_observation_window"
    temporally_adjacent = "temporally_adjacent"
    related_analytical_pattern = "related_analytical_pattern"
    compatible_operating_context = "compatible_operating_context"
    same_system = "same_system"


class TemporalRelationship(str, Enum):
    overlapping_observation_window = "overlapping_observation_window"
    temporally_adjacent = "temporally_adjacent"
    not_supported = "not_supported"
    unavailable = "unavailable"


class OperatingContextRelationship(str, Enum):
    compatible = "compatible"
    different = "different"
    unavailable = "unavailable"


class CorrelationLimitation(str, Enum):
    package_lifecycle_ineligible = "package_lifecycle_ineligible"
    legacy_package_without_correlation_projection = "legacy_package_without_correlation_projection"
    missing_required_scope = "missing_required_scope"
    observation_window_unavailable = "observation_window_unavailable"
    operating_context_unavailable = "operating_context_unavailable"
    canonical_signal_identity_unavailable = "canonical_signal_identity_unavailable"
    analytical_pattern_identity_unavailable = "analytical_pattern_identity_unavailable"
    related_package_projection_missing = "related_package_projection_missing"
    stale_or_corrupt_correlation_sidecar = "stale_or_corrupt_correlation_sidecar"
    no_relationship_anchor = "no_relationship_anchor"


class SignalOrSystemOverlap(StrictModel):
    same_system: bool
    shared_canonical_signal_ids: list[str] = Field(default_factory=list)
    shared_analytical_pattern_ids: list[str] = Field(default_factory=list)


class RelationshipProvenance(StrictModel):
    relationship_rule_version: str
    evaluated_from: str


class RelatedPackageResponse(StrictModel):
    relationship_id: str
    package_id: str
    relationship_type: PackageRelationshipType
    strongest_supported_relationship: SupportedRelationship
    supporting_relationships: list[SupportedRelationship] = Field(default_factory=list)
    temporal_relationship: TemporalRelationship
    operating_context_relationship: OperatingContextRelationship
    signal_or_system_overlap: SignalOrSystemOverlap
    evidence_refs: list[str] = Field(default_factory=list)
    limitations: list[CorrelationLimitation] = Field(default_factory=list)
    provenance: RelationshipProvenance


class RelatedPackageSetProvenance(StrictModel):
    projector_version: str
    relationship_rule_version: str
    repository: str
    read_mode: str


class RelatedPackageSetResponse(StrictModel):
    schema_version: str
    package_id: str
    correlation_status: CorrelationStatus
    related_packages: list[RelatedPackageResponse] = Field(default_factory=list)
    limitations: list[CorrelationLimitation] = Field(default_factory=list)
    provenance: RelatedPackageSetProvenance


class PackageNotFoundError(LookupError):
    """The package does not exist inside the authenticated dataset scope."""


class CorrelationIntegrityError(RuntimeError):
    def __init__(self, limitation: str = "stale_or_corrupt_correlation_sidecar") -> None:
        self.limitation = limitation
        super().__init__(limitation)


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def immutable_package_content(package: dict[str, Any]) -> dict[str, Any]:
    """Exclude the independently mutable operator lifecycle from integrity binding."""
    return {key: value for key, value in package.items() if key != "lifecycle"}


def package_content_hash(package: dict[str, Any]) -> str:
    return sha256(canonical_json(immutable_package_content(package)).encode("utf-8")).hexdigest()


def relationship_id_for(
    *,
    tenant_id: str,
    workspace_id: str,
    system_id: str,
    package_a_id: str,
    package_b_id: str,
) -> str:
    first_id, second_id = sorted((package_a_id, package_b_id))
    identity = canonical_json(
        {
            "schema_version": RELATIONSHIP_SCHEMA_VERSION,
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "system_id": system_id,
            "package_ids": [first_id, second_id],
        }
    )
    return str(uuid5(CORRELATION_NAMESPACE, identity))


def build_source_projection(package: dict[str, Any]) -> dict[str, Any] | None:
    package_id = normalize_scalar(package.get("id"))
    if package_id is None or package.get("schema_version") != "evidence-package-v1":
        return None

    created_at, created_valid = normalize_timestamp(package.get("created_at"))
    completed_at, completed_valid = normalize_timestamp(package.get("latest_evaluated_at"))
    if not created_valid or not completed_valid or created_at is None or completed_at is None:
        return None
    if timestamp_value(completed_at) < timestamp_value(created_at):
        return None

    tenant_id = normalize_scalar(package.get("organization_id"))
    workspace_id = normalize_scalar(package.get("portfolio_id"))
    system_id = normalize_scalar(package.get("system_id"))
    facility_field = "site_id" if package.get("site_id") is not None else "facility_id"
    facility_id = normalize_scalar(package.get(facility_field))
    equipment_id = normalize_scalar(package.get("equipment_id"))

    operating_context = package.get("operating_context")
    operating_context = operating_context if isinstance(operating_context, dict) else {}
    comparison_window = operating_context.get("comparison_window")
    comparison_window = comparison_window if isinstance(comparison_window, dict) else {}
    observation_start, observation_start_valid = normalize_timestamp(comparison_window.get("start"))
    observation_end, observation_end_valid = normalize_timestamp(comparison_window.get("end"))
    observation_valid = bool(
        observation_start_valid
        and observation_end_valid
        and observation_start is not None
        and observation_end is not None
        and timestamp_value(observation_start) <= timestamp_value(observation_end)
    )
    if not observation_valid:
        observation_start = None
        observation_end = None

    comparison_state = operating_context.get("comparison_state")
    comparison_state = comparison_state if isinstance(comparison_state, dict) else {}
    context_value = comparison_state.get("state_label")
    context_field = "operating_context.comparison_state.state_label"
    if normalize_context(context_value) is None:
        state_type = comparison_state.get("state_type")
        context_value = None if str(state_type or "").strip().casefold() == "unknown" else state_type
        context_field = "operating_context.comparison_state.state_type"
    operating_context_id = normalize_context(context_value)

    canonical_signal_ids, signals_valid = normalize_id_list(package.get("canonical_signal_ids"))
    analytical_pattern_ids, patterns_valid = normalize_pattern_ids(package)

    limitations: list[str] = []
    if not all((tenant_id, workspace_id, system_id)):
        limitations.append("missing_required_scope")
    if not observation_valid:
        limitations.append("observation_window_unavailable")
    if operating_context_id is None:
        limitations.append("operating_context_unavailable")
    if not signals_valid or not canonical_signal_ids:
        limitations.append("canonical_signal_identity_unavailable")
    if not patterns_valid or not analytical_pattern_ids:
        limitations.append("analytical_pattern_identity_unavailable")

    evidence_refs = [
        evidence_ref(package_id, "schema_version"),
        evidence_ref(package_id, "created_at"),
        evidence_ref(package_id, "latest_evaluated_at"),
    ]
    for field_name, value in (
        ("organization_id", tenant_id),
        ("portfolio_id", workspace_id),
        ("system_id", system_id),
        (facility_field, facility_id),
        ("equipment_id", equipment_id),
        ("operating_context.comparison_window.start", observation_start),
        ("operating_context.comparison_window.end", observation_end),
    ):
        if value is not None:
            evidence_refs.append(evidence_ref(package_id, field_name))
    if operating_context_id is not None:
        evidence_refs.append(evidence_ref(package_id, context_field))
    if canonical_signal_ids:
        evidence_refs.append(evidence_ref(package_id, "canonical_signal_ids"))
    for pattern_field in ("analytical_pattern_ids", "historical_pattern_ids"):
        pattern_values, pattern_values_valid = normalize_id_list(package.get(pattern_field))
        if pattern_values_valid and pattern_values:
            evidence_refs.append(evidence_ref(package_id, pattern_field))

    return {
        "schema_version": SOURCE_SCHEMA_VERSION,
        "package_id": package_id,
        "package_revision": package.get("revision"),
        "package_content_hash": package_content_hash(package),
        "package_fingerprint_id": normalize_scalar(package.get("fingerprint_id")),
        "lifecycle_state": "completed_analysis",
        "package_created_at": created_at,
        "package_completed_at": completed_at,
        "scope": {
            "tenant_id": tenant_id,
            "workspace_id": workspace_id,
            "system_id": system_id,
            "facility_id": facility_id,
            "equipment_id": equipment_id,
        },
        "observation_window": {
            "start": observation_start,
            "end": observation_end,
            "status": "available" if observation_valid else "unavailable",
        },
        "operating_context_id": operating_context_id,
        "canonical_signal_ids": canonical_signal_ids,
        "analytical_pattern_ids": analytical_pattern_ids,
        "evidence_refs": sorted(set(evidence_refs)),
        "limitations": order_limitations(limitations),
        "provenance": {
            "projector_version": PROJECTOR_VERSION,
            "projected_from": "persisted_evidence_package",
        },
    }


def build_relationship(first_source: dict[str, Any], second_source: dict[str, Any]) -> dict[str, Any] | None:
    package_a, package_b = sorted(
        (first_source, second_source), key=lambda item: item.get("package_id") or ""
    )
    package_a_id = normalize_scalar(package_a.get("package_id"))
    package_b_id = normalize_scalar(package_b.get("package_id"))
    if package_a_id is None or package_b_id is None or package_a_id == package_b_id:
        return None

    scope_a = package_a.get("scope") if isinstance(package_a.get("scope"), dict) else {}
    scope_b = package_b.get("scope") if isinstance(package_b.get("scope"), dict) else {}
    tenant_id = normalize_scalar(scope_a.get("tenant_id"))
    workspace_id = normalize_scalar(scope_a.get("workspace_id"))
    system_id = normalize_scalar(scope_a.get("system_id"))
    if not all((tenant_id, workspace_id, system_id)):
        return None
    if (
        tenant_id != normalize_scalar(scope_b.get("tenant_id"))
        or workspace_id != normalize_scalar(scope_b.get("workspace_id"))
        or system_id != normalize_scalar(scope_b.get("system_id"))
    ):
        return None
    for optional_scope in ("facility_id", "equipment_id"):
        value_a = normalize_scalar(scope_a.get(optional_scope))
        value_b = normalize_scalar(scope_b.get(optional_scope))
        if value_a is not None and value_b is not None and value_a != value_b:
            return None

    temporal_relationship = classify_temporal_relationship(package_a, package_b)
    operating_context_relationship = classify_operating_context(package_a, package_b)
    shared_signals = sorted(
        set(normalized_projection_ids(package_a, "canonical_signal_ids"))
        & set(normalized_projection_ids(package_b, "canonical_signal_ids"))
    )
    shared_patterns = sorted(
        set(normalized_projection_ids(package_a, "analytical_pattern_ids"))
        & set(normalized_projection_ids(package_b, "analytical_pattern_ids"))
    )

    relationships: list[str] = []
    if shared_signals:
        relationships.append("shared_canonical_signal")
    if temporal_relationship == "overlapping_observation_window":
        relationships.append("overlapping_observation_window")
    elif temporal_relationship == "temporally_adjacent":
        relationships.append("temporally_adjacent")
    if shared_patterns:
        relationships.append("related_analytical_pattern")
    anchors = [item for item in relationships if item in RELATIONSHIP_PRIORITY[:4]]
    if not anchors:
        return None
    if operating_context_relationship == "compatible":
        relationships.append("compatible_operating_context")
    relationships.append("same_system")
    relationships = order_relationships(relationships)
    strongest = next(item for item in RELATIONSHIP_PRIORITY if item in anchors)

    evidence_refs = [
        evidence_ref(package_a_id, "system_id"),
        evidence_ref(package_b_id, "system_id"),
    ]
    if temporal_relationship in {"overlapping_observation_window", "temporally_adjacent"}:
        for related_id in (package_a_id, package_b_id):
            evidence_refs.extend(
                [
                    evidence_ref(related_id, "operating_context.comparison_window.start"),
                    evidence_ref(related_id, "operating_context.comparison_window.end"),
                ]
            )
    if shared_signals:
        evidence_refs.extend(
            [
                evidence_ref(package_a_id, "canonical_signal_ids"),
                evidence_ref(package_b_id, "canonical_signal_ids"),
            ]
        )
    if shared_patterns:
        evidence_refs.extend(
            projection_evidence_refs(package_a, ("analytical_pattern_ids", "historical_pattern_ids"))
        )
        evidence_refs.extend(
            projection_evidence_refs(package_b, ("analytical_pattern_ids", "historical_pattern_ids"))
        )
    if operating_context_relationship == "compatible":
        evidence_refs.extend(
            projection_evidence_refs(
                package_a,
                (
                    "operating_context.comparison_state.state_label",
                    "operating_context.comparison_state.state_type",
                ),
            )
        )
        evidence_refs.extend(
            projection_evidence_refs(
                package_b,
                (
                    "operating_context.comparison_state.state_label",
                    "operating_context.comparison_state.state_type",
                ),
            )
        )

    limitations: list[str] = []
    if temporal_relationship == "unavailable":
        limitations.append("observation_window_unavailable")
    if operating_context_relationship == "unavailable":
        limitations.append("operating_context_unavailable")
    if not normalized_projection_ids(package_a, "canonical_signal_ids") or not normalized_projection_ids(
        package_b, "canonical_signal_ids"
    ):
        limitations.append("canonical_signal_identity_unavailable")
    if not normalized_projection_ids(package_a, "analytical_pattern_ids") or not normalized_projection_ids(
        package_b, "analytical_pattern_ids"
    ):
        limitations.append("analytical_pattern_identity_unavailable")

    relationship_id = relationship_id_for(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        system_id=system_id,
        package_a_id=package_a_id,
        package_b_id=package_b_id,
    )
    return {
        "schema_version": RELATIONSHIP_SCHEMA_VERSION,
        "relationship_id": relationship_id,
        "package_a_id": package_a_id,
        "package_b_id": package_b_id,
        "relationship_type": "evidence_supported_association",
        "strongest_supported_relationship": strongest,
        "supporting_relationships": relationships,
        "temporal_relationship": temporal_relationship,
        "operating_context_relationship": operating_context_relationship,
        "signal_or_system_overlap": {
            "same_system": True,
            "shared_canonical_signal_ids": shared_signals,
            "shared_analytical_pattern_ids": shared_patterns,
        },
        "evidence_refs": sorted(set(evidence_refs)),
        "limitations": order_limitations(limitations),
        "source_hashes": {
            package_a_id: package_a["package_content_hash"],
            package_b_id: package_b["package_content_hash"],
        },
        "provenance": {
            "relationship_rule_version": RULE_VERSION,
            "evaluated_from": "immutable_correlation_sources",
        },
    }


def persist_completed_package_projection(package: dict[str, Any], *, scope: DatasetScope | None = None) -> str:
    source = build_source_projection(package)
    if source is None:
        return "ineligible"
    resolved_scope = scope or current_dataset_scope()
    package_id = source["package_id"]
    source_scope = source.get("scope", {})
    if (
        source_scope.get("tenant_id") not in {None, resolved_scope.tenant_id}
        or source_scope.get("workspace_id") not in {None, resolved_scope.workspace_id}
    ):
        return "ineligible"
    source_created = False
    with _PERSISTENCE_LOCK:
        source_name = _source_key(package_id, resolved_scope)
        source_created, persisted = _insert(source_name, _source_record(source), scope=resolved_scope)
        existing_source = _source_from_record(persisted, scope=resolved_scope)
        if existing_source is None or canonical_json(existing_source) != canonical_json(source):
            logger.error("evidence_package_correlation_source_conflict package_id=%s", package_id)
            return "conflict"

        if all((source_scope.get("tenant_id"), source_scope.get("workspace_id"), source_scope.get("system_id"))):
            for record in list_shared_state_prefix(_source_prefix(resolved_scope), scope=resolved_scope):
                other_source = _source_from_record(record, scope=resolved_scope)
                if other_source is None or other_source.get("package_id") == package_id:
                    continue
                relationship = build_relationship(source, other_source)
                if relationship is not None:
                    _persist_relationship(
                        relationship,
                        system_id=source_scope["system_id"],
                        scope=resolved_scope,
                    )
    return "created" if source_created else "idempotent"


def get_related_package_set(package_id: str) -> dict[str, Any]:
    package_id = normalize_scalar(package_id)
    if package_id is None:
        raise PackageNotFoundError
    try:
        package = read_persisted_package_pure(package_id)
    except CorrelationIntegrityError as exc:
        raise PackageNotFoundError from exc
    if package is None:
        raise PackageNotFoundError
    scope = current_dataset_scope()
    try:
        source_record = _read_pure(_source_key(package_id, scope), scope=scope)
    except CorrelationIntegrityError as exc:
        return unavailable_response(package_id, [exc.limitation])
    if source_record is None:
        if build_source_projection(package) is None:
            return unavailable_response(package_id, ["package_lifecycle_ineligible"])
        return unavailable_response(package_id, ["legacy_package_without_correlation_projection"])
    source = validated_source(source_record, package, scope=scope)
    if source is None:
        return unavailable_response(package_id, ["stale_or_corrupt_correlation_sidecar"])
    source_scope = source.get("scope", {})
    if not all((source_scope.get("tenant_id"), source_scope.get("workspace_id"), source_scope.get("system_id"))):
        return response_payload(
            package_id,
            status="insufficient_evidence",
            related_packages=[],
            limitations=order_limitations([*source.get("limitations", []), "missing_required_scope"]),
        )
    if source_scope.get("tenant_id") != scope.tenant_id or source_scope.get("workspace_id") != scope.workspace_id:
        raise PackageNotFoundError

    related_packages: list[dict[str, Any]] = []
    try:
        relationship_records = _list_pure(_relationship_prefix(scope), scope=scope)
    except CorrelationIntegrityError as exc:
        return unavailable_response(package_id, [exc.limitation])
    for relationship_record in relationship_records:
        if package_id not in {
            relationship_record.get("package_a_id"),
            relationship_record.get("package_b_id"),
        }:
            continue
        try:
            relationship = validate_relationship_record(
                relationship_record,
                current_package_id=package_id,
                current_source=source,
                scope=scope,
            )
        except CorrelationIntegrityError as exc:
            return unavailable_response(package_id, [exc.limitation])
        if relationship is None:
            return unavailable_response(package_id, ["stale_or_corrupt_correlation_sidecar"])
        candidate_id = (
            relationship["package_b_id"]
            if relationship["package_a_id"] == package_id
            else relationship["package_a_id"]
        )
        related_packages.append(
            {
                "relationship_id": relationship["relationship_id"],
                "package_id": candidate_id,
                "relationship_type": relationship["relationship_type"],
                "strongest_supported_relationship": relationship["strongest_supported_relationship"],
                "supporting_relationships": relationship["supporting_relationships"],
                "temporal_relationship": relationship["temporal_relationship"],
                "operating_context_relationship": relationship["operating_context_relationship"],
                "signal_or_system_overlap": relationship["signal_or_system_overlap"],
                "evidence_refs": relationship["evidence_refs"],
                "limitations": relationship["limitations"],
                "provenance": relationship["provenance"],
                "_observation_start": relationship.get("_candidate_observation_start"),
            }
        )

    related_packages.sort(
        key=lambda item: (
            RELATIONSHIP_PRIORITY.index(item["strongest_supported_relationship"]),
            item["_observation_start"] or "",
            item["package_id"],
        )
    )
    for item in related_packages:
        item.pop("_observation_start", None)
    if related_packages:
        return response_payload(
            package_id,
            status="related_packages_found",
            related_packages=related_packages,
            limitations=source.get("limitations", []),
        )
    return response_payload(
        package_id,
        status="no_supported_relationship",
        related_packages=[],
        limitations=order_limitations([*source.get("limitations", []), "no_relationship_anchor"]),
    )


def validated_source(
    record: dict[str, Any], package: dict[str, Any], *, scope: DatasetScope
) -> dict[str, Any] | None:
    persisted_source = _source_from_record(record, scope=scope)
    rebuilt_source = build_source_projection(package)
    if persisted_source is None or rebuilt_source is None:
        return None
    expected_scope = rebuilt_source.get("scope", {})
    if (
        record.get("schema_version") != SOURCE_SCHEMA_VERSION
        or record.get("package_id") != rebuilt_source.get("package_id")
        or record.get("tenant_id") != expected_scope.get("tenant_id")
        or record.get("workspace_id") != expected_scope.get("workspace_id")
        or record.get("system_id") != expected_scope.get("system_id")
        or record.get("package_content_hash") != rebuilt_source.get("package_content_hash")
        or record.get("projected_at") != rebuilt_source.get("package_completed_at")
        or canonical_json(persisted_source) != canonical_json(rebuilt_source)
    ):
        return None
    return rebuilt_source


def validate_relationship_record(
    record: dict[str, Any],
    *,
    current_package_id: str,
    current_source: dict[str, Any],
    scope: DatasetScope,
) -> dict[str, Any] | None:
    if (
        not payload_matches_dataset_scope(record, scope)
        or record.get("schema_version") != RELATIONSHIP_SCHEMA_VERSION
        or record.get("tenant_id") != scope.tenant_id
        or record.get("workspace_id") != scope.workspace_id
        or record.get("system_id") != current_source.get("scope", {}).get("system_id")
    ):
        return None
    persisted_relationship = record.get("relationship")
    if not isinstance(persisted_relationship, dict):
        return None
    if current_package_id not in {
        persisted_relationship.get("package_a_id"),
        persisted_relationship.get("package_b_id"),
    }:
        return None
    candidate_id = (
        persisted_relationship.get("package_b_id")
        if persisted_relationship.get("package_a_id") == current_package_id
        else persisted_relationship.get("package_a_id")
    )
    candidate_id = normalize_scalar(candidate_id)
    if candidate_id is None:
        return None

    candidate_package = read_persisted_package_pure(candidate_id)
    if candidate_package is None:
        raise CorrelationIntegrityError
    candidate_record = _read_pure(_source_key(candidate_id, scope), scope=scope)
    if candidate_record is None:
        raise CorrelationIntegrityError("related_package_projection_missing")
    candidate_source = validated_source(candidate_record, candidate_package, scope=scope)
    if candidate_source is None:
        return None
    recomputed = build_relationship(current_source, candidate_source)
    if recomputed is None or canonical_json(recomputed) != canonical_json(persisted_relationship):
        return None
    package_a_id = recomputed["package_a_id"]
    package_b_id = recomputed["package_b_id"]
    if (
        record.get("relationship_id") != recomputed["relationship_id"]
        or record.get("package_a_id") != package_a_id
        or record.get("package_b_id") != package_b_id
        or record.get("package_a_hash") != recomputed["source_hashes"][package_a_id]
        or record.get("package_b_hash") != recomputed["source_hashes"][package_b_id]
    ):
        return None
    candidate_window = candidate_source.get("observation_window")
    validated = dict(recomputed)
    validated["_candidate_observation_start"] = (
        candidate_window.get("start") if isinstance(candidate_window, dict) else None
    )
    return validated


def response_payload(
    package_id: str,
    *,
    status: str,
    related_packages: list[dict[str, Any]],
    limitations: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": RESPONSE_SCHEMA_VERSION,
        "package_id": package_id,
        "correlation_status": status,
        "related_packages": related_packages,
        "limitations": order_limitations(limitations),
        "provenance": {
            "projector_version": PROJECTOR_VERSION,
            "relationship_rule_version": RULE_VERSION,
            "repository": "scoped_analysis_state_sidecar",
            "read_mode": "pure",
        },
    }


def unavailable_response(package_id: str, limitations: list[str]) -> dict[str, Any]:
    return response_payload(
        package_id,
        status="unavailable",
        related_packages=[],
        limitations=limitations,
    )


def read_persisted_package_pure(package_id: str) -> dict[str, Any] | None:
    """Rebuild a current Evidence Package without invoking write-capable stores."""
    from app.services.baseline_analysis_repository import validate_completed_analysis
    from app.services.evidence_package import ensure_evidence_package

    scope = current_dataset_scope()
    prefix = f"scopes/{scope.storage_id}/baseline-analyses"
    package_link = _read_pure(f"{prefix}/by-package/{package_id}", scope=scope)
    if not isinstance(package_link, dict) or not payload_matches_dataset_scope(package_link, scope):
        return None
    if normalize_scalar(package_link.get("package_id")) != package_id:
        return None
    analysis_id = normalize_scalar(package_link.get("analysis_run_id"))
    if analysis_id is None:
        return None
    analysis_link = _read_pure(f"{prefix}/by-analysis/{analysis_id}", scope=scope)
    if not isinstance(analysis_link, dict) or not payload_matches_dataset_scope(analysis_link, scope):
        return None
    result_job_id = normalize_scalar(analysis_link.get("result_job_id"))
    if result_job_id is None or result_job_id != analysis_id:
        return None
    result = _read_pure(f"upload_result_{result_job_id}", scope=scope)
    try:
        validate_completed_analysis(result, scope=scope, analysis_run_id=analysis_id)
    except ValueError:
        return None
    package = ensure_evidence_package(result) if isinstance(result, dict) else None
    if package is None or package.get("id") != package_id:
        return None
    return package


def classify_temporal_relationship(first_source: dict[str, Any], second_source: dict[str, Any]) -> str:
    first_window = first_source.get("observation_window")
    second_window = second_source.get("observation_window")
    if not isinstance(first_window, dict) or not isinstance(second_window, dict):
        return "unavailable"
    if first_window.get("status") != "available" or second_window.get("status") != "available":
        return "unavailable"
    first_start, first_start_valid = normalize_timestamp(first_window.get("start"))
    first_end, first_end_valid = normalize_timestamp(first_window.get("end"))
    second_start, second_start_valid = normalize_timestamp(second_window.get("start"))
    second_end, second_end_valid = normalize_timestamp(second_window.get("end"))
    if not all(
        (
            first_start_valid,
            first_end_valid,
            second_start_valid,
            second_end_valid,
            first_start,
            first_end,
            second_start,
            second_end,
        )
    ):
        return "unavailable"
    first_start_value = timestamp_value(first_start)
    first_end_value = timestamp_value(first_end)
    second_start_value = timestamp_value(second_start)
    second_end_value = timestamp_value(second_end)
    if first_start_value <= second_end_value and second_start_value <= first_end_value:
        return "overlapping_observation_window"
    gap = (
        second_start_value - first_end_value
        if first_end_value < second_start_value
        else first_start_value - second_end_value
    ).total_seconds()
    return "temporally_adjacent" if 0 <= gap <= MAX_TEMPORAL_ADJACENCY_SECONDS else "not_supported"


def classify_operating_context(first_source: dict[str, Any], second_source: dict[str, Any]) -> str:
    first_context = normalize_context(first_source.get("operating_context_id"))
    second_context = normalize_context(second_source.get("operating_context_id"))
    if first_context is None or second_context is None:
        return "unavailable"
    return "compatible" if first_context == second_context else "different"


def normalize_timestamp(value: Any) -> tuple[str | None, bool]:
    if value is None:
        return None, False
    raw_value = str(value).strip()
    if not raw_value:
        return None, False
    if raw_value.endswith("Z"):
        raw_value = f"{raw_value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError:
        return None, False
    parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    return parsed.isoformat(), True


def timestamp_value(value: str) -> datetime:
    return datetime.fromisoformat(value)


def normalize_scalar(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def normalize_context(value: Any) -> str | None:
    normalized = normalize_scalar(value)
    return normalized.casefold() if normalized else None


def normalize_id_list(value: Any) -> tuple[list[str], bool]:
    if value is None:
        return [], True
    if not isinstance(value, list):
        return [], False
    normalized: list[str] = []
    for item in value:
        normalized_item = normalize_scalar(item)
        if normalized_item is None:
            return [], False
        normalized.append(normalized_item)
    return sorted(set(normalized)), True


def normalize_pattern_ids(package: dict[str, Any]) -> tuple[list[str], bool]:
    combined: list[str] = []
    for field_name in ("analytical_pattern_ids", "historical_pattern_ids"):
        values, valid = normalize_id_list(package.get(field_name))
        if not valid:
            return [], False
        combined.extend(values)
    return sorted(set(combined)), True


def normalized_projection_ids(source: dict[str, Any], field_name: str) -> list[str]:
    values, valid = normalize_id_list(source.get(field_name))
    return values if valid else []


def evidence_ref(package_id: str, field_name: str) -> str:
    return f"evidence-package:{package_id}#{field_name}"


def projection_evidence_refs(source: dict[str, Any], field_names: tuple[str, ...]) -> list[str]:
    package_id = normalize_scalar(source.get("package_id"))
    source_refs = source.get("evidence_refs")
    if package_id is None or not isinstance(source_refs, list):
        return []
    allowed_refs = {evidence_ref(package_id, field_name) for field_name in field_names}
    return sorted(reference for reference in source_refs if isinstance(reference, str) and reference in allowed_refs)


def order_relationships(values: list[str]) -> list[str]:
    unique = set(values)
    return [item for item in RELATIONSHIP_PRIORITY if item in unique]


def order_limitations(values: list[str]) -> list[str]:
    unique = {value for value in values if value in LIMITATION_PRIORITY}
    return [item for item in LIMITATION_PRIORITY if item in unique]


def _correlation_prefix(scope: DatasetScope) -> str:
    return f"scopes/{scope.storage_id}/baseline-analyses/package-correlation"


def _source_prefix(scope: DatasetScope) -> str:
    return f"{_correlation_prefix(scope)}/sources"


def _source_key(package_id: str, scope: DatasetScope) -> str:
    return f"{_source_prefix(scope)}/{package_id}"


def _relationship_prefix(scope: DatasetScope) -> str:
    return f"{_correlation_prefix(scope)}/relationships"


def _relationship_key(relationship_id: str, scope: DatasetScope) -> str:
    return f"{_relationship_prefix(scope)}/{relationship_id}"


def _read(name: str, *, scope: DatasetScope) -> dict[str, Any] | None:
    shared = read_shared_state(name, scope=scope)
    if isinstance(shared, dict):
        return shared
    return read_local_json(f"{name}.json", scope=scope)


def _read_pure(name: str, *, scope: DatasetScope) -> dict[str, Any] | None:
    """Read current storage without initialization, migration, or repair."""
    try:
        return read_shared_state_pure(name, scope=scope)
    except Exception as exc:
        raise CorrelationIntegrityError from exc


def _list_pure(name: str, *, scope: DatasetScope) -> list[dict[str, Any]]:
    """Enumerate immutable sidecars without invoking runtime initialization."""
    try:
        return list_shared_state_prefix_pure(name, scope=scope)
    except Exception as exc:
        raise CorrelationIntegrityError from exc


def _write(name: str, payload: dict[str, Any], *, scope: DatasetScope) -> None:
    normalized = attach_dataset_scope(dict(payload), scope=scope)
    write_local_json(f"{name}.json", normalized, scope=scope)
    write_shared_state_strict(name, normalized, scope=scope)


def _insert(
    name: str,
    payload: dict[str, Any],
    *,
    scope: DatasetScope,
) -> tuple[bool, dict[str, Any]]:
    normalized = attach_dataset_scope(dict(payload), scope=scope)
    return insert_shared_state_strict(name, normalized, scope=scope)


def _source_record(source: dict[str, Any]) -> dict[str, Any]:
    source_scope = source.get("scope", {})
    return {
        "version": 1,
        "schema_version": SOURCE_SCHEMA_VERSION,
        "package_id": source["package_id"],
        "tenant_id": source_scope.get("tenant_id"),
        "workspace_id": source_scope.get("workspace_id"),
        "system_id": source_scope.get("system_id"),
        "package_content_hash": source["package_content_hash"],
        "projected_at": source["package_completed_at"],
        "source": source,
    }


def _source_from_record(record: Any, *, scope: DatasetScope) -> dict[str, Any] | None:
    if not isinstance(record, dict) or not payload_matches_dataset_scope(record, scope):
        return None
    source = record.get("source")
    if not isinstance(source, dict) or source.get("schema_version") != SOURCE_SCHEMA_VERSION:
        return None
    source_scope = source.get("scope") if isinstance(source.get("scope"), dict) else {}
    if (
        record.get("package_id") != source.get("package_id")
        or record.get("tenant_id") != source_scope.get("tenant_id")
        or record.get("workspace_id") != source_scope.get("workspace_id")
        or record.get("system_id") != source_scope.get("system_id")
        or record.get("package_content_hash") != source.get("package_content_hash")
        or record.get("projected_at") != source.get("package_completed_at")
    ):
        return None
    return source


def _persist_relationship(
    relationship: dict[str, Any],
    *,
    system_id: str,
    scope: DatasetScope,
) -> None:
    relationship_id = relationship["relationship_id"]
    package_a_id = relationship["package_a_id"]
    package_b_id = relationship["package_b_id"]
    relationship_scope = relationship["source_hashes"]
    record = {
        "version": 1,
        "schema_version": RELATIONSHIP_SCHEMA_VERSION,
        "relationship_id": relationship_id,
        "package_a_id": package_a_id,
        "package_b_id": package_b_id,
        "package_a_hash": relationship_scope[package_a_id],
        "package_b_hash": relationship_scope[package_b_id],
        "tenant_id": scope.tenant_id,
        "workspace_id": scope.workspace_id,
        "system_id": system_id,
        "relationship": relationship,
    }
    key = _relationship_key(relationship_id, scope)
    _, persisted = _insert(key, record, scope=scope)
    expected = attach_dataset_scope(dict(record), scope=scope)
    if canonical_json(persisted) != canonical_json(expected):
        logger.error("evidence_package_correlation_relationship_conflict relationship_id=%s", relationship_id)
