from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import baseline_analysis_repository as repository
from app.services import evidence_correlation as correlation
from app.services.baseline_analysis_repository import persist_completed_analysis, stamp_comparison_analysis_identity
from app.services.dataset_scope import attach_dataset_scope, current_dataset_scope
from app.services.evidence_correlation import (
    RELATIONSHIP_SCHEMA_VERSION,
    build_relationship,
    build_source_projection,
    relationship_id_for,
)
from app.services.evidence_package_lifecycle import LifecycleTransitionRequest
from app.services.runtime_db import DB_PATH
from app.services.upload_state_repository import write_upload_result


def comparison(
    run_id: str,
    *,
    completed_at: str,
    window_start: str | None,
    window_end: str | None,
    system_id: str = "chilled-water-1",
) -> dict:
    scope = current_dataset_scope()
    result = {
        "job_id": run_id,
        "run_id": run_id,
        "dataset_id": f"dataset-{run_id}",
        "organization_id": scope.tenant_id,
        "portfolio_id": scope.workspace_id,
        "system_id": system_id,
        "baseline_id": "baseline-correlation",
        "baseline_dataset_id": "baseline-dataset-correlation",
        "comparison_dataset_id": f"dataset-{run_id}",
        "comparison_analysis_id": run_id,
        "analysis_run_id": run_id,
        "workflow": "analyze_new_data",
        "status": "COMPLETE",
        "processing_state": "complete",
        "sii_completed": True,
        "completed_at": completed_at,
        "active_baseline_reference": {
            "model_id": "baseline-correlation",
            "version": 1,
            "dataset_id": "baseline-dataset-correlation",
        },
        "conditions": [
            {
                "id": f"condition-{run_id}",
                "headline": f"Finding {run_id}",
                "system": "Chilled Water",
            }
        ],
        "baseline_analysis": {
            "baseline_model_id": "baseline-correlation",
            "relationship_drift": [
                {
                    "left": "pump_power_kw",
                    "right": "chw_flow_gpm",
                    "direction": "weakened",
                    "baseline_correlation": 0.9,
                    "recent_correlation": 0.4,
                    "correlation_delta": 0.5,
                    "baseline_sample_count": 48,
                    "recent_sample_count": 48,
                    "persistence_score": 1.0,
                }
            ],
        },
        "operating_context_inputs": {
            "schema_version": "operating-context-input-v1",
            "source": "analysis_metadata",
            "baseline": {
                "process_demand": {
                    "canonical_role": "process_demand",
                    "source_variable": "cooling_load_tons",
                    "unit": "tons",
                    "count": 48,
                    "mean": 300,
                    "min": 200,
                    "max": 400,
                    "source": "baseline_model",
                }
            },
            "comparison": {
                "process_demand": {
                    "canonical_role": "process_demand",
                    "source_variable": "cooling_load_tons",
                    "unit": "tons",
                    "count": 48,
                    "mean": 300,
                    "min": 200,
                    "max": 400,
                    "early_median": 300,
                    "late_median": 302,
                    "source": "telemetry",
                }
            },
            "windows": {
                "baseline": {"start": "2026-07-01T00:00:00Z", "end": "2026-07-01T01:00:00Z"},
                "comparison": {"start": window_start, "end": window_end},
            },
        },
    }
    return stamp_comparison_analysis_identity(
        attach_dataset_scope(result, scope=scope, dataset_id=result["dataset_id"])
    )


def persist(result: dict) -> dict:
    write_upload_result(result["job_id"], result)
    assert persist_completed_analysis(result) is not None
    package = repository.read_evidence_package_by_analysis_id(result["job_id"])
    assert package is not None
    return package


def client() -> TestClient:
    return TestClient(create_app())


def test_current_packages_persist_deterministic_explainable_relationships() -> None:
    first = persist(
        comparison(
            "correlation-a",
            completed_at="2026-08-01T03:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T02:00:00Z",
        )
    )
    second = persist(
        comparison(
            "correlation-b",
            completed_at="2026-08-01T04:00:00Z",
            window_start="2026-08-01T01:00:00Z",
            window_end="2026-08-01T03:00:00Z",
        )
    )

    first_read = client().get(f"/api/data/evidence-packages/{first['id']}/related-packages")
    second_read = client().get(f"/api/data/evidence-packages/{first['id']}/related-packages")

    assert first_read.status_code == 200
    assert first_read.json() == second_read.json()
    payload = first_read.json()
    assert payload["schema_version"] == "neraium.evidence-package-related-set.v1"
    assert payload["correlation_status"] == "related_packages_found"
    assert [item["package_id"] for item in payload["related_packages"]] == [second["id"]]
    relationship = payload["related_packages"][0]
    assert relationship["relationship_id"] == relationship_id_for(
        tenant_id=current_dataset_scope().tenant_id,
        workspace_id=current_dataset_scope().workspace_id,
        system_id="chilled-water-1",
        package_a_id=first["id"],
        package_b_id=second["id"],
    )
    assert relationship["strongest_supported_relationship"] == "overlapping_observation_window"
    assert relationship["supporting_relationships"] == [
        "overlapping_observation_window",
        "compatible_operating_context",
        "same_system",
    ]
    assert relationship["temporal_relationship"] == "overlapping_observation_window"
    assert relationship["operating_context_relationship"] == "compatible"
    assert relationship["signal_or_system_overlap"] == {
        "same_system": True,
        "shared_canonical_signal_ids": [],
        "shared_analytical_pattern_ids": [],
    }
    assert relationship["evidence_refs"] == sorted(relationship["evidence_refs"])
    assert not any("pump_power_kw" in reference for reference in relationship["evidence_refs"])
    assert client().get(
        f"/api/data/evidence-packages/{first['id']}/related-packages",
        headers={"X-Neraium-Workspace-Id": "foreign-workspace"},
    ).status_code == 404


def test_temporal_adjacency_is_bounded_and_system_scope_is_exact() -> None:
    anchor = persist(
        comparison(
            "correlation-anchor",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    adjacent = persist(
        comparison(
            "correlation-adjacent",
            completed_at="2026-08-02T03:00:00Z",
            window_start="2026-08-02T01:00:00Z",
            window_end="2026-08-02T02:00:00Z",
        )
    )
    persist(
        comparison(
            "correlation-distant",
            completed_at="2026-08-05T03:00:00Z",
            window_start="2026-08-05T01:00:00Z",
            window_end="2026-08-05T02:00:00Z",
        )
    )
    persist(
        comparison(
            "correlation-other-system",
            completed_at="2026-08-01T03:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
            system_id="condenser-water-1",
        )
    )

    payload = client().get(f"/api/data/evidence-packages/{anchor['id']}/related-packages").json()

    assert [item["package_id"] for item in payload["related_packages"]] == [adjacent["id"]]
    assert payload["related_packages"][0]["temporal_relationship"] == "temporally_adjacent"


def test_explicit_signal_and_pattern_ids_anchor_without_using_names_or_similarity() -> None:
    base = persist(
        comparison(
            "correlation-explicit",
            completed_at="2026-08-01T02:00:00Z",
            window_start=None,
            window_end=None,
        )
    )
    first = deepcopy(base)
    first.update(
        {
            "id": "package-explicit-a",
            "canonical_signal_ids": ["chw.flow"],
            "analytical_pattern_ids": ["pattern:hydraulic-shift"],
            "historical_pattern_classification": "similar_historical_pattern",
        }
    )
    second = deepcopy(base)
    second.update(
        {
            "id": "package-explicit-b",
            "canonical_signal_ids": ["chw.flow"],
            "historical_pattern_ids": ["pattern:hydraulic-shift"],
            "historical_pattern_classification": "similar_historical_pattern",
        }
    )
    first_source = build_source_projection(first)
    second_source = build_source_projection(second)
    assert first_source and second_source

    relationship = build_relationship(first_source, second_source)

    assert relationship is not None
    assert relationship["strongest_supported_relationship"] == "shared_canonical_signal"
    assert relationship["signal_or_system_overlap"]["shared_canonical_signal_ids"] == ["chw.flow"]
    assert relationship["signal_or_system_overlap"]["shared_analytical_pattern_ids"] == [
        "pattern:hydraulic-shift"
    ]
    assert "historical_pattern_classification" not in json.dumps(relationship)


def test_same_system_and_operating_context_are_not_relationship_anchors() -> None:
    first = comparison(
        "correlation-scope-only-a",
        completed_at="2026-08-01T02:00:00Z",
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-01T01:00:00Z",
    )["evidence_package"]
    second = comparison(
        "correlation-scope-only-b",
        completed_at="2026-09-01T02:00:00Z",
        window_start="2026-09-01T00:00:00Z",
        window_end="2026-09-01T01:00:00Z",
    )["evidence_package"]

    assert build_relationship(build_source_projection(first), build_source_projection(second)) is None


def test_invalid_window_is_unavailable_but_an_explicit_signal_can_anchor() -> None:
    first = comparison(
        "correlation-invalid-window-a",
        completed_at="2026-08-01T02:00:00Z",
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-01T01:00:00Z",
    )["evidence_package"]
    second = deepcopy(first)
    second["id"] = "package-invalid-window-b"
    second["operating_context"]["comparison_window"] = {
        "start": "2026-08-02T02:00:00Z",
        "end": "2026-08-02T01:00:00Z",
        "source": "analysis_metadata",
    }
    first["canonical_signal_ids"] = ["chw.flow"]
    second["canonical_signal_ids"] = ["chw.flow"]

    relationship = build_relationship(build_source_projection(first), build_source_projection(second))

    assert relationship is not None
    assert relationship["strongest_supported_relationship"] == "shared_canonical_signal"
    assert relationship["temporal_relationship"] == "unavailable"
    assert "observation_window_unavailable" in relationship["limitations"]


def test_explicit_site_or_equipment_conflicts_exclude_a_pair() -> None:
    package = comparison(
        "correlation-optional-scope",
        completed_at="2026-08-01T02:00:00Z",
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-01T01:00:00Z",
    )["evidence_package"]
    first = {**deepcopy(package), "id": "package-scope-a", "site_id": "plant-a", "equipment_id": "pump-1"}
    other_site = {**deepcopy(package), "id": "package-scope-b", "site_id": "plant-b", "equipment_id": "pump-1"}
    other_equipment = {**deepcopy(package), "id": "package-scope-c", "site_id": "plant-a", "equipment_id": "pump-2"}

    first_source = build_source_projection(first)
    assert build_relationship(first_source, build_source_projection(other_site)) is None
    assert build_relationship(first_source, build_source_projection(other_equipment)) is None


def test_fingerprint_similarity_and_descriptive_history_do_not_anchor_relationships() -> None:
    first = comparison(
        "correlation-independent-a",
        completed_at="2026-08-01T02:00:00Z",
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-01T01:00:00Z",
    )["evidence_package"]
    second = comparison(
        "correlation-independent-b",
        completed_at="2026-09-01T02:00:00Z",
        window_start="2026-09-01T00:00:00Z",
        window_end="2026-09-01T01:00:00Z",
    )["evidence_package"]
    for package in (first, second):
        package.update({
            "fingerprint_id": "sha256:shared",
            "exact_historical_match": {"status": "match"},
            "approximate_similarity": {"status": "supported_similarity", "score": 1.0},
            "historical_pattern_classification": "similar_historical_pattern",
        })

    first_source = build_source_projection(first)
    second_source = build_source_projection(second)

    assert first_source["package_fingerprint_id"] == "sha256:shared"
    assert "historical_pattern_classification" not in first_source
    assert build_relationship(first_source, second_source) is None


def test_legacy_package_is_unavailable_and_get_is_byte_pure(monkeypatch) -> None:
    monkeypatch.setattr(repository, "persist_completed_package_projection", lambda *args, **kwargs: "disabled")
    package = persist(
        comparison(
            "correlation-legacy",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    before = sha256(DB_PATH.read_bytes()).hexdigest()

    first = client().get(f"/api/data/evidence-packages/{package['id']}/related-packages")
    second = client().get(f"/api/data/evidence-packages/{package['id']}/related-packages")

    assert first.json() == second.json()
    assert first.json()["correlation_status"] == "unavailable"
    assert first.json()["limitations"] == ["legacy_package_without_correlation_projection"]
    assert sha256(DB_PATH.read_bytes()).hexdigest() == before


def test_get_does_not_invoke_runtime_initialization(monkeypatch) -> None:
    package = persist(
        comparison(
            "correlation-pure-runtime-read",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    monkeypatch.setattr(
        correlation.runtime_db,
        "init_runtime_db",
        lambda: (_ for _ in ()).throw(AssertionError("GET attempted runtime initialization")),
    )

    payload = correlation.get_related_package_set(package["id"])

    assert payload["correlation_status"] == "no_supported_relationship"


def test_projection_is_insert_only_and_a_revision_conflict_does_not_overwrite() -> None:
    package = comparison(
        "correlation-revision",
        completed_at="2026-08-01T02:00:00Z",
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-01T01:00:00Z",
    )["evidence_package"]
    scope = current_dataset_scope()
    assert correlation.persist_completed_package_projection(package, scope=scope) == "created"
    assert correlation.persist_completed_package_projection(package, scope=scope) == "idempotent"
    original = correlation._read(correlation._source_key(package["id"], scope), scope=scope)

    revised = deepcopy(package)
    revised["revision"] = 2
    revised["provenance"]["revision"] = 2
    revised["provenance"]["last_update_reason"] = "future_revision"

    assert correlation.persist_completed_package_projection(revised, scope=scope) == "conflict"
    assert correlation._read(correlation._source_key(package["id"], scope), scope=scope) == original
    assert original["source"]["package_revision"] == 1


def test_concurrent_projection_converges_on_one_append_only_pair(monkeypatch) -> None:
    monkeypatch.setattr(repository, "persist_completed_package_projection", lambda *args, **kwargs: "disabled")
    first = persist(
        comparison(
            "correlation-concurrent-a",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    second = persist(
        comparison(
            "correlation-concurrent-b",
            completed_at="2026-08-01T03:00:00Z",
            window_start="2026-08-01T00:30:00Z",
            window_end="2026-08-01T01:30:00Z",
        )
    )
    scope = current_dataset_scope()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(correlation.persist_completed_package_projection, package, scope=scope)
            for package in (first, second)
        ]
        statuses = [future.result() for future in futures]

    assert sorted(statuses) == ["created", "created"]
    relationships = correlation._list_pure(correlation._relationship_prefix(scope), scope=scope)
    assert len(relationships) == 1
    assert correlation.get_related_package_set(first["id"])["correlation_status"] == "related_packages_found"


def test_lifecycle_changes_do_not_mutate_or_stale_analytical_correlation() -> None:
    first = persist(
        comparison(
            "correlation-lifecycle-a",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    persist(
        comparison(
            "correlation-lifecycle-b",
            completed_at="2026-08-01T03:00:00Z",
            window_start="2026-08-01T00:30:00Z",
            window_end="2026-08-01T01:30:00Z",
        )
    )
    before = client().get(f"/api/data/evidence-packages/{first['id']}/related-packages").json()
    repository.transition_evidence_package_lifecycle(
        first["id"],
        LifecycleTransitionRequest(
            timestamp="2026-08-01T04:00:00Z",
            actor="user",
            event_type="package_acknowledged",
            reason="Accepted for investigation.",
        ),
    )

    after = client().get(f"/api/data/evidence-packages/{first['id']}/related-packages").json()

    assert after == before
    assert after["correlation_status"] == "related_packages_found"


def test_missing_candidate_source_fails_closed(monkeypatch) -> None:
    first = persist(
        comparison(
            "correlation-integrity-a",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    second = persist(
        comparison(
            "correlation-integrity-b",
            completed_at="2026-08-01T03:00:00Z",
            window_start="2026-08-01T00:30:00Z",
            window_end="2026-08-01T01:30:00Z",
        )
    )
    original_read = correlation._read_pure
    second_key = correlation._source_key(second["id"], current_dataset_scope())

    def missing_candidate(name: str, *, scope):
        if name == second_key:
            return None
        return original_read(name, scope=scope)

    monkeypatch.setattr(correlation, "_read_pure", missing_candidate)
    payload = client().get(f"/api/data/evidence-packages/{first['id']}/related-packages").json()
    assert payload["correlation_status"] == "unavailable"
    assert payload["limitations"] == ["related_package_projection_missing"]


def test_stale_source_fails_closed() -> None:
    package = persist(
        comparison(
            "correlation-stale-source",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    scope = current_dataset_scope()
    key = correlation._source_key(package["id"], scope)
    record = correlation._read(key, scope=scope)
    assert record is not None
    record["source"]["package_content_hash"] = "stale-content-hash"
    correlation._write(key, record, scope=scope)

    payload = client().get(f"/api/data/evidence-packages/{package['id']}/related-packages").json()
    assert payload["correlation_status"] == "unavailable"
    assert payload["limitations"] == ["stale_or_corrupt_correlation_sidecar"]


def test_corrupt_relationship_metadata_fails_closed() -> None:
    first = persist(
        comparison(
            "correlation-corrupt-relationship-a",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    persist(
        comparison(
            "correlation-corrupt-relationship-b",
            completed_at="2026-08-01T03:00:00Z",
            window_start="2026-08-01T00:30:00Z",
            window_end="2026-08-01T01:30:00Z",
        )
    )
    scope = current_dataset_scope()
    records = correlation._list_pure(correlation._relationship_prefix(scope), scope=scope)
    assert len(records) == 1
    record = records[0]
    record["system_id"] = "other-system"
    correlation._write(correlation._relationship_key(record["relationship_id"], scope), record, scope=scope)

    payload = client().get(f"/api/data/evidence-packages/{first['id']}/related-packages").json()

    assert payload["correlation_status"] == "unavailable"
    assert payload["limitations"] == ["stale_or_corrupt_correlation_sidecar"]


def test_missing_scope_projection_is_explicitly_insufficient() -> None:
    package = comparison(
        "correlation-insufficient",
        completed_at="2026-08-01T02:00:00Z",
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-01T01:00:00Z",
    )["evidence_package"]
    package["system_id"] = None

    source = build_source_projection(package)
    payload = correlation.response_payload(
        package["id"],
        status="insufficient_evidence",
        related_packages=[],
        limitations=source["limitations"],
    )

    assert "missing_required_scope" in source["limitations"]
    assert payload["correlation_status"] == "insufficient_evidence"
    assert payload["limitations"][0] == "missing_required_scope"


def test_publication_failure_preserves_completed_package(monkeypatch) -> None:
    result = comparison(
        "correlation-publication-failure",
        completed_at="2026-08-01T02:00:00Z",
        window_start="2026-08-01T00:00:00Z",
        window_end="2026-08-01T01:00:00Z",
    )
    write_upload_result(result["job_id"], result)
    monkeypatch.setattr(
        repository,
        "persist_completed_package_projection",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated_correlation_failure")),
    )

    assert persist_completed_analysis(result) is not None
    package = repository.read_evidence_package_by_analysis_id(result["job_id"])
    assert package is not None
    assert package["analysis_id"] == result["job_id"]


def test_schema_is_versioned_and_response_contains_no_causal_claims() -> None:
    assert RELATIONSHIP_SCHEMA_VERSION == "neraium.evidence-package-relationship.v1"
    package = persist(
        comparison(
            "correlation-nonclaim",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    serialized = json.dumps(
        client().get(f"/api/data/evidence-packages/{package['id']}/related-packages").json()
    ).casefold()
    for prohibited in ("root cause", "caused", "propagated", "diagnosis", "equipment failure"):
        assert prohibited not in serialized


def test_authenticated_tenant_and_workspace_boundaries_do_not_disclose_package_identity() -> None:
    package = persist(
        comparison(
            "correlation-auth-scope",
            completed_at="2026-08-01T02:00:00Z",
            window_start="2026-08-01T00:00:00Z",
            window_end="2026-08-01T01:00:00Z",
        )
    )
    endpoint = f"/api/data/evidence-packages/{package['id']}/related-packages"

    assert client().get(endpoint, headers={"X-Neraium-Workspace-Id": "foreign-workspace"}).status_code == 404
    assert client().get(endpoint, headers={"X-Neraium-User": "foreign@example.com"}).status_code == 404
