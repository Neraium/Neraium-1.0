from __future__ import annotations

from datetime import datetime, timezone
import threading
from typing import Any

from app.services.dataset_scope import attach_dataset_scope, current_dataset_scope
from app.services.upload_state_repository import (
    read_local_json,
    read_shared_state,
    write_local_json,
    write_shared_state_strict,
)


_ACTIVATION_LOCK = threading.RLock()


def _scope_prefix() -> str:
    return f"scopes/{current_dataset_scope().storage_id}/behavioral-models"


def _key(name: str) -> str:
    return f"{_scope_prefix()}/{name}"


def _read(name: str) -> dict[str, Any] | None:
    storage_name = _key(name)
    shared = read_shared_state(storage_name)
    if isinstance(shared, dict):
        return shared
    return read_local_json(f"{storage_name}.json")


def _write(name: str, payload: dict[str, Any]) -> None:
    storage_name = _key(name)
    normalized = attach_dataset_scope(dict(payload))
    write_local_json(f"{storage_name}.json", normalized)
    write_shared_state_strict(storage_name, normalized)


def read_model(model_id: str) -> dict[str, Any] | None:
    return _read(f"models/{model_id}")


def read_active_behavioral_model() -> dict[str, Any] | None:
    pointer = _read("active")
    model_id = str((pointer or {}).get("model_id") or "").strip()
    if not model_id:
        return None
    model = read_model(model_id)
    return model if isinstance(model, dict) and model.get("status") == "active" else None


def read_latest_candidate() -> dict[str, Any] | None:
    pointer = _read("latest-candidate")
    model_id = str((pointer or {}).get("model_id") or "").strip()
    return read_model(model_id) if model_id else None


def read_baseline_result(job_id: str) -> dict[str, Any] | None:
    return _read(f"results/{job_id}")


def read_baseline_result_by_model_id(model_id: str) -> dict[str, Any] | None:
    model = read_model(model_id)
    job_id = str(((model or {}).get("source") or {}).get("job_id") or "").strip()
    if not job_id:
        return None
    result = read_baseline_result(job_id)
    returned_model_id = str(((result or {}).get("candidate_model") or {}).get("model_id") or "").strip()
    return result if isinstance(result, dict) and returned_model_id == str(model_id) else None


def read_model_index() -> dict[str, Any]:
    payload = _read("index")
    if isinstance(payload, dict):
        return payload
    return {"latest_version": 0, "models": []}


def next_model_version() -> int:
    index = read_model_index()
    try:
        return max(0, int(index.get("latest_version") or 0)) + 1
    except (TypeError, ValueError):
        return 1


def persist_candidate(
    model: dict[str, Any],
    result: dict[str, Any],
    *,
    activate: bool,
) -> dict[str, Any]:
    """Persist one candidate and publish COMPLETE only after automatic activation."""
    with _ACTIVATION_LOCK:
        model_id = str(model["model_id"])
        version = int(model["version"])
        persisted_model = dict(model)
        persisted_result = dict(result)
        _write(f"models/{model_id}", persisted_model)
        _write(
            "latest-candidate",
            {
                "model_id": model_id,
                "version": version,
                "status": persisted_model.get("status"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        index = read_model_index()
        entries = [
            item
            for item in index.get("models", [])
            if isinstance(item, dict) and item.get("model_id") != model_id
        ]
        entries.append(
            {
                "model_id": model_id,
                "version": version,
                "status": persisted_model.get("status"),
                "workflow": persisted_model.get("workflow"),
                "created_at": persisted_model.get("created_at"),
            }
        )
        entries.sort(key=lambda item: int(item.get("version") or 0))
        _write("index", {"latest_version": max(version, int(index.get("latest_version") or 0)), "models": entries[-100:]})

        if not activate:
            _write(f"results/{persisted_result['job_id']}", persisted_result)
            return persisted_model

        # The active pointer is committed before the terminal result. If any
        # activation write fails, the upload job fails and cannot advertise a
        # completed baseline while the previous pointer remains selected.
        activated = activate_candidate(model_id, approved_by="automatic_policy")
        completed_result = {
            **persisted_result,
            "candidate_model": activated,
            "activation": dict(activated.get("activation") or {}),
        }
        _write(f"results/{persisted_result['job_id']}", completed_result)
        return activated


def activate_candidate(model_id: str, *, approved_by: str) -> dict[str, Any]:
    with _ACTIVATION_LOCK:
        candidate = read_model(model_id)
        if not isinstance(candidate, dict):
            raise ValueError("behavioral_model_candidate_not_found")
        if candidate.get("activation", {}).get("eligible") is not True:
            raise ValueError("behavioral_model_candidate_not_eligible")

        activated_at = datetime.now(timezone.utc).isoformat()
        active = read_active_behavioral_model()
        activated = {
            **candidate,
            "status": "active",
            "activation": {
                **dict(candidate.get("activation") or {}),
                "state": "active",
                "approved_by": approved_by,
                "activated_at": activated_at,
            },
        }
        _write(f"models/{model_id}", activated)
        try:
            _write(
                "active",
                {
                    "model_id": model_id,
                    "version": activated.get("version"),
                    "activated_at": activated_at,
                    "approved_by": approved_by,
                },
            )
        except Exception:
            # Best-effort rollback keeps the candidate contract aligned with
            # the unchanged pointer. The activation error still fails the job.
            try:
                _write(f"models/{model_id}", candidate)
            except Exception:
                pass
            raise

        # Supersede the previous model only after the new active pointer is
        # durable, so readers never observe a pointer to an inactive model.
        previous_model_id = str((active or {}).get("model_id") or "").strip()
        if previous_model_id and previous_model_id != model_id:
            superseded = {
                **active,
                "status": "superseded",
                "superseded_at": activated_at,
                "superseded_by": model_id,
            }
            _write(f"models/{previous_model_id}", superseded)
            previous_job_id = str((superseded.get("source") or {}).get("job_id") or "").strip()
            previous_result = read_baseline_result(previous_job_id) if previous_job_id else None
            if isinstance(previous_result, dict):
                _write(
                    f"results/{previous_job_id}",
                    {
                        **previous_result,
                        "candidate_model": superseded,
                        "activation": dict(superseded.get("activation") or {}),
                    },
                )

        index = read_model_index()
        entries = []
        for item in index.get("models", []):
            if not isinstance(item, dict):
                continue
            entry_id = item.get("model_id")
            status = "active" if entry_id == model_id else item.get("status")
            if entry_id == previous_model_id and previous_model_id != model_id:
                status = "superseded"
            entries.append({**item, "status": status})
        _write("index", {**index, "models": entries})

        job_id = str((activated.get("source") or {}).get("job_id") or "").strip()
        if job_id:
            result = read_baseline_result(job_id)
            if isinstance(result, dict):
                _write(
                    f"results/{job_id}",
                    {
                        **result,
                        "candidate_model": activated,
                        "activation": dict(activated.get("activation") or {}),
                    },
                )
        return activated
