from __future__ import annotations

import re
from collections.abc import Collection
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


TIMESTAMP_NORMALIZATION_VERSION = "neraium.telemetry.timestamps/v1"
DEFAULT_FUTURE_TOLERANCE = timedelta(minutes=5)

_OFFSET_SUFFIX = re.compile(r"(Z|[+-]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)$", re.IGNORECASE)


@dataclass(frozen=True)
class TimestampNormalizationResult:
    """A source-preserving UTC normalization and ordering decision."""

    status: str
    quality_state: str
    ingestion_disposition: str
    analysis_eligible: bool
    reason_code: str | None
    source_timestamp_raw: str
    source_timezone: str | None
    source_offset: str | None
    observed_at_utc: datetime | None
    normalization_version: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _raw_value(source_timestamp: Any) -> str:
    if isinstance(source_timestamp, str):
        return source_timestamp
    if isinstance(source_timestamp, datetime):
        return source_timestamp.isoformat()
    return str(source_timestamp)


def _offset_from_raw(raw: str) -> str | None:
    match = _OFFSET_SUFFIX.search(raw.strip())
    return match.group(1) if match else None


def _format_offset(value: timedelta | None) -> str | None:
    if value is None:
        return None
    seconds = int(value.total_seconds())
    sign = "+" if seconds >= 0 else "-"
    seconds = abs(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    suffix = f":{seconds:02d}" if seconds else ""
    return f"{sign}{hours:02d}:{minutes:02d}{suffix}"


def _invalid(
    *,
    raw: str,
    source_timezone: str | None,
    source_offset: str | None,
    reason_code: str,
) -> TimestampNormalizationResult:
    return TimestampNormalizationResult(
        status="timestamp_invalid",
        quality_state="timestamp_invalid",
        ingestion_disposition="rejected",
        analysis_eligible=False,
        reason_code=reason_code,
        source_timestamp_raw=raw,
        source_timezone=source_timezone,
        source_offset=source_offset,
        observed_at_utc=None,
        normalization_version=TIMESTAMP_NORMALIZATION_VERSION,
    )


def _iana_zone(name: str | None) -> ZoneInfo | None:
    if not name or not str(name).strip():
        return None
    try:
        return ZoneInfo(str(name).strip())
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _localize_naive(value: datetime, zone: ZoneInfo) -> tuple[datetime | None, str | None]:
    """Resolve a wall time without allowing zoneinfo's implicit fold/gap choice."""

    candidates: list[datetime] = []
    for fold in (0, 1):
        aware = value.replace(tzinfo=zone, fold=fold)
        round_trip = aware.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
        if round_trip == value:
            candidates.append(aware)

    unique_offsets = {candidate.utcoffset() for candidate in candidates}
    if not candidates:
        return None, "timestamp_dst_nonexistent"
    if len(unique_offsets) > 1:
        return None, "timestamp_dst_ambiguous"
    return candidates[0], None


def _utc_reference(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def normalize_telemetry_timestamp(
    *,
    source_timestamp: str | datetime,
    source_timezone: str | None = None,
    now: datetime | None = None,
    future_tolerance: timedelta = DEFAULT_FUTURE_TOLERANCE,
    high_watermark_utc: datetime | None = None,
    seen_observed_at_utc: Collection[datetime] = (),
) -> TimestampNormalizationResult:
    """Normalize an explicit source timestamp and classify its ingestion order.

    A supplied numeric offset is authoritative for aware timestamps. Naive wall
    times require an IANA zone and are rejected when that zone makes the instant
    ambiguous or nonexistent. Duplicate classification precedes out-of-order
    classification, making replay behavior deterministic.
    """

    raw = _raw_value(source_timestamp)
    raw_offset = _offset_from_raw(raw)
    normalized_timezone = str(source_timezone).strip() if source_timezone else None
    if (
        normalized_timezone is None
        and isinstance(source_timestamp, datetime)
        and source_timestamp.tzinfo is not None
    ):
        normalized_timezone = getattr(source_timestamp.tzinfo, "key", None)
    zone = _iana_zone(normalized_timezone)
    if normalized_timezone and zone is None:
        return _invalid(
            raw=raw,
            source_timezone=normalized_timezone,
            source_offset=raw_offset,
            reason_code="source_timezone_invalid",
        )

    if isinstance(source_timestamp, datetime):
        parsed = source_timestamp
    elif isinstance(source_timestamp, str):
        try:
            parsed = datetime.fromisoformat(source_timestamp.strip().replace("Z", "+00:00").replace("z", "+00:00"))
        except (ValueError, TypeError, OverflowError):
            return _invalid(
                raw=raw,
                source_timezone=normalized_timezone,
                source_offset=raw_offset,
                reason_code="timestamp_parse_invalid",
            )
    else:
        return _invalid(
            raw=raw,
            source_timezone=normalized_timezone,
            source_offset=raw_offset,
            reason_code="timestamp_type_invalid",
        )

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if zone is None:
            return _invalid(
                raw=raw,
                source_timezone=normalized_timezone,
                source_offset=None,
                reason_code="source_timezone_required",
            )
        parsed, local_error = _localize_naive(parsed, zone)
        if local_error:
            return _invalid(
                raw=raw,
                source_timezone=normalized_timezone,
                source_offset=None,
                reason_code=local_error,
            )
        assert parsed is not None

    source_offset = raw_offset or _format_offset(parsed.utcoffset())
    observed_at_utc = parsed.astimezone(timezone.utc)
    reference_now = _utc_reference(now or datetime.now(timezone.utc), field="now")
    if future_tolerance < timedelta(0):
        raise ValueError("future_tolerance must not be negative")
    if observed_at_utc > reference_now + future_tolerance:
        return _invalid(
            raw=raw,
            source_timezone=normalized_timezone,
            source_offset=source_offset,
            reason_code="timestamp_future",
        )

    seen = {
        _utc_reference(item, field="seen_observed_at_utc item")
        for item in seen_observed_at_utc
    }
    if observed_at_utc in seen:
        disposition = "duplicate"
        eligible = False
        reason_code = "timestamp_duplicate"
    elif high_watermark_utc is not None and observed_at_utc < _utc_reference(
        high_watermark_utc, field="high_watermark_utc"
    ):
        disposition = "out_of_order_accepted"
        eligible = True
        reason_code = "timestamp_out_of_order"
    else:
        disposition = "accepted"
        eligible = True
        reason_code = None

    return TimestampNormalizationResult(
        status="normalized",
        quality_state="good",
        ingestion_disposition=disposition,
        analysis_eligible=eligible,
        reason_code=reason_code,
        source_timestamp_raw=raw,
        source_timezone=normalized_timezone,
        source_offset=source_offset,
        observed_at_utc=observed_at_utc,
        normalization_version=TIMESTAMP_NORMALIZATION_VERSION,
    )


__all__ = [
    "DEFAULT_FUTURE_TOLERANCE",
    "TIMESTAMP_NORMALIZATION_VERSION",
    "TimestampNormalizationResult",
    "normalize_telemetry_timestamp",
]
