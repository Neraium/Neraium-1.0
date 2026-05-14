from __future__ import annotations

from typing import Any


FACILITY_SUBSYSTEMS = (
    "HVAC",
    "dehumidification",
    "irrigation",
    "thermal systems",
    "power systems",
    "environmental systems",
    "operator interventions",
    "external conditions",
)


class FacilityCognitionEngine:
    def build_state(
        self,
        *,
        room_summary: dict[str, Any] | None,
        driver_attribution: dict[str, Any],
        engine_result: dict[str, Any],
        causality_graph: dict[str, Any],
    ) -> dict[str, Any]:
        room_count = int((room_summary or {}).get("room_count", 1) or 1)
        system_evidence = engine_result.get("system_evidence", {}).get("categories", {})
        subsystem_pressures = {
            normalize_subsystem(name): round(min(len(details.get("signals", [])) * 0.18 + len(details.get("evidence", [])) * 0.12, 1.0), 4)
            for name, details in system_evidence.items()
            if len(details.get("signals", [])) or len(details.get("evidence", []))
        }
        if not subsystem_pressures:
            subsystem_pressures = {normalize_subsystem(driver_attribution.get("driver_category") or "environmental systems"): 0.24}
        total_pressure = sum(subsystem_pressures.values())
        dominant_share = max(subsystem_pressures.values()) / max(total_pressure, 1e-6)
        global_pressure_score = min(total_pressure / max(len(subsystem_pressures), 1), 1.0)
        topology_nodes = [
            {
                "id": normalize_subsystem(system),
                "label": system,
                "pressure_score": round(subsystem_pressures.get(normalize_subsystem(system), 0.0), 4),
            }
            for system in FACILITY_SUBSYSTEMS
        ]
        dependency_map = {
            edge["source"]: [related["target"] for related in causality_graph.get("edges", []) if related["source"] == edge["source"]]
            for edge in causality_graph.get("edges", [])[:6]
        }
        return {
            "facility_topology_graph": {
                "nodes": topology_nodes,
                "edges": causality_graph.get("edges", [])[:8],
            },
            "subsystem_dependency_map": dependency_map,
            "cross_system_instability_propagation": causality_graph.get("dominant_pathways", [])[:4],
            "global_structural_pressure_score": round(global_pressure_score, 4),
            "facility_cognition_state": facility_state_label(global_pressure_score, room_count),
            "subsystem_pressure": {
                "subsystems": subsystem_pressures,
                "pressure_score": round(global_pressure_score, 4),
                "volatility_index": round(min(float(causality_graph.get("propagation_score", 0.0)) * 0.7 + dominant_share * 0.3, 1.0), 4),
                "dominant_subsystem_share": round(dominant_share, 4),
                "runway_compression": round(min(global_pressure_score * 0.65 + float(causality_graph.get("propagation_score", 0.0)) * 0.35, 1.0), 4),
            },
        }


def normalize_subsystem(value: str) -> str:
    return str(value).strip().lower().replace("_", " ")


def facility_state_label(global_pressure_score: float, room_count: int) -> str:
    if global_pressure_score >= 0.58:
        return f"Facility-wide structural pressure active across {room_count} room(s)."
    if global_pressure_score >= 0.34:
        return f"Localized structural pressure is building across {room_count} room(s)."
    return f"Facility structure remains mostly convergent across {room_count} room(s)."

