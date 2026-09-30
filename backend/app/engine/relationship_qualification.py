"""Conditional bounded-moment evidence. No acquisition assumptions are inferred.

Profiles are caller declarations, not evidence that independence has been proved.
See docs/relationship_qualified_evidence.md for the admission and state contracts.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime
from fractions import Fraction
from hashlib import sha256
import json
import math
from app.engine.relationship_change import TEMPORAL_RULES

VERSION = "relationship-qualification.v2"
IMPLEMENTATION_VERSION = "bounded-moments-reference-envelope.v1"
NUMERIC_POLICY = "binary64-outward-nextafter.v1"
PROFILE_VERSION = "relationship-acquisition.v1"
RESOLUTION = TEMPORAL_RULES["minimum_displacement"]


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def limited(reason, status="limited"):
    return {"version": VERSION, "status": status, "reason_codes": [reason]}


def retained_qualification(previous):
    """Reject malformed caller state; never silently turn it into a new ledger.

    This is structural validation, not authentication of caller declarations.
    Persisted/transported state must still pass the existing integrity binding.
    """
    if previous is None:
        return {}
    if not isinstance(previous, dict):
        raise ValueError("invalid_qualification_state")
    if previous.get("version") == 2 and "qualified_evidence" not in previous:
        raise ValueError("invalid_qualification_state")
    value = previous.get("qualified_evidence", {})
    if not isinstance(value, dict):
        raise ValueError("invalid_qualification_state")
    if value and (value.get("version") != VERSION or value.get("invalid_state")
                  or any(not isinstance(value.get(k), dict) for k in ("reference", "identity", "slots"))
                  or any(not isinstance(value.get(k), list) for k in ("observations", "seen_acquisitions", "seen_groups"))
                  or any(not isinstance(value.get(k), str) for k in ("reference_id", "reference_hash"))):
        raise ValueError("invalid_qualification_state")
    if value:
        for name in ("seen_acquisitions", "seen_groups"):
            if any(not isinstance(item, str) or not item for item in value[name]):
                raise ValueError("invalid_qualification_state")
        if value.get("last_end") is not None and not isinstance(value["last_end"], str):
            raise ValueError("invalid_qualification_state")
        for slot, entry in value["slots"].items():
            if (not isinstance(slot, str) or not isinstance(entry, dict)
                    or not isinstance(entry.get("fingerprint"), str)
                    or not isinstance(entry.get("assessment"), dict)):
                raise ValueError("invalid_qualification_state")
        for observation in value["observations"]:
            if (not isinstance(observation, dict) or not isinstance(observation.get("slot_id"), str)
                    or not isinstance(observation.get("comparison"), dict)
                    or not isinstance(observation.get("assessment"), dict)
                    or observation["assessment"].get("status") not in {"sufficient", "limited", "insufficient"}):
                raise ValueError("invalid_qualification_state")
            if "admission_gates" in observation:
                gates = observation["admission_gates"]
                if (not isinstance(gates, dict) or not isinstance(gates.get("eligible"), bool)
                        or any(not isinstance(gates.get(k), (int, float)) or isinstance(gates[k], bool)
                               or not math.isfinite(gates[k]) or not 0 <= gates[k] <= 1
                               for k in ("edge_confidence", "data_quality_factor"))):
                    raise ValueError("invalid_qualification_state")
    return value


def down(x):
    return math.nextafter(x, -math.inf)


def up(x):
    return math.nextafter(x, math.inf)


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("missing_profile_identifier")
    return value


def clock(value):
    parsed = datetime.fromisoformat(text(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None and parsed.strftime("%Y-%m-%d %H:%M:%S") != value:
        raise ValueError("invalid_source_clock")
    return parsed


def bounds_for(pair, columns, units):
    text(pair["bounds_basis"])
    bounds = pair["signal_bounds"]
    for c in columns:
        lo, hi = bounds[c]
        if (isinstance(lo, bool) or isinstance(hi, bool)
                or not math.isfinite(lo) or not math.isfinite(hi)
                or lo >= hi or not math.isfinite(hi - lo) or down(hi - lo) <= 0):
            raise ValueError("invalid_signal_bounds")
        if pair["signal_units"][c] != units.get(c) or units.get(c) is None:
            raise ValueError("unestablished_bound_units")
    return bounds


def normalized_interval(value, lo, hi):
    value = float(value)
    if not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError("nonfinite_or_out_of_bounds_measurement")
    return (max(0.0, down(down(value - lo) / up(hi - lo))),
            min(1.0, up(up(value - lo) / down(hi - lo))))


def moment_evidence(rows, events, columns, bounds, budget):
    """Outward intervals, including input arithmetic and summation rounding."""
    n = len(rows)
    if n != len(events):
        raise ValueError("acquisition_schedule_mismatch")
    if n < 3:
        return limited("insufficient_paired_observations", "insufficient")
    counts = Counter(e["group_id"] for e in events)
    square_counts = sum(count * count for count in counts.values())
    eps = up(math.sqrt(up(up(math.log(up(float(10 / budget))))
                          * up(square_counts / (2 * n * n)))))
    lows, highs = [[] for _ in range(5)], [[] for _ in range(5)]
    constant = [set(), set()]
    for row in rows:
        x, y = [normalized_interval(row[c], *bounds[c]) for c in columns]
        for i, c in enumerate(columns):
            constant[i].add(float(row[c]))
        terms = [x, y, (max(0, down(x[0] ** 2)), min(1, up(x[1] ** 2))),
                 (max(0, down(y[0] ** 2)), min(1, up(y[1] ** 2))),
                 (max(0, down(x[0] * y[0])), min(1, up(x[1] * y[1])))]
        for i, (lo, hi) in enumerate(terms):
            lows[i].append(lo)
            highs[i].append(hi)
    observed = [(max(0, down(down(math.fsum(lo)) / n)),
                 min(1, up(up(math.fsum(hi)) / n))) for lo, hi in zip(lows, highs)]
    intervals = [(max(0, down(lo - eps)), min(1, up(hi + eps))) for lo, hi in observed]
    (xl, xu), (yl, yu), (xxl, xxu), (yyl, yyu), (xyl, xyu) = intervals
    vx = (max(0, down(xxl - up(xu * xu))), min(.25, up(xxu - down(xl * xl))))
    vy = (max(0, down(yyl - up(yu * yu))), min(.25, up(yyu - down(yl * yl))))
    result = {"status": "sufficient", "reason_codes": [], "nominal_count": n,
              "group_counts": dict(sorted(counts.items())),
              "group_weights": {k: v / n for k, v in sorted(counts.items())},
              "effective_group_count": n * n / square_counts,
              "budget": str(budget), "epsilon": eps, "observed_moment_intervals": observed,
              "moment_intervals": intervals, "variance_intervals": [vx, vy]}
    if any(len(values) == 1 for values in constant):
        result.update(status="insufficient", reason_codes=["undefined_relationship_variance"])
    elif vx[0] <= 0 or vy[0] <= 0:
        result.update(status="limited", reason_codes=["unresolved_relationship_variance"])
    else:
        denom = (down(math.sqrt(max(0, down(vx[0] * vy[0])))),
                 up(math.sqrt(up(vx[1] * vy[1]))))
        if denom[0] <= 0:
            result.update(status="limited", reason_codes=["unresolved_relationship_variance"])
            return result
        cov = (down(xyl - up(xu * yu)), up(xyu - down(xl * yl)))
        quotients = [c / d for c in cov for d in denom]
        result["correlation_interval"] = [max(-1, down(min(quotients))), min(1, up(max(quotients)))]
    return result


def scheduled(window, coverage):
    start, end = clock(window["start"]), clock(window["end"])
    if (end - start).total_seconds() < coverage:
        raise ValueError("incomplete_temporal_coverage")
    events = window["observations"]
    if not isinstance(events, list) or len(events) < 3:
        raise ValueError("incomplete_acquisition_schedule")
    times = [clock(e["timestamp"]) for e in events]
    if times[0] != start or times[-1] != end or any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("invalid_acquisition_clock")
    if (times[-1] - times[0]).total_seconds() < coverage:
        raise ValueError("incomplete_observed_temporal_coverage")
    ids = [text(e["acquisition_id"]) for e in events]
    if len(set(ids)) != len(ids):
        raise ValueError("replayed_acquisition")
    for event in events:
        text(event["group_id"])
    text(window["source_locator"])
    return events


def bind_window(rows, window, coverage, timestamp_column):
    events = scheduled(window, coverage)
    if len(rows) != len(events) or any(r.get(timestamp_column) != e["timestamp"] for r, e in zip(rows, events)):
        raise ValueError("acquisition_schedule_mismatch")
    return events


def window_record(rows, window, events, columns, timestamp_column, bounds, budget):
    result = moment_evidence(rows, events, columns, bounds, budget)
    result.update(start=window["start"], end=window["end"], source_locator=window["source_locator"],
                  observations=deepcopy(events), selected_observations_hash=digest(
                      [[r[timestamp_column], [float(r[c]) for c in columns]] for r in rows]))
    return result


def reference_quality(rows, columns, timestamp_column):
    """Use existing quality/health calculations on reference data alone."""
    from app.engine.sii_inputs import normalize_rows, build_data_conditions
    from app.services.baseline_analysis import build_baseline_analysis
    from app.services.sensor_health import assess_sensor_health, build_data_confidence
    from app.services.relationship_baselines import _confidence_score
    from app.engine.sii.relationship_graph import _global_quality_factor, _sensor_health_factor
    names = [timestamp_column, *columns]
    profiles = [{"column": c} for c in columns]
    _, matrix = normalize_rows(names, rows)
    baseline = build_baseline_analysis(names, matrix, profiles, reference_rows=matrix)
    quality, timestamps = build_data_conditions(columns=names, matrix_rows=matrix,
        numeric_columns_used=columns, numeric_profiles=profiles, timestamp_column=timestamp_column,
        baseline_analysis=baseline, provided_data_quality=None, config={})
    health = assess_sensor_health(rows, columns, timestamp_column=timestamp_column,
                                 numeric_profiles=profiles, timestamp_profile=timestamps)
    quality["data_confidence"] = build_data_confidence(quality, health)
    sensor, context = _sensor_health_factor(columns, {s["signal"]: s for s in health["signals"]})
    return {"data_quality_factor": _global_quality_factor(quality) * sensor,
            "edge_confidence": _confidence_score(len(rows), len(rows), 0.) * sensor,
            "sensor_health": context, "data_confidence": quality["data_confidence"]}


def qualify_reference(rows, pair, columns, timestamp_column, bounds, pair_budget, coverage):
    plan = pair["reference"]
    events = bind_window(rows, plan, 2 * coverage, timestamp_column)
    epochs = plan["epochs"]
    if len(epochs) < 2 or len({text(e["epoch_id"]) for e in epochs}) != len(epochs):
        raise ValueError("invalid_reference_epochs")
    if any(clock(a["end"]) >= clock(b["start"]) for a, b in zip(epochs, epochs[1:])):
        raise ValueError("overlapping_reference_epochs")
    result = window_record(rows, plan, events, columns, timestamp_column, bounds, pair_budget / 4)
    epoch_results, used = [], set()
    for epoch in epochs:
        indices = [i for i, event in enumerate(events) if event.get("epoch_id") == epoch["epoch_id"]]
        selected = [rows[i] for i in indices]
        epoch_plan = {**epoch, "observations": [events[i] for i in indices], "source_locator": plan["source_locator"]}
        chosen = bind_window(selected, epoch_plan, coverage, timestamp_column)
        assessment = window_record(selected, epoch_plan, chosen, columns, timestamp_column, bounds,
                                   pair_budget / (4 * len(epochs)))
        # The parent reference already retains the acquisitions; no duplicate reference ledger.
        assessment.pop("observations", None)
        epoch_results.append({"epoch_id": epoch["epoch_id"], **assessment})
        used.update(indices)
    if len(used) != len(rows):
        raise ValueError("unassigned_reference_acquisitions")
    result.update(qualification_method="bounded_historical_envelope.v1", epoch_intervals=epoch_results,
                  pooled_correlation_interval=result.get("correlation_interval"),
                  epoch_difference_intervals=[], resolved_incompatibility_witnesses=[],
                  equivalence_established=False, comparison_envelope=None)
    quality = reference_quality(rows, columns, timestamp_column)
    result["quality"] = quality
    if result["status"] != "sufficient" or any(e["status"] != "sufficient" for e in epoch_results):
        result.update(status="limited" if result["status"] != "insufficient" else "insufficient",
                      reason_codes=list(dict.fromkeys(result["reason_codes"] + ["unresolved_reference_epoch"])))
        return result
    intervals = [result["correlation_interval"], *[e["correlation_interval"] for e in epoch_results]]
    result["comparison_envelope"] = [min(i[0] for i in intervals), max(i[1] for i in intervals)]
    result["envelope_hash"] = digest({"selected_observations_hash": result["selected_observations_hash"],
        "pooled_correlation_interval": result["pooled_correlation_interval"], "epoch_intervals": epoch_results,
        "comparison_envelope": result["comparison_envelope"], "implementation_version": IMPLEMENTATION_VERSION})
    result["pooled_interval_width"] = up(intervals[0][1] - intervals[0][0])
    differences = []
    for i, left in enumerate(epoch_results):
        for right in epoch_results[i + 1:]:
            a, b = left["correlation_interval"], right["correlation_interval"]
            differences.append({"epochs": [left["epoch_id"], right["epoch_id"]],
                                "interval": [down(a[0] - b[1]), up(a[1] - b[0])]})
    result["epoch_difference_intervals"] = differences
    result["resolved_incompatibility_witnesses"] = [d for d in differences
        if d["interval"][0] > RESOLUTION or d["interval"][1] < -RESOLUTION]
    result["equivalence_established"] = all(-RESOLUTION <= d["interval"][0]
                                             and d["interval"][1] <= RESOLUTION for d in differences)
    if result["pooled_interval_width"] > RESOLUTION:
        result["reason_codes"].append("inadequate_reference_precision")
    if result["resolved_incompatibility_witnesses"]:
        result["reason_codes"].append("reference_epoch_change_resolved")
    # These are the existing defaults, not new qualification thresholds.
    from app.engine.relationship_change import MINIMUM_DATA_QUALITY, MINIMUM_EDGE_CONFIDENCE
    if quality["data_quality_factor"] < MINIMUM_DATA_QUALITY or quality["edge_confidence"] < MINIMUM_EDGE_CONFIDENCE:
        result["reason_codes"].append("reference_quality_gate")
    result["status"] = "limited" if result["reason_codes"] else "sufficient"
    return result


def estimate(profile, previous, *, columns, baseline_rows, current_rows,
             timestamp_column, units, source):
    """Called only at the actual global/like-mode estimation site."""
    try:
        prior = retained_qualification(previous)
    except ValueError:
        return limited("invalid_qualification_state")
    if profile is None:
        return limited("acquisition_profile_unavailable")
    try:
        if not timestamp_column:
            return limited("timestamps_unavailable", "insufficient")
        if profile["version"] != PROFILE_VERSION:
            raise ValueError("unsupported_acquisition_profile")
        for key in ("assessment_id", "acquisition_profile_id", "independence_basis"):
            text(profile[key])
        if profile["dependence_assumption"] != "independent_groups_conditional_on_context_and_schedule":
            raise ValueError("dependence_assumption_unavailable")
        if profile["schedule_assumption"] != "predeclared_noninformative":
            raise ValueError("acquisition_schedule_assumption_unavailable")
        coverage = float(profile["coverage_period_seconds"])
        if isinstance(profile["coverage_period_seconds"], bool) or not math.isfinite(coverage) or coverage <= 0:
            raise ValueError("invalid_coverage_period")
        profile_hash = digest(profile)
        pairs = profile["pairs"]
        identities = [(tuple(sorted(p["columns"])), text(p["context"]["context_id"])) for p in pairs]
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate_assessment_pair")
        matching = [p for p in pairs if sorted(p["columns"]) == columns
                    and p["context"]["selection"] == source["selection"]]
        if len(matching) != 1:
            raise ValueError("unestablished_context_comparability")
        pair = matching[0]
        text(pair["context"]["basis"])
        bounds = bounds_for(pair, columns, units)
        budget = Fraction(1, 20 * len(pairs))
        identity = {"profile_hash": profile_hash, "reference_observations_hash": source["baseline_observations"],
                    "columns": columns, "units": units, "context": pair["context"], "method": source["method"],
                    "implementation_version": IMPLEMENTATION_VERSION, "numeric_policy": NUMERIC_POLICY}
        reference_id = digest(identity)
        frozen = prior.get("reference")
        if frozen is not None:
            if prior.get("reference_id") != reference_id or prior.get("reference_hash") != digest(frozen):
                return limited("reference_or_profile_changed")
            reference = deepcopy(frozen)  # Detached evidence; never recalculate from comparisons.
        else:
            reference = qualify_reference(baseline_rows, pair, columns, timestamp_column, bounds, budget, coverage)
        windows = pair["comparisons"]
        if not windows or len({text(w["slot_id"]) for w in windows}) != len(windows):
            raise ValueError("invalid_comparison_slots")
        starts = [clock(w["start"]) for w in windows]
        if any(a >= b for a, b in zip(starts, starts[1:])):
            raise ValueError("unordered_comparison_plan")
        matches = [(j, w) for j, w in enumerate(windows, 1)
                   if w["observations"] and current_rows
                   and current_rows[0].get(timestamp_column) == w["observations"][0]["timestamp"]
                   and current_rows[-1].get(timestamp_column) == w["observations"][-1]["timestamp"]]
        if len(matches) != 1:
            raise ValueError("comparison_not_in_assessment_plan")
        ordinal, window = matches[0]
        events = bind_window(current_rows, window, coverage, timestamp_column)
        comparison = window_record(current_rows, window, events, columns, timestamp_column, bounds,
                                   budget / (2 * ordinal * (ordinal + 1)))
        comparison.update(slot_id=window["slot_id"], ordinal=ordinal,
                          plan_slots=[{"slot_id": w["slot_id"], "ordinal": j,
                                       "end": w["end"]} for j, w in enumerate(windows, 1)])
        return {"version": VERSION, "status": comparison["status"], "reason_codes": comparison["reason_codes"],
                "reference_id": reference_id, "reference": reference, "reference_hash": digest(reference),
                "identity": deepcopy(identity), "comparison": comparison,
                "assurance": {"family_budget": "1/20", "pair_count": len(pairs), "pair_budget": str(budget)},
                "profile": {k: profile[k] for k in ("assessment_id", "acquisition_profile_id", "independence_basis",
                    "dependence_assumption", "schedule_assumption", "coverage_period_seconds")},
                "signal_bounds": deepcopy(bounds), "bounds_basis": pair["bounds_basis"]}
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, ZeroDivisionError) as exc:
        return limited(str(exc) if isinstance(exc, ValueError) else "invalid_acquisition_profile")


def reduce_qualification(edge, state, previous, chronological, minimum_confidence, minimum_quality):
    """Separate bounded evidence ledger. Reference and lifetime reuse ledger survive horizon eviction."""
    incoming = edge.get("relationship_qualification") or limited("acquisition_profile_unavailable")
    try:
        saved = deepcopy(retained_qualification(previous))
    except ValueError:
        assessment = limited("invalid_qualification_state")
        state.update(version=2, qualified_evidence={"version": VERSION, "invalid_state": True,
                                                   "reason_codes": assessment["reason_codes"]})
        return {"qualified_persistence_supported": False, "qualification_status": "limited",
                "qualified_persistence": assessment, "reference_qualification_id": None}
    assessment = limited("acquisition_profile_unavailable")
    if "reference" in incoming and chronological:
        if saved and saved.get("reference_id") != incoming["reference_id"]:
            assessment = limited("reference_or_profile_changed")
        else:
            if not saved:
                saved = {k: deepcopy(incoming[k]) for k in ("version", "reference_id", "reference_hash", "reference",
                                                          "identity", "assurance", "profile", "signal_bounds", "bounds_basis")}
                saved.update(slots={}, seen_acquisitions=[], seen_groups=[], observations=[], last_end=None)
            current = incoming["comparison"]
            slot = current["slot_id"]
            fingerprint = digest({"comparison": current, "eligible": edge["eligible"],
                                  "confidence": edge["edge_confidence"], "quality": edge["data_quality_factor"],
                                  "minimum_confidence": minimum_confidence, "minimum_quality": minimum_quality})
            if slot in saved["slots"]:
                assessment = deepcopy(saved["slots"][slot]["assessment"]) if (
                    saved["slots"][slot]["fingerprint"] == fingerprint
                    and slot == saved.get("latest_slot")) else limited("conflicting_or_old_retry")
            else:
                assessment = {"status": "sufficient", "reason_codes": [], "direction": 0}
                ids = {e["acquisition_id"] for e in current["observations"]}
                groups = {e["group_id"] for e in current["observations"]}
                reference_events = saved["reference"].get("observations", [])
                reference_ids = {e["acquisition_id"] for e in reference_events}
                reference_groups = {e["group_id"] for e in reference_events}
                overlap = (clock(current["start"]) <= clock(saved["reference"]["end"])
                           and clock(saved["reference"]["start"]) <= clock(current["end"]))
                overlap = overlap or (saved["last_end"] is not None and clock(current["start"]) <= clock(saved["last_end"]))
                if ids & (reference_ids | set(saved["seen_acquisitions"])) or groups & (reference_groups | set(saved["seen_groups"])) or overlap:
                    assessment = limited("reused_or_overlapping_acquisitions")
                elif incoming["reference_hash"] != saved["reference_hash"]:
                    assessment = limited("reference_changed")
                elif saved["reference"]["status"] != "sufficient":
                    assessment = limited("reference_not_sufficient", saved["reference"]["status"])
                elif current["status"] != "sufficient":
                    assessment = limited("comparison_not_sufficient", current["status"])
                elif (not edge["eligible"] or edge["edge_confidence"] < minimum_confidence
                      or edge["data_quality_factor"] < minimum_quality
                      or saved["reference"]["quality"]["edge_confidence"] < minimum_confidence
                      or saved["reference"]["quality"]["data_quality_factor"] < minimum_quality):
                    assessment = limited("existing_quality_or_eligibility_gate")
                else:
                    ref, comp = saved["reference"]["comparison_envelope"], current["correlation_interval"]
                    delta = [down(comp[0] - ref[1]), up(comp[1] - ref[0])]
                    direction = 1 if delta[0] >= RESOLUTION else -1 if delta[1] <= -RESOLUTION else 0
                    assessment.update(delta_interval=delta, direction=direction)
                saved["seen_acquisitions"] = sorted(set(saved["seen_acquisitions"]) | ids)
                saved["seen_groups"] = sorted(set(saved["seen_groups"]) | groups)
                saved["slots"][slot] = {"fingerprint": fingerprint, "assessment": deepcopy(assessment)}
                saved["latest_slot"] = slot
                if saved["last_end"] is None or clock(current["end"]) > clock(saved["last_end"]):
                    saved["last_end"] = current["end"]
                saved["observations"].append({"slot_id": slot, "ordinal": current["ordinal"],
                    "end": current["end"], "comparison": deepcopy(current), "assessment": deepcopy(assessment),
                    "admission_gates": {"eligible": edge["eligible"], "edge_confidence": edge["edge_confidence"],
                                        "data_quality_factor": edge["data_quality_factor"]}})
            # Include scheduled, missing windows as neutral observations in the bounded horizon.
            plan = current["plan_slots"]
            horizon = [w for w in plan if w["ordinal"] <= current["ordinal"]
                       and 0 <= (clock(current["end"]) - clock(w["end"])).total_seconds()
                       <= TEMPORAL_RULES["maximum_age_days"] * 86400][-TEMPORAL_RULES["maximum_observations"]:]
            actual = {o["slot_id"]: o for o in saved["observations"]}
            saved["observations"] = [actual[w["slot_id"]] for w in horizon if w["slot_id"] in actual]
            def admitted_vote(observation):
                gates = observation.get("admission_gates", {})
                if (gates.get("eligible") is not True
                        or gates.get("edge_confidence", -1) < minimum_confidence
                        or gates.get("data_quality_factor", -1) < minimum_quality
                        or observation["assessment"]["status"] != "sufficient"):
                    return 0
                return observation["assessment"].get("direction", 0)
            # Recheck the same historical observations against the current gates,
            # as the directional reducer does. Old state without gate provenance
            # cannot supply qualified votes. Intersecting two unrelated vote
            # counts is not proof that six windows satisfy both requirements.
            votes = [admitted_vote(actual[w["slot_id"]]) if w["slot_id"] in actual else 0 for w in horizon]
            direction = 1 if votes.count(1) > votes.count(-1) else -1 if votes.count(-1) > votes.count(1) else 0
            count = votes.count(direction) if direction else 0
            agreement = count / max(1, len(votes))
            supported = (count >= TEMPORAL_RULES["minimum_supporting_observations"]
                         and agreement >= TEMPORAL_RULES["minimum_direction_agreement"] and assessment.get("direction", 0) == direction
                         and assessment["status"] == "sufficient")
            assessment.update(supported=supported, supporting_observations=count,
                              observations=len(votes), direction_agreement=agreement)
    else:
        assessment = limited("invalid_chronology") if not chronological else deepcopy(incoming)
    state["qualified_evidence"] = saved
    state["version"] = 2
    return {"qualified_persistence_supported": bool(assessment.get("supported", False)),
            "qualification_status": assessment["status"], "qualified_persistence": assessment,
            "reference_qualification_id": saved.get("reference_id")}
