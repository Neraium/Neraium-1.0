from __future__ import annotations

from typing import Any


FORBIDDEN_KEYS = {
    "control_command",
    "actuation_request",
    "automated_action",
    "maintenance_command",
    "closed_loop_output",
}


def enforce_read_only(payload: dict[str, Any]) -> dict[str, Any]:
    keys = set(payload)
    forbidden = sorted(keys & FORBIDDEN_KEYS)
    if forbidden:
        return {
            "allowed": False,
            "reason": f"Read-only guard rejected forbidden keys: {', '.join(forbidden)}",
        }
    return {"allowed": True, "reason": "Payload is read-only compatible."}

