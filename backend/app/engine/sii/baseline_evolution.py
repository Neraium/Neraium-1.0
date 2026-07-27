from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any


DEFAULT_CONFIG = {
    "minimum_candidate_rows": 30,
    "learning_delay_runs": 1,
    "human_validation_required": False,
    "maximum_instability_index": 0.20,
    "require_expected_model_validation_after_initialization": True,
}

LEARNING_DECISIONS = {
    "accepted",
    "deferred",
    "rejected",
    "insufficient_evidence",
    "blocked_by_active_observation",
    "blocked_by_data_quality",
    "blocked_by_sensor_health",
    "blocked_by_mode_ambiguity",
    "blocked_by_physics_evidence",
    "blocked_by_instability",
    "blocked_by_model_validation",
    "blocked_by_insufficient_history",
}


def evaluate_baseline_evolution(
    *,
    active_model: dict[str, Any] | None,
    rows_count: int,
    numeric_columns: list[str],
    operating_mode: dict[str, Any],
    data_quality: dict[str, Any],
    sensor_health: dict[str, Any],
    temporal_analysis: dict[str, Any],
    multiscale_analysis: dict[str, Any],
    physics_reasoning: dict[str, Any],
    expected_behavior: dict[str, Any],
    graph_comparison: dict[str, Any],
    active_observations: list[dict[str, Any]] | None,
    source_run_id: str,
    effective_time: str,
    model_version: str | None,
    prior_learning_decisions: list[dict[str, Any]] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Gate every behavioral/baseline write with explicit deterministic rules."""

    cfg = {**DEFAULT_CONFIG, **(config or {})}
    checks: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    supporting: list[dict[str, Any]] = []
    limiting: list[dict[str, Any]] = []
    contradicting: list[dict[str, Any]] = []

    def check(name: str, passed: bool, evidence: Any, failure_decision: str, reason: str) -> None:
        record = {
            "check": name,
            "passed": bool(passed),
            "source_evidence": deepcopy(evidence),
            "failure_decision": failure_decision,
            "reason": reason,
        }
        checks.append(record)
        (supporting if passed else limiting).append(record)

    check(
        "candidate_period_duration",
        rows_count >= int(cfg["minimum_candidate_rows"]),
        {"rows_count": rows_count, "minimum_candidate_rows": int(cfg["minimum_candidate_rows"])},
        "blocked_by_insufficient_history",
        "candidate_period_too_short",
    )
    data_rating = str((data_quality.get("data_confidence") or {}).get("rating") or "").lower()
    data_ok = str(data_quality.get("readiness") or "").lower() != "not_ready" and data_rating not in {"low", "not_reliable"}
    check(
        "data_quality",
        data_ok,
        {"readiness": data_quality.get("readiness"), "data_confidence": deepcopy(data_quality.get("data_confidence", {}))},
        "blocked_by_data_quality",
        "data_quality_not_acceptable",
    )
    health_by_signal = {
        str(item.get("signal")): str(item.get("health") or "unavailable").lower()
        for item in sensor_health.get("signals", [])
        if isinstance(item, dict) and item.get("signal")
    }
    unhealthy = [
        signal for signal in numeric_columns if health_by_signal.get(signal) not in {"healthy", "good"}
    ]
    check(
        "sensor_health",
        not unhealthy,
        {"unhealthy_or_unavailable_signals": unhealthy, "profiles": deepcopy(sensor_health.get("signals", []))},
        "blocked_by_sensor_health",
        "sensor_health_not_acceptable",
    )
    recent_mode = operating_mode.get("recent_mode")
    mode_ok = bool(recent_mode and recent_mode != "unavailable" and operating_mode.get("match") not in {"weak", "unavailable"})
    check(
        "operating_mode",
        mode_ok,
        deepcopy(operating_mode),
        "blocked_by_mode_ambiguity",
        "operating_mode_unknown_or_ambiguous",
    )
    unresolved = [item for item in (active_observations or []) if isinstance(item, dict)]
    unresolved.extend(
        item for item in expected_behavior.get("residual_evidence", []) if isinstance(item, dict)
    )
    check(
        "unresolved_significant_observation",
        not unresolved,
        {"active_observations": deepcopy(unresolved)},
        "blocked_by_active_observation",
        "unresolved_significant_observation_active",
    )
    contradictory_priors = list(physics_reasoning.get("contradictory_priors") or [])
    physics_ok = not contradictory_priors
    check(
        "physics_evidence",
        physics_ok,
        {"contradictory_priors": contradictory_priors},
        "blocked_by_physics_evidence",
        "configured_physics_evidence_contradicts_adaptation",
    )
    multiscale_classification = str(
        multiscale_analysis.get("cross_scale_classification")
        or (multiscale_analysis.get("cross_scale_interpretation") or {}).get("classification")
        or ""
    ).lower()
    multiscale_ok = multiscale_analysis.get("status") == "complete" and multiscale_classification in {
        "agreement",
        "consistent",
        "stable",
        "stable_across_scales",
    }
    check(
        "multiscale_stability",
        multiscale_ok,
        {"status": multiscale_analysis.get("status"), "classification": multiscale_analysis.get("cross_scale_classification"), "scales_used": deepcopy(multiscale_analysis.get("scales_used", []))},
        "blocked_by_instability",
        "multiscale_evidence_does_not_support_stability",
    )
    instability = float((temporal_analysis.get("instability_index") or {}).get("score") or 0.0)
    temporal_state = str((temporal_analysis.get("decision_thresholding") or {}).get("state") or "").lower()
    temporal_ok = instability <= float(cfg["maximum_instability_index"]) and temporal_state in {"", "normal", "stable"}
    check(
        "temporal_stability",
        temporal_ok,
        {"instability_index": instability, "decision_state": temporal_state, "maximum": float(cfg["maximum_instability_index"])},
        "blocked_by_instability",
        "temporal_evidence_does_not_support_stability",
    )
    graph_changes = graph_comparison.get("changed_edges", []) if isinstance(graph_comparison, dict) else []
    graph_ok = not graph_changes or not active_model
    check(
        "relationship_structure_consistency",
        graph_ok,
        {"changed_edges": deepcopy(graph_changes), "comparison_status": graph_comparison.get("status") if isinstance(graph_comparison, dict) else None},
        "blocked_by_instability",
        "relationship_structure_changed_relative_to_active_model",
    )
    expected_required = bool(active_model and cfg["require_expected_model_validation_after_initialization"])
    expected_ok = not expected_required or (
        expected_behavior.get("status") == "complete"
        and int(expected_behavior.get("models_evaluated") or 0) > 0
        and not expected_behavior.get("residual_evidence")
    )
    check(
        "expected_behavior_validation",
        expected_ok,
        {
            "required": expected_required,
            "status": expected_behavior.get("status"),
            "models_evaluated": expected_behavior.get("models_evaluated"),
            "residual_evidence_count": len(expected_behavior.get("residual_evidence", [])),
        },
        "blocked_by_model_validation",
        "expected_behavior_validation_unavailable_or_unstable",
    )

    failed_checks = [item for item in checks if not item["passed"]]
    if failed_checks:
        decision = str(failed_checks[0]["failure_decision"])
        reason = str(failed_checks[0]["reason"])
    else:
        stable_candidates = _consecutive_stable_candidates(
            active_model,
            prior_learning_decisions,
        ) + 1
        delay = max(1, int(cfg["learning_delay_runs"]))
        if stable_candidates < delay:
            decision = "deferred"
            reason = "configured_learning_delay_not_satisfied"
            limiting.append(
                {
                    "check": "learning_delay",
                    "passed": False,
                    "source_evidence": {"stable_candidate_runs": stable_candidates, "required_runs": delay},
                    "reason": reason,
                }
            )
        else:
            decision = "accepted"
            reason = "all_deterministic_learning_safeguards_passed"
    if decision not in LEARNING_DECISIONS:
        decision = "rejected"
        reason = "invalid_internal_learning_decision"

    current_baseline = _active_baseline_version(active_model)
    candidate_version = _candidate_baseline_version(current_baseline, source_run_id)
    human_required = bool(cfg["human_validation_required"])
    pending_validation = decision == "accepted" and human_required
    learning_allowed = decision == "accepted" and not human_required
    baseline = None
    if decision == "accepted":
        baseline = {
            "previous_version": current_baseline,
            "candidate_version": candidate_version,
            "active_version": current_baseline if pending_validation else candidate_version,
            "effective_time": effective_time,
            "signals_updated": list(numeric_columns),
            "relationships_updated": [
                str(item.get("relationship_id"))
                for item in graph_comparison.get("changed_edges", [])
                if isinstance(item, dict) and item.get("relationship_id")
            ],
            "operating_modes_updated": [str(recent_mode)],
            "evidence_supporting_update": deepcopy(supporting),
            "evidence_limiting_update": deepcopy(limiting),
            "evidence_contradicting_update": deepcopy(contradicting),
            "excluded_data": deepcopy(exclusions),
            "learning_delay": {"required_runs": max(1, int(cfg["learning_delay_runs"])), "satisfied": True},
            "approval_status": "pending_validation" if pending_validation else "automatic",
            "source_run_id": source_run_id,
            "processing_trace": {"checks": deepcopy(checks), "decision": decision},
        }
    decision_id = f"learning-decision:{sha256(f'{source_run_id}|{decision}|{candidate_version}'.encode('utf-8')).hexdigest()[:20]}"
    return {
        "decision_id": decision_id,
        "decision": decision,
        "status": "pending_validation" if pending_validation else decision,
        "reason": reason,
        "source_evidence": deepcopy(checks),
        "affected_signals": list(numeric_columns),
        "affected_relationships": [
            str(item.get("relationship_id"))
            for item in graph_comparison.get("changed_edges", [])
            if isinstance(item, dict) and item.get("relationship_id")
        ],
        "model_version": model_version,
        "baseline_version": current_baseline,
        "candidate_baseline": baseline,
        "learning_allowed": learning_allowed,
        "human_validation_required": human_required,
        "pending_validation": pending_validation,
        "learning_exclusions": deepcopy(exclusions),
        "processing_trace": {
            "checks_evaluated": len(checks),
            "checks_failed": [item["check"] for item in failed_checks],
            "model_update_after_evidence_evaluation": True,
            "silent_adaptation_performed": False,
        },
    }


def _active_baseline_version(active_model: dict[str, Any] | None) -> str | None:
    if not isinstance(active_model, dict):
        return None
    history = active_model.get("baseline_history") or []
    for item in reversed(history):
        if isinstance(item, dict) and item.get("active_version"):
            return str(item["active_version"])
    versions = active_model.get("baseline_versions") or []
    return str(versions[-1]) if versions else None


def _candidate_baseline_version(active_version: str | None, source_run_id: str) -> str:
    sequence = 1
    if active_version:
        digits = "".join(character for character in active_version if character.isdigit())
        sequence = int(digits or 0) + 1
    digest = sha256(source_run_id.encode("utf-8")).hexdigest()[:8]
    return f"baseline-v{sequence}-{digest}"


def _consecutive_stable_candidates(
    active_model: dict[str, Any] | None,
    prior_learning_decisions: list[dict[str, Any]] | None,
) -> int:
    decisions = (
        prior_learning_decisions
        if isinstance(prior_learning_decisions, list)
        else active_model.get("learning_decisions") or []
        if isinstance(active_model, dict)
        else []
    )
    count = 0
    for item in reversed(decisions):
        if isinstance(item, dict) and item.get("decision") in {"accepted", "deferred"}:
            count += 1
        else:
            break
    return count
