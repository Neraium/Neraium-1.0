from __future__ import annotations

from app.water_intelligence.models import RelationshipPrior, SignalRequirement, UnitRequirement
from app.water_intelligence.units import accepted_units_for_dimension


def unit(dimension: str, normalized_unit: str) -> UnitRequirement:
    return UnitRequirement(
        dimension=dimension,
        accepted_units=accepted_units_for_dimension(dimension),
        normalized_unit=normalized_unit,
    )


FLOW = unit("flow", "gpm")
PRESSURE = unit("pressure", "psi")
TEMPERATURE = unit("temperature", "degF")
DELTA_T = unit("temperature_difference", "degF")
POWER = unit("power", "kW")
CONDUCTIVITY = unit("conductivity", "uS/cm")
LEVEL = unit("level", "ft")
FRACTION = unit("fraction", "%")
FREQUENCY = unit("frequency", "Hz")


WATER_PRIORS: tuple[RelationshipPrior, ...] = (
    RelationshipPrior(
        prior_id="water.pump_hydraulic_behavior",
        version="1.0.0",
        name="Pump hydraulic behavior",
        description="Interprets SII relationship drift among pump flow, differential pressure, and electrical input without assuming fixed efficiency.",
        applicable_system_types=("pumping", "distribution", "chilled_water_loop", "process_water_loop", "circulation_loop"),
        applicable_asset_classes=("pump", "pump_train", "vfd_pump", "booster_pump"),
        required_signals=(
            SignalRequirement("flow", "Hydraulic flow output", FLOW),
            SignalRequirement("differential_pressure", "Hydraulic differential pressure or head", PRESSURE),
        ),
        optional_supporting_signals=(
            SignalRequirement("pump_power", "Electrical input to pump, motor, or drive", POWER),
            SignalRequirement("pump_current", "Electrical current input", None),
            SignalRequirement("pump_speed", "Pump or VFD speed", FREQUENCY),
            SignalRequirement("valve_position", "Valve position affecting resistance", FRACTION),
            SignalRequirement("bypass_state", "Bypass or recirculation state", None),
            SignalRequirement("pump_stage", "Pump staging or count", None),
            SignalRequirement("operating_mode", "Operating mode context", None),
        ),
        valid_operating_modes=("normal", "occupied", "unoccupied", "manual", "automatic", "lead_lag", "unknown"),
        expected_relationship_form=(
            "Hydraulic output relates flow and differential pressure under comparable pump and system configurations. "
            "Electrical power is supporting context and also depends on pump, motor, and drive efficiency."
        ),
        known_confounders=(
            "static-head contribution changes",
            "valve position changes",
            "bypass state changes",
            "pump staging changes",
            "impeller configuration differs",
            "operating mode changes",
            "signal synchronization is poor",
            "sensor drift",
        ),
        lag_alignment_requirements={"max_lag_seconds_default": 300, "configurable": True},
        data_quality_requirements={"minimum_recent_samples": 6, "minimum_baseline_samples": 6, "max_missing_fraction": 0.25},
        applicability_rules={
            "requires_hydraulic_signals": ["flow", "differential_pressure"],
            "requires_sii_relationship_finding": True,
            "do_not_assume_fixed_efficiency": True,
            "affinity_laws_only_under_comparable_configuration": True,
        },
        invalidation_conditions=(
            "Flow or differential-pressure unit is incompatible.",
            "Operating mode is outside the configured valid modes.",
            "Graph edge is speculative or correlation-only.",
        ),
        confidence_reduction_conditions=(
            "Static head, valve, bypass, staging, impeller, mode, or timestamp alignment changed.",
            "Only electrical input drift is present without hydraulic relationship evidence.",
        ),
        evidence_requirements={
            "sii_relationship_strength": "preserve existing SII confidence and relationship magnitude",
            "hydraulic_signals": ["flow", "differential_pressure"],
            "supporting_signals": ["pump_power", "pump_speed", "valve_position", "bypass_state", "pump_stage"],
        },
        possible_explanations=(
            "Increased system resistance",
            "Valve-position change",
            "Bypass flow",
            "Filter or strainer loading",
            "Sensor drift",
            "Pump-performance change",
            "Changed operating configuration",
        ),
        recommended_checks=(
            "Compare flow and differential-pressure sensors against local gauges or trend validation.",
            "Check valve position, bypass status, pump staging, speed command, and operating mode during the same window.",
            "Review filter or strainer differential pressure before assigning pump performance as the cause.",
            "Confirm whether static head or system configuration changed before applying affinity-law reasoning.",
        ),
        rationale="Engineering prior for pump hydraulic interpretation; SII remains responsible for learning the site-specific relationship.",
        parameters={"minimum_proposed_graph_evidence_types": 3, "timestamp_alignment_tolerance_seconds": 300},
    ),
    RelationshipPrior(
        prior_id="water.chilled_water_thermal_behavior",
        version="1.0.0",
        name="Chilled-water thermal behavior",
        description="Interprets drift among chilled-water temperature split, flow, load, chiller power, valve behavior, and operating mode.",
        applicable_system_types=("chilled_water_loop", "cooling_loop", "central_plant"),
        applicable_asset_classes=("chiller", "chilled_water_pump", "coil", "air_handler", "plant_loop"),
        required_signals=(
            SignalRequirement("supply_temperature", "Chilled-water supply temperature", TEMPERATURE),
            SignalRequirement("return_temperature", "Chilled-water return temperature", TEMPERATURE),
            SignalRequirement("flow", "Chilled-water flow", FLOW),
        ),
        optional_supporting_signals=(
            SignalRequirement("delta_t", "Return minus supply temperature difference", DELTA_T),
            SignalRequirement("thermal_load", "Thermal load", POWER),
            SignalRequirement("chiller_power", "Chiller/compressor power", POWER),
            SignalRequirement("valve_position", "Control valve position", FRACTION),
            SignalRequirement("pump_power", "Pump power", POWER),
            SignalRequirement("pump_speed", "Pump speed", FREQUENCY),
            SignalRequirement("pump_stage", "Pump or chiller staging", None),
            SignalRequirement("operating_mode", "Operating mode context", None),
        ),
        valid_operating_modes=("cooling", "occupied", "unoccupied", "economizer", "manual", "automatic", "unknown"),
        expected_relationship_form=(
            "Thermal behavior is context-dependent: load, flow, supply temperature, return temperature, delta-T, "
            "valve position, pumping, and chiller power must be interpreted by operating mode and sensor location."
        ),
        known_confounders=(
            "sensor location mismatch",
            "fluid assumption mismatch",
            "timestamp misalignment",
            "flow direction uncertainty",
            "unstable operating state",
            "valve control behavior",
            "pump or chiller staging changes",
        ),
        lag_alignment_requirements={"max_lag_seconds_default": 600, "configurable": True},
        data_quality_requirements={"minimum_recent_samples": 6, "minimum_baseline_samples": 6, "stable_operating_state_required": True},
        applicability_rules={
            "requires_temperature_pair_and_flow": True,
            "validate_sensor_locations": True,
            "telemetry_must_not_confirm_low_delta_t_syndrome": True,
        },
        invalidation_conditions=(
            "Supply/return temperature or flow unit is incompatible.",
            "Operating mode is outside the configured valid modes.",
            "Graph edge is speculative or correlation-only.",
        ),
        confidence_reduction_conditions=(
            "Sensor locations, fluid assumptions, timestamp alignment, flow direction, or stable operating state are unknown.",
            "Valve position or pump/chiller staging changed during the compared windows.",
        ),
        evidence_requirements={
            "sii_relationship_strength": "preserve SII relationship finding",
            "thermal_signals": ["supply_temperature", "return_temperature", "flow"],
            "supporting_signals": ["delta_t", "thermal_load", "chiller_power", "valve_position", "pump_power"],
        },
        possible_explanations=(
            "Bypass flow",
            "Control-valve behavior",
            "Coil behavior",
            "Sensor bias",
            "Load-distribution change",
            "Pump or staging changes",
        ),
        recommended_checks=(
            "Validate supply/return sensor locations, timestamp alignment, and flow direction.",
            "Compare flow and delta-T against valve position, pump operation, chiller staging, and operating mode.",
            "Review load distribution before labeling the finding as low delta-T syndrome.",
            "Confirm fluid assumptions and units before calculating thermal load.",
        ),
        rationale="Engineering prior for chilled-water interpretation; telemetry alone does not confirm low delta-T syndrome or maintenance prediction claims.",
        parameters={"minimum_proposed_graph_evidence_types": 3, "timestamp_alignment_tolerance_seconds": 600},
    ),
    RelationshipPrior(
        prior_id="water.filter_differential_pressure",
        version="1.0.0",
        name="Filter differential-pressure behavior",
        description="Interprets site-learned filter differential-pressure drift at comparable flow without forcing a universal flow-squared relationship.",
        applicable_system_types=("filtration", "treatment", "process_water_loop", "cooling_water_loop", "circulation_loop"),
        applicable_asset_classes=("filter", "strainer", "media_filter", "cartridge_filter"),
        required_signals=(
            SignalRequirement("filter_differential_pressure", "Differential pressure across filter or strainer", PRESSURE),
            SignalRequirement("flow", "Flow through filter", FLOW),
        ),
        optional_supporting_signals=(
            SignalRequirement("filter_mode", "Filter mode", None),
            SignalRequirement("backwash_event", "Backwash or maintenance event", None),
            SignalRequirement("valve_position", "Valve configuration", FRACTION),
            SignalRequirement("pump_speed", "Pump speed", FREQUENCY),
            SignalRequirement("operating_mode", "Operating mode context", None),
        ),
        valid_operating_modes=("filtering", "normal", "backwash", "maintenance", "bypass", "unknown"),
        expected_relationship_form=(
            "Use the SII-learned, state-conditioned site baseline. A rise in differential pressure at similar flow can support "
            "a loading or restriction hypothesis, but does not confirm filter loading without corroboration."
        ),
        known_confounders=(
            "flow not comparable",
            "backwash or maintenance event",
            "valve configuration changed",
            "filter mode changed",
            "pump speed changed",
            "sensor quality issue",
        ),
        lag_alignment_requirements={"max_lag_seconds_default": 300, "configurable": True},
        data_quality_requirements={"minimum_recent_samples": 6, "minimum_baseline_samples": 6, "flow_normalized_comparison": True},
        applicability_rules={
            "requires_sii_site_specific_baseline": True,
            "no_universal_dp_flow_squared_law": True,
            "supports_loading_only_as_hypothesis": True,
        },
        invalidation_conditions=(
            "Filter differential-pressure or flow unit is incompatible.",
            "Graph edge is speculative or correlation-only.",
        ),
        confidence_reduction_conditions=(
            "Flow is not comparable across windows.",
            "Backwash, maintenance, valve, mode, pump speed, or sensor-quality confounder is active.",
        ),
        evidence_requirements={
            "sii_relationship_strength": "relationship drift at comparable flow",
            "filter_signals": ["filter_differential_pressure", "flow"],
            "supporting_signals": ["filter_mode", "backwash_event", "valve_position", "pump_speed"],
        },
        possible_explanations=(
            "Filter or strainer loading",
            "Valve configuration change",
            "Flow distribution change",
            "Recent backwash or maintenance effect",
            "Sensor drift",
            "Downstream restriction",
        ),
        recommended_checks=(
            "Compare differential pressure at similar flow and filter mode.",
            "Check recent backwash, filter maintenance, and valve configuration logs.",
            "Verify upstream/downstream pressure sensor calibration before confirming filter loading.",
            "Use existing SII baseline/model output rather than fitting a hardcoded universal curve.",
        ),
        rationale="Filter dP interpretation is site-specific and state-conditioned; SII owns the baseline comparison.",
        parameters={"minimum_proposed_graph_evidence_types": 3, "timestamp_alignment_tolerance_seconds": 300},
    ),
    RelationshipPrior(
        prior_id="water.cooling_tower_mass_balance",
        version="1.0.0",
        name="Cooling-tower mass balance",
        description="Represents tower makeup balance with explicit residual terms when outflow components are not identifiable.",
        applicable_system_types=("cooling_tower", "condenser_water", "heat_rejection"),
        applicable_asset_classes=("cooling_tower", "tower_cell", "basin"),
        required_signals=(
            SignalRequirement("makeup_flow", "Cooling tower makeup water flow", FLOW),
        ),
        optional_supporting_signals=(
            SignalRequirement("evaporation_flow", "Measured evaporation", FLOW),
            SignalRequirement("blowdown_flow", "Measured blowdown", FLOW),
            SignalRequirement("drift_flow", "Measured drift loss", FLOW),
            SignalRequirement("leak_flow", "Measured leak loss", FLOW),
            SignalRequirement("overflow_flow", "Measured overflow loss", FLOW),
            SignalRequirement("storage_change", "Rate-equivalent storage change", FLOW),
            SignalRequirement("basin_level", "Basin level", LEVEL),
            SignalRequirement("makeup_conductivity", "Makeup conductivity", CONDUCTIVITY),
            SignalRequirement("circulating_conductivity", "Circulating-water conductivity", CONDUCTIVITY),
            SignalRequirement("chemical_feed_pump", "Chemical feed state", None),
            SignalRequirement("operating_mode", "Operating mode context", None),
        ),
        valid_operating_modes=("normal", "occupied", "heat_rejection", "blowdown", "maintenance", "startup", "shutdown", "unknown"),
        expected_relationship_form=(
            "makeup = evaporation + blowdown + drift + leaks + overflow + storage change. "
            "Unmeasured components remain combined residuals unless independently measured."
        ),
        known_confounders=(
            "unmeasured blowdown",
            "unmeasured evaporation",
            "unmeasured drift",
            "unmeasured leak or overflow",
            "storage change unknown",
            "makeup conductivity unstable",
            "circulating conductivity unreliable",
            "treatment chemistry invalidates conductivity tracer",
            "sampling points or timing inappropriate",
        ),
        lag_alignment_requirements={"max_lag_seconds_default": 900, "configurable": True},
        data_quality_requirements={"minimum_recent_samples": 4, "sensor_uncertainty_fraction_default": 0.05},
        applicability_rules={
            "represent_residual_if_not_identifiable": True,
            "do_not_hardcode_evaporation_formula": True,
            "conductivity_cycles_are_supporting_only": True,
        },
        invalidation_conditions=(
            "Makeup flow unit is incompatible.",
            "Operating mode is outside the configured valid modes.",
            "Graph edge is speculative or correlation-only when used for operator-facing findings.",
        ),
        confidence_reduction_conditions=(
            "Balance terms are missing or non-identifiable.",
            "Conductivity tracer conditions are incomplete or invalid.",
            "Sensor uncertainty or model uncertainty is high.",
        ),
        evidence_requirements={
            "balance_formula": "makeup = evaporation + blowdown + drift + leaks + overflow + storage change",
            "known_input": ["makeup_flow"],
            "independent_measurements_required_for_component_estimates": True,
        },
        possible_explanations=(
            "Combined unmeasured outflow",
            "Unmeasured blowdown or bleed",
            "Unmeasured evaporation",
            "Unmeasured drift loss",
            "Leakage or overflow",
            "Storage change",
            "Sensor or meter uncertainty",
        ),
        recommended_checks=(
            "Add or validate blowdown, basin level/storage-change, overflow, and leak indicators before separating loss components.",
            "Check makeup meter calibration and sensor uncertainty.",
            "Use conductivity cycles only as supporting evidence after verifying makeup stability, circulating conductivity reliability, chemistry compatibility, and sampling timing.",
            "Do not assign evaporation, blowdown, drift, or leakage individually without independent measurements.",
        ),
        rationale="Mass-balance prior with explicit non-identifiability handling; no universal evaporation equation is embedded.",
        parameters={"minimum_proposed_graph_evidence_types": 3, "timestamp_alignment_tolerance_seconds": 900, "sensor_uncertainty_fraction": 0.05, "model_uncertainty_fraction": 0.2},
    ),
)


def water_priors() -> tuple[RelationshipPrior, ...]:
    return WATER_PRIORS


def prior_by_id(prior_id: str) -> RelationshipPrior | None:
    for prior in WATER_PRIORS:
        if prior.prior_id == prior_id:
            return prior
    return None
