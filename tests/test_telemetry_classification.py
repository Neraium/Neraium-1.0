import pytest

from app.services.telemetry_classification import (
    build_telemetry_signal_catalog,
    classify_telemetry_signal,
)


def test_zone_temperature_is_numeric_equipment_process_telemetry() -> None:
    column = "AHU3_Zone_Temp_F"
    values = [60.0 + index / 100 for index in range(575)]
    profile = {
        "column": column,
        "min": min(values),
        "max": max(values),
        "unique_values": values,
        "constant_or_stuck": False,
    }

    classification = classify_telemetry_signal(column, numeric_profile=profile)
    assert classification["category"] == "equipment_process"
    assert classification["structural_class"] == "Equipment Process Variable"
    assert classification["analysis_role"] == "primary_signal"
    assert classification["operator_primary_eligible"] is True
    assert classification["is_ignored"] is False
    assert classify_telemetry_signal(column) == classification
    catalog = build_telemetry_signal_catalog([column], numeric_profiles=[profile])
    assert catalog[column]["telemetry_classification"] == classification


@pytest.mark.parametrize(
    ("column", "category"),
    [
        ("AHU1_Zone_Temperature_C", "equipment_process"),
        ("zone_temp_f", "equipment_process"),
        ("Zone Temperature (F)", "equipment_process"),
        ("AHU2-Zone-Humidity-Pct", "equipment_process"),
        ("zone_relative_humidity", "equipment_process"),
        ("zone_rh_pct", "equipment_process"),
        ("zone_pressure_pa", "equipment_process"),
        ("zone_airflow_cfm", "equipment_process"),
        ("zone_temperature_setpoint_f", "setpoint"),
        ("AHU2_Zone_Temp_SP_F", "setpoint"),
        ("zone_humidity_set_point", "setpoint"),
        ("zone_setpoint", "setpoint"),
    ],
)
def test_zone_measurements_and_setpoints_remain_telemetry(column: str, category: str) -> None:
    classification = classify_telemetry_signal(column)

    assert classification["category"] == category
    assert classification["is_ignored"] is False


@pytest.mark.parametrize(
    "column",
    [
        "zone",
        "AHU3_Zone",
        "zone_identifier",
        "zone_id",
        "AHU3_Zone_ID",
        "Zone Name",
        "AHU3_Zone_Name",
        "zone_code",
        "zone_number",
        "zone_code_value",
        "zone_temp_sensor_id",
        "zone_humidity_identifier",
        "zone_temperature_name",
        "zone_setpoint_uuid",
        "zone_sensor_serial",
        "asset_id",
        "sensor_uuid",
        "sensor_serial",
        "sensor_identifier",
        "equipment_code",
        "asset",
        "site",
        "facility",
        "room",
        "location",
        "area",
    ],
)
@pytest.mark.parametrize("numeric_profile", [{}, {"unique_values": [101, 102, 103]}])
def test_identifier_fields_remain_ignored(column: str, numeric_profile: dict) -> None:
    classification = classify_telemetry_signal(column, numeric_profile=numeric_profile)

    assert classification["category"] == "identifier"
    assert classification["analysis_role"] == "ignored"
    assert classification["is_ignored"] is True
    assert classification["operator_primary_eligible"] is False


def test_telemetry_structural_classification_covers_operator_eligibility() -> None:
    assert classify_telemetry_signal("pump_vibration_ips")["structural_class"] == "Equipment Process Variable"
    assert classify_telemetry_signal("pump_vibration_ips")["operator_primary_eligible"] is True

    binary = classify_telemetry_signal(
        "pump_status",
        numeric_profile={"min": 0, "max": 1, "unique_values": [0, 1]},
    )
    assert binary["structural_class"] == "Binary Status"
    assert binary["analysis_role"] == "state_signal"
    assert binary["operator_primary_eligible"] is False

    assert classify_telemetry_signal("supply_air_setpoint_f")["structural_class"] == "Setpoint"
    assert classify_telemetry_signal("outdoor_air_temp_f")["structural_class"] == "Weather / Environmental"
    assert classify_telemetry_signal("occupancy_load_pct")["structural_class"] == "Context / Demand Driver"
    assert classify_telemetry_signal("meter_cumulative_gal")["requires_derived_rate"] is True
    assert classify_telemetry_signal("gt_fault_label")["analysis_role"] == "validation_label"
    assert classify_telemetry_signal("asset_id")["analysis_role"] == "ignored"
    assert classify_telemetry_signal("timestamp")["structural_class"] == "Timestamp"


def test_signal_catalog_preserves_identity_priority_fields() -> None:
    catalog = build_telemetry_signal_catalog(
        ["Timestamp", "Supply Pressure (psi)", "Pump Status"],
        numeric_profiles=[
            {"column": "Supply Pressure (psi)", "min": 50, "max": 75, "unique_values": [50, 75]},
            {"column": "Pump Status", "min": 0, "max": 1, "unique_values": [0, 1]},
        ],
        timestamp_column="Timestamp",
        header_present=True,
    )

    pressure = catalog["Supply Pressure (psi)"]
    assert pressure["original_header"] == "Supply Pressure (psi)"
    assert pressure["normalized_name"] == "supply_pressure_psi"
    assert pressure["display_name"] == "Supply pressure"
    assert pressure["engineering_units"] == "psi"
    assert pressure["source_column_index"] == 1
    assert catalog["Pump Status"]["structural_class"] == "Binary Status"


def test_canonical_context_roles_require_specific_semantic_evidence() -> None:
    catalog = build_telemetry_signal_catalog([
        "cooling_demand_tons",
        "occupancy_load_pct",
        "outdoor_air_temp_f",
        "weather_humidity_pct",
        "wet_bulb_f",
    ])

    assert catalog["cooling_demand_tons"]["canonical_role"] == "process_demand"
    assert catalog["cooling_demand_tons"]["engineering_units"] == "tons"
    assert catalog["occupancy_load_pct"]["telemetry_category"] == "scheduled_load_context"
    assert catalog["occupancy_load_pct"]["canonical_role"] is None
    assert catalog["outdoor_air_temp_f"]["canonical_role"] == "environmental_temperature"
    assert catalog["weather_humidity_pct"]["telemetry_category"] == "weather_environment"
    assert catalog["weather_humidity_pct"]["canonical_role"] is None
    assert catalog["wet_bulb_f"]["canonical_role"] is None
