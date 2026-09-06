from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

import pytest
from app.connectors.https_telemetry import _HttpsConfig
from app.models.telemetry_api_models import ConnectionCreateRequest
from app.services.consequence_configuration import validate_consequence_configuration
from app.services.telemetry_analysis_service import run_post_ingestion_analysis
from app.services.telemetry_domain import ConnectorType
from neraium_consequence import RESOURCE_PROFILES
from pydantic import ValidationError
from test_consequence_certification import FLOW, START, configured_signal, source_result
from test_historian_provider_boundary import context, setup_connector
from test_https_telemetry_connector import configuration
from test_measurable_consequence import fixture, run
from test_telemetry_analysis_service import (
    DIGEST,
    FakeAnalysisRepository,
    _observation,
    _scope,
)


@pytest.mark.parametrize(
    "profile_key",
    [
        "water_gpm",
        "electricity_kw",
        "steam_lb_per_hr",
        "chemical_feed_gal_per_hr",
        "compressed_air_scfm",
    ],
)
def test_all_explicit_resource_profiles_are_admitted_and_quantified(profile_key):
    profile = RESOURCE_PROFILES[profile_key]
    metadata = {
        "resource_type": profile.resource_type,
        "consequence_profile_key": profile_key,
        "rate_unit": profile.rate_unit,
        "max_gap_seconds": 3600,
    }
    config = validate_consequence_configuration({"signals": {FLOW: metadata}})
    assert config["signals"][FLOW] == metadata
    finding, expected, catalog = fixture()
    catalog["flow"] = {**metadata, "canonical_unit": profile.rate_unit}
    result = run(finding, expected, catalog)
    assert result["status"] == "quantified"
    assert result["profile_key"] == profile_key
    assert result["resource_type"] == profile.resource_type
    assert result["cumulative_unit"] == profile.cumulative_unit


@pytest.mark.parametrize(
    "unit,name",
    [
        ("gpm", "volumetric_flow"),
        ("kW", "electrical.active_power"),
        ("scfm", "air_flow"),
    ],
)
def test_bare_units_and_signal_names_never_establish_resource_identity(unit, name):
    finding, expected, catalog = fixture()
    catalog["flow"] = {
        "canonical_unit": unit,
        "canonical_signal_name": name,
        "max_gap_seconds": 3600,
    }
    assert run(finding, expected, catalog)["status"] == "not_quantifiable"


@pytest.mark.parametrize(
    "change",
    [
        {"resource_type": "steam"},
        {"rate_unit": "scfm"},
        {"consequence_profile_key": "unknown"},
        {"max_gap_seconds": 0},
        {"max_gap_seconds": -1},
        {"max_gap_seconds": True},
        {"max_gap_seconds": "60"},
        {"max_gap_seconds": float("inf")},
        {"max_gap_seconds": float("nan")},
        {"max_gap_seconds": None},
        {"unexpected": "field"},
    ],
)
def test_configuration_rejects_ambiguous_profiles_and_invalid_gaps(change):
    with pytest.raises(ValidationError):
        validate_consequence_configuration(
            {"signals": {FLOW: {**configured_signal(), **change}}}
        )


@pytest.mark.parametrize(
    "field",
    ["resource_type", "consequence_profile_key", "rate_unit", "max_gap_seconds"],
)
def test_explicit_signal_configuration_requires_every_field(field):
    metadata = configured_signal()
    metadata.pop(field)
    with pytest.raises(ValidationError):
        validate_consequence_configuration({"signals": {FLOW: metadata}})


def test_https_and_historian_admit_configuration_without_forwarding_it_to_provider_parameters():
    consequence = {"signals": {FLOW: configured_signal()}}
    request = ConnectionCreateRequest(
        name="Flow",
        connector_type=ConnectorType.HTTPS_TELEMETRY,
        configuration=configuration(consequence=consequence),
    )
    _HttpsConfig.from_mapping(request.configuration)
    connector, executor, binding, _ = setup_connector()
    historian_context = context(binding, consequence=consequence)
    request = ConnectionCreateRequest(
        name="Flow",
        connector_type=ConnectorType.HISTORIAN_TEMPLATE,
        configuration={
            "template_id": "central_plant_v1",
            "network_profile_id": "customer_private_link_01",
            "parameters": {"facility_code": "FAC-1", "batch_size": 500},
            "consequence": consequence,
        },
    )
    assert request.configuration["consequence"] == consequence
    assert connector.validate(historian_context).valid
    assert "consequence" not in executor.requests[0].parameters


@pytest.mark.parametrize("gap", [None, False, 0, -1, "60", float("inf"), float("nan")])
def test_missing_or_invalid_source_gap_never_falls_back_to_package_or_model_default(
    gap,
):
    finding, expected, catalog = fixture()
    catalog["flow"]["max_gap_seconds"] = gap
    result = run(finding, expected, catalog)
    assert result["status"] == "not_quantifiable"
    assert "maximum interval gap" in result["reason"]
    assert "cumulative_amount" not in result
    assert "duration_seconds" not in result


def test_unconfigured_expected_model_has_no_invented_acquisition_cadence():
    source, _ = source_result("resort-chilled-water", "A")
    expected = source["sii_result"]["expected_behavior"]["expected_values"][0]
    assert expected["max_gap_seconds"] is None
    result = source["analysis_result"]["conditions"][0]["measurable_consequence"]
    assert result["provenance"]["rate_unit_conversion"]["source_unit"] == "L/s"
    assert result["provenance"]["rate_unit_conversion"]["rate_unit"] == "gpm"
    assert result["provenance"]["expected_behavior"] == expected


def test_partial_gaps_exclude_duration_without_interpolation():
    finding, expected, catalog = fixture()
    expected["expected_values"][0]["observations"] = [
        {"timestamp": timestamp, "observed": 30, "expected": 20}
        for timestamp in (0, 60, 600, 660)
    ]
    catalog["flow"]["max_gap_seconds"] = 60
    result = run(finding, expected, catalog)
    assert result["status"] == "quantified"
    assert result["cumulative_amount"] == 20
    assert result["duration_seconds"] == 120
    assert result["contributing_interval_count"] == 2
    assert result["skipped_interval_count"] == 1
    assert result["provenance"]["effective_max_gap_seconds"] == 60


def test_conflicting_units_and_resource_profile_withhold_quantification():
    finding, expected, catalog = fixture()
    catalog["flow"]["engineering_units"] = "scfm"
    assert run(finding, expected, catalog)["status"] == "not_quantifiable"
    catalog["flow"] = {
        "resource_type": "steam",
        "canonical_unit": "gpm",
        "consequence_profile_key": "water_gpm",
    }
    assert run(finding, expected, catalog)["status"] == "not_quantifiable"


def test_operational_service_reads_scoped_connection_policy_and_reuses_recorded_execution():
    observations = [
        _observation(index, START + timedelta(minutes=index)) for index in range(2)
    ]
    for row in observations:
        row.update(
            canonical_concept_id=FLOW,
            canonical_signal_name="volumetric_flow",
            canonical_unit="L/s",
        )
    repository = FakeAnalysisRepository(observations)
    repository.configuration = {
        "consequence": {"signals": {FLOW: configured_signal(60)}}
    }
    seen = []

    def evaluator(**kwargs):
        seen.append(deepcopy(kwargs["telemetry_signal_catalog"]))
        return {"status": "limited", "compatibility": {}}

    kwargs = {
        "repository": repository,
        "scope": _scope(),
        "connection_id": "connection-a",
        "source_run_id": "run-a",
        "system_id": "system-a",
        "asset_id": "asset-a",
        "window_start": START,
        "window_end": START + timedelta(minutes=2),
        "persisted_authority_digest": DIGEST,
        "evaluator": evaluator,
    }
    first = run_post_ingestion_analysis(**kwargs)
    assert first.status == "completed"
    assert seen[0][FLOW]["max_gap_seconds"] == 60
    assert seen[0][FLOW]["consequence_connection_id"] == "connection-a"
    repository.configuration["consequence"]["signals"][FLOW]["max_gap_seconds"] = 1
    replay = run_post_ingestion_analysis(**kwargs)
    assert replay.reused_existing
    assert replay.artifact_digest == first.artifact_digest
    assert len(seen) == 1


def test_no_catalog_or_expected_gap_refuses_quantification():
    finding, expected, catalog = fixture()
    catalog["flow"].pop("max_gap_seconds")
    expected["expected_values"][0].pop("max_gap_seconds")
    assert run(finding, expected, catalog)["status"] == "not_quantifiable"


def test_profile_rate_conversion_cannot_cross_dimensions():
    finding, expected, catalog = fixture()
    catalog["flow"] = {**configured_signal(), "canonical_unit": "kW"}
    result = run(finding, expected, catalog)
    assert result["status"] == "not_quantifiable"
    assert "conversion is unsupported" in result["reason"]


def test_unit_conversion_preserves_quality_barriers_and_original_evidence():
    finding, expected, catalog = fixture()
    catalog["flow"] = {**configured_signal(), "canonical_unit": "L/s"}
    expected["expected_values"][0]["observations"][3]["observed"] = True
    original = deepcopy(expected)
    result = run(finding, expected, catalog)
    assert result["skipped_interval_count"] == 2
    assert result["duration_seconds"] == 14400
    assert result["provenance"]["expected_behavior"] == original["expected_values"][0]
    assert expected == original
