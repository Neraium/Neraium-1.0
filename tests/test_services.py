import pytest

from app.services.analysis_explanations import build_analysis_explanation
from app.services.baseline_analysis import build_baseline_analysis
from app.services.csv_parser import parse_csv_content, preview_rows
from app.services.cultivation_mapping import map_cultivation_columns
from app.services.data_quality import (
    build_data_quality,
    detect_timestamp_column,
    profile_numeric_columns,
    profile_timestamps,
)
from app.services.driver_attribution import build_driver_attribution
from app.services.operator_report import build_operator_report
from app.services.sii_intelligence import confidence_number, urgency_from_upload
from app.services.sii_runner import (
    CORE_ENGINE,
    RUNNER_MODULE,
    VALIDATION_RUNNER,
    build_runner_status,
    runner_available,
)


def test_sii_runner_import_status_reports_real_modules() -> None:
    status = build_runner_status()

    assert runner_available() is True
    assert status["runner_available"] is True
    assert status["runner_module"] == RUNNER_MODULE
    assert status["core_engine"] == CORE_ENGINE
    assert status["validation_runner"] == VALIDATION_RUNNER
    assert status["same_engine_family_as_validation"] is False
    assert status["same_exact_fd004_validation_runner"] is False


def test_csv_parser_returns_columns_rows_and_preview() -> None:
    columns, rows = parse_csv_content(
        b"timestamp,temperature\n2026-05-01T08:00:00Z,75\n"
    )

    assert columns == ["timestamp", "temperature"]
    assert rows == [["2026-05-01T08:00:00Z", "75"]]
    assert preview_rows(columns, rows) == [
        {"timestamp": "2026-05-01T08:00:00Z", "temperature": "75"}
    ]


def test_csv_parser_rejects_empty_content() -> None:
    with pytest.raises(ValueError, match="CSV file is empty."):
        parse_csv_content(b"")


def test_data_quality_profiles_numeric_and_timestamp_data() -> None:
    columns = ["recorded_at", "temperature", "humidity"]
    rows = [
        ["2026-05-01T08:00:00Z", "74", "55"],
        ["2026-05-01T08:05:00Z", "76", ""],
        ["2026-05-01T08:10:00Z", "75", "56"],
        ["2026-05-01T08:15:00Z", "77", "54"],
        ["2026-05-01T08:20:00Z", "78", "53"],
    ]

    timestamp_column = detect_timestamp_column(columns)
    numeric_profiles = profile_numeric_columns(columns, rows)
    timestamp_profile = profile_timestamps(columns, rows, timestamp_column)
    quality = build_data_quality(
        row_count=len(rows),
        column_count=len(columns),
        numeric_column_count=len(numeric_profiles),
        timestamp_detected=timestamp_column is not None,
        warnings=[],
    )

    assert timestamp_column == "recorded_at"
    assert timestamp_profile["estimated_sample_interval"] == "5 minutes"
    assert {profile["column"] for profile in numeric_profiles} == {"temperature", "humidity"}
    assert quality["readiness"] == "ready"


def test_baseline_analysis_compares_first_and_last_windows() -> None:
    columns = ["timestamp", "temperature"]
    rows = [
        ["2026-05-01T08:00:00Z", "70"],
        ["2026-05-01T08:05:00Z", "70"],
        ["2026-05-01T08:10:00Z", "74"],
        ["2026-05-01T08:15:00Z", "80"],
        ["2026-05-01T08:20:00Z", "90"],
        ["2026-05-01T08:25:00Z", "90"],
    ]
    numeric_profiles = [{"column": "temperature"}]

    analysis = build_baseline_analysis(columns, rows, numeric_profiles)

    assert analysis["baseline_window_rows"] == 3
    assert analysis["recent_window_rows"] == 3
    assert analysis["column_drift"][0]["direction"] == "up"
    assert analysis["column_drift"][0]["drift_flag"] == "review"


def test_operator_report_uses_existing_sections() -> None:
    data_quality = {
        "row_count": 6,
        "column_count": 2,
        "numeric_column_count": 1,
        "timestamp_detected": True,
        "warnings": [],
        "readiness": "ready",
    }
    timestamp_profile = {
        "detected_timestamp_column": "timestamp",
        "first_timestamp": "2026-05-01T08:00:00",
        "last_timestamp": "2026-05-01T08:25:00",
        "estimated_sample_interval": "5 minutes",
        "warnings": [],
    }
    numeric_profiles = [
        {
            "column": "temperature",
            "missing_count": 0,
            "missing_percent": 0,
            "variability": "low",
            "range_warning": None,
        }
    ]
    baseline_analysis = {
        "baseline_window_rows": 2,
        "recent_window_rows": 2,
        "columns_analyzed": 1,
        "column_drift": [
            {
                "column": "temperature",
                "direction": "flat",
                "drift_flag": "normal",
                "warnings": [],
            }
        ],
        "overall_assessment": "normal",
        "warnings": [],
    }

    report = build_operator_report(
        data_quality=data_quality,
        timestamp_profile=timestamp_profile,
        numeric_profiles=numeric_profiles,
        baseline_analysis=baseline_analysis,
    )

    assert report["data_readiness"] == "ready"
    assert report["source_sections_used"] == [
        "data_quality",
        "timestamp_profile",
        "numeric_profiles",
        "baseline_analysis",
    ]
    assert "usable for initial review" in report["summary"]


def test_cultivation_mapping_maps_core_categories() -> None:
    mapping = map_cultivation_columns(
        [
            "canopy_temp",
            "relative_humidity",
            "irrigation_pump",
            "ppfd",
            "batch_name",
        ]
    )

    assert mapping["categories"]["thermal"] == ["canopy_temp"]
    assert mapping["categories"]["moisture"] == ["relative_humidity"]
    assert mapping["categories"]["timing"] == []
    assert mapping["categories"]["unknown"] == ["irrigation_pump", "ppfd", "batch_name"]


def test_cultivation_mapping_counts_coverage() -> None:
    mapping = map_cultivation_columns(["temp", "rh", "zone"])

    assert mapping["mapped_column_count"] == 3
    assert mapping["unknown_column_count"] == 0
    assert mapping["coverage_percent"] == 100.0
    assert mapping["mapping_version"] == "schema-generic-v1"
    assert mapping["warnings"] == []


def test_operator_report_references_mapped_categories_when_present() -> None:
    data_quality = {
        "row_count": 6,
        "column_count": 2,
        "numeric_column_count": 1,
        "timestamp_detected": True,
        "warnings": [],
        "readiness": "ready",
    }
    timestamp_profile = {
        "detected_timestamp_column": "timestamp",
        "first_timestamp": "2026-05-01T08:00:00",
        "last_timestamp": "2026-05-01T08:25:00",
        "estimated_sample_interval": "5 minutes",
        "warnings": [],
    }
    baseline_analysis = {
        "baseline_window_rows": 2,
        "recent_window_rows": 2,
        "columns_analyzed": 1,
        "column_drift": [],
        "overall_assessment": "normal",
        "warnings": [],
    }
    cultivation_mapping = map_cultivation_columns(["temperature", "humidity"])

    report = build_operator_report(
        data_quality=data_quality,
        timestamp_profile=timestamp_profile,
        numeric_profiles=[],
        baseline_analysis=baseline_analysis,
        cultivation_mapping=cultivation_mapping,
    )

    assert "cultivation_mapping" in report["source_sections_used"]
    assert any("thermal, moisture" in item for item in report["key_observations"])


def test_operator_report_omits_mapping_source_when_no_categories_mapped() -> None:
    data_quality = {
        "row_count": 6,
        "column_count": 1,
        "numeric_column_count": 0,
        "timestamp_detected": False,
        "warnings": [],
        "readiness": "not_ready",
    }
    timestamp_profile = {
        "detected_timestamp_column": None,
        "first_timestamp": None,
        "last_timestamp": None,
        "estimated_sample_interval": None,
        "warnings": [],
    }
    baseline_analysis = {
        "baseline_window_rows": 0,
        "recent_window_rows": 0,
        "columns_analyzed": 0,
        "column_drift": [],
        "overall_assessment": "needs_review",
        "warnings": [],
    }
    cultivation_mapping = map_cultivation_columns(["batch_name"])

    report = build_operator_report(
        data_quality=data_quality,
        timestamp_profile=timestamp_profile,
        numeric_profiles=[],
        baseline_analysis=baseline_analysis,
        cultivation_mapping=cultivation_mapping,
    )

    assert "cultivation_mapping" not in report["source_sections_used"]
    assert not any("Cultivation mapping identified" in item for item in report["key_observations"])


def test_driver_attribution_ranks_humidity_control_with_persistent_relationship_evidence() -> None:
    attribution = build_driver_attribution(
        room_state={"room": "Flower Room 2", "state": "Needs review", "severity": "review"},
        telemetry_context={
            "numeric_profiles": [],
            "timestamp_profile": {"detected_timestamp_column": "timestamp", "warnings": []},
            "data_quality": {"warnings": [], "readiness": "ready"},
            "cultivation_mapping": map_cultivation_columns(["humidity", "hvac_runtime"]),
        },
        baseline_context={
            "cultivation_mapping": map_cultivation_columns(["humidity", "hvac_runtime"]),
            "baseline_analysis": {
                "column_drift": [
                    {
                        "column": "humidity",
                        "drift_flag": "review",
                        "direction": "up",
                        "warnings": [],
                    }
                ]
            },
        },
        engine_result={
            "persistence_assessment": {"persistent_columns": ["humidity"]},
            "evidence": [
                {
                    "type": "relationship_change",
                    "columns": ["humidity", "hvac_runtime"],
                    "change": -0.72,
                }
            ],
        },
    )

    assert attribution["driver_category"] == "process_timing"
    assert attribution["likely_driver"] == "Process timing response"
    assert attribution["attribution_confidence"] == "low"
    assert "Humidity recovery is becoming less stable" in attribution["supporting_evidence"][0]
    assert "root cause" not in str(attribution).lower()


def test_driver_attribution_ranks_sensor_network_for_missing_and_timestamp_evidence() -> None:
    attribution = build_driver_attribution(
        room_state={"room": "Veg Room A", "state": "Needs review", "severity": "review"},
        telemetry_context={
            "numeric_profiles": [
                {"column": "sensor_node_1", "missing_count": 4},
            ],
            "timestamp_profile": {
                "detected_timestamp_column": None,
                "warnings": ["Timestamp column contains values that could not be parsed."],
            },
            "data_quality": {
                "warnings": ["sensor_node_1 contains missing numeric values."],
                "readiness": "needs_review",
            },
            "cultivation_mapping": map_cultivation_columns(["sensor_node_1"]),
        },
        baseline_context={
            "cultivation_mapping": map_cultivation_columns(["sensor_node_1"]),
            "baseline_analysis": {
                "column_drift": [],
                "warnings": ["sensor_node_1 has missing values in baseline or recent windows."],
            },
        },
        engine_result={"persistence_assessment": {"persistent_columns": []}, "evidence": []},
    )

    assert attribution["driver_category"] == "sensor_network"
    assert attribution["likely_driver"] == "Sensor/network continuity"
    assert attribution["next_operator_move"] == "Check sensor sync, gateway status, and stale readings"


def test_driver_attribution_returns_unknown_for_single_weak_signal() -> None:
    attribution = build_driver_attribution(
        room_state={"room": "Flower Room 1", "state": "Needs review", "severity": "review"},
        telemetry_context={
            "numeric_profiles": [],
            "timestamp_profile": {"detected_timestamp_column": "timestamp", "warnings": []},
            "data_quality": {"warnings": [], "readiness": "ready"},
            "cultivation_mapping": map_cultivation_columns(["temperature"]),
        },
        baseline_context={
            "cultivation_mapping": map_cultivation_columns(["temperature"]),
            "baseline_analysis": {
                "column_drift": [
                    {
                        "column": "temperature",
                        "drift_flag": "watch",
                        "direction": "up",
                        "warnings": [],
                    }
                ]
            },
        },
        engine_result={"persistence_assessment": {"persistent_columns": []}, "evidence": []},
    )

    assert attribution["driver_category"] == "thermal_control"
    assert attribution["attribution_confidence"] == "low"
    assert attribution["next_operator_move"] == "Check thermal control setpoints and recovery timing"


def test_confidence_and_urgency_are_downgraded_for_contradictory_weak_evidence() -> None:
    data_quality = {
        "readiness": "needs_review",
        "reliability_rating": "weak",
        "quality_metrics": {
            "rows_used": 24,
            "drop_ratio": 0.18,
            "rows_with_missing_values": 5,
            "rows_with_invalid_numeric": 0,
            "irregular_sampling": False,
            "baseline_reliable": False,
        },
    }
    baseline_analysis = {
        "baseline_window_rows": 12,
        "recent_window_rows": 12,
        "columns_analyzed": 2,
        "column_drift": [],
        "overall_assessment": "normal",
        "warnings": [],
    }
    engine_result = {
        "overall_result": "normal",
        "signals": [{"level": "elevated", "type": "baseline_drift"}],
        "evidence": [{"type": "relationship_change", "columns": ["temperature", "humidity"], "change": 0.71}],
        "system_evidence": {"corroboration_level": "limited", "categories_showing_meaningful_change": 1},
        "persistence_assessment": {"persistent_columns": []},
    }
    attribution = {"attribution_confidence": "high", "severity": "action"}

    assert confidence_number(
        attribution,
        data_quality=data_quality,
        baseline_analysis=baseline_analysis,
        engine_result=engine_result,
    ) <= 40
    assert urgency_from_upload(
        data_quality=data_quality,
        engine_result=engine_result,
        attribution=attribution,
    ) == "review"


def test_driver_attribution_elevates_aquatic_infrastructure_narrative_when_multiple_families_align() -> None:
    attribution = build_driver_attribution(
        room_state={"room": "Pool 4", "state": "Needs review", "severity": "review"},
        telemetry_context={
            "columns": ["pool_water_temp", "heater_runtime", "filter_pressure", "water_level", "circulation_pump_runtime"],
            "telemetry_profile": "pool_hottub_systems",
            "numeric_profiles": [],
            "timestamp_profile": {"detected_timestamp_column": "timestamp", "warnings": []},
            "data_quality": {"warnings": [], "readiness": "ready"},
            "cultivation_mapping": map_cultivation_columns(["pool_water_temp", "heater_runtime", "filter_pressure", "water_level", "circulation_pump_runtime"]),
        },
        baseline_context={
            "cultivation_mapping": map_cultivation_columns(["pool_water_temp", "heater_runtime", "filter_pressure", "water_level", "circulation_pump_runtime"]),
            "baseline_analysis": {
                "column_drift": [
                    {"column": "filter_pressure", "drift_flag": "review", "direction": "up", "warnings": []},
                    {"column": "water_level", "drift_flag": "watch", "direction": "down", "warnings": []},
                    {"column": "heater_runtime", "drift_flag": "review", "direction": "up", "warnings": []},
                ]
            },
        },
        engine_result={
            "system_evidence": {"corroboration_level": "strong"},
            "persistence_assessment": {"persistent_columns": ["filter_pressure", "heater_runtime"]},
            "evidence": [
                {
                    "type": "relationship_change",
                    "columns": ["filter_pressure", "heater_runtime"],
                    "change": 0.81,
                }
            ],
        },
    )

    assert attribution["driver_category"] == "aquatic_circulation_infrastructure"
    assert "Pool circulation system drift coincides with" in attribution["likely_driver"]
    assert "makeup-water demand increase" in attribution["likely_driver"]
    assert "heater runtime divergence" in attribution["likely_driver"]
    assert attribution["attribution_confidence"] in {"medium", "high"}


def test_driver_attribution_elevates_hvac_infrastructure_narrative_when_multiple_families_align() -> None:
    columns = ["supply_temp", "return_temp", "static_pressure", "compressor_runtime", "air_handler_status"]
    attribution = build_driver_attribution(
        room_state={"room": "AHU-3", "state": "Needs review", "severity": "review"},
        telemetry_context={
            "columns": columns,
            "telemetry_profile": "hvac_systems",
            "numeric_profiles": [],
            "timestamp_profile": {"detected_timestamp_column": "timestamp", "warnings": []},
            "data_quality": {"warnings": [], "readiness": "ready"},
            "cultivation_mapping": map_cultivation_columns(columns),
        },
        baseline_context={
            "cultivation_mapping": map_cultivation_columns(columns),
            "baseline_analysis": {
                "column_drift": [
                    {"column": "static_pressure", "drift_flag": "review", "direction": "up", "warnings": []},
                    {"column": "supply_temp", "drift_flag": "review", "direction": "down", "warnings": []},
                    {"column": "compressor_runtime", "drift_flag": "watch", "direction": "up", "warnings": []},
                ]
            },
        },
        engine_result={
            "system_evidence": {"corroboration_level": "strong"},
            "persistence_assessment": {"persistent_columns": ["static_pressure", "compressor_runtime"]},
            "evidence": [
                {
                    "type": "relationship_change",
                    "columns": ["static_pressure", "compressor_runtime"],
                    "change": 0.78,
                }
            ],
        },
    )

    assert attribution["driver_category"] == "hvac_air_distribution_infrastructure"
    assert "Air distribution system drift coincides with" in attribution["likely_driver"]
    assert "supply-return thermal split divergence" in attribution["likely_driver"]
    assert "compressor runtime divergence" in attribution["likely_driver"]
    assert attribution["attribution_confidence"] in {"medium", "high"}


def test_driver_attribution_elevates_utility_infrastructure_narrative_from_operational_profile() -> None:
    columns = [
        "distribution_pressure",
        "pump_station_output",
        "reservoir_refill_rate",
        "leak_detection_indicator",
        "sewer_flow",
    ]
    attribution = build_driver_attribution(
        room_state={"room": "Utility Grid", "state": "Needs review", "severity": "review"},
        telemetry_context={
            "columns": columns,
            "telemetry_profile": "unknown",
            "operational_signal_profile": "utility_infrastructure",
            "numeric_profiles": [],
            "timestamp_profile": {"detected_timestamp_column": "timestamp", "warnings": []},
            "data_quality": {"warnings": [], "readiness": "ready"},
            "cultivation_mapping": map_cultivation_columns(columns),
        },
        baseline_context={
            "cultivation_mapping": map_cultivation_columns(columns),
            "baseline_analysis": {
                "column_drift": [
                    {"column": "distribution_pressure", "drift_flag": "review", "direction": "down", "warnings": []},
                    {"column": "reservoir_refill_rate", "drift_flag": "watch", "direction": "up", "warnings": []},
                    {"column": "leak_detection_indicator", "drift_flag": "review", "direction": "up", "warnings": []},
                ]
            },
        },
        engine_result={
            "system_evidence": {"corroboration_level": "strong"},
            "persistence_assessment": {"persistent_columns": ["distribution_pressure", "leak_detection_indicator"]},
            "evidence": [
                {
                    "type": "relationship_change",
                    "columns": ["distribution_pressure", "pump_station_output", "leak_detection_indicator"],
                    "change": 0.74,
                }
            ],
        },
    )

    assert attribution["driver_category"] == "utility_distribution_infrastructure"
    assert "Utility distribution system drift coincides with" in attribution["likely_driver"]
    assert "reservoir refill divergence" in attribution["likely_driver"]
    assert "leak or downstream demand divergence" in attribution["likely_driver"]
    assert attribution["attribution_confidence"] in {"medium", "high"}


def test_analysis_explanation_builds_decision_outputs_from_upload_result() -> None:
    result = {
        "operating_state": "Structural drift observed",
        "timestamp_profile": {
            "first_timestamp": "2026-06-23T09:00:00Z",
            "last_timestamp": "2026-06-24T21:00:00Z",
        },
        "baseline_analysis": {
            "overall_assessment": "needs_review",
            "baseline_window_rows": 18,
            "recent_window_rows": 18,
            "columns_analyzed": 3,
            "column_drift": [
                {
                    "column": "pressure",
                    "direction": "up",
                    "drift_flag": "review",
                    "baseline_average": 50,
                    "recent_average": 59,
                    "absolute_change": 9,
                    "percent_change": 18,
                }
            ],
        },
        "relationship_model": {
            "top_relationship_changes": [
                {
                    "relationship": "pressure <-> flow",
                    "baseline_correlation": 0.91,
                    "recent_correlation": -0.2,
                    "correlation_delta": 1.11,
                    "baseline_sample_size": 18,
                    "recent_sample_size": 18,
                    "summary": "Coupling shift in pressure vs flow: baseline=0.910, recent=-0.200, delta=1.110.",
                }
            ]
        },
        "operator_report": {
            "recommended_operator_checks": ["Review pressure readings against facility logs for the uploaded period."],
        },
        "sii_intelligence": {"facility_state": "drift", "primary_room": "Pump room", "confidence": 0.88},
        "engine_result": {
            "persistence_assessment": {
                "persistent_columns": ["pressure"],
                "details": [{"column": "pressure", "persistent": True, "recent_values_checked": 18, "support_percent": 83.3}],
            }
        },
    }

    explanation = build_analysis_explanation(result)

    assert explanation["executive_summary"]["overall_operational_status"] == "Structural drift observed"
    assert explanation["executive_summary"]["highest_priority_finding"] == "Flow & Pressure Degrading"
    assert explanation["insights"][0]["evidence"][0]["confidence"] == "high"
    assert "Operating pattern change: 1.11" in explanation["insights"][0]["evidence"][0]["relevant_metric_changes"]
    assert explanation["systems"][0]["health_status"] == "Structural drift observed"
    assert explanation["relationships"][0]["columns"] == ["pressure", "flow"]
    assert explanation["relationships"][0]["confidence"] == "high"
    assert explanation["evidence"][0]["what_happened"]
    assert explanation["evidence"][0]["why_neraium_believes_this"]
    assert explanation["recommendations"][0]["recommendation"]
    assert {"executive_summary", "systems", "relationships", "insights", "fingerprint", "evidence", "recommendations"}.issubset(explanation)
    assert "operating fingerprint is changing" in explanation["fingerprint"]["meaning"]
