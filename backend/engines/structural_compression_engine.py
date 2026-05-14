from __future__ import annotations

from typing import Any


class StructuralCompressionEngine:
    def detect(
        self,
        *,
        baseline_analysis: dict[str, Any],
        engine_result: dict[str, Any],
        causality_graph: dict[str, Any],
    ) -> dict[str, Any]:
        drift_watch = sum(1 for item in baseline_analysis.get("column_drift", []) if item.get("drift_flag") == "watch")
        drift_review = sum(1 for item in baseline_analysis.get("column_drift", []) if item.get("drift_flag") == "review")
        relationship_count = sum(1 for item in engine_result.get("evidence", []) if item.get("type") == "relationship_change")
        pathway_density = len(causality_graph.get("edges", []))
        volatility = float(engine_result.get("system_evidence", {}).get("numeric_signals_showing_meaningful_change", 0)) / 5.0
        intensity = min(1.0, drift_watch * 0.09 + drift_review * 0.18 + relationship_count * 0.08 + pathway_density * 0.04 + volatility * 0.12)
        hidden_indicators = []
        if drift_watch >= 2 and drift_review <= 1:
            hidden_indicators.append("volatility_compression")
        if relationship_count >= 2 and drift_review <= 1:
            hidden_indicators.append("relationship_tightening_without_full_divergence")
        if pathway_density >= 3:
            hidden_indicators.append("hidden_pressure_accumulation")
        if not hidden_indicators:
            hidden_indicators.append("compression_not_dominant")
        return {
            "compression_intensity": intensity_label(intensity),
            "compression_index": round(intensity, 4),
            "hidden_instability_indicators": hidden_indicators,
            "compression_persistence": persistence_label(drift_watch, relationship_count),
            "delayed_divergence_risk": risk_label(intensity, drift_review),
        }


def intensity_label(value: float) -> str:
    if value >= 0.68:
        return "HIGH_COMPRESSION"
    if value >= 0.45:
        return "MODERATE_COMPRESSION"
    return "LOW_COMPRESSION"


def persistence_label(drift_watch: int, relationships: int) -> str:
    if drift_watch >= 3 and relationships >= 2:
        return "PERSISTENT"
    if drift_watch >= 2 or relationships >= 2:
        return "EMERGING"
    return "LIMITED"


def risk_label(value: float, drift_review: int) -> str:
    if value >= 0.68 and drift_review >= 1:
        return "ELEVATED_DELAYED_DIVERGENCE_RISK"
    if value >= 0.45:
        return "WATCH_DELAYED_DIVERGENCE_RISK"
    return "LOW_DELAYED_DIVERGENCE_RISK"

