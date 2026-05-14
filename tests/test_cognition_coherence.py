from cognition.operational_time_engine import OperationalTimeEngine
from cognition.structural_stability_index import StructuralStabilityIndex
from engines.recovery_convergence_engine import RecoveryConvergenceEngine
from engines.structural_compression_engine import StructuralCompressionEngine


def test_structural_stability_index_returns_operational_state() -> None:
    engine = StructuralStabilityIndex()
    result = engine.evaluate(
        topology_consistency=0.44,
        propagation_stability=0.39,
        subsystem_convergence=0.32,
        persistence_quality=0.35,
        fragmentation_pressure=0.72,
        recovery_convergence=0.22,
        relationship_coherence=0.37,
    )

    assert result["state"] in {"WATCH", "DETERIORATING", "FRAGMENTING"}
    assert "coherence_profile" in result
    assert result["descriptor"]


def test_recovery_and_compression_engines_return_structural_outputs() -> None:
    recovery = RecoveryConvergenceEngine().model(
        facility_cognition={
            "subsystem_pressure": {
                "subsystems": {"thermal_control": 0.42, "moisture_control": 0.38},
            },
        },
        causality_graph={"dominant_pathways": ["airflow_to_moisture"], "edges": [{"source": "a", "target": "b"}]},
        memory_retrieval={"memory_matches": [{"label": "Recovery convergence after targeted intervention"}]},
        persistence={"persistent_columns": ["humidity"]},
    )
    compression = StructuralCompressionEngine().detect(
        baseline_analysis={
            "column_drift": [
                {"drift_flag": "watch"},
                {"drift_flag": "watch"},
                {"drift_flag": "review"},
            ]
        },
        engine_result={"evidence": [{"type": "relationship_change"}], "system_evidence": {"numeric_signals_showing_meaningful_change": 3}},
        causality_graph={"edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]},
    )

    assert "convergence_quality" in recovery
    assert "compression_intensity" in compression
    assert "delayed_divergence_risk" in compression


def test_operational_time_engine_exposes_canonical_intervals() -> None:
    result = OperationalTimeEngine().model(
        causality_graph={"dominant_pathways": ["a->b", "b->c"]},
        compression={"compression_intensity": "MODERATE_COMPRESSION"},
        recovery={"convergence_quality": "MODERATE_CONVERGENCE", "convergence_timing": "4-7 operational windows"},
        counterfactuals={"uncertainty_ranges": {"instability_acceleration_window_days": [6, 11]}},
        persistence={"persistent_columns": ["humidity", "temperature"]},
    )

    assert result["operational_progression_phase"]
    assert result["timing_windows"]["continuation_acceleration_window"] == "6-11 operational days"
    assert "phase_8" in result["structural_progression_intervals"]
