"""Mechanism fixtures: no benchmark inputs, labels, families or seeds."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
import json
import math

import pytest

from app.engine import relationship_qualification as q
from app.engine.relationship_change import relationship_temporal_evidence
from app.services.relationship_evidence_binding import source_evidence, temporal_descriptor, SOURCE
from app.services.relationship_baselines import _pearson_corr

COLS = ["flow", "pressure"]
UNITS = {"flow": "L/s", "pressure": "kPa"}


def rows(day, kind="same", n=12000):
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day)
    result = []
    for i in range(n):
        x = i % 2
        y = x if kind == "same" else 1 - x if kind == "opposite" else (i // 2) % 2
        result.append({"timestamp": (origin + timedelta(seconds=i)).isoformat(),
                       "flow": x, "pressure": y})
    return result


def schedule(data, name, reference=False):
    events = [{"timestamp": row["timestamp"], "acquisition_id": f"{name}:a{i}",
               "group_id": f"{name}:g{i}", **({"epoch_id": "early" if i < len(data)//2 else "late"} if reference else {})}
              for i, row in enumerate(data)]
    plan = {"start": data[0]["timestamp"], "end": data[-1]["timestamp"],
            "source_locator": f"immutable-fixture:{name}", "observations": events}
    if reference:
        mid = len(data)//2
        plan["epochs"] = [{"epoch_id": name, "start": data[a]["timestamp"], "end": data[b]["timestamp"]}
                          for name, a, b in (("early", 0, mid-1), ("late", mid, len(data)-1))]
    else:
        plan["slot_id"] = name
    return plan


def profile(reference, comparisons):
    return {"version": q.PROFILE_VERSION, "assessment_id": "mechanism-assessment",
            "acquisition_profile_id": "documented-independent-fixture", "independence_basis": "independent bounded draws",
            "dependence_assumption": "independent_groups_conditional_on_context_and_schedule",
            "schedule_assumption": "predeclared_noninformative", "coverage_period_seconds": 5999,
            "pairs": [{"columns": COLS, "signal_units": UNITS, "signal_bounds": {c: [0, 1] for c in COLS},
                       "bounds_basis": "bounded acquisition fixture specification",
                       "context": {"context_id": "one-context", "basis": "declared_homogeneous", "selection": {}},
                       "reference": schedule(reference, "ref", True),
                       "comparisons": [schedule(c, f"window-{i}") for i, c in enumerate(comparisons, 1)]}]}


def observe(reference, comparison, declared, previous=None, rho=0):
    baseline = _pearson_corr([r[COLS[0]] for r in reference], [r[COLS[1]] for r in reference]) or 0.
    edge = {"columns": COLS, "baseline_correlation": baseline, "current_correlation": rho,
            "signed_correlation_delta": rho-baseline, "eligible": True, "edge_confidence": .9,
            "data_quality_factor": 1., "signal_units": UNITS,
            "baseline_sample_count": len(reference), "current_sample_count": len(comparison),
            "time_window": {"baseline_start": reference[0]["timestamp"], "baseline_end": reference[-1]["timestamp"],
                            "current_start": comparison[0]["timestamp"], "current_end": comparison[-1]["timestamp"]}}
    source = source_evidence(edge, columns=COLS, baseline_rows=reference, current_rows=comparison,
                             timestamp_column="timestamp", units=UNITS)
    edge[SOURCE] = source
    edge["relationship_qualification"] = q.estimate(declared, previous, columns=COLS,
        baseline_rows=reference, current_rows=comparison, timestamp_column="timestamp", units=UNITS, source=source)
    result, state = relationship_temporal_evidence(edge, previous, basis="global_relationship_model")
    return result, state, edge


@pytest.fixture(scope="module")
def example():
    reference = rows(0)
    comparisons = [rows(day, "independent") for day in range(1, 7)]
    return reference, comparisons, profile(reference, comparisons)


def test_adequate_reference_and_sustained_change_with_binding_and_immutable_anchor(example, monkeypatch):
    reference, comparisons, declared = example
    before = q.digest(declared)
    result, state, edge = observe(reference, comparisons[0], declared)
    frozen = deepcopy(state["qualified_evidence"]["reference"])
    assert frozen["status"] == "sufficient", frozen
    assert frozen["pooled_interval_width"] < .15
    assert frozen["equivalence_established"] is False
    assert frozen["comparison_envelope"][0] < frozen["pooled_correlation_interval"][0]
    monkeypatch.setattr(q, "qualify_reference", lambda *a, **kw: pytest.fail("reference recalculated"))
    for comparison in comparisons[1:]:
        result, state, edge = observe(reference, comparison, declared, state)
        assert state["qualified_evidence"]["reference"] == frozen
    assert result["directional_persistence_supported"]
    assert result["qualified_persistence_supported"]
    assert result["persistent_relationship_change"]
    assert result["qualified_persistence"]["delta_interval"][1] < -.15
    graph = {"edge_basis": "global_relationship_model", "relationship_persistence_state": {
        json.dumps(COLS, separators=(",", ":")): state}}
    descriptor = temporal_descriptor({**edge, **result}, graph)
    assert descriptor["qualified_evidence"]["reference"] == frozen
    assert descriptor["assessment"]["qualified_persistence_supported"] is True
    assert q.digest(declared) == before
    from app.services.relationship_evidence_binding import finalize, resolve
    model = {"relationship_graph": {"edges": [edge]}, "top_relationship_changes": [deepcopy(edge)]}
    graph["edges"] = [{**edge, **result}]
    registry = finalize(model, graph, scope="qualified-fixture")
    resolved = resolve(model["top_relationship_changes"][0], registry,
                       authorized_scope="qualified-fixture", require_temporal=True)
    assert resolved["temporal"]["qualified_evidence"]["reference"] == json.loads(json.dumps(frozen))
    from app.services.telemetry_repository import _relationship_state_payload
    identity = ("tenant", "workspace", "resource", "facility", "system", "asset", "lineage")
    body, _ = _relationship_state_payload(identity, "a" * 64, state)
    assert body["reducer_state"]["qualified_evidence"]["reference"] == frozen
    from test_relationship_temporal_state_loading import _evidence, _descriptor, _stored, _run
    from app.services import relationship_temporal_state as storage
    record, lineage = _evidence(), _descriptor()
    record["temporal"].update(method=storage.QUALIFIED_REDUCER, identity=state["identity"],
                              qualified_evidence=state["qualified_evidence"])
    stored = _stored(record, lineage, reducer_state=state,
                     head_event_time=datetime.fromisoformat(state["observations"][-1]["observed_at"]))
    loaded, _ = _run(monkeypatch, stored, evidence=record, descriptor=lineage)
    assert loaded == state
    changed = deepcopy(record)
    changed["temporal"]["qualified_evidence"]["reference_id"] = "another-reference"
    assert storage.compatibility_digest(changed, lineage) != storage.compatibility_digest(record, lineage)
    tampered = deepcopy(state)
    tampered["qualified_evidence"]["reference"]["comparison_envelope"] = [-.1, .1]
    graph["relationship_persistence_state"][json.dumps(COLS, separators=(",", ":"))] = tampered
    with pytest.raises(ValueError, match="qualification_binding"):
        temporal_descriptor({**edge, **result}, graph)


def test_retry_and_lifetime_reuse_cannot_add_support(example):
    reference, comparisons, declared = example
    first, state, _ = observe(reference, comparisons[0], declared)
    retry, repeated, _ = observe(reference, comparisons[0], declared, state)
    assert state == repeated
    assert first == retry
    changed = deepcopy(declared)
    for a, b in zip(changed["pairs"][0]["comparisons"][1]["observations"],
                    changed["pairs"][0]["comparisons"][0]["observations"]):
        a["acquisition_id"] = b["acquisition_id"]
        a["group_id"] = b["group_id"]
    _, state, _ = observe(reference, comparisons[0], changed)
    result, state, _ = observe(reference, comparisons[1], changed, state)
    assert result["qualified_persistence"]["reason_codes"] == ["reused_or_overlapping_acquisitions"]
    assert result["qualified_persistence"]["supporting_observations"] == 1


def test_dependent_rows_have_one_unit_and_equal_values_remain_valid(example):
    reference, comparisons, declared = example
    _, state, _ = observe(reference, comparisons[0], declared)
    assert state["qualified_evidence"]["reference"]["effective_group_count"] == 12000
    assert len({r["flow"] for r in reference}) == 2  # Value uniqueness is not evidence identity.
    dependent = deepcopy(declared)
    for event in dependent["pairs"][0]["reference"]["observations"]:
        event["group_id"] = "one-dependent-group"
    result, state, _ = observe(reference, comparisons[0], dependent)
    assert state["qualified_evidence"]["reference"]["effective_group_count"] == 1
    assert result["qualification_status"] == "limited"


@pytest.mark.parametrize("defect", ["missing", "bounds", "assumption", "group", "clock", "schedule", "context"])
def test_missing_invalid_profile_fails_closed(example, defect):
    reference, comparisons, declared = example
    declared = deepcopy(declared)
    if defect == "missing": declared = None
    elif defect == "bounds": declared["pairs"][0].pop("signal_bounds")
    elif defect == "assumption": declared["dependence_assumption"] = "inferred_from_N"
    elif defect == "group": declared["pairs"][0]["reference"]["observations"][0].pop("group_id")
    elif defect == "clock": declared["pairs"][0]["reference"]["observations"][0]["timestamp"] = "bad"
    elif defect == "schedule": declared["pairs"][0]["reference"]["observations"].pop()
    elif defect == "context": declared["pairs"][0]["context"]["selection"] = {"mode": "different"}
    result, _, _ = observe(reference, comparisons[0], declared)
    assert result["qualification_status"] in ("limited", "insufficient")
    assert not result["qualified_persistence_supported"]


def test_unstable_epochs_retained_and_constant_reference_insufficient(example):
    reference, comparisons, _ = example
    unstable = deepcopy(reference)
    for row in unstable[6000:]: row["pressure"] = 1 - row["flow"]
    _, state, _ = observe(unstable, comparisons[0], profile(unstable, comparisons))
    ref = state["qualified_evidence"]["reference"]
    assert ref["status"] == "limited"
    assert ref["resolved_incompatibility_witnesses"]
    assert ref["comparison_envelope"] == [-1, 1]
    constant = deepcopy(reference)
    for row in constant: row["flow"] = .5
    _, state, _ = observe(constant, comparisons[0], profile(constant, comparisons))
    assert state["qualified_evidence"]["reference"]["status"] == "insufficient"


@pytest.mark.parametrize("kinds", [["independent"] + ["same"] * 5, ["same", "independent"] * 3])
def test_transient_and_intermittent_do_not_qualify(kinds):
    reference = rows(0)
    comparisons = [rows(i, kind) for i, kind in enumerate(kinds, 1)]
    declared = profile(reference, comparisons)
    state = None
    for comparison, kind in zip(comparisons, kinds):
        result, state, _ = observe(reference, comparison, declared, state, rho=1 if kind == "same" else 0)
        assert not result["qualified_persistence_supported"]


def test_extreme_sampled_reference_stationary_comparisons_are_not_assumed_safe():
    # A stationary bounded process can sample a perfectly correlated reference.
    # Under the declared independent-draw model, such a sufficiently large rare
    # sample is not distinguishable from a change. The contract is not zero-error.
    reference = rows(0, n=96)
    comparisons = [rows(1, "independent", n=96)]
    declared = profile(reference, comparisons)
    declared["coverage_period_seconds"] = 47
    result, state, _ = observe(reference, comparisons[0], declared)
    assert not result["qualified_persistence_supported"]
    assert state["qualified_evidence"]["reference"]["status"] == "limited"


def test_overlapping_windows_do_not_add_support(example):
    reference, comparisons, _ = example
    shifted = deepcopy(comparisons[0])
    for row in shifted:
        row["timestamp"] = (datetime.fromisoformat(row["timestamp"]) + timedelta(seconds=6000)).isoformat()
    declared = profile(reference, [comparisons[0], shifted])
    _, state, _ = observe(reference, comparisons[0], declared)
    result, state, _ = observe(reference, shifted, declared, state)
    assert result["qualified_persistence"]["reason_codes"] == ["reused_or_overlapping_acquisitions"]
    assert result["qualified_persistence"]["supporting_observations"] == 1


def test_mean_intervals_enclose_analytic_moments():
    data = rows(0, n=12000)
    events = schedule(data, "fresh")["observations"]
    evidence = q.moment_evidence(data, events, COLS, {c: [0, 1] for c in COLS}, Fraction(1, 80))
    assert all(lo <= .5 <= hi for lo, hi in evidence["observed_moment_intervals"])
    lo, hi = evidence["correlation_interval"]
    assert lo <= 0.8653732346992433 and hi == 1


@pytest.mark.parametrize("count,reference_status", [(64, "limited"), (12000, "sufficient")])
def test_entrypoint_accepts_profile_without_relaxing_paired_boundary(count, reference_status):
    from app.engine.sii_engine import evaluate_sii
    reference, comparison = rows(0, n=count), rows(1, "independent", n=count)
    declared = profile(reference, [comparison])
    declared["coverage_period_seconds"] = count // 2 - 1
    kwargs = dict(columns=["timestamp", *COLS], reference_rows=reference, comparison_rows=comparison,
                  numeric_profiles=[{"column": c} for c in COLS], signal_units=UNITS, timestamp_column="timestamp")
    original = deepcopy(kwargs)
    output = evaluate_sii(**kwargs, relationship_acquisition_profile=declared)
    assert not output["processing_trace"]["modules_failed"]
    edge = output["relationship_graph"]["edges"][0]
    assert edge["qualification_status"] == reference_status
    state = next(iter(output["relationship_graph"]["relationship_persistence_state"].values()))
    assert state["qualified_evidence"]["reference"]["status"] == reference_status
    assert kwargs == original
    kwargs["reference_rows"] = deepcopy(reference)
    kwargs["reference_rows"][1]["timestamp"] = kwargs["reference_rows"][0]["timestamp"]
    with pytest.raises(ValueError):
        evaluate_sii(**kwargs, relationship_acquisition_profile=declared)


def test_source_identity_and_pearson_invariance_with_profile(example):
    from app.services.relationship_baselines import build_relationship_baseline
    reference, comparisons, declared = example
    kwargs = dict(timestamp_column="timestamp", reference_rows=reference, binding_signal_units=UNITS,
                  recent_window_limit=12000)
    before = build_relationship_baseline(comparisons[0], COLS, **kwargs)
    after = build_relationship_baseline(comparisons[0], COLS, acquisition_profile=declared, **kwargs)
    def numerical(value):
        if isinstance(value, dict):
            return {k: numerical(v) for k, v in value.items() if k != "relationship_qualification"}
        if isinstance(value, list): return [numerical(v) for v in value]
        return value
    assert numerical(before) == numerical(after)


def test_late_start_and_changed_profile_cannot_claim_missing_evidence(example):
    reference, comparisons, declared = example
    result, state, _ = observe(reference, comparisons[5], declared)
    assert result["qualified_persistence"]["observations"] == 6
    assert result["qualified_persistence"]["supporting_observations"] == 1
    changed = deepcopy(declared)
    changed["pairs"][0]["signal_bounds"]["flow"] = [-1, 2]
    result, state2, _ = observe(reference, comparisons[5], changed, state)
    assert not result["qualified_persistence_supported"]
    assert result["qualified_persistence"]["reason_codes"] == ["reference_or_profile_changed"]
    assert state2["qualified_evidence"]["reference"] == state["qualified_evidence"]["reference"]


def test_block_replication_cannot_reduce_moment_uncertainty():
    original = rows(0, n=100)
    events = schedule(original, "measurements")["observations"]
    replicated = [r for r in original for _ in range(6)]
    groups = [e for e in events for _ in range(6)]
    a = q.moment_evidence(original, events, COLS, {c: [0, 1] for c in COLS}, Fraction(1, 80))
    b = q.moment_evidence(replicated, groups, COLS, {c: [0, 1] for c in COLS}, Fraction(1, 80))
    assert a["effective_group_count"] == b["effective_group_count"] == 100
    assert a["epsilon"] == b["epsilon"]


def test_true_alternating_signed_displacement_and_unknown_reference_fail_closed():
    def correlated(day, rho):
        data = rows(day, n=64)
        for i, row in enumerate(data):
            angle = 2 * math.pi * i / 32
            row["flow"] = (1 + math.sin(angle)) / 2
            row["pressure"] = .5 + (rho * math.sin(angle) + math.sqrt(1-rho*rho) * math.cos(angle)) / 3
        return data
    reference = correlated(0, .65)
    rhos = [.95, .35] * 3
    comparisons = [correlated(day, rho) for day, rho in enumerate(rhos, 1)]
    declared = profile(reference, comparisons)
    declared["coverage_period_seconds"] = 31
    state = None
    for comparison, rho in zip(comparisons, rhos):
        result, state, edge = observe(reference, comparison, declared, state, rho=rho)
        assert (edge["signed_correlation_delta"] > 0) == (rho > .65)
        assert not result["directional_persistence_supported"]
        assert not result["qualified_persistence_supported"]
    assert state["qualified_evidence"]["reference"]["status"] == "limited"
