from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class StructuralArchetypeName(StrEnum):
    RELATIONSHIP_DECAY = "RELATIONSHIP_DECAY"
    LOAD_RESPONSE_MISMATCH = "LOAD_RESPONSE_MISMATCH"
    COMPENSATION_MASKING = "COMPENSATION_MASKING"
    THERMAL_LAG_PROPAGATION = "THERMAL_LAG_PROPAGATION"
    OSCILLATORY_INSTABILITY = "OSCILLATORY_INSTABILITY"
    SUBSYSTEM_FRAGMENTATION = "SUBSYSTEM_FRAGMENTATION"
    PROPAGATION_ACCELERATION = "PROPAGATION_ACCELERATION"
    RECOVERY_CONVERGENCE = "RECOVERY_CONVERGENCE"
    STRUCTURAL_COMPRESSION = "STRUCTURAL_COMPRESSION"
    VOLATILITY_CLUSTERING = "VOLATILITY_CLUSTERING"


@dataclass(frozen=True)
class StructuralArchetype:
    name: StructuralArchetypeName
    description: str
    structural_indicators: list[str]
    required_evidence: list[str]
    propagation_characteristics: list[str]
    persistence_conditions: list[str]
    recovery_indicators: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["name"] = self.name.value
        return payload


@dataclass(frozen=True)
class RankedArchetype:
    archetype: StructuralArchetype
    score: float
    evidence_strength: str
    confidence_band: str
    supporting_relationships: list[str]
    rationale: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.archetype.name.value,
            "description": self.archetype.description,
            "score": round(self.score, 4),
            "evidence_strength": self.evidence_strength,
            "confidence_band": self.confidence_band,
            "supporting_relationships": self.supporting_relationships,
            "rationale": self.rationale,
            "structural_indicators": self.archetype.structural_indicators,
            "required_evidence": self.archetype.required_evidence,
            "propagation_characteristics": self.archetype.propagation_characteristics,
            "persistence_conditions": self.archetype.persistence_conditions,
            "recovery_indicators": self.archetype.recovery_indicators,
        }


ARCHETYPES: tuple[StructuralArchetype, ...] = (
    StructuralArchetype(
        name=StructuralArchetypeName.RELATIONSHIP_DECAY,
        description="Relationship coherence is decaying faster than local signal magnitude alone would suggest.",
        structural_indicators=["relationship divergence", "pairwise decoupling", "persistent multi-signal drift"],
        required_evidence=["relationship_change evidence", "persistent drift", "baseline displacement"],
        propagation_characteristics=["coupling weakens before subsystem separation", "drift migrates across linked channels"],
        persistence_conditions=["repeated across recent windows", "more than one category involved"],
        recovery_indicators=["relationship recoupling", "pressure migration slows"],
    ),
    StructuralArchetype(
        name=StructuralArchetypeName.LOAD_RESPONSE_MISMATCH,
        description="Demand or load signatures are no longer met by subsystem response patterns.",
        structural_indicators=["thermal or moisture drift", "recovery lag", "response asymmetry"],
        required_evidence=["baseline drift", "response lag", "corroborating category drift"],
        propagation_characteristics=["load stress appears upstream", "response lag appears downstream"],
        persistence_conditions=["elevated pressure remains after transitions"],
        recovery_indicators=["response lag contracts", "baseline alignment returns"],
    ),
    StructuralArchetype(
        name=StructuralArchetypeName.COMPENSATION_MASKING,
        description="One subsystem appears stable only because another subsystem is absorbing structural pressure.",
        structural_indicators=["moderate score but strong corroboration", "cross-category compensation", "masked instability"],
        required_evidence=["relationship evidence", "multi-category drift", "operator intervention history"],
        propagation_characteristics=["pressure migration", "apparent local stability with downstream strain"],
        persistence_conditions=["compensating subsystem remains active", "pressure does not dissipate"],
        recovery_indicators=["support subsystem load relaxes", "masked drift becomes visible or resolves"],
    ),
    StructuralArchetype(
        name=StructuralArchetypeName.THERMAL_LAG_PROPAGATION,
        description="Thermal recovery lag is propagating into adjacent environmental relationships.",
        structural_indicators=["thermal drift", "recovery mismatch", "humidity or airflow coupling change"],
        required_evidence=["thermal baseline drift", "relationship coupling evidence"],
        propagation_characteristics=["thermal response lag pushes into moisture or VPD stability"],
        persistence_conditions=["repeated lag across recent windows"],
        recovery_indicators=["thermal response recovers before downstream pressure builds"],
    ),
    StructuralArchetype(
        name=StructuralArchetypeName.OSCILLATORY_INSTABILITY,
        description="Structural pressure is alternating instead of converging, increasing control volatility.",
        structural_indicators=["high variability", "alternating response", "velocity reversals"],
        required_evidence=["variability evidence", "instability velocity change"],
        propagation_characteristics=["instability revisits the same subsystem in cycles"],
        persistence_conditions=["high variance remains after baseline resets"],
        recovery_indicators=["variance compresses", "velocity settles"],
    ),
    StructuralArchetype(
        name=StructuralArchetypeName.SUBSYSTEM_FRAGMENTATION,
        description="Subsystems are losing shared operating coherence and beginning to fragment.",
        structural_indicators=["three or more categories involved", "cross-system decoupling", "facility pressure accumulation"],
        required_evidence=["strong corroboration", "relationship drift", "multi-system topology change"],
        propagation_characteristics=["pressure spreads across facility boundaries"],
        persistence_conditions=["more than one subsystem remains unstable"],
        recovery_indicators=["cross-system coupling returns", "global pressure score declines"],
    ),
    StructuralArchetype(
        name=StructuralArchetypeName.PROPAGATION_ACCELERATION,
        description="Instability is moving faster through the graph than recent patterns would normally support.",
        structural_indicators=["velocity increase", "shrinking continuation window", "dominant path concentration"],
        required_evidence=["propagation score", "counterfactual window compression"],
        propagation_characteristics=["pathways strengthen over time", "source pressure concentrates downstream"],
        persistence_conditions=["acceleration remains positive across windows"],
        recovery_indicators=["path dominance weakens", "window widens"],
    ),
    StructuralArchetype(
        name=StructuralArchetypeName.RECOVERY_CONVERGENCE,
        description="Separate signals are returning toward a shared operating rhythm after intervention or drift.",
        structural_indicators=["stable urgency", "reduced drift", "restored relationship coherence"],
        required_evidence=["nominal pressure", "reduced persistence", "recovery behavior"],
        propagation_characteristics=["pressure pathways collapse rather than spread"],
        persistence_conditions=["recovery remains visible across windows"],
        recovery_indicators=["continued convergence", "memory match to prior recoveries"],
    ),
    StructuralArchetype(
        name=StructuralArchetypeName.STRUCTURAL_COMPRESSION,
        description="Operational runway is shortening because several weak shifts are compressing into the same decision horizon.",
        structural_indicators=["multiple watch signals", "intervention window compression", "stacked evidence"],
        required_evidence=["multi-signal watch/review state", "compressed window"],
        propagation_characteristics=["localized drift aggregates into facility-level pressure"],
        persistence_conditions=["compressed runway remains despite limited severity"],
        recovery_indicators=["decision horizon expands", "weak signals disperse"],
    ),
    StructuralArchetype(
        name=StructuralArchetypeName.VOLATILITY_CLUSTERING,
        description="Instability is clustering around a small set of subsystems instead of diffusing evenly.",
        structural_indicators=["high variability", "localized dominant pathways", "repeated subsystem targeting"],
        required_evidence=["variability evidence", "pathway concentration"],
        propagation_characteristics=["clusters strengthen around the same subsystem family"],
        persistence_conditions=["same nodes remain active across windows"],
        recovery_indicators=["cluster concentration drops", "pressure redistributes or settles"],
    ),
)


class StructuralArchetypeClassifier:
    def __init__(self, archetypes: tuple[StructuralArchetype, ...] = ARCHETYPES) -> None:
        self._archetypes = archetypes

    def classify(
        self,
        *,
        topology_drift: dict[str, Any],
        subsystem_pressure: dict[str, Any],
        relationship_changes: list[dict[str, Any]],
        persistence: dict[str, Any],
        propagation_velocity: float,
        acceleration: float,
        facility_pressure_score: float,
        intervention_history: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        intervention_history = intervention_history or []
        ranked: list[RankedArchetype] = []
        corroboration = str(topology_drift.get("corroboration_level", "limited"))
        category_count = int(topology_drift.get("meaningful_categories", 0))
        persistent_count = len(persistence.get("persistent_columns", []))
        relationship_count = len(relationship_changes)
        volatility = float(subsystem_pressure.get("volatility_index", 0.0))
        compression = float(subsystem_pressure.get("runway_compression", 0.0))
        for archetype in self._archetypes:
            score = 0.0
            rationale: list[str] = []
            if archetype.name is StructuralArchetypeName.RELATIONSHIP_DECAY:
                score += relationship_count * 0.18 + persistent_count * 0.12
                if corroboration in {"moderate", "strong"}:
                    score += 0.18
                    rationale.append("Cross-signal corroboration supports decaying relationship coherence.")
            elif archetype.name is StructuralArchetypeName.LOAD_RESPONSE_MISMATCH:
                score += float(subsystem_pressure.get("pressure_score", 0.0)) * 0.45
                if persistent_count:
                    score += 0.16
                    rationale.append("Persistent drift suggests response is not closing against current load.")
            elif archetype.name is StructuralArchetypeName.COMPENSATION_MASKING:
                if corroboration == "strong":
                    score += 0.26
                if relationship_count and category_count >= 2:
                    score += 0.24
                    rationale.append("Multiple subsystems show coordination strain without a single isolated failure mode.")
                if intervention_history:
                    score += 0.1
            elif archetype.name is StructuralArchetypeName.THERMAL_LAG_PROPAGATION:
                thermal_pressure = float(subsystem_pressure.get("subsystems", {}).get("thermal_control", 0.0))
                score += thermal_pressure * 0.55
                if any("humidity" in " ".join(item.get("columns", [])).lower() for item in relationship_changes):
                    score += 0.18
            elif archetype.name is StructuralArchetypeName.OSCILLATORY_INSTABILITY:
                score += volatility * 0.6 + max(acceleration, 0.0) * 0.12
                if relationship_count:
                    rationale.append("Variability and changing relationships suggest instability is cycling rather than settling.")
            elif archetype.name is StructuralArchetypeName.SUBSYSTEM_FRAGMENTATION:
                score += min(category_count / 4, 1.0) * 0.45 + facility_pressure_score * 0.25
                if corroboration == "strong":
                    score += 0.18
            elif archetype.name is StructuralArchetypeName.PROPAGATION_ACCELERATION:
                score += max(propagation_velocity, 0.0) * 0.4 + max(acceleration, 0.0) * 0.25 + compression * 0.15
            elif archetype.name is StructuralArchetypeName.RECOVERY_CONVERGENCE:
                if facility_pressure_score < 0.35 and persistent_count == 0:
                    score += 0.48
                    rationale.append("Pressure remains low and persistence is not reinforcing deterioration.")
                if relationship_count <= 1:
                    score += 0.08
            elif archetype.name is StructuralArchetypeName.STRUCTURAL_COMPRESSION:
                score += compression * 0.55 + (relationship_count * 0.08)
                if persistent_count >= 1:
                    score += 0.12
            elif archetype.name is StructuralArchetypeName.VOLATILITY_CLUSTERING:
                dominant = float(subsystem_pressure.get("dominant_subsystem_share", 0.0))
                score += dominant * 0.45 + volatility * 0.25
                if category_count <= 2 and dominant >= 0.45:
                    rationale.append("Instability appears concentrated in a narrow subsystem cluster.")
            score = min(max(score, 0.0), 1.0)
            if score < 0.22:
                continue
            ranked.append(
                RankedArchetype(
                    archetype=archetype,
                    score=score,
                    evidence_strength=evidence_strength_for_score(score),
                    confidence_band=confidence_band_for_score(score),
                    supporting_relationships=supporting_relationships(relationship_changes),
                    rationale=rationale or default_rationale(archetype, category_count, persistent_count, relationship_count),
                )
            )
        ranked.sort(key=lambda item: item.score, reverse=True)
        return [item.to_dict() for item in ranked[:5]]


def evidence_strength_for_score(score: float) -> str:
    if score >= 0.72:
        return "strong"
    if score >= 0.48:
        return "moderate"
    return "developing"


def confidence_band_for_score(score: float) -> str:
    if score >= 0.72:
        return "0.68-0.84"
    if score >= 0.48:
        return "0.48-0.72"
    return "0.28-0.56"


def supporting_relationships(relationship_changes: list[dict[str, Any]]) -> list[str]:
    relationships: list[str] = []
    for item in relationship_changes[:4]:
        columns = item.get("columns", [])
        if len(columns) >= 2:
            relationships.append(f"{columns[0]} -> {columns[1]}")
    return relationships


def default_rationale(
    archetype: StructuralArchetype,
    category_count: int,
    persistent_count: int,
    relationship_count: int,
) -> list[str]:
    return [
        archetype.description,
        f"Active categories: {category_count}, persistent columns: {persistent_count}, relationship shifts: {relationship_count}.",
    ]

