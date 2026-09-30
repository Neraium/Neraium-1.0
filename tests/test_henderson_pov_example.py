"""Only the checked-in NON-HENDERSON example; no historical or labelled datasets."""
from copy import deepcopy
import csv
from datetime import datetime
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess

import pytest

from app.engine.relationship_qualification import digest
from app.services.historical_pov import PoVAdmissionError, prepare_historical_pov, run_historical_pov


PACKAGE = Path(__file__).resolve().parents[1] / "examples" / "henderson-pov"


def example():
    return ((PACKAGE / "telemetry-example.csv").read_bytes(),
            json.loads((PACKAGE / "acquisition-example.json").read_text()))


def test_synthetic_csv_is_not_ignored_for_handoff():
    checked = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", "examples/henderson-pov/telemetry-example.csv"],
        cwd=PACKAGE.parents[1], capture_output=True, text=True,
    )
    assert checked.returncode == 1, checked.stderr or "Synthetic CSV is ignored"


def test_synthetic_package_chronology_blindness_provenance_and_frozen_result(monkeypatch):
    from app.engine import sii_engine

    raw, metadata = example()
    original_metadata = deepcopy(metadata)
    source_rows = list(csv.DictReader(io.StringIO(raw.decode(), newline="")))
    assert len(source_rows) == 112
    assert all(set(row) == {"timestamp", "s01", "s02"} for row in source_rows)
    assert set(metadata["signals"]) == {"s01", "s02"}
    assert metadata["acquisition"]["namespace"].startswith("non-henderson-synthetic-")
    assert "NON-HENDERSON" in (PACKAGE / "README.md").read_text()

    # Measurement clocks and the contract's boolean policy flag are permitted;
    # no truth field, withheld event time, outcome or failure type is an input.
    forbidden = {"event", "event_id", "event_identity", "event_time", "event_timestamp",
                 "outcome", "failure_type", "label", "labels", "event_label", "ground_truth"}
    def assert_blind(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for key, item in value.items():
                if key.startswith("event_"):
                    assert key == "event_independent" and item is True
                assert_blind(item)
        elif isinstance(value, list):
            for item in value:
                assert_blind(item)
    assert_blind(metadata)
    assert_blind(source_rows)

    prepared = prepare_historical_pov(csv_bytes=raw, metadata=metadata)
    bundle = prepared.inspect()
    frozen_bundle_hash = digest(bundle)
    pair = bundle["profile"]["pairs"][0]
    observed_calls = []
    evaluator = sii_engine.evaluate_sii
    def observe(**kwargs):
        observed_calls.append({
            "profile_hash": digest(kwargs["relationship_acquisition_profile"]),
            "reference_hash": digest(kwargs["reference_rows"]),
            "first": kwargs["comparison_rows"][0]["timestamp"],
            "last": kwargs["comparison_rows"][-1]["timestamp"],
            "prior": deepcopy(kwargs["relationship_persistence_state"]),
        })
        return evaluator(**kwargs)
    monkeypatch.setattr(sii_engine, "evaluate_sii", observe)
    result = run_historical_pov(prepared)
    assert len(observed_calls) == 6
    assert [s["slot_id"] for s in result["slots"]] == [f"slot-{i:04d}" for i in range(1, 7)]
    assert {c["profile_hash"] for c in observed_calls} == {result["profile_hash"]}
    assert len({c["reference_hash"] for c in observed_calls}) == 1
    assert observed_calls[0]["prior"] == {}
    assert all(c["prior"] for c in observed_calls[1:])
    assert all(datetime.fromisoformat(a["last"]) < datetime.fromisoformat(b["first"])
               for a, b in zip(observed_calls, observed_calls[1:]))
    assert [c["first"] for c in observed_calls] == [w["start"] for w in pair["comparisons"]]

    provenance = result["provenance"]
    assert provenance["source"]["text"].encode() == raw
    assert provenance["source"]["sha256"] == sha256(raw).hexdigest()
    mapping = provenance["row_mapping"]
    all_indices = mapping["reference"] + [i for indices in mapping["comparisons"] for i in indices]
    assert all_indices == list(range(1, 113))
    checkpoint = result["checkpoint"]
    assert checkpoint["prepared_identity"] == prepared.identity == frozen_bundle_hash
    assert checkpoint["completed_slots"] == 6
    assert checkpoint["digest"] == digest({k: v for k, v in checkpoint.items() if k != "digest"})
    state = next(iter(checkpoint["relationship_persistence_state"].values()))["qualified_evidence"]
    assert state["version"] == "relationship-qualification.v2"
    assert len(state["slots"]) == 6
    windows = [state["reference"], *[o["comparison"] for o in state["observations"]]]
    for evidence, indices in zip(windows, [mapping["reference"], *mapping["comparisons"]]):
        reconstructed = [[source_rows[i-1]["timestamp"],
                          [float(source_rows[i-1][c]) for c in pair["columns"]]] for i in indices]
        assert digest(reconstructed) == evidence["selected_observations_hash"]
        assert sha256(raw).hexdigest() in evidence["source_locator"]

    assert result["not_quantifiable"] is True
    assert all(s["assessments"][0]["qualification_status"] in {"limited", "insufficient"}
               and not s["assessments"][0]["qualified_persistence_supported"] for s in result["slots"])
    frozen_result = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    replay = run_historical_pov(prepared)
    assert frozen_result == json.dumps(replay, sort_keys=True, separators=(",", ":"), allow_nan=False)
    assert digest(prepared.inspect()) == frozen_bundle_hash
    assert metadata == original_metadata


@pytest.mark.parametrize("field", [
    "signals", "timestamp", "acquisition", "grouping", "dependence_assumption",
    "independence_basis", "schedule", "context", "coverage_period_seconds", "plan",
])
def test_example_missing_required_metadata_fails_closed(field, monkeypatch):
    from app.engine import sii_engine

    monkeypatch.setattr(sii_engine, "evaluate_sii", lambda **kwargs: pytest.fail("unadmitted engine call"))
    raw, metadata = example()
    del metadata[field]
    with pytest.raises(PoVAdmissionError) as error:
        prepared = prepare_historical_pov(csv_bytes=raw, metadata=metadata)
        run_historical_pov(prepared)
    assert error.value.not_quantifiable is True
