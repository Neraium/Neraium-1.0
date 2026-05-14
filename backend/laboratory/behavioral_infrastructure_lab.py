from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SimulatedTopologyEvolution:
    phase_sequence: list[str]
    drift_direction: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SimulatedPropagationEcosystem:
    pathways: list[str]
    propagation_intensity: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorLabScenario:
    scenario_id: str
    title: str
    focus: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorLabRun:
    run_id: str
    scenario_id: str
    replay_frames: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BehaviorLabResult:
    scenario: dict[str, Any]
    run: dict[str, Any]
    topology_evolution: dict[str, Any]
    propagation_ecosystem: dict[str, Any]
    evidence_output: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_behavior_lab(intelligence: dict[str, Any]) -> dict[str, Any]:
    scenario = BehaviorLabScenario(
        scenario_id="lab-scenario-1",
        title="Propagation ecosystem under environmental stress",
        focus="propagation_and_convergence_dynamics",
    )
    frame_count = len(intelligence.get("replay_timeline", {}).get("timeline", []))
    run = BehaviorLabRun(
        run_id="lab-run-latest",
        scenario_id=scenario.scenario_id,
        replay_frames=frame_count,
    )
    result = BehaviorLabResult(
        scenario=scenario.to_dict(),
        run=run.to_dict(),
        topology_evolution=SimulatedTopologyEvolution(
            phase_sequence=[
                "stable_topology",
                "relationship_weakening",
                "pressure_migration",
                "propagation_activation",
                "recovery_or_escalation",
            ],
            drift_direction="toward_fragmentation_then_partial_recovery",
        ).to_dict(),
        propagation_ecosystem=SimulatedPropagationEcosystem(
            pathways=intelligence.get("causality_graph", {}).get("dominant_pathways", [])[:5],
            propagation_intensity="moderate_to_elevated",
        ).to_dict(),
        evidence_output=[item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])][:8],
    )
    return result.to_dict()

