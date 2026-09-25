from __future__ import annotations

from copy import deepcopy
from app.services import relationship_temporal_state
from app.services import telemetry_analysis_window as analysis_window
from app.services.relationship_evidence_binding import REGISTRY
from app.engine.sii.behavioral_model_store import InMemoryBehavioralModelStore
from app.engine.sii.phase4 import evaluate_phase4

from test_telemetry_analysis_handoff import _window
from test_sii_phase4_orchestrator import _phase4_args


def _prior():
    return {"version": 1, "identity": {"basis": "global_relationship_model"}, "observations": [
        {"observed_at": "2026-08-25T00:00:00+00:00", "time_window": {}, "source_rows": [],
         "source_dataset_id": "dataset", "signed_correlation_delta": 0.2,
         "edge_confidence": 0.8, "data_quality_factor": 0.9, "eligible": True, "acceptable": True}
    ]}


def _current(at="2026-08-26T00:00:00+00:00", delta=0.2):
    return {"observed_at": at, "time_window": {"current_end": at}, "source_rows": [],
            "source_dataset_id": "dataset", "signed_correlation_delta": delta,
            "edge_confidence": 0.8, "data_quality_factor": 0.9, "eligible": True, "acceptable": True}


def _candidate_result(item):
    candidate = {"relationship_evidence_ref": "evidence", "relationship_lineage_ref": "lineage",
                 "relationship_source_evidence": {"columns": ["canonical-a", "canonical-b"]}}
    record = {"temporal": {"observations": [item]}}
    return {"status": "limited", "processing_trace": {},
            "compatibility": {"relationship_model": {"top_relationship_changes": [candidate]}},
            REGISTRY: {"records": {"evidence": record}, "relationship_lineage": {"evidence": {"ref": "lineage"}}}}


def test_validated_prior_is_passed_to_existing_reducer(monkeypatch):
    prior, calls = _prior(), []
    monkeypatch.setattr(relationship_temporal_state, "load_prior_relationship_state",
                        lambda *a, **k: deepcopy(prior))
    monkeypatch.setattr(analysis_window, "evaluate_sii", lambda **kwargs: calls.append(kwargs) or _candidate_result(_current()))
    analysis_window.run_analysis_window(_window(), temporal_state_repository=object())
    assert len(calls) == 2
    assert calls[1]["relationship_persistence_state"] == {
        '["canonical-a","canonical-b"]': prior
    }
    assert "relationship_persistence_state" not in calls[0]
    # Continuation changes only the reducer-state argument; the current run's
    # owned rows, canonical identity, and all other evaluator inputs stay fixed.
    assert {key: value for key, value in calls[1].items()
            if key != "relationship_persistence_state"} == calls[0]


def test_no_prior_and_incompatible_event_keep_one_run_behavior(monkeypatch):
    calls = []
    monkeypatch.setattr(relationship_temporal_state, "load_prior_relationship_state", lambda *a, **k: None)
    monkeypatch.setattr(analysis_window, "evaluate_sii", lambda **kwargs: calls.append(kwargs) or _candidate_result(_current()))
    analysis_window.run_analysis_window(_window(), temporal_state_repository=object())
    assert len(calls) == 2
    assert "relationship_persistence_state" not in calls[1]
    assert calls[1] == calls[0]
    calls.clear()
    prior = _prior()
    monkeypatch.setattr(relationship_temporal_state, "load_prior_relationship_state", lambda *a, **k: prior)
    monkeypatch.setattr(analysis_window, "evaluate_sii", lambda **kwargs: calls.append(kwargs) or _candidate_result(
        _current("2026-08-24T00:00:00+00:00")))
    analysis_window.run_analysis_window(_window(), temporal_state_repository=object())
    assert len(calls) == 2
    assert "relationship_persistence_state" not in calls[1]


def test_exact_replay_is_allowed_only_as_reducer_idempotent_replay(monkeypatch):
    prior = _prior()
    replay = deepcopy(prior["observations"][-1])
    calls = []
    monkeypatch.setattr(relationship_temporal_state, "load_prior_relationship_state", lambda *a, **k: prior)
    monkeypatch.setattr(analysis_window, "evaluate_sii", lambda **kwargs: calls.append(kwargs) or _candidate_result(replay))
    analysis_window.run_analysis_window(_window(), temporal_state_repository=object())
    assert len(calls) == 2
    assert calls[1]["relationship_persistence_state"][ '["canonical-a","canonical-b"]' ] == prior


def test_conflicting_replay_does_not_reach_reducer(monkeypatch):
    prior = _prior()
    conflict = _current("2026-08-25T00:00:00+00:00", delta=-0.7)
    calls = []
    monkeypatch.setattr(relationship_temporal_state, "load_prior_relationship_state", lambda *a, **k: prior)
    monkeypatch.setattr(analysis_window, "evaluate_sii", lambda **kwargs: calls.append(kwargs) or _candidate_result(conflict))
    analysis_window.run_analysis_window(_window(), temporal_state_repository=object())
    assert len(calls) == 2
    assert "relationship_persistence_state" not in calls[1]


def test_prior_read_failure_keeps_successful_current_run(monkeypatch):
    calls = []
    def reject(*_args, **_kwargs):
        raise RuntimeError("unavailable")
    monkeypatch.setattr(relationship_temporal_state, "load_prior_relationship_state", reject)
    current = _candidate_result(_current())
    monkeypatch.setattr(analysis_window, "evaluate_sii", lambda **kwargs: calls.append(kwargs) or current)
    execution = analysis_window.run_analysis_window(_window(), temporal_state_repository=object())
    assert len(calls) == 2
    assert "relationship_persistence_state" not in calls[1]
    assert calls[1] == calls[0]
    assert dict(execution.sii_result) == current


def test_discovery_phase4_is_read_only_and_authoritative_phase4_writes_once(monkeypatch):
    prior, calls, phase4_results = _prior(), [], []
    store = InMemoryBehavioralModelStore()
    monkeypatch.setattr(relationship_temporal_state, "load_prior_relationship_state",
                        lambda *a, **k: deepcopy(prior))

    def evaluator(**kwargs):
        calls.append(kwargs)
        result = evaluate_phase4(**_phase4_args(store, run_id="continuation-run"))
        phase4_results.append(result)
        return _candidate_result(_current())

    monkeypatch.setattr(analysis_window, "evaluate_sii", evaluator)
    analysis_window.run_analysis_window(_window(), temporal_state_repository=object())

    assert len(calls) == 2
    assert "relationship_persistence_state" not in calls[0]
    assert calls[1]["relationship_persistence_state"] == {
        '["canonical-a","canonical-b"]': prior
    }
    assert {key: value for key, value in calls[1].items()
            if key != "relationship_persistence_state"} == calls[0]
    # Exercise the real Phase 4 persistence path: discovery has no writes and
    # the authoritative pass creates exactly one version and snapshot.
    assert phase4_results[0]["processing_trace"]["storage_writes"] == []
    assert phase4_results[1]["processing_trace"]["storage_writes"]
    scope = _phase4_args(store, run_id="unused")["phase4_scope"]
    model_id = phase4_results[1]["behavioral_model"]["model_id"]
    assert store.load_model(scope, model_id)["model_version"] == "v1"
    assert len(store.list_snapshots(scope, model_id)) == 1


def test_injected_evaluator_remains_one_run_even_if_repository_is_available():
    calls = []
    evaluator = lambda **kwargs: calls.append(kwargs) or {"status": "limited", "compatibility": {}, "processing_trace": {}}
    analysis_window.run_analysis_window(_window(), evaluator=evaluator, temporal_state_repository=object())
    assert len(calls) == 1
