from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from typing import Any

from app.engine.sii.common import clamp


PATH_MESSAGE = "Candidate propagation path consistent with observed timing and graph structure."
SUPPORTED_DIRECTIONALITY = {
    "configured_source_to_target",
    "lag_supported_source_to_target",
    "source_precedes_target",
}
DEFAULT_CONFIG = {"maximum_path_edges": 4, "minimum_edge_strength": 0.35}
DEFAULT_CONFIG.update(
    {
        "lag_tolerance_seconds": 0.0,
        "lag_relative_tolerance": 0.25,
        "simultaneous_change_tolerance_seconds": 5.0,
    }
)


def analyze_propagation(
    *,
    graph_comparison: dict[str, Any],
    relationship_memory: dict[str, Any],
    signal_drift: dict[str, Any],
    expected_behavior: dict[str, Any],
    operating_mode: dict[str, Any],
    sensor_health: dict[str, Any],
    data_quality: dict[str, Any],
    multiscale_analysis: dict[str, Any],
    signal_change_times: dict[str, str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Find supported timing-compatible paths without selecting a cause."""

    cfg = {**DEFAULT_CONFIG, **(config or {})}
    limitations: list[str] = []
    unsupported: list[dict[str, Any]] = []
    changed_edges = [item for item in graph_comparison.get("changed_edges", []) if isinstance(item, dict)]
    residual_targets = {
        str(item.get("target_signal"))
        for item in expected_behavior.get("residual_evidence", [])
        if isinstance(item, dict) and item.get("target_signal")
    }
    drift_signals = {
        str(item.get("column"))
        for item in signal_drift.get("column_drift", [])
        if isinstance(item, dict)
        and item.get("column")
        and str(item.get("direction") or "").lower() not in {"", "flat", "stable"}
    }
    edge_nodes = {
        str(value)
        for edge in changed_edges
        for value in (edge.get("source_signal"), edge.get("target_signal"))
        if value
    }
    activated_nodes = sorted(residual_targets | drift_signals | edge_nodes)
    activated_edges = sorted({str(item.get("relationship_id")) for item in changed_edges if item.get("relationship_id")})
    times = _change_times(signal_change_times or {}, signal_drift)
    health = {
        str(item.get("signal")): str(item.get("health") or "unavailable").lower()
        for item in sensor_health.get("signals", [])
        if isinstance(item, dict) and item.get("signal")
    }
    adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for relationship_id, relationship in sorted(relationship_memory.items()):
        if not isinstance(relationship, dict) or relationship.get("status") in {"inactive", "retired"}:
            continue
        source = str(relationship.get("source_signal") or "")
        target = str(relationship.get("target_signal") or "")
        direction = str(relationship.get("directionality_status") or "")
        strength = float(relationship.get("current_strength") or 0.0)
        mode_ok = str(operating_mode.get("recent_mode") or "unavailable") in list(relationship.get("operating_modes_observed") or [])
        health_ok = health.get(source) in {"healthy", "good"} and health.get(target) in {"healthy", "good"}
        lag = _latest_lag(relationship)
        lag_specification = (
            _lag_specification(relationship, lag, cfg)
            if lag is not None
            else None
        )
        reasons = []
        if direction not in SUPPORTED_DIRECTIONALITY:
            reasons.append("direction_ambiguous")
        if lag_specification is None:
            reasons.append("lag_evidence_unavailable")
        if strength < float(cfg["minimum_edge_strength"]):
            reasons.append("graph_support_weak")
        if not mode_ok:
            reasons.append("operating_mode_incompatible")
        if not health_ok:
            reasons.append("sensor_health_limitation")
        if reasons:
            unsupported.append(
                {
                    "relationship_id": relationship_id,
                    "source_signal": source,
                    "target_signal": target,
                    "reasons": reasons,
                    "source_evidence": deepcopy(relationship),
                }
            )
            continue
        adjacency[source].append(
            {
                "relationship_id": relationship_id,
                "source_signal": source,
                "target_signal": target,
                "edge_strength": strength,
                "lag": lag,
                "lag_specification": lag_specification,
                "stability": relationship.get("stability"),
                "persistence": relationship.get("persistence"),
                "physics_prior_references": deepcopy(relationship.get("physics_prior_references", [])),
                "source_evidence": deepcopy(relationship),
            }
        )

    candidate_paths = []
    for start in activated_nodes:
        _walk_paths(
            current=start,
            path_nodes=[start],
            path_edges=[],
            activated=set(activated_nodes),
            adjacency=adjacency,
            times=times,
            output=candidate_paths,
            maximum_edges=int(cfg["maximum_path_edges"]),
        )
    candidate_paths = _unique_paths(candidate_paths)
    competing = _competing_paths(candidate_paths)
    change_roles = _change_roles(
        activated_nodes=activated_nodes,
        times=times,
        candidate_paths=candidate_paths,
        simultaneous_tolerance=float(
            cfg["simultaneous_change_tolerance_seconds"]
        ),
    )
    if not times:
        limitations.append("Signal change timestamps were inadequate for temporal precedence checks.")
    if not relationship_memory:
        limitations.append("Persistent relationship memory was unavailable.")
    if unsupported:
        limitations.append("Some graph segments were excluded because direction, lag, health, mode, or strength support was inadequate.")
    quality_ok = str(data_quality.get("readiness") or "").lower() != "not_ready"
    if not quality_ok:
        limitations.append("Data quality was not sufficient for propagation interpretation.")
        candidate_paths = []
        competing = []
    cross_scale = str(
        multiscale_analysis.get("cross_scale_classification")
        or (multiscale_analysis.get("cross_scale_interpretation") or {}).get("classification")
        or ""
    ).lower()
    factors = {
        "timestamp_coverage": 1.0 if times else 0.0,
        "supported_directional_edges": round(clamp(sum(len(items) for items in adjacency.values()) / max(1, len(relationship_memory))), 6),
        "data_quality": 1.0 if quality_ok else 0.0,
        "sensor_health": round(clamp(sum(1 for value in health.values() if value in {"healthy", "good"}) / max(1, len(health))), 6),
        "multiscale_agreement": 1.0 if cross_scale in {"agreement", "consistent", "stable", "stable_across_scales"} else 0.5 if multiscale_analysis.get("status") == "complete" else 0.0,
        "alternative_path_visibility": 1.0,
    }
    confidence = {
        "compatibility": round(sum(factors.values()) / len(factors), 6),
        "not_probability": True,
        "factors": factors,
        "method": "unweighted_deterministic_path_evidence_factor_mean",
    }
    status = "complete" if candidate_paths else "limited"
    return {
        "status": status,
        "reason": None if status == "complete" else "no_fully_supported_candidate_propagation_path",
        "activated_nodes": activated_nodes,
        "activated_edges": activated_edges,
        "candidate_paths": candidate_paths,
        "earliest_observed_changes": [
            {"signal": signal, "timestamp": timestamp}
            for signal, timestamp in sorted(times.items(), key=lambda item: (item[1], item[0]))
        ],
        "downstream_consistent_changes": sorted({path["nodes"][-1] for path in candidate_paths}),
        "change_roles": change_roles,
        "primary_behavioral_change_candidates": change_roles[
            "earliest_upstream_candidates"
        ],
        "downstream_behavioral_responses": change_roles[
            "downstream_consistent_candidates"
        ],
        "independent_simultaneous_changes": change_roles[
            "independent_simultaneous_groups"
        ],
        "competing_paths": competing,
        "unsupported_segments": unsupported,
        "path_evidence": [
            {"path_id": path["path_id"], "evidence": deepcopy(path["path_evidence"])} for path in candidate_paths
        ],
        "propagation_confidence": confidence,
        "uncertainty": {
            "not_probability": True,
            "cause_selected": False,
            "alternative_paths_retained": True,
            "propagation_uncertainty": {
                "timestamped_signal_fraction": round(
                    len(times) / max(1, len(activated_nodes)),
                    6,
                ),
                "unsupported_segment_count": len(unsupported),
                "competing_path_group_count": len(competing),
                "independent_simultaneous_group_count": len(
                    change_roles["independent_simultaneous_groups"]
                ),
                "traceable_sources": [
                    "earliest_observed_changes",
                    "unsupported_segments",
                    "competing_paths",
                    "candidate_paths.*.lag_consistency",
                ],
            },
        },
        "limitations": list(dict.fromkeys(limitations)),
        "reasoning_trace": {
            "statement": PATH_MESSAGE,
            "temporal_precedence_required": True,
            "lag_evidence_required": True,
            "expected_lag_window_required": True,
            "path_lag_consistency_evaluated": True,
            "causal_proof_claimed": False,
            "root_cause_selected": False,
        },
        "processing_trace": {
            "relationships_considered": len(relationship_memory),
            "supported_directed_edges": sum(len(items) for items in adjacency.values()),
            "candidate_paths_generated": len(candidate_paths),
            "competing_path_groups": len(competing),
        },
    }


def _walk_paths(
    *,
    current: str,
    path_nodes: list[str],
    path_edges: list[dict[str, Any]],
    activated: set[str],
    adjacency: dict[str, list[dict[str, Any]]],
    times: dict[str, str],
    output: list[dict[str, Any]],
    maximum_edges: int,
) -> None:
    if len(path_edges) >= maximum_edges:
        return
    for edge in sorted(adjacency.get(current, []), key=lambda item: item["relationship_id"]):
        target = edge["target_signal"]
        if target in path_nodes:
            continue
        timing = _timing_compatibility(
            current,
            target,
            edge["lag_specification"],
            times,
        )
        if not timing["compatible"]:
            continue
        next_nodes = [*path_nodes, target]
        next_edges = [*path_edges, {**edge, "timing_evidence": timing}]
        if target in activated and len(next_edges) >= 1:
            output.append(_path(next_nodes, next_edges, times))
        _walk_paths(
            current=target,
            path_nodes=next_nodes,
            path_edges=next_edges,
            activated=activated,
            adjacency=adjacency,
            times=times,
            output=output,
            maximum_edges=maximum_edges,
        )


def _path(nodes: list[str], edges: list[dict[str, Any]], times: dict[str, str]) -> dict[str, Any]:
    key = "->".join(nodes)
    observed_total = _elapsed_seconds(nodes[0], nodes[-1], times)
    expected_total = sum(
        float(edge["lag_specification"]["expected_seconds"]) for edge in edges
    )
    minimum_total = sum(
        float(edge["lag_specification"]["minimum_seconds"]) for edge in edges
    )
    maximum_total = sum(
        float(edge["lag_specification"]["maximum_seconds"]) for edge in edges
    )
    edge_lag_scores = [
        float(edge.get("timing_evidence", {}).get("lag_fit_score") or 0.0)
        for edge in edges
    ]
    end_to_end_fit = _lag_fit_score(
        observed_total,
        expected_total,
        minimum_total,
        maximum_total,
    )
    factors = {
        "minimum_edge_strength": round(min(float(edge["edge_strength"]) for edge in edges), 6),
        "stable_edge_fraction": round(sum(1 for edge in edges if edge.get("stability") == "stable") / len(edges), 6),
        "temporal_precedence": 1.0,
        "lag_support": round(sum(edge_lag_scores) / len(edge_lag_scores), 6),
        "path_lag_consistency": round(end_to_end_fit, 6),
    }
    return {
        "path_id": f"candidate_path:{key}",
        "statement": PATH_MESSAGE,
        "nodes": list(nodes),
        "edges": [edge["relationship_id"] for edge in edges],
        "observed_times": {node: times.get(node) for node in nodes},
        "lag_consistency": {
            "observed_end_to_end_seconds": round(observed_total, 6)
            if observed_total is not None
            else None,
            "expected_end_to_end_seconds": round(expected_total, 6),
            "expected_window_seconds": [
                round(minimum_total, 6),
                round(maximum_total, 6),
            ],
            "edge_lag_fit_scores": [
                round(value, 6) for value in edge_lag_scores
            ],
            "end_to_end_fit_score": round(end_to_end_fit, 6),
        },
        "path_evidence": deepcopy(edges),
        "compatibility": round(sum(factors.values()) / len(factors), 6),
        "confidence_factors": factors,
        "not_probability": True,
        "causal_claim": False,
    }


def _timing_compatibility(
    source: str,
    target: str,
    lag_specification: dict[str, Any],
    times: dict[str, str],
) -> dict[str, Any]:
    if source not in times or target not in times:
        return {
            "compatible": False,
            "reason": "change_time_unavailable",
            "observed_delay_seconds": None,
        }
    try:
        source_time = datetime.fromisoformat(times[source].replace("Z", "+00:00"))
        target_time = datetime.fromisoformat(times[target].replace("Z", "+00:00"))
    except ValueError:
        return {
            "compatible": False,
            "reason": "change_time_invalid",
            "observed_delay_seconds": None,
        }
    delta = (target_time - source_time).total_seconds()
    minimum = float(lag_specification["minimum_seconds"])
    maximum = float(lag_specification["maximum_seconds"])
    compatible = delta >= 0.0 and minimum <= delta <= maximum
    return {
        "compatible": compatible,
        "reason": "within_expected_lag_window"
        if compatible
        else "outside_expected_lag_window",
        "observed_delay_seconds": round(delta, 6),
        "expected_delay_seconds": lag_specification["expected_seconds"],
        "expected_window_seconds": [minimum, maximum],
        "lag_fit_score": round(
            _lag_fit_score(
                delta,
                float(lag_specification["expected_seconds"]),
                minimum,
                maximum,
            ),
            6,
        ),
        "source": lag_specification["source"],
    }


def _change_times(configured: dict[str, str], signal_drift: dict[str, Any]) -> dict[str, str]:
    output = {str(key): str(value) for key, value in configured.items() if value}
    for item in signal_drift.get("column_drift", []):
        if not isinstance(item, dict) or not item.get("column"):
            continue
        timestamp = item.get("first_observed_change") or item.get("first_detected_at")
        if timestamp:
            output.setdefault(str(item["column"]), str(timestamp))
    return output


def _latest_lag(relationship: dict[str, Any]) -> float | None:
    configured = relationship.get("configured_lag_seconds")
    if isinstance(configured, (int, float)):
        return float(configured)
    for item in reversed(relationship.get("lag_history", [])):
        if not isinstance(item, dict):
            continue
        evidence = item.get("global_temporal_lag_evidence") if isinstance(item.get("global_temporal_lag_evidence"), dict) else {}
        value = evidence.get("dominant_lag_seconds")
        if isinstance(value, (int, float)):
            return abs(float(value))
        shift = evidence.get("dominant_lag_shift")
        if isinstance(shift, (int, float)) and shift != 0:
            return abs(float(shift))
    return None


def _lag_specification(
    relationship: dict[str, Any],
    lag: float,
    config: dict[str, Any],
) -> dict[str, Any]:
    expected = max(0.0, float(lag))
    configured_window = relationship.get(
        "configured_response_window_seconds",
        relationship.get("expected_response_window_seconds"),
    )
    lower = None
    upper = None
    source = "lag_with_configured_tolerance"
    if isinstance(configured_window, (list, tuple)) and len(configured_window) == 2:
        lower, upper = configured_window
        source = "configured_response_window_seconds"
    elif isinstance(configured_window, dict):
        lower = configured_window.get(
            "minimum",
            configured_window.get("minimum_seconds"),
        )
        upper = configured_window.get(
            "maximum",
            configured_window.get("maximum_seconds"),
        )
        source = "configured_response_window_seconds"
    explicit_lower = relationship.get("minimum_response_delay_seconds")
    explicit_upper = relationship.get("maximum_response_delay_seconds")
    if isinstance(explicit_lower, (int, float)):
        lower = explicit_lower
        source = "configured_response_delay_bounds"
    if isinstance(explicit_upper, (int, float)):
        upper = explicit_upper
        source = "configured_response_delay_bounds"
    tolerance = max(
        float(config.get("lag_tolerance_seconds") or 0.0),
        expected * float(config.get("lag_relative_tolerance") or 0.0),
    )
    minimum = (
        max(0.0, float(lower))
        if isinstance(lower, (int, float))
        else max(0.0, expected - tolerance)
    )
    maximum = (
        max(minimum, float(upper))
        if isinstance(upper, (int, float))
        else max(minimum, expected + tolerance)
    )
    return {
        "expected_seconds": round(expected, 6),
        "minimum_seconds": round(minimum, 6),
        "maximum_seconds": round(maximum, 6),
        "source": source,
        "window_width_seconds": round(maximum - minimum, 6),
    }


def _elapsed_seconds(
    source: str,
    target: str,
    times: dict[str, str],
) -> float | None:
    if source not in times or target not in times:
        return None
    try:
        source_time = datetime.fromisoformat(times[source].replace("Z", "+00:00"))
        target_time = datetime.fromisoformat(times[target].replace("Z", "+00:00"))
    except ValueError:
        return None
    return (target_time - source_time).total_seconds()


def _lag_fit_score(
    observed: float | None,
    expected: float,
    minimum: float,
    maximum: float,
) -> float:
    if observed is None or observed < minimum or observed > maximum:
        return 0.0
    scale = max(expected - minimum, maximum - expected, 1e-12)
    return clamp(1.0 - abs(observed - expected) / scale)


def _unique_paths(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique = {str(item["path_id"]): item for item in paths}
    return [unique[key] for key in sorted(unique)]


def _competing_paths(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        grouped[(path["nodes"][0], path["nodes"][-1])].append(path)
    return [
        {
            "start": key[0],
            "end": key[1],
            "candidate_path_ids": [
                item["path_id"]
                for item in sorted(
                    items,
                    key=lambda candidate: (
                        -float(candidate.get("compatibility") or 0.0),
                        str(candidate["path_id"]),
                    ),
                )
            ],
            "path_evaluations": [
                {
                    "path_id": item["path_id"],
                    "compatibility": item.get("compatibility"),
                    "lag_consistency": deepcopy(item.get("lag_consistency")),
                }
                for item in sorted(
                    items,
                    key=lambda candidate: (
                        -float(candidate.get("compatibility") or 0.0),
                        str(candidate["path_id"]),
                    ),
                )
            ],
            "cause_selected": False,
            "interpretation": "Paths are ordered for inspectability only; no path is selected as causal.",
        }
        for key, items in sorted(grouped.items())
        if len(items) > 1
    ]


def _change_roles(
    *,
    activated_nodes: list[str],
    times: dict[str, str],
    candidate_paths: list[dict[str, Any]],
    simultaneous_tolerance: float,
) -> dict[str, Any]:
    reachable = {
        (str(path["nodes"][0]), str(path["nodes"][-1]))
        for path in candidate_paths
        if len(path.get("nodes", [])) >= 2
    }
    upstream = {source for source, _target in reachable}
    downstream = {target for _source, target in reachable}
    primary = sorted(
        upstream - downstream,
        key=lambda node: (times.get(node, ""), node),
    )
    downstream_records = [
        {
            "signal": node,
            "preceded_by": sorted(
                source for source, target in reachable if target == node
            ),
            "classification": "downstream_behavioral_response_candidate",
            "causal_claim": False,
        }
        for node in sorted(downstream, key=lambda item: (times.get(item, ""), item))
    ]
    simultaneous_adjacency: dict[str, set[str]] = defaultdict(set)
    for index, left in enumerate(activated_nodes):
        for right in activated_nodes[index + 1 :]:
            delta = _elapsed_seconds(left, right, times)
            linked = (left, right) in reachable or (right, left) in reachable
            if (
                delta is not None
                and abs(delta) <= max(0.0, simultaneous_tolerance)
                and not linked
            ):
                simultaneous_adjacency[left].add(right)
                simultaneous_adjacency[right].add(left)
    groups = []
    visited: set[str] = set()
    for start in sorted(simultaneous_adjacency):
        if start in visited:
            continue
        queue = [start]
        members = []
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            members.append(node)
            queue.extend(sorted(simultaneous_adjacency[node] - visited))
        if len(members) > 1:
            groups.append(
                {
                    "signals": sorted(members),
                    "change_times": {
                        node: times.get(node) for node in sorted(members)
                    },
                    "tolerance_seconds": max(0.0, simultaneous_tolerance),
                    "classification": "independent_simultaneous_change_candidates",
                    "path_between_signals_observed": False,
                    "causal_claim": False,
                }
            )
    path_nodes = {
        str(node)
        for path in candidate_paths
        for node in path.get("nodes", [])
    }
    return {
        "earliest_upstream_candidates": [
            {
                "signal": node,
                "change_time": times.get(node),
                "classification": "earliest_upstream_behavioral_change_candidate",
                "causal_claim": False,
            }
            for node in primary
        ],
        "downstream_consistent_candidates": downstream_records,
        "independent_simultaneous_groups": groups,
        "unconnected_activated_signals": sorted(
            set(activated_nodes) - path_nodes
        ),
        "classification_method": "temporal_precedence_plus_supported_graph_reachability",
        "cause_selected": False,
    }
