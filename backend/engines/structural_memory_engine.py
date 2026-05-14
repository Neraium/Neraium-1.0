from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StructuralFingerprint:
    fingerprint_id: str
    label: str
    topology_drift_progression: list[float]
    subsystem_pressure_migration: dict[str, float]
    relationship_evolution_trajectory: list[float]
    propagation_sequence: list[str]
    volatility_acceleration: float
    operator_intervention_outcomes: list[str]
    recovery_behaviors: list[str]
    persistence_timeline: list[str]
    archetypes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StructuralMemoryMatch:
    fingerprint: StructuralFingerprint
    similarity_score: float
    matched_dimensions: list[str]
    progression_match_score: float
    confidence_band: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint_id": self.fingerprint.fingerprint_id,
            "label": self.fingerprint.label,
            "similarity_score": round(self.similarity_score, 4),
            "progression_match_score": round(self.progression_match_score, 4),
            "confidence_band": self.confidence_band,
            "matched_dimensions": self.matched_dimensions,
            "propagation_sequence": self.fingerprint.propagation_sequence,
            "archetypes": self.fingerprint.archetypes,
            "operator_intervention_outcomes": self.fingerprint.operator_intervention_outcomes,
            "recovery_behaviors": self.fingerprint.recovery_behaviors,
            "persistence_timeline": self.fingerprint.persistence_timeline,
        }


DEFAULT_STRUCTURAL_MEMORY: tuple[StructuralFingerprint, ...] = (
    StructuralFingerprint(
        fingerprint_id="fp-compensation-masking-001",
        label="Compensation masking through thermal lag",
        topology_drift_progression=[0.14, 0.19, 0.27, 0.36],
        subsystem_pressure_migration={"airflow_restriction": 0.32, "thermal_control": 0.41, "moisture_control": 0.27},
        relationship_evolution_trajectory=[0.11, 0.22, 0.31, 0.44],
        propagation_sequence=["airflow imbalance", "thermal lag", "humidity compensation", "VPD instability"],
        volatility_acceleration=0.18,
        operator_intervention_outcomes=["airflow path cleared", "thermal recovery improved after 2 windows"],
        recovery_behaviors=["pressure redistributed away from thermal subsystem", "relationship coherence partially restored"],
        persistence_timeline=["window_1_watch", "window_2_review", "window_3_review", "window_4_recovery"],
        archetypes=["COMPENSATION_MASKING", "THERMAL_LAG_PROPAGATION"],
    ),
    StructuralFingerprint(
        fingerprint_id="fp-fragmentation-002",
        label="Cross-system fragmentation with facility pressure accumulation",
        topology_drift_progression=[0.21, 0.29, 0.42, 0.53],
        subsystem_pressure_migration={"thermal_control": 0.28, "moisture_control": 0.22, "energy_schedule": 0.24, "sensor_network": 0.12},
        relationship_evolution_trajectory=[0.18, 0.26, 0.39, 0.51],
        propagation_sequence=["schedule mismatch", "thermal overshoot", "moisture lag", "subsystem fragmentation"],
        volatility_acceleration=0.24,
        operator_intervention_outcomes=["staggered reset reduced spread", "recovery took 5 operating days"],
        recovery_behaviors=["dependency pressure fell gradually", "cross-system coupling recovered late"],
        persistence_timeline=["window_1_review", "window_2_review", "window_3_unstable", "window_4_unstable"],
        archetypes=["SUBSYSTEM_FRAGMENTATION", "PROPAGATION_ACCELERATION"],
    ),
    StructuralFingerprint(
        fingerprint_id="fp-recovery-convergence-003",
        label="Recovery convergence after targeted intervention",
        topology_drift_progression=[0.28, 0.24, 0.18, 0.09],
        subsystem_pressure_migration={"moisture_control": 0.44, "thermal_control": 0.31},
        relationship_evolution_trajectory=[0.37, 0.28, 0.19, 0.1],
        propagation_sequence=["humidity lag", "thermal support", "pressure release", "recovery convergence"],
        volatility_acceleration=-0.12,
        operator_intervention_outcomes=["dehumidification response tuned", "coupling normalized within 3 windows"],
        recovery_behaviors=["instability pathways collapsed", "persistence cleared"],
        persistence_timeline=["window_1_review", "window_2_watch", "window_3_nominal"],
        archetypes=["RECOVERY_CONVERGENCE"],
    ),
)


class StructuralMemoryEngine:
    def __init__(self, memory_bank: tuple[StructuralFingerprint, ...] = DEFAULT_STRUCTURAL_MEMORY) -> None:
        self._memory_bank = memory_bank

    def build_fingerprint(
        self,
        *,
        baseline_analysis: dict[str, Any],
        engine_result: dict[str, Any],
        driver_attribution: dict[str, Any],
        room_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        drift_values = [
            abs(float(item.get("percent_change") or 0.0)) / 100.0
            for item in baseline_analysis.get("column_drift", [])
            if item.get("drift_flag") in {"watch", "review"}
        ]
        if not drift_values:
            drift_values = [0.05]
        relationship_steps = [
            min(abs(float(item.get("change") or 0.0)) / 2.0, 1.0)
            for item in engine_result.get("evidence", [])
            if item.get("type") == "relationship_change"
        ] or [0.08]
        persistence = engine_result.get("persistence_assessment", {}).get("persistent_columns", [])
        propagation_sequence = infer_propagation_sequence(driver_attribution, engine_result)
        subsystem_pressure = subsystem_pressure_migration(driver_attribution, engine_result)
        return {
            "fingerprint_id": "active-structural-fingerprint",
            "label": driver_attribution.get("likely_driver") or "Active structural pattern",
            "topology_drift_progression": round_series(drift_values[:4]),
            "subsystem_pressure_migration": subsystem_pressure,
            "relationship_evolution_trajectory": round_series(relationship_steps[:4]),
            "propagation_sequence": propagation_sequence,
            "volatility_acceleration": round(compute_acceleration(drift_values), 4),
            "operator_intervention_outcomes": operator_outcomes(room_summary),
            "recovery_behaviors": ["Recovery behavior not established yet." if persistence else "Recovery convergence remains possible if current pressure stabilizes."],
            "persistence_timeline": build_persistence_timeline(persistence, len(drift_values)),
            "archetypes": [],
        }

    def retrieve(
        self,
        *,
        fingerprint: dict[str, Any],
        limit: int = 3,
    ) -> dict[str, Any]:
        matches: list[StructuralMemoryMatch] = []
        active_sequence = fingerprint.get("propagation_sequence", [])
        active_pressure = fingerprint.get("subsystem_pressure_migration", {})
        active_drift = fingerprint.get("topology_drift_progression", [])
        for candidate in self._memory_bank:
            sequence_score = sequence_similarity(active_sequence, candidate.propagation_sequence)
            pressure_score = pressure_similarity(active_pressure, candidate.subsystem_pressure_migration)
            drift_score = series_similarity(active_drift, candidate.topology_drift_progression)
            volatility_score = 1.0 - min(abs(float(fingerprint.get("volatility_acceleration", 0.0)) - candidate.volatility_acceleration), 1.0)
            overall = max(min(sequence_score * 0.35 + pressure_score * 0.25 + drift_score * 0.25 + volatility_score * 0.15, 1.0), 0.0)
            matches.append(
                StructuralMemoryMatch(
                    fingerprint=candidate,
                    similarity_score=overall,
                    progression_match_score=(sequence_score + drift_score) / 2,
                    matched_dimensions=matched_dimensions(sequence_score, pressure_score, drift_score, volatility_score),
                    confidence_band=memory_confidence_band(overall),
                )
            )
        matches.sort(key=lambda item: item.similarity_score, reverse=True)
        ranked = [item.to_dict() for item in matches[:limit]]
        return {
            "active_fingerprint": fingerprint,
            "memory_matches": ranked,
            "retrieval_status": "matched" if ranked else "no_match",
        }


def infer_propagation_sequence(driver_attribution: dict[str, Any], engine_result: dict[str, Any]) -> list[str]:
    category = str(driver_attribution.get("driver_category", "unknown_system_drift"))
    relationship_changes = [
        item for item in engine_result.get("evidence", [])
        if item.get("type") == "relationship_change"
    ]
    if relationship_changes:
        first = relationship_changes[0].get("columns", [])
        if len(first) >= 2:
            return [display_name(category), first[0], first[1], "structural pressure accumulation"]
    return [display_name(category), "relationship strain", "continuation pressure"]


def subsystem_pressure_migration(driver_attribution: dict[str, Any], engine_result: dict[str, Any]) -> dict[str, float]:
    categories = engine_result.get("system_evidence", {}).get("categories", {})
    migration: dict[str, float] = {}
    for category, details in categories.items():
        evidence_count = len(details.get("evidence", []))
        signal_count = len(details.get("signals", []))
        if evidence_count or signal_count:
            migration[category] = round(min(evidence_count * 0.18 + signal_count * 0.14, 1.0), 4)
    primary = str(driver_attribution.get("driver_category", "unknown_system_drift"))
    if primary and primary not in migration:
        migration[primary] = 0.22
    return migration or {primary: 0.12}


def compute_acceleration(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(values[-1] - values[0]) / max(len(values) - 1, 1)


def round_series(values: list[float]) -> list[float]:
    return [round(float(value), 4) for value in values]


def operator_outcomes(room_summary: dict[str, Any] | None) -> list[str]:
    room_count = int((room_summary or {}).get("room_count", 1) or 1)
    if room_count > 1:
        return ["Multi-room upload captured; intervention effect should be compared across rooms."]
    return ["Operator intervention outcome not yet observed in current upload."]


def build_persistence_timeline(persistent_columns: list[str], progression_length: int) -> list[str]:
    if not persistent_columns:
        return [f"window_{index + 1}_developing" for index in range(max(progression_length, 1))]
    return [
        f"window_{index + 1}_{'persistent' if index >= max(progression_length - 2, 0) else 'developing'}"
        for index in range(max(progression_length, 1))
    ]


def sequence_similarity(active: list[str], candidate: list[str]) -> float:
    if not active or not candidate:
        return 0.0
    active_tokens = {token.lower() for token in active}
    candidate_tokens = {token.lower() for token in candidate}
    overlap = len(active_tokens & candidate_tokens)
    return overlap / max(len(active_tokens | candidate_tokens), 1)


def pressure_similarity(active: dict[str, float], candidate: dict[str, float]) -> float:
    keys = set(active) | set(candidate)
    if not keys:
        return 0.0
    delta = sum(abs(float(active.get(key, 0.0)) - float(candidate.get(key, 0.0))) for key in keys)
    return max(0.0, 1.0 - delta / max(len(keys), 1))


def series_similarity(active: list[float], candidate: list[float]) -> float:
    if not active or not candidate:
        return 0.0
    compared = min(len(active), len(candidate))
    delta = sum(abs(float(active[index]) - float(candidate[index])) for index in range(compared))
    return max(0.0, 1.0 - delta / max(compared, 1))


def matched_dimensions(sequence_score: float, pressure_score: float, drift_score: float, volatility_score: float) -> list[str]:
    dimensions = []
    if sequence_score >= 0.3:
        dimensions.append("propagation_sequence")
    if pressure_score >= 0.4:
        dimensions.append("subsystem_pressure_migration")
    if drift_score >= 0.45:
        dimensions.append("topology_drift_progression")
    if volatility_score >= 0.5:
        dimensions.append("volatility_acceleration")
    return dimensions or ["weak_partial_match"]


def memory_confidence_band(score: float) -> str:
    if score >= 0.7:
        return "0.66-0.82"
    if score >= 0.5:
        return "0.5-0.68"
    return "0.28-0.52"


def display_name(value: str) -> str:
    return value.replace("_", " ")

