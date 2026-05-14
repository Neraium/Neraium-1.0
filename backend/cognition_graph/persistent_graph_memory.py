from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CognitionMemoryRecord:
    facility_id: str
    timestamp: str
    archetypes: list[str]
    propagation_paths: list[str]
    convergence_state: str
    recovery_state: str
    intervention_context: list[str]
    environmental_context: list[str]
    topology_transformation: str
    evidence_references: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GraphMemorySnapshot:
    snapshot_id: str
    facility_id: str
    timestamp: str
    graph_snapshot: dict[str, Any]
    record: CognitionMemoryRecord

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["record"] = self.record.to_dict()
        return payload


@dataclass(frozen=True)
class GraphMemoryQueryResult:
    query_type: str
    matches: list[dict[str, Any]]
    total_matches: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PersistentCognitionGraphMemory:
    snapshots: list[GraphMemorySnapshot] = field(default_factory=list)

    def append_graph_snapshot(
        self,
        *,
        facility_id: str,
        graph_snapshot: dict[str, Any],
        intelligence: dict[str, Any],
    ) -> GraphMemorySnapshot:
        record = CognitionMemoryRecord(
            facility_id=facility_id,
            timestamp=str(intelligence.get("last_updated", "")),
            archetypes=[item.get("name", "") for item in intelligence.get("active_archetypes", [])],
            propagation_paths=intelligence.get("causality_graph", {}).get("dominant_pathways", []),
            convergence_state=str(intelligence.get("recovery_convergence", {}).get("convergence_quality", "developing")),
            recovery_state=str(intelligence.get("recovery_convergence", {}).get("stabilization_progression", "tracking")),
            intervention_context=[item.get("label", "") for item in intelligence.get("operator_interaction_model", {}).get("adaptation_patterns", [])],
            environmental_context=intelligence.get("domain_cognition_pack", {}).get("environmental_context", []),
            topology_transformation=str(intelligence.get("structural_stability_index", {}).get("state", "WATCH")),
            evidence_references=[item.get("target", "") for item in intelligence.get("evidence_lineage", {}).get("lineages", [])],
        )
        snapshot = GraphMemorySnapshot(
            snapshot_id=f"{facility_id}-{len(self.snapshots) + 1}",
            facility_id=facility_id,
            timestamp=record.timestamp,
            graph_snapshot=graph_snapshot,
            record=record,
        )
        self.snapshots.append(snapshot)
        return snapshot

    def retrieve_similar_graph_states(self, *, archetypes: list[str], pathways: list[str]) -> GraphMemoryQueryResult:
        wanted_archetypes = set(archetypes)
        wanted_paths = set(pathways)
        matches: list[dict[str, Any]] = []
        for snapshot in self.snapshots:
            record = snapshot.record
            overlap = len(wanted_archetypes.intersection(record.archetypes)) + len(wanted_paths.intersection(record.propagation_paths))
            if overlap <= 0:
                continue
            matches.append(
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "facility_id": snapshot.facility_id,
                    "overlap_score": overlap,
                    "record": record.to_dict(),
                }
            )
        matches.sort(key=lambda item: item["overlap_score"], reverse=True)
        return GraphMemoryQueryResult(query_type="similar_graph_states", matches=matches, total_matches=len(matches))

    def query_recurring_propagation_paths(self) -> GraphMemoryQueryResult:
        counts: dict[str, int] = {}
        for snapshot in self.snapshots:
            for path in snapshot.record.propagation_paths:
                counts[path] = counts.get(path, 0) + 1
        matches = [{"path": path, "occurrences": count} for path, count in counts.items() if count > 1]
        matches.sort(key=lambda item: item["occurrences"], reverse=True)
        return GraphMemoryQueryResult(query_type="recurring_propagation_paths", matches=matches, total_matches=len(matches))

    def query_convergence_failures(self) -> GraphMemoryQueryResult:
        matches = [
            snapshot.to_dict()
            for snapshot in self.snapshots
            if snapshot.record.convergence_state.upper() in {"DETERIORATING", "FRAGMENTING", "LOW_CONVERGENCE"}
        ]
        return GraphMemoryQueryResult(query_type="convergence_failures", matches=matches, total_matches=len(matches))

    def query_recovery_patterns(self) -> GraphMemoryQueryResult:
        matches = [
            snapshot.to_dict()
            for snapshot in self.snapshots
            if "recover" in snapshot.record.recovery_state.lower() or "convergence" in snapshot.record.recovery_state.lower()
        ]
        return GraphMemoryQueryResult(query_type="recovery_patterns", matches=matches, total_matches=len(matches))

    def compare_facility_graph_histories(self, *, facility_a: str, facility_b: str) -> GraphMemoryQueryResult:
        a_records = [item for item in self.snapshots if item.facility_id == facility_a]
        b_records = [item for item in self.snapshots if item.facility_id == facility_b]
        matches = [
            {
                "facility_a": facility_a,
                "facility_b": facility_b,
                "snapshot_count_a": len(a_records),
                "snapshot_count_b": len(b_records),
                "shared_archetypes": sorted(
                    set(archetype for snap in a_records for archetype in snap.record.archetypes).intersection(
                        archetype for snap in b_records for archetype in snap.record.archetypes
                    )
                ),
            }
        ]
        return GraphMemoryQueryResult(query_type="facility_graph_history_comparison", matches=matches, total_matches=1)

