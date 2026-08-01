from __future__ import annotations

from datetime import UTC, datetime
from statistics import median
from typing import Any

from app.services.runtime_db import db_connection, init_runtime_db


MIN_LIVE_ANALYSIS_ROWS = 18
ELIGIBLE_QUALITY_STATUSES = ("good", "out_of_order")


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("rolling window timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def build_rolling_window(
    *,
    system_id: str,
    window_start: datetime,
    window_end: datetime,
    minimum_coverage_percent: float,
    eligible_signals: set[str] | None = None,
) -> dict[str, Any]:
    """Build a deterministic rectangular comparison window from Phase 1 rows."""

    if window_start.tzinfo is None or window_start.utcoffset() is None:
        raise ValueError("window_start must be timezone-aware")
    if window_end.tzinfo is None or window_end.utcoffset() is None:
        raise ValueError("window_end must be timezone-aware")
    start = window_start.astimezone(UTC)
    end = window_end.astimezone(UTC)
    if start >= end:
        raise ValueError("window_start must be before window_end")
    start_iso = _utc_iso(start)
    end_iso = _utc_iso(end)
    init_runtime_db()

    with db_connection() as connection:
        telemetry_rows = connection.execute(
            """
            SELECT telemetry_id, canonical_signal, telemetry_timestamp, value,
                   source, source_tag, quality_status, ingested_at
            FROM normalized_telemetry
            WHERE system_id = ?
              AND telemetry_timestamp >= ?
              AND telemetry_timestamp <= ?
              AND quality_status IN ('good', 'out_of_order')
            ORDER BY telemetry_timestamp ASC,
                     canonical_signal ASC,
                     ingested_at DESC,
                     source ASC,
                     telemetry_id DESC
            """,
            (system_id, start_iso, end_iso),
        ).fetchall()
        rejected_count = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM rejected_telemetry
                WHERE system_id = ?
                  AND telemetry_timestamp >= ?
                  AND telemetry_timestamp <= ?
                """,
                (system_id, start_iso, end_iso),
            ).fetchone()[0]
        )

    selected: dict[tuple[str, str], dict[str, Any]] = {}
    duplicate_count = 0
    excluded_signal_count = 0
    out_of_order_count = 0
    for raw in telemetry_rows:
        row = dict(raw)
        signal = str(row["canonical_signal"])
        if eligible_signals is not None and signal not in eligible_signals:
            excluded_signal_count += 1
            continue
        key = (str(row["telemetry_timestamp"]), signal)
        if key in selected:
            duplicate_count += 1
            continue
        selected[key] = row
        if row["quality_status"] == "out_of_order":
            out_of_order_count += 1

    timestamps = sorted({timestamp for timestamp, _ in selected})
    signals = sorted({signal for _, signal in selected})
    values_by_timestamp: dict[str, dict[str, float]] = {timestamp: {} for timestamp in timestamps}
    for (timestamp, signal), row in selected.items():
        values_by_timestamp[timestamp][signal] = float(row["value"])

    rectangular_rows = [
        {
            "timestamp": timestamp,
            **{
                signal: values_by_timestamp[timestamp].get(signal)
                for signal in signals
            },
        }
        for timestamp in timestamps
    ]
    parsed_timestamps = [
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        for timestamp in timestamps
    ]
    intervals = [
        (current - previous).total_seconds()
        for previous, current in zip(parsed_timestamps, parsed_timestamps[1:])
        if current > previous
    ]
    sampling_interval_seconds = float(median(intervals)) if intervals else None
    expected_rows = (
        max(
            len(timestamps),
            int((end - start).total_seconds() / sampling_interval_seconds) + 1,
        )
        if sampling_interval_seconds
        else len(timestamps)
    )
    coverage_by_signal = {
        signal: round(
            sum(1 for timestamp in timestamps if signal in values_by_timestamp[timestamp])
            / max(1, expected_rows)
            * 100.0,
            4,
        )
        for signal in signals
    }
    total_cells = expected_rows * len(signals)
    observed_cells = sum(len(values) for values in values_by_timestamp.values())
    overall_coverage = (
        round(observed_cells / max(1, total_cells) * 100.0, 4)
        if signals
        else 0.0
    )

    warnings: list[str] = []
    if out_of_order_count:
        warnings.append("mildly_out_of_order_values_included")
    if duplicate_count:
        warnings.append("duplicate_source_values_deduplicated")
    if rejected_count:
        warnings.append("quarantined_values_excluded")
    if excluded_signal_count:
        warnings.append("signals_not_present_in_approved_baseline_excluded")

    enough_rows = len(rectangular_rows) >= MIN_LIVE_ANALYSIS_ROWS
    enough_signals = len(signals) >= 2
    coverage_ready = overall_coverage >= float(minimum_coverage_percent)
    return {
        "system_id": system_id,
        "window_start": start_iso,
        "window_end": end_iso,
        "signals_included": signals,
        "rows_included": len(rectangular_rows),
        "expected_rows": expected_rows,
        "sampling_interval_seconds": sampling_interval_seconds,
        "rows": rectangular_rows,
        "coverage_by_signal": coverage_by_signal,
        "overall_coverage": overall_coverage,
        "exclusions": {
            "quarantined_values": rejected_count,
            "duplicate_source_values": duplicate_count,
            "signals_not_in_approved_baseline": excluded_signal_count,
        },
        "warnings": warnings,
        "analysis_ready": bool(enough_rows and enough_signals and coverage_ready),
    }
