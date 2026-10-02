"""Endpoint-keyed relationship lineage and immutable artifact projection.

Only an explicitly constructed V2 window can issue this lineage. This module
does not consume V1 relationship lineage or longitudinal memory, and no
production analytical caller selects it yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields
import json
from typing import Any

from app.services.authority_contract_common import canonical_json_bytes
from app.services.relationship_evidence_binding import digest
from app.services.telemetry_analysis_window_v2 import (
    EndpointAnalysisWindowV2,
    EndpointRelationshipPairV2,
    RELATIONSHIP_PAIR_VERSION,
    WINDOW_VERSION,
)
from app.services.telemetry_endpoint_identity import PhysicalEndpointIdentity


CONTRACT = "relationship-lineage.v2"
ARTIFACT_CONTRACT = "telemetry-relationship-artifact.v2"
OBSERVATION_REF_CONTRACT = "relationship-observation-refs.v2"
MAX_ARTIFACT_BYTES = 1_000_000
_IDENTITY_FIELDS = {field.name for field in fields(PhysicalEndpointIdentity)}
_LINEAGE_FIELDS = {
    "contract_version", "window_contract_version", "window_id", "source_run_id",
    "scope", "schema_fingerprint", "window_content_digest", "pair_ref",
    "source_endpoint", "target_endpoint", "source_observation_count",
    "target_observation_count", "observation_ref_digest",
}


class RelationshipLineageV2Error(ValueError):
    """A V2 identity, artifact, or readback invariant failed."""


def _endpoint(value: Any) -> PhysicalEndpointIdentity:
    if not isinstance(value, Mapping) or set(value) != _IDENTITY_FIELDS:
        raise RelationshipLineageV2Error("relationship_v2_endpoint_fields_invalid")
    try:
        return PhysicalEndpointIdentity(**value)
    except (TypeError, ValueError) as exc:
        raise RelationshipLineageV2Error("relationship_v2_endpoint_invalid") from exc


def _pair_observations(window: EndpointAnalysisWindowV2, pair: EndpointRelationshipPairV2) -> list[dict[str, Any]]:
    keys = {
        (pair.source.connection_id, pair.source.external_signal_id),
        (pair.target.connection_id, pair.target.external_signal_id),
    }
    return sorted(
        (item.as_dict() for item in window.observation_lineage
         if (item.connection_id, item.external_signal_id) in keys),
        key=lambda item: item["observation_id"],
    )


def issue(window: EndpointAnalysisWindowV2, pair: EndpointRelationshipPairV2) -> dict[str, Any]:
    """Issue a deterministic descriptor from the analyzed V2 window and pair."""
    if not isinstance(window, EndpointAnalysisWindowV2) or not isinstance(pair, EndpointRelationshipPairV2):
        raise RelationshipLineageV2Error("relationship_v2_window_pair_required")
    if pair.contract_version != RELATIONSHIP_PAIR_VERSION or pair.schema_fingerprint != window.schema_fingerprint:
        raise RelationshipLineageV2Error("relationship_v2_pair_schema_mismatch")
    expected = window.relationship_pair(pair.source.endpoint_id, pair.target.endpoint_id)
    if expected != pair:
        raise RelationshipLineageV2Error("relationship_v2_pair_mismatch")
    observations = _pair_observations(window, pair)
    source_count = sum(item["external_signal_id"] == pair.source.external_signal_id
                       and item["connection_id"] == pair.source.connection_id for item in observations)
    target_count = len(observations) - source_count
    if not source_count or not target_count:
        raise RelationshipLineageV2Error("relationship_v2_observations_missing")
    payload = {
        "contract_version": CONTRACT,
        "window_contract_version": WINDOW_VERSION,
        "window_id": window.window_id,
        "source_run_id": window.source_run_id,
        "scope": {
            "tenant_scope_id": window.scope.tenant_scope_id,
            "workspace_id": window.scope.workspace_id,
            "resource_scope_id": window.scope.resource_scope_id,
            "facility_id": window.scope.facility_id,
            "system_id": window.system_identity.system_id,
            "asset_id": window.asset_id,
        },
        "schema_fingerprint": window.schema_fingerprint,
        "window_content_digest": window.content_digest,
        "pair_ref": pair.ref,
        "source_endpoint": pair.source.as_dict(),
        "target_endpoint": pair.target.as_dict(),
        "source_observation_count": source_count,
        "target_observation_count": target_count,
        "observation_ref_digest": digest(OBSERVATION_REF_CONTRACT, observations),
    }
    return {"ref": digest(CONTRACT, payload), "payload": payload}


def verify(descriptor: Any, *, window: EndpointAnalysisWindowV2,
           pair: EndpointRelationshipPairV2) -> bool:
    """Require exact replay of the original window and physical endpoint pair."""
    try:
        if not isinstance(descriptor, Mapping) or set(descriptor) != {"ref", "payload"}:
            return False
        payload = descriptor["payload"]
        if not isinstance(payload, Mapping) or set(payload) != _LINEAGE_FIELDS:
            return False
        if payload.get("contract_version") != CONTRACT or payload.get("window_contract_version") != WINDOW_VERSION:
            return False
        if _endpoint(payload["source_endpoint"]) != pair.source or _endpoint(payload["target_endpoint"]) != pair.target:
            return False
        return dict(descriptor) == issue(window, pair)
    except (RelationshipLineageV2Error, TypeError, ValueError, KeyError, AttributeError):
        return False


def build_artifact(
    window: EndpointAnalysisWindowV2, pair: EndpointRelationshipPairV2,
    *, result: Mapping[str, Any], evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Wrap opaque numerical output with non-overridable endpoint authority."""
    if not isinstance(result, Mapping) or not isinstance(evidence, Mapping):
        raise RelationshipLineageV2Error("relationship_v2_result_evidence_required")
    descriptor = issue(window, pair)
    try:
        result_copy = json.loads(canonical_json_bytes(result))
        evidence_copy = json.loads(canonical_json_bytes(evidence))
    except (TypeError, ValueError) as exc:
        raise RelationshipLineageV2Error("relationship_v2_payload_invalid") from exc
    payload = {
        "contract_version": ARTIFACT_CONTRACT,
        "lineage": descriptor,
        "result": {"relationship_lineage_ref": descriptor["ref"], "payload": result_copy},
        "evidence": {"relationship_lineage_ref": descriptor["ref"], "payload": evidence_copy},
    }
    encoded = canonical_json_bytes(payload)
    if len(encoded) > MAX_ARTIFACT_BYTES:
        raise RelationshipLineageV2Error("relationship_v2_artifact_too_large")
    return {"ref": digest(ARTIFACT_CONTRACT, payload), "payload": payload}


def readback(
    stored: Any, *, window: EndpointAnalysisWindowV2, pair: EndpointRelationshipPairV2,
) -> dict[str, Any]:
    """Verify persisted bytes and their exact V2 analytical origin."""
    if isinstance(stored, str):
        try:
            stored = json.loads(stored)
        except (TypeError, ValueError) as exc:
            raise RelationshipLineageV2Error("relationship_v2_artifact_invalid") from exc
    if not isinstance(stored, Mapping) or set(stored) != {"ref", "payload"}:
        raise RelationshipLineageV2Error("relationship_v2_artifact_invalid")
    payload = stored.get("payload")
    if not isinstance(payload, Mapping) or set(payload) != {"contract_version", "lineage", "result", "evidence"}:
        raise RelationshipLineageV2Error("relationship_v2_artifact_invalid")
    if payload.get("contract_version") != ARTIFACT_CONTRACT:
        raise RelationshipLineageV2Error("relationship_v2_artifact_version_invalid")
    descriptor = payload["lineage"]
    if not verify(descriptor, window=window, pair=pair):
        raise RelationshipLineageV2Error("relationship_v2_lineage_mismatch")
    for field in ("result", "evidence"):
        item = payload[field]
        if (not isinstance(item, Mapping) or set(item) != {"relationship_lineage_ref", "payload"}
                or item.get("relationship_lineage_ref") != descriptor["ref"]
                or not isinstance(item.get("payload"), Mapping)):
            raise RelationshipLineageV2Error("relationship_v2_evidence_identity_mismatch")
    try:
        expected_ref = digest(ARTIFACT_CONTRACT, payload)
        if len(canonical_json_bytes(payload)) > MAX_ARTIFACT_BYTES or stored["ref"] != expected_ref:
            raise RelationshipLineageV2Error("relationship_v2_artifact_digest_mismatch")
    except (TypeError, ValueError) as exc:
        if isinstance(exc, RelationshipLineageV2Error):
            raise
        raise RelationshipLineageV2Error("relationship_v2_artifact_invalid") from exc
    return deepcopy(dict(stored))
