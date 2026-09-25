"""Phase D read-only gate for governed relationship temporal state.

This module validates authority and compatibility and returns stored state to
an explicit caller. It does not pass state to an analytical reducer.
"""
from datetime import datetime
import hashlib
import json
import math
from collections.abc import Mapping

from app.services.relationship_evidence_binding import REF, resolve
from app.services.relationship_lineage import verify_for_evidence
from app.services.telemetry_repository import (
    RelationshipTemporalStateConflict,
    _relationship_state_identity,
    _relationship_state_payload,
)

CONTRACT = "relationship-temporal-compat.v1"
SCHEMA = "relationship-temporal-state.v1"
REDUCER = "relationship_temporal_evidence.v1"
MAX_OBSERVATIONS = 8


def compatibility_digest(record: Mapping, lineage: Mapping) -> str:
    """Derive compatibility solely from certified semantic and reducer inputs."""
    temporal = record.get("temporal")
    if (not isinstance(temporal, Mapping) or temporal.get("status") != "available"
            or temporal.get("method") != REDUCER):
        raise ValueError("relationship_temporal_compatibility_unavailable")
    payload = lineage.get("payload")
    if not isinstance(payload, Mapping):
        raise ValueError("relationship_temporal_lineage_unavailable")
    compatible = {
        "contract": CONTRACT,
        "lineage_ref": lineage.get("ref"),
        "scope_ref": payload.get("scope_ref"),
        "system_id": payload.get("scope", {}).get("system_id"),
        "asset_id": payload.get("scope", {}).get("asset_id"),
        "endpoints": payload.get("endpoints"),
        "relationship_semantics": payload.get("relationship_semantics"),
        "semantic_version": payload.get("semantic_version"),
        "assessment_basis": payload.get("assessment_basis"),
        "mode_identity": payload.get("mode_identity"),
        "reducer_contract": REDUCER,
        "reducer_version": 1,
        "reducer_identity": temporal.get("identity"),
        "reducer_parameters": temporal.get("parameters"),
        "reference": record.get("reference"),
        "context": record.get("context"),
    }
    return hashlib.sha256(json.dumps(compatible, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def _valid_state(record, expected_compatibility, expected_identity, scope, system_id, asset_id, lineage_ref):
    if not isinstance(record, Mapping):
        return False
    state = record.get("reducer_state")
    observations = state.get("observations") if isinstance(state, Mapping) else None
    if (record.get("state_schema") != SCHEMA
            or record.get("compatibility_digest") != expected_compatibility
            or type(record.get("storage_revision")) is not int or record["storage_revision"] < 1
            or not isinstance(record.get("head_event_ref"), str) or not record["head_event_ref"].strip()
            or not isinstance(record.get("head_event_time"), datetime)
            or record["head_event_time"].tzinfo is None
            or record["head_event_time"].utcoffset() is None
            or not isinstance(state, Mapping) or state.get("version") != 1
            or state.get("identity") != expected_identity
            or not isinstance(observations, list) or not observations
            or len(observations) > MAX_OBSERVATIONS):
        return False
    times = []
    for item in observations:
        if (not isinstance(item, Mapping)
                or not {"observed_at", "time_window", "source_rows", "source_dataset_id",
                        "signed_correlation_delta", "edge_confidence", "data_quality_factor",
                        "eligible", "acceptable"}.issubset(item)
                or not isinstance(item.get("time_window"), Mapping)
                or not isinstance(item.get("source_rows"), list)
                or type(item.get("eligible")) is not bool
                or type(item.get("acceptable")) is not bool):
            return False
        observed = item.get("observed_at")
        try:
            at = datetime.fromisoformat(str(observed).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return False
        try:
            values = [float(item[key]) for key in
                      ("signed_correlation_delta", "edge_confidence", "data_quality_factor")]
        except (TypeError, ValueError, OverflowError):
            return False
        if (at.tzinfo is None or at.utcoffset() is None
                or not all(math.isfinite(value) for value in values)):
            return False
        times.append(at)
    if any(a >= b for a, b in zip(times, times[1:])):
        return False
    if times[-1] != record["head_event_time"]:
        return False
    identity = _relationship_state_identity(scope, system_id, asset_id, lineage_ref)
    _body, calculated_digest = _relationship_state_payload(
        identity, record["compatibility_digest"], state,
        head_event_ref=record["head_event_ref"], head_event_time=record["head_event_time"])
    if record.get("state_digest") != calculated_digest:
        return False
    return True


def load_prior_relationship_state(repository, scope, *, system_id, asset_id,
                                  candidate, registry, authorized_scope):
    """Load one exact Phase C key only after A/B and compatibility validation.

    Returns None for absent or unusable state. A successful result is inert
    metadata; the caller must not feed it into current-run analysis in Phase D.
    """
    try:
        if not isinstance(candidate, Mapping) or candidate.get("relationship_lineage_ref") is None:
            return None
        evidence = resolve(candidate, registry, authorized_scope=authorized_scope,
                           require_temporal=True)
        if evidence is None or evidence.get("basis") == "global_relationship_model_failure_fallback":
            return None
        descriptor = (registry.get("relationship_lineage") or {}).get(candidate.get(REF))
        if (not isinstance(descriptor, Mapping)
                or descriptor.get("ref") != candidate.get("relationship_lineage_ref")
                or not verify_for_evidence(descriptor, evidence, authorized_scope=authorized_scope)):
            return None
        payload = descriptor["payload"]
        identity_scope = payload.get("scope") or {}
        if (identity_scope.get("system_id") != system_id or identity_scope.get("asset_id") != asset_id
                or identity_scope.get("tenant_scope_id") != scope.tenant_scope_id
                or identity_scope.get("workspace_id") != scope.workspace_id
                or identity_scope.get("resource_scope_id") != scope.resource_scope_id):
            return None
        if payload.get("assessment_basis") not in {"global_relationship_model", "mode_conditioned_relationships"}:
            return None
        expected = compatibility_digest(evidence, descriptor)
        stored = repository.read_relationship_temporal_state(
            scope, system_id=system_id, asset_id=asset_id, lineage_ref=descriptor["ref"])
        if stored is None:
            return None
        if not _valid_state(stored, expected, evidence["temporal"]["identity"], scope,
                            system_id, asset_id, descriptor["ref"]):
            return None
        return stored["reducer_state"]
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError,
            RelationshipTemporalStateConflict):
        return None
