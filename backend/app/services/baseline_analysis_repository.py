from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services.baseline_contracts import WORKFLOW_ANALYZE_NEW_DATA
from app.services.dataset_scope import (
    DatasetScope,
    attach_dataset_scope,
    current_dataset_scope,
    dataset_scope_from_payload,
    payload_matches_dataset_scope,
)
from app.services.upload_state_repository import (
    read_local_json,
    read_shared_state,
    read_upload_result_by_job_id,
    write_local_json,
    write_shared_state_strict,
)


ANALYSIS_INDEX_VERSION = 1


def _scope_prefix(scope: DatasetScope | None = None) -> str:
    resolved = scope or current_dataset_scope()
    return f"scopes/{resolved.storage_id}/baseline-analyses"


def _analysis_key(baseline_id: str, analysis_run_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_scope_prefix(scope)}/{baseline_id}/{analysis_run_id}"


def _index_key(baseline_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_scope_prefix(scope)}/{baseline_id}/index"


def _read(name: str, *, scope: DatasetScope | None = None) -> dict[str, Any] | None:
    shared = read_shared_state(name, scope=scope)
    if isinstance(shared, dict):
        return shared
    return read_local_json(f"{name}.json", scope=scope)


def _write(name: str, payload: dict[str, Any], *, scope: DatasetScope) -> None:
    normalized = attach_dataset_scope(dict(payload), scope=scope, dataset_id=payload.get("comparison_dataset_id"))
    write_local_json(f"{name}.json", normalized, scope=scope)
    write_shared_state_strict(name, normalized, scope=scope)


def analysis_identity(result: dict[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(result, dict):
        return None
    scope = dataset_scope_from_payload(result)
    baseline_reference = result.get("active_baseline_reference")
    if not isinstance(baseline_reference, dict):
        baseline_reference = {}
    identity = {
        "organization_id": str(result.get("organization_id") or (scope or current_dataset_scope()).tenant_id).strip(),
        "portfolio_id": str(result.get("portfolio_id") or (scope or current_dataset_scope()).workspace_id).strip(),
        "system_id": str(result.get("system_id") or "").strip(),
        "baseline_id": str(result.get("baseline_id") or baseline_reference.get("model_id") or "").strip(),
        "comparison_dataset_id": str(result.get("comparison_dataset_id") or result.get("dataset_id") or "").strip(),
        "analysis_run_id": str(result.get("analysis_run_id") or result.get("run_id") or result.get("job_id") or "").strip(),
    }
    return identity if all(identity.values()) else None


def validate_completed_analysis(
    result: dict[str, Any] | None,
    *,
    scope: DatasetScope | None = None,
    portfolio_id: str | None = None,
    system_id: str | None = None,
    baseline_id: str | None = None,
    comparison_dataset_id: str | None = None,
    analysis_run_id: str | None = None,
) -> dict[str, str]:
    if not isinstance(result, dict):
        raise ValueError("analysis_result_missing")
    resolved_scope = scope or current_dataset_scope()
    if not payload_matches_dataset_scope(result, resolved_scope):
        raise ValueError("analysis_scope_mismatch")
    if str(result.get("workflow") or "") != WORKFLOW_ANALYZE_NEW_DATA:
        raise ValueError("analysis_workflow_not_baseline_comparison")
    if str(result.get("status") or "").upper() != "COMPLETE" or str(result.get("processing_state") or "").lower() != "complete":
        raise ValueError("analysis_run_not_complete")
    if result.get("sii_completed") is not True:
        raise ValueError("analysis_run_not_complete")

    identity = analysis_identity(result)
    if identity is None:
        raise ValueError("analysis_identity_incomplete")
    expected = {
        "organization_id": resolved_scope.tenant_id,
        "portfolio_id": portfolio_id or resolved_scope.workspace_id,
        "system_id": system_id,
        "baseline_id": baseline_id,
        "comparison_dataset_id": comparison_dataset_id,
        "analysis_run_id": analysis_run_id,
    }
    for key, value in expected.items():
        if value is not None and identity[key] != str(value):
            raise ValueError(f"analysis_{key}_mismatch")

    baseline_reference = result.get("active_baseline_reference")
    reference_id = str((baseline_reference or {}).get("model_id") or "").strip()
    if reference_id != identity["baseline_id"]:
        raise ValueError("analysis_baseline_reference_mismatch")
    if str(result.get("dataset_id") or "").strip() != identity["comparison_dataset_id"]:
        raise ValueError("analysis_comparison_dataset_mismatch")
    if str(result.get("run_id") or result.get("job_id") or "").strip() != identity["analysis_run_id"]:
        raise ValueError("analysis_run_id_mismatch")
    return identity


def persist_completed_analysis(result: dict[str, Any]) -> dict[str, str] | None:
    if str(result.get("workflow") or "") != WORKFLOW_ANALYZE_NEW_DATA:
        return None
    scope = dataset_scope_from_payload(result) or current_dataset_scope()
    identity = validate_completed_analysis(result, scope=scope)
    record = {
        **identity,
        "analysis_record_version": 1,
        "result_job_id": str(result.get("job_id") or identity["analysis_run_id"]),
        "job_id": identity["analysis_run_id"],
        "run_id": identity["analysis_run_id"],
        "dataset_id": identity["comparison_dataset_id"],
        "workflow": WORKFLOW_ANALYZE_NEW_DATA,
        "status": "COMPLETE",
        "processing_state": "complete",
        "sii_completed": True,
        "active_baseline_reference": dict(result.get("active_baseline_reference") or {}),
        "filename": result.get("filename"),
        "completed_at": result.get("completed_at"),
    }
    _write(
        _analysis_key(identity["baseline_id"], identity["analysis_run_id"], scope=scope),
        record,
        scope=scope,
    )

    index_name = _index_key(identity["baseline_id"], scope=scope)
    index = _read(index_name, scope=scope) or {}
    entries = [
        item
        for item in index.get("analyses", [])
        if isinstance(item, dict) and str(item.get("analysis_run_id") or "") != identity["analysis_run_id"]
    ]
    entries.append(
        {
            **identity,
            "status": "complete",
            "filename": result.get("filename"),
            "completed_at": result.get("completed_at"),
        }
    )
    entries.sort(key=lambda item: str(item.get("completed_at") or ""))
    _write(
        index_name,
        {
            "version": ANALYSIS_INDEX_VERSION,
            "baseline_id": identity["baseline_id"],
            "organization_id": identity["organization_id"],
            "portfolio_id": identity["portfolio_id"],
            "system_id": identity["system_id"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "analyses": entries[-100:],
        },
        scope=scope,
    )
    return identity


def list_completed_analyses(
    baseline_id: str,
    *,
    portfolio_id: str | None = None,
    system_id: str | None = None,
) -> list[dict[str, Any]]:
    scope = current_dataset_scope()
    if portfolio_id is not None and str(portfolio_id) != scope.workspace_id:
        return []
    index = _read(_index_key(str(baseline_id), scope=scope), scope=scope)
    if not isinstance(index, dict) or not payload_matches_dataset_scope(index, scope):
        return []
    if str(index.get("baseline_id") or "") != str(baseline_id):
        return []
    if str(index.get("portfolio_id") or "") != scope.workspace_id:
        return []
    if system_id is not None and str(index.get("system_id") or "") != str(system_id):
        return []
    return [
        dict(item)
        for item in index.get("analyses", [])
        if isinstance(item, dict)
        and str(item.get("baseline_id") or "") == str(baseline_id)
        and str(item.get("portfolio_id") or "") == scope.workspace_id
        and (system_id is None or str(item.get("system_id") or "") == str(system_id))
    ]


def read_completed_analysis(
    baseline_id: str,
    analysis_run_id: str,
    *,
    portfolio_id: str,
    system_id: str,
) -> dict[str, Any] | None:
    scope = current_dataset_scope()
    if str(portfolio_id) != scope.workspace_id:
        return None
    link = _read(_analysis_key(str(baseline_id), str(analysis_run_id), scope=scope), scope=scope)
    try:
        validate_completed_analysis(
            link,
            scope=scope,
            portfolio_id=portfolio_id,
            system_id=system_id,
            baseline_id=baseline_id,
            analysis_run_id=analysis_run_id,
        )
    except ValueError:
        return None
    result_job_id = str((link or {}).get("result_job_id") or "").strip()
    if result_job_id != str(analysis_run_id):
        return None
    result = read_upload_result_by_job_id(result_job_id)
    try:
        validate_completed_analysis(
            result,
            scope=scope,
            portfolio_id=portfolio_id,
            system_id=system_id,
            baseline_id=baseline_id,
            comparison_dataset_id=(link or {}).get("comparison_dataset_id"),
            analysis_run_id=analysis_run_id,
        )
    except ValueError:
        return None
    return result
