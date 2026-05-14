from __future__ import annotations

from typing import Any


class EvidenceLineageEngine:
    def build(self, *, intelligence: dict[str, Any], engine_result: dict[str, Any] | None = None) -> dict[str, Any]:
        engine_result = engine_result or {}
        lineages: list[dict[str, Any]] = []
        for archetype in intelligence.get("active_archetypes", [])[:5]:
            lineages.append(
                self._lineage_for_archetype(
                    archetype=archetype,
                    intelligence=intelligence,
                    engine_result=engine_result,
                )
            )
        if not lineages:
            lineages.append(self._fallback_lineage(intelligence))
        corroboration = evidence_corroboration(lineages)
        return {
            "lineages": lineages,
            "corroboration_model": {
                "evidence_density": density_level(lineages),
                "corroboration_quality": corroboration,
                "persistence_consistency": persistence_consistency(intelligence, engine_result),
                "topology_agreement": topology_agreement(intelligence),
            },
        }

    def _lineage_for_archetype(
        self,
        *,
        archetype: dict[str, Any],
        intelligence: dict[str, Any],
        engine_result: dict[str, Any],
    ) -> dict[str, Any]:
        memory_matches = intelligence.get("structural_memory", {}).get("memory_matches", [])
        propagation_edges = intelligence.get("causality_graph", {}).get("edges", [])
        relationship_changes = [
            item
            for item in engine_result.get("evidence", [])
            if item.get("type") == "relationship_change"
        ]
        persistent = engine_result.get("persistence_assessment", {}).get("persistent_columns", [])
        return {
            "target": archetype.get("name", "UNSPECIFIED_ARCHETYPE"),
            "evidence_sources": {
                "supporting_signals": intelligence.get("supporting_evidence", [])[:4],
                "relationship_changes": [item.get("columns", []) for item in relationship_changes[:4]],
                "persistence_evidence": persistent[:4],
                "corroborating_subsystems": list(intelligence.get("facility_cognition", {}).get("subsystem_pressure", {}).get("subsystems", {}).keys())[:6],
                "propagation_confirmations": [edge.get("explanation") for edge in propagation_edges[:4] if edge.get("explanation")],
                "historical_memory_references": [item.get("fingerprint_id") for item in memory_matches[:3]],
                "topology_evidence": intelligence.get("causality_graph", {}).get("dominant_pathways", [])[:4],
                "timeline_evidence": timeline_evidence(intelligence),
            },
            "confidence_factors": {
                "evidence_density": density_level_from_counts(
                    signal_count=len(intelligence.get("supporting_evidence", [])),
                    relationship_count=len(relationship_changes),
                    propagation_count=len(propagation_edges),
                ),
                "corroboration_strength": archetype.get("evidence_strength", "developing"),
                "persistence_score": persistence_score(persistent),
                "topology_support": support_level(len(intelligence.get("causality_graph", {}).get("dominant_pathways", []))),
                "propagation_support": support_level(len(propagation_edges)),
                "historical_similarity": memory_similarity_level(memory_matches),
            },
            "evidence_timeline": timeline_evidence(intelligence),
        }

    def _fallback_lineage(self, intelligence: dict[str, Any]) -> dict[str, Any]:
        return {
            "target": "FACILITY_COGNITION_STATE",
            "evidence_sources": {
                "supporting_signals": intelligence.get("supporting_evidence", []),
                "relationship_changes": intelligence.get("relationship_evidence", []),
                "persistence_evidence": [],
                "corroborating_subsystems": [],
                "propagation_confirmations": [],
                "historical_memory_references": [],
                "topology_evidence": [],
                "timeline_evidence": timeline_evidence(intelligence),
            },
            "confidence_factors": {
                "evidence_density": "LOW",
                "corroboration_strength": "developing",
                "persistence_score": "LOW",
                "topology_support": "LOW",
                "propagation_support": "LOW",
                "historical_similarity": "LOW",
            },
            "evidence_timeline": timeline_evidence(intelligence),
        }


def timeline_evidence(intelligence: dict[str, Any]) -> list[dict[str, Any]]:
    ts = intelligence.get("last_updated")
    return [
        {"timestamp": ts, "event": "supporting_signal_captured"},
        {"timestamp": ts, "event": "relationship_shift_validated"},
        {"timestamp": ts, "event": "cognition_state_emitted"},
    ]


def persistence_score(persistent_columns: list[str]) -> str:
    if len(persistent_columns) >= 3:
        return "HIGH"
    if len(persistent_columns) >= 1:
        return "MODERATE"
    return "LOW"


def support_level(count: int) -> str:
    if count >= 4:
        return "HIGH"
    if count >= 2:
        return "MODERATE"
    return "LOW"


def memory_similarity_level(memory_matches: list[dict[str, Any]]) -> str:
    if not memory_matches:
        return "LOW"
    score = float(memory_matches[0].get("similarity_score", 0.0))
    if score >= 0.7:
        return "HIGH"
    if score >= 0.5:
        return "MODERATE"
    return "LOW"


def density_level(lineages: list[dict[str, Any]]) -> str:
    sources = sum(len(item.get("evidence_sources", {}).get("supporting_signals", [])) for item in lineages)
    if sources >= 10:
        return "HIGH"
    if sources >= 5:
        return "MODERATE"
    return "LOW"


def density_level_from_counts(*, signal_count: int, relationship_count: int, propagation_count: int) -> str:
    total = signal_count + relationship_count + propagation_count
    if total >= 10:
        return "HIGH"
    if total >= 5:
        return "MODERATE"
    return "LOW"


def evidence_corroboration(lineages: list[dict[str, Any]]) -> str:
    high = sum(1 for item in lineages if item.get("confidence_factors", {}).get("corroboration_strength") == "strong")
    if high >= 2:
        return "STRONG"
    if high >= 1:
        return "MODERATE"
    return "DEVELOPING"


def persistence_consistency(intelligence: dict[str, Any], engine_result: dict[str, Any]) -> str:
    persistent = engine_result.get("persistence_assessment", {}).get("persistent_columns", [])
    if not persistent:
        return "LOW"
    if len(persistent) >= 2 and intelligence.get("urgency") in {"review", "unstable"}:
        return "HIGH"
    return "MODERATE"


def topology_agreement(intelligence: dict[str, Any]) -> str:
    paths = intelligence.get("causality_graph", {}).get("dominant_pathways", [])
    if len(paths) >= 3:
        return "HIGH"
    if len(paths) >= 1:
        return "MODERATE"
    return "LOW"
