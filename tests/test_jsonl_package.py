from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
import json

import pytest

from app.connectors.jsonl_package import load_jsonl_connector_page
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_ingestion import MappingSnapshot, prepare_connector_page
from app.services.telemetry_units import UNIT_NORMALIZATION_VERSION


NOW = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)


def record(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "source": "vendor.test",
        "partition_id": "partition-1",
        "asset_id": "asset-1",
        "point_id": "point-1",
        "point_name": "Supply temperature",
        "timestamp": "2026-08-25T11:00:00Z",
        "value": 21.5,
        "unit": "degC",
        "quality": "good",
        "metadata": {"description": "test", "site": "north"},
    }
    result.update(overrides)
    return result


def package(*records: dict[str, object]) -> StringIO:
    return StringIO("\n".join(json.dumps(item) for item in records) + "\n")


def test_valid_numeric_record_maps_source_neutral_fields() -> None:
    page = load_jsonl_connector_page(package(record()))
    assert len(page.observations) == 1
    observation = page.observations[0]
    assert observation.external_tag_id == "point-1"
    assert observation.external_tag_name == "Supply temperature"
    assert observation.source_timestamp == "2026-08-25T11:00:00Z"
    assert observation.raw_value == 21.5
    assert observation.reported_unit == "degC"
    assert observation.reported_quality == "good"
    assert observation.metadata["source"] == "vendor.test"
    assert observation.metadata["asset_id"] == "asset-1"
    assert observation.metadata["partition_id"] == "partition-1"
    assert "canonical_signal_id" not in observation.metadata
    assert "internal_asset_id" not in observation.metadata


def test_multiple_records_create_one_connector_page() -> None:
    page = load_jsonl_connector_page(package(record(point_id="a"), record(point_id="b", value=2)))
    assert [item.external_tag_id for item in page.observations] == ["a", "b"]
    assert page.pages_read == 1
    assert page.issues == ()


@pytest.mark.parametrize("bad", [record(value=True), record(value="21.5"), record(value={"x": 1})])
def test_unsupported_scalar_is_explicitly_rejected(bad: dict[str, object]) -> None:
    page = load_jsonl_connector_page(package(bad))
    assert page.observations == ()
    assert page.issues[0].code == "unsupported_value_type"


def test_missing_required_and_malformed_json_are_rejected_deterministically() -> None:
    missing = record()
    del missing["point_id"]
    page = load_jsonl_connector_page(StringIO(json.dumps(missing) + "\nnot-json\n"))
    assert [issue.code for issue in page.issues] == ["missing_point_id", "malformed_json"]


def test_invalid_timestamp_reaches_existing_preparation_layer() -> None:
    page = load_jsonl_connector_page(package(record(timestamp="not-a-timestamp")))
    assert len(page.observations) == 1
    tenant, workspace = "tenant", "workspace"
    scope = TelemetryScopeRef(tenant, workspace, canonical_phase4_resource_scope_id(tenant, workspace), workspace)
    mapping = MappingSnapshot(
        scope=scope, connection_id="connection", external_tag_id="point-1",
        external_signal_id="signal", mapping_id="mapping", revision=1,
        actor_id="actor", mapped_at=NOW, authority_digest="a" * 64,
        facility_id=workspace, system_id="system", canonical_signal_id="canonical",
        canonical_signal_name="temperature", source_unit="degC", canonical_unit="degC",
        expected_dimension="temperature", conversion_id="c_to_c",
        conversion_version=UNIT_NORMALIZATION_VERSION, source_timezone="UTC",
    )
    prepared = prepare_connector_page(
        page=page, scope=scope, connection_id="connection", ingestion_run_id="run",
        mappings_by_external_tag={"point-1": mapping}, now=NOW, ingested_at_utc=NOW,
    )
    assert prepared.accepted_count == 0
    assert prepared.rejections[0].reason_code == "timestamp_parse_invalid"


@pytest.mark.parametrize("key", ["password", "authorization", "api_key", "clientSecret"])
def test_credential_like_metadata_is_rejected(key: str) -> None:
    page = load_jsonl_connector_page(package(record(metadata={key: "secret"})))
    assert page.observations == ()
    assert page.issues[0].code == "metadata_sensitive_or_invalid_key"


def test_bearer_token_like_metadata_is_rejected() -> None:
    page = load_jsonl_connector_page(package(record(metadata={"note": "Bearer abcdefghijk"})))
    assert page.issues[0].code == "metadata_sensitive_or_invalid_value"
