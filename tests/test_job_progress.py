from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import upload_jobs
from app.services.dataset_scope import build_dataset_scope, set_current_dataset_scope
from app.services.job_progress import (
    ProgressReporter,
    complete_progress,
    enrich_progress_timing,
    fail_progress,
    initialize_progress,
    retry_progress,
    update_progress,
)
from app.services.runtime_db import claim_next_upload_job
from app.services.upload_session_service import resolve_upload_status


UTC = timezone.utc


def _operation(progress: dict, operation_id: str) -> dict:
    return next(item for item in progress["operations"] if item["id"] == operation_id)


def test_indeterminate_progress_never_invents_an_operation_percentage() -> None:
    started = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    progress = initialize_progress(
        job_id="indeterminate-job",
        workflow="create_baseline",
        started_at=started.isoformat(),
    )

    progress = update_progress(
        progress,
        job_id="indeterminate-job",
        workflow="create_baseline",
        stage="validate",
        substage="parse_source",
        completed_units=5_000,
        total_units=None,
        unit_type="rows",
        message="Parsed 5,000 rows; discovering the source total.",
        observed_at=started + timedelta(seconds=4),
    )

    assert progress["completed_units"] == 5_000
    assert progress["total_units"] is None
    assert progress["percent_complete"] is None
    assert _operation(progress, "parse_source")["percent_complete"] is None
    assert progress["overall_percent_complete"] == 9


def test_measurable_progress_is_exact_bounded_and_monotonic() -> None:
    progress = update_progress(
        None,
        job_id="measurable-job",
        workflow="create_baseline",
        stage="validate",
        substage="timestamp_quality",
        completed_units=62,
        total_units=100,
        unit_type="rows",
        message="Checked 62 of 100 timestamps.",
    )
    assert progress["percent_complete"] == 62

    progress = update_progress(
        progress,
        job_id="measurable-job",
        workflow="create_baseline",
        stage="validate",
        substage="timestamp_quality",
        completed_units=40,
        total_units=100,
        unit_type="rows",
        message="A late counter update arrived.",
    )
    assert progress["completed_units"] == 62
    assert progress["percent_complete"] == 62

    progress = update_progress(
        progress,
        job_id="measurable-job",
        workflow="create_baseline",
        stage="validate",
        substage="timestamp_quality",
        completed_units=120,
        total_units=100,
        unit_type="rows",
        message="Timestamp checks complete.",
    )
    assert progress["completed_units"] == 100
    assert progress["percent_complete"] == 100

    progress = update_progress(
        progress,
        job_id="measurable-job",
        workflow="create_baseline",
        stage="validate",
        substage="timestamp_quality",
        completed_units=100,
        total_units=500,
        unit_type="rows",
        message="A conflicting total arrived late.",
    )
    assert progress["total_units"] == 100
    assert progress["percent_complete"] == 100


def test_late_callback_cannot_move_progress_back_to_an_earlier_substage() -> None:
    progress = update_progress(
        None,
        job_id="ordered-job",
        workflow="create_baseline",
        stage="validate",
        substage="semantic_mapping",
        completed_units=3,
        total_units=10,
        unit_type="signals",
        message="Mapping signals.",
    )
    unchanged = update_progress(
        progress,
        job_id="ordered-job",
        workflow="create_baseline",
        stage="validate",
        substage="parse_source",
        completed_units=1,
        total_units=1,
        unit_type="rows",
        message="Late parse callback.",
    )

    assert unchanged["substage"] == "semantic_mapping"
    assert unchanged["overall_percent_complete"] == progress["overall_percent_complete"]


def test_failure_preserves_completed_work_and_retry_records_attempt_lineage() -> None:
    progress = update_progress(
        None,
        job_id="recovery-job",
        workflow="create_baseline",
        stage="learn",
        substage="learn_relationships",
        completed_units=45,
        total_units=100,
        unit_type="relationship_pairs",
        message="Learning relationships.",
    )
    failed = fail_progress(
        progress,
        job_id="recovery-job",
        workflow="create_baseline",
        message="Relationship learning could not continue.",
        retryable=True,
    )

    assert failed["status"] == "failed"
    assert failed["overall_percent_complete"] == progress["overall_percent_complete"]
    assert failed["completed_units"] == 45
    assert failed["percent_complete"] == 45
    assert failed["retryable"] is True
    assert _operation(failed, "learn_relationships")["status"] == "failed"
    assert _operation(failed, "compute_baseline_statistics")["status"] == "completed"

    retried = retry_progress(
        failed,
        job_id="recovery-job",
        workflow="create_baseline",
        message="Retry queued.",
    )
    assert retried["status"] == "queued"
    assert retried["metadata"]["retry_count"] == 1
    assert retried["metadata"]["previous_attempt_failed_substage"] == "learn_relationships"
    assert "compute_baseline_statistics" in retried["metadata"]["previous_attempt_completed_operations"]


def test_terminal_completion_is_exactly_one_hundred_percent() -> None:
    progress = complete_progress(
        initialize_progress(job_id="complete-job", workflow="create_baseline"),
        job_id="complete-job",
        workflow="create_baseline",
        message="Baseline ready.",
    )

    assert progress["status"] == "completed"
    assert progress["overall_percent_complete"] == 100
    assert all(item["status"] == "completed" for item in progress["operations"])


def test_stall_detection_is_visibility_only(monkeypatch) -> None:
    monkeypatch.setenv("NERAIUM_PROGRESS_STALL_SECONDS", "120")
    started = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    progress = initialize_progress(
        job_id="stalled-progress",
        workflow="create_baseline",
        started_at=started.isoformat(),
    )
    progress["updated_at"] = started.isoformat()
    stalled = enrich_progress_timing(progress, observed_at=started + timedelta(seconds=121))

    assert stalled["stalled"] is True
    assert stalled["seconds_since_update"] == 121
    assert stalled["status"] == "queued"


def test_progress_reporter_throttles_large_dataset_counter_updates() -> None:
    clock = [10.0]
    writes: list[dict] = []

    def persist(**values):
        writes.append(values)
        return values

    reporter = ProgressReporter(
        job_id="large-job",
        workflow="create_baseline",
        persist=persist,
        minimum_interval_seconds=2,
        monotonic=lambda: clock[0],
    )
    for completed in range(0, 100_001, 5_000):
        reporter.report(
            stage="validate",
            substage="parse_source",
            completed_units=completed,
            total_units=100_000,
            unit_type="rows",
            message="Parsing rows.",
        )
        clock[0] += 0.05

    assert reporter.write_count == 1
    clock[0] += 2
    reporter.report(
        stage="validate",
        substage="parse_source",
        completed_units=100_000,
        total_units=100_000,
        unit_type="rows",
        message="Parsing rows.",
    )
    assert reporter.write_count == 2


def test_progress_persists_across_reads_and_get_is_pure(monkeypatch) -> None:
    job_id = "persisted-progress"
    upload_jobs.write_job({
        "job_id": job_id,
        "filename": "history.csv",
        "workflow": "create_baseline",
        "status": "PROCESSING",
        "processing_state": "parsing_telemetry",
        "message": "Parsing rows.",
    })
    upload_jobs._persist_job_progress(
        job_id=job_id,
        workflow="create_baseline",
        stage="validate",
        substage="parse_source",
        completed_units=250,
        total_units=1_000,
        unit_type="rows",
        message="Parsed 250 of 1,000 rows.",
    )
    persisted = upload_jobs.read_upload_status(job_id)
    assert persisted["job_progress"]["completed_units"] == 250

    monkeypatch.setattr(
        "app.services.upload_state_repository.write_upload_status_progress",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("GET wrote progress state")),
    )
    response = TestClient(create_app()).get(f"/api/data/upload-status/{job_id}")

    assert response.status_code == 200
    assert response.json()["job_progress"]["completed_units"] == 250


def test_queue_claim_state_is_authoritative_and_non_contradictory() -> None:
    job_id = "queue-authority"
    upload_jobs.write_job({
        "job_id": job_id,
        "filename": "queued.csv",
        "workflow": "legacy_analysis",
        "status": "PENDING",
        "processing_state": "queued",
        "message": "Waiting for a worker.",
    })
    upload_jobs.enqueue_upload_job(job_id)

    queued = resolve_upload_status(job_id)
    assert queued["execution_state"] == "queued"
    assert queued["worker_state"] == "queued"
    assert queued["worker_claimed"] is False
    assert queued["job_progress"]["last_worker_heartbeat_at"] is None

    assert claim_next_upload_job() == job_id
    upload_jobs._persist_job_progress(
        job_id=job_id,
        workflow="legacy_analysis",
        stage="validate",
        substage="parse_source",
        completed_units=10,
        total_units=100,
        unit_type="rows",
        message="Parsed 10 of 100 rows.",
    )
    persisted = upload_jobs.read_upload_status(job_id)
    claimed = resolve_upload_status(job_id)
    assert claimed["execution_state"] == "processing"
    assert claimed["worker_state"] == "running"
    assert datetime.fromisoformat(claimed["worker_last_seen_at"]) >= datetime.fromisoformat(persisted["worker_last_seen_at"])
    assert claimed["job_progress"]["last_worker_heartbeat_at"] == claimed["worker_last_seen_at"]

    upload_jobs.write_job({
        **persisted,
        "status": "COMPLETE",
        "processing_state": "complete",
        "message": "Baseline ready.",
    })
    terminal = resolve_upload_status(job_id)
    assert terminal["execution_state"] == "completed"
    assert terminal["worker_state"] == "idle"
    assert terminal["job_progress"]["last_worker_heartbeat_at"]


def test_progress_isolated_by_tenant_and_workspace_even_for_same_job_id() -> None:
    job_id = "shared-job-id"
    tenant_a = build_dataset_scope(user_id="operator-a", tenant_id="tenant-a", workspace_id="plant-a")
    tenant_b = build_dataset_scope(user_id="operator-b", tenant_id="tenant-b", workspace_id="plant-b")

    set_current_dataset_scope(tenant_a)
    upload_jobs.write_job({
        "job_id": job_id,
        "filename": "tenant-a.csv",
        "workflow": "create_baseline",
        "status": "PROCESSING",
        "processing_state": "parsing_telemetry",
        "message": "Tenant A progress.",
    })

    set_current_dataset_scope(tenant_b)
    assert resolve_upload_status(job_id)["status"] == "NOT_FOUND"
    upload_jobs.write_job({
        "job_id": job_id,
        "filename": "tenant-b.csv",
        "workflow": "create_baseline",
        "status": "PENDING",
        "processing_state": "queued",
        "message": "Tenant B queued.",
    })
    assert upload_jobs.read_upload_status(job_id)["filename"] == "tenant-b.csv"

    set_current_dataset_scope(tenant_a)
    assert upload_jobs.read_upload_status(job_id)["filename"] == "tenant-a.csv"
