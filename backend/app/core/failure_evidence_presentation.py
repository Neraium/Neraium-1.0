"""Customer failure view; persisted forensic and analytical evidence is untouched."""
from datetime import datetime
import re

from app.services.upload_errors import UPLOAD_ERROR_DEFAULTS, canonical_upload_error_code

_FAILED = frozenset({"failed", "error", "timeout", "cancelled", "canceled"})
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
_DIGEST = re.compile(r"[a-fA-F0-9]{64}")


def is_failure_evidence(record: dict) -> bool:
    return str(record.get("status") or "").strip().lower() in _FAILED


def customer_evidence_view(record: dict) -> dict:
    """Allowlist a failed run's presentation, never edit its raw record.

    Digests, when present, are references to the original stored artifact, not
    checksums of this view. Successful analytical records pass through exactly.
    The existing response schema exposes category in data_conditions and the
    safe explanation in errors/historical_fact; no schema migration is needed.
    """
    if not is_failure_evidence(record):
        return record
    category = canonical_upload_error_code(record.get("error_code") or record.get("error_type"))
    message = UPLOAD_ERROR_DEFAULTS[category][0]
    safe = {
        "run_id": "unavailable",
        "source_type": "upload",
        "created_at": "",
        "status": "failed",
        "observation_type": "data_condition",
        "observation_status": "failed",
        "historical_fact": message,
        "errors": [message],
        "data_conditions": [category],
    }
    # Do not copy source filenames, nested provenance, notes, diagnostics or
    # arbitrary new fields. Those belong to the restricted forensic view.
    for key in ("run_id", "job_id", "upload_id", "dataset_id", "baseline_id", "baseline_dataset_id"):
        value = record.get(key)
        if isinstance(value, str) and _IDENTIFIER.fullmatch(value):
            safe[key] = value
    for key in ("input_hash", "result_hash", "evidence_hash", "configuration_hash", "baseline_hash"):
        value = record.get(key)
        if isinstance(value, str) and _DIGEST.fullmatch(value):
            safe[key] = value
    for key in ("created_at", "completed_at"):
        value = record.get(key)
        if isinstance(value, str) and len(value) <= 40:
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            safe[key] = value
    return safe
