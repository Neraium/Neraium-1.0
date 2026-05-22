from app.engine.temporal_math import evaluate_temporal_math


def test_temporal_math_engine_emits_instability_index_and_decision_state() -> None:
    columns = ["timestamp", "flow", "pressure", "power"]
    rows = []
    for i in range(120):
        if i < 70:
            flow = 100.0 + (i % 3) * 0.2
            pressure = 40.0 + (i % 4) * 0.15
            power = 20.0 + (i % 5) * 0.1
        else:
            step = i - 70
            flow = 100.0 - (step * 0.35)
            pressure = 40.0 + (step * 0.4)
            power = 20.0 + (step * 0.3)
        rows.append([f"2026-01-01T00:{i:02d}:00Z", f"{flow:.3f}", f"{pressure:.3f}", f"{power:.3f}"])

    numeric_profiles = [
        {"column": "flow"},
        {"column": "pressure"},
        {"column": "power"},
    ]

    result = evaluate_temporal_math(
        columns=columns,
        rows=rows,
        numeric_profiles=numeric_profiles,
        timestamp_column="timestamp",
    )

    instability = result["instability_index"]
    assert 0.0 <= instability["score"] <= 1.0
    assert "state_drift" in instability["components"]
    assert "relationship_drift" in instability["components"]
    assert "entropy_growth" in instability["components"]
    assert "variance_growth" in instability["components"]
    assert "acceleration" in instability["components"]
    assert "causal_evidence" in instability["components"]
    assert "topology_propagation" in instability["components"]
    assert result["decision_thresholding"]["state"] in {"Normal", "Watch", "Investigate", "Act", "Critical"}
    assert "lead_time_estimate" in result
