from typing import Any

from app.engine.baseline import baseline_window_evidence
from app.engine.drift import evaluate_column_drift
from app.engine.explanations import base_limitations, build_summary, determine_overall_result
from app.engine.relationships import evaluate_relationships
from app.engine.schemas import ENGINE_VERSION


def run_engine_analysis(
    *,
    columns: list[str],
    rows: list[list[str]],
    data_quality: dict[str, Any],
    baseline_analysis: dict[str, Any],
    cultivation_mapping: dict[str, Any],
    numeric_profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    recommended_checks: list[str] = []
    limitations = base_limitations()
    audit_trace = [
        f"engine.version:{ENGINE_VERSION}",
        f"inputs.rows:{data_quality['row_count']}",
        f"inputs.columns:{data_quality['column_count']}",
        f"inputs.mapped_columns:{cultivation_mapping['mapped_column_count']}",
    ]

    baseline_evidence, baseline_audit = baseline_window_evidence(baseline_analysis)
    evidence.extend(baseline_evidence)
    audit_trace.extend(baseline_audit)

    if data_quality["readiness"] == "not_ready":
        signals.append(
            {
                "type": "data_readiness",
                "level": "watch",
                "message": "Upload data is not ready for a complete engine pass.",
            }
        )
        limitations.append("Engine review is limited because the upload is not ready.")
        audit_trace.append("engine.data_readiness:not_ready")

    if data_quality["warnings"]:
        limitations.append("Data quality warnings are present in the upload profile.")
        audit_trace.append("engine.data_quality:warnings_present")

    if any(profile["missing_count"] > 0 for profile in numeric_profiles):
        limitations.append("One or more numeric columns contain missing values.")
        audit_trace.append("engine.numeric_profile:missing_values_present")

    drift_signals, drift_evidence, drift_checks, drift_audit = evaluate_column_drift(
        baseline_analysis
    )
    signals.extend(drift_signals)
    evidence.extend(drift_evidence)
    recommended_checks.extend(drift_checks)
    audit_trace.extend(drift_audit)

    relationship_signals, relationship_evidence, relationship_checks, relationship_limitations, relationship_audit = evaluate_relationships(
        columns,
        rows,
        numeric_profiles,
    )
    signals.extend(relationship_signals)
    evidence.extend(relationship_evidence)
    recommended_checks.extend(relationship_checks)
    limitations.extend(relationship_limitations)
    audit_trace.extend(relationship_audit)

    if cultivation_mapping["unknown_column_count"]:
        recommended_checks.append("Review unmapped CSV columns for clearer cultivation sensor labels.")
        audit_trace.append("engine.mapping:unknown_columns_present")

    if not recommended_checks:
        recommended_checks.append("Confirm the uploaded period and sensor channels match the facility area under review.")

    overall_result = determine_overall_result(signals, limitations[3:])

    return {
        "engine_version": ENGINE_VERSION,
        "summary": build_summary(overall_result, signals, limitations[3:]),
        "overall_result": overall_result,
        "signals": signals,
        "evidence": evidence,
        "recommended_checks": list(dict.fromkeys(recommended_checks)),
        "limitations": list(dict.fromkeys(limitations)),
        "audit_trace": audit_trace,
    }
