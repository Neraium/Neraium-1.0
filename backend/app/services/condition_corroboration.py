from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.change_trajectory import build_change_trajectory
from app.services.finding_classification import (
    INSUFFICIENT_EVIDENCE,
    KNOWN_OPERATIONAL_CHANGE,
    UNEXPLAINED_SYSTEMIC_CHANGE,
    classify_finding,
)
from app.services.historical_comparables import ComparableHistoricalEpisodeService


CORROBORATION_STRENGTHS = ("isolated", "limited", "moderate", "strong", "systemic")
GENERIC_SYSTEMS = {
    "",
    "uploaded telemetry",
    "observed subsystem behavior changed",
    "mapped system",
    "unknown",
}


@dataclass(frozen=True)
class ConditionCorroboration:
    condition_id: str
    corroboration_strength: str
    relationship_count: int
    affected_signals: list[str]
    affected_systems: list[str]
    supporting_relationships: list[dict[str, Any]]
    conflicting_relationships: list[dict[str, Any]]
    uncertain_relationships: list[dict[str, Any]]
    independent_relationships: list[dict[str, Any]]
    evidence_summary: str
    confidence: str
    confidence_score: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Condition:
    condition_id: str
    headline: str
    classification: dict[str, Any]
    trajectory: dict[str, Any]
    corroboration: dict[str, Any]
    confidence: str
    confidence_score: float
    affected_systems: list[str]
    affected_boundaries: list[str]
    affected_signals: list[str]
    localization: dict[str, Any]
    evidence: list[dict[str, Any]]
    evidence_summary: str
    comparable_operation: dict[str, Any]
    timeline: list[dict[str, Any]]
    next_checks: list[str]
    escalation: dict[str, Any]
    status: str = "open"
    object_type: str = "condition"
    schema_version: str = "condition-v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ConditionCorroborationService:
    """Synthesize relationship evidence into conservative condition objects."""

    def __init__(
        self,
        comparable_service: ComparableHistoricalEpisodeService | None = None,
    ) -> None:
        self.comparable_service = comparable_service or ComparableHistoricalEpisodeService()

    def corroborate(
        self,
        relationships: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized = [
            _normalize_relationship(item, index)
            for index, item in enumerate(relationships or [])
            if isinstance(item, dict) and _is_changed_relationship(item)
        ]
        if not normalized:
            return []

        groups = _coherent_groups(normalized)
        results: list[dict[str, Any]] = []
        for group in groups:
            support = [normalized[index] for index in group]
            conflicts = [
                relationship
                for relationship in normalized
                if relationship not in support
                and any(_related(candidate, relationship) for candidate in support)
                and _orientation(relationship) != _orientation(support[0])
            ]
            uncertain = [
                relationship
                for relationship in normalized
                if relationship not in support
                and relationship not in conflicts
                and any(_related(candidate, relationship) for candidate in support)
            ]
            independent = [
                relationship
                for relationship in normalized
                if relationship not in support
                and relationship not in conflicts
                and relationship not in uncertain
                and not any(_related(candidate, relationship) for candidate in support)
            ]
            results.append(
                _corroboration_result(support, conflicts, uncertain, independent).to_dict()
            )
        return results

    def corroborate_relationship(
        self,
        relationship: dict[str, Any],
        nearby_relationships: list[dict[str, Any]],
    ) -> dict[str, Any]:
        candidates = [relationship, *nearby_relationships]
        target_id = _relationship_id(_normalize_relationship(relationship, 0))
        for result in self.corroborate(candidates):
            ids = {
                str(item.get("relationship_id") or item.get("id") or "")
                for item in result["supporting_relationships"]
            }
            if target_id in ids:
                return result
        normalized = _normalize_relationship(relationship, 0)
        return _corroboration_result([normalized], [], [], []).to_dict()

    def build_conditions(
        self,
        *,
        relationships: list[dict[str, Any]],
        findings: list[dict[str, Any]] | None = None,
        rows: list[dict[str, Any]] | None = None,
        timestamp_column: str | None = None,
        baseline_analysis: dict[str, Any] | None = None,
        data_quality: dict[str, Any] | None = None,
        operating_mode: dict[str, Any] | None = None,
        telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
        site_name: str | None = None,
        generated_at: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized = [
            _normalize_relationship(item, index)
            for index, item in enumerate(relationships or [])
            if isinstance(item, dict) and _is_changed_relationship(item)
        ]
        if not normalized:
            return []

        findings = [item for item in (findings or []) if isinstance(item, dict)]
        data_quality = data_quality or {}
        operating_mode = operating_mode or data_quality.get("operating_mode") or {}
        baseline_analysis = baseline_analysis or {}
        conditions: list[dict[str, Any]] = []

        for group in _coherent_groups(normalized):
            support = [normalized[index] for index in group]
            conflicts = [
                relationship
                for relationship in normalized
                if relationship not in support
                and any(_related(candidate, relationship) for candidate in support)
                and _orientation(relationship) != _orientation(support[0])
            ]
            uncertain = [
                relationship
                for relationship in normalized
                if relationship not in support
                and relationship not in conflicts
                and any(_related(candidate, relationship) for candidate in support)
            ]
            independent = [
                relationship
                for relationship in normalized
                if relationship not in support
                and relationship not in conflicts
                and relationship not in uncertain
                and not any(_related(candidate, relationship) for candidate in support)
            ]
            corroboration = _corroboration_result(
                support,
                conflicts,
                uncertain,
                independent,
            )
            primary = max(support, key=_relationship_rank)
            related_finding = _matching_finding(findings, support)
            classification = _condition_classification(
                related_finding=related_finding,
                support=support,
                data_quality=data_quality,
                operating_mode=operating_mode,
                baseline_analysis=baseline_analysis,
            )
            trajectory = build_change_trajectory(
                support,
                rows=rows,
                timestamp_column=timestamp_column,
                baseline_trajectory=baseline_analysis.get("drift_trajectory"),
            )
            trajectory["operational_explanation"] = (
                "No known operational explanation"
                if classification.get("type") == UNEXPLAINED_SYSTEMIC_CHANGE
                and str(operating_mode.get("match") or "").lower() == "strong"
                else "Aligned with a known operating-context change"
                if classification.get("type") == KNOWN_OPERATIONAL_CHANGE
                else "Operational explanation not established"
            )
            comparable = self.comparable_service.retrieve(
                rows=rows or [],
                relationship=primary,
                timestamp_column=timestamp_column,
                telemetry_signal_catalog=telemetry_signal_catalog,
            )
            localization = localize_condition(
                support,
                site_name=site_name,
            )
            confidence_score = _condition_confidence(
                support=support,
                conflicts=conflicts,
                data_quality=data_quality,
                comparable=comparable,
            )
            confidence = _confidence_label(confidence_score)
            condition_id = corroboration.condition_id
            evidence = _condition_evidence(
                support=support,
                conflicts=conflicts,
                corroboration=corroboration,
                trajectory=trajectory,
                comparable=comparable,
            )
            next_checks = _next_checks(localization, support)
            escalation = evaluate_condition_escalation(
                classification=classification,
                confidence=confidence,
                trajectory=trajectory,
                corroboration=corroboration.to_dict(),
                operating_mode=operating_mode,
                data_quality=data_quality,
                criticality=_condition_criticality(support, related_finding),
            )
            timeline = _condition_timeline(
                support=support,
                trajectory=trajectory,
                corroboration=corroboration,
                generated_at=generated_at,
            )
            condition = Condition(
                condition_id=condition_id,
                headline=_condition_headline(support, localization),
                classification=classification,
                trajectory=trajectory,
                corroboration=corroboration.to_dict(),
                confidence=confidence,
                confidence_score=round(confidence_score, 4),
                affected_systems=corroboration.affected_systems,
                affected_boundaries=localization["affected_boundaries"],
                affected_signals=corroboration.affected_signals,
                localization=localization,
                evidence=evidence,
                evidence_summary=corroboration.evidence_summary,
                comparable_operation=comparable,
                timeline=timeline,
                next_checks=next_checks,
                escalation=escalation,
            ).to_dict()
            # Flat aliases make the canonical object easy to consume while the
            # nested corroboration record preserves its complete evidence.
            condition.update(
                {
                    "id": condition_id,
                    "title": condition["headline"],
                    "corroboration_strength": corroboration.corroboration_strength,
                    "relationship_count": corroboration.relationship_count,
                    "supporting_relationships": corroboration.supporting_relationships,
                    "conflicting_relationships": corroboration.conflicting_relationships,
                    "uncertain_relationships": corroboration.uncertain_relationships,
                    "independent_relationships": corroboration.independent_relationships,
                    "coherence": {
                        "temporal_alignment": "supported" if corroboration.relationship_count > 1 else "not corroborated",
                        "shared_signals": localization.get("shared_signals", []),
                        "system_alignment": (
                            "same monitored system"
                            if len(corroboration.affected_systems) == 1
                            else "multiple monitored systems"
                            if len(corroboration.affected_systems) > 1
                            else "system mapping unavailable"
                        ),
                        "change_direction": _orientation(primary),
                        "joint_evolution": trajectory.get("state"),
                        "conflict_count": len(corroboration.conflicting_relationships),
                        "uncertain_count": len(corroboration.uncertain_relationships),
                        "independent_count": len(corroboration.independent_relationships),
                    },
                    "recommended_check": next_checks[0] if next_checks else "",
                    "recommended_investigation": next_checks,
                    "activity_timeline": timeline,
                    "supporting_evidence": [item["summary"] for item in evidence],
                    "what_changed": evidence[0]["summary"] if evidence else corroboration.evidence_summary,
                    "why_it_matters": _condition_importance(corroboration, trajectory),
                    "operating_mode": operating_mode,
                    "data_confidence": data_quality.get("data_confidence") or {},
                    "persistence": {
                        "persistent": float(trajectory.get("persistence") or 0.0) >= 0.6,
                        "summary": trajectory.get("observed_for"),
                    },
                    "source_tags": corroboration.affected_signals,
                }
            )
            conditions.append(condition)

        return sorted(
            conditions,
            key=lambda item: (
                _strength_rank(item.get("corroboration_strength")),
                float(item.get("confidence_score") or 0.0),
                int(item.get("relationship_count") or 0),
            ),
            reverse=True,
        )

    analyze = build_conditions


def localize_condition(
    relationships: list[dict[str, Any]],
    *,
    site_name: str | None = None,
) -> dict[str, Any]:
    normalized = [
        _normalize_relationship(item, index)
        for index, item in enumerate(relationships or [])
        if isinstance(item, dict)
    ]
    signals = _dedupe([signal for item in normalized for signal in item["columns"]])
    explicit_systems = _dedupe(
        [
            item["system"]
            for item in normalized
            if item["system"].lower() not in GENERIC_SYSTEMS
        ]
    )
    system = explicit_systems[0] if len(explicit_systems) == 1 else ""
    boundaries = _supported_boundaries(signals)
    boundary = boundaries[0] if len(boundaries) == 1 else ""
    shared_signals = _shared_signals(normalized)
    subsystem = boundary if boundary and system and boundary.lower() not in system.lower() else ""
    likely_area = boundary or system or "Monitored signal boundary"
    site = str(site_name or "").strip()
    hierarchy = [
        {"level": "site", "label": site, "supported": bool(site), "basis": "assigned site metadata" if site else "not available"},
        {"level": "system", "label": system, "supported": bool(system), "basis": "relationship system mapping" if system else "not narrowed"},
        {"level": "subsystem", "label": subsystem, "supported": bool(subsystem), "basis": "signal-name boundary evidence" if subsystem else "not narrowed"},
        {"level": "monitored_boundary", "label": boundary, "supported": bool(boundary), "basis": "observed signal identifiers" if boundary else "not narrowed"},
        {"level": "signals", "label": ", ".join(signals), "supported": bool(signals), "basis": "source telemetry"},
        {"level": "likely_investigation_area", "label": likely_area, "supported": bool(likely_area), "basis": "deepest telemetry-supported area"},
    ]
    return {
        "site": site,
        "system": system,
        "subsystem": subsystem,
        "monitored_boundary": boundary,
        "signals_involved": signals,
        "shared_signals": shared_signals,
        "likely_investigation_area": likely_area,
        "affected_boundaries": boundaries,
        "hierarchy": hierarchy,
        "precision": (
            "monitored_boundary"
            if boundary
            else "system"
            if system
            else "signals"
        ),
        "precision_limit": (
            "Localization stops at the deepest boundary supported by telemetry; no exact pipe, valve, or equipment location is inferred."
        ),
    }


def evaluate_condition_escalation(
    *,
    classification: dict[str, Any] | str,
    confidence: str,
    trajectory: dict[str, Any] | str,
    corroboration: dict[str, Any],
    operating_mode: dict[str, Any] | None,
    data_quality: dict[str, Any] | None,
    criticality: str | None,
) -> dict[str, Any]:
    classification_type = (
        str(classification.get("type") or "")
        if isinstance(classification, dict)
        else str(classification or "")
    )
    trajectory_state = (
        str(trajectory.get("state") or "")
        if isinstance(trajectory, dict)
        else str(trajectory or "")
    )
    relationship_count = int(corroboration.get("relationship_count") or 0)
    strength = str(corroboration.get("corroboration_strength") or "isolated").lower()
    mode_match = str((operating_mode or {}).get("match") or "unavailable").lower()
    quality = _data_quality_rating(data_quality or {})
    critical = str(criticality or "unknown").lower()
    reasons: list[str] = []
    blocked_by: list[str] = []

    if relationship_count < 2:
        blocked_by.append("Fewer than two telemetry-supported relationships corroborate the condition.")
    if strength in {"isolated", "limited"}:
        blocked_by.append(f"Corroboration is {strength}.")
    if str(confidence).lower() not in {"high", "moderate"}:
        blocked_by.append("Condition confidence is below moderate.")
    if quality == "low":
        blocked_by.append("Data quality is low.")
    if classification_type == INSUFFICIENT_EVIDENCE:
        blocked_by.append("The condition is classified as insufficient evidence.")

    prompt_ready = (
        not blocked_by
        and classification_type == UNEXPLAINED_SYSTEMIC_CHANGE
        and strength in {"strong", "systemic"}
        and trajectory_state in {"Strengthening", "Sudden", "Recurring"}
        and mode_match == "strong"
        and quality == "high"
        and critical in {"high", "critical"}
    )
    if prompt_ready:
        level = "prompt_engineering_review"
        reasons.extend(
            [
                f"{relationship_count} related relationships provide {strength} corroboration.",
                f"The condition trajectory is {trajectory_state.lower()}.",
                "Operating-mode and data-quality evidence support like-for-like comparison.",
                "The monitored area is marked high criticality.",
            ]
        )
    elif not blocked_by and relationship_count >= 2 and strength in {"moderate", "strong", "systemic"}:
        level = "review"
        reasons.extend(
            [
                f"{relationship_count} related relationships corroborate the condition.",
                f"The trajectory is {trajectory_state.lower() or 'available for review'}.",
                f"Data quality is {quality}.",
            ]
        )
        if mode_match != "strong":
            reasons.append("Operating-mode support is not strong enough for prompt escalation.")
        if critical not in {"high", "critical"}:
            reasons.append("High criticality is not established.")
    else:
        level = "hold"
        reasons.append("Continue evidence collection; escalation gates are not met.")

    return {
        "level": level,
        "eligible": level in {"review", "prompt_engineering_review"},
        "prompt_engineering_review": level == "prompt_engineering_review",
        "reasons": reasons,
        "blocked_by": _dedupe(blocked_by),
        "inputs": {
            "classification": classification_type or "unavailable",
            "confidence": str(confidence).lower(),
            "trajectory": trajectory_state or "unavailable",
            "corroboration": strength,
            "relationship_count": relationship_count,
            "operating_mode_match": mode_match,
            "data_quality": quality,
            "criticality": critical,
        },
        "human_review_required": True,
        "rule_version": "deterministic_condition_escalation_v1",
    }


def _normalize_relationship(item: dict[str, Any], index: int) -> dict[str, Any]:
    columns = _relationship_columns(item)
    localization = item.get("localization") if isinstance(item.get("localization"), dict) else {}
    normalized = dict(item)
    normalized.update(
        {
            "id": str(item.get("id") or item.get("relationship_id") or f"relationship-{index}"),
            "columns": columns,
            "system": str(
                item.get("system")
                or item.get("affected_system")
                or item.get("subsystem")
                or ""
            ).strip(),
            "boundary": str(
                item.get("monitored_boundary")
                or localization.get("monitored_boundary")
                or ""
            ).strip(),
            "confidence_score": _score(
                item.get("confidence_score"),
                item.get("confidence"),
            ),
            "change_type": str(item.get("change_type") or item.get("state") or "changed").lower(),
            "evidence_refs": _list(item.get("evidence_refs")),
        }
    )
    return normalized


def _coherent_groups(relationships: list[dict[str, Any]]) -> list[list[int]]:
    remaining = set(range(len(relationships)))
    groups: list[list[int]] = []
    while remaining:
        seed = max(remaining, key=lambda index: _relationship_rank(relationships[index]))
        orientation = _orientation(relationships[seed])
        group = {seed}
        expanded = True
        while expanded:
            expanded = False
            for candidate in list(remaining - group):
                relationship = relationships[candidate]
                if _orientation(relationship) != orientation:
                    continue
                if relationship["confidence_score"] < 0.45:
                    continue
                if any(_related(relationships[current], relationship) for current in group):
                    group.add(candidate)
                    expanded = True
        ordered = sorted(group, key=lambda index: _relationship_rank(relationships[index]), reverse=True)
        groups.append(ordered)
        remaining -= group
    return groups


def _related(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if not _time_aligned(left, right):
        return False
    shared = set(left["columns"]) & set(right["columns"])
    if shared:
        return True
    left_boundary = str(left.get("boundary") or "").strip().lower()
    right_boundary = str(right.get("boundary") or "").strip().lower()
    return bool(left_boundary and left_boundary == right_boundary)


def _time_aligned(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_interval = _relationship_interval(left)
    right_interval = _relationship_interval(right)
    if left_interval and right_interval:
        left_start, left_end = left_interval
        right_start, right_end = right_interval
        duration = max(left_end - left_start, right_end - right_start, timedelta(seconds=1))
        tolerance = min(timedelta(days=7), duration * 0.25)
        return left_start <= right_end + tolerance and right_start <= left_end + tolerance
    left_window = str(left.get("time_window") or "").strip()
    right_window = str(right.get("time_window") or "").strip()
    return bool(left_window and right_window and left_window == right_window)


def _relationship_interval(item: dict[str, Any]) -> tuple[datetime, datetime] | None:
    ranges = item.get("source_time_ranges")
    candidates: list[tuple[Any, Any]] = []
    if isinstance(ranges, list):
        for value in ranges:
            if isinstance(value, dict):
                candidates.append(
                    (
                        value.get("current_start") or value.get("start"),
                        value.get("current_end") or value.get("end"),
                    )
                )
    candidates.append(
        (
            item.get("current_start") or item.get("start"),
            item.get("current_end") or item.get("end"),
        )
    )
    source_rows = item.get("source_rows")
    if isinstance(source_rows, list):
        by_window = {
            value.get("window"): value
            for value in source_rows
            if isinstance(value, dict) and value.get("window")
        }
        candidates.append(
            (
                (by_window.get("recent_start") or {}).get("timestamp"),
                (by_window.get("recent_end") or {}).get("timestamp"),
            )
        )
    for raw_start, raw_end in candidates:
        start = _datetime(raw_start)
        end = _datetime(raw_end)
        if start and end:
            return (min(start, end), max(start, end))
    return None


def _corroboration_result(
    support: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    uncertain: list[dict[str, Any]],
    independent: list[dict[str, Any]],
) -> ConditionCorroboration:
    signals = _dedupe([column for relationship in support for column in relationship["columns"]])
    systems = _dedupe(
        [
            relationship["system"]
            for relationship in support
            if relationship["system"].lower() not in GENERIC_SYSTEMS
        ]
    )
    confidence_score = _corroboration_confidence(support, conflicts)
    strength = _corroboration_strength(
        relationship_count=len(support),
        signal_count=len(signals),
        system_count=len(systems),
        confidence_score=confidence_score,
        conflict_count=len(conflicts),
    )
    common = _shared_signals(support)
    support_records = [
        _relationship_record(item, role="primary" if index == 0 else "secondary evidence")
        for index, item in enumerate(sorted(support, key=_relationship_rank, reverse=True))
    ]
    conflict_records = [
        _relationship_record(item, role="conflicting evidence")
        for item in sorted(conflicts, key=_relationship_rank, reverse=True)
    ]
    uncertain_records = [
        _relationship_record(item, role="uncertain evidence")
        for item in sorted(uncertain, key=_relationship_rank, reverse=True)
    ]
    independent_records = [
        _relationship_record(item, role="independent evidence")
        for item in sorted(independent, key=_relationship_rank, reverse=True)
    ]
    if len(support) == 1:
        summary = "No second changed relationship shares telemetry-supported signals in the same comparison window."
    else:
        connection = (
            f" through {', '.join(common[:3])}"
            if common
            else " at the same monitored boundary"
        )
        summary = (
            f"{len(support)} relationship changes align{connection} during comparable recent operation."
        )
        if conflicts:
            summary += f" {len(conflicts)} related relationship{'s' if len(conflicts) != 1 else ''} move differently and remain conflicting evidence."
        if uncertain:
            summary += f" {len(uncertain)} connected relationship{'s' if len(uncertain) != 1 else ''} remain below the evidence threshold."
    return ConditionCorroboration(
        condition_id=_condition_id(support),
        corroboration_strength=strength,
        relationship_count=len(support),
        affected_signals=signals,
        affected_systems=systems,
        supporting_relationships=support_records,
        conflicting_relationships=conflict_records,
        uncertain_relationships=uncertain_records,
        independent_relationships=independent_records,
        evidence_summary=summary,
        confidence=_confidence_label(confidence_score),
        confidence_score=round(confidence_score, 4),
    )


def _relationship_record(item: dict[str, Any], *, role: str) -> dict[str, Any]:
    connection_basis = {
        "primary": "highest-ranked relationship evidence",
        "secondary evidence": "shared monitored signal and aligned comparison window",
        "conflicting evidence": "connected telemetry changed in a different direction",
        "uncertain evidence": "connected telemetry did not meet the confidence threshold",
        "independent evidence": "no telemetry-supported connection to this condition",
    }.get(role, "relationship evidence")
    return {
        "relationship_id": _relationship_id(item),
        "id": _relationship_id(item),
        "signals": item["columns"],
        "columns": item["columns"],
        "system": item.get("system") or "",
        "change_type": item.get("change_type") or "changed",
        "baseline_strength": item.get("baseline_strength"),
        "current_strength": _first_defined(
            item.get("current_strength"),
            item.get("strength"),
        ),
        "correlation_delta": item.get("correlation_delta"),
        "confidence": _confidence_label(float(item.get("confidence_score") or 0.0)),
        "confidence_score": round(float(item.get("confidence_score") or 0.0), 4),
        "time_window": item.get("time_window") or "",
        "evidence_refs": item.get("evidence_refs") or [],
        "role": role,
        "connection_basis": connection_basis,
    }


def _condition_classification(
    *,
    related_finding: dict[str, Any] | None,
    support: list[dict[str, Any]],
    data_quality: dict[str, Any],
    operating_mode: dict[str, Any],
    baseline_analysis: dict[str, Any],
) -> dict[str, Any]:
    explicit = (related_finding or {}).get("classification")
    if isinstance(explicit, dict) and explicit.get("type"):
        return explicit

    primary = max(support, key=_relationship_rank)
    affected = set(column for item in support for column in item["columns"])
    sensor_health = [
        item
        for item in _list(data_quality.get("sensor_health"))
        if isinstance(item, dict) and str(item.get("signal") or "") in affected
    ]
    data_confidence = data_quality.get("data_confidence")
    if not isinstance(data_confidence, dict):
        data_confidence = {
            "rating": _data_quality_rating(data_quality),
            "reasons": _list(data_quality.get("warnings")),
        }
    trajectory = baseline_analysis.get("drift_trajectory")
    persistent_signals = set(
        (trajectory or {}).get("persistent_columns") or []
        if isinstance(trajectory, dict)
        else []
    )
    persistent = bool(persistent_signals & affected) or all(
        int(item.get("recent_sample_size") or 0) >= 6 for item in support
    )
    relationship_evidence = {
        "baseline_sample_size": primary.get("baseline_sample_size"),
        "recent_sample_size": primary.get("recent_sample_size"),
        "confidence_score": primary.get("confidence_score"),
        "correlation_delta": primary.get("correlation_delta"),
    }
    return classify_finding(
        data_confidence=data_confidence,
        sensor_health=sensor_health,
        operating_mode=operating_mode,
        persistence={"persistent": persistent, "summary": "The changed relationships persist in the available current window."},
        relationship_evidence=relationship_evidence,
    )


def _matching_finding(
    findings: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
) -> dict[str, Any] | None:
    ids = {_relationship_id(item) for item in relationships}
    signals = set(column for item in relationships for column in item["columns"])
    best: tuple[int, dict[str, Any]] | None = None
    for finding in findings:
        finding_ids = {
            str(item.get("id") or item.get("relationship_id") or "")
            for item in _list(
                finding.get("contributing_relationships")
                or finding.get("supporting_relationships")
            )
            if isinstance(item, dict)
        }
        finding_signals = set(
            str(value)
            for value in [
                *_list(finding.get("source_tags")),
                *_list(finding.get("source_metrics")),
                *_list(finding.get("affected_signals")),
            ]
            if value
        )
        score = len(ids & finding_ids) * 3 + len(signals & finding_signals)
        if score and (best is None or score > best[0]):
            best = (score, finding)
    return best[1] if best else None


def _condition_evidence(
    *,
    support: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    corroboration: ConditionCorroboration,
    trajectory: dict[str, Any],
    comparable: dict[str, Any],
) -> list[dict[str, Any]]:
    primary = max(support, key=_relationship_rank)
    evidence = [
        {
            "type": "corroboration",
            "summary": corroboration.evidence_summary,
            "relationship_ids": [_relationship_id(item) for item in support],
            "source_signals": corroboration.affected_signals,
        },
        {
            "type": "relationship_change",
            "summary": _primary_relationship_summary(primary),
            "relationship_ids": [_relationship_id(primary)],
            "source_signals": primary["columns"],
        },
        {
            "type": "trajectory",
            "summary": f"Trajectory is {trajectory.get('state', 'unavailable').lower()}; {trajectory.get('corroboration_change', 'corroboration history is unavailable').lower()}.",
            "relationship_ids": [_relationship_id(item) for item in support],
            "source_signals": corroboration.affected_signals,
        },
    ]
    if comparable.get("status") == "supported":
        evidence.append(
            {
                "type": "comparable_operation",
                "summary": f"{comparable.get('comparable_period_count')} comparable historical periods support this like-for-like comparison.",
                "relationship_ids": [_relationship_id(primary)],
                "source_signals": primary["columns"],
            }
        )
    if conflicts:
        evidence.append(
            {
                "type": "conflicting_evidence",
                "summary": f"{len(conflicts)} connected relationship{'s' if len(conflicts) != 1 else ''} move differently and limit certainty.",
                "relationship_ids": [_relationship_id(item) for item in conflicts],
                "source_signals": _dedupe([column for item in conflicts for column in item["columns"]]),
            }
        )
    return evidence[:5]


def _condition_timeline(
    *,
    support: list[dict[str, Any]],
    trajectory: dict[str, Any],
    corroboration: ConditionCorroboration,
    generated_at: str | None,
) -> list[dict[str, Any]]:
    intervals = [
        interval
        for item in support
        if (interval := _relationship_interval(item)) is not None
    ]
    timeline: list[dict[str, Any]] = []
    if intervals:
        start = min(interval[0] for interval in intervals).isoformat()
        end = max(interval[1] for interval in intervals).isoformat()
        timeline.append(
            {
                "event_type": "condition_evidence_window",
                "title": "Condition evidence observed",
                "detail": f"{corroboration.relationship_count} relationship changes were evaluated in the same recent operating window.",
                "start": start,
                "end": end,
                "precision": "source_timestamp",
            }
        )
    else:
        timeline.append(
            {
                "event_type": "condition_evidence_window",
                "title": "Condition evidence observed",
                "detail": f"{corroboration.relationship_count} relationship changes were evaluated in the available comparison window.",
                "period_label": "Available comparison window",
                "precision": "period",
            }
        )
    timeline.append(
        {
            "event_type": "trajectory_classified",
            "title": f"Trajectory: {trajectory.get('state', 'Unavailable')}",
            "detail": trajectory.get("corroboration_change") or "Evidence evolution was classified from available windows.",
            "period_label": trajectory.get("observed_for") or "Available comparison window",
            "precision": "period",
        }
    )
    if generated_at:
        timeline.append(
            {
                "event_type": "condition_generated",
                "title": "Condition generated for human review",
                "detail": "Neraium grouped only telemetry-supported relationship evidence.",
                "time": generated_at,
                "precision": "source_timestamp",
            }
        )
    return timeline


def _condition_headline(
    relationships: list[dict[str, Any]],
    localization: dict[str, Any],
) -> str:
    orientation = _orientation(relationships[0])
    signals = " ".join(column.lower().replace("_", " ") for item in relationships for column in item["columns"])
    system = localization.get("system") or localization.get("monitored_boundary") or "monitored area"
    site = str(localization.get("site") or "").strip()
    area = f"{site} {system}".strip() if site and site.lower() not in str(system).lower() else system
    if orientation == "weakening":
        subject = "Pump response" if "pump" in signals and any(token in signals for token in ("flow", "pressure", "power", "current")) else f"{area} response"
        return f"{subject} weakening in {area}" if subject.lower() != f"{area} response".lower() else f"{area} response weakening"
    if orientation == "strengthening":
        return f"Connected relationships strengthening in {area}"
    return f"Connected behavior changing in {area}"


def _condition_importance(
    corroboration: ConditionCorroboration,
    trajectory: dict[str, Any],
) -> str:
    if corroboration.relationship_count == 1:
        return "The relationship remains isolated evidence and should not be treated as a broader system condition."
    trajectory_label = str(trajectory.get("state") or "developing").lower()
    article = "an" if trajectory_label[:1] in {"a", "e", "i", "o", "u"} else "a"
    return (
        f"{corroboration.relationship_count} connected relationship changes form a "
        f"{corroboration.corroboration_strength} evidence pattern with "
        f"{article} {trajectory_label} trajectory."
    )


def _next_checks(
    localization: dict[str, Any],
    relationships: list[dict[str, Any]],
) -> list[str]:
    signals = localization.get("signals_involved") or []
    boundary = localization.get("monitored_boundary")
    system = localization.get("system")
    checks = [
        f"Verify source data for {', '.join(signals[:3])}." if signals else "Verify the contributing source data.",
        (
            f"Inspect the monitored {boundary.lower()} and compare it with operator logs."
            if boundary
            else f"Inspect the monitored {system.lower()} boundary and compare it with operator logs."
            if system
            else "Review the monitored signal boundary and operator logs."
        ),
        "Confirm staging, setpoints, load, and operating mode during the evidence window.",
        "Compare the next like-for-like operating period to determine whether corroboration strengthens or weakens.",
    ]
    return _dedupe(checks)


def _condition_confidence(
    *,
    support: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    data_quality: dict[str, Any],
    comparable: dict[str, Any],
) -> float:
    relationship_score = sum(float(item.get("confidence_score") or 0.0) for item in support) / len(support)
    count_support = min(1.0, len(support) / 4.0)
    quality_score = {"high": 0.9, "limited": 0.62, "moderate": 0.7, "low": 0.35}.get(
        _data_quality_rating(data_quality),
        0.5,
    )
    comparable_score = min(1.0, float(comparable.get("comparable_period_count") or 0) / 8.0)
    conflict_penalty = min(0.25, len(conflicts) * 0.08)
    score = (
        relationship_score * 0.48
        + count_support * 0.22
        + quality_score * 0.2
        + comparable_score * 0.1
        - conflict_penalty
    )
    return max(0.0, min(1.0, score))


def _corroboration_confidence(
    support: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
) -> float:
    evidence = sum(float(item.get("confidence_score") or 0.0) for item in support) / len(support)
    connected_support = min(1.0, max(0, len(support) - 1) / 3.0)
    conflict_penalty = min(0.3, len(conflicts) * 0.1)
    return max(0.0, min(1.0, evidence * 0.75 + connected_support * 0.25 - conflict_penalty))


def _corroboration_strength(
    *,
    relationship_count: int,
    signal_count: int,
    system_count: int,
    confidence_score: float,
    conflict_count: int,
) -> str:
    if relationship_count <= 1:
        return "isolated"
    if relationship_count == 2 or confidence_score < 0.58 or conflict_count >= relationship_count:
        return "limited"
    if relationship_count == 3:
        return "moderate"
    if (
        relationship_count >= 5
        and system_count >= 1
        and signal_count >= 5
        and confidence_score >= 0.75
        and conflict_count == 0
    ):
        return "systemic"
    return "strong" if relationship_count >= 4 and confidence_score >= 0.68 else "moderate"


def _condition_criticality(
    relationships: list[dict[str, Any]],
    finding: dict[str, Any] | None,
) -> str:
    values = [
        (finding or {}).get("criticality"),
        (finding or {}).get("asset_criticality"),
        *[item.get("criticality") for item in relationships],
    ]
    for value in values:
        text = str(value or "").lower()
        if text in {"critical", "high"}:
            return text
        if text in {"medium", "moderate"}:
            return "moderate"
    return "unknown"


def _supported_boundaries(signals: list[str]) -> list[str]:
    boundaries: list[str] = []
    patterns = (
        ("discharge", "Discharge boundary"),
        ("suction", "Suction boundary"),
        ("supply", "Supply boundary"),
        ("return", "Return boundary"),
        ("condenser", "Condenser boundary"),
        ("evaporator", "Evaporator boundary"),
        ("inlet", "Inlet boundary"),
        ("outlet", "Outlet boundary"),
        ("wet_well", "Wet well boundary"),
        ("wet well", "Wet well boundary"),
    )
    for signal in signals:
        normalized = signal.lower().replace("-", "_")
        for token, label in patterns:
            if token in normalized:
                boundaries.append(label)
    return _dedupe(boundaries)


def _shared_signals(relationships: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for item in relationships:
        for column in set(item["columns"]):
            counts[column] = counts.get(column, 0) + 1
    return [column for column, count in counts.items() if count >= 2]


def _primary_relationship_summary(item: dict[str, Any]) -> str:
    label = " / ".join(item["columns"]) or "Primary relationship"
    baseline = item.get("baseline_strength")
    current = _first_defined(item.get("current_strength"), item.get("strength"))
    if baseline is not None and current is not None:
        return f"{label} changed from {_strength_label(baseline)} to {_strength_label(current)} coupling."
    return f"{label} is classified as {str(item.get('change_type') or 'changed').replace('_', ' ')}."


def _strength_label(value: Any) -> str:
    try:
        numeric = abs(float(value))
    except (TypeError, ValueError):
        return "unavailable"
    if numeric < 0.3:
        return "weak"
    if numeric < 0.7:
        return "moderate"
    return "strong"


def _data_quality_rating(value: dict[str, Any]) -> str:
    data_confidence = value.get("data_confidence")
    if isinstance(data_confidence, dict) and data_confidence.get("rating"):
        return str(data_confidence["rating"]).lower()
    raw = str(
        value.get("reliability_rating")
        or value.get("confidence")
        or value.get("status")
        or ""
    ).lower()
    if any(token in raw for token in ("strong", "high", "ready", "reliable")):
        return "high"
    if any(token in raw for token in ("low", "unreliable", "failed", "poor")):
        return "low"
    return "limited"


def _is_changed_relationship(item: dict[str, Any]) -> bool:
    change = str(item.get("change_type") or item.get("state") or "changed").lower()
    if change in {"stable", "normal", "unchanged"}:
        return False
    try:
        delta = abs(float(item.get("correlation_delta") or item.get("delta") or 0.0))
    except (TypeError, ValueError):
        delta = 0.0
    return change in {"weakened", "strengthened", "missing", "new", "disrupted", "changed", "emerging"} or delta > 0


def _orientation(item: dict[str, Any]) -> str:
    change = str(item.get("change_type") or "").lower()
    if change in {"weakened", "missing"}:
        return "weakening"
    if change in {"strengthened", "new", "emerging"}:
        return "strengthening"
    if change in {"disrupted", "inverted"}:
        return "disrupted"
    baseline = _number(item.get("baseline_strength"))
    current = _number(_first_defined(item.get("current_strength"), item.get("strength")))
    if baseline is not None and current is not None:
        if current < baseline:
            return "weakening"
        if current > baseline:
            return "strengthening"
    signed = _number(item.get("signed_correlation_delta"))
    return "strengthening" if signed is not None and signed > 0 else "changed"


def _relationship_columns(item: dict[str, Any]) -> list[str]:
    columns = [str(value) for value in _list(item.get("columns")) if str(value).strip()]
    if len(columns) >= 2:
        return _dedupe(columns)[:2]
    signals = [str(value) for value in _list(item.get("signals")) if str(value).strip()]
    if len(signals) >= 2:
        return _dedupe(signals)[:2]
    pairs = item.get("supporting_metric_pairs")
    if isinstance(pairs, list) and pairs and isinstance(pairs[0], dict):
        pair = pairs[0]
        columns = [str(pair.get("left") or ""), str(pair.get("right") or "")]
    if len([value for value in columns if value]) >= 2:
        return [value for value in columns if value][:2]
    source = str(item.get("source") or "").removeprefix("metric:").removeprefix("tag:")
    target = str(item.get("target") or "").removeprefix("metric:").removeprefix("tag:")
    return _dedupe([value for value in (source, target) if value])


def _relationship_rank(item: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(item.get("relationship_importance_score") or 0.0),
        abs(float(item.get("correlation_delta") or 0.0)),
        float(item.get("confidence_score") or 0.0),
    )


def _relationship_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or item.get("relationship_id") or "")


def _condition_id(relationships: list[dict[str, Any]]) -> str:
    identifiers = "|".join(sorted(_relationship_id(item) for item in relationships))
    digest = hashlib.sha256(identifiers.encode("utf-8")).hexdigest()[:10]
    systems = [
        item.get("system")
        for item in relationships
        if str(item.get("system") or "").lower() not in GENERIC_SYSTEMS
    ]
    prefix = _slug(systems[0] if systems else "monitored-area")
    return f"condition-{prefix}-{digest}"


def _strength_rank(value: Any) -> int:
    try:
        return CORROBORATION_STRENGTHS.index(str(value).lower())
    except ValueError:
        return 0


def _confidence_label(value: float) -> str:
    if value >= 0.75:
        return "high"
    if value >= 0.55:
        return "moderate"
    return "low"


def _score(*values: Any) -> float:
    for value in values:
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            text = str(value or "").lower()
            if "high" in text or "strong" in text:
                return 0.85
            if "moderate" in text or "medium" in text or "limited" in text:
                return 0.62
            if "low" in text or "weak" in text:
                return 0.35
            continue
        if numeric > 1.0 and numeric <= 100.0:
            numeric /= 100.0
        return max(0.0, min(1.0, numeric))
    return 0.5


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_defined(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dedupe(values: list[Any]) -> list[Any]:
    return list(dict.fromkeys(value for value in values if value not in (None, "")))


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "condition"
