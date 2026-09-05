from __future__ import annotations

import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.engine.sii.expected_behavior import evaluate_expected_behavior
from app.engine.sii.expected_rate_evidence import expected_rate_observations
from app.main import create_app
from app.services.analysis_result_contract import build_analysis_result
from app.services.measurable_consequence import build_measurable_consequence


def fixture():
    finding = {
        "id": "finding-1",
        "headline": "Water response changed",
        "support_level": "high",
        "operating_mode": {"match": "strong"},
        "evidence_id": "evidence-1",
        "persistence": {"status": "persistent"},
        "source_relationship_ids": ["rel-1"],
        "source_tags": ["flow", "load"],
        "source_time_ranges": [{"current_start": 0, "current_end": 21600}],
    }
    expected = {
        "expected_values": [
            {
                "status": "complete",
                "target_signal": "flow",
                "predictor_signals": ["load"],
                "source_relationships": ["rel-1"],
                "source_model_version": "model-v3",
                "max_gap_seconds": 3600,
                "limitations": ["Expected rates use the validated reference model."],
                "observations": [
                    {
                        "timestamp": i * 3600,
                        "observed": 135.66666666666666,
                        "expected": 100,
                    }
                    for i in range(7)
                ],
            }
        ],
    }
    catalog = {"flow": {"resource_type": "water", "canonical_unit": "gpm"}}
    return finding, expected, catalog


def run(finding, expected, catalog):
    return build_measurable_consequence(
        finding,
        expected_behavior=expected,
        signal_catalog=catalog,
        analysis_run_id="run-1",
    )


def test_quantified_and_provenance():
    finding, expected, catalog = fixture()
    result = run(finding, expected, catalog)
    assert result["cumulative_amount"] == pytest.approx(12840)
    assert result["duration_seconds"] == 21600
    assert result["finding_id"] == "finding-1"
    assert result["evidence_id"] == "evidence-1"
    assert result["analysis_run_id"] == "run-1"
    assert result["source_relationship_ids"] == ["rel-1"]
    assert result["source_tag_ids"] == ["flow", "load"]
    assert result["provenance"]["expected_behavior"] == expected["expected_values"][0]
    assert result == run(finding, expected, catalog)
    assert json.loads(json.dumps(result, allow_nan=False)) == result


@pytest.mark.parametrize(
    "case",
    [
        "persistence",
        "window",
        "sibling",
        "unit",
        "resource",
        "ambiguous",
        "summary_only",
        "disjoint",
    ],
)
def test_unsupported_evidence_refuses_number(case):
    finding, expected, catalog = fixture()
    if case == "persistence":
        finding["persistence"] = {"status": "not_established"}
    elif case == "window":
        finding["source_time_ranges"] = []
    elif case == "sibling":
        finding["source_relationship_ids"] = ["other-relationship"]
    elif case == "unit":
        catalog["flow"]["canonical_unit"] = "m3/s"
    elif case == "resource":
        catalog["flow"].pop("resource_type")
    elif case == "ambiguous":
        expected["expected_values"] *= 2
    elif case == "summary_only":
        expected["expected_values"][0].pop("observations")
    elif case == "disjoint":
        finding["source_time_ranges"] *= 2
    result = run(finding, expected, catalog)
    assert result["status"] == "not_quantifiable"
    assert "cumulative_amount" not in result
    assert result["finding_id"] == "finding-1"


def test_exact_window_excludes_external_points_without_mutation():
    finding, expected, catalog = fixture()
    finding["source_time_ranges"] = [{"current_start": 3600, "current_end": 7200}]
    original = deepcopy(expected)
    result = run(finding, expected, catalog)
    assert result["duration_seconds"] == 3600
    assert result["cumulative_amount"] == pytest.approx(2140)
    assert expected == original


def test_quality_barrier_is_retained():
    finding, expected, catalog = fixture()
    expected["expected_values"][0]["observations"][3]["valid"] = False
    result = run(finding, expected, catalog)
    assert result["duration_seconds"] == 14400
    assert result["skipped_interval_count"] == 2


def test_existing_expected_model_emits_aligned_evidence():
    model = {
        "model_id": "model-1",
        "target_signal": "flow",
        "predictor_signals": ["load"],
        "operating_mode": "running",
        "validation": {"passed": True},
        "sample_support": 80,
        "model_parameters": {"intercept": 5, "slope": 2, "lag_samples": 0},
        "source_relationships": ["rel-1"],
    }
    rows = [{"t": i * 60, "load": 10 + i, "flow": 35 + 2 * i} for i in range(10)]
    result = evaluate_expected_behavior(
        active_model={"expected_behavior_models": {"model-1": model}},
        rows=rows,
        operating_mode="running",
        data_quality={"readiness": "ready"},
        sensor_health={
            "signals": [
                {"signal": signal, "health": "healthy"} for signal in ("flow", "load")
            ]
        },
        source_model_version="3",
        evaluation_time="2026-09-05T00:00:00Z",
        timestamp_column="t",
    )
    series = result["expected_values"][0]["observations"]
    assert [item["timestamp"] for item in series] == [row["t"] for row in rows]
    assert [item["expected"] for item in series] == [25 + 2 * i for i in range(10)]
    finding, _, catalog = fixture()
    finding["source_time_ranges"] = [{"current_start": 0, "current_end": 540}]
    assert run(finding, result, catalog)["cumulative_amount"] == 90


def test_aligned_evidence_never_drops_missing_predictor_or_uses_sample_lag():
    rows = [{"t": 0, "x": 1, "y": 5}, {"t": 60, "y": 6}, {"t": 120, "x": 2, "y": 7}]
    kwargs = dict(predictor="x", target="y", timestamp_column="t")
    series = expected_rate_observations(
        rows, parameters={"slope": 2, "intercept": 0}, **kwargs
    )
    assert len(series) == 3
    assert series[1]["valid"] is False
    assert (
        expected_rate_observations(rows, parameters={"lag_samples": 1}, **kwargs) == []
    )


def test_canonical_analysis_attaches_exact_finding_owned_consequence():
    finding, expected, catalog = fixture()
    source = {
        "analysis_id": "analysis-1",
        "run_id": "run-1",
        "completed_at": "2026-09-05T00:00:00Z",
        "conditions": [finding],
        "analysis_explanation": {"insights": []},
        "sii_result": {"expected_behavior": expected},
        "telemetry_signal_catalog": catalog,
    }
    result = build_analysis_result(source)
    consequence = result["conditions"][0]["measurable_consequence"]
    assert consequence == run(finding, expected, catalog)
    assert (
        json.loads(json.dumps(result, allow_nan=False))["conditions"][0][
            "measurable_consequence"
        ]
        == consequence
    )


def test_findings_api_uses_package_and_preserves_insufficient_state():
    with TestClient(create_app()) as client:
        profiles = client.get("/api/findings/consequence/profiles")
        assert profiles.status_code == 200
        assert "steam_lb_per_hr" in profiles.json()["profiles"]
        for observations in (
            [],
            [{"timestamp": 0, "observed": 1, "expected": 0}],
            [{"timestamp": "bad"}],
        ):
            response = client.post(
                "/api/findings/consequence/quantify",
                json={
                    "profile_key": "water_gpm",
                    "observations": observations,
                    "finding_id": "f",
                    "evidence_id": "e",
                },
            )
            assert response.status_code == 200
            assert response.json()["status"] == "not_quantifiable"
            assert response.json()["finding_id"] == "f"
        response = client.post(
            "/api/findings/consequence/quantify",
            json={
                "profile_key": "water_gpm",
                "observations": fixture()[1]["expected_values"][0]["observations"],
            },
        )
        assert response.status_code == 200
        assert response.json()["cumulative_amount"] == pytest.approx(12840)


def test_api_preserves_original_values_and_gates_boolean_rates():
    observations = [
        {
            "timestamp": "1970-01-01T01:00:00+01:00",
            "observed": True,
            "expected": "20.0",
            "source_row": 7,
        },
        {"timestamp": 60, "observed": 30, "expected": 20},
    ]
    with TestClient(create_app()) as client:
        result = client.post(
            "/api/findings/consequence/quantify",
            json={
                "profile_key": "water_gpm",
                "observations": observations,
            },
        ).json()
    assert result["status"] == "not_quantifiable"
    assert result["provenance"]["observations"] == observations


@pytest.mark.parametrize(
    "bad", [{"source_relationships": ["rel-1", 42]}, {"target_signal": []}]
)
def test_malformed_model_identity_cannot_pass_ownership_gate(bad):
    finding, expected, catalog = fixture()
    expected["expected_values"][0].update(bad)
    assert run(finding, expected, catalog)["status"] == "not_quantifiable"


@pytest.mark.parametrize("context", [{}, {"match": "weak"}, {"match": "partial"}])
def test_missing_or_incomparable_operating_context_withholds_number(context):
    finding, expected, catalog = fixture()
    finding["operating_mode"] = context
    result = run(finding, expected, catalog)
    assert result["status"] == "not_quantifiable"
    assert "operating context" in result["reason"]
