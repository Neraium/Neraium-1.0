from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.services.runtime_db import (
    claim_next_upload_job,
    complete_upload_queue_job,
    mark_queue_job_failed,
    read_upload_job,
    touch_upload_queue_job,
)
from app.services.upload_runtime_state import UploadRuntimeState


def _log_queue_event(logger: logging.Logger, event: str, **fields: Any) -> None:
    normalized = {"event": event, **fields}
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
        read_upload_status: Callable[[str], dict[str, Any] | None],
        write_job: Callable[[dict[str, Any]], None],
        process_json_payload: Callable[..., dict[str, Any]],
        process_csv_file: Callable[..., dict[str, Any]],
        restore_upload_source: Callable[[str, str], Path],
        delete_upload_source: Callable[[str | None], None],
    ) -> None:
        self.runtime_state = runtime_state
        self.logger = logger
        self.read_job = read_job
        self.read_upload_result_by_job_id = read_upload_result_by_job_id
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
        path = Path(str(file_path)) if file_path else None
        if path and path.exists():
            return path

        source_key = str(metadata.get("shared_upload_source_key") or "").strip()
        if not source_key:
            return None

        restored = self.restore_upload_source(job_id, source_key)
        metadata["file_path"] = str(restored)
        self.write_job({**metadata, "job_id": job_id, "file_path": str(restored)})
        return restored

    def process_next_queued_upload_job(self) -> bool:
        started_at = time.perf_counter()
        job_id = claim_next_upload_job()
        if not job_id:
            return False
        metadata = self._read_processing_metadata(job_id)
        filename = metadata.get("filename")
        request_id = metadata.get("request_id")
        _log_queue_event(
            self.logger,
            "job_claimed",
            job_id=job_id,
            request_id=request_id,
            filename=filename,
            queue_status="processing",
            processing_stage="claim",
        )
        try:
            path = self._resolve_processing_path(job_id, metadata)
        except Exception as exc:
            self.logger.exception("upload_source_restore_failed job_id=%s filename=%s", job_id, filename)
            _log_queue_event(
                self.logger,
                "job_failed",
                job_id=job_id,
                request_id=request_id,
                filename=filename,
                queue_status="failed",
                processing_stage="restore_source",
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                failure_reason=str(exc) or exc.__class__.__name__,
            )
            path = None
        if path is None or not path.exists():
            existing_result = self.read_upload_result_by_job_id(job_id)
            existing_status = self.read_upload_status(job_id) or {}
            if existing_result or str(existing_status.get("status", "")).upper() == "COMPLETE":
                complete_upload_queue_job(job_id, "completed")
                _log_queue_event(
                    self.logger,
                    "job_completed",
                    job_id=job_id,
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
                    "job_id": job_id,
                    "status": "FAILED",
                    "processing_state": "failed",
                    "error_type": "missing_upload_file",
                    "error": "missing_upload_file",
                    "message": "Upload file could not be found for processing.",
                }
            )
            _log_queue_event(
                self.logger,
                "job_failed",
                job_id=job_id,
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
                "job_processing_started",
                job_id=job_id,
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
                    "file_path": str(path),
                    "status": "PROCESSING",
                    "processing_state": "parsing_telemetry",
                    "percent": 20,
                    "progress": 20,
                    "message": "Parsing telemetry.",
                    "progress_label": "Parsing telemetry.",
                    "propagation_stage": "parsing_telemetry",
                    "propagation_progress": 20,
                    "propagation_label": "Parsing telemetry.",
                }
            )
            try:
                touch_upload_queue_job(job_id, "processing")
            except Exception:
                pass
            if path.suffix.lower() == ".json":
                result = self.process_json_payload(
                    path.read_text(encoding="utf-8"),
                    filename=metadata.get("filename") or path.name,
                    job_id=job_id,
                )
            else:
                result = self.process_csv_file(path, filename=metadata.get("filename") or path.name, job_id=job_id)
            completed = self.read_upload_status(job_id) or {}
            if metadata.get("runner_used") is False:
                completed["runner_used"] = False
            completed["job_id"] = job_id
            completed["status"] = "COMPLETE"

            if completed.get("processing_state") == "partial_complete":
                completed["result_available"] = True
                completed["first_usable_available"] = True
                completed["sii_completed"] = False
                completed["replay_ready"] = False
                completed["replay_frame_count"] = 0
                completed["percent"] = 100
                completed["progress"] = 100
                completed.setdefault("message", "Upload completed, but full intelligence processing could not finish.")
                completed["propagation_stage"] = "partial_complete"
                completed["propagation_progress"] = 100
                completed["propagation_label"] = "Partial upload complete."
            else:
                completed["processing_state"] = "complete"
                completed["result_available"] = True
                completed["percent"] = 100
                completed["progress"] = 100
                completed["message"] = "Telemetry processing complete."
                completed["propagation_stage"] = "complete"
                completed["propagation_progress"] = 100
                completed["propagation_label"] = "Complete."
            self.write_job(completed)
            complete_upload_queue_job(job_id, "completed")
            _log_queue_event(
                self.logger,
                "job_completed",
                job_id=job_id,
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
            self.logger.exception("upload_queue_job_timed_out job_id=%s filename=%s", job_id, filename)
            _log_queue_event(
                self.logger,
                "job_failed",
                job_id=job_id,
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
                    "job_id": job_id,
                    "status": "TIMEOUT",
                    "processing_state": "timeout",
                    "error_type": "processing_timeout",
                    "error": str(exc) or exc.__class__.__name__,
                    "message": f"Telemetry processing timed out: {str(exc) or exc.__class__.__name__}",
                    "progress_label": "Telemetry processing timed out.",
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
            self.logger.exception("upload_queue_job_failed job_id=%s filename=%s", job_id, filename)
            current = self.read_upload_status(job_id) or {}
            error_message = str(exc) or exc.__class__.__name__
            _log_queue_event(
                self.logger,
                "job_failed",
                job_id=job_id,
                request_id=request_id,
                filename=filename,
                queue_status="failed",
                processing_stage="processing",
                elapsed_ms=round((time.perf_counter() - started_at) * 1000, 2),
                failure_reason=error_message,
            )
            mark_queue_job_failed(job_id, error_message)
            complete_upload_queue_job(job_id, "failed", error_message)
            self.write_job(
                {
                    **metadata,
                    **current,
                    "job_id": job_id,
                    "status": "FAILED",
                    "processing_state": "failed",
                    "error_type": "processing_error",
                    "error": error_message,
                    "message": f"Telemetry processing failed: {error_message}",
                    "progress_label": "Telemetry processing failed.",
                    "result_available": False,
                    "first_usable_available": False,
                    "replay_ready": False,
                    "replay_frame_count": 0,
                    "propagation_stage": "failed",
                    "propagation_label": "Failed.",
                }
            )
            try:
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
            except Exception:
                pass
            return False
