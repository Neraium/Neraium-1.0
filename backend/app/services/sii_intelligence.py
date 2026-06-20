from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.services.aletheia_governance import govern_candidate
from app.services.structural_cognition import build_structural_cognition


REQUIRED_INTELLIGENCE_FIELDS = [
    "facility_state",
    "room_state",
    "urgency",
    "intervention_window",
    "neraium_score",
    "primary_driver",
    "supporting_evidence",
    "relationship_evidence",
    "structural_explanation",
    "confidence_basis",
    "recommended_operator_review",
    "what_to_check",
    "why_flagged",
    "baseline_comparison",
    "observed_persistence",
    "last_updated",
    "core_sii_outputs",
]


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_sample_intelligence() -> dict[str, Any]:
    """Return backend-provided SII sample intelligence for no-upload sessions."""

    last_updated = now_iso()
    rooms = [
        {
            "room": "State Group A",
            "room_state": "Structural drift observed",
            "urgency": "review",
            "intervention_window": "Monitor next analysis window",
            "primary_driver": "A persistent weakening in the relationship between airflow_rate and return_pressure has emerged.",
            "supporting_evidence": [
                "Correlation between airflow_rate and return_pressure fell materially below baseline.",
                "The state trajectory continues drifting in the same direction across recent windows.",
                "The shift has persisted long enough to exceed expected background fluctuation.",
            ],
            "relationship_evidence": [
                "Coupling between airflow_rate and return_pressure is weaker than baseline.",
                "Secondary variables are no longer returning to their usual covariance structure.",
            ],
            "structural_explanation": [
                "The current covariance structure is departing from the learned baseline regime.",
                "A small set of variables is contributing most of the observed structural drift.",
                "Recovery behavior after recent perturbations is less consistent than baseline.",
            ],
            "confidence_basis": "Persistent multi-variable drift compared to the baseline regime.",
            "recommended_operator_review": "Inspect the affected variable relationships",
            "what_to_check": [
                "Review the affected variables in context",
                "Check whether the shift reflects an operational change, sensor issue, or emerging fault",
                "Compare the current recovery shape to baseline",
            ],
            "why_flagged": "The system has shifted away from its baseline relational structure and has not returned.",
            "baseline_comparison": "The active covariance pattern differs from the baseline regime.",
            "observed_persistence": "Observed across 3 monitoring windows",
            "projected_time_to_failure": "Not inferred in agnostic mode",
            "projected_time_to_failure_hours": None,
            "last_updated": last_updated,
            "confidence": 86,
        },
        {
            "room": "State Group B",
            "room_state": "Baseline-aligned",
            "urgency": "nominal",
            "intervention_window": "Baseline-aligned window",
            "primary_driver": "The current state remains close to the learned baseline regime.",
            "supporting_evidence": [
                "The leading variables remain inside their normal baseline envelope.",
                "Relationship strengths remain close to baseline values.",
            ],
            "relationship_evidence": [
                "The covariance structure remains stable.",
            ],
            "structural_explanation": [
                "The system is occupying its expected baseline region in state space.",
                "No persistent structural deformation is visible.",
                "Recent perturbations appear to recover normally.",
            ],
            "confidence_basis": "Stable relationship behavior across recent monitoring windows.",
            "recommended_operator_review": "Continue monitoring",
            "what_to_check": [
                "Continue monitoring",
                "Watch the next perturbation and recovery cycle",
                "Review only if persistence or drift velocity increases",
            ],
            "why_flagged": "Current behavior remains inside the baseline regime.",
            "baseline_comparison": "Current behavior is inside the learned baseline regime.",
            "observed_persistence": "Stable across recent monitoring windows",
            "projected_time_to_failure": "Not inferred in agnostic mode",
            "projected_time_to_failure_hours": None,
            "last_updated": last_updated,
            "confidence": 74,
        },
    ]
    structural_cognition = build_structural_cognition(
        baseline_analysis={
            "column_drift": [
                {"column": "humidity", "percent_change": 18, "drift_flag": "review"},
                {"column": "temperature", "percent_change": 11, "drift_flag": "watch"},
            ]
        },
        engine_result={
            "system_evidence": {
                "corroboration_level": "strong",
                "categories_showing_meaningful_change": 3,
                "categories": {
                    "moisture_control": {"signals": [1, 2], "evidence": [1]},
                    "thermal_control": {"signals": [1], "evidence": [1]},
                    "flow_restriction": {"signals": [1], "evidence": [1]},
                },
            },
            "evidence": [
                {"type": "relationship_change", "columns": ["airflow", "humidity"], "change": 0.82},
                {"type": "relationship_change", "columns": ["temperature", "humidity"], "change": 0.76},
            ],
            "persistence_assessment": {"persistent_columns": ["humidity", "temperature"]},
        },
        driver_attribution={
            "likely_driver": rooms[0]["primary_driver"],
            "driver_category": "humidity_control",
            "supporting_evidence": rooms[0]["supporting_evidence"],
        },
        room_summary={"room_count": len(rooms), "rooms": [{"room": room["room"]} for room in rooms]},
        urgency="review",
    )
    operator_explanation = structural_cognition["operator_explanation_v2"]
    candidate = {
        "source": "sii_engine",
        "mode": "sample",
        "facility_state": "Structural drift observed",
        "room_state": rooms[0]["room_state"],
        "urgency": "review",
        "intervention_window": rooms[0]["intervention_window"],
        "neraium_score": 82,
        "primary_room": rooms[0]["room"],
        "primary_driver": rooms[0]["primary_driver"],
        "supporting_evidence": rooms[0]["supporting_evidence"],
        "relationship_evidence": rooms[0]["relationship_evidence"],
        "structural_explanation": rooms[0]["structural_explanation"],
        "confidence_basis": rooms[0]["confidence_basis"],
        "recommended_operator_review": rooms[0]["recommended_operator_review"],
        "what_to_check": rooms[0]["what_to_check"],
        "why_flagged": rooms[0]["why_flagged"],
        "baseline_comparison": rooms[0]["baseline_comparison"],
        "observed_persistence": rooms[0]["observed_persistence"],
        "projected_time_to_failure": rooms[0]["projected_time_to_failure"],
        "projected_time_to_failure_hours": rooms[0]["projected_time_to_failure_hours"],
        "last_updated": last_updated,
        "rooms": rooms,
        **structural_cognition,
        "structural_explanation": [
            operator_explanation["summary"],
            *rooms[0]["structural_explanation"][:2],
        ],
    }
    candidate["core_sii_outputs"] = build_core_sii_outputs(candidate)
    candidate["aletheia_gate"] = govern_candidate(candidate)
    return candidate


def build_upload_intelligence(
    *,
    filename: str,
    row_count: int,
    data_quality: dict[str, Any],
    baseline_analysis: dict[str, Any],
    engine_result: dict[str, Any],
    driver_attribution: dict[str, Any],
    operator_report: dict[str, Any],
    timestamp_profile: dict[str, Any],
    room_summary: dict[str, Any] | None = None,
    room_assessments: dict[str, dict[str, Any]] | None = None,
    source: str = "uploaded",
    mode: str = "live",
    source_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_updated = now_iso()
    evidence_guard = evaluate_evidence_guard(
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        attribution=driver_attribution,
    )
    evidence_chain_quality = build_evidence_chain_quality(
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        attribution=driver_attribution,
    )
    regime_context = baseline_analysis.get("regime_context") or classify_regime_from_metadata(timestamp_profile, source_metadata)
    adaptive_baseline = baseline_analysis.get("adaptive_baseline") or {}
    drift_trajectory = baseline_analysis.get("drift_trajectory") or {}
    feedback_calibration = build_feedback_calibration(source_metadata or {}, evidence_chain_quality)
    urgency = urgency_from_upload(
        data_quality=data_quality,
        engine_result=engine_result,
        attribution=driver_attribution,
    )
    score = score_from_upload(data_quality, engine_result, driver_attribution)
    primary_driver = driver_attribution.get("likely_driver") or "Available telemetry suggests a persistent structural change."
    if evidence_guard["strong_finding_blocked"]:
        if driver_attribution.get("driver_category") not in {None, "", "unknown_system_drift"}:
            primary_driver = f"Possible contributor: {primary_driver}. Evidence remains limited."
        else:
            primary_driver = "Evidence remains insufficient for a strong driver assignment."
    supporting_evidence = driver_attribution.get("supporting_evidence") or operator_report.get("key_observations", [])
    relationship_evidence = relationship_evidence_from_engine(engine_result)
    structural_explanation = structural_explanation_from_attribution(driver_attribution, relationship_evidence)
    why_flagged = supporting_evidence[0] if supporting_evidence else "Telemetry changed compared to the baseline regime."
    what_to_check = checks_from_attribution(driver_attribution, operator_report)
    intervention_window = window_from_urgency(urgency)
    room = driver_attribution.get("room") or "State Group A"
    room_state = driver_attribution.get("state") or state_from_urgency(urgency)
    projected_time_to_failure_hours = project_time_to_failure_hours(
        urgency=urgency,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
    )
    projected_time_to_failure = format_projected_time_to_failure(projected_time_to_failure_hours)
    calibrated_confidence = confidence_number(
        driver_attribution,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
    )
    reliability_rating = data_quality.get("reliability_rating") or "unknown"
    data_quality_warning = (data_quality.get("warnings") or [None])[0]
    structural_cognition = build_structural_cognition(
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        room_summary=room_summary,
        urgency=urgency,
    )
    operator_explanation = structural_cognition["operator_explanation_v2"]
    structural_explanation = [
        operator_explanation["summary"],
        *structural_explanation[:2],
    ]

    room_records = build_upload_room_records(
        room_summary=room_summary,
        fallback_room=room,
        room_state=room_state,
        urgency=urgency,
        intervention_window=intervention_window,
        primary_driver=primary_driver,
        supporting_evidence=supporting_evidence,
        relationship_evidence=relationship_evidence,
        structural_explanation=structural_explanation,
        confidence_basis=guarded_confidence_basis(
            driver_attribution.get("confidence_basis") or "Evidence is being compared across uploaded variable relationships.",
            evidence_guard=evidence_guard,
        ),
        recommended_operator_review=driver_attribution.get("next_operator_move") or (what_to_check[0] if what_to_check else "Continue monitoring"),
        what_to_check=what_to_check,
        why_flagged=why_flagged,
        baseline_comparison=baseline_comparison_from_analysis(baseline_analysis),
        observed_persistence=observed_persistence_from_engine(engine_result),
        projected_time_to_failure=projected_time_to_failure,
        projected_time_to_failure_hours=projected_time_to_failure_hours,
        last_updated=last_updated,
        confidence=calibrated_confidence,
        room_assessments=room_assessments,
    )
    primary_room_record = room_records[0]
    top_level_confidence_components = primary_room_record.get("confidence_components") or {
        "data_sufficiency": "medium",
        "signal_strength": "medium",
        "relationship_support": "medium",
        "persistence": "medium",
    }
    candidate = {
        "source": source,
        "mode": mode,
        "facility_state": primary_room_record["room_state"],
        "room_state": primary_room_record["room_state"],
        "urgency": primary_room_record["urgency"],
        "intervention_window": primary_room_record["intervention_window"],
        "neraium_score": score,
        "primary_room": primary_room_record["room"],
        "priority_room": primary_room_record["room"],
        "primary_driver": primary_room_record["primary_driver"],
        "driver_category": primary_room_record.get("driver_category") or driver_attribution.get("driver_category"),
        "attribution_confidence": primary_room_record.get("attribution_confidence") or driver_attribution.get("attribution_confidence"),
        "supporting_evidence": supporting_evidence,
        "relationship_evidence": relationship_evidence,
        "relationship_graph": relationship_graph_from_engine(engine_result),
        "structural_explanation": structural_explanation,
        "regime_context": regime_context,
        "adaptive_baseline": adaptive_baseline,
        "drift_trajectory": drift_trajectory,
        "counterfactual_driver_ranking": driver_attribution.get("counterfactual_driver_ranking", []),
        "evidence_chain_quality": evidence_chain_quality,
        "operator_feedback_calibration": feedback_calibration,
        "confidence_basis": primary_room_record["confidence_basis"],
        "confidence_components": top_level_confidence_components,
        "recommended_operator_review": primary_room_record["recommended_operator_review"],
        "next_operator_move": primary_room_record["recommended_operator_review"],
        "what_to_check": what_to_check,
        "why_flagged": why_flagged,
        "what_changed": primary_room_record["baseline_comparison"],
        "why_it_matters": why_flagged,
        "review_next": primary_room_record["recommended_operator_review"],
        "data_quality_warning": data_quality_warning,
        "reliability_rating": reliability_rating,
        "baseline_comparison": primary_room_record["baseline_comparison"],
        "observed_persistence": primary_room_record["observed_persistence"],
        "projected_time_to_failure": primary_room_record["projected_time_to_failure"],
        "projected_time_to_failure_hours": primary_room_record["projected_time_to_failure_hours"],
        "last_updated": last_updated,
        "filename": filename,
        "row_count": row_count,
        "timestamp_coverage": timestamp_profile,
        "telemetry_profile": (source_metadata or {}).get("telemetry_profile", "unknown"),
        "telemetry_profile_confidence": (source_metadata or {}).get("telemetry_profile_confidence", "low"),
        "telemetry_profile_signals": (source_metadata or {}).get("telemetry_profile_signals", []),
        "telemetry_modality": (source_metadata or {}).get("telemetry_modality", "unknown"),
        "operational_signal_profile": (source_metadata or {}).get("operational_signal_profile", "unknown"),
        "operational_signal_profile_confidence": (source_metadata or {}).get("operational_signal_profile_confidence", "low"),
        "operational_signal_profile_signals": (source_metadata or {}).get("operational_signal_profile_signals", []),
        "operational_signal_modality": (source_metadata or {}).get("operational_signal_modality", "unknown"),
        "system_identity": {
            "profile": (source_metadata or {}).get("telemetry_profile", "unknown"),
            "confidence": (source_metadata or {}).get("telemetry_profile_confidence", "low"),
            "signals": (source_metadata or {}).get("telemetry_profile_signals", []),
            "modality": (source_metadata or {}).get("telemetry_modality", "unknown"),
            "operational_profile": (source_metadata or {}).get("operational_signal_profile", "unknown"),
            "operational_confidence": (source_metadata or {}).get("operational_signal_profile_confidence", "low"),
            "operational_signals": (source_metadata or {}).get("operational_signal_profile_signals", []),
            "operational_modality": (source_metadata or {}).get("operational_signal_modality", "unknown"),
            "claim_made": (
                (source_metadata or {}).get("telemetry_profile_confidence") in {"medium", "high"}
                or (source_metadata or {}).get("operational_signal_profile_confidence") in {"medium", "high"}
            ),
        },
        "room_summary": room_summary or {},
        "rooms": room_records,
        "source_metadata": {
            **(source_metadata or {}),
            "regime_context": regime_context,
            "adaptive_baseline_strategy": adaptive_baseline.get("strategy"),
            "evidence_chain_quality": evidence_chain_quality,
        },
        **structural_cognition,
    }
    candidate["core_sii_outputs"] = build_core_sii_outputs(candidate)
    candidate["aletheia_gate"] = govern_candidate(candidate)
    return candidate


def build_core_sii_outputs(intelligence: dict[str, Any]) -> dict[str, Any]:
    supporting_evidence = intelligence.get("supporting_evidence")
    contributing_factors = (
        supporting_evidence[:5]
        if isinstance(supporting_evidence, list)
        else []
    )
    lead_time_hours = intelligence.get("projected_time_to_failure_hours")
    lead_time_text = intelligence.get("projected_time_to_failure")
    return {
        "emerging_instability": {
            "state": intelligence.get("facility_state"),
            "urgency": intelligence.get("urgency"),
            "instability_index": intelligence.get("instability_index"),
        },
        "affected_system": {
            "primary": intelligence.get("primary_room") or intelligence.get("priority_room"),
        },
        "contributing_factors": contributing_factors,
        # Lead time is explicitly an inference product of the three core outputs, not a hard-coded rule.
        "lead_time_inference": {
            "hours": lead_time_hours if isinstance(lead_time_hours, (int, float)) else None,
            "summary": lead_time_text if isinstance(lead_time_text, str) and lead_time_text.strip() else None,
            "confidence_basis": intelligence.get("confidence_basis"),
        },
    }


def build_upload_room_records(
    *,
    room_summary: dict[str, Any] | None,
    fallback_room: str,
    room_state: str,
    urgency: str,
    intervention_window: str,
    primary_driver: str,
    supporting_evidence: list[str],
    relationship_evidence: list[str],
    structural_explanation: list[str],
    confidence_basis: str,
    recommended_operator_review: str,
    what_to_check: list[str],
    why_flagged: str,
    baseline_comparison: str,
    observed_persistence: str,
    projected_time_to_failure: str,
    projected_time_to_failure_hours: int,
    last_updated: str,
    confidence: int,
    room_assessments: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    summary_rooms = room_summary.get("rooms", []) if isinstance(room_summary, dict) else []
    room_details = [
        {
            "room": str(item.get("room")),
            "row_count": int(item.get("row_count") or 0),
        }
        for item in summary_rooms
        if isinstance(item, dict) and item.get("room")
    ]
    room_names = [item["room"] for item in room_details]
    if not room_names:
        fallback = fallback_room or "State Group A"
        room_names = [fallback]
        room_details = [{"room": fallback, "row_count": 0}]

    records = []
    for index, room_name in enumerate(room_names):
        detail = room_details[index] if index < len(room_details) else {"room": room_name, "row_count": 0}
        assessment = (room_assessments or {}).get(room_name, {})
        room_count_context = (
            f" across {detail['row_count']} telemetry row(s)"
            if detail["row_count"] > 0
            else ""
        )
        derived_why = str(assessment.get("why_flagged") or why_flagged)
        room_specific_why = why_flagged if index == 0 else f"{room_name} is flagged because {derived_why.lower()}{room_count_context}."
        room_supporting_evidence = (
            supporting_evidence
            if index == 0
            else prefix_room_evidence(room_name, assessment.get("supporting_evidence") or supporting_evidence)
        )
        room_relationship_evidence = (
            relationship_evidence
            if index == 0
            else prefix_room_evidence(room_name, assessment.get("relationship_evidence") or relationship_evidence)
        )
        room_structural_explanation = (
            structural_explanation
            if index == 0
            else prefix_room_evidence(room_name, assessment.get("structural_explanation") or structural_explanation)
        )
        room_checks = (
            what_to_check
            if index == 0
            else prefix_room_evidence(room_name, assessment.get("what_to_check") or what_to_check)
        )
        room_urgency = str(assessment.get("urgency") or urgency)
        room_state_value = str(assessment.get("room_state") or (room_state if index == 0 else state_from_urgency(room_urgency)))
        room_intervention_window = str(assessment.get("intervention_window") or (intervention_window if index == 0 else window_from_urgency(room_urgency)))
        room_driver = str(assessment.get("primary_driver") or (primary_driver if index == 0 else "Room telemetry indicates a separate operating pattern."))
        room_confidence = int(assessment.get("confidence") or (confidence if index == 0 else max(confidence - 6, 0)))
        room_driver_category = (
            str(assessment.get("driver_category") or "unknown_system_drift")
            if index > 0
            else str((room_assessments or {}).get(room_name, {}).get("driver_category") or "unknown_system_drift")
        )
        room_attribution_confidence = (
            str(assessment.get("attribution_confidence") or "low")
            if index > 0
            else str((room_assessments or {}).get(room_name, {}).get("attribution_confidence") or "medium")
        )
        room_confidence_components = (
            assessment.get("confidence_components")
            if index > 0
            else ((room_assessments or {}).get(room_name, {}).get("confidence_components"))
        ) or {
            "data_sufficiency": "medium",
            "signal_strength": "medium",
            "relationship_support": "medium",
            "persistence": "medium",
        }
        room_confidence_basis = confidence_basis if index == 0 else confidence_basis_from_components(room_confidence_components)
        records.append(
            {
                "room": room_name,
                "room_state": room_state_value,
                "urgency": room_urgency,
                "intervention_window": room_intervention_window,
                "primary_driver": room_driver,
                "driver_category": room_driver_category,
                "attribution_confidence": room_attribution_confidence,
                "supporting_evidence": room_supporting_evidence,
                "relationship_evidence": room_relationship_evidence,
                "structural_explanation": room_structural_explanation,
                "confidence_basis": room_confidence_basis,
                "confidence_components": room_confidence_components,
                "recommended_operator_review": (
                    str(assessment.get("recommended_operator_review"))
                    if assessment.get("recommended_operator_review")
                    else (
                        recommended_operator_review
                        if index == 0
                        else room_checks[0].replace(f"{room_name}: ", "")
                    )
                ),
                "next_operator_move": (
                    str(assessment.get("next_operator_move"))
                    if assessment.get("next_operator_move")
                    else (
                        recommended_operator_review
                        if index == 0
                        else str(assessment.get("recommended_operator_review") or room_checks[0].replace(f"{room_name}: ", ""))
                    )
                ),
                "what_to_check": room_checks,
                "why_flagged": room_specific_why,
                "baseline_comparison": baseline_comparison,
                "observed_persistence": observed_persistence,
                "projected_time_to_failure": projected_time_to_failure if index == 0 else (assessment.get("projected_time_to_failure") or "Monitoring"),
                "projected_time_to_failure_hours": projected_time_to_failure_hours if index == 0 else assessment.get("projected_time_to_failure_hours"),
                "last_updated": last_updated,
                "confidence": room_confidence,
            }
        )
    return records


def prefix_room_evidence(room_name: str, lines: list[Any]) -> list[str]:
    prefix = f"{room_name}:"
    return [
        text if text.startswith(prefix) else f"{prefix} {text}"
        for line in lines[:3]
        if (text := str(line).strip())
    ]


def confidence_basis_from_components(components: dict[str, Any]) -> str:
    data = str(components.get("data_sufficiency", "unknown")).lower()
    signal = str(components.get("signal_strength", "unknown")).lower()
    relationship = str(components.get("relationship_support", "unknown")).lower()
    persistence = str(components.get("persistence", "unknown")).lower()
    return (
        "Confidence components: "
        f"data_sufficiency={data}, "
        f"signal_strength={signal}, "
        f"relationship_support={relationship}, "
        f"persistence={persistence}."
    )


def project_time_to_failure_hours(
    *,
    urgency: str,
    engine_result: dict[str, Any],
    driver_attribution: dict[str, Any],
) -> int:
    base_hours = {"unstable": 8, "review": 48, "nominal": 504}.get(urgency, 72)
    signal_profile = summarize_signal_profile(engine_result)
    if signal_profile["elevated_count"] > 0:
        base_hours = min(base_hours, 8)
    elif signal_profile["review_count"] > 0:
        base_hours = min(base_hours, 36)
    elif signal_profile["watch_count"] > 0:
        base_hours = min(base_hours, 120)
    if signal_profile["corroboration_level"] == "strong":
        base_hours = max(4, int(base_hours * 0.65))
    elif signal_profile["corroboration_level"] == "moderate":
        base_hours = max(6, int(base_hours * 0.8))
    if signal_profile["persistent_columns"] > 0:
        base_hours = max(4, int(base_hours * 0.7))
    if driver_attribution.get("severity") == "action":
        base_hours = min(base_hours, 8)
    elif driver_attribution.get("severity") == "review":
        base_hours = min(base_hours, 36)
    return base_hours


def format_projected_time_to_failure(hours: int) -> str:
    if hours <= 12:
        return f"Approximately {hours} hours at current trajectory"
    if hours <= 72:
        days = max(1, round(hours / 24))
        return f"Approximately {days} days at current trajectory"
    weeks = max(1, round(hours / 168))
    return f"More than {weeks} weeks at current trajectory"


def build_intelligence_status(intelligence: dict[str, Any] | None = None) -> dict[str, Any]:
    intelligence = intelligence or build_sample_intelligence()
    fields = set(REQUIRED_INTELLIGENCE_FIELDS)
    return {
        "engine_loaded": True,
        "source": intelligence.get("source", "sii_engine"),
        "last_processed_at": intelligence.get("last_updated"),
        "active_rooms_count": len(intelligence.get("rooms", [])),
        "evidence_fields_present": sorted(field for field in fields if field in intelligence),
        "mode": intelligence.get("mode", "sample"),
    }


def build_empty_intelligence_status() -> dict[str, Any]:
    return {
        "engine_loaded": True,
        "source": "none",
        "last_processed_at": None,
        "active_rooms_count": 0,
        "evidence_fields_present": [],
        "mode": "empty",
        "status": "no_data",
    }


def score_from_upload(data_quality: dict[str, Any], engine_result: dict[str, Any], attribution: dict[str, Any]) -> int:
    evidence_guard = evaluate_evidence_guard(
        data_quality=data_quality,
        baseline_analysis={},
        engine_result=engine_result,
        attribution=attribution,
    )
    readiness = data_quality.get("readiness")
    severity = attribution.get("severity", "info")
    signal_profile = summarize_signal_profile(engine_result)
    score = 92 if readiness == "ready" else 80 if readiness == "needs_review" else 64
    score -= signal_profile["watch_count"] * 2
    score -= signal_profile["review_count"] * 4
    score -= signal_profile["elevated_count"] * 7
    if signal_profile["corroboration_level"] == "strong":
        score -= 4
    elif signal_profile["corroboration_level"] == "moderate":
        score -= 2
    score -= min(signal_profile["persistent_columns"] * 2, 4)
    if engine_result.get("overall_result") == "needs_review" and not engine_result.get("signals"):
        score -= 6
    elif engine_result.get("overall_result") == "needs_review":
        score -= 8
    elif engine_result.get("overall_result") == "elevated":
        score -= 10
    if severity == "action":
        score -= 6
    elif severity == "review":
        score -= 3
    if evidence_guard["contradictory"]:
        score = min(score, 54)
    elif evidence_guard["strong_finding_blocked"] and evidence_guard["active_finding"]:
        score = min(score, 62)
    elif evidence_guard["strong_finding_blocked"]:
        score = min(score, 68)
    return max(0, min(100, score))


def urgency_from_upload(
    *,
    data_quality: dict[str, Any],
    engine_result: dict[str, Any],
    attribution: dict[str, Any],
) -> str:
    evidence_guard = evaluate_evidence_guard(
        data_quality=data_quality,
        baseline_analysis={},
        engine_result=engine_result,
        attribution=attribution,
    )
    severity = attribution.get("severity", "info")
    if severity == "action" and not evidence_guard["strong_finding_blocked"]:
        return "unstable"
    signal_profile = summarize_signal_profile(engine_result)
    if signal_profile["elevated_count"] > 0 and not evidence_guard["strong_finding_blocked"]:
        return "unstable"
    if evidence_guard["strong_finding_blocked"] and (
        severity in {"action", "review"}
        or signal_profile["elevated_count"] > 0
        or signal_profile["review_count"] > 0
        or len(engine_result.get("evidence", []) or []) > 0
    ):
        return "review"
    if severity == "review":
        return "review"
    if data_quality.get("readiness") == "not_ready":
        return "review"
    if (
        signal_profile["review_count"] > 0
        or signal_profile["watch_count"] >= 1
        or signal_profile["corroboration_level"] in {"moderate", "strong"}
        or signal_profile["persistent_columns"] > 0
    ):
        return "review"
    return "nominal"


def summarize_signal_profile(engine_result: dict[str, Any]) -> dict[str, Any]:
    signals = engine_result.get("signals", [])
    watch_count = sum(1 for signal in signals if signal.get("level") == "watch")
    review_count = sum(1 for signal in signals if signal.get("level") == "review")
    elevated_count = sum(1 for signal in signals if signal.get("level") == "elevated")
    system_evidence = engine_result.get("system_evidence", {})
    persistence = engine_result.get("persistence_assessment", {})
    return {
        "watch_count": watch_count,
        "review_count": review_count,
        "elevated_count": elevated_count,
        "corroboration_level": system_evidence.get("corroboration_level", "limited"),
        "meaningful_categories": system_evidence.get("categories_showing_meaningful_change", 0),
        "persistent_columns": len(persistence.get("persistent_columns", [])),
    }


def relationship_evidence_from_engine(engine_result: dict[str, Any]) -> list[str]:
    evidence = []
    for item in engine_result.get("evidence", []):
        if item.get("type") == "relationship_change":
            columns = item.get("columns", [])
            if len(columns) >= 2:
                evidence.append(relationship_evidence_sentence(columns[0], columns[1]))
    return evidence[:4] or ["Relationship evidence is limited in the current telemetry."]


def relationship_evidence_sentence(first_column: str, second_column: str) -> str:
    first = display_column(first_column)
    second = display_column(second_column)
    return f"Coupling between {first} and {second} has shifted away from its baseline relationship."


def display_column(column: str) -> str:
    normalized = str(column).lower().replace("_", " ")
    aliases = {
        "intervention window hours": "intervention window",
        "hvac runtime": "HVAC runtime",
        "co2": "CO2",
    }
    return aliases.get(normalized, normalized)


def structural_explanation_from_attribution(attribution: dict[str, Any], relationship_evidence: list[str]) -> list[str]:
    if relationship_evidence:
        return [
            relationship_evidence[0],
            "The active covariance structure is diverging from the learned baseline regime.",
            "The drift appears structural rather than random scatter.",
        ]
    return [
        "The active covariance structure is diverging from the learned baseline regime.",
        "A subset of variables is carrying most of the observed drift.",
        "Persistence and recovery behavior are being compared against the baseline window.",
    ]


def checks_from_attribution(attribution: dict[str, Any], operator_report: dict[str, Any]) -> list[str]:
    category = str(attribution.get("driver_category") or "").lower()
    if category == "sensor_network":
        return [
            "Confirm telemetry continuity for the affected variables",
            "Review missing, stale, or noisy readings",
            "Check whether the structural shift is data-quality related",
        ]
    report_checks = operator_report.get("recommended_operator_checks", [])
    return report_checks[:3] or [
        "Inspect the affected variable relationships in context",
        "Check whether the shift reflects an operational change, sensor issue, or emerging fault",
        "Compare the current recovery path to baseline",
    ]


def baseline_comparison_from_analysis(baseline_analysis: dict[str, Any]) -> str:
    drift = baseline_analysis.get("column_drift", [])
    review_columns = [item.get("column") for item in drift if item.get("drift_flag") == "review"]
    if review_columns:
        return f"{review_columns[0]} moved away from the baseline regime."
    return "Current telemetry remains inside the available baseline comparison."


def observed_persistence_from_engine(engine_result: dict[str, Any]) -> str:
    persistent = engine_result.get("persistence_assessment", {}).get("persistent_columns", [])
    if persistent:
        return f"Observed as persistent drift involving {persistent[0]}"
    return "Persistence evidence is limited in the current telemetry."


def confidence_number(
    attribution: dict[str, Any],
    *,
    data_quality: dict[str, Any] | None = None,
    baseline_analysis: dict[str, Any] | None = None,
    engine_result: dict[str, Any] | None = None,
) -> int:
    confidence = attribution.get("attribution_confidence")
    if confidence == "high":
        score = 88
    elif confidence == "medium":
        score = 74
    else:
        score = 58

    data_quality = data_quality or {}
    baseline_analysis = baseline_analysis or {}
    engine_result = engine_result or {}
    rating = str(data_quality.get("reliability_rating") or "unknown")
    readiness = str(data_quality.get("readiness") or "")
    quality_metrics = data_quality.get("quality_metrics") or {}
    baseline_rows = int(baseline_analysis.get("baseline_window_rows") or 0)
    recent_rows = int(baseline_analysis.get("recent_window_rows") or 0)
    columns_analyzed = int(baseline_analysis.get("columns_analyzed") or 0)
    evidence_count = len(engine_result.get("evidence") or []) + len(engine_result.get("signals") or [])
    evidence_guard = evaluate_evidence_guard(
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        attribution=attribution,
    )

    caps = []
    if rating == "not_reliable":
        caps.append(38)
    elif rating == "weak":
        caps.append(48)
    elif rating == "usable":
        caps.append(68)
    if readiness == "not_ready":
        caps.append(35)
    elif readiness == "needs_review":
        caps.append(70)
    if baseline_rows < 5 or recent_rows < 1 or columns_analyzed < 1:
        caps.append(42)
    elif baseline_rows < 25:
        caps.append(62)
    if int(quality_metrics.get("rows_used") or 0) < 12:
        caps.append(44)
    if float(quality_metrics.get("drop_ratio") or 0.0) >= 0.2:
        caps.append(58)
    if quality_metrics.get("irregular_sampling"):
        caps.append(72)
    if evidence_count == 0:
        caps.append(56)
    if evidence_guard["baseline_weak"]:
        caps.append(52 if baseline_rows >= 12 else 42)
    if evidence_guard["data_quality_poor"]:
        caps.append(50 if readiness == "needs_review" else 38)
    if evidence_guard["persistence_short"]:
        caps.append(58 if evidence_count > 1 else 46)
    if evidence_guard["contradictory"]:
        caps.append(40)
    if evidence_guard["strong_finding_blocked"] and evidence_count <= 1:
        caps.append(48)

    if caps:
        score = min(score, min(caps))
    return max(0, min(100, score))


def evaluate_evidence_guard(
    *,
    data_quality: dict[str, Any],
    baseline_analysis: dict[str, Any],
    engine_result: dict[str, Any],
    attribution: dict[str, Any],
) -> dict[str, bool]:
    quality_metrics = data_quality.get("quality_metrics") or {}
    rating = str(data_quality.get("reliability_rating") or "unknown").lower()
    readiness = str(data_quality.get("readiness") or "").lower()
    baseline_rows = int(baseline_analysis.get("baseline_window_rows") or 0)
    recent_rows = int(baseline_analysis.get("recent_window_rows") or 0)
    columns_analyzed = int(baseline_analysis.get("columns_analyzed") or 0)
    baseline_warnings = list(baseline_analysis.get("warnings") or [])
    has_baseline_context = bool(baseline_analysis)
    baseline_review_count = sum(
        1 for item in (baseline_analysis.get("column_drift") or []) if item.get("drift_flag") == "review"
    )
    signal_profile = summarize_signal_profile(engine_result)
    evidence_count = len(engine_result.get("evidence") or []) + len(engine_result.get("signals") or [])
    persistent_columns = signal_profile["persistent_columns"]
    corroboration_level = str(signal_profile["corroboration_level"] or "limited").lower()
    severity = str(attribution.get("severity") or "info").lower()
    active_finding = evidence_count > 0 or signal_profile["review_count"] > 0 or signal_profile["elevated_count"] > 0 or severity == "action"
    drop_ratio = float(quality_metrics.get("drop_ratio") or 0.0)
    missing_rows = int(quality_metrics.get("rows_with_missing_values") or 0)
    invalid_rows = int(quality_metrics.get("rows_with_invalid_numeric") or 0)
    rows_used = max(1, int(quality_metrics.get("rows_used") or data_quality.get("row_count") or 0))

    baseline_weak = has_baseline_context and (
        baseline_rows < 25
        or recent_rows < 5
        or columns_analyzed < 2
        or any("not enough" in str(warning).lower() for warning in baseline_warnings)
    )
    data_quality_poor = (
        readiness in {"not_ready", ""}
        or rating in {"weak", "not_reliable", "unknown"}
        or drop_ratio >= 0.12
        or (missing_rows / rows_used) >= 0.12
        or (invalid_rows / rows_used) >= 0.08
        or bool(quality_metrics.get("irregular_sampling"))
        or not bool(quality_metrics.get("baseline_reliable", True))
    )
    persistence_short = active_finding and (persistent_columns == 0 or (persistent_columns < 2 and evidence_count <= 1))
    contradictory = (
        evidence_count > 0
        and (
            (corroboration_level == "limited" and persistent_columns == 0 and baseline_review_count == 0)
            or (severity == "action" and (baseline_weak or data_quality_poor) and corroboration_level != "strong")
        )
    )
    strong_finding_blocked = baseline_weak or data_quality_poor or persistence_short or contradictory
    return {
        "active_finding": active_finding,
        "baseline_weak": baseline_weak,
        "data_quality_poor": data_quality_poor,
        "persistence_short": persistence_short,
        "contradictory": contradictory,
        "strong_finding_blocked": strong_finding_blocked,
    }


def guarded_confidence_basis(base: str, *, evidence_guard: dict[str, bool]) -> str:
    if evidence_guard["contradictory"]:
        return (
            "Evidence is contradictory across baseline, persistence, and corroboration checks. "
            "Treat the current finding as preliminary."
        )
    limitations: list[str] = []
    if evidence_guard["baseline_weak"]:
        limitations.append("baseline depth is weak")
    if evidence_guard["data_quality_poor"]:
        limitations.append("data quality is poor")
    if evidence_guard["persistence_short"]:
        limitations.append("persistence is short")
    if limitations:
        joined = ", ".join(limitations)
        return f"{base} Confidence is capped because {joined}."
    return base


def window_from_urgency(urgency: str) -> str:
    return {
        "unstable": "Immediate review window",
        "review": "Monitor next analysis window",
        "nominal": "Baseline-aligned window",
    }.get(urgency, "Monitoring")


def state_from_urgency(urgency: str) -> str:
    return {
        "unstable": "Persistent structural drift observed",
        "review": "Structural drift observed",
        "nominal": "Baseline-aligned",
    }.get(urgency, "Monitoring")



def relationship_graph_from_engine(engine_result: dict[str, Any]) -> dict[str, Any]:
    for item in engine_result.get("evidence", []) or []:
        if isinstance(item, dict) and item.get("type") == "relationship_graph":
            return {
                "edge_count": item.get("edge_count", 0),
                "changed_edge_count": item.get("changed_edge_count", 0),
                "dominant_subsystems": item.get("dominant_subsystems", []),
                "deformation_score": item.get("deformation_score", 0),
                "density": item.get("density", 0),
                "top_edges": item.get("top_edges", []),
            }
    return {
        "edge_count": 0,
        "changed_edge_count": 0,
        "dominant_subsystems": [],
        "deformation_score": 0,
        "density": 0,
        "top_edges": [],
    }


def build_evidence_chain_quality(
    *,
    data_quality: dict[str, Any],
    baseline_analysis: dict[str, Any],
    engine_result: dict[str, Any],
    attribution: dict[str, Any],
) -> dict[str, Any]:
    quality_metrics = data_quality.get("quality_metrics") or {}
    relationship_graph = relationship_graph_from_engine(engine_result)
    signal_profile = summarize_signal_profile(engine_result)
    baseline_rows = int(baseline_analysis.get("baseline_window_rows") or 0)
    recent_rows = int(baseline_analysis.get("recent_window_rows") or 0)
    data_score = 1.0
    if data_quality.get("readiness") == "needs_review":
        data_score -= 0.2
    elif data_quality.get("readiness") == "not_ready":
        data_score -= 0.45
    data_score -= min(0.35, float(quality_metrics.get("drop_ratio") or 0.0))
    baseline_score = min(1.0, (baseline_rows + recent_rows) / 120) if baseline_rows or recent_rows else 0.0
    relationship_score = min(1.0, float(relationship_graph.get("deformation_score") or 0) + 0.25 * min(2, relationship_graph.get("changed_edge_count", 0)))
    persistence_score_value = min(1.0, signal_profile["persistent_columns"] / 3)
    attribution_score = {"high": 1.0, "medium": 0.72, "low": 0.38}.get(str(attribution.get("attribution_confidence") or "low"), 0.38)
    score = round(max(0.0, min(1.0, (data_score * 0.25) + (baseline_score * 0.2) + (relationship_score * 0.2) + (persistence_score_value * 0.2) + (attribution_score * 0.15))), 3)
    return {
        "score": score,
        "rating": "strong" if score >= 0.75 else "moderate" if score >= 0.5 else "limited",
        "components": {
            "data_quality": round(max(0.0, min(1.0, data_score)), 3),
            "baseline_depth": round(max(0.0, min(1.0, baseline_score)), 3),
            "relationship_graph": round(max(0.0, min(1.0, relationship_score)), 3),
            "persistence": round(max(0.0, min(1.0, persistence_score_value)), 3),
            "driver_attribution": attribution_score,
        },
        "limitations": evidence_quality_limitations(data_quality, baseline_analysis, signal_profile),
    }


def evidence_quality_limitations(data_quality: dict[str, Any], baseline_analysis: dict[str, Any], signal_profile: dict[str, Any]) -> list[str]:
    limitations: list[str] = []
    if data_quality.get("readiness") != "ready":
        limitations.append("data quality limits confidence")
    if int(baseline_analysis.get("baseline_window_rows") or 0) < 25:
        limitations.append("baseline window is shallow")
    if signal_profile["persistent_columns"] == 0:
        limitations.append("persistence is not yet established")
    return limitations


def build_feedback_calibration(source_metadata: dict[str, Any], evidence_quality: dict[str, Any]) -> dict[str, Any]:
    feedback_summary = source_metadata.get("feedback_summary") if isinstance(source_metadata.get("feedback_summary"), dict) else {}
    false_positive_count = int(feedback_summary.get("false_positive") or feedback_summary.get("ignore") or 0)
    confirmed_count = int(feedback_summary.get("confirmed_issue") or feedback_summary.get("useful_warning") or 0)
    sensitivity_adjustment = max(-0.08, min(0.08, (confirmed_count - false_positive_count) * 0.015))
    return {
        "feedback_available": bool(feedback_summary),
        "sensitivity_adjustment": round(sensitivity_adjustment, 3),
        "calibration_direction": "more_sensitive" if sensitivity_adjustment > 0 else "less_sensitive" if sensitivity_adjustment < 0 else "neutral",
        "evidence_quality_rating": evidence_quality.get("rating"),
        "operator_authority_preserved": True,
    }


def classify_regime_from_metadata(timestamp_profile: dict[str, Any], source_metadata: dict[str, Any] | None) -> dict[str, Any]:
    profile = str((source_metadata or {}).get("operational_signal_profile") or (source_metadata or {}).get("telemetry_profile") or "unknown")
    interval = str(timestamp_profile.get("estimated_sample_interval") or "").lower()
    if "runtime" in profile or "equipment" in profile:
        regime = "equipment_response"
    elif "continuous" in interval or interval:
        regime = "steady_state"
    else:
        regime = "unknown"
    return {"regime": regime, "confidence": "low", "basis": "metadata fallback"}
