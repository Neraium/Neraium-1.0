from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class SIIRuntimeState:
    topology_cognition_state: dict[str, Any]
    propagation_state: dict[str, Any]
    structural_memory_state: dict[str, Any]
    continuation_windows: list[dict[str, Any]]
    evidence_lineage_state: dict[str, Any]
    replay_frame_state: dict[str, Any]
    behavioral_twin_state: dict[str, Any]
    cognition_confidence_state: dict[str, Any]
    execution_mode: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

