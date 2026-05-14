from __future__ import annotations

from typing import Any


def readiness() -> dict[str, Any]:
    return {"adapter": "digital_twin", "mode": "read_only", "replay_export": True, "control_write": False}

