from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class SIIReplayFrameExport:
    frames: list[dict[str, Any]]
    format: str = "sii.replay.v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SIIEvidenceExport:
    lineage: dict[str, Any]
    format: str = "sii.evidence.v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SIIOntologyExport:
    ontology: dict[str, Any]
    format: str = "sii.ontology.v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

