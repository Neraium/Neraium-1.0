from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_EVEN
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "evidence-package-fingerprint-v1"
ALGORITHM_VERSION = "evidence-package-canonical-sha256-v1"
MATCH_SCHEMA_VERSION = "evidence-package-exact-match-v1"
ROUNDING_PLACES = 8


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FingerprintStatus(str, Enum):
    available = "available"
    unavailable = "unavailable"


class ExactMatchStatus(str, Enum):
    not_evaluated = "not_evaluated"
    insufficient_history = "insufficient_history"
    unavailable = "unavailable"
    no_exact_match = "no_exact_match"
    exact_match = "exact_match"


SIMILARITY_SCHEMA_VERSION = "evidence-package-approximate-similarity-v1"
SIMILARITY_ALGORITHM_VERSION = "evidence-package-explainable-weighted-v1"
HISTORICAL_PATTERN_SCHEMA_VERSION = "evidence-package-historical-pattern-classification-v1"
HISTORICAL_PATTERN_ALGORITHM_VERSION = "evidence-package-historical-pattern-rules-v1"
MINIMUM_SUPPORTED_WEIGHT = 0.80
SUPPORTED_SIMILARITY_THRESHOLD = 0.60


class SimilarityStatus(str, Enum):
    not_evaluated = "not_evaluated"
    insufficient_history = "insufficient_history"
    unavailable = "unavailable"
    insufficient_similarity_evidence = "insufficient_similarity_evidence"
    excluded = "excluded"
    no_supported_similarity = "no_supported_similarity"
    supported_similarity = "supported_similarity"


class HistoricalPatternClassification(str, Enum):
    not_evaluated = "not_evaluated"
    insufficient_history = "insufficient_history"
    unavailable = "unavailable"
    no_supported_historical_pattern = "no_supported_historical_pattern"
    exact_historical_match = "exact_historical_match"
    similar_historical_pattern = "similar_historical_pattern"


class DimensionStatus(str, Enum):
    supported = "supported"
    unavailable = "unavailable"
    excluded = "excluded"
    not_applicable = "not_applicable"


class FingerprintScope(StrictModel):
    organization_id: str
    workspace_id: str
    system_id: str | None = None


class FingerprintProvenance(StrictModel):
    source_schema_version: str
    package_revision: int
    source: str
    calculation_versions: list[str]


class EvidencePackageFingerprint(StrictModel):
    schema_version: str = SCHEMA_VERSION
    algorithm_version: str = ALGORITHM_VERSION
    status: FingerprintStatus
    package_id: str
    fingerprint_id: str | None = None
    canonical_digest: str | None = None
    scope: FingerprintScope
    features: dict[str, Any]
    available_dimensions: list[str]
    unavailable_dimensions: list[str]
    evidence_refs: list[str]
    limitations: list[str]
    provenance: FingerprintProvenance


class ExactMatchObservation(StrictModel):
    observation_id: str
    evaluated_package_id: str
    evaluated_fingerprint_id: str
    prior_package_id: str
    prior_fingerprint_id: str
    canonical_digest: str
    algorithm_version: str
    eligibility_basis: str
    scope_basis: str
    temporal_basis: str
    evidence_refs: list[str]
    limitations: list[str]


class ExactMatchResult(StrictModel):
    schema_version: str = MATCH_SCHEMA_VERSION
    status: ExactMatchStatus
    evaluated_package_id: str
    evaluated_fingerprint_id: str | None = None
    algorithm_version: str = ALGORITHM_VERSION
    matches: list[ExactMatchObservation] = Field(default_factory=list)
    eligible_history_count: int = 0
    limitations: list[str] = Field(default_factory=list)


class SimilarityDimension(StrictModel):
    name: str
    status: DimensionStatus
    score: float | None
    weight: float
    evidence_refs: list[str] = Field(default_factory=list)
    unavailable_reason: str | None = None
    exclusion_reason: str | None = None


class SimilarityProvenance(StrictModel):
    eligibility_basis: str
    scope_basis: str
    temporal_basis: str
    score_formula: str


class ApproximateSimilarityResult(StrictModel):
    schema_version: str = SIMILARITY_SCHEMA_VERSION
    algorithm_version: str = SIMILARITY_ALGORITHM_VERSION
    evaluated_package_id: str
    evaluated_fingerprint_id: str
    candidate_package_id: str
    candidate_fingerprint_id: str
    overall_similarity: float | None
    overall_status: SimilarityStatus
    supported_weight: float
    required_supported_weight: float = MINIMUM_SUPPORTED_WEIGHT
    dimensions: list[SimilarityDimension]
    supported_dimensions: list[str]
    unavailable_dimensions: list[str]
    excluded_dimensions: list[str]
    limitations: list[str]
    provenance: SimilarityProvenance


class ApproximateSimilarityResponse(StrictModel):
    schema_version: str = SIMILARITY_SCHEMA_VERSION
    algorithm_version: str = SIMILARITY_ALGORITHM_VERSION
    evaluated_package_id: str
    evaluated_fingerprint_id: str | None = None
    overall_status: SimilarityStatus
    eligible_history_count: int = 0
    results: list[ApproximateSimilarityResult] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class HistoricalPatternMatch(StrictModel):
    candidate_package_id: str
    candidate_fingerprint_id: str
    match_type: str
    exact_match_observation_id: str | None = None
    approximate_similarity_score: float | None = None
    approximate_algorithm_version: str | None = None
    prior_package_timestamp: str
    evidence_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    non_causal_interpretation: str
    supported_dimensions: list[str] = Field(default_factory=list)
    unavailable_dimensions: list[str] = Field(default_factory=list)
    excluded_dimensions: list[str] = Field(default_factory=list)
    supported_weight: float | None = None
    required_supported_weight: float | None = None


class HistoricalPatternProvenance(StrictModel):
    rule: str
    exact_match_schema_version: str
    approximate_similarity_schema_version: str
    fingerprint_algorithm_version: str
    approximate_algorithm_version: str
    temporal_tie_break: str


class HistoricalPatternResponse(StrictModel):
    schema_version: str = HISTORICAL_PATTERN_SCHEMA_VERSION
    algorithm_version: str = HISTORICAL_PATTERN_ALGORITHM_VERSION
    evaluated_package_id: str
    evaluated_fingerprint_id: str | None = None
    classification: HistoricalPatternClassification
    exact_match_count: int = 0
    similar_pattern_count: int = 0
    no_supported_similarity_candidate_count: int = 0
    eligible_history_count: int = 0
    strongest_supported_match: HistoricalPatternMatch | None = None
    supporting_matches: list[HistoricalPatternMatch] = Field(default_factory=list)
    excluded_candidate_count: int = 0
    insufficient_evidence_candidate_count: int = 0
    evidence_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    provenance: HistoricalPatternProvenance


SIMILARITY_WEIGHTS = {
    "system_identity": 0.20,
    "primary_signal_pair": 0.20,
    "relationship_type": 0.10,
    "relationship_direction": 0.10,
    "relationship_strength_similarity": 0.12,
    "relationship_change_magnitude": 0.10,
    "relationship_change_direction": 0.08,
    "persistence_similarity": 0.05,
    "operating_context_compatibility": 0.05,
}


def _bounded_similarity(left: Any, right: Any) -> float:
    return round(max(0.0, 1.0 - min(abs(float(left) - float(right)), 1.0)), ROUNDING_PLACES)


def compare_fingerprints(
    evaluated: EvidencePackageFingerprint,
    candidate: EvidencePackageFingerprint,
) -> ApproximateSimilarityResult:
    """Compare two persisted fingerprints with transparent, non-renormalized weights."""
    dimensions: list[SimilarityDimension] = []
    evaluated_relationship = evaluated.features.get("relationship", {})
    candidate_relationship = candidate.features.get("relationship", {})

    def dimension_refs(name: str) -> list[str]:
        """Return only typed evidence IDs retained by Fingerprinting v1."""
        available = set(evaluated.evidence_refs) | set(candidate.evidence_refs)
        expected = {
            "primary_signal_pair": {"ev-baseline-strength", "ev-comparison-strength"},
            "relationship_type": {"ev-baseline-strength", "ev-comparison-strength"},
            "relationship_direction": {"ev-baseline-strength", "ev-comparison-strength"},
            "relationship_strength_similarity": {"ev-baseline-strength", "ev-comparison-strength"},
            "relationship_change_magnitude": {"ev-absolute-change"},
            "relationship_change_direction": {"ev-baseline-strength", "ev-comparison-strength"},
            "persistence_similarity": {"ev-persistence"},
        }.get(name)
        if expected is not None:
            return sorted(available & expected)
        if name == "operating_context_compatibility":
            return sorted(ref for ref in available if ref.startswith("ev-context-"))
        # The v1 sidecar scope is authoritative, but it does not retain a typed
        # supporting-evidence ID for system identity.
        return []

    def add(name: str, score: float | None, *, unavailable: str | None = None, not_applicable: str | None = None) -> None:
        status = DimensionStatus.supported
        reason = unavailable
        if unavailable:
            status = DimensionStatus.unavailable
        elif not_applicable:
            status = DimensionStatus.not_applicable
            reason = not_applicable
        dimensions.append(SimilarityDimension(
            name=name, status=status, score=score, weight=SIMILARITY_WEIGHTS[name],
            evidence_refs=dimension_refs(name) if score is not None else [],
            unavailable_reason=reason, exclusion_reason=None,
        ))

    if evaluated.algorithm_version != ALGORITHM_VERSION or candidate.algorithm_version != ALGORITHM_VERSION:
        for name, weight in SIMILARITY_WEIGHTS.items():
            dimensions.append(SimilarityDimension(name=name, status=DimensionStatus.excluded, score=None, weight=weight, exclusion_reason="compatible_fingerprint_algorithm_required"))
        return ApproximateSimilarityResult(
            evaluated_package_id=evaluated.package_id, evaluated_fingerprint_id=evaluated.fingerprint_id or "",
            candidate_package_id=candidate.package_id, candidate_fingerprint_id=candidate.fingerprint_id or "",
            overall_similarity=None, overall_status=SimilarityStatus.excluded, dimensions=dimensions,
            supported_weight=0.0,
            supported_dimensions=[], unavailable_dimensions=[], excluded_dimensions=list(SIMILARITY_WEIGHTS),
            limitations=["Comparison requires fingerprint algorithm evidence-package-canonical-sha256-v1."],
            provenance=SimilarityProvenance(eligibility_basis="compatible_persisted_fingerprints_required", scope_basis="not_evaluated", temporal_basis="established_by_caller", score_formula="not_evaluated_for_excluded_comparison"),
        )

    same_scope = evaluated.scope.organization_id == candidate.scope.organization_id and evaluated.scope.workspace_id == candidate.scope.workspace_id
    same_system = same_scope and bool(evaluated.scope.system_id) and evaluated.scope.system_id == candidate.scope.system_id
    if not same_system:
        for name, weight in SIMILARITY_WEIGHTS.items():
            dimensions.append(SimilarityDimension(name=name, status=DimensionStatus.excluded, score=None, weight=weight, exclusion_reason="same_system_scope_required"))
        return ApproximateSimilarityResult(
            evaluated_package_id=evaluated.package_id, evaluated_fingerprint_id=evaluated.fingerprint_id or "",
            candidate_package_id=candidate.package_id, candidate_fingerprint_id=candidate.fingerprint_id or "",
            overall_similarity=None, overall_status=SimilarityStatus.excluded, dimensions=dimensions,
            supported_weight=0.0,
            supported_dimensions=[], unavailable_dimensions=[], excluded_dimensions=list(SIMILARITY_WEIGHTS),
            limitations=["Comparison requires equal tenant, workspace, and system identity."],
            provenance=SimilarityProvenance(eligibility_basis="persisted_available_fingerprints", scope_basis="same_system_scope_required", temporal_basis="established_by_caller", score_formula="not_evaluated_for_excluded_comparison"),
        )

    add("system_identity", 1.0)
    if evaluated_relationship.get("signal_ids") != candidate_relationship.get("signal_ids"):
        dimensions = []
        for name, weight in SIMILARITY_WEIGHTS.items():
            reason = "same_primary_signal_pair_required_v1" if name == "primary_signal_pair" else "not_evaluated_after_primary_signal_pair_exclusion"
            dimensions.append(SimilarityDimension(
                name=name, status=DimensionStatus.excluded, score=None, weight=weight,
                evidence_refs=dimension_refs(name) if name == "primary_signal_pair" else [],
                exclusion_reason=reason,
            ))
        return ApproximateSimilarityResult(
            evaluated_package_id=evaluated.package_id, evaluated_fingerprint_id=evaluated.fingerprint_id or "",
            candidate_package_id=candidate.package_id, candidate_fingerprint_id=candidate.fingerprint_id or "",
            overall_similarity=None, overall_status=SimilarityStatus.excluded, supported_weight=0.0,
            dimensions=dimensions, supported_dimensions=[], unavailable_dimensions=[], excluded_dimensions=list(SIMILARITY_WEIGHTS),
            limitations=["The canonical primary signal pair must match exactly in Approximate Similarity v1."],
            provenance=SimilarityProvenance(eligibility_basis="same_primary_signal_pair_required_v1", scope_basis="equal_tenant_workspace_and_system", temporal_basis="established_by_caller", score_formula="not_evaluated_for_excluded_comparison"),
        )
    add("primary_signal_pair", 1.0)
    add("relationship_type", 1.0 if evaluated_relationship.get("relationship_type") == candidate_relationship.get("relationship_type") else 0.0)
    evaluated_direction = evaluated_relationship.get("directionality")
    candidate_direction = candidate_relationship.get("directionality")
    if evaluated_direction == candidate_direction == "symmetric":
        add("relationship_direction", None, not_applicable="Both relationship types are symmetric.")
    else:
        add("relationship_direction", 1.0 if evaluated_direction == candidate_direction and evaluated_relationship.get("signal_ids") == candidate_relationship.get("signal_ids") else 0.0)
    if evaluated_relationship.get("comparison_strength") is None or candidate_relationship.get("comparison_strength") is None:
        add("relationship_strength_similarity", None, unavailable="Comparison strength is not available for both fingerprints.")
    else:
        add("relationship_strength_similarity", _bounded_similarity(evaluated_relationship["comparison_strength"], candidate_relationship["comparison_strength"]))
    if evaluated_relationship.get("absolute_change") is None or candidate_relationship.get("absolute_change") is None:
        add("relationship_change_magnitude", None, unavailable="Relationship change magnitude is not available for both fingerprints.")
    else:
        add("relationship_change_magnitude", _bounded_similarity(evaluated_relationship["absolute_change"], candidate_relationship["absolute_change"]))
    if evaluated_relationship.get("signed_change") is None or candidate_relationship.get("signed_change") is None:
        add("relationship_change_direction", None, unavailable="Relationship change direction is not available for both fingerprints.")
    else:
        evaluated_change = float(evaluated_relationship["signed_change"])
        candidate_change = float(candidate_relationship["signed_change"])
        add("relationship_change_direction", 1.0 if (evaluated_change > 0) == (candidate_change > 0) and (evaluated_change < 0) == (candidate_change < 0) else 0.0)
    if "persistence" in evaluated_relationship and "persistence" in candidate_relationship:
        add("persistence_similarity", _bounded_similarity(evaluated_relationship["persistence"], candidate_relationship["persistence"]))
    else:
        add("persistence_similarity", None, unavailable="Quantified persistence is not available for both packages.")
    evaluated_context = {item["canonical_role"]: item for item in evaluated.features.get("operating_context", [])}
    candidate_context = {item["canonical_role"]: item for item in candidate.features.get("operating_context", [])}
    common_roles = sorted(set(evaluated_context) & set(candidate_context))
    context_scores = [
        _bounded_similarity(evaluated_context[role][key], candidate_context[role][key])
        for role in common_roles for key in ("baseline_mean", "comparison_mean")
        if key in evaluated_context[role] and key in candidate_context[role]
    ]
    if context_scores:
        add("operating_context_compatibility", round(sum(context_scores) / len(context_scores), ROUNDING_PLACES))
    else:
        add("operating_context_compatibility", None, unavailable="Comparable operating context is not available for both packages.")

    supported = [item for item in dimensions if item.status == DimensionStatus.supported]
    supported_weight = round(sum(item.weight for item in supported), 8)
    overall = round(sum((item.score or 0.0) * item.weight for item in supported), ROUNDING_PLACES)
    enough = supported_weight >= MINIMUM_SUPPORTED_WEIGHT
    status = SimilarityStatus.insufficient_similarity_evidence if not enough else (SimilarityStatus.supported_similarity if overall >= SUPPORTED_SIMILARITY_THRESHOLD else SimilarityStatus.no_supported_similarity)
    limitations = [
        "Unavailable dimensions are omitted from the weighted sum and weights are not renormalized.",
        "Fingerprinting v1 retains no typed supporting-evidence reference for system identity; persisted scope is the authority.",
    ]
    if not enough:
        overall = None
        limitations.append(f"Supported dimension weight {supported_weight:.2f} did not meet required minimum {MINIMUM_SUPPORTED_WEIGHT:.2f}.")
    return ApproximateSimilarityResult(
        evaluated_package_id=evaluated.package_id, evaluated_fingerprint_id=evaluated.fingerprint_id or "",
        candidate_package_id=candidate.package_id, candidate_fingerprint_id=candidate.fingerprint_id or "",
        overall_similarity=overall, overall_status=status, dimensions=dimensions,
        supported_weight=supported_weight,
        supported_dimensions=[item.name for item in supported],
        unavailable_dimensions=[item.name for item in dimensions if item.status in {DimensionStatus.unavailable, DimensionStatus.not_applicable}],
        excluded_dimensions=[item.name for item in dimensions if item.status == DimensionStatus.excluded],
        limitations=limitations,
        provenance=SimilarityProvenance(
            eligibility_basis="persisted_available_fingerprints",
            scope_basis="equal_tenant_workspace_and_system",
            temporal_basis="candidate_evaluation_strictly_precedes_evaluated_package",
            score_formula="sum(dimension.score * dimension.weight); unavailable weights are not renormalized",
        ),
    )


def aggregate_similarity_status(results: list[ApproximateSimilarityResult]) -> SimilarityStatus:
    """Apply deterministic collection precedence without hiding insufficient evidence."""
    statuses = {result.overall_status for result in results}
    for status in (
        SimilarityStatus.supported_similarity,
        SimilarityStatus.no_supported_similarity,
        SimilarityStatus.insufficient_similarity_evidence,
        SimilarityStatus.excluded,
        SimilarityStatus.unavailable,
    ):
        if status in statuses:
            return status
    return SimilarityStatus.insufficient_history


def _number(value: Any) -> str:
    if isinstance(value, bool):
        raise ValueError("fingerprint_numeric_value_invalid")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("fingerprint_numeric_value_invalid") from exc
    if not math.isfinite(number):
        raise ValueError("fingerprint_numeric_value_not_finite")
    quantum = Decimal(1).scaleb(-ROUNDING_PLACES)
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_EVEN)
    return format(rounded, "f").rstrip("0").rstrip(".") or "0"


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build_fingerprint(package: dict[str, Any], *, algorithm_version: str = ALGORITHM_VERSION) -> EvidencePackageFingerprint:
    relationship = package.get("primary_relationship") if isinstance(package.get("primary_relationship"), dict) else {}
    scope = FingerprintScope(
        organization_id=str(package.get("organization_id") or ""),
        workspace_id=str(package.get("portfolio_id") or ""),
        system_id=str(package.get("system_id") or "") or None,
    )
    evidence_ids = {str(item.get("id")) for item in package.get("supporting_evidence", []) if isinstance(item, dict)}
    required_refs = {
        "baseline_strength": "ev-baseline-strength",
        "comparison_strength": "ev-comparison-strength",
        "absolute_change": "ev-absolute-change",
    }
    required: dict[str, Any] = {
        "organization_id": scope.organization_id,
        "workspace_id": scope.workspace_id,
        "system_id": scope.system_id,
        "condition_type": package.get("condition_type"),
        "left_signal_id": relationship.get("left_variable"),
        "right_signal_id": relationship.get("right_variable"),
        "relationship_type": relationship.get("relationship_type"),
        "baseline_strength": relationship.get("baseline_strength"),
        "comparison_strength": relationship.get("comparison_strength"),
        "signed_change": relationship.get("signed_change"),
        "absolute_change": relationship.get("absolute_change"),
    }
    missing = sorted(key for key, value in required.items() if value is None or value == "")
    missing.extend(sorted(key for key, ref in required_refs.items() if ref not in evidence_ids and key not in missing))
    numeric: dict[str, str] = {}
    try:
        for key in ("baseline_strength", "comparison_strength", "signed_change", "absolute_change"):
            if key not in missing:
                numeric[key] = _number(required[key])
    except ValueError:
        raise

    relationship_type = str(required.get("relationship_type") or "").lower()
    symmetric = relationship_type in {"correlation", "pearson_correlation", "spearman_correlation"}
    signals = [str(required.get("left_signal_id") or ""), str(required.get("right_signal_id") or "")]
    if symmetric:
        signals.sort()

    context_features: list[dict[str, Any]] = []
    context = package.get("operating_context") if isinstance(package.get("operating_context"), dict) else {}
    metrics: list[dict[str, Any]] = []
    if isinstance(context.get("load_context"), dict):
        metrics.append(context["load_context"])
    for group in ("equipment_configuration", "control_context", "environmental_context"):
        metrics.extend(item for item in context.get(group, []) if isinstance(item, dict))
    for metric in metrics:
        values = {}
        for key in ("baseline_mean", "comparison_mean"):
            if metric.get(key) is not None:
                values[key] = _number(metric[key])
        if values:
            context_features.append({"canonical_role": str(metric.get("canonical_role") or ""), **values})
    context_features.sort(key=lambda item: (item["canonical_role"], canonical_bytes(item)))

    persistence = relationship.get("persistence_score")
    optional_unavailable = []
    if persistence is None:
        optional_unavailable.append("quantified_persistence")
    if not context_features:
        optional_unavailable.append("operating_context")
    selected_ref_ids = set(required_refs.values())
    if persistence is not None:
        selected_ref_ids.add("ev-persistence")
    if context_features:
        selected_ref_ids.update(item for item in evidence_ids if item.startswith("ev-context-"))
    selected_evidence = [
        item for item in package.get("supporting_evidence", [])
        if isinstance(item, dict) and item.get("id") in selected_ref_ids
    ]
    calculation_versions = sorted({str(item.get("calculation_version")) for item in selected_evidence if item.get("calculation_version")})
    features: dict[str, Any] = {}
    refs = sorted(item for item in evidence_ids if item in selected_ref_ids)
    if not missing:
        features = {
            "scope": scope.model_dump(mode="json"),
            "condition_type": str(required["condition_type"]),
            "relationship": {
                "signal_ids": signals,
                "relationship_type": str(required["relationship_type"]),
                "directionality": "symmetric" if symmetric else "directed",
                **numeric,
                **({"persistence": _number(persistence)} if persistence is not None else {}),
            },
            "operating_context": context_features,
            "calculation_versions": calculation_versions,
            "evidence": sorted(
                ({"id": item["id"], "quality_status": item.get("quality_status"), "calculation_version": item.get("calculation_version")} for item in selected_evidence),
                key=lambda item: item["id"],
            ),
        }
    digest = None
    fingerprint_id = None
    if not missing:
        digest = hashlib.sha256(canonical_bytes({"algorithm_version": algorithm_version, "features": features})).hexdigest()
        fingerprint_id = f"sha256:{digest}"
    unavailable = sorted(set(missing + optional_unavailable))
    available = sorted(set(required) - set(missing))
    if persistence is not None:
        available.append("quantified_persistence")
    if context_features:
        available.append("operating_context")
    return EvidencePackageFingerprint(
        algorithm_version=algorithm_version,
        status=FingerprintStatus.available if digest else FingerprintStatus.unavailable,
        package_id=str(package.get("id") or ""), fingerprint_id=fingerprint_id, canonical_digest=digest,
        scope=scope, features=features, available_dimensions=sorted(available), unavailable_dimensions=unavailable,
        evidence_refs=refs, limitations=[f"Unavailable dimension: {item}." for item in unavailable],
        provenance=FingerprintProvenance(source_schema_version=str(package.get("schema_version") or ""), package_revision=int(package.get("revision") or 0), source="completed_analysis_persistence", calculation_versions=calculation_versions),
    )


def parse_timestamp(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None


def observation_id(evaluated_package_id: str, prior_package_id: str, algorithm_version: str, basis: str) -> str:
    payload = {"evaluated_package_id": evaluated_package_id, "prior_package_id": prior_package_id, "algorithm_version": algorithm_version, "basis": basis}
    return f"sha256:{hashlib.sha256(canonical_bytes(payload)).hexdigest()}"
