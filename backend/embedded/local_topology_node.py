from __future__ import annotations

from typing import Any


def local_topology_state(*, node_id: str, drift_index: float, coherence_state: str) -> dict[str, Any]:
    return {
        "event_type": "LocalTopologyState",
        "node_id": node_id,
        "drift_index": drift_index,
        "coherence_state": coherence_state,
        "read_only": True,
    }

