import pandas as pd

from app.services.telemetry_normalization import (
    IntegrityLayer,
    NormalizationLayer,
    NormalizationPipeline,
    SENTINEL,
    build_normalization_report,
)


def test_integrity_classifies_short_drop_as_filled():
    signal = pd.Series(
        [1.0, None, 1.2, 1.3, 1.4],
        name="flow",
        index=pd.date_range("2026-01-01", periods=5, freq="60s"),
    )

    profile = IntegrityLayer(sample_interval_seconds=60).classify(
        signal,
        "SCADA-01",
        signal.index.min(),
        signal.index.max(),
    )

    assert profile.gap_type == "short_drop"
    assert profile.treatment == "filled"
    assert profile.completeness == 0.8
    assert profile.suppress_confidence is False


def test_normalizer_preserves_integrity_flag_for_short_drop():
    signal = pd.Series([10.0, None, 10.2], name="pressure")
    profile = IntegrityLayer().classify(signal, "BAS-01", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-01 00:03:00"))

    normalized, fill_method, integrity_flag = NormalizationLayer().normalize(signal, profile)

    assert normalized.isna().sum() == 0
    assert fill_method in {"linear", "forward_fill"}
    assert integrity_flag == "degraded"


def test_pipeline_keeps_single_dead_sensor_as_terminal_not_source_outage():
    raw = pd.DataFrame(
        {
            "flow": [None, None, None],
            "pressure": [1.0, 1.1, 1.2],
        },
        index=pd.date_range("2026-01-01", periods=3, freq="60s"),
    )

    result = NormalizationPipeline("SCADA-01", sample_interval_seconds=60).run(raw, raw.index.min(), raw.index.max())

    assert result["integrity_profiles"]["flow"].gap_type == "terminal"
    assert result["correlated_signals"] == []
    assert result["integrity_flags"]["flow"] == "missing"
    assert result["window_suppressed"] is True


def test_pipeline_marks_overlapping_multi_signal_gap_as_correlated():
    raw = pd.DataFrame(
        {
            "flow": [100.0, None, None, None, 105.0],
            "pressure": [20.0, None, None, None, 21.0],
            "temperature": [70.0, 70.2, 70.3, 70.4, 70.5],
        },
        index=pd.date_range("2026-01-01", periods=5, freq="60s"),
    )

    result = NormalizationPipeline("SCADA-01", sample_interval_seconds=60).run(raw, raw.index.min(), raw.index.max())

    assert result["correlated_signals"] == ["flow", "pressure"]
    assert result["integrity_profiles"]["flow"].gap_type == "correlated"
    assert result["integrity_profiles"]["pressure"].gap_type == "correlated"
    assert result["integrity_profiles"]["temperature"].gap_type is None
    assert result["integrity_flags"]["flow"] == "missing"
    assert result["normalized"]["flow"].iloc[1] == SENTINEL


def test_build_normalization_report_exposes_sii_integrity_context():
    rows = [
        {"time": "2026-01-01T00:00:00", "flow": 100.0, "pressure": 20.0},
        {"time": "2026-01-01T00:01:00", "flow": None, "pressure": 21.0},
        {"time": "2026-01-01T00:02:00", "flow": 102.0, "pressure": 22.0},
    ]

    report = build_normalization_report(
        rows=rows,
        numeric_columns=["flow", "pressure"],
        timestamp_column="time",
        source_id="SCADA-01",
    )

    assert report["enabled"] is True
    assert report["status"] in {"good", "degraded"}
    assert report["fill_methods"]["flow"] in {"linear", "forward_fill"}
    assert report["integrity_flags"]["flow"] == "degraded"
    assert report["signal_integrity"]
