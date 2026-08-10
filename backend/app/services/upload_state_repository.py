from __future__ import annotations

import hashlib
import json
import os
import logging
import re
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterator

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
    insert_latest_payload_if_absent,
    list_latest_payloads_prefix,
    list_latest_payloads_prefix_pure,
    read_latest_payload,
    read_latest_payload_pure,
    upsert_latest_payload,
)
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE, UploadRuntimeState
from app.services.upload_persistence import project_result_for_transport, summarize_result as summarize_result_payload
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

_TERMINAL_UPLOAD_STATES = {
    "cancelled",
    "complete",
    "completed",
    "completed_compatibility",
    "error",
    "failed",
    "failure",
    "success",
    "timeout",
    "validation_error",
}
_SUCCESS_UPLOAD_STATES = {"complete", "completed", "completed_compatibility", "success"}
_ACTIVE_UPLOAD_STATES = {"accepted", "pending", "processing", "queued", "running", "running_sii", "uploading"}
_TERMINAL_STATE_CONTRACT_VERSION = "upload-terminal-state.v1"
_TERMINAL_RESULT_CONTRACT_VERSION = "upload-terminal-result.v1"
_UPLOAD_PUBLICATION_LOCKS = tuple(threading.RLock() for _ in range(64))
_UNSET_UPLOAD_STATUS = object()


def _is_scope_bound_state(raw_name: str) -> bool:
    return raw_name in _SCOPED_LATEST_NAMES or raw_name.startswith(
        ("upload_status_", "upload_result_", "upload_terminal_")
    )


def _upload_state_value(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    values = [
        str(payload.get(field) or "").strip().lower()
        for field in ("processing_state", "status", "job_state")
    ]
    # Treat any explicit terminal field as terminal even if a stale
    # compatibility field still says "processing".
    return next(
        (value for value in values if value in _TERMINAL_UPLOAD_STATES),
        next((value for value in values if value), ""),
    )


def _is_terminal_upload_state(payload: dict[str, Any] | None) -> bool:
    return _upload_state_value(payload) in _TERMINAL_UPLOAD_STATES


def _upload_attempt_id(job_id: str, payload: dict[str, Any] | None = None) -> str:
    if isinstance(payload, dict):
        explicit = str(payload.get("attempt_id") or "").strip()
        if explicit:
            return explicit
    return str(job_id)


def _terminal_state_name(job_id: str, payload: dict[str, Any] | None = None) -> str:
    attempt_digest = hashlib.sha256(_upload_attempt_id(job_id, payload).encode("utf-8")).hexdigest()[:24]
    return f"upload_terminal_{job_id}_{attempt_digest}"


def _terminal_result_digest(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _terminal_result_state_name(
    job_id: str,
    payload: dict[str, Any] | None,
) -> str:
    attempt_digest = hashlib.sha256(_upload_attempt_id(job_id, payload).encode("utf-8")).hexdigest()[:24]
    return f"upload_terminal_result_{job_id}_{attempt_digest}"


@contextmanager
def upload_job_publication_lock(job_id: str) -> Iterator[None]:
    """Serialize same-process publication without retaining one lock per job."""
    digest = hashlib.sha256(str(job_id).encode("utf-8")).digest()
    lock = _UPLOAD_PUBLICATION_LOCKS[int.from_bytes(digest[:4], "big") % len(_UPLOAD_PUBLICATION_LOCKS)]
    with lock:
        yield


def _state_scope(*, scope: DatasetScope | None = None, payload: dict[str, Any] | None = None) -> DatasetScope:
    return scope or dataset_scope_from_payload(payload) or current_dataset_scope()


def _state_name(name: str, *, scope: DatasetScope | None = None, payload: dict[str, Any] | None = None) -> str:
    raw_name = str(name).replace(".json", "")
    if not _is_scope_bound_state(raw_name):
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


def _runtime_db_latest_write_enabled() -> bool:
    return os.getenv("NERAIUM_DISABLE_RUNTIME_DB_LATEST", "0") != "1"


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


UPLOAD_SOURCE_TAGGING = "neraium-upload-source=true"


def create_presigned_upload_target(
    job_id: str,
    *,
    filename: str,
    content_type: str,
    expires_in_seconds: int = 3600,
) -> dict[str, Any]:
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket or not hasattr(client, "generate_presigned_url"):
        raise RuntimeError("large_upload_storage_unavailable")
    key = _upload_source_object_key(job_id, filename)
    normalized_content_type = str(content_type or "application/octet-stream")
    url = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": normalized_content_type,
            "Tagging": UPLOAD_SOURCE_TAGGING,
            "IfNoneMatch": "*",
        },
        ExpiresIn=max(60, min(int(expires_in_seconds), 3600)),
        HttpMethod="PUT",
    )
    return {
        "object_key": key,
        "upload_url": url,
        "upload_headers": {
            "Content-Type": normalized_content_type,
            "x-amz-tagging": UPLOAD_SOURCE_TAGGING,
            "If-None-Match": "*",
        },
    }


def inspect_upload_source(source_key: str) -> dict[str, Any]:
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket or not hasattr(client, "head_object"):
        raise RuntimeError("large_upload_storage_unavailable")
    response = client.head_object(Bucket=bucket, Key=str(source_key))
    return {
        "content_length": int(response.get("ContentLength") or 0),
        "content_type": str(response.get("ContentType") or ""),
        "etag": str(response.get("ETag") or "").strip('"'),
    }


def resolve_existing_upload_source_key(job_id: str, filename: str | None = None) -> str | None:
    """Resolve a retry source without trusting a client-provided object key."""
    source_key = _upload_source_object_key(str(job_id), filename)
    try:
        inspect_upload_source(source_key)
    except Exception:
        return None
    return source_key


def _large_upload_session_name(session_id: str, *, scope: DatasetScope | None = None) -> str:
    resolved = scope or current_dataset_scope()
    return f"scopes/{resolved.storage_id}/large-upload-sessions/{session_id}"


def write_large_upload_session(session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    scope = dataset_scope_from_payload(payload) or current_dataset_scope()
    normalized = attach_dataset_scope(dict(payload or {}), scope=scope, dataset_id=session_id)
    normalized["upload_session_id"] = str(session_id)
    name = _large_upload_session_name(session_id, scope=scope)
    write_local_json(f"{name}.json", normalized)
    write_shared_state(name, normalized)
    return normalized


def read_large_upload_session(session_id: str) -> dict[str, Any] | None:
    scope = current_dataset_scope()
    name = _large_upload_session_name(session_id, scope=scope)
    payload = read_shared_state(name, scope=scope) or read_local_json(f"{name}.json", scope=scope)
    return payload if payload_matches_dataset_scope(payload, scope) else None


def persist_upload_source(job_id: str, source_path: str | os.PathLike[str], *, filename: str, content_type: str | None = None) -> str:
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket:
        raise RuntimeError("shared_upload_source_client_unavailable")
    key = _upload_source_object_key(job_id, filename)
    extra_args = {"Tagging": UPLOAD_SOURCE_TAGGING}
    if content_type:
        extra_args["ContentType"] = content_type
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
                Tagging=UPLOAD_SOURCE_TAGGING,
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


def persist_immutable_derived_artifact(
    dataset_id: str,
    source_path: str | os.PathLike[str],
    *,
    artifact_id: str,
    artifact_kind: str,
    content_type: str = "application/octet-stream",
) -> dict[str, Any]:
    """Persist a scoped immutable derived artifact when shared storage is configured."""

    clean_dataset_id = str(dataset_id or "").strip()
    clean_artifact_id = str(artifact_id or "").strip().lower()
    clean_kind = str(artifact_kind or "").strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", clean_dataset_id):
        raise ValueError("invalid_derived_artifact_dataset_id")
    if not re.fullmatch(r"[a-f0-9]{64}", clean_artifact_id):
        raise ValueError("invalid_derived_artifact_id")
    if clean_kind not in {"raw", "canonical", "profile"}:
        raise ValueError("invalid_derived_artifact_kind")
    digest = hashlib.sha256()
    with Path(source_path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != clean_artifact_id:
        raise ValueError("derived_artifact_digest_mismatch")
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket:
        return {"backend": "scoped_local", "artifact_id": clean_artifact_id}
    scope = current_dataset_scope()
    key = (
        f"{_upload_state_prefix()}/scopes/{scope.storage_id}/historical-ingestion/"
        f"{clean_dataset_id}/{clean_kind}/{clean_artifact_id}.artifact"
    )
    with Path(source_path).open("rb") as handle:
        if hasattr(client, "put_object"):
            try:
                client.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=handle,
                    ContentType=content_type,
                    Tagging="neraium-artifact=historical-derived",
                    Metadata={"sha256": clean_artifact_id, "immutability": "content-addressed"},
                    IfNoneMatch="*",
                )
            except Exception as exc:
                response = getattr(exc, "response", {})
                error = response.get("Error", {}) if isinstance(response, dict) else {}
                status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode") if isinstance(response, dict) else None
                if status != 412 and str(error.get("Code") or "") not in {"PreconditionFailed", "412"}:
                    raise
        else:
            # Compatibility for storage doubles without conditional PUT. The
            # production S3 client follows the atomic If-None-Match path above.
            client.upload_fileobj(
                Fileobj=handle,
                Bucket=bucket,
                Key=key,
                ExtraArgs={
                    "ContentType": content_type,
                    "Tagging": "neraium-artifact=historical-derived",
                    "Metadata": {"sha256": clean_artifact_id, "immutability": "content-addressed"},
                },
            )
    return {"backend": "s3_immutable", "artifact_id": clean_artifact_id, "object_key": key}


def restore_immutable_derived_artifact(reference: dict[str, Any]) -> Path:
    artifact_id = str((reference or {}).get("artifact_id") or "").strip().lower()
    object_key = str((reference or {}).get("object_key") or "").strip()
    if not re.fullmatch(r"[a-f0-9]{64}", artifact_id) or not object_key:
        raise ValueError("invalid_derived_artifact_reference")
    scope = current_dataset_scope()
    required_fragment = f"/scopes/{scope.storage_id}/historical-ingestion/"
    if required_fragment not in f"/{object_key}":
        raise ValueError("derived_artifact_scope_mismatch")
    client = _get_s3_client()
    bucket = _upload_state_bucket()
    if client is None or not bucket:
        raise RuntimeError("shared_derived_artifact_client_unavailable")
    upload_root = ensure_storage_root(runtime_state().upload_dir)
    with NamedTemporaryFile(delete=False, dir=upload_root, prefix="historical-derived-", suffix=".artifact") as temp:
        path = Path(temp.name)
    try:
        with path.open("wb") as output:
            if hasattr(client, "download_fileobj"):
                client.download_fileobj(bucket, object_key, output)
            else:
                response = client.get_object(Bucket=bucket, Key=object_key)
                output.write(response["Body"].read())
        digest = hashlib.sha256()
        with path.open("rb") as restored:
            for chunk in iter(lambda: restored.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != artifact_id:
            raise RuntimeError("derived_artifact_digest_mismatch")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


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


def _get_s3_state_client() -> Any | None:
    state = runtime_state()
    if state.upload_state_s3_read_client is not None:
        return state.upload_state_s3_read_client
    if not _external_shared_state_enabled() or not _upload_state_bucket():
        return None
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore

        state.upload_state_s3_read_client = boto3.client(
            "s3",
            config=Config(
                connect_timeout=2,
                read_timeout=4,
                retries={"total_max_attempts": 1, "mode": "standard"},
            ),
        )
        return state.upload_state_s3_read_client
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
    client = _get_s3_state_client()
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


def _read_s3_state_pure(storage_name: str, bucket: str) -> dict[str, Any] | None:
    """Read S3 state without suppressing integrity or availability failures."""
    client = _get_s3_state_client()
    if client is None:
        raise RuntimeError("shared_state_client_unavailable")
    try:
        response = client.get_object(Bucket=bucket, Key=_s3_object_key(storage_name))
    except Exception as error:
        if _is_missing_shared_state_error(error):
            return None
        raise RuntimeError("shared_state_read_failed") from error
    payload = json.loads(response["Body"].read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("shared_state_payload_not_object")
    return payload


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
    # A configured S3 bucket is the cross-process source of truth. API and
    # worker tasks can each have a valid but divergent runtime database, so a
    # process-local row must not shadow a newer shared worker update.
    bucket = _upload_state_bucket() if _external_shared_state_enabled() else ""
    if bucket:
        shared_payload = _read_s3_state(storage_name, bucket)
        if isinstance(shared_payload, dict):
            return shared_payload
    database_payload = _read_runtime_db_state(storage_name)
    if isinstance(database_payload, dict):
        return database_payload
    return None


def _read_legacy_unscoped_state(name: str) -> dict[str, Any] | None:
    """Read a pre-scope per-job object for a verified migration fallback."""
    storage_name = str(name).replace(".json", "")
    database_payload = _read_runtime_db_state(storage_name)
    if isinstance(database_payload, dict):
        return database_payload
    bucket = _upload_state_bucket() if _external_shared_state_enabled() else ""
    return _read_s3_state(storage_name, bucket) if bucket else None


def _read_legacy_unscoped_local(name: str) -> dict[str, Any] | None:
    path = runtime_state().runtime_dir / f"{str(name).replace('.json', '')}.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def read_shared_state_pure(name: str, *, scope: DatasetScope | None = None) -> dict[str, Any] | None:
    """Read shared state without initializing storage or mutating cache state."""
    storage_name = _state_name(name, scope=scope)
    bucket = _upload_state_bucket() if _external_shared_state_enabled() else ""
    if bucket:
        payload = _read_s3_state_pure(storage_name, bucket)
        if payload is not None:
            return payload
    if _runtime_db_latest_write_enabled():
        payload = read_latest_payload_pure(_shared_key(storage_name))
        if payload is not None and not isinstance(payload, dict):
            raise ValueError("shared_state_payload_not_object")
        if payload is not None:
            return payload
    path = runtime_state().runtime_dir / _local_state_name(storage_name, scope=scope)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("shared_state_payload_not_object")
    return payload


def list_shared_state_prefix(name: str, *, scope: DatasetScope | None = None) -> list[dict[str, Any]]:
    """Enumerate immutable records under a key prefix without mutating storage."""
    storage_name = _state_name(name, scope=scope)
    bucket = _upload_state_bucket() if _external_shared_state_enabled() else ""
    if bucket:
        client = _get_s3_state_client()
        if client is None:
            return []
        payloads: list[dict[str, Any]] = []
        continuation: str | None = None
        try:
            while True:
                kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": _s3_object_key(storage_name).removesuffix(".json")}
                if continuation:
                    kwargs["ContinuationToken"] = continuation
                response = client.list_objects_v2(**kwargs)
                for item in response.get("Contents", []):
                    key = str(item.get("Key") or "")
                    if not key:
                        continue
                    body = client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
                    payload = json.loads(body)
                    if isinstance(payload, dict):
                        payloads.append(payload)
                if not response.get("IsTruncated"):
                    break
                continuation = str(response.get("NextContinuationToken") or "") or None
            return payloads
        except Exception:
            logger.warning("shared_state_list_failed backend=s3")
            return []
    if _runtime_db_latest_enabled():
        try:
            return [item for item in list_latest_payloads_prefix(_shared_key(storage_name)) if isinstance(item, dict)]
        except Exception:
            logger.warning("shared_state_list_failed backend=runtime_db")
            return []
    root = runtime_state().runtime_dir / _local_state_name(storage_name, scope=scope)
    prefix_path = Path(str(root).removesuffix(".json"))
    if not prefix_path.exists():
        return []
    payloads = []
    for path in sorted(prefix_path.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def list_shared_state_prefix_pure(name: str, *, scope: DatasetScope | None = None) -> list[dict[str, Any]]:
    """Enumerate shared state without initializing tables, directories, or caches."""
    storage_name = _state_name(name, scope=scope)
    bucket = _upload_state_bucket() if _external_shared_state_enabled() else ""
    if bucket:
        client = _get_s3_state_client()
        if client is None:
            raise RuntimeError("shared_state_client_unavailable")
        payloads: list[dict[str, Any]] = []
        continuation: str | None = None
        while True:
            kwargs: dict[str, Any] = {
                "Bucket": bucket,
                "Prefix": _s3_object_key(storage_name).removesuffix(".json"),
            }
            if continuation:
                kwargs["ContinuationToken"] = continuation
            response = client.list_objects_v2(**kwargs)
            for item in response.get("Contents", []):
                key = str(item.get("Key") or "")
                if not key:
                    continue
                body = client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError("shared_state_payload_not_object")
                payloads.append(payload)
            if not response.get("IsTruncated"):
                return payloads
            continuation = str(response.get("NextContinuationToken") or "") or None
    if _runtime_db_latest_write_enabled():
        payloads = list_latest_payloads_prefix_pure(_shared_key(storage_name))
        if any(not isinstance(payload, dict) for payload in payloads):
            raise ValueError("shared_state_payload_not_object")
        return payloads
    prefix_path = runtime_state().runtime_dir / storage_name
    if not prefix_path.exists():
        return []
    payloads = []
    for path in sorted(prefix_path.rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("shared_state_payload_not_object")
        payloads.append(payload)
    return payloads


def write_shared_state(name: str, payload: dict[str, Any], *, scope: DatasetScope | None = None) -> None:
    normalized = dict(payload or {})
    storage_name = _state_name(name, scope=scope, payload=normalized)
    if _runtime_db_latest_write_enabled():
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


def write_shared_state_strict(name: str, payload: dict[str, Any], *, scope: DatasetScope | None = None) -> None:
    """Write activation-critical state and surface production persistence failures."""
    normalized = dict(payload or {})
    storage_name = _state_name(name, scope=scope, payload=normalized)
    runtime_written = False
    if _runtime_db_latest_write_enabled():
        try:
            upsert_latest_payload(_shared_key(storage_name), normalized)
            runtime_written = True
        except Exception:
            logger.error("shared_state_write_failed backend=runtime_db")

    bucket = _upload_state_bucket()
    if bucket:
        client = _get_s3_client()
        if client is None:
            raise RuntimeError("shared_state_client_unavailable")
        try:
            client.put_object(
                Bucket=bucket,
                Key=_s3_object_key(storage_name),
                Body=json.dumps(normalized, indent=2, default=str).encode("utf-8"),
                ContentType="application/json",
            )
        except Exception as exc:
            logger.error("shared_state_write_failed backend=s3")
            raise RuntimeError("shared_state_write_failed") from exc
        return

    # Tests and single-process development intentionally use local JSON even
    # when the optional runtime latest-payload database is disabled.
    if _runtime_db_latest_write_enabled() and not runtime_written:
        raise RuntimeError("shared_state_write_failed")


def insert_shared_state_strict(
    name: str,
    payload: dict[str, Any],
    *,
    scope: DatasetScope | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Publish an immutable shared-state value and return the canonical stored value."""
    normalized = dict(payload or {})
    storage_name = _state_name(name, scope=scope, payload=normalized)
    bucket = _upload_state_bucket()
    if bucket:
        client = _get_s3_client()
        if client is None:
            raise RuntimeError("shared_state_client_unavailable")
        inserted = True
        try:
            client.put_object(
                Bucket=bucket,
                Key=_s3_object_key(storage_name),
                Body=json.dumps(normalized, indent=2, default=str).encode("utf-8"),
                ContentType="application/json",
                IfNoneMatch="*",
            )
            canonical = normalized
        except Exception as error:
            if _shared_state_error_code(error) not in {
                "PreconditionFailed",
                "412",
                "ConditionalRequestConflict",
                "409",
            }:
                raise RuntimeError("shared_state_write_failed") from error
            inserted = False
            canonical = _read_s3_state(storage_name, bucket)
            if not isinstance(canonical, dict):
                raise RuntimeError("shared_state_existing_value_unavailable") from error
        if _runtime_db_latest_write_enabled():
            upsert_latest_payload(_shared_key(storage_name), canonical)
        write_local_json(f"{storage_name}.json", canonical, scope=scope)
        return inserted, canonical

    if _runtime_db_latest_write_enabled():
        try:
            inserted, canonical = insert_latest_payload_if_absent(_shared_key(storage_name), normalized)
            if not isinstance(canonical, dict):
                raise RuntimeError("shared_state_existing_value_invalid")
            write_local_json(f"{storage_name}.json", canonical, scope=scope)
            return inserted, canonical
        except Exception:
            # A no-bucket deployment already uses the local runtime directory
            # as its fallback authority. Preserve atomic create semantics there
            # if the optional latest-payload database is unavailable.
            logger.warning("shared_state_conditional_write_fallback backend=local")

    path = runtime_state().runtime_dir / _local_state_name(storage_name, scope=scope, payload=normalized)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile("w", delete=False, dir=path.parent, encoding="utf-8") as temporary:
            json.dump(normalized, temporary, indent=2, default=str)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        try:
            os.link(temporary_path, path)
            inserted = True
        except FileExistsError:
            inserted = False
        canonical = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(canonical, dict):
            raise RuntimeError("shared_state_existing_value_invalid")
        return inserted, canonical
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_upload_result(job_id: str, payload: dict[str, Any]) -> None:
    normalized = attach_dataset_scope(dict(payload or {}), dataset_id=payload.get("dataset_id") or job_id)
    write_local_json(f"upload_result_{job_id}.json", normalized)
    write_shared_state(f"upload_result_{job_id}", normalized)


def _write_upload_result_strict(
    job_id: str,
    result: dict[str, Any],
    summary: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Persist one immutable completion bundle before publishing terminal status."""
    normalized_result = attach_dataset_scope(
        dict(result or {}),
        dataset_id=result.get("dataset_id") or job_id,
    )
    normalized_summary = attach_dataset_scope(
        dict(summary or {}),
        scope=_state_scope(payload=normalized_result),
        dataset_id=summary.get("dataset_id") or normalized_result.get("dataset_id") or job_id,
    )
    result_digest = _terminal_result_digest(normalized_result)
    state_name = _terminal_result_state_name(str(job_id), normalized_summary)
    normalized_summary.update(
        {
            "terminal_result_contract_version": _TERMINAL_RESULT_CONTRACT_VERSION,
            "terminal_result_digest": result_digest,
            "terminal_result_ref": state_name,
        }
    )
    bundle = attach_dataset_scope(
        {
            "job_id": str(job_id),
            "attempt_id": _upload_attempt_id(str(job_id), normalized_summary),
            "terminal_result_contract_version": _TERMINAL_RESULT_CONTRACT_VERSION,
            "terminal_result_digest": result_digest,
            "result": normalized_result,
            "summary": normalized_summary,
        },
        scope=_state_scope(payload=normalized_summary),
        dataset_id=normalized_summary.get("dataset_id") or job_id,
    )
    try:
        _, canonical_bundle = insert_shared_state_strict(
            state_name,
            bundle,
            scope=_state_scope(payload=normalized_summary),
        )
    except Exception:
        canonical_bundle = read_shared_state(
            state_name,
            scope=_state_scope(payload=normalized_summary),
        )
        if not isinstance(canonical_bundle, dict):
            raise
        logger.warning(
            "terminal_result_secondary_persistence_failed job_id=%s attempt_id=%s",
            job_id,
            _upload_attempt_id(str(job_id), normalized_summary),
        )
    canonical_result = canonical_bundle.get("result") if isinstance(canonical_bundle, dict) else None
    canonical_summary = canonical_bundle.get("summary") if isinstance(canonical_bundle, dict) else None
    canonical_digest = str((canonical_bundle or {}).get("terminal_result_digest") or "")
    canonical_scope = _state_scope(payload=normalized_summary)
    expected_attempt = _upload_attempt_id(str(job_id), normalized_summary)
    if (
        not isinstance(canonical_result, dict)
        or not isinstance(canonical_summary, dict)
        or canonical_digest != _terminal_result_digest(canonical_result)
        or not payload_matches_dataset_scope(canonical_bundle, canonical_scope)
        or not payload_matches_dataset_scope(canonical_result, canonical_scope)
        or not payload_matches_dataset_scope(canonical_summary, canonical_scope)
        or str(canonical_bundle.get("job_id") or "") != str(job_id)
        or str(canonical_result.get("job_id") or "") != str(job_id)
        or str(canonical_summary.get("job_id") or "") != str(job_id)
        or _upload_attempt_id(str(job_id), canonical_bundle) != expected_attempt
        or _upload_attempt_id(str(job_id), canonical_result) != expected_attempt
        or _upload_attempt_id(str(job_id), canonical_summary) != expected_attempt
    ):
        raise RuntimeError("terminal_result_existing_value_invalid")
    return canonical_result, canonical_summary


def _read_terminal_upload_result(
    job_id: str,
    terminal: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(terminal, dict):
        return None
    result_digest = str(terminal.get("terminal_result_digest") or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", result_digest):
        return None
    scope = _state_scope(payload=terminal)
    name = _terminal_result_state_name(str(job_id), terminal)
    terminal_ref = str(terminal.get("terminal_result_ref") or "").strip()
    if terminal_ref and terminal_ref != name:
        return None
    bundle = read_shared_state(name, scope=scope)
    if not isinstance(bundle, dict):
        bundle = read_local_json(f"{name}.json", scope=scope)
    result = bundle.get("result") if isinstance(bundle, dict) else None
    if (
        not isinstance(bundle, dict)
        or not isinstance(result, dict)
        or not payload_matches_dataset_scope(bundle, scope)
        or not payload_matches_dataset_scope(result, scope)
        or str(bundle.get("job_id") or "") != str(job_id)
        or str(result.get("job_id") or "") != str(job_id)
        or str(bundle.get("attempt_id") or "") != _upload_attempt_id(str(job_id), terminal)
        or str(bundle.get("terminal_result_digest") or "").lower() != result_digest
        or _terminal_result_digest(result) != result_digest
    ):
        return None
    return result


def _write_upload_status_mirror(job_id: str, payload: dict[str, Any]) -> None:
    normalized = attach_dataset_scope(dict(payload or {}), dataset_id=payload.get("dataset_id") or job_id)
    write_local_json(f"upload_status_{job_id}.json", normalized)
    write_shared_state(f"upload_status_{job_id}", normalized)


def _write_upload_attempt_transition_strict(job_id: str, payload: dict[str, Any]) -> None:
    """Durably move the mutable status pointer to an explicit new attempt."""
    normalized = attach_dataset_scope(dict(payload or {}), dataset_id=payload.get("dataset_id") or job_id)
    write_local_json(f"upload_status_{job_id}.json", normalized)
    try:
        write_shared_state_strict(f"upload_status_{job_id}", normalized)
    except Exception:
        if shared_state_configured():
            raise
        logger.warning(
            "upload_attempt_transition_shared_write_fallback backend=local job_id=%s",
            job_id,
        )


def _read_terminal_upload_state(job_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | None:
    scope = _state_scope(payload=payload)
    name = _terminal_state_name(str(job_id), payload)
    expected_attempt = _upload_attempt_id(str(job_id), payload)
    persisted = read_shared_state(name, scope=scope)
    if (
        isinstance(persisted, dict)
        and payload_matches_dataset_scope(persisted, scope)
        and str(persisted.get("job_id") or "") == str(job_id)
        and _upload_attempt_id(str(job_id), persisted) == expected_attempt
    ):
        return persisted
    local = read_local_json(f"{name}.json", scope=scope)
    return (
        local
        if isinstance(local, dict)
        and payload_matches_dataset_scope(local, scope)
        and str(local.get("job_id") or "") == str(job_id)
        and _upload_attempt_id(str(job_id), local) == expected_attempt
        else None
    )


def write_upload_status(
    job_id: str,
    payload: dict[str, Any],
    *,
    _existing_status: dict[str, Any] | None | object = _UNSET_UPLOAD_STATUS,
) -> dict[str, Any]:
    """Publish upload state, using an immutable envelope for terminal attempts."""
    normalized = attach_dataset_scope(dict(payload or {}), dataset_id=payload.get("dataset_id") or job_id)
    normalized["job_id"] = str(job_id)

    with upload_job_publication_lock(str(job_id)):
        existing = (
            _read_upload_status_mirror(str(job_id))
            if _existing_status is _UNSET_UPLOAD_STATUS
            else _existing_status
        )
        existing = existing if isinstance(existing, dict) else None
        normalized.setdefault("attempt_id", _upload_attempt_id(str(job_id), existing))
        existing_attempt = _upload_attempt_id(str(job_id), existing)
        incoming_attempt = _upload_attempt_id(str(job_id), normalized)
        retry_transition = bool(
            normalized.get("retry_requested_at")
            and normalized.get("retry_requested_at") != (existing or {}).get("retry_requested_at")
        )
        incoming_progress = normalized.get("job_progress") if isinstance(normalized.get("job_progress"), dict) else {}
        existing_progress = existing.get("job_progress") if isinstance((existing or {}).get("job_progress"), dict) else {}
        historical_review_transition = bool(
            str(incoming_progress.get("workflow") or "").lower() == "historical_review"
            and (
                str(existing_progress.get("workflow") or "").lower() != "historical_review"
                or str(incoming_progress.get("started_at") or "")
                != str(existing_progress.get("started_at") or "")
            )
        )
        published_terminal = (
            existing
            if _existing_status is not _UNSET_UPLOAD_STATUS
            and _is_terminal_upload_state(existing)
            and existing_attempt == incoming_attempt
            else _read_terminal_upload_state(str(job_id), normalized)
            if _existing_status is _UNSET_UPLOAD_STATUS
            else None
        )

        if (
            _is_terminal_upload_state(normalized)
            and isinstance(existing, dict)
            and incoming_attempt != existing_attempt
        ):
            logger.info(
                "stale_upload_attempt_terminal_prevented job_id=%s active_attempt_id=%s stale_attempt_id=%s",
                job_id,
                existing_attempt,
                incoming_attempt,
            )
            return existing

        if not _is_terminal_upload_state(normalized):
            if (
                isinstance(existing, dict)
                and incoming_attempt != existing_attempt
                and not retry_transition
                and not historical_review_transition
            ):
                logger.info(
                    "stale_upload_attempt_write_prevented job_id=%s active_attempt_id=%s stale_attempt_id=%s",
                    job_id,
                    existing_attempt,
                    incoming_attempt,
                )
                return existing
            if isinstance(published_terminal, dict):
                logger.info(
                    "terminal_state_regression_prevented job_id=%s attempt_id=%s incoming_state=%s",
                    job_id,
                    incoming_attempt,
                    _upload_state_value(normalized),
                )
                return published_terminal
            if (
                _is_terminal_upload_state(existing)
                and existing_attempt == incoming_attempt
            ):
                logger.info(
                    "terminal_state_regression_prevented job_id=%s attempt_id=%s incoming_state=%s",
                    job_id,
                    incoming_attempt,
                    _upload_state_value(normalized),
                )
                return existing
            if retry_transition or historical_review_transition:
                _write_upload_attempt_transition_strict(str(job_id), normalized)
            else:
                _write_upload_status_mirror(str(job_id), normalized)
            # A terminal writer in another process may win immediately after
            # this write. Readers prefer its immutable envelope, and a repeat
            # finalization repairs this secondary mirror.
            return normalized

        if isinstance(published_terminal, dict):
            canonical = published_terminal
            inserted = False
        else:
            logger.info(
                "terminal_state_publication_attempt job_id=%s attempt_id=%s state=%s",
                job_id,
                incoming_attempt,
                _upload_state_value(normalized),
            )
            seed = normalized
            # A pre-v1 terminal record is already externally valid. Preserve it
            # when the first v1 retry establishes the immutable envelope.
            if _is_terminal_upload_state(existing) and existing_attempt == incoming_attempt:
                seed = existing
            seed = {
                **seed,
                "job_id": str(job_id),
                "attempt_id": incoming_attempt,
                "terminal_state_contract_version": _TERMINAL_STATE_CONTRACT_VERSION,
            }
            seed.setdefault(
                "terminal_published_at",
                str(seed.get("completed_at") or seed.get("updated_at") or datetime.now(timezone.utc).isoformat()),
            )
            try:
                inserted, canonical = insert_shared_state_strict(
                    _terminal_state_name(str(job_id), seed),
                    seed,
                    scope=_state_scope(payload=seed),
                )
            except Exception:
                # S3 may have accepted the conditional create before a local
                # compatibility mirror failed. If the authority can read the
                # envelope back, finalization succeeded and is retryable.
                canonical = _read_terminal_upload_state(str(job_id), seed)
                if not isinstance(canonical, dict):
                    raise
                inserted = False
                logger.warning(
                    "terminal_state_secondary_persistence_failed job_id=%s attempt_id=%s",
                    job_id,
                    incoming_attempt,
                )

        if _upload_state_value(canonical) != _upload_state_value(normalized):
            logger.warning(
                "terminal_state_conflict_prevented job_id=%s attempt_id=%s published_state=%s rejected_state=%s",
                job_id,
                incoming_attempt,
                _upload_state_value(canonical),
                _upload_state_value(normalized),
            )
        # Keep the mutable status object as the attempt pointer/progress
        # snapshot. Writing a terminal value back into it after the envelope
        # is visible could race with an immediately requested retry and restore
        # the prior attempt. Readers resolve the immutable envelope for the
        # pointer's attempt instead.
        log_publication = logger.info if inserted else logger.debug
        log_publication(
            "terminal_state_published job_id=%s attempt_id=%s state=%s publication=%s",
            job_id,
            incoming_attempt,
            _upload_state_value(canonical),
            "created" if inserted else "reused",
        )
        return canonical


def write_upload_status_progress(
    job_id: str,
    payload: dict[str, Any],
    *,
    latest_summary: dict[str, Any] | None = None,
    keep_result: bool = False,
    existing_status: dict[str, Any] | None | object = _UNSET_UPLOAD_STATUS,
) -> dict[str, Any]:
    normalized_payload = dict(payload or {}) if isinstance(payload, dict) else {}
    normalized_payload["job_id"] = str(job_id)
    with upload_job_publication_lock(str(job_id)):
        existing_job_status = (
            read_upload_status(str(job_id))
            if existing_status is _UNSET_UPLOAD_STATUS
            else existing_status
        )
        existing_job_status = existing_job_status if isinstance(existing_job_status, dict) else None
        normalized_payload.setdefault(
            "attempt_id",
            _upload_attempt_id(str(job_id), existing_job_status),
        )
        if (
            _is_terminal_upload_state(existing_job_status)
            and _upload_attempt_id(str(job_id), existing_job_status)
            == _upload_attempt_id(str(job_id), normalized_payload)
            and not _is_terminal_upload_state(normalized_payload)
        ):
            return existing_job_status
        summary_payload = dict(latest_summary or normalized_payload)
        summary_payload.setdefault("attempt_id", normalized_payload["attempt_id"])
        if _is_terminal_upload_state(normalized_payload):
            if (
                _is_terminal_upload_state(existing_job_status)
                and _upload_attempt_id(str(job_id), existing_job_status)
                == normalized_payload["attempt_id"]
            ):
                canonical = write_upload_status(
                    str(job_id),
                    normalized_payload,
                    _existing_status=existing_job_status,
                )
                record = persist_latest_upload_state(
                    summary=canonical,
                    result=None,
                    keep_result=_upload_state_value(canonical) in _SUCCESS_UPLOAD_STATES,
                )
                if identity_matches(record, str(job_id)):
                    write_latest_upload_summary_payload(canonical)
                return canonical
            # Latest/canonical records are derived mirrors, but publish their
            # complete payload before making the per-job terminal state visible.
            record = persist_latest_upload_state(summary=summary_payload, result=None, keep_result=keep_result)
            if identity_matches(record, str(job_id)):
                write_latest_upload_summary_payload(summary_payload)
            return write_upload_status(
                str(job_id),
                normalized_payload,
                _existing_status=existing_job_status,
            )

        canonical = write_upload_status(
            str(job_id),
            normalized_payload,
            _existing_status=existing_job_status,
        )
        if _is_terminal_upload_state(canonical):
            return canonical
        record = persist_latest_upload_state(summary=summary_payload, result=None, keep_result=keep_result)
        if identity_matches(record, str(job_id)):
            write_latest_upload_summary_payload(summary_payload)
        return canonical


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


def _repair_upload_completion_mirrors(
    job_id: str,
    *,
    result: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    """Best-effort compatibility mirrors after authoritative publication."""
    try:
        write_upload_result(str(job_id), result)
    except Exception:
        logger.warning("terminal_completion_result_mirror_write_failed job_id=%s", job_id)
    try:
        transport_result = project_result_for_transport(result) or result
        record = persist_latest_upload_state(summary=summary, result=transport_result)
        if identity_matches(record, str(job_id)):
            write_latest_upload_result_payload(transport_result)
            write_latest_upload_summary_payload(summary)
    except Exception:
        logger.warning("terminal_completion_latest_mirror_write_failed job_id=%s", job_id)


def write_upload_completion(job_id: str, *, result: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    for value in (result, summary):
        explicit_job_id = str((value or {}).get("job_id") or "").strip()
        if explicit_job_id and explicit_job_id != str(job_id):
            raise ValueError("upload_completion_identity_mismatch")
    result_scope = dataset_scope_from_payload(result)
    summary_scope = dataset_scope_from_payload(summary)
    if result_scope is not None and summary_scope is not None and result_scope != summary_scope:
        raise ValueError("upload_completion_scope_mismatch")
    scope = _state_scope(payload=result or summary)
    dataset_id = (result or {}).get("dataset_id") or (summary or {}).get("dataset_id") or job_id
    normalized_result = attach_dataset_scope(dict(result or {}) if isinstance(result, dict) else {}, scope=scope, dataset_id=dataset_id)
    normalized_summary = attach_dataset_scope(dict(summary or {}) if isinstance(summary, dict) else {}, scope=scope, dataset_id=dataset_id)
    normalized_result.setdefault("job_id", str(job_id))
    normalized_result.setdefault("run_id", str(job_id))
    normalized_result.setdefault("upload_id", str(job_id))
    normalized_result["session_scope"] = build_session_scope(
        str(job_id),
        filename=normalized_result.get("filename"),
        status="active",
        dataset_scope=scope,
        dataset_id=dataset_id,
    )
    normalized_summary.setdefault("job_id", str(job_id))
    normalized_summary.setdefault("run_id", str(job_id))
    normalized_summary.setdefault("upload_id", str(job_id))
    normalized_summary["session_scope"] = build_session_scope(
        str(job_id),
        filename=normalized_summary.get("filename") or normalized_result.get("filename"),
        status=str(normalized_summary.get("processing_state") or normalized_summary.get("status") or "active").lower(),
        dataset_scope=scope,
        dataset_id=dataset_id,
    )
    normalized_summary["transport_result_available"] = True

    with upload_job_publication_lock(str(job_id)):
        existing_status = read_upload_status(str(job_id))
        existing_scope = dataset_scope_from_payload(existing_status)
        if existing_scope is not None and existing_scope != scope:
            raise ValueError("upload_completion_scope_mismatch")
        attempt_source = (
            normalized_summary
            if normalized_summary.get("attempt_id")
            else normalized_result
            if normalized_result.get("attempt_id")
            else existing_status
        )
        attempt_id = _upload_attempt_id(str(job_id), attempt_source)
        normalized_result["attempt_id"] = attempt_id
        normalized_summary["attempt_id"] = attempt_id
        existing_terminal = _read_terminal_upload_state(str(job_id), normalized_summary)
        if (
            not isinstance(existing_terminal, dict)
            and _is_terminal_upload_state(existing_status)
            and _upload_attempt_id(str(job_id), existing_status) == attempt_id
        ):
            # Upgrade a valid pre-v1 terminal record into the immutable model
            # before deciding whether completion may write a result.
            existing_terminal = write_upload_status(str(job_id), existing_status)
        if isinstance(existing_terminal, dict):
            # Duplicate finalization never overwrites the committed result.
            persisted_result = _read_terminal_upload_result(str(job_id), existing_terminal)
            if not isinstance(persisted_result, dict):
                persisted_result = read_upload_result_by_job_id(str(job_id))
            if _upload_state_value(existing_terminal) in _SUCCESS_UPLOAD_STATES and isinstance(persisted_result, dict):
                _repair_upload_completion_mirrors(
                    str(job_id),
                    result=persisted_result,
                    summary=existing_terminal,
                )
            write_upload_status(str(job_id), existing_terminal)
            logger.info(
                "terminal_state_finalization_retry job_id=%s attempt_id=%s state=%s",
                job_id,
                attempt_id,
                _upload_state_value(existing_terminal),
            )
            return existing_terminal

        canonical_result, canonical_summary = _write_upload_result_strict(
            job_id,
            normalized_result,
            normalized_summary,
        )
        # The immutable bundle has already selected the canonical publisher,
        # so these mirrors can be prepared without duplicate-finalizer
        # contamination. Publish the terminal envelope only after normal
        # latest/result readers can resolve the completed job.
        _repair_upload_completion_mirrors(
            str(job_id),
            result=canonical_result,
            summary=canonical_summary,
        )
        canonical = write_upload_status(job_id, canonical_summary)
        if _upload_state_value(canonical) in _SUCCESS_UPLOAD_STATES:
            published_result = _read_terminal_upload_result(str(job_id), canonical)
            if not isinstance(published_result, dict):
                logger.error(
                    "terminal_completion_result_read_failed job_id=%s attempt_id=%s",
                    job_id,
                    _upload_attempt_id(str(job_id), canonical),
                )
                return canonical
        else:
            # A competing terminal publisher won. Restore derived mirrors to
            # the authoritative terminal state rather than leaving completion
            # metadata visible alongside a failure/cancellation envelope.
            persist_latest_upload_state(summary=canonical, result=None, keep_result=False)
            write_latest_upload_summary_payload(canonical)
        return canonical


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


def _identity_field(payload: dict[str, Any] | None, key: str) -> str:
    if not isinstance(payload, dict):
        return ""
    direct = str(payload.get(key) or "").strip()
    if direct:
        return direct
    session_scope = payload.get("session_scope") if isinstance(payload.get("session_scope"), dict) else {}
    return str(session_scope.get(key) or "").strip()


def _payloads_share_attempt(
    active: dict[str, Any] | None,
    candidate: dict[str, Any] | None,
) -> bool:
    """Return whether candidate data is safe to attach to the active attempt.

    Job identity is authoritative. Older payloads without a job ID may only be
    reconciled through another shared immutable identifier; timestamps and
    "latest successful" ordering are deliberately not used.
    """
    if not isinstance(active, dict) or not isinstance(candidate, dict):
        return False
    active_attempt_id = str(active.get("attempt_id") or "").strip()
    candidate_attempt_id = str(candidate.get("attempt_id") or "").strip()
    if active_attempt_id or candidate_attempt_id:
        return bool(active_attempt_id and candidate_attempt_id and active_attempt_id == candidate_attempt_id)
    active_job_id = _identity_field(active, "job_id")
    if active_job_id:
        return _identity_field(candidate, "job_id") == active_job_id
    for key in ("upload_id", "run_id", "dataset_id"):
        active_id = _identity_field(active, key)
        if active_id:
            return _identity_field(candidate, key) == active_id
    return False


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
    incoming = result if isinstance(result, dict) else summary
    incoming_state_payload = summary if isinstance(summary, dict) else incoming
    incoming_job_id = _identity_field(incoming, "job_id")
    existing_record = read_latest_upload_record()
    existing_job_id = _identity_field(existing_record, "job_id")
    if (
        incoming_job_id
        and existing_job_id
        and incoming_job_id != existing_job_id
        and _upload_state_value(existing_record) in _ACTIVE_UPLOAD_STATES
        and _upload_state_value(incoming_state_payload) in _TERMINAL_UPLOAD_STATES
    ):
        logger.info(
            "stale_upload_terminal_ignored active_job_id=%s stale_job_id=%s",
            existing_job_id,
            incoming_job_id,
        )
        return existing_record
    retained_result = result
    if keep_result and retained_result is None:
        cached_result = _cache_get("result", scope=scope)
        retained_result = cached_result if isinstance(cached_result, dict) else read_latest_upload_result()
    if isinstance(retained_result, dict) and not payload_matches_dataset_scope(retained_result, scope):
        retained_result = None
    if isinstance(summary, dict) and isinstance(retained_result, dict) and not _payloads_share_attempt(summary, retained_result):
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
    scope = current_dataset_scope()
    terminal = read_upload_status(str(job_id))
    if (
        isinstance(terminal, dict)
        and terminal.get("terminal_state_contract_version") == _TERMINAL_STATE_CONTRACT_VERSION
        and _is_terminal_upload_state(terminal)
    ):
        immutable_result = _read_terminal_upload_result(str(job_id), terminal)
        if isinstance(immutable_result, dict):
            return immutable_result
        if _upload_state_value(terminal) not in _SUCCESS_UPLOAD_STATES:
            return None
    name = f"upload_result_{job_id}"
    persisted = read_shared_state(name, scope=scope)
    if isinstance(persisted, dict) and payload_matches_dataset_scope(persisted, scope):
        return persisted
    local = read_local_json(f"{name}.json", scope=scope)
    if isinstance(local, dict) and payload_matches_dataset_scope(local, scope):
        return local
    legacy = _read_legacy_unscoped_state(name) or _read_legacy_unscoped_local(name)
    return legacy if payload_matches_dataset_scope(legacy, scope) else None


def _read_upload_status_mirror(job_id: str) -> dict[str, Any] | None:
    scope = current_dataset_scope()
    name = f"upload_status_{job_id}"
    persisted = read_shared_state(name, scope=scope)
    if isinstance(persisted, dict) and payload_matches_dataset_scope(persisted, scope):
        return persisted
    local = read_local_json(f"{name}.json", scope=scope)
    if isinstance(local, dict) and payload_matches_dataset_scope(local, scope):
        return local
    cached = runtime_state().jobs.get(job_id)
    if isinstance(cached, dict) and payload_matches_dataset_scope(cached, scope):
        return cached
    legacy = _read_legacy_unscoped_state(name)
    if not isinstance(legacy, dict):
        legacy = _read_legacy_unscoped_local(name)
    return legacy if payload_matches_dataset_scope(legacy, scope) else None


def read_upload_status(job_id: str) -> dict[str, Any] | None:
    """Read the current attempt, preferring its immutable terminal envelope."""
    mirror = _read_upload_status_mirror(str(job_id))
    terminal = _read_terminal_upload_state(str(job_id), mirror)
    canonical = terminal or mirror
    if isinstance(canonical, dict):
        runtime_state().cache_job(str(job_id), canonical)
    return canonical


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
        dataset_id=payload.get("dataset_id"),
    )
    payload = attach_dataset_scope(payload, scope=scope, dataset_id=payload.get("dataset_id") or payload.get("job_id"))
    payload = _attach_traceability(payload)

    transport_payload = project_result_for_transport(payload) or payload

    if payload.get("job_id"):
        latest_summary = summarize_result_payload(payload)
        latest_summary["transport_result_available"] = True
        write_upload_completion(
            str(payload["job_id"]),
            result=payload,
            summary=latest_summary,
        )
    else:
        write_latest_upload_result_payload(transport_payload)
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
        dataset_id=payload.get("dataset_id"),
    )
    payload = attach_dataset_scope(payload, scope=scope, dataset_id=payload.get("dataset_id") or payload.get("job_id"))
    if payload.get("job_id") and "status_url" not in payload:
        payload["status_url"] = f"/api/data/upload-status/{payload['job_id']}"

    result = None
    raw_result = None
    if payload.get("job_id"):
        raw_result = read_upload_result_by_job_id(str(payload["job_id"]))
        result = project_result_for_transport(raw_result)
        if isinstance(result, dict):
            payload["transport_result_available"] = True
    if payload.get("job_id"):
        if isinstance(raw_result, dict) and _upload_state_value(payload) in _SUCCESS_UPLOAD_STATES:
            write_upload_completion(
                str(payload["job_id"]),
                result=raw_result,
                summary=payload,
            )
            return
        existing_status = read_upload_status(str(payload["job_id"]))
        payload.setdefault(
            "attempt_id",
            _upload_attempt_id(str(payload["job_id"]), existing_status),
        )
        if (
            _is_terminal_upload_state(existing_status)
            and _upload_attempt_id(str(payload["job_id"]), existing_status)
            == _upload_attempt_id(str(payload["job_id"]), payload)
        ):
            canonical = write_upload_status(
                str(payload["job_id"]),
                payload,
                _existing_status=existing_status,
            )
            retained_result = (
                result
                if _upload_state_value(canonical) in _SUCCESS_UPLOAD_STATES
                else None
            )
            record = persist_latest_upload_state(
                summary=canonical,
                result=retained_result,
                keep_result=retained_result is not None,
            )
            if identity_matches(record, str(payload["job_id"])):
                write_latest_upload_summary_payload(canonical)
            return
        record = persist_latest_upload_state(summary=payload, result=result, keep_result=True)
        if identity_matches(record, str(payload["job_id"])):
            write_latest_upload_summary_payload(payload)
        write_upload_status(str(payload["job_id"]), payload)
    else:
        persist_latest_upload_state(summary=payload, result=None, keep_result=True)
        write_latest_upload_summary_payload(payload)


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
