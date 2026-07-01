from app.services.telemetry_classification import (
    build_telemetry_signal_catalog,
    classify_telemetry_signal,
)


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
