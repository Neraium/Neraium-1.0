from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.connectors.base import (
    ConnectorCheckpoint,
    ConnectorPage,
    ConnectorRecordIssue,
    RawObservationEnvelope,
)
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_domain import (
    IngestionDisposition,
    TelemetryQualityState,
    TelemetryScopeRef,
)
from app.services.telemetry_ingestion import (
    MappingSnapshot,
    prepare_connector_page,
    stable_source_record_digest,
)
from app.services.telemetry_timestamps import TIMESTAMP_NORMALIZATION_VERSION
from app.services.telemetry_units import UNIT_NORMALIZATION_VERSION


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
CONNECTION_ID = "00000000-0000-0000-0000-000000000001"
RUN_ID = "00000000-0000-0000-0000-000000000002"


@pytest.fixture
def scope() -> TelemetryScopeRef:
    tenant = "tenant-normalizer"
    workspace = "facility-normalizer"
    return TelemetryScopeRef(
        tenant_scope_id=tenant,
        workspace_id=workspace,
        resource_scope_id=canonical_phase4_resource_scope_id(tenant, workspace),
        facility_id=workspace,
    )


@pytest.fixture
def mapping(scope: TelemetryScopeRef) -> MappingSnapshot:
    return MappingSnapshot(
        scope=scope,
        connection_id=CONNECTION_ID,
        external_tag_id="AHU-1.SAT",
        external_signal_id="00000000-0000-0000-0000-000000000101",
        mapping_id="00000000-0000-0000-0000-000000000201",
        revision=3,
        actor_id="operator@example.test",
        mapped_at=datetime(2026, 8, 20, 9, 30, tzinfo=UTC),
        authority_digest="a" * 64,
        facility_id=scope.facility_id,
        system_id="ahu-1",
        asset_id="sat-sensor-1",
        canonical_signal_id="00000000-0000-0000-0000-000000000301",
        canonical_signal_name="supply_air_temperature",
        source_unit="degF",
        canonical_unit="degC",
        expected_dimension="temperature",
        conversion_id="f_to_c",
        conversion_version=UNIT_NORMALIZATION_VERSION,
        source_timezone="America/New_York",
        provenance="manual",
    )


def raw(
    *,
    timestamp: object = "2026-08-25T07:00:00-04:00",
    value: object = 77.0,
    unit: str | None = "degF",
    quality: str | None = "good",
    event_id: str | None = "provider-event-1",
    metadata: dict[str, object] | None = None,
    tag: str = "AHU-1.SAT",
) -> RawObservationEnvelope:
    return RawObservationEnvelope(
        external_tag_id=tag,
        external_tag_name="AHU 1 Supply Air Temperature",
        source_timestamp=timestamp,
        raw_value=value,
        reported_unit=unit,
        reported_quality=quality,
        provider_event_id=event_id,
        metadata=metadata or {"source_sequence": 42, "site": {"zone": "east"}},
    )


def prepare(
    *,
    scope: TelemetryScopeRef,
    mapping: MappingSnapshot,
    observations: tuple[object, ...],
    **kwargs: object,
):
    return prepare_connector_page(
        page=ConnectorPage(observations=observations),  # type: ignore[arg-type]
        scope=scope,
        connection_id=CONNECTION_ID,
        ingestion_run_id=RUN_ID,
        mappings_by_external_tag={mapping.external_tag_id: mapping},
        now=NOW,
        ingested_at_utc=NOW,
        **kwargs,
    )


def test_happy_path_is_source_neutral_immutable_and_preserves_lineage(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    checkpoint = ConnectorCheckpoint(cursor="next:2", high_water_at=NOW)
    page = ConnectorPage(
        observations=(raw(),),
        next_checkpoint=checkpoint,
        has_more=True,
        pages_read=1,
        response_bytes=512,
        retry_count=1,
    )

    result = prepare_connector_page(
        page=page,
        scope=scope,
        connection_id=CONNECTION_ID,
        ingestion_run_id=RUN_ID,
        mappings_by_external_tag={mapping.external_tag_id: mapping},
        now=NOW,
        ingested_at_utc=NOW,
    )

    assert result.accepted_count == 1
    assert result.rejected_count == result.duplicate_count == 0
    assert result.next_checkpoint is checkpoint
    assert result.has_more is True
    observation = result.observations[0]
    assert observation.scope is scope
    assert observation.system_id == "ahu-1"
    assert observation.asset_id == "sat-sensor-1"
    assert observation.canonical_signal_name == "supply_air_temperature"
    assert observation.provider_event_id == "provider-event-1"
    assert observation.source_timestamp_raw == "2026-08-25T07:00:00-04:00"
    assert observation.source_offset == "-04:00"
    assert observation.source_timezone == "America/New_York"
    assert observation.observed_at_utc == datetime(2026, 8, 25, 11, tzinfo=UTC)
    assert observation.timestamp_normalization_version == TIMESTAMP_NORMALIZATION_VERSION
    assert observation.original_value == 77.0
    assert observation.original_unit == "degF"
    assert observation.normalized_value == pytest.approx(25.0)
    assert observation.conversion_id == "f_to_c"
    assert observation.analysis_eligible is True
    assert observation.source_metadata["site"]["zone"] == "east"
    with pytest.raises(FrozenInstanceError):
        observation.normalized_value = 5.0  # type: ignore[misc]
    with pytest.raises(TypeError):
        observation.source_metadata["new"] = "unsafe"  # type: ignore[index]


def test_mapping_provenance_snapshot_is_copied_in_full(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    observation = prepare(scope=scope, mapping=mapping, observations=(raw(),)).observations[0]

    assert observation.external_signal_id == mapping.external_signal_id
    assert observation.mapping_id == mapping.mapping_id
    assert observation.mapping_revision == 3
    assert observation.mapping_actor_id == "operator@example.test"
    assert observation.mapping_mapped_at == mapping.mapped_at
    assert observation.mapping_authority_digest == "a" * 64
    assert observation.mapping_provenance == "manual"


def test_digest_is_stable_typed_and_independent_of_metadata_enrichment() -> None:
    first = raw(metadata={"sequence": 1})
    replay = raw(metadata={"sequence": 2, "new_safe_field": True})
    renamed = replace(replay, external_tag_name="Renamed display label")
    string_value = raw(value="77.0", event_id=None)
    numeric_value = raw(value=77.0, event_id=None)

    assert stable_source_record_digest(first) == stable_source_record_digest(replay)
    assert stable_source_record_digest(first) == stable_source_record_digest(renamed)
    assert stable_source_record_digest(numeric_value) != stable_source_record_digest(string_value)
    assert len(stable_source_record_digest(first)) == 64


def test_duplicate_from_existing_digest_and_same_page_is_rejected_once_each(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    replayed = raw()
    result = prepare(
        scope=scope,
        mapping=mapping,
        observations=(replayed, replayed),
        existing_source_record_digests={stable_source_record_digest(replayed)},
    )

    assert result.observations == ()
    assert result.duplicate_count == 2
    assert result.rejected_count == 0
    assert all(
        item.ingestion_disposition is IngestionDisposition.DUPLICATE
        for item in result.rejections
    )
    assert all(item.analysis_eligible is False for item in result.rejections)


def test_out_of_order_is_accepted_eligible_and_does_not_move_high_water_backward(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    high_water = datetime(2026, 8, 25, 11, 30, tzinfo=UTC)
    result = prepare(
        scope=scope,
        mapping=mapping,
        observations=(raw(timestamp="2026-08-25T07:00:00-04:00"),),
        high_watermark_utc=high_water,
    )

    assert result.out_of_order_count == 1
    assert result.high_watermark_utc == high_water
    assert (
        result.observations[0].ingestion_disposition
        is IngestionDisposition.OUT_OF_ORDER_ACCEPTED
    )
    assert result.observations[0].reason_codes == ("timestamp_out_of_order",)
    assert result.observations[0].analysis_eligible is True


@pytest.mark.parametrize(
    ("timestamp", "reason"),
    [
        ("2024-03-10T02:30:00", "timestamp_dst_nonexistent"),
        ("2024-11-03T01:30:00", "timestamp_dst_ambiguous"),
        ("2026-08-25T12:06:00Z", "timestamp_future"),
        ("not-a-time", "timestamp_parse_invalid"),
    ],
)
def test_dst_future_and_invalid_timestamps_are_deterministic_rejections(
    scope: TelemetryScopeRef,
    mapping: MappingSnapshot,
    timestamp: str,
    reason: str,
) -> None:
    result = prepare(scope=scope, mapping=mapping, observations=(raw(timestamp=timestamp),))

    rejection = result.rejections[0]
    assert rejection.quality_state is TelemetryQualityState.TIMESTAMP_INVALID
    assert rejection.reason_code == reason
    assert rejection.source_timestamp_raw == timestamp
    assert rejection.analysis_eligible is False


@pytest.mark.parametrize(
    ("value", "unit", "reason", "quality"),
    [
        (float("nan"), "degF", "value_nonfinite", TelemetryQualityState.INVALID_VALUE),
        (True, "degF", "value_nonfinite", TelemetryQualityState.INVALID_VALUE),
        ([72.0], "degF", "value_type_invalid", TelemetryQualityState.INVALID_VALUE),
        (72.0, "mystery", "source_unit_unknown", TelemetryQualityState.UNIT_UNRESOLVED),
        (72.0, "degC", "reported_unit_mapping_mismatch", TelemetryQualityState.UNIT_UNRESOLVED),
    ],
)
def test_invalid_value_or_unit_never_becomes_an_observation(
    scope: TelemetryScopeRef,
    mapping: MappingSnapshot,
    value: object,
    unit: str,
    reason: str,
    quality: TelemetryQualityState,
) -> None:
    result = prepare(scope=scope, mapping=mapping, observations=(raw(value=value, unit=unit),))

    assert result.observations == ()
    assert result.rejections[0].quality_state is quality
    assert result.rejections[0].reason_code == reason
    assert result.rejections[0].original_unit == unit


@pytest.mark.parametrize(
    ("reported", "state", "reason"),
    [
        ("stale", TelemetryQualityState.STALE, "reported_quality_stale"),
        ("no data", TelemetryQualityState.MISSING, "reported_quality_missing"),
        ("BAD", TelemetryQualityState.INVALID_VALUE, "reported_quality_ineligible"),
        ("vendor-code-123", TelemetryQualityState.FORMAT_INVALID, "reported_quality_unrecognized"),
    ],
)
def test_non_good_reported_quality_fails_closed(
    scope: TelemetryScopeRef,
    mapping: MappingSnapshot,
    reported: str,
    state: TelemetryQualityState,
    reason: str,
) -> None:
    result = prepare(scope=scope, mapping=mapping, observations=(raw(quality=reported),))

    assert result.observations == ()
    assert result.rejections[0].quality_state is state
    assert result.rejections[0].reason_code == reason


def test_unusual_but_finite_value_remains_good_and_eligible(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    result = prepare(scope=scope, mapping=mapping, observations=(raw(value=-1_000_000_000.25),))

    assert result.accepted_count == 1
    assert result.observations[0].quality_state is TelemetryQualityState.GOOD
    assert result.observations[0].analysis_eligible is True


def test_unmapped_and_disabled_signals_are_rejected_without_inference(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    unmapped = prepare_connector_page(
        page=ConnectorPage(observations=(raw(tag="unknown-tag"),)),
        scope=scope,
        connection_id=CONNECTION_ID,
        ingestion_run_id=RUN_ID,
        mappings_by_external_tag={mapping.external_tag_id: mapping},
        now=NOW,
    )
    disabled_mapping = replace(mapping, enabled=False)
    disabled = prepare(scope=scope, mapping=disabled_mapping, observations=(raw(),))

    assert unmapped.rejections[0].reason_code == "mapping_not_approved"
    assert unmapped.rejections[0].external_signal_id is None
    assert disabled.rejections[0].reason_code == "signal_disabled"
    assert disabled.rejections[0].external_signal_id == mapping.external_signal_id


def test_partial_record_failures_do_not_discard_valid_siblings(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    result = prepare(
        scope=scope,
        mapping=mapping,
        observations=(
            raw(event_id="good-1"),
            raw(event_id="bad-1", value="not-numeric"),
            raw(event_id="good-2", timestamp="2026-08-25T07:01:00-04:00"),
        ),
    )

    assert [item.provider_event_id for item in result.observations] == ["good-1", "good-2"]
    assert result.accepted_count == 2
    assert result.rejected_count == 1
    assert result.rejections[0].reason_code == "value_nonfinite"


def test_raw_values_and_metadata_are_not_in_default_log_representation(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    accepted = prepare(
        scope=scope,
        mapping=mapping,
        observations=(raw(value=77.123456, metadata={"site_note": "private-note"}),),
    ).observations[0]
    rejected = prepare(
        scope=scope,
        mapping=mapping,
        observations=(raw(value="sensitive-source-payload"),),
    ).rejections[0]

    assert "77.123456" not in repr(accepted)
    assert "private-note" not in repr(accepted)
    assert "sensitive-source-payload" not in repr(rejected)


def test_connector_record_issues_are_bounded_quarantined_rejections(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    result = prepare_connector_page(
        page=ConnectorPage(
            observations=(raw(),),
            issues=(ConnectorRecordIssue(record_index=4, code="record_shape_invalid"),),
        ),
        scope=scope,
        connection_id=CONNECTION_ID,
        ingestion_run_id=RUN_ID,
        mappings_by_external_tag={mapping.external_tag_id: mapping},
        now=NOW,
    )

    assert result.accepted_count == 1
    assert result.rejected_count == 1
    issue = result.rejections[0]
    assert issue.ingestion_disposition is IngestionDisposition.QUARANTINED
    assert issue.safe_context == {
        "connector_record_index": 4,
        "connector_issue_code": "record_shape_invalid",
    }


@pytest.mark.parametrize(
    "unsafe_key", ["password", "Authorization", "rawPayload", "request_headers"]
)
def test_sensitive_or_log_payload_metadata_is_rejected_without_echo(
    scope: TelemetryScopeRef, mapping: MappingSnapshot, unsafe_key: str
) -> None:
    # Connector envelopes normally reject credential-shaped metadata at their
    # own boundary. A provider-contract violation must still fail per-record,
    # without copying the value into rejection context or repr output.
    malformed = SimpleNamespace(
        external_tag_id="AHU-1.SAT",
        external_tag_name="AHU 1 Supply Air Temperature",
        source_timestamp="2026-08-25T07:00:00-04:00",
        raw_value=77.0,
        reported_unit="degF",
        reported_quality="good",
        provider_event_id="unsafe-event",
        metadata={unsafe_key: "must-never-escape"},
    )

    result = prepare(scope=scope, mapping=mapping, observations=(malformed,))

    assert result.observations == ()
    assert result.rejections[0].reason_code == "source_metadata_unsafe"
    assert result.rejections[0].safe_context == {}
    assert "must-never-escape" not in repr(result)


def test_mapping_snapshot_fails_closed_on_scope_or_key_mismatch(
    scope: TelemetryScopeRef, mapping: MappingSnapshot
) -> None:
    with pytest.raises(ValueError, match="external_tag_mismatch"):
        prepare_connector_page(
            page=ConnectorPage(),
            scope=scope,
            connection_id=CONNECTION_ID,
            ingestion_run_id=RUN_ID,
            mappings_by_external_tag={"wrong": mapping},
            now=NOW,
        )
    other_scope = TelemetryScopeRef(
        tenant_scope_id="other-tenant",
        workspace_id="other-facility",
        resource_scope_id=canonical_phase4_resource_scope_id(
            "other-tenant", "other-facility"
        ),
        facility_id="other-facility",
    )
    with pytest.raises(ValueError, match="scope_mismatch"):
        prepare_connector_page(
            page=ConnectorPage(),
            scope=scope,
            connection_id=CONNECTION_ID,
            ingestion_run_id=RUN_ID,
            mappings_by_external_tag={
                mapping.external_tag_id: replace(
                    mapping, scope=other_scope, facility_id=other_scope.facility_id
                )
            },
            now=NOW,
        )
    with pytest.raises(ValueError, match="connection_mismatch"):
        prepare_connector_page(
            page=ConnectorPage(),
            scope=scope,
            connection_id="00000000-0000-0000-0000-000000000999",
            ingestion_run_id=RUN_ID,
            mappings_by_external_tag={mapping.external_tag_id: mapping},
            now=NOW,
        )
