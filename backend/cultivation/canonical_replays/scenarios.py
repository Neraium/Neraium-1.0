from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CultivationReplayFrame:
    phase: str
    topology_evolution: str
    propagation_pathway: str
    continuation_window: str
    recovery_state: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReplayNarrativeSequence:
    frames: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CultivationReplayScenario:
    scenario_id: str
    title: str
    sequence: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_cultivation_replay_scenarios() -> dict[str, Any]:
    scenario_titles = [
        "Dehumidification Compensation Progression",
        "Thermal Lag Propagation",
        "VPD Decoupling Emergence",
        "Multi-Room Environmental Fragmentation",
        "Night Recovery Failure",
        "Recovery Reconvergence",
        "Airflow Propagation Instability",
        "Latent Humidity Accumulation",
    ]
    scenarios: list[dict[str, Any]] = []
    for idx, title in enumerate(scenario_titles, start=1):
        frames = [
            CultivationReplayFrame("stable_topology", "coherent environmental loop", "limited", "14-21 days", "stable").to_dict(),
            CultivationReplayFrame("relationship_weakening", "humidity-temperature decoupling", "airflow->thermal lag", "10-14 days", "developing").to_dict(),
            CultivationReplayFrame("compensation_masking", "apparent stability with hidden drift", "thermal->humidity compensation", "7-12 days", "masked").to_dict(),
            CultivationReplayFrame("propagation_activation", "room synchronization drift", "multi-room pressure propagation", "5-9 days", "lagging").to_dict(),
            CultivationReplayFrame("fragmentation", "environmental fragmentation", "VPD decoupling pathway", "3-6 days", "elevated risk").to_dict(),
            CultivationReplayFrame("recovery_or_escalation", "reconvergence or escalation split", "operator intervention pathway", "variable", "conditional").to_dict(),
        ]
        scenarios.append(
            CultivationReplayScenario(
                scenario_id=f"cultivation-scenario-{idx}",
                title=title,
                sequence=ReplayNarrativeSequence(frames=frames).to_dict(),
            ).to_dict()
        )
    return {"scenarios": scenarios}

