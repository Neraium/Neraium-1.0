"""Numerical comparisons to the unchanged pre-implementation source revision."""
import subprocess
from types import ModuleType
from pathlib import Path

from app.services.relationship_baselines import build_relationship_baseline
from app.engine.relationship_change import relationship_temporal_evidence
from test_relationship_qualification import rows, COLS, UNITS
from test_relationship_temporal_persistence import edge

ROOT = Path(__file__).resolve().parents[1]


def original(path):
    source = subprocess.check_output(["git", "show", "HEAD:" + path], cwd=ROOT, text=True)
    module = ModuleType("qualification_prechange_numerical_audit")
    exec(compile(source, path, "exec"), module.__dict__)
    return module


def without_qualification(value):
    if isinstance(value, dict):
        return {k: without_qualification(v) for k, v in value.items() if k != "relationship_qualification"}
    if isinstance(value, list): return [without_qualification(v) for v in value]
    return value


def test_reference_relationship_estimates_and_scores_equal_original():
    old = original("backend/app/services/relationship_baselines.py")
    for kind in ("same", "independent", "opposite"):
        reference, comparison = rows(0, n=128), rows(1, kind, n=128)
        kwargs = dict(timestamp_column="timestamp", reference_rows=reference, binding_signal_units=UNITS)
        before = old.build_relationship_baseline(comparison, COLS, **kwargs)
        after = build_relationship_baseline(comparison, COLS, **kwargs)
        assert without_qualification(after) == before


def test_entire_directional_reducer_remains_numerically_identical():
    old = original("backend/app/engine/relationship_change.py")
    for displacements in ([0.] * 12, [-.22] * 12, [-.22, .22] * 6,
                          [-.22] * 3 + [0.] * 9, [-.22] * 6 + [0.] * 6):
        previous = current = None
        for day, delta in enumerate(displacements, 1):
            raw = edge(day, delta)
            raw.update(eligible=True, edge_confidence=.8, data_quality_factor=1,
                       signed_correlation_delta=delta)
            before, previous = old.relationship_temporal_evidence(raw, previous, basis="global_relationship_model")
            after, current = relationship_temporal_evidence(raw, current, basis="global_relationship_model")
            for key, value in before.items():
                if key in ("temporal_persistence_supported", "persistent_relationship_change"):
                    assert after["directional_persistence_supported"] == value
                elif key == "temporal_persistence_status":
                    assert after["directional_persistence_status"] == value
                else:
                    assert after[key] == value
            assert current["observations"] == previous["observations"]
