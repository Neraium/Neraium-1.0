from __future__ import annotations

from typing import Any


class StructuralCausalityEngine:
    def build_graph(
        self,
        *,
        baseline_analysis: dict[str, Any],
        engine_result: dict[str, Any],
        driver_attribution: dict[str, Any],
    ) -> dict[str, Any]:
        nodes: dict[str, dict[str, Any]] = {}
        edges: list[dict[str, Any]] = []
        source = normalize_node_id(driver_attribution.get("driver_category") or "system_pressure_origin")
        nodes[source] = {
            "id": source,
            "label": display_name(driver_attribution.get("likely_driver") or "Structural pressure origin"),
            "type": "source",
            "pressure_score": 0.72,
        }
        for item in baseline_analysis.get("column_drift", []):
            if item.get("drift_flag") not in {"watch", "review"}:
                continue
            node_id = normalize_node_id(item.get("column", "unknown"))
            nodes[node_id] = {
                "id": node_id,
                "label": str(item.get("column", "unknown")),
                "type": "signal",
                "pressure_score": pressure_from_drift(item),
            }
            edges.append(
                {
                    "source": source,
                    "target": node_id,
                    "weight": pressure_from_drift(item),
                    "directionality": "upstream_to_signal",
                    "explanation": f"{display_name(driver_attribution.get('driver_category') or 'source')} is contributing pressure into {item.get('column', 'unknown')}.",
                }
            )
        for relationship in engine_result.get("evidence", []):
            if relationship.get("type") != "relationship_change":
                continue
            columns = relationship.get("columns", [])
            if len(columns) < 2:
                continue
            first = normalize_node_id(columns[0])
            second = normalize_node_id(columns[1])
            nodes.setdefault(first, {"id": first, "label": columns[0], "type": "signal", "pressure_score": 0.44})
            nodes.setdefault(second, {"id": second, "label": columns[1], "type": "signal", "pressure_score": 0.48})
            change = min(abs(float(relationship.get("change") or 0.0)) / 2.0, 1.0)
            edges.append(
                {
                    "source": first,
                    "target": second,
                    "weight": round(change, 4),
                    "directionality": directional_flow(columns[0], columns[1]),
                    "explanation": relationship_sentence(columns[0], columns[1]),
                }
            )
        ordered_edges = sorted(edges, key=lambda item: item["weight"], reverse=True)
        dominant_pathways = [
            f"{edge['source']} -> {edge['target']}"
            for edge in ordered_edges[:3]
        ]
        return {
            "nodes": list(nodes.values()),
            "edges": ordered_edges,
            "source_localization": {
                "dominant_source": source,
                "dominant_source_label": nodes[source]["label"],
            },
            "dominant_pathways": dominant_pathways,
            "propagation_score": round(sum(edge["weight"] for edge in ordered_edges[:4]) / max(min(len(ordered_edges), 4), 1), 4) if ordered_edges else 0.0,
            "dependency_weighting": dependency_weighting(ordered_edges),
        }


def normalize_node_id(value: str) -> str:
    return str(value).strip().lower().replace(" ", "_")


def display_name(value: str) -> str:
    return str(value).replace("_", " ")


def pressure_from_drift(item: dict[str, Any]) -> float:
    percent = abs(float(item.get("percent_change") or 0.0)) / 100.0
    return round(min(max(percent, 0.15), 1.0), 4)


def directional_flow(first: str, second: str) -> str:
    normalized = f"{first} {second}".lower()
    if "airflow" in normalized and "humidity" in normalized:
        return "airflow_to_moisture"
    if "thermal" in normalized or "temperature" in normalized:
        return "thermal_to_environment"
    return "structural_pressure_flow"


def relationship_sentence(first: str, second: str) -> str:
    normalized = f"{first} {second}".lower()
    if "airflow" in normalized and "humidity" in normalized:
        return "Airflow imbalance is propagating into humidity response instability."
    if "temperature" in normalized and "humidity" in normalized:
        return "Thermal lag is propagating into humidity compensation behavior."
    return f"Structural pressure is propagating from {first} into {second}."


def dependency_weighting(edges: list[dict[str, Any]]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for edge in edges:
        weights[edge["target"]] = round(weights.get(edge["target"], 0.0) + float(edge["weight"]), 4)
    return weights

