from __future__ import annotations

from typing import Any


def build_analysis_explanation(result: dict[str, Any]) -> dict[str, Any]:
    baseline = result.get("baseline_analysis") if isinstance(result.get("baseline_analysis"), dict) else {}
    relationship_model = result.get("relationship_model") if isinstance(result.get("relationship_model"), dict) else {}
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
    fingerprint = build_fingerprint(
        baseline=baseline,
        relationship_model=relationship_model,
        intelligence=intelligence,
        result=result,
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
        "insights": insights,
        "fingerprint": fingerprint,
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

    relationship_changes = [
        item for item in relationship_model.get("top_relationship_changes", [])
        if isinstance(item, dict)
    ]
    for index, item in enumerate(relationship_changes[:3]):
        columns = relationship_columns(item)
        label = " / ".join(columns) if columns else str(item.get("relationship") or "Signal relationship")
        evidence = relationship_evidence(item, time_window)
        insights.append(
            compact_dict(
                {
                    "id": f"relationship-{index}",
                    "title": f"Relationship shift: {label}",
                    "severity": severity_from_number(item.get("correlation_delta")),
                    "explanation": first_text(
                        item.get("summary"),
                        f"{label} changed between the baseline window and recent window.",
                    ),
                    "likely_cause": "The affected signals no longer move together the way they did in the baseline window.",
                    "contributing_factors": columns,
                    "possible_consequence": "A coupled subsystem may be changing state instead of an isolated sensor moving alone.",
                    "recommended_action": f"Compare {label} timing against operator logs, setpoint changes, and equipment activity for the same window.",
                    "operator_check": f"Check whether {label} changed after a known operating mode or equipment state change.",
                    "evidence": evidence,
                    "confidence": confidence_from_samples(item.get("baseline_sample_size"), item.get("recent_sample_size")),
                    "system": system_from_columns(columns),
                }
            )
        )

    drift_items = [
        item for item in baseline.get("column_drift", [])
        if isinstance(item, dict) and item.get("drift_flag") in {"watch", "review"}
    ]
    drift_items.sort(key=lambda item: abs(float(item.get("percent_change") or item.get("absolute_change") or 0)), reverse=True)
    for index, item in enumerate(drift_items[: max(0, 5 - len(insights))]):
        column = str(item.get("column") or "Signal")
        direction = str(item.get("direction") or "changed")
        persistent = column in persistent_columns
        evidence = column_evidence(item, time_window, persistence if isinstance(persistence, dict) else {})
        insights.append(
            compact_dict(
                {
                    "id": f"metric-{index}",
                    "title": f"{column} moved {direction}",
                    "severity": "high" if item.get("drift_flag") == "review" else "moderate",
                    "explanation": f"{column} moved {direction} from the baseline window to the recent window.",
                    "likely_cause": "The recent operating period differs from the baseline period for this signal.",
                    "contributing_factors": [column],
                    "possible_consequence": "If this persists, the related process may continue moving away from its operating fingerprint.",
                    "recommended_action": first_text(
                        matching_operator_check(operator_report, column),
                        f"Review {column} readings against facility logs for the uploaded period.",
                    ),
                    "operator_check": f"Check source readings, control changes, and maintenance activity involving {column}.",
                    "evidence": evidence,
                    "confidence": "high" if persistent else "moderate",
                    "system": system_from_columns([column]),
                }
            )
        )

    if not insights and baseline.get("overall_assessment") == "normal":
        evidence = [
            compact_dict(
                {
                    "confidence": confidence_from_baseline(baseline),
                    "supporting_signals": [
                        f"{baseline.get('columns_analyzed')} numeric columns analyzed",
                        f"{baseline.get('baseline_window_rows')} baseline rows",
                        f"{baseline.get('recent_window_rows')} recent rows",
                    ],
                    "time_window": time_window,
                }
            )
        ]
        insights.append(
            compact_dict(
                {
                    "id": "baseline-stable",
                    "title": "Operating fingerprint remains stable",
                    "severity": "low",
                    "explanation": "No numeric signal crossed the baseline review threshold in the uploaded analysis.",
                    "likely_cause": "Recent readings remained close to the baseline window.",
                    "possible_consequence": "Continue normal monitoring unless operator logs show an unmodeled event.",
                    "recommended_action": first_item(operator_report.get("recommended_operator_checks")),
                    "operator_check": first_item(operator_report.get("recommended_operator_checks")),
                    "evidence": evidence,
                    "confidence": confidence_from_baseline(baseline),
                    "system": first_text(intelligence.get("primary_room"), "Uploaded telemetry"),
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
        if not isinstance(item, dict) or item.get("drift_flag") not in {"watch", "review"}:
            continue
        target = entry(system_from_columns([str(item.get("column") or "")]))
        target["key_behaviors"].append(f"{item.get('column')} is moving {item.get('direction')} against baseline.")
        target["what_changed"].append(change_phrase(item))

    for relationship in relationship_model.get("top_relationship_changes", []) if isinstance(relationship_model.get("top_relationship_changes"), list) else []:
        if not isinstance(relationship, dict):
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


def build_fingerprint(
    *,
    baseline: dict[str, Any],
    relationship_model: dict[str, Any],
    intelligence: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    relationship_changes = relationship_model.get("top_relationship_changes", []) if isinstance(relationship_model.get("top_relationship_changes"), list) else []
    significant_columns = [
        item for item in baseline.get("column_drift", [])
        if isinstance(item, dict) and item.get("drift_flag") in {"watch", "review"}
    ]
    largest = largest_deviation(significant_columns, relationship_changes)
    assessment = baseline.get("overall_assessment")
    if assessment == "normal" and not relationship_changes:
        meaning = "The operating fingerprint is stable. Current behavior closely matches the baseline window in the uploaded telemetry."
        status = "stable"
    elif relationship_changes or significant_columns:
        meaning = "The operating fingerprint is changing. Recent behavior no longer fully matches the baseline window in the uploaded telemetry."
        status = "changed"
    else:
        meaning = ""
        status = ""
    if largest:
        meaning = f"{meaning} The largest deviation is {largest}.".strip()

    return compact_dict(
        {
            "status": status,
            "meaning": meaning,
            "largest_deviation": largest,
            "baseline_window_rows": baseline.get("baseline_window_rows"),
            "recent_window_rows": baseline.get("recent_window_rows"),
            "columns_analyzed": baseline.get("columns_analyzed"),
            "confidence": confidence_from_baseline(baseline),
            "primary_driver": intelligence.get("primary_driver"),
        }
    )


def compact_system(item: dict[str, Any]) -> dict[str, Any]:
    compacted: dict[str, Any] = {}
    for key, value in item.items():
        if value is None or value == "" or value == []:
            continue
        compacted[key] = dedupe(value) if isinstance(value, list) else value
    return compacted


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
        return columns[:2]
    relationship = str(item.get("relationship") or "")
    if "<->" in relationship:
        return [part.strip() for part in relationship.split("<->", 1) if part.strip()]
    columns = item.get("columns")
    if isinstance(columns, list):
        return [str(column) for column in columns if column]
    return []


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
        column = str(item.get("column") or "signal")
        direction = str(item.get("direction") or "changed")
        magnitude = abs(float(item.get("percent_change") or item.get("absolute_change") or 0))
        candidates.append((magnitude, f"{column} moving {direction}"))
    for item in relationships:
        magnitude = abs(float(item.get("correlation_delta") or 0))
        label = " / ".join(relationship_columns(item)) or str(item.get("relationship") or "signal coupling")
        candidates.append((magnitude, f"relationship shift in {label}"))
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
