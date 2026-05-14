from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class LatentStressIndicator:
    latent_instability: str
    hidden_propagation: str
    compensation_masking_duration: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DelayedSymptomProfile:
    delayed_symptom_emergence: str
    canopy_visibility_lag: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralLeadWindow:
    lead_window: str
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PreVisibilityStructuralState:
    latent_stress: dict[str, Any]
    delayed_symptom_profile: dict[str, Any]
    structural_lead_window: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_pre_visibility_state() -> dict[str, Any]:
    return PreVisibilityStructuralState(
        latent_stress=LatentStressIndicator(
            latent_instability="evidence-backed structural drift present",
            hidden_propagation="room-to-room pressure transfer ongoing",
            compensation_masking_duration="extended",
        ).to_dict(),
        delayed_symptom_profile=DelayedSymptomProfile(
            delayed_symptom_emergence="likely after environmental compensation release",
            canopy_visibility_lag="multi-cycle delay possible",
        ).to_dict(),
        structural_lead_window=StructuralLeadWindow(
            lead_window="early structural lead window available",
            interpretation="relationships changed before visible crop stress signatures",
        ).to_dict(),
    ).to_dict()

