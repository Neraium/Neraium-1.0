from app.services.structural_cognition import build_structural_cognition
from app.services.upload_jobs import process_csv_content


def sample_inputs():
    baseline_analysis = {
        "column_drift": [
            {
                "column": "temperature",
                "percent_change": 24.0,
                "drift_flag": "review",
            },
            {
                "column": "humidity",
                "percent_change": 16.0,
                "drift_flag": "watch",
            },
            {
                "column": "airflow",
                "percent_change": 12.0,
                "drift_flag": "watch",
            },
        ]
    }
    engine_result = {
        "system_evidence": {
            "corroboration_level": "strong",
            "categories_showing_meaningful_change": 3,
            "categories": {
                "thermal_control": {"signals": [{"level": "review"}], "evidence": [{"type": "column_drift"}]},
                "moisture_control": {"signals": [{"level": "watch"}], "evidence": [{"type": "relationship_change"}]},
                "flow_restriction": {"signals": [{"level": "watch"}], "evidence": [{"type": "relationship_change"}]},
            },
        },
        "evidence": [
            {"type": "relationship_change", "columns": ["airflow", "humidity"], "change": 0.84},
            {"type": "relationship_change", "columns": ["temperature", "humidity"], "change": 0.72},
        ],
        "persistence_assessment": {"persistent_columns": ["temperature", "humidity"]},
    }
    driver_attribution = {
        "likely_driver": "Thermal signal instability",
        "driver_category": "thermal_control",
        "supporting_evidence": ["Temperature recovery remained slower than baseline."],
    }
    return baseline_analysis, engine_result, driver_attribution


def test_structural_cognition_returns_memory_archetypes_and_graph() -> None:
    baseline_analysis, engine_result, driver_attribution = sample_inputs()

    cognition = build_structural_cognition(
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        room_summary={"room_count": 2, "rooms": [{"room": "Flower 1"}, {"room": "Flower 2"}]},
        urgency="review",
    )

    assert cognition["structural_memory"]["retrieval_status"] == "matched"
    assert cognition["structural_memory"]["memory_matches"]
    assert cognition["active_archetypes"]
    assert cognition["causality_graph"]["edges"]
    assert cognition["counterfactuals"]["progression_scenarios"]
    assert cognition["facility_cognition"]["facility_cognition_state"]
    assert "Structural pressure is propagating" in cognition["operator_explanation_v2"]["summary"]


def test_upload_processing_embeds_structural_cognition_payload() -> None:
    result = process_csv_content(
        filename="structural-cognition.csv",
        content=(
            "timestamp,room,temperature,humidity,airflow\n"
            "2026-05-01T08:00:00Z,Flower 1,72,54,1.20\n"
            "2026-05-01T08:05:00Z,Flower 1,72,55,1.19\n"
            "2026-05-01T08:10:00Z,Flower 1,73,56,1.15\n"
            "2026-05-01T08:15:00Z,Flower 1,77,61,1.05\n"
            "2026-05-01T08:20:00Z,Flower 1,80,65,0.98\n"
            "2026-05-01T08:25:00Z,Flower 1,82,68,0.92\n"
        ).encode(),
    )

    intelligence = result["sii_intelligence"]

    assert intelligence["active_archetypes"]
    assert intelligence["structural_memory"]["memory_matches"]
    assert intelligence["causality_graph"]["dominant_pathways"]
    assert intelligence["counterfactuals"]["uncertainty_ranges"]["instability_acceleration_window_days"]
    assert intelligence["facility_cognition"]["global_structural_pressure_score"] >= 0
    assert intelligence["operator_explanation_v2"]["active_archetypes"]
    assert intelligence["structural_explanation"][0] == intelligence["operator_explanation_v2"]["summary"]


def test_structural_cognition_counterfactuals_remain_nondeterministic() -> None:
    baseline_analysis, engine_result, driver_attribution = sample_inputs()

    cognition = build_structural_cognition(
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
        driver_attribution=driver_attribution,
        room_summary={"room_count": 1, "rooms": [{"room": "Flower 1"}]},
        urgency="unstable",
    )

    scenario = cognition["counterfactuals"]["progression_scenarios"][0]

    assert "operational days" in scenario["window"]
    assert "If the current deterioration path persists" in scenario["summary"]
    assert "failure" not in scenario["summary"].lower()
