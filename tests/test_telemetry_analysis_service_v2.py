from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from app.core.config import Settings
from app.models.telemetry_api_models import _validate_safe_configuration
from app.services.telemetry_analysis_service import process_ingestion_run
from app.services.telemetry_analysis_service import TelemetryAnalysisServiceResult
from app.services.telemetry_analysis_service_v2 import _bindings, _evaluate, run_post_ingestion_analysis_v2
from app.services.telemetry_endpoint_execution_v2_repository import _record
from app.services.telemetry_analysis_window import AnalysisWindowValidationError
from app.services.telemetry_domain import ConnectorType
from app.services.telemetry_relationship_lineage_v2_repository import PostgreSQLEndpointLineageV2Repository
from test_relationship_lineage_v2 import _Connection
from test_telemetry_analysis_window_v2 import DIGEST, START, _binding, _observation, _scope, _window


def _authority_row(binding):
    mapping = binding.mapping
    signal = binding.signal
    return {
        "external_signal_id": signal.signal_id,
        "connection_id": signal.connection_id,
        "external_tag_id": signal.external_tag_id,
        "external_tag_name": signal.external_tag_name,
        "signal_enabled": signal.enabled,
        "mapping_enabled": mapping.enabled,
        "mapping_status": signal.mapping_status.value,
        "mapping_id": mapping.mapping_id,
        "revision": mapping.revision,
        "system_id": mapping.system_id,
        "asset_id": mapping.asset_id,
        "canonical_concept_id": mapping.canonical_signal_id,
        "canonical_signal_name": mapping.canonical_signal_name,
        "source_unit": mapping.source_unit,
        "canonical_unit": mapping.canonical_unit,
        "expected_dimension": mapping.expected_dimension,
        "conversion_id": mapping.conversion_id,
        "conversion_version": mapping.conversion_version,
        "source_timezone": mapping.source_timezone,
        "provenance": mapping.provenance,
        "mapped_by": mapping.actor_id,
        "mapped_at": mapping.mapped_at,
        "authority_digest": mapping.authority_digest,
    }


def test_server_selector_defaults_to_v1_and_rejects_unknown_version() -> None:
    settings = Settings(app_env="test", backend_host="127.0.0.1", backend_port=8010, cors_origins=[])
    assert settings.telemetry_execution_identity_version == "concept-keyed.v1"
    with pytest.raises(ValueError, match="execution_identity_version_invalid"):
        replace(settings, telemetry_execution_identity_version="unknown")
    with pytest.raises(ValueError, match="unsupported fields"):
        _validate_safe_configuration(
            ConnectorType.HISTORIAN_TEMPLATE,
            {"template_id": "t", "network_profile_id": "n", "execution_identity_version": "physical-endpoint-keyed.v2"},
        )


def test_endpoint_bindings_require_exact_server_mapping_authority() -> None:
    first, second, flow = _binding(1), _binding(2), _binding(3, "00000000-0000-0000-0000-000000000302")
    bindings = (first, second, flow)
    observations = tuple(_observation(binding, 0) for binding in bindings)
    rows = [_authority_row(binding) for binding in bindings]
    loaded = _bindings(_scope(), first.mapping.connection_id, observations, rows)
    assert loaded[0].identity.endpoint_id != loaded[1].identity.endpoint_id
    assert loaded[0].identity.canonical_concept_id == loaded[1].identity.canonical_concept_id
    for field, value in (
        ("revision", 4), ("authority_digest", "b" * 64),
        ("canonical_concept_id", flow.mapping.canonical_signal_id),
        ("system_id", "other"), ("asset_id", "other"),
        ("external_signal_id", "00000000-0000-0000-0000-000000000999"),
        ("connection_id", "00000000-0000-0000-0000-000000000999"),
        ("mapping_enabled", False),
    ):
        bad = [dict(row) for row in rows]
        bad[0][field] = value
        with pytest.raises((AnalysisWindowValidationError, ValueError)):
            window_bindings = _bindings(_scope(), first.mapping.connection_id, observations, bad)
            from app.services.telemetry_analysis_window_v2 import build_endpoint_analysis_window_v2
            from app.services.phase4_scope import ServerBoundSystemIdentityV2
            build_endpoint_analysis_window_v2(
                window_id="window", source_run_id="run-a", scope=_scope(),
                system_identity=ServerBoundSystemIdentityV2(
                    system_id="system-a", resource_scope_id=_scope().resource_scope_id,
                    authority_record_digest=DIGEST,
                ),
                asset_id="pump-1", bindings=window_bindings, observations=observations,
            )


def test_v2_engine_receives_endpoint_keys_and_separate_memory_namespace() -> None:
    window = _window()
    captured = {}

    def evaluator(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "compatibility": {"relationship_model": {"top_relationship_changes": []}}}

    _evaluate(window, evaluator=evaluator)
    assert set(captured["config"]["numeric_columns"]) == set(window.numeric_columns)
    assert all(key.startswith("physical-endpoint:") for key in captured["config"]["numeric_columns"])
    assert captured["canonical_endpoint_identity"] is None
    assert captured["relationship_persistence_state"] is None
    assert captured["config"]["infrastructure_identity"]["configured_model_id"].startswith("physical-endpoint-keyed.v2:")
    concepts = {item["canonical_signal_id"] for item in captured["telemetry_signal_catalog"].values()}
    assert len(concepts) == 2 and len(captured["telemetry_signal_catalog"]) == 3
    assert captured["operating_mode"]["match"] == "unavailable"
    assert "explicit endpoint selection" in captured["operating_mode"]["reasons"][0]
    with pytest.raises(AnalysisWindowValidationError, match="prior_memory_unsupported"):
        window.relationship_pair(window.numeric_columns[0], window.numeric_columns[1],
                                 prior_memory={"version": "relationship-temporal-state.v1"})
    from app.engine.sii.behavioral_model import resolve_infrastructure_identity
    v2_identity = resolve_infrastructure_identity(
        columns=captured["columns"], telemetry_signal_catalog=captured["telemetry_signal_catalog"],
        config=captured["config"], authenticated_scope=captured["phase4_scope"],
    )
    v1_config = {**captured["config"], "infrastructure_identity": {
        key: value for key, value in captured["config"]["infrastructure_identity"].items()
        if key != "configured_model_id"
    }}
    v1_identity = resolve_infrastructure_identity(
        columns=captured["columns"], telemetry_signal_catalog=captured["telemetry_signal_catalog"],
        config=v1_config, authenticated_scope=captured["phase4_scope"],
    )
    assert v2_identity["model_id"] != v1_identity["model_id"]


def test_same_concept_operating_context_ambiguity_is_order_independent() -> None:
    from test_telemetry_analysis_window_v2 import CONCEPT_FLOW

    observations = tuple(_observation(binding, minute) for minute in (0, 1)
                         for binding in (_binding(1), _binding(2), _binding(3, CONCEPT_FLOW)))
    windows = (
        _window((_binding(1), _binding(2), _binding(3, CONCEPT_FLOW)), observations),
        _window((_binding(3, CONCEPT_FLOW), _binding(2), _binding(1)), observations),
    )
    modes = []
    for window in windows:
        captured = {}
        def evaluator(**kwargs):
            captured.update(kwargs)
            return {"status": "completed"}
        _evaluate(window, evaluator=evaluator)
        modes.append(captured["operating_mode"])
    assert modes[0] == modes[1]
    assert modes[0]["match"] == "unavailable"


def test_v2_persists_and_reads_distinct_same_concept_pairs() -> None:
    from app.services.phase4_scope import ServerBoundSystemIdentityV2

    bindings = (_binding(1), _binding(2), _binding(3, "00000000-0000-0000-0000-000000000302"))
    observations = [_observation(binding, minute) for minute in (0, 1) for binding in bindings]

    class Repository:
        def resolve_analysis_authority_snapshot(self, scope, **kwargs):
            return ServerBoundSystemIdentityV2(
                system_id=kwargs["system_id"], resource_scope_id=scope.resource_scope_id,
                authority_record_digest=kwargs["authority_digest"],
            )

        def list_analysis_eligible_observations(self, scope, **kwargs):
            return observations

        def list_analysis_endpoint_authority(self, scope, **kwargs):
            return [_authority_row(binding) for binding in bindings]

    rows = {}
    lineage_repository = PostgreSQLEndpointLineageV2Repository(lambda: _Connection(rows))

    def evaluator(**kwargs):
        ids = list(kwargs["config"]["numeric_columns"])
        candidates = []
        evidence = {}
        for index, source_id in enumerate(ids[:2]):
            ref = f"ev-{index}"
            candidates.append({
                "relationship_source_evidence": {"columns": [source_id, ids[2]]},
                "relationship_evidence_ref": ref,
            })
            evidence[ref] = {"basis": "test-only", "source": source_id}
        return {
            "status": "completed",
            "compatibility": {"relationship_model": {"top_relationship_changes": candidates}},
            "relationship_evidence_registry": {"records": evidence},
        }

    class ExecutionRepository:
        def load_window_row(self, scope, *, window_id):
            return None

        def persist_execution(self, scope, *, window, result, pairs, lineage_repository):
            return _record(window, result, pairs)

        def read_execution(self, scope, *, window, pairs, lineage_repository):
            return self.persist_execution(scope, window=window, result=sii_result, pairs=pairs,
                                          lineage_repository=lineage_repository)

    sii_result = {}

    def capturing_evaluator(**kwargs):
        sii_result.update(evaluator(**kwargs))
        return sii_result

    result = run_post_ingestion_analysis_v2(
        repository=Repository(), lineage_repository=lineage_repository,
        execution_repository=ExecutionRepository(),
        scope=_scope(), connection_id=bindings[0].mapping.connection_id,
        source_run_id="run-a", system_id="system-a", asset_id="pump-1",
        window_start=START - timedelta(seconds=1), window_end=START + timedelta(minutes=2),
        persisted_authority_digest=DIGEST, evaluator=capturing_evaluator,
    )
    assert result.status == "completed"
    assert result.contract_version == "physical-endpoint-keyed.v2"
    assert len(rows) == 2
    endpoint_ids = {row["source_endpoint_id"] for row in rows.values()}
    assert len(endpoint_ids) == 2
    assert all(row["artifact_payload"]["payload"]["lineage"]["payload"]["source_endpoint"]["canonical_concept_id"] == bindings[0].mapping.canonical_signal_id for row in rows.values())


def test_explicit_server_selection_dispatches_to_v2_only_with_lineage_store(monkeypatch) -> None:
    from app.services import telemetry_analysis_service_v2

    binding = _binding(1)
    observation = _observation(binding, 0)

    class Repository:
        def list_analysis_eligible_observations(self, scope, **kwargs):
            return [observation]

    invoked = []

    def selected(**kwargs):
        invoked.append(kwargs)
        return TelemetryAnalysisServiceResult(window_id="v2-window", status="completed")

    monkeypatch.setattr(telemetry_analysis_service_v2, "run_post_ingestion_analysis_v2", selected)
    with pytest.raises(ValueError, match="v2_repositories_required"):
        process_ingestion_run(
            repository=Repository(), scope=_scope(), connection_id=binding.mapping.connection_id,
            source_run_id="run-a", execution_identity_version="physical-endpoint-keyed.v2",
        )
    store = object()
    response = process_ingestion_run(
        repository=Repository(), scope=_scope(), connection_id=binding.mapping.connection_id,
        source_run_id="run-a", execution_identity_version="physical-endpoint-keyed.v2",
        v2_lineage_repository=store, v2_execution_repository=store,
    )
    assert response.status == "completed"
    assert len(invoked) == 1 and invoked[0]["lineage_repository"] is store
    assert invoked[0]["execution_repository"] is store


def test_existing_engine_evaluates_distinct_endpoint_series_without_formula_change() -> None:
    from app.engine.sii.phase4 import phase4_persistence_suppressed
    from app.services.telemetry_analysis_service_v2 import _pairs

    bindings = (_binding(1), _binding(2), _binding(3, "00000000-0000-0000-0000-000000000302"))
    observations = tuple(_observation(binding, minute) for minute in range(30) for binding in bindings)
    window = _window(bindings, observations)
    with phase4_persistence_suppressed():
        result = _evaluate(window)
    assert result["status"] == "complete"
    pairs = _pairs(window, result)
    assert len(pairs) == 3
    assert any(
        pair.source.canonical_concept_id == pair.target.canonical_concept_id
        and pair.source.endpoint_id != pair.target.endpoint_id
        for pair, _, _ in pairs
    )


def test_single_endpoint_per_concept_keeps_correlation_numerics() -> None:
    from app.engine.sii.phase4 import phase4_persistence_suppressed
    from app.engine.sii_engine import evaluate_sii

    bindings = (_binding(1), _binding(3, "00000000-0000-0000-0000-000000000302"))
    window = _window(bindings, tuple(_observation(binding, minute) for minute in range(30) for binding in bindings))
    captured = {}

    def capture(**kwargs):
        captured.update(kwargs)
        return evaluate_sii(**kwargs)

    with phase4_persistence_suppressed():
        endpoint_result = _evaluate(window, evaluator=capture)
    column_map = {item.series_id: item.identity.canonical_concept_id for item in window.series}
    concept_kwargs = dict(captured)
    concept_kwargs["columns"] = [captured["columns"][0], *(column_map[key] for key in window.numeric_columns)]
    concept_kwargs["rows"] = [
        {captured["timestamp_column"]: row[captured["timestamp_column"]],
         **{column_map[key]: row[key] for key in window.numeric_columns}}
        for row in captured["rows"]
    ]
    concept_kwargs["numeric_profiles"] = [
        {**item, "column": column_map.get(item.get("column"), item.get("column"))}
        for item in captured["numeric_profiles"]
    ]
    concept_kwargs["telemetry_signal_catalog"] = {
        column_map[key]: {**value, "column": column_map[key]}
        for key, value in captured["telemetry_signal_catalog"].items()
    }
    concept_kwargs["config"] = {
        **captured["config"],
        "numeric_columns": list(column_map.values()),
    }
    with phase4_persistence_suppressed():
        concept_result = evaluate_sii(**concept_kwargs)
    def correlations(result):
        edges = result["compatibility"]["relationship_model"]["relationship_graph"]["edges"]
        return sorted((edge["baseline_correlation"], edge["recent_correlation"]) for edge in edges)
    assert correlations(endpoint_result) == correlations(concept_result)
