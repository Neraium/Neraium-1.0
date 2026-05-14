from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class VPDCouplingDrift:
    drift_level: str
    temperature_humidity_synchronization: str
    room_to_room_coherence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VPDPropagationEvent:
    pathway: str
    propagation_strength: str
    latent_instability: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VPDConvergenceProfile:
    convergence_state: str
    recovery_lag: str
    convergence_failure_risk: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class VPDRelationshipState:
    coupling_drift: dict[str, Any]
    propagation_events: list[dict[str, Any]]
    convergence_profile: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_vpd_relationship_state(intelligence: dict[str, Any]) -> dict[str, Any]:
    pathways = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
    state = VPDRelationshipState(
        coupling_drift=VPDCouplingDrift(
            drift_level="moderate_drift",
            temperature_humidity_synchronization="weakening",
            room_to_room_coherence="partial_decoupling",
        ).to_dict(),
        propagation_events=[
            VPDPropagationEvent(
                pathway=path if "humidity" in path.lower() or "thermal" in path.lower() else f"vpd-coupling->{path}",
                propagation_strength="developing",
                latent_instability="present",
            ).to_dict()
            for path in pathways[:4]
        ],
        convergence_profile=VPDConvergenceProfile(
            convergence_state="recovery_lagging",
            recovery_lag="night_cycle_delay",
            convergence_failure_risk="elevating_if_compensation_persists",
        ).to_dict(),
    )
    return state.to_dict()

