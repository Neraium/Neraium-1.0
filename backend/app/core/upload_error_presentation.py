"""Sanitize HTTP upload failures, never persisted/canonical analytical objects."""
import json
import logging
import re

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse

from app.core.failure_evidence_presentation import customer_evidence_view
from app.services.upload_errors import LEGACY_UPLOAD_ERROR_CODES, UPLOAD_ERROR_DEFAULTS, build_upload_error_payload, canonical_upload_error_code

logger = logging.getLogger(__name__)
_FAILURE_STATES = {"failed", "error", "timeout", "cancelled", "not_found"}


def public_upload_error(payload=None, status_code=500):
    payload = payload if isinstance(payload, dict) else {}
    fallback = {400: "validation_failed", 401: "auth_session_expired", 403: "auth_session_expired",
                404: "not_found", 413: "file_too_large", 415: "validation_failed",
                422: "validation_failed", 429: "rate_limited", 503: "server_unavailable"}
    code = canonical_upload_error_code(payload.get("error_code") or payload.get("errorCode")
                                       or payload.get("error_type") or fallback.get(status_code))
    legacy_type = payload.get("error_type")
    if not isinstance(legacy_type, str) or (legacy_type not in LEGACY_UPLOAD_ERROR_CODES and legacy_type not in UPLOAD_ERROR_DEFAULTS):
        legacy_type = "auth" if status_code in {401, 403} else code
    safe = build_upload_error_payload(code, legacy_error_type=legacy_type, progress=0)
    safe.pop("technicalMessage", None)
    safe.pop("exception_type", None)
    safe["detail"] = safe["message"]
    # Correlation is useful for polling/support. No free-form exception fields.
    for key in ("job_id", "jobId", "dataset_id", "datasetId", "upload_session_id", "request_id", "requestId"):
        value = payload.get(key)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value):
            safe[key] = value
    return safe


def public_upload_state(payload):
    """Only transport-owned envelope paths; never descend into result/evidence."""
    if not isinstance(payload, dict):
        return payload
    failed = any(str(payload.get(key, "")).lower() in _FAILURE_STATES
                 for key in ("status", "processing_state", "job_state", "session_state"))
    summary = payload.get("summary")
    if isinstance(summary, dict):
        failed = failed or any(str(summary.get(key, "")).lower() in _FAILURE_STATES
                               for key in ("status", "processing_state", "job_state"))
    if failed:
        # Preserve complete governed results when a newer execution has failed.
        safe = public_upload_error(payload)
        for key in ("status", "processing_state", "job_state", "session_state"):
            # Session lifecycle is transport metadata. A historical result can
            # have a terminal COMPLETE status while belonging to a stale
            # session, so preserve its safe lifecycle state through the error
            # projection as well.
            if key == "session_state" and payload.get(key) in {
                "empty", "queued", "processing", "verified", "restored", "stale", "error"
            }:
                safe[key] = payload[key]
            elif str(payload.get(key, "")).lower() in _FAILURE_STATES:
                safe[key] = payload[key]
        for key in ("result", "current_result", "latest_result", "latestResult", "analysis_result", "history", "system_interpretation", "traceability", "adaptive_learning"):
            if key in payload:
                safe[key] = payload[key]
    else:
        safe = dict(payload)
    for key in ("snapshot", "summary", "current_upload"):
        if isinstance(payload.get(key), dict):
            safe[key] = public_upload_state(payload[key])
    if isinstance(safe.get("evidence"), dict):
        safe["evidence"] = customer_evidence_view(safe["evidence"])
    return safe


class UploadErrorRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handler(request):
            try:
                response = await original(request)
            except RequestValidationError:
                return JSONResponse(public_upload_error(status_code=422), status_code=422)
            except HTTPException as exc:
                return JSONResponse(public_upload_error(exc.detail, exc.status_code),
                                    status_code=exc.status_code, headers=exc.headers)
            except Exception as exc:
                # Class name provides a diagnostic category without logging raw
                # exception text, paths, credentials or customer telemetry.
                logger.error("upload_boundary_failed exception_type=%s", type(exc).__name__)
                return JSONResponse(public_upload_error(), status_code=500)
            if response.status_code >= 400:
                try:
                    payload = json.loads(response.body)
                except (ValueError, AttributeError):
                    payload = None
                headers = dict(response.headers)
                headers.pop("content-length", None)
                return JSONResponse(public_upload_error(payload, response.status_code),
                                    status_code=response.status_code, headers=headers)
            return response
        return handler
