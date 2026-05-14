from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SparseTelemetryCognitionState:
    telemetry_density: str
    confidence_constraints: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DisconnectedReplayPacket:
    replay_window: str
    packet_integrity: str
    delayed_sync_tolerance: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class HighUncertaintyEvidenceBundle:
    uncertainty_factors: list[str]
    corroboration_strategy: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExtremeEnvironmentCognitionProfile:
    contexts: list[str]
    sparse_telemetry_state: dict[str, Any]
    disconnected_replay_packet: dict[str, Any]
    uncertainty_bundle: dict[str, Any]
    constrained_intervention_window: str
    long_duration_memory_requirements: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_extreme_environment_cognition_profile() -> dict[str, Any]:
    return ExtremeEnvironmentCognitionProfile(
        contexts=[
            "aerospace_systems",
            "defense_installations",
            "remote_industrial_sites",
            "underwater_infrastructure",
            "space_adjacent_systems",
            "disconnected_facilities",
        ],
        sparse_telemetry_state=SparseTelemetryCognitionState(
            telemetry_density="sparse_or_bursty",
            confidence_constraints=["limited_signal_frequency", "missing_intermediate_state_visibility"],
        ).to_dict(),
        disconnected_replay_packet=DisconnectedReplayPacket(
            replay_window="delayed_sync_operational_window",
            packet_integrity="evidence_lineage_preserved",
            delayed_sync_tolerance="high",
        ).to_dict(),
        uncertainty_bundle=HighUncertaintyEvidenceBundle(
            uncertainty_factors=["communication_delay", "intervention_latency", "partial_observability"],
            corroboration_strategy="cross-subsystem lineage corroboration with replay fallback",
        ).to_dict(),
        constrained_intervention_window="compressed_due_to_high_uncertainty",
        long_duration_memory_requirements=["multi-cycle structural memory", "extended replay retention"],
    ).to_dict()

