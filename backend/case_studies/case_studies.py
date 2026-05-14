from __future__ import annotations

from typing import Any


def load_case_studies() -> list[dict[str, Any]]:
    return [
        case("cultivation", "airflow fragmentation progression"),
        case("data_centers", "load-response mismatch under cooling strain"),
        case("aerospace_manufacturing", "subsystem desynchronization across shift transition"),
        case("hvac_systems", "thermal propagation with delayed convergence"),
        case("energy_infrastructure", "cascading compensation under load redistribution"),
    ]


def case(domain: str, scenario: str) -> dict[str, Any]:
    return {
        "domain": domain,
        "scenario": scenario,
        "replay_timeline": ["stable_topology", "relationship_weakening", "pressure_migration", "propagation_activation"],
        "topology_evolution": ["coherent", "drifting", "fragmenting"],
        "subsystem_pressure_migration": ["upstream->downstream"],
        "archetype_activation": ["RELATIONSHIP_DECAY", "PROPAGATION_ACCELERATION"],
        "propagation_pathways": ["path_a", "path_b"],
        "continuation_windows": ["6-10 operational days"],
        "evidence_overlays": ["relationship evidence", "topology evidence"],
        "convergence_tracking": ["recovery_convergence"],
    }

