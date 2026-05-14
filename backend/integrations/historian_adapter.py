from __future__ import annotations

from typing import Any


def readiness() -> dict[str, Any]:
    return {"adapter": "historian", "mode": "read_only", "context_import": True, "control_write": False}

