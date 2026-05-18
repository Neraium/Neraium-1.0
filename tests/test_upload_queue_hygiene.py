from app.main import create_app
from app.services.runtime_db import clear_stale_processing_queue_jobs, db_connection, enqueue_upload_job, init_runtime_db
from app.services.upload_jobs import process_next_queued_upload_job, read_job, write_job
from fastapi.testclient import TestClient


def test_clear_stale_processing_queue_jobs_marks_processing_as_failed() -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO upload_queue (job_id, status, attempts, last_error, created_at, updated_at, locked_at)
            VALUES ('stale-job', 'processing', 1, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """
        )

    recovered = clear_stale_processing_queue_jobs()
    assert recovered >= 1

    with db_connection() as connection:
        row = connection.execute("SELECT status, last_error FROM upload_queue WHERE job_id='stale-job'").fetchone()
    assert row is not None
    assert row["status"] == "failed"
    assert row["last_error"] == "stale_processing_job_recovered"


def test_process_next_queued_upload_job_marks_missing_file_failed() -> None:
    with db_connection() as connection:
        connection.execute("DELETE FROM upload_queue")
    job_id = "missing-file-job"
    write_job(
        {
            "job_id": job_id,
            "filename": "missing.csv",
            "file_path": "C:/path/does/not/exist.csv",
            "file_size_bytes": 10,
            "status": "PENDING",
            "progress_label": "queued",
            "started_at": "2026-01-01T00:00:00+00:00",
        }
    )
    enqueue_upload_job(job_id)
    process_next_queued_upload_job()
    metadata = read_job(job_id)
    assert metadata is not None
    # Queue status is source-of-truth for dispatch hygiene.
    with db_connection() as connection:
        row = connection.execute("SELECT status, last_error FROM upload_queue WHERE job_id = ?", (job_id,)).fetchone()
    assert row is not None
    assert row["status"] == "failed"
    assert row["last_error"] == "missing_upload_file"


def test_startup_recovers_stale_processing_jobs() -> None:
    init_runtime_db()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO upload_queue (job_id, status, attempts, last_error, created_at, updated_at, locked_at)
            VALUES ('startup-stale-job', 'processing', 1, NULL, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')
            """
        )
    with TestClient(create_app()) as _client:
        pass
    with db_connection() as connection:
        row = connection.execute("SELECT status, last_error FROM upload_queue WHERE job_id='startup-stale-job'").fetchone()
    assert row is not None
    assert row["status"] == "failed"
    assert row["last_error"] == "stale_processing_job_recovered"
