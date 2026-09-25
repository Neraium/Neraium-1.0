"""Deterministic identity for producer-authorized relationship candidates.

This identity is metadata, not an authorization capability or temporal state.
"""
from copy import deepcopy

from app.services.relationship_evidence_binding import digest
from app.services.phase4_scope import ServerBoundSystemIdentityV2
from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope

CONTRACT = "relationship-lineage.v1"
SEMANTICS = "linear_correlation.v1"
REF = "relationship_lineage_ref"


def issue(endpoint_identity, source, evidence, *, authorized_scope=None, authenticated_scope=None,
          phase4_system_identity=None, asset_id=None, observation_lineage=None):
    """Return a verifiable lineage descriptor, or None when authority is absent."""
    try:
        if not isinstance(endpoint_identity, dict) or endpoint_identity.get("contract") != "relationship-endpoint-identity.v1":
            return None
        scope = endpoint_identity.get("scope")
        if not isinstance(scope, dict) or not all(scope.get(k) for k in ("tenant_scope_id", "workspace_id", "resource_scope_id", "system_id", "asset_id")):
            return None
        authority_digest = endpoint_identity.get("mapping_authority_digest")
        if not isinstance(authority_digest, str) or not authority_digest.strip():
            return None
        if (not isinstance(authenticated_scope, AuthenticatedPhase4Scope)
                or not isinstance(phase4_system_identity, ServerBoundSystemIdentityV2) or asset_id is None):
            return None
        if any(scope.get(key) != value for key, value in authenticated_scope.as_dict().items()):
            return None
        if (
            scope.get("system_id") != getattr(phase4_system_identity, "system_id", None)
            or scope.get("resource_scope_id") != getattr(phase4_system_identity, "resource_scope_id", None)
            or endpoint_identity.get("mapping_authority_digest") != getattr(phase4_system_identity, "authority_record_digest", None)
            or scope.get("asset_id") != asset_id
        ):
            return None
        phase4_scope = authenticated_scope.as_dict()
        if authorized_scope != digest("relationship-scope.v1", phase4_scope):
            return None
        if not isinstance(observation_lineage, (list, tuple)) or not observation_lineage:
            return None
        authoritative_mappings = {}
        for observation in observation_lineage:
            signal_id = getattr(observation, "canonical_signal_id", None)
            mapping_id = getattr(observation, "mapping_id", None)
            revision = getattr(observation, "mapping_revision", None)
            if (not signal_id or not mapping_id or type(revision) is not int or revision < 1
                    or getattr(observation, "system_id", None) != phase4_system_identity.system_id
                    or getattr(observation, "asset_id", None) != asset_id
                    or getattr(observation, "mapping_authority_digest", None) != authority_digest):
                return None
            authoritative_mappings.setdefault(signal_id, set()).add((mapping_id, revision))
        endpoints = endpoint_identity.get("endpoints")
        ids = [item.get("canonical_signal_id") for item in endpoints if isinstance(item, dict)]
        provenance = {}
        for item in endpoints:
            if not isinstance(item, dict):
                return None
            signal_id = item.get("canonical_signal_id")
            mappings = item.get("mapping_provenance")
            if not isinstance(signal_id, str) or not signal_id or not isinstance(mappings, list) or not mappings:
                return None
            normalized = []
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    return None
                mapping_id = mapping.get("mapping_id")
                revision = mapping.get("mapping_revision")
                if not isinstance(mapping_id, str) or not mapping_id.strip() or type(revision) is not int or revision < 1:
                    return None
                normalized.append({"mapping_id": mapping_id, "mapping_revision": revision})
            if normalized != sorted(normalized, key=lambda value: (value["mapping_id"], value["mapping_revision"])):
                return None
            provenance[signal_id] = normalized
            if set((item["mapping_id"], item["mapping_revision"]) for item in normalized) != authoritative_mappings.get(signal_id):
                return None
        if set(authoritative_mappings) != set(provenance):
            return None
        columns = source.get("columns")
        if len(ids) != len(endpoints) or len(set(ids)) != len(ids) or len(columns or []) != 2:
            return None
        if not set(columns).issubset(set(ids)):
            return None
        basis = evidence.get("basis")
        if basis not in {"global_relationship_model", "mode_conditioned_relationships", "global_relationship_model_failure_fallback"}:
            return None
        if basis == "mode_conditioned_relationships":
            mode = (evidence.get("context") or {}).get("mode_conditioning") or {}
            selection = source.get("selection") or {}
            if not mode.get("mode_id") or mode.get("mode_id") != selection.get("mode_id") or not isinstance(mode.get("features"), dict) or mode.get("features") != selection.get("features"):
                return None
            mode_identity = {"mode_id": mode["mode_id"], "features": deepcopy(mode["features"])}
        else:
            mode_identity = None
        payload = {
            "contract": CONTRACT,
            "scope_ref": digest("relationship-scope.v1", scope),
            "scope": deepcopy(scope),
            "mapping_authority_digest": authority_digest,
            "endpoints": sorted(columns),
            "endpoint_provenance": {key: provenance[key] for key in sorted(columns)},
            "relationship_semantics": SEMANTICS,
            "semantic_version": source.get("method"),
            "assessment_basis": basis,
            "mode_identity": mode_identity,
        }
        return {"ref": digest(CONTRACT, payload), "payload": payload,
                "continuation_eligible": basis != "global_relationship_model_failure_fallback"}
    except (TypeError, ValueError, KeyError):
        return None


def verify(descriptor):
    try:
        payload = descriptor["payload"]
        return (payload.get("contract") == CONTRACT
                and descriptor.get("ref") == digest(CONTRACT, payload)
                and descriptor.get("continuation_eligible") is (payload.get("assessment_basis") != "global_relationship_model_failure_fallback"))
    except (TypeError, ValueError, KeyError):
        return False


def verify_for_evidence(descriptor, evidence, *, authorized_scope):
    """Verify the descriptor against the already resolved, authorized evidence."""
    try:
        if not verify(descriptor):
            return False
        payload = descriptor["payload"]
        source = evidence["source"]
        scope = payload["scope"]
        phase4_scope = {key: scope.get(key) for key in (
            "version", "tenant_scope_id", "workspace_id", "resource_scope_id"
        )}
        basis = evidence["basis"]
        mode = (evidence.get("context") or {}).get("mode_conditioning") or {}
        expected_mode = ({"mode_id": mode.get("mode_id"), "features": mode.get("features")}
                         if basis == "mode_conditioned_relationships" else None)
        selected_mode = (source.get("selection") or {}) if basis == "mode_conditioned_relationships" else None
        return (
            digest("relationship-scope.v1", phase4_scope) == authorized_scope
            and payload.get("scope_ref") == digest("relationship-scope.v1", scope)
            and all(scope.get(key) for key in ("system_id", "asset_id"))
            and set(payload.get("endpoints") or ()) == set(source.get("columns") or ())
            and payload.get("assessment_basis") == basis
            and payload.get("relationship_semantics") == SEMANTICS
            and payload.get("semantic_version") == source.get("method")
            and payload.get("mode_identity") == expected_mode
            and (basis != "mode_conditioned_relationships" or expected_mode == selected_mode)
            and descriptor.get("continuation_eligible") is (basis != "global_relationship_model_failure_fallback")
            and isinstance(payload.get("mapping_authority_digest"), str)
            and bool(payload["mapping_authority_digest"].strip())
            and set(payload.get("endpoint_provenance") or {}) == set(source.get("columns") or ())
            and all(_valid_provenance(payload["endpoint_provenance"].get(column)) for column in source["columns"])
        )
    except (TypeError, ValueError, KeyError, AttributeError):
        return False


def _valid_provenance(value):
    if not isinstance(value, list) or not value:
        return False
    return all(
        isinstance(item, dict)
        and isinstance(item.get("mapping_id"), str) and bool(item["mapping_id"].strip())
        and type(item.get("mapping_revision")) is int and item["mapping_revision"] > 0
        for item in value
    )
