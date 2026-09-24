"""Baseline regression for the complete SII result, including compatibility."""
import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.engine.sii_engine import evaluate_sii
from app.governance.authority_store import RuntimeAuthorityDecisionStore
from app.services.analysis_result_contract import build_sii_evidence_projection
from test_sii_engine_v2 import _profiles, _stable_rows


ORIGINAL_DIGEST = "334b6bd43f0ea23f1e8100b075c29cc8c19f5b1852b71bb59591410e36020dc4"
PRE_RECURRENCE_DIGEST = "96867ed89a82e29ea47184ec5f3693d3297ccf3457bb1acf6adfe68f0b4700a5"
CURRENT_DIGEST = "58fa745062d6ac2a2c3e7918827a8ec16cc2eda5b25506d78c337f06cbf1a671"
CONTRACTS = json.loads((Path(__file__).parent / "fixtures/governance_compatibility_transitions.json").read_text())


def result_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def reverse_documented_transition(result, transition):
    """Validate exact captured values, then undo only enumerated contract paths.

    No recursive key-name exclusions: an unexpected field, even with a known
    name in a different location, remains covered by the historical digest.
    """
    restored = deepcopy(result)
    for change in CONTRACTS[transition]:
        for path in change["paths"]:
            parts = path.removeprefix("/").split("/")
            parent = restored
            for part in parts[:-1]:
                parent = parent[int(part)] if isinstance(parent, list) else parent[part]
            key = parts[-1]
            if change["kind"] == "removed":
                assert key not in parent, path
                parent[key] = deepcopy(change["old"])
            else:
                assert key in parent, path
                # Python equality equates False with 0 and 1 with 1.0, even
                # inside dictionaries. Preserve the exact JSON contract types.
                assert json.dumps(parent[key], sort_keys=True, allow_nan=False) == json.dumps(
                    change["new"], sort_keys=True, allow_nan=False
                ), path
                if change["kind"] == "added":
                    del parent[key]
                else:
                    assert change["kind"] == "value", path
                    parent[key] = deepcopy(change["old"])
    return restored


def assert_historical_contracts(stable):
    # Keep both historical authorities immutable when updating CURRENT_DIGEST.
    # Exact transition assertions plus restored historical hashes cover every
    # preexisting key/value, including all duplicate transports and processing.
    assert {change["kind"] for change in CONTRACTS["recurrence"]} == {"added"}
    previous = reverse_documented_transition(stable, "recurrence")
    assert result_digest(previous) == PRE_RECURRENCE_DIGEST
    original = reverse_documented_transition(previous, "continuous")
    assert result_digest(original) == ORIGINAL_DIGEST
    return previous, original


def stable_result(value):
    # These fields are measured execution diagnostics, duplicated in fusion.
    # Analytical results, findings, state, severity and compatibility stay intact.
    diagnostics = {"runtime_seconds", "total_runtime_seconds", "step_timings", "performance"}
    if isinstance(value, dict):
        if "runtime_metadata" in value:
            runtime = value["runtime_metadata"]
            # Invert only the declared producer relocation to exercise the
            # unchanged historical mathematical contract and its pinned hash.
            assert set(runtime) <= diagnostics | {"run_id", "job_id"}
            value = {**{k: v for k, v in value.items() if k != "runtime_metadata"}, **runtime}
        return {key: ("upload-fixture" if key == "run_id" and isinstance(item, str) and item.startswith("upload-")
                      else stable_result(item)) for key, item in value.items() if key not in diagnostics}
    if isinstance(value, list):
        return [stable_result(item) for item in value]
    return value


def test_unused_governance_preserves_base_sii_result_and_compatibility(monkeypatch):
    import app.governance.maturity as maturity_module

    def unexpected(*args, **kwargs):
        raise AssertionError("Live SII must not call governance")
    monkeypatch.setattr(maturity_module, "evaluate_maturity", unexpected)
    monkeypatch.setattr(RuntimeAuthorityDecisionStore, "append_decision", unexpected)
    columns, rows = _stable_rows()
    result = evaluate_sii(columns=columns, rows=rows, numeric_profiles=_profiles(columns),
                          timestamp_column="timestamp", config={"numeric_columns": columns[1:]})
    stable = stable_result(result)
    # Python 3.12 changed float summation. On 3.11 this one score is
    # 0.0147772473205815 instead of 0.014777247320581544 (also in its three
    # transport copies). Check that score within 1e-16, with no relative
    # tolerance, before canonicalizing ONLY those four values for the hash.
    # Every other analytical value and the original base digest stay exact.
    entropy_results = (
        stable["temporal_analysis"]["entropy_growth"],
        stable["compatibility"]["temporal_analysis"]["entropy_growth"],
        stable["evidence_fusion"]["evidence_inventory"][5]["evidence"]["entropy_growth"],
        stable["evidence_fusion"]["neutral_evidence"][3]["evidence"]["entropy_growth"],
    )
    for entropy in entropy_results:
        assert entropy["score"] == pytest.approx(0.014777247320581544, rel=0, abs=1e-16)
        entropy["score"] = 0.014777247320581544
    previous, original = assert_historical_contracts(stable)
    graph = stable["relationship_graph"]
    assert graph["changed_edges"] == previous["relationship_graph"]["changed_edges"] == []
    assert graph["recurring_edges"] == []
    assert stable["compatibility"] == previous["compatibility"]
    assert stable["persistence_analysis"] == previous["persistence_analysis"] == original["persistence_analysis"]
    assert stable["processing_trace"] == previous["processing_trace"] == original["processing_trace"]
    assert stable["findings"] == previous["findings"] == original["findings"]
    for edge, prior, legacy in zip(graph["edges"], previous["relationship_graph"]["edges"], original["relationship_graph"]["edges"], strict=True):
        assert edge["persistence_factor"] == 0.0
        assert edge["sample_sufficiency_factor"] == legacy["persistence_factor"] == 1.0
        assert edge["ranking_factors"]["sample_sufficiency"] == legacy["ranking_factors"]["persistence"]
        assert "persistence" not in edge["ranking_factors"]
        assert edge["temporal_persistence_status"] == "unconfirmed"
        assert edge["temporal_persistence_observations"] == 1
        assert edge["temporal_persistence_supporting_observations"] == 0
        assert edge["supporting_windows"] == []
        assert edge["persistent_relationship_change"] is False
        assert edge["temporal_persistence_supported"] is False
        assert edge["single_window_change_type"] == edge["change_type"] == "stable"
        for field in ("change_type", "column_classifications", "confidence", "edge_confidence",
                      "data_quality_factor", "eligible", "promoted_changed_edge", "source_column_metadata"):
            assert edge[field] == prior[field] == legacy[field], field
        assert edge["source_rows"] == prior["source_rows"]
        assert edge["time_window"] == prior["time_window"]
        assert edge["recurrence_evidence"]["supported"] is False
        assert edge["recurrence_evidence"]["episodes"] == []

    governed = build_sii_evidence_projection({"sii_result": stable})
    assert governed.pop("relationship_recurrences") == []
    assert governed == CONTRACTS["pre_recurrence_governed_evidence"]
    # No new causal/diagnostic/prescriptive text or fields can bypass the exact
    # transition allowlist and historical hashes. Recurrence payloads are neutral.
    for change in CONTRACTS["recurrence"]:
        payload = json.dumps(change["new"]).lower()
        assert all(word not in payload for word in ("cause", "diagnos", "prescri", "recommend"))

    # Only after structural and historical checks pass, pin the expanded result.
    # 2a25a331 introduced the continuous contract; 86b55790 added recurrence.
    # See docs/governance_compatibility_contract.md for capture provenance.
    assert result_digest(stable) == CURRENT_DIGEST

    # Prove that a current-digest refresh cannot mask changes to protected fields
    # or to the documented additions themselves. These mutations never run the
    # engine or modify its returned result.
    mutations = (
        ("/relationship_graph/edges/0/confidence", 0.1),
        ("/relationship_graph/edges/0/data_quality_factor", 0.1),
        ("/relationship_graph/edges/0/eligible", False),
        ("/relationship_graph/edges/0/change_type", "weakened"),
        ("/relationship_graph/edges/0/source_rows", []),
        ("/relationship_graph/edges/0/persistence_factor", 1.0),
        ("/relationship_graph/edges/0/recurrence_evidence", {}),
        ("/relationship_graph/edges/0/recurrence_evidence/supported", 0),
        ("/relationship_graph/changed_edges", [{"cause": "invented"}]),
        ("/compatibility/unexpected_diagnosis", "invented"),
        ("/processing_trace/unexpected_prescription", "invented"),
    )
    for path, value in mutations:
        mutated = deepcopy(stable)
        parts = path.removeprefix("/").split("/")
        parent = mutated
        for part in parts[:-1]:
            parent = parent[int(part)] if isinstance(parent, list) else parent[part]
        parent[parts[-1]] = value
        with pytest.raises(AssertionError):
            assert_historical_contracts(mutated)
