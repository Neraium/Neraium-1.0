"""
SIIEngine Adapter: Bridges SIIEngine unified output to API/UI contracts.

This adapter consolidates the SIIEngine as the single source of truth for:
- instability_score (normalized, [0,1])
- regime (STABLE, TRANSITION, UNSTABLE, LOCK_IN)
- urgency (NOMINAL, WATCH, ALERT, CRITICAL)
- structural_drift, drift_velocity, transition_pressure
- confidence, gradient_norm, recovery_alignment

Responsibilities:
1. Maintain per-asset engine instances
2. Track detection lead times (cycles before threshold alert)
3. Expose unified output in API-compatible format
4. Support baseline comparison runners
5. Ensure no UI component computes regime or urgency independently
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, Optional
from collections import defaultdict
import numpy as np

from neraium_core.sii_engine_unified import SIIEngine, SIIEngineOutput


@dataclass
class DetectionContext:
    """Tracks when instability was first detected relative to failure."""
    first_detection_cycle: Optional[int] = None
    threshold_alert_cycle: Optional[int] = None
    lead_time_cycles: Optional[int] = None
    detection_confidence: float = 0.0
    novelty_vs_baseline: float = 0.0


@dataclass
class ComparisonMetrics:
    """Baseline comparison metrics for validation."""
    sii_instability_score: float = 0.0
    sii_detection_cycle: Optional[int] = None

    threshold_score: float = 0.0
    threshold_detection_cycle: Optional[int] = None

    zscore_score: float = 0.0
    zscore_detection_cycle: Optional[int] = None

    pca_reconstruction_error: float = 0.0
    pca_detection_cycle: Optional[int] = None

    sii_lead_time: Optional[int] = None
    threshold_lead_time: Optional[int] = None
    zscore_lead_time: Optional[int] = None
    pca_lead_time: Optional[int] = None


@dataclass
class UnifiedSystemState:
    """Unified system state derived entirely from SIIEngine."""
    timestamp: float
    cycle: int

    # Primary SIIEngine outputs
    instability_score: float
    regime: str
    urgency: str
    structural_drift: float
    drift_velocity: float
    transition_pressure: float
    confidence: float

    # Auxiliary metrics
    gradient_norm: float = 0.0
    recovery_alignment: float = 0.0

    # Detection context for evidence panel
    detection_context: DetectionContext = field(default_factory=DetectionContext)

    # For comparison/validation
    comparison_metrics: ComparisonMetrics = field(default_factory=ComparisonMetrics)

    # History for trend analysis
    instability_history: list[float] = field(default_factory=list)
    regime_history: list[str] = field(default_factory=list)
    velocity_history: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to serializable dictionary for API response."""
        return {
            "timestamp": self.timestamp,
            "cycle": self.cycle,
            "instability_score": float(self.instability_score),
            "regime": self.regime,
            "urgency": self.urgency,
            "structural_drift": float(self.structural_drift),
            "drift_velocity": float(self.drift_velocity),
            "transition_pressure": float(self.transition_pressure),
            "confidence": float(self.confidence),
            "gradient_norm": float(self.gradient_norm),
            "recovery_alignment": float(self.recovery_alignment),
            "detection_context": {
                "first_detection_cycle": self.detection_context.first_detection_cycle,
                "threshold_alert_cycle": self.detection_context.threshold_alert_cycle,
                "lead_time_cycles": self.detection_context.lead_time_cycles,
                "detection_confidence": float(self.detection_context.detection_confidence),
            },
            "instability_history": [float(v) for v in self.instability_history[-50:]],
            "regime_history": self.regime_history[-50:],
            "velocity_history": [float(v) for v in self.velocity_history[-50:]],
        }


class PerAssetSIIEngine:
    """Manages a single SIIEngine instance for an asset with detection tracking."""

    def __init__(
        self,
        asset_id: str,
        baseline_window: int = 50,
        recent_window: int = 12,
        detection_threshold: float = 0.65,
    ):
        self.asset_id = asset_id
        self.engine = SIIEngine(
            baseline_window=baseline_window,
            recent_window=recent_window,
        )
        self.detection_threshold = detection_threshold
        self.cycle_count = 0
        self.detection_context = DetectionContext()

    def update(
        self,
        x_t: np.ndarray,
        timestamp: float,
    ) -> UnifiedSystemState:
        """Process one frame and return unified system state."""
        self.cycle_count += 1

        # Get SIIEngine output
        sii_output = self.engine.update(x_t, timestamp)

        # Track detection events
        self._update_detection_context(sii_output)

        # Build unified state
        # Copy detection_context to prevent retroactive mutation of historical snapshots
        detection_context_copy = replace(self.detection_context)

        state = UnifiedSystemState(
            timestamp=timestamp,
            cycle=self.cycle_count,
            instability_score=sii_output.instability_score,
            regime=sii_output.regime,
            urgency=sii_output.urgency,
            structural_drift=sii_output.structural_drift,
            drift_velocity=sii_output.drift_velocity,
            transition_pressure=sii_output.transition_pressure,
            confidence=sii_output.confidence,
            gradient_norm=sii_output.gradient_norm,
            recovery_alignment=sii_output.recovery_alignment,
            detection_context=detection_context_copy,
            instability_history=list(sii_output.instability_history),
            regime_history=list(sii_output.regime_history),
            velocity_history=list(sii_output.velocity_history),
        )

        return state

    def _update_detection_context(self, sii_output: SIIEngineOutput) -> None:
        """Track detection timing for evidence panel."""
        # Record first detection (crossing threshold)
        if (
            self.detection_context.first_detection_cycle is None
            and sii_output.instability_score >= self.detection_threshold
        ):
            self.detection_context.first_detection_cycle = self.cycle_count
            self.detection_context.detection_confidence = sii_output.confidence

        # Update novelty score (how different from baseline)
        if self.engine.baseline.is_valid():
            self.detection_context.novelty_vs_baseline = float(
                sii_output.structural_drift
            )

    def get_state(self) -> dict[str, Any]:
        """Get serializable state for persistence."""
        return {
            "asset_id": self.asset_id,
            "cycle_count": self.cycle_count,
            "engine_state": self.engine.get_state(),
            "detection_context": {
                "first_detection_cycle": self.detection_context.first_detection_cycle,
                "threshold_alert_cycle": self.detection_context.threshold_alert_cycle,
                "lead_time_cycles": self.detection_context.lead_time_cycles,
                "detection_confidence": float(self.detection_context.detection_confidence),
                "novelty_vs_baseline": float(self.detection_context.novelty_vs_baseline),
            },
        }

    def restore_state(self, state: dict[str, Any]) -> None:
        """Restore engine from state snapshot."""
        self.cycle_count = state.get("cycle_count", 0)
        if "engine_state" in state:
            self.engine.restore_state(state["engine_state"])

        ctx = state.get("detection_context", {})
        self.detection_context = DetectionContext(
            first_detection_cycle=ctx.get("first_detection_cycle"),
            threshold_alert_cycle=ctx.get("threshold_alert_cycle"),
            lead_time_cycles=ctx.get("lead_time_cycles"),
            detection_confidence=float(ctx.get("detection_confidence", 0.0)),
            novelty_vs_baseline=float(ctx.get("novelty_vs_baseline", 0.0)),
        )


class SIIEngineAdapter:
    """
    Central adapter managing SIIEngine instances and exposing unified state.

    Single source of truth for:
    - All regime classifications
    - All urgency determinations
    - All instability scoring

    Prevents duplicate computation in UI, API, or decision layers.
    """

    def __init__(
        self,
        baseline_window: int = 50,
        recent_window: int = 12,
        detection_threshold: float = 0.65,
    ):
        self.baseline_window = baseline_window
        # Ensure recent_window >= baseline_window for proper warmup
        self.recent_window = max(recent_window, baseline_window)
        self.detection_threshold = detection_threshold

        # Per-asset/run engines
        self.engines: Dict[tuple[str, str], PerAssetSIIEngine] = {}

    def get_engine(self, asset_id: str, run_id: str = "default") -> PerAssetSIIEngine:
        """Get or create engine for asset/run combination."""
        key = (asset_id, run_id)
        if key not in self.engines:
            self.engines[key] = PerAssetSIIEngine(
                asset_id=asset_id,
                baseline_window=self.baseline_window,
                recent_window=self.recent_window,
                detection_threshold=self.detection_threshold,
            )
        return self.engines[key]

    def ingest(
        self,
        sensor_vector: np.ndarray,
        timestamp: float,
        asset_id: str,
        run_id: str = "default",
    ) -> UnifiedSystemState:
        """
        Process sensor data and return unified system state.

        This is the ONLY place where regime, urgency, and instability_score
        should be computed. No other component should compute these independently.
        """
        engine = self.get_engine(asset_id, run_id)
        return engine.update(sensor_vector, timestamp)

    def to_api_compatible_dict(self, state: UnifiedSystemState) -> dict[str, Any]:
        """
        Convert unified state to format compatible with existing API/UI.

        Maps SIIEngine outputs to fields expected by output_contract and API routes:
        - instability_score → latest_instability
        - structural_drift → structural_drift_score
        - regime → regime (new canonical)
        - urgency → urgency (new canonical)
        """
        return {
            "timestamp": state.timestamp,
            "cycle": state.cycle,
            "latest_instability": state.instability_score,
            "instability_score": state.instability_score,
            "structural_drift_score": state.structural_drift,
            "regime": state.regime,
            "urgency": state.urgency,
            "drift_velocity": state.drift_velocity,
            "transition_pressure": state.transition_pressure,
            "confidence": state.confidence,
            "gradient_norm": state.gradient_norm,
            "recovery_alignment": state.recovery_alignment,
            "regime_confidence": state.confidence,
            "instability_history": state.instability_history,
            "regime_history": state.regime_history,
            "velocity_history": state.velocity_history,
            "lead_time_cycles": state.detection_context.lead_time_cycles,
            "first_detection_cycle": state.detection_context.first_detection_cycle,
        }


# Global singleton instance
_adapter_instance: Optional[SIIEngineAdapter] = None


def get_sii_adapter() -> SIIEngineAdapter:
    """Get or create the global SIIEngineAdapter instance."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = SIIEngineAdapter()
    return _adapter_instance


def set_sii_adapter(adapter: SIIEngineAdapter) -> None:
    """Override the global adapter (mainly for testing)."""
    global _adapter_instance
    _adapter_instance = adapter


__all__ = [
    "SIIEngineAdapter",
    "PerAssetSIIEngine",
    "UnifiedSystemState",
    "DetectionContext",
    "ComparisonMetrics",
    "get_sii_adapter",
    "set_sii_adapter",
]
