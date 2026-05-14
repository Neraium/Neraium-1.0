from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from federation.federated_cognition_exchange import build_federated_exchange_payload


@dataclass(frozen=True)
class FederatedBehaviorPrimitive:
    primitive: str
    validation_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FederatedReplaySummary:
    replay_reference: str
    replay_support: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FederatedOntologyContribution:
    candidate: str
    governance_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FederatedValidationRecord:
    provenance: str
    auditability: str
    privacy_constraints: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InfrastructureCognitionFederation:
    exchange_payload: dict[str, Any]
    behavior_primitives: list[dict[str, Any]]
    replay_summaries: list[dict[str, Any]]
    ontology_contributions: list[dict[str, Any]]
    validation_record: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_infrastructure_cognition_federation(intelligence: dict[str, Any]) -> dict[str, Any]:
    exchange = build_federated_exchange_payload(intelligence)
    behavior_primitives = [
        FederatedBehaviorPrimitive(primitive=item.get("signature", ""), validation_status="validated").to_dict()
        for item in exchange.get("primitives", [])[:8]
    ]
    replay_summaries = [
        FederatedReplaySummary(replay_reference=f"replay:{idx}", replay_support="replay_backed").to_dict()
        for idx, _ in enumerate(exchange.get("primitives", [])[:4])
    ]
    ontology_contributions = [
        FederatedOntologyContribution(candidate="compression_variant", governance_status="under_review").to_dict()
    ]
    validation_record = FederatedValidationRecord(
        provenance="federated_structural_cognition_exchange",
        auditability="traceable",
        privacy_constraints="raw_telemetry_excluded",
    ).to_dict()
    return InfrastructureCognitionFederation(
        exchange_payload=exchange,
        behavior_primitives=behavior_primitives,
        replay_summaries=replay_summaries,
        ontology_contributions=ontology_contributions,
        validation_record=validation_record,
    ).to_dict()

