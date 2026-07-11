from __future__ import annotations

from typing import Any

from app.services.cumulative_counters import is_cumulative_counter_name
from app.services.telemetry_classification import is_context_or_supporting_column


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
    operator_interpretation = build_operator_interpretation(
        insights=insights,
        systems=systems,
        relationships=relationships,
        fingerprint=fingerprint,
        baseline=baseline,
        operator_report=operator_report,
        intelligence=intelligence,
        result=result,
        recommendations=recommendations,
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
        "operator_interpretation": operator_interpretation,
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

    supporting_context = context_driver_drift_items(baseline)
    relationship_changes = sorted(
        [
            item for item in relationship_model.get("top_relationship_changes", [])
            if isinstance(item, dict)
            and not relationship_has_cumulative_counter(item)
            and not relationship_is_context_only(item)
        ],
        key=relationship_importance_sort_key,
        reverse=True,
    )
    relationship_groups = cluster_relationship_changes(relationship_changes)
    for index, group in enumerate(relationship_groups[:3]):
        if not group:
            continue
        primary = group[0]
        primary_columns = relationship_columns(primary)
        primary_display_columns = relationship_display_columns(primary)
        all_columns = dedupe([column for entry in group for column in relationship_columns(entry)])
        all_signal_names = relationship_group_signal_names(group)
        label = " / ".join(primary_display_columns) if primary_display_columns else str(primary.get("display_relationship") or primary.get("relationship") or "Signal relationship")
        confidence_scores = [
            numeric_confidence_score(
                entry.get("confidence_score"),
                sample_confidence_score(entry.get("baseline_sample_size"), entry.get("recent_sample_size"), entry.get("correlation_delta")),
            )
            for entry in group
        ]
        confidence_score = max(confidence_scores) if confidence_scores else 0.5
        confidence = confidence_label_from_score(confidence_score)
        system = relationship_subsystem_name(all_signal_names or all_columns or primary_columns, confidence_score=confidence_score)
        evidence_items: list[dict[str, Any]] = []
        contributions: list[dict[str, Any]] = []
        group_source_ranges = []
        for group_index, entry in enumerate(group):
            columns = relationship_columns(entry)
            display_columns = relationship_display_columns(entry)
            entry_label = " / ".join(display_columns) if display_columns else str(entry.get("display_relationship") or entry.get("relationship") or "Signal relationship")
            relationship_ranges = relationship_source_time_ranges(entry, source_time_ranges(result, time_window))
            group_source_ranges.extend(relationship_ranges)
            entry_confidence = numeric_confidence_score(
                entry.get("confidence_score"),
                sample_confidence_score(entry.get("baseline_sample_size"), entry.get("recent_sample_size"), entry.get("correlation_delta")),
            )
            for evidence_item in relationship_evidence_items(
                item=entry,
                label=entry_label,
                time_window=time_window,
                source_ranges=relationship_ranges,
                upload_id=upload_id,
                analysis_id=analysis_id,
                confidence_score=entry_confidence,
            ):
                adjusted = dict(evidence_item)
                adjusted["id"] = f"relationship-{index}-{group_index}-evidence-0"
                evidence_items.append(adjusted)
            contributions.append(relationship_contribution(entry, group_index, columns))
        signal_context = all_signal_names or all_columns or primary_columns
        possible_causes = possible_operational_causes(system, signal_context)
        what_changed = merged_relationship_observable_sentence(group, primary)
        why = merged_relationship_reason(group, primary, label)
        persistence_duration = sample_window_phrase(primary.get("baseline_sample_size"), primary.get("recent_sample_size"))
        title = operational_diagnosis_title(system, signal_context, group, confidence_score)
        operational_impact = relationship_operational_impact_sentence(
            system,
            signal_context,
            possible_causes,
        )
        deduped_source_ranges = dedupe_ranges(group_source_ranges)
        observed_facts = relationship_observed_facts(
            group=group,
            baseline=baseline,
            source_ranges=deduped_source_ranges,
        )
        likely_impacts = relationship_why_this_matters(system, signal_context)
        investigation_steps = recommended_investigation_steps(system, signal_context, label)
        first_check = first_item(investigation_steps)
        behavior_interpretation = relationship_behavior_interpretation(system, signal_context, possible_causes)
        activity_timeline = relationship_activity_timeline(
            system=system,
            facts=observed_facts,
            first_check=first_check,
            source_ranges=deduped_source_ranges,
        )
        insight = compact_dict(
            {
                "id": f"relationship-{index}",
                "title": title,
                "primary_finding": title,
                "severity": severity_from_number(primary.get("correlation_delta")),
                "confidence": confidence,
                "confidence_score": confidence_score,
                "confidence_rationale": confidence_rationale_for_relationship(primary, confidence_score),
                "relationship_importance_score": primary.get("relationship_importance_score"),
                "relationship_importance_rationale": primary.get("relationship_importance_rationale"),
                "ranking_factors": primary.get("ranking_factors"),
                "affected_systems": [system],
                "system": system,
                "what_changed": what_changed,
                "explanation": what_changed,
                "observed": observed_facts,
                "observed_facts": observed_facts,
                "why_neraium_thinks_it_happened": why,
                "why_neraium_thinks": why,
                "behavior_interpretation": behavior_interpretation,
                "why_it_matters": operational_impact,
                "why_this_matters": likely_impacts,
                "if_ignored": likely_impacts,
                "likely_cause": why,
                "contributing_factors": [relationship_label(entry) for entry in group],
                "possible_operational_consequence": operational_impact,
                "possible_consequence": operational_impact,
                "possible_operational_causes": possible_causes,
                "likely_causes": possible_causes,
                "possible_operational_causes_summary": "; ".join(possible_causes),
                "recommended_operator_check": operational_cause_check(label, possible_causes),
                "recommended_action": relationship_recommended_action(system),
                "recommended_investigation": investigation_steps,
                "recommended_first_action": first_check,
                "operator_check": operational_cause_check(label, possible_causes),
                "first_check": first_check,
                "activity_timeline": activity_timeline,
                "evidence_summary": evidence_summary(evidence_items),
                "evidence_items": evidence_items,
                "evidence": evidence_items,
                "contributing_relationships": contributions,
                "affected_relationships": [relationship_label(entry) for entry in group],
                "contributing_metrics": metric_contributions(all_columns),
                "source_metrics": all_columns,
                "source_tags": all_columns,
                "source_time_ranges": deduped_source_ranges,
                "time_window": time_window,
                "persistence_duration": persistence_duration,
                "upload_id": upload_id,
                "analysis_id": analysis_id,
            }
        )
        insights.append(insight)

    relationship_columns_in_primary_insights = {
        column for group in relationship_groups[:3] for entry in group for column in relationship_columns(entry)
    }
    drift_items = [
        item for item in baseline.get("column_drift", [])
        if isinstance(item, dict)
        and item.get("drift_flag") in {"watch", "review"}
        and not is_supporting_context_item(item)
        and (
            not relationship_columns_in_primary_insights
            or str(item.get("column") or "") not in relationship_columns_in_primary_insights
        )
    ]
    drift_items.sort(key=lambda item: abs(float(item.get("percent_change") or item.get("absolute_change") or 0)), reverse=True)
    for index, item in enumerate(drift_items[: max(0, 5 - len(insights))]):
        column = str(item.get("column") or "Signal")
        column_label = signal_label_from_item(item)
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
        evidence_items.extend(
            context_modifier_evidence_items(
                context_items=supporting_context,
                time_window=time_window,
                source_ranges=source_ranges,
                upload_id=upload_id,
                analysis_id=analysis_id,
            )
        )
        what_changed = metric_change_sentence(item)
        why = metric_confidence_basis(item, persistence_detail)
        operator_check = first_text(
            matching_operator_check(operator_report, column),
            f"Review {column_label} readings against facility logs for the uploaded period.",
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
                    "operator_check": f"Check source readings, control changes, and maintenance activity involving {column_label}.",
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
            or is_supporting_context_item(item)
        ):
            continue
        target = entry(system_from_columns([str(item.get("column") or "")]))
        target["key_behaviors"].append(f"{signal_label_from_item(item)} is moving {item.get('direction')} against baseline.")
        target["what_changed"].append(change_phrase(item))

    for relationship in relationship_model.get("top_relationship_changes", []) if isinstance(relationship_model.get("top_relationship_changes"), list) else []:
        if not isinstance(relationship, dict) or relationship_has_cumulative_counter(relationship) or relationship_is_context_only(relationship):
            continue
        columns = relationship_columns(relationship)
        target = entry(system_from_columns(columns))
        display_columns = relationship_display_columns(relationship)
        label = " / ".join(display_columns) if display_columns else str(relationship.get("display_relationship") or relationship.get("relationship") or "Signal relationship")
        summary = relationship_operator_summary(relationship, label)
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
    changes = sorted([item for item in changes if isinstance(item, dict)], key=relationship_importance_sort_key, reverse=True)

    for index, item in enumerate(changes[:5]):
        if not isinstance(item, dict) or relationship_has_cumulative_counter(item):
            continue
        columns = relationship_columns(item)
        display_columns = relationship_display_columns(item)
        label = " / ".join(display_columns) if display_columns else str(item.get("display_relationship") or item.get("relationship") or "Signal relationship")
        confidence_score = numeric_confidence_score(
            item.get("confidence_score"),
            sample_confidence_score(item.get("baseline_sample_size"), item.get("recent_sample_size"), item.get("correlation_delta")),
        )
        system = relationship_subsystem_name([*columns, *display_columns], confidence_score=confidence_score)
        why_it_matters = relationship_operational_impact_sentence(
            system,
            [*columns, *display_columns],
            possible_operational_causes(system, [*columns, *display_columns]),
        )
        relationships.append(
            compact_dict(
                {
                    "id": f"relationship-{index}",
                    "name": label,
                    "columns": columns,
                    "display_columns": display_columns,
                    "system": system,
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
                    "relationship_importance_score": item.get("relationship_importance_score"),
                    "relationship_importance_rationale": item.get("relationship_importance_rationale"),
                    "ranking_factors": item.get("ranking_factors"),
                    "column_classifications": item.get("column_classifications"),
                    "relationship_context": item.get("relationship_context"),
                    "what_changed": first_text(
                        relationship_operator_summary(item, label),
                        relationship_change_sentence(label, item),
                    ),
                    "why_it_matters": why_it_matters,
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
        if isinstance(item, dict) and not relationship_has_cumulative_counter(item) and not relationship_is_context_only(item)
    ]
    significant_columns = [
        item for item in baseline.get("column_drift", [])
        if isinstance(item, dict)
        and item.get("drift_flag") in {"watch", "review"}
        and not is_supporting_context_item(item)
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
                        metric_change("Operating pattern change", relationship.get("correlation_delta")),
                        metric_change("Baseline operating coupling", relationship.get("baseline_correlation")),
                        metric_change("Current operating coupling", relationship.get("recent_correlation")),
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


def build_operator_interpretation(
    *,
    insights: list[dict[str, Any]],
    systems: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    fingerprint: dict[str, Any],
    baseline: dict[str, Any],
    operator_report: dict[str, Any],
    intelligence: dict[str, Any],
    result: dict[str, Any],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    primary = primary_operator_insight(insights)
    changed = operator_change_present(primary, relationships, fingerprint)
    raw_system = operator_primary_system(primary, systems, relationships, intelligence)
    relationship_labels = operator_relationship_labels(primary, relationships)
    system = operator_report_system_label(raw_system, relationship_labels)
    confidence = operator_confidence_label(
        first_text(primary.get("confidence") if primary else "", fingerprint.get("confidence"), intelligence.get("confidence")),
        primary.get("confidence_score") if primary else fingerprint.get("confidence_score"),
    )
    overall_condition = "Attention Needed" if changed else "Normal"
    possible_causes = operator_possible_causes(primary, system, relationship_labels)
    recommended_review = operator_review_items(system, relationship_labels, recommendations, operator_report)
    executive_summary = operator_executive_summary(system, relationship_labels, fingerprint, changed)
    what_changed = operator_what_changed(primary, system, relationship_labels, changed)
    relationship_entries = operator_relationship_change_entries(primary, relationships)
    relationship_changes = [compact_dict({"label": entry.get("label")}) for entry in relationship_entries]
    advanced_details = operator_advanced_details(relationship_entries)

    return compact_dict(
        {
            "title": "Operational Assessment",
            "overall_condition": overall_condition,
            "confidence": confidence,
            "summary": executive_summary,
            "what_changed": what_changed,
            "potential_operational_causes": possible_causes,
            "recommended_review": recommended_review,
            "relationship_changes": relationship_changes,
            "advanced_details": advanced_details,
            "subsystem": system,
        }
    )


def primary_operator_insight(insights: list[dict[str, Any]]) -> dict[str, Any]:
    for insight in insights:
        if not isinstance(insight, dict):
            continue
        if str(insight.get("id") or "") == "baseline-stable":
            continue
        if str(insight.get("severity") or "").lower() != "low":
            return insight
    for insight in insights:
        if isinstance(insight, dict):
            return insight
    return {}


def operator_change_present(primary: dict[str, Any], relationships: list[dict[str, Any]], fingerprint: dict[str, Any]) -> bool:
    status = str(fingerprint.get("status") or fingerprint.get("drift_status") or "").lower()
    if status in {"changed", "drifting", "review", "unstable"}:
        return True
    if relationships:
        return True
    if primary and str(primary.get("id") or "") != "baseline-stable" and str(primary.get("severity") or "").lower() != "low":
        return True
    return False


def operator_primary_system(
    primary: dict[str, Any],
    systems: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    intelligence: dict[str, Any],
) -> str:
    return first_text(
        primary.get("system") if primary else "",
        first_item(primary.get("affected_systems") if primary else []),
        relationships[0].get("system") if relationships else "",
        systems[0].get("name") if systems else "",
        intelligence.get("primary_room"),
        "Uploaded telemetry",
    )



def operator_report_system_label(system: str, relationship_labels: list[str]) -> str:
    combined = " ".join([system, *relationship_labels]).lower()
    if system == "Pumping System" and any(token in combined for token in ["pressure", "filter", "flow", "valve", "hydraulic"]):
        return "Flow & Pressure"
    return system


def operator_primary_title(primary: dict[str, Any], raw_system: str, system: str, changed: bool) -> str:
    raw_title = first_text(primary.get("title") if primary else "")
    if raw_title and raw_system and raw_system != system and raw_title.lower().startswith(raw_system.lower()):
        return system + raw_title[len(raw_system):]
    return first_text(raw_title, f"{system} subsystem behavior changed" if changed else "Operating fingerprint remains stable")

def operator_relationship_labels(primary: dict[str, Any], relationships: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    if primary:
        for value in primary.get("affected_relationships") or []:
            labels.append(clean_operator_relationship_label(value))
        for item in primary.get("contributing_relationships") or []:
            if isinstance(item, dict):
                labels.append(clean_operator_relationship_label(first_text(item.get("label"), " / ".join(item.get("display_columns") or []), " / ".join(item.get("columns") or []))))
            else:
                labels.append(clean_operator_relationship_label(item))
    for item in relationships:
        if not isinstance(item, dict):
            continue
        labels.append(clean_operator_relationship_label(first_text(item.get("name"), " / ".join(item.get("display_columns") or []), " / ".join(item.get("columns") or []))))
    return dedupe([label for label in labels if label])[:6]


def clean_operator_relationship_label(value: Any) -> str:
    text = first_text(value)
    text = text.replace(" shifted", "").replace("Shifted", "")
    text = text.replace(" / ", " <-> ")
    return " ".join(text.split())


def operator_confidence_label(label: str, score: Any) -> str:
    text = str(label or "").lower()
    if "high" in text or "strong" in text or "confirmed" in text:
        return "High"
    if "moderate" in text or "medium" in text or "present" in text:
        return "Medium"
    numeric = numeric_confidence_score(score, 0.0)
    if numeric >= 0.75:
        return "High"
    if numeric >= 0.45:
        return "Medium"
    return "Low"


def operator_urgency_label(primary: dict[str, Any], relationships: list[dict[str, Any]], changed: bool) -> str:
    severity = str(primary.get("severity") if primary else "").lower()
    if severity in {"high", "critical"}:
        return "High"
    if severity in {"moderate", "medium", "elevated"} or changed or len(relationships) >= 2:
        return "Medium"
    return "Low"


def operator_fingerprint_status(fingerprint: dict[str, Any], changed: bool) -> str:
    status = str(fingerprint.get("status") or fingerprint.get("drift_status") or "").lower()
    if changed or status in {"changed", "drifting", "review", "unstable"}:
        return "Changed"
    if status == "stable":
        return "Stable"
    return "Pending"


def operator_possible_causes(primary: dict[str, Any], system: str, relationship_labels: list[str]) -> list[str]:
    return [
        "Operating setpoint modification",
        "Control sequence adjustment",
        "Process demand change",
        "Equipment operating state change",
        "Recent maintenance activity",
        "Sensor calibration change",
    ]


def operator_review_items(
    system: str,
    relationship_labels: list[str],
    recommendations: list[dict[str, Any]],
    operator_report: dict[str, Any],
) -> list[str]:
    return [
        "Operator logs",
        "Maintenance activity",
        "Control mode changes",
        "Setpoint changes",
        "Equipment state changes",
        "Demand during the detected window",
    ]


def operator_relationship_change_entries(primary: dict[str, Any], relationships: list[dict[str, Any]]) -> list[dict[str, str]]:
    candidates: list[tuple[str, str]] = []
    if primary:
        for value in primary.get("affected_relationships") or []:
            raw = first_text(value)
            candidates.append((clean_operator_relationship_label(raw), raw))
        for item in primary.get("contributing_relationships") or []:
            if isinstance(item, dict):
                display = first_text(item.get("label"), " / ".join(item.get("display_columns") or []), " / ".join(item.get("columns") or []))
                raw = first_text(item.get("relationship"), item.get("raw_identifier"), " / ".join(item.get("columns") or []), display)
                candidates.append((clean_operator_relationship_label(display), raw))
            else:
                raw = first_text(item)
                candidates.append((clean_operator_relationship_label(raw), raw))
    for item in relationships:
        if not isinstance(item, dict):
            continue
        display = first_text(item.get("name"), " / ".join(item.get("display_columns") or []), " / ".join(item.get("columns") or []))
        raw = first_text(item.get("display_relationship"), item.get("relationship"), item.get("raw_identifier"), " / ".join(item.get("columns") or []), display)
        candidates.append((clean_operator_relationship_label(display), raw))

    entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for label, raw in candidates:
        if not label and not raw:
            continue
        display_label = operator_relationship_public_label(label, raw, len(entries))
        key = display_label.lower()
        if key in seen:
            continue
        seen.add(key)
        entries.append(compact_dict({"label": display_label, "raw_identifier": raw}))
    return entries[:8]


def operator_relationship_public_label(label: str, raw: str, index: int) -> str:
    candidate = clean_operator_relationship_label(label or raw)
    if operator_relationship_label_is_generic(candidate):
        return f"Relationship {chr(ord('A') + index)}"
    return candidate


def operator_relationship_label_is_generic(label: str) -> bool:
    text = str(label or "").lower()
    generic_tokens = ["exogenous", "numeric ", "column ", "unknown", "unnamed"]
    return any(token in text for token in generic_tokens)


def operator_advanced_details(entries: list[dict[str, str]]) -> dict[str, Any]:
    raw_identifiers = []
    for entry in entries:
        raw = first_text(entry.get("raw_identifier"))
        label = first_text(entry.get("label"))
        if raw and raw != label:
            raw_identifiers.append(f"{label}: {raw}")
    return compact_dict({"raw_relationship_identifiers": dedupe(raw_identifiers)})


def operator_investigation_steps(
    system: str,
    relationship_labels: list[str],
    recommendations: list[dict[str, Any]],
    operator_report: dict[str, Any],
) -> list[str]:
    combined = " ".join([system, *relationship_labels]).lower()
    if any(token in combined for token in ["flow", "pressure", "pump", "valve", "vfd", "filter", "hydraulic"]):
        steps = [
            "Review recent maintenance activity and operator logs.",
            "Inspect filter condition and differential pressure trends.",
            "Verify current pump loading and operating point.",
            "Review operating setpoints, valve positions, and VFD commands.",
            "Compare current flow and pressure response with historical operation.",
        ]
    elif any(token in combined for token in ["chemical", "chlor", "dose", "feed", "quality", "ph", "orp"]):
        steps = [
            "Review chemical feed trends.",
            "Verify current dosing setpoints and feed pump status.",
            "Compare water quality readings with historical operation.",
            "Review recent chemical changes and operator logs.",
            "Confirm control commands match expected operation.",
        ]
    elif any(token in combined for token in ["thermal", "cooling", "heat", "chiller", "condenser", "tower"]):
        steps = [
            "Review heat transfer and temperature approach trends.",
            "Verify current equipment staging and operating point.",
            "Compare flow and valve positions with historical operation.",
            "Review recent maintenance and load changes.",
            "Confirm control commands match expected operation.",
        ]
    else:
        steps = [
            "Review the contributing signal trends.",
            "Verify current operating mode and setpoints.",
            "Compare equipment states with historical operation.",
            "Review recent maintenance and operator logs.",
            "Monitor the next operating window for persistence.",
        ]
    extra = [str(item.get("recommendation") or item.get("next_check") or "") for item in recommendations if isinstance(item, dict)]
    report_checks = operator_report.get("recommended_operator_checks") if isinstance(operator_report.get("recommended_operator_checks"), list) else []
    return dedupe([*steps, *extra, *report_checks])[:7]


def operator_executive_summary(system: str, relationship_labels: list[str], fingerprint: dict[str, Any], changed: bool) -> list[str]:
    if not changed:
        return [
            "Behavior stayed within the historical operating pattern during the analyzed period.",
            "No subsystem-level operating shift was flagged for review.",
        ]
    relationship_sentence = (
        "Multiple operational relationships changed together, suggesting a system-level operational shift rather than an isolated sensor anomaly."
        if len(relationship_labels) >= 2 else
        "One operational relationship changed enough to warrant operator review."
    )
    return [
        "Behavior within this subsystem deviated from its historical operating pattern during the analyzed period.",
        relationship_sentence,
    ]


def operator_what_changed(primary: dict[str, Any], system: str, relationship_labels: list[str], changed: bool) -> list[str]:
    if changed:
        relationship_count = len(relationship_labels)
        count_label = (
            f"{relationship_count} operational relationship{'s' if relationship_count != 1 else ''} changed"
            if relationship_count else
            "Operational relationships changed"
        )
        return [
            count_label,
            f"Changes occurred within the {system} subsystem",
            "Relationship fingerprint differs from the established baseline",
        ]
    return [
        "No reviewed operational relationship moved outside the baseline threshold",
        f"{system} behavior remained consistent with the established baseline",
    ]


def operator_why_it_matters(primary: dict[str, Any], changed: bool) -> list[str]:
    direct = first_text(
        primary.get("possible_operational_consequence") if primary else "",
        primary.get("possible_consequence") if primary else "",
        primary.get("why_it_matters") if primary else "",
    )
    if direct:
        return [direct]
    if changed:
        return [
            "When several operating relationships change together, the underlying operating state of the subsystem may have shifted.",
            "This is commonly observed before operators can isolate a single failed component.",
        ]
    return ["Stable relationships reduce the need to investigate this subsystem first."]


def operator_relationship_persistence(relationships: list[dict[str, Any]]) -> str:
    if not relationships:
        return "Low"
    sample_counts = []
    for relationship in relationships:
        try:
            sample_counts.append(min(int(relationship.get("baseline_sample_size") or 0), int(relationship.get("recent_sample_size") or 0)))
        except (TypeError, ValueError):
            sample_counts.append(0)
    if max(sample_counts or [0]) >= 12:
        return "High"
    if max(sample_counts or [0]) >= 4:
        return "Medium"
    return "Low"


def operator_did_not_observe(system: str, systems: list[dict[str, Any]], relationships: list[dict[str, Any]], baseline: dict[str, Any]) -> list[str]:
    active_text = " ".join(
        [system, *[str(item.get("name") or "") for item in systems if isinstance(item, dict)], *[str(item.get("system") or "") for item in relationships if isinstance(item, dict)]]
    ).lower()
    candidates = [
        ("thermal", "No evidence of abnormal thermal subsystem behavior was flagged."),
        ("chemical", "Chemical feed relationships remain consistent with the available baseline."),
        ("electrical", "Electrical load relationships remain stable in the reviewed evidence."),
        ("water quality", "Water quality relationships remain consistent with the available baseline."),
    ]
    observations = [message for token, message in candidates if token not in active_text]
    if baseline.get("overall_assessment") == "normal" and not relationships:
        observations.insert(0, "No subsystem-level relationship change was flagged.")
    return observations[:3]


def operator_trend(result: dict[str, Any], baseline: dict[str, Any], changed: bool) -> dict[str, Any]:
    timestamp = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    drift_trajectory = baseline.get("drift_trajectory") if isinstance(baseline.get("drift_trajectory"), dict) else {}
    progression = first_text(drift_trajectory.get("direction"), drift_trajectory.get("trend"))
    return compact_dict(
        {
            "first_observed": first_text(timestamp.get("first_timestamp"), result.get("deformation_started_at"), "Current analysis window"),
            "direction": progression.capitalize() if progression else ("Increasing" if changed else "Stable"),
            "subsystem_stability": "Declining" if changed else "Stable",
            "recommended_follow_up": "Monitor next 24 hours" if changed else "Continue routine monitoring",
        }
    )


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
    pair = relationship_pair_phrase(label)
    if change_type == "missing":
        return f"The historical relationship between {pair} no longer follows its established operating pattern."
    if change_type == "weakened":
        return f"The historical relationship between {pair} weakened substantially during the analysis window."
    if change_type in {"disrupted", "inverted"}:
        return f"The historical relationship between {pair} shifted from its established operating pattern."
    if change_type == "new":
        return f"A new operating relationship between {pair} emerged during the analysis window and should be checked against operating changes."
    if change_type == "strengthened":
        return f"{pair} became more tightly coupled than their historical operating pattern."
    return f"The relationship between {pair} changed significantly from baseline operation."


def relationship_pair_phrase(label: str) -> str:
    text = first_text(label, "these signals")
    for separator in ["<->", " / ", " vs ", " vs. "]:
        if separator in text:
            parts = [part.strip() for part in text.split(separator, 1) if part.strip()]
            if len(parts) == 2:
                return f"{parts[0]} and {parts[1]}"
    return text


def relationship_confidence_basis(label: str, item: dict[str, Any]) -> str:
    return (
        f"Neraium compared how {label} usually moves in the baseline window with how it moved in the current window."
    )


def confidence_rationale_for_relationship(item: dict[str, Any], confidence_score: float) -> str:
    return "Confidence reflects comparison-window coverage and how clearly the operating pattern departed from its usual behavior. Technical values are retained in evidence."


def confidence_rationale_for_metric(item: dict[str, Any], persistence_detail: dict[str, Any], confidence_score: float) -> str:
    if persistence_detail:
        return "Confidence reflects the size of the signal movement and whether recent readings continued in the same direction."
    return "Confidence reflects the size of the signal movement and the baseline/current window coverage."


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
        summary = first_text(item.get("summary"), *(item.get("supporting_signals") or []))
        if summary:
            summaries.append(summary)
            continue
        if item.get("relevant_metric_changes"):
            summaries.append("Baseline/current evidence is available in the technical details.")
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
                    metric_change("Operating pattern change", item.get("correlation_delta")),
                    metric_change("Baseline operating coupling", item.get("baseline_strength", item.get("coupling_strength"))),
                    metric_change("Current operating coupling", item.get("current_strength", item.get("strength"))),
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
    column = signal_label_from_item(item)
    direction = str(item.get("direction") or "changed")
    return f"{column} moved {direction} from the baseline window to the current window."


def metric_confidence_basis(item: dict[str, Any], persistence_detail: dict[str, Any]) -> str:
    column = signal_label_from_item(item) or "this signal"
    persistence = persistence_phrase(persistence_detail)
    basis = f"Neraium compared baseline and current windows for {column}"
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
    column_label = signal_label_from_item(item)
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
                "display_name": column_label,
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
    display_columns = relationship_display_columns(item)
    return compact_dict(
        {
            "id": f"relationship-{index}",
            "columns": columns,
            "display_columns": display_columns,
            "label": relationship_label(item),
            "relationship_type": item.get("relationship_type"),
            "change_type": item.get("change_type"),
            "strength": item.get("strength"),
            "baseline_strength": item.get("baseline_strength"),
            "current_strength": item.get("current_strength"),
            "change_percentage": item.get("change_percentage"),
            "confidence_score": item.get("confidence_score"),
            "relationship_importance_score": item.get("relationship_importance_score"),
            "relationship_importance_rationale": item.get("relationship_importance_rationale"),
            "ranking_factors": item.get("ranking_factors"),
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
                    "label": signal_label_from_item(item),
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
                    "label": " / ".join(relationship_display_columns(item)) or item.get("display_relationship") or item.get("relationship"),
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
            "relationship_changes": [
                relationship_operator_summary(
                    item,
                    " / ".join(relationship_display_columns(item)) or str(item.get("display_relationship") or item.get("relationship") or "Signal relationship"),
                )
                for item in relationship_changes[:5]
            ],
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
                    "summary": relationship_operator_summary(
                        item,
                        " / ".join(relationship_display_columns(item)) or str(item.get("display_relationship") or item.get("relationship") or "Signal relationship"),
                    ),
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
                    metric_change("Operating pattern change", item.get("correlation_delta")),
                    metric_change("Baseline operating coupling", item.get("baseline_correlation")),
                    metric_change("Current operating coupling", item.get("recent_correlation")),
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


def is_supporting_context_item(item: dict[str, Any]) -> bool:
    column = str(item.get("column") or "")
    metric_type = str(item.get("metric_type") or "")
    classification = item.get("telemetry_classification") if isinstance(item.get("telemetry_classification"), dict) else {}
    category = str(item.get("telemetry_category") or classification.get("category") or "")
    role = str(item.get("analysis_role") or classification.get("analysis_role") or "")
    return (
        is_cumulative_context_item(item)
        or role == "supporting_context"
        or category in {"scheduled_load_context", "weather_environment", "setpoint", "identifier_constant", "identifier", "constant", "cumulative_counter", "counter", "ground_truth_label", "binary_status", "equipment_state", "synthetic_feature", "timestamp", "unknown"}
        or is_context_or_supporting_column(column, metric_type=metric_type or None)
    )


def context_driver_drift_items(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    items = [
        item for item in baseline.get("column_drift", [])
        if isinstance(item, dict)
        and is_supporting_context_item(item)
        and item.get("drift_flag") == "context"
    ]
    items.sort(key=lambda item: abs(float(item.get("percent_change") or item.get("absolute_change") or 0)), reverse=True)
    return items[:4]


def context_modifier_evidence_items(
    *,
    context_items: list[dict[str, Any]],
    time_window: str,
    source_ranges: list[dict[str, Any]],
    upload_id: str,
    analysis_id: str,
) -> list[dict[str, Any]]:
    if not context_items:
        return []
    changes = [context_change_sentence(item) for item in context_items if context_change_sentence(item)]
    if not changes:
        return []
    return [
        compact_dict(
            {
                "id": "context-modifier-evidence-0",
                "type": "context_modifier",
                "summary": "Context/load signals were reviewed as explanatory modifiers, not primary anomalies.",
                "supporting_signals": changes,
                "relevant_metric_changes": changes,
                "source_columns": [str(item.get("column")) for item in context_items if item.get("column")],
                "source_metrics": [str(item.get("column")) for item in context_items if item.get("column")],
                "source_tags": [str(item.get("column")) for item in context_items if item.get("column")],
                "display_names": [signal_label_from_item(item) for item in context_items if item.get("column")],
                "source_time_ranges": source_ranges,
                "time_window": time_window,
                "confidence": "moderate",
                "confidence_score": 0.65,
                "source_upload_id": upload_id,
                "analysis_id": analysis_id,
            }
        )
    ]


def context_change_sentence(item: dict[str, Any]) -> str:
    column = signal_label_from_item(item) or "Context signal"
    direction = str(item.get("direction") or "changed")
    percent = item.get("percent_change")
    if percent is not None:
        return f"{column} moved {direction} by {percent}% and was treated as context/load evidence."
    return f"{column} moved {direction} and was treated as context/load evidence."


def relationship_importance_sort_key(item: dict[str, Any]) -> tuple[float, float, float]:
    return (
        float(item.get("relationship_importance_score") or 0.0),
        abs(float(item.get("correlation_delta") or 0.0)),
        float(item.get("confidence_score") or 0.0),
    )


def relationship_is_context_only(item: dict[str, Any]) -> bool:
    context = item.get("relationship_context") if isinstance(item.get("relationship_context"), dict) else {}
    if context.get("operator_primary_eligible") is False:
        return True
    if context.get("context_only") is True:
        return True
    classifications = item.get("column_classifications") if isinstance(item.get("column_classifications"), list) else []
    if classifications:
        return all(not classification.get("is_primary_anomaly_candidate") for classification in classifications if isinstance(classification, dict))
    columns = relationship_columns(item)
    return bool(columns) and all(is_context_or_supporting_column(column) for column in columns)


def cluster_relationship_changes(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for item in items:
        key = relationship_cluster_key(item)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)
    for group in groups.values():
        group.sort(key=relationship_importance_sort_key, reverse=True)
    return sorted((groups[key] for key in order), key=lambda group: relationship_importance_sort_key(group[0]), reverse=True)


def relationship_cluster_key(item: dict[str, Any]) -> str:
    columns = relationship_columns(item)
    signal_names = [*columns, *relationship_display_columns(item)]
    subsystem = relationship_subsystem_name(signal_names)
    if subsystem == GENERIC_SUBSYSTEM_NAME:
        return "observed:" + ":".join(sorted(columns[:2]))
    return subsystem.lower().replace(" / ", "_").replace(" ", "_")


def operational_diagnosis_title(
    system: str,
    names: list[str],
    group: list[dict[str, Any]],
    confidence_score: float,
) -> str:
    if system == GENERIC_SUBSYSTEM_NAME or confidence_label_from_score(confidence_score) == "limited":
        return GENERIC_SUBSYSTEM_NAME
    combined = relationship_context_text(system, names, group)
    evidence_context = relationship_context_text("", names, group)
    if all(token in evidence_context for token in ["pump", "power"]) and any(token in evidence_context for token in ["filter", "dp", "differential pressure", "flow", "hydraulic resistance"]):
        return "Pump Efficiency Degrading"
    if system == "Pumping System" and "pump" in combined and any(token in combined for token in ["vibration", "bearing", "current", "amp"]):
        return "Pump Mechanical Behavior Degrading"
    if any(token in combined for token in ["flow", "pressure", "hydraulic", "filter", "valve", "suction", "discharge"]):
        return f"{system} Degrading" if system not in {GENERIC_SUBSYSTEM_NAME, "Uploaded telemetry"} else "Hydraulic Resistance Increasing"
    if any(token in combined for token in ["chemical", "chlor", "dose", "feed", "turbidity", "orp", "ph", "quality", "conductivity"]):
        return f"{system} Control Drift" if system not in {GENERIC_SUBSYSTEM_NAME, "Uploaded telemetry"} else "Water Quality Control Drift"
    if any(token in combined for token in ["thermal", "cooling", "heat", "chiller", "condenser", "tower", "temperature"]):
        if system in {GENERIC_SUBSYSTEM_NAME, "Uploaded telemetry"}:
            return "Heat Transfer Performance Degrading"
        return f"{system} Degrading" if "performance" in system.lower() else f"{system} Performance Degrading"
    return f"{system} Behavior Degrading"


def relationship_context_text(system: str, names: list[str], group: list[dict[str, Any]]) -> str:
    values: list[str] = [system, *[str(name or "") for name in names]]
    for item in group:
        values.extend(relationship_columns(item))
        values.extend(relationship_display_columns(item))
        values.extend([str(item.get("summary") or ""), str(item.get("relationship") or "")])
    return " ".join(values).lower().replace("_", " ").replace("-", " ")


def relationship_observed_facts(
    *,
    group: list[dict[str, Any]],
    baseline: dict[str, Any],
    source_ranges: list[dict[str, Any]],
) -> list[str]:
    facts: list[str] = []
    drift_by_column = {
        str(item.get("column") or ""): item
        for item in baseline.get("column_drift", [])
        if isinstance(item, dict) and item.get("column")
    }
    seen_columns: set[str] = set()
    for relationship in group:
        for column in relationship_columns(relationship):
            if column in seen_columns:
                continue
            seen_columns.add(column)
            drift_item = drift_by_column.get(column)
            if drift_item:
                facts.append(metric_observed_fact(drift_item))
        facts.append(relationship_strength_fact(relationship))
    window = observed_window_fact(source_ranges)
    if window:
        facts.append(window)
    trajectory = baseline.get("drift_trajectory") if isinstance(baseline.get("drift_trajectory"), dict) else {}
    direction = first_text(trajectory.get("direction"), trajectory.get("trend"))
    if direction:
        facts.append(f"Drift trajectory: {direction}.")
    return dedupe([fact for fact in facts if fact])[:8]


def metric_observed_fact(item: dict[str, Any]) -> str:
    label = signal_label_from_item(item)
    direction = str(item.get("direction") or "changed")
    percent = item.get("percent_change")
    absolute = item.get("absolute_change")
    if percent is not None:
        return f"{label} {direction_word(direction)} {format_signed_percent(percent)}."
    if absolute is not None:
        return f"{label} {direction_word(direction)} by {absolute}."
    return f"{label} moved {direction} from its learned operating range."


def relationship_strength_fact(item: dict[str, Any]) -> str:
    label = " / ".join(relationship_display_columns(item)) or first_text(item.get("display_relationship"), item.get("relationship"), "Operating relationship")
    baseline = first_text(item.get("baseline_strength"), item.get("baseline_correlation"), item.get("coupling_strength"))
    current = first_text(item.get("current_strength"), item.get("recent_correlation"), item.get("strength"))
    change_type = first_text(item.get("change_type"), "changed").replace("_", " ")
    if baseline and current:
        return f"{label} operating coupling {change_type} from {baseline} to {current}."
    delta = first_text(item.get("correlation_delta"), item.get("change_percentage"))
    if delta:
        return f"{label} operating behavior changed; magnitude {delta}."
    return f"{label} operating behavior changed from the learned fingerprint."


def observed_window_fact(source_ranges: list[dict[str, Any]]) -> str:
    for item in source_ranges:
        if not isinstance(item, dict):
            continue
        start = first_text(item.get("current_start"), item.get("start"), item.get("baseline_start"))
        end = first_text(item.get("current_end"), item.get("end"), item.get("baseline_end"))
        if start and end:
            return f"Observed during {start} to {end}."
        if start:
            return f"Started around {start}."
        if item.get("window"):
            return f"Observed during {item.get('window')}."
    return ""


def direction_word(direction: str) -> str:
    text = str(direction or "").lower()
    if text in {"up", "increase", "increased", "rising", "high"}:
        return "increased"
    if text in {"down", "decrease", "decreased", "falling", "low"}:
        return "decreased"
    return "changed"


def format_signed_percent(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return f"by {value}%"
    sign = "+" if number > 0 else ""
    if number.is_integer():
        return f"{sign}{int(number)}%"
    return f"{sign}{number:.1f}%"


def relationship_why_this_matters(system: str, names: list[str]) -> list[str]:
    combined = " ".join([system, *[str(name or "") for name in names]]).lower().replace("_", " ").replace("-", " ")
    if any(token in combined for token in ["flow", "pressure", "hydraulic", "pump", "valve", "vfd", "filter"]):
        return [
            "Higher energy consumption for the same hydraulic output",
            "Reduced filtration or flow performance",
            "Increased risk of cavitation, overload, or nuisance trips",
            "More rapid equipment wear if restriction continues",
        ]
    if any(token in combined for token in ["chemical", "chlor", "dose", "feed", "turbidity", "orp", "ph", "quality"]):
        return [
            "Reduced treatment consistency",
            "Higher chemical use or under-dosing risk",
            "Water quality excursions may develop before alarms trigger",
            "Operator response may be delayed if sensor drift is not ruled out",
        ]
    if any(token in combined for token in ["thermal", "cooling", "heat", "chiller", "condenser", "tower", "temperature"]):
        return [
            "Higher energy consumption for the same cooling load",
            "Reduced heat-transfer capacity",
            "Increased risk of equipment staging or limit problems",
            "Fouling or flow imbalance can compound if left unresolved",
        ]
    return [
        "Operating behavior may continue moving away from the learned fingerprint",
        "Energy, quality, or reliability risk can increase if the cause is not isolated",
        "Operators may spend more time troubleshooting without a first-check path",
    ]


def recommended_investigation_steps(system: str, names: list[str], label: str) -> list[str]:
    combined = " ".join([system, label, *[str(name or "") for name in names]]).lower().replace("_", " ").replace("-", " ")
    if any(token in combined for token in ["flow", "pressure", "hydraulic", "pump", "valve", "vfd", "filter"]):
        return [
            "Inspect filter differential pressure trend.",
            "Confirm valve lineup and suction restrictions.",
            "Review maintenance or cleaning performed within the last week.",
            "Compare pump power, speed, flow, and pressure against the expected operating curve.",
        ]
    if any(token in combined for token in ["chemical", "chlor", "dose", "feed", "turbidity", "orp", "ph", "quality"]):
        return [
            "Verify chemical feed setpoint and feed pump status.",
            "Check water quality sensor calibration and sample timing.",
            "Review chemical deliveries, dilution changes, and maintenance activity.",
            "Compare dosing response against turbidity, ORP, and pH trends.",
        ]
    if any(token in combined for token in ["thermal", "cooling", "heat", "chiller", "condenser", "tower", "temperature"]):
        return [
            "Check approach temperature and heat-transfer trends.",
            "Confirm equipment staging, valve position, and flow state.",
            "Review recent cleaning, weather, and load changes.",
            "Compare current power and temperature response against historical operation.",
        ]
    return [
        "Review the contributing signal trends.",
        "Confirm current operating mode and setpoints.",
        "Review recent maintenance and operator logs.",
        "Monitor the next operating window to confirm persistence.",
    ]


def relationship_behavior_interpretation(system: str, names: list[str], causes: list[str]) -> str:
    combined = " ".join([system, *[str(name or "") for name in names], *causes]).lower().replace("_", " ").replace("-", " ")
    if any(token in combined for token in ["pump", "flow", "pressure", "hydraulic", "filter"]):
        return "The system is requiring different hydraulic behavior than its established fingerprint. This pattern is more consistent with increasing restriction or changed pump operating point than normal demand variation."
    if any(token in combined for token in ["chemical", "chlor", "dose", "feed", "quality"]):
        return "Treatment response no longer matches the learned control fingerprint. This pattern is consistent with feed, sensor, or source-water changes that should be separated before changing controls."
    if any(token in combined for token in ["thermal", "cooling", "heat", "chiller", "condenser", "tower"]):
        return "Thermal output no longer matches the learned equipment response. This pattern is consistent with fouling, staging, flow imbalance, or load changes."
    return "Current equipment behavior no longer matches its established operating fingerprint. Review the first listed check before treating the finding as a sensor-only issue."


def relationship_activity_timeline(
    *,
    system: str,
    facts: list[str],
    first_check: str,
    source_ranges: list[dict[str, Any]],
) -> list[dict[str, str]]:
    base_time = timeline_base_time(source_ranges)
    entries = []
    for index, fact in enumerate(facts[:3]):
        entries.append(
            compact_dict(
                {
                    "time": timeline_time_label(base_time, index),
                    "title": timeline_title_from_fact(fact),
                    "detail": fact,
                }
            )
        )
    entries.append(
        compact_dict(
            {
                "time": timeline_time_label(base_time, len(entries)),
                "title": f"Behavior classified as {system} degradation.",
                "detail": first_check or "Investigation recommended.",
            }
        )
    )
    return entries[:4]


def timeline_base_time(source_ranges: list[dict[str, Any]]) -> str:
    for item in source_ranges:
        if not isinstance(item, dict):
            continue
        value = first_text(item.get("current_start"), item.get("start"), item.get("baseline_start"))
        if value:
            return value
    return "Current window"


def timeline_time_label(base_time: str, index: int) -> str:
    if not base_time or base_time == "Current window":
        return "Current window" if index == 0 else f"+{index * 3} min"
    return base_time if index == 0 else f"+{index * 3} min"


def timeline_title_from_fact(fact: str) -> str:
    clean = fact.rstrip(".")
    if " operating coupling " in clean:
        return "Operating relationship deviated from learned behavior."
    if "Observed during" in clean or "Started around" in clean:
        return "Change window established."
    return clean


def merged_relationship_title(group: list[dict[str, Any]], primary: dict[str, Any], subsystem: str, confidence_score: float) -> str:
    if subsystem == GENERIC_SUBSYSTEM_NAME or confidence_label_from_score(confidence_score) == "limited":
        return GENERIC_SUBSYSTEM_NAME
    return f"{subsystem} behavior changed"


def merged_relationship_observable_sentence(group: list[dict[str, Any]], primary: dict[str, Any]) -> str:
    if len(group) <= 1:
        return relationship_observable_sentence(relationship_columns(primary), primary)
    relationships = "; ".join(relationship_label(item) for item in group[:4])
    return f"{len(group)} related relationships shifted away from the historical operating pattern: {relationships}."


def merged_relationship_reason(group: list[dict[str, Any]], primary: dict[str, Any], label: str) -> str:
    rationale = first_text(primary.get("relationship_importance_rationale"), relationship_confidence_basis(label, primary))
    if len(group) <= 1:
        return rationale
    return f"{rationale} Neraium grouped the related changes because they describe the same subsystem behavior instead of separate isolated sensor findings."


def relationship_label(item: dict[str, Any]) -> str:
    columns = relationship_display_columns(item)
    if len(columns) >= 2:
        return f"{columns[0]} <-> {columns[1]} shifted"
    return first_text(item.get("display_relationship"), item.get("relationship"), item.get("summary"), "Relationship shifted")


def dedupe_ranges(ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in ranges:
        if not isinstance(item, dict):
            continue
        key = str(sorted(item.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def is_cumulative_context_item(item: dict[str, Any]) -> bool:
    column = str(item.get("column") or "")
    return (
        item.get("metric_type") == "cumulative_counter"
        or item.get("analysis_role") == "supporting_context"
        or is_cumulative_counter_name(column)
    )


def relationship_has_cumulative_counter(item: dict[str, Any]) -> bool:
    return any(is_cumulative_counter_name(column) for column in relationship_columns(item))


def signal_label_from_item(item: dict[str, Any]) -> str:
    return first_text(item.get("display_name"), item.get("normalized_name"), item.get("original_header"), item.get("column"), "Signal")


def relationship_display_columns(item: dict[str, Any]) -> list[str]:
    display_columns = item.get("display_columns")
    if isinstance(display_columns, list):
        values = dedupe([str(column) for column in display_columns if column])
        if values:
            return values
    metadata = item.get("source_column_metadata") if isinstance(item.get("source_column_metadata"), list) else []
    values = [first_text(meta.get("display_name"), meta.get("normalized_name"), meta.get("original_header"), meta.get("source_column")) for meta in metadata if isinstance(meta, dict)]
    values = dedupe([value for value in values if value])
    return values or relationship_columns(item)


GENERIC_SUBSYSTEM_NAME = "Observed subsystem behavior changed"


def relationship_group_signal_names(group: list[dict[str, Any]]) -> list[str]:
    names: list[str] = []
    for item in group:
        names.extend(relationship_columns(item))
        names.extend(relationship_display_columns(item))
    return dedupe(names)


def relationship_subsystem_name(names: list[str], confidence_score: float | None = None, *, allow_generic: bool = True) -> str:
    if confidence_score is not None and confidence_label_from_score(confidence_score) == "limited":
        return GENERIC_SUBSYSTEM_NAME if allow_generic else "Uploaded telemetry"
    scores = telemetry_group_scores(names)
    if not scores:
        return GENERIC_SUBSYSTEM_NAME if allow_generic else "Uploaded telemetry"
    combined = " ".join(str(name or "").lower().replace("_", " ").replace("-", " ") for name in names)
    if scores.get("lift_station") and ("wet well" in combined or "wetwell" in combined or "lift station" in combined or ("pump" in combined and "status" in combined and "flow" in combined)):
        return "Lift Station Operations"
    if scores.get("flow_pressure") and scores.get("chemical_water_quality") and scores["flow_pressure"] >= scores["chemical_water_quality"]:
        return "Flow & Pressure"
    winner, winner_score = max(scores.items(), key=lambda item: item[1])
    if winner_score < 2 and allow_generic:
        return GENERIC_SUBSYSTEM_NAME
    tied = [name for name, score in scores.items() if score == winner_score]
    if len(tied) > 1 and allow_generic:
        return GENERIC_SUBSYSTEM_NAME
    labels = {
        "flow_pressure": flow_pressure_label(names),
        "chemical_water_quality": chemical_water_quality_label(names),
        "lift_station": "Lift Station Operations",
        "thermal_transfer": thermal_performance_label(names),
        "moisture_control": "Moisture Control",
        "schedule_energy": "Energy & Schedule Operations",
    }
    return labels.get(winner, GENERIC_SUBSYSTEM_NAME if allow_generic else "Uploaded telemetry")


def flow_pressure_label(names: list[str]) -> str:
    combined = " ".join(str(name or "").lower().replace("_", " ").replace("-", " ") for name in names)
    if "pump" in combined and any(token in combined for token in ["vibration", "power", "kw", "speed", "amp", "current"]):
        return "Pumping System"
    if any(token in combined for token in ["flow", "pressure", "valve", "suction", "discharge"]):
        return "Flow & Pressure"
    return "Hydraulic Performance"


def chemical_water_quality_label(names: list[str]) -> str:
    combined = " ".join(str(name or "").lower().replace("_", " ").replace("-", " ") for name in names)
    if any(token in combined for token in ["dose", "feed", "chemical", "chlorine", "chlor"]):
        return "Chemical Feed"
    if any(token in combined for token in ["orp", "disinfect"]):
        return "Disinfection"
    return "Water Quality"


def thermal_performance_label(names: list[str]) -> str:
    combined = " ".join(str(name or "").lower().replace("_", " ").replace("-", " ") for name in names)
    if any(token in combined for token in ["tower", "condenser", "ct ", "heat rejection"]):
        return "Heat Rejection"
    if any(token in combined for token in ["chiller", "chw", "cooling"]):
        return "Cooling Distribution"
    return "Thermal Performance"


def telemetry_group_scores(names: list[str]) -> dict[str, int]:
    scores: dict[str, int] = {}
    normalized_names = [str(name or "").lower().replace("_", " ").replace("-", " ") for name in names if str(name or "").strip()]
    combined = " ".join(normalized_names)
    if ("wet well" in combined or "wetwell" in combined) and any(token in combined for token in ["pump", "flow"]):
        scores["lift_station"] = 4
    if "pump" in combined and "status" in combined and "flow" in combined:
        scores["lift_station"] = max(scores.get("lift_station", 0), 3)
    for name in normalized_names:
        for group in telemetry_groups_for_signal(name, combined):
            scores[group] = scores.get(group, 0) + 1
    return scores


def telemetry_groups_for_signal(name: str, combined: str) -> list[str]:
    groups: list[str] = []
    has_temp = any(token in name for token in ["temp", "temperature", "thermal"])
    has_thermal_equipment = any(token in name for token in ["condenser", "chiller", "evaporator", "cooling", "heating", "chw", "lwt", "ewt"])
    if "wet well" in name or "wetwell" in name or ("lift" in name and "station" in name):
        groups.append("lift_station")
    if "level" in name and any(token in combined for token in ["wet well", "wetwell", "lift station", "sewer"]):
        groups.append("lift_station")
    if any(token in name for token in ["chlorine", "chlor", "dose", "feed", "chemical", "turbidity", "orp", "disinfect", "quality", "ph", "conductivity"]):
        groups.append("chemical_water_quality")
    if any(token in name for token in ["flow", "pressure", "pump", "valve", "main", "suction", "discharge", "speed", "power", "kw", "vibration"]):
        groups.append("flow_pressure")
    if has_thermal_equipment or (has_temp and any(token in combined for token in ["condenser", "chiller", "evaporator", "supply", "return", "chw", "lwt", "ewt"])):
        groups.append("thermal_transfer")
    if any(token in name for token in ["humidity", "moisture", "vpd"]):
        groups.append("moisture_control")
    if any(token in name for token in ["runtime", "schedule", "energy"]):
        groups.append("schedule_energy")
    return groups


def relationship_operator_summary(item: dict[str, Any], label: str) -> str:
    summary = first_text(item.get("operator_summary"), item.get("summary"))
    if summary and not contains_algorithmic_relationship_language(summary):
        return summary
    return relationship_change_sentence(label, item)


def contains_algorithmic_relationship_language(value: str) -> bool:
    text = str(value or "").lower()
    return any(fragment in text for fragment in ["relationship missing", "correlation delta", "relationship strength", "baseline strength=", "current strength=", "delta=", "baseline=", "recent="])


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
    label = human_metric_label(first_text(item.get("display_name"), column))
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
    display_columns = relationship_display_columns(item) or columns
    subsystem = relationship_subsystem_name([*columns, *display_columns])
    if subsystem != GENERIC_SUBSYSTEM_NAME:
        return f"{subsystem} behavior changed"
    labels = [human_metric_label(column) for column in display_columns[:2]]
    if len(labels) == 2 and labels[0] != "Signal" and labels[1] != "Signal":
        return f"{labels[0]} and {labels[1]} relationship changed"
    return GENERIC_SUBSYSTEM_NAME


def relationship_observable_sentence(columns: list[str], item: dict[str, Any]) -> str:
    title = relationship_title(columns, item).rstrip(".")
    label = " / ".join(relationship_display_columns(item) or columns) or str(item.get("display_relationship") or item.get("relationship") or "these signals")
    return f"{title}; {relationship_change_sentence(label, item)}"


def relationship_recommended_action(system: str) -> str:
    if any(token in str(system or "").lower() for token in ["pump", "flow", "pressure", "hydraulic"]):
        return "Inspect filter differential pressure trend before checking pump performance."
    return f"Review {system.lower()} trends, operator logs, setpoint changes, maintenance activity, and demand changes for the same window."


def relationship_operational_impact_sentence(system: str, names: list[str], causes: list[str]) -> str:
    combined = " ".join([system, *[str(name or "") for name in names], *causes]).lower().replace("_", " ").replace("-", " ")
    if any(token in combined for token in ["flow", "pressure", "hydraulic", "pump", "valve", "vfd", "filter"]):
        return "Operational impact: This relationship change is consistent with conditions such as increasing hydraulic resistance, equipment degradation, operational changes, or recent maintenance. Investigation is recommended to determine the cause."
    if any(token in combined for token in ["chemical", "chlor", "dose", "feed", "turbidity", "orp", "ph", "quality", "disinfection"]):
        return "Operational impact: This relationship change is consistent with conditions such as feed calibration drift, water quality variation, control loop changes, or recent maintenance. Investigation is recommended to determine the cause."
    if any(token in combined for token in ["thermal", "cooling", "heat", "chiller", "condenser", "tower"]):
        return "Operational impact: This relationship change is consistent with conditions such as heat transfer degradation, equipment staging changes, load variation, or recent maintenance. Investigation is recommended to determine the cause."
    if any(token in combined for token in ["humidity", "moisture", "vpd"]):
        return "Operational impact: This relationship change is consistent with conditions such as airflow balance changes, latent load variation, control adjustments, or recent maintenance. Investigation is recommended to determine the cause."
    if any(token in combined for token in ["energy", "schedule", "runtime"]):
        return "Operational impact: This relationship change is consistent with conditions such as schedule changes, load profile shifts, control mode adjustments, or recent maintenance. Investigation is recommended to determine the cause."
    return "Operational impact: This relationship change is consistent with conditions such as a control mode change, equipment state change, sensor calibration issue, demand shift, or recent maintenance. Investigation is recommended to determine the cause."


def operational_cause_check(label: str, causes: list[str]) -> str:
    if not causes:
        return f"Investigate whether {label} changed after a known operating mode, load condition, or equipment state change."
    return f"Investigate whether any of these operating conditions changed during the same window: {'; '.join(causes[:5])}."


def possible_operational_causes(system: str, names: list[str]) -> list[str]:
    combined = " ".join([system, *[str(name or "") for name in names]]).lower().replace("_", " ").replace("-", " ")
    if any(token in combined for token in ["flow", "pressure", "hydraulic", "pump", "valve", "vfd", "filter"]):
        if any(token in combined for token in ["filter", "dp", "differential pressure"]):
            return [
                "Dirty filter",
                "Partial blockage",
                "Pump wear",
                "Valve position change",
                "Restricted suction",
                "Recent maintenance activity",
                "Sensor calibration issue",
            ]
        return [
            "Increasing filter resistance",
            "Pump operating point shifted",
            "Valve position changed",
            "Increased hydraulic resistance",
            "VFD control adjustment",
            "Recent maintenance activity",
            "Operational demand change",
        ]
    if any(token in combined for token in ["chemical", "chlor", "dose", "feed", "turbidity", "orp", "ph", "quality", "disinfection"]):
        return [
            "Feed pump calibration drift",
            "Chemical concentration changes",
            "Water quality variation",
            "Control loop tuning",
            "Process demand changes",
            "Recent maintenance activity",
        ]
    if any(token in combined for token in ["thermal", "cooling", "heat", "chiller", "condenser", "tower"]):
        return [
            "Heat exchanger fouling",
            "Cooling tower performance change",
            "Chiller staging or control adjustment",
            "Flow imbalance",
            "Outdoor load condition change",
            "Recent maintenance activity",
        ]
    if any(token in combined for token in ["humidity", "moisture", "vpd"]):
        return [
            "Airflow balance change",
            "Latent load variation",
            "Humidification or dehumidification control adjustment",
            "Envelope or ventilation change",
            "Operational demand change",
        ]
    if any(token in combined for token in ["energy", "schedule", "runtime"]):
        return [
            "Schedule change",
            "Load profile change",
            "Equipment runtime pattern changed",
            "Control mode adjustment",
            "Recent maintenance activity",
        ]
    return [
        "Setpoint or control mode change",
        "Equipment state change",
        "Sensor calibration drift",
        "Recent maintenance activity",
        "Operational demand change",
    ]


def metric_recommended_action(column: str, item: dict[str, Any]) -> str:
    label = human_metric_label(first_text(item.get("display_name"), column)).lower()
    if "vibration" in label:
        return "Prioritize pump mechanical review and trend the vibration signal against the next operating window."
    return f"Prioritize {label} in the next operations review and track whether it continues outside baseline."


def system_from_columns(columns: list[str]) -> str:
    subsystem = relationship_subsystem_name(columns, allow_generic=False)
    return subsystem if subsystem != GENERIC_SUBSYSTEM_NAME else "Uploaded telemetry"


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
    column = signal_label_from_item(item)
    direction = str(item.get("direction") or "changed")
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
