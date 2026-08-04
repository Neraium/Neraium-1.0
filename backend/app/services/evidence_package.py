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


class LifecycleStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RESOLVED = "RESOLVED"


class LifecycleEventType(str, Enum):
    package_created = "package_created"
    package_acknowledged = "package_acknowledged"
    package_resolved = "package_resolved"


class LifecycleActor(str, Enum):
    system = "system"
    user = "user"
    unknown = "unknown"


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


class TimelineEventType(str, Enum):
    comparison_started = "comparison_started"
    earliest_supported_deviation = "earliest_supported_deviation"
    behavior_persisted = "behavior_persisted"
    supporting_relationship_change = "supporting_relationship_change"
    comparison_completed = "comparison_completed"
    unknown = "unknown"


class OperatingStateType(str, Enum):
    steady = "steady"
    ramping_up = "ramping_up"
    ramping_down = "ramping_down"
    transitioning = "transitioning"
    unknown = "unknown"


class TransitionDirection(str, Enum):
    increasing = "increasing"
    decreasing = "decreasing"
    stable = "stable"
    mixed = "mixed"
    unknown = "unknown"


class ComparabilityLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class ContextSource(str, Enum):
    telemetry = "telemetry"
    analysis_metadata = "analysis_metadata"
    baseline_model = "baseline_model"
    replay = "replay"
    not_available = "not_available"


class LimitationCategory(str, Enum):
    telemetry_ambiguity = "telemetry_ambiguity"
    comparable_operating_conditions_unavailable = "comparable_operating_conditions_unavailable"
    insufficient_post_change_evidence = "insufficient_post_change_evidence"
    insufficient_instrumentation = "insufficient_instrumentation"
    multiple_plausible_explanations = "multiple_plausible_explanations"
    missing_semantic_mapping = "missing_semantic_mapping"
    missing_environmental_context = "missing_environmental_context"
    missing_operating_state_evidence = "missing_operating_state_evidence"
    missing_topology = "missing_topology"
    physics_validation_unavailable = "physics_validation_unavailable"


class LimitationSeverity(str, Enum):
    unknown = "unknown"
    low = "low"
    medium = "medium"
    high = "high"


class LimitationStatus(str, Enum):
    active = "active"
    resolved = "resolved"


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
    event_type: TimelineEventType
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
    title: str
    description: str
    reason: str
    supporting_evidence_refs: list[str]
    category: LimitationCategory
    severity: LimitationSeverity
    status: LimitationStatus


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


class LifecycleEvent(StrictModel):
    event_id: str
    timestamp: str
    actor: LifecycleActor
    event_type: LifecycleEventType
    reason: str
    metadata: dict[str, Any]


class LifecycleProvenance(StrictModel):
    schema_version: str
    source: str


class PackageLifecycle(StrictModel):
    status: LifecycleStatus
    events: list[LifecycleEvent]
    provenance: LifecycleProvenance


class ContextRange(StrictModel):
    min: float | None = None
    max: float | None = None


class ContextMetric(StrictModel):
    canonical_role: str
    unit: str | None = None
    baseline_unit: str | None = None
    comparison_unit: str | None = None
    baseline_mean: float | None = None
    comparison_mean: float | None = None
    baseline_range: ContextRange
    comparison_range: ContextRange
    baseline_source_variable: str | None = None
    comparison_source_variable: str | None = None
    baseline_source: ContextSource
    comparison_source: ContextSource


class ContextWindow(StrictModel):
    start: str | None = None
    end: str | None = None
    source: ContextSource = ContextSource.analysis_metadata


class StateConfidence(StrictModel):
    level: ConfidenceLevel = ConfidenceLevel.unknown
    score: float | None = None
    reason: str


class ComparisonState(StrictModel):
    state_label: str | None = None
    state_type: OperatingStateType
    state_confidence: StateConfidence


class TransitionContext(StrictModel):
    direction: TransitionDirection
    rate: float | None = None
    unit: str | None = None
    method: str
    reason: str


class Comparability(StrictModel):
    level: ComparabilityLevel
    score: float | None = None
    method: str
    reason: str
    matched_dimensions: list[str]
    unavailable_dimensions: list[str]


class OperatingContext(StrictModel):
    schema_version: str
    comparison_state: ComparisonState
    load_context: ContextMetric | None = None
    equipment_configuration: list[ContextMetric]
    control_context: list[ContextMetric]
    environmental_context: list[ContextMetric]
    baseline_window: ContextWindow
    comparison_window: ContextWindow
    transition_context: TransitionContext
    comparability: Comparability


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
    operating_context: OperatingContext | None = None
    confidence: PackageConfidence
    timeline: list[TimelineEvent]
    supporting_evidence: list[SupportingEvidence]
    limitations: list[EvidenceLimitation]
    hypotheses: list[Hypothesis]
    provenance: PackageProvenance
    lifecycle: PackageLifecycle | None = None


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first(value: Any, *keys: str, default: Any = None) -> Any:
    current = _mapping(value)
    for key in keys:
        candidate = current.get(key)
        if candidate is not None and candidate != "":
            return candidate
    return default


def _timestamp(value: Any) -> tuple[str, datetime] | None:
    """Return one canonical UTC timestamp, or no temporal evidence."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat(timespec="microseconds").replace(".000000+00:00", "Z").replace("+00:00", "Z"), utc


def _timeline(
    *,
    created: str,
    first_supported: Any,
    comparison_start: Any,
    comparison_end: Any,
    persistence_value: Any,
    variables: list[str],
    finding_confidence: ConfidenceDimension,
    evidence_ids: set[str],
) -> tuple[list[TimelineEvent], str | None]:
    """Order only persisted temporal facts; ordering is not a causal claim."""
    completed = _timestamp(created)
    start = _timestamp(comparison_start)
    end = _timestamp(comparison_end)
    onset = _timestamp(first_supported)
    onset_supported = onset is not None
    unknown_reason = "No persisted comparison evidence identifies when the behavioral change first became supported."
    if onset is not None and start is not None and onset[1] < start[1]:
        onset_supported = False
        unknown_reason = "The persisted onset precedes the comparison window and cannot establish earliest support within this comparison."
    if onset is not None and end is not None and onset[1] > end[1]:
        onset_supported = False
        unknown_reason = "The persisted onset follows the comparison window and cannot establish earliest support within this comparison."

    candidates: list[tuple[datetime, int, TimelineEventType, str, list[str], ConfidenceLevel, bool]] = []
    if start is not None and "ev-context-comparison-window" in evidence_ids:
        candidates.append((start[1], 0, TimelineEventType.comparison_started,
            "Persisted comparison evidence window started.", ["ev-context-comparison-window"], ConfidenceLevel.unknown, False))
    if onset_supported and onset is not None:
        refs = [ref for ref in ("ev-absolute-change", "ev-comparison-samples", "ev-persistence", "ev-context-comparison-window") if ref in evidence_ids]
        candidates.append((onset[1], 1, TimelineEventType.earliest_supported_deviation,
            "Earliest timestamp at which persisted comparison evidence supports the behavioral change; this is not a physical failure-start or causal claim.",
            refs, finding_confidence.level, True))
    else:
        # The completion timestamp records when the unknown determination was
        # evaluated. It is deliberately not substituted as the onset.
        assert completed is not None
        candidates.append((completed[1], 2, TimelineEventType.unknown,
            f"Earliest supported deviation is unknown. {unknown_reason}", [], ConfidenceLevel.unknown, False))
    if persistence_value is not None and end is not None and "ev-persistence" in evidence_ids:
        refs = [ref for ref in ("ev-persistence", "ev-context-comparison-window") if ref in evidence_ids]
        candidates.append((end[1], 3, TimelineEventType.behavior_persisted,
            "Persisted comparison output records continued relationship-change persistence through the comparison window.",
            refs, finding_confidence.level, False))
    assert completed is not None
    candidates.append((completed[1], 4, TimelineEventType.comparison_completed,
        "Persisted comparison analysis completed.",
        [ref for ref in ("ev-comparison-strength", "ev-comparison-samples", "ev-replay") if ref in evidence_ids],
        finding_confidence.level, False))

    events = []
    for sequence, (instant, _priority, event_type, summary, refs, confidence, earliest) in enumerate(
        sorted(candidates, key=lambda item: (item[0], item[1], item[2].value)), start=1
    ):
        occurred_at = instant.isoformat(timespec="microseconds").replace(".000000+00:00", "Z").replace("+00:00", "Z")
        events.append(TimelineEvent(
            id=f"event-{sequence:03d}", sequence=sequence, event_type=event_type,
            occurred_at=occurred_at, summary=summary, variables=variables,
            evidence_refs=refs, confidence_level=confidence, is_earliest_supported=earliest,
        ))
    return events, onset[0] if onset_supported and onset is not None else None


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


def _unknown(reason: str = "This confidence dimension is not calculated in Evidence Package v1.") -> ConfidenceDimension:
    return ConfidenceDimension(level=ConfidenceLevel.unknown, score=None, reason=reason, method="not_calculated", evidence_refs=[])


def _confidence_level(value: Any) -> ConfidenceLevel:
    normalized = str(value or "").strip().lower()
    aliases = {"moderate": "medium", "limited": "medium", "strong": "high", "usable": "medium", "weak": "low", "not_reliable": "low"}
    try:
        return ConfidenceLevel(aliases.get(normalized, normalized))
    except ValueError:
        return ConfidenceLevel.unknown


def _finding_confidence(edge: dict[str, Any]) -> ConfidenceDimension:
    """Preserve an existing relationship-confidence result without rescoring it."""
    score = _first(edge, "confidence_score", "relationship_confidence_score", default=None)
    level = _confidence_level(_first(edge, "confidence_level", "confidence", default=None))
    if score is None and level is ConfidenceLevel.unknown:
        return _unknown("The relationship evidence is recorded, but the comparison workflow did not provide a documented finding-confidence result.")
    refs = ["ev-baseline-strength", "ev-comparison-strength", "ev-absolute-change", "ev-baseline-samples", "ev-comparison-samples"]
    if edge.get("persistence_score") is not None:
        refs.append("ev-persistence")
    return ConfidenceDimension(
        level=level,
        score=float(score) if score is not None else None,
        reason="The level and score are preserved from the existing relationship comparison; Evidence Package does not average or recalculate them.",
        method="preserved_relationship_confidence_v1",
        evidence_refs=refs,
    )


def _data_quality_confidence(result: dict[str, Any]) -> ConfidenceDimension:
    quality = _mapping(result.get("data_quality"))
    existing = _mapping(quality.get("data_confidence"))
    rating = _first(existing, "rating", default=quality.get("reliability_rating"))
    score = quality.get("reliability_score")
    if rating is None and score is None:
        return _unknown("No persisted data-confidence or telemetry reliability assessment was available for this comparison.")
    reasons = [str(item) for item in existing.get("reasons", []) if str(item).strip()]
    reason = str(existing.get("summary") or "The existing telemetry reliability assessment is preserved without recalculation.")
    if reasons:
        reason = f"{reason} {' '.join(reasons)}"
    return ConfidenceDimension(
        level=_confidence_level(rating),
        score=float(score) if score is not None else None,
        reason=reason,
        method="preserved_data_quality_assessment_v1",
        evidence_refs=["ev-data-quality"],
    )


def _signal_catalog_entries(catalog: Any) -> list[tuple[str, dict[str, Any]]]:
    """Resolve exact source identity without display-name or label guessing."""
    raw_entries = catalog.items() if isinstance(catalog, dict) else (
        ((None, item) for item in catalog) if isinstance(catalog, list) else []
    )
    resolved = []
    for catalog_key, item in raw_entries:
        if not isinstance(item, dict):
            continue
        identity = str(item.get("source_column") or item.get("column") or catalog_key or "").strip()
        if identity:
            resolved.append((identity, item))
    return resolved


def _mapping_confidence(result: dict[str, Any], variables: list[str]) -> ConfidenceDimension:
    catalog = result.get("telemetry_signal_catalog")
    if not isinstance(catalog, (dict, list)):
        return _unknown("Canonical semantic role information was not available for the signals supporting this finding.")
    catalog_entries = _signal_catalog_entries(catalog)
    entries = [item for _, item in catalog_entries]
    by_signal = dict(catalog_entries)
    selected = [by_signal.get(variable) for variable in variables]
    roles = [str(item.get("canonical_role") or "").strip() if item else "" for item in selected]
    if any(not role for role in roles):
        return _unknown("A canonical semantic role was unavailable for one or more signals supporting this finding.")
    competing = sorted({
        role for role in roles
        if sum(1 for item in entries if str(item.get("canonical_role") or "").strip() == role) > 1
    })
    if competing:
        return ConfidenceDimension(
            level=ConfidenceLevel.low, score=None,
            reason=f"Multiple telemetry signals compete for the canonical role(s): {', '.join(competing)}.",
            method="canonical_role_uniqueness_v1", evidence_refs=[],
        )
    return ConfidenceDimension(
        level=ConfidenceLevel.medium, score=None,
        reason="Each signal supporting the relationship has an available, unambiguous canonical semantic role, but its physical correctness has not been independently validated.",
        method="canonical_role_uniqueness_v1", evidence_refs=[],
    )


def _context_metric(role: str, inputs: dict[str, Any]) -> ContextMetric | None:
    baseline = _mapping(_mapping(inputs.get("baseline")).get(role))
    comparison = _mapping(_mapping(inputs.get("comparison")).get(role))
    if not baseline or not comparison:
        return None
    baseline_unit = _normalized_unit(baseline.get("unit"))
    comparison_unit = _normalized_unit(comparison.get("unit"))
    compatible_unit = baseline_unit if _units_compatible(role, baseline_unit, comparison_unit) else None
    return ContextMetric(
        canonical_role=role,
        unit=compatible_unit,
        baseline_unit=baseline_unit,
        comparison_unit=comparison_unit,
        baseline_mean=baseline.get("mean"), comparison_mean=comparison.get("mean"),
        baseline_range=ContextRange(min=baseline.get("min"), max=baseline.get("max")),
        comparison_range=ContextRange(min=comparison.get("min"), max=comparison.get("max")),
        baseline_source_variable=baseline.get("source_variable"),
        comparison_source_variable=comparison.get("source_variable"),
        baseline_source=ContextSource(str(baseline.get("source") or "baseline_model")),
        comparison_source=ContextSource(str(comparison.get("source") or "telemetry")),
    )


DIMENSIONLESS_CONTEXT_ROLES = {"equipment_enable", "equipment_state"}


def _normalized_unit(value: Any) -> str | None:
    unit = str(value or "").strip()
    return unit or None


def _units_compatible(role: str, baseline_unit: str | None, comparison_unit: str | None) -> bool:
    if baseline_unit is None or comparison_unit is None:
        return role in DIMENSIONLESS_CONTEXT_ROLES and baseline_unit is None and comparison_unit is None
    return baseline_unit.casefold() == comparison_unit.casefold()


def _range_overlap(metric: ContextMetric) -> float | None:
    if not _units_compatible(metric.canonical_role, metric.baseline_unit, metric.comparison_unit):
        return None
    left_min, left_max = metric.baseline_range.min, metric.baseline_range.max
    right_min, right_max = metric.comparison_range.min, metric.comparison_range.max
    if None in {left_min, left_max, right_min, right_max}:
        return None
    intersection = max(0.0, min(float(left_max), float(right_max)) - max(float(left_min), float(right_min)))
    smaller_span = min(float(left_max) - float(left_min), float(right_max) - float(right_min))
    if smaller_span <= 0:
        return 1.0 if left_min == right_min == left_max == right_max else 0.0
    return round(intersection / smaller_span, 6)


def _comparability(load: ContextMetric | None, controls: list[ContextMetric]) -> Comparability:
    if load is None or (load_overlap := _range_overlap(load)) is None:
        return Comparability(level=ComparabilityLevel.unknown, score=None, method="not_calculated",
            reason="A canonical process-demand range was not available for both periods.", matched_dimensions=[],
            unavailable_dimensions=["process_demand", "equipment_configuration", "operating_mode", "environmental_conditions"])
    checks = [("process_demand", load_overlap)]
    unavailable_controls = []
    for item in controls:
        overlap = _range_overlap(item)
        if overlap is None:
            unavailable_controls.append(item.canonical_role)
        else:
            checks.append((item.canonical_role, overlap))
    score = round(sum(value for _, value in checks) / len(checks), 6)
    level = ComparabilityLevel.high if all(value >= 0.8 for _, value in checks) else ComparabilityLevel.medium if load_overlap > 0 else ComparabilityLevel.low
    return Comparability(
        level=level, score=score, method="minimum_span_range_overlap_v1",
        reason="Each overlap is intersection width divided by the smaller observed range; high requires every available dimension to be at least 0.8, medium requires process-demand overlap, and low means no process-demand overlap.",
        matched_dimensions=[name for name, value in checks if value > 0],
        unavailable_dimensions=[*unavailable_controls, "equipment_configuration", "operating_mode", "environmental_conditions"],
    )


def _transition(inputs: dict[str, Any]) -> tuple[TransitionContext, OperatingStateType]:
    demand = _mapping(_mapping(inputs.get("comparison")).get("process_demand"))
    early, late = demand.get("early_median"), demand.get("late_median")
    minimum, maximum = demand.get("min"), demand.get("max")
    if None in {early, late, minimum, maximum}:
        return TransitionContext(direction=TransitionDirection.unknown, method="not_calculated", reason="A complete canonical process-demand summary was unavailable."), OperatingStateType.unknown
    delta = float(late) - float(early)
    threshold = max((float(maximum) - float(minimum)) * 0.05, abs(float(early)) * 0.02)
    segments = [float(value) for value in demand.get("segment_medians", []) if value is not None]
    material_signs = {
        1 if right - left > threshold else -1
        for left, right in zip(segments, segments[1:])
        if abs(right - left) > threshold
    }
    if len(material_signs) > 1:
        return TransitionContext(direction=TransitionDirection.mixed, method="early_late_decile_median_v1", reason="Five ordered segment medians contained material changes in both directions, so no single directional trend is claimed."), OperatingStateType.transitioning
    if abs(delta) <= threshold:
        return TransitionContext(direction=TransitionDirection.stable, method="early_late_decile_median_v1", reason="Early and late 10% medians differed by no more than the deterministic 5%-of-range or 2%-of-early-median threshold."), OperatingStateType.steady
    direction = TransitionDirection.increasing if delta > 0 else TransitionDirection.decreasing
    state = OperatingStateType.ramping_up if delta > 0 else OperatingStateType.ramping_down
    return TransitionContext(direction=direction, method="early_late_decile_median_v1", reason="Direction compares the median of the first and last 10% of canonical process-demand samples using the documented material-change threshold."), state


def _operating_context(result: dict[str, Any]) -> OperatingContext | None:
    inputs = _mapping(result.get("operating_context_inputs"))
    if inputs.get("schema_version") != "operating-context-input-v1":
        return None
    load = _context_metric("process_demand", inputs)
    controls = [item for role in ("control_command", "setpoint") if (item := _context_metric(role, inputs))]
    equipment = [item for role in ("equipment_enable", "equipment_state") if (item := _context_metric(role, inputs))]
    environment = [item for role in ("environmental_temperature",) if (item := _context_metric(role, inputs))]
    transition, state_type = _transition(inputs)
    windows = _mapping(inputs.get("windows"))
    return OperatingContext(
        schema_version="operating-context-v1",
        comparison_state=ComparisonState(state_label=None, state_type=state_type,
            state_confidence=StateConfidence(reason="The transition descriptor is deterministic, but no operating-state matching model or confidence score is calculated.")),
        load_context=load, equipment_configuration=equipment, control_context=controls,
        environmental_context=environment,
        baseline_window=ContextWindow(**_mapping(windows.get("baseline"))),
        comparison_window=ContextWindow(**_mapping(windows.get("comparison"))),
        transition_context=transition, comparability=_comparability(load, controls),
    )


def _limitations(
    result: dict[str, Any],
    finding: dict[str, Any],
    operating_context: OperatingContext | None,
    evidence: list[SupportingEvidence],
    variables: list[str],
) -> list[EvidenceLimitation]:
    """Describe only boundaries explicitly demonstrated by persisted outputs."""
    limitations: list[EvidenceLimitation] = []

    def record_evidence(evidence_id: str, label: str, value: Any, source_variables: list[str] | None = None) -> None:
        evidence.append(SupportingEvidence(
            id=evidence_id,
            evidence_type="limitation_support",
            label=label,
            summary=f"{label} preserved from the completed comparison result.",
            value=value,
            source_variables=source_variables or [],
            quality_status="recorded",
            calculation_version="evidence-limitations-v1",
            metadata={},
        ))

    def add(
        *, identifier: str, title: str, description: str, reason: str,
        evidence_ref: str, category: LimitationCategory,
        severity: LimitationSeverity = LimitationSeverity.unknown,
    ) -> None:
        limitations.append(EvidenceLimitation(
            id=identifier, title=title, description=description, reason=reason,
            supporting_evidence_refs=[evidence_ref], category=category,
            severity=severity, status=LimitationStatus.active,
        ))

    # Key presence matters: an absent legacy field is unknown, whereas a
    # persisted null explicitly records that the workflow had no context output.
    if "operating_context_inputs" in result and result.get("operating_context_inputs") is None:
        evidence_ref = "ev-operating-context-availability"
        record_evidence(evidence_ref, "Operating context availability", {"status": "not_available"})
        add(
            identifier="lim-missing-operating-context", title="Operating context unavailable",
            description="The available evidence cannot establish whether the baseline and comparison represent comparable operating states.",
            reason="The completed comparison explicitly records no operating-context input.",
            evidence_ref=evidence_ref, category=LimitationCategory.missing_operating_state_evidence,
        )
    elif operating_context is not None and operating_context.comparability.level is ComparabilityLevel.unknown:
        add(
            identifier="lim-comparable-conditions-unavailable", title="Comparable operating conditions unavailable",
            description="The available evidence cannot establish that the relationship was compared under comparable process demand.",
            reason=operating_context.comparability.reason,
            evidence_ref="ev-context-comparability",
            category=LimitationCategory.comparable_operating_conditions_unavailable,
        )

    if "telemetry_signal_catalog" in result:
        catalog = result.get("telemetry_signal_catalog")
        mapped = {
            identity for identity, item in _signal_catalog_entries(catalog)
            if str(item.get("canonical_role") or "").strip()
        }
        missing = [variable for variable in variables if variable not in mapped]
        if missing:
            evidence_ref = "ev-semantic-mapping-availability"
            record_evidence(evidence_ref, "Semantic mapping availability", {"unmapped_variables": missing}, variables)
            add(
                identifier="lim-missing-semantic-mapping", title="Semantic mapping unavailable",
                description="The available evidence cannot interpret every supporting signal through a canonical semantic role.",
                reason=f"The persisted signal catalog has no canonical role for: {', '.join(missing)}.",
                evidence_ref=evidence_ref, category=LimitationCategory.missing_semantic_mapping,
            )

    ambiguity = result.get("telemetry_ambiguity") if "telemetry_ambiguity" in result else None
    if ambiguity:
        evidence_ref = "ev-telemetry-ambiguity"
        record_evidence(evidence_ref, "Telemetry ambiguity", ambiguity, variables)
        add(
            identifier="lim-telemetry-ambiguity", title="Telemetry ambiguity",
            description="The available telemetry cannot uniquely distinguish the recorded alternatives.",
            reason="The completed comparison explicitly records telemetry ambiguity.",
            evidence_ref=evidence_ref, category=LimitationCategory.telemetry_ambiguity,
        )

    alternatives = _first(
        finding, "alternative_explanations", "possible_explanations", default=[]
    )
    if isinstance(alternatives, list):
        normalized = [item for item in alternatives if isinstance(item, (str, dict)) and item]
        if len(normalized) > 1:
            evidence_ref = "ev-supported-alternatives"
            record_evidence(evidence_ref, "Persisted alternative explanations", normalized, variables)
            add(
                identifier="lim-multiple-plausible-explanations", title="Multiple explanations remain plausible",
                description="The available evidence supports more than one explanation and cannot select among them.",
                reason=f"The completed finding retains {len(normalized)} alternative explanations.",
                evidence_ref=evidence_ref, category=LimitationCategory.multiple_plausible_explanations,
            )

    if "physics_reasoning" in result:
        physics = _mapping(result.get("physics_reasoning"))
        status = str(physics.get("status") or "").strip().lower()
        if status in {"unavailable", "not_available", "not_implemented"}:
            evidence_ref = "ev-physics-availability"
            record_evidence(evidence_ref, "Physics validation availability", {
                key: physics.get(key) for key in ("status", "reason") if physics.get(key) is not None
            })
            add(
                identifier="lim-physics-validation-unavailable", title="Physics validation unavailable",
                description="The relationship change has not been checked against an applicable physics validation result.",
                reason=str(physics.get("reason") or "The completed comparison records physics validation as unavailable."),
                evidence_ref=evidence_ref, category=LimitationCategory.physics_validation_unavailable,
            )

    return limitations


def build_evidence_package(result: dict[str, Any]) -> dict[str, Any] | None:
    """Formalize one existing comparison finding without adding analytical claims."""
    analysis_id = str(result.get("comparison_analysis_id") or result.get("analysis_run_id") or "").strip()
    baseline_id = str(result.get("baseline_id") or _mapping(result.get("active_baseline_reference")).get("model_id") or "").strip()
    dataset_id = str(result.get("comparison_dataset_id") or result.get("dataset_id") or "").strip()
    reference = _mapping(result.get("active_baseline_reference"))
    baseline_analysis = _mapping(result.get("baseline_analysis"))
    persisted_model_id = str(baseline_analysis.get("baseline_model_id") or "").strip()
    selected_model_id = str(reference.get("model_id") or "").strip()
    scope = _mapping(result.get("dataset_scope"))
    organization_id = str(scope.get("tenant_id") or "").strip()
    recorded_organization_id = str(result.get("organization_id") or "").strip()
    created = str(result.get("completed_at") or result.get("last_processed_at") or "").strip()
    edge = _relationship(result)
    if (
        not analysis_id
        or not baseline_id
        or not dataset_id
        or edge is None
        or not created
        or _timestamp(created) is None
        or not organization_id
        or (recorded_organization_id and recorded_organization_id != organization_id)
        or not selected_model_id
        or selected_model_id != baseline_id
        or persisted_model_id != selected_model_id
    ):
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
    first_supported = _first(finding, "first_detected_at", "first_supported_at", "change_onset") or result.get("change_onset")
    last_observed = _first(finding, "last_observed_at", "updated_at") or result.get("last_processed_at") or created
    package_uuid = str(uuid5(PACKAGE_NAMESPACE, f"{organization_id}:{analysis_id}:{baseline_id}:{dataset_id}"))
    package_number = f"EP-{analysis_id[:8].upper()}-{package_uuid[:4].upper()}"
    created_timestamp = _timestamp(created)[0]
    created_event = LifecycleEvent(
        event_id=str(uuid5(PACKAGE_NAMESPACE, f"{package_uuid}:package_created:{created_timestamp}")),
        timestamp=created_timestamp,
        actor=LifecycleActor.system,
        event_type=LifecycleEventType.package_created,
        reason="Evidence Package created from the completed baseline comparison.",
        metadata={},
    )
    variables = [left, right]
    operating_context = _operating_context(result)
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
    data_quality = _mapping(result.get("data_quality"))
    if data_quality.get("data_confidence") or data_quality.get("reliability_rating") is not None or data_quality.get("reliability_score") is not None:
        evidence.append(SupportingEvidence(
            id="ev-data-quality", evidence_type="data_quality", label="Telemetry data quality",
            summary="Existing data-quality assessment for the comparison telemetry.",
            value={key: data_quality.get(key) for key in ("readiness", "reliability_rating", "reliability_score", "data_confidence") if data_quality.get(key) is not None},
            source_variables=variables, quality_status="recorded", calculation_version="existing-data-quality-v1", metadata={},
        ))
    if operating_context is not None:
        context_specs: list[tuple[str, str, str, Any, str | None, list[str], dict[str, Any]]] = []
        if operating_context.load_context is not None:
            load = operating_context.load_context
            context_specs.extend([
                ("context-baseline-demand-range", "operating_context", "Baseline process-demand range", load.baseline_range.model_dump(), load.unit, [load.baseline_source_variable] if load.baseline_source_variable else [], {"canonical_role": load.canonical_role, "method": "persisted_full_window_summary_v1"}),
                ("context-comparison-demand-range", "operating_context", "Comparison process-demand range", load.comparison_range.model_dump(), load.unit, [load.comparison_source_variable] if load.comparison_source_variable else [], {"canonical_role": load.canonical_role, "method": "persisted_full_window_summary_v1"}),
            ])
        for index, metric in enumerate(operating_context.control_context, start=1):
            context_specs.append((f"context-control-{index:02d}", "operating_context", f"{metric.canonical_role.replace('_', ' ').title()} means", {"baseline": metric.baseline_mean, "comparison": metric.comparison_mean}, metric.unit, [value for value in (metric.baseline_source_variable, metric.comparison_source_variable) if value], {"canonical_role": metric.canonical_role, "method": "arithmetic_mean_v1"}))
        context_specs.extend([
            ("context-baseline-window", "operating_context_window", "Baseline context window", operating_context.baseline_window.model_dump(), None, [], {"method": "persisted_analysis_metadata_v1"}),
            ("context-comparison-window", "operating_context_window", "Comparison context window", operating_context.comparison_window.model_dump(), None, [], {"method": "persisted_analysis_metadata_v1"}),
            ("context-comparability", "operating_context_comparability", "Operating-context comparability", {"level": operating_context.comparability.level.value, "score": operating_context.comparability.score}, None, [], {"method": operating_context.comparability.method}),
        ])
        evidence.extend(SupportingEvidence(
            id=f"ev-{suffix}", evidence_type=kind, label=label, summary=f"{label} preserved from canonical operating-context inputs.",
            value=value, unit=unit, source_variables=source_variables, quality_status="recorded",
            calculation_version="operating-context-v1", metadata=metadata,
        ) for suffix, kind, label, value, unit, source_variables, metadata in context_specs)
    limitations = _limitations(result, finding, operating_context, evidence, variables)
    system_label = str(_first(finding, "system", default=_mapping(finding.get("localization")).get("system")) or "System")
    title = str(_first(finding, "headline", "title", default=f"Persistent relationship change in {system_label}"))
    relationship_label = f"{left} / {right}"
    direction = str(_first(edge, "direction", "change_direction", "change_type", default="weakened" if abs(comparison_strength) < abs(baseline_strength) else "strengthened"))
    persistence_value = _first(edge, "persistence_score", default=_first(finding, "persistence_score", "persistence", default=None))
    finding_confidence = _finding_confidence(edge)
    comparison_window = operating_context.comparison_window if operating_context is not None else ContextWindow()
    timeline, canonical_first_supported = _timeline(
        created=created, first_supported=first_supported,
        comparison_start=comparison_window.start, comparison_end=comparison_window.end,
        persistence_value=persistence_value, variables=variables,
        finding_confidence=finding_confidence, evidence_ids={item.id for item in evidence},
    )
    package = EvidencePackage(
        id=package_uuid, package_number=package_number, schema_version=SCHEMA_VERSION, revision=1,
        analysis_id=analysis_id, organization_id=organization_id,
        portfolio_id=result.get("portfolio_id"), site_id=result.get("site_id"), system_id=result.get("system_id"),
        baseline_id=baseline_id, baseline_version=reference.get("version"), comparison_dataset_id=dataset_id,
        created_at=created, updated_at=created, first_supported_at=canonical_first_supported,
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
        operating_context=operating_context,
        confidence=PackageConfidence(
            finding_confidence=finding_confidence,
            data_quality_confidence=_data_quality_confidence(result),
            operating_state_confidence=_unknown("Operating Context v1 comparability is available, but no operating-state matching model or state-confidence calculation exists.") if operating_context is not None else _unknown("Operating Context v1 evidence was not available for this comparison."),
            mapping_confidence=_mapping_confidence(result, variables),
            physical_consistency_confidence=_unknown("Physics consistency engine not implemented."),
        ),
        timeline=timeline, supporting_evidence=evidence, limitations=limitations, hypotheses=[],
        provenance=PackageProvenance(analysis_version="analysis-result-v1", algorithm_version=str(_mapping(result.get("traceability")).get("model_version") or "existing-comparison"), baseline_model_version=reference.get("version"), topology_version=None,
            source_dataset_ids=[str(result.get("baseline_dataset_id")), dataset_id], creation_reason="completed_baseline_comparison", last_update_reason="created", created_at=created, latest_evaluated_at=created, revision=1),
        lifecycle=PackageLifecycle(
            status=LifecycleStatus.OPEN,
            events=[created_event],
            provenance=LifecycleProvenance(schema_version="evidence-package-lifecycle-v1", source="lifecycle_event_store"),
        ),
    )
    return package.model_dump(mode="json")


def ensure_evidence_package(result: dict[str, Any]) -> dict[str, Any] | None:
    existing = result.get("evidence_package")
    if isinstance(existing, dict):
        # A stored package is readable only while its owning analysis still
        # proves the exact-baseline invariant required by this schema.
        if build_evidence_package({key: value for key, value in result.items() if key != "evidence_package"}) is None:
            return None
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
