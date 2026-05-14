from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RoomPropagationPathway:
    source_room: str
    target_room: str
    pathway: str
    pressure_migration: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EnvironmentalPressureState:
    facility_pressure: str
    synchronization_drift: str
    topology_fragmentation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FacilityConvergenceProfile:
    convergence_state: str
    shared_hvac_instability: str
    room_recovery_alignment: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CultivationFacilityTopology:
    rooms: list[str]
    pathways: list[dict[str, Any]]
    pressure_state: dict[str, Any]
    convergence_profile: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_multi_room_cognition(intelligence: dict[str, Any]) -> dict[str, Any]:
    room_names = ["Veg A", "Flower 1", "Flower 2", "Drying"]
    dom_paths = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
    pathways = []
    for idx, path in enumerate(dom_paths[:3]):
        pathways.append(
            RoomPropagationPathway(
                source_room=room_names[idx],
                target_room=room_names[idx + 1],
                pathway=path,
                pressure_migration="elevating",
            ).to_dict()
        )
    topology = CultivationFacilityTopology(
        rooms=room_names,
        pathways=pathways,
        pressure_state=EnvironmentalPressureState(
            facility_pressure="moderate_elevated",
            synchronization_drift="present",
            topology_fragmentation="developing",
        ).to_dict(),
        convergence_profile=FacilityConvergenceProfile(
            convergence_state="partial_recovery",
            shared_hvac_instability="shared_load_response_shift",
            room_recovery_alignment="misaligned_night_recovery",
        ).to_dict(),
    )
    return topology.to_dict()

