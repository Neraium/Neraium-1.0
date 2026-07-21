from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.core.path_safety import resolve_existing_storage_path
from app.main import create_app
from app.routers import data as data_router
from app.services import upload_jobs


def test_duplicate_upload_filenames_use_distinct_server_storage_keys(monkeypatch) -> None:
    monkeypatch.setattr(data_router, "_dispatch_upload_worker_for_runtime", lambda runtime_dir: None)
    client = TestClient(create_app())
    csv_content = "timestamp,room,temperature\n2026-05-01T08:00:00Z,Flower,75\n"

    first = client.post("/api/data/upload", files={"file": ("same.csv", csv_content, "text/csv")})
    second = client.post("/api/data/upload", files={"file": ("same.csv", csv_content, "text/csv")})

    assert first.status_code == 202
    assert second.status_code == 202
    first_status = upload_jobs.read_upload_status(first.json()["job_id"]) or {}
    second_status = upload_jobs.read_upload_status(second.json()["job_id"]) or {}
    first_key = str(first_status.get("file_path") or "")
    second_key = str(second_status.get("file_path") or "")

    assert first_key
    assert second_key
    assert first_key != second_key
    assert not Path(first_key).is_absolute()
    assert not Path(second_key).is_absolute()
    assert "same.csv" not in first_key
    assert "same.csv" not in second_key
    assert resolve_existing_storage_path(upload_jobs.UPLOAD_DIR, first_key).exists()
    assert resolve_existing_storage_path(upload_jobs.UPLOAD_DIR, second_key).exists()
