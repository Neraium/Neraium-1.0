from __future__ import annotations

from typing import Any


def replay_frame_packet(*, frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_type": "ReplayFramePacket",
        "frame": frame,
        "cached_for_disconnected_mode": True,
        "read_only": True,
    }

