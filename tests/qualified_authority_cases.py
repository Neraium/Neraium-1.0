"""Real qualified producer fixtures for ownership/authority unit tests.

This replaces the old assumption that an eight-window point-delta history alone
is qualified. The last-only variant supplies a real one-observation contrast
against the identical source. No qualification flag or reducer result is fabricated.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from app.services.relationship_evidence_binding import finalize
from qualification_battery_cases import case, run, window


@lru_cache(maxsize=6)
def qualified_product(columns=("flow", "load"), scope="authority-test", history=6, epoch_end=False, last_only=False):
    spec = case("qualified-authority-fixture", [-1.] * history, columns=columns)
    reference, comparisons, profile = spec
    if epoch_end:
        for day, data in enumerate([reference, *comparisons]):
            for i, row in enumerate(data):
                row["timestamp"] = (datetime(1970, 1, 1, tzinfo=timezone.utc)
                    + timedelta(days=day-history, seconds=21600*i/(len(data)-1))).isoformat()
        profile["pairs"][0]["reference"] = window(reference, 0, reference=True)
        profile["pairs"][0]["comparisons"] = [window(data, day) for day, data in enumerate(comparisons, 1)]
    # A one-observation assessment of the SAME final source is useful for
    # ambiguity/anti-borrowing tests. Keep its declared schedule and source;
    # simply do not supply previous observations to the actual reducer.
    observed = (reference, comparisons[-1:], profile) if last_only else spec
    summaries, _, raw, graph = run(observed, columns=columns)
    assert summaries[-1]["qualified_persistence_supported"] is (not last_only)
    raw.pop("relationship_qualification", None)
    # Match the producer boundary: raw estimates enter finalize; assessed graph
    # evidence supplies temporal authority. Copying assessed flags into the raw
    # model would incorrectly retain temporal claims in graph-failure fallback.
    model = {"relationship_graph": {"edges": [raw]}, "top_relationship_changes": [deepcopy(raw)]}
    registry = finalize(model, graph, scope=scope)
    entry = model["top_relationship_changes"][0]
    entry.update(change_type=graph["edges"][0]["change_type"],
                 correlation_delta=graph["edges"][0]["correlation_delta"],
                 baseline_sample_size=len(reference), recent_sample_size=len(comparisons[-1]), confidence_score=.9,
                 data_confidence={"rating": "high"}, operating_mode={"match": "strong", "confidence": "high"})
    return entry, registry, graph
