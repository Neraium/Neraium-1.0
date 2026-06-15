from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.services.runtime_db import (
    delete_latest_payload_prefix,
    read_latest_payload,
    upsert_latest_payload,
)
from app.services.upload_runtime_state import UPLOAD_RUNTIME_STATE, UploadRuntimeState
from app.services.upload_state import (
    build_empty_latest_upload_record,
    build_latest_upload_record,
    normalize_upload_identity,
    select_current_upload_result,
)


def runtime_state() -> UploadRuntimeState:
    return UPLOAD_RUNTIME_STATE


def configure_runtime_dir(path: str | os.PathLike[str]) -> None:
    runtime_state().configure_runtime_dir(path)


def _runtime_db_latest_enabled() -> bool:
    return os.getenv("PYTEST_CURRENT_TEST") is None and os.getenv("NERAIUM_DISABLE_RUNTIME_DB_LATEST", "0") != "1"


def _upload_state_bucket() -> str:
    return os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", "").strip()


def shared_state_configured() -> bool:
    return bool(_upload_state_bucket())


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


def _get_s3_client() -> Any | None:
    state = runtime_state()
    if state.upload_state_s3_client is not None:
        return state.upload_state_s3_client
    if not _upload_state_bucket():
        return None
    try:
        import boto3  # type: ignore

        state.upload_state_s3_client = boto3.client("s3")
        return state.upload_state_s3_client
    except Exception:
        return None


def read_local_json(name: str) -> dict[str, Any] | None:
    path = runtime_state().runtime_dir / name
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_local_json(name: str, payload: dict[str, Any]) -> None:
    state = runtime_state()
    state.runtime_dir.mkdir(parents=True, exist_ok=True)
    (state.runtime_dir / name).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def read_shared_state(name: str) -> dict[str, Any] | None:
    bucket = _upload_state_bucket()
    if bucket:
        client = _get_s3_client()
        if client is not None:
            try:
                response = client.get_object(Bucket=bucket, Key=_s3_object_key(name))
                body = response["Body"].read().decode("utf-8")
                payload = json.loads(body)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
    if _runtime_db_latest_enabled():
        try:
            payload = read_latest_payload(_shared_key(name))
            if isinstance(payload, dict):
                return payload
        except Exception:
            pass
    return None


def write_shared_state(name: str, payload: dict[str, Any]) -> None:
    normalized = dict(payload or {})
    try:
        upsert_latest_payload(_shared_key(name), normalized)
    except Exception:
        pass
    bucket = _upload_state_bucket()
    if bucket:
        client = _get_s3_client()
        if client is not None:
            try:
                client.put_object(
                    Bucket=bucket,
                    Key=_s3_object_key(name),
                    Body=json.dumps(normalized, indent=2, default=str).encode("utf-8"),
                    ContentType="application/json",
                )
            except Exception:
                pass


def write_upload_result(job_id: str, payload: dict[str, Any]) -> None:
    write_local_json(f"upload_result_{job_id}.json", payload)
    write_shared_state(f"upload_result_{job_id}", payload)


def write_upload_status(job_id: str, payload: dict[str, Any]) -> None:
    write_local_json(f"upload_status_{job_id}.json", payload)
    write_shared_state(f"upload_status_{job_id}", payload)


def write_latest_upload_result_payload(payload: dict[str, Any]) -> None:
    write_local_json("latest_upload_result.json", payload)
    write_shared_state("latest_upload_result", payload)
    runtime_state().latest_upload_cache["result"] = payload


def write_latest_upload_summary_payload(payload: dict[str, Any]) -> None:
    write_local_json("latest_upload_summary.json", payload)
    write_shared_state("latest_upload_summary", payload)
    runtime_state().latest_upload_cache["summary"] = payload


def write_latest_upload_record(record: dict[str, Any] | None) -> dict[str, Any]:
    payload = build_empty_latest_upload_record() if not isinstance(record, dict) else dict(record)
    write_local_json("latest_upload.json", payload)
    write_shared_state("latest_upload", payload)
    runtime_state().latest_upload_cache["canonical"] = payload
    _invalidate_router_latest_cache()
    return payload


def read_latest_upload_record() -> dict[str, Any] | None:
    persisted = read_shared_state("latest_upload")
    if isinstance(persisted, dict):
        runtime_state().latest_upload_cache["canonical"] = persisted
        return persisted
    cached = runtime_state().latest_upload_cache.get("canonical")
    if isinstance(cached, dict):
        return cached
    return read_local_json("latest_upload.json")


def read_current_upload_result() -> dict[str, Any] | None:
    return select_current_upload_result(read_latest_upload_record())


def persist_latest_upload_state(
    *,
    summary: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    keep_result: bool = True,
) -> dict[str, Any]:
    evidence_record = None
    job_id, _, _ = normalize_upload_identity(result or summary)
    if job_id:
        try:
            from app.services.evidence_store import read_evidence_run

            evidence_record = read_evidence_run(job_id)
        except Exception:
            evidence_record = None
    record = build_latest_upload_record(
        summary=summary,
        result=result if keep_result else None,
        evidence=evidence_record,
    )
    return write_latest_upload_record(record)


def warm_latest_upload_cache() -> None:
    state = runtime_state()
    state.latest_upload_cache["summary"] = read_shared_state("latest_upload_summary") or read_local_json("latest_upload_summary.json")
    state.latest_upload_cache["result"] = read_shared_state("latest_upload_result") or read_local_json("latest_upload_result.json")
    state.latest_upload_cache["canonical"] = read_shared_state("latest_upload") or read_local_json("latest_upload.json")


def read_latest_upload_result() -> dict[str, Any] | None:
    persisted = read_shared_state("latest_upload_result")
    if isinstance(persisted, dict):
        runtime_state().latest_upload_cache["result"] = persisted
        return persisted
    cached = runtime_state().latest_upload_cache.get("result")
    return cached if isinstance(cached, dict) else read_local_json("latest_upload_result.json")


def read_latest_upload_summary() -> dict[str, Any] | None:
    persisted = read_shared_state("latest_upload_summary")
    if isinstance(persisted, dict):
        runtime_state().latest_upload_cache["summary"] = persisted
        return persisted
    cached = runtime_state().latest_upload_cache.get("summary")
    return cached if isinstance(cached, dict) else read_local_json("latest_upload_summary.json")


def read_upload_result_by_job_id(job_id: str) -> dict[str, Any] | None:
    persisted = read_shared_state(f"upload_result_{job_id}")
    if isinstance(persisted, dict):
        return persisted
    return read_local_json(f"upload_result_{job_id}.json")


def read_upload_status(job_id: str) -> dict[str, Any] | None:
    persisted = read_shared_state(f"upload_status_{job_id}")
    if isinstance(persisted, dict):
        runtime_state().jobs[job_id] = persisted
        return persisted
    cached = runtime_state().jobs.get(job_id)
    if isinstance(cached, dict):
        return cached
    return read_local_json(f"upload_status_{job_id}.json")


def clear_reset_block_persisted() -> None:
    runtime_state().reset_block_persisted = False


def reset_block_persisted_active() -> bool:
    return bool(runtime_state().reset_block_persisted)


def reset_upload_state() -> None:
    state = runtime_state()
    state.jobs.clear()
    for path in state.runtime_dir.glob("*upload*"):
        try:
            path.unlink()
        except OSError:
            pass
    state.latest_upload_cache["summary"] = None
    state.latest_upload_cache["result"] = None
    state.latest_upload_cache["canonical"] = None
    try:
        delete_latest_payload_prefix("upload_")
        delete_latest_payload_prefix("latest_upload_")
        delete_latest_payload_prefix("latest_upload")
    except Exception:
        pass
    state.reset_block_persisted = True
    _invalidate_router_latest_cache()


def _invalidate_router_latest_cache() -> None:
    try:
        from app.routers import data as data_router

        data_router.invalidate_latest_upload_cache()
    except Exception:
        pass
