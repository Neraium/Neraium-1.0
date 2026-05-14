from __future__ import annotations

from typing import Any


def build_ontology_corpus() -> dict[str, Any]:
    return {
        "structural_primitives": [item("StructuralPrimitive", "relationship_weakening"), item("StructuralPrimitive", "pressure_migration")],
        "propagation_patterns": [item("PropagationPattern", "directed_pressure_migration"), item("PropagationPattern", "pathway_acceleration")],
        "deterioration_sequences": [item("DeteriorationSequence", "structural_fragmentation_path"), item("DeteriorationSequence", "compression_to_divergence")],
        "recovery_patterns": [item("RecoveryPattern", "reconvergence_decay"), item("RecoveryPattern", "compensation_unwind")],
        "compression_patterns": [item("CompressionPattern", "latent_pressure_accumulation")],
        "compensation_patterns": [item("CompensationPattern", "cascading_compensation")],
        "fragmentation_patterns": [item("FragmentationPattern", "topology_fragmentation")],
        "convergence_patterns": [item("ConvergencePattern", "recovery_reconvergence")],
    }


def item(kind: str, name: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "canonical_name": name,
        "description": f"{name.replace('_', ' ')} primitive",
        "structural_indicators": ["topology drift", "propagation pressure", "evidence corroboration"],
        "topology_signature": "coherence shift",
        "propagation_signature": "pathway activation",
        "domain_mappings": ["cultivation", "data_centers", "aerospace_manufacturing", "water_infrastructure", "energy_systems"],
        "evidence_requirements": ["signal lineage", "topology lineage", "propagation lineage"],
        "replay_references": ["canonical replay phase mapping"],
        "validation_status": "validated_internally",
    }

