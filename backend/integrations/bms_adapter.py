from __future__ import annotations

from typing import Any


def readiness() -> dict[str, Any]:
    return {"adapter": "bms", "mode": "read_only", "telemetry_pull": True, "control_write": False}

