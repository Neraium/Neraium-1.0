from __future__ import annotations

from typing import Any


def sii_layers() -> list[dict[str, Any]]:
    return [
        layer("telemetry_normalization", "Normalize heterogeneous telemetry into structural signal families."),
        layer("structural_state", "Represent evolving structural state and subsystem coupling context."),
        layer("topology_cognition", "Track topology drift, coherence, and subsystem interaction signatures."),
        layer("propagation_reasoning", "Model directional instability movement and pathway activation."),
        layer("structural_memory", "Retrieve historical structural fingerprints and progression analogs."),
        layer("archetype_ontology", "Classify recurring structural behavior archetypes with evidence grounding."),
        layer("evidence_lineage", "Trace evidence sources, corroboration quality, and lineage completeness."),
        layer("replay_audit", "Reconstruct replay/audit trajectories for inspection and defensibility."),
        layer("continuation_modeling", "Model continuation windows and convergence envelopes as operational ranges."),
        layer("operator_cognition_interface", "Present replay-first, explainable, operator-centric cognition outputs."),
    ]


def layer(name: str, purpose: str) -> dict[str, Any]:
    return {
        "name": name,
        "purpose": purpose,
        "inputs": ["upstream structural artifacts"],
        "outputs": ["layer-specific structural cognition artifacts"],
        "evidence_requirements": ["lineage references", "topology context", "propagation traces"],
        "failure_modes": ["insufficient evidence", "topology ambiguity", "low corroboration continuity"],
        "audit_requirements": ["timestamped outputs", "replay references", "lineage traceability"],
        "operator_facing_outputs": ["interpretable structural state", "reasoning artifacts", "continuation context"],
    }

