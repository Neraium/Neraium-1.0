"""Read-only, bounded disclosure of retained observations, never finding authority.

Transport only: do not attach to stored/canonical analysis or use in selection.
Lists preserve the engine's order; mappings use fixed field order. No clocks,
reduction, qualification, or runtime/forensic dictionaries enter this contract.
"""
from __future__ import annotations

import json
import math
from typing import Any

LIMIT = 12
MAX_BYTES = 48 * 1024
VERSION = "relationship-observations.v1"

# Recorded mode-conditioned comparison codes only. Failure paths may carry raw
# exception text in fallback_reason; never copy arbitrary strings from there.
COMPARISON_BASES = frozenset({
    "global_relationship_model", "mode_conditioned_relationships",
    "global_relationship_model_failure_fallback",
})
MODE_STATUSES = frozenset({"complete", "limited", "failed"})
FALLBACK_REASONS = frozenset({
    "no_explicit_operating_mode_features",
    "insufficient_recent_mode_rows",
    "ambiguous_recent_operating_mode",
    "insufficient_like_mode_historical_rows",
})


def _map(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _pick(value: Any, fields: tuple[str, ...]) -> dict:
    source = _map(value)
    result = {}
    for field in fields:
        item = source.get(field)
        if field not in source:
            continue
        if item is None or type(item) is bool:
            result[field] = item
        elif type(item) in (int, float) and math.isfinite(item):
            result[field] = item
        elif isinstance(item, str):
            result[field] = item[:256]
    return result


WINDOW_FIELDS = ("baseline_start", "baseline_end", "current_start", "current_end")
EDGE_FIELDS = (
    "id", "relationship_id", "single_window_change_type", "change_type",
    "baseline_correlation", "current_correlation", "signed_correlation_delta",
    "eligible", "promoted_changed_edge", "edge_confidence", "data_quality_factor",
    "baseline_sample_count", "current_sample_count", "sample_sufficiency_factor",
    "temporal_persistence_observations", "temporal_persistence_supporting_observations",
    "temporal_persistence_direction", "temporal_persistence_direction_agreement",
    "temporal_persistence_supported", "temporal_persistence_status",
    "persistent_relationship_change", "first_supported_observation",
    "latest_supported_observation", "reference_dataset_id",
)


def _count(edges: list[tuple[int, dict]], field: str) -> int | None:
    if any(type(edge.get(field)) is not bool for _, edge in edges):
        return None
    return sum(edge[field] for _, edge in edges)


def _comparison_qualification(sii_result: Any, graph: dict) -> dict:
    # Preserve the two distinct source paths; neither source infers the other.
    result = {}
    basis = graph.get("edge_basis")
    if isinstance(basis, str) and basis in COMPARISON_BASES:
        result["edge_basis"] = basis
    source = _map(_map(_map(sii_result).get("operating_modes")).get("mode_conditioned_baseline"))
    conditioned = {}
    status = source.get("status")
    if isinstance(status, str) and status in MODE_STATUSES:
        conditioned["status"] = status
    if type(source.get("used_global_fallback")) is bool:
        conditioned["used_global_fallback"] = source["used_global_fallback"]
    reason = source.get("fallback_reason")
    if isinstance(reason, str) and reason in FALLBACK_REASONS:
        conditioned["fallback_reason"] = reason
    elif "fallback_reason" in source and reason is None:
        conditioned["fallback_reason"] = None
    if conditioned:
        result["mode_conditioned_baseline"] = conditioned
    return result


def relationship_observations(sii_result: Any) -> dict | None:
    graph = _map(_map(sii_result).get("relationship_graph"))
    # Absent historical evidence is unknown, never an invented zero count.
    if not isinstance(graph.get("edges"), list):
        return None
    edges = [(index, edge) for index, edge in enumerate(graph["edges"]) if isinstance(edge, dict)]
    observations = []
    for index, edge in edges[:LIMIT]:
        item = _pick(edge, EDGE_FIELDS)
        item["source_path"] = f"sii_result.relationship_graph.edges[{index}]"
        item["columns"] = [column[:256] for column in edge.get("columns", [])[:2]
                           if isinstance(column, str)] if isinstance(edge.get("columns"), list) else []
        item["time_window"] = _pick(edge.get("time_window"), WINDOW_FIELDS)
        item["operating_context"] = _pick(edge.get("operating_mode_context"),
                                                  ("status", "baseline_mode", "recent_mode", "match", "confidence"))
        item["relationship_context"] = _pick(edge.get("relationship_context"),
                                                     ("context_only", "operator_primary_eligible", "state_signal_involved"))
        item["recurrence"] = _pick(edge.get("recurrence_evidence"),
                                         ("status", "supported", "direction", "episode_count", "opposite_direction_veto"))
        item["supporting_windows"] = []
        windows = edge.get("supporting_windows")
        for window in (windows[:8] if isinstance(windows, list) else []):
            projected = _pick(window, ("observed_at", "signed_correlation_delta", "eligible", "acceptable", "source_dataset_id"))
            projected["time_window"] = _pick(_map(window).get("time_window"), WINDOW_FIELDS)
            anchors = _map(window).get("source_rows")
            projected["source_rows"] = [_pick(anchor, ("window", "source_row", "timestamp"))
                                        for anchor in (anchors[:4] if isinstance(anchors, list) else [])]
            item["supporting_windows"].append(projected)
        observations.append(item)
    result = {
        "version": VERSION,
        "authority": "observation_only",
        "source_path": "sii_result.relationship_graph.edges",
        "coverage": {
            "evaluated": len(edges),
            "eligible": _count(edges, "eligible"),
            "temporally_supported": _count(edges, "temporal_persistence_supported"),
            "promoted_changed_edges": _count(edges, "promoted_changed_edge"),
            "displayed": len(observations),
            "omitted": max(0, len(edges) - len(observations)),
        },
        "selection": "engine_order_first_12_not_primary_ranking",
        "observations": observations,
    }
    qualification = _comparison_qualification(sii_result, graph)
    if qualification:
        result["comparison_qualification"] = qualification
    # Fit inside the connector shared-envelope reserve. Drop whole observations
    # in engine order, never fragments of their provenance or support evidence.
    while len(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")) > MAX_BYTES and observations:
        observations.pop()
        result["coverage"]["displayed"] = len(observations)
        result["coverage"]["omitted"] = len(edges) - len(observations)
    return result
