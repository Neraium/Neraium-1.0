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
        reasons = []
        if direction not in SUPPORTED_DIRECTIONALITY:
            reasons.append("direction_ambiguous")
        if lag is None:
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
    cross_scale = str(multiscale_analysis.get("cross_scale_classification") or "").lower()
    factors = {
        "timestamp_coverage": 1.0 if times else 0.0,
        "supported_directional_edges": round(clamp(sum(len(items) for items in adjacency.values()) / max(1, len(relationship_memory))), 6),
        "data_quality": 1.0 if quality_ok else 0.0,
        "sensor_health": round(clamp(sum(1 for value in health.values() if value in {"healthy", "good"}) / max(1, len(health))), 6),
        "multiscale_agreement": 1.0 if cross_scale in {"agreement", "consistent", "stable"} else 0.5 if multiscale_analysis.get("status") == "complete" else 0.0,
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
        },
        "limitations": list(dict.fromkeys(limitations)),
        "reasoning_trace": {
            "statement": PATH_MESSAGE,
            "temporal_precedence_required": True,
            "lag_evidence_required": True,
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
        if not _timing_compatible(current, target, edge["lag"], times):
            continue
        next_nodes = [*path_nodes, target]
        next_edges = [*path_edges, edge]
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
    factors = {
        "minimum_edge_strength": round(min(float(edge["edge_strength"]) for edge in edges), 6),
        "stable_edge_fraction": round(sum(1 for edge in edges if edge.get("stability") == "stable") / len(edges), 6),
        "temporal_precedence": 1.0,
        "lag_support": 1.0,
    }
    return {
        "path_id": f"candidate_path:{key}",
        "statement": PATH_MESSAGE,
        "nodes": list(nodes),
        "edges": [edge["relationship_id"] for edge in edges],
        "observed_times": {node: times.get(node) for node in nodes},
        "path_evidence": deepcopy(edges),
        "compatibility": round(sum(factors.values()) / len(factors), 6),
        "confidence_factors": factors,
        "not_probability": True,
        "causal_claim": False,
    }


def _timing_compatible(source: str, target: str, lag: float, times: dict[str, str]) -> bool:
    if source not in times or target not in times:
        return False
    try:
        source_time = datetime.fromisoformat(times[source].replace("Z", "+00:00"))
        target_time = datetime.fromisoformat(times[target].replace("Z", "+00:00"))
    except ValueError:
        return False
    delta = (target_time - source_time).total_seconds()
    return delta >= 0.0 and (lag <= 0.0 or delta >= lag)


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
            "candidate_path_ids": [item["path_id"] for item in items],
            "cause_selected": False,
        }
        for key, items in sorted(grouped.items())
        if len(items) > 1
    ]
