from __future__ import annotations

from typing import Any


def embedded_cognition_event(*, topology_state: dict[str, Any], evidence_lineage: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": "EmbeddedCognitionEvent",
        "topology_state": topology_state,
        "evidence_lineage": evidence_lineage,
        "read_only": True,
    }

