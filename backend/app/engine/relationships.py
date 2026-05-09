import math
from itertools import combinations
from typing import Any

from app.services.baseline_analysis import BASELINE_WINDOW_FRACTION, MIN_BASELINE_ROWS

RELATIONSHIP_CHANGE_THRESHOLD = 0.5


def evaluate_relationships(
    columns: list[str],
    rows: list[list[str]],
    numeric_profiles: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str], list[str]]:
    signals: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    recommended_checks: list[str] = []
    limitations: list[str] = []
    audit_trace: list[str] = []

    numeric_columns = [
        profile["column"]
        for profile in numeric_profiles
        if not is_timestamp_like(profile["column"])
    ]
    if len(rows) < MIN_BASELINE_ROWS:
        limitations.append("Relationship review skipped because there are not enough rows.")
        audit_trace.append("relationships.skipped:insufficient_rows")
        audit_trace.append("relationship_checks_attempted:0")
        audit_trace.append("relationship_checks_skipped:insufficient_rows")
        return signals, evidence, recommended_checks, limitations, audit_trace

    if len(numeric_columns) < 2:
        limitations.append("Relationship review skipped because fewer than two numeric columns were available.")
        audit_trace.append("relationships.skipped:insufficient_numeric_columns")
        audit_trace.append("relationship_checks_attempted:0")
        audit_trace.append("relationship_checks_skipped:insufficient_numeric_columns")
        return signals, evidence, recommended_checks, limitations, audit_trace

    window_size = max(1, math.ceil(len(rows) * BASELINE_WINDOW_FRACTION))
    baseline_rows = rows[:window_size]
    recent_rows = rows[-window_size:]
    column_indexes = {column: columns.index(column) for column in numeric_columns if column in columns}
    attempted_checks = 0

    for first_column, second_column in combinations(column_indexes.keys(), 2):
        attempted_checks += 1
        baseline_corr = correlation_for_pair(
            baseline_rows,
            column_indexes[first_column],
            column_indexes[second_column],
        )
        recent_corr = correlation_for_pair(
            recent_rows,
            column_indexes[first_column],
            column_indexes[second_column],
        )
        if baseline_corr is None or recent_corr is None:
            audit_trace.append(f"relationships.pair_skipped:{first_column}:{second_column}")
            audit_trace.append("relationship_checks_skipped:insufficient_paired_values")
            continue

        change = recent_corr - baseline_corr
        evidence.append(
            {
                "type": "relationship_change",
                "columns": [first_column, second_column],
                "baseline_correlation": round(baseline_corr, 4),
                "recent_correlation": round(recent_corr, 4),
                "change": round(change, 4),
            }
        )
        audit_trace.append(
            "relationships.pair:"
            f"{first_column}:{second_column}:change={round(change, 4)}"
        )

        if abs(change) >= RELATIONSHIP_CHANGE_THRESHOLD:
            signals.append(
                {
                    "type": "relationship_change",
                    "level": "elevated",
                    "columns": [first_column, second_column],
                    "message": (
                        f"{display_column(first_column)} and {display_column(second_column)} relationship consistency "
                        "became less stable between the baseline and active windows."
                    ),
                }
            )
            recommended_checks.append(
                f"Compare {display_column(first_column)} and {display_column(second_column)} timing against room activity logs."
            )

    if not evidence:
        audit_trace.append("relationships.skipped:no_comparable_pairs")
        audit_trace.append("relationship_checks_skipped:no_comparable_pairs")

    audit_trace.append(f"relationship_checks_attempted:{attempted_checks}")

    return signals, evidence, recommended_checks, limitations, audit_trace


def correlation_for_pair(rows: list[list[str]], first_index: int, second_index: int) -> float | None:
    pairs: list[tuple[float, float]] = []
    for row in rows:
        try:
            first = float(row[first_index].strip()) if first_index < len(row) else None
            second = float(row[second_index].strip()) if second_index < len(row) else None
        except ValueError:
            continue
        if first is None or second is None:
            continue
        if math.isfinite(first) and math.isfinite(second):
            pairs.append((first, second))

    if len(pairs) < 2:
        return None

    first_values = [pair[0] for pair in pairs]
    second_values = [pair[1] for pair in pairs]
    first_avg = sum(first_values) / len(first_values)
    second_avg = sum(second_values) / len(second_values)
    numerator = sum(
        (first - first_avg) * (second - second_avg)
        for first, second in pairs
    )
    first_variance = sum((first - first_avg) ** 2 for first in first_values)
    second_variance = sum((second - second_avg) ** 2 for second in second_values)
    denominator = math.sqrt(first_variance * second_variance)
    if denominator == 0:
        return None
    return numerator / denominator


def is_timestamp_like(column: str) -> bool:
    normalized = column.lower().replace(" ", "_")
    return normalized in {"timestamp", "time", "datetime", "date", "recorded_at", "created_at"}


def display_column(column: str) -> str:
    normalized = column.lower().replace("_", " ")
    aliases = {
        "intervention window hours": "intervention window",
        "hvac runtime": "HVAC runtime",
        "co2": "CO2",
    }
    return aliases.get(normalized, normalized)
