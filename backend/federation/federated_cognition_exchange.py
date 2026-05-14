from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from federation.cognition_primitive_export import export_primitives
from federation.federation_policy import default_federation_policy
from federation.privacy_preserving_payloads import sanitize_for_federation


@dataclass(frozen=True)
class FederationExchangePayload:
    federation_id: str
    policy: dict[str, Any]
    primitives: list[dict[str, Any]]
    privacy_preserving_summary: dict[str, Any]
    exchange_scope: str = "cross_facility_structural_cognition"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_federated_exchange_payload(
    intelligence: dict[str, Any],
    *,
    federation_id: str = "federation-default",
    facility_hash: str = "facility-anonymized",
) -> dict[str, Any]:
    policy = default_federation_policy()
    payload = FederationExchangePayload(
        federation_id=federation_id,
        policy=policy.to_dict(),
        primitives=export_primitives(intelligence),
        privacy_preserving_summary=sanitize_for_federation(intelligence, facility_hash=facility_hash).to_dict(),
    )
    return payload.to_dict()

