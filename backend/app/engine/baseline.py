from typing import Any


def baseline_window_evidence(baseline_analysis: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    evidence = [
        {
            "type": "baseline_window",
            "baseline_window_rows": baseline_analysis["baseline_window_rows"],
            "recent_window_rows": baseline_analysis["recent_window_rows"],
            "columns_analyzed": baseline_analysis["columns_analyzed"],
            "overall_assessment": baseline_analysis["overall_assessment"],
        }
    ]
    audit_trace = [
        (
            "baseline.windows:"
            f"baseline={baseline_analysis['baseline_window_rows']},"
            f"recent={baseline_analysis['recent_window_rows']},"
            f"columns={baseline_analysis['columns_analyzed']}"
        )
    ]
    return evidence, audit_trace
