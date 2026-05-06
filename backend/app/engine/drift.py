from typing import Any


def evaluate_column_drift(baseline_analysis: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    signals: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    recommended_checks: list[str] = []
    audit_trace: list[str] = []

    for drift in baseline_analysis["column_drift"]:
        if is_timestamp_like(drift["column"]):
            audit_trace.append(f"drift.column_skipped_timestamp:{drift['column']}")
            continue
        audit_trace.append(
            "drift.column:"
            f"{drift['column']}:{drift['direction']}:{drift['drift_flag']}"
        )
        evidence.append(
            {
                "type": "column_drift",
                "column": drift["column"],
                "baseline_average": drift["baseline_average"],
                "recent_average": drift["recent_average"],
                "absolute_change": drift["absolute_change"],
                "percent_change": drift["percent_change"],
                "direction": drift["direction"],
                "drift_flag": drift["drift_flag"],
            }
        )

        if drift["drift_flag"] in {"watch", "review"}:
            level = "elevated" if drift["drift_flag"] == "review" else "watch"
            signals.append(
                {
                    "type": "baseline_drift",
                    "level": level,
                    "column": drift["column"],
                    "message": (
                        f"{drift['column']} moved {drift['direction']} from the baseline "
                        "window to the recent window."
                    ),
                }
            )
            recommended_checks.append(
                f"Review {drift['column']} readings against facility logs for the uploaded period."
            )

    return signals, evidence, recommended_checks, audit_trace


def is_timestamp_like(column: str) -> bool:
    normalized = column.lower().replace(" ", "_")
    return normalized in {"timestamp", "time", "datetime", "date", "recorded_at", "created_at"}
