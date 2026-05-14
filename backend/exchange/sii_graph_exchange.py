from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class SIIGraphValidationStatus:
    status: str
    evidence_sufficiency: str
    replay_available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SIIGraphFragment:
    fragment_id: str
    archetypes: list[str]
    propagation_chains: list[str]
    convergence_models: list[str]
    evidence_summaries: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SIIGraphExchangePacket:
    packet_id: str
    fragment: SIIGraphFragment
    validation: SIIGraphValidationStatus
    ontology_extensions: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fragment"] = self.fragment.to_dict()
        payload["validation"] = self.validation.to_dict()
        return payload


@dataclass(frozen=True)
class SIIGraphImportResult:
    packet_id: str
    imported: bool
    governance_status: str
    notes: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_graph_exchange_packet(intelligence: dict[str, Any]) -> dict[str, Any]:
    fragment = SIIGraphFragment(
        fragment_id="fragment-latest",
        archetypes=[item.get("name", "") for item in intelligence.get("active_archetypes", [])],
        propagation_chains=intelligence.get("causality_graph", {}).get("dominant_pathways", []),
        convergence_models=[intelligence.get("recovery_convergence", {}).get("convergence_quality", "developing")],
        evidence_summaries=[item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])],
    )
    validation = SIIGraphValidationStatus(
        status="VALIDATED",
        evidence_sufficiency="CORROBORATED",
        replay_available=True,
    )
    packet = SIIGraphExchangePacket(
        packet_id="packet-latest",
        fragment=fragment,
        validation=validation,
        ontology_extensions=[item.get("name", "") for item in intelligence.get("ontology_extension_candidates", [])],
    )
    return packet.to_dict()

