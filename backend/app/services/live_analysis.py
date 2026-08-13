from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services import behavioral_model_repository, live_intelligence
from app.services.dataset_scope import current_dataset_scope
from app.services.live_windows import MIN_LIVE_ANALYSIS_ROWS, build_rolling_window
from app.services.runtime_db import db_connection, init_runtime_db


logger = logging.getLogger(__name__)

DEFAULT_ANALYSIS_INTERVAL_SECONDS = 300
DEFAULT_COMPARISON_WINDOW_MINUTES = 60
DEFAULT_MINIMUM_COVERAGE_PERCENT = 80.0
DEFAULT_ALLOWED_LATENESS_MINUTES = 5
MIN_STALE_ACTIVE_RUN_SECONDS = 900
SKIPPED_REASONS = frozenset(
    {
        "disabled",
        "missing_baseline",
        "insufficient_coverage",
        "insufficient_signals",
        "telemetry_delayed",
        "telemetry_unavailable",
        "duplicate_window",
        "analysis_already_running",
    }
)


class LiveAnalysisConflictError(ValueError):
    pass


class LiveAnalysisNotFoundError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _scope_id() -> str:
    return current_dataset_scope().storage_id


def _config_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload.pop("scope_storage_id", None)
    payload["enabled"] = bool(payload["enabled"])
    payload["minimum_coverage_percent"] = float(payload["minimum_coverage_percent"])
    return payload


def _run_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload.pop("scope_storage_id", None)
    payload.pop("analytics_result_json", None)
    return payload


def _finding_payload(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload.pop("scope_storage_id", None)
    payload["finding_classification"] = json.loads(payload.pop("finding_classification_json"))
    payload["persistence_state"] = json.loads(payload.pop("persistence_state_json"))
    payload["latest_evidence"] = json.loads(payload.pop("latest_evidence_json"))
    return payload


def create_live_analysis_configuration(
    payload: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    init_runtime_db()
    current = (now or _now()).astimezone(UTC)
    timestamp = _iso(current)
    enabled = bool(payload.get("enabled", False))
    next_analysis = timestamp if enabled else None
    values = {
        "system_id": str(payload["system_id"]),
        "enabled": enabled,
        "approved_baseline_id": payload.get("approved_baseline_id"),
        "analysis_interval_seconds": int(
            payload.get("analysis_interval_seconds", DEFAULT_ANALYSIS_INTERVAL_SECONDS)
        ),
        "comparison_window_minutes": int(
            payload.get("comparison_window_minutes", DEFAULT_COMPARISON_WINDOW_MINUTES)
        ),
        "minimum_coverage_percent": float(
            payload.get("minimum_coverage_percent", DEFAULT_MINIMUM_COVERAGE_PERCENT)
        ),
        "allowed_lateness_minutes": int(
            payload.get("allowed_lateness_minutes", DEFAULT_ALLOWED_LATENESS_MINUTES)
        ),
    }
    try:
        with db_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO live_analysis_configurations (
                    system_id, scope_storage_id, enabled, approved_baseline_id,
                    analysis_interval_seconds, comparison_window_minutes,
                    minimum_coverage_percent, allowed_lateness_minutes,
                    last_analysis_started_at, last_analysis_completed_at,
                    next_analysis_at, current_status, latest_error,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, ?, ?)
                """,
                (
                    values["system_id"],
                    _scope_id(),
                    1 if enabled else 0,
                    values["approved_baseline_id"],
                    values["analysis_interval_seconds"],
                    values["comparison_window_minutes"],
                    values["minimum_coverage_percent"],
                    values["allowed_lateness_minutes"],
                    next_analysis,
                    "enabled" if enabled else "disabled",
                    timestamp,
                    timestamp,
                ),
            )
            _upsert_health(
                connection,
                system_id=values["system_id"],
                status="never_run" if enabled else "disabled",
                timestamp=timestamp,
                next_scheduled_run=next_analysis,
            )
            row = connection.execute(
                "SELECT * FROM live_analysis_configurations "
                "WHERE system_id = ? AND scope_storage_id = ?",
                (values["system_id"], _scope_id()),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        if "UNIQUE constraint failed" in str(error):
            raise LiveAnalysisConflictError(
                "A live-analysis configuration already exists for this system."
            ) from None
        raise
    if row is None:
        raise RuntimeError("live_analysis_configuration_insert_failed")
    return _config_payload(row)


def read_live_analysis_configuration(system_id: str) -> dict[str, Any]:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM live_analysis_configurations "
            "WHERE system_id = ? AND scope_storage_id = ?",
            (system_id, _scope_id()),
        ).fetchone()
    if row is None:
        raise LiveAnalysisNotFoundError("Live-analysis configuration not found.")
    return _config_payload(row)


def list_live_analysis_configurations(
    *,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    init_runtime_db()
    query = "SELECT * FROM live_analysis_configurations WHERE scope_storage_id = ?"
    params: tuple[Any, ...] = (_scope_id(),)
    if enabled is not None:
        query += " AND enabled = ?"
        params = (*params, 1 if enabled else 0)
    query += " ORDER BY system_id"
    with db_connection() as connection:
        rows = connection.execute(query, params).fetchall()
    return [_config_payload(row) for row in rows]


def update_live_analysis_configuration(
    system_id: str,
    updates: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    allowed = {
        "approved_baseline_id",
        "analysis_interval_seconds",
        "comparison_window_minutes",
        "minimum_coverage_percent",
        "allowed_lateness_minutes",
    }
    selected = {key: value for key, value in updates.items() if key in allowed}
    if not selected:
        raise ValueError("At least one live-analysis configuration field must be supplied.")
    timestamp = _iso((now or _now()).astimezone(UTC))
    assignments = [f"{key} = ?" for key in selected]
    params = [*selected.values(), timestamp, system_id, _scope_id()]
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        updated = connection.execute(
            f"""
            UPDATE live_analysis_configurations
            SET {', '.join(assignments)}, updated_at = ?, latest_error = NULL
            WHERE system_id = ? AND scope_storage_id = ?
            """,
            tuple(params),
        ).rowcount
        row = connection.execute(
            "SELECT * FROM live_analysis_configurations "
            "WHERE system_id = ? AND scope_storage_id = ?",
            (system_id, _scope_id()),
        ).fetchone()
    if not updated or row is None:
        raise LiveAnalysisNotFoundError("Live-analysis configuration not found.")
    return _config_payload(row)


def set_live_analysis_enabled(
    system_id: str,
    enabled: bool,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or _now()).astimezone(UTC)
    timestamp = _iso(current)
    next_analysis = timestamp if enabled else None
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        updated = connection.execute(
            """
            UPDATE live_analysis_configurations
            SET enabled = ?, current_status = ?, next_analysis_at = ?,
                latest_error = NULL, updated_at = ?
            WHERE system_id = ? AND scope_storage_id = ?
            """,
            (
                1 if enabled else 0,
                "enabled" if enabled else "disabled",
                next_analysis,
                timestamp,
                system_id,
                _scope_id(),
            ),
        ).rowcount
        if not updated:
            raise LiveAnalysisNotFoundError("Live-analysis configuration not found.")
        _upsert_health(
            connection,
            system_id=system_id,
            status="never_run" if enabled else "disabled",
            timestamp=timestamp,
            next_scheduled_run=next_analysis,
            preserve_history=True,
        )
        row = connection.execute(
            "SELECT * FROM live_analysis_configurations "
            "WHERE system_id = ? AND scope_storage_id = ?",
            (system_id, _scope_id()),
        ).fetchone()
    return _config_payload(row)


def _window_bounds(config: dict[str, Any], now: datetime) -> tuple[datetime, datetime]:
    watermark = now - timedelta(minutes=int(config["allowed_lateness_minutes"]))
    interval = int(config["analysis_interval_seconds"])
    bucket_epoch = int(watermark.timestamp()) // interval * interval
    window_end = datetime.fromtimestamp(bucket_epoch, UTC)
    window_start = window_end - timedelta(minutes=int(config["comparison_window_minutes"]))
    return window_start, window_end


def _next_analysis(config: dict[str, Any], now: datetime) -> str | None:
    if not config["enabled"]:
        return None
    return _iso(now + timedelta(seconds=int(config["analysis_interval_seconds"])))


def _upsert_health(
    connection: sqlite3.Connection,
    *,
    system_id: str,
    status: str,
    timestamp: str,
    coverage: float = 0.0,
    skipped_reason: str | None = None,
    latest_error: str | None = None,
    next_scheduled_run: str | None = None,
    attempted_at: str | None = None,
    completed_at: str | None = None,
    successful_at: str | None = None,
    failure_increment: bool = False,
    reset_failures: bool = False,
    preserve_history: bool = False,
) -> None:
    scope_storage_id = _scope_id()
    existing = connection.execute(
        "SELECT * FROM live_analysis_health "
        "WHERE system_id = ? AND scope_storage_id = ?",
        (system_id, scope_storage_id),
    ).fetchone()
    prior = dict(existing) if existing else {}
    failures = int(prior.get("consecutive_failures") or 0)
    if failure_increment:
        failures += 1
    elif reset_failures:
        failures = 0
    if preserve_history:
        attempted_at = attempted_at or prior.get("last_attempted_run_at")
        completed_at = completed_at or prior.get("last_completed_run_at")
        successful_at = successful_at or prior.get("last_successful_run_at")
    connection.execute(
        """
        INSERT INTO live_analysis_health (
            system_id, scope_storage_id, last_attempted_run_at, last_completed_run_at,
            last_successful_run_at, current_status, current_window_coverage,
            latest_skipped_reason, consecutive_failures, latest_error,
            next_scheduled_run, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scope_storage_id, system_id) DO UPDATE SET
            last_attempted_run_at = excluded.last_attempted_run_at,
            last_completed_run_at = excluded.last_completed_run_at,
            last_successful_run_at = excluded.last_successful_run_at,
            current_status = excluded.current_status,
            current_window_coverage = excluded.current_window_coverage,
            latest_skipped_reason = excluded.latest_skipped_reason,
            consecutive_failures = excluded.consecutive_failures,
            latest_error = excluded.latest_error,
            next_scheduled_run = excluded.next_scheduled_run,
            updated_at = excluded.updated_at
        """,
        (
            system_id,
            scope_storage_id,
            attempted_at if attempted_at is not None else prior.get("last_attempted_run_at"),
            completed_at if completed_at is not None else prior.get("last_completed_run_at"),
            successful_at if successful_at is not None else prior.get("last_successful_run_at"),
            status,
            max(0.0, min(100.0, float(coverage))),
            skipped_reason,
            failures,
            latest_error,
            next_scheduled_run,
            timestamp,
        ),
    )


def _create_or_reuse_run(
    config: dict[str, Any],
    *,
    window_start: datetime,
    window_end: datetime,
    now: datetime,
) -> tuple[dict[str, Any], bool]:
    timestamp = _iso(now)
    baseline_reference = str(config.get("approved_baseline_id") or "")
    start_iso, end_iso = _iso(window_start), _iso(window_end)
    run_id = f"live-run-{uuid.uuid4().hex}"
    next_analysis = _next_analysis(config, now)
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            """
            SELECT * FROM live_analysis_runs
            WHERE system_id = ? AND baseline_reference = ?
              AND window_start = ? AND window_end = ? AND scope_storage_id = ?
            """,
            (config["system_id"], baseline_reference, start_iso, end_iso, _scope_id()),
        ).fetchone()
        if existing:
            existing_status = str(existing["status"])
            health_status = {
                "completed": "healthy",
                "running": "running",
                "failed": "error",
            }.get(existing_status, "waiting_for_data")
            _upsert_health(
                connection,
                system_id=config["system_id"],
                status=health_status,
                timestamp=timestamp,
                coverage=float(existing["coverage"]),
                skipped_reason=(
                    "duplicate_window"
                    if existing_status in {"completed", "skipped"}
                    else existing["skipped_reason"]
                ),
                latest_error=existing["error_summary"],
                next_scheduled_run=next_analysis,
                preserve_history=True,
            )
            return _run_payload(existing), True

        running = connection.execute(
            """
            SELECT run_id FROM live_analysis_runs
            WHERE system_id = ? AND status = 'running' AND scope_storage_id = ?
            LIMIT 1
            """,
            (config["system_id"], _scope_id()),
        ).fetchone()
        initial_status = "skipped" if running else "pending"
        skipped_reason = "analysis_already_running" if running else None
        completed_at = timestamp if running else None
        connection.execute(
            """
            INSERT INTO live_analysis_runs (
                run_id, scope_storage_id, system_id, baseline_reference, window_start, window_end,
                status, started_at, completed_at, skipped_reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                _scope_id(),
                config["system_id"],
                baseline_reference,
                start_iso,
                end_iso,
                initial_status,
                timestamp,
                completed_at,
                skipped_reason,
                timestamp,
            ),
        )
        if running:
            _upsert_health(
                connection,
                system_id=config["system_id"],
                status="running",
                timestamp=timestamp,
                skipped_reason=skipped_reason,
                next_scheduled_run=next_analysis,
                attempted_at=timestamp,
                completed_at=timestamp,
                preserve_history=True,
            )
        row = connection.execute(
            "SELECT * FROM live_analysis_runs WHERE run_id = ? AND scope_storage_id = ?",
            (run_id, _scope_id()),
        ).fetchone()
    return _run_payload(row), bool(running)


def _skip_run(
    run_id: str,
    config: dict[str, Any],
    *,
    reason: str,
    now: datetime,
    coverage: float = 0.0,
    rows: int = 0,
    signals: int = 0,
) -> dict[str, Any]:
    if reason not in SKIPPED_REASONS:
        raise ValueError(f"Unsupported live-analysis skip reason: {reason}")
    timestamp = _iso(now)
    next_analysis = _next_analysis(config, now)
    health_status = {
        "disabled": "disabled",
        "missing_baseline": "missing_baseline",
        "telemetry_delayed": "delayed",
        "telemetry_unavailable": "waiting_for_data",
        "insufficient_coverage": "waiting_for_data",
        "insufficient_signals": "waiting_for_data",
        "duplicate_window": "waiting_for_data",
        "analysis_already_running": "running",
    }[reason]
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE live_analysis_runs
            SET status = 'skipped', completed_at = ?, rows_analyzed = ?,
                signals_analyzed = ?, coverage = ?, skipped_reason = ?
            WHERE run_id = ? AND status = 'pending' AND scope_storage_id = ?
            """,
            (timestamp, rows, signals, coverage, reason, run_id, _scope_id()),
        )
        connection.execute(
            """
            UPDATE live_analysis_configurations
            SET last_analysis_started_at = ?, last_analysis_completed_at = ?,
                next_analysis_at = ?, current_status = ?, updated_at = ?
            WHERE system_id = ? AND scope_storage_id = ?
            """,
            (
                timestamp,
                timestamp,
                next_analysis,
                "disabled" if reason == "disabled" else "waiting",
                timestamp,
                config["system_id"],
                _scope_id(),
            ),
        )
        _upsert_health(
            connection,
            system_id=config["system_id"],
            status=health_status,
            timestamp=timestamp,
            coverage=coverage,
            skipped_reason=reason,
            next_scheduled_run=next_analysis,
            attempted_at=timestamp,
            completed_at=timestamp,
            preserve_history=True,
        )
        row = connection.execute(
            "SELECT * FROM live_analysis_runs WHERE run_id = ? AND scope_storage_id = ?",
            (run_id, _scope_id()),
        ).fetchone()
    return _run_payload(row)


def _blocking_ingestion_reason(system_id: str) -> str | None:
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT status FROM telemetry_ingestion_health WHERE system_id = ?",
            (system_id,),
        ).fetchall()
    statuses = {str(row["status"]) for row in rows}
    if "healthy" in statuses:
        return None
    if "delayed" in statuses:
        return "telemetry_delayed"
    if statuses:
        return "telemetry_unavailable"
    return None


def _claim_run(run_id: str, config: dict[str, Any], now: datetime, coverage: float) -> bool:
    timestamp = _iso(now)
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            claimed = connection.execute(
                """
                UPDATE live_analysis_runs
                SET status = 'running', started_at = ?
                WHERE run_id = ? AND status = 'pending' AND scope_storage_id = ?
                """,
                (timestamp, run_id, _scope_id()),
            ).rowcount
        except sqlite3.IntegrityError:
            return False
        if not claimed:
            return False
        connection.execute(
            """
            UPDATE live_analysis_configurations
            SET current_status = 'running', last_analysis_started_at = ?,
                latest_error = NULL, updated_at = ?
            WHERE system_id = ? AND scope_storage_id = ?
            """,
            (timestamp, timestamp, config["system_id"], _scope_id()),
        )
        _upsert_health(
            connection,
            system_id=config["system_id"],
            status="running",
            timestamp=timestamp,
            coverage=coverage,
            attempted_at=timestamp,
            next_scheduled_run=config.get("next_analysis_at"),
            preserve_history=True,
        )
    return True


def _deduplication_key(system_id: str, baseline_reference: str, identity: str) -> str:
    material = "\0".join((_scope_id(), system_id, baseline_reference, identity)).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _finalize_findings(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    config: dict[str, Any],
    window: dict[str, Any],
    analytics: dict[str, Any],
    timestamp: str,
) -> tuple[int, int, int]:
    created = updated = resolved = 0
    system_id = str(config["system_id"])
    baseline_reference = str(config["approved_baseline_id"])
    for detection in analytics.get("detections", []):
        identity = str(detection["relationship_identity"])
        key = _deduplication_key(system_id, baseline_reference, identity)
        existing = connection.execute(
            "SELECT * FROM live_findings "
            "WHERE deduplication_key = ? AND scope_storage_id = ?",
            (key, _scope_id()),
        ).fetchone()
        persistence = detection.get("persistence") or {}
        persistent = persistence.get("persistent") is True
        observed_at = str(
            persistence.get("first_surfaced_at")
            or window["window_end"]
        )
        evidence_json = json.dumps(detection["latest_evidence"], separators=(",", ":"), default=str)
        classification_json = json.dumps(detection["classification"], separators=(",", ":"), default=str)
        persistence_json = json.dumps(persistence, separators=(",", ":"), default=str)
        if existing is None:
            state = "open" if persistent else "observing"
            finding_id = f"live-finding-{uuid.uuid4().hex}"
            connection.execute(
                """
                INSERT INTO live_findings (
                    finding_id, scope_storage_id, deduplication_key, system_id, relationship_identity,
                    finding_classification_json, first_detected_at, last_observed_at,
                    opened_at, resolved_at, current_state, persistence_state_json,
                    severity_score, latest_evidence_json,
                    source_live_analysis_run_id, baseline_reference,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding_id,
                    _scope_id(),
                    key,
                    system_id,
                    identity,
                    classification_json,
                    observed_at,
                    window["window_end"],
                    timestamp if persistent else None,
                    state,
                    persistence_json,
                    detection.get("severity_score"),
                    evidence_json,
                    run_id,
                    baseline_reference,
                    timestamp,
                    timestamp,
                ),
            )
            created += 1
            continue

        prior = dict(existing)
        state = str(prior["current_state"])
        opened_at = prior.get("opened_at")
        if persistent:
            state = "open"
            opened_at = opened_at or timestamp
        elif state != "open":
            state = "observing"
        connection.execute(
            """
            UPDATE live_findings
            SET finding_classification_json = ?, last_observed_at = ?,
                opened_at = ?, resolved_at = NULL, current_state = ?,
                persistence_state_json = ?, severity_score = ?,
                latest_evidence_json = ?, source_live_analysis_run_id = ?,
                updated_at = ?
            WHERE finding_id = ? AND scope_storage_id = ?
            """,
            (
                classification_json,
                window["window_end"],
                opened_at,
                state,
                persistence_json,
                detection.get("severity_score"),
                evidence_json,
                run_id,
                timestamp,
                prior["finding_id"],
                _scope_id(),
            ),
        )
        updated += 1

    aligned = set(analytics.get("baseline_aligned_relationships") or [])
    if aligned:
        placeholders = ",".join("?" for _ in aligned)
        rows = connection.execute(
            f"""
            SELECT finding_id FROM live_findings
            WHERE system_id = ? AND baseline_reference = ?
              AND scope_storage_id = ?
              AND current_state IN ('observing', 'open')
              AND relationship_identity IN ({placeholders})
            """,
            (system_id, baseline_reference, _scope_id(), *sorted(aligned)),
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                UPDATE live_findings
                SET current_state = 'resolved', resolved_at = ?,
                    source_live_analysis_run_id = ?, updated_at = ?
                WHERE finding_id = ? AND scope_storage_id = ?
                """,
                (timestamp, run_id, timestamp, row["finding_id"], _scope_id()),
            )
            resolved += 1
    return created, updated, resolved


def _complete_run(
    run_id: str,
    config: dict[str, Any],
    *,
    window: dict[str, Any],
    analytics: dict[str, Any],
    now: datetime,
) -> dict[str, Any]:
    timestamp = _iso(now)
    next_analysis = _next_analysis(config, now)
    analytics_json = json.dumps(analytics, separators=(",", ":"), default=str)
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        created, updated, resolved = _finalize_findings(
            connection,
            run_id=run_id,
            config=config,
            window=window,
            analytics=analytics,
            timestamp=timestamp,
        )
        connection.execute(
            """
            UPDATE live_analysis_runs
            SET status = 'completed', completed_at = ?, rows_analyzed = ?,
                signals_analyzed = ?, coverage = ?, skipped_reason = NULL,
                error_summary = NULL, analytics_result_reference = ?,
                analytics_result_json = ?, created_findings_count = ?,
                updated_findings_count = ?, resolved_findings_count = ?
            WHERE run_id = ? AND status = 'running' AND scope_storage_id = ?
            """,
            (
                timestamp,
                window["rows_included"],
                len(window["signals_included"]),
                window["overall_coverage"],
                f"live-analysis-result:{run_id}",
                analytics_json,
                created,
                updated,
                resolved,
                run_id,
                _scope_id(),
            ),
        )
        connection.execute(
            """
            UPDATE live_analysis_configurations
            SET last_analysis_completed_at = ?, next_analysis_at = ?,
                current_status = 'enabled', latest_error = NULL, updated_at = ?
            WHERE system_id = ? AND scope_storage_id = ?
            """,
            (timestamp, next_analysis, timestamp, config["system_id"], _scope_id()),
        )
        _upsert_health(
            connection,
            system_id=config["system_id"],
            status="healthy",
            timestamp=timestamp,
            coverage=window["overall_coverage"],
            next_scheduled_run=next_analysis,
            completed_at=timestamp,
            successful_at=timestamp,
            reset_failures=True,
            preserve_history=True,
        )
        row = connection.execute(
            "SELECT * FROM live_analysis_runs WHERE run_id = ? AND scope_storage_id = ?",
            (run_id, _scope_id()),
        ).fetchone()
    return _run_payload(row)


def _fail_run(
    run_id: str,
    config: dict[str, Any],
    *,
    error: Exception,
    now: datetime,
) -> dict[str, Any]:
    timestamp = _iso(now)
    next_analysis = _next_analysis(config, now)
    summary = f"Live analysis failed ({error.__class__.__name__})."
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE live_analysis_runs
            SET status = 'failed', completed_at = ?, error_summary = ?
            WHERE run_id = ? AND status IN ('pending', 'running') AND scope_storage_id = ?
            """,
            (timestamp, summary, run_id, _scope_id()),
        )
        connection.execute(
            """
            UPDATE live_analysis_configurations
            SET last_analysis_completed_at = ?, next_analysis_at = ?,
                current_status = 'error', latest_error = ?, updated_at = ?
            WHERE system_id = ? AND scope_storage_id = ?
            """,
            (timestamp, next_analysis, summary, timestamp, config["system_id"], _scope_id()),
        )
        _upsert_health(
            connection,
            system_id=config["system_id"],
            status="error",
            timestamp=timestamp,
            latest_error=summary,
            next_scheduled_run=next_analysis,
            completed_at=timestamp,
            failure_increment=True,
            preserve_history=True,
        )
        row = connection.execute(
            "SELECT * FROM live_analysis_runs WHERE run_id = ? AND scope_storage_id = ?",
            (run_id, _scope_id()),
        ).fetchone()
    return _run_payload(row)


def _prepare_analysis_window(
    *,
    system_id: str,
    config: dict[str, Any],
    baseline: dict[str, Any],
    window_start: datetime,
    window_end: datetime,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    baseline_signals = live_intelligence.approved_baseline_signals(baseline)
    window = build_rolling_window(
        system_id=system_id,
        window_start=window_start,
        window_end=window_end,
        minimum_coverage_percent=float(config["minimum_coverage_percent"]),
        eligible_signals=baseline_signals,
    )
    models = live_intelligence.analysis_ready_expected_models(
        baseline,
        window,
    )
    return window, models


def _recover_stale_active_run(
    config: dict[str, Any],
    *,
    now: datetime,
) -> bool:
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT run_id, status, started_at
            FROM live_analysis_runs
            WHERE system_id = ? AND status IN ('pending', 'running')
              AND scope_storage_id = ?
            ORDER BY created_at
            LIMIT 1
            """,
            (config["system_id"], _scope_id()),
        ).fetchone()
    if row is None:
        return False
    try:
        started_at = datetime.fromisoformat(str(row["started_at"]).replace("Z", "+00:00"))
        started_at = started_at.astimezone(UTC)
    except (TypeError, ValueError):
        started_at = datetime.min.replace(tzinfo=UTC)
    stale_seconds = max(
        MIN_STALE_ACTIVE_RUN_SECONDS,
        int(config["analysis_interval_seconds"]) * 2,
    )
    if started_at > now - timedelta(seconds=stale_seconds):
        return False

    timestamp = _iso(now)
    next_analysis = _next_analysis(config, now)
    summary = "Live analysis failed (WorkerRestartRecovery)."
    with db_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")
        updated = connection.execute(
            """
            UPDATE live_analysis_runs
            SET status = 'failed', completed_at = ?, error_summary = ?
            WHERE run_id = ? AND status IN ('pending', 'running') AND scope_storage_id = ?
            """,
            (timestamp, summary, row["run_id"], _scope_id()),
        ).rowcount
        if not updated:
            return False
        connection.execute(
            """
            UPDATE live_analysis_configurations
            SET last_analysis_completed_at = ?, next_analysis_at = ?,
                current_status = 'error', latest_error = ?, updated_at = ?
            WHERE system_id = ? AND scope_storage_id = ?
            """,
            (timestamp, next_analysis, summary, timestamp, config["system_id"], _scope_id()),
        )
        _upsert_health(
            connection,
            system_id=config["system_id"],
            status="error",
            timestamp=timestamp,
            latest_error=summary,
            next_scheduled_run=next_analysis,
            completed_at=timestamp,
            failure_increment=True,
            preserve_history=True,
        )
    logger.warning(
        "live_analysis_stale_run_recovered",
        extra={
            "event": "live_analysis_stale_run_recovered",
            "run_id": row["run_id"],
            "system_id": config["system_id"],
            "previous_status": row["status"],
        },
    )
    return True


def trigger_live_analysis(
    system_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    current = (now or _now()).astimezone(UTC)
    config = read_live_analysis_configuration(system_id)
    _recover_stale_active_run(config, now=current)
    config = read_live_analysis_configuration(system_id)
    window_start, window_end = _window_bounds(config, current)
    run, reused = _create_or_reuse_run(
        config,
        window_start=window_start,
        window_end=window_end,
        now=current,
    )
    if reused or run["status"] == "skipped":
        return run
    run_id = str(run["run_id"])

    if not config["enabled"]:
        return _skip_run(run_id, config, reason="disabled", now=current)

    baseline_reference = str(config.get("approved_baseline_id") or "")
    try:
        baseline = (
            behavioral_model_repository.read_model(baseline_reference)
            if baseline_reference
            else None
        )
    except Exception as error:
        logger.exception(
            "live_analysis_baseline_load_failed",
            extra={"event": "live_analysis_baseline_load_failed", "run_id": run_id, "system_id": system_id},
        )
        return _fail_run(run_id, config, error=error, now=current)
    if (
        not isinstance(baseline, dict)
        or baseline.get("status") != "active"
        or baseline.get("model_id") != baseline_reference
    ):
        return _skip_run(run_id, config, reason="missing_baseline", now=current)

    blocking_health = _blocking_ingestion_reason(system_id)
    if blocking_health:
        return _skip_run(run_id, config, reason=blocking_health, now=current)

    try:
        window, models = _prepare_analysis_window(
            system_id=system_id,
            config=config,
            baseline=baseline,
            window_start=window_start,
            window_end=window_end,
        )
    except Exception as error:
        logger.exception(
            "live_analysis_window_preparation_failed",
            extra={"event": "live_analysis_window_preparation_failed", "run_id": run_id, "system_id": system_id},
        )
        return _fail_run(run_id, config, error=error, now=current)
    if not window["rows_included"]:
        return _skip_run(
            run_id,
            config,
            reason="telemetry_unavailable",
            now=current,
        )
    if (
        window["overall_coverage"] < float(config["minimum_coverage_percent"])
        or window["rows_included"] < MIN_LIVE_ANALYSIS_ROWS
    ):
        return _skip_run(
            run_id,
            config,
            reason="insufficient_coverage",
            now=current,
            coverage=window["overall_coverage"],
            rows=window["rows_included"],
            signals=len(window["signals_included"]),
        )
    if len(window["signals_included"]) < 2 or not models:
        return _skip_run(
            run_id,
            config,
            reason="insufficient_signals",
            now=current,
            coverage=window["overall_coverage"],
            rows=window["rows_included"],
            signals=len(window["signals_included"]),
        )
    if not _claim_run(run_id, config, current, window["overall_coverage"]):
        return _skip_run(
            run_id,
            config,
            reason="analysis_already_running",
            now=current,
            coverage=window["overall_coverage"],
            rows=window["rows_included"],
            signals=len(window["signals_included"]),
        )

    try:
        analytics = live_intelligence.analyze_live_window(
            run_id=run_id,
            system_id=system_id,
            baseline=baseline,
            window=window,
        )
        return _complete_run(
            run_id,
            config,
            window=window,
            analytics=analytics,
            now=current,
        )
    except Exception as error:
        logger.exception(
            "live_analysis_failed",
            extra={
                "event": "live_analysis_failed",
                "run_id": run_id,
                "system_id": system_id,
                "error_type": error.__class__.__name__,
            },
        )
        return _fail_run(run_id, config, error=error, now=current)


def run_due_live_analyses(*, now: datetime | None = None) -> dict[str, Any]:
    current = (now or _now()).astimezone(UTC)
    timestamp = _iso(current)
    init_runtime_db()
    with db_connection() as connection:
        systems = [
            str(row["system_id"])
            for row in connection.execute(
                """
                SELECT system_id
                FROM live_analysis_configurations
                WHERE scope_storage_id = ? AND enabled = 1
                  AND (next_analysis_at IS NULL OR next_analysis_at <= ?)
                ORDER BY next_analysis_at, system_id
                """,
                (_scope_id(), timestamp),
            ).fetchall()
        ]

    results = []
    for system_id in systems:
        try:
            results.append(trigger_live_analysis(system_id, now=current))
        except Exception as error:
            logger.exception(
                "live_analysis_system_iteration_failed",
                extra={
                    "event": "live_analysis_system_iteration_failed",
                    "system_id": system_id,
                    "error_type": error.__class__.__name__,
                },
            )
            results.append(
                {
                    "system_id": system_id,
                    "status": "failed",
                    "error_summary": f"Live analysis iteration failed ({error.__class__.__name__}).",
                }
            )
    summary = {
        "attempted_systems": len(systems),
        "completed": sum(item.get("status") == "completed" for item in results),
        "skipped": sum(item.get("status") == "skipped" for item in results),
        "failed": sum(item.get("status") == "failed" for item in results),
        "results": results,
    }
    logger.info(
        "live_analysis_due_iteration_completed",
        extra={
            "event": "live_analysis_due_iteration_completed",
            **{key: summary[key] for key in ("attempted_systems", "completed", "skipped", "failed")},
        },
    )
    return summary


def list_live_analysis_runs(
    *,
    system_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    init_runtime_db()
    query = "SELECT * FROM live_analysis_runs WHERE scope_storage_id = ?"
    params: list[Any] = [_scope_id()]
    if system_id:
        query += " AND system_id = ?"
        params.append(system_id)
    query += " ORDER BY created_at DESC, run_id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with db_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return [_run_payload(row) for row in rows]


def read_live_analysis_run(run_id: str) -> dict[str, Any]:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM live_analysis_runs WHERE run_id = ? AND scope_storage_id = ?",
            (run_id, _scope_id()),
        ).fetchone()
    if row is None:
        raise LiveAnalysisNotFoundError("Live-analysis run not found.")
    return _run_payload(row)


def list_live_findings(
    *,
    system_id: str | None = None,
    state: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    init_runtime_db()
    conditions: list[str] = ["scope_storage_id = ?"]
    params: list[Any] = [_scope_id()]
    if system_id:
        conditions.append("system_id = ?")
        params.append(system_id)
    if state:
        conditions.append("current_state = ?")
        params.append(state)
    query = "SELECT * FROM live_findings"
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY last_observed_at DESC, finding_id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with db_connection() as connection:
        rows = connection.execute(query, tuple(params)).fetchall()
    return [_finding_payload(row) for row in rows]


def read_live_finding(finding_id: str) -> dict[str, Any]:
    init_runtime_db()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT * FROM live_findings WHERE finding_id = ? AND scope_storage_id = ?",
            (finding_id, _scope_id()),
        ).fetchone()
    if row is None:
        raise LiveAnalysisNotFoundError("Live finding not found.")
    return _finding_payload(row)


def list_live_analysis_health(
    *,
    system_id: str | None = None,
) -> list[dict[str, Any]]:
    init_runtime_db()
    query = "SELECT * FROM live_analysis_health WHERE scope_storage_id = ?"
    params: tuple[Any, ...] = (_scope_id(),)
    if system_id:
        query += " AND system_id = ?"
        params = (*params, system_id)
    query += " ORDER BY system_id"
    with db_connection() as connection:
        rows = [dict(row) for row in connection.execute(query, params).fetchall()]
    for row in rows:
        row.pop("scope_storage_id", None)
    if not rows and system_id:
        return [
            {
                "system_id": system_id,
                "last_attempted_run_at": None,
                "last_completed_run_at": None,
                "last_successful_run_at": None,
                "current_status": "never_run",
                "current_window_coverage": 0.0,
                "latest_skipped_reason": None,
                "consecutive_failures": 0,
                "latest_error": None,
                "next_scheduled_run": None,
                "updated_at": None,
            }
        ]
    return rows
