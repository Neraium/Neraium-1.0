from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.dataset_scope import attach_dataset_scope, current_dataset_scope
from app.services.upload_state_repository import (
    read_local_json,
    read_shared_state,
    write_local_json,
    write_shared_state,
)


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
    write_shared_state(storage_name, normalized)


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
    model_id = str(model["model_id"])
    version = int(model["version"])
    persisted_model = dict(model)
    persisted_result = dict(result)
    _write(f"models/{model_id}", persisted_model)
    _write(f"results/{persisted_result['job_id']}", persisted_result)
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
    _write("index", {"latest_version": version, "models": entries[-100:]})

    if activate:
        activated = activate_candidate(model_id, approved_by="automatic_policy")
        _write(
            f"results/{persisted_result['job_id']}",
            {
                **persisted_result,
                "candidate_model": activated,
                "activation": dict(activated.get("activation") or {}),
            },
        )
        return activated
    return persisted_model


def activate_candidate(model_id: str, *, approved_by: str) -> dict[str, Any]:
    candidate = read_model(model_id)
    if not isinstance(candidate, dict):
        raise ValueError("behavioral_model_candidate_not_found")
    if candidate.get("activation", {}).get("eligible") is not True:
        raise ValueError("behavioral_model_candidate_not_eligible")

    activated_at = datetime.now(timezone.utc).isoformat()
    active = read_active_behavioral_model()
    if isinstance(active, dict) and active.get("model_id") != model_id:
        superseded = {
            **active,
            "status": "superseded",
            "superseded_at": activated_at,
            "superseded_by": model_id,
        }
        _write(f"models/{active['model_id']}", superseded)

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
    _write(
        "active",
        {
            "model_id": model_id,
            "version": activated.get("version"),
            "activated_at": activated_at,
            "approved_by": approved_by,
        },
    )

    index = read_model_index()
    entries = [
        {**item, "status": "active" if item.get("model_id") == model_id else item.get("status")}
        for item in index.get("models", [])
        if isinstance(item, dict)
    ]
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
