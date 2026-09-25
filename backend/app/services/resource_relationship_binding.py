"""Prospective producer lineage and exact resource/assessment integrity.

Like relationship bindings, these hashes are integrity seals, not signatures or
access tokens. Callers supply an already authorized result-local registry.
"""
from copy import deepcopy

from app.services.relationship_evidence_binding import (
    OWNER_REF, REF, ASSESSMENT_BINDING, SOURCE, digest, resolve, valid_source, assessment_binding,
)

LINEAGE = "resource_relationship_source_ref"
BINDING = "resource_relationship_binding"
TUPLE = (OWNER_REF, REF, ASSESSMENT_BINDING)
VERSION = "resource-relationship.v1"
# Only calculation/provenance inputs participate; presentation and ranking do not.
RESOURCE_FIELDS = (
    "status", "target_signal", "predictor_signals", "source_relationships",
    "model_type", "model_version", "model_parameters", "training_window",
    "source_model_version", "operating_mode", "observations", "max_gap_seconds",
    "observation_methodology", LINEAGE,
)


def source_lineage(edge):
    """Called on the actual edge consumed by a producer, never a name lookup."""
    try:
        return edge[SOURCE]["source_id"] if valid_source(edge) else None
    except (KeyError, TypeError, ValueError):
        return None


def ownership(value):
    if not isinstance(value, dict):
        return None
    if not all(isinstance(value.get(key), str) and value[key] for key in TUPLE):
        return None
    return {key: value[key] for key in TUPLE}


def _payload(resource, owner):
    return {"version": VERSION, **owner, "resource": {
        key: deepcopy(resource[key]) for key in RESOURCE_FIELDS if key in resource
    }}


def finalize_resources(expected_behavior, registry, *, authorized_scope):
    """New-result producer only; no historical reads, repair, or pair matching.

    The rate model carries the exact source selected during training. Only a
    unique final record for that very source can complete ownership using the
    certified assessment-binding function. Candidate ranking is not an input.
    A new comparison source cannot adopt a model's old source lineage.
    """
    if not isinstance(expected_behavior, dict):
        return
    resources = expected_behavior.get("expected_values")
    if not isinstance(resources, list):
        return
    owners = {}
    records = registry.get("records", {}) if isinstance(registry, dict) else {}
    for evidence_ref, record in records.items() if isinstance(records, dict) else []:
        try:
            source_ref = record["source"]["source_id"]
            owner = {OWNER_REF: source_ref, REF: evidence_ref,
                     ASSESSMENT_BINDING: assessment_binding(source_ref, evidence_ref, authorized_scope)}
            if resolve(owner, registry, authorized_scope=authorized_scope) is not None:
                owners.setdefault(source_ref, {})[evidence_ref] = owner
        except (KeyError, TypeError, ValueError):
            continue
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        resource.pop(BINDING, None)
        candidates = owners.get(resource.get(LINEAGE), {}) if isinstance(resource.get(LINEAGE), str) else {}
        if len(candidates) != 1:
            continue
        owner = next(iter(candidates.values()))
        try:
            resource[BINDING] = {
                "version": VERSION, **owner,
                "resource_digest": digest(VERSION, _payload(resource, owner)),
            }
        except (TypeError, ValueError, OverflowError):
            continue  # Unavailable metadata cannot fail a completed calculation.


def resolve_resource(resource, finding, registry, *, authorized_scope):
    """Require the scoped finding itself, not its contributions, to own the rate."""
    try:
        owner = ownership(finding)
        binding = resource.get(BINDING)
        if not owner or not isinstance(binding, dict) or binding.get("version") != VERSION:
            return None
        if ownership(binding) != owner or resource.get(LINEAGE) != owner[OWNER_REF]:
            return None
        if binding.get("resource_digest") != digest(VERSION, _payload(resource, owner)):
            return None
        record = resolve(finding, registry, authorized_scope=authorized_scope, require_temporal=True)
        if record is None or record["qualification"].get("eligible") is not True:
            return None
        if record["temporal"]["assessment"].get("persistent_relationship_change") is not True:
            return None
        # Consistency validation after exact resolution; these names never select
        # an owner or grant ownership to an unbound series.
        predictors = resource.get("predictor_signals")
        if (not isinstance(predictors, list) or len(predictors) != 1
                or not all(isinstance(value, str) for value in predictors)
                or not isinstance(resource.get("target_signal"), str)
                or sorted([resource["target_signal"], *predictors]) != record["source"]["columns"]):
            return None
        return record
    except (KeyError, TypeError, ValueError):
        return None
