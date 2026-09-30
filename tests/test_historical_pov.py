"""Synthetic mechanism tests only: no benchmark or event-labelled inputs."""
from copy import deepcopy
import csv
from hashlib import sha256
import io

import pytest

from app.services.historical_pov import (
    DEPENDENCE, PoVAdmissionError, prepare_historical_pov, run_historical_pov,
)
from test_relationship_qualification import observe, rows as measurements


def case(n=64, kinds=("independent",)):
    source = measurements(0, n=n)
    for day, kind in enumerate(kinds, 1):
        source.extend(measurements(day, kind, n=n))
    for i, row in enumerate(source):
        row["acq"] = f"native-{i}"
        row["block"] = f"independent-run-{i}"
    metadata = {
        "signals": {c: {"unit": unit, "bounds": [0, 1], "bounds_unit": unit,
                         "bounds_basis": "Synthetic bounded acquisition specification."}
                    for c, unit in (("flow", "L/s"), ("pressure", "kPa"))},
        "timestamp": {"column": "timestamp", "mode": "timezone_aware",
                      "basis": "Fresh simultaneous paired samples; fixed UTC source clock."},
        "acquisition": {"namespace": "synthetic-source", "identity": {"kind": "column", "column": "acq"},
                        "basis": "Native keys identify fresh acquisitions and survive replay."},
        "grouping": {"kind": "column", "column": "block", "justified": True,
                     "basis": "Synthetic independently initiated runs, no shared residual dependence."},
        "dependence_assumption": DEPENDENCE,
        "independence_basis": "Independent bounded draws conditional on this synthetic context and schedule.",
        "schedule": {"assumption": "predeclared_noninformative", "basis": "Fixed acquisition and export schedule."},
        "context": {"selection": {}, "basis": "One homogeneous synthetic acquisition population."},
        "coverage_period_seconds": n // 2 - 1,
        "plan": {"reference_epoch_rows": [n // 2, n // 2], "comparison_rows": [n] * len(kinds),
                 "basis": "Fixed chronological record counts, all source records included.",
                 "declared_before_analysis": True, "event_independent": True},
    }
    return source, metadata


@pytest.fixture(scope="module")
def sufficient():
    source, metadata = case(12000, ("independent",) * 6)
    prepared = prepare_historical_pov(rows=source, metadata=metadata)
    return prepared, run_historical_pov(prepared)


def test_sufficient_path_sustained_change_and_equal_valued_fresh_acquisitions(sufficient):
    prepared, output = sufficient
    assert not output["not_quantifiable"]
    assert len(output["slots"]) == 6
    final = output["slots"][-1]["assessments"][0]
    assert final["qualification_status"] == "sufficient"
    assert final["directional_persistence_supported"]
    assert final["qualified_persistence_supported"]
    assert final["persistent_relationship_change"]
    state = next(iter(output["checkpoint"]["relationship_persistence_state"].values()))
    ref = state["qualified_evidence"]["reference"]
    assert ref["status"] == "sufficient"
    assert ref["effective_group_count"] == 12000
    assert len({r["flow"] for r in prepared.inspect()["rows"]}) == 2
    assert len(state["qualified_evidence"]["slots"]) == 6
    assert len(state["qualified_evidence"]["seen_acquisitions"]) == 72000
    assert len({s["assessments"][0]["reference_qualification_id"] for s in output["slots"]}) == 1
    assert all(s["evidence_registry"] for s in output["slots"])


@pytest.mark.parametrize("defect,reason", [
    ("independence", "missing_independence_basis"),
    ("unjustified", "unjustified_grouping"),
    ("cadence", "unsupported_grouping_rule"),
    ("acquisition", "replayed_acquisition"),
    ("group", "reused_or_overlapping_groups"),
    ("clock", "unordered_or_overlapping_source_clock"),
    ("bounds", "measurement_out_of_bounds"),
    ("units", "bounds_unit_mismatch"),
    ("unknown_units", "unjustified_unit"),
    ("schedule", "unjustified_schedule"),
    ("plan", "informative_or_undeclared_plan"),
    ("coverage", "incomplete_temporal_coverage"),
    ("missing", "invalid_metadata_fields"),
])
def test_fail_closed_before_engine(defect, reason, monkeypatch):
    from app.engine import sii_engine
    monkeypatch.setattr(sii_engine, "evaluate_sii", lambda **kw: pytest.fail("engine called before admission"))
    source, metadata = case()
    if defect == "independence": metadata["independence_basis"] = ""
    if defect == "unjustified": metadata["grouping"]["justified"] = False
    if defect == "cadence": metadata["grouping"] = {"kind": "sampling_cadence", "basis": "one second", "justified": True}
    if defect == "acquisition": source[-1]["acq"] = source[0]["acq"]
    if defect == "group": source[-1]["block"] = source[0]["block"]
    if defect == "clock": source[64]["timestamp"] = source[63]["timestamp"]
    if defect == "bounds": source[-1]["flow"] = 2
    if defect == "units": metadata["signals"]["flow"]["bounds_unit"] = "gpm"
    if defect == "unknown_units":
        metadata["signals"]["flow"].update(unit="unknown", bounds_unit="unknown")
    if defect == "schedule": metadata["schedule"]["assumption"] = "unknown"
    if defect == "plan": metadata["plan"]["event_independent"] = False
    if defect == "coverage": metadata["coverage_period_seconds"] = 100000
    if defect == "missing": del metadata["independence_basis"]
    with pytest.raises(PoVAdmissionError, match=reason) as exc:
        prepare_historical_pov(rows=source, metadata=metadata)
    assert exc.value.not_quantifiable


def test_groups_cannot_cross_comparisons_but_can_cross_reference_epochs():
    source, metadata = case(kinds=("independent", "independent"))
    for row in source[:64]: row["block"] = "dependent-reference"
    prepared = prepare_historical_pov(rows=source, metadata=metadata)
    result = run_historical_pov(prepared, stop_after_slots=1)
    ref = next(iter(result["checkpoint"]["relationship_persistence_state"].values()))["qualified_evidence"]["reference"]
    assert ref["effective_group_count"] == 1
    assert result["not_quantifiable"]
    source[128]["block"] = source[64]["block"]
    with pytest.raises(PoVAdmissionError, match="reused_or_overlapping_groups"):
        prepare_historical_pov(rows=source, metadata=metadata)


def test_inadequate_reference_and_constant_fresh_comparison_abstain():
    source, metadata = case()
    result = run_historical_pov(prepare_historical_pov(rows=source, metadata=metadata))
    assert result["not_quantifiable"]
    assert not result["slots"][0]["assessments"][0]["qualified_persistence_supported"]
    state = next(iter(result["checkpoint"]["relationship_persistence_state"].values()))["qualified_evidence"]
    assert state["reference"]["status"] == "limited"
    for row in source[64:]: row["flow"] = .5
    result = run_historical_pov(prepare_historical_pov(rows=source, metadata=metadata))
    assert result["not_quantifiable"]
    assert result["slots"][0]["assessments"][0]["qualification"]["reason_codes"] == ["relationship_evidence_unavailable"]


def test_state_continuity_replay_and_detached_inputs():
    source, metadata = case(kinds=("independent",) * 3)
    prepared = prepare_historical_pov(rows=source, metadata=metadata)
    original_identity = prepared.identity
    source[0]["flow"] = 999
    metadata["coverage_period_seconds"] = 999
    prepared.inspect()["profile"]["assessment_id"] = "changed-disposable-copy"
    assert prepared.identity == original_identity
    whole = run_historical_pov(prepared)
    first = run_historical_pov(prepared, stop_after_slots=1)
    checkpoint = deepcopy(first["checkpoint"])
    rest = run_historical_pov(prepared, checkpoint=checkpoint)
    assert checkpoint == first["checkpoint"]
    assert whole["slots"] == first["slots"] + rest["slots"]
    assert whole["checkpoint"] == rest["checkpoint"]
    assert whole == run_historical_pov(prepared)


def test_absent_constant_slot_preserves_state_and_can_resume():
    source, metadata = case(kinds=("independent",) * 3)
    for row in source[128:192]: row["flow"] = .5
    prepared = prepare_historical_pov(rows=source, metadata=metadata)
    first = run_historical_pov(prepared, stop_after_slots=1)
    second = run_historical_pov(prepared, checkpoint=first["checkpoint"], stop_after_slots=2)
    assert second["not_quantifiable"]
    assert second["checkpoint"]["relationship_persistence_state"] == first["checkpoint"]["relationship_persistence_state"]
    last = run_historical_pov(prepared, checkpoint=second["checkpoint"])
    qualified = next(iter(last["checkpoint"]["relationship_persistence_state"].values()))["qualified_evidence"]
    assert len(qualified["slots"]) == 2
    assert last["slots"][0]["assessments"][0]["qualification"]["observations"] == 3


@pytest.mark.parametrize("mode", [None, [], {}])
def test_malformed_timestamp_mode_fails_closed(mode, monkeypatch):
    from app.engine import sii_engine

    monkeypatch.setattr(sii_engine, "evaluate_sii", lambda **kw: pytest.fail("unadmitted engine call"))
    source, metadata = case()
    metadata["timestamp"]["mode"] = mode
    with pytest.raises(PoVAdmissionError, match="unsupported_timestamp_mode") as error:
        prepared = prepare_historical_pov(rows=source, metadata=metadata)
        run_historical_pov(prepared)
    assert error.value.not_quantifiable is True


def test_unknown_basis_and_naive_clock_are_explicit():
    source, metadata = case()
    metadata["grouping"]["basis"] = "unknown"
    with pytest.raises(PoVAdmissionError, match="unjustified_grouping_basis"):
        prepare_historical_pov(rows=source, metadata=metadata)
    source, metadata = case()
    metadata["timestamp"]["mode"] = "naive_historical_source_clock"
    with pytest.raises(PoVAdmissionError, match="timestamp_mode_mismatch"):
        prepare_historical_pov(rows=source, metadata=metadata)
    for row in source:
        row["timestamp"] = row["timestamp"].replace("T", " ").replace("+00:00", "")
    prepared = prepare_historical_pov(rows=source, metadata=metadata)
    output = run_historical_pov(prepared)
    assert output["slots"][0]["supplied_reference"]["timestamp_mode"] == "naive_historical_source_clock"
    assert any("timezone_not_supplied" in s for s in output["slots"][0]["evidence_limitations"])


@pytest.mark.parametrize("change", ["profile", "reference", "checkpoint"])
def test_changed_profile_reference_or_checkpoint_rejected(change):
    source, metadata = case(kinds=("independent",) * 2)
    prepared = prepare_historical_pov(rows=source, metadata=metadata)
    checkpoint = run_historical_pov(prepared, stop_after_slots=1)["checkpoint"]
    if change == "profile": metadata["independence_basis"] += " Revised declaration."
    if change == "reference": source[0]["flow"] = .25
    if change == "checkpoint": checkpoint["relationship_persistence_state"] = {}
    modified = prepare_historical_pov(rows=source, metadata=metadata)
    with pytest.raises(PoVAdmissionError, match="checkpoint_changed|reference_or_profile_changed"):
        run_historical_pov(modified, checkpoint=checkpoint)


@pytest.mark.parametrize("kinds", [("independent",) + ("same",) * 5, ("same", "independent") * 3])
def test_transient_and_alternating_behavior_do_not_qualify(kinds):
    source, metadata = case(12000, kinds)
    bundle = prepare_historical_pov(rows=source, metadata=metadata).inspect()
    reference = bundle["rows"][:12000]
    state = None
    # Full paired-engine sustained coverage is above. Exercise these patterns at
    # the actual qualifier/reducer boundary without repeating unrelated runner
    # calculations; neither the profile nor the statistical math is mocked.
    for indices, kind in zip(bundle["row_mapping"]["comparisons"], kinds):
        comparison = [bundle["rows"][i-1] for i in indices]
        result, state, _ = observe(reference, comparison, bundle["profile"], state,
                                   rho=1 if kind == "same" else 0)
        assert not result["qualified_persistence_supported"]
    assert not result["directional_persistence_supported"]


def test_true_alternating_signed_changes_do_not_accumulate_directional_support():
    source, metadata = case(kinds=("same", "opposite") * 3)
    for i, row in enumerate(source[:64]):
        row["pressure"] = (i // 2) % 2
    result = run_historical_pov(prepare_historical_pov(rows=source, metadata=metadata))
    assessments = [s["assessments"][0] for s in result["slots"]]
    assert [a["signed_correlation_delta"] for a in assessments] == [1., -1.] * 3
    assert all(not a["directional_persistence_supported"] and not a["qualified_persistence_supported"]
               for a in assessments)


@pytest.mark.parametrize("location", ["top", "nested", "source"])
def test_blind_event_isolation_rejects_extra_fields(location):
    source, metadata = case()
    if location == "top": metadata["event_time"] = "withheld"
    if location == "nested": metadata["plan"]["outcome"] = "withheld"
    if location == "source":
        for row in source: row["event_label"] = "withheld"
    with pytest.raises(PoVAdmissionError, match="invalid_.*fields|unexpected_source_columns"):
        prepare_historical_pov(rows=source, metadata=metadata)


def test_csv_exact_provenance_reconstruction_and_deterministic_profile():
    from app.engine.relationship_qualification import digest
    source, metadata = case()
    source[0]["acq"] = "native\n0"  # Source records must not be confused with physical CSV lines.
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=list(source[0]), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(source)
    raw = b"\xef\xbb\xbf" + text.getvalue().encode()
    prepared = prepare_historical_pov(csv_bytes=raw, metadata=metadata)
    assert prepared == prepare_historical_pov(csv_bytes=raw, metadata=metadata)
    result = run_historical_pov(prepared)
    provenance = result["provenance"]
    assert provenance["source"]["text"].encode() == raw
    assert provenance["source"]["sha256"] == sha256(raw).hexdigest()
    parsed = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    bundle = prepared.inspect()
    pair = bundle["profile"]["pairs"][0]
    state = next(iter(result["checkpoint"]["relationship_persistence_state"].values()))["qualified_evidence"]
    evidence_windows = [state["reference"], state["observations"][0]["comparison"]]
    for evidence, (plan, indices) in zip(evidence_windows, [
            (pair["reference"], provenance["row_mapping"]["reference"]),
            (pair["comparisons"][0], provenance["row_mapping"]["comparisons"][0])]):
        assert len(plan["observations"]) == len(indices)
        for observation, i in zip(plan["observations"], indices):
            row = parsed[i-1]
            expected = {"timestamp": row["timestamp"], "flow": float(row["flow"]), "pressure": float(row["pressure"])}
            assert bundle["rows"][i-1] == expected
            assert observation["timestamp"] == row["timestamp"]
        assert sha256(raw).hexdigest() in plan["source_locator"]
        reconstructed = [[parsed[i-1]["timestamp"], [float(parsed[i-1][c]) for c in pair["columns"]]]
                         for i in indices]
        assert digest(reconstructed) == evidence["selected_observations_hash"]


def test_explicit_fresh_rows_and_independent_acquisitions_rule():
    source, metadata = case()
    for row in source:
        del row["acq"], row["block"]
    metadata["acquisition"]["identity"] = {"kind": "source_row", "fresh_nonreplayed_rows": True}
    metadata["grouping"] = {"kind": "independent_acquisitions", "justified": True,
                            "basis": "Every paired acquisition is an independently initiated synthetic run."}
    prepared = prepare_historical_pov(rows=source, metadata=metadata)
    events = prepared.inspect()["profile"]["pairs"][0]["reference"]["observations"]
    assert len({e["group_id"] for e in events}) == 64
    metadata["acquisition"]["identity"]["fresh_nonreplayed_rows"] = False
    with pytest.raises(PoVAdmissionError, match="unjustified_acquisition_identity"):
        prepare_historical_pov(rows=source, metadata=metadata)


def test_adapter_preserves_direct_engine_directional_numerics():
    from app.engine.sii_engine import evaluate_sii
    source, metadata = case()
    prepared = prepare_historical_pov(rows=source, metadata=metadata)
    bundle = prepared.inspect()
    result = run_historical_pov(prepared)["slots"][0]["assessments"][0]
    direct = evaluate_sii(columns=bundle["columns"], reference_rows=bundle["rows"][:64],
        comparison_rows=bundle["rows"][64:], timestamp_column="timestamp",
        signal_units={"flow": "L/s", "pressure": "kPa"},
        numeric_profiles=[{"column": "flow"}, {"column": "pressure"}])
    edge = direct["relationship_graph"]["edges"][0]
    for key in ("baseline_correlation", "current_correlation", "signed_correlation_delta",
                "persistence_factor", "directional_persistence_supported"):
        assert result[key] == edge[key]
