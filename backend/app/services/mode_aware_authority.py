from __future__ import annotations

from typing import Any


POLICY_VERSION = "mode_aware_suppression_v1"
MINIMUM_MODE_CONFIDENCE = 0.70


def apply_mode_aware_suppression(
    *,
    engine_result: dict[str, Any] | None,
    relationship_model: dict[str, Any] | None,
    mode_conditioned: dict[str, Any] | None,
    relationship_graph: dict[str, Any] | None,
    adaptive_persistence: dict[str, Any] | None,
    multiscale_analysis: dict[str, Any] | None,
    enabled: bool,
) -> dict[str, Any]:
    """Conservatively suppress a compatibility candidate using corroborated Phase 2 evidence.

    This policy is deliberately one-way: it may suppress a candidate produced by
    the compatibility path, but it never creates a finding, raises severity, or
    increases confidence.
    """

    candidate = dict(engine_result or {})
    source_relationships = dict(relationship_model or {})
    conditioned = dict(mode_conditioned or {})
    graph = dict(relationship_graph or {})
    persistence = dict(adaptive_persistence or {})
    multiscale = dict(multiscale_analysis or {})

    candidate_present = str(candidate.get("overall_result") or "complete") in {
        "needs_review",
        "elevated",
    }
    mode_confidence = _number(conditioned.get("selection_confidence"))
    exact_mode_comparison = bool(
        conditioned.get("status") == "complete"
        and conditioned.get("used_global_fallback") is False
        and mode_confidence >= MINIMUM_MODE_CONFIDENCE
    )
    graph_stable = bool(
        graph.get("status") == "complete"
        and graph.get("edge_basis") == "mode_conditioned_relationships"
        and not list(graph.get("changed_edges") or [])
    )
    persistence_stable = bool(
        persistence.get("status") == "complete"
        and not list(persistence.get("persistent_columns") or [])
    )
    cross_scale = (
        multiscale.get("cross_scale_interpretation")
        if isinstance(multiscale.get("cross_scale_interpretation"), dict)
        else {}
    )
    multiscale_stable = bool(
        cross_scale.get("status") == "complete"
        and cross_scale.get("classification") == "stable_across_scales"
    )

    gates = {
        "candidate_present": candidate_present,
        "exact_mode_comparison": exact_mode_comparison,
        "mode_selection_confidence": round(mode_confidence, 6),
        "minimum_mode_selection_confidence": MINIMUM_MODE_CONFIDENCE,
        "mode_conditioned_graph_stable": graph_stable,
        "adaptive_persistence_stable": persistence_stable,
        "multiscale_stable": multiscale_stable,
    }
    applied = bool(
        enabled
        and candidate_present
        and exact_mode_comparison
        and graph_stable
        and persistence_stable
        and multiscale_stable
    )
    reasons = [
        label
        for label, passed in (
            ("same_mode_comparison_supported", exact_mode_comparison),
            ("no_conditioned_relationship_change", graph_stable),
            ("no_adaptive_persistence", persistence_stable),
            ("stable_across_scales", multiscale_stable),
        )
        if passed
    ]
    blockers = [
        label
        for label, passed in (
            ("feature_disabled", enabled),
            ("no_compatibility_candidate", candidate_present),
            ("mode_comparison_not_authoritative", exact_mode_comparison),
            ("conditioned_graph_not_stable", graph_stable),
            ("persistent_signal_present_or_unavailable", persistence_stable),
            ("multiscale_stability_not_established", multiscale_stable),
        )
        if not passed
    ]
    decision = {
        "policy_version": POLICY_VERSION,
        "enabled": bool(enabled),
        "authority": "suppression_only",
        "applied": applied,
        "decision": "suppressed" if applied else "retained",
        "reasons": reasons if applied else [],
        "blockers": blockers,
        "gates": gates,
        "candidate_overall_result": candidate.get("overall_result"),
        "candidate_signal_count": len(candidate.get("signals") or []),
        "candidate_relationship_count": len(source_relationships.get("top_relationship_changes") or []),
    }
    if not applied:
        return {
            "engine_result": candidate,
            "relationship_model": source_relationships,
            "decision": decision,
        }

    suppressed_relationships = list(source_relationships.get("top_relationship_changes") or [])
    authoritative_relationships = {
        **source_relationships,
        "top_relationship_changes": [],
        "suppressed_top_relationship_changes": suppressed_relationships,
        "mode_aware_suppression": decision,
    }
    authoritative_engine = {
        **candidate,
        "overall_result": "complete",
        "signals": [],
        "evidence": [],
        "system_evidence": {
            **dict(candidate.get("system_evidence") or {}),
            "corroboration_level": "limited",
            "categories_showing_meaningful_change": 0,
            "categories": {},
        },
        "persistence_assessment": {
            **dict(candidate.get("persistence_assessment") or {}),
            "persistent_columns": [],
        },
        "mode_aware_suppression": {
            **decision,
            "suppressed_signals": list(candidate.get("signals") or []),
            "suppressed_evidence": list(candidate.get("evidence") or []),
        },
    }
    return {
        "engine_result": authoritative_engine,
        "relationship_model": authoritative_relationships,
        "decision": decision,
    }


def _number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if number == number else 0.0
