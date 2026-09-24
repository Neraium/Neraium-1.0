"""Producer schema for complete upload artifacts, not a comparator filter.

Only fields owned by upload orchestration are relocated. No recursive timestamp
matching: source chronology and embedded evidence are opaque to this serializer.
"""
from copy import deepcopy
from typing import Any

from app.services.output_semantics import RUNTIME_VERSION, runtime_metadata

UPLOAD_EVIDENCE_VERSION = 'complete-upload-evidence.v2'


def _move(record: Any, fields: tuple[str, ...]) -> None:
    if not isinstance(record, dict):
        return
    values = {field: record.pop(field) for field in fields if field in record}
    if values:
        record['runtime_metadata'] = runtime_metadata(**{
            **record.get('runtime_metadata', {}), **values,
        })


def _owned_records(result: dict[str, Any]):
    yield result, ('completed_at', 'last_processed_at', 'stage_changed_at', 'processing_time_seconds',
                   'request_id', 'upload_session_id', 'attempt_id')
    yield result.get('processing_stats'), ('processing_time_seconds', 'timings')
    yield result.get('processing_trace'), ('completed_at', 'processing_time_seconds')
    yield (result.get('sii_result') or {}).get('processing_trace'), ('completed_at', 'processing_time_seconds')
    yield result.get('report_finalization'), ('started_at', 'completed_at')
    progress = result.get('job_progress') or {}
    yield progress, ('started_at', 'updated_at', 'last_worker_heartbeat_at',
                     'elapsed_seconds', 'seconds_since_update', 'seconds_since_worker_heartbeat')
    for operation in progress.get('operations', []):
        yield operation, ('started_at', 'updated_at', 'completed_at')
    intelligence = result.get('sii_intelligence') or {}
    yield intelligence, ('last_updated',)
    for room in intelligence.get('rooms', []):
        yield room, ('last_updated',)
    for packet in (result.get('traceability'), result.get('decision_integrity'), intelligence.get('decision_integrity')):
        yield (packet or {}).get('timestamps'), ('created_at', 'completed_at', 'processed_at')


def encode_upload_result(result: dict[str, Any]) -> dict[str, Any]:
    """Produce the persisted v2 artifact after analytical construction is complete."""
    output = deepcopy(result)
    output['upload_evidence_contract'] = UPLOAD_EVIDENCE_VERSION
    for record, fields in _owned_records(output):
        _move(record, fields)
    return output


def upload_compatibility_view(result: dict[str, Any]) -> dict[str, Any]:
    """Restore only the upload producer's moved fields for legacy UI consumers."""
    if result.get('upload_evidence_contract') != UPLOAD_EVIDENCE_VERSION:
        return result
    output = deepcopy(result)
    for record, fields in _owned_records(output):
        if not isinstance(record, dict):
            continue
        runtime = record.get('runtime_metadata') or {}
        if runtime.get('contract_version') == RUNTIME_VERSION:
            for field in fields:
                if field in runtime:
                    record[field] = runtime[field]
    return output
