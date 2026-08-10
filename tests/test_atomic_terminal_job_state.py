from __future__ import annotations

import threading
from contextlib import nullcontext
from pathlib import Path

import pytest

from app.services import upload_jobs, upload_state_repository
from app.services.runtime_db import (
    claim_next_upload_job,
    enqueue_upload_job,
    mark_queue_job_failed,
    read_upload_job,
)
from app.services.upload_session_service import resolve_upload_status


def _processing(job_id: str) -> dict:
    return {
        "job_id": job_id,
        "dataset_id": job_id,
        "filename": "terminal-state.csv",
        "workflow": "create_baseline",
        "status": "PROCESSING",
        "processing_state": "building_baseline",
        "message": "Building the behavioral baseline.",
    }


def _failure(job_id: str, *, message: str = "The baseline worker failed safely.") -> dict:
    return {
        **_processing(job_id),
        "status": "FAILED",
        "processing_state": "failed",
        "error": "baseline_processing_failed",
        "error_type": "baseline_processing_failed",
        "error_code": "processing_failed",
        "error_details": {"failed_stage": "baseline_creation", "retryable": True},
        "failed_stage": "baseline_creation",
        "retryable": True,
        "message": message,
        "result_available": False,
        "baseline_result_available": False,
    }


def _completion(job_id: str, *, message: str = "Behavioral baseline candidate ready.") -> tuple[dict, dict]:
    result = {
        "job_id": job_id,
        "dataset_id": job_id,
        "filename": "terminal-state.csv",
        "workflow": "create_baseline",
        "baseline_id": f"baseline-{job_id}",
        "status": "COMPLETE",
        "processing_state": "complete",
        "payload": {"committed": True},
    }
    summary = {
        "job_id": job_id,
        "dataset_id": job_id,
        "filename": "terminal-state.csv",
        "workflow": "create_baseline",
        "baseline_id": f"baseline-{job_id}",
        "baselineId": f"baseline-{job_id}",
        "datasetId": job_id,
        "jobId": job_id,
        "createdAt": "2026-08-10T00:00:00+00:00",
        "workspacePath": f"/baseline/{job_id}",
        "status": "COMPLETE",
        "processing_state": "complete",
        "result_available": True,
        "baseline_result_available": True,
        "message": message,
    }
    return result, summary


def _run_in_thread(target) -> tuple[threading.Thread, list[BaseException]]:
    errors: list[BaseException] = []

    def guarded() -> None:
        try:
            target()
        except BaseException as exc:  # pragma: no cover - asserted by caller
            errors.append(exc)

    thread = threading.Thread(target=guarded)
    thread.start()
    return thread, errors


def _finish_thread(thread: threading.Thread, errors: list[BaseException]) -> None:
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []


def test_failure_payload_is_not_observable_before_terminal_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = "delayed-failure-payload"
    upload_jobs.write_job(_processing(job_id))
    entered = threading.Event()
    release = threading.Event()
    original = upload_jobs.write_upload_status

    def delayed_status_write(current_job_id: str, payload: dict, **kwargs) -> dict:
        if str(payload.get("status") or "").upper() == "FAILED":
            entered.set()
            assert release.wait(timeout=5)
        return original(current_job_id, payload, **kwargs)

    monkeypatch.setattr(upload_jobs, "write_upload_status", delayed_status_write)
    thread, errors = _run_in_thread(lambda: upload_jobs.write_job(_failure(job_id)))
    assert entered.wait(timeout=5)

    during_publication = resolve_upload_status(job_id)
    assert during_publication["status"] == "PROCESSING"
    assert during_publication.get("error_type") is None

    release.set()
    _finish_thread(thread, errors)
    published = resolve_upload_status(job_id)
    assert published["status"] == "FAILED"
    assert published["error_type"] == "baseline_processing_failed"
    assert published["error_details"] == {"failed_stage": "baseline_creation", "retryable": True}
    assert published["job_progress"]["status"] == "failed"
    assert published["terminal_state_contract_version"] == "upload-terminal-state.v1"
    assert published["terminal_published_at"]


def test_terminal_queue_mirror_cannot_synthesize_an_incomplete_failure() -> None:
    job_id = "queue-failure-before-envelope"
    upload_jobs.write_job(_processing(job_id))
    enqueue_upload_job(job_id)
    assert claim_next_upload_job() == job_id

    mark_queue_job_failed(job_id, "quality profiler exploded")
    before_envelope = resolve_upload_status(job_id)
    assert before_envelope["status"] == "PROCESSING"
    assert before_envelope["execution_state"] == "processing"
    assert before_envelope["queue_state"] == "processing"
    assert before_envelope["terminal_publication_pending"] is True
    assert before_envelope.get("error_type") is None

    upload_jobs.write_job(_failure(job_id))
    after_envelope = resolve_upload_status(job_id)
    assert after_envelope["status"] == "FAILED"
    assert after_envelope["terminal_publication_pending"] is False
    assert after_envelope["error_details"]["failed_stage"] == "baseline_creation"


def test_completion_stays_nonterminal_until_result_and_derived_payloads_are_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = "delayed-completion-payload"
    upload_jobs.write_job(_processing(job_id))
    result, summary = _completion(job_id)
    entered = threading.Event()
    release = threading.Event()
    original = upload_state_repository.insert_shared_state_strict

    def delayed_result_write(name: str, *args, **kwargs):
        if name.startswith("upload_terminal_result_"):
            entered.set()
            assert release.wait(timeout=5)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(upload_state_repository, "insert_shared_state_strict", delayed_result_write)
    thread, errors = _run_in_thread(
        lambda: upload_state_repository.write_upload_completion(job_id, result=result, summary=summary)
    )
    assert entered.wait(timeout=5)

    during_publication = resolve_upload_status(job_id)
    assert during_publication["status"] == "PROCESSING"
    assert upload_state_repository.read_upload_result_by_job_id(job_id) is None

    release.set()
    _finish_thread(thread, errors)
    published = resolve_upload_status(job_id)
    assert published["status"] == "COMPLETE"
    assert published["result_available"] is True
    assert published["baselineId"] == f"baseline-{job_id}"


def test_completion_stays_nonterminal_until_compatibility_read_paths_are_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = "completion-result-authority"
    upload_jobs.write_job(_processing(job_id))
    result, summary = _completion(job_id)
    entered = threading.Event()
    release = threading.Event()
    original = upload_state_repository.write_upload_result

    def delayed_result_mirror(current_job_id: str, payload: dict) -> None:
        entered.set()
        assert release.wait(timeout=5)
        original(current_job_id, payload)

    monkeypatch.setattr(upload_state_repository, "write_upload_result", delayed_result_mirror)
    thread, errors = _run_in_thread(
        lambda: upload_state_repository.write_upload_completion(job_id, result=result, summary=summary)
    )
    assert entered.wait(timeout=5)

    during_mirror_write = resolve_upload_status(job_id)
    assert during_mirror_write["status"] == "PROCESSING"
    assert upload_state_repository.read_upload_result_by_job_id(job_id) is None

    release.set()
    _finish_thread(thread, errors)
    published = resolve_upload_status(job_id)
    assert published["status"] == "COMPLETE"
    assert published["terminal_result_contract_version"] == "upload-terminal-result.v1"
    assert upload_state_repository.read_upload_result_by_job_id(job_id)["payload"] == {"committed": True}


def test_completion_mirror_failure_is_repaired_by_idempotent_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = "completion-result-mirror-retry"
    upload_jobs.write_job(_processing(job_id))
    result, summary = _completion(job_id)
    original = upload_state_repository.write_upload_result

    def fail_result_mirror(_job_id: str, _payload: dict) -> None:
        raise OSError("simulated result mirror outage")

    monkeypatch.setattr(upload_state_repository, "write_upload_result", fail_result_mirror)
    published = upload_state_repository.write_upload_completion(job_id, result=result, summary=summary)

    assert published["status"] == "COMPLETE"
    assert resolve_upload_status(job_id)["status"] == "COMPLETE"
    assert upload_state_repository.read_upload_result_by_job_id(job_id)["payload"] == {"committed": True}
    assert upload_state_repository.read_local_json(f"upload_result_{job_id}.json") is None

    monkeypatch.setattr(upload_state_repository, "write_upload_result", original)
    retried = upload_state_repository.write_upload_completion(job_id, result=result, summary=summary)
    assert retried["status"] == "COMPLETE"
    assert upload_state_repository.read_local_json(f"upload_result_{job_id}.json")["payload"] == {
        "committed": True
    }


def test_duplicate_terminal_finalization_reuses_first_complete_envelope() -> None:
    job_id = "duplicate-completion"
    upload_jobs.write_job(_processing(job_id))
    result, first_summary = _completion(job_id, message="First committed completion.")
    _, duplicate_summary = _completion(job_id, message="Duplicate completion must not replace the first.")

    first = upload_state_repository.write_upload_completion(
        job_id,
        result=result,
        summary=first_summary,
    )
    duplicate = upload_state_repository.write_upload_completion(
        job_id,
        result={**result, "payload": {"committed": False}},
        summary=duplicate_summary,
    )

    assert first["message"] == "First committed completion."
    assert duplicate == first
    assert upload_state_repository.read_upload_result_by_job_id(job_id)["payload"] == {"committed": True}


def test_cross_process_duplicate_completion_keeps_status_and_result_from_one_publisher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = "cross-process-duplicate-completion"
    upload_jobs.write_job(_processing(job_id))
    first_result, first_summary = _completion(job_id, message="Publisher A completed.")
    second_result, second_summary = _completion(job_id, message="Publisher B completed.")
    first_result["payload"] = {"publisher": "A"}
    second_result["payload"] = {"publisher": "B"}
    publication_barrier = threading.Barrier(2)
    original_status_write = upload_state_repository.write_upload_status

    monkeypatch.setattr(
        upload_state_repository,
        "upload_job_publication_lock",
        lambda _job_id: nullcontext(),
    )

    def synchronized_status_write(current_job_id: str, payload: dict, **kwargs) -> dict:
        if str(payload.get("status") or "").upper() == "COMPLETE":
            publication_barrier.wait(timeout=5)
        return original_status_write(current_job_id, payload, **kwargs)

    monkeypatch.setattr(upload_state_repository, "write_upload_status", synchronized_status_write)
    first_thread, first_errors = _run_in_thread(
        lambda: upload_state_repository.write_upload_completion(
            job_id,
            result=first_result,
            summary=first_summary,
        )
    )
    second_thread, second_errors = _run_in_thread(
        lambda: upload_state_repository.write_upload_completion(
            job_id,
            result=second_result,
            summary=second_summary,
        )
    )
    _finish_thread(first_thread, first_errors)
    _finish_thread(second_thread, second_errors)

    published = upload_jobs.read_job(job_id)
    persisted_result = upload_state_repository.read_upload_result_by_job_id(job_id)
    expected_message = f"Publisher {persisted_result['payload']['publisher']} completed."
    assert published["message"] == expected_message


def test_completion_rejects_cross_job_payload_before_terminal_publication() -> None:
    job_id = "completion-identity-boundary"
    upload_jobs.write_job(_processing(job_id))
    result, summary = _completion(job_id)
    result["job_id"] = "another-job"

    with pytest.raises(ValueError, match="upload_completion_identity_mismatch"):
        upload_state_repository.write_upload_completion(job_id, result=result, summary=summary)

    assert upload_jobs.read_job(job_id)["status"] == "PROCESSING"
    assert upload_state_repository.read_upload_result_by_job_id(job_id) is None


def test_late_progress_and_competing_terminal_cannot_replace_failed_attempt() -> None:
    job_id = "monotonic-failure"
    upload_jobs.write_job(_processing(job_id))
    failure = _failure(job_id)
    upload_jobs.write_job(failure)

    upload_jobs.write_job({**_processing(job_id), "message": "Late worker heartbeat."})
    result, completion = _completion(job_id)
    canonical = upload_state_repository.write_upload_completion(
        job_id,
        result=result,
        summary=completion,
    )

    assert canonical["status"] == "FAILED"
    assert upload_jobs.read_job(job_id)["status"] == "FAILED"
    assert upload_jobs.UPLOAD_RUNTIME_STATE.jobs[job_id]["status"] == "FAILED"
    assert read_upload_job(job_id)["status"] == "FAILED"
    assert upload_state_repository.read_upload_result_by_job_id(job_id) is None


def test_losing_terminal_update_cannot_contaminate_latest_derived_mirrors() -> None:
    job_id = "competing-latest-mirror"
    processing = {**_processing(job_id), "workflow": "legacy_analysis"}
    upload_jobs.write_job(processing)
    result, completion = _completion(job_id)
    result["workflow"] = "legacy_analysis"
    completion["workflow"] = "legacy_analysis"
    upload_state_repository.write_upload_completion(
        job_id,
        result=result,
        summary=completion,
    )

    upload_jobs.write_job(
        {
            **_failure(job_id, message="A late failure must lose."),
            "workflow": "legacy_analysis",
        }
    )

    assert upload_jobs.read_job(job_id)["status"] == "COMPLETE"
    assert upload_state_repository.read_latest_upload_summary()["status"] == "COMPLETE"
    latest_record = upload_state_repository.read_latest_upload_record()
    assert latest_record["summary"]["status"] == "COMPLETE"
    assert latest_record["result"]["payload"] == {"committed": True}


def test_terminal_authority_does_not_depend_on_mutable_status_mirror() -> None:
    job_id = "terminal-status-pointer"
    upload_jobs.write_job(_processing(job_id))
    upload_jobs.write_job(_failure(job_id))

    published = resolve_upload_status(job_id)
    assert published["status"] == "FAILED"
    assert published["error_details"]["failed_stage"] == "baseline_creation"
    mirrored = upload_state_repository.read_local_json(f"upload_status_{job_id}.json")
    assert mirrored["status"] == "PROCESSING"
    assert mirrored["attempt_id"] == published["attempt_id"]

    # A duplicate finalization reuses the envelope without changing the
    # mutable attempt pointer back into a terminal-status authority.
    upload_jobs.write_job(_failure(job_id))
    assert upload_state_repository.read_local_json(f"upload_status_{job_id}.json")["status"] == "PROCESSING"
    assert resolve_upload_status(job_id)["status"] == "FAILED"


def test_authoritative_store_failure_keeps_prior_state_visible_until_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = "terminal-authority-retry"
    upload_jobs.write_job(_processing(job_id))
    original = upload_state_repository.insert_shared_state_strict

    def fail_authority(*args, **kwargs):
        raise OSError("simulated authoritative store outage")

    monkeypatch.setattr(upload_state_repository, "insert_shared_state_strict", fail_authority)
    with pytest.raises(OSError, match="authoritative store outage"):
        upload_jobs.write_job(_failure(job_id))
    assert resolve_upload_status(job_id)["status"] == "PROCESSING"
    assert upload_jobs.UPLOAD_RUNTIME_STATE.jobs[job_id]["status"] == "PROCESSING"

    monkeypatch.setattr(upload_state_repository, "insert_shared_state_strict", original)
    upload_jobs.write_job(_failure(job_id))
    assert resolve_upload_status(job_id)["status"] == "FAILED"


def test_concurrent_polling_never_returns_an_incomplete_terminal_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = "concurrent-terminal-reader"
    upload_jobs.write_job(_processing(job_id))
    entered = threading.Event()
    release = threading.Event()
    original = upload_state_repository.insert_shared_state_strict

    def delayed_authority(*args, **kwargs):
        entered.set()
        assert release.wait(timeout=5)
        return original(*args, **kwargs)

    monkeypatch.setattr(upload_state_repository, "insert_shared_state_strict", delayed_authority)
    writer, errors = _run_in_thread(lambda: upload_jobs.write_job(_failure(job_id)))
    assert entered.wait(timeout=5)

    observed = [resolve_upload_status(job_id) for _ in range(50)]
    release.set()
    _finish_thread(writer, errors)
    observed.extend(resolve_upload_status(job_id) for _ in range(50))

    for payload in observed:
        if payload["status"] == "FAILED":
            assert payload["error_type"] == "baseline_processing_failed"
            assert payload["error_details"]["failed_stage"] == "baseline_creation"
            assert payload["job_progress"]["status"] == "failed"
        else:
            assert payload["status"] == "PROCESSING"


def test_terminal_envelope_is_reconstructed_after_process_cache_reset() -> None:
    job_id = "terminal-restart-read"
    upload_jobs.write_job(_processing(job_id))
    upload_jobs.write_job(_failure(job_id))

    runtime_dir = Path(upload_jobs.UPLOAD_RUNTIME_STATE.runtime_dir)
    for path in runtime_dir.rglob(f"upload_status_{job_id}.json"):
        path.unlink()
    upload_jobs.UPLOAD_RUNTIME_STATE.jobs.clear()
    upload_jobs.UPLOAD_RUNTIME_STATE.latest_upload_cache.clear()

    reconstructed = upload_jobs.read_job(job_id)
    assert reconstructed["status"] == "FAILED"
    assert reconstructed["error_details"]["failed_stage"] == "baseline_creation"
    assert reconstructed["terminal_state_contract_version"] == "upload-terminal-state.v1"


def test_explicit_retry_uses_a_new_attempt_and_rejects_stale_attempt_writes() -> None:
    job_id = "retry-attempt-isolation"
    upload_jobs.write_job(_processing(job_id))
    upload_jobs.write_job(_failure(job_id))
    failed = upload_jobs.read_job(job_id)
    failed_attempt_id = failed["attempt_id"]

    upload_jobs.write_job(
        {
            **failed,
            "status": "PENDING",
            "processing_state": "queued",
            "message": "Retry queued.",
            "retry_requested_at": "2026-08-10T01:00:00+00:00",
            "result_available": False,
        }
    )
    retried = upload_jobs.read_job(job_id)
    assert retried["status"] == "PENDING"
    assert retried["attempt_id"] != failed_attempt_id
    assert retried["job_state"] == "queued"
    assert retried["terminal"] is False
    assert "terminal_state_contract_version" not in retried
    assert "terminal_published_at" not in retried

    upload_jobs.write_job(
        {
            **_processing(job_id),
            "attempt_id": failed_attempt_id,
            "message": "Late callback from the failed attempt.",
        }
    )
    still_retried = upload_jobs.read_job(job_id)
    assert still_retried["status"] == "PENDING"
    assert still_retried["attempt_id"] == retried["attempt_id"]

    result, summary = _completion(job_id)
    result["attempt_id"] = retried["attempt_id"]
    summary["attempt_id"] = retried["attempt_id"]
    completed = upload_state_repository.write_upload_completion(
        job_id,
        result=result,
        summary=summary,
    )
    assert completed["status"] == "COMPLETE"
    assert completed["attempt_id"] == retried["attempt_id"]
