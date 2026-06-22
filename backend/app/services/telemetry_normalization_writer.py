from __future__ import annotations

from typing import Any

import pandas as pd
from psycopg import Connection

from app.services.telemetry_normalization import IntegrityProfile, SENTINEL


def write_normalized(conn: Connection[Any], result: dict[str, Any]) -> None:
    """Persist normalized telemetry and signal integrity profiles.

    This helper is intentionally separate from the upload path so SII can run in
    read-only/file mode today while TimescaleDB persistence can be enabled for
    connected deployments.
    """

    normalized: pd.DataFrame = result["normalized"]
    fill_methods: dict[str, str | None] = result["fill_methods"]
    integrity_flags: dict[str, str] = result["integrity_flags"]
    profiles: dict[str, IntegrityProfile] = result["integrity_profiles"]

    telemetry_rows: list[tuple[Any, str, float | None, bool, str | None, str]] = []
    for signal_id, series in normalized.items():
        flag = integrity_flags[signal_id]
        fill = fill_methods[signal_id]
        for ts, value in series.items():
            telemetry_rows.append((
                ts,
                signal_id,
                None if pd.isna(value) or value == SENTINEL else float(value),
                fill is not None,
                fill,
                flag,
            ))

    profile_rows = [
        (
            profile.signal_id,
            profile.source_id,
            profile.window_start,
            profile.window_end,
            profile.gap_type,
            profile.completeness,
            profile.samples_expected,
            profile.samples_received,
            profile.treatment,
        )
        for profile in profiles.values()
    ]

    with conn.cursor() as cur:
        if telemetry_rows:
            cur.executemany(
                """
                INSERT INTO telemetry_normalized
                    (time, signal_id, value, is_filled, fill_method, integrity_flag)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                telemetry_rows,
            )
        if profile_rows:
            cur.executemany(
                """
                INSERT INTO signal_integrity
                    (signal_id, source_id, window_start, window_end,
                     gap_type, completeness, samples_expected,
                     samples_received, treatment)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                profile_rows,
            )
    conn.commit()


def write_source_integrity(
    conn: Connection[Any],
    *,
    source_id: str,
    window_start: Any,
    window_end: Any,
    status: str,
    affected_signals: list[str],
    notes: str | None = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_integrity
                (source_id, window_start, window_end, status, affected_signals, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (source_id, window_start, window_end, status, affected_signals, notes),
        )
    conn.commit()
