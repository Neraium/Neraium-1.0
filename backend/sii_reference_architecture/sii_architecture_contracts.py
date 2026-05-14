from __future__ import annotations

from typing import Any

from sii_reference_architecture.sii_layers import sii_layers


def build_sii_architecture_contracts() -> dict[str, Any]:
    contracts = []
    for item in sii_layers():
        contracts.append(
            {
                "layer": item["name"],
                "contract": {
                    "required_inputs": item["inputs"],
                    "required_evidence": item["evidence_requirements"],
                    "required_audit_fields": ["timestamp", "lineage_ref", "replay_ref"],
                    "required_outputs": item["outputs"],
                    "failure_mode_signals": item["failure_modes"],
                },
            }
        )
    return {
        "contracts": contracts,
        "global_requirements": {
            "replayable": True,
            "auditable": True,
            "evidence_driven": True,
            "operator_explainable": True,
            "non_actuating": True,
        },
    }

