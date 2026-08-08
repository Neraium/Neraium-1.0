from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.core.path_safety import StoragePathError, resolve_existing_storage_path, storage_key_for_server_path
from app.services.baseline_contracts import canonical_baseline_creation_response, is_baseline_workflow
from app.services.behavioral_model_repository import read_baseline_result_by_model_id, read_model
from app.services.dataset_scope import current_dataset_scope, dataset_scope_from_payload, set_current_dataset_scope
from app.services.runtime_db import (
    claim_next_upload_job,
    complete_upload_queue_job,
    mark_queue_job_failed,
    read_upload_job,
    read_upload_queue_job,
    touch_upload_queue_job,
)
from app.services.upload_runtime_state import UploadRuntimeState
from app.services.upload_errors import build_upload_error_payload


UPLOAD_QUEUE_HEARTBEAT_INTERVAL_SECONDS = 30.0


def _parse_iso_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _log_queue_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    job_id = str(fields.get("job_id") or "").strip() or None
    scope = current_dataset_scope()
    normalized = {
        "event": event,
        "correlation_id": fields.get("correlation_id") or job_id,
        "dataset_id": fields.get("dataset_id") or job_id,
        "upload_id": fields.get("upload_id") or job_id,
        "user_id": fields.get("user_id") or scope.user_id,
        "organization_id": fields.get("organization_id") or scope.tenant_id,
        **fields,
    }
    parts = []
    for key, value in normalized.items():
        if value is None:
            continue
        text = str(value).replace("\n", " ").replace("\r", " ")
        if len(text) > 500:
            text = f"{text[:500]}..."
        parts.append(f"{key}={text}")
    logger.info("upload_queue_lifecycle_event %s", " ".join(parts))


class UploadQueueLifecycleService:
    def __init__(
        self,
        *,
        runtime_state: UploadRuntimeState,
        logger: logging.Logger,
        read_job: Callable[[str], dict[str, Any] | None],
        read_upload_result_by_job_id: Callable[[str], dict[str, Any] | None],
        read_baseline_result: Callable[[str], dict[str, Any] | None],
        read_upload_status: Callable[[str], dict[str, Any] | None],
        write_job: Callable[[dict[str, Any]], None],
        process_json_payload: Callable[..., dict[str, Any]],
        process_csv_file: Callable[..., dict[str, Any]],
        restore_upload_source: Callable[..., Path],
        delete_upload_source: Callable[[str | None], None],
    ) -> None:
        self.runtime_state = runtime_state
        self.logger = logger
        self.read_job = read_job
        self.read_upload_result_by_job_id = read_upload_result_by_job_id
        self.read_baseline_result = read_baseline_result
        self.read_upload_status = read_upload_status
        self.write_job = write_job
        self.process_json_payload = process_json_payload
        self.process_csv_file = process_csv_file
        self.restore_upload_source = restore_upload_source
        self.delete_upload_source = delete_upload_source

    def _read_processing_metadata(self, job_id: str) -> dict[str, Any]:
        """Return the private processing metadata, including file_path when available.

        The public upload-status artifact can intentionally omit internal fields such as
        file_path. The queue worker needs the private runtime queue row instead; otherwise
        a freshly accepted upload can be marked failed even though the file was spooled.
        """
        public_metadata = self.read_job(job_id) or {}
        private_metadata = read_upload_job(job_id) or {}
        if not isinstance(public_metadata, dict):
            public_metadata = {}
        if not isinstance(private_metadata, dict):
            private_metadata = {}
        return {**public_metadata, **private_metadata, "job_id": job_id}

    def _resolve_processing_path(self, job_id: str, metadata: dict[str, Any]) -> Path | None:
        file_path = metadata.get("file_path")
        if file_path:
            try:
                return resolve_existing_storage_path(self.runtime_state.upload_dir, file_path)
            except StoragePathError:
                pass

        source_key = str(metadata.get("shared_upload_source_key") or "").strip()
        if not source_key:
            return None

        restored = self.restore_upload_source(job_id, source_key, filename=metadata.get("filename"))
        restored_key = storage_key_for_server_path(self.runtime_state.upload_dir, restored)
        metadata["file_path"] = restored_key
        self.write_job({**metadata, "job_id": job_id, "file_path": restored_key})
        return restored

    def _start_claim_heartbeat(self, job_id: str) -> tuple[threading.Event, threading.Thread]:
        """Refresh only a still-claimed queue row until this worker invocation ends."""
        stop = threading.Event()

        def heartbeat() -> None:
            while not stop.wait(UPLOAD_QUEUE_HEARTBEAT_INTERVAL_SECONDS):
                try:
                    queue_entry = read_upload_queue_job(job_id)
                    if not isinstance(queue_entry, dict) or str(queue_entry.get("status") or "").lower() != "processing":
                        return
                    touch_upload_queue_job(job_id, "processing")
                except Exception:
                    # Status polling can tolerate a missed heartbeat. Processing must
                    # continue so a transient queue-store failure cannot fail the job.
                    self.logger.warning("upload_queue_heartbeat_failed job_id=%s", job_id, exc_info=True)

        thread = threading.Thread(
            target=heartbeat,
            daemon=True,
            name=f"neraium-upload-heartbeat-{job_id[:8]}",
        )
        thread.start()
        return stop, thread

    def process_next_queued_upload_job(self) -> bool:
        started_at = time.perf_counter()
        job_id = claim_next_upload_job()
        if not job_id:
            return False
        heartbeat_stop, heartbeat_thread = self._start_claim_heartbeat(job_id)
        try:
            return self._process_claimed_upload_job(job_id, started_at)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=1.0)

    def _process_claimed_upload_job(self, job_id: str, started_at: float) -> bool:
        metadata = self._read_processing_metadata(job_id)
        claimed_at = datetime.now(timezone.utc)
        queue_entry = read_upload_queue_job(job_id) or {}
        queued_at = _parse_iso_timestamp(queue_entry.get("created_at")) or _parse_iso_timestamp(metadata.get("enqueued_at"))
        worker_pickup_delay_ms = max(0.0, (claimed_at - queued_at).total_seconds() * 1000) if queued_at else None
        timings = {**dict(metadata.get("timings") or {})}
        if worker_pickup_delay_ms is not None:
            timings["worker_pickup_delay_ms"] = round(worker_pickup_delay_ms, 3)
        metadata.update({
            "worker_started_at": claimed_at.isoformat(),
            "worker_pickup_delay_ms": round(worker_pickup_delay_ms, 3) if worker_pickup_delay_ms is not None else None,
            "timings": timings,
        })
        dataset_scope = dataset_scope_from_payload(metadata)
        if dataset_scope is None:
            mark_queue_job_failed(job_id, "missing_dataset_scope")
            self.logger.error("upload_queue_job_missing_dataset_scope job_id=%s", job_id)
            return False
        set_current_dataset_scope(dataset_scope)
        filename = metadata.get("filename")
        request_id = metadata.get("request_id")
        dataset_id = str(metadata.get("dataset_id") or job_id)
        _log_queue_event(
            self.logger,
            "job_claimed",
            job_id=job_id,
            dataset_id=dataset_id,
            request_id=request_id,
            filename=filename,
            queue_status="processing",
            processing_stage="claim",
            worker_pickup_delay_ms=round(worker_pickup_delay_ms, 3) if worker_pickup_delay_ms is not None else None,
            queue_attempts=queue_entry.get("attempts"),
            duplicate_claim=bool(int(queue_entry.get("attempts") or 0) > 1),
        )
        try:
            path = self._resolve_processing_path(job_id, metadata)
        except Exception as exc:
            technical_message = f"{exc.__class__.__name__}: {str(exc) or 'upload source restore failed'}"
            self.logger.exception(
                "upload_source_restore_failed dataset_id=%s job_id=%s request_id=%s stage=import exception_type=%s filename=%s",
                dataset_id,
                job_id,
                request_id,
                exc.__class__.__name__,
                filename,
            )
            _log_queue_event(
                self.logger,
                "job_failed",
                job_id=job_id,
                dataset_id=dataset_id,
                request_id=request_id,
                filename=filename,
                queue_status="failed",
                processing_stage="restore_source",
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                failure_reason=str(exc) or exc.__class__.__name__,
            )
            mark_queue_job_failed(job_id, technical_message)
            complete_upload_queue_job(job_id, "failed", technical_message)
            self.write_job({
                **metadata,
                **build_upload_error_payload(
                    "file_storage_failed",
                    message="The uploaded file is stored, but it could not be opened for processing.",
                    failed_stage="import",
                    retryable=True,
                    legacy_error_type="upload_source_restore_failed",
                    job_id=job_id,
                    dataset_id=dataset_id,
                    request_id=request_id,
                    technical_message=technical_message,
                    exception_type=exc.__class__.__name__,
                    file_stored=True,
                    transfer_succeeded=True,
                    retry_url=f"/api/data/upload/{job_id}/retry",
                ),
                "result_available": False,
            })
            return False
        if path is None or not path.exists():
            existing_result = self.read_upload_result_by_job_id(job_id)
            existing_status = self.read_upload_status(job_id) or {}
            existing_status_text = str(existing_status.get("status", "")).upper()
            existing_artifacts = {}
            if isinstance(existing_status.get("sii_completion_artifacts"), dict):
                existing_artifacts = existing_status["sii_completion_artifacts"]
            elif isinstance(existing_result, dict) and isinstance(existing_result.get("sii_completion_artifacts"), dict):
                existing_artifacts = existing_result["sii_completion_artifacts"]
            required_artifacts = {
                "evidence_persisted",
                "relationships_persisted",
                "behavioral_structure_persisted",
                "baseline_persisted",
                "final_result_persisted",
                "terminal_backend_state_published",
            }
            has_required_artifacts = all(existing_artifacts.get(key) is True for key in required_artifacts)
            has_completed_status = (
                existing_status_text == "COMPLETE"
                and (
                    (
                        existing_status.get("sii_completed") is True
                        and has_required_artifacts
                    )
                    or (
                        is_baseline_workflow(existing_status.get("workflow"))
                        and existing_status.get("baseline_candidate_created") is True
                        and existing_status.get("sii_engine_invoked") is False
                    )
                )
            )
            has_completed_result = (
                isinstance(existing_result, dict)
                and existing_result.get("sii_completed") is True
                and has_required_artifacts
            )
            if has_completed_status or has_completed_result:
                complete_upload_queue_job(job_id, "completed")
                _log_queue_event(
                    self.logger,
                    "job_completed",
                    job_id=job_id,
                    dataset_id=dataset_id,
                    request_id=request_id,
                    filename=filename,
                    queue_status="completed",
                    processing_stage="existing_result",
                    elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                )
                return True
            mark_queue_job_failed(job_id, "missing_upload_file")
            self.write_job(
                {
                    **metadata,
                    **build_upload_error_payload(
                        "file_storage_failed",
                        message="The stored file could not be found for processing.",
                        failed_stage="file_storage",
                        retryable=False,
                        legacy_error_type="missing_upload_file",
                        job_id=job_id,
                        dataset_id=metadata.get("dataset_id") or job_id,
                        request_id=request_id,
                    ),
                }
            )
            _log_queue_event(
                self.logger,
                "job_failed",
                job_id=job_id,
                dataset_id=dataset_id,
                request_id=request_id,
                filename=filename,
                queue_status="failed",
                processing_stage="resolve_source",
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                failure_reason="missing_upload_file",
            )
            return False
        try:
            file_size_bytes = None
            try:
                file_size_bytes = path.stat().st_size
            except OSError:
                pass
            _log_queue_event(
                self.logger,
                "storage_object_resolved",
                job_id=job_id,
                dataset_id=dataset_id,
                request_id=request_id,
                source_filename=filename,
                file_size_bytes=file_size_bytes,
                processing_stage="file_storage",
            )
            _log_queue_event(
                self.logger,
                "csv_opened",
                job_id=job_id,
                dataset_id=dataset_id,
                request_id=request_id,
                source_filename=filename,
                file_size_bytes=file_size_bytes,
                processing_stage="csv_parsing",
            )
            _log_queue_event(
                self.logger,
                "job_started",
                job_id=job_id,
                dataset_id=dataset_id,
                request_id=request_id,
                filename=filename,
                file_size_bytes=file_size_bytes,
                queue_status="processing",
                processing_stage="parsing_telemetry",
            )
            self.write_job(
                {
                    **metadata,
                    "job_id": job_id,
                    "file_path": storage_key_for_server_path(self.runtime_state.upload_dir, path),
                    "status": "PROCESSING",
                    "processing_state": "parsing_telemetry",
                    "percent": 20,
                    "progress": 20,
                    "message": "Parsing telemetry.",
                    "progress_label": "Parsing telemetry.",
                    "propagation_stage": "parsing_telemetry",
                    "propagation_progress": 20,
                    "propagation_label": "Parsing telemetry.",
                    "worker_started_at": metadata.get("worker_started_at"),
                    "worker_pickup_delay_ms": metadata.get("worker_pickup_delay_ms"),
                    "timings": timings,
                }
            )
            try:
                touch_upload_queue_job(job_id, "processing")
            except Exception:
                pass
            if path.suffix.lower() == ".json":
                result = self.process_json_payload(
                    path.read_bytes(),
                    filename=metadata.get("filename") or path.name,
                    job_id=job_id,
                )
            else:
                result = self.process_csv_file(path, filename=metadata.get("filename") or path.name, job_id=job_id)
            completed = self.read_upload_status(job_id) or {}
            completed["job_id"] = job_id
            baseline_workflow = is_baseline_workflow(metadata.get("workflow"))
            terminal_candidate = result if baseline_workflow and isinstance(result, dict) else completed
            completed_status = str(terminal_candidate.get("status") or completed.get("status") or "").upper()
            if completed_status in {"FAILED", "TIMEOUT", "CANCELLED"}:
                error_message = str(terminal_candidate.get("error") or completed.get("error") or terminal_candidate.get("message") or completed.get("message") or completed_status.lower())
                mark_queue_job_failed(job_id, error_message)
                complete_upload_queue_job(job_id, "failed", error_message)
                self.write_job({
                    **metadata,
                    **completed,
                    "job_id": job_id,
                    "status": completed_status,
                    "processing_state": str(completed.get("processing_state") or "failed").lower(),
                    "result_available": False,
                    "first_usable_available": False,
                    "sii_completed": False,
                    "replay_ready": False,
                    "replay_frame_count": 0,
                    "propagation_stage": "failed",
                    "propagation_label": completed.get("propagation_label") or "Failed.",
                })
                _log_queue_event(
                    self.logger,
                    "job_failed",
                    job_id=job_id,
                    dataset_id=dataset_id,
                    request_id=request_id,
                    filename=filename,
                    queue_status="failed",
                    processing_stage=completed.get("processing_state") or "failed",
                    elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                    failure_reason=error_message,
                )
                return False
            if completed_status != "COMPLETE":
                error_message = f"terminal_status_missing:{completed_status or 'empty'}"
                mark_queue_job_failed(job_id, error_message)
                complete_upload_queue_job(job_id, "failed", error_message)
                self.write_job({
                    **metadata,
                    **completed,
                    "job_id": job_id,
                    "status": "FAILED",
                    "processing_state": "failed",
                    "error_type": "terminal_status_missing",
                    "error": error_message,
                    "message": "Telemetry processing failed.",
                    "progress_label": "Telemetry processing failed.",
                    "result_available": False,
                    "first_usable_available": False,
                    "sii_completed": False,
                    "propagation_stage": "failed",
                    "propagation_label": "Failed.",
                })
                return False
            result_reader = self.read_baseline_result if baseline_workflow else self.read_upload_result_by_job_id
            result_deadline = time.monotonic() + 2.0
            persisted_result = result_reader(job_id)
            while not isinstance(persisted_result, dict) and time.monotonic() < result_deadline:
                time.sleep(0.05)
                persisted_result = result_reader(job_id)

            persistence_error = None
            baseline_contract: dict[str, Any] = {}
            if not isinstance(persisted_result, dict) or str(persisted_result.get("job_id") or job_id) != job_id:
                persistence_error = "terminal status was produced without a retrievable result"
            elif baseline_workflow:
                try:
                    baseline_contract = canonical_baseline_creation_response(persisted_result)
                    baseline_id = baseline_contract["baselineId"]
                    persisted_model = read_model(baseline_id)
                    model_readback = read_baseline_result_by_model_id(baseline_id)
                    if not isinstance(persisted_model, dict) or str(persisted_model.get("model_id") or "").strip() != baseline_id:
                        raise ValueError("baseline row could not be read by ID")
                    if not isinstance(model_readback, dict) or str(model_readback.get("job_id") or "").strip() != job_id:
                        raise ValueError("baseline result could not be read by ID")
                except (KeyError, TypeError, ValueError) as exc:
                    persistence_error = str(exc) or exc.__class__.__name__

            if persistence_error:
                technical_message = f"ResultPersistenceError: {persistence_error}"
                failure = build_upload_error_payload(
                    "result_persistence_failed",
                    message="Processing finished, but the baseline result could not be made available.",
                    failed_stage="baseline_creation",
                    retryable=True,
                    legacy_error_type="result_persistence_failed",
                    job_id=job_id,
                    dataset_id=metadata.get("dataset_id") or job_id,
                    request_id=request_id,
                    technical_message=technical_message,
                    exception_type="ResultPersistenceError",
                    file_stored=True,
                    transfer_succeeded=True,
                    retry_url=f"/api/data/upload/{job_id}/retry",
                )
                mark_queue_job_failed(job_id, technical_message)
                complete_upload_queue_job(job_id, "failed", technical_message)
                self.write_job({**metadata, **completed, **failure, "result_available": False})
                self.logger.error(
                    "upload_result_persistence_failed dataset_id=%s job_id=%s request_id=%s stage=baseline_creation exception_type=ResultPersistenceError",
                    metadata.get("dataset_id") or job_id,
                    job_id,
                    request_id,
                )
                return False
            if baseline_workflow:
                terminal_response = {
                    **completed,
                    **terminal_candidate,
                    **baseline_contract,
                    "job_id": job_id,
                    "status": "COMPLETE",
                    "processing_state": "complete",
                    "analysis_state": "completed",
                    "job_state": "completed",
                    "terminal": True,
                    "result_available": True,
                    "baseline_result_available": True,
                }
                self.write_job(terminal_response)
                completed = self.read_upload_status(job_id) or terminal_response
                _log_queue_event(
                    self.logger,
                    "baseline_handoff_completed",
                    job_id=job_id,
                    dataset_id=baseline_contract.get("datasetId"),
                    baseline_id=baseline_contract.get("baselineId"),
                    request_id=request_id,
                    persistence_result="readback_verified",
                    returned_response_body=baseline_contract,
                    route_destination=baseline_contract.get("workspacePath"),
                )
            complete_upload_queue_job(job_id, "completed")
            _log_queue_event(
                self.logger,
                "job_completed",
                job_id=job_id,
                dataset_id=dataset_id,
                request_id=request_id,
                filename=filename,
                queue_status="completed",
                processing_stage=completed.get("processing_state") or "complete",
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            self.delete_upload_source(metadata.get("shared_upload_source_key"))
            return bool(result)
        except TimeoutError as exc:
            self.logger.exception(
                "upload_queue_job_timed_out dataset_id=%s job_id=%s request_id=%s stage=baseline_creation exception_type=%s filename=%s",
                metadata.get("dataset_id") or job_id,
                job_id,
                request_id,
                exc.__class__.__name__,
                filename,
            )
            _log_queue_event(
                self.logger,
                "job_failed",
                job_id=job_id,
                dataset_id=dataset_id,
                request_id=request_id,
                filename=filename,
                queue_status="failed",
                processing_stage="processing_timeout",
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                failure_reason=str(exc) or exc.__class__.__name__,
            )
            mark_queue_job_failed(job_id, str(exc) or exc.__class__.__name__)
            complete_upload_queue_job(job_id, "failed", str(exc) or exc.__class__.__name__)
            self.write_job(
                {
                    **metadata,
                    **build_upload_error_payload(
                        "server_timeout",
                        message="The server timed out while processing the dataset. Retry the import.",
                        failed_stage="baseline_processing",
                        retryable=True,
                        legacy_error_type="processing_timeout",
                        job_id=job_id,
                        dataset_id=metadata.get("dataset_id") or job_id,
                        request_id=request_id,
                        technical_message=f"{exc.__class__.__name__}: {str(exc) or 'processing timeout'}",
                        exception_type=exc.__class__.__name__,
                    ),
                    "status": "TIMEOUT",
                    "processing_state": "timeout",
                    "progress_label": "Dataset processing timed out.",
                    "result_available": False,
                    "first_usable_available": False,
                    "replay_ready": False,
                    "replay_frame_count": 0,
                    "propagation_stage": "failed",
                    "propagation_label": "Timed out.",
                }
            )
            return False
        except Exception as exc:
            current = self.read_upload_status(job_id) or {}
            error_message = str(exc) or exc.__class__.__name__
            current_stage = str(
                current.get("processing_state")
                or current.get("propagation_stage")
                or metadata.get("processing_state")
                or ""
            ).strip().lower()
            if current_stage in {"reading_csv", "parsing", "parsing_telemetry"}:
                error_code = "csv_parsing_failed"
                failed_stage = "csv_parsing"
                safe_message = "The CSV could not be parsed. Check its format and try again."
                retryable = False
            elif current_stage in {
                "detecting_schema_signals",
                "validating_schema",
                "baseline_validating",
                "baseline_quality_assessment",
            }:
                error_code = "validation_failed"
                failed_stage = "validation"
                safe_message = "The dataset did not pass validation. Check the file and try again."
                retryable = False
            elif current_stage == "baseline_relationship_learning":
                error_code = "relationship_learning_failed"
                failed_stage = "relationship_learning"
                safe_message = "The file was uploaded, but expected signal relationships could not be learned."
                retryable = True
            else:
                error_code = "baseline_processing_failed"
                failed_stage = "baseline_creation"
                safe_message = "The dataset was imported, but baseline processing could not complete."
                retryable = True
            dataset_id = str(current.get("dataset_id") or metadata.get("dataset_id") or job_id)
            self.logger.exception(
                "upload_queue_job_failed dataset_id=%s job_id=%s request_id=%s stage=%s exception_type=%s filename=%s",
                dataset_id,
                job_id,
                request_id,
                failed_stage,
                exc.__class__.__name__,
                filename,
            )
            _log_queue_event(
                self.logger,
                "job_failed",
                job_id=job_id,
                dataset_id=dataset_id,
                request_id=request_id,
                filename=filename,
                queue_status="failed",
                processing_stage="processing",
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                failure_reason=error_message,
            )
            mark_queue_job_failed(job_id, error_message)
            complete_upload_queue_job(job_id, "failed", error_message)
            failed_payload = {
                **metadata,
                **current,
                **build_upload_error_payload(
                    error_code,
                    message=safe_message,
                    failed_stage=failed_stage,
                    retryable=retryable,
                    legacy_error_type="processing_error",
                    job_id=job_id,
                    dataset_id=dataset_id,
                    request_id=request_id,
                    technical_message=f"{exc.__class__.__name__}: {error_message}",
                    exception_type=exc.__class__.__name__,
                    file_stored=True,
                    transfer_succeeded=True,
                    retry_url=f"/api/data/upload/{job_id}/retry",
                ),
                "progress_label": safe_message,
                "result_available": False,
                "first_usable_available": False,
                "replay_ready": False,
                "replay_frame_count": 0,
                "propagation_stage": "failed",
                "propagation_label": "Failed.",
            }
            try:
                if is_baseline_workflow(metadata.get("workflow")):
                    raise LookupError("baseline_workflows_do_not_persist_evidence")
                from app.services.evidence_store import upsert_evidence_run

                now = datetime.now(timezone.utc).isoformat()
                upsert_evidence_run(
                    {
                        "run_id": job_id,
                        "source_name": metadata.get("filename") or "upload.csv",
                        "source_type": "csv_upload",
                        "status": "failed",
                        "created_at": now,
                        "completed_at": now,
                        "rows_received": 0,
                        "rows_accepted": 0,
                        "rows_rejected": 0,
                        "sensors_detected": 0,
                        "room": "Uploaded telemetry",
                        "operating_state": "error",
                        "drift_status": "error",
                        "warnings": [],
                        "errors": [str(exc)],
                        "primary_drivers": [],
                        "evidence_summary": [],
                        "structural_archetypes": [],
                        "initiated_by": metadata.get("initiated_by", "anonymous"),
                        "adaptive_site_key": "site::default",
                        "operator_feedback_history": [],
                        "observation_type": "data_condition",
                        "observation_status": "failed",
                        "variables": [],
                        "drift_metrics": {},
                        "data_conditions": [str(exc)],
                        "regime_label": None,
                        "structural_state": "Error",
                        "deformation_started_at": None,
                    }
                )
            except LookupError:
                pass
            except Exception:
                self.logger.exception("failed_evidence_persistence_failed job_id=%s", job_id)
            self.write_job(failed_payload)
            return False
