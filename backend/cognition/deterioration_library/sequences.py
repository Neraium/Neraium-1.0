from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class DeteriorationSequence:
    sequence_id: str
    name: str
    topology_evolution: list[str]
    subsystem_pressure_migration: list[str]
    propagation_activation: list[str]
    archetype_emergence: list[str]
    continuation_pathways: list[str]
    recovery_behavior: list[str]
    evidence_lineage: list[str]
    cognition_state_evolution: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CANONICAL_DETERIORATION_SEQUENCES: tuple[DeteriorationSequence, ...] = (
    DeteriorationSequence(
        "dl-airflow-fragmentation",
        "Airflow Fragmentation",
        ["stable_topology", "relationship_weakening", "subsystem_fragmentation"],
        ["airflow -> thermal", "thermal -> humidity"],
        ["airflow imbalance", "propagation acceleration"],
        ["RELATIONSHIP_DECAY", "TOPOLOGY_FRAGMENTATION"],
        ["fragmentation continuation", "constrained recovery"],
        ["pathway suppression after flow correction"],
        ["airflow and humidity corroboration", "topology support from path concentration"],
        ["WATCH", "DETERIORATING", "FRAGMENTING"],
    ),
    DeteriorationSequence(
        "dl-thermal-compensation",
        "Thermal Compensation Masking",
        ["stable_topology", "pressure_migration", "latent_pressure_accumulation"],
        ["thermal -> moisture", "moisture -> compensation load"],
        ["thermal lag propagation"],
        ["COMPENSATION_MASKING", "THERMAL_PROPAGATION"],
        ["continuation with masking", "eventual divergence"],
        ["recovery after compensation unwind"],
        ["cross-category relationship evidence", "persistence support"],
        ["WATCH", "DETERIORATING", "RECOVERING"],
    ),
    DeteriorationSequence(
        "dl-oscillatory-instability",
        "Oscillatory Instability",
        ["relationship_weakening", "pressure_migration", "propagation_activation"],
        ["thermal <-> airflow feedback loops"],
        ["oscillatory pathway reactivation"],
        ["OSCILLATORY_INSTABILITY"],
        ["continuation under cycling pressure"],
        ["stabilization after damping"],
        ["high variability evidence", "alternating relationship evidence"],
        ["WATCH", "DETERIORATING", "WATCH"],
    ),
    DeteriorationSequence(
        "dl-delayed-convergence",
        "Delayed Convergence",
        ["pressure_migration", "archetype_emergence", "continuation_pathways"],
        ["moisture -> thermal -> timing"],
        ["slow propagation with delayed decay"],
        ["DELAYED_DIVERGENCE", "RESPONSE_LAG"],
        ["extended continuation window"],
        ["late reconvergence"],
        ["timing evidence", "persistent but non-fragmenting drift"],
        ["WATCH", "DETERIORATING", "RECOVERING"],
    ),
    DeteriorationSequence(
        "dl-load-response-mismatch",
        "Load Response Mismatch",
        ["relationship_weakening", "pressure_migration", "subsystem_desynchronization"],
        ["load signal -> response lag"],
        ["lag propagation"],
        ["LOAD_RESPONSE_MISMATCH", "RESPONSE_LAG"],
        ["continued lag under demand"],
        ["convergence after load balance reset"],
        ["baseline drift + relationship mismatch"],
        ["WATCH", "DETERIORATING"],
    ),
    DeteriorationSequence(
        "dl-propagation-acceleration",
        "Propagation Acceleration",
        ["pressure_migration", "propagation_activation", "topology_fragmentation"],
        ["multi-subsystem acceleration"],
        ["pathway concentration growth"],
        ["PROPAGATION_ACCELERATION", "CASCADING_COMPENSATION"],
        ["shortening continuation windows"],
        ["partial reconvergence if path dominance falls"],
        ["path density evidence", "timing compression evidence"],
        ["DETERIORATING", "FRAGMENTING"],
    ),
    DeteriorationSequence(
        "dl-structural-compression",
        "Structural Compression",
        ["stable_topology", "latent_pressure_accumulation", "delayed_divergence"],
        ["hidden pressure accumulation"],
        ["delayed propagation activation"],
        ["STRUCTURAL_COMPRESSION", "LATENT_PRESSURE_ACCUMULATION"],
        ["compression continuation"],
        ["release after subsystem normalization"],
        ["moderate corroboration + persistent low amplitude drift"],
        ["WATCH", "DETERIORATING"],
    ),
    DeteriorationSequence(
        "dl-recovery-reconvergence",
        "Recovery Reconvergence",
        ["topology_fragmentation", "continuation_pathways", "recovery_reconvergence"],
        ["pressure unwind across subsystems"],
        ["pathway decay"],
        ["RECOVERY_RECONVERGENCE"],
        ["convergence continuation"],
        ["stable reconvergence with lowered persistence"],
        ["decaying propagation evidence", "improving topology coherence"],
        ["FRAGMENTING", "RECOVERING", "STABLE"],
    ),
)


def sequence_similarity(
    observed_archetypes: list[str],
    observed_paths: list[str],
) -> list[dict[str, Any]]:
    observed_set = {value.upper() for value in observed_archetypes}
    path_tokens = {token.lower() for token in observed_paths}
    scored: list[dict[str, Any]] = []
    for item in CANONICAL_DETERIORATION_SEQUENCES:
        arch_overlap = len(observed_set & {name.upper() for name in item.archetype_emergence})
        path_overlap = sum(1 for token in item.subsystem_pressure_migration if any(part in token.lower() for part in path_tokens))
        score = min(1.0, arch_overlap * 0.26 + path_overlap * 0.18)
        scored.append(
            {
                "sequence_id": item.sequence_id,
                "name": item.name,
                "similarity": round(score, 4),
                "continuation_pathways": item.continuation_pathways,
                "recovery_behavior": item.recovery_behavior,
            }
        )
    return sorted(scored, key=lambda entry: entry["similarity"], reverse=True)

