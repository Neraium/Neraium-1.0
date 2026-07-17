from __future__ import annotations

from typing import Any

from psycopg import Connection


MIGRATION_ID = "001_create_normalization_tables"


def run(conn: Connection[Any]) -> None:
    """Create the PostgreSQL telemetry-normalization schema.

    The only automatic supported starting state is an empty schema or a schema
    already stamped with this migration. The historical unversioned table used
    a primary key that omitted source_id; upgrading it requires an operator-run,
    batched copy and is rejected here to avoid an unbounded production rewrite.
    TimescaleDB is used only when already installed by infrastructure owners.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS neraium_schema_migrations (
                migration_id TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cur.execute(
            "SELECT 1 FROM neraium_schema_migrations WHERE migration_id = %s",
            (MIGRATION_ID,),
        )
        if cur.fetchone():
            conn.commit()
            return

        cur.execute("SELECT to_regclass('telemetry_normalized')")
        if cur.fetchone()[0] is not None:
            raise RuntimeError(
                "unsupported_unversioned_normalization_schema: follow the documented "
                "batched source_id primary-key migration before stamping 001"
            )

        cur.execute(
            """
            CREATE TABLE signal_integrity (
                id               BIGSERIAL PRIMARY KEY,
                signal_id        TEXT NOT NULL,
                source_id        TEXT NOT NULL,
                window_start     TIMESTAMPTZ NOT NULL,
                window_end       TIMESTAMPTZ NOT NULL,
                gap_type         TEXT CHECK (gap_type IS NULL OR gap_type IN
                                    ('terminal', 'scheduled', 'short_drop', 'sustained', 'correlated')),
                completeness     DOUBLE PRECISION NOT NULL
                                    CHECK (completeness >= 0 AND completeness <= 1),
                samples_expected INTEGER NOT NULL CHECK (samples_expected >= 0),
                samples_received INTEGER NOT NULL CHECK (
                                    samples_received >= 0 AND samples_received <= samples_expected),
                treatment        TEXT CHECK (treatment IS NULL OR treatment IN
                                    ('excluded', 'filled', 'sentinel')),
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CHECK (window_end > window_start),
                UNIQUE (signal_id, source_id, window_start, window_end)
            );

            CREATE INDEX idx_signal_integrity_signal_window
                ON signal_integrity (signal_id, source_id, window_start DESC, window_end DESC);

            CREATE TABLE source_integrity (
                id               BIGSERIAL PRIMARY KEY,
                source_id        TEXT NOT NULL,
                window_start     TIMESTAMPTZ NOT NULL,
                window_end       TIMESTAMPTZ NOT NULL,
                status           TEXT NOT NULL CHECK (status IN ('good', 'degraded', 'outage', 'missing')),
                affected_signals TEXT[] NOT NULL DEFAULT '{}',
                notes            TEXT,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CHECK (window_end > window_start),
                UNIQUE (source_id, window_start, window_end)
            );

            CREATE INDEX idx_source_integrity_source_window
                ON source_integrity (source_id, window_start DESC, window_end DESC);

            CREATE TABLE telemetry_normalized (
                time             TIMESTAMPTZ NOT NULL,
                signal_id        TEXT NOT NULL,
                source_id        TEXT NOT NULL,
                value            DOUBLE PRECISION CHECK (
                                    value IS NULL OR (
                                        value = value
                                        AND value NOT IN ('Infinity'::DOUBLE PRECISION, '-Infinity'::DOUBLE PRECISION)
                                    )),
                is_filled        BOOLEAN NOT NULL DEFAULT FALSE,
                fill_method      TEXT CHECK (fill_method IS NULL OR fill_method IN
                                    ('linear', 'forward_fill', 'sentinel')),
                integrity_flag   TEXT NOT NULL CHECK (integrity_flag IN ('good', 'degraded', 'missing')),
                PRIMARY KEY (time, source_id, signal_id)
            );

            CREATE INDEX idx_telemetry_normalized_signal_time
                ON telemetry_normalized (signal_id, source_id, time DESC);

            CREATE INDEX idx_telemetry_normalized_source_time
                ON telemetry_normalized (source_id, time DESC);
            """
        )
        cur.execute(
            "INSERT INTO neraium_schema_migrations (migration_id) VALUES (%s)",
            (MIGRATION_ID,),
        )

        cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")
        if cur.fetchone():
            cur.execute(
                """
                SELECT create_hypertable(
                    'telemetry_normalized', 'time',
                    partitioning_column => 'source_id',
                    number_partitions => 4,
                    if_not_exists => TRUE,
                    migrate_data => FALSE
                )
                """
            )
    conn.commit()
