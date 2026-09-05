from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.services.product_evidence_contract import product_evidence
from app.services.measurable_consequence import attach_measurable_consequences
from app.services.analysis_explanations import build_analysis_explanation
from app.services.condition_corroboration import ConditionCorroborationService
from app.services.cumulative_counters import is_cumulative_counter_name
from app.services.data_quality import parse_numeric_value
from app.services.telemetry_classification import (
    signal_classification,
    signal_display_name,
    signal_metadata,
    telemetry_catalog_by_column,
)


CONTRACT_VERSION = "analysis-result-v1"
CONDITION_CONTRACT_VERSION = "condition-v1"
NORMALIZED_RECORD_LIMIT = 500
SII_RELATIONSHIP_LIMIT = 12
SII_OBSERVATION_LIMIT = 8
SII_SENSOR_LIMIT = 32
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
    projected = product_evidence(payload)
    # Completion still appends operational timing stages to these shared records.
    # They are lifecycle bookkeeping, not finding conclusions.
    for key in ("processing_trace", "processing_stats"):
        if key in payload:
            projected[key] = payload[key]
    return projected


def ensure_analysis_result(result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        return empty_analysis_result()
    candidate = product_evidence(result.get("analysis_result"))
    if is_canonical_analysis_result(candidate):
        if isinstance(candidate.get("sii_evidence"), dict):
            return candidate
        return {
            **candidate,
            "sii_evidence": build_sii_evidence_projection(result),
        }
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
        "conditions": [],
        "primary_object": "finding",
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
        "sii_evidence": empty_sii_evidence_projection(),
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
    telemetry_signal_catalog: dict[str, dict[str, Any]] | list[dict[str, Any]] | None = None,
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
    signal_catalog = telemetry_catalog_by_column(telemetry_signal_catalog)
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
            classification = signal_classification(column, signal_catalog)
            metadata = signal_metadata(column, signal_catalog)
            display_name = signal_display_name(column, signal_catalog)
            tag = tag_summaries.setdefault(
                column,
                {
                    "tag_name": display_name,
                    "source_column": column,
                    "original_header": metadata.get("original_header"),
                    "normalized_name": metadata.get("normalized_name"),
                    "display_name": display_name,
                    "unit": metadata.get("engineering_units") or detect_unit(column),
                    "engineering_units": metadata.get("engineering_units") or detect_unit(column),
                    "source_column_index": metadata.get("source_column_index"),
                    "quality_counts": {},
                    "missing_value_flags": [],
                    "sampling_interval": sample_interval,
                    "detected_metric_type": detect_metric_type(column),
                    "inferred_telemetry_type": classification.get("structural_class"),
                    "telemetry_category": classification["category"],
                    "analysis_role": classification["analysis_role"],
                    "canonical_role": metadata.get("canonical_role"),
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
                    "tag_name": tag.get("tag_name"),
                    "value": parsed,
                    "unit": tag.get("unit"),
                    "source_column": column,
                    "original_header": tag.get("original_header"),
                    "normalized_name": tag.get("normalized_name"),
                    "display_name": tag.get("display_name"),
                    "source_column_index": tag.get("source_column_index"),
                    "quality": quality,
                    "missing_value_flags": flags,
                    "sampling_interval": sample_interval,
                    "detected_metric_type": tag.get("detected_metric_type"),
                    "telemetry_category": tag.get("telemetry_category"),
                    "analysis_role": tag.get("analysis_role"),
                    "canonical_role": tag.get("canonical_role"),
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
        "signals": list(signal_catalog.values()) if signal_catalog else [],
        "calculation_method": "CSV rows were parsed once during upload ingestion and expanded into one normalized telemetry record per numeric tag reading.",
    }


def build_analysis_result(
    result: dict[str, Any],
    *,
    normalized_telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return empty_analysis_result()

    result = product_evidence(result)
    analysis_id = first_present(result.get("analysis_id"), result.get("run_id"), result.get("job_id"))
    source_kind = clean_text(result.get("source_kind"))
    source_type_value = result.get("source_type") or (
        result.get("ingestion_metadata") or {}
    ).get("source_type")
    source_type = clean_text(source_type_value)
    connector_analysis = source_kind in {"connector", "telemetry_connector"} or source_type == "telemetry_connector"
    # Historical uploads retain their established fallback. Connector analysis
    # must not synthesize an upload identity for an ongoing telemetry window.
    upload_id = (
        clean_text(result.get("upload_id"))
        if connector_analysis
        else first_present(result.get("upload_id"), result.get("job_id"), analysis_id)
    )
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
    telemetry_signals = list((result.get("telemetry_signal_catalog") or {}).values()) if isinstance(result.get("telemetry_signal_catalog"), dict) else to_list(result.get("telemetry_signals"))
    if telemetry_signals:
        data_quality["telemetry_signals"] = telemetry_signals

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
            "calculation_method": (
                "Baseline/current window split over canonical normalized observations."
                if connector_analysis
                else "Baseline/current window split over uploaded CSV telemetry."
            ),
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
                    "relationship_comparison": item.get("relationship_comparison"),
                    "baseline_value": item.get("baseline_value"),
                    "current_value": item.get("current_value"),
                    "signed_change": item.get("signed_change"),
                    "absolute_change": item.get("absolute_change"),
                    "change_percent": first_present(item.get("change_percent"), item.get("change_percentage")),
                    "change_type": item.get("change_type"),
                },
                "time_window": item.get("time_window") or build_time_window(result),
                "confidence": first_present(item.get("confidence"), item.get("confidence_level")),
                "confidence_score": first_present(item.get("confidence_score"), item.get("confidence")),
                "calculation_method": "Historical and current operating windows were compared for this signal pair.",
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
                    "system": item.get("system"),
                    "monitored_boundary": item.get("monitored_boundary"),
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
                    "relationship_comparison": item.get("relationship_comparison"),
                    "baseline_value": number_or_none(item.get("baseline_value")),
                    "current_value": number_or_none(item.get("current_value")),
                    "signed_change": number_or_none(item.get("signed_change")),
                    "absolute_change": number_or_none(item.get("absolute_change")),
                    "relationship_direction": item.get("relationship_direction"),
                    "relationship_importance_score": number_or_none(item.get("relationship_importance_score")),
                    "relationship_importance_rationale": item.get("relationship_importance_rationale"),
                    "ranking_factors": item.get("ranking_factors"),
                    "column_classifications": item.get("column_classifications"),
                    "relationship_context": item.get("relationship_context"),
                    "operating_mode": item.get("operating_mode"),
                    "data_confidence": item.get("data_confidence"),
                    "sensor_health": item.get("sensor_health"),
                    "supporting_metrics": item.get("supporting_metric_pairs") or [{"tag_name": column} for column in columns],
                    "source_tags": columns,
                    "source_tag_display_names": to_list(item.get("display_columns")),
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
        source_tag_display_names = dedupe_text([*to_list(item.get("source_tag_display_names")), *to_list(item.get("display_names"))])
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
                    "confidence_and_uncertainty": item.get("confidence_and_uncertainty"),
                    "classification": item.get("classification"),
                    "finding_confidence_v1": first_present(
                        item.get("finding_confidence_v1"),
                        (item.get("classification") or {}).get("finding_confidence_v1")
                        if isinstance(item.get("classification"), dict)
                        else None,
                    ),
                    "relationship_comparison": item.get("relationship_comparison"),
                    "data_confidence": item.get("data_confidence"),
                    "sensor_health": item.get("sensor_health"),
                    "certainty_limit": item.get("certainty_limit"),
                    "alternative_explanations": to_list(item.get("alternative_explanations")),
                    "data_limitations": to_list(item.get("data_limitations")),
                    "persistence": item.get("persistence"),
                    "persistence_duration": item.get("persistence_duration"),
                    "relationship_evidence": item.get("relationship_evidence"),
                    "activity_timeline": to_list(item.get("activity_timeline")),
                    "sii_finding_id": item.get("sii_finding_id"),
                    "affected_assets": to_list(item.get("affected_assets")),
                    "relationship_prior_id": item.get("relationship_prior_id"),
                    "relationship_prior_version": item.get("relationship_prior_version"),
                    "operating_mode": item.get("operating_mode"),
                    "graph_trust": item.get("graph_trust"),
                    "first_detected_at": item.get("first_detected_at"),
                    "last_observed_at": item.get("last_observed_at"),
                    "status": item.get("status"),
                    "hypothesis_state": item.get("hypothesis_state"),
                    "observed_evidence": to_list(item.get("observed_evidence")),
                    "derived_metrics": to_list(item.get("derived_metrics")),
                    "confounding_conditions": to_list(item.get("confounding_conditions")),
                    "recommended_checks": to_list(item.get("recommended_checks")),
                    "investigation_guidance": to_list(item.get("investigation_guidance")),
                    "recommended_investigation": to_list(item.get("recommended_investigation")),
                    "recommended_first_action": item.get("recommended_first_action"),
                    "first_check": item.get("first_check"),
                    "source_time_ranges": to_list(item.get("source_time_ranges")),
                    "water_interpretation": item.get("water_interpretation"),
                    "relationship_importance_score": number_or_none(item.get("relationship_importance_score")),
                    "relationship_importance_rationale": item.get("relationship_importance_rationale"),
                    "ranking_factors": item.get("ranking_factors"),
                    "affected_systems": to_list(item.get("affected_systems")) or [first_present(item.get("system"), "Uploaded telemetry")],
                    "what_changed": first_present(item.get("what_changed"), item.get("whatHappened"), item.get("explanation")),
                    "what_happened": first_present(item.get("what_happened"), item.get("what_changed"), item.get("whatHappened"), item.get("explanation")),
                    "why_it_matters": first_present(
                        item.get("why_it_matters"),
                        item.get("possible_operational_consequence"),
                        item.get("possible_consequence"),
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
                    "source_tag_display_names": source_tag_display_names,
                    "explanation": first_present(item.get("explanation"), item.get("what_changed")),
                }
            )
        )

    result_conditions = result.get("conditions") if isinstance(result.get("conditions"), list) else []
    explanation_conditions = explanation.get("conditions") if isinstance(explanation.get("conditions"), list) else []
    raw_conditions = result_conditions or explanation_conditions
    if not raw_conditions and relationships:
        raw_conditions = ConditionCorroborationService().build_conditions(
            relationships=relationships,
            findings=insights,
            baseline_analysis=baseline,
            data_quality=data_quality,
            operating_mode=data_quality.get("operating_mode"),
            site_name=first_present(result.get("facility_name"), result.get("site_name")),
            generated_at=generated_at,
        )
    conditions = build_condition_contracts(
        raw_conditions=raw_conditions,
        add_evidence=add_evidence,
        relationship_refs_by_id=relationship_refs_by_id,
        baseline_ref=baseline_ref,
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
        conditions=conditions,
        insights=insights,
        recommendations=recommendations,
        fingerprint=fingerprint,
    )
    behavior_windows = build_behavior_windows(
        result=result,
        baseline=baseline,
        relationships=relationships,
        insights=insights,
        normalized_telemetry=normalized_telemetry,
    )
    sii_evidence = build_sii_evidence_projection(result)

    analysis_metadata = {
        "contract_version": CONTRACT_VERSION,
        "job_id": result.get("job_id"),
        "run_id": result.get("run_id") or result.get("job_id"),
        "upload_id": upload_id,
        "source_type": source_type if connector_analysis else source_type_value,
        "row_count": result.get("row_count"),
        "column_count": result.get("column_count"),
        "generated_from": (
            "canonical_normalized_observations"
            if connector_analysis
            else "uploaded_csv_telemetry"
        ),
        "processing_time_seconds": result.get("processing_time_seconds"),
        "telemetry_signal_count": len(telemetry_signals),
        "condition_contract_version": CONDITION_CONTRACT_VERSION,
        "condition_count": len(conditions),
    }
    telemetry_lineage = (
        dict(result.get("telemetry_lineage"))
        if connector_analysis and isinstance(result.get("telemetry_lineage"), dict)
        else None
    )
    if telemetry_lineage is not None:
        analysis_metadata["lineage_digest"] = telemetry_lineage.get("lineage_digest")
        analysis_metadata["lineage_observation_count"] = telemetry_lineage.get("observation_count")
        analysis_metadata["lineage_observation_sample"] = telemetry_lineage.get("observation_sample")

    payload = {
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
        "conditions": conditions,
        "primary_object": "condition" if conditions else "finding",
        "relationships": relationships,
        "relationship_graph": relationship_model.get("relationship_graph", {}),
        "water_intelligence": result.get("water_intelligence")
        if isinstance(result.get("water_intelligence"), dict)
        else {},
        "fingerprint": fingerprint,
        "insights": insights,
        "recommendations": recommendations,
        "evidence_index": evidence_index,
        "warnings": warnings,
        "errors": errors,
        "telemetry_signals": telemetry_signals,
        "analysis_metadata": analysis_metadata,
        "sii_evidence": sii_evidence,
        "normalized_telemetry": normalized_telemetry,
    }
    if telemetry_lineage is not None:
        payload["telemetry_lineage"] = telemetry_lineage
    payload = product_evidence(sanitize_payload(payload))
    # Attach after presentation sanitization to preserve exact calculation provenance.
    attach_measurable_consequences(
        payload, source=result, original_findings=[*raw_conditions, *raw_insights],
    )
    return payload


def empty_sii_evidence_projection(
    *,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an explicit empty projection without asserting absent evidence."""

    return {
        "source": "sii_result",
        "source_path": "sii_result",
        "authority": {
            "scope": "canonical_engine_evidence",
            "finding_classification": False,
        },
        "status": "unavailable",
        "engine": {},
        "relationship_changes": [],
        "operating_context": {},
        "persistence": {},
        "uncertainty": {"status": "unavailable", "limitations": []},
        "data_quality": {},
        "sensor_health": {"signals": []},
        "configured_prior_observations": [],
        "phase_4": {
            "status": "unavailable",
            "available": False,
            "limitations": [],
            "behavioral_evolution": {},
            "propagation": {},
        },
        "provenance": provenance or {},
    }


def build_sii_evidence_projection(result: dict[str, Any] | None) -> dict[str, Any]:
    """Select bounded canonical SII evidence without changing its authority."""

    payload = result if isinstance(result, dict) else {}
    provenance = _sii_provenance(payload)
    sii = _sii_map(payload.get("sii_result"))
    if not sii:
        return empty_sii_evidence_projection(provenance=provenance)

    conditions = _sii_map(sii.get("data_conditions"))
    model = _sii_map(sii.get("behavioral_model"))
    evolution = _sii_map(sii.get("behavioral_evolution"))
    propagation = _sii_map(sii.get("propagation_analysis"))
    phase_statuses = [
        str(section.get("status") or "")
        for section in (model, evolution, propagation)
        if section
    ]
    phase_available = any(status == "complete" for status in phase_statuses)
    phase_status = (
        "complete"
        if phase_available
        else phase_statuses[0]
        if phase_statuses
        else "unavailable"
    )
    phase_limitations = _sii_texts(
        [
            *_sii_items(model.get("limitations")),
            *_sii_items(evolution.get("limitations")),
            *_sii_items(propagation.get("limitations")),
            model.get("reason"),
            evolution.get("reason"),
            propagation.get("reason"),
        ],
        8,
    )
    return {
        "source": "sii_result",
        "source_path": "sii_result",
        "authority": {
            "scope": "canonical_engine_evidence",
            "finding_classification": False,
        },
        "status": str(sii.get("status") or "unavailable"),
        "engine": _sii_pick(_sii_map(sii.get("engine")), ("name", "version")),
        "relationship_changes": [
            _sii_relationship(item)
            for item in _sii_dicts(
                _sii_map(sii.get("relationship_graph")).get("changed_edges"),
                SII_RELATIONSHIP_LIMIT,
            )
        ],
        "operating_context": _sii_operating(_sii_map(sii.get("operating_modes"))),
        "persistence": _sii_persistence(_sii_map(sii.get("persistence_analysis"))),
        "uncertainty": _sii_uncertainty(_sii_map(sii.get("uncertainty"))),
        "data_quality": _sii_quality(_sii_map(conditions.get("data_quality"))),
        "sensor_health": _sii_health(_sii_map(conditions.get("sensor_health"))),
        "configured_prior_observations": [
            _sii_prior_observation(item)
            for item in _sii_dicts(
                _sii_map(sii.get("evidence_fusion")).get("observations"),
                SII_OBSERVATION_LIMIT,
            )
        ],
        "phase_4": {
            "status": phase_status,
            "available": phase_available,
            "limitations": phase_limitations,
            "behavioral_evolution": _sii_evolution(evolution),
            "propagation": _sii_propagation(propagation),
        },
        "provenance": provenance,
    }


def _sii_map(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _sii_items(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _sii_dicts(value: Any, limit: int) -> list[dict[str, Any]]:
    return [item for item in _sii_items(value) if isinstance(item, dict)][:limit]


def _sii_pick(value: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Copy only scalar values and bounded lists of scalar values."""

    output: dict[str, Any] = {}
    for field in fields:
        item = value.get(field)
        if isinstance(item, (str, int, float, bool)) or item is None:
            if field in value:
                output[field] = item
        elif isinstance(item, list):
            output[field] = [
                child
                for child in item
                if isinstance(child, (str, int, float, bool)) or child is None
            ][:12]
    return output


def _sii_scalar_map(value: Any, limit: int = 12) -> dict[str, Any]:
    mapping = _sii_map(value)
    return _sii_pick(mapping, tuple(list(mapping)[:limit]))


def _sii_texts(values: list[Any], limit: int) -> list[str]:
    output: list[str] = []
    for value in values:
        text = clean_text(value)
        if text and text not in output:
            output.append(text)
        if len(output) >= limit:
            break
    return output


def _sii_relationship(item: dict[str, Any]) -> dict[str, Any]:
    projected = _sii_pick(
        item,
        (
            "id", "relationship_id", "source", "target", "source_signal",
            "target_signal", "columns", "relationship", "relationship_type",
            "change_type", "baseline_correlation", "current_correlation",
            "recent_correlation", "correlation_delta", "signed_correlation_delta",
            "baseline_strength", "current_strength", "signed_change",
            "absolute_change", "change_percent", "confidence", "confidence_level",
            "persistence", "status",
        ),
    )
    refs = []
    for ref in _sii_items(item.get("evidence_refs"))[:8]:
        if isinstance(ref, str):
            refs.append(ref)
        elif isinstance(ref, dict):
            refs.append(
                _sii_pick(
                    ref,
                    (
                        "evidence_id", "source", "source_reference",
                        "originating_module", "column", "window", "source_row",
                        "timestamp",
                    ),
                )
            )
    if refs:
        projected["evidence_refs"] = refs
    window = _sii_scalar_map(item.get("time_window"), 8)
    if window:
        projected["time_window"] = window
    return projected


def _sii_operating(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    projected = _sii_pick(
        value,
        ("status", "reason", "baseline_mode", "recent_mode", "match", "confidence"),
    )
    projected["limitations"] = _sii_texts(_sii_items(value.get("limitations")), 6)
    conditioned = _sii_map(value.get("mode_conditioned_baseline"))
    if not conditioned:
        return projected
    summary = _sii_pick(
        conditioned,
        (
            "status", "reason", "method", "used_global_fallback",
            "fallback_reason", "selection_confidence",
            "selection_confidence_level",
        ),
    )
    summary["limitations"] = _sii_texts(
        _sii_items(conditioned.get("limitations")), 6
    )
    mode = _sii_map(conditioned.get("selected_operating_mode"))
    if mode:
        summary["selected_operating_mode"] = {
            **_sii_pick(
                mode,
                (
                    "mode_id", "mode_label", "minimum_feature_support",
                    "ambiguous", "confidence", "confidence_level",
                    "reported_recent_mode",
                ),
            ),
            "features": _sii_scalar_map(mode.get("features"), 8),
        }
    selection = _sii_map(conditioned.get("selection"))
    if selection:
        summary["selection"] = _sii_pick(
            selection,
            (
                "historical_start_index", "historical_end_index_exclusive",
                "recent_start_index", "recent_end_index_exclusive",
                "selected_baseline_rows", "recent_rows",
                "minimum_baseline_rows", "minimum_recent_rows",
                "minimum_recent_mode_purity",
            ),
        )
    projected["mode_conditioned_baseline"] = summary
    return projected


def _sii_persistence_detail(item: dict[str, Any]) -> dict[str, Any]:
    return _sii_pick(
        item,
        (
            "column", "direction", "recent_values_checked",
            "supporting_recent_rows", "support_percent", "persistent",
            "observations", "supporting_observations",
            "observed_duration_seconds", "supporting_duration_seconds",
            "support_fraction", "satisfied", "required_observations",
        ),
    )


def _sii_persistence(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    fixed = _sii_map(value.get("fixed_row_support"))
    adaptive = _sii_map(value.get("adaptive_persistence"))
    baseline = _sii_map(value.get("baseline_signal_persistence"))
    return {
        **_sii_pick(value, ("status", "method")),
        "fixed_row_support": {
            **_sii_pick(
                fixed,
                ("status", "reason", "persistent_columns", "columns_assessed"),
            ),
            "limitations": _sii_texts(_sii_items(fixed.get("limitations")), 6),
            "details": [
                _sii_persistence_detail(item)
                for item in _sii_dicts(fixed.get("details"), 12)
            ],
        },
        "baseline_signal_persistence": {
            "signals": [
                _sii_pick(item, ("column", "persistence_score", "drift_flag"))
                for item in _sii_dicts(baseline.get("signals"), 24)
            ]
        },
        "covariance_gates": _sii_scalar_map(value.get("covariance_gates"), 8),
        "adaptive_persistence": {
            **_sii_pick(
                adaptive,
                (
                    "status", "reason", "method", "persistence_basis",
                    "elapsed_time_available", "used_row_fallback",
                    "sampling_regular", "observed_duration_seconds",
                    "required_observations", "persistent_columns",
                ),
            ),
            "limitations": _sii_texts(
                _sii_items(adaptive.get("limitations")), 6
            ),
            "actual_persistence": _sii_scalar_map(
                adaptive.get("actual_persistence"), 8
            ),
            "details": [
                _sii_persistence_detail(item)
                for item in _sii_dicts(adaptive.get("details"), 12)
            ],
        },
    }


def _sii_uncertainty(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {"status": "unavailable", "limitations": []}
    components = {}
    for name, component in list(_sii_map(value.get("components")).items())[:6]:
        if not isinstance(component, dict):
            continue
        components[str(name)] = {
            **_sii_pick(component, ("status", "not_probability", "source_references")),
            "traceable_metrics": _sii_scalar_map(
                component.get("traceable_metrics"), 10
            ),
            "limitations": _sii_texts(
                _sii_items(component.get("limitations")), 6
            ),
        }
    confidence = _sii_map(value.get("data_confidence"))
    return {
        **_sii_pick(value, ("status",)),
        "data_confidence": _sii_pick(
            confidence, ("rating", "score", "method", "not_probability")
        ),
        "module_failures": [
            _sii_pick(item, ("module", "status", "reason"))
            for item in _sii_dicts(value.get("module_failures"), 8)
        ],
        "components": components,
        "limitations": _sii_texts(_sii_items(value.get("limitations")), 8),
    }


def _sii_quality(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    confidence = _sii_map(value.get("data_confidence"))
    return {
        **_sii_pick(
            value,
            (
                "status", "readiness", "analysis_gate_state",
                "reliability_score", "reliability_rating",
                "rows_received", "rows_used", "rows_dropped",
            ),
        ),
        "data_confidence": _sii_pick(
            confidence, ("rating", "score", "method", "not_probability")
        ),
        "quality_metrics": _sii_scalar_map(value.get("quality_metrics"), 12),
        "warnings": _sii_texts(_sii_items(value.get("warnings")), 8),
        "limitations": _sii_texts(_sii_items(value.get("limitations")), 8),
    }


def _sii_health(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {"signals": []}
    return {
        **_sii_pick(value, ("status", "reason")),
        "limitations": _sii_texts(_sii_items(value.get("limitations")), 8),
        "signals": [
            {
                **_sii_pick(
                    item,
                    (
                        "signal", "column", "health", "status", "confidence",
                        "missing_fraction", "constant_or_stuck",
                        "non_numeric_count",
                    ),
                ),
                "conditions": _sii_texts(
                    _sii_items(item.get("conditions")), 6
                ),
            }
            for item in _sii_dicts(value.get("signals"), SII_SENSOR_LIMIT)
        ],
    }


def _sii_prior_observation(item: dict[str, Any]) -> dict[str, Any]:
    trace = _sii_map(item.get("processing_trace"))
    return {
        **_sii_pick(
            item,
            (
                "observation_id", "behavioral_status",
                "contributing_analytical_modules",
                "evaluated_engineering_priors", "human_review_required",
                "causal_interpretation_provided",
                "maintenance_recommendation_provided",
            ),
        ),
        **_sii_pick(trace, ("prior_id", "prior_status")),
        "supporting_evidence_ids": _sii_pick(
            trace, ("supporting_evidence_ids",)
        ).get("supporting_evidence_ids", []),
        "limiting_evidence_ids": _sii_pick(
            trace, ("limiting_evidence_ids",)
        ).get("limiting_evidence_ids", []),
        "contradictory_evidence_ids": _sii_pick(
            trace, ("contradictory_evidence_ids",)
        ).get("contradictory_evidence_ids", []),
    }


def _sii_evolution_item(item: dict[str, Any]) -> dict[str, Any]:
    return _sii_pick(
        item,
        (
            "id", "type", "signal_id", "relationship_id", "source_signal",
            "target_signal", "columns", "operating_mode", "classification",
            "change_type", "status", "direction", "persistence",
            "persistent_across_references", "historical_center",
            "current_center", "normalized_change", "history_support",
            "source_model_version", "decision_id", "baseline_version",
            "human_validation_required",
        ),
    )


def _sii_evolution(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    projected = {
        **_sii_pick(value, ("status", "reason", "evidence_classification")),
        "limitations": _sii_texts(_sii_items(value.get("limitations")), 8),
    }
    for field in (
        "signal_changes", "relationship_changes", "operating_mode_changes",
        "recovery_evidence", "adaptation_evidence", "unresolved_changes",
    ):
        projected[field] = [
            _sii_evolution_item(item)
            for item in _sii_dicts(value.get(field), 8)
        ]
    graph = _sii_map(value.get("graph_changes"))
    if graph:
        projected["graph_changes"] = {
            **_sii_pick(
                graph,
                ("structural_change_scope", "persistent_topology_change"),
            ),
            "fragmentation": _sii_scalar_map(graph.get("fragmentation"), 8),
        }
    return projected


def _sii_propagation(value: dict[str, Any]) -> dict[str, Any]:
    if not value:
        return {}
    paths = []
    for item in _sii_dicts(value.get("candidate_paths"), 6):
        paths.append(
            {
                **_sii_pick(
                    item,
                    (
                        "path_id", "nodes", "edges", "compatibility",
                        "not_probability", "causal_claim",
                    ),
                ),
                "observed_times": _sii_scalar_map(
                    item.get("observed_times"), 8
                ),
                "lag_consistency": _sii_scalar_map(
                    item.get("lag_consistency"), 8
                ),
                "confidence_factors": _sii_scalar_map(
                    item.get("confidence_factors"), 8
                ),
            }
        )
    uncertainty = _sii_map(value.get("uncertainty"))
    propagation_uncertainty = _sii_map(
        uncertainty.get("propagation_uncertainty")
    )
    return {
        **_sii_pick(
            value,
            (
                "status", "reason", "evidence_classification",
                "activated_nodes", "activated_edges",
                "downstream_consistent_changes",
            ),
        ),
        "candidate_paths": paths,
        "earliest_observed_changes": [
            _sii_pick(item, ("signal", "timestamp"))
            for item in _sii_dicts(value.get("earliest_observed_changes"), 12)
        ],
        "unsupported_segments": [
            {
                **_sii_pick(
                    item,
                    (
                        "relationship_id", "source_signal", "target_signal",
                        "reasons",
                    ),
                )
            }
            for item in _sii_dicts(value.get("unsupported_segments"), 6)
        ],
        "competing_path_count": len(_sii_items(value.get("competing_paths"))),
        "propagation_confidence": _sii_scalar_map(
            value.get("propagation_confidence"), 8
        ),
        "uncertainty": {
            **_sii_pick(
                uncertainty,
                (
                    "not_probability", "cause_selected",
                    "alternative_paths_retained",
                ),
            ),
            "propagation_uncertainty": _sii_scalar_map(
                propagation_uncertainty, 8
            ),
        },
        "limitations": _sii_texts(_sii_items(value.get("limitations")), 8),
        "reasoning_trace": _sii_pick(
            _sii_map(value.get("reasoning_trace")),
            (
                "temporal_precedence_required", "lag_evidence_required",
                "path_lag_consistency_evaluated", "causal_proof_claimed",
                "root_cause_selected",
            ),
        ),
    }


def _sii_provenance(result: dict[str, Any]) -> dict[str, Any]:
    traceability = _sii_map(result.get("traceability"))
    provenance = _sii_map(traceability.get("provenance"))
    if not provenance:
        provenance = _sii_map(result.get("provenance"))
    selected = _sii_pick(
        provenance,
        (
            "schema_version", "analysis_run_id", "upload_id", "dataset_id",
            "input_hash", "baseline_id", "baseline_dataset_id",
            "baseline_version", "baseline_hash", "engine_name",
            "engine_version", "build_commit", "configuration_hash",
            "result_hash",
        ),
    )
    ingestion = _sii_map(result.get("ingestion_report"))
    fallbacks = {
        "analysis_run_id": result.get("run_id") or result.get("job_id"),
        "upload_id": result.get("upload_id") or result.get("job_id"),
        "dataset_id": result.get("dataset_id") or result.get("comparison_dataset_id"),
        "input_hash": ingestion.get("input_hash") or result.get("input_hash"),
        "baseline_id": result.get("baseline_id"),
        "baseline_dataset_id": result.get("baseline_dataset_id"),
    }
    for key, value in fallbacks.items():
        if key not in selected and value is not None:
            selected[key] = value
    return selected

def build_condition_contracts(
    *,
    raw_conditions: list[dict[str, Any]],
    add_evidence: Any,
    relationship_refs_by_id: dict[str, list[str]],
    baseline_ref: str,
) -> list[dict[str, Any]]:
    conditions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_conditions):
        if not isinstance(item, dict):
            continue
        condition_id = clean_text(item.get("condition_id") or item.get("id")) or f"condition-{index}"
        support = [
            relationship
            for relationship in to_list(
                item.get("supporting_relationships")
                or (item.get("corroboration") or {}).get("supporting_relationships")
            )
            if isinstance(relationship, dict)
        ]
        conflicts = [
            relationship
            for relationship in to_list(
                item.get("conflicting_relationships")
                or (item.get("corroboration") or {}).get("conflicting_relationships")
            )
            if isinstance(relationship, dict)
        ]
        uncertain = [
            relationship
            for relationship in to_list(
                item.get("uncertain_relationships")
                or (item.get("corroboration") or {}).get("uncertain_relationships")
            )
            if isinstance(relationship, dict)
        ]
        relationship_ids = dedupe_text(
            [
                relationship.get("relationship_id") or relationship.get("id")
                for relationship in [*support, *conflicts, *uncertain]
            ]
        )
        refs = dedupe_text(
            [
                ref
                for relationship_id in relationship_ids
                for ref in relationship_refs_by_id.get(relationship_id, [])
            ]
        )
        evidence_items = [
            evidence
            for evidence in to_list(item.get("evidence"))
            if isinstance(evidence, dict)
        ]
        for evidence_index_number, evidence in enumerate(evidence_items):
            refs.append(
                add_evidence(
                    f"{condition_id}-evidence-{evidence_index_number}",
                    {
                        **evidence,
                        "description": first_present(evidence.get("summary"), evidence.get("description")),
                        "source_tags": first_present(
                            evidence.get("source_signals"),
                            item.get("affected_signals"),
                            [],
                        ),
                        "confidence": item.get("confidence"),
                        "confidence_score": item.get("confidence_score"),
                        "calculation_method": first_present(
                            evidence.get("calculation_method"),
                            "Deterministic condition corroboration over telemetry-supported relationship changes.",
                        ),
                    },
                )
            )
        refs = dedupe_text(refs) or [baseline_ref]
        corroboration = item.get("corroboration") if isinstance(item.get("corroboration"), dict) else {}
        trajectory = item.get("trajectory") if isinstance(item.get("trajectory"), dict) else {}
        localization = item.get("localization") if isinstance(item.get("localization"), dict) else {}
        classification = item.get("classification") if isinstance(item.get("classification"), dict) else {}
        comparable = item.get("comparable_operation") if isinstance(item.get("comparable_operation"), dict) else {}
        next_checks = dedupe_text(
            to_list(
                first_present(
                    item.get("next_checks"),
                    item.get("recommended_investigation"),
                    [item.get("recommended_check")],
                )
            )
        )
        condition = dict(item)
        condition.update(
            compact_dict(
                {
                    "schema_version": first_present(item.get("schema_version"), CONDITION_CONTRACT_VERSION),
                    "object_type": "condition",
                    "condition_id": condition_id,
                    "id": condition_id,
                    "headline": first_present(item.get("headline"), item.get("title"), "Monitored condition changed"),
                    "title": first_present(item.get("headline"), item.get("title"), "Monitored condition changed"),
                    "classification": classification,
                    "finding_confidence_v1": first_present(
                        item.get("finding_confidence_v1"),
                        classification.get("finding_confidence_v1"),
                    ),
                    "relationship_comparison": first_present(
                        item.get("relationship_comparison"),
                        (item.get("finding_confidence_v1") or {}).get("relationship_comparison")
                        if isinstance(item.get("finding_confidence_v1"), dict)
                        else None,
                        (classification.get("finding_confidence_v1") or {}).get("relationship_comparison")
                        if isinstance(classification.get("finding_confidence_v1"), dict)
                        else None,
                    ),
                    "trajectory": trajectory,
                    "corroboration": corroboration,
                    "corroboration_strength": first_present(
                        item.get("corroboration_strength"),
                        corroboration.get("corroboration_strength"),
                        "isolated",
                    ),
                    "relationship_count": first_present(
                        item.get("relationship_count"),
                        corroboration.get("relationship_count"),
                        len(support),
                    ),
                    "confidence": first_present(item.get("confidence"), corroboration.get("confidence"), "low"),
                    "confidence_score": number_or_none(
                        first_present(item.get("confidence_score"), corroboration.get("confidence_score"))
                    ),
                    "affected_signals": dedupe_text(
                        to_list(
                            first_present(
                                item.get("affected_signals"),
                                corroboration.get("affected_signals"),
                                [],
                            )
                        )
                    ),
                    "affected_systems": dedupe_text(
                        to_list(
                            first_present(
                                item.get("affected_systems"),
                                corroboration.get("affected_systems"),
                                [],
                            )
                        )
                    ),
                    "affected_boundaries": dedupe_text(
                        to_list(
                            first_present(
                                item.get("affected_boundaries"),
                                localization.get("affected_boundaries"),
                                [],
                            )
                        )
                    ),
                    "localization": localization,
                    "supporting_relationships": support,
                    "contributing_relationships": support,
                    "conflicting_relationships": conflicts,
                    "uncertain_relationships": uncertain,
                    "evidence": evidence_items,
                    "supporting_evidence": dedupe_text(
                        to_list(
                            first_present(
                                item.get("supporting_evidence"),
                                [evidence.get("summary") for evidence in evidence_items],
                                [],
                            )
                        )
                    ),
                    "evidence_summary": item.get("evidence_summary"),
                    "comparable_operation": comparable,
                    "timeline": to_list(first_present(item.get("timeline"), item.get("activity_timeline"))),
                    "activity_timeline": to_list(first_present(item.get("timeline"), item.get("activity_timeline"))),
                    "next_checks": next_checks,
                    "recommended_check": first_present(item.get("recommended_check"), next_checks[0] if next_checks else ""),
                    "recommended_investigation": next_checks,
                    "escalation": item.get("escalation") if isinstance(item.get("escalation"), dict) else {},
                    "status": first_present(item.get("status"), "open"),
                    "evidence_refs": refs,
                    "source_tags": dedupe_text(
                        to_list(first_present(item.get("source_tags"), item.get("affected_signals"), []))
                    ),
                    "certainty_limit": first_present(
                        item.get("certainty_limit"),
                        classification.get("certainty_limit"),
                    ),
                }
            )
        )
        conditions.append(condition)
    return conditions


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
    conditions: list[dict[str, Any]],
    insights: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
    fingerprint: dict[str, Any],
) -> dict[str, Any]:
    raw = explanation.get("executive_summary") if isinstance(explanation.get("executive_summary"), dict) else {}
    top_condition = conditions[0] if conditions else {}
    top_insight = insights[0] if insights else {}
    top_recommendation = recommendations[0] if recommendations else {}
    return compact_dict(
        {
            "overall_operational_status": first_present(raw.get("overall_operational_status"), result.get("operating_state"), "Analysis complete"),
            "highest_priority_finding": first_present(top_condition.get("headline"), top_insight.get("title"), raw.get("highest_priority_finding")),
            "biggest_emerging_risk": first_present(top_insight.get("possible_consequence"), raw.get("biggest_emerging_risk"), fingerprint.get("explanation")),
            "recommended_action": first_present(top_condition.get("recommended_check"), top_recommendation.get("recommendation"), top_insight.get("recommended_check"), raw.get("recommended_action")),
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
        return "Operating relationship change from the historical and current windows."
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
    normalized_telemetry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    timestamp = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    first = clean_text(timestamp.get("first_timestamp"))
    last = clean_text(timestamp.get("last_timestamp"))
    baseline_rows = int_or_none(baseline.get("baseline_window_rows"))
    recent_rows = int_or_none(baseline.get("recent_window_rows"))
    total_rows = int_or_none(result.get("row_count") or result.get("rows_processed"))
    fallback_window = build_time_window(result)
    stable_start, stable_end = adaptive_baseline_window_bounds(
        baseline=baseline,
        result=result,
        normalized_telemetry=normalized_telemetry,
        fallback_start=first,
        fallback_end=last,
    )

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
            start=stable_start,
            end=stable_end,
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


def adaptive_baseline_window_bounds(
    *,
    baseline: dict[str, Any],
    result: dict[str, Any],
    normalized_telemetry: dict[str, Any] | None,
    fallback_start: str,
    fallback_end: str,
) -> tuple[str, str]:
    adaptive = baseline.get("adaptive_baseline") if isinstance(baseline.get("adaptive_baseline"), dict) else {}
    start_index = int_or_none(adaptive.get("start_index"))
    end_index = int_or_none(adaptive.get("end_index"))
    if start_index is None or end_index is None:
        return fallback_start, fallback_end

    exact_start = timestamp_for_normalized_row(normalized_telemetry, start_index)
    exact_end = timestamp_for_normalized_row(normalized_telemetry, end_index)
    if exact_start or exact_end:
        return first_present(exact_start, fallback_start), first_present(exact_end, fallback_end)

    profile = result.get("timestamp_profile") if isinstance(result.get("timestamp_profile"), dict) else {}
    first_timestamp = clean_text(profile.get("first_timestamp"))
    interval_seconds = sample_interval_seconds(profile.get("estimated_sample_interval"))
    if first_timestamp and interval_seconds:
        return (
            timestamp_at_index(first_timestamp, start_index, interval_seconds) or fallback_start,
            timestamp_at_index(first_timestamp, end_index, interval_seconds) or fallback_end,
        )
    return fallback_start, fallback_end


def timestamp_for_normalized_row(normalized_telemetry: dict[str, Any] | None, row_index: int) -> str:
    if not isinstance(normalized_telemetry, dict):
        return ""
    timestamps: list[str] = []
    seen: set[str] = set()
    for record in to_list(normalized_telemetry.get("records")):
        if not isinstance(record, dict):
            continue
        timestamp = clean_text(record.get("timestamp"))
        if timestamp and timestamp not in seen:
            seen.add(timestamp)
            timestamps.append(timestamp)
    if 0 <= row_index < len(timestamps):
        return timestamps[row_index]
    return ""


def timestamp_at_index(first_timestamp: str, row_index: int, interval_seconds: int) -> str:
    try:
        parsed = datetime.fromisoformat(first_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return ""
    value = parsed + timedelta(seconds=row_index * interval_seconds)
    return value.isoformat().replace("+00:00", "Z")


def sample_interval_seconds(value: Any) -> int | None:
    text = clean_text(value).lower()
    if not text:
        return None
    match = re.match(r"^(\d+)\s*(second|seconds|minute|minutes|hour|hours)$", text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("second"):
        return amount
    if unit.startswith("minute"):
        return amount * 60
    if unit.startswith("hour"):
        return amount * 3600
    return None


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
