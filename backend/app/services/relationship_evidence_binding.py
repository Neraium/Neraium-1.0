"""Producer-issued, result-local relationship evidence references.

This module records existing calculations. It never computes persistence or
grants authorization. Callers must obtain the registry through an authorized
result read; an evidence ID is not a capability.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math

from app.services.authority_contract_common import canonical_json_bytes
from app.services.relationship_observation_projection import FALLBACK_REASONS, MODE_STATUSES

VERSION = "relationship-evidence.v1"
BASES = frozenset({"global_relationship_model", "mode_conditioned_relationships",
                   "global_relationship_model_failure_fallback"})
SOURCE = "relationship_source_evidence"
OWNER_REF = "relationship_source_ref"
REF = "relationship_evidence_ref"
ASSESSMENT_BINDING = "relationship_assessment_binding"
REGISTRY = "relationship_evidence_registry"
WINDOW = ("baseline_start", "baseline_end", "current_start", "current_end")
TEMPORAL = ("temporal_persistence_observations", "temporal_persistence_supporting_observations",
            "temporal_persistence_direction", "temporal_persistence_direction_agreement",
            "temporal_persistence_supported", "persistent_relationship_change",
            "temporal_persistence_status", "first_supported_observation", "latest_supported_observation")


def digest(domain, value):
    return domain + ":" + sha256(canonical_json_bytes(value)).hexdigest()


def pick(value, keys):
    return {key: deepcopy(value[key]) for key in keys if key in value}


def measurement(edge):
    pair = next(iter(edge.get("supporting_metric_pairs") or [{}]))
    return {
        "baseline": edge.get("baseline_correlation"),
        "current": edge.get("recent_correlation", edge.get("current_correlation")),
        "baseline_count": edge.get("baseline_sample_count", edge.get("baseline_sample_size", pair.get("baseline_sample_size"))),
        "current_count": edge.get("current_sample_count", edge.get("recent_sample_size", pair.get("recent_sample_size"))),
        "window": pick(edge.get("time_window") or {}, WINDOW),
    }


def source_evidence(edge, *, columns, baseline_rows, current_rows, timestamp_column,
                    units=None, selection=None, method="pearson-global.v1"):
    """Called at calculation time with the actual selected numerical rows.

    Missing/nonfinite numerical values are recorded as missing, never silently
    discarded. Full selected sequences are hashed, not just their endpoints.
    """
    columns = sorted(columns)  # These two registered Pearson methods are symmetric.
    if method not in {"pearson-global.v1", "pearson-mode.v1"} or len(set(columns)) != 2:
        raise ValueError("unsupported_relationship_source_method")

    def observations(rows):
        values = []
        for row in rows:
            cells = []
            for column in columns:
                value = row.get(column)
                try:
                    number = float(value)
                    cells.append(number if math.isfinite(number) else None)
                except (ValueError, TypeError, OverflowError):
                    cells.append(None)
            values.append([row.get(timestamp_column) if timestamp_column else None, cells])
        return digest("relationship-observations.v1", values)

    payload = {
        "version": VERSION, "method": method, "columns": columns,
        "baseline_observations": observations(baseline_rows),
        "current_observations": observations(current_rows),
        "units": {c: (units or {}).get(c) for c in columns},
        "selection": deepcopy(selection or {}), "measurement": measurement(edge),
    }
    return {"source_id": digest("relationship-source.v1", payload), **payload}


def try_source_evidence(*args, **kwargs):
    # Metadata unavailability must never fail or alter a successful calculation.
    try:
        return source_evidence(*args, **kwargs)
    except (ValueError, TypeError, OverflowError):
        return None


def valid_source(edge):
    source = edge.get(SOURCE)
    if not isinstance(source, dict) or source.get("version") != VERSION:
        return False
    payload = {k: v for k, v in source.items() if k != "source_id"}
    pairs = edge.get("supporting_metric_pairs") or []
    columns = ([pairs[0].get("left"), pairs[0].get("right")]
               if pairs else edge.get("columns", []))
    if sorted(columns) != source.get("columns"):
        return False
    if "columns" in edge and sorted(edge["columns"]) != source.get("columns"):
        return False
    return (source.get("source_id") == digest("relationship-source.v1", payload)
            and source.get("measurement") == measurement(edge)
            and source.get("method") in {"pearson-global.v1", "pearson-mode.v1"})


def temporal_descriptor(edge, graph):
    if "temporal_persistence_status" not in edge:
        return {"status": "unavailable"}
    key = json.dumps(sorted(edge[SOURCE]["columns"]), separators=(",", ":"))
    state = (graph.get("relationship_persistence_state") or {}).get(key)
    if not isinstance(state, dict) or state.get("identity", {}).get("basis") != graph.get("edge_basis"):
        raise ValueError("relationship_temporal_scope_missing")
    identity = pick(state["identity"], ("columns", "basis", "baseline_correlation", "baseline_start", "baseline_end",
                                         "mode", "reference_dataset_id", "signal_units"))
    if identity.get("columns") != edge[SOURCE]["columns"]:
        raise ValueError("relationship_temporal_owner_mismatch")
    window = edge.get("time_window") or {}
    for key, expected in {
        "baseline_correlation": edge.get("baseline_correlation"),
        "baseline_start": window.get("baseline_start"),
        "baseline_end": window.get("baseline_end"),
        "reference_dataset_id": edge.get("reference_dataset_id"),
        "signal_units": edge.get("signal_units"),
        "mode": edge.get("mode_conditioning") or {
            "baseline_mode": (edge.get("operating_mode_context") or {}).get("baseline_mode"),
            "recent_mode": (edge.get("operating_mode_context") or {}).get("recent_mode"),
        },
    }.items():
        if identity.get(key) != expected:
            raise ValueError("relationship_temporal_identity_mismatch")
    observations = []
    for item in state.get("observations", []):
        observations.append({
            **pick(item, ("observed_at", "source_dataset_id", "signed_correlation_delta",
                          "edge_confidence", "data_quality_factor", "eligible", "acceptable")),
            "time_window": pick(item.get("time_window") or {}, WINDOW),
            "source_rows": [pick(row, ("window", "source_row", "timestamp")) for row in item.get("source_rows", [])],
        })
    if edge["temporal_persistence_status"] in {"supported", "unconfirmed"}:
        if not observations:
            raise ValueError("relationship_temporal_history_missing")
        latest = observations[-1]
        if latest["time_window"] != pick(window, WINDOW):
            raise ValueError("relationship_temporal_window_mismatch")
        for field in ("signed_correlation_delta", "edge_confidence", "data_quality_factor", "eligible"):
            if latest.get(field) != edge.get(field):
                raise ValueError("relationship_temporal_measurement_mismatch")
    return {"status": "available", "identity": deepcopy(identity),
            "method": "relationship_temporal_evidence.v1",
            "parameters": pick(graph.get("thresholds") or {},
                               ("temporal_persistence", "minimum_edge_confidence", "minimum_data_quality_factor")),
            "observations": observations, "assessment": pick(edge, TEMPORAL)}


def evidence_record(edge, graph, scope, comparison_qualification=None):
    if not valid_source(edge) or graph.get("edge_basis") not in BASES:
        raise ValueError("relationship_source_unavailable")
    basis = graph["edge_basis"]
    if (basis == "mode_conditioned_relationships") != (edge[SOURCE]["method"] == "pearson-mode.v1"):
        raise ValueError("relationship_source_basis_mismatch")
    temporal = temporal_descriptor(edge, graph)
    if basis == "global_relationship_model_failure_fallback" and temporal["status"] != "unavailable":
        raise ValueError("fallback_temporal_evidence_invalid")
    payload = {
        "version": VERSION, "scope": scope, "source": deepcopy(edge[SOURCE]),
        "basis": basis,
        "reference": pick(edge, ("reference_dataset_id", "source_dataset_id", "signal_units")),
        "context": {
            "mode_conditioning": pick(edge.get("mode_conditioning") or {}, ("mode_id", "features")),
            "operating_mode": pick(edge.get("operating_mode_context") or {},
                                   ("baseline_mode", "recent_mode", "match", "confidence")),
        },
        "comparison_qualification": deepcopy(comparison_qualification or {}),
        "qualification": pick(edge, ("eligible", "edge_confidence", "data_quality_factor")),
        "temporal": temporal,
    }
    return {"evidence_id": digest(VERSION, payload), **payload}


def registry_record(registry, record):
    identity = record["evidence_id"]
    existing = registry["records"].get(identity)
    if existing is not None and existing != record:
        raise ValueError("conflicting_relationship_evidence_id")
    registry["records"][identity] = deepcopy(record)


def finalize(relationship_model, graph, *, scope, mode_conditioned=None):
    """Finalize a newly produced result only. Never called by historical reads.

    A lineage is resolved only through producer-issued source IDs. Mode evidence
    cannot claim a global candidate. Unassessed global source records stay out of
    the dynamic graph's analytical edge collections.
    """
    registry = {"version": VERSION, "scope": scope, "records": {}}
    comparison = {}
    mode_conditioned = mode_conditioned or {}
    if mode_conditioned.get("status") in MODE_STATUSES:
        comparison["status"] = mode_conditioned["status"]
    if type(mode_conditioned.get("used_global_fallback")) is bool:
        comparison["used_global_fallback"] = mode_conditioned["used_global_fallback"]
    reason = mode_conditioned.get("fallback_reason")
    if isinstance(reason, str) and reason in FALLBACK_REASONS:
        comparison["fallback_reason"] = reason
    by_source = {}
    for edge in graph.get("edges", []):
        try:
            record = evidence_record(edge, graph, scope, comparison)
        except (ValueError, TypeError, KeyError):
            continue
        registry_record(registry, record)
        by_source.setdefault(record["source"]["source_id"], set()).add(record["evidence_id"])
        edge["relationship_evidence_id"] = record["evidence_id"]
    for edge in (relationship_model.get("relationship_graph") or {}).get("edges", []):
        if not valid_source(edge) or edge[SOURCE]["source_id"] in by_source:
            continue
        record = evidence_record(edge, {"edge_basis": "global_relationship_model"}, scope, comparison)
        registry_record(registry, record)
        by_source[record["source"]["source_id"]] = {record["evidence_id"]}
    for candidate in relationship_model.get("top_relationship_changes", []):
        candidate.pop(REF, None)
        candidate.pop(OWNER_REF, None)
        candidate.pop(ASSESSMENT_BINDING, None)
        if not valid_source(candidate):
            continue
        # Producer finalization retains the assertion's own lineage independently
        # of whichever final evidence record is referenced. Projections only copy.
        candidate[OWNER_REF] = candidate[SOURCE]["source_id"]
        identities = by_source.get(candidate[SOURCE]["source_id"], set())
        if len(identities) == 1:
            candidate[REF] = next(iter(identities))
            candidate[ASSESSMENT_BINDING] = assessment_binding(candidate[OWNER_REF], candidate[REF], scope)
    registry["records"] = dict(sorted(registry["records"].items()))
    # Freeze ordinary JSON values and deterministic key ordering at the boundary.
    return json.loads(canonical_json_bytes(registry))


def assessment_binding(source_ref, evidence_ref, scope):
    """Integrity seal for the producer assignment, not an authorization token."""
    return digest("relationship-assessment-binding.v1", {
        "version": VERSION, "source_ref": source_ref,
        "evidence_ref": evidence_ref, "scope": scope,
    })


def resolve(assertion, registry, *, authorized_scope, require_temporal=False):
    """Resolve only inside the caller's already-authorized result registry."""
    try:
        if not isinstance(assertion, dict) or not isinstance(registry, dict):
            return None
        owner_ref = assertion.get(OWNER_REF)
        if not isinstance(owner_ref, str):
            return None  # Historical or incomplete assertions have no authority.
        if registry.get("version") != VERSION or registry.get("scope") != authorized_scope:
            return None
        record = registry["records"].get(assertion.get(REF))
        if not isinstance(record, dict) or record.get("version") != VERSION or record.get("scope") != authorized_scope:
            return None
        payload = {k: v for k, v in record.items() if k != "evidence_id"}
        if record.get("evidence_id") != assertion.get(REF) or digest(VERSION, payload) != record["evidence_id"]:
            return None
        if assertion.get(ASSESSMENT_BINDING) != assessment_binding(owner_ref, assertion[REF], authorized_scope):
            return None
        source = record["source"]
        if source.get("version") != VERSION or source.get("method") not in {"pearson-global.v1", "pearson-mode.v1"}:
            return None
        if source["source_id"] != digest("relationship-source.v1", {k: v for k, v in source.items() if k != "source_id"}):
            return None
        if owner_ref != source["source_id"]:
            return None
        if SOURCE in assertion and (not valid_source(assertion) or assertion[SOURCE] != source):
            return None
        if record["basis"] not in BASES:
            return None
        if (record["basis"] == "mode_conditioned_relationships") != (source["method"] == "pearson-mode.v1"):
            return None
        temporal = record["temporal"]
        if temporal.get("status") not in {"available", "unavailable"}:
            return None
        if temporal["status"] == "available":
            if temporal.get("method") != "relationship_temporal_evidence.v1":
                return None
            if temporal.get("identity", {}).get("columns") != source["columns"]:
                return None
            if temporal.get("identity", {}).get("basis") != record["basis"]:
                return None
            if record["basis"] == "global_relationship_model_failure_fallback":
                return None
        if require_temporal and record["temporal"]["status"] != "available":
            return None
        return deepcopy(record)
    except (TypeError, KeyError, ValueError):
        return None
