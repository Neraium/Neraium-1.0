"""Commercial flow certification across production evidence and read boundaries."""

from __future__ import annotations

import json
from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

import pytest
from app.engine.sii.expected_behavior import evaluate_expected_behavior
from app.services import evidence_store, runtime_db
from app.services.analysis_result_contract import build_analysis_result
from app.services.finding_workflow import evidence_finding_id
from app.services.telemetry_analysis_window import build_canonical_analysis_window
from app.services.telemetry_result_artifact import (
    build_canonical_result_artifact,
    decode_canonical_result_artifact,
)
from app.services.telemetry_result_projection import build_canonical_result_projection
from app.services.telemetry_units import normalize_telemetry_unit
from app.services.upload_evidence import build_evidence_record_from_result
from test_telemetry_analysis_service import (
    DIGEST,
    FakeAnalysisRepository,
    _observation,
    _scope,
)
from test_telemetry_result_artifact import _execution
from test_telemetry_result_projection import _scope as projection_scope

FLOW = "a19db5be-5ca1-5373-a9e4-6957e9f54c43"
LOAD = "ba959381-2fc2-556f-aa57-279a9f97d3b8"
START = datetime(2026, 9, 1, tzinfo=UTC)


def configured_signal(max_gap=3600):
    return {
        "resource_type": "water",
        "consequence_profile_key": "water_gpm",
        "rate_unit": "gpm",
        "max_gap_seconds": max_gap,
    }


def flow_lps(value):
    return normalize_telemetry_unit(
        value=value, source_unit="gpm", canonical_unit="L/s", expected_dimension="flow"
    ).canonical_value


def source_result(system, case, sign=1):
    observations = []
    # Explicit normalized telemetry fixture: rates differ by 10 gpm for six hours.
    for index in range(7):
        for signal, value, unit in [
            (FLOW, 100 + 2 * index + sign * 10, "gpm"),
            (LOAD, index, "fraction"),
        ]:
            row = _observation(
                index, START + timedelta(hours=index), run_id=_execution().source_run_id
            )
            row.update(
                id=f"{signal}-{index}",
                canonical_concept_id=signal,
                canonical_signal_name="volumetric_flow"
                if signal == FLOW
                else "fraction",
                normalized_value=flow_lps(value) if signal == FLOW else value,
                canonical_unit="L/s" if signal == FLOW else unit,
                original_unit=unit,
                external_tag_id=f"{system}.{signal}",
                conversion_id="identity",
            )
            observations.append(row)
    repository = FakeAnalysisRepository(observations)
    scope = _scope()
    identity = repository.resolve_analysis_authority_snapshot(
        scope, system_id="system-a", asset_id="asset-a", authority_digest=DIGEST
    )
    window = build_canonical_analysis_window(
        window_id=_execution().window_id,
        source_run_id=_execution().source_run_id,
        scope=scope,
        system_id="system-a",
        asset_id="asset-a",
        persisted_authority_digest=DIGEST,
        phase4_system_identity=identity,
        observations=observations,
        consequence_connection_id="connection-a",
        consequence_configuration=None
        if case == "B"
        else {"signals": {FLOW: configured_signal(1800 if case == "C" else 3600)}},
    )
    model = {
        "model_id": "validated-flow-response-v3",
        "target_signal": FLOW,
        "predictor_signals": [LOAD],
        "operating_mode": "running",
        "validation": {"passed": True},
        "sample_support": 80,
        "model_parameters": {
            "intercept": flow_lps(100),
            "slope": flow_lps(2),
            "lag_samples": 0,
        },
        "source_relationships": ["flow:load"],
        "limitations": ["Expected rates use the validated reference model."],
    }
    expected = evaluate_expected_behavior(
        active_model={"expected_behavior_models": {model["model_id"]: model}},
        rows=[dict(row) for row in window.rows],
        operating_mode="running",
        data_quality={"readiness": "ready"},
        sensor_health={
            "signals": [
                {"signal": signal, "health": "healthy"} for signal in (FLOW, LOAD)
            ]
        },
        source_model_version="3",
        evaluation_time=START.isoformat(),
        timestamp_column=window.timestamp_column,
    )
    finding = {
        "id": "flow-finding",
        "headline": "Flow response changed",
        "support_level": "high",
        "operating_mode": {"match": "strong"},
        "persistence": {"status": "persistent"},
        "source_relationship_ids": ["flow:load"],
        "source_tags": [FLOW, LOAD],
        "evidence_id": "flow-evidence",
        "source_time_ranges": [
            {
                "current_start": START.isoformat(),
                "current_end": (START + timedelta(hours=6)).isoformat(),
            }
        ],
    }
    source = {
        "analysis_id": window.window_id,
        "run_id": window.source_run_id,
        "completed_at": START.isoformat(),
        "conditions": [finding],
        "analysis_explanation": {"insights": []},
        "sii_result": {"expected_behavior": expected},
        "telemetry_signal_catalog": {
            key: dict(value) for key, value in window.telemetry_signal_catalog.items()
        },
    }
    source["analysis_result"] = build_analysis_result(source)
    return source, window


@pytest.mark.parametrize("system", ["resort-chilled-water", "wastewater-treatment"])
@pytest.mark.parametrize("case,sign", [("A", 1), ("A", -1), ("B", 1), ("C", 1)])
def test_cases_through_canonical_persistence_replay_and_findings_api(
    system, case, sign, client, monkeypatch
):
    source, window = source_result(system, case, sign)
    canonical = source["analysis_result"]["conditions"][0]["measurable_consequence"]
    if case == "A":
        assert canonical["status"] == "quantified"
        assert canonical["cumulative_amount"] == pytest.approx(sign * 3600)
        assert canonical["cumulative_unit"] == "gal"
        assert canonical["duration_seconds"] == 21600
        assert canonical["start_timestamp"] == START.timestamp()
        assert canonical["end_timestamp"] == (START + timedelta(hours=6)).timestamp()
        assert canonical["support_level"] == "high"
        assert canonical["observation_count"] == 7
        assert canonical["contributing_interval_count"] == 6
        assert canonical["skipped_interval_count"] == 0
        assert canonical["provenance"]["effective_max_gap_seconds"] == 3600
    else:
        assert canonical["status"] == "not_quantifiable"
        assert "cumulative_amount" not in canonical
        assert "duration_seconds" not in canonical
        assert canonical["reason"] and canonical["limitations"]
        if case == "C":
            assert canonical["skipped_interval_count"] == 6
            assert canonical["provenance"]["effective_max_gap_seconds"] == 1800
    assert canonical["source_relationship_ids"] == ["flow:load"]
    assert canonical["source_tag_ids"] == [FLOW, LOAD]
    assert canonical["methodology"] == "timestamp_aware_trapezoidal_integration"
    assert canonical["methodology_version"] == "1.0.0"
    assert canonical["limitations"]
    assert not {
        "cost",
        "savings",
        "cause",
        "diagnosis",
        "leak",
        "waste",
        "remediation",
    }.intersection(canonical)

    execution = replace(
        _execution(),
        source_kind="telemetry_connector",
        analysis_result=MappingProxyType(source["analysis_result"]),
        sii_result=MappingProxyType(source["sii_result"]),
        telemetry_lineage=MappingProxyType(window.lineage_summary()),
    )
    artifact = build_canonical_result_artifact(execution)
    # Real SQLite evidence persistence complements the compressed connector artifact.
    record = build_evidence_record_from_result(
        run_id=source["run_id"],
        filename=f"{system}.csv",
        source_type="csv_upload",
        result=source,
        created_at=START.isoformat(),
        completed_at=START.isoformat(),
        status="completed",
        initiated_by="certification",
    )
    evidence_store.upsert_evidence_run(record)
    stored = runtime_db.read_evidence_run_db(source["run_id"])
    assert (
        stored["finding_identity_snapshot"][0]["finding"]["measurable_consequence"]
        == canonical
    )

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Replay must not recalculate consequence or expected behavior"
        )

    monkeypatch.setattr(
        "app.services.measurable_consequence.quantify_consequence", forbidden
    )
    monkeypatch.setattr(
        "app.engine.sii.expected_behavior.evaluate_expected_behavior", forbidden
    )
    replayed = decode_canonical_result_artifact(artifact)
    assert replayed["analysis_result"] == source["analysis_result"]
    projection = build_canonical_result_projection(
        replayed,
        artifact_metadata={
            field.name: getattr(artifact, field.name)
            for field in fields(artifact)
            if field.name != "payload"
        },
        scope=projection_scope(),
    )
    assert (
        projection.product_result["analysis_result"]["conditions"][0][
            "measurable_consequence"
        ]
        == canonical
    )
    finding_id = evidence_finding_id(source["run_id"], "flow-finding")
    for _ in range(2):
        response = client.get(f"/api/findings/{finding_id}")
        assert response.status_code == 200
        assert response.json()["measurable_consequence"] == canonical
    assert runtime_db.read_evidence_run_db(source["run_id"]) == stored
    fixture = json.loads(
        (
            Path(__file__).parents[1]
            / "frontend/tests/fixtures/consequence-certification.json"
        ).read_text()
    )
    assert fixture[f"{case}:{sign}"] == canonical


def test_historical_evidence_without_consequence_remains_readable(client):
    source, _ = source_result("wastewater-treatment", "A")
    source["analysis_result"]["conditions"][0].pop("measurable_consequence")
    record = build_evidence_record_from_result(
        run_id=source["run_id"],
        filename="historical.csv",
        source_type="csv_upload",
        result=source,
        created_at=START.isoformat(),
        completed_at=START.isoformat(),
        status="completed",
        initiated_by="certification",
    )
    evidence_store.upsert_evidence_run(record)
    response = client.get(
        f"/api/findings/{evidence_finding_id(source['run_id'], 'flow-finding')}"
    )
    assert response.status_code == 200
    assert response.json()["measurable_consequence"]["status"] == "not_quantifiable"
    assert "cumulative_amount" not in response.json()["measurable_consequence"]
