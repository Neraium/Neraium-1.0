from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.telemetry_timestamps import (
    TIMESTAMP_NORMALIZATION_VERSION,
    normalize_telemetry_timestamp,
)


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def test_aware_timestamp_preserves_raw_offset_and_normalizes_to_utc() -> None:
    raw = " 2026-08-25T07:15:30.125-04:00 "
    result = normalize_telemetry_timestamp(source_timestamp=raw, now=NOW)

    assert result.status == "normalized"
    assert result.source_timestamp_raw == raw
    assert result.source_offset == "-04:00"
    assert result.source_timezone is None
    assert result.observed_at_utc == datetime(2026, 8, 25, 11, 15, 30, 125000, tzinfo=timezone.utc)
    assert result.normalization_version == TIMESTAMP_NORMALIZATION_VERSION
    assert result.analysis_eligible is True


def test_z_offset_is_preserved_instead_of_stripped() -> None:
    result = normalize_telemetry_timestamp(
        source_timestamp="2026-08-25T11:00:00Z",
        source_timezone="America/New_York",
        now=NOW,
    )

    assert result.source_timestamp_raw.endswith("Z")
    assert result.source_offset == "Z"
    assert result.source_timezone == "America/New_York"
    assert result.observed_at_utc == datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)


def test_naive_timestamp_requires_explicit_iana_timezone() -> None:
    result = normalize_telemetry_timestamp(
        source_timestamp="2026-08-25T07:00:00",
        now=NOW,
    )

    assert result.quality_state == "timestamp_invalid"
    assert result.ingestion_disposition == "rejected"
    assert result.analysis_eligible is False
    assert result.reason_code == "source_timezone_required"


def test_naive_timestamp_uses_iana_timezone_and_preserves_context() -> None:
    result = normalize_telemetry_timestamp(
        source_timestamp="2026-08-25 07:00:00",
        source_timezone="America/New_York",
        now=NOW,
    )

    assert result.observed_at_utc == datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    assert result.source_timestamp_raw == "2026-08-25 07:00:00"
    assert result.source_timezone == "America/New_York"
    assert result.source_offset == "-04:00"


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ("2024-03-10T02:30:00", "timestamp_dst_nonexistent"),
        ("2024-11-03T01:30:00", "timestamp_dst_ambiguous"),
    ],
)
def test_naive_dst_gap_and_fold_are_rejected(raw: str, reason: str) -> None:
    result = normalize_telemetry_timestamp(
        source_timestamp=raw,
        source_timezone="America/New_York",
        now=NOW,
    )

    assert result.status == "timestamp_invalid"
    assert result.reason_code == reason
    assert result.observed_at_utc is None
    assert result.source_timestamp_raw == raw


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-11-03T01:30:00-04:00", datetime(2024, 11, 3, 5, 30, tzinfo=timezone.utc)),
        ("2024-11-03T01:30:00-05:00", datetime(2024, 11, 3, 6, 30, tzinfo=timezone.utc)),
    ],
)
def test_explicit_offsets_disambiguate_both_dst_fold_instants(
    raw: str, expected: datetime
) -> None:
    result = normalize_telemetry_timestamp(
        source_timestamp=raw,
        source_timezone="America/New_York",
        now=NOW,
    )

    assert result.status == "normalized"
    assert result.observed_at_utc == expected
    assert result.source_offset == raw[-6:]


def test_zoneinfo_aware_datetime_preserves_named_timezone_and_fold() -> None:
    local = datetime(2024, 11, 3, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=1)
    result = normalize_telemetry_timestamp(source_timestamp=local, now=NOW)

    assert result.source_timezone == "America/New_York"
    assert result.source_offset == "-05:00"
    assert result.observed_at_utc == datetime(2024, 11, 3, 6, 30, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("raw", "timezone_name", "reason"),
    [
        ("not-a-timestamp", None, "timestamp_parse_invalid"),
        ("2026-08-25T07:00:00", "Not/AZone", "source_timezone_invalid"),
    ],
)
def test_invalid_timestamp_or_non_iana_zone_fails_closed(
    raw: str, timezone_name: str | None, reason: str
) -> None:
    result = normalize_telemetry_timestamp(
        source_timestamp=raw,
        source_timezone=timezone_name,
        now=NOW,
    )

    assert result.reason_code == reason
    assert result.quality_state == "timestamp_invalid"
    assert result.analysis_eligible is False


def test_obvious_future_timestamp_is_rejected_but_clock_skew_tolerance_is_allowed() -> None:
    allowed = normalize_telemetry_timestamp(
        source_timestamp="2026-08-25T12:04:59Z",
        now=NOW,
        future_tolerance=timedelta(minutes=5),
    )
    rejected = normalize_telemetry_timestamp(
        source_timestamp="2026-08-25T12:05:01Z",
        now=NOW,
        future_tolerance=timedelta(minutes=5),
    )

    assert allowed.analysis_eligible is True
    assert rejected.reason_code == "timestamp_future"
    assert rejected.source_timestamp_raw == "2026-08-25T12:05:01Z"
    assert rejected.observed_at_utc is None


def test_duplicate_takes_precedence_over_out_of_order_and_is_ineligible() -> None:
    observed = datetime(2026, 8, 25, 10, 0, tzinfo=timezone.utc)
    result = normalize_telemetry_timestamp(
        source_timestamp="2026-08-25T10:00:00Z",
        now=NOW,
        high_watermark_utc=datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc),
        seen_observed_at_utc=[observed],
    )

    assert result.ingestion_disposition == "duplicate"
    assert result.reason_code == "timestamp_duplicate"
    assert result.quality_state == "good"
    assert result.analysis_eligible is False


def test_out_of_order_history_is_accepted_with_distinct_disposition() -> None:
    result = normalize_telemetry_timestamp(
        source_timestamp="2026-08-25T10:00:00+00:00",
        now=NOW,
        high_watermark_utc=datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc),
    )

    assert result.ingestion_disposition == "out_of_order_accepted"
    assert result.reason_code == "timestamp_out_of_order"
    assert result.quality_state == "good"
    assert result.analysis_eligible is True


def test_equivalent_offsets_compare_as_the_same_duplicate_instant() -> None:
    result = normalize_telemetry_timestamp(
        source_timestamp="2026-08-25T07:00:00-04:00",
        now=NOW,
        seen_observed_at_utc=[datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)],
    )

    assert result.ingestion_disposition == "duplicate"


def test_negative_future_tolerance_and_naive_order_references_are_rejected() -> None:
    with pytest.raises(ValueError, match="future_tolerance"):
        normalize_telemetry_timestamp(
            source_timestamp="2026-08-25T11:00:00Z",
            now=NOW,
            future_tolerance=timedelta(seconds=-1),
        )

    with pytest.raises(ValueError, match="high_watermark_utc"):
        normalize_telemetry_timestamp(
            source_timestamp="2026-08-25T11:00:00Z",
            now=NOW,
            high_watermark_utc=datetime(2026, 8, 25, 10, 0),
        )
