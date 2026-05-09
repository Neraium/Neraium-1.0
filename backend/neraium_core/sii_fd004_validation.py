"""
PHASE 3: FD004 Full Validation Runner

Computes detection metrics for all methods on FD004 dataset:
- SIIEngine
- Threshold-based
- Z-score anomaly
- PCA reconstruction

Produces CSV and summary statistics for white paper validation.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import numpy as np
from collections import deque

from neraium_core.sii_engine_unified import SIIEngine


@dataclass
class DetectionMetrics:
    """Summary statistics for a detection method."""
    method_name: str
    detection_cycles: list[int] = field(default_factory=list)
    lead_times: list[int] = field(default_factory=list)
    detected_count: int = 0
    total_count: int = 0

    @property
    def detection_rate(self) -> float:
        """Percentage of units detected before failure."""
        if self.total_count == 0:
            return 0.0
        return 100.0 * self.detected_count / self.total_count

    @property
    def mean_lead_time(self) -> float:
        """Mean lead time (cycles before failure)."""
        if not self.lead_times:
            return 0.0
        return float(np.mean(self.lead_times))

    @property
    def median_lead_time(self) -> float:
        """Median lead time."""
        if not self.lead_times:
            return 0.0
        return float(np.median(self.lead_times))

    @property
    def std_lead_time(self) -> float:
        """Standard deviation of lead times."""
        if len(self.lead_times) < 2:
            return 0.0
        return float(np.std(self.lead_times))

    @property
    def min_lead_time(self) -> float:
        """Minimum lead time."""
        if not self.lead_times:
            return 0.0
        return float(np.min(self.lead_times))

    @property
    def max_lead_time(self) -> float:
        """Maximum lead time."""
        if not self.lead_times:
            return 0.0
        return float(np.max(self.lead_times))

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "method": self.method_name,
            "detection_rate_percent": round(self.detection_rate, 2),
            "mean_lead_time": round(self.mean_lead_time, 2),
            "median_lead_time": round(self.median_lead_time, 2),
            "std_lead_time": round(self.std_lead_time, 2),
            "min_lead_time": round(self.min_lead_time, 2),
            "max_lead_time": round(self.max_lead_time, 2),
            "detected_count": self.detected_count,
            "total_count": self.total_count,
        }


@dataclass
class UnitValidationResult:
    """Results for a single unit."""
    unit_id: str
    failure_cycle: int

    sii_detection_cycle: Optional[int] = None
    threshold_detection_cycle: Optional[int] = None
    zscore_detection_cycle: Optional[int] = None
    pca_detection_cycle: Optional[int] = None

    @property
    def sii_lead_time(self) -> Optional[int]:
        return (
            self.failure_cycle - self.sii_detection_cycle
            if self.sii_detection_cycle
            else None
        )

    @property
    def threshold_lead_time(self) -> Optional[int]:
        return (
            self.failure_cycle - self.threshold_detection_cycle
            if self.threshold_detection_cycle
            else None
        )

    @property
    def zscore_lead_time(self) -> Optional[int]:
        return (
            self.failure_cycle - self.zscore_detection_cycle
            if self.zscore_detection_cycle
            else None
        )

    @property
    def pca_lead_time(self) -> Optional[int]:
        return (
            self.failure_cycle - self.pca_detection_cycle
            if self.pca_detection_cycle
            else None
        )

    def to_csv_row(self) -> dict[str, Any]:
        """Convert to CSV row."""
        return {
            "unit_id": self.unit_id,
            "failure_cycle": self.failure_cycle,
            "sii_detection_cycle": self.sii_detection_cycle or "",
            "threshold_detection_cycle": self.threshold_detection_cycle or "",
            "zscore_detection_cycle": self.zscore_detection_cycle or "",
            "pca_detection_cycle": self.pca_detection_cycle or "",
            "sii_lead_time": self.sii_lead_time or "",
            "threshold_lead_time": self.threshold_lead_time or "",
            "zscore_lead_time": self.zscore_lead_time or "",
            "pca_lead_time": self.pca_lead_time or "",
        }


class ThresholdDetector:
    """Simple threshold detector."""

    def __init__(self, threshold: float = 0.65):
        self.threshold = threshold
        self.detection_cycle: Optional[int] = None

    def update(self, score: float, cycle: int) -> bool:
        if self.detection_cycle is None and score >= self.threshold:
            self.detection_cycle = cycle
            return True
        return False


class ZScoreDetector:
    """Z-score based anomaly detection."""

    def __init__(self, baseline_window: int = 50, zscore_threshold: float = 2.5):
        self.baseline_window = baseline_window
        self.zscore_threshold = zscore_threshold
        self.sensor_history: deque[np.ndarray] = deque(maxlen=baseline_window)
        self.baseline_mean: Optional[np.ndarray] = None
        self.baseline_std: Optional[np.ndarray] = None
        self.frame_count = 0
        self.detection_cycle: Optional[int] = None

    def update(self, x_t: np.ndarray, cycle: int) -> bool:
        x_t = np.asarray(x_t, dtype=float)
        self.frame_count += 1

        if self.frame_count <= self.baseline_window:
            self.sensor_history.append(x_t)
            if self.frame_count == self.baseline_window:
                data = np.array(list(self.sensor_history), dtype=float)
                self.baseline_mean = np.mean(data, axis=0)
                self.baseline_std = np.std(data, axis=0) + 1e-9
            return False

        if self.baseline_mean is None or self.baseline_std is None:
            return False

        z_scores = np.abs((x_t - self.baseline_mean) / self.baseline_std)
        max_zscore = float(np.max(z_scores))

        if self.detection_cycle is None and max_zscore >= self.zscore_threshold:
            self.detection_cycle = cycle
            return True

        return False


class PCADetector:
    """PCA reconstruction error detector."""

    def __init__(
        self,
        baseline_window: int = 50,
        n_components: int = 3,
        error_threshold: float = 0.5,
    ):
        self.baseline_window = baseline_window
        self.n_components = n_components
        self.error_threshold = error_threshold
        self.sensor_history: deque[np.ndarray] = deque(maxlen=baseline_window)
        self.pca_components: Optional[np.ndarray] = None
        self.pca_mean: Optional[np.ndarray] = None
        self.frame_count = 0
        self.detection_cycle: Optional[int] = None

    def update(self, x_t: np.ndarray, cycle: int) -> bool:
        x_t = np.asarray(x_t, dtype=float)
        self.frame_count += 1

        if self.frame_count <= self.baseline_window:
            self.sensor_history.append(x_t)
            if self.frame_count == self.baseline_window:
                self._fit_pca()
            return False

        if self.pca_components is None or self.pca_mean is None:
            return False

        error = self._reconstruction_error(x_t)
        if self.detection_cycle is None and error >= self.error_threshold:
            self.detection_cycle = cycle
            return True

        return False

    def _fit_pca(self) -> None:
        data = np.array(list(self.sensor_history), dtype=float)
        self.pca_mean = np.mean(data, axis=0)
        centered = data - self.pca_mean

        try:
            U, S, Vt = np.linalg.svd(centered.T, full_matrices=False)
            n_comp = min(self.n_components, U.shape[1])
            self.pca_components = U[:, :n_comp]
        except (ValueError, np.linalg.LinAlgError):
            self.pca_components = np.eye(
                data.shape[1], min(self.n_components, data.shape[1])
            )

    def _reconstruction_error(self, x_t: np.ndarray) -> float:
        if self.pca_components is None or self.pca_mean is None:
            return 0.0

        centered = x_t - self.pca_mean
        projected = self.pca_components @ (self.pca_components.T @ centered)
        residual = centered - projected
        error = float(np.linalg.norm(residual))
        return error


class FD004ValidationRunner:
    """Runs validation on FD004 dataset."""

    def __init__(self, baseline_window: int = 50, recent_window: int = 12):
        self.baseline_window = baseline_window
        self.recent_window = recent_window

    def validate_unit(
        self,
        unit_id: str,
        sensor_data: np.ndarray,
        timestamps: np.ndarray,
        failure_cycle: int,
    ) -> UnitValidationResult:
        """
        Validate a single unit with all four methods.

        Args:
            unit_id: Unit identifier
            sensor_data: Shape (N, d) - N cycles, d sensors
            timestamps: Shape (N,) - timestamp for each cycle
            failure_cycle: The true failure cycle

        Returns:
            UnitValidationResult with detection timings
        """
        sii_engine = SIIEngine(
            baseline_window=self.baseline_window,
            recent_window=self.recent_window,
        )
        threshold_detector = ThresholdDetector(threshold=0.65)
        zscore_detector = ZScoreDetector(
            baseline_window=self.baseline_window,
            zscore_threshold=2.5,
        )
        pca_detector = PCADetector(
            baseline_window=self.baseline_window,
            n_components=min(3, sensor_data.shape[1]),
            error_threshold=0.5,
        )

        sii_detection: Optional[int] = None
        threshold_detection: Optional[int] = None
        zscore_detection: Optional[int] = None
        pca_detection: Optional[int] = None

        # Process each cycle
        for cycle in range(sensor_data.shape[0]):
            x_t = sensor_data[cycle, :]
            timestamp = float(timestamps[cycle])
            cycle_num = cycle + 1  # 1-indexed

            # Always update SII engine for fresh outputs
            sii_output = sii_engine.update(x_t, timestamp)

            # SII detection
            if sii_detection is None:
                if sii_output.instability_score >= 0.65:
                    sii_detection = cycle_num

            # Threshold detection (use structural drift - independent signal)
            if threshold_detection is None:
                threshold_detector.update(sii_output.structural_drift, cycle_num)
                if threshold_detector.detection_cycle is not None:
                    threshold_detection = threshold_detector.detection_cycle

            # Z-score detection
            if zscore_detection is None:
                zscore_detector.update(x_t, cycle_num)
                if zscore_detector.detection_cycle is not None:
                    zscore_detection = zscore_detector.detection_cycle

            # PCA detection
            if pca_detection is None:
                pca_detector.update(x_t, cycle_num)
                if pca_detector.detection_cycle is not None:
                    pca_detection = pca_detector.detection_cycle

        return UnitValidationResult(
            unit_id=unit_id,
            failure_cycle=failure_cycle,
            sii_detection_cycle=sii_detection,
            threshold_detection_cycle=threshold_detection,
            zscore_detection_cycle=zscore_detection,
            pca_detection_cycle=pca_detection,
        )

    def run_all_units(
        self, units: dict[str, tuple[np.ndarray, np.ndarray, int]]
    ) -> tuple[list[UnitValidationResult], dict[str, Any]]:
        """
        Run validation on all units.

        Args:
            units: Dict mapping unit_id to (sensor_data, timestamps, failure_cycle)

        Returns:
            (results, summary_statistics)
        """
        results = []

        for unit_id, (sensor_data, timestamps, failure_cycle) in units.items():
            result = self.validate_unit(unit_id, sensor_data, timestamps, failure_cycle)
            results.append(result)

        # Compute summary statistics
        summary = self._compute_summary(results)

        return results, summary

    @staticmethod
    def _compute_summary(results: list[UnitValidationResult]) -> dict[str, Any]:
        """Compute summary statistics from all results."""
        metrics = {
            "sii": DetectionMetrics("SIIEngine"),
            "threshold": DetectionMetrics("Threshold"),
            "zscore": DetectionMetrics("Z-Score"),
            "pca": DetectionMetrics("PCA"),
        }

        for result in results:
            for method_key, metric in metrics.items():
                metric.total_count += 1

                if method_key == "sii" and result.sii_detection_cycle:
                    metric.detected_count += 1
                    metric.detection_cycles.append(result.sii_detection_cycle)
                    if result.sii_lead_time:
                        metric.lead_times.append(result.sii_lead_time)

                elif method_key == "threshold" and result.threshold_detection_cycle:
                    metric.detected_count += 1
                    metric.detection_cycles.append(result.threshold_detection_cycle)
                    if result.threshold_lead_time:
                        metric.lead_times.append(result.threshold_lead_time)

                elif method_key == "zscore" and result.zscore_detection_cycle:
                    metric.detected_count += 1
                    metric.detection_cycles.append(result.zscore_detection_cycle)
                    if result.zscore_lead_time:
                        metric.lead_times.append(result.zscore_lead_time)

                elif method_key == "pca" and result.pca_detection_cycle:
                    metric.detected_count += 1
                    metric.detection_cycles.append(result.pca_detection_cycle)
                    if result.pca_lead_time:
                        metric.lead_times.append(result.pca_lead_time)

        return {
            "total_units": len(results),
            "sii": metrics["sii"].to_dict(),
            "threshold": metrics["threshold"].to_dict(),
            "zscore": metrics["zscore"].to_dict(),
            "pca": metrics["pca"].to_dict(),
            "best_method": max(
                ("sii", metrics["sii"]),
                ("threshold", metrics["threshold"]),
                ("zscore", metrics["zscore"]),
                ("pca", metrics["pca"]),
                key=lambda x: x[1].mean_lead_time,
            )[0],
        }

    def export_csv(self, results: list[UnitValidationResult], output_path: str | Path) -> None:
        """Export detailed results to CSV."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        fieldnames = [
            "unit_id",
            "failure_cycle",
            "sii_detection_cycle",
            "threshold_detection_cycle",
            "zscore_detection_cycle",
            "pca_detection_cycle",
            "sii_lead_time",
            "threshold_lead_time",
            "zscore_lead_time",
            "pca_lead_time",
        ]

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for result in results:
                writer.writerow(result.to_csv_row())

    def export_summary(self, summary: dict[str, Any], output_path: str | Path) -> None:
        """Export summary statistics to JSON."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2)

    @staticmethod
    def print_comparison_summary(summary: dict[str, Any]) -> str:
        """Print human-readable comparison summary."""
        lines = []
        lines.append("\n" + "=" * 70)
        lines.append("FD004 VALIDATION RESULTS - DETECTION METHOD COMPARISON")
        lines.append("=" * 70)
        lines.append(f"\nTotal Units Tested: {summary['total_units']}\n")

        methods = ["sii", "threshold", "zscore", "pca"]
        for method_key in methods:
            metrics = summary[method_key]
            lines.append(f"\n{metrics['method'].upper()}:")
            lines.append(f"  Detection Rate:       {metrics['detection_rate_percent']}%")
            lines.append(
                f"  Mean Lead Time:       {metrics['mean_lead_time']:.1f} cycles"
            )
            lines.append(
                f"  Median Lead Time:     {metrics['median_lead_time']:.1f} cycles"
            )
            lines.append(
                f"  Std Dev Lead Time:    {metrics['std_lead_time']:.1f} cycles"
            )
            lines.append(
                f"  Min/Max Lead Time:    {metrics['min_lead_time']:.0f} / "
                f"{metrics['max_lead_time']:.0f} cycles"
            )
            lines.append(f"  Units Detected:       {metrics['detected_count']} / {metrics['total_count']}")

        lines.append("\n" + "=" * 70)
        best = summary["best_method"]
        sii_mean = summary["sii"]["mean_lead_time"]
        threshold_mean = summary["threshold"]["mean_lead_time"]
        # Improvement: positive when SII has larger lead time (earlier detection)
        lead_time_difference = sii_mean - threshold_mean
        improvement_percent = ((lead_time_difference) / threshold_mean * 100) if threshold_mean > 0 else 0

        lines.append(f"\nBEST METHOD: {best.upper()}")
        lines.append(
            f"\nKEY CLAIM: SII achieves mean lead time of {sii_mean:.1f} cycles vs {threshold_mean:.1f} cycles "
            f"for threshold-based detection ({lead_time_difference:+.1f} cycle improvement, {improvement_percent:+.1f}%)."
        )
        lines.append("=" * 70 + "\n")

        return "\n".join(lines)


__all__ = [
    "FD004ValidationRunner",
    "UnitValidationResult",
    "DetectionMetrics",
]
