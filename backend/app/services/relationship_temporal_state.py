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
from app.services.telemetry_domain import TelemetryScopeRef
from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope

CONTRACT = "relationship-temporal-compat.v1"
SCHEMA = "relationship-temporal-state.v1"
REDUCER = "relationship_temporal_evidence.v1"
MAX_OBSERVATIONS = 8


def _repository_scope(scope):
    """Adapt the exact authenticated Phase 4 scope to the repository contract."""
    if isinstance(scope, TelemetryScopeRef):
        return scope
    if not isinstance(scope, AuthenticatedPhase4Scope):
        raise TypeError("relationship_temporal_authenticated_scope_required")
    return TelemetryScopeRef(
        tenant_scope_id=scope.tenant_scope_id,
        workspace_id=scope.workspace_id,
        resource_scope_id=scope.resource_scope_id,
        facility_id=scope.workspace_id,
    )


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
            _repository_scope(scope), system_id=system_id, asset_id=asset_id, lineage_ref=descriptor["ref"])
        if stored is None:
            return None
        if not _valid_state(stored, expected, evidence["temporal"]["identity"], _repository_scope(scope),
                            system_id, asset_id, descriptor["ref"]):
            return None
        return stored["reducer_state"]
    except (TypeError, ValueError, KeyError, AttributeError, OverflowError,
            RelationshipTemporalStateConflict):
        return None


def persist_authoritative_relationship_state(repository, scope, *, system_id, asset_id,
                                             result, authorized_scope):
    """Best-effort Phase F write from the successful authoritative result only.

    Every write is reconstructed from the result-local evidence registry and
    producer-issued lineage. Persistence errors are deliberately isolated from
    the completed analysis result.
    """
    try:
        from app.services.relationship_evidence_binding import REGISTRY, digest, resolve
        from app.services.relationship_lineage import verify_for_evidence

        compatibility = result.get("compatibility") if isinstance(result, Mapping) else None
        relationship_model = compatibility.get("relationship_model") if isinstance(compatibility, Mapping) else None
        candidates = relationship_model.get("top_relationship_changes") if isinstance(relationship_model, Mapping) else None
        registry = result.get(REGISTRY) if isinstance(result, Mapping) else None
        if not isinstance(candidates, list) or not isinstance(registry, Mapping):
            return
        repository_scope = _repository_scope(scope)
        for candidate in candidates:
            try:
                if not isinstance(candidate, Mapping):
                    continue
                evidence = resolve(candidate, registry, authorized_scope=authorized_scope,
                                   require_temporal=True)
                if evidence is None or evidence.get("basis") == "global_relationship_model_failure_fallback":
                    continue
                ref = candidate.get("relationship_evidence_ref")
                descriptor = (registry.get("relationship_lineage") or {}).get(ref)
                lineage_ref = candidate.get("relationship_lineage_ref")
                payload = descriptor.get("payload") if isinstance(descriptor, Mapping) else None
                bound_scope = payload.get("scope") if isinstance(payload, Mapping) else None
                if (not isinstance(descriptor, Mapping) or descriptor.get("ref") != lineage_ref
                        or not verify_for_evidence(descriptor, evidence, authorized_scope=authorized_scope)
                        or not isinstance(bound_scope, Mapping)
                        or bound_scope.get("tenant_scope_id") != scope.tenant_scope_id
                        or bound_scope.get("workspace_id") != scope.workspace_id
                        or bound_scope.get("resource_scope_id") != scope.resource_scope_id
                        or bound_scope.get("system_id") != system_id
                        or bound_scope.get("asset_id") != asset_id):
                    continue
                temporal = evidence.get("temporal") or {}
                observations = temporal.get("observations")
                identity = temporal.get("identity")
                if not isinstance(observations, list) or not observations or not isinstance(identity, Mapping):
                    continue
                latest = observations[-1]
                latest_time = datetime.fromisoformat(str(latest.get("observed_at")).replace("Z", "+00:00"))
                window = latest.get("time_window")
                source = evidence.get("source")
                if (latest_time.tzinfo is None or latest_time.utcoffset() is None
                        or not isinstance(window, Mapping)
                        or latest_time.isoformat() != str(window.get("current_end"))
                        or not isinstance(source, Mapping)
                        or candidate.get("relationship_source_ref") != source.get("source_id")
                        or len(observations) > MAX_OBSERVATIONS):
                    continue
                compatibility = compatibility_digest(evidence, descriptor)
                reducer_state = {"version": 1, "identity": dict(identity), "observations": observations}
                interval = {key: window.get(key) for key in ("baseline_start", "baseline_end", "current_start", "current_end")}
                event_ref = digest("relationship-temporal-event.v1", {
                    "lineage_ref": lineage_ref, "source_ref": source["source_id"], "interval": interval,
                })
                current = repository.read_relationship_temporal_state(
                    repository_scope, system_id=system_id, asset_id=asset_id, lineage_ref=lineage_ref)
                if current is not None and current.get("compatibility_digest") != compatibility:
                    continue
                repository.compare_and_swap_relationship_temporal_state(
                    repository_scope, system_id=system_id, asset_id=asset_id, lineage_ref=lineage_ref,
                    compatibility_digest=compatibility, reducer_state=reducer_state,
                    head_event_ref=event_ref, head_event_time=latest_time,
                    expected_revision=current["storage_revision"] if current else 0,
                    expected_head_event_ref=current["head_event_ref"] if current else None,
                )
            except Exception:
                # The governed analysis has completed; state write failures are
                # fail-closed and cannot rewrite its result or status.
                continue
    except Exception:
        return
