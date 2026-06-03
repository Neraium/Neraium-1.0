from app.main import create_app
from app.services.runtime_db import claim_next_upload_job, clear_stale_processing_queue_jobs, db_connection, enqueue_upload_job, init_runtime_db, queue_metrics, read_upload_queue_job
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


class _FakeS3Body:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


class _FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str | None = None) -> None:
        self.objects[(Bucket, Key)] = Body

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, _FakeS3Body]:
        payload = self.objects[(Bucket, Key)]
        return {"Body": _FakeS3Body(payload)}

    def list_objects_v2(self, *, Bucket: str, Prefix: str, ContinuationToken: str | None = None) -> dict[str, object]:
        contents = [
            {"Key": key}
            for bucket, key in sorted(self.objects)
            if bucket == Bucket and key.startswith(Prefix)
        ]
        return {"Contents": contents, "IsTruncated": False}


def test_shared_upload_queue_backend_allows_api_enqueue_and_worker_claim(monkeypatch) -> None:
    fake_s3 = _FakeS3Client()
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "api")
    monkeypatch.setenv("NERAIUM_UPLOAD_STATE_BUCKET", "shared-upload-state")
    monkeypatch.setattr("app.services.runtime_db._get_s3_client", lambda: fake_s3)

    enqueue_upload_job("shared-queue-job")

    queued = read_upload_queue_job("shared-queue-job")
    assert queued is not None
    assert queued["status"] == "pending"
    assert queued["queue_position"] == 1

    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "worker")
    claimed_job_id = claim_next_upload_job()

    assert claimed_job_id == "shared-queue-job"

    claimed = read_upload_queue_job("shared-queue-job")
    assert claimed is not None
    assert claimed["status"] == "processing"
    assert claimed["attempts"] == 1
    assert queue_metrics() == {"pending": 0, "processing": 1, "completed": 0, "failed": 0}
