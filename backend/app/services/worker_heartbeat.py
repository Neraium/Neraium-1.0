from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import boto3  # type: ignore
except Exception:  # pragma: no cover
    boto3 = None

logger = logging.getLogger(__name__)
_HEARTBEAT_KEY = "infrastructure/worker-heartbeat.json"
_TELEMETRY_HEARTBEAT_KEY = "infrastructure/telemetry-worker-heartbeat.json"
_LOCK = threading.RLock()
_LAST_WRITE_MONOTONIC = 0.0
_TELEMETRY_LAST_WRITE_MONOTONIC = 0.0
_S3_CLIENT: Any | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runtime_path() -> Path:
    configured = os.getenv("NERAIUM_RUNTIME_DIR", "").strip()
    runtime_dir = Path(configured) if configured else Path(__file__).resolve().parents[1] / "runtime"
    return runtime_dir / "infrastructure-worker-heartbeat.json"


def _telemetry_runtime_path() -> Path:
    return _runtime_path().with_name("infrastructure-telemetry-worker-heartbeat.json")


def _bucket() -> str:
    return os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", "").strip()


def _client():
    global _S3_CLIENT
    if _S3_CLIENT is None:
        if boto3 is None:
            raise RuntimeError("boto3 is required for shared worker heartbeat storage.")
        _S3_CLIENT = boto3.client("s3", region_name=os.getenv("AWS_REGION") or None)
    return _S3_CLIENT


def publish_worker_heartbeat(
    *,
    status: str = "healthy",
    processed_job: bool = False,
    error_type: str | None = None,
    force: bool = False,
    minimum_interval_seconds: float = 30.0,
) -> bool:
    """Publish a non-secret heartbeat shared by the production API and worker."""
    global _LAST_WRITE_MONOTONIC
    now_monotonic = time.monotonic()
    with _LOCK:
        if not force and now_monotonic - _LAST_WRITE_MONOTONIC < minimum_interval_seconds:
            return False
        payload = {
            "status": str(status or "unknown"),
            "observed_at": _now_iso(),
            "process_role": os.getenv("NERAIUM_PROCESS_ROLE", "worker"),
            "build_sha": os.getenv("NERAIUM_BUILD_SHA", "unknown")[:12],
            "processed_job": bool(processed_job),
            "error_type": str(error_type or "") or None,
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        bucket = _bucket()
        if bucket:
            _client().put_object(
                Bucket=bucket,
                Key=_HEARTBEAT_KEY,
                Body=body,
                ContentType="application/json",
                ServerSideEncryption="AES256",
            )
        else:
            path = _runtime_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(body)
            os.replace(temporary, path)
        _LAST_WRITE_MONOTONIC = now_monotonic
        return True


def read_worker_heartbeat() -> dict[str, Any] | None:
    return _read_heartbeat(key=_HEARTBEAT_KEY, path=_runtime_path())


def publish_telemetry_worker_heartbeat(
    *,
    status: str = "healthy",
    processed_page: bool = False,
    error_code: str | None = None,
    force: bool = False,
    minimum_interval_seconds: float = 30.0,
) -> bool:
    """Publish scheduler state under a key separate from upload workers."""
    global _TELEMETRY_LAST_WRITE_MONOTONIC
    now_monotonic = time.monotonic()
    with _LOCK:
        if (
            not force
            and now_monotonic - _TELEMETRY_LAST_WRITE_MONOTONIC
            < minimum_interval_seconds
        ):
            return False
        payload = {
            "status": str(status or "unknown"),
            "observed_at": _now_iso(),
            "process_role": os.getenv("NERAIUM_PROCESS_ROLE", "worker"),
            "build_sha": os.getenv("NERAIUM_BUILD_SHA", "unknown")[:12],
            "processed_page": bool(processed_page),
            "error_code": str(error_code or "")[:128] or None,
        }
        _write_heartbeat(
            key=_TELEMETRY_HEARTBEAT_KEY,
            path=_telemetry_runtime_path(),
            payload=payload,
        )
        _TELEMETRY_LAST_WRITE_MONOTONIC = now_monotonic
        return True


def read_telemetry_worker_heartbeat() -> dict[str, Any] | None:
    return _read_heartbeat(
        key=_TELEMETRY_HEARTBEAT_KEY,
        path=_telemetry_runtime_path(),
    )


def _write_heartbeat(*, key: str, path: Path, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    bucket = _bucket()
    if bucket:
        _client().put_object(
            Bucket=bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(body)
    os.replace(temporary, path)


def _read_heartbeat(*, key: str, path: Path) -> dict[str, Any] | None:
    bucket = _bucket()
    try:
        if bucket:
            response = _client().get_object(Bucket=bucket, Key=key)
            raw = response["Body"].read()
        else:
            if not path.exists():
                return None
            raw = path.read_bytes()
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception as error:
        error_code = str(getattr(error, "response", {}).get("Error", {}).get("Code", ""))
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            return None
        logger.warning(
            "worker_heartbeat_read_failed",
            extra={"event": "worker_heartbeat_read_failed", "error_type": type(error).__name__},
        )
        return None
