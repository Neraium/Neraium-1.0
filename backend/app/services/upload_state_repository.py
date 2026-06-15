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
    write_local_json("latest_upload_result.json", payload)
    write_shared_state("latest_upload_result", payload)
    runtime_state().latest_upload_cache["result"] = payload


def write_latest_upload_summary_payload(payload: dict[str, Any]) -> None:
    write_local_json("latest_upload_summary.json", payload)
    write_shared_state("latest_upload_summary", payload)
    runtime_state().latest_upload_cache["summary"] = payload


def write_upload_completion(job_id: str, *, result: dict[str, Any], summary: dict[str, Any]) -> None:
    normalized_result = dict(result or {}) if isinstance(result, dict) else {}
    normalized_summary = dict(summary or {}) if isinstance(summary, dict) else {}
    write_upload_result(job_id, normalized_result)
    write_upload_status(job_id, normalized_summary)
    write_latest_upload_result_payload(normalized_result)
    write_latest_upload_summary_payload(normalized_summary)
    persist_latest_upload_state(summary=normalized_summary, result=normalized_result)


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
    if not isinstance(result, dict):
        result = record_result if isinstance(record_result, dict) else None

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
    clear_reset_block_persisted()
    result = args[0] if len(args) == 1 else args[1] if len(args) >= 2 else {}
    payload = dict(result or {}) if isinstance(result, dict) else {}

    if len(args) >= 2:
        job_id = str(args[0])
        payload["job_id"] = job_id
        payload["run_id"] = job_id
        payload["upload_id"] = job_id

    payload["session_scope"] = build_session_scope(
        payload.get("job_id"),
        filename=payload.get("filename"),
        status="active",
    )
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
    clear_reset_block_persisted()
    summary = args[0] if len(args) == 1 else args[1] if len(args) >= 2 else {}
    payload = dict(summary or {}) if isinstance(summary, dict) else {}

    if len(args) >= 2:
        job_id = str(args[0])
        payload["job_id"] = job_id
        payload["run_id"] = job_id
        payload["upload_id"] = job_id

    payload.setdefault("status", "COMPLETE")
    payload["session_scope"] = build_session_scope(
        payload.get("job_id"),
        filename=payload.get("filename"),
        status="active",
    )
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
