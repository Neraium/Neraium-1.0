from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class SIIEvent:
    event_type: str
    timestamp: str
    payload: dict[str, Any]
    read_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

