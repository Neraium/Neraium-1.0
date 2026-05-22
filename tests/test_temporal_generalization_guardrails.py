from app.engine.temporal_math import TemporalMathConfig, evaluate_temporal_math


def _build_rows(col_a: str, col_b: str, col_c: str) -> tuple[list[str], list[list[str]], list[dict[str, str]]]:
    columns = ["timestamp", col_a, col_b, col_c]
    rows: list[list[str]] = []
    for i in range(180):
        if i < 120:
            a = 80.0 + (i % 4) * 0.1
            b = 35.0 + (i % 3) * 0.1
            c = 22.0 + (i % 5) * 0.1
        else:
            step = i - 120
            a = 80.0 - (step * 0.2)
            b = 35.0 + (step * 0.25)
            c = 22.0 + (step * 0.18)
        rows.append([f"2026-01-01T00:{i%60:02d}:00Z", f"{a:.4f}", f"{b:.4f}", f"{c:.4f}"])
    profiles = [{"column": col_a}, {"column": col_b}, {"column": col_c}]
    return columns, rows, profiles


def test_generalization_column_name_invariant() -> None:
    cols1, rows1, prof1 = _build_rows("flow", "pressure", "power")
    cols2, rows2, prof2 = _build_rows("x1", "x2", "x3")
    result1 = evaluate_temporal_math(columns=cols1, rows=rows1, numeric_profiles=prof1, timestamp_column="timestamp")
    result2 = evaluate_temporal_math(columns=cols2, rows=rows2, numeric_profiles=prof2, timestamp_column="timestamp")
    assert result1["decision_thresholding"]["state"] == result2["decision_thresholding"]["state"]
    assert abs(result1["instability_index"]["score"] - result2["instability_index"]["score"]) < 1e-9


def test_escalation_requires_multiple_indicators() -> None:
    columns = ["timestamp", "v1"]
    rows = [[f"2026-01-01T00:{i%60:02d}:00Z", f"{10 + i * 0.3:.3f}"] for i in range(160)]
    profiles = [{"column": "v1"}]
    result = evaluate_temporal_math(columns=columns, rows=rows, numeric_profiles=profiles, timestamp_column="timestamp")
    assert result["decision_thresholding"]["state"] in {"Normal", "Watch"}
    assert result["evidence_accumulation"]["persistence_score"] >= 0.0


def test_default_config_is_fixed_and_transparent() -> None:
    cfg = TemporalMathConfig()
    assert cfg.baseline_fraction == 0.35
    assert cfg.min_baseline_rows == 12
    assert cfg.max_rows == 5000
    assert cfg.max_lag == 8
    assert cfg.evidence_trigger == 0.15


def test_uncertainty_reported_for_weak_or_conflicting_signals() -> None:
    columns = ["timestamp", "x", "y", "z"]
    rows = []
    for i in range(90):
        x = 10 + (i % 2) * 0.1
        y = 10 + ((i * 7) % 5) * 0.2
        z = 10 + ((i * 11) % 7) * 0.25
        rows.append([f"2026-01-02T00:{i%60:02d}:00Z", f"{x:.3f}", f"{y:.3f}", f"{z:.3f}"])
    profiles = [{"column": "x"}, {"column": "y"}, {"column": "z"}]
    result = evaluate_temporal_math(columns=columns, rows=rows, numeric_profiles=profiles, timestamp_column="timestamp")
    uncertainty = result["uncertainty_summary"]
    assert "explicit_uncertainty" in uncertainty
    assert "weak_signals" in uncertainty
    assert "conflicting_signals" in uncertainty
