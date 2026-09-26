"""End-to-end Phase F persistence through certified producers and PostgreSQL."""
from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
import json
import os
from uuid import uuid4

import pytest

from app.services.relationship_evidence_binding import REGISTRY, TEMPORAL, finalize
from app.services.relationship_temporal_state import (
    _valid_state, compatibility_digest, load_prior_relationship_state,
    persist_authoritative_relationship_state,
)
from app.services.telemetry_analysis_window import build_canonical_analysis_window, run_analysis_window
from app.services.telemetry_domain import TelemetryScopeRef
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_repository import PostgreSQLTelemetryRepository, RelationshipTemporalStateConflict
from test_telemetry_analysis_handoff import DIGEST, _identity, _observation, _scope


DSN = os.environ.get("NERAIUM_TEST_POSTGRES_DSN", "").strip()
pytestmark = pytest.mark.skipif(not DSN, reason="NERAIUM_TEST_POSTGRES_DSN is not configured")
SIGNALS = ("9fa5d454-6b13-5f59-99d1-7f6fb0a3e07f", "4385267d-f840-59c4-ba65-06a6726e3189")


def _window(window_id: str, rows: int, *, changed_last: bool = False):
    scope = _scope()
    start = datetime(2026, 8, 25, tzinfo=UTC)
    observations = []
    for index in range(rows):
        for endpoint, signal in enumerate(SIGNALS):
            value = 80.0 + index if endpoint == 0 else (
                40.0 + index * 0.5 if index < 28 else 30.0 + (index * 17) % 11
            )
            if changed_last and index == rows - 1 and endpoint == 1:
                value += 13.0
            observations.append({
                **_observation(index * 2 + endpoint, signal, start + timedelta(minutes=index), value),
                "canonical_signal_name": f"pressure_{endpoint}",
            })
    return build_canonical_analysis_window(
        window_id=window_id, source_run_id="run-a", scope=scope,
        system_id="system-a", asset_id="asset-a", persisted_authority_digest=DIGEST,
        phase4_system_identity=_identity(scope), observations=observations,
    )


def _apply_phase_c_migrations(connection):
    from db.migrations.create_telemetry_connection_tables import apply as foundation
    from db.migrations.seed_telemetry_canonical_signal_concepts import apply as catalog
    from db.migrations.extend_telemetry_ingestion_runtime import apply as ingestion
    from db.migrations.persist_canonical_analysis_results import apply as results
    from db.migrations.preserve_telemetry_source_representation import apply as source
    from db.migrations.create_relationship_temporal_state import apply as temporal

    for migration in (foundation, catalog, ingestion, results, source, temporal):
        migration(connection)


@pytest.fixture
def postgres_repository():
    psycopg = pytest.importorskip("psycopg")
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    database = f"phasef_{uuid4().hex}"
    with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    test_dsn = make_conninfo(DSN, dbname=database)
    try:
        with psycopg.connect(test_dsn) as connection:
            _apply_phase_c_migrations(connection)
        yield PostgreSQLTelemetryRepository(lambda: psycopg.connect(test_dsn))
    finally:
        with psycopg.connect(DSN, autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(database)))


def _read(repository, scope, *, system="system-a", asset="asset-a", lineage):
    return repository.read_relationship_temporal_state(
        scope, system_id=system, asset_id=asset, lineage_ref=lineage,
    )


def _assert_unchanged(repository, scope, lineage, before):
    after = _read(repository, scope, lineage=lineage)
    assert after["storage_revision"] == before["storage_revision"]
    assert after["head_event_ref"] == before["head_event_ref"]
    assert after["head_event_time"] == before["head_event_time"]
    assert after["reducer_state"] == before["reducer_state"]


def test_phase_f_real_authoritative_projection_cas_replay_and_rejections(postgres_repository, monkeypatch):
    repository = postgres_repository
    authenticated_scope = _scope()
    scope = TelemetryScopeRef(
        authenticated_scope.tenant_scope_id, authenticated_scope.workspace_id,
        authenticated_scope.resource_scope_id, authenticated_scope.workspace_id,
    )

    # Actual evaluate_sii discovery/finalization and authoritative continuation;
    # no mocked evidence, lineage, reducer result, or persistence projection.
    from app.services import telemetry_analysis_window
    evaluate = telemetry_analysis_window.evaluate_sii
    first_calls = []
    def first_spy(**kwargs):
        first_calls.append(kwargs)
        return evaluate(**kwargs)
    monkeypatch.setattr(telemetry_analysis_window, "evaluate_sii", first_spy)
    first = run_analysis_window(_window("phasef-first", 40), temporal_state_repository=repository)
    monkeypatch.setattr(telemetry_analysis_window, "evaluate_sii", evaluate)
    assert len(first_calls) == 2
    assert "relationship_persistence_state" not in first_calls[0]
    assert "relationship_persistence_state" not in first_calls[1]
    first_candidate = first.sii_result["compatibility"]["relationship_model"]["top_relationship_changes"][0]
    first_registry = first.sii_result[REGISTRY]
    lineage = first_candidate["relationship_lineage_ref"]
    record = first_registry["records"][first_candidate["relationship_evidence_ref"]]
    assert first_candidate["relationship_source_ref"] == record["source"]["source_id"]
    assert first_registry["relationship_lineage"][first_candidate["relationship_evidence_ref"]]["ref"] == lineage
    first_state = _read(repository, scope, lineage=lineage)
    assert first_state["storage_revision"] == 1
    assert first_state["head_event_time"].isoformat() == record["temporal"]["observations"][-1]["observed_at"]
    assert len(first_state["reducer_state"]["observations"]) == 1

    next_window = _window("phasef-next", 41)
    probe = run_analysis_window(next_window)
    probe_candidate = probe.sii_result["compatibility"]["relationship_model"]["top_relationship_changes"][0]
    probe_registry = probe.sii_result[REGISTRY]
    probe_record = probe_registry["records"][probe_candidate["relationship_evidence_ref"]]
    probe_descriptor = probe_registry["relationship_lineage"][probe_candidate["relationship_evidence_ref"]]
    assert probe_candidate["relationship_lineage_ref"] == lineage
    assert first_state["compatibility_digest"] == compatibility_digest(probe_record, probe_descriptor)
    assert _valid_state(first_state, first_state["compatibility_digest"],
        probe_record["temporal"]["identity"], scope,
        "system-a", "asset-a", lineage)
    probe_prior = load_prior_relationship_state(
        repository, next_window.phase4_scope, system_id="system-a", asset_id="asset-a",
        candidate=probe_candidate, registry=probe_registry,
        authorized_scope=probe_registry["scope"],
    )
    assert probe_prior is not None
    next_calls = []
    def next_spy(**kwargs):
        next_calls.append(kwargs)
        return evaluate(**kwargs)
    monkeypatch.setattr(telemetry_analysis_window, "evaluate_sii", next_spy)
    continued = run_analysis_window(next_window, temporal_state_repository=repository)
    monkeypatch.setattr(telemetry_analysis_window, "evaluate_sii", evaluate)
    assert len(next_calls) == 2
    assert "relationship_persistence_state" not in next_calls[0]
    assert "relationship_persistence_state" in next_calls[1]
    continued_candidate = continued.sii_result["compatibility"]["relationship_model"]["top_relationship_changes"][0]
    assert continued_candidate["relationship_lineage_ref"] == lineage
    continued_state = _read(repository, scope, lineage=lineage)
    assert continued_state["storage_revision"] == 2
    assert len(continued_state["reducer_state"]["observations"]) == 2
    assert continued_state["head_event_time"] > first_state["head_event_time"]

    # Exact evidence replay leaves both storage revision and reducer votes intact.
    replay = run_analysis_window(_window("phasef-replay", 41), temporal_state_repository=repository)
    replay_state = _read(repository, scope, lineage=lineage)
    assert replay_state["storage_revision"] == 2
    assert replay_state["reducer_state"] == continued_state["reducer_state"]
    assert replay.sii_result["relationship_graph"]["relationship_persistence_state"] == \
        continued.sii_result["relationship_graph"]["relationship_persistence_state"]

    with pytest.raises(RelationshipTemporalStateConflict, match="conflicting_replay"):
        repository.compare_and_swap_relationship_temporal_state(
            scope, system_id="system-a", asset_id="asset-a", lineage_ref=lineage,
            compatibility_digest=continued_state["compatibility_digest"],
            reducer_state={"version": 1, "identity": continued_state["reducer_state"]["identity"],
                           "observations": [{**continued_state["reducer_state"]["observations"][-1],
                                             "signed_correlation_delta": 0.123}]},
            head_event_ref=continued_state["head_event_ref"],
            head_event_time=continued_state["head_event_time"], expected_revision=2,
            expected_head_event_ref=continued_state["head_event_ref"],
        )
    with pytest.raises(RelationshipTemporalStateConflict, match="unbounded"):
        repository.compare_and_swap_relationship_temporal_state(
            scope, system_id="system-a", asset_id="asset-a", lineage_ref=lineage,
            compatibility_digest=continued_state["compatibility_digest"],
            reducer_state={"version": 1, "identity": continued_state["reducer_state"]["identity"],
                           "observations": [{}] * 9},
            head_event_ref="phasef-unbounded-event",
            head_event_time=continued_state["head_event_time"] + timedelta(days=1),
            expected_revision=2, expected_head_event_ref=continued_state["head_event_ref"],
        )
    _assert_unchanged(repository, scope, lineage, continued_state)

    # Same interval with different producer-owned source evidence is rejected.
    conflicted = run_analysis_window(
        _window("phasef-conflict", 41, changed_last=True), temporal_state_repository=repository,
    )
    assert conflicted.sii_result["status"] != "failed"
    _assert_unchanged(repository, scope, lineage, continued_state)

    # Older evidence cannot replace the later current head.
    out_of_order = run_analysis_window(_window("phasef-old", 40), temporal_state_repository=repository)
    assert out_of_order.sii_result["status"] != "failed"
    _assert_unchanged(repository, scope, lineage, continued_state)

    # Actual repository predicates keep scope, system, asset and lineage independent.
    assert _read(repository, TelemetryScopeRef("tenant-other", "workspace-other",
        canonical_phase4_resource_scope_id("tenant-other", "workspace-other"), "workspace-other"),
        lineage=lineage) is None
    assert _read(repository, scope, system="system-other", lineage=lineage) is None
    assert _read(repository, scope, asset="asset-other", lineage=lineage) is None
    assert _read(repository, scope, lineage="relationship-lineage.v1:other") is None

    # Stale CAS and out-of-order direct attempts fail without changing the real head.
    with pytest.raises(RelationshipTemporalStateConflict, match="stale_head"):
        repository.compare_and_swap_relationship_temporal_state(
            scope, system_id="system-a", asset_id="asset-a", lineage_ref=lineage,
            compatibility_digest=continued_state["compatibility_digest"],
            reducer_state=continued_state["reducer_state"], head_event_ref="phasef-stale-event",
            head_event_time=continued_state["head_event_time"] + timedelta(days=1),
            expected_revision=1, expected_head_event_ref=continued_state["head_event_ref"],
        )
    with pytest.raises(RelationshipTemporalStateConflict, match="out_of_order"):
        repository.compare_and_swap_relationship_temporal_state(
            scope, system_id="system-a", asset_id="asset-a", lineage_ref=lineage,
            compatibility_digest=continued_state["compatibility_digest"],
            reducer_state=continued_state["reducer_state"], head_event_ref="phasef-old-event",
            head_event_time=first_state["head_event_time"], expected_revision=2,
            expected_head_event_ref=continued_state["head_event_ref"],
        )
    _assert_unchanged(repository, scope, lineage, continued_state)

    # Tampering with finalized authority or compatibility cannot reach the writer.
    for mutation in ("registry_missing", "lineage_tampered", "record_tampered", "fallback", "incompatible"):
        forged = deepcopy(dict(continued.sii_result))
        candidate = forged["compatibility"]["relationship_model"]["top_relationship_changes"][0]
        registry = forged[REGISTRY]
        evidence_ref = candidate["relationship_evidence_ref"]
        if mutation == "registry_missing":
            forged.pop(REGISTRY)
        elif mutation == "lineage_tampered":
            candidate["relationship_lineage_ref"] = "relationship-lineage.v1:forged"
        elif mutation == "record_tampered":
            registry["records"][evidence_ref]["source"]["source_id"] = "forged-source"
        elif mutation == "fallback":
            registry["records"][evidence_ref]["basis"] = "global_relationship_model_failure_fallback"
        else:
            registry["relationship_lineage"][evidence_ref]["payload"]["semantic_version"] = "pearson-global.v999"
        persist_authoritative_relationship_state(
            repository, scope, system_id="system-a", asset_id="asset-a", result=forged,
            authorized_scope=continued_registry_scope(continued.sii_result),
        )
        _assert_unchanged(repository, scope, lineage, continued_state)

    # Re-finalize a valid result with a changed compatibility reference but the
    # same producer lineage/source identity. It must not reset or replace head.
    incompatible_graph = deepcopy(continued.sii_result["relationship_graph"])
    incompatible_model = deepcopy(continued.sii_result["compatibility"]["relationship_model"])
    for edge in incompatible_graph.get("edges", []):
        edge["reference_dataset_id"] = "different-reference"
        state_key = json.dumps(sorted(edge["columns"]), separators=(",", ":"))
        state = incompatible_graph["relationship_persistence_state"][state_key]
        state["identity"]["reference_dataset_id"] = "different-reference"
    for candidate in incompatible_model.get("top_relationship_changes", []):
        candidate["reference_dataset_id"] = "different-reference"
    incompatible_registry = finalize(
        incompatible_model, incompatible_graph,
        scope=continued_registry_scope(continued.sii_result),
        endpoint_identity=continued.sii_result["relationship_endpoint_identity"],
        phase4_system_identity=next_window.phase4_system_identity,
        asset_id=next_window.asset_id, authenticated_scope=next_window.phase4_scope,
        observation_lineage=next_window.observation_lineage,
    )
    incompatible_result = deepcopy(dict(continued.sii_result))
    incompatible_result["relationship_graph"] = incompatible_graph
    incompatible_result[REGISTRY] = incompatible_registry
    incompatible_result["compatibility"]["relationship_model"] = incompatible_model
    incompatible_candidate = incompatible_model["top_relationship_changes"][0]
    assert incompatible_candidate["relationship_lineage_ref"] == lineage
    persist_authoritative_relationship_state(
        repository, scope, system_id="system-a", asset_id="asset-a", result=incompatible_result,
        authorized_scope=continued_registry_scope(continued.sii_result),
    )
    _assert_unchanged(repository, scope, lineage, continued_state)

    # A separately finalized, producer-issued graph-failure fallback has no
    # temporal authority and cannot borrow the successful lineage head.
    fallback_graph = deepcopy(continued.sii_result["relationship_graph"])
    fallback_graph["edge_basis"] = "global_relationship_model_failure_fallback"
    fallback_graph.pop("relationship_persistence_state", None)
    for edge in fallback_graph.get("edges", []):
        for field in TEMPORAL:
            edge.pop(field, None)
    fallback_model = deepcopy(continued.sii_result["compatibility"]["relationship_model"])
    for candidate in fallback_model.get("top_relationship_changes", []):
        for field in TEMPORAL:
            candidate.pop(field, None)
    fallback_registry = finalize(
        fallback_model, fallback_graph, scope=continued_registry_scope(continued.sii_result),
        endpoint_identity=continued.sii_result["relationship_endpoint_identity"],
        phase4_system_identity=next_window.phase4_system_identity,
        asset_id=next_window.asset_id, authenticated_scope=next_window.phase4_scope,
        observation_lineage=next_window.observation_lineage,
    )
    fallback_result = deepcopy(dict(continued.sii_result))
    fallback_result["relationship_graph"] = fallback_graph
    fallback_result[REGISTRY] = fallback_registry
    fallback_result["compatibility"]["relationship_model"] = fallback_model
    persist_authoritative_relationship_state(
        repository, scope, system_id="system-a", asset_id="asset-a", result=fallback_result,
        authorized_scope=continued_registry_scope(continued.sii_result),
    )
    _assert_unchanged(repository, scope, lineage, continued_state)

    # A candidate cannot borrow evidence or lineage from another result-local registry.
    borrowed = deepcopy(dict(continued.sii_result))
    borrowed[REGISTRY] = first_registry
    persist_authoritative_relationship_state(
        repository, scope, system_id="system-a", asset_id="asset-a", result=borrowed,
        authorized_scope=continued_registry_scope(continued.sii_result),
    )
    _assert_unchanged(repository, scope, lineage, continued_state)

    # Presentation/ranking/runtime labels do not choose the storage identity.
    decorated = deepcopy(dict(continued.sii_result))
    decorated_candidate = decorated["compatibility"]["relationship_model"]["top_relationship_changes"][0]
    decorated_candidate.update({"rank": 999, "primary": True, "group": "other",
                                "persistent_columns": ["forged"], "runtime_id": "retry"})
    before_revision = continued_state["storage_revision"]
    persist_authoritative_relationship_state(
        repository, scope, system_id="system-a", asset_id="asset-a", result=decorated,
        authorized_scope=continued_registry_scope(continued.sii_result),
    )
    assert _read(repository, scope, lineage=lineage)["storage_revision"] == before_revision

    # A failed authoritative second evaluation cannot advance temporal state.
    calls = 0
    def fail_authoritative(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("authoritative evaluator failure")
        return evaluate(**kwargs)
    from app.services.telemetry_analysis_window import AnalysisWindowExecutionError
    monkeypatch.setattr(telemetry_analysis_window, "evaluate_sii", fail_authoritative)
    with pytest.raises(AnalysisWindowExecutionError):
        run_analysis_window(_window("phasef-failed-authoritative", 42), temporal_state_repository=repository)
    monkeypatch.setattr(telemetry_analysis_window, "evaluate_sii", evaluate)
    _assert_unchanged(repository, scope, lineage, continued_state)

    # A real completed analysis survives a failed persistence call unchanged.
    class FailingWriteRepository:
        def read_relationship_temporal_state(self, target_scope, **kwargs):
            return repository.read_relationship_temporal_state(target_scope, **kwargs)
        def compare_and_swap_relationship_temporal_state(self, *_args, **_kwargs):
            raise RuntimeError("simulated persistence outage")

    persistence_failed = run_analysis_window(next_window, temporal_state_repository=FailingWriteRepository())
    assert persistence_failed.sii_result["status"] == replay.sii_result["status"]
    failed_graph = deepcopy(persistence_failed.sii_result["relationship_graph"])
    replay_graph = deepcopy(replay.sii_result["relationship_graph"])
    failed_graph.pop("runtime_metadata", None)
    replay_graph.pop("runtime_metadata", None)
    assert failed_graph == replay_graph
    _assert_unchanged(repository, scope, lineage, continued_state)


def continued_registry_scope(result):
    return result[REGISTRY]["scope"]
