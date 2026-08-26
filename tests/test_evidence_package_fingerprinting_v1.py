from __future__ import annotations

from copy import deepcopy
import multiprocessing
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.services.evidence_package_fingerprint import (
    ALGORITHM_VERSION,
    EvidencePackageFingerprint,
    build_fingerprint,
    observation_id,
)
from app.services import baseline_analysis_repository as repository
from app.services.dataset_scope import current_dataset_scope
from app.services.runtime_db import configure_runtime_dir, list_latest_payloads_prefix
from app.services import runtime_db


def _write_independent_index_entry(
    runtime_dir: str,
    prefix: str,
    package_id: str,
    start_barrier,
) -> None:
    from app.services.runtime_db import configure_runtime_dir, upsert_latest_payload

    configure_runtime_dir(Path(runtime_dir))
    start_barrier.wait(timeout=30)
    upsert_latest_payload(f"{prefix}/{package_id}", {"package_id": package_id, "canonical_digest": f"digest-{package_id}"})


def _package(package_id: str = "package-a", relationship_type: str = "correlation") -> dict:
    return {
        "id": package_id, "schema_version": "evidence-package-v1", "revision": 1,
        "organization_id": "tenant-a", "portfolio_id": "workspace-a", "system_id": "system-a",
        "condition_type": "persistent_relationship_change",
        "primary_relationship": {
            "left_variable": "signal-z", "right_variable": "signal-a",
            "relationship_type": relationship_type, "baseline_strength": 0.123456785,
            "comparison_strength": 0.25, "signed_change": 0.126543215,
            "absolute_change": 0.126543215, "persistence_score": None,
        },
        "operating_context": None,
        "supporting_evidence": [
            {"id": "ev-comparison-strength", "quality_status": "recorded", "calculation_version": "calc-v1"},
            {"id": "ev-absolute-change", "quality_status": "recorded", "calculation_version": "calc-v1"},
            {"id": "ev-baseline-strength", "quality_status": "recorded", "calculation_version": "calc-v1"},
        ],
    }


def test_canonical_fingerprint_is_stable_across_repetition_mapping_and_unordered_inputs() -> None:
    package = _package()
    first = build_fingerprint(package)
    reordered = {key: package[key] for key in reversed(package)}
    reordered["supporting_evidence"] = list(reversed(package["supporting_evidence"]))
    second = build_fingerprint(reordered)
    assert first == second
    assert first.canonical_digest == second.canonical_digest
    assert first.features["relationship"]["baseline_strength"] == "0.12345678"
    assert first.unavailable_dimensions == ["operating_context", "quantified_persistence"]
    assert "persistence" not in first.features["relationship"]


def test_symmetric_reversal_is_equal_but_directed_reversal_is_distinct() -> None:
    symmetric = _package()
    reversed_symmetric = deepcopy(symmetric)
    reversed_symmetric["primary_relationship"]["left_variable"] = "signal-a"
    reversed_symmetric["primary_relationship"]["right_variable"] = "signal-z"
    assert build_fingerprint(symmetric).canonical_digest == build_fingerprint(reversed_symmetric).canonical_digest

    directed = _package(relationship_type="model_edge")
    reversed_directed = deepcopy(directed)
    reversed_directed["primary_relationship"]["left_variable"] = "signal-a"
    reversed_directed["primary_relationship"]["right_variable"] = "signal-z"
    assert build_fingerprint(directed).canonical_digest != build_fingerprint(reversed_directed).canonical_digest


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_values_are_rejected(value: float) -> None:
    package = _package()
    package["primary_relationship"]["baseline_strength"] = value
    with pytest.raises(ValueError, match="not_finite"):
        build_fingerprint(package)


def test_algorithm_namespace_identity_and_strict_schema() -> None:
    package = _package()
    first = build_fingerprint(package)
    changed = build_fingerprint(package, algorithm_version="evidence-package-canonical-sha256-v2")
    assert first.canonical_digest != changed.canonical_digest
    assert first.package_id != first.fingerprint_id
    other = build_fingerprint(_package("package-b"))
    assert first.canonical_digest == other.canonical_digest
    assert first.package_id != other.package_id
    assert observation_id("a", "b", ALGORITHM_VERSION, "basis") == observation_id("a", "b", ALGORITHM_VERSION, "basis")
    payload = first.model_dump()
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        EvidencePackageFingerprint.model_validate(payload)


def test_missing_required_structure_is_explicitly_unavailable_not_zero() -> None:
    package = _package()
    package["system_id"] = None
    package["primary_relationship"]["signed_change"] = None
    fingerprint = build_fingerprint(package)
    assert fingerprint.status.value == "unavailable"
    assert fingerprint.canonical_digest is None
    assert fingerprint.features == {}
    assert {"system_id", "signed_change"}.issubset(fingerprint.unavailable_dimensions)


def test_lifecycle_and_display_fields_do_not_change_equivalence() -> None:
    first = _package()
    second = deepcopy(first)
    second.update({"title": "A fuzzy display label", "filename": "same-looking.csv", "lifecycle": {"status": "RESOLVED"}})
    assert build_fingerprint(first).canonical_digest == build_fingerprint(second).canonical_digest


def test_exact_match_history_is_strictly_earlier_and_deterministically_ordered(monkeypatch) -> None:
    scope = current_dataset_scope()
    evaluated_package = _package("evaluated")
    evaluated_package.update({"organization_id": scope.tenant_id, "portfolio_id": scope.workspace_id, "latest_evaluated_at": "2026-08-04T12:00:00Z"})
    evaluated = build_fingerprint(evaluated_package)
    priors = {}
    for package_id in ("prior-b", "prior-a"):
        package = deepcopy(evaluated_package)
        package["id"] = package_id
        priors[package_id] = build_fingerprint(package)

    prior_packages = {
        package_id: {**deepcopy(evaluated_package), "id": package_id, "latest_evaluated_at": "2026-08-03T12:00:00Z"}
        for package_id in priors
    }
    monkeypatch.setattr(repository, "read_evidence_package_by_id", lambda package_id: evaluated_package if package_id == "evaluated" else prior_packages.get(package_id))
    monkeypatch.setattr(repository, "read_evidence_package_fingerprint", lambda package_id: evaluated if package_id == "evaluated" else None)

    index_entries = [
        {"package_id": "evaluated", "evaluated_at": "2026-08-04T12:00:00Z", "fingerprint_id": evaluated.fingerprint_id, "canonical_digest": evaluated.canonical_digest},
        {"package_id": "future", "evaluated_at": "2026-08-05T12:00:00Z", "fingerprint_id": "sha256:future", "canonical_digest": "future"},
        {"package_id": "prior-b", "evaluated_at": "2026-08-03T12:00:00Z", "fingerprint_id": priors["prior-b"].fingerprint_id, "canonical_digest": priors["prior-b"].canonical_digest},
        {"package_id": "prior-a", "evaluated_at": "2026-08-03T12:00:00Z", "fingerprint_id": priors["prior-a"].fingerprint_id, "canonical_digest": priors["prior-a"].canonical_digest},
    ]
    for entry in index_entries:
        entry.update({"dataset_scope": scope.as_dict(), "organization_id": scope.tenant_id, "portfolio_id": scope.workspace_id, "system_id": "system-a", "algorithm_version": ALGORITHM_VERSION})

    def fake_read(name, *, scope=None):
        if "/fingerprint-index/" in name:
            return index
        package_id = next((item for item in priors if f"/{item}/" in name), None)
        if package_id:
            return {"dataset_scope": scope.as_dict(), "fingerprint": priors[package_id].model_dump(mode="json")}
        return None

    monkeypatch.setattr(repository, "_read", fake_read)
    monkeypatch.setattr(repository, "list_shared_state_prefix", lambda *args, **kwargs: index_entries)
    result = repository.read_exact_fingerprint_matches("evaluated")
    assert result.status.value == "exact_match"
    assert [match.prior_package_id for match in result.matches] == ["prior-a", "prior-b"]
    assert all("fault-onset" in match.temporal_basis for match in result.matches)
    assert result.eligible_history_count == 2


def test_exact_match_empty_history_is_insufficient(monkeypatch) -> None:
    scope = current_dataset_scope()
    package = _package("evaluated")
    package.update({"organization_id": scope.tenant_id, "portfolio_id": scope.workspace_id, "latest_evaluated_at": "2026-08-04T12:00:00Z"})
    fingerprint = build_fingerprint(package)
    monkeypatch.setattr(repository, "read_evidence_package_by_id", lambda package_id: package)
    monkeypatch.setattr(repository, "read_evidence_package_fingerprint", lambda package_id: fingerprint)
    monkeypatch.setattr(repository, "list_shared_state_prefix", lambda *args, **kwargs: [])
    assert repository.read_exact_fingerprint_matches("evaluated").status.value == "insufficient_history"


def test_independent_index_entries_survive_separate_process_connections(tmp_path) -> None:
    original_runtime_dir = runtime_db.RUNTIME_DIR
    runtime_dir = tmp_path / "concurrent-runtime"
    runtime_dir.mkdir()
    prefix = "scopes/scope-a/baseline-analyses/fingerprint-index/system-a/evidence-package-canonical-sha256-v1"
    context = multiprocessing.get_context("spawn")
    start_barrier = context.Barrier(12)
    processes = [
        context.Process(
            target=_write_independent_index_entry,
            args=(str(runtime_dir), prefix, f"package-{index}", start_barrier),
        )
        for index in range(8)
    ] + [
        context.Process(
            target=_write_independent_index_entry,
            args=(str(runtime_dir), prefix, "package-0", start_barrier),
        )
        for _ in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    try:
        configure_runtime_dir(runtime_dir)
        entries = list_latest_payloads_prefix(prefix)
        assert {entry["package_id"] for entry in entries} == {f"package-{index}" for index in range(8)}
        assert len(entries) == 8
    finally:
        configure_runtime_dir(original_runtime_dir)
