from typing import Any


def build_operator_report(
    data_quality: dict[str, Any],
    timestamp_profile: dict[str, Any],
    numeric_profiles: list[dict[str, Any]],
    baseline_analysis: dict[str, Any],
    cultivation_mapping: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report_warnings = list(
        dict.fromkeys(
            [
                *data_quality["warnings"],
                *timestamp_profile["warnings"],
                *baseline_analysis["warnings"],
                *(cultivation_mapping["warnings"] if cultivation_mapping else []),
            ]
        )
    )
    columns_requiring_review = columns_requiring_review_from_profiles(
        numeric_profiles,
        baseline_analysis,
    )

    return {
        "title": "Telemetry Upload Report",
        "summary": report_summary(data_quality, baseline_analysis),
        "data_readiness": data_quality["readiness"],
        "time_coverage": {
            "detected_timestamp_column": timestamp_profile["detected_timestamp_column"],
            "first_timestamp": timestamp_profile["first_timestamp"],
            "last_timestamp": timestamp_profile["last_timestamp"],
            "estimated_sample_interval": timestamp_profile["estimated_sample_interval"],
        },
        "key_observations": key_observations(
            data_quality,
            timestamp_profile,
            baseline_analysis,
            cultivation_mapping,
        ),
        "columns_requiring_review": columns_requiring_review,
        "recommended_operator_checks": recommended_operator_checks(
            data_quality,
            timestamp_profile,
            baseline_analysis,
            columns_requiring_review,
            cultivation_mapping,
        ),
        "limitations": report_limitations(data_quality, baseline_analysis),
        "source_sections_used": [
            "data_quality",
            "timestamp_profile",
            "numeric_profiles",
            "baseline_analysis",
            *(
                ["cultivation_mapping"]
                if cultivation_mapping and cultivation_mapping["mapped_column_count"] > 0
                else []
            ),
        ],
        "warnings": report_warnings,
    }


def report_summary(data_quality: dict[str, Any], baseline_analysis: dict[str, Any]) -> str:
    if data_quality["readiness"] == "ready" and baseline_analysis["overall_assessment"] == "normal":
        return (
            "The uploaded telemetry export is usable for initial review. "
            "Neraium found timestamp context, numeric readings, and no baseline "
            "comparison items requiring review."
        )
    if data_quality["readiness"] == "not_ready":
        return (
            "The uploaded telemetry export does not yet have enough usable "
            "structure for a reliable review. Address the listed warnings before "
            "using this file for operational comparison."
        )
    return (
        "The uploaded telemetry export can be reviewed, but one or more "
        "data quality or baseline comparison items need operator review."
    )


def key_observations(
    data_quality: dict[str, Any],
    timestamp_profile: dict[str, Any],
    baseline_analysis: dict[str, Any],
    cultivation_mapping: dict[str, Any] | None = None,
) -> list[str]:
    observations = [
        (
            f"File contains {data_quality['row_count']} data rows, "
            f"{data_quality['column_count']} columns, and "
            f"{data_quality['numeric_column_count']} numeric columns."
        )
    ]
    if timestamp_profile["detected_timestamp_column"]:
        observations.append(
            f"Timestamp column detected: {timestamp_profile['detected_timestamp_column']}."
        )
    else:
        observations.append("No timestamp column was detected; row order was used for basic review.")

    if timestamp_profile["first_timestamp"] and timestamp_profile["last_timestamp"]:
        observations.append(
            "Time coverage runs from "
            f"{timestamp_profile['first_timestamp']} to {timestamp_profile['last_timestamp']}."
        )

    if baseline_analysis["columns_analyzed"]:
        observations.append(
            f"Baseline comparison analyzed {baseline_analysis['columns_analyzed']} numeric columns "
            f"using {baseline_analysis['baseline_window_rows']} baseline rows and "
            f"{baseline_analysis['recent_window_rows']} recent rows."
        )
        flagged_columns = [
            item
            for item in baseline_analysis["column_drift"]
            if item["drift_flag"] in {"watch", "review"}
        ]
        if flagged_columns:
            names = ", ".join(item["column"] for item in flagged_columns)
            observations.append(f"Columns flagged for operator review: {names}.")
        else:
            observations.append("No numeric columns were flagged by the simple baseline comparison.")
    else:
        observations.append("Baseline comparison was limited because not enough usable rows were available.")

    if cultivation_mapping and cultivation_mapping["mapped_column_count"] > 0:
        mapped_categories = [
            category
            for category, mapped_columns in cultivation_mapping["categories"].items()
            if category != "unknown" and mapped_columns
        ]
        observations.append(
            "Schema mapping identified columns for: "
            f"{', '.join(mapped_categories)}."
        )

    return observations


def columns_requiring_review_from_profiles(
    numeric_profiles: list[dict[str, Any]],
    baseline_analysis: dict[str, Any],
) -> list[dict[str, Any]]:
    review_columns: dict[str, dict[str, Any]] = {}
    for profile in numeric_profiles:
        reasons: list[str] = []
        if profile["missing_count"]:
            reasons.append(
                f"{profile['missing_count']} missing values ({profile['missing_percent']}%)."
            )
        if profile["variability"] == "high":
            reasons.append("High variability in the uploaded values.")
        if profile["range_warning"]:
            reasons.append(profile["range_warning"])
        if reasons:
            review_columns[profile["column"]] = {
                "column": profile["column"],
                "reasons": reasons,
            }

    for drift in baseline_analysis["column_drift"]:
        if drift["drift_flag"] not in {"watch", "review"} and not drift["warnings"]:
            continue
        entry = review_columns.setdefault(
            drift["column"],
            {"column": drift["column"], "reasons": []},
        )
        if drift["drift_flag"] in {"watch", "review"}:
            entry["reasons"].append(
                f"Baseline comparison flag is {drift['drift_flag']} with {drift['direction']} movement."
            )
        entry["reasons"].extend(drift["warnings"])

    return list(review_columns.values())


def recommended_operator_checks(
    data_quality: dict[str, Any],
    timestamp_profile: dict[str, Any],
    baseline_analysis: dict[str, Any],
    columns_requiring_review: list[dict[str, Any]],
    cultivation_mapping: dict[str, Any] | None = None,
) -> list[str]:
    checks: list[str] = []
    if not timestamp_profile["detected_timestamp_column"]:
        checks.append("Confirm the export includes a timestamp column or a reliable row order.")
    if timestamp_profile["warnings"]:
        checks.append("Review timestamp formatting and sampling consistency in the source export.")
    if data_quality["numeric_column_count"] == 0:
        checks.append("Confirm the export includes numeric signal readings.")
    if columns_requiring_review:
        column_names = ", ".join(item["column"] for item in columns_requiring_review)
        checks.append(f"Review source sensor channels for: {column_names}.")
    if baseline_analysis["overall_assessment"] == "needs_review":
        checks.append("Compare the baseline and recent windows against facility logs for the same period.")
    if cultivation_mapping and cultivation_mapping["unknown_column_count"]:
        checks.append("Review unmapped CSV columns and rename source exports when labels are unclear.")
    if not checks:
        checks.append("Confirm the uploaded period and sensor channels match the facility area under review.")
    return checks


def report_limitations(
    data_quality: dict[str, Any],
    baseline_analysis: dict[str, Any],
) -> list[str]:
    limitations = [
        "This report uses only the uploaded CSV profile and simple baseline comparison.",
        "No data is stored permanently and the Neraium engine has not been run.",
        "This report does not identify root cause or predict downstream operational impact.",
    ]
    if data_quality["readiness"] != "ready":
        limitations.append("Evidence is limited because the upload has data quality items requiring review.")
    if baseline_analysis["columns_analyzed"] == 0:
        limitations.append("Baseline comparison is limited because no numeric columns were analyzed.")
    return limitations
