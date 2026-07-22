from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.water_intelligence.models import (
    CONFIDENCE_DIMENSIONS,
    GRAPH_TRUST_PROPOSED,
    GRAPH_TRUST_SPECULATIVE,
    GRAPH_TRUST_TRUSTED,
    HYPOTHESIS_OBSERVED,
    HYPOTHESIS_SUSPECTED,
    RelationshipPrior,
    SignalMatch,
    build_confidence_summary,
    empty_confidence_dimensions,
)
from app.water_intelligence.priors import water_priors
from app.water_intelligence.signals import best_signal, columns_for_signals, match_water_signals
from app.water_intelligence.units import normalize_unit


SCHEMA_VERSION = "water-intelligence-v1"


@dataclass
class WaterIntelligenceContext:
    columns: list[str]
    engine_result: dict[str, Any]
    relationship_model: dict[str, Any]
    baseline_analysis: dict[str, Any]
    normalized_telemetry: dict[str, Any] | None = None
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None
    timestamp_profile: dict[str, Any] | None = None
    data_quality: dict[str, Any] | None = None
    operating_mode: str | None = None
    site_id: str | None = None
    system_id: str | None = None
    asset_id: str | None = None
    asset_metadata: dict[str, Any] | None = None
    config: dict[str, Any] = field(default_factory=dict)
    generated_at: str | None = None
    upload_id: str | None = None
    analysis_id: str | None = None


def interpret_water_intelligence(context: WaterIntelligenceContext) -> dict[str, Any]:
    generated_at = context.generated_at or datetime.now(UTC).isoformat()
    signal_matches = match_water_signals(
        columns=context.columns,
        telemetry_signal_catalog=context.telemetry_signal_catalog,
        required_dimensions=_required_dimensions(),
    )
    findings = _sii_relationship_findings(context)
    matched_edges: list[dict[str, Any]] = []
    insights: list[dict[str, Any]] = []
    skipped_priors: list[dict[str, Any]] = []

    for prior in water_priors():
        params = _resolved_prior_parameters(prior, context)
        applicability = _prior_applicability(prior, context, signal_matches)
        if not applicability["applicable"]:
            skipped_priors.append(_skip(prior, applicability["reason"], applicability["missing_required_signals"], applicability["invalid_conditions"]))
            continue
        relevant = _relevant_findings(prior, findings, signal_matches)
        if not relevant:
            skipped_priors.append(_skip(prior, "No SII relationship-drift finding involved the required water signals.", [], []))
            continue
        emitted = False
        for finding_index, finding in enumerate(relevant[:2]):
            finding_signals = _finding_signal_names(finding, signal_matches)
            trust = infer_graph_trust(finding=finding, prior=prior, matched_signal_names=finding_signals, context=context, parameters=params)
            matched_edges.append({"sii_finding_id": _finding_id(finding, finding_index), "relationship_prior_id": prior.prior_id, "graph_trust": trust})
            if not trust["eligible_for_operator_insight"]:
                skipped_priors.append({**_skip(prior, "Graph edge is speculative or correlation-only and is not eligible for automated water insight.", [], ["graph_trust_speculative"]), "sii_finding_id": _finding_id(finding, finding_index), "graph_trust": trust})
                continue
            insights.append(
                _build_water_insight(
                    prior=prior,
                    finding=finding,
                    finding_index=finding_index,
                    context=context,
                    signal_matches=signal_matches,
                    graph_trust=trust,
                    applicability=applicability,
                    parameters=params,
                    generated_at=generated_at,
                )
            )
            emitted = True
        if not emitted:
            skipped_priors.append(_skip(prior, "SII findings were present, but none passed graph-trust eligibility.", [], ["graph_trust_not_eligible"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "source": "sii_relationship_drift_interpretation",
        "engine_boundary": {
            "sii_engine_remains_responsible_for": [
                "learning site-specific telemetry relationships",
                "detecting relationship drift",
                "scoring SII evidence and uncertainty",
                "prioritizing generic operator investigation targets",
            ],
            "water_layer_adds": [
                "asset and signal meaning",
                "conditional engineering priors",
                "unit validation and normalization",
                "possible explanations, confounders, and recommended checks",
                "confidence decomposition without replacing SII confidence",
            ],
        },
        "prior_library": [prior.as_dict() for prior in water_priors()],
        "signal_map": {canonical: [match.as_dict() for match in matches] for canonical, matches in sorted(signal_matches.items())},
        "graph_trust_edges": matched_edges,
        "insights": insights,
        "skipped_priors": skipped_priors,
        "no_applicable_prior": not insights,
    }


def infer_graph_trust(*, finding: dict[str, Any], prior: RelationshipPrior, matched_signal_names: set[str], context: WaterIntelligenceContext, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    parameters = parameters or {}
    explicit = _explicit_graph_trust(finding)
    evidence_types = _graph_evidence_types(finding, prior, matched_signal_names, context)
    if explicit == GRAPH_TRUST_TRUSTED:
        tier = GRAPH_TRUST_TRUSTED
        reason = "Edge is explicitly trusted by operator confirmation or validated topology metadata."
    elif explicit == GRAPH_TRUST_PROPOSED:
        tier = GRAPH_TRUST_PROPOSED
        reason = "Edge is explicitly proposed and awaiting operator validation."
    elif explicit == GRAPH_TRUST_SPECULATIVE:
        tier = GRAPH_TRUST_SPECULATIVE
        reason = "Edge is explicitly marked speculative."
    else:
        statistical_only = evidence_types == {"statistical_association"}
        required_count = int(parameters.get("minimum_proposed_graph_evidence_types") or 3)
        if "validated_topology" in evidence_types or "operator_confirmation" in evidence_types:
            tier = GRAPH_TRUST_TRUSTED
            reason = "Edge has validated topology or operator confirmation evidence."
        elif not statistical_only and len(evidence_types) >= required_count and "statistical_association" in evidence_types:
            tier = GRAPH_TRUST_PROPOSED
            reason = "Edge is supported by multiple evidence types and remains awaiting operator validation."
        else:
            tier = GRAPH_TRUST_SPECULATIVE
            reason = "Edge is suggested from limited evidence; correlation alone cannot promote it."
    eligible = tier == GRAPH_TRUST_TRUSTED or (tier == GRAPH_TRUST_PROPOSED and len(evidence_types - {"statistical_association"}) >= 2)
    return {
        "tier": tier,
        "eligible_for_operator_insight": eligible,
        "evidence_types": sorted(evidence_types),
        "correlation_only": evidence_types == {"statistical_association"},
        "promotion_rule": "Trusted requires operator/validated topology evidence. Proposed requires multiple evidence types; correlation alone is insufficient.",
        "explanation": reason,
    }


def _build_water_insight(*, prior: RelationshipPrior, finding: dict[str, Any], finding_index: int, context: WaterIntelligenceContext, signal_matches: dict[str, list[SignalMatch]], graph_trust: dict[str, Any], applicability: dict[str, Any], parameters: dict[str, Any], generated_at: str) -> dict[str, Any]:
    active_confounders = _active_confounders(prior, context, signal_matches, finding)
    derived_metrics = _derived_metrics(prior, signal_matches, context, parameters)
    dimensions = _confidence_dimensions(prior=prior, finding=finding, context=context, signal_matches=signal_matches, graph_trust=graph_trust, active_confounders=active_confounders, derived_metrics=derived_metrics, applicability=applicability)
    confidence = build_confidence_summary(dimensions, preserved_sii_confidence=_sii_confidence(finding))
    first_detected, last_observed = _finding_times(finding, context)
    affected_system = _affected_system(prior)
    observed_evidence = _observed_evidence(prior, finding, signal_matches, graph_trust, context)
    explanations = _possible_explanations(prior, derived_metrics, active_confounders)
    checks = _recommended_checks(prior, active_confounders)
    insight_id = f"water-{_slug(prior.prior_id)}-{_slug(_finding_id(finding, finding_index))}"
    what_changed = _what_changed(prior, finding)
    why_matters = _why_it_matters(prior)
    return {
        "id": insight_id,
        "title": f"Water interpretation: {prior.name}",
        "severity": _severity_from_finding(finding),
        "confidence": confidence["overall"],
        "confidence_rationale": confidence["explanation"],
        "sii_finding_id": _finding_id(finding, finding_index),
        "affected_system": affected_system,
        "affected_systems": [affected_system],
        "affected_assets": _affected_assets(prior, context, signal_matches),
        "relationship_prior_id": prior.prior_id,
        "relationship_prior_version": prior.version,
        "operating_mode": _operating_mode(context),
        "graph_trust": graph_trust,
        "first_detected_at": first_detected,
        "last_observed_at": last_observed,
        "status": HYPOTHESIS_OBSERVED,
        "hypothesis_state": HYPOTHESIS_OBSERVED,
        "observed_evidence": observed_evidence,
        "derived_metrics": derived_metrics,
        "possible_explanations": explanations,
        "confounding_conditions": active_confounders,
        "recommended_checks": checks,
        "confidence_and_uncertainty": confidence,
        "water_interpretation": {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, "prior": prior.as_dict(), "strict_separation": {"observed_evidence": "Observed SII relationship drift and source telemetry context.", "possible_explanations": "Hypotheses to investigate; not confirmed causes.", "confirmation": "Telemetry alone never sets operator_confirmed."}},
        "what_changed": what_changed,
        "what_happened": what_changed,
        "why_it_matters": why_matters,
        "why_neraium_thinks_it_happened": "SII detected relationship drift; Water Intelligence mapped the affected signals to a conditional water-system prior without assigning a confirmed cause.",
        "possible_operational_consequence": why_matters,
        "possible_operational_causes": [item["explanation"] for item in explanations],
        "likely_causes": [item["explanation"] for item in explanations],
        "recommended_operator_check": checks[0]["check"] if checks else None,
        "recommended_investigation": [item["check"] for item in checks],
        "operator_check": checks[0]["check"] if checks else None,
        "evidence_summary": [item["summary"] for item in observed_evidence],
        "evidence_items": observed_evidence,
        "evidence": observed_evidence,
        "contributing_relationships": [_relationship_contribution(finding, signal_matches)],
        "source_tags": _finding_columns(finding),
        "source_time_ranges": _source_time_ranges(finding),
        "time_window": finding.get("time_window"),
        "upload_id": context.upload_id,
        "analysis_id": context.analysis_id,
    }


def _required_dimensions() -> dict[str, str | None]:
    dimensions: dict[str, str | None] = {}
    for prior in water_priors():
        for signal, requirement in prior.unit_requirements().items():
            dimensions.setdefault(signal, requirement.dimension)
    return dimensions


def _sii_relationship_findings(context: WaterIntelligenceContext) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if isinstance(context.relationship_model, dict):
        for source_key in ("top_relationship_changes", "baseline_relationships"):
            for item in context.relationship_model.get(source_key, []) or []:
                if isinstance(item, dict):
                    findings.append({**item, "sii_source": f"relationship_model.{source_key}"})
        graph = context.relationship_model.get("relationship_graph")
        if isinstance(graph, dict):
            for item in graph.get("changed_edges", []) or []:
                if isinstance(item, dict):
                    findings.append({**item, "sii_source": "relationship_model.relationship_graph.changed_edges"})
    if isinstance(context.engine_result, dict):
        for item in context.engine_result.get("evidence", []) or []:
            if isinstance(item, dict) and item.get("type") == "relationship_change":
                findings.append({**item, "sii_source": "engine_result.evidence"})
    return _dedupe_findings(findings)


def _dedupe_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for index, item in enumerate(findings):
        columns = _finding_columns(item)
        column_key = "cols:" + "|".join(sorted(columns)) if columns else ""
        explicit_key = str(item.get("id") or item.get("relationship") or "")
        key = column_key or explicit_key or f"finding-{index}"
        if key in seen:
            continue
        seen.add(key)
        if explicit_key:
            seen.add("id:" + explicit_key)
        deduped.append(item)
    return deduped


def _prior_applicability(prior: RelationshipPrior, context: WaterIntelligenceContext, signal_matches: dict[str, list[SignalMatch]]) -> dict[str, Any]:
    missing = sorted(signal for signal in prior.required_signal_names if not signal_matches.get(signal))
    invalid_conditions: list[str] = []
    for signal_name in prior.required_signal_names:
        for match in signal_matches.get(signal_name, []):
            if match.unit_status == "incompatible":
                invalid_conditions.append(f"incompatible_unit:{signal_name}:{match.source_column}")
    mode = _operating_mode(context)
    if mode not in prior.valid_operating_modes:
        invalid_conditions.append(f"invalid_operating_mode:{mode}")
    applicable = not missing and not invalid_conditions
    return {"applicable": applicable, "reason": "Applicable" if applicable else "Prior applicability requirements were not met.", "missing_required_signals": missing, "invalid_conditions": invalid_conditions, "matched_required_signals": sorted(prior.required_signal_names - set(missing))}


def _relevant_findings(prior: RelationshipPrior, findings: list[dict[str, Any]], signal_matches: dict[str, list[SignalMatch]]) -> list[dict[str, Any]]:
    relevant_columns = columns_for_signals(signal_matches, prior.all_signal_names)
    relevant: list[dict[str, Any]] = []
    for finding in findings:
        columns = set(_finding_columns(finding))
        finding_signals = _finding_signal_names(finding, signal_matches)
        if prior.prior_id == "water.cooling_tower_mass_balance":
            if signal_matches.get("makeup_flow") and (columns & relevant_columns or len(signal_matches) >= 2):
                relevant.append(finding)
        elif len(finding_signals & prior.all_signal_names) >= 2 and prior.required_signal_names.issubset(set(signal_matches)):
            relevant.append(finding)
    return relevant


def _finding_signal_names(finding: dict[str, Any], signal_matches: dict[str, list[SignalMatch]]) -> set[str]:
    columns = set(_finding_columns(finding))
    return {signal_name for signal_name, matches in signal_matches.items() if any(match.source_column in columns for match in matches)}


def _explicit_graph_trust(finding: dict[str, Any]) -> str | None:
    raw = str(finding.get("graph_trust") or finding.get("trust_state") or finding.get("edge_trust") or "").strip().lower()
    if raw in {GRAPH_TRUST_TRUSTED, "trusted_edge", "operator_validated", "validated"}:
        return GRAPH_TRUST_TRUSTED
    if raw in {GRAPH_TRUST_PROPOSED, "candidate", "awaiting_confirmation"}:
        return GRAPH_TRUST_PROPOSED
    if raw in {GRAPH_TRUST_SPECULATIVE, "correlation_only", "weak"}:
        return GRAPH_TRUST_SPECULATIVE
    topology_source = str(finding.get("topology_source") or finding.get("validated_source") or "").lower()
    if topology_source in {"operator", "p&id", "pid", "p_and_id", "validated", "validated_source"} or finding.get("operator_confirmed") is True:
        return GRAPH_TRUST_TRUSTED
    return None


def _graph_evidence_types(finding: dict[str, Any], prior: RelationshipPrior, matched_signal_names: set[str], context: WaterIntelligenceContext) -> set[str]:
    evidence_types: set[str] = set()
    if any(key in finding for key in ("correlation_delta", "baseline_correlation", "recent_correlation", "strength", "change")):
        evidence_types.add("statistical_association")
    if matched_signal_names & prior.all_signal_names:
        evidence_types.add("tag_semantics")
    if finding.get("source_column_metadata") or finding.get("supporting_metric_pairs"):
        evidence_types.add("asset_or_signal_metadata")
    if finding.get("time_window") or finding.get("source_rows"):
        evidence_types.add("temporal_context")
    if prior.required_signal_names.issubset(_contextual_signal_names(context) | matched_signal_names):
        evidence_types.add("engineering_plausibility")
    if _operating_mode(context) != "unknown":
        evidence_types.add("operating_state_alignment")
    if context.asset_metadata or context.asset_id:
        evidence_types.add("asset_metadata")
    topology_source = str(finding.get("topology_source") or finding.get("validated_source") or "").lower()
    if topology_source in {"operator", "p&id", "pid", "p_and_id", "validated", "validated_source"}:
        evidence_types.add("validated_topology")
    if finding.get("operator_confirmed") is True:
        evidence_types.add("operator_confirmation")
    if not evidence_types and _finding_columns(finding):
        evidence_types.add("statistical_association")
    return evidence_types


def _contextual_signal_names(context: WaterIntelligenceContext) -> set[str]:
    matches = match_water_signals(columns=context.columns, telemetry_signal_catalog=context.telemetry_signal_catalog, required_dimensions=_required_dimensions())
    return {match.canonical for group in matches.values() for match in group}


def _active_confounders(prior: RelationshipPrior, context: WaterIntelligenceContext, signal_matches: dict[str, list[SignalMatch]], finding: dict[str, Any]) -> list[dict[str, Any]]:
    warning_text = " ".join(str(item) for item in _warnings(context)).lower()
    conditions: list[dict[str, Any]] = []
    for confounder in prior.known_confounders:
        normalized = confounder.lower()
        active = False
        source = "known_prior"
        if "timestamp" in normalized and any(token in warning_text for token in ("timestamp", "alignment", "irregular", "inconsistent")):
            active = True; source = "data_quality"
        elif "valve" in normalized and signal_matches.get("valve_position"):
            active = True; source = "supporting_signal_present"
        elif "bypass" in normalized and signal_matches.get("bypass_state"):
            active = True; source = "supporting_signal_present"
        elif "staging" in normalized and signal_matches.get("pump_stage"):
            active = True; source = "supporting_signal_present"
        elif "backwash" in normalized and (signal_matches.get("backwash_event") or _operating_mode(context) == "backwash"):
            active = True; source = "supporting_signal_present"
        elif "maintenance" in normalized and (signal_matches.get("backwash_event") or "maintenance" in warning_text):
            active = True; source = "supporting_signal_present"
        elif "unmeasured" in normalized and prior.prior_id == "water.cooling_tower_mass_balance":
            active = True; source = "missing_balance_term"
        elif "conductivity" in normalized and prior.prior_id == "water.cooling_tower_mass_balance":
            active = _conductivity_confounder_active(context, signal_matches); source = "conductivity_context"
        conditions.append({"condition": confounder, "state": "active" if active else "possible", "source": source, "confidence_effect": "reduces" if active else "context", "explanation": f"{confounder} {'is active or directly indicated' if active else 'is a known confounder to check before confirming a cause'}."})
    for signal_name, matches in signal_matches.items():
        for match in matches:
            if match.unit_status in {"unknown", "incompatible"}:
                conditions.append({"condition": f"unit validation for {signal_name}", "state": match.unit_status, "source": match.source_column, "confidence_effect": "reduces" if match.unit_status == "unknown" else "invalidates", "explanation": f"{match.source_column} unit status is {match.unit_status}; incompatible units are not silently calculated."})
    if _finding_timestamp_misaligned(finding, context):
        conditions.append({"condition": "timestamp misalignment", "state": "active", "source": "time_window", "confidence_effect": "reduces", "explanation": "SII evidence includes timestamp or sampling warnings, so lag alignment must be checked."})
    return _dedupe_dicts(conditions, key="condition")


def _conductivity_confounder_active(context: WaterIntelligenceContext, signal_matches: dict[str, list[SignalMatch]]) -> bool:
    tracer = context.config.get("conductivity_tracer") if isinstance(context.config, dict) else {}
    if not signal_matches.get("makeup_conductivity") or not signal_matches.get("circulating_conductivity"):
        return True
    if not isinstance(tracer, dict):
        return True
    required = ("makeup_conductivity_stable", "circulating_conductivity_reliable", "chemistry_tracer_valid", "sampling_points_and_timing_valid")
    return not all(tracer.get(key) is True for key in required)


def _derived_metrics(prior: RelationshipPrior, signal_matches: dict[str, list[SignalMatch]], context: WaterIntelligenceContext, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    if prior.prior_id == "water.pump_hydraulic_behavior":
        return _pump_metrics(signal_matches, context)
    if prior.prior_id == "water.chilled_water_thermal_behavior":
        return _chilled_water_metrics(signal_matches, context)
    if prior.prior_id == "water.filter_differential_pressure":
        return _filter_metrics(signal_matches, context)
    if prior.prior_id == "water.cooling_tower_mass_balance":
        return _tower_mass_balance_metrics(signal_matches, context, parameters)
    return []


def _pump_metrics(signal_matches: dict[str, list[SignalMatch]], context: WaterIntelligenceContext) -> list[dict[str, Any]]:
    flow = _window_stat(signal_matches, context, "flow")
    dp = _window_stat(signal_matches, context, "differential_pressure")
    power = _window_stat(signal_matches, context, "pump_power")
    if flow and dp and flow.get("current_average") is not None and dp.get("current_average") is not None:
        baseline_proxy = _product(flow.get("baseline_average"), dp.get("baseline_average"))
        current_proxy = _product(flow.get("current_average"), dp.get("current_average"))
        metrics = [_metric(name="hydraulic_output_proxy", formula="flow * differential_pressure", known_inputs=[flow, dp], value=current_proxy, baseline_value=baseline_proxy, normalized_unit=f"{flow.get('normalized_unit')}*{dp.get('normalized_unit')}", explanation="Hydraulic output proxy is kept separate from electrical input; no fixed pump, motor, or drive efficiency is assumed.")]
        if power and power.get("current_average") is not None and current_proxy not in {None, 0}:
            baseline_ratio = round(float(power["baseline_average"]) / float(baseline_proxy), 6) if baseline_proxy not in {None, 0} and power.get("baseline_average") is not None else None
            metrics.append(_metric(name="electrical_input_per_hydraulic_proxy", formula="pump_power / (flow * differential_pressure)", known_inputs=[power, flow, dp], value=round(float(power["current_average"]) / float(current_proxy), 6), baseline_value=baseline_ratio, normalized_unit=f"{power.get('normalized_unit')}/({flow.get('normalized_unit')}*{dp.get('normalized_unit')})", explanation="This is a comparison proxy only, not pump efficiency."))
        return metrics
    return [_unknown_metric("hydraulic_output_proxy", "Flow and differential pressure values are not both identifiable from normalized telemetry.")]


def _chilled_water_metrics(signal_matches: dict[str, list[SignalMatch]], context: WaterIntelligenceContext) -> list[dict[str, Any]]:
    supply = _window_stat(signal_matches, context, "supply_temperature")
    ret = _window_stat(signal_matches, context, "return_temperature")
    flow = _window_stat(signal_matches, context, "flow")
    delta = _window_stat(signal_matches, context, "delta_t")
    metrics: list[dict[str, Any]] = []
    if supply and ret and supply.get("current_average") is not None and ret.get("current_average") is not None:
        baseline_delta = _subtract(ret.get("baseline_average"), supply.get("baseline_average"))
        current_delta = _subtract(ret.get("current_average"), supply.get("current_average"))
        metrics.append(_metric(name="derived_delta_t", formula="return_temperature - supply_temperature", known_inputs=[supply, ret], value=current_delta, baseline_value=baseline_delta, normalized_unit="degF", explanation="Delta-T is derived from supply/return temperatures and remains sensitive to sensor location and flow direction."))
    elif delta:
        metrics.append(_metric(name="reported_delta_t", formula="reported delta_t", known_inputs=[delta], value=delta.get("current_average"), baseline_value=delta.get("baseline_average"), normalized_unit=delta.get("normalized_unit"), explanation="Reported delta-T is used as supplied after unit validation."))
    if flow and metrics and metrics[0].get("value") is not None and flow.get("current_average") is not None:
        metrics.append(_metric(name="thermal_load_proxy", formula="flow * delta_t", known_inputs=[flow, metrics[0]], value=_product(flow.get("current_average"), metrics[0].get("value")), baseline_value=_product(flow.get("baseline_average"), metrics[0].get("baseline_value")), normalized_unit=f"{flow.get('normalized_unit')}*degF", explanation="This is a thermal pickup proxy and not a confirmed load calculation unless fluid assumptions are validated."))
    return metrics or [_unknown_metric("chilled_water_thermal_metrics", "Supply, return, flow, or delta-T values are incomplete.")]


def _filter_metrics(signal_matches: dict[str, list[SignalMatch]], context: WaterIntelligenceContext) -> list[dict[str, Any]]:
    dp = _window_stat(signal_matches, context, "filter_differential_pressure")
    flow = _window_stat(signal_matches, context, "flow")
    if not dp or not flow:
        return [_unknown_metric("filter_flow_normalized_context", "Filter differential pressure and flow are not both available.")]
    flow_change = _relative_change(flow.get("baseline_average"), flow.get("current_average"))
    dp_change = _relative_change(dp.get("baseline_average"), dp.get("current_average"))
    similar = flow_change is not None and abs(flow_change) <= 0.1
    return [_metric(name="filter_dp_at_comparable_flow_context", formula="site-specific SII baseline comparison; no universal dP-flow squared model is assumed", known_inputs=[dp, flow], value={"flow_relative_change": flow_change, "differential_pressure_relative_change": dp_change, "similar_flow": similar}, baseline_value=None, normalized_unit=None, explanation="A differential-pressure rise at similar flow can support a restriction/loading hypothesis, but does not confirm filter loading." if similar else "Flow is not similar enough for a simple flow-normalized comparison; use the SII state-conditioned baseline.")]


def _tower_mass_balance_metrics(signal_matches: dict[str, list[SignalMatch]], context: WaterIntelligenceContext, parameters: dict[str, Any]) -> list[dict[str, Any]]:
    makeup = _window_stat(signal_matches, context, "makeup_flow")
    if not makeup or makeup.get("current_average") is None:
        return [_unknown_metric("cooling_tower_mass_balance", "Makeup flow is required and not identifiable.")]
    term_names = ("evaporation_flow", "blowdown_flow", "drift_flow", "leak_flow", "overflow_flow", "storage_change")
    known_terms = []
    missing_terms = []
    for term in term_names:
        stat = _window_stat(signal_matches, context, term)
        if stat and stat.get("current_average") is not None:
            known_terms.append(stat)
        else:
            missing_terms.append(term)
    known_total = sum(float(term["current_average"]) for term in known_terms)
    residual = round(float(makeup["current_average"]) - known_total, 6)
    sensor_uncertainty = float(parameters.get("sensor_uncertainty_fraction") or 0.05)
    model_uncertainty = float(parameters.get("model_uncertainty_fraction") or 0.2)
    uncertainty = abs(residual) * (sensor_uncertainty + model_uncertainty)
    return [{"name": "unmeasured_outflow", "formula": "makeup - measured_evaporation - measured_blowdown - measured_drift - measured_leaks - measured_overflow - measured_storage_change", "known_inputs": [makeup, *known_terms], "missing_inputs": missing_terms, "value": residual, "source_units": [item.get("source_unit") for item in [makeup, *known_terms] if item.get("source_unit")], "normalized_unit": makeup.get("normalized_unit"), "conversion_applied": [item.get("conversion_applied") for item in [makeup, *known_terms] if item.get("conversion_applied")], "calculation_version": "water.mass_balance.residual.v1", "sensor_uncertainty": {"fraction": sensor_uncertainty, "basis": "configurable default unless site/asset override supplies a value"}, "model_uncertainty": {"fraction": model_uncertainty, "basis": "residual combines non-identifiable terms"}, "uncertainty_range": [round(residual - uncertainty, 6), round(residual + uncertainty, 6)], "identifiability": "not_separable" if missing_terms else "separable_for_measured_terms", "explanation": "Individual evaporation, blowdown, drift, leakage, overflow, and storage components cannot be separated without enough independent measurements.", "conductivity_cycles_supporting_evidence": _conductivity_support(signal_matches, context)}]


def _conductivity_support(signal_matches: dict[str, list[SignalMatch]], context: WaterIntelligenceContext) -> dict[str, Any]:
    tracer = context.config.get("conductivity_tracer") if isinstance(context.config, dict) else {}
    conditions = {"makeup_conductivity_stable": bool(isinstance(tracer, dict) and tracer.get("makeup_conductivity_stable") is True), "circulating_conductivity_reliable": bool(isinstance(tracer, dict) and tracer.get("circulating_conductivity_reliable") is True), "chemistry_tracer_valid": bool(isinstance(tracer, dict) and tracer.get("chemistry_tracer_valid") is True), "sampling_points_and_timing_valid": bool(isinstance(tracer, dict) and tracer.get("sampling_points_and_timing_valid") is True)}
    return {"eligible": bool(signal_matches.get("makeup_conductivity") and signal_matches.get("circulating_conductivity") and all(conditions.values())), "role": "supporting_only", "conditions": conditions, "chemical_feed_pump_note": "A chemical-feed pump running does not automatically invalidate conductivity cycles; treatment chemistry must be reviewed for tracer validity."}


def _confidence_dimensions(*, prior: RelationshipPrior, finding: dict[str, Any], context: WaterIntelligenceContext, signal_matches: dict[str, list[SignalMatch]], graph_trust: dict[str, Any], active_confounders: list[dict[str, Any]], derived_metrics: list[dict[str, Any]], applicability: dict[str, Any]) -> dict[str, dict[str, Any]]:
    dimensions = empty_confidence_dimensions()
    sii_score = _sii_score(finding)
    dimensions["sii_finding_strength"] = {"state": _score_state(sii_score), "score": sii_score, "explanation": "SII relationship finding strength was preserved from the generic engine output."}
    bad_units = [item for matches in signal_matches.values() for item in matches if item.unit_status in {"unknown", "incompatible"}]
    signal_score = 0.85
    if bad_units:
        signal_score = 0.45 if any(item.unit_status == "incompatible" for item in bad_units) else 0.6
    if str((context.data_quality or {}).get("readiness") or "ready").lower() == "not_ready":
        signal_score = min(signal_score, 0.35)
    dimensions["signal_quality"] = {"state": _score_state(signal_score), "score": signal_score, "explanation": "Signal quality reflects data readiness plus unit validation and normalization status."}
    applicability_score = 0.85 if applicability.get("applicable") else 0.2
    dimensions["prior_applicability"] = {"state": _score_state(applicability_score), "score": applicability_score, "explanation": "Prior applicability is based on required water signals, valid operating mode, and invalidation checks."}
    optional_present = len([name for name in prior.optional_signal_names if signal_matches.get(name)])
    optional_total = max(1, len(prior.optional_signal_names))
    context_score = min(0.9, 0.35 + (optional_present / optional_total) * 0.45 + (0.1 if _operating_mode(context) != "unknown" else 0.0))
    dimensions["context_completeness"] = {"state": _score_state(context_score), "score": round(context_score, 4), "explanation": "Context completeness reflects operating mode and supporting signals such as valves, staging, maintenance, or chemistry context."}
    graph_score = {GRAPH_TRUST_TRUSTED: 0.9, GRAPH_TRUST_PROPOSED: 0.65, GRAPH_TRUST_SPECULATIVE: 0.2}.get(graph_trust.get("tier"), 0.2)
    dimensions["graph_trust"] = {"state": str(graph_trust.get("tier") or GRAPH_TRUST_SPECULATIVE), "score": graph_score, "explanation": graph_trust.get("explanation")}
    supporting_score = 0.45 + (0.2 if finding.get("evidence_refs") or finding.get("source_rows") else 0.0) + min(0.25, optional_present * 0.06)
    dimensions["supporting_evidence"] = {"state": _score_state(supporting_score), "score": round(min(0.9, supporting_score), 4), "explanation": "Supporting evidence reflects SII evidence references, source rows, and available supporting water context."}
    active_count = len([item for item in active_confounders if item.get("state") == "active"])
    dimensions["confounder_severity"] = {"state": "low" if active_count == 0 else ("medium" if active_count <= 2 else "high"), "score": round(0.9 if active_count == 0 else max(0.25, 0.75 - active_count * 0.12), 4), "explanation": "Active confounders reduce confidence until operators separate operating context, instrumentation, or topology effects."}
    high_uncertainty = any(metric.get("identifiability") == "not_separable" for metric in derived_metrics)
    dimensions["model_or_residual_uncertainty"] = {"state": "high" if high_uncertainty else "medium", "score": 0.35 if high_uncertainty else 0.75, "explanation": "Residual/model uncertainty is high when balance terms or derived components are not independently identifiable."}
    return {name: dimensions[name] for name in CONFIDENCE_DIMENSIONS}


def _observed_evidence(prior: RelationshipPrior, finding: dict[str, Any], signal_matches: dict[str, list[SignalMatch]], graph_trust: dict[str, Any], context: WaterIntelligenceContext) -> list[dict[str, Any]]:
    columns = _finding_columns(finding)
    return [{"type": "observed_sii_relationship_drift", "summary": finding.get("summary") or finding.get("what_changed") or f"SII reported relationship drift involving {', '.join(columns)}.", "source": finding.get("sii_source"), "source_columns": columns, "matched_water_signals": sorted(_finding_signal_names(finding, signal_matches)), "relationship_type": finding.get("relationship_type"), "change_type": finding.get("change_type"), "baseline_strength": finding.get("baseline_strength"), "current_strength": finding.get("current_strength") or finding.get("strength"), "correlation_delta": finding.get("correlation_delta") or finding.get("change"), "sii_confidence": _sii_confidence(finding), "graph_trust": graph_trust, "time_window": finding.get("time_window") or _build_time_window(context), "source_rows": finding.get("source_rows"), "evidence_refs": finding.get("evidence_refs"), "separation": "observed_evidence"}]


def _possible_explanations(prior: RelationshipPrior, derived_metrics: list[dict[str, Any]], active_confounders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    context_text = " ".join(str(item.get("condition") or "") for item in active_confounders if item.get("state") == "active") + " " + " ".join(str(item.get("name") or "") + " " + str(item.get("explanation") or "") for item in derived_metrics)
    tokens = _tokens(context_text)
    return [{"explanation": explanation, "hypothesis_state": "supported" if _tokens(explanation) & tokens else HYPOTHESIS_SUSPECTED, "confirmation_state": "not_confirmed", "separation": "hypothesis", "note": "This is a possible operational explanation to investigate, not a confirmed cause."} for explanation in prior.possible_explanations]


def _recommended_checks(prior: RelationshipPrior, active_confounders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks = [{"check": check, "purpose": "Separate observed relationship drift from possible causes before confirmation.", "confirmation_required": "operator confirmation, physical inspection, maintenance/work-order evidence, validated diagnostic test, or authoritative equipment/control event", "separation": "recommended_check"} for check in prior.recommended_checks]
    checks.extend({"check": f"Resolve or document confounder: {item.get('condition')}.", "purpose": item.get("explanation"), "confirmation_required": "operator review", "separation": "recommended_check"} for item in active_confounders if item.get("state") == "active")
    return _dedupe_dicts(checks, key="check")[:8]


def _window_stat(signal_matches: dict[str, list[SignalMatch]], context: WaterIntelligenceContext, signal_name: str) -> dict[str, Any] | None:
    match = best_signal(signal_matches, signal_name)
    if match is None:
        return None
    records = (context.normalized_telemetry or {}).get("records", []) if isinstance(context.normalized_telemetry, dict) else []
    values: list[float] = []
    for record in records:
        if not isinstance(record, dict) or str(record.get("source_column")) != match.source_column:
            continue
        try:
            numeric = float(record.get("value"))
        except (TypeError, ValueError):
            continue
        unit_result = normalize_unit(value=numeric, source_unit=record.get("unit") or match.source_unit, expected_dimension=match.unit_dimension)
        if unit_result.get("status") == "ok" and unit_result.get("normalized_value") is not None:
            values.append(float(unit_result["normalized_value"]))
    base = {"signal": signal_name, "source_column": match.source_column, "source_unit": match.source_unit, "normalized_unit": match.normalized_unit, "conversion_applied": match.conversion_applied, "record_count": len(values), "calculation_version": "water.window_stat.v1"}
    if not values:
        return {**base, "baseline_average": None, "current_average": None}
    split = max(1, int(len(values) * 0.7))
    baseline_values = values[:split]
    current_values = values[split:] or values[-max(1, len(values) // 3):]
    return {**base, "baseline_average": round(sum(baseline_values) / len(baseline_values), 6), "current_average": round(sum(current_values) / len(current_values), 6)}


def _metric(*, name: str, formula: str, known_inputs: list[dict[str, Any]], value: Any, baseline_value: Any, normalized_unit: str | None, explanation: str) -> dict[str, Any]:
    return {"name": name, "formula": formula, "known_inputs": known_inputs, "missing_inputs": [], "value": value, "baseline_value": baseline_value, "normalized_unit": normalized_unit, "source_units": [item.get("source_unit") for item in known_inputs if isinstance(item, dict) and item.get("source_unit")], "conversion_applied": [item.get("conversion_applied") for item in known_inputs if isinstance(item, dict) and item.get("conversion_applied")], "calculation_version": "water.derived_metric.v1", "explanation": explanation, "separation": "derived"}


def _unknown_metric(name: str, reason: str) -> dict[str, Any]:
    return {"name": name, "known": "unknown", "reason": reason, "formula": None, "known_inputs": [], "missing_inputs": ["independent measurements or normalized telemetry values"], "calculation_version": "water.derived_metric.v1", "separation": "derived"}


def _resolved_prior_parameters(prior: RelationshipPrior, context: WaterIntelligenceContext) -> dict[str, Any]:
    merged = dict(prior.parameters)
    config = context.config if isinstance(context.config, dict) else {}
    _deep_update(merged, config.get("prior_overrides", {}).get(prior.prior_id, {}) if isinstance(config.get("prior_overrides"), dict) else {})
    for scope_name, scope_id in (("site_overrides", context.site_id), ("system_overrides", context.system_id), ("asset_overrides", context.asset_id), ("operating_mode_overrides", _operating_mode(context))):
        scope = config.get(scope_name)
        if isinstance(scope, dict) and scope_id and isinstance(scope.get(scope_id), dict):
            scoped = scope[scope_id]
            _deep_update(merged, scoped.get(prior.prior_id, {}) if isinstance(scoped.get(prior.prior_id), dict) else {})
            _deep_update(merged, scoped.get("*", {}) if isinstance(scoped.get("*"), dict) else {})
    return merged


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _finding_columns(finding: dict[str, Any]) -> list[str]:
    columns: list[str] = []
    for key in ("columns", "source_tags"):
        if isinstance(finding.get(key), list):
            columns.extend(str(item) for item in finding.get(key, []) if str(item or "").strip())
    for pair in finding.get("supporting_metric_pairs", []) or []:
        if isinstance(pair, dict):
            columns.extend(str(pair.get(key)) for key in ("left", "right") if pair.get(key))
    for ref in finding.get("evidence_refs", []) or []:
        if isinstance(ref, dict) and ref.get("column"):
            columns.append(str(ref.get("column")))
    relationship = str(finding.get("relationship") or "")
    if "<->" in relationship:
        columns.extend(part.strip() for part in relationship.split("<->") if part.strip())
    for key in ("source", "target"):
        value = str(finding.get(key) or "")
        if value.startswith("metric:"):
            columns.append(value.replace("metric:", "", 1))
    return list(dict.fromkeys(columns))


def _finding_id(finding: dict[str, Any], fallback_index: int) -> str:
    return str(finding.get("id") or finding.get("relationship") or "-".join(_finding_columns(finding)) or f"sii-finding-{fallback_index}")


def _sii_confidence(finding: dict[str, Any]) -> Any:
    return finding.get("confidence_score", finding.get("confidence", finding.get("confidence_level")))


def _sii_score(finding: dict[str, Any]) -> float:
    for key in ("confidence_score", "confidence", "correlation_delta", "change"):
        try:
            score = abs(float(finding.get(key)))
        except (TypeError, ValueError):
            continue
        if score > 1.0 and score <= 100.0:
            score /= 100.0
        return max(0.0, min(1.0, score))
    return 0.45


def _score_state(score: float) -> str:
    if score >= 0.72:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _severity_from_finding(finding: dict[str, Any]) -> str:
    score = _sii_score(finding)
    return "high" if score >= 0.8 else "moderate" if score >= 0.45 else "low"


def _operating_mode(context: WaterIntelligenceContext) -> str:
    mode = context.operating_mode
    if not mode and isinstance(context.asset_metadata, dict):
        mode = context.asset_metadata.get("operating_mode")
    if not mode and isinstance(context.data_quality, dict):
        mode = context.data_quality.get("operating_mode")
    return str(mode or "unknown").strip().lower().replace(" ", "_")


def _warnings(context: WaterIntelligenceContext) -> list[Any]:
    warnings: list[Any] = []
    for payload in (context.data_quality, context.timestamp_profile, context.baseline_analysis):
        if isinstance(payload, dict) and isinstance(payload.get("warnings"), list):
            warnings.extend(payload.get("warnings") or [])
    return warnings


def _finding_timestamp_misaligned(finding: dict[str, Any], context: WaterIntelligenceContext) -> bool:
    text = " ".join(str(item) for item in _warnings(context)).lower()
    return any(token in text for token in ("timestamp misalignment", "misaligned", "irregular sampling", "inconsistent"))


def _finding_times(finding: dict[str, Any], context: WaterIntelligenceContext) -> tuple[Any, Any]:
    window = finding.get("time_window") if isinstance(finding.get("time_window"), dict) else {}
    first = window.get("current_start") or window.get("baseline_start")
    last = window.get("current_end") or window.get("baseline_end")
    if first or last:
        return first, last
    built = _build_time_window(context)
    return built.get("start"), built.get("end")


def _build_time_window(context: WaterIntelligenceContext) -> dict[str, Any]:
    profile = context.timestamp_profile or {}
    return {"start": profile.get("first_timestamp") if isinstance(profile, dict) else None, "end": profile.get("last_timestamp") if isinstance(profile, dict) else None}


def _source_time_ranges(finding: dict[str, Any]) -> list[dict[str, Any]]:
    return [finding["time_window"]] if isinstance(finding.get("time_window"), dict) else []


def _affected_system(prior: RelationshipPrior) -> str:
    return {"water.pump_hydraulic_behavior": "Pumping", "water.chilled_water_thermal_behavior": "Chilled water loop", "water.filter_differential_pressure": "Filtration", "water.cooling_tower_mass_balance": "Cooling tower"}.get(prior.prior_id, "Water system")


def _affected_assets(prior: RelationshipPrior, context: WaterIntelligenceContext, signal_matches: dict[str, list[SignalMatch]]) -> list[dict[str, Any]]:
    if context.asset_id:
        return [{"asset_id": context.asset_id, "asset_class": (prior.applicable_asset_classes or ("water_asset",))[0]}]
    assets = []
    for signal in sorted(prior.all_signal_names):
        for match in signal_matches.get(signal, [])[:1]:
            assets.append({"asset_class": (prior.applicable_asset_classes or ("water_asset",))[0], "signal": signal, "source_column": match.source_column})
    return assets[:6]


def _relationship_contribution(finding: dict[str, Any], signal_matches: dict[str, list[SignalMatch]]) -> dict[str, Any]:
    columns = _finding_columns(finding)
    return {"id": _finding_id(finding, 0), "columns": columns, "display_columns": columns, "matched_water_signals": sorted(_finding_signal_names(finding, signal_matches)), "relationship_type": finding.get("relationship_type"), "change_type": finding.get("change_type"), "baseline_strength": finding.get("baseline_strength"), "current_strength": finding.get("current_strength") or finding.get("strength"), "correlation_delta": finding.get("correlation_delta") or finding.get("change")}


def _what_changed(prior: RelationshipPrior, finding: dict[str, Any]) -> str:
    columns = ", ".join(_finding_columns(finding))
    return f"SII observed relationship drift involving {columns}; Water Intelligence mapped it to {prior.name}." if columns else f"SII observed relationship drift; Water Intelligence mapped it to {prior.name}."


def _why_it_matters(prior: RelationshipPrior) -> str:
    if prior.prior_id == "water.cooling_tower_mass_balance":
        return "An unresolved cooling-tower balance can indicate combined unmeasured outflow, but individual loss terms are not identifiable without more measurements."
    return "The observed relationship changed in a water-system context where operating mode, confounders, and units determine whether the finding warrants investigation."


def _product(left: Any, right: Any) -> float | None:
    try:
        return None if left is None or right is None else round(float(left) * float(right), 6)
    except (TypeError, ValueError):
        return None


def _subtract(left: Any, right: Any) -> float | None:
    try:
        return None if left is None or right is None else round(float(left) - float(right), 6)
    except (TypeError, ValueError):
        return None


def _relative_change(baseline: Any, current: Any) -> float | None:
    try:
        baseline_f = float(baseline)
        current_f = float(current)
        if abs(baseline_f) < 1e-9:
            return None
        return round((current_f - baseline_f) / abs(baseline_f), 6)
    except (TypeError, ValueError):
        return None


def _tokens(text: str) -> set[str]:
    return {token for token in re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split() if len(token) > 3}


def _slug(value: Any) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", str(value or "").strip().lower()).strip("-") or "item"


def _dedupe_dicts(items: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for item in items:
        marker = str(item.get(key) or "")
        if marker in seen:
            continue
        seen.add(marker)
        deduped.append(item)
    return deduped


def _skip(prior: RelationshipPrior, reason: str, missing: list[str], invalid: list[str]) -> dict[str, Any]:
    return {"relationship_prior_id": prior.prior_id, "relationship_prior_version": prior.version, "reason": reason, "missing_required_signals": missing, "invalid_conditions": invalid}
