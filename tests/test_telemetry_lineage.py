from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.services.telemetry_lineage import (
    MAX_LINEAGE_SAMPLE_LIMIT,
    ObservationLineage,
    bounded_lineage_bundle,
    build_durable_result_lineage,
    build_lineage_summary,
    build_observation_lineage,
    observation_lineage_digest,
    project_analysis_window_observations,
    project_analysis_window_persistence,
)


def _record(index: int) -> ObservationLineage:
    timestamp = datetime(2026, 8, 25, tzinfo=UTC) + timedelta(minutes=index)
    return ObservationLineage(
        observation_id=f"observation-{index:03d}",
        connection_id="connection-a",
        ingestion_run_id="run-a",
        external_signal_id="external-signal-a",
        mapping_id="mapping-a",
        mapping_revision=3,
        canonical_signal_id="canonical-pressure",
        canonical_signal_name="pressure",
        system_id="system-a",
        asset_id="asset-a",
        external_tag_id="vendor.pressure",
        source_timestamp_raw=timestamp.isoformat(),
        source_timezone="America/Chicago",
        source_offset="-05:00",
        timestamp_normalization_version="timestamp-normalization.v1",
        observed_at_utc=timestamp,
        original_unit="psi",
        canonical_unit="kPa",
        conversion_id="pressure:psi-to-kpa",
        conversion_version="unit-normalization.v1",
        source_record_digest=f"{index + 1:064x}",
        mapping_authority_digest="a" * 64,
    )


def test_full_lineage_round_trips_and_digest_is_order_independent() -> None:
    records = tuple(_record(index) for index in range(3))
    rebuilt = build_observation_lineage(records)

    assert rebuilt == records
    assert observation_lineage_digest(records) == observation_lineage_digest(tuple(reversed(records)))
    assert rebuilt[0].as_dict()["external_tag_id"] == "vendor.pressure"
    assert rebuilt[0].as_dict()["source_timezone"] == "America/Chicago"
    assert rebuilt[0].as_dict()["conversion_version"] == "unit-normalization.v1"


def test_public_lineage_summary_is_bounded_but_complete_digest_is_retained() -> None:
    records = tuple(_record(index) for index in range(MAX_LINEAGE_SAMPLE_LIMIT + 10))
    summary = build_lineage_summary(records, sample_limit=10_000)

    assert summary["observation_count"] == len(records)
    assert len(summary["observation_sample"]) == MAX_LINEAGE_SAMPLE_LIMIT
    assert summary["sample_truncated"] is True
    assert summary["lineage_digest"] == observation_lineage_digest(records)
    assert bounded_lineage_bundle(summary) == {
        **summary,
        "window_id": None,
        "source_kind": None,
        "source_run_id": None,
    }


def test_repository_projections_cover_window_and_every_observation() -> None:
    records = tuple(_record(index) for index in range(3))
    start = records[0].observed_at_utc
    end = records[-1].observed_at_utc
    window = project_analysis_window_persistence(
        window_id="window-a",
        tenant_scope_id="tenant-a",
        workspace_id="ws-facility-a",
        resource_scope_id="phase4-scope:0123456789abcdef0123456789abcdef",
        facility_id="ws-facility-a",
        system_id="system-a",
        asset_id="asset-a",
        source_run_id="run-a",
        window_start=start,
        window_end=end,
        authority_digest="a" * 64,
        quality_summary={"status": "ready"},
    )
    joins = project_analysis_window_observations(
        window_id="window-a",
        tenant_scope_id="tenant-a",
        workspace_id="ws-facility-a",
        resource_scope_id="phase4-scope:0123456789abcdef0123456789abcdef",
        facility_id="ws-facility-a",
        lineage=records,
    )

    assert window["source_ingestion_run_id"] == "run-a"
    assert window["authority_digest"] == "a" * 64
    assert [item["observation_id"] for item in joins] == [
        "observation-000",
        "observation-001",
        "observation-002",
    ]


def test_durable_result_lineage_keeps_only_bounded_ids_and_digests() -> None:
    records = (
        _record(0),
        ObservationLineage(
            **{
                **_record(1).as_dict(),
                "ingestion_run_id": "run-b",
                "observed_at_utc": _record(1).observed_at_utc,
            }
        ),
    )
    metadata, lineage, digest = build_durable_result_lineage(
        window_id="window-a",
        source_run_id="run-a",
        lineage=records,
        sii_result={
            "status": "limited",
            "evidence_fusion": {
                "evidence_inventory": [{"evidence_id": "evidence-a"}]
            },
            "findings": [{"finding_id": "finding-a", "raw_payload": "forbidden"}],
            "config": {"token": "must-not-survive"},
        },
        analysis_result={
            "schema_version": "analysis-schema.v1",
            "analysis_metadata": {"contract_version": "analysis-result.v1"},
            "conditions": [{"id": "condition-generated-a"}],
            "insights": [{"id": "insight-generated-a"}],
        },
    )

    assert lineage["contributing_ingestion_run_ids"] == ["run-a", "run-b"]
    assert lineage["evidence_ids"] == ["evidence-a"]
    assert lineage["finding_ids"] == [
        "condition-generated-a",
        "finding-a",
        "insight-generated-a",
    ]
    assert len(digest) == 64
    assert metadata["reference_digest"] == lineage["reference_digest"]
    assert metadata["analysis_schema_version"] == "analysis-schema.v1"
    assert metadata["analysis_contract_version"] == "analysis-result.v1"
    assert "raw_payload" not in repr((metadata, lineage))
    assert "must-not-survive" not in repr((metadata, lineage))
