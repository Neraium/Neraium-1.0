from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services import live_analysis, live_intelligence
from app.services.auth_store import create_user
from app.services.live_windows import build_rolling_window
from app.services.runtime_db import db_connection, init_runtime_db


SYSTEM_ID = "resort-chilled-water"
BASELINE_ID = "bdm-v1-live"
NOW = datetime(2026, 8, 1, 12, 7, tzinfo=UTC)


def _baseline() -> dict[str, Any]:
    return {
        "model_id": BASELINE_ID,
        "status": "active",
        "telemetry_schema": {
            "numeric_columns": ["pump_power", "flow"],
            "signal_catalog": {},
        },
        "relationship_graph": {
            "edges": [
                {
                    "edge_id": "all_operation:pump_power:flow",
                    "mode_id": "all_operation",
                    "source": "pump_power",
                    "target": "flow",
                    "correlation": 1.0,
                }
            ]
        },
        "expected_behavior_models": [
            {
                "model_id": "expected:all_operation:pump_power:flow",
                "mode_id": "all_operation",
                "predictor": "pump_power",
                "response": "flow",
                "parameters": {"slope": 2.0, "intercept": 1.0},
                "training_samples": 80,
                "validation_samples": 20,
                "validation": {
                    "rmse": 0.1,
                    "mae": 0.08,
                    "r_squared": 0.99,
                    "accepted": True,
                },
            }
        ],
        "sensor_health": {"signals": []},
    }


def _insert_batch(
    *,
    system_id: str,
    source: str,
    values: list[tuple[datetime, str, float, str]],
    batch_id: str,
    ingested_at: datetime | None = None,
) -> None:
    init_runtime_db()
    received = (ingested_at or NOW).astimezone(UTC).isoformat()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO telemetry_ingestion_batches (
                batch_id, system_id, source, received_at, completed_at, result_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (batch_id, system_id, source, received, received, "{}"),
        )
        for timestamp, signal, value, quality in values:
            connection.execute(
                """
                INSERT INTO normalized_telemetry (
                    system_id, canonical_signal, telemetry_timestamp, value,
                    source, source_tag, quality_status, ingested_at, batch_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    system_id,
                    signal,
                    timestamp.astimezone(UTC).isoformat(),
                    value,
                    source,
                    f"tag-{signal}",
                    quality,
                    received,
                    batch_id,
                ),
            )


def _insert_changed_series(
    *,
    system_id: str = SYSTEM_ID,
    source: str = "historian-rest",
    batch_id: str = "batch-live",
) -> list[datetime]:
    timestamps = [datetime(2026, 8, 1, 11, 2, tzinfo=UTC) + timedelta(minutes=2 * index) for index in range(30)]
    values: list[tuple[datetime, str, float, str]] = []
    for index, timestamp in enumerate(timestamps, start=1):
        values.extend(
            [
                (timestamp, "pump_power", float(index), "good"),
                (timestamp, "flow", float(100 - 2 * index), "good"),
            ]
        )
    _insert_batch(
        system_id=system_id,
        source=source,
        values=values,
        batch_id=batch_id,
    )
    return timestamps


def _configuration(
    *,
    system_id: str = SYSTEM_ID,
    enabled: bool = True,
    baseline_id: str | None = BASELINE_ID,
    now: datetime = NOW,
    minimum_coverage_percent: float = 80,
) -> dict[str, Any]:
    return live_analysis.create_live_analysis_configuration(
        {
            "system_id": system_id,
            "enabled": enabled,
            "approved_baseline_id": baseline_id,
            "analysis_interval_seconds": 300,
            "comparison_window_minutes": 60,
            "minimum_coverage_percent": minimum_coverage_percent,
            "allowed_lateness_minutes": 5,
        },
        now=now,
    )


def _analytics(*, persistent: bool, aligned: bool = False) -> dict[str, Any]:
    if aligned:
        return {
            "evaluated_relationships": ["expected:all_operation:pump_power:flow"],
            "baseline_aligned_relationships": ["expected:all_operation:pump_power:flow"],
            "detections": [],
        }
    return {
        "evaluated_relationships": ["expected:all_operation:pump_power:flow"],
        "baseline_aligned_relationships": [],
        "detections": [
            {
                "relationship_identity": "expected:all_operation:pump_power:flow",
                "classification": {
                    "type": "unexplained_systemic_change",
                    "label": "Unexplained systemic change",
                },
                "persistence": {
                    "persistent": persistent,
                    "first_surfaced_at": "2026-08-01T11:02:00+00:00",
                    "support_fraction": 1.0 if persistent else 0.5,
                    "windows": [],
                },
                "severity_score": 72.5,
                "latest_evidence": {"evidence_id": "evidence-live"},
            }
        ],
    }


def test_window_builder_is_rectangular_ordered_deduplicated_and_quality_aware() -> None:
    timestamps = _insert_changed_series()
    _insert_batch(
        system_id=SYSTEM_ID,
        source="secondary-source",
        batch_id="batch-secondary",
        ingested_at=NOW + timedelta(seconds=1),
        values=[
            (timestamps[0], "pump_power", 999.0, "good"),
            (timestamps[1], "flow", 95.0, "out_of_order"),
            (timestamps[2], "outside_baseline", 1.0, "good"),
        ],
    )
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO rejected_telemetry (
                batch_id, system_id, source, source_tag, telemetry_timestamp,
                submitted_value_json, rejection_reason, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "batch-secondary",
                SYSTEM_ID,
                "secondary-source",
                "bad-tag",
                timestamps[3].isoformat(),
                json.dumps("bad"),
                "non_numeric_value",
                NOW.isoformat(),
            ),
        )

    result = build_rolling_window(
        system_id=SYSTEM_ID,
        window_start=datetime(2026, 8, 1, 11, 0, tzinfo=UTC),
        window_end=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        minimum_coverage_percent=80,
        eligible_signals={"pump_power", "flow"},
    )

    assert result["analysis_ready"] is True
    assert result["rows_included"] == 30
    assert result["signals_included"] == ["flow", "pump_power"]
    assert [row["timestamp"] for row in result["rows"]] == sorted(
        row["timestamp"] for row in result["rows"]
    )
    assert result["rows"][0]["pump_power"] == 999.0
    assert result["expected_rows"] == 31
    assert result["sampling_interval_seconds"] == 120.0
    assert result["coverage_by_signal"] == {"flow": 96.7742, "pump_power": 96.7742}
    assert result["overall_coverage"] == 96.7742
    assert result["exclusions"] == {
        "quarantined_values": 1,
        "duplicate_source_values": 2,
        "signals_not_in_approved_baseline": 1,
    }
    assert {
        "mildly_out_of_order_values_included",
        "duplicate_source_values_deduplicated",
        "quarantined_values_excluded",
        "signals_not_present_in_approved_baseline_excluded",
    } <= set(result["warnings"])


def test_window_builder_does_not_interpolate_and_reports_insufficient_coverage() -> None:
    timestamps = [datetime(2026, 8, 1, 11, 0, tzinfo=UTC) + timedelta(minutes=index) for index in range(18)]
    values = [(timestamp, "pump_power", float(index), "good") for index, timestamp in enumerate(timestamps)]
    values.extend(
        (timestamp, "flow", float(index * 2), "good")
        for index, timestamp in enumerate(timestamps[:9])
    )
    _insert_batch(
        system_id="sparse-system",
        source="historian-rest",
        batch_id="batch-sparse",
        values=values,
    )

    result = build_rolling_window(
        system_id="sparse-system",
        window_start=timestamps[0],
        window_end=timestamps[-1],
        minimum_coverage_percent=80,
    )

    assert result["rows_included"] == 18
    assert result["overall_coverage"] == 75.0
    assert result["coverage_by_signal"]["flow"] == 50.0
    assert result["rows"][-1]["flow"] is None
    assert result["analysis_ready"] is False


def test_readiness_skips_disabled_missing_baseline_delayed_and_unavailable(monkeypatch) -> None:
    _configuration(system_id="disabled-system", enabled=False)
    disabled = live_analysis.trigger_live_analysis("disabled-system", now=NOW)
    assert (disabled["status"], disabled["skipped_reason"]) == ("skipped", "disabled")

    _configuration(system_id="no-baseline", baseline_id=None)
    missing = live_analysis.trigger_live_analysis("no-baseline", now=NOW)
    assert (missing["status"], missing["skipped_reason"]) == ("skipped", "missing_baseline")

    _configuration(system_id="delayed-system")
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO telemetry_ingestion_health (
                system_id, source, accepted_count, rejected_count,
                latest_error_or_warning, status, updated_at
            ) VALUES (?, ?, 0, 1, ?, 'delayed', ?)
            """,
            ("delayed-system", "historian-rest", "late", NOW.isoformat()),
        )
    monkeypatch.setattr(
        live_analysis.behavioral_model_repository,
        "read_model",
        lambda model_id: _baseline(),
    )
    delayed = live_analysis.trigger_live_analysis("delayed-system", now=NOW)
    assert (delayed["status"], delayed["skipped_reason"]) == ("skipped", "telemetry_delayed")

    _configuration(system_id="empty-system")
    unavailable = live_analysis.trigger_live_analysis("empty-system", now=NOW)
    assert (unavailable["status"], unavailable["skipped_reason"]) == (
        "skipped",
        "telemetry_unavailable",
    )
    assert live_analysis.list_live_findings() == []


def test_insufficient_coverage_and_signals_do_not_call_analytics(monkeypatch) -> None:
    _configuration(system_id="short-system")
    timestamps = [datetime(2026, 8, 1, 11, 30, tzinfo=UTC) + timedelta(minutes=index) for index in range(10)]
    _insert_batch(
        system_id="short-system",
        source="historian-rest",
        batch_id="batch-short",
        values=[
            item
            for index, timestamp in enumerate(timestamps)
            for item in (
                (timestamp, "pump_power", float(index), "good"),
                (timestamp, "flow", float(index * 2), "good"),
            )
        ],
    )
    monkeypatch.setattr(
        live_analysis.behavioral_model_repository,
        "read_model",
        lambda model_id: _baseline(),
    )
    called = []
    monkeypatch.setattr(
        live_analysis.live_intelligence,
        "analyze_live_window",
        lambda **kwargs: called.append(kwargs),
    )
    result = live_analysis.trigger_live_analysis("short-system", now=NOW)
    assert result["skipped_reason"] == "insufficient_coverage"
    assert called == []

    _configuration(system_id="unusable-signals", minimum_coverage_percent=0)
    _insert_batch(
        system_id="unusable-signals",
        source="historian-rest",
        batch_id="batch-unusable",
        values=[
            item
            for index in range(20)
            for item in (
                (
                    datetime(2026, 8, 1, 11, 10, tzinfo=UTC) + timedelta(minutes=index),
                    "pump_power",
                    float(index),
                    "good",
                ),
                (
                    datetime(2026, 8, 1, 11, 10, tzinfo=UTC) + timedelta(minutes=index),
                    "flow",
                    1.0,
                    "good",
                ),
            )
        ],
    )
    unusable = live_analysis.trigger_live_analysis("unusable-signals", now=NOW)
    assert unusable["skipped_reason"] == "insufficient_signals"
    assert called == []


def test_existing_engine_scoring_classification_and_evidence_are_reused(monkeypatch) -> None:
    _configuration()
    _insert_changed_series()
    calls: list[str] = []

    monkeypatch.setattr(
        live_analysis.behavioral_model_repository,
        "read_model",
        lambda model_id: calls.append(f"baseline:{model_id}") or _baseline(),
    )
    original_relationship = live_intelligence.pilot_assessment.evaluate_relationship_against_baseline
    original_score = live_intelligence.relationship_baselines.score_relationship_importance
    original_classify = live_intelligence.finding_classification.classify_finding
    original_evidence = live_intelligence.upload_evidence.build_evidence_record_from_result

    def relationship(*args, **kwargs):
        calls.append("relationship_and_persistence")
        return original_relationship(*args, **kwargs)

    def score(*args, **kwargs):
        calls.append("score")
        return original_score(*args, **kwargs)

    def classify(*args, **kwargs):
        calls.append("classify")
        return original_classify(*args, **kwargs)

    def evidence(*args, **kwargs):
        calls.append("evidence")
        return original_evidence(*args, **kwargs)

    monkeypatch.setattr(
        live_intelligence.pilot_assessment,
        "evaluate_relationship_against_baseline",
        relationship,
    )
    monkeypatch.setattr(
        live_intelligence.relationship_baselines,
        "score_relationship_importance",
        score,
    )
    monkeypatch.setattr(
        live_intelligence.finding_classification,
        "classify_finding",
        classify,
    )
    monkeypatch.setattr(
        live_intelligence.upload_evidence,
        "build_evidence_record_from_result",
        evidence,
    )

    run = live_analysis.trigger_live_analysis(SYSTEM_ID, now=NOW)

    assert run["status"] == "completed"
    assert run["created_findings_count"] == 1
    assert {
        "relationship_and_persistence",
        "score",
        "classify",
        "evidence",
        f"baseline:{BASELINE_ID}",
    } <= set(calls)
    finding = live_analysis.list_live_findings(system_id=SYSTEM_ID)[0]
    assert finding["current_state"] == "open"
    assert finding["persistence_state"]["persistent"] is True
    assert finding["source_live_analysis_run_id"] == run["run_id"]
    assert live_analysis.list_live_analysis_health(system_id=SYSTEM_ID)[0]["current_status"] == "healthy"
    assert live_analysis.read_live_analysis_configuration(SYSTEM_ID)["next_analysis_at"] > NOW.isoformat()


def test_finding_lifecycle_observes_opens_updates_resolves_and_is_idempotent(monkeypatch) -> None:
    _configuration()
    _insert_changed_series()
    monkeypatch.setattr(
        live_analysis.behavioral_model_repository,
        "read_model",
        lambda model_id: _baseline(),
    )
    monkeypatch.setattr(
        live_analysis.live_intelligence,
        "analyze_live_window",
        lambda **kwargs: _analytics(persistent=False),
    )

    observing_run = live_analysis.trigger_live_analysis(SYSTEM_ID, now=NOW)
    finding = live_analysis.list_live_findings(system_id=SYSTEM_ID)[0]
    assert finding["current_state"] == "observing"
    assert finding["opened_at"] is None

    duplicate = live_analysis.trigger_live_analysis(SYSTEM_ID, now=NOW)
    assert duplicate["run_id"] == observing_run["run_id"]
    assert len(live_analysis.list_live_analysis_runs(system_id=SYSTEM_ID)) == 1
    assert len(live_analysis.list_live_findings(system_id=SYSTEM_ID)) == 1

    monkeypatch.setattr(
        live_analysis.live_intelligence,
        "analyze_live_window",
        lambda **kwargs: _analytics(persistent=True),
    )
    opened_run = live_analysis.trigger_live_analysis(
        SYSTEM_ID,
        now=NOW + timedelta(minutes=5),
    )
    opened = live_analysis.list_live_findings(system_id=SYSTEM_ID)[0]
    assert opened_run["updated_findings_count"] == 1
    assert opened["current_state"] == "open"
    assert opened["opened_at"] is not None
    assert opened["last_observed_at"] == opened_run["window_end"]

    missing = live_analysis.trigger_live_analysis(
        SYSTEM_ID,
        now=NOW + timedelta(hours=3),
    )
    assert missing["status"] == "skipped"
    assert live_analysis.list_live_findings(system_id=SYSTEM_ID)[0]["current_state"] == "open"

    monkeypatch.setattr(
        live_analysis.live_intelligence,
        "analyze_live_window",
        lambda **kwargs: _analytics(persistent=False, aligned=True),
    )
    resolved_run = live_analysis.trigger_live_analysis(
        SYSTEM_ID,
        now=NOW + timedelta(minutes=10),
    )
    resolved = live_analysis.list_live_findings(system_id=SYSTEM_ID)[0]
    assert resolved_run["resolved_findings_count"] == 1
    assert resolved["current_state"] == "resolved"
    assert resolved["resolved_at"] is not None
    assert len(live_analysis.list_live_findings(system_id=SYSTEM_ID)) == 1


def test_analytics_failure_is_auditable_and_creates_no_half_open_finding(monkeypatch) -> None:
    _configuration()
    _insert_changed_series()
    monkeypatch.setattr(
        live_analysis.behavioral_model_repository,
        "read_model",
        lambda model_id: _baseline(),
    )

    def fail(**kwargs):
        raise RuntimeError("payload must not be exposed")

    monkeypatch.setattr(live_analysis.live_intelligence, "analyze_live_window", fail)
    run = live_analysis.trigger_live_analysis(SYSTEM_ID, now=NOW)

    assert run["status"] == "failed"
    assert run["error_summary"] == "Live analysis failed (RuntimeError)."
    assert "payload" not in run["error_summary"]
    assert live_analysis.list_live_findings(system_id=SYSTEM_ID) == []
    health = live_analysis.list_live_analysis_health(system_id=SYSTEM_ID)[0]
    assert health["current_status"] == "error"
    assert health["consecutive_failures"] == 1


def test_duplicate_window_and_concurrent_claim_are_prevented(monkeypatch) -> None:
    _configuration()
    _insert_changed_series()
    monkeypatch.setattr(
        live_analysis.behavioral_model_repository,
        "read_model",
        lambda model_id: _baseline(),
    )
    monkeypatch.setattr(
        live_analysis.live_intelligence,
        "analyze_live_window",
        lambda **kwargs: _analytics(persistent=False),
    )
    first = live_analysis.trigger_live_analysis(SYSTEM_ID, now=NOW)
    retry = live_analysis.trigger_live_analysis(SYSTEM_ID, now=NOW)
    assert retry["run_id"] == first["run_id"]

    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO live_analysis_runs (
                run_id, system_id, baseline_reference, window_start, window_end,
                status, started_at, created_at
            ) VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (
                "live-run-active",
                SYSTEM_ID,
                BASELINE_ID,
                "2026-08-01T10:00:00+00:00",
                "2026-08-01T10:30:00+00:00",
                NOW.isoformat(),
                NOW.isoformat(),
            ),
        )

    concurrent = live_analysis.trigger_live_analysis(
        SYSTEM_ID,
        now=NOW + timedelta(minutes=5),
    )
    assert concurrent["status"] == "skipped"
    assert concurrent["skipped_reason"] == "analysis_already_running"


def test_due_worker_selects_only_due_enabled_and_continues_after_system_failure(monkeypatch) -> None:
    _configuration(system_id="system-a")
    _configuration(system_id="system-b")
    _configuration(system_id="system-disabled", enabled=False)
    with db_connection() as connection:
        connection.execute(
            "UPDATE live_analysis_configurations SET next_analysis_at = ? WHERE system_id = ?",
            ((NOW + timedelta(hours=1)).isoformat(), "system-b"),
        )

    selected: list[str] = []

    def trigger(system_id: str, *, now: datetime):
        selected.append(system_id)
        if system_id == "system-a":
            raise RuntimeError("system failed")
        return {"system_id": system_id, "status": "completed"}

    monkeypatch.setattr(live_analysis, "trigger_live_analysis", trigger)
    summary = live_analysis.run_due_live_analyses(now=NOW)
    assert selected == ["system-a"]
    assert summary == {
        "attempted_systems": 1,
        "completed": 0,
        "skipped": 0,
        "failed": 1,
        "results": [
            {
                "system_id": "system-a",
                "status": "failed",
                "error_summary": "Live analysis iteration failed (RuntimeError).",
            }
        ],
    }

    with db_connection() as connection:
        connection.execute(
            "UPDATE live_analysis_configurations SET next_analysis_at = ? WHERE system_id = ?",
            (NOW.isoformat(), "system-b"),
        )
    summary = live_analysis.run_due_live_analyses(now=NOW)
    assert selected[-2:] == ["system-a", "system-b"]
    assert summary["attempted_systems"] == 2
    assert summary["completed"] == 1
    assert summary["failed"] == 1


def test_live_analysis_api_crud_manual_run_lists_and_health(client: TestClient, monkeypatch) -> None:
    created = client.post(
        "/api/live-analysis/configurations",
        json={
            "system_id": SYSTEM_ID,
            "enabled": False,
            "approved_baseline_id": BASELINE_ID,
        },
    )
    assert created.status_code == 201
    assert created.json()["analysis_interval_seconds"] == 300

    listed = client.get("/api/live-analysis/configurations")
    assert listed.status_code == 200
    assert listed.json()["configurations"][0]["system_id"] == SYSTEM_ID

    updated = client.put(
        f"/api/live-analysis/configurations/{SYSTEM_ID}",
        json={"comparison_window_minutes": 90, "minimum_coverage_percent": 85},
    )
    assert updated.status_code == 200
    assert updated.json()["comparison_window_minutes"] == 90

    assert client.post(
        f"/api/live-analysis/configurations/{SYSTEM_ID}/enable"
    ).json()["enabled"] is True
    assert client.post(
        f"/api/live-analysis/configurations/{SYSTEM_ID}/disable"
    ).json()["enabled"] is False

    run = client.post(f"/api/live-analysis/systems/{SYSTEM_ID}/runs")
    assert run.status_code == 200
    assert run.json()["skipped_reason"] == "disabled"
    run_id = run.json()["run_id"]
    assert client.get("/api/live-analysis/runs").json()["runs"][0]["run_id"] == run_id
    assert client.get(f"/api/live-analysis/runs/{run_id}").status_code == 200
    assert client.get("/api/live-analysis/findings").json() == {"findings": []}
    health = client.get(
        "/api/live-analysis/health",
        params={"system_id": SYSTEM_ID},
    )
    assert health.status_code == 200
    assert health.json()["health"][0]["current_status"] == "disabled"


def test_live_analysis_api_authorization_follows_existing_roles(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.neraium.com")
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    settings = Settings(
        app_env="production",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["https://app.neraium.com"],
        runtime_dir=tmp_path,
    )
    with TestClient(create_app(settings), base_url="https://testserver") as production_client:
        assert production_client.get("/api/live-analysis/configurations").status_code == 401

        create_user("viewer-live@example.com", "password123", role="viewer")
        assert production_client.post(
            "/api/auth/login",
            json={"email": "viewer-live@example.com", "password": "password123"},
        ).status_code == 200
        assert production_client.get("/api/live-analysis/configurations").status_code == 200
        assert production_client.post(
            "/api/live-analysis/configurations",
            json={"system_id": SYSTEM_ID},
        ).status_code == 403
        assert production_client.post(
            f"/api/live-analysis/systems/{SYSTEM_ID}/runs"
        ).status_code == 403

        create_user("operator-live@example.com", "password123", role="operator")
        assert production_client.post(
            "/api/auth/login",
            json={"email": "operator-live@example.com", "password": "password123"},
        ).status_code == 200
        assert production_client.post(
            "/api/live-analysis/configurations",
            json={"system_id": SYSTEM_ID},
        ).status_code == 403
        assert production_client.post(
            f"/api/live-analysis/systems/{SYSTEM_ID}/runs"
        ).status_code == 404

        create_user("admin-live@example.com", "password123", role="admin")
        assert production_client.post(
            "/api/auth/login",
            json={"email": "admin-live@example.com", "password": "password123"},
        ).status_code == 200
        assert production_client.post(
            "/api/live-analysis/configurations",
            json={"system_id": SYSTEM_ID},
        ).status_code == 201
        assert production_client.post(
            f"/api/live-analysis/systems/{SYSTEM_ID}/runs"
        ).status_code == 200


def test_baseline_and_window_preparation_failures_are_durable(monkeypatch) -> None:
    _configuration(system_id="baseline-error")
    monkeypatch.setattr(
        live_analysis.behavioral_model_repository,
        "read_model",
        lambda model_id: (_ for _ in ()).throw(OSError("secret storage detail")),
    )
    baseline_failure = live_analysis.trigger_live_analysis("baseline-error", now=NOW)
    assert baseline_failure["status"] == "failed"
    assert baseline_failure["error_summary"] == "Live analysis failed (OSError)."

    _configuration(system_id="window-error")
    monkeypatch.setattr(
        live_analysis.behavioral_model_repository,
        "read_model",
        lambda model_id: _baseline(),
    )
    monkeypatch.setattr(
        live_analysis,
        "_prepare_analysis_window",
        lambda **kwargs: (_ for _ in ()).throw(ValueError("malformed private row")),
    )
    window_failure = live_analysis.trigger_live_analysis("window-error", now=NOW)
    assert window_failure["status"] == "failed"
    assert window_failure["error_summary"] == "Live analysis failed (ValueError)."
    assert live_analysis.list_live_findings() == []


def test_stale_active_run_is_failed_after_worker_restart() -> None:
    config = _configuration(system_id="restart-system")
    stale_start = NOW - timedelta(minutes=30)
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO live_analysis_runs (
                run_id, system_id, baseline_reference, window_start, window_end,
                status, started_at, created_at
            ) VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
            """,
            (
                "live-run-stale",
                "restart-system",
                BASELINE_ID,
                "2026-08-01T10:00:00+00:00",
                "2026-08-01T10:30:00+00:00",
                stale_start.isoformat(),
                stale_start.isoformat(),
            ),
        )

    assert live_analysis._recover_stale_active_run(config, now=NOW) is True
    recovered = live_analysis.read_live_analysis_run("live-run-stale")
    assert recovered["status"] == "failed"
    assert recovered["error_summary"] == "Live analysis failed (WorkerRestartRecovery)."
    health = live_analysis.list_live_analysis_health(system_id="restart-system")[0]
    assert health["current_status"] == "error"
    assert health["consecutive_failures"] == 1


def test_window_builder_requires_timezone_aware_bounds() -> None:
    naive = datetime(2026, 8, 1, 11, 0)
    try:
        build_rolling_window(
            system_id=SYSTEM_ID,
            window_start=naive,
            window_end=naive + timedelta(hours=1),
            minimum_coverage_percent=80,
        )
    except ValueError as error:
        assert str(error) == "window_start must be timezone-aware"
    else:
        raise AssertionError("naive rolling-window bounds must be rejected")
