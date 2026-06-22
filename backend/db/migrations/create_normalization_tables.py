from __future__ import annotations

from typing import Any

from psycopg import Connection


def run(conn: Connection[Any]) -> None:
    """Create telemetry integrity and normalized telemetry tables.

    TimescaleDB is used when available. The tables still work as regular
    PostgreSQL tables if the extension is not installed in a local/test database.
    """

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_integrity (
                id               BIGSERIAL PRIMARY KEY,
                signal_id        TEXT NOT NULL,
                source_id        TEXT NOT NULL,
                window_start     TIMESTAMPTZ NOT NULL,
                window_end       TIMESTAMPTZ NOT NULL,
                gap_type         TEXT,
                completeness     DOUBLE PRECISION,
                samples_expected INTEGER,
                samples_received INTEGER,
                treatment        TEXT,
                created_at       TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_signal_integrity_signal_window
                ON signal_integrity (signal_id, window_start, window_end);

            CREATE TABLE IF NOT EXISTS source_integrity (
                id               BIGSERIAL PRIMARY KEY,
                source_id        TEXT NOT NULL,
                window_start     TIMESTAMPTZ NOT NULL,
                window_end       TIMESTAMPTZ NOT NULL,
                status           TEXT,
                affected_signals TEXT[],
                notes            TEXT,
                created_at       TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_source_integrity_source_window
                ON source_integrity (source_id, window_start, window_end);

            CREATE TABLE IF NOT EXISTS telemetry_normalized (
                time             TIMESTAMPTZ NOT NULL,
                signal_id        TEXT NOT NULL,
                value            DOUBLE PRECISION,
                is_filled        BOOLEAN DEFAULT FALSE,
                fill_method      TEXT,
                integrity_flag   TEXT,
                PRIMARY KEY (time, signal_id)
            );
            """
        )

        cur.execute("CREATE EXTENSION IF NOT EXISTS timescaledb;")
        cur.execute(
            """
            SELECT create_hypertable(
                'telemetry_normalized', 'time',
                if_not_exists => TRUE
            );
            """
        )

    conn.commit()
