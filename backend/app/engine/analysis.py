from typing import Any

from app.engine.baseline import baseline_window_evidence
from app.engine.drift import evaluate_column_drift
from app.engine.explanations import base_limitations, build_summary, determine_overall_result
from app.engine.relationships import evaluate_relationships
from app.engine.schemas import ENGINE_VERSION

PERSISTENCE_RECENT_ROW_MINIMUM = 3


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
        f"baseline_window_rows_used:{baseline_analysis['baseline_window_rows']}",
        f"recent_window_rows_used:{baseline_analysis['recent_window_rows']}",
        f"columns_analyzed:{baseline_analysis['columns_analyzed']}",
    ]
    audit_trace.extend(skipped_column_audit(columns, numeric_profiles))

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

    system_evidence = build_system_evidence(
        cultivation_mapping,
        evidence,
        signals,
    )
    persistence_assessment = assess_persistence(
        columns,
        rows,
        baseline_analysis,
    )
    audit_trace.extend(persistence_assessment["audit_trace"])
    if persistence_assessment["limitations"]:
        limitations.extend(persistence_assessment["limitations"])

    if not recommended_checks:
        recommended_checks.append("Confirm the uploaded period and sensor channels match the facility area under review.")

    overall_result = determine_overall_result(signals, limitations[3:])

    return {
        "engine_version": ENGINE_VERSION,
        "summary": build_summary(overall_result, signals, limitations[3:]),
        "overall_result": overall_result,
        "signals": signals,
        "evidence": evidence,
        "system_evidence": system_evidence,
        "persistence_assessment": {
            key: value
            for key, value in persistence_assessment.items()
            if key != "audit_trace"
        },
        "recommended_checks": list(dict.fromkeys(recommended_checks)),
        "limitations": list(dict.fromkeys(limitations)),
        "audit_trace": audit_trace,
    }


def skipped_column_audit(columns: list[str], numeric_profiles: list[dict[str, Any]]) -> list[str]:
    numeric_columns = {profile["column"] for profile in numeric_profiles}
    audit: list[str] = []
    for column in columns:
        if is_timestamp_like(column):
            audit.append(f"columns_skipped:{column}:timestamp_context")
        elif column not in numeric_columns:
            audit.append(f"columns_skipped:{column}:non_numeric")
    if not audit:
        audit.append("columns_skipped:none")
    return audit


def build_system_evidence(
    cultivation_mapping: dict[str, Any],
    evidence: list[dict[str, Any]],
    signals: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped = {
        category: {
            "columns": mapped_columns,
            "signals": [],
            "evidence": [],
        }
        for category, mapped_columns in cultivation_mapping["categories"].items()
    }
    column_to_category = {
        column: category
        for category, mapped_columns in cultivation_mapping["categories"].items()
        for column in mapped_columns
    }

    meaningful_categories: set[str] = set()
    meaningful_numeric_columns: set[str] = set()
    relationship_signal_count = 0

    for item in evidence:
        if item["type"] == "column_drift":
            category = column_to_category.get(item["column"], "unknown")
            grouped[category]["evidence"].append(item)
            if item["drift_flag"] in {"watch", "review"}:
                meaningful_categories.add(category)
                meaningful_numeric_columns.add(item["column"])
        elif item["type"] == "relationship_change":
            for column in item["columns"]:
                category = column_to_category.get(column, "unknown")
                grouped[category]["evidence"].append(item)

    for signal in signals:
        if signal["type"] == "baseline_drift":
            category = column_to_category.get(signal["column"], "unknown")
            grouped[category]["signals"].append(signal)
            meaningful_categories.add(category)
            meaningful_numeric_columns.add(signal["column"])
        elif signal["type"] == "relationship_change":
            relationship_signal_count += 1
            for column in signal["columns"]:
                category = column_to_category.get(column, "unknown")
                grouped[category]["signals"].append(signal)
                meaningful_categories.add(category)
                meaningful_numeric_columns.add(column)

    numeric_signal_count = len(meaningful_numeric_columns)
    categories_showing_meaningful_change = len(meaningful_categories)

    return {
        "categories": grouped,
        "categories_showing_meaningful_change": categories_showing_meaningful_change,
        "numeric_signals_showing_meaningful_change": numeric_signal_count,
        "corroboration_level": corroboration_level(
            categories_showing_meaningful_change,
            numeric_signal_count,
            relationship_signal_count,
        ),
    }


def corroboration_level(
    category_count: int,
    numeric_signal_count: int,
    relationship_signal_count: int,
) -> str:
    if category_count >= 3 or (numeric_signal_count >= 2 and relationship_signal_count >= 1):
        return "strong"
    if category_count >= 2 or numeric_signal_count >= 2 or relationship_signal_count >= 1:
        return "moderate"
    return "limited"


def assess_persistence(
    columns: list[str],
    rows: list[list[str]],
    baseline_analysis: dict[str, Any],
) -> dict[str, Any]:
    recent_window_rows = baseline_analysis["recent_window_rows"]
    audit_trace = [f"persistence.recent_window_rows:{recent_window_rows}"]
    if recent_window_rows < PERSISTENCE_RECENT_ROW_MINIMUM:
        return {
            "status": "limited",
            "persistent_columns": [],
            "columns_assessed": 0,
            "details": [],
            "limitations": ["Persistence review needs at least 3 recent-window rows."],
            "audit_trace": [*audit_trace, "persistence.skipped:insufficient_recent_rows"],
        }

    recent_rows = rows[-recent_window_rows:]
    details = []
    persistent_columns = []

    for drift in baseline_analysis["column_drift"]:
        if drift["drift_flag"] == "normal" or is_timestamp_like(drift["column"]):
            continue
        column_index = columns.index(drift["column"])
        baseline_average = drift["baseline_average"]
        direction = drift["direction"]
        threshold = max(abs(baseline_average) * 0.01, 0.01)
        values = []
        for row in recent_rows:
            try:
                value = float(row[column_index].strip()) if column_index < len(row) else None
            except ValueError:
                continue
            if value is not None:
                values.append(value)
        if not values:
            continue
        if direction == "up":
            supporting_count = sum(value > baseline_average + threshold for value in values)
        elif direction == "down":
            supporting_count = sum(value < baseline_average - threshold for value in values)
        else:
            supporting_count = 0
        support_percent = round(supporting_count / len(values) * 100, 4)
        persistent = support_percent >= 70
        if persistent:
            persistent_columns.append(drift["column"])
        details.append(
            {
                "column": drift["column"],
                "direction": direction,
                "recent_values_checked": len(values),
                "supporting_recent_rows": supporting_count,
                "support_percent": support_percent,
                "persistent": persistent,
            }
        )
        audit_trace.append(
            f"persistence.column:{drift['column']}:{supporting_count}/{len(values)}:{'persistent' if persistent else 'not_persistent'}"
        )

    status = "persistent" if persistent_columns else "not_persistent"
    return {
        "status": status,
        "persistent_columns": persistent_columns,
        "columns_assessed": len(details),
        "details": details,
        "limitations": [],
        "audit_trace": audit_trace,
    }


def is_timestamp_like(column: str) -> bool:
    normalized = column.lower().replace(" ", "_")
    return normalized in {"timestamp", "time", "datetime", "date", "recorded_at", "created_at"}
