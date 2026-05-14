from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TrainingReplay:
    replay_id: str
    focus: str
    frame_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrainingScenario:
    scenario_id: str
    title: str
    objective: str
    replay: TrainingReplay

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["replay"] = self.replay.to_dict()
        return payload


@dataclass(frozen=True)
class OperatorAssessment:
    operator_id: str
    scenario_id: str
    outcome: str
    evidence_interpretation_score: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CognitionTrainingProgress:
    operator_id: str
    completed_scenarios: int
    active_focus: str
    proficiency_state: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_training_payload(intelligence: dict[str, Any]) -> dict[str, Any]:
    timeline = intelligence.get("replay_timeline", {}).get("timeline", [])
    scenarios = [
        TrainingScenario(
            scenario_id="scenario-relationship-decay",
            title="Identify relationship decay",
            objective="Recognize relationship weakening before subsystem fragmentation.",
            replay=TrainingReplay(replay_id="replay-rd-1", focus="relationship_decay", frame_count=len(timeline)),
        ),
        TrainingScenario(
            scenario_id="scenario-compensation-masking",
            title="Interpret compensation masking",
            objective="Differentiate temporary compensation from structural reconvergence.",
            replay=TrainingReplay(replay_id="replay-cm-1", focus="compensation_masking", frame_count=len(timeline)),
        ),
    ]
    assessment = OperatorAssessment(
        operator_id="operator-demo",
        scenario_id=scenarios[0].scenario_id,
        outcome="evidence review complete",
        evidence_interpretation_score="STRONG_CONVERGENCE",
    )
    progress = CognitionTrainingProgress(
        operator_id="operator-demo",
        completed_scenarios=1,
        active_focus="propagation pathway interpretation",
        proficiency_state="developing_operational_cognition",
    )
    return {
        "scenarios": [item.to_dict() for item in scenarios],
        "latest_assessment": assessment.to_dict(),
        "training_progress": progress.to_dict(),
    }

