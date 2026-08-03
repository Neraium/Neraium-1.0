from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field


SCHEMA_VERSION = "evidence-package-v1"
PACKAGE_NAMESPACE = UUID("873d640e-f7c7-4c40-9fac-c09957ee49e8")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PackageStatus(str, Enum):
    emerging = "emerging"
    active = "active"
    escalating = "escalating"
    stable_persistent = "stable_persistent"
    dormant = "dormant"
    load_dependent = "load_dependent"
    monitoring_after_intervention = "monitoring_after_intervention"
    resolved = "resolved"
    superseded = "superseded"
    insufficient_evidence = "insufficient_evidence"


class ReferenceLevel(str, Enum):
    matched_historical_baseline = "matched_historical_baseline"
    related_state = "related_state"
    physics_informed_envelope = "physics_informed_envelope"
    insufficient_evidence = "insufficient_evidence"


class ConfidenceLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class HypothesisSupport(str, Enum):
    strongly_supported = "strongly_supported"
    moderately_supported = "moderately_supported"
    weakly_supported = "weakly_supported"
    cannot_distinguish = "cannot_distinguish"


class PrimaryRelationship(StrictModel):
    left_variable: str
    right_variable: str
    relationship_label: str
    relationship_type: str
    change_direction: str
    baseline_strength: float
    comparison_strength: float
    absolute_change: float
    signed_change: float | None = None
    baseline_sample_count: int
    comparison_sample_count: int
    persistence_score: float | None = None
    relationship_importance_score: float | None = None
    relationship_importance_rationale: str
    source_model_edge_id: str | None = None


class ComparisonReference(StrictModel):
    reference_level: ReferenceLevel
    reference_baseline_id: str
    reference_baseline_version: int | str | None = None
    reference_summary: str


class ConfidenceDimension(StrictModel):
    level: ConfidenceLevel = ConfidenceLevel.unknown
    score: float | None = None
    reason: str
    method: str
    evidence_refs: list[str] = Field(default_factory=list)


class PackageConfidence(StrictModel):
    finding_confidence: ConfidenceDimension
    data_quality_confidence: ConfidenceDimension
    operating_state_confidence: ConfidenceDimension
    mapping_confidence: ConfidenceDimension
    physical_consistency_confidence: ConfidenceDimension


class TimelineEvent(StrictModel):
    id: str
    sequence: int
    event_type: str
    occurred_at: str
    summary: str
    variables: list[str]
    evidence_refs: list[str]
    confidence_level: ConfidenceLevel
    is_earliest_supported: bool


class SupportingEvidence(StrictModel):
    id: str
    evidence_type: str
    label: str
    summary: str
    value: Any
    unit: str | None = None
    expected_value: Any | None = None
    expected_min: float | None = None
    expected_max: float | None = None
    observed_at: str | None = None
    window_start: str | None = None
    window_end: str | None = None
    source_variables: list[str]
    quality_status: str
    calculation_version: str
    metadata: dict[str, Any]


class EvidenceLimitation(StrictModel):
    id: str
    limitation_type: str
    summary: str
    affected_confidence_dimensions: list[str]
    source: str


class Hypothesis(StrictModel):
    id: str
    rank: int
    label: str
    support_level: HypothesisSupport
    supporting_evidence_refs: list[str]
    contradicting_evidence_refs: list[str]
    limitations: list[str]
    status: str


class PackageProvenance(StrictModel):
    analysis_version: str
    algorithm_version: str
    baseline_model_version: int | str | None = None
    topology_version: str | None = None
    source_dataset_ids: list[str]
    creation_reason: str
    last_update_reason: str
    created_at: str
    latest_evaluated_at: str
    revision: int


class EvidencePackage(StrictModel):
    id: str
    package_number: str
    schema_version: str
    revision: int
    analysis_id: str
    organization_id: str
    portfolio_id: str | None = None
    site_id: str | None = None
    system_id: str | None = None
    baseline_id: str
    baseline_version: int | str | None = None
    comparison_dataset_id: str
    created_at: str
    updated_at: str
    first_supported_at: str | None = None
    last_observed_at: str | None = None
    latest_evaluated_at: str
    title: str
    system_label: str
    condition_type: str
    status: PackageStatus
    severity: str | None = None
    active_duration_seconds: float | None = None
    persistence_summary: str
    change_summary: str
    primary_relationship: PrimaryRelationship
    comparison_reference: ComparisonReference
    confidence: PackageConfidence
    timeline: list[TimelineEvent]
    supporting_evidence: list[SupportingEvidence]
    limitations: list[EvidenceLimitation]
    hypotheses: list[Hypothesis]
    provenance: PackageProvenance


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(value: Any, *keys: str, default: Any = None) -> Any:
    current = _mapping(value)
    for key in keys:
        candidate = current.get(key)
        if candidate is not None and candidate != "":
            return candidate
    return default


def _relationship(result: dict[str, Any]) -> dict[str, Any] | None:
    baseline = _mapping(result.get("baseline_analysis"))
    relationship = _mapping(result.get("relationship_analysis"))
    model = _mapping(result.get("relationship_model"))
    candidates: list[Any] = []
    for container in (baseline, relationship, model):
        for key in ("relationship_drift", "top_relationship_changes"):
            if isinstance(container.get(key), list):
                candidates.extend(container[key])
    for item in candidates:
        if not isinstance(item, dict):
            continue
        columns = item.get("columns")
        has_pair = isinstance(columns, list) and len(columns) >= 2
        if has_pair or (_first(item, "left", "source", "left_variable") and _first(item, "right", "target", "right_variable")):
            return item
    return None


def _finding(result: dict[str, Any]) -> dict[str, Any]:
    for key in ("conditions", "findings"):
        values = result.get(key)
        if isinstance(values, list) and values and isinstance(values[0], dict):
            return values[0]
    for key in ("analysis_result", "analysis_explanation", "analysis"):
        container = _mapping(result.get(key))
        for child in ("conditions", "insights", "findings"):
            values = container.get(child)
            if isinstance(values, list) and values and isinstance(values[0], dict):
                return values[0]
    return {}


def _iso(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _unknown(reason: str = "This confidence dimension is not calculated in Evidence Package v1.") -> ConfidenceDimension:
    return ConfidenceDimension(level=ConfidenceLevel.unknown, score=None, reason=reason, method="not_calculated", evidence_refs=[])


def build_evidence_package(result: dict[str, Any]) -> dict[str, Any] | None:
    """Formalize one existing comparison finding without adding analytical claims."""
    analysis_id = str(result.get("comparison_analysis_id") or result.get("analysis_run_id") or "").strip()
    baseline_id = str(result.get("baseline_id") or _mapping(result.get("active_baseline_reference")).get("model_id") or "").strip()
    dataset_id = str(result.get("comparison_dataset_id") or result.get("dataset_id") or "").strip()
    edge = _relationship(result)
    if not analysis_id or not baseline_id or not dataset_id or edge is None:
        return None
    columns = edge.get("columns") if isinstance(edge.get("columns"), list) else []
    left = str(_first(edge, "left", "source", "left_variable", default=columns[0] if len(columns) > 0 else ""))
    right = str(_first(edge, "right", "target", "right_variable", default=columns[1] if len(columns) > 1 else ""))
    baseline_strength = float(_first(edge, "baseline_correlation", "baseline_strength", default=0.0))
    comparison_strength = float(_first(edge, "recent_correlation", "current_correlation", "current_strength", "comparison_strength", default=0.0))
    absolute_change = float(_first(edge, "correlation_delta", "absolute_change", default=abs(comparison_strength - baseline_strength)))
    signed_change = float(_first(edge, "signed_correlation_delta", "signed_change", default=comparison_strength - baseline_strength))
    baseline_count = int(_first(edge, "baseline_sample_count", "baseline_sample_size", default=0))
    comparison_count = int(_first(edge, "recent_sample_count", "comparison_sample_count", "recent_sample_size", default=0))
    finding = _finding(result)
    reference = _mapping(result.get("active_baseline_reference"))
    created = _iso(result.get("completed_at") or result.get("last_processed_at"), datetime.now(timezone.utc).isoformat())
    first_supported = _first(finding, "first_detected_at", "first_supported_at", "change_onset") or result.get("change_onset")
    last_observed = _first(finding, "last_observed_at", "updated_at") or result.get("last_processed_at") or created
    package_uuid = str(uuid5(PACKAGE_NAMESPACE, f"{result.get('organization_id')}:{analysis_id}:{baseline_id}:{dataset_id}"))
    package_number = f"EP-{analysis_id[:8].upper()}-{package_uuid[:4].upper()}"
    variables = [left, right]
    evidence_specs = [
        ("baseline-strength", "relationship_strength", "Baseline relationship strength", baseline_strength, None),
        ("comparison-strength", "relationship_strength", "Comparison relationship strength", comparison_strength, None),
        ("absolute-change", "relationship_change", "Absolute correlation change", absolute_change, None),
        ("baseline-samples", "sample_count", "Baseline sample count", baseline_count, "samples"),
        ("comparison-samples", "sample_count", "Comparison sample count", comparison_count, "samples"),
        ("persistence", "persistence", "Persistence", _first(edge, "persistence_score", default=_first(finding, "persistence_score", "persistence", default=None)), None),
        ("baseline-identity", "baseline_identity", "Exact baseline identity", baseline_id, None),
        ("replay", "replay_availability", "Replay frame count", int(result.get("replay_frame_count") or len(_mapping(result.get("replay_timeline")).get("timeline") or [])), "frames"),
    ]
    evidence = [
        SupportingEvidence(
            id=f"ev-{suffix}", evidence_type=kind, label=label, summary=f"{label} recorded by the existing comparison workflow.",
            value=value, unit=unit, source_variables=variables if kind not in {"baseline_identity", "replay_availability"} else [],
            quality_status="recorded", calculation_version="existing-comparison-v1", metadata={},
        )
        for suffix, kind, label, value, unit in evidence_specs if value is not None
    ]
    timeline = []
    if first_supported:
        timeline.append(TimelineEvent(id="event-001", sequence=1, event_type="earliest_supported_deviation", occurred_at=str(first_supported), summary="Earliest supported deviation in the available comparison evidence.", variables=variables, evidence_refs=["ev-absolute-change"], confidence_level=ConfidenceLevel.unknown, is_earliest_supported=True))
    system_label = str(_first(finding, "system", default=_mapping(finding.get("localization")).get("system")) or "System")
    title = str(_first(finding, "headline", "title", default=f"Persistent relationship change in {system_label}"))
    relationship_label = f"{left} / {right}"
    direction = str(_first(edge, "direction", "change_direction", "change_type", default="weakened" if abs(comparison_strength) < abs(baseline_strength) else "strengthened"))
    persistence_value = _first(edge, "persistence_score", default=_first(finding, "persistence_score", "persistence", default=None))
    package = EvidencePackage(
        id=package_uuid, package_number=package_number, schema_version=SCHEMA_VERSION, revision=1,
        analysis_id=analysis_id, organization_id=str(result.get("organization_id") or "default"),
        portfolio_id=result.get("portfolio_id"), site_id=result.get("site_id"), system_id=result.get("system_id"),
        baseline_id=baseline_id, baseline_version=reference.get("version"), comparison_dataset_id=dataset_id,
        created_at=created, updated_at=created, first_supported_at=str(first_supported) if first_supported else None,
        last_observed_at=str(last_observed) if last_observed else None, latest_evaluated_at=created,
        title=title, system_label=system_label, condition_type=str(_first(finding, "condition_type", "type", default="persistent_relationship_change")),
        status=PackageStatus.active, severity=_first(finding, "severity", default=None), active_duration_seconds=_first(finding, "active_duration_seconds", default=None),
        persistence_summary="Persistence is recorded from the existing comparison result." if persistence_value is not None else "Persistence was not quantified by the existing comparison result.",
        change_summary=str(_first(edge, "summary", default=f"{relationship_label} {direction}.")),
        primary_relationship=PrimaryRelationship(left_variable=left, right_variable=right, relationship_label=relationship_label,
            relationship_type=str(_first(edge, "relationship_type", "type", default="correlation")), change_direction=direction,
            baseline_strength=baseline_strength, comparison_strength=comparison_strength, absolute_change=absolute_change,
            signed_change=signed_change, baseline_sample_count=baseline_count, comparison_sample_count=comparison_count,
            persistence_score=persistence_value, relationship_importance_score=_first(edge, "relationship_importance_score", "importance_score", default=None),
            relationship_importance_rationale=str(_first(edge, "relationship_importance_rationale", "importance_rationale", default="Selected by the existing comparison finding.")),
            source_model_edge_id=_first(edge, "edge_id", "id", default=None)),
        comparison_reference=ComparisonReference(reference_level=ReferenceLevel.matched_historical_baseline, reference_baseline_id=baseline_id,
            reference_baseline_version=reference.get("version"), reference_summary="Compared with the exact selected persisted Behavioral Digital Model."),
        confidence=PackageConfidence(finding_confidence=_unknown("The existing generic confidence is retained in legacy fields and is not reinterpreted."), data_quality_confidence=_unknown(), operating_state_confidence=_unknown(), mapping_confidence=_unknown(), physical_consistency_confidence=_unknown()),
        timeline=timeline, supporting_evidence=evidence, limitations=[], hypotheses=[],
        provenance=PackageProvenance(analysis_version="analysis-result-v1", algorithm_version=str(_mapping(result.get("traceability")).get("model_version") or "existing-comparison"), baseline_model_version=reference.get("version"), topology_version=None,
            source_dataset_ids=[str(result.get("baseline_dataset_id")), dataset_id], creation_reason="completed_baseline_comparison", last_update_reason="created", created_at=created, latest_evaluated_at=created, revision=1),
    )
    return package.model_dump(mode="json")


def ensure_evidence_package(result: dict[str, Any]) -> dict[str, Any] | None:
    existing = result.get("evidence_package")
    if isinstance(existing, dict):
        return EvidencePackage.model_validate(existing).model_dump(mode="json")
    package = build_evidence_package(result)
    if package is not None:
        result["evidence_package"] = package
    return package


def legacy_findings(package: dict[str, Any], original: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One-way compatibility projection; package identity and evidence remain canonical."""
    projected = [dict(item) for item in original] or [{}]
    primary = package["primary_relationship"]
    projected[0].update({
        "id": projected[0].get("id") or package["id"], "headline": projected[0].get("headline") or package["title"],
        "system": projected[0].get("system") or package["system_label"], "status": projected[0].get("status") or "open",
        "evidence_package_id": package["id"], "relationship": primary["relationship_label"],
        "change_direction": primary["change_direction"], "baseline_strength": primary["baseline_strength"],
        "comparison_strength": primary["comparison_strength"], "absolute_change": primary["absolute_change"],
    })
    return projected
