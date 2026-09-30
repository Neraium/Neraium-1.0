"""Independent bounded acquisition model; no benchmark data or outcomes.

X is Bernoulli(1/2); Y = X xor Bernoulli((1-rho)/2). Thus both signals
are physically bounded by [0,1] and population Pearson correlation is rho.
PRNG streams are domain-separated by acquisition window. A group repeats one
joint draw when testing dependence; fresh IDs do not imply fresh groups.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math
import random

from app.engine import relationship_qualification as q
from app.engine.relationship_change import relationship_change_type
from app.engine.sii.relationship_graph import analyze_relationship_graph
from app.services.relationship_baselines import _pearson_corr
from app.services.relationship_evidence_binding import SOURCE, source_evidence

COLS = ["bounded_a", "bounded_b"]
SEED_DOMAIN = "independent-qualification-battery/v1"


def measurements(day, rho, n=12000, *, columns=COLS, block=1, irregular=False):
    rng = random.Random(sha256(f"{SEED_DOMAIN}/{day}/{rho}/{n}".encode()).digest())
    origin = datetime(2027, 3, 1, tzinfo=timezone.utc) + timedelta(days=day)
    elapsed, step = 0, max(1, math.ceil(3600 / (n - 1)))
    data = []
    for i in range(n):
        if i % block == 0:
            x = int(rng.random() < .5)
            y = x ^ int(rng.random() < (1-rho)/2)
        data.append({"timestamp": (origin + timedelta(seconds=elapsed)).isoformat(), columns[0]: x, columns[1]: y})
        elapsed += step + (i % 3 if irregular else 0)
    return data


def window(data, day, *, reference=False, block=1):
    events = [{"timestamp": row["timestamp"], "acquisition_id": f"{day:x}.{i:x}",
               "group_id": f"{day:x}.{i//block:x}",
               **({"epoch_id": "first" if i < len(data)//2 else "second"} if reference else {})}
              for i, row in enumerate(data)]
    plan = {"start": data[0]["timestamp"], "end": data[-1]["timestamp"],
            "source_locator": f"qualification-fixture:{day}", "observations": events}
    if reference:
        mid = len(data)//2
        plan["epochs"] = [{"epoch_id": key, "start": data[a]["timestamp"], "end": data[b]["timestamp"]}
                          for key, a, b in (("first", 0, mid-1), ("second", mid, len(data)-1))]
    else:
        plan["slot_id"] = f"slot-{day}"
    return plan


def case(name, rhos, *, reference_rho=1., reference_n=12000, comparison_n=12000,
         block=1, irregular=False, columns=COLS):
    reference = measurements(0, reference_rho, reference_n, columns=columns, block=block, irregular=irregular)
    comparisons = [measurements(day, rho, comparison_n, columns=columns, block=block, irregular=irregular)
                   for day, rho in enumerate(rhos, 1)]
    units = {c: "unit" for c in columns}
    profile = {"version": q.PROFILE_VERSION, "assessment_id": name, "acquisition_profile_id": SEED_DOMAIN,
               "independence_basis": "independent Bernoulli pair draws across declared groups",
               "dependence_assumption": "independent_groups_conditional_on_context_and_schedule",
               "schedule_assumption": "predeclared_noninformative", "coverage_period_seconds": 1200,
               "pairs": [{"columns": list(columns), "signal_units": units,
                          "signal_bounds": {c: [0, 1] for c in columns}, "bounds_basis": "binary instrument domain",
                          "context": {"context_id": "fixed-context", "basis": "same declared acquisition mechanism", "selection": {}},
                          "reference": window(reference, 0, reference=True, block=block),
                          "comparisons": [window(rows, day, block=block) for day, rows in enumerate(comparisons, 1)]}]}
    return reference, comparisons, profile


def step(reference, comparison, profile, state=None, *, columns=COLS, confidence=.9, config=None):
    units = {c: "unit" for c in columns}
    corr = lambda rows: _pearson_corr([r[columns[0]] for r in rows], [r[columns[1]] for r in rows]) or 0.
    baseline, current = round(corr(reference), 6), round(corr(comparison), 6)
    raw = {"columns": list(columns), "baseline_correlation": baseline, "recent_correlation": current,
           "change_type": relationship_change_type(baseline, current),
           "confidence": confidence, "baseline_sample_count": len(reference), "current_sample_count": len(comparison),
           "signal_units": units, "relationship_context": {"operator_primary_eligible": True},
           "time_window": {"baseline_start": reference[0]["timestamp"], "baseline_end": reference[-1]["timestamp"],
                           "current_start": comparison[0]["timestamp"], "current_end": comparison[-1]["timestamp"]}}
    raw[SOURCE] = source_evidence(raw, columns=columns, baseline_rows=reference, current_rows=comparison,
                                 timestamp_column="timestamp", units=units)
    key = json.dumps(sorted(columns), separators=(",", ":"))
    raw["relationship_qualification"] = q.estimate(profile, (state or {}).get(key), columns=sorted(columns),
        baseline_rows=reference, current_rows=comparison, timestamp_column="timestamp", units=units, source=raw[SOURCE])
    graph = analyze_relationship_graph(relationship_model={"relationship_graph": {"edges": [raw]}},
        relationship_persistence_state=state, sensor_health={"signals": [{"signal": c, "health": "healthy"} for c in columns]},
        data_quality={"data_confidence": {"rating": "high"}}, config=config)
    return graph["edges"][0], graph["relationship_persistence_state"], raw, graph


def run(spec, *, columns=COLS):
    reference, comparisons, profile = spec
    state, summaries, frozen = None, [], None
    for comparison in comparisons:
        edge, state, raw, graph = step(reference, comparison, profile, state, columns=columns)
        evidence = next(iter(state.values()))["qualified_evidence"]
        if evidence:
            anchor = evidence["reference"]
            if frozen is None: frozen = deepcopy(anchor)
            assert anchor == frozen, "comparison changed the historical envelope"
            delta = edge["qualified_persistence"].get("delta_interval")
            if delta:
                comp = evidence["observations"][-1]["comparison"]["correlation_interval"]
                envelope = anchor["comparison_envelope"]
                assert delta == [q.down(comp[0]-envelope[1]), q.up(comp[1]-envelope[0])]
        summaries.append({k: deepcopy(edge[k]) for k in ("directional_persistence_supported", "qualified_persistence_supported",
                          "qualification_status", "qualified_persistence", "persistence_factor", "promoted_changed_edge")})
    return summaries, state, raw, graph
