from __future__ import annotations

from datetime import datetime, timezone
import logging
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
    list_shared_state_prefix,
    read_shared_state,
    read_upload_result_by_job_id,
    write_local_json,
    write_shared_state_strict,
)
from app.services.evidence_package import ensure_evidence_package, legacy_findings
from app.services.evidence_package_fingerprint import (
    ALGORITHM_VERSION,
    ApproximateSimilarityResponse,
    EvidencePackageFingerprint,
    ExactMatchObservation,
    ExactMatchResult,
    ExactMatchStatus,
    FingerprintStatus,
    build_fingerprint,
    aggregate_similarity_status,
    compare_fingerprints,
    observation_id,
    parse_timestamp,
)
from app.services.evidence_package_lifecycle import (
    LifecycleTransitionRequest,
    append_lifecycle_event,
    initial_lifecycle,
    lifecycle_lock,
)


ANALYSIS_INDEX_VERSION = 1
logger = logging.getLogger(__name__)


def _scope_prefix(scope: DatasetScope | None = None) -> str:
    resolved = scope or current_dataset_scope()
    return f"scopes/{resolved.storage_id}/baseline-analyses"


def _analysis_key(baseline_id: str, analysis_run_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_scope_prefix(scope)}/{baseline_id}/{analysis_run_id}"


def _index_key(baseline_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_scope_prefix(scope)}/{baseline_id}/index"


def _analysis_id_key(analysis_run_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_scope_prefix(scope)}/by-analysis/{analysis_run_id}"


def _package_id_key(package_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_scope_prefix(scope)}/by-package/{package_id}"


def _package_lifecycle_key(package_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_scope_prefix(scope)}/package-lifecycle/{package_id}"


def _package_fingerprint_key(package_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_scope_prefix(scope)}/package-fingerprints/{package_id}/{ALGORITHM_VERSION}"


def _fingerprint_index_prefix(system_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_scope_prefix(scope)}/fingerprint-index/{system_id}/{ALGORITHM_VERSION}"


def _fingerprint_index_entry_key(system_id: str, package_id: str, *, scope: DatasetScope | None = None) -> str:
    return f"{_fingerprint_index_prefix(system_id, scope=scope)}/{package_id}"


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
        "baseline_dataset_id": str(result.get("baseline_dataset_id") or baseline_reference.get("dataset_id") or "").strip(),
        "comparison_dataset_id": str(result.get("comparison_dataset_id") or result.get("dataset_id") or "").strip(),
        "analysis_run_id": str(result.get("comparison_analysis_id") or result.get("analysis_run_id") or result.get("run_id") or result.get("job_id") or "").strip(),
    }
    return identity if all(identity.values()) else None


def _finding_collections(result: dict[str, Any]) -> list[list[dict[str, Any]]]:
    collections: list[list[dict[str, Any]]] = []
    seen: set[int] = set()
    candidates: list[Any] = [result.get("findings"), result.get("conditions")]
    for container_name in ("analysis_explanation", "analysis", "analysis_result"):
        container = result.get(container_name)
        if isinstance(container, dict):
            candidates.extend((container.get("findings"), container.get("insights"), container.get("conditions")))
    for candidate in candidates:
        if not isinstance(candidate, list) or id(candidate) in seen:
            continue
        seen.add(id(candidate))
        collections.append([item for item in candidate if isinstance(item, dict)])
    return collections


def stamp_comparison_analysis_identity(result: dict[str, Any]) -> dict[str, Any]:
    """Stamp every comparison finding with its owning analysis and dataset IDs."""
    if str(result.get("workflow") or "") != WORKFLOW_ANALYZE_NEW_DATA:
        return result
    identity = analysis_identity(result)
    if identity is None:
        raise ValueError("analysis_identity_incomplete")
    result["comparison_analysis_id"] = identity["analysis_run_id"]
    result["analysis_run_id"] = identity["analysis_run_id"]
    result["baseline_id"] = identity["baseline_id"]
    result["baseline_dataset_id"] = identity["baseline_dataset_id"]
    result["comparison_dataset_id"] = identity["comparison_dataset_id"]
    finding_identity = {
        "comparison_analysis_id": identity["analysis_run_id"],
        "analysis_run_id": identity["analysis_run_id"],
        "baseline_id": identity["baseline_id"],
        "baseline_dataset_id": identity["baseline_dataset_id"],
        "comparison_dataset_id": identity["comparison_dataset_id"],
    }
    for collection in _finding_collections(result):
        for finding in collection:
            finding.update(finding_identity)
    ensure_evidence_package(result)
    return result


def comparison_findings(result: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[int] = set()
    for collection in _finding_collections(result):
        for finding in collection:
            if id(finding) in seen:
                continue
            seen.add(id(finding))
            findings.append(dict(finding))
    package = ensure_evidence_package(result)
    return legacy_findings(package, findings) if package else findings


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
    reference_dataset_id = str((baseline_reference or {}).get("dataset_id") or "").strip()
    if reference_dataset_id != identity["baseline_dataset_id"]:
        raise ValueError("analysis_baseline_dataset_reference_mismatch")
    if identity["baseline_dataset_id"] == identity["comparison_dataset_id"]:
        raise ValueError("comparison_dataset_matches_baseline_dataset")
    if str(result.get("dataset_id") or "").strip() != identity["comparison_dataset_id"]:
        raise ValueError("analysis_comparison_dataset_mismatch")
    if str(result.get("run_id") or result.get("job_id") or "").strip() != identity["analysis_run_id"]:
        raise ValueError("analysis_run_id_mismatch")
    if str(result.get("comparison_analysis_id") or "").strip() != identity["analysis_run_id"]:
        raise ValueError("comparison_analysis_id_mismatch")
    for collection in _finding_collections(result):
        for finding in collection:
            for key, expected_value in (
                ("comparison_analysis_id", identity["analysis_run_id"]),
                ("baseline_id", identity["baseline_id"]),
                ("comparison_dataset_id", identity["comparison_dataset_id"]),
            ):
                if str(finding.get(key) or "").strip() != expected_value:
                    raise ValueError(f"finding_{key}_mismatch")
    return identity


def persist_completed_analysis(result: dict[str, Any]) -> dict[str, str] | None:
    if str(result.get("workflow") or "") != WORKFLOW_ANALYZE_NEW_DATA:
        return None
    scope = dataset_scope_from_payload(result) or current_dataset_scope()
    identity = validate_completed_analysis(result, scope=scope)
    package = ensure_evidence_package(result)
    record = {
        **identity,
        "analysis_record_version": 1,
        "comparison_analysis_id": identity["analysis_run_id"],
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
    if package:
        _write(
            _package_id_key(package["id"], scope=scope),
            {**identity, "package_id": package["id"], "analysis_run_id": identity["analysis_run_id"]},
            scope=scope,
        )
        lifecycle = initial_lifecycle(package)
        lifecycle_key = _package_lifecycle_key(package["id"], scope=scope)
        if _read(lifecycle_key, scope=scope) is None:
            _write(
                lifecycle_key,
                {"package_id": package["id"], "lifecycle": lifecycle.model_dump(mode="json")},
                scope=scope,
            )
    _write(
        _analysis_id_key(identity["analysis_run_id"], scope=scope),
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
    if package:
        try:
            _persist_fingerprint(package, scope=scope)
        except Exception:
            # Completed analysis is authoritative and must remain readable when
            # publication of its derived fingerprint fails.
            logger.exception("evidence_package_fingerprint_publication_failed package_id=%s", package["id"])
    return identity


def _persist_fingerprint(package: dict[str, Any], *, scope: DatasetScope) -> None:
    """Publish an immutable sidecar, then an independent available-only entry."""
    fingerprint = build_fingerprint(package)
    key = _package_fingerprint_key(package["id"], scope=scope)
    existing = _read(key, scope=scope)
    if isinstance(existing, dict) and payload_matches_dataset_scope(existing, scope):
        try:
            fingerprint = EvidencePackageFingerprint.model_validate(existing.get("fingerprint"))
        except (ValueError, TypeError):
            # Corrupt records are not silently repaired by ordinary persistence.
            return
    else:
        _write(key, {"package_id": package["id"], "fingerprint": fingerprint.model_dump(mode="json")}, scope=scope)
    stored = _read(key, scope=scope)
    try:
        persisted = EvidencePackageFingerprint.model_validate((stored or {}).get("fingerprint"))
    except (ValueError, TypeError):
        raise RuntimeError("fingerprint_sidecar_not_persisted")
    scope_valid = (
        payload_matches_dataset_scope(stored, scope)
        and persisted.scope.organization_id == scope.tenant_id
        and persisted.scope.workspace_id == scope.workspace_id
        and persisted.package_id == package["id"]
    )
    if not (
        scope_valid
        and persisted.status == FingerprintStatus.available
        and persisted.fingerprint_id
        and persisted.canonical_digest
        and persisted.scope.system_id
    ):
        return
    entry_key = _fingerprint_index_entry_key(persisted.scope.system_id, package["id"], scope=scope)
    _write(entry_key, {
        "version": 1, "algorithm_version": ALGORITHM_VERSION,
        "organization_id": scope.tenant_id, "portfolio_id": scope.workspace_id,
        "system_id": persisted.scope.system_id, "package_id": package["id"],
        "fingerprint_id": persisted.fingerprint_id, "canonical_digest": persisted.canonical_digest,
        "evaluated_at": package.get("latest_evaluated_at"),
    }, scope=scope)


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


def read_completed_analysis_by_id(analysis_run_id: str) -> dict[str, Any] | None:
    scope = current_dataset_scope()
    requested_id = str(analysis_run_id or "").strip()
    if not requested_id:
        return None
    link = _read(_analysis_id_key(requested_id, scope=scope), scope=scope)
    if not isinstance(link, dict) or not payload_matches_dataset_scope(link, scope):
        return None
    baseline_id = str(link.get("baseline_id") or "").strip()
    system_id = str(link.get("system_id") or "").strip()
    portfolio_id = str(link.get("portfolio_id") or "").strip()
    if not baseline_id or not system_id or not portfolio_id:
        return None
    return read_completed_analysis(
        baseline_id,
        requested_id,
        portfolio_id=portfolio_id,
        system_id=system_id,
    )


def read_evidence_package_by_analysis_id(analysis_run_id: str) -> dict[str, Any] | None:
    result = read_completed_analysis_by_id(analysis_run_id)
    package = ensure_evidence_package(result) if isinstance(result, dict) else None
    if package is None:
        return None
    scope = current_dataset_scope()
    stored = _read(_package_lifecycle_key(package["id"], scope=scope), scope=scope)
    lifecycle_payload = stored.get("lifecycle") if isinstance(stored, dict) and payload_matches_dataset_scope(stored, scope) else None
    lifecycle = initial_lifecycle({**package, "lifecycle": lifecycle_payload}) if isinstance(lifecycle_payload, dict) else initial_lifecycle(package)
    return {**package, "lifecycle": lifecycle.model_dump(mode="json")}


def read_evidence_package_by_id(package_id: str) -> dict[str, Any] | None:
    scope = current_dataset_scope()
    link = _read(_package_id_key(str(package_id), scope=scope), scope=scope)
    if not isinstance(link, dict) or not payload_matches_dataset_scope(link, scope):
        return None
    package = read_evidence_package_by_analysis_id(str(link.get("analysis_run_id") or ""))
    return package if package and package.get("id") == str(package_id) else None


def read_evidence_package_fingerprint(package_id: str) -> EvidencePackageFingerprint | None:
    """Pure sidecar read; absence never triggers generation or repair."""
    package = read_evidence_package_by_id(package_id)
    if package is None:
        return None
    scope = current_dataset_scope()
    stored = _read(_package_fingerprint_key(package_id, scope=scope), scope=scope)
    if not isinstance(stored, dict) or not payload_matches_dataset_scope(stored, scope):
        return EvidencePackageFingerprint(
            status=FingerprintStatus.unavailable, package_id=package_id,
            scope={"organization_id": package["organization_id"], "workspace_id": package.get("portfolio_id") or "", "system_id": package.get("system_id")},
            features={}, available_dimensions=[], unavailable_dimensions=["persisted_fingerprint"], evidence_refs=[],
            limitations=["No persisted fingerprint is available; reads do not generate one."],
            provenance={"source_schema_version": package["schema_version"], "package_revision": package["revision"], "source": "fingerprint_sidecar_read", "calculation_versions": []},
        )
    try:
        fingerprint = EvidencePackageFingerprint.model_validate(stored.get("fingerprint"))
    except (ValueError, TypeError):
        return None
    expected = (scope.tenant_id, scope.workspace_id, package.get("system_id"))
    actual = (fingerprint.scope.organization_id, fingerprint.scope.workspace_id, fingerprint.scope.system_id)
    return fingerprint if actual == expected and fingerprint.package_id == package_id else None


def read_exact_fingerprint_matches(package_id: str) -> ExactMatchResult | None:
    package = read_evidence_package_by_id(package_id)
    if package is None:
        return None
    fingerprint = read_evidence_package_fingerprint(package_id)
    if fingerprint is None or fingerprint.status != FingerprintStatus.available or not fingerprint.scope.system_id:
        return ExactMatchResult(
            status=ExactMatchStatus.unavailable, evaluated_package_id=package_id,
            evaluated_fingerprint_id=fingerprint.fingerprint_id if fingerprint else None,
            limitations=["Required persisted fingerprint or system scope evidence is unavailable."],
        )
    evaluated_at = parse_timestamp(package.get("latest_evaluated_at"))
    if evaluated_at is None:
        return ExactMatchResult(
            status=ExactMatchStatus.unavailable, evaluated_package_id=package_id,
            evaluated_fingerprint_id=fingerprint.fingerprint_id,
            limitations=["The evaluated package timestamp is missing, invalid, or not timezone-aware."],
        )
    scope = current_dataset_scope()
    entries = list_shared_state_prefix(f"{_fingerprint_index_prefix(fingerprint.scope.system_id, scope=scope)}/", scope=scope)
    candidates: list[tuple[datetime, str, EvidencePackageFingerprint]] = []
    for entry in entries:
        if not payload_matches_dataset_scope(entry, scope):
            return ExactMatchResult(status=ExactMatchStatus.unavailable, evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, limitations=["The fingerprint index scope is invalid."])
        if (entry.get("organization_id"), entry.get("portfolio_id"), entry.get("system_id"), entry.get("algorithm_version")) != (scope.tenant_id, scope.workspace_id, fingerprint.scope.system_id, ALGORITHM_VERSION):
            return ExactMatchResult(status=ExactMatchStatus.unavailable, evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, limitations=["The fingerprint index scope is invalid."])
        if not entry.get("fingerprint_id") or not entry.get("canonical_digest"):
            return ExactMatchResult(status=ExactMatchStatus.unavailable, evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, limitations=["The fingerprint index contains an incomplete entry."])
        if entry.get("package_id") == package_id:
            continue
        timestamp = parse_timestamp(entry.get("evaluated_at"))
        if timestamp is None:
            return ExactMatchResult(status=ExactMatchStatus.unavailable, evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, limitations=["Eligible history contains an invalid package timestamp."])
        if timestamp >= evaluated_at:
            continue
        prior_id = str(entry.get("package_id") or "")
        prior_package = read_evidence_package_by_id(prior_id)
        prior_package_timestamp = parse_timestamp((prior_package or {}).get("latest_evaluated_at"))
        if prior_package is None or prior_package_timestamp != timestamp:
            return ExactMatchResult(status=ExactMatchStatus.unavailable, evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, limitations=["Eligible history contains a stale package reference or inconsistent timestamp."])
        stored = _read(_package_fingerprint_key(prior_id, scope=scope), scope=scope)
        try:
            prior = EvidencePackageFingerprint.model_validate((stored or {}).get("fingerprint"))
        except (ValueError, TypeError):
            return ExactMatchResult(status=ExactMatchStatus.unavailable, evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, limitations=["Eligible history contains a stale fingerprint reference."])
        if (
            not payload_matches_dataset_scope(stored, scope)
            or prior.package_id != prior_id
            or prior.scope != fingerprint.scope
            or prior.status != FingerprintStatus.available
            or prior.fingerprint_id != entry.get("fingerprint_id")
            or prior.canonical_digest != entry.get("canonical_digest")
        ):
            return ExactMatchResult(status=ExactMatchStatus.unavailable, evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, limitations=["Eligible history contains unavailable or scope-invalid fingerprint evidence."])
        candidates.append((timestamp, prior_id, prior))
    candidates.sort(key=lambda item: (item[0], item[1]))
    matches = []
    basis = "same_scope_system_algorithm_and_strictly_earlier_evaluation_v1"
    for _, prior_id, prior in candidates:
        if prior.canonical_digest != fingerprint.canonical_digest:
            continue
        matches.append(ExactMatchObservation(
            observation_id=observation_id(package_id, prior_id, ALGORITHM_VERSION, basis),
            evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id or "",
            prior_package_id=prior_id, prior_fingerprint_id=prior.fingerprint_id or "",
            canonical_digest=fingerprint.canonical_digest or "", algorithm_version=ALGORITHM_VERSION,
            eligibility_basis="Persisted fingerprint evidence was available for both packages.",
            scope_basis="Tenant, workspace, and persisted system identity are equal.",
            temporal_basis="Prior package evaluation completed strictly earlier; this is not fault-onset ordering.",
            evidence_refs=sorted(set(fingerprint.evidence_refs + prior.evidence_refs)), limitations=[],
        ))
    status = ExactMatchStatus.exact_match if matches else (ExactMatchStatus.no_exact_match if candidates else ExactMatchStatus.insufficient_history)
    return ExactMatchResult(status=status, evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, matches=matches, eligible_history_count=len(candidates))


def read_approximate_fingerprint_similarity(package_id: str) -> ApproximateSimilarityResponse | None:
    """Purely compare a package sidecar with valid, same-system, earlier sidecars."""
    package = read_evidence_package_by_id(package_id)
    if package is None:
        return None
    fingerprint = read_evidence_package_fingerprint(package_id)
    if fingerprint is None or fingerprint.status != FingerprintStatus.available or not fingerprint.scope.system_id or fingerprint.algorithm_version != ALGORITHM_VERSION:
        return ApproximateSimilarityResponse(
            evaluated_package_id=package_id,
            evaluated_fingerprint_id=fingerprint.fingerprint_id if fingerprint else None,
            overall_status="unavailable",
            limitations=["Required persisted fingerprint or system scope evidence is unavailable."],
        )
    evaluated_at = parse_timestamp(package.get("latest_evaluated_at"))
    if evaluated_at is None:
        return ApproximateSimilarityResponse(
            evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id,
            overall_status="unavailable", limitations=["The evaluated package timestamp is missing, invalid, or not timezone-aware."],
        )
    scope = current_dataset_scope()
    entries = list_shared_state_prefix(f"{_fingerprint_index_prefix(fingerprint.scope.system_id, scope=scope)}/", scope=scope)
    candidates: list[tuple[datetime, str, EvidencePackageFingerprint]] = []
    for entry in entries:
        expected_index = (scope.tenant_id, scope.workspace_id, fingerprint.scope.system_id, ALGORITHM_VERSION)
        actual_index = (entry.get("organization_id"), entry.get("portfolio_id"), entry.get("system_id"), entry.get("algorithm_version"))
        if not payload_matches_dataset_scope(entry, scope) or actual_index != expected_index:
            return ApproximateSimilarityResponse(evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, overall_status="unavailable", limitations=["The fingerprint index scope is invalid."])
        prior_id = str(entry.get("package_id") or "")
        if prior_id == package_id:
            continue
        timestamp = parse_timestamp(entry.get("evaluated_at"))
        if timestamp is None:
            return ApproximateSimilarityResponse(evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, overall_status="unavailable", limitations=["Eligible history contains an invalid package timestamp."])
        if timestamp >= evaluated_at:
            continue
        prior_package = read_evidence_package_by_id(prior_id)
        if prior_package is None or parse_timestamp(prior_package.get("latest_evaluated_at")) != timestamp:
            return ApproximateSimilarityResponse(evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, overall_status="unavailable", limitations=["Eligible history contains a stale package reference or inconsistent timestamp."])
        stored = _read(_package_fingerprint_key(prior_id, scope=scope), scope=scope)
        try:
            prior = EvidencePackageFingerprint.model_validate((stored or {}).get("fingerprint"))
        except (ValueError, TypeError):
            return ApproximateSimilarityResponse(evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, overall_status="unavailable", limitations=["Eligible history contains a stale fingerprint reference."])
        if (
            not payload_matches_dataset_scope(stored, scope) or prior.package_id != prior_id
            or prior.scope != fingerprint.scope or prior.status != FingerprintStatus.available
            or prior.fingerprint_id != entry.get("fingerprint_id") or prior.canonical_digest != entry.get("canonical_digest")
        ):
            return ApproximateSimilarityResponse(evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id, overall_status="unavailable", limitations=["Eligible history contains unavailable or scope-invalid fingerprint evidence."])
        candidates.append((timestamp, prior_id, prior))
    candidates.sort(key=lambda item: (item[0], item[1]))
    results = [compare_fingerprints(fingerprint, prior) for _, _, prior in candidates]
    status = aggregate_similarity_status(results)
    return ApproximateSimilarityResponse(
        evaluated_package_id=package_id, evaluated_fingerprint_id=fingerprint.fingerprint_id,
        overall_status=status, eligible_history_count=len(results), results=results,
    )


def transition_evidence_package_lifecycle(
    package_id: str, request: LifecycleTransitionRequest
) -> dict[str, Any] | None:
    with lifecycle_lock():
        package = read_evidence_package_by_id(package_id)
        if package is None:
            return None
        lifecycle = initial_lifecycle(package)
        updated = append_lifecycle_event(package, lifecycle, request)
        scope = current_dataset_scope()
        _write(
            _package_lifecycle_key(package_id, scope=scope),
            {"package_id": package_id, "lifecycle": updated.model_dump(mode="json")},
            scope=scope,
        )
        return {**package, "lifecycle": updated.model_dump(mode="json")}
