from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.services.telemetry_constants import SENTINEL

SAMPLE_INTERVAL_SECONDS = 60
SHORT_DROP_THRESHOLD = 3
COMPLETENESS_FLOOR = 0.80


@dataclass
class IntegrityProfile:
    signal_id: str
    source_id: str
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    gap_type: str | None
    completeness: float
    samples_expected: int
    samples_received: int
    treatment: str | None
    suppress_confidence: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["window_start"] = self.window_start.isoformat()
        payload["window_end"] = self.window_end.isoformat()
        payload["completeness"] = round(float(self.completeness), 4)
        return payload


class IntegrityLayer:
    """Profiles signal completeness before normalization.

    This layer intentionally runs beside SII rather than hiding data quality problems
    before analysis. It produces the uncertainty context that SII and the UI can
    use when explaining telemetry integrity.
    """

    def __init__(self, maintenance_windows: list[tuple[pd.Timestamp, pd.Timestamp]] | None = None, sample_interval_seconds: int | None = None):
        self.maintenance_windows = maintenance_windows or []
        self.sample_interval_seconds = sample_interval_seconds or SAMPLE_INTERVAL_SECONDS

    def classify(self, signal: pd.Series, source_id: str, window_start: Any, window_end: Any) -> IntegrityProfile:
        window_start_ts = pd.Timestamp(window_start)
        window_end_ts = pd.Timestamp(window_end)
        expected = expected_samples(signal, window_start_ts, window_end_ts, self.sample_interval_seconds)
        received = int(signal.notna().sum())
        completeness = received / expected if expected > 0 else 0.0
        missing = max(0, expected - received)

        if missing == 0:
            gap_type, treatment = None, None
        elif signal.isna().all():
            gap_type, treatment = "terminal", "excluded"
        elif self._is_scheduled(window_start_ts, window_end_ts):
            gap_type, treatment = "scheduled", "excluded"
        elif missing <= SHORT_DROP_THRESHOLD:
            gap_type, treatment = "short_drop", "filled"
        else:
            gap_type, treatment = "sustained", "sentinel"

        return IntegrityProfile(
            signal_id=str(signal.name),
            source_id=source_id,
            window_start=window_start_ts,
            window_end=window_end_ts,
            gap_type=gap_type,
            completeness=completeness,
            samples_expected=expected,
            samples_received=received,
            treatment=treatment,
            suppress_confidence=completeness < COMPLETENESS_FLOOR,
        )

    def detect_correlated(self, df: pd.DataFrame) -> list[str]:
        if df.empty:
            return []
        null_mask = df.isnull()
        if len(null_mask.columns) < 2:
            return []

        correlated_columns: set[str] = set()
        active_counts = null_mask.sum(axis=1)
        source_gap_rows = active_counts >= 2
        if not bool(source_gap_rows.any()):
            return []

        for column in null_mask.columns:
            column_missing = null_mask[column]
            overlap = int((column_missing & source_gap_rows).sum())
            if overlap <= 0:
                continue
            missing_total = int(column_missing.sum())
            if bool(column_missing.all()) or overlap >= max(2, int(missing_total * 0.5)):
                correlated_columns.add(str(column))
        return sorted(correlated_columns)

    def _is_scheduled(self, start: pd.Timestamp, end: pd.Timestamp) -> bool:
        for mw_start, mw_end in self.maintenance_windows:
            if start >= pd.Timestamp(mw_start) and end <= pd.Timestamp(mw_end):
                return True
        return False


class NormalizationLayer:
    """Builds the normalized working copy while preserving integrity context."""

    def normalize(self, signal: pd.Series, profile: IntegrityProfile) -> tuple[pd.Series, str | None, str]:
        normalized = signal.copy()

        if profile.gap_type is None:
            return normalized, None, "good"

        if profile.gap_type == "short_drop":
            if self._is_slow_moving(signal):
                normalized = normalized.interpolate(method="linear", limit_direction="both")
                fill_method = "linear"
            else:
                normalized = normalized.ffill().bfill()
                fill_method = "forward_fill"
            return normalized, fill_method, "degraded"

        normalized = normalized.fillna(SENTINEL)
        return normalized, "sentinel", "missing"

    def _is_slow_moving(self, signal: pd.Series) -> bool:
        mean = signal.mean(skipna=True)
        std = signal.std(skipna=True)
        if pd.isna(mean) or pd.isna(std) or std == 0 or mean == 0:
            return True
        return (float(std) / abs(float(mean))) < 0.05


class NormalizationPipeline:
    def __init__(self, source_id: str, maintenance_windows: list[tuple[pd.Timestamp, pd.Timestamp]] | None = None, sample_interval_seconds: int | None = None):
        self.source_id = source_id
        self.integrity = IntegrityLayer(maintenance_windows, sample_interval_seconds)
        self.normalizer = NormalizationLayer()

    def run(self, raw: pd.DataFrame, window_start: Any, window_end: Any) -> dict[str, Any]:
        correlated = set(self.integrity.detect_correlated(raw))
        profiles: dict[str, IntegrityProfile] = {}
        normalized_cols: dict[str, pd.Series] = {}
        fill_methods: dict[str, str | None] = {}
        integrity_flags: dict[str, str] = {}

        for column in raw.columns:
            signal = raw[column].copy()
            signal.name = str(column)
            profile = self.integrity.classify(signal, self.source_id, window_start, window_end)

            if column in correlated and profile.gap_type in {"sustained", "terminal", "short_drop"}:
                profile.gap_type = "correlated"
                profile.treatment = "sentinel"
                profile.suppress_confidence = True

            normalized, fill_method, integrity_flag = self.normalizer.normalize(signal, profile)
            profiles[str(column)] = profile
            normalized_cols[str(column)] = normalized
            fill_methods[str(column)] = fill_method
            integrity_flags[str(column)] = integrity_flag

        normalized_df = pd.DataFrame(normalized_cols, index=raw.index)
        return {
            "normalized": normalized_df,
            "fill_methods": fill_methods,
            "integrity_flags": integrity_flags,
            "integrity_profiles": profiles,
            "window_suppressed": any(profile.suppress_confidence for profile in profiles.values()),
            "correlated_signals": sorted(correlated),
        }


def build_normalization_report(
    *,
    rows: list[dict[str, Any]],
    numeric_columns: list[str],
    timestamp_column: str | None,
    source_id: str,
    maintenance_windows: list[tuple[pd.Timestamp, pd.Timestamp]] | None = None,
) -> dict[str, Any]:
    raw, window_start, window_end = dataframe_from_rows(rows, numeric_columns, timestamp_column)
    if raw.empty or not list(raw.columns):
        return {
            "enabled": True,
            "status": "missing",
            "warnings": ["No numeric telemetry was available for normalization."],
            "signal_integrity": [],
            "source_integrity": {
                "source_id": source_id,
                "status": "missing",
                "affected_signals": [],
                "notes": "No numeric telemetry was available for normalization.",
            },
            "fill_methods": {},
            "integrity_flags": {},
            "window_suppressed": True,
            "normalized_columns": [],
            "missing_values": [],
        }

    sample_interval = infer_sample_interval_seconds(raw.index)
    result = NormalizationPipeline(
        source_id=source_id,
        maintenance_windows=maintenance_windows,
        sample_interval_seconds=sample_interval,
    ).run(raw, window_start, window_end)
    profiles: dict[str, IntegrityProfile] = result["integrity_profiles"]
    signal_integrity = [profile.to_dict() for profile in profiles.values()]
    affected_signals = [signal_id for signal_id, profile in profiles.items() if profile.gap_type in {"sustained", "terminal", "correlated"}]
    warnings = build_integrity_warnings(profiles)
    source_status = "outage" if result["correlated_signals"] else ("degraded" if affected_signals or warnings else "good")
    source_notes = "Correlated missing telemetry detected." if result["correlated_signals"] else ("Telemetry usable with integrity conditions." if source_status == "degraded" else "Telemetry integrity appears acceptable.")

    return {
        "enabled": True,
        "status": source_status,
        "warnings": warnings,
        "signal_integrity": signal_integrity,
        "source_integrity": {
            "source_id": source_id,
            "window_start": pd.Timestamp(window_start).isoformat(),
            "window_end": pd.Timestamp(window_end).isoformat(),
            "status": source_status,
            "affected_signals": affected_signals or result["correlated_signals"],
            "notes": source_notes,
        },
        "fill_methods": result["fill_methods"],
        "integrity_flags": result["integrity_flags"],
        "window_suppressed": bool(result["window_suppressed"]),
        "normalized_columns": list(result["normalized"].columns),
        "missing_values": [f"{profile.signal_id}: {max(0.0, 1 - profile.completeness):.1%} missing, treatment {profile.treatment or 'none'}" for profile in profiles.values() if profile.gap_type],
    }


def dataframe_from_rows(rows: list[dict[str, Any]], numeric_columns: list[str], timestamp_column: str | None) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
    if not rows or not numeric_columns:
        now = pd.Timestamp.utcnow()
        return pd.DataFrame(), now, now

    frame = pd.DataFrame(rows)
    available_columns = [column for column in numeric_columns if column in frame.columns]
    raw = pd.DataFrame({column: pd.to_numeric(frame[column], errors="coerce") for column in available_columns})

    if timestamp_column and timestamp_column in frame.columns:
        timestamps = pd.to_datetime(frame[timestamp_column], errors="coerce", utc=True)
        if timestamps.notna().any():
            raw.index = timestamps
            window_start = timestamps.min()
            window_end = timestamps.max()
            if window_start == window_end:
                window_end = window_start + timedelta(seconds=SAMPLE_INTERVAL_SECONDS)
            return raw, pd.Timestamp(window_start), pd.Timestamp(window_end)

    start = pd.Timestamp.utcnow()
    raw.index = pd.date_range(start=start, periods=len(raw), freq=f"{SAMPLE_INTERVAL_SECONDS}s")
    end = raw.index[-1] + timedelta(seconds=SAMPLE_INTERVAL_SECONDS) if len(raw.index) else start
    return raw, pd.Timestamp(start), pd.Timestamp(end)


def expected_samples(signal: pd.Series, window_start: pd.Timestamp, window_end: pd.Timestamp, sample_interval_seconds: int) -> int:
    if len(signal.index) > 0 and isinstance(signal.index, pd.DatetimeIndex):
        return max(1, len(signal.index))
    seconds = max(0, int((window_end - window_start).total_seconds()))
    return max(1, int(seconds / max(1, sample_interval_seconds)), len(signal))


def infer_sample_interval_seconds(index: pd.Index) -> int | None:
    if not isinstance(index, pd.DatetimeIndex) or len(index) < 2:
        return None
    ordered = index.dropna().sort_values()
    diffs = ordered.to_series().diff().dropna().dt.total_seconds()
    diffs = diffs[diffs > 0]
    if diffs.empty:
        return None
    return max(1, int(diffs.median()))


def build_integrity_warnings(profiles: dict[str, IntegrityProfile]) -> list[str]:
    warnings: list[str] = []
    for profile in profiles.values():
        if profile.gap_type == "short_drop":
            warnings.append(f"{profile.signal_id} had short telemetry gaps that were filled for analysis.")
        elif profile.gap_type == "correlated":
            warnings.append(f"{profile.signal_id} appears affected by a correlated source gap.")
        elif profile.gap_type in {"sustained", "terminal", "scheduled"}:
            warnings.append(f"{profile.signal_id} had {profile.gap_type} telemetry gaps and was marked missing for analysis.")
        if profile.suppress_confidence:
            warnings.append(f"{profile.signal_id} completeness fell below the confidence floor.")
    return list(dict.fromkeys(warnings))
