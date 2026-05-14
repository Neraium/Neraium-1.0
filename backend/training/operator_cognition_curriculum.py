from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ReplayTrainingScenario:
    scenario_id: str
    focus: str
    replay_reference: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OperatorInterpretationExercise:
    exercise_id: str
    objective: str
    evidence_tasks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CognitionTrainingModule:
    module_id: str
    title: str
    scenario: dict[str, Any]
    exercise: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TrainingProgressRecord:
    operator_id: str
    completed_modules: int
    current_focus: str
    proficiency_state: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_operator_cognition_curriculum(intelligence: dict[str, Any]) -> dict[str, Any]:
    modules = [
        CognitionTrainingModule(
            module_id="module-topology-drift",
            title="Reading topology drift",
            scenario=ReplayTrainingScenario(
                scenario_id="scenario-topology-1",
                focus="topology_drift_interpretation",
                replay_reference="replay:topology_drift",
            ).to_dict(),
            exercise=OperatorInterpretationExercise(
                exercise_id="exercise-topology-1",
                objective="Identify drift phase transitions and evidence sufficiency gaps.",
                evidence_tasks=["trace propagation sequence", "validate continuity evidence", "compare memory match"],
            ).to_dict(),
        ).to_dict(),
        CognitionTrainingModule(
            module_id="module-propagation",
            title="Recognizing propagation and compensation masking",
            scenario=ReplayTrainingScenario(
                scenario_id="scenario-propagation-1",
                focus="propagation_pathway_recognition",
                replay_reference="replay:propagation",
            ).to_dict(),
            exercise=OperatorInterpretationExercise(
                exercise_id="exercise-propagation-1",
                objective="Differentiate compensation behavior from reconvergence signals.",
                evidence_tasks=["inspect lineage", "review convergence markers", "assess continuation window"],
            ).to_dict(),
        ).to_dict(),
    ]
    progress = TrainingProgressRecord(
        operator_id="operator-demo",
        completed_modules=1,
        current_focus="convergence_interpretation",
        proficiency_state="developing_structural_reasoning",
    ).to_dict()
    return {"modules": modules, "progress": progress}

