from __future__ import annotations

from typing import Any


def build_graph_memory_store(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "latest_snapshot": snapshot,
        "history_count": 1 if snapshot else 0,
        "storage_mode": "in_memory_reference",
    }

