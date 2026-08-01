from __future__ import annotations

import io

import numpy as np
import pandas as pd


def _tower_datasets(rows: int = 480) -> tuple[bytes, bytes]:
    index = np.arange(rows)
    random = np.random.default_rng(42)
    demand = 52 + 24 * np.sin(index / 18)
    baseline = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq="15min", tz="UTC"),
            "pump_demand_kw": demand,
            "flow_gpm": 2.1 * demand + random.normal(0, 1.0, rows),
            "header_pressure_psi": 0.72 * demand + random.normal(0, 0.5, rows),
            "operator_note": ["normal"] * rows,
        }
    )
    changed = index >= 120
    comparison = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-02-01", periods=rows, freq="15min", tz="UTC"),
            "pump_demand_kw": demand,
            "flow_gpm": np.where(
                changed,
                135 - 0.35 * demand + random.normal(0, 7, rows),
                2.1 * demand + random.normal(0, 1.0, rows),
            ),
            "header_pressure_psi": np.where(
                changed,
                43 - 0.12 * demand + random.normal(0, 3, rows),
                0.72 * demand + random.normal(0, 0.5, rows),
            ),
            "operator_note": ["comparison"] * rows,
        }
    )
    return baseline.to_csv(index=False).encode(), comparison.to_csv(index=False).encode()


def _intake(client, baseline: bytes, comparison: bytes) -> dict:
    response = client.post(
        "/api/pilot-assessments/intake",
        files={
            "baseline_file": ("tower-baseline.csv", io.BytesIO(baseline), "text/csv"),
            "comparison_file": ("tower-comparison.csv", io.BytesIO(comparison), "text/csv"),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_full_blinded_historical_assessment_workflow(client) -> None:
    baseline, comparison = _tower_datasets()
    intake = _intake(client, baseline, comparison)
    assessment_id = intake["assessment_id"]

    assert intake["event_backtest"] is None
    assert intake["schemas"]["baseline"]["inferred_timestamp_column"] == "timestamp"
    unusable = {item["column"] for item in intake["schemas"]["baseline"]["unusable_columns"]}
    assert "operator_note" in unusable

    mapping = intake["mapping"]
    for signal in mapping["signals"]:
        signal["system_name"] = "Chilled-water distribution loop"
    mapped = client.put(f"/api/pilot-assessments/{assessment_id}/mapping", json=mapping)
    assert mapped.status_code == 200
    assert mapped.json()["mapping_validation"]["ready"] is True

    # The API enforces the blinded sequence rather than relying on UI order.
    premature_event = client.post(
        f"/api/pilot-assessments/{assessment_id}/event",
        json={"event_label": "Tower outage", "event_timestamp": "2026-02-04T00:00:00+00:00"},
    )
    assert premature_event.status_code == 409

    analyzed = client.post(f"/api/pilot-assessments/{assessment_id}/analyze")
    assert analyzed.status_code == 200, analyzed.text
    result = analyzed.json()
    assert result["status"] == "analysis_complete"
    assert result["analysis"]["event_timestamp_used"] is False
    assert result["quality_gate"]["passed"] is True
    assert result["analysis"]["finding_count"] >= 1
    finding = result["analysis"]["findings"][0]
    assert finding["title"] == "Pump demand no longer matches expected flow response"
    assert finding["operational_summary"] == (
        "The system required a different level of pump demand to produce the hydraulic response "
        "learned during the baseline period."
    )
    assert finding["evidence_count"] == len(finding["relationships"])
    evidence = finding["relationships"][0]
    assert evidence["before_behavior"]["records"] > 0
    assert evidence["after_behavior"]["records"] > 0
    assert evidence["magnitude"]["absolute_correlation_change"] >= 0.25
    assert evidence["persistence"]["supporting_windows"] >= 2
    assert evidence["start_time"]
    assert evidence["exact_records"]["record_count"] > 0
    assert len(evidence["exact_records"]["sha256"]) == 64

    records = client.get(evidence["exact_records"]["download_url"])
    assert records.status_code == 200
    assert "period,source_row,timestamp,operating_mode" in records.text
    assert "baseline" in records.text
    assert "comparison" in records.text

    revealed = client.post(
        f"/api/pilot-assessments/{assessment_id}/event",
        json={
            "event_label": "Tower outage work order",
            "event_timestamp": "2026-02-04T00:00:00+00:00",
            "repair_timestamp": "2026-02-05T00:00:00+00:00",
        },
    )
    assert revealed.status_code == 200, revealed.text
    backtest = revealed.json()["event_backtest"]
    assert backtest["analysis_was_blinded"] is True
    assert backtest["findings"][0]["surfaced_before_event"] is True
    assert backtest["findings"][0]["lead_time_hours"] > 0

    first_feedback = client.post(
        f"/api/pilot-assessments/{assessment_id}/feedback",
        json={"category": "useful", "note": "Matches the operator's hydraulic concern.", "finding_id": finding["finding_id"]},
    )
    second_feedback = client.post(
        f"/api/pilot-assessments/{assessment_id}/feedback",
        json={"category": "needs_investigation", "note": "Check pump staging records.", "finding_id": finding["finding_id"]},
    )
    assert first_feedback.status_code == 201
    assert second_feedback.status_code == 201
    history = second_feedback.json()["feedback_history"]
    assert [item["category"] for item in history] == ["useful", "needs_investigation"]
    assert all(item["feedback_id"] and item["recorded_at"] and item["recorded_by"] for item in history)

    report = client.get(f"/api/pilot-assessments/{assessment_id}/report.html")
    assert report.status_code == 200
    section_titles = [
        "Finding",
        "What changed",
        "Detection timeline",
        "Why this finding is credible",
        "Supporting relationship evidence",
        "Before-and-after repair comparison",
        "Data quality notes",
        "Methodology and limitations",
    ]
    assert [report.text.index(f"<h2>{title}</h2>") for title in section_titles] == sorted(
        report.text.index(f"<h2>{title}</h2>") for title in section_titles
    )
    assert finding["title"] in report.text
    assert finding["operational_summary"] in report.text
    assert "Median behavioral deviation" in report.text
    assert "Neraium identifies persistent changes in learned operating relationships." in report.text
    assert "It does not independently diagnose equipment failure or replace engineering judgment." in report.text
    assert "Engineer feedback (append-only)" in report.text
    assert evidence["exact_records"]["sha256"] in report.text


def test_poor_baseline_is_withheld_with_exact_reasons(client) -> None:
    rows = 60
    baseline = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq="5min", tz="UTC"),
            "pump_power_kw": np.ones(rows) * 50,
            "flow_gpm": np.linspace(100, 120, rows),
        }
    )
    comparison = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-02-01", periods=rows, freq="5min", tz="UTC"),
            "pump_power_kw": np.ones(rows) * 51,
            "flow_gpm": np.linspace(95, 140, rows),
        }
    )
    intake = _intake(client, baseline.to_csv(index=False).encode(), comparison.to_csv(index=False).encode())
    assessment_id = intake["assessment_id"]
    mapped = client.put(f"/api/pilot-assessments/{assessment_id}/mapping", json=intake["mapping"])
    assert mapped.status_code == 200
    analyzed = client.post(f"/api/pilot-assessments/{assessment_id}/analyze")
    assert analyzed.status_code == 200
    result = analyzed.json()
    assert result["status"] == "baseline_withheld"
    assert result["quality_gate"]["passed"] is False
    assert result["analysis"]["finding_count"] == 0
    assert any("at least 12 hours" in reason for reason in result["quality_gate"]["blocking_reasons"])
    flatlined = next(item for item in result["quality_gate"]["signals"] if item["name"] == "Pump Power Kw")
    assert flatlined["included"] is False
    assert "flatlined" in flatlined["baseline"]["flags"]
    assert "only 1 distinct values" in flatlined["exclusion_reasons"][0]


def test_assessments_are_scoped_to_the_creating_operator(client) -> None:
    baseline, comparison = _tower_datasets(rows=96)
    response = client.post(
        "/api/pilot-assessments/intake",
        headers={"X-Neraium-User": "owner@tower.test"},
        files={
            "baseline_file": ("baseline.csv", io.BytesIO(baseline), "text/csv"),
            "comparison_file": ("comparison.csv", io.BytesIO(comparison), "text/csv"),
        },
    )
    assert response.status_code == 201
    assessment_id = response.json()["assessment_id"]
    hidden = client.get(
        f"/api/pilot-assessments/{assessment_id}",
        headers={"X-Neraium-User": "other@tower.test"},
    )
    assert hidden.status_code == 404
    owner_list = client.get(
        "/api/pilot-assessments",
        headers={"X-Neraium-User": "owner@tower.test"},
    )
    other_list = client.get(
        "/api/pilot-assessments",
        headers={"X-Neraium-User": "other@tower.test"},
    )
    assert [item["assessment_id"] for item in owner_list.json()["assessments"]] == [assessment_id]
    assert other_list.json()["assessments"] == []
