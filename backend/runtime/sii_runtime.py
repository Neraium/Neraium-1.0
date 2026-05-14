from __future__ import annotations

from typing import Any

from runtime.runtime_contracts import build_runtime_contract, evaluate_runtime_contract
from runtime.runtime_state import SIIRuntimeState


class SIIRuntime:
    def build_state(self, *, intelligence: dict[str, Any], execution_mode: str = "cloud") -> dict[str, Any]:
        state = SIIRuntimeState(
            topology_cognition_state=intelligence.get("structural_stability_index", {}),
            propagation_state=intelligence.get("causality_graph", {}),
            structural_memory_state=intelligence.get("structural_memory", {}),
            continuation_windows=intelligence.get("counterfactuals", {}).get("progression_scenarios", []),
            evidence_lineage_state=intelligence.get("evidence_lineage", {}),
            replay_frame_state=intelligence.get("replay_timeline", {}),
            behavioral_twin_state=intelligence.get("behavioral_infrastructure_twin", {}),
            cognition_confidence_state=intelligence.get("cognition_confidence", {}),
            execution_mode=execution_mode,
        )
        contract = build_runtime_contract()
        evaluation = evaluate_runtime_contract(read_only_guard=True)
        return {
            "runtime_contract": contract.__dict__,
            "runtime_state": state.to_dict(),
            "runtime_evaluation": evaluation.__dict__,
        }

