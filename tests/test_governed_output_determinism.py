"""Contract regressions use synthetic telemetry only; no external fault labels."""
from copy import deepcopy
from datetime import datetime, timedelta
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.engine.sii_engine import evaluate_sii
from app.services.analysis_result_contract import build_analysis_result
from app.services.condition_corroboration import ConditionCorroborationService
from app.services.output_semantics import canonical_json, semantic_content, semantic_digest
from test_sii_supplied_reference import contract
from test_condition_intelligence import relationship, historical_rows


def sequence(reverse=False):
    """Six chronological windows, carrying only engine-owned incoming state."""
    state = recurrence = None
    outputs = []
    for index in range(6):
        args = contract(32)
        for row in args["comparison_rows"]:
            row["timestamp"] = (datetime.fromisoformat(row["timestamp"]) + timedelta(days=index)).isoformat()
        if reverse:
            for key in ("comparison_rows", "reference_rows"):
                args[key] = [dict(reversed(list(row.items()))) for row in args[key]]
        result = evaluate_sii(**args, relationship_persistence_state=deepcopy(state),
                              relationship_recurrence_state=deepcopy(recurrence))
        graph = result["relationship_graph"]
        state = deepcopy(graph["relationship_persistence_state"])
        recurrence = deepcopy(graph["relationship_recurrence_state"])
        outputs.append({
            "semantic": semantic_digest(result["analysis_result"]),
            "graph": semantic_digest(graph),
            "state": semantic_digest([state, recurrence]),
            "full": semantic_digest(result),
        })
    return outputs


def test_fresh_process_sequences_match(tmp_path):
    expected = None
    for seed in range(6):
        env = {**os.environ, "PYTHONHASHSEED": str(seed),
               "PYTHONPATH": os.pathsep.join(["backend", "tests"]),
               "NERAIUM_RUNTIME_DIR": str(tmp_path / str(seed)),
               "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
        script = ("import json; from test_governed_output_determinism import sequence; "
                  f"print(json.dumps(sequence(reverse={bool(seed % 2)})))")
        completed = subprocess.run([sys.executable, "-c", script], env=env, text=True,
                                   capture_output=True, check=True)
        actual = json.loads(completed.stdout)
        if expected is None:
            expected = actual
        assert actual == expected, f"fresh process seed {seed}"


def test_canonical_serialization_preserves_semantic_order():
    assert canonical_json({"b": {"z", "a"}, "a": 1}) == canonical_json({"a": 1, "b": {"a", "z"}})
    assert semantic_digest(["a", "z"]) != semantic_digest(["z", "a"])
    with pytest.raises(TypeError):
        canonical_json(object())
    with pytest.raises(ValueError):
        canonical_json(float("nan"))
    # Actual source times are never stripped.
    assert semantic_digest({"source_timestamp": "2018"}) != semantic_digest({"source_timestamp": "2026"})


def test_condition_supplied_ties_and_runtime_times():
    relationships = [relationship("r1", "a", "b"), relationship("r2", "b", "c"),
                     relationship("r3", "c", "a")]
    expected = None
    for index, permutation in enumerate(itertools.permutations(relationships)):
        result = ConditionCorroborationService().build_conditions(
            relationships=list(permutation), findings=[], rows=historical_rows(),
            timestamp_column="timestamp", data_quality={}, operating_mode={},
            site_name="", generated_at=f"2030-01-0{index + 1}T00:00:00Z")
        assert result[0]["title_evidence_relationship_id"] == permutation[0]["id"]
        for condition in result:
            for event in condition["timeline"]:
                assert event.get("event_type") != "condition_generated"
                assert not str(event.get("time", "")).startswith("2030")
            event = condition["runtime_metadata"]["events"][0]
            assert event["precision"] == "runtime_timestamp"
            assert event["time_basis"] == "execution_clock"
            assert condition["coherence"]["shared_signals"] == sorted(condition["coherence"]["shared_signals"])


def test_runtime_metadata_cannot_change_semantics():
    result = evaluate_sii(**contract(32))
    altered = deepcopy(result)
    def change(value):
        if isinstance(value, dict):
            if "runtime_metadata" in value:
                value["runtime_metadata"].update({"run_id": "different", "generated_at": "2099", "step_timings": {"a": 99}})
            if "output_semantics" in value:
                for key in value.get("runtime_metadata", {}).get("legacy_root_aliases", ["generated_at"]):
                    if key in value:
                        value[key] = "another execution"
            for key, child in value.items():
                if key != "runtime_metadata":
                    change(child)
        elif isinstance(value, list):
            for child in value:
                change(child)
    change(altered)
    assert semantic_digest(altered) == semantic_digest(result)
    assert semantic_digest(altered["relationship_graph"]) == semantic_digest(result["relationship_graph"])
    assert semantic_digest(altered["analysis_result"]) == semantic_digest(result["analysis_result"])


def test_runtime_ids_do_not_create_evidence_identity():
    source = {"status": "complete", "upload_id": "source-file",
              "relationship_model": {"top_relationship_changes": [relationship("r1", "a", "b")]}}
    a = build_analysis_result({**source, "run_id": "runtime-a", "completed_at": "2030-01-01T00:00:00Z"})
    b = build_analysis_result({**source, "run_id": "runtime-b", "completed_at": "2040-01-01T00:00:00Z"})
    assert semantic_content(a) == semantic_content(b)
    assert a["runtime_metadata"]["run_id"] != b["runtime_metadata"]["run_id"]


def test_insufficient_evidence_and_consequence_abstention():
    result = build_analysis_result({"status": "complete", "data_quality": {"readiness": "not_ready"}})
    serialized = canonical_json(semantic_content(result))
    assert not result["relationships"]
    assert not result["insights"]
    from test_measurable_consequence import fixture, run
    finding, expected, catalog = fixture()
    finding["persistence"] = {"status": "not_established"}
    consequence = run(finding, expected, catalog)
    assert consequence["status"] == "not_quantifiable"
    assert "cumulative_amount" not in consequence
    limited = build_analysis_result({"status": "complete",
        "data_quality": {"data_confidence": {"rating": "low"}},
        "relationship_model": {"top_relationship_changes": [relationship("r1", "a", "b")]}})
    assert limited["conditions"][0]["classification"]["type"] == "insufficient_evidence"
    assert limited["conditions"][0]["measurable_consequence"]["status"] == "not_quantifiable"


def test_phase4_source_identity_ignores_execution_identity():
    from app.engine.sii.phase4 import _source_run_id
    columns, rows = ["flow"], [{"flow": 1}]
    assert _source_run_id(columns, rows, {"run_id": "a", "job_id": "a"}) == _source_run_id(
        columns, rows, {"run_id": "b", "job_id": "b"})
    assert _source_run_id(columns, rows, {"source_run_id": "source"}) == "source"


def test_legacy_result_hash_is_preserved():
    from app.services.analysis_provenance import result_digest, canonical_digest
    legacy = {"analysis_result": {"generated_at": "2030", "evidence": [1, 2]}}
    assert result_digest(legacy) == canonical_digest({"analysis_result": {"evidence": [1, 2]}})
