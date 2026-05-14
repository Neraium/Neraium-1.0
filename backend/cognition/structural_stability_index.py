from __future__ import annotations

from typing import Any


STATES = ("STABLE", "WATCH", "DETERIORATING", "FRAGMENTING", "RECOVERING")


class StructuralStabilityIndex:
    def evaluate(
        self,
        *,
        topology_consistency: float,
        propagation_stability: float,
        subsystem_convergence: float,
        persistence_quality: float,
        fragmentation_pressure: float,
        recovery_convergence: float,
        relationship_coherence: float,
    ) -> dict[str, Any]:
        frag = clamp(fragmentation_pressure)
        recover = clamp(recovery_convergence)
        coherence = mean(
            clamp(topology_consistency),
            clamp(propagation_stability),
            clamp(subsystem_convergence),
            clamp(persistence_quality),
            clamp(relationship_coherence),
        )
        if recover >= 0.64 and coherence >= 0.58 and frag < 0.42:
            state = "RECOVERING"
        elif frag >= 0.68 or (coherence < 0.32 and recover < 0.42):
            state = "FRAGMENTING"
        elif coherence < 0.45:
            state = "DETERIORATING"
        elif coherence < 0.62 or frag >= 0.5:
            state = "WATCH"
        else:
            state = "STABLE"
        return {
            "state": state,
            "coherence_profile": {
                "topology_consistency": round(clamp(topology_consistency), 4),
                "propagation_stability": round(clamp(propagation_stability), 4),
                "subsystem_convergence": round(clamp(subsystem_convergence), 4),
                "persistence_quality": round(clamp(persistence_quality), 4),
                "fragmentation_pressure": round(frag, 4),
                "recovery_convergence": round(recover, 4),
                "relationship_coherence": round(clamp(relationship_coherence), 4),
            },
            "descriptor": descriptor(state),
        }


def descriptor(state: str) -> str:
    return {
        "STABLE": "Topology and subsystem relationships remain convergent.",
        "WATCH": "Early structural drift is present; relationship coherence should be watched.",
        "DETERIORATING": "Structural pressure is reinforcing deterioration pathways.",
        "FRAGMENTING": "Cross-system cohesion is breaking and fragmentation pressure is dominant.",
        "RECOVERING": "Subsystem pathways are reconverging and propagation pressure is decaying.",
    }[state]


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def mean(*values: float) -> float:
    return sum(values) / max(len(values), 1)

