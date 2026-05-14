from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class FederationPolicy:
    allow_raw_telemetry: bool
    allow_control_payloads: bool
    allowed_exports: list[str]
    privacy_requirements: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_federation_policy() -> FederationPolicy:
    return FederationPolicy(
        allow_raw_telemetry=False,
        allow_control_payloads=False,
        allowed_exports=[
            "archetype_signatures",
            "topology_state_summaries",
            "propagation_primitives",
            "convergence_patterns",
            "structural_memory_matches",
            "evidence_summaries",
            "replay_fingerprints",
            "ontology_extensions",
        ],
        privacy_requirements=[
            "remove_customer_identifiers",
            "remove_raw_telemetry",
            "retain_replay_reference_hashes_only",
        ],
    )

