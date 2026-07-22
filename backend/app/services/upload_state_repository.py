from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.core.path_safety import ensure_storage_root, safe_upload_suffix
from app.services.dataset_scope import (
    DatasetScope,
    attach_dataset_scope,
    current_dataset_scope,
    dataset_scope_from_payload,
    payload_matches_dataset_scope,
)
from app.services.runtime_db import (
    delete_latest_payload_prefix,
    read_latest_payload,
    upsert_latest_payload,
)
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE, UploadRuntimeState
from app.services.upload_persistence import summarize_result as summarize_result_payload
from app.services.upload_state import (
    build_empty_latest_upload_record,
    build_latest_upload_record,
    build_replay_payload_from_result,
    build_session_scope,
    has_active_session_artifact,
    normalize_upload_identity,
    select_current_upload_result,
)


logger = logging.getLogger(__name__)


_SCOPED_LATEST_NAMES = {
    "latest_upload",
    "latest_upload_result",
    "latest_upload_summary",
}


def _state_scope(*, scope: DatasetScope | None = None, payload: dict[str, Any] | None = None) -> DatasetScope:
    return scope or dataset_scope_from_payload(payload) or current_dataset_scope()


def _state_name(name: str, *, scope: DatasetScope | None = None, payload: dict[str, Any] | None = None) -> str:
    raw_name = str(name).replace(".json", "")
    if raw_name not in _SCOPED_LATEST_NAMES:
        return raw_name
    resolved = _state_scope(scope=scope, payload=payload)
    return f"scopes/{resolved.storage_id}/{raw_name}"


def _local_state_name(name: str, *, scope: DatasetScope | None = None, payload: dict[str, Any] | None = None) -> str:
    normalized = _state_name(name, scope=scope, payload=payload)
    return f"{normalized}.json"


def _cache_key(kind: str, scope: DatasetScope | None = None) -> str:
    return f"{kind}:{(scope or current_dataset_scope()).storage_id}"


def _cache_set(kind: str, payload: dict[str, Any] | None, *, scope: DatasetScope | None = None) -> None:
    resolved = _state_scope(scope=scope, payload=payload)
    state = runtime_state()
    state.latest_upload_cache[_cache_key(kind, resolved)] = payload
    # Compatibility slot for older internal writers. Reads never trust it unless
    # the embedded scope matches the current request.
    state.latest_upload_cache[kind] = payload


def _cache_get(kind: str, *, scope: DatasetScope | None = None) -> dict[str, Any] | None:
    resolved = scope or current_dataset_scope()
    state = runtime_state()
    scoped = state.latest_upload_cache.get(_cache_key(kind, resolved))
    if isinstance(scoped, dict) and payload_matches_dataset_scope(scoped, resolved):
        return scoped
    legacy_slot = state.latest_upload_cache.get(kind)
    if isinstance(legacy_slot, dict) and payload_matches_dataset_scope(legacy_slot, resolved):
        return legacy_slot
    return None


def cache_latest_upload_payload(kind: str, payload: dict[str, Any] | None) -> None:
    _cache_set(kind, payload)


def runtime_state() -> UploadRuntimeState:
    return UPLOAD_RUNTIME_STATE


def configure_runtime_dir(path: str | os.PathLike[str]) -> None:
    runtime_state().configure_runtime_dir(path)


def _runtime_db_latest_enabled() -> bool:
    return os.getenv("PYTEST_CURRENT_TEST") is None and os.getenv("NERAIUM_DISABLE_RUNTIME_DB_LATEST", "0") != "1"


def _upload_state_bucket() -> str:
    return os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", "").strip()


def _external_shared_state_enabled() -> bool:
    return os.getenv("PYTEST_CURRENT_TEST") is None


def shared_state_configured() -> bool:
    return _external_shared_state_enabled() and bool(_upload_state_bucket())


def upload_state_backend() -> str:
    if shared_state_configured():
        return "s3"
    if _runtime_db_latest_enabled():
        return "runtime_db"
    return "local"


def _upload_state_prefix() -> str:
    prefix = os.getenv("NERAIUM_UPLOAD_STATE_PREFIX", "upload-state/").strip()
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    return prefix


def _shared_key(name: str) -> str:
    return str(name).replace(".json", "")


def _s3_object_key(name: str) -> str:
    return f"{_upload_state_prefix()}{_shared_key(name)}.json"


def _upload_source_object_key(job_id: str, filename: str | None = None, *, scope: DatasetScope | None = None) -> str:
    suffix = Path(str(filename or "upload.csv")).suffix or ".csv"
    resolved = scope or current_dataset_scope()
    return f"{_upload_state_prefix()}scopes/{resolved.storage_id}/upload-sources/{job_id}{suffix}"


def persist_upload_source(job_id: str, source_path: str | os.PathLike[str], *, filename: str, content_type: str | None = None) -> str:
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket:
        raise RuntimeError("shared_upload_source_client_unavailable")
    key = _upload_source_object_key(job_id, filename)
    extra_args = {"ContentType": content_type} if content_type else None
    with Path(source_path).open("rb") as handle:
        if hasattr(client, "upload_fileobj"):
            kwargs = {"Fileobj": handle, "Bucket": bucket, "Key": key}
            if extra_args:
                kwargs["ExtraArgs"] = extra_args
            client.upload_fileobj(**kwargs)
        else:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=handle.read(),
                ContentType=content_type or "application/octet-stream",
            )
    return key


def restore_upload_source(job_id: str, source_key: str, *, filename: str | None = None) -> Path:
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket:
        raise RuntimeError("shared_upload_source_client_unavailable")
    upload_root = ensure_storage_root(runtime_state().upload_dir)
    suffix = safe_upload_suffix(filename or source_key)
    with NamedTemporaryFile(delete=False, dir=upload_root, prefix=f"{job_id}-", suffix=suffix) as temp:
        temp_path = Path(temp.name)
    try:
        with temp_path.open("wb") as handle:
            if hasattr(client, "download_fileobj"):
                client.download_fileobj(bucket, source_key, handle)
            else:
                response = client.get_object(Bucket=bucket, Key=source_key)
                handle.write(response["Body"].read())
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    return temp_path


def delete_upload_source(source_key: str | None) -> None:
    if not source_key:
        return
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket:
        return
    try:
        if hasattr(client, "delete_object"):
            client.delete_object(Bucket=bucket, Key=source_key)
    except Exception:
        logger.exception("shared_upload_source_delete_failed bucket=%s key=%s", bucket, source_key)


def _get_s3_client() -> Any | None:
    state = runtime_state()
    if state.upload_state_s3_client is not None:
        return state.upload_state_s3_client
    if not _external_shared_state_enabled() or not _upload_state_bucket():
        return None
    try:
        import boto3  # type: ignore

        state.upload_state_s3_client = boto3.client("s3")
        return state.upload_state_s3_client
    except Exception:
        return None




def _shared_state_error_code(error: Exception) -> str:
    response = getattr(error, "response", None)
    if not isinstance(response, dict):
        return ""
    error_payload = response.get("Error")
    if not isinstance(error_payload, dict):
        return ""
    return str(error_payload.get("Code") or "").strip()


def _is_missing_shared_state_error(error: Exception) -> bool:
    return _shared_state_error_code(error) in {"404", "NoSuchKey", "NotFound"}


def read_local_json(name: str, *, scope: DatasetScope | None = None) -> dict[str, Any] | None:
    path = runtime_state().runtime_dir / _local_state_name(name, scope=scope)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_local_json(name: str, payload: dict[str, Any], *, scope: DatasetScope | None = None) -> None:
    state = runtime_state()
    path = state.runtime_dir / _local_state_name(name, scope=scope, payload=payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def _read_s3_state(storage_name: str, bucket: str) -> dict[str, Any] | None:
    client = _get_s3_client()
    if client is None:
        return None
    try:
        response = client.get_object(Bucket=bucket, Key=_s3_object_key(storage_name))
        body = response["Body"].read().decode("utf-8")
        payload = json.loads(body)
        return payload if isinstance(payload, dict) else None
    except Exception as error:
        if not _is_missing_shared_state_error(error):
            logger.warning("shared_state_read_failed backend=s3")
        return None


def _read_runtime_db_state(storage_name: str) -> dict[str, Any] | None:
    if not _runtime_db_latest_enabled():
        return None
    try:
        payload = read_latest_payload(_shared_key(storage_name))
        return payload if isinstance(payload, dict) else None
    except Exception:
        logger.warning("shared_state_read_failed backend=runtime_db")
        return None


def read_shared_state(name: str, *, scope: DatasetScope | None = None) -> dict[str, Any] | None:
    storage_name = _state_name(name, scope=scope)
    bucket = _upload_state_bucket() if _external_shared_state_enabled() else ""
    if bucket:
        payload = _read_s3_state(storage_name, bucket)
        if isinstance(payload, dict):
            return payload
    return _read_runtime_db_state(storage_name)


def write_shared_state(name: str, payload: dict[str, Any], *, scope: DatasetScope | None = None) -> None:
    normalized = dict(payload or {})
    storage_name = _state_name(name, scope=scope, payload=normalized)
    try:
        upsert_latest_payload(_shared_key(storage_name), normalized)
    except Exception:
        logger.error("shared_state_write_failed backend=runtime_db")
    bucket = _upload_state_bucket()
    if bucket:
        client = _get_s3_client()
        if client is not None:
            try:
                client.put_object(
                    Bucket=bucket,
                    Key=_s3_object_key(storage_name),
                    Body=json.dumps(normalized, indent=2, default=str).encode("utf-8"),
                    ContentType="application/json",
                )
            except Exception:
                logger.error("shared_state_write_failed backend=s3")


def write_upload_result(job_id: str, payload: dict[str, Any]) -> None:
    normalized = attach_dataset_scope(dict(payload or {}), dataset_id=job_id)
    write_local_json(f"upload_result_{job_id}.json", normalized)
    write_shared_state(f"upload_result_{job_id}", normalized)


def write_upload_status(job_id: str, payload: dict[str, Any]) -> None:
    normalized = attach_dataset_scope(dict(payload or {}), dataset_id=job_id)
    write_local_json(f"upload_status_{job_id}.json", normalized)
    write_shared_state(f"upload_status_{job_id}", normalized)


def write_upload_status_progress(
    job_id: str,
    payload: dict[str, Any],
    *,
    latest_summary: dict[str, Any] | None = None,
    keep_result: bool = False,
) -> dict[str, Any]:
    normalized_payload = dict(payload or {}) if isinstance(payload, dict) else {}
    normalized_payload["job_id"] = str(job_id)
    write_upload_status(str(job_id), normalized_payload)
    summary_payload = dict(latest_summary or normalized_payload)
    write_latest_upload_summary_payload(summary_payload)
    persist_latest_upload_state(summary=summary_payload, result=None, keep_result=keep_result)
    return summary_payload


def write_latest_upload_result_payload(payload: dict[str, Any]) -> None:
    normalized = attach_dataset_scope(dict(payload or {}), dataset_id=payload.get("dataset_id") or payload.get("job_id"))
    scope = _state_scope(payload=normalized)
    write_local_json("latest_upload_result.json", normalized, scope=scope)
    write_shared_state("latest_upload_result", normalized, scope=scope)
    _cache_set("result", normalized, scope=scope)


def write_latest_upload_summary_payload(payload: dict[str, Any]) -> None:
    normalized = attach_dataset_scope(dict(payload or {}), dataset_id=payload.get("dataset_id") or payload.get("job_id"))
    scope = _state_scope(payload=normalized)
    write_local_json("latest_upload_summary.json", normalized, scope=scope)
    write_shared_state("latest_upload_summary", normalized, scope=scope)
    _cache_set("summary", normalized, scope=scope)


def write_upload_completion(job_id: str, *, result: dict[str, Any], summary: dict[str, Any]) -> None:
    scope = _state_scope(payload=result or summary)
    normalized_result = attach_dataset_scope(dict(result or {}) if isinstance(result, dict) else {}, scope=scope, dataset_id=job_id)
    normalized_summary = attach_dataset_scope(dict(summary or {}) if isinstance(summary, dict) else {}, scope=scope, dataset_id=job_id)
    normalized_result.setdefault("job_id", str(job_id))
    normalized_result.setdefault("run_id", str(job_id))
    normalized_result.setdefault("upload_id", str(job_id))
    normalized_result["session_scope"] = build_session_scope(
        str(job_id),
        filename=normalized_result.get("filename"),
        status="active",
        dataset_scope=scope,
    )
    normalized_summary.setdefault("job_id", str(job_id))
    normalized_summary.setdefault("run_id", str(job_id))
    normalized_summary.setdefault("upload_id", str(job_id))
    normalized_summary["session_scope"] = build_session_scope(
        str(job_id),
        filename=normalized_summary.get("filename") or normalized_result.get("filename"),
        status=str(normalized_summary.get("processing_state") or normalized_summary.get("status") or "active").lower(),
        dataset_scope=scope,
    )
    write_upload_result(job_id, normalized_result)
    write_upload_status(job_id, normalized_summary)
    write_latest_upload_result_payload(normalized_result)
    write_latest_upload_summary_payload(normalized_summary)
    persist_latest_upload_state(summary=normalized_summary, result=normalized_result)


def write_latest_upload_record(record: dict[str, Any] | None) -> dict[str, Any]:
    payload = build_empty_latest_upload_record() if not isinstance(record, dict) else dict(record)
    payload = attach_dataset_scope(payload, dataset_id=payload.get("dataset_id") or payload.get("job_id"))
    scope = _state_scope(payload=payload)
    write_local_json("latest_upload.json", payload, scope=scope)
    write_shared_state("latest_upload", payload, scope=scope)
    _cache_set("canonical", payload, scope=scope)
    runtime_state().reset_blocked_scopes.discard(scope.storage_id)
    _invalidate_router_latest_cache()
    return payload


def read_latest_upload_record() -> dict[str, Any] | None:
    scope = current_dataset_scope()
    persisted = read_shared_state("latest_upload", scope=scope)
    if isinstance(persisted, dict) and payload_matches_dataset_scope(persisted, scope):
        _cache_set("canonical", persisted, scope=scope)
        return persisted
    cached = _cache_get("canonical", scope=scope)
    if isinstance(cached, dict):
        return cached
    local = read_local_json("latest_upload.json", scope=scope)
    return local if payload_matches_dataset_scope(local, scope) else None


def read_current_upload_result() -> dict[str, Any] | None:
    return select_current_upload_result(read_latest_upload_record())


def _payload_identity_values(payload: dict[str, Any] | None) -> set[str]:
    if not isinstance(payload, dict):
        return set()
    values = set(value for value in normalize_upload_identity(payload) if value)
    scope = payload.get("session_scope") if isinstance(payload.get("session_scope"), dict) else {}
    for key in ("job_id", "run_id", "upload_id"):
        value = str(scope.get(key) or "").strip()
        if value:
            values.add(value)
    return values


def _record_identity_values(record: dict[str, Any] | None) -> set[str]:
    if not isinstance(record, dict):
        return set()
    values = _payload_identity_values(record)
    values.update(_payload_identity_values(record.get("summary") if isinstance(record.get("summary"), dict) else None))
    values.update(_payload_identity_values(record.get("result") if isinstance(record.get("result"), dict) else None))
    return values


def identity_matches(record: dict[str, Any] | None, requested_id: str | None) -> bool:
    requested = str(requested_id or "").strip()
    return bool(requested) and requested in _record_identity_values(record)


def resolve_upload_artifacts(job_id: str | None = None) -> dict[str, Any]:
    requested_id = str(job_id or "").strip()
    record = read_latest_upload_record() or {}
    if requested_id and not identity_matches(record, requested_id):
        record = {}

    summary = record.get("summary") if isinstance(record.get("summary"), dict) else None
    record_result = record.get("result") if isinstance(record.get("result"), dict) else None
    result = read_upload_result_by_job_id(requested_id) if requested_id else None
    if isinstance(result, dict) and not payload_matches_dataset_scope(result):
        result = None
    if not isinstance(result, dict):
        result = record_result if isinstance(record_result, dict) and payload_matches_dataset_scope(record_result) else None

    canonical_job_id, canonical_run_id, canonical_upload_id = normalize_upload_identity(result or summary or record)
    active_result = result if has_active_session_artifact(result, job_id=canonical_job_id or requested_id or None) else None
    replay = build_replay_payload_from_result(active_result or result, job_id=canonical_job_id or requested_id or None)

    evidence = None
    evidence_identity = canonical_job_id or canonical_run_id or canonical_upload_id or requested_id
    if evidence_identity:
        try:
            from app.services.evidence_store import read_evidence_run

            evidence = read_evidence_run(evidence_identity)
        except Exception:
            evidence = None

    return {
        "requested_id": requested_id or None,
        "record": record if isinstance(record, dict) else {},
        "summary": summary,
        "result": result,
        "active_result": active_result,
        "replay": replay,
        "evidence": evidence,
        "job_id": canonical_job_id or requested_id or None,
        "run_id": canonical_run_id or canonical_job_id or requested_id or None,
        "upload_id": canonical_upload_id or canonical_job_id or requested_id or None,
    }


def read_replay_payload(job_id: str | None = None) -> dict[str, Any]:
    artifacts = resolve_upload_artifacts(job_id)
    payload = dict(artifacts.get("replay") or {})
    if job_id and not isinstance(artifacts.get("result"), dict):
        payload["message"] = "No replay is available for the requested upload job."
    return payload


def read_evidence_by_identity(job_id: str | None = None) -> dict[str, Any] | None:
    artifacts = resolve_upload_artifacts(job_id)
    evidence = artifacts.get("evidence")
    return evidence if isinstance(evidence, dict) else None


def persist_latest_upload_state(
    *,
    summary: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    keep_result: bool = True,
) -> dict[str, Any]:
    scope = _state_scope(payload=result or summary)
    retained_result = result
    if keep_result and retained_result is None:
        cached_result = _cache_get("result", scope=scope)
        retained_result = cached_result if isinstance(cached_result, dict) else read_latest_upload_result()
    if isinstance(retained_result, dict) and not payload_matches_dataset_scope(retained_result, scope):
        retained_result = None
    evidence_record = None
    job_id, _, _ = normalize_upload_identity(retained_result or summary)
    if job_id:
        try:
            from app.services.evidence_store import read_evidence_run

            evidence_record = read_evidence_run(job_id)
        except Exception:
            evidence_record = None
    record = build_latest_upload_record(
        summary=summary,
        result=retained_result if keep_result else None,
        evidence=evidence_record,
    )
    return write_latest_upload_record(record)


def warm_latest_upload_cache() -> None:
    state = runtime_state()
    # Startup has no authenticated workspace. Do not hydrate an arbitrary global
    # latest object; scoped records are restored lazily for the requesting scope.
    state.latest_upload_cache.clear()
    state.latest_upload_cache.update({"summary": None, "result": None, "canonical": None})
    state.reset_blocked_scopes.clear()
    state.reset_block_persisted = False


def read_latest_upload_result() -> dict[str, Any] | None:
    scope = current_dataset_scope()
    persisted = read_shared_state("latest_upload_result", scope=scope)
    if isinstance(persisted, dict) and payload_matches_dataset_scope(persisted, scope):
        _cache_set("result", persisted, scope=scope)
        return persisted
    cached = _cache_get("result", scope=scope)
    if isinstance(cached, dict):
        return cached
    local = read_local_json("latest_upload_result.json", scope=scope)
    return local if payload_matches_dataset_scope(local, scope) else None


def read_latest_upload_summary() -> dict[str, Any] | None:
    scope = current_dataset_scope()
    persisted = read_shared_state("latest_upload_summary", scope=scope)
    if isinstance(persisted, dict) and payload_matches_dataset_scope(persisted, scope):
        _cache_set("summary", persisted, scope=scope)
        return persisted
    cached = _cache_get("summary", scope=scope)
    if isinstance(cached, dict):
        return cached
    local = read_local_json("latest_upload_summary.json", scope=scope)
    return local if payload_matches_dataset_scope(local, scope) else None


def read_upload_result_by_job_id(job_id: str) -> dict[str, Any] | None:
    persisted = read_shared_state(f"upload_result_{job_id}")
    if isinstance(persisted, dict):
        return persisted
    return read_local_json(f"upload_result_{job_id}.json")


def read_upload_status(job_id: str) -> dict[str, Any] | None:
    persisted = read_shared_state(f"upload_status_{job_id}")
    if isinstance(persisted, dict):
        runtime_state().cache_job(job_id, persisted)
        return persisted
    cached = runtime_state().jobs.get(job_id)
    if isinstance(cached, dict):
        return cached
    return read_local_json(f"upload_status_{job_id}.json")


def clear_reset_block_persisted(scope: DatasetScope | None = None) -> None:
    resolved = scope or current_dataset_scope()
    runtime_state().reset_blocked_scopes.discard(resolved.storage_id)
    runtime_state().reset_block_persisted = False


def reset_block_persisted_active(scope: DatasetScope | None = None) -> bool:
    resolved = scope or current_dataset_scope()
    return resolved.storage_id in runtime_state().reset_blocked_scopes


def _attach_traceability(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or not payload.get("filename"):
        return payload
    try:
        from app.services.upload_evidence import build_traceability_packet

        payload["traceability"] = build_traceability_packet(
            job_id=str(payload.get("job_id") or ""),
            filename=str(payload.get("filename") or ""),
            result=payload,
        )
    except Exception:
        return payload
    if isinstance(payload.get("traceability"), dict):
        payload["decision_integrity"] = dict(payload["traceability"])
    return payload


def write_latest_upload_result(*args) -> None:
    result = args[0] if len(args) == 1 else args[1] if len(args) >= 2 else {}
    payload = dict(result or {}) if isinstance(result, dict) else {}

    if len(args) >= 2:
        job_id = str(args[0])
        payload["job_id"] = job_id
        payload["run_id"] = job_id
        payload["upload_id"] = job_id

    scope = _state_scope(payload=payload)
    clear_reset_block_persisted(scope)
    payload["session_scope"] = build_session_scope(
        payload.get("job_id"),
        filename=payload.get("filename"),
        status="active",
        dataset_scope=scope,
    )
    payload = attach_dataset_scope(payload, scope=scope, dataset_id=payload.get("job_id"))
    payload = _attach_traceability(payload)

    if payload.get("job_id"):
        write_upload_result(str(payload["job_id"]), payload)
    write_latest_upload_result_payload(payload)

    if payload.get("job_id"):
        latest_summary = summarize_result_payload(payload)
        write_latest_upload_summary_payload(latest_summary)
        write_upload_status(str(payload["job_id"]), latest_summary)
        persist_latest_upload_state(summary=latest_summary, result=payload)
    else:
        _invalidate_router_latest_cache()


def write_latest_upload_summary(*args, **kwargs) -> None:
    del kwargs
    summary = args[0] if len(args) == 1 else args[1] if len(args) >= 2 else {}
    payload = dict(summary or {}) if isinstance(summary, dict) else {}

    if len(args) >= 2:
        job_id = str(args[0])
        payload["job_id"] = job_id
        payload["run_id"] = job_id
        payload["upload_id"] = job_id

    payload.setdefault("status", "COMPLETE")
    scope = _state_scope(payload=payload)
    clear_reset_block_persisted(scope)
    payload["session_scope"] = build_session_scope(
        payload.get("job_id"),
        filename=payload.get("filename"),
        status="active",
        dataset_scope=scope,
    )
    payload = attach_dataset_scope(payload, scope=scope, dataset_id=payload.get("job_id"))
    if payload.get("job_id") and "status_url" not in payload:
        payload["status_url"] = f"/api/data/upload-status/{payload['job_id']}"

    write_latest_upload_summary_payload(payload)
    if payload.get("job_id"):
        write_upload_status(str(payload["job_id"]), payload)
        persist_latest_upload_state(
            summary=payload,
            result=read_upload_result_by_job_id(str(payload["job_id"])),
            keep_result=True,
        )
    else:
        persist_latest_upload_state(summary=payload, result=None, keep_result=True)


def _clear_latest_cache_for_scope(state: UploadRuntimeState, scope: DatasetScope) -> None:
    for kind in ("summary", "result", "canonical"):
        state.latest_upload_cache.pop(_cache_key(kind, scope), None)
        cached = state.latest_upload_cache.get(kind)
        if isinstance(cached, dict) and payload_matches_dataset_scope(cached, scope):
            state.latest_upload_cache[kind] = None


def _delete_local_latest_state(state: UploadRuntimeState, scope: DatasetScope) -> None:
    local_scope_dir = state.runtime_dir / "scopes" / scope.storage_id
    for name in _SCOPED_LATEST_NAMES:
        try:
            (local_scope_dir / f"{name}.json").unlink(missing_ok=True)
        except OSError:
            pass


def _delete_database_latest_state(scope_prefix: str) -> None:
    try:
        delete_latest_payload_prefix(scope_prefix)
    except Exception:
        pass


def _delete_s3_latest_state(scope_prefix: str) -> None:
    bucket = _upload_state_bucket()
    client = _get_s3_client() if bucket else None
    if client is None or not bucket:
        return
    for name in _SCOPED_LATEST_NAMES:
        try:
            client.delete_object(Bucket=bucket, Key=_s3_object_key(f"{scope_prefix}{name}"))
        except Exception:
            logger.error("scoped_upload_state_delete_failed backend=s3")


def reset_upload_state() -> None:
    state = runtime_state()
    scope = current_dataset_scope()
    scope_prefix = f"scopes/{scope.storage_id}/"
    _clear_latest_cache_for_scope(state, scope)
    _delete_local_latest_state(state, scope)
    _delete_database_latest_state(scope_prefix)
    _delete_s3_latest_state(scope_prefix)
    state.reset_blocked_scopes.add(scope.storage_id)
    state.reset_block_persisted = False
    _invalidate_router_latest_cache()


def _invalidate_router_latest_cache() -> None:
    try:
        from app.routers import data as data_router

        data_router.invalidate_latest_upload_cache()
    except Exception:
        pass
