from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

from app.services.analysis_explanations import build_analysis_explanation
from app.services.cumulative_counters import is_cumulative_counter_name
from app.services.data_quality import parse_numeric_value
from app.services.telemetry_classification import classify_telemetry_signal


CONTRACT_VERSION = "analysis-result-v1"
NORMALIZED_RECORD_LIMIT = 500
PLACEHOLDER_TEXT = {
    "placeholder",
    "structural drift observed",
    "persistent structural drift observed",
    "pending verification",
}
UNSUPPORTED_TEXT_FRAGMENTS = (
    "pending verification",
    "maintenance correlation will appear",
    "demo system",
    "sample intelligence",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def attach_analysis_result(
    result: dict[str, Any],
    *,
    normalized_telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(result or {})
    payload["analysis_result"] = build_analysis_result(
        payload,
        normalized_telemetry=normalized_telemetry,
    )
    payload["analysis_id"] = payload["analysis_result"]["analysis_id"]
    if normalized_telemetry is not None:
        payload["normalized_telemetry"] = normalized_telemetry
    return payload


def ensure_analysis_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return empty_analysis_result()
    candidate = result.get("analysis_result")
    if is_canonical_analysis_result(candidate):
        return candidate
    return build_analysis_result(result, normalized_telemetry=result.get("normalized_telemetry"))


def is_canonical_analysis_result(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    required = {
        "analysis_id",
        "upload_id",
        "source_file",
        "generated_at",
        "data_quality",
        "executive_summary",
        "systems",
        "relationships",
        "fingerprint",
        "insights",
        "recommendations",
        "evidence_index",
        "warnings",
        "errors",
    }
    return required.issubset(value.keys())


def empty_analysis_result(
    *,
    analysis_id: str | None = None,
    upload_id: str | None = None,
    source_file: str | None = None,
    status: str = "empty",
    message: str | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    error_items = [clean_text(item) for item in (errors or []) if clean_text(item)]
    warning_items = [clean_text(message)] if message and not error_items else []
    return {
        "schema_version": CONTRACT_VERSION,
        "status": status,
        "analysis_id": clean_text(analysis_id),
        "upload_id": clean_text(upload_id),
        "source_file": clean_text(source_file),
        "generated_at": now_iso(),
        "change_onset": "",
        "stable_window": {},
        "deviation_window": {},
        "current_state_window": {},
        "data_quality": {
            "status": status,
            "readiness": "not_ready",
            "warnings": warning_items,
            "normalized_telemetry": empty_normalized_telemetry(source_file=source_file),
        },
        "executive_summary": {},
        "systems": [],
        "relationships": [],
        "fingerprint": {
            "drift_status": "unavailable",
            "normal_operating_behavior": {},
            "current_behavior": {},
            "largest_deviations": [],
            "confidence": "limited",
            "confidence_score": 0.0,
            "evidence_refs": [],
            "explanation": clean_text(message),
        },
        "insights": [],
        "recommendations": [],
        "evidence_index": {},
        "warnings": warning_items,
        "errors": error_items,
        "analysis_metadata": {
            "contract_version": CONTRACT_VERSION,
            "source": "empty",
        },
    }


def build_normalized_telemetry(
    *,
    rows: list[dict[str, Any]],
    columns: list[str],
    numeric_columns: list[str],
    timestamp_column: str | None,
    timestamp_profile: dict[str, Any] | None,
    data_quality: dict[str, Any] | None,
    ingestion_report: dict[str, Any] | None,
    source_file: str,
    record_limit: int = NORMALIZED_RECORD_LIMIT,
) -> dict[str, Any]:
    timestamp_profile = timestamp_profile if isinstance(timestamp_profile, dict) else {}
    data_quality = data_quality if isinstance(data_quality, dict) else {}
    ingestion_report = ingestion_report if isinstance(ingestion_report, dict) else {}
    integrity_flags = data_quality.get("integrity_flags") if isinstance(data_quality.get("integrity_flags"), dict) else {}
    fill_methods = data_quality.get("fill_methods") if isinstance(data_quality.get("fill_methods"), dict) else {}
    sample_interval = first_present(
        ingestion_report.get("sample_interval_seconds"),
        timestamp_profile.get("estimated_sample_interval"),
    )
    normalized_columns = [column for column in numeric_columns if column in columns]
    tag_summaries: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    total_records = 0

    for row_index, row in enumerate(rows):
        timestamp = normalized_timestamp(row, timestamp_column, fallback_index=row_index)
        for column in normalized_columns:
            raw_value = row.get(column)
            flags = missing_value_flags(raw_value)
            parsed = parse_numeric_value(str(raw_value)) if raw_value is not None else None
            quality = normalized_quality(column, flags, integrity_flags)
            classification = classify_telemetry_signal(column)
            tag = tag_summaries.setdefault(
                column,
                {
                    "tag_name": column,
                    "source_column": column,
                    "unit": detect_unit(column),
                    "quality_counts": {},
                    "missing_value_flags": [],
                    "sampling_interval": sample_interval,
                    "detected_metric_type": detect_metric_type(column),
                    "telemetry_category": classification["category"],
                    "analysis_role": classification["analysis_role"],
                    "telemetry_classification": classification,
                    "record_count": 0,
                },
            )
            tag["record_count"] += 1
            tag["quality_counts"][quality] = int(tag["quality_counts"].get(quality, 0)) + 1
            tag["missing_value_flags"] = dedupe([*tag["missing_value_flags"], *flags])
            if fill_methods.get(column):
                tag["fill_method"] = fill_methods.get(column)

            total_records += 1
            if len(records) >= max(0, record_limit):
                continue
            records.append(
                {
                    "timestamp": timestamp,
                    "tag_name": column,
                    "value": parsed,
                    "unit": tag.get("unit"),
                    "source_column": column,
                    "quality": quality,
                    "missing_value_flags": flags,
                    "sampling_interval": sample_interval,
                    "detected_metric_type": tag.get("detected_metric_type"),
                    "telemetry_category": tag.get("telemetry_category"),
                    "analysis_role": tag.get("analysis_role"),
                    "source_row": row.get("__source_row_number"),
                }
            )

    return {
        "status": "ready" if total_records else "missing",
        "source_file": clean_text(source_file),
        "timestamp_column": clean_text(timestamp_column),
        "row_count": len(rows),
        "tag_count": len(normalized_columns),
        "record_count": total_records,
        "record_limit": max(0, record_limit),
        "truncated": total_records > max(0, record_limit),
        "sampling_interval": sample_interval,
        "records": records,
        "tags": list(tag_summaries.values()),
        "calculation_method": "CSV rows were parsed once during upload ingestion and expanded into one normalized telemetry record per numeric tag reading.",
    }


def build_analysis_result(
    result: dict[str, Any],
    *,
    normalized_telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return empty_analysis_result()

    analysis_id = first_present(result.get("analysis_id"), result.get("run_id"), result.get("job_id"))
    upload_id = first_present(result.get("upload_id"), result.get("job_id"), analysis_id)
    source_file = first_present(result.get("source_file"), result.get("filename"))
    generated_at = first_present(result.get("completed_at"), result.get("last_processed_at"), now_iso())
    errors = dedupe_text([*to_list(result.get("errors")), result.get("error")])
    if str(result.get("status") or "").upper() == "FAILED" or errors:
        return empty_analysis_result(
            analysis_id=analysis_id,
            upload_id=upload_id,
            source_file=source_file,
            status="failed",
            message=first_present(result.get("message"), "Analysis failed."),
            errors=errors,
        )

    data_quality = dict(result.get("data_quality") or {}) if isinstance(result.get("data_quality"), dict) else {}
    timestamp_profile = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    baseline = result.get("baseline_analysis") if isinstance(result.get("baseline_analysis"), dict) else {}
    relationship_model = result.get("relationship_model") if isinstance(result.get("relationship_model"), dict) else {}
    operator_report = result.get("operator_report") if isinstance(result.get("operator_report"), dict) else {}
    normalized_telemetry = (
        normalized_telemetry
        if isinstance(normalized_telemetry, dict)
        else result.get("normalized_telemetry")
        if isinstance(result.get("normalized_telemetry"), dict)
        else empty_normalized_telemetry(source_file=source_file)
    )

    explanation = result.get("analysis_explanation") if isinstance(result.get("analysis_explanation"), dict) else {}
    if not explanation:
        explanation = build_analysis_explanation(result)

    warnings = dedupe_text(
        [
            *to_list(data_quality.get("warnings")),
            *to_list(timestamp_profile.get("warnings")),
            *to_list(baseline.get("warnings")),
            *to_list(result.get("warnings")),
        ]
    )
    data_quality["normalized_telemetry"] = normalized_telemetry

    evidence_index: dict[str, dict[str, Any]] = {}

    def add_evidence(seed: str, payload: dict[str, Any]) -> str:
        base_id = f"ev-{slug(analysis_id or upload_id or 'analysis')}-{slug(seed)}"
        evidence_id = base_id
        counter = 2
        while evidence_id in evidence_index:
            evidence_id = f"{base_id}-{counter}"
            counter += 1
        evidence_index[evidence_id] = normalize_evidence_item(
            evidence_id=evidence_id,
            payload=payload,
            default_time_window=build_time_window(result),
        )
        return evidence_id

    baseline_ref = add_evidence(
        "baseline-window",
        {
            "type": "baseline_context",
            "description": "Baseline and current telemetry windows used for metric and relationship comparison.",
            "source_tags": telemetry_tag_names(normalized_telemetry) or [item.get("column") for item in to_list(baseline.get("column_drift")) if isinstance(item, dict)],
            "metric_delta": baseline_metric_deltas(baseline),
            "relationship_delta": [],
            "time_window": build_time_window(result),
            "confidence": confidence_from_data_quality(data_quality),
            "confidence_score": data_quality.get("reliability_score"),
            "calculation_method": "Baseline/current window split over uploaded CSV telemetry.",
        },
    )

    raw_relationships = source_relationships(explanation, relationship_model)
    relationships = []
    relationship_refs_by_id: dict[str, list[str]] = {}
    for index, item in enumerate(raw_relationships):
        relationship_id = clean_text(item.get("id")) or f"relationship-{index}"
        columns = relationship_columns(item)
        ref = add_evidence(
            f"{relationship_id}-relationship",
            {
                "type": "relationship_delta",
                "description": first_present(item.get("what_changed"), item.get("summary"), item.get("name")),
                "source_tags": columns,
                "metric_delta": item.get("supporting_metric_pairs") or metric_changes_from_text(item.get("relevant_metric_changes")),
                "relationship_delta": {
                    "baseline_strength": item.get("baseline_strength"),
                    "current_strength": first_present(item.get("current_strength"), item.get("strength")),
                    "correlation_delta": item.get("correlation_delta"),
                    "change_percent": first_present(item.get("change_percent"), item.get("change_percentage")),
                    "change_type": item.get("change_type"),
                },
                "time_window": item.get("time_window") or build_time_window(result),
                "confidence": first_present(item.get("confidence"), item.get("confidence_level")),
                "confidence_score": first_present(item.get("confidence_score"), item.get("confidence")),
                "calculation_method": "Pearson correlation compared between baseline and current telemetry windows.",
            },
        )
        relationship_refs_by_id[relationship_id] = [ref]
        relationships.append(
            compact_dict(
                {
                    "id": relationship_id,
                    "source": first_present(item.get("source"), f"tag:{columns[0]}" if columns else ""),
                    "target": first_present(item.get("target"), f"tag:{columns[1]}" if len(columns) > 1 else ""),
                    "relationship_type": first_present(item.get("relationship_type"), "linear_correlation"),
                    "strength": number_or_none(first_present(item.get("strength"), item.get("current_strength"))),
                    "confidence": first_present(item.get("confidence"), item.get("confidence_level")),
                    "confidence_score": number_or_none(first_present(item.get("confidence_score"), item.get("confidence"))),
                    "baseline_strength": number_or_none(item.get("baseline_strength")),
                    "current_strength": number_or_none(first_present(item.get("current_strength"), item.get("strength"))),
                    "change_percent": number_or_none(first_present(item.get("change_percent"), item.get("change_percentage"))),
                    "change_type": item.get("change_type"),
                    "baseline_correlation": number_or_none(item.get("baseline_correlation")),
                    "current_correlation": number_or_none(first_present(item.get("current_correlation"), item.get("recent_correlation"))),
                    "correlation_delta": number_or_none(item.get("correlation_delta")),
                    "relationship_importance_score": number_or_none(item.get("relationship_importance_score")),
                    "relationship_importance_rationale": item.get("relationship_importance_rationale"),
                    "ranking_factors": item.get("ranking_factors"),
                    "column_classifications": item.get("column_classifications"),
                    "relationship_context": item.get("relationship_context"),
                    "supporting_metrics": item.get("supporting_metric_pairs") or [{"tag_name": column} for column in columns],
                    "source_tags": columns,
                    "time_window": item.get("time_window") or build_time_window(result),
                    "evidence_refs": [ref],
                    "explanation": first_present(item.get("what_changed"), item.get("summary"), item.get("name")),
                }
            )
        )

    raw_insights = explanation.get("insights") if isinstance(explanation.get("insights"), list) else []
    insights = []
    insight_refs_by_id: dict[str, list[str]] = {}
    for index, item in enumerate(raw_insights):
        if not isinstance(item, dict):
            continue
        insight_id = clean_text(item.get("id")) or f"insight-{index}"
        title = first_present(item.get("title"), item.get("summary"), item.get("explanation"))
        if is_unsupported_output(title, item) or insight_uses_cumulative_counter(item):
            continue
        refs = []
        for evidence_index_number, evidence_item in enumerate(to_list(first_present(item.get("evidence_items"), item.get("evidence")))):
            if not isinstance(evidence_item, dict):
                continue
            refs.append(add_evidence(f"{insight_id}-evidence-{evidence_index_number}", evidence_item))
        if not refs:
            refs = [baseline_ref]
        insight_refs_by_id[insight_id] = refs
        source_tags = dedupe_text(
            [
                *to_list(item.get("source_tags")),
                *to_list(item.get("source_metrics")),
                *[metric.get("source_column") or metric.get("name") for metric in to_list(item.get("contributing_metrics")) if isinstance(metric, dict)],
            ]
        )
        likely_contributors = dedupe_text(
            [
                *to_list(item.get("likely_contributors")),
                *to_list(item.get("contributing_factors")),
                *source_tags,
            ]
        )
        insights.append(
            compact_dict(
                {
                    "id": insight_id,
                    "title": title,
                    "severity": normalize_severity(item.get("severity")),
                    "confidence": first_present(item.get("confidence"), "limited"),
                    "confidence_score": number_or_none(item.get("confidence_score")),
                    "confidence_rationale": item.get("confidence_rationale"),
                    "relationship_importance_score": number_or_none(item.get("relationship_importance_score")),
                    "relationship_importance_rationale": item.get("relationship_importance_rationale"),
                    "ranking_factors": item.get("ranking_factors"),
                    "affected_systems": to_list(item.get("affected_systems")) or [first_present(item.get("system"), "Uploaded telemetry")],
                    "what_changed": first_present(item.get("what_changed"), item.get("whatHappened"), item.get("explanation")),
                    "what_happened": first_present(item.get("what_happened"), item.get("what_changed"), item.get("whatHappened"), item.get("explanation")),
                    "why_it_matters": first_present(
                        item.get("why_neraium_thinks_it_happened"),
                        item.get("why_neraium_thinks"),
                        item.get("why_it_matters"),
                        item.get("likely_cause"),
                    ),
                    "why_neraium_thinks_it_happened": first_present(
                        item.get("why_neraium_thinks_it_happened"),
                        item.get("why_neraium_thinks"),
                        item.get("likely_cause"),
                        item.get("why_it_matters"),
                    ),
                    "likely_contributors": likely_contributors,
                    "contributing_relationships": to_list(item.get("contributing_relationships")),
                    "recommended_check": first_present(item.get("recommended_operator_check"), item.get("operator_check"), item.get("recommended_check")),
                    "operator_check": first_present(item.get("operator_check"), item.get("recommended_operator_check"), item.get("recommended_check")),
                    "recommended_action": first_distinct_from(
                        first_present(item.get("operator_check"), item.get("recommended_operator_check"), item.get("recommended_check")),
                        item.get("recommended_action"),
                        item.get("recommendation"),
                    ),
                    "possible_consequence": first_present(item.get("possible_consequence"), item.get("possible_operational_consequence")),
                    "possible_operational_consequence": first_present(item.get("possible_operational_consequence"), item.get("possible_consequence")),
                    "evidence_refs": refs,
                    "time_window": first_present(item.get("time_window"), build_time_window(result)),
                    "source_tags": source_tags,
                    "explanation": first_present(item.get("explanation"), item.get("what_changed")),
                }
            )
        )

    fingerprint = build_fingerprint_contract(
        result=result,
        baseline=baseline,
        explanation=explanation,
        add_evidence=add_evidence,
        baseline_ref=baseline_ref,
    )
    systems = build_system_contracts(
        explanation=explanation,
        insights=insights,
        relationships=relationships,
        baseline_ref=baseline_ref,
    )
    recommendations = build_recommendation_contracts(
        explanation=explanation,
        insights=insights,
        insight_refs_by_id=insight_refs_by_id,
        baseline_ref=baseline_ref,
        operator_report=operator_report,
    )
    executive_summary = build_executive_summary_contract(
        explanation=explanation,
        result=result,
        insights=insights,
        recommendations=recommendations,
        fingerprint=fingerprint,
    )
    behavior_windows = build_behavior_windows(
        result=result,
        baseline=baseline,
        relationships=relationships,
        insights=insights,
    )

    return sanitize_payload(
        {
            "schema_version": CONTRACT_VERSION,
            "status": "complete",
            "analysis_id": clean_text(analysis_id),
            "upload_id": clean_text(upload_id),
            "source_file": clean_text(source_file),
            "generated_at": clean_text(generated_at),
            "change_onset": behavior_windows.get("change_onset", ""),
            "stable_window": behavior_windows.get("stable_window", {}),
            "deviation_window": behavior_windows.get("deviation_window", {}),
            "current_state_window": behavior_windows.get("current_state_window", {}),
            "data_quality": data_quality,
            "executive_summary": executive_summary,
            "systems": systems,
            "relationships": relationships,
            "relationship_graph": relationship_model.get("relationship_graph", {}),
            "fingerprint": fingerprint,
            "insights": insights,
            "recommendations": recommendations,
            "evidence_index": evidence_index,
            "warnings": warnings,
            "errors": errors,
            "analysis_metadata": {
                "contract_version": CONTRACT_VERSION,
                "job_id": result.get("job_id"),
                "run_id": result.get("run_id") or result.get("job_id"),
                "upload_id": upload_id,
                "source_type": result.get("source_type") or (result.get("ingestion_metadata") or {}).get("source_type"),
                "row_count": result.get("row_count"),
                "column_count": result.get("column_count"),
                "generated_from": "uploaded_csv_telemetry",
                "processing_time_seconds": result.get("processing_time_seconds"),
            },
            "normalized_telemetry": normalized_telemetry,
        }
    )


def build_fingerprint_contract(
    *,
    result: dict[str, Any],
    baseline: dict[str, Any],
    explanation: dict[str, Any],
    add_evidence: Any,
    baseline_ref: str,
) -> dict[str, Any]:
    raw = explanation.get("fingerprint") if isinstance(explanation.get("fingerprint"), dict) else {}
    refs = [baseline_ref]
    for index, item in enumerate(to_list(first_present(raw.get("evidence"), raw.get("evidence_supporting_status")))):
        if isinstance(item, dict):
            refs.append(add_evidence(f"fingerprint-evidence-{index}", item))
    explanation_text = first_present(raw.get("explanation"), raw.get("meaning"))
    return compact_dict(
        {
            "drift_status": first_present(raw.get("drift_status"), raw.get("status"), result.get("drift_status"), "stable"),
            "normal_operating_behavior": first_present(raw.get("normal_operating_behavior"), raw.get("baseline_summary"), {}),
            "current_behavior": first_present(raw.get("current_behavior"), raw.get("current_behavior_summary"), {}),
            "largest_deviations": to_list(raw.get("largest_deviations")) or ([raw.get("largest_deviation")] if raw.get("largest_deviation") else []),
            "confidence": first_present(raw.get("confidence"), confidence_from_baseline(baseline)),
            "confidence_score": number_or_none(raw.get("confidence_score")),
            "evidence_refs": dedupe_text(refs),
            "explanation": explanation_text,
            "plain_language_explanation": explanation_text,
        }
    )


def build_system_contracts(
    *,
    explanation: dict[str, Any],
    insights: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    baseline_ref: str,
) -> list[dict[str, Any]]:
    raw_systems = explanation.get("systems") if isinstance(explanation.get("systems"), list) else []
    systems: list[dict[str, Any]] = []
    if raw_systems:
        for index, item in enumerate(raw_systems):
            if not isinstance(item, dict):
                continue
            name = safe_system_name(first_present(item.get("name"), item.get("label"), f"System {index + 1}"))
            related_relationships = [
                rel for rel in relationships
                if name in to_list(rel.get("affected_systems")) or any(tag in " ".join(to_list(item.get("key_behaviors")) + to_list(item.get("what_changed"))) for tag in rel.get("source_tags", []))
            ]
            evidence_refs = dedupe_text(
                [
                    baseline_ref,
                    *[ref for insight in insights if name in to_list(insight.get("affected_systems")) for ref in to_list(insight.get("evidence_refs"))],
                    *[ref for rel in related_relationships for ref in to_list(rel.get("evidence_refs"))],
                ]
            )
            systems.append(
                compact_dict(
                    {
                        "id": clean_text(item.get("id")) or slug(name),
                        "name": name,
                        "status": first_present(item.get("health_status"), item.get("status")),
                        "confidence": item.get("confidence"),
                        "key_behaviors": to_list(item.get("key_behaviors")),
                        "what_changed": to_list(item.get("what_changed")),
                        "relationship_changes": related_relationships,
                        "relationships": to_list(item.get("relationships")),
                        "evidence_refs": evidence_refs,
                    }
                )
            )
    elif insights:
        names = dedupe_text([system for insight in insights for system in to_list(insight.get("affected_systems"))])
        for name in names:
            systems.append(
                {
                    "id": slug(name),
                    "name": safe_system_name(name),
                    "status": "needs_review" if any(insight.get("severity") in {"high", "moderate"} for insight in insights if name in to_list(insight.get("affected_systems"))) else "observed",
                    "relationship_changes": [rel for rel in relationships if any(tag in rel.get("source_tags", []) for insight in insights if name in to_list(insight.get("affected_systems")) for tag in insight.get("source_tags", []))],
                    "evidence_refs": dedupe_text([ref for insight in insights if name in to_list(insight.get("affected_systems")) for ref in to_list(insight.get("evidence_refs"))] or [baseline_ref]),
                }
            )
    return systems


def build_recommendation_contracts(
    *,
    explanation: dict[str, Any],
    insights: list[dict[str, Any]],
    insight_refs_by_id: dict[str, list[str]],
    baseline_ref: str,
    operator_report: dict[str, Any],
) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    raw = explanation.get("recommendations") if isinstance(explanation.get("recommendations"), list) else []
    insight_by_id = {insight.get("id"): insight for insight in insights}
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        text = first_present(item.get("recommendation"), item.get("recommended_check"), item.get("next_check"))
        if is_unsupported_text(text):
            continue
        refs = []
        for ref in to_list(item.get("evidence_refs")):
            if ref in insight_refs_by_id:
                refs.extend(insight_refs_by_id[ref])
            elif str(ref).startswith("ev-"):
                refs.append(str(ref))
        if not refs and insights:
            refs = to_list(insights[0].get("evidence_refs"))
        if not refs:
            refs = [baseline_ref]
        recommendations.append(
            compact_dict(
                {
                    "id": clean_text(item.get("id")) or f"recommendation-{index}",
                    "priority": first_present(item.get("priority"), priority_from_severity((insights[0] or {}).get("severity") if insights else "")),
                    "recommendation": text,
                    "recommended_check": first_present(item.get("next_check"), text),
                    "reason": item.get("reason"),
                    "affected_systems": to_list(item.get("affected_systems")) or to_list((insight_by_id.get(item.get("insight_id")) or {}).get("affected_systems")),
                    "evidence_refs": dedupe_text(refs),
                }
            )
        )

    if not recommendations:
        for insight in insights:
            text = first_present(insight.get("recommended_action"), insight.get("recommended_check"))
            if text and not is_unsupported_text(text):
                recommendations.append(
                    {
                        "id": f"{insight['id']}-recommendation",
                        "priority": priority_from_severity(insight.get("severity")),
                        "recommendation": text,
                        "recommended_check": first_present(insight.get("operator_check"), insight.get("recommended_check")),
                        "reason": insight.get("what_changed"),
                        "affected_systems": insight.get("affected_systems", []),
                        "evidence_refs": insight.get("evidence_refs", []),
                    }
                )

    if not recommendations and operator_report:
        for index, check in enumerate(to_list(operator_report.get("recommended_operator_checks"))[:3]):
            text = first_present(check)
            if text and not is_unsupported_text(text):
                recommendations.append(
                    {
                        "id": f"operator-check-{index}",
                        "priority": "low",
                        "recommendation": text,
                        "recommended_check": text,
                        "reason": "Generated from upload data quality and baseline review.",
                        "evidence_refs": [baseline_ref],
                    }
                )
    return dedupe_recommendations(recommendations)


def build_executive_summary_contract(
    *,
    explanation: dict[str, Any],
    result: dict[str, Any],
    insights: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    fingerprint: dict[str, Any],
) -> dict[str, Any]:
    raw = explanation.get("executive_summary") if isinstance(explanation.get("executive_summary"), dict) else {}
    top_insight = insights[0] if insights else {}
    top_recommendation = recommendations[0] if recommendations else {}
    return compact_dict(
        {
            "overall_operational_status": first_present(raw.get("overall_operational_status"), result.get("operating_state"), "Analysis complete"),
            "highest_priority_finding": first_present(top_insight.get("title"), raw.get("highest_priority_finding")),
            "biggest_emerging_risk": first_present(top_insight.get("possible_consequence"), raw.get("biggest_emerging_risk"), fingerprint.get("explanation")),
            "recommended_action": first_present(top_recommendation.get("recommendation"), top_insight.get("recommended_check"), raw.get("recommended_action")),
        }
    )


def normalize_evidence_item(
    *,
    evidence_id: str,
    payload: dict[str, Any],
    default_time_window: str,
) -> dict[str, Any]:
    source_tags = dedupe_text(
        [
            *to_list(payload.get("source_tags")),
            *to_list(payload.get("source_columns")),
            *to_list(payload.get("source_metrics")),
            *to_list(payload.get("supporting_evidence")),
            *[pair.get("left") for pair in to_list(payload.get("supporting_metric_pairs")) if isinstance(pair, dict)],
            *[pair.get("right") for pair in to_list(payload.get("supporting_metric_pairs")) if isinstance(pair, dict)],
        ]
    )
    return compact_dict(
        {
            "evidence_id": evidence_id,
            "type": first_present(payload.get("type"), "analysis_evidence"),
            "description": first_present(payload.get("description"), payload.get("summary"), payload.get("what_happened")),
            "source_tags": source_tags,
            "metric_delta": first_present(payload.get("metric_delta"), payload.get("relevant_metric_changes"), []),
            "relationship_delta": first_present(payload.get("relationship_delta"), relationship_delta_from_payload(payload), []),
            "time_window": first_present(payload.get("time_window"), default_time_window),
            "source_time_ranges": payload.get("source_time_ranges"),
            "confidence": payload.get("confidence"),
            "confidence_score": number_or_none(payload.get("confidence_score")),
            "calculation_method": first_present(payload.get("calculation_method"), calculation_method_for_evidence(payload)),
        }
    )


def first_distinct_from(reference: Any, *values: Any) -> Any:
    reference_text = clean_text(reference).lower()
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        value_text = clean_text(value)
        if value_text and value_text.lower() != reference_text:
            return value
    return ""


def relationship_uses_cumulative_counter(item: dict[str, Any]) -> bool:
    return any(is_cumulative_counter_name(column) for column in relationship_columns(item))


def insight_uses_cumulative_counter(item: dict[str, Any]) -> bool:
    candidates: list[Any] = [
        item.get("title"),
        item.get("summary"),
        *to_list(item.get("source_tags")),
        *to_list(item.get("source_metrics")),
        *to_list(item.get("contributing_factors")),
        *to_list(item.get("likely_contributors")),
    ]
    for metric in to_list(item.get("contributing_metrics")):
        if isinstance(metric, dict):
            candidates.extend([metric.get("source_column"), metric.get("name")])
    for relationship in to_list(item.get("contributing_relationships")):
        if isinstance(relationship, dict):
            candidates.extend(relationship_columns(relationship))
    return any(is_cumulative_counter_name(str(candidate)) for candidate in candidates if candidate)


def source_relationships(explanation: dict[str, Any], relationship_model: dict[str, Any]) -> list[dict[str, Any]]:
    relationships = explanation.get("relationships") if isinstance(explanation.get("relationships"), list) else []
    if relationships:
        return [item for item in relationships if isinstance(item, dict) and not relationship_uses_cumulative_counter(item)]
    graph = relationship_model.get("relationship_graph") if isinstance(relationship_model.get("relationship_graph"), dict) else {}
    changed = graph.get("changed_edges") if isinstance(graph.get("changed_edges"), list) else []
    return [item for item in changed if isinstance(item, dict) and not relationship_uses_cumulative_counter(item)]


def relationship_columns(item: dict[str, Any]) -> list[str]:
    columns = item.get("columns")
    if isinstance(columns, list):
        return dedupe_text(columns)
    source_tags = item.get("source_tags")
    if isinstance(source_tags, list):
        return dedupe_text(source_tags)
    pairs = item.get("supporting_metric_pairs")
    if isinstance(pairs, list) and pairs:
        first_pair = next((pair for pair in pairs if isinstance(pair, dict)), {})
        return dedupe_text([first_pair.get("left"), first_pair.get("right")])
    evidence_refs = item.get("evidence_refs")
    if isinstance(evidence_refs, list):
        refs = [ref.get("column") for ref in evidence_refs if isinstance(ref, dict)]
        if refs:
            return dedupe_text(refs)
    relationship = str(item.get("relationship") or item.get("name") or "")
    if "<->" in relationship:
        return dedupe_text(part.strip() for part in relationship.split("<->", 1))
    return []


def relationship_delta_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    delta = {
        "baseline_strength": payload.get("baseline_strength"),
        "current_strength": first_present(payload.get("current_strength"), payload.get("strength")),
        "correlation_delta": payload.get("correlation_delta") or payload.get("calculated_delta"),
        "change_percent": payload.get("change_percentage") or payload.get("change_percent"),
    }
    return compact_dict(delta)


def calculation_method_for_evidence(payload: dict[str, Any]) -> str:
    evidence_type = str(payload.get("type") or "").lower()
    if "relationship" in evidence_type:
        return "Relationship strength delta from baseline/current correlation windows."
    if "metric" in evidence_type or "drift" in evidence_type:
        return "Metric delta from baseline average versus current average."
    if "baseline" in evidence_type:
        return "Baseline/current window context from uploaded CSV telemetry."
    return "Derived from uploaded CSV telemetry analysis artifacts."


def baseline_metric_deltas(baseline: dict[str, Any]) -> list[dict[str, Any]]:
    deltas = []
    for item in to_list(baseline.get("column_drift")):
        if not isinstance(item, dict):
            continue
        deltas.append(
            compact_dict(
                {
                    "tag_name": item.get("column"),
                    "baseline_average": item.get("baseline_average"),
                    "current_average": item.get("recent_average"),
                    "absolute_change": item.get("absolute_change"),
                    "percent_change": item.get("percent_change"),
                    "drift_flag": item.get("drift_flag"),
                }
            )
        )
    return deltas


def empty_normalized_telemetry(source_file: str | None = None) -> dict[str, Any]:
    return {
        "status": "missing",
        "source_file": clean_text(source_file),
        "row_count": 0,
        "tag_count": 0,
        "record_count": 0,
        "record_limit": NORMALIZED_RECORD_LIMIT,
        "truncated": False,
        "records": [],
        "tags": [],
        "calculation_method": "No uploaded telemetry was available to normalize.",
    }


def normalized_timestamp(row: dict[str, Any], timestamp_column: str | None, *, fallback_index: int) -> str | None:
    if row.get("__source_timestamp"):
        return clean_text(row.get("__source_timestamp"))
    if timestamp_column and row.get(timestamp_column):
        return clean_text(row.get(timestamp_column))
    return f"row:{fallback_index + 1}"


def missing_value_flags(value: Any) -> list[str]:
    if value is None:
        return ["missing"]
    text = str(value).strip()
    if text == "":
        return ["blank"]
    if text.lower() in {"nan", "null", "none", "n/a", "na", "-"}:
        return ["null_token"]
    if parse_numeric_value(text) is None:
        return ["not_numeric"]
    return []


def normalized_quality(column: str, flags: list[str], integrity_flags: dict[str, Any]) -> str:
    if flags:
        return "missing" if any(flag in {"missing", "blank", "null_token"} for flag in flags) else "invalid"
    flag = str(integrity_flags.get(column) or "").strip().lower()
    if flag in {"missing", "degraded", "good"}:
        return flag
    return "good"


def detect_unit(column: str) -> str | None:
    text = str(column or "")
    match = re.search(r"\(([^)]+)\)", text)
    if match:
        return clean_text(match.group(1))
    normalized = text.lower()
    suffixes = {
        "_f": "F",
        "_c": "C",
        "_psi": "psi",
        "_kpa": "kPa",
        "_gpm": "gpm",
        "_lpm": "lpm",
        "_ppm": "ppm",
        "_pct": "%",
        "_percent": "%",
    }
    for suffix, unit in suffixes.items():
        if normalized.endswith(suffix):
            return unit
    if "humidity" in normalized or "percent" in normalized:
        return "%"
    if "pressure" in normalized:
        return "pressure"
    if "flow" in normalized:
        return "flow"
    return None


def detect_metric_type(column: str) -> str:
    text = str(column or "").lower()
    if any(token in text for token in ("temp", "thermal", "heat", "cool")):
        return "temperature"
    if "pressure" in text:
        return "pressure"
    if "flow" in text:
        return "flow"
    if any(token in text for token in ("humidity", "moisture", "rh")):
        return "humidity"
    if text == "ph" or "_ph" in text or "ph_" in text:
        return "ph"
    if "conductivity" in text:
        return "conductivity"
    if "turbidity" in text:
        return "turbidity"
    if any(token in text for token in ("power", "kw", "voltage", "current", "amp")):
        return "electrical"
    if any(token in text for token in ("level", "height")):
        return "level"
    if any(token in text for token in ("runtime", "schedule", "state", "status")):
        return "state"
    return "numeric"


def build_time_window(result: dict[str, Any]) -> str:
    timestamp = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    first = clean_text(timestamp.get("first_timestamp"))
    last = clean_text(timestamp.get("last_timestamp"))
    if first and last:
        return f"{first} to {last}"
    return first_present(result.get("last_processed_at"), result.get("completed_at"), "")


def build_behavior_windows(
    *,
    result: dict[str, Any],
    baseline: dict[str, Any],
    relationships: list[dict[str, Any]],
    insights: list[dict[str, Any]],
) -> dict[str, Any]:
    timestamp = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    first = clean_text(timestamp.get("first_timestamp"))
    last = clean_text(timestamp.get("last_timestamp"))
    baseline_rows = int_or_none(baseline.get("baseline_window_rows"))
    recent_rows = int_or_none(baseline.get("recent_window_rows"))
    total_rows = int_or_none(result.get("row_count") or result.get("rows_processed"))
    fallback_window = build_time_window(result)

    deviation_source = first_present(
        *[item.get("time_window") for item in relationships if isinstance(item, dict)],
        *[item.get("time_window") for item in insights if isinstance(item, dict)],
        fallback_window,
    )
    deviation_start, deviation_end = split_window_bounds(deviation_source)
    if not deviation_start and not deviation_end:
        deviation_start, deviation_end = first, last

    return {
        "change_onset": first_present(deviation_start, first),
        "stable_window": behavior_window(
            label="Stable window",
            start=first,
            end=last,
            rows=baseline_rows,
            description="Reference behavior window used for baseline comparison.",
        ),
        "deviation_window": behavior_window(
            label="Deviation window",
            start=deviation_start,
            end=deviation_end,
            rows=recent_rows,
            description="Window where current behavior diverged from the reference pattern.",
        ),
        "current_state_window": behavior_window(
            label="Current state window",
            start=deviation_start or first,
            end=deviation_end or last,
            rows=recent_rows or total_rows,
            description="Most recent behavior window represented by this analysis result.",
        ),
    }


def behavior_window(*, label: str, start: Any = None, end: Any = None, rows: int | None = None, description: str = "") -> dict[str, Any]:
    time_window = " to ".join(item for item in [clean_text(start), clean_text(end)] if item)
    return compact_dict({
        "label": label,
        "start": clean_text(start),
        "end": clean_text(end),
        "time_window": time_window,
        "rows": rows,
        "description": description,
    })


def split_window_bounds(value: Any) -> tuple[str, str]:
    if isinstance(value, dict):
        start = first_present(value.get("current_start"), value.get("start"), value.get("baseline_start"))
        end = first_present(value.get("current_end"), value.get("end"), value.get("baseline_end"))
        return clean_text(start), clean_text(end)
    text = clean_text(value)
    if " to " in text:
        start, end = text.split(" to ", 1)
        return clean_text(start), clean_text(end)
    return text, ""


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def telemetry_tag_names(normalized_telemetry: dict[str, Any]) -> list[str]:
    tags = normalized_telemetry.get("tags") if isinstance(normalized_telemetry, dict) else []
    return dedupe_text(tag.get("tag_name") for tag in tags if isinstance(tag, dict))


def metric_changes_from_text(value: Any) -> list[str]:
    return to_list(value)


def confidence_from_data_quality(data_quality: dict[str, Any]) -> str:
    rating = str(data_quality.get("reliability_rating") or "").lower()
    if rating in {"strong", "high"}:
        return "high"
    if rating in {"usable", "medium", "moderate"}:
        return "moderate"
    return "limited"


def confidence_from_baseline(baseline: dict[str, Any]) -> str:
    try:
        rows = min(int(baseline.get("baseline_window_rows") or 0), int(baseline.get("recent_window_rows") or 0))
        columns = int(baseline.get("columns_analyzed") or 0)
    except (TypeError, ValueError):
        return "limited"
    if rows >= 12 and columns >= 2:
        return "high"
    if rows >= 3 and columns >= 1:
        return "moderate"
    return "limited"


def priority_from_severity(value: Any) -> str:
    severity = str(value or "").lower()
    if severity in {"high", "critical", "elevated"}:
        return "high"
    if severity in {"moderate", "medium", "review"}:
        return "medium"
    return "low"


def normalize_severity(value: Any) -> str:
    severity = str(value or "").strip().lower()
    if severity in {"critical", "high", "elevated"}:
        return "high"
    if severity in {"moderate", "medium", "review", "watch"}:
        return "moderate"
    return "low"


def safe_system_name(value: Any) -> str:
    text = first_present(value, "Uploaded telemetry")
    if text.strip().lower() in {"state group a", "primary water system"}:
        return "Uploaded telemetry"
    return text


def is_unsupported_output(title: str, item: dict[str, Any]) -> bool:
    text = f"{title} {item.get('explanation', '')} {item.get('recommended_action', '')}".lower()
    if title.strip().lower() in PLACEHOLDER_TEXT:
        return True
    return any(fragment in text for fragment in UNSUPPORTED_TEXT_FRAGMENTS)


def is_unsupported_text(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return not text or text in PLACEHOLDER_TEXT or any(fragment in text for fragment in UNSUPPORTED_TEXT_FRAGMENTS)


def dedupe_recommendations(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for item in items:
        key = clean_text(item.get("recommendation")).lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def sanitize_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {clean_text(key): sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return clean_text(value)
    return value


def clean_text(value: Any, *, max_length: int = 1200) -> str:
    if value is None:
        return ""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", str(value))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_length]


def first_present(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        return value
    return ""


def to_list(value: Any, *more_values: Any) -> list[Any]:
    values = (value, *more_values)
    output: list[Any] = []
    for item in values:
        if item is None or item == "":
            continue
        if isinstance(item, list):
            output.extend(item)
        else:
            output.append(item)
    return output


def dedupe(values: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result = []
    for value in values:
        key = clean_text(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def dedupe_text(values: Any) -> list[str]:
    return [clean_text(item) for item in dedupe(list(values or []))]


def compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, item in value.items():
        if item is None or item == "" or item == [] or item == {}:
            continue
        compacted[key] = item
    return compacted


def number_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 6)


def slug(value: Any) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"
