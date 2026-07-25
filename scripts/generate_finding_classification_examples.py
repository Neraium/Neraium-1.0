#!/usr/bin/env python3
"""Generate deterministic representative finding payloads for contract review."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.analysis_explanations import build_analysis_explanation  # noqa: E402
from app.services.analysis_result_contract import build_analysis_result  # noqa: E402


SCENARIOS = ROOT / "tests" / "fixtures" / "finding_classification_scenarios.json"
OUTPUT = ROOT / "docs" / "validation" / "finding-classification-examples.json"


def result_for(scenario: dict) -> dict:
    relationship = {
        "relationship": "pump_speed <-> discharge_pressure",
        "display_columns": ["Pump speed", "Discharge pressure"],
        "change_type": "weakened",
        "baseline_correlation": 0.91,
        "recent_correlation": 0.19,
        "coupling_strength": 0.91,
        "baseline_strength": 0.91,
        "current_strength": 0.19,
        "operating_mode": scenario["operating_mode"],
        "data_confidence": scenario["data_confidence"],
        "sensor_health": scenario["sensor_health"],
        "time_window": {
            "baseline_start": "2026-06-01T00:00:00Z",
            "baseline_end": "2026-06-30T23:59:00Z",
            "current_start": "2026-07-01T00:00:00Z",
            "current_end": "2026-07-18T23:59:00Z",
        },
        **scenario["relationship_evidence"],
    }
    persistent_signals = ["pump_speed", "discharge_pressure"] if scenario["persistence"].get("persistent") else []
    return {
        "job_id": scenario["id"],
        "run_id": scenario["id"],
        "upload_id": scenario["id"],
        "filename": f"{scenario['id']}.csv",
        "completed_at": "2026-07-19T00:05:00Z",
        "timestamp_profile": {
            "first_timestamp": "2026-06-01T00:00:00Z",
            "last_timestamp": "2026-07-18T23:59:00Z",
        },
        "baseline_analysis": {
            "overall_assessment": "needs_review",
            "baseline_window_rows": scenario["relationship_evidence"]["baseline_sample_size"],
            "recent_window_rows": scenario["relationship_evidence"]["recent_sample_size"],
            "columns_analyzed": 2,
            "column_drift": [],
            "warnings": scenario["data_confidence"].get("reasons", []),
        },
        "relationship_model": {
            "top_relationship_changes": [relationship],
            "baseline_relationships": [relationship],
            "relationship_graph": {},
            "operating_mode": scenario["operating_mode"],
        },
        "data_quality": {
            "readiness": "ready" if scenario["data_confidence"]["rating"] != "low" else "not_ready",
            "reliability_rating": "strong" if scenario["data_confidence"]["rating"] == "high" else "usable",
            "data_confidence": scenario["data_confidence"],
            "operating_mode": scenario["operating_mode"],
            "sensor_health": scenario["sensor_health"],
            "warnings": scenario["data_confidence"].get("reasons", []),
        },
        "engine_result": {"persistence_assessment": {"persistent_columns": persistent_signals}},
        "operator_report": {"recommended_operator_checks": ["Review the source evidence."]},
        "sii_intelligence": {"facility_state": "needs_review"},
    }


def compact_example(scenario: dict) -> dict:
    result = result_for(scenario)
    result["analysis_explanation"] = build_analysis_explanation(result)
    payload = build_analysis_result(result)["insights"][0]
    return {
        "scenario": scenario["description"],
        "classification": payload["classification"],
        "data_confidence": payload["data_confidence"],
        "sensor_health": payload.get("sensor_health", []),
        "operating_mode": payload["operating_mode"],
        "persistence": payload["persistence"],
        "relationship_evidence": payload["relationship_evidence"],
        "certainty_limit": payload["certainty_limit"],
        "engineer_wording": {
            "title": payload["title"],
            "what_changed": payload["what_changed"],
            "why_classified": payload["why_neraium_thinks_it_happened"],
            "why_it_matters": payload["why_it_matters"],
        },
        "investigation_guidance": payload["investigation_guidance"],
        "recommended_first_check": payload["investigation_guidance"][0]["check"],
        "relationship_timeline": payload["activity_timeline"],
    }


def main() -> None:
    scenarios = json.loads(SCENARIOS.read_text())
    examples = {scenario["expected_classification"]: compact_example(scenario) for scenario in scenarios}
    OUTPUT.write_text(json.dumps(examples, indent=2) + "\n")
    print(OUTPUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
