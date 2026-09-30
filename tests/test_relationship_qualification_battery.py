"""Independent supported-data battery. Expectations precede execution.

Moderate means rho 1 -> 1/4 (versus the full-span 1 -> -1 strong change).
No binary FPR estimate is inferred from this intentionally small mechanism set.
"""
from copy import deepcopy
from fractions import Fraction
import json

import pytest

from app.engine import relationship_qualification as q
from app.services.relationship_evidence_binding import finalize, resolve, temporal_descriptor
from qualification_battery_cases import COLS, case, measurements, window, step, run


# All parameters are physical/sample constructions, not gate adjustments.
SCENARIOS = [
    ("stable_adequate", [1.] * 6, {}, False, "sufficient"),
    ("stable_inadequate", [1.] * 6, {"reference_n": 64}, False, "limited"),
    ("strong_sustained", [-1.] * 6, {}, True, "sufficient"),
    ("moderate_resolvable", [.25] * 6, {}, True, "sufficient"),
    ("small_unresolved", [.9] * 6, {}, False, "sufficient"),
    ("transient", [-1.] + [1.] * 5, {}, False, "sufficient"),
    ("alternating_displacement_recovery", [-1., 1.] * 3, {}, False, "sufficient"),
    ("alternating_direction", [-1., 1.] * 3, {"reference_rho": 0.}, False, "limited"),
    ("noisy_stationary", [.75] * 6, {"reference_rho": .75}, False, "limited"),
    ("extreme_small_sample_reference", [0.] * 6, {"reference_n": 64}, False, "limited"),
    ("dependent_blocks", [-1.] * 6, {"block": 24}, False, "limited"),
    ("insufficient_comparison", [-1.] * 6, {"comparison_n": 64}, False, "limited"),
    ("irregular_declared_schedule", [-1.] * 6, {"irregular": True}, True, "sufficient"),
]


@pytest.mark.parametrize("name,rhos,options,qualified,status", SCENARIOS, ids=[s[0] for s in SCENARIOS])
def test_physical_scenarios(name, rhos, options, qualified, status, record_property):
    summaries, state, _, graph = run(case(name, rhos, **options))
    assert [s["qualified_persistence_supported"] for s in summaries] == [False]*5 + [qualified]
    assert summaries[-1]["qualification_status"] == status
    anchor = next(iter(state.values()))["qualified_evidence"]["reference"]
    if qualified:
        assert summaries[-1]["directional_persistence_supported"]
        assert summaries[-1]["promoted_changed_edge"]
        assert anchor["status"] == "sufficient"
        assert anchor["equivalence_established"] is False  # not an admission requirement
    if name in {"dependent_blocks", "insufficient_comparison", "extreme_small_sample_reference"}:
        assert summaries[-1]["directional_persistence_supported"]
        assert summaries[-1]["persistence_factor"] == 1.
        assert not summaries[-1]["qualified_persistence_supported"]
    record_property("scenario", name)
    record_property("reference_status", anchor["status"])
    record_property("qualified", qualified)
    record_property("last_assessment", json.dumps(summaries[-1], sort_keys=True))


@pytest.fixture(scope="module")
def admissible():
    return case("adversarial-admission", [-1.] * 7)


def admission_mutation(kind, reference, comparison, profile):
    pair = profile["pairs"][0]
    events = pair["comparisons"][0]["observations"]
    if kind == "missing_profile": return None
    if kind == "missing_groups": events[0].pop("group_id")
    if kind == "missing_timestamp": comparison[5].pop("timestamp")
    if kind == "duplicate_id": events[1]["acquisition_id"] = events[0]["acquisition_id"]
    if kind == "invalid_id": events[0]["acquisition_id"] = 7
    if kind == "duplicate_timestamp":
        events[1]["timestamp"] = events[0]["timestamp"]
        comparison[1]["timestamp"] = comparison[0]["timestamp"]
    if kind == "missing_bounds": pair.pop("signal_bounds")
    if kind == "invalid_bounds": pair["signal_bounds"][COLS[0]] = [1, 0]
    if kind == "nonfinite_bounds": pair["signal_bounds"][COLS[0]] = [0, float('inf')]
    if kind == "out_of_bounds": comparison[5][COLS[0]] = 2
    if kind == "inadequate_coverage": profile["coverage_period_seconds"] = 86400
    if kind == "context_mismatch": pair["context"]["selection"] = {"mode_id": "different"}
    if kind == "reordered_rows": comparison[2], comparison[3] = comparison[3], comparison[2]
    if kind == "undeclared_dependence": profile.pop("dependence_assumption")
    return profile


@pytest.mark.parametrize("kind", ["missing_profile", "missing_groups", "missing_timestamp", "duplicate_id", "invalid_id",
    "duplicate_timestamp", "missing_bounds", "invalid_bounds", "nonfinite_bounds", "out_of_bounds", "inadequate_coverage",
    "context_mismatch", "reordered_rows", "undeclared_dependence"])
def test_invalid_admission_fails_closed(admissible, kind):
    ref, comparisons, profile = deepcopy(admissible)
    profile = admission_mutation(kind, ref, comparisons[0], profile)
    edge, _, _, _ = step(ref, comparisons[0], profile)
    assert edge["qualification_status"] in {"limited", "insufficient"}
    assert not edge["qualified_persistence_supported"]


def test_replay_reload_retry_conflicting_values_and_reset(admissible):
    ref, comparisons, profile = admissible
    edge, state, _, _ = step(ref, comparisons[0], profile)
    serialized = json.loads(json.dumps(state))
    retry, unchanged, _, _ = step(ref, comparisons[0], profile, serialized)
    assert json.loads(json.dumps(unchanged)) == serialized
    assert retry["qualified_persistence"] == edge["qualified_persistence"]
    for _ in range(6):
        replay, state, _, _ = step(ref, comparisons[0], profile, state)
        assert replay["qualified_persistence"]["supporting_observations"] == 1
        assert not replay["qualified_persistence_supported"]
    changed = deepcopy(comparisons[0]); changed[0][COLS[0]] = 1 - changed[0][COLS[0]]
    conflict, _, _, _ = step(ref, changed, profile, state)
    assert conflict["qualification_status"] == "limited"
    # Dropping state cannot borrow previous votes. A complete caller forgery is
    # outside the approved integrity boundary; no hidden global store exists.
    reset, reset_state, _, _ = step(ref, comparisons[5], profile, None)
    assert reset["qualified_persistence"]["supporting_observations"] == 1
    assert reset["qualified_persistence"]["observations"] == 6
    assert not reset["qualified_persistence_supported"]


@pytest.mark.parametrize("reuse", ["acquisition", "group", "reference", "time_overlap"])
def test_reuse_cannot_supply_a_second_vote(admissible, reuse):
    ref, comparisons, profile = deepcopy(admissible)
    a, b = profile["pairs"][0]["comparisons"][:2]
    if reuse in {"acquisition", "group"}:
        key = "acquisition_id" if reuse == "acquisition" else "group_id"
        for first, second in zip(a["observations"], b["observations"]): second[key] = first[key]
    elif reuse == "reference":
        for first, second in zip(profile["pairs"][0]["reference"]["observations"], b["observations"]):
            second["acquisition_id"] = first["acquisition_id"]
    else:
        from datetime import datetime, timedelta
        for row in comparisons[1]: row["timestamp"] = (datetime.fromisoformat(row["timestamp"])-timedelta(hours=23)).isoformat()
        profile["pairs"][0]["comparisons"][1] = window(comparisons[1], 2)
    _, state, _, _ = step(ref, comparisons[0], profile)
    blocked, _, _, _ = step(ref, comparisons[1], profile, state)
    assert blocked["qualified_persistence"]["supporting_observations"] == 1
    assert blocked["qualified_persistence"]["reason_codes"] == ["reused_or_overlapping_acquisitions"]


@pytest.mark.parametrize("change", ["reference", "profile", "reference_hash", "malformed_reference"])
def test_reference_identity_and_provenance_cannot_change(admissible, change):
    ref, comparisons, profile = deepcopy(admissible)
    _, state, _, _ = step(ref, comparisons[0], profile)
    original = deepcopy(next(iter(state.values()))["qualified_evidence"]["reference"])
    if change == "reference": ref[0][COLS[0]] = 1-ref[0][COLS[0]]
    if change == "profile": profile["assessment_id"] = "different-assessment"
    if change == "reference_hash": next(iter(state.values()))["qualified_evidence"]["reference_hash"] = "invalid"
    if change == "malformed_reference": next(iter(state.values()))["qualified_evidence"]["reference"] = {"status": "sufficient"}
    edge, _, _, _ = step(ref, comparisons[1], profile, state)
    assert edge["qualification_status"] == "limited"
    assert not edge["qualified_persistence_supported"]


def test_out_of_order_cannot_rewrite_retained_evidence(admissible):
    ref, comparisons, profile = admissible
    _, state, _, _ = step(ref, comparisons[1], profile)
    saved = deepcopy(state)
    edge, after, _, _ = step(ref, comparisons[0], profile, state)
    assert after == saved
    assert edge["qualified_persistence"]["reason_codes"] == ["invalid_chronology"]


@pytest.mark.parametrize("pattern", ["independent", "repeated", "uneven", "one_group"])
def test_effective_information_uses_declared_groups_only(pattern):
    data = measurements(0, 1., 12000)
    events = window(data, 0)["observations"]
    baseline = q.moment_evidence(data, events, COLS, {c: [0, 1] for c in COLS}, Fraction(1, 80))
    if pattern == "repeated":
        data = [row for row in data for _ in range(3)]
        events = [event for event in events for _ in range(3)]
    elif pattern == "uneven":
        for event in events[:11900]: event["group_id"] = "large-dependent-group"
    elif pattern == "one_group":
        for event in events: event["group_id"] = "single-group"
    result = q.moment_evidence(data, events, COLS, {c: [0, 1] for c in COLS}, Fraction(1, 80))
    if pattern in {"independent", "repeated"}:
        assert result["effective_group_count"] == baseline["effective_group_count"] == 12000
        assert result["epsilon"] == baseline["epsilon"]
    else:
        assert result["effective_group_count"] < 2
        assert result["status"] == "limited"
    # Two distinct values do not make only two independent acquisitions.
    assert len({row[COLS[0]] for row in data}) == 2


def test_fresh_information_improves_precision_without_inventing_independence():
    data = measurements(0, 1., 12000)
    events = window(data, 0)["observations"]
    bounds = {c: [0, 1] for c in COLS}
    small = q.moment_evidence(data[:100], events[:100], COLS, bounds, Fraction(1,80))
    large = q.moment_evidence(data, events, COLS, bounds, Fraction(1,80))
    assert small["effective_group_count"] == 100
    assert large["effective_group_count"] == 12000
    assert large["epsilon"] < small["epsilon"]


def test_legitimate_constant_plateau_is_not_duplicate_evidence_but_has_no_relationship(admissible):
    ref, comparisons, profile = deepcopy(admissible)
    for row in comparisons[0]: row[COLS[0]] = .5
    edge, state, _, _ = step(ref, comparisons[0], profile)
    evidence = next(iter(state.values()))["qualified_evidence"]
    comp = evidence["observations"][0]["comparison"]
    assert comp["effective_group_count"] == 12000
    assert comp["status"] == "insufficient"
    assert comp["reason_codes"] == ["undefined_relationship_variance"]
    assert not edge["qualified_persistence_supported"]


@pytest.mark.parametrize('malformed', ['ledger', 'observation', 'gate_nan', 'slot', 'partial_reset'])
def test_malformed_retained_provenance_fails_closed(admissible, malformed):
    ref, comparisons, profile = admissible
    _, state, _, _ = step(ref, comparisons[0], profile)
    saved = next(iter(state.values()))
    if malformed == 'ledger': saved["qualified_evidence"] = "malformed retained qualification"
    if malformed == 'observation': saved["qualified_evidence"]["observations"] = ['invalid']
    if malformed == 'gate_nan': saved["qualified_evidence"]["observations"][0]['admission_gates']['edge_confidence'] = float('nan')
    if malformed == 'slot': saved["qualified_evidence"]["slots"]['slot-1'] = 'invalid'
    if malformed == 'partial_reset': saved.pop('qualified_evidence')
    edge, rejected_state, _, _ = step(ref, comparisons[1], profile, state)
    assert edge["qualification_status"] == "limited"
    assert not edge["qualified_persistence_supported"]
    again, _, _, _ = step(ref, comparisons[2], profile, rejected_state)
    assert again["qualified_persistence"]["reason_codes"] == ["invalid_qualification_state"]


def test_supported_assertion_requires_qualification_provenance():
    from test_relationship_evidence_binding import produced
    _, graph, _ = produced(6)  # genuine directional-only control
    edge = graph['edges'][0]
    edge['qualified_persistence_supported'] = True
    edge['persistent_relationship_change'] = True
    edge['temporal_persistence_supported'] = True
    edge['temporal_persistence_status'] = 'supported'
    with pytest.raises(ValueError, match='qualification'):
        temporal_descriptor(edge, graph)


def test_governed_projection_retains_both_endpoints_and_reference_identity():
    from app.services.analysis_result_contract import _sii_relationship
    from test_relationship_evidence_binding import produced
    _, graph, _ = produced(6)
    edge = graph['edges'][0]
    result = _sii_relationship(edge)
    for field in ('directional_persistence_supported', 'directional_persistence_status',
                  'qualified_persistence_supported', 'qualification_status', 'reference_qualification_id',
                  'persistence_factor'):
        assert result[field] == edge[field]
    assert result['directional_persistence_supported'] is True
    assert result['qualified_persistence_supported'] is False


def test_historical_qualification_obeys_current_existing_quality_gates():
    # Six directional votes and six interval votes are not enough if they are
    # different sets. Only five windows satisfy BOTH gates in the final horizon.
    ref, comparisons, profile = case('historical-quality-admission', [-1.] * 6 + [.75, -1.])
    state = None
    for i, comparison in enumerate(comparisons):
        edge, state, _, _ = step(ref, comparison, profile, state,
            confidence=.5 if i < 2 else .9,
            config={'minimum_edge_confidence': .6} if i == 7 else None)
    assert edge['directional_persistence_supported']
    assert not edge['qualified_persistence_supported']
    assert edge['qualified_persistence']['supporting_observations'] == 5


def test_retry_under_changed_gate_policy_cannot_borrow_previous_qualification(admissible):
    ref, comparisons, profile = admissible
    _, state, _, _ = step(ref, comparisons[0], profile)
    edge, _, _, _ = step(ref, comparisons[0], profile, state, config={'minimum_edge_confidence': .8})
    assert edge['qualification_status'] == 'limited'
    assert not edge['qualified_persistence_supported']
