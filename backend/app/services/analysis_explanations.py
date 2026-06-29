from __future__ import annotations

from typing import Any

from app.services.cumulative_counters import is_cumulative_counter_name


def build_analysis_explanation(result: dict[str, Any]) -> dict[str, Any]:
    baseline = result.get("baseline_analysis") if isinstance(result.get("baseline_analysis"), dict) else {}
    relationship_model = result.get("relationship_model") if isinstance(result.get("relationship_model"), dict) else {}
    if not relationship_model and isinstance(baseline.get("top_relationship_changes"), list):
        relationship_model = {
            "top_relationship_changes": baseline.get("top_relationship_changes", []),
            "baseline_relationships": baseline.get("baseline_relationships", []),
            "relationship_graph": baseline.get("relationship_graph", {}),
        }
    operator_report = result.get("operator_report") if isinstance(result.get("operator_report"), dict) else {}
    intelligence = result.get("sii_intelligence") if isinstance(result.get("sii_intelligence"), dict) else {}
    interpretation = result.get("system_interpretation") if isinstance(result.get("system_interpretation"), dict) else {}

    insights = build_insights(
        baseline=baseline,
        relationship_model=relationship_model,
        operator_report=operator_report,
        intelligence=intelligence,
        result=result,
    )
    systems = build_systems(
        baseline=baseline,
        relationship_model=relationship_model,
        intelligence=intelligence,
        interpretation=interpretation,
        result=result,
    )
    relationships = build_relationships(
        relationship_model=relationship_model,
    )
    fingerprint = build_fingerprint(
        baseline=baseline,
        relationship_model=relationship_model,
        intelligence=intelligence,
        result=result,
    )
    evidence = build_evidence(
        insights=insights,
        relationships=relationships,
        baseline=baseline,
        operator_report=operator_report,
        result=result,
    )
    recommendations = build_recommendations(
        insights=insights,
        operator_report=operator_report,
        relationships=relationships,
    )

    return {
        "executive_summary": build_executive_summary(
            insights=insights,
            fingerprint=fingerprint,
            intelligence=intelligence,
            result=result,
            operator_report=operator_report,
        ),
        "systems": systems,
        "relationships": relationships,
        "relationship_graph": relationship_model.get("relationship_graph", {}),
        "insights": insights,
        "fingerprint": fingerprint,
        "evidence": evidence,
        "recommendations": recommendations,
    }


def build_executive_summary(
    *,
    insights: list[dict[str, Any]],
    fingerprint: dict[str, Any],
    intelligence: dict[str, Any],
    result: dict[str, Any],
    operator_report: dict[str, Any],
) -> dict[str, str]:
    top_insight = insights[0] if insights else {}
    status = first_text(
        result.get("operating_state"),
        intelligence.get("facility_state"),
        "Analysis complete",
    )
    recommendation = first_text(
        top_insight.get("recommended_action"),
        result.get("recommended_action"),
        operator_report.get("recommended_action"),
        first_item(operator_report.get("recommended_operator_checks")),
    )
    summary = {
        "overall_operational_status": status,
        "highest_priority_finding": first_text(top_insight.get("title"), top_insight.get("explanation")),
        "biggest_emerging_risk": first_text(top_insight.get("possible_consequence"), fingerprint.get("meaning")),
        "recommended_action": recommendation,
    }
    return {key: value for key, value in summary.items() if value}


def build_insights(
    *,
    baseline: dict[str, Any],
    relationship_model: dict[str, Any],
    operator_report: dict[str, Any],
    intelligence: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []
    persistence = result.get("engine_result", {}).get("persistence_assessment") if isinstance(result.get("engine_result"), dict) else {}
    persistent_columns = set(persistence.get("persistent_columns") or []) if isinstance(persistence, dict) else set()
    time_window = build_time_window(result)
    source_ranges = source_time_ranges(result, time_window)
    upload_id = first_text(result.get("upload_id"), result.get("job_id"), result.get("run_id"))
    analysis_id = first_text(result.get("analysis_id"), result.get("run_id"), upload_id)

    relationship_changes = [
        item for item in relationship_model.get("top_relationship_changes", [])
        if isinstance(item, dict) and not relationship_has_cumulative_counter(item)
    ]
    for index, item in enumerate(relationship_changes[:3]):
        columns = relationship_columns(item)
        label = " / ".join(columns) if columns else str(item.get("relationship") or "Signal relationship")
        system = system_from_columns(columns)
        confidence_score = numeric_confidence_score(
            item.get("confidence_score"),
            sample_confidence_score(item.get("baseline_sample_size"), item.get("recent_sample_size"), item.get("correlation_delta")),
        )
        confidence = confidence_label_from_score(confidence_score)
        relationship_ranges = relationship_source_time_ranges(item, source_ranges)
        evidence_items = relationship_evidence_items(
            item=item,
            label=label,
            time_window=time_window,
            source_ranges=relationship_ranges,
            upload_id=upload_id,
            analysis_id=analysis_id,
            confidence_score=confidence_score,
        )
        what_changed = relationship_observable_sentence(columns, item)
        why = relationship_confidence_basis(label, item)
        persistence_duration = sample_window_phrase(item.get("baseline_sample_size"), item.get("recent_sample_size"))
        insight = compact_dict(
            {
                "id": f"relationship-{index}",
                "title": relationship_title(columns, item),
                "severity": severity_from_number(item.get("correlation_delta")),
                "confidence": confidence,
                "confidence_score": confidence_score,
                "confidence_rationale": confidence_rationale_for_relationship(item, confidence_score),
                "affected_systems": [system],
                "system": system,
                "what_changed": what_changed,
                "explanation": what_changed,
                "why_neraium_thinks_it_happened": why,
                "why_neraium_thinks": why,
                "likely_cause": why,
                "contributing_factors": columns,
                "possible_operational_consequence": "A coupled subsystem may be changing state instead of an isolated sensor moving alone.",
                "possible_consequence": "A coupled subsystem may be changing state instead of an isolated sensor moving alone.",
                "recommended_operator_check": f"Compare {label} timing against operator logs, setpoint changes, and equipment activity for the same window.",
                "recommended_action": relationship_recommended_action(system),
                "operator_check": f"Check whether {label} changed after a known operating mode or equipment state change.",
                "evidence_summary": evidence_summary(evidence_items),
                "evidence_items": evidence_items,
                "evidence": evidence_items,
                "contributing_relationships": [relationship_contribution(item, index, columns)],
                "contributing_metrics": metric_contributions(columns),
                "source_metrics": columns,
                "source_tags": columns,
                "source_time_ranges": relationship_ranges,
                "time_window": time_window,
                "persistence_duration": persistence_duration,
                "upload_id": upload_id,
                "analysis_id": analysis_id,
            }
        )
        insights.append(insight)

    drift_items = [
        item for item in baseline.get("column_drift", [])
        if isinstance(item, dict)
        and item.get("drift_flag") in {"watch", "review"}
        and not is_cumulative_context_item(item)
    ]
    drift_items.sort(key=lambda item: abs(float(item.get("percent_change") or item.get("absolute_change") or 0)), reverse=True)
    for index, item in enumerate(drift_items[: max(0, 5 - len(insights))]):
        column = str(item.get("column") or "Signal")
        direction = str(item.get("direction") or "changed")
        persistent = column in persistent_columns
        persistence_detail = persistence_detail_for_column(persistence if isinstance(persistence, dict) else {}, column)
        confidence_score = metric_confidence_score(item, persistence_detail)
        confidence = confidence_label_from_score(confidence_score)
        system = system_from_columns([column])
        evidence_items = column_evidence_items(
            item=item,
            persistence_detail=persistence_detail,
            time_window=time_window,
            source_ranges=source_ranges,
            upload_id=upload_id,
            analysis_id=analysis_id,
            confidence_score=confidence_score,
        )
        what_changed = metric_change_sentence(item)
        why = metric_confidence_basis(item, persistence_detail)
        operator_check = first_text(
            matching_operator_check(operator_report, column),
            f"Review {column} readings against facility logs for the uploaded period.",
        )
        insights.append(
            compact_dict(
                {
                    "id": f"metric-{index}",
                    "title": metric_title(item),
                    "severity": "high" if item.get("drift_flag") == "review" else "moderate",
                    "confidence": confidence,
                    "confidence_score": confidence_score,
                    "confidence_rationale": confidence_rationale_for_metric(item, persistence_detail, confidence_score),
                    "affected_systems": [system],
                    "system": system,
                    "what_changed": what_changed,
                    "explanation": what_changed,
                    "why_neraium_thinks_it_happened": why,
                    "why_neraium_thinks": why,
                    "likely_cause": why,
                    "contributing_factors": [column],
                    "possible_operational_consequence": "If this persists, the related process may continue moving away from its operating fingerprint.",
                    "possible_consequence": "If this persists, the related process may continue moving away from its operating fingerprint.",
                    "recommended_operator_check": operator_check,
                    "recommended_action": metric_recommended_action(column, item),
                    "operator_check": f"Check source readings, control changes, and maintenance activity involving {column}.",
                    "evidence_summary": evidence_summary(evidence_items),
                    "evidence_items": evidence_items,
                    "evidence": evidence_items,
                    "contributing_metrics": metric_contributions([column], item),
                    "source_metrics": [column],
                    "source_tags": [column],
                    "source_time_ranges": source_ranges,
                    "time_window": time_window,
                    "persistence_duration": persistence_phrase(persistence_detail),
                    "upload_id": upload_id,
                    "analysis_id": analysis_id,
                    "persistent": persistent,
                }
            )
        )

    if not insights and baseline.get("overall_assessment") == "normal":
        confidence_score = baseline_confidence_score(baseline)
        confidence = confidence_label_from_score(confidence_score)
        evidence_items = [
            compact_dict(
                {
                    "id": "baseline-stable-evidence-0",
                    "type": "baseline_context",
                    "summary": "No numeric signal crossed the baseline review threshold in the uploaded analysis.",
                    "supporting_signals": [
                        f"{baseline.get('columns_analyzed')} numeric columns analyzed",
                        f"{baseline.get('baseline_window_rows')} baseline rows",
                        f"{baseline.get('recent_window_rows')} recent rows",
                    ],
                    "relevant_metric_changes": [],
                    "time_window": time_window,
                    "source_time_ranges": source_ranges,
                    "confidence": confidence,
                    "confidence_score": confidence_score,
                    "source_upload_id": upload_id,
                    "analysis_id": analysis_id,
                }
            )
        ]
        title = "Operating fingerprint remains stable"
        insights.append(
            compact_dict(
                {
                    "id": "baseline-stable",
                    "title": title,
                    "severity": "low",
                    "confidence": confidence,
                    "confidence_score": confidence_score,
                    "confidence_rationale": baseline_confidence_rationale(baseline, confidence_score),
                    "affected_systems": [first_text(intelligence.get("primary_room"), "Uploaded telemetry")],
                    "system": first_text(intelligence.get("primary_room"), "Uploaded telemetry"),
                    "what_changed": "No reviewed metric or relationship moved beyond the configured baseline thresholds.",
                    "explanation": "No reviewed metric or relationship moved beyond the configured baseline thresholds.",
                    "why_neraium_thinks_it_happened": "The current window remained close to the baseline window across the numeric columns available in the CSV.",
                    "likely_cause": "The current window remained close to the baseline window across the numeric columns available in the CSV.",
                    "possible_operational_consequence": "Continue normal monitoring unless operator logs show an unmodeled event.",
                    "possible_consequence": "Continue normal monitoring unless operator logs show an unmodeled event.",
                    "recommended_operator_check": first_item(operator_report.get("recommended_operator_checks")),
                    "recommended_action": first_item(operator_report.get("recommended_operator_checks")),
                    "operator_check": first_item(operator_report.get("recommended_operator_checks")),
                    "evidence_summary": evidence_summary(evidence_items),
                    "evidence_items": evidence_items,
                    "evidence": evidence_items,
                    "contributing_metrics": [],
                    "source_time_ranges": source_ranges,
                    "time_window": time_window,
                    "upload_id": upload_id,
                    "analysis_id": analysis_id,
                }
            )
        )

    return insights

def build_systems(
    *,
    baseline: dict[str, Any],
    relationship_model: dict[str, Any],
    intelligence: dict[str, Any],
    interpretation: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    system_map: dict[str, dict[str, Any]] = {}

    def entry(name: str) -> dict[str, Any]:
        clean_name = first_text(name, intelligence.get("primary_room"), "Uploaded telemetry")
        return system_map.setdefault(
            clean_name,
            {
                "id": clean_name.lower().replace(" ", "-").replace("_", "-"),
                "name": clean_name,
                "health_status": first_text(result.get("operating_state"), intelligence.get("facility_state")),
                "confidence": first_text(intelligence.get("confidence"), interpretation.get("confidence")),
                "key_behaviors": [],
                "what_changed": [],
                "relationships": [],
            },
        )

    primary = entry(first_text(intelligence.get("primary_room"), result.get("primary_room"), "Uploaded telemetry"))
    for item in baseline.get("column_drift", []) if isinstance(baseline.get("column_drift"), list) else []:
        if (
            not isinstance(item, dict)
            or item.get("drift_flag") not in {"watch", "review"}
            or is_cumulative_context_item(item)
        ):
            continue
        target = entry(system_from_columns([str(item.get("column") or "")]))
        target["key_behaviors"].append(f"{item.get('column')} is moving {item.get('direction')} against baseline.")
        target["what_changed"].append(change_phrase(item))

    for relationship in relationship_model.get("top_relationship_changes", []) if isinstance(relationship_model.get("top_relationship_changes"), list) else []:
        if not isinstance(relationship, dict) or relationship_has_cumulative_counter(relationship):
            continue
        columns = relationship_columns(relationship)
        target = entry(system_from_columns(columns))
        summary = first_text(relationship.get("summary"), "Signal relationship changed against baseline.")
        target["relationships"].append(summary)
        target["what_changed"].append(summary)

    if not primary["key_behaviors"] and not primary["what_changed"]:
        primary["key_behaviors"].append("Recent behavior stayed close to the baseline operating fingerprint.")

    return [
        compact_system(item)
        for item in system_map.values()
    ]


def build_relationships(
    *,
    relationship_model: dict[str, Any],
) -> list[dict[str, Any]]:
    relationships = []
    changes = relationship_model.get("top_relationship_changes", [])
    if not isinstance(changes, list):
        return relationships

    for index, item in enumerate(changes[:5]):
        if not isinstance(item, dict) or relationship_has_cumulative_counter(item):
            continue
        columns = relationship_columns(item)
        label = " / ".join(columns) if columns else str(item.get("relationship") or "Signal relationship")
        confidence_score = numeric_confidence_score(
            item.get("confidence_score"),
            sample_confidence_score(item.get("baseline_sample_size"), item.get("recent_sample_size"), item.get("correlation_delta")),
        )
        relationships.append(
            compact_dict(
                {
                    "id": f"relationship-{index}",
                    "name": label,
                    "columns": columns,
                    "system": system_from_columns(columns),
                    "relationship_type": item.get("relationship_type"),
                    "change_type": item.get("change_type"),
                    "strength": item.get("strength"),
                    "baseline_strength": item.get("baseline_strength"),
                    "current_strength": item.get("current_strength"),
                    "baseline_correlation": item.get("baseline_correlation"),
                    "recent_correlation": item.get("recent_correlation"),
                    "correlation_delta": item.get("correlation_delta"),
                    "signed_correlation_delta": item.get("signed_correlation_delta"),
                    "change_percentage": item.get("change_percentage"),
                    "direction": item.get("direction"),
                    "coupling_strength": item.get("coupling_strength"),
                    "baseline_sample_size": item.get("baseline_sample_size"),
                    "recent_sample_size": item.get("recent_sample_size"),
                    "confidence": confidence_label_from_score(confidence_score),
                    "confidence_score": confidence_score,
                    "confidence_rationale": confidence_rationale_for_relationship(item, confidence_score),
                    "what_changed": first_text(
                        item.get("summary"),
                        relationship_change_sentence(label, item),
                    ),
                    "why_it_matters": "Coupled signals changing together can reveal a subsystem state change before a single metric explains it.",
                    "operator_check": f"Compare {label} timing against operator logs, setpoint changes, and equipment activity.",
                    "supporting_metric_pairs": item.get("supporting_metric_pairs"),
                    "time_window": item.get("time_window"),
                    "evidence_refs": item.get("evidence_refs"),
                    "source_rows": item.get("source_rows"),
                    "sampled_for_baseline": item.get("sampled_for_baseline"),
                }
            )
        )
    return relationships

def build_fingerprint(
    *,
    baseline: dict[str, Any],
    relationship_model: dict[str, Any],
    intelligence: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    relationship_changes = [
        item for item in (relationship_model.get("top_relationship_changes", []) if isinstance(relationship_model.get("top_relationship_changes"), list) else [])
        if isinstance(item, dict) and not relationship_has_cumulative_counter(item)
    ]
    significant_columns = [
        item for item in baseline.get("column_drift", [])
        if isinstance(item, dict)
        and item.get("drift_flag") in {"watch", "review"}
        and not is_cumulative_context_item(item)
    ]
    largest = largest_deviation(significant_columns, relationship_changes)
    largest_items = largest_deviation_items(significant_columns, relationship_changes)
    assessment = baseline.get("overall_assessment")
    graph = relationship_model.get("relationship_graph") if isinstance(relationship_model.get("relationship_graph"), dict) else baseline.get("relationship_graph", {})
    changed_edges = graph.get("changed_edges", []) if isinstance(graph, dict) and isinstance(graph.get("changed_edges"), list) else []

    if assessment == "normal" and not relationship_changes and not significant_columns:
        meaning = "The operating fingerprint is stable. Current behavior closely matches the baseline window in the uploaded telemetry."
        status = "stable"
    elif relationship_changes or significant_columns or changed_edges:
        meaning = "The operating fingerprint is changing. Recent behavior no longer fully matches the baseline window in the uploaded telemetry."
        status = "changed"
    else:
        meaning = ""
        status = ""
    if largest:
        meaning = f"{meaning} The largest deviation is {largest}.".strip()

    confidence_score = fingerprint_confidence_score(baseline, relationship_changes, significant_columns)
    confidence = confidence_label_from_score(confidence_score)
    source_range = source_time_ranges(result, build_time_window(result))
    evidence = fingerprint_evidence_items(
        baseline=baseline,
        relationship_changes=relationship_changes,
        significant_columns=significant_columns,
        source_ranges=source_range,
        confidence_score=confidence_score,
    )

    return compact_dict(
        {
            "status": status,
            "drift_status": status,
            "meaning": meaning,
            "baseline_summary": baseline_summary(baseline),
            "current_behavior_summary": current_behavior_summary(baseline, relationship_changes, significant_columns),
            "largest_deviation": largest,
            "largest_deviations": largest_items,
            "baseline_window_rows": baseline.get("baseline_window_rows"),
            "recent_window_rows": baseline.get("recent_window_rows"),
            "columns_analyzed": baseline.get("columns_analyzed"),
            "confidence": confidence,
            "confidence_score": confidence_score,
            "confidence_rationale": fingerprint_confidence_rationale(baseline, relationship_changes, confidence_score),
            "primary_driver": intelligence.get("primary_driver"),
            "evidence": evidence,
            "evidence_supporting_status": evidence,
        }
    )

def build_evidence(
    *,
    insights: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    baseline: dict[str, Any],
    operator_report: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []

    for insight in insights:
        insight_evidence = insight.get("evidence") if isinstance(insight.get("evidence"), list) else []
        for index, item in enumerate(insight_evidence):
            if not isinstance(item, dict):
                continue
            evidence.append(
                compact_dict(
                    {
                        "id": f"{insight.get('id', 'insight')}-evidence-{index}",
                        "type": "insight_support",
                        "insight_id": insight.get("id"),
                        "what_happened": insight.get("explanation"),
                        "why_neraium_believes_this": insight.get("likely_cause"),
                        "supporting_evidence": item.get("supporting_signals"),
                        "relevant_metric_changes": item.get("relevant_metric_changes"),
                        "time_window": item.get("time_window"),
                        "persistence_duration": item.get("persistence_duration"),
                        "confidence": item.get("confidence") or insight.get("confidence"),
                        "next_check": first_text(insight.get("operator_check"), insight.get("recommended_action")),
                    }
                )
            )

    for relationship in relationships:
        evidence.append(
            compact_dict(
                {
                    "id": f"{relationship.get('id', 'relationship')}-evidence",
                    "type": "relationship_change",
                    "relationship_id": relationship.get("id"),
                    "what_happened": relationship.get("what_changed"),
                    "why_neraium_believes_this": relationship.get("why_it_matters"),
                    "supporting_evidence": relationship.get("columns"),
                    "relevant_metric_changes": [
                        metric_change("Correlation delta", relationship.get("correlation_delta")),
                        metric_change("Baseline correlation", relationship.get("baseline_correlation")),
                        metric_change("Recent correlation", relationship.get("recent_correlation")),
                    ],
                    "confidence": relationship.get("confidence"),
                    "source_rows": relationship.get("source_rows"),
                    "next_check": relationship.get("operator_check"),
                }
            )
        )

    evidence.append(
        compact_dict(
            {
                "id": "baseline-window",
                "type": "baseline_context",
                "what_happened": "Neraium compared the early baseline window with the most recent operating window.",
                "why_neraium_believes_this": "The baseline and recent row counts define the comparison windows used by drift and relationship scoring.",
                "supporting_evidence": [
                    f"{baseline.get('baseline_window_rows')} baseline rows",
                    f"{baseline.get('recent_window_rows')} recent rows",
                    f"{baseline.get('columns_analyzed')} numeric columns analyzed",
                ],
                "confidence": confidence_from_baseline(baseline),
                "next_check": first_item(operator_report.get("recommended_operator_checks")),
            }
        )
    )

    timestamp_profile = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    if timestamp_profile:
        evidence.append(
            compact_dict(
                {
                    "id": "timestamp-coverage",
                    "type": "time_context",
                    "what_happened": "Timestamp coverage was profiled for the uploaded file.",
                    "supporting_evidence": [
                        timestamp_profile.get("detected_timestamp_column"),
                        build_time_window(result),
                    ],
                    "confidence": "moderate" if timestamp_profile.get("detected_timestamp_column") else "limited",
                    "next_check": "Confirm the uploaded time range matches the operating period under review.",
                }
            )
        )

    return dedupe_evidence(evidence)


def build_recommendations(
    *,
    insights: list[dict[str, Any]],
    operator_report: dict[str, Any],
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    for insight in insights:
        action = first_text(insight.get("recommended_action"), insight.get("operator_check"))
        if not action:
            continue
        recommendations.append(
            compact_dict(
                {
                    "id": f"{insight.get('id', 'insight')}-recommendation",
                    "priority": priority_from_severity(insight.get("severity")),
                    "recommendation": action,
                    "reason": first_text(insight.get("explanation"), insight.get("likely_cause")),
                    "evidence_refs": [insight.get("id")],
                    "next_check": insight.get("operator_check"),
                    "system": insight.get("system"),
                }
            )
        )

    for relationship in relationships[:3]:
        recommendations.append(
            compact_dict(
                {
                    "id": f"{relationship.get('id', 'relationship')}-recommendation",
                    "priority": priority_from_severity(severity_from_number(relationship.get("correlation_delta"))),
                    "recommendation": relationship.get("operator_check"),
                    "reason": relationship.get("what_changed"),
                    "evidence_refs": [relationship.get("id")],
                    "next_check": relationship.get("operator_check"),
                    "system": relationship.get("system"),
                }
            )
        )

    checks = operator_report.get("recommended_operator_checks") if isinstance(operator_report.get("recommended_operator_checks"), list) else []
    for index, check in enumerate(checks):
        text = first_text(check)
        if not text:
            continue
        recommendations.append(
            {
                "id": f"operator-check-{index}",
                "priority": "medium",
                "recommendation": text,
                "reason": "Operator report check generated from upload data quality, baseline, and timestamp review.",
                "next_check": text,
            }
        )

    return dedupe_recommendations(recommendations)


def compact_system(item: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in item.items():
        if value is None or value == "" or value == []:
            continue
        compacted[key] = dedupe(value) if isinstance(value, list) else value
    return compacted



def numeric_confidence_score(value: Any, fallback: float = 0.5) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = float(fallback)
    if score > 1.0 and score <= 100.0:
        score = score / 100.0
    return round(max(0.0, min(1.0, score)), 4)


def sample_confidence_score(baseline_size: Any, recent_size: Any, magnitude: Any = None) -> float:
    try:
        minimum = min(int(baseline_size or 0), int(recent_size or 0))
    except (TypeError, ValueError):
        minimum = 0
    try:
        change = abs(float(magnitude or 0.0))
    except (TypeError, ValueError):
        change = 0.0
    sample_factor = min(1.0, minimum / 12.0)
    change_factor = min(1.0, change / 0.75)
    return round(max(0.2, sample_factor * 0.65 + change_factor * 0.35), 4)


def baseline_confidence_score(baseline: dict[str, Any]) -> float:
    rows = min(int(baseline.get("baseline_window_rows") or 0), int(baseline.get("recent_window_rows") or 0))
    columns = int(baseline.get("columns_analyzed") or 0)
    row_factor = min(1.0, rows / 12.0)
    column_factor = min(1.0, columns / 2.0)
    return round(max(0.2, row_factor * 0.7 + column_factor * 0.3), 4)


def confidence_label_from_score(score: Any) -> str:
    score = numeric_confidence_score(score, 0.0)
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "moderate"
    return "limited"


def source_time_ranges(result: dict[str, Any], fallback_window: str = "") -> list[dict[str, Any]]:
    timestamp = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    first = first_text(timestamp.get("first_timestamp"))
    last = first_text(timestamp.get("last_timestamp"))
    if first or last:
        return [compact_dict({"label": "uploaded_csv", "start": first, "end": last})]
    if fallback_window:
        return [{"label": "uploaded_csv", "window": fallback_window}]
    return []


def relationship_source_time_ranges(item: dict[str, Any], fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    window = item.get("time_window") if isinstance(item.get("time_window"), dict) else {}
    if window:
        return [
            compact_dict(
                {
                    "label": "relationship_comparison",
                    "baseline_start": window.get("baseline_start"),
                    "baseline_end": window.get("baseline_end"),
                    "current_start": window.get("current_start"),
                    "current_end": window.get("current_end"),
                }
            )
        ]
    return fallback


def relationship_change_sentence(label: str, item: dict[str, Any]) -> str:
    change_type = first_text(item.get("change_type"), "changed").replace("_", " ")
    baseline = item.get("baseline_strength", item.get("coupling_strength"))
    current = item.get("current_strength", item.get("strength"))
    if baseline is not None and current is not None:
        return f"{label} relationship {change_type}; baseline strength was {baseline} and current strength is {current}."
    return f"{label} changed between the baseline window and current window."


def relationship_confidence_basis(label: str, item: dict[str, Any]) -> str:
    return (
        f"Neraium compared the {label} correlation in the baseline window with the current window "
        f"and found a {item.get('correlation_delta')} correlation delta."
    )


def confidence_rationale_for_relationship(item: dict[str, Any], confidence_score: float) -> str:
    baseline_size = item.get("baseline_sample_size")
    recent_size = item.get("recent_sample_size")
    delta = item.get("correlation_delta")
    return (
        f"Confidence score {confidence_score} is based on {baseline_size} baseline samples, "
        f"{recent_size} current samples, and correlation delta {delta}."
    )


def confidence_rationale_for_metric(item: dict[str, Any], persistence_detail: dict[str, Any], confidence_score: float) -> str:
    support = persistence_detail.get("support_percent") if persistence_detail else None
    percent = item.get("percent_change")
    if support is not None:
        return f"Confidence score {confidence_score} is based on {percent}% metric change and {support}% recent-window directional support."
    return f"Confidence score {confidence_score} is based on {percent}% metric change and available baseline/current window rows."


def baseline_confidence_rationale(baseline: dict[str, Any], confidence_score: float) -> str:
    return (
        f"Confidence score {confidence_score} is based on {baseline.get('baseline_window_rows')} baseline rows, "
        f"{baseline.get('recent_window_rows')} current rows, and {baseline.get('columns_analyzed')} analyzed numeric columns."
    )


def evidence_summary(evidence_items: list[dict[str, Any]]) -> str:
    summaries: list[str] = []
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        metric_changes = [change for change in (item.get("relevant_metric_changes") or []) if change]
        if metric_changes:
            summaries.extend(metric_changes[:3])
        else:
            summaries.append(first_text(item.get("summary"), *(item.get("supporting_signals") or [])))
    return "; ".join(dedupe([summary for summary in summaries if summary])[:4])


def relationship_evidence_items(
    *,
    item: dict[str, Any],
    label: str,
    time_window: str,
    source_ranges: list[dict[str, Any]],
    upload_id: str,
    analysis_id: str,
    confidence_score: float,
) -> list[dict[str, Any]]:
    confidence = confidence_label_from_score(confidence_score)
    summary = first_text(item.get("summary"), relationship_change_sentence(label, item))
    return [
        compact_dict(
            {
                "id": "relationship-evidence-0",
                "type": "relationship_change",
                "summary": summary,
                "supporting_signals": [summary],
                "relevant_metric_changes": [
                    metric_change("Correlation delta", item.get("correlation_delta")),
                    metric_change("Baseline strength", item.get("baseline_strength", item.get("coupling_strength"))),
                    metric_change("Current strength", item.get("current_strength", item.get("strength"))),
                    metric_change("Change percentage", item.get("change_percentage"), suffix="%"),
                ],
                "relationship_type": item.get("relationship_type"),
                "change_type": item.get("change_type"),
                "source_columns": relationship_columns(item),
                "source_metrics": relationship_columns(item),
                "source_tags": relationship_columns(item),
                "supporting_metric_pairs": item.get("supporting_metric_pairs"),
                "source_rows": item.get("source_rows"),
                "source_time_ranges": source_ranges,
                "time_window": time_window,
                "persistence_duration": sample_window_phrase(item.get("baseline_sample_size"), item.get("recent_sample_size")),
                "confidence": confidence,
                "confidence_score": confidence_score,
                "source_upload_id": upload_id,
                "analysis_id": analysis_id,
                "calculated_delta": item.get("correlation_delta"),
            }
        )
    ]


def persistence_detail_for_column(persistence: dict[str, Any], column: str) -> dict[str, Any]:
    details = persistence.get("details") if isinstance(persistence.get("details"), list) else []
    return next((detail for detail in details if isinstance(detail, dict) and detail.get("column") == column), {})


def metric_confidence_score(item: dict[str, Any], persistence_detail: dict[str, Any]) -> float:
    try:
        magnitude = abs(float(item.get("percent_change") or 0.0))
    except (TypeError, ValueError):
        magnitude = abs(float(item.get("absolute_change") or 0.0))
    signal_factor = min(1.0, magnitude / 30.0)
    persistence_factor = 0.45 if item.get("drift_flag") in {"watch", "review"} else 0.2
    if persistence_detail.get("persistent"):
        persistence_factor = 1.0
    elif persistence_detail.get("support_percent") is not None:
        persistence_factor = min(1.0, float(persistence_detail.get("support_percent") or 0.0) / 100.0)
    return round(max(0.2, signal_factor * 0.55 + persistence_factor * 0.45), 4)


def metric_change_sentence(item: dict[str, Any]) -> str:
    column = str(item.get("column") or "Signal")
    direction = str(item.get("direction") or "changed")
    percent = item.get("percent_change")
    baseline = item.get("baseline_average")
    current = item.get("recent_average")
    if percent is not None and baseline is not None and current is not None:
        return f"{column} moved {direction} by {percent}%: baseline average {baseline}, current average {current}."
    if baseline is not None and current is not None:
        return f"{column} moved {direction}: baseline average {baseline}, current average {current}."
    return f"{column} moved {direction} from the baseline window to the current window."


def metric_confidence_basis(item: dict[str, Any], persistence_detail: dict[str, Any]) -> str:
    column = str(item.get("column") or "this signal")
    percent = item.get("percent_change")
    persistence = persistence_phrase(persistence_detail)
    basis = f"Neraium compared baseline and current windows for {column}"
    if percent is not None:
        basis = f"{basis} and measured a {percent}% change"
    if persistence:
        return f"{basis}. {persistence}"
    return f"{basis}."


def column_evidence_items(
    *,
    item: dict[str, Any],
    persistence_detail: dict[str, Any],
    time_window: str,
    source_ranges: list[dict[str, Any]],
    upload_id: str,
    analysis_id: str,
    confidence_score: float,
) -> list[dict[str, Any]]:
    column = str(item.get("column") or "Signal")
    confidence = confidence_label_from_score(confidence_score)
    summary = metric_change_sentence(item)
    return [
        compact_dict(
            {
                "id": f"metric-{column}-evidence-0",
                "type": "metric_drift",
                "summary": summary,
                "supporting_signals": [summary],
                "relevant_metric_changes": [
                    metric_change("Percent change", item.get("percent_change"), suffix="%"),
                    metric_change("Absolute change", item.get("absolute_change")),
                    metric_change("Baseline average", item.get("baseline_average")),
                    metric_change("Current average", item.get("recent_average")),
                    metric_change("Persistence score", item.get("persistence_score")),
                ],
                "source_columns": [column],
                "source_metrics": [column],
                "source_tags": [column],
                "baseline_value": item.get("baseline_average"),
                "current_value": item.get("recent_average"),
                "calculated_delta": item.get("absolute_change"),
                "calculated_percent_delta": item.get("percent_change"),
                "source_time_ranges": source_ranges,
                "time_window": time_window,
                "persistence_duration": persistence_phrase(persistence_detail),
                "confidence": confidence,
                "confidence_score": confidence_score,
                "source_upload_id": upload_id,
                "analysis_id": analysis_id,
            }
        )
    ]


def relationship_contribution(item: dict[str, Any], index: int, columns: list[str]) -> dict[str, Any]:
    return compact_dict(
        {
            "id": f"relationship-{index}",
            "columns": columns,
            "relationship_type": item.get("relationship_type"),
            "change_type": item.get("change_type"),
            "strength": item.get("strength"),
            "baseline_strength": item.get("baseline_strength"),
            "current_strength": item.get("current_strength"),
            "change_percentage": item.get("change_percentage"),
            "confidence_score": item.get("confidence_score"),
            "time_window": item.get("time_window"),
        }
    )


def metric_contributions(columns: list[str], drift_item: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    contributions = []
    for column in columns:
        item = {"name": column, "source_column": column}
        if drift_item and drift_item.get("column") == column:
            item.update(
                {
                    "baseline_average": drift_item.get("baseline_average"),
                    "current_average": drift_item.get("recent_average"),
                    "absolute_change": drift_item.get("absolute_change"),
                    "percent_change": drift_item.get("percent_change"),
                    "direction": drift_item.get("direction"),
                }
            )
        contributions.append(compact_dict(item))
    return contributions


def largest_deviation_items(columns: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in columns:
        items.append(
            compact_dict(
                {
                    "type": "metric",
                    "label": item.get("column"),
                    "magnitude": abs(float(item.get("percent_change") or item.get("absolute_change") or 0)),
                    "direction": item.get("direction"),
                    "percent_change": item.get("percent_change"),
                }
            )
        )
    for item in relationships:
        items.append(
            compact_dict(
                {
                    "type": "relationship",
                    "label": " / ".join(relationship_columns(item)) or item.get("relationship"),
                    "magnitude": abs(float(item.get("correlation_delta") or 0)),
                    "change_type": item.get("change_type"),
                    "baseline_strength": item.get("baseline_strength"),
                    "current_strength": item.get("current_strength"),
                }
            )
        )
    return sorted(items, key=lambda item: float(item.get("magnitude") or 0), reverse=True)[:5]


def baseline_summary(baseline: dict[str, Any]) -> dict[str, Any]:
    return compact_dict(
        {
            "baseline_window_rows": baseline.get("baseline_window_rows"),
            "recent_window_rows": baseline.get("recent_window_rows"),
            "columns_analyzed": baseline.get("columns_analyzed"),
            "overall_assessment": baseline.get("overall_assessment"),
            "adaptive_baseline": baseline.get("adaptive_baseline"),
            "regime_context": baseline.get("regime_context"),
        }
    )


def current_behavior_summary(
    baseline: dict[str, Any],
    relationship_changes: list[dict[str, Any]],
    significant_columns: list[dict[str, Any]],
) -> dict[str, Any]:
    return compact_dict(
        {
            "active_metric_deviations": len(significant_columns),
            "active_relationship_deviations": len(relationship_changes),
            "largest_metric_deviations": [change_phrase(item) for item in significant_columns[:5]],
            "relationship_changes": [first_text(item.get("summary"), item.get("relationship")) for item in relationship_changes[:5]],
            "drift_trajectory": baseline.get("drift_trajectory"),
        }
    )


def fingerprint_confidence_score(
    baseline: dict[str, Any],
    relationship_changes: list[dict[str, Any]],
    significant_columns: list[dict[str, Any]],
) -> float:
    base = baseline_confidence_score(baseline)
    relationship_scores = [numeric_confidence_score(item.get("confidence_score"), 0.0) for item in relationship_changes]
    if relationship_scores:
        return round((base * 0.6) + (max(relationship_scores) * 0.4), 4)
    if significant_columns:
        return round(max(0.2, base * 0.85), 4)
    return base


def fingerprint_confidence_rationale(baseline: dict[str, Any], relationship_changes: list[dict[str, Any]], confidence_score: float) -> str:
    relation_text = f" and {len(relationship_changes)} changed relationships" if relationship_changes else ""
    return (
        f"Confidence score {confidence_score} is based on {baseline.get('baseline_window_rows')} baseline rows, "
        f"{baseline.get('recent_window_rows')} current rows, {baseline.get('columns_analyzed')} numeric columns{relation_text}."
    )


def fingerprint_evidence_items(
    *,
    baseline: dict[str, Any],
    relationship_changes: list[dict[str, Any]],
    significant_columns: list[dict[str, Any]],
    source_ranges: list[dict[str, Any]],
    confidence_score: float,
) -> list[dict[str, Any]]:
    evidence = [
        compact_dict(
            {
                "id": "fingerprint-baseline-window",
                "type": "baseline_summary",
                "summary": "Baseline and current windows were compared to classify the operating fingerprint.",
                "supporting_signals": [
                    f"{baseline.get('baseline_window_rows')} baseline rows",
                    f"{baseline.get('recent_window_rows')} current rows",
                    f"{baseline.get('columns_analyzed')} numeric columns analyzed",
                ],
                "source_time_ranges": source_ranges,
                "confidence_score": confidence_score,
                "confidence": confidence_label_from_score(confidence_score),
            }
        )
    ]
    for index, item in enumerate(significant_columns[:3]):
        evidence.append(
            compact_dict(
                {
                    "id": f"fingerprint-metric-{index}",
                    "type": "metric_deviation",
                    "summary": metric_change_sentence(item),
                    "source_columns": [item.get("column")],
                    "calculated_percent_delta": item.get("percent_change"),
                    "source_time_ranges": source_ranges,
                }
            )
        )
    for index, item in enumerate(relationship_changes[:3]):
        evidence.append(
            compact_dict(
                {
                    "id": f"fingerprint-relationship-{index}",
                    "type": "relationship_deviation",
                    "summary": first_text(item.get("summary"), item.get("relationship")),
                    "source_columns": relationship_columns(item),
                    "calculated_delta": item.get("correlation_delta"),
                    "change_percentage": item.get("change_percentage"),
                    "source_time_ranges": relationship_source_time_ranges(item, source_ranges),
                }
            )
        )
    return evidence

def relationship_evidence(item: dict[str, Any], time_window: str) -> list[dict[str, Any]]:
    signals = []
    columns = relationship_columns(item)
    if columns:
        signals.append("Relationship: " + " / ".join(columns))
    if item.get("summary"):
        signals.append(str(item.get("summary")))
    return [
        compact_dict(
            {
                "confidence": confidence_from_samples(item.get("baseline_sample_size"), item.get("recent_sample_size")),
                "supporting_signals": signals,
                "relevant_metric_changes": [
                    metric_change("Correlation delta", item.get("correlation_delta")),
                    metric_change("Baseline correlation", item.get("baseline_correlation")),
                    metric_change("Recent correlation", item.get("recent_correlation")),
                ],
                "time_window": time_window,
                "persistence_duration": sample_window_phrase(item.get("baseline_sample_size"), item.get("recent_sample_size")),
            }
        )
    ]


def column_evidence(item: dict[str, Any], time_window: str, persistence: dict[str, Any]) -> list[dict[str, Any]]:
    column = str(item.get("column") or "")
    persistence_detail = next(
        (
            detail for detail in persistence.get("details", [])
            if isinstance(detail, dict) and detail.get("column") == column
        ),
        {},
    ) if isinstance(persistence.get("details"), list) else {}
    return [
        compact_dict(
            {
                "confidence": "high" if persistence_detail.get("persistent") else "moderate",
                "supporting_signals": [column],
                "relevant_metric_changes": [
                    metric_change("Percent change", item.get("percent_change"), suffix="%"),
                    metric_change("Absolute change", item.get("absolute_change")),
                    metric_change("Baseline average", item.get("baseline_average")),
                    metric_change("Recent average", item.get("recent_average")),
                ],
                "time_window": time_window,
                "persistence_duration": persistence_phrase(persistence_detail),
            }
        )
    ]


def relationship_columns(item: dict[str, Any]) -> list[str]:
    refs = item.get("evidence_refs") if isinstance(item.get("evidence_refs"), list) else []
    columns = [str(ref.get("column")) for ref in refs if isinstance(ref, dict) and ref.get("column")]
    if len(columns) >= 2:
        return dedupe(columns)[:2]
    relationship = str(item.get("relationship") or "")
    if "<->" in relationship:
        return dedupe([part.strip() for part in relationship.split("<->", 1) if part.strip()])
    columns = item.get("columns")
    if isinstance(columns, list):
        return dedupe([str(column) for column in columns if column])
    return []


def is_cumulative_context_item(item: dict[str, Any]) -> bool:
    column = str(item.get("column") or "")
    return (
        item.get("metric_type") == "cumulative_counter"
        or item.get("analysis_role") == "supporting_context"
        or is_cumulative_counter_name(column)
    )


def relationship_has_cumulative_counter(item: dict[str, Any]) -> bool:
    return any(is_cumulative_counter_name(column) for column in relationship_columns(item))


def human_metric_label(column: str) -> str:
    text = str(column or "").lower()
    if "pump" in text and "vibration" in text:
        return "Pump vibration"
    if "fouling" in text:
        return "Fouling severity"
    if "outlet" in text and "temp" in text:
        return "Outlet temperature"
    if "pressure" in text:
        return "Pressure"
    if "flow" in text:
        return "Flow"
    if "temp" in text:
        return "Temperature"
    if "vibration" in text:
        return "Vibration"
    words = [part for part in re_split_identifier(column) if part not in {"f", "c", "pct", "psi", "gal"}]
    return " ".join(words).capitalize() if words else "Signal"


def re_split_identifier(value: str) -> list[str]:
    return [part for part in str(value or "").replace("-", "_").split("_") if part]


def metric_title(item: dict[str, Any]) -> str:
    column = str(item.get("column") or "Signal")
    label = human_metric_label(column)
    direction = str(item.get("direction") or "changed")
    try:
        magnitude = abs(float(item.get("percent_change") or item.get("absolute_change") or 0))
    except (TypeError, ValueError):
        magnitude = 0.0
    if direction == "up":
        verb = "increased sharply" if magnitude >= 30 else "increased"
    elif direction == "down":
        verb = "decreased sharply" if magnitude >= 30 else "decreased"
    else:
        verb = "changed"
    return f"{label} {verb}"


def relationship_title(columns: list[str], item: dict[str, Any]) -> str:
    text = " ".join(columns).lower()
    if "fouling" in text and ("temp" in text or "thermal" in text):
        return "Fouling-related thermal behavior changed"
    if "pressure" in text and "flow" in text:
        return "Pressure and flow relationship changed"
    if "pump" in text and "vibration" in text:
        return "Pump behavior relationship changed"
    if "temp" in text or "thermal" in text:
        return "Thermal relationship changed"
    if "flow" in text or "pressure" in text:
        return "Flow and pressure behavior changed"
    labels = [human_metric_label(column) for column in columns[:2]]
    if len(labels) == 2 and labels[0] != "Signal" and labels[1] != "Signal":
        return f"{labels[0]} and {labels[1]} relationship changed"
    return "Signal relationship changed"


def relationship_observable_sentence(columns: list[str], item: dict[str, Any]) -> str:
    change_type = first_text(item.get("change_type"), "changed").replace("_", " ")
    title = relationship_title(columns, item).rstrip(".")
    return f"{title}; the relationship {change_type} between the baseline window and current window."


def relationship_recommended_action(system: str) -> str:
    return f"Prioritize {system.lower()} trend review and decide whether maintenance triage or closer monitoring is needed."


def metric_recommended_action(column: str, item: dict[str, Any]) -> str:
    label = human_metric_label(column).lower()
    if "vibration" in label:
        return "Prioritize pump mechanical review and trend the vibration signal against the next operating window."
    return f"Prioritize {label} in the next operations review and track whether it continues outside baseline."


def system_from_columns(columns: list[str]) -> str:
    text = " ".join(columns).lower()
    if any(token in text for token in ["flow", "pressure", "pump", "valve", "air"]):
        return "Flow and pressure system"
    if any(token in text for token in ["temp", "heat", "cool", "hvac"]):
        return "Thermal response system"
    if any(token in text for token in ["humidity", "moisture", "water"]):
        return "Moisture response system"
    if any(token in text for token in ["runtime", "schedule", "energy"]):
        return "Schedule and energy system"
    return "Uploaded telemetry"


def largest_deviation(columns: list[dict[str, Any]], relationships: list[dict[str, Any]]) -> str:
    candidates: list[tuple[float, str]] = []
    for item in columns:
        direction = str(item.get("direction") or "changed")
        magnitude = abs(float(item.get("percent_change") or item.get("absolute_change") or 0))
        candidates.append((magnitude, metric_title(item) if direction in {"up", "down", "flat"} else change_phrase(item)))
    for item in relationships:
        magnitude = abs(float(item.get("correlation_delta") or 0))
        columns_for_title = relationship_columns(item)
        candidates.append((magnitude, relationship_title(columns_for_title, item)))
    if not candidates:
        return ""
    return max(candidates, key=lambda item: item[0])[1]


def change_phrase(item: dict[str, Any]) -> str:
    column = str(item.get("column") or "Signal")
    direction = str(item.get("direction") or "changed")
    percent = item.get("percent_change")
    if percent is not None:
        return f"{column} moved {direction} by {percent}% versus baseline."
    return f"{column} moved {direction} versus baseline."


def matching_operator_check(operator_report: dict[str, Any], column: str) -> str:
    checks = operator_report.get("recommended_operator_checks") if isinstance(operator_report.get("recommended_operator_checks"), list) else []
    column_lower = column.lower()
    return first_text(*(check for check in checks if column_lower in str(check).lower()))


def metric_change(label: str, value: Any, suffix: str = "") -> str:
    if value is None or value == "":
        return ""
    return f"{label}: {value}{suffix}"


def build_time_window(result: dict[str, Any]) -> str:
    timestamp = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    return first_text(
        " to ".join(
            item for item in [
                str(timestamp.get("first_timestamp") or ""),
                str(timestamp.get("last_timestamp") or ""),
            ] if item
        ),
        result.get("last_processed_at"),
    )


def persistence_phrase(detail: dict[str, Any]) -> str:
    if not detail:
        return ""
    checked = detail.get("recent_values_checked")
    support = detail.get("support_percent")
    if checked is None:
        return ""
    if support is None:
        return f"Observed across {checked} recent readings."
    return f"{support}% of {checked} recent readings supported the same direction."


def sample_window_phrase(baseline_size: Any, recent_size: Any) -> str:
    if baseline_size and recent_size:
        return f"Compared {baseline_size} baseline samples with {recent_size} recent samples."
    return ""


def confidence_from_samples(baseline_size: Any, recent_size: Any) -> str:
    try:
        minimum = min(int(baseline_size or 0), int(recent_size or 0))
    except (TypeError, ValueError):
        minimum = 0
    if minimum >= 12:
        return "high"
    if minimum >= 4:
        return "moderate"
    return "limited"


def confidence_from_baseline(baseline: dict[str, Any]) -> str:
    rows = min(int(baseline.get("baseline_window_rows") or 0), int(baseline.get("recent_window_rows") or 0))
    columns = int(baseline.get("columns_analyzed") or 0)
    if rows >= 12 and columns >= 2:
        return "high"
    if rows >= 3 and columns >= 1:
        return "moderate"
    return "limited"


def severity_from_number(value: Any) -> str:
    try:
        number = abs(float(value or 0))
    except (TypeError, ValueError):
        number = 0
    if number >= 0.75:
        return "high"
    if number >= 0.35:
        return "moderate"
    return "low"


def priority_from_severity(severity: Any) -> str:
    normalized = str(severity or "").lower()
    if normalized in {"high", "elevated", "critical"}:
        return "high"
    if normalized in {"moderate", "medium", "review"}:
        return "medium"
    return "low"


def first_item(value: Any) -> str:
    if isinstance(value, list):
        return first_text(*value)
    return first_text(value)


def first_text(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def dedupe(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = first_text(item.get("id"), item.get("what_happened"), item.get("type"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def dedupe_recommendations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = first_text(item.get("recommendation"), item.get("next_check"))
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, item in value.items():
        if item is None or item == "":
            continue
        if isinstance(item, list):
            cleaned = [entry for entry in item if entry is not None and entry != "" and entry != [] and entry != {}]
            if cleaned:
                compacted[key] = cleaned
            continue
        if isinstance(item, dict):
            nested = compact_dict(item)
            if nested:
                compacted[key] = nested
            continue
        compacted[key] = item
    return compacted
