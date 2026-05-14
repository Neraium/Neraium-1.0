from __future__ import annotations

from typing import Any


def facility_cognition_relay_payload(*, facility_id: str, cognition_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": "FacilityCognitionRelayPayload",
        "facility_id": facility_id,
        "cognition_state": cognition_state,
        "read_only": True,
    }

