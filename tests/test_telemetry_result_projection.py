from __future__ import annotations

import json

import pytest

from app.services.telemetry_result_projection import (
    MAX_EVIDENCE_AUDIT_BYTES,
    MAX_SHARED_ENVELOPE_BYTES,
    MAX_TECHNICAL_CHANNEL_BYTES,
    MAX_TECHNICAL_CHANNELS_BYTES,
    CanonicalResultProjectionError,
    build_canonical_result_projection,
    canonical_projection_digest,
)


WINDOW_ID = "00000000-0000-5000-8000-000000000101"
RUN_ID = "00000000-0000-4000-8000-000000000202"
RESULT_ID = "00000000-0000-5000-8000-000000000303"
PAYLOAD_DIGEST = "d" * 64
LINEAGE_DIGEST = "a" * 64


def _execution(*, state: str = "material") -> dict:
    if state == "stable":
        conditions = []
        insights = []
        summary = {"status": "normal", "headline": "No supported change"}
        warnings = []
    elif state == "insufficient":
        conditions = []
        insights = []
        summary = {"status": "insufficient", "headline": "Insufficient evidence"}
        warnings = ["Baseline coverage is insufficient."]
    else:
        conditions = [
            {
                "id": "condition-1",
                "title": "Power relationship changed",
                "status": "supported",
                "tier": "Material",
                "metrics": {"change": 0.42, "confidence": 0.91},
                "relationships": [
                    {
                        "id": "relationship-1",
                        "source": "power",
                        "target": "flow",
                        "evidence_refs": ["evidence-1"],
                    }
                ],
                "limitations": ["Cause is not established."],
            }
        ]
        insights = [{"id": "insight-1", "condition_id": "condition-1"}]
        summary = {"status": "change", "headline": "Analysis complete"}
        warnings = []
    execution = {
        "contract_version": "analysis-window-execution.v1",
        "status": "completed",
        "window_id": WINDOW_ID,
        "source_kind": "telemetry_connector",
        "source_run_id": RUN_ID,
        "sii_result": {
            "status": "complete",
            "engine": {"name": "sii", "version": "2.4.1"},
            "relationship_graph": {
                "changed_edges": [
                    {
                        "id": "relationship-1",
                        "source": "power",
                        "target": "flow",
                        "change": 0.42,
                    }
                ]
            },
            "temporal_analysis": {
                "lagged_relationships": [{"lag": 2, "score": 0.73}],
                "mutual_information_drift": [{"signal": "power", "delta": 0.2}],
            },
            "covariance_analysis": {"matrix": [[1.0, 0.4], [0.4, 1.0]]},
            "behavioral_model": {"model_id": "model-real", "model_version": "7"},
            "physics_reasoning": {"status": "unavailable", "reason": "not supplied"},
        },
        "analysis_result": {
            "schema_version": "analysis-schema.actual",
            "status": "complete",
            "analysis_id": WINDOW_ID,
            "upload_id": "",
            "source_file": "",
            "generated_at": "2026-08-26T12:00:00+00:00",
            "data_quality": {"status": "ready"},
            "executive_summary": summary,
            "systems": [{"id": "system-1", "status": summary["status"]}],
            "conditions": conditions,
            "relationships": conditions[0]["relationships"] if conditions else [],
            "fingerprint": {"drift_status": summary["status"]},
            "insights": insights,
            "recommendations": [],
            "evidence_index": {"evidence-1": {"metric": 0.42}} if conditions else {},
            "warnings": warnings,
            "errors": [],
            "telemetry_signals": [
                {"canonical_signal_id": "power"},
                {"canonical_signal_id": "flow"},
            ],
            "analysis_metadata": {
                "contract_version": "analysis-contract.actual",
                "run_id": RUN_ID,
                "source_type": "telemetry_connector",
            },
            "sii_evidence": {
                "status": "complete",
                "relationship_changes": [{"id": "relationship-1"}],
            },
            "telemetry_lineage": {
                "window_id": WINDOW_ID,
                "source_run_id": RUN_ID,
                "observation_count": 2,
                "lineage_digest": LINEAGE_DIGEST,
            },
            "normalized_telemetry": {
                "status": "ready",
                "row_count": 2,
                "record_count": 4,
                "records": [
                    {"timestamp": "2026-08-26T00:00:00Z", "value": 10.0},
                    {"timestamp": "2026-08-26T00:00:00Z", "value": 20.0},
                    {"timestamp": "2026-08-26T00:01:00Z", "value": 11.0},
                    {"timestamp": "2026-08-26T00:01:00Z", "value": 21.0},
                ],
                "tags": [{"source_column": "power"}, {"source_column": "flow"}],
                "signals": [{"source_column": "power"}, {"source_column": "flow"}],
            },
        },
        "telemetry_lineage": {
            "contract_version": "telemetry-window-lineage-summary.v1",
            "window_id": WINDOW_ID,
            "source_kind": "telemetry_connector",
            "source_run_id": RUN_ID,
            "observation_count": 2,
            "lineage_digest": LINEAGE_DIGEST,
        },
    }
    execution["analysis_result"]["data_quality"]["normalized_telemetry"] = (
        execution["analysis_result"]["normalized_telemetry"]
    )
    return execution


def _metadata() -> dict:
    return {
        "result_id": RESULT_ID,
        "artifact_schema_version": "telemetry-canonical-result-artifact.v1",
        "execution_contract_version": "analysis-window-execution.v1",
        "analysis_schema_version": "analysis-schema.actual",
        "analysis_contract_version": "analysis-contract.actual",
        "engine_name": "sii",
        "engine_version": "2.4.1",
        "reference_metadata": {
            "references": [
                {
                    "kind": "model_id",
                    "source_path": "sii_result.behavioral_model.model_id",
                    "value": "model-real",
                }
            ],
            "total": 1,
            "truncated": False,
        },
        "observation_count": 2,
        "observation_lineage_digest": LINEAGE_DIGEST,
        "finding_ids": {"ids": ["condition-1", "insight-1"], "total": 2, "truncated": False},
        "evidence_ids": {"ids": ["evidence-1"], "total": 1, "truncated": False},
        "payload_digest": PAYLOAD_DIGEST,
        "payload_uncompressed_bytes": 10_000,
        "payload_stored_bytes": 2_000,
    }


def _scope() -> dict:
    return {
        "tenant_scope_id": "tenant-a",
        "workspace_id": "ws-facility-a",
        "resource_scope_id": "resource-a",
        "facility_id": "ws-facility-a",
        "analysis_window_id": WINDOW_ID,
        "connection_id": "00000000-0000-4000-8000-000000000404",
        "source_ingestion_run_id": RUN_ID,
        "system_id": "system-1",
        "asset_id": "asset-1",
        "window_start": "2026-08-26T00:00:00+00:00",
        "window_end": "2026-08-26T01:00:00+00:00",
        "authority_digest": "b" * 64,
    }


def _plain_projection(projection) -> dict:
    return dict(projection.product_result)


def test_projection_routes_exact_result_without_normalized_records_or_recalculation() -> None:
    execution = _execution()

    projection = build_canonical_result_projection(
        execution,
        artifact_metadata=_metadata(),
        scope=_scope(),
        lineage_verified=True,
    )
    result = _plain_projection(projection)

    assert result["identity"]["result_id"] == RESULT_ID
    assert result["identity"]["analysis_window_id"] == WINDOW_ID
    assert result["identity"]["payload_digest"] == PAYLOAD_DIGEST
    assert result["result_id"] == RESULT_ID
    assert result["analysis_window_id"] == WINDOW_ID
    assert result["connection_id"] == _scope()["connection_id"]
    assert result["source_run_id"] == RUN_ID
    assert result["facility_id"] == "ws-facility-a"
    assert result["window_start"] == "2026-08-26T00:00:00+00:00"
    assert result["window_end"] == "2026-08-26T01:00:00+00:00"
    assert result["payload_digest"] == PAYLOAD_DIGEST
    assert result["lineage_verified"] is True
    assert result["lineage"] == {
        "analysis_window_id": WINDOW_ID,
        "observation_count": 2,
        "digest": LINEAGE_DIGEST,
        "verified": True,
        "detail_source": "analysis_window_observations",
    }
    assert "records" not in result["analysis_result"]["normalized_telemetry"]
    assert "records" not in result["analysis_result"]["data_quality"][
        "normalized_telemetry"
    ]
    assert result["analysis_result"]["normalized_telemetry"]["record_count"] == 4
    assert result["analysis_result"]["conditions"] == execution["analysis_result"]["conditions"]
    assert (
        result["sii_result"]["temporal_analysis"]
        == execution["sii_result"]["temporal_analysis"]
    )
    assert result["canonical_result"]["reference_metadata"] == _metadata()["reference_metadata"]
    assert result["product_boundary"] == {"mode": "read_only", "control_actions": []}
    assert result["data_quality"]["status"] == "ready"
    assert "records" not in result["data_quality"]["normalized_telemetry"]
    assert result["sii_result"]["engine"] == execution["sii_result"]["engine"]
    assert projection.shared_envelope_bytes <= MAX_SHARED_ENVELOPE_BYTES
    assert projection.technical_channels_bytes <= MAX_TECHNICAL_CHANNELS_BYTES
    assert projection.evidence_audit_bytes <= MAX_EVIDENCE_AUDIT_BYTES
    assert projection.projection_bytes > 0
    assert projection.serialization_ms >= 0


@pytest.mark.parametrize("state", ["stable", "insufficient"])
def test_stable_and_insufficient_results_preserve_empty_finding_state(state: str) -> None:
    execution = _execution(state=state)
    metadata = _metadata()
    metadata["finding_ids"] = {"ids": [], "total": 0, "truncated": False}
    metadata["evidence_ids"] = {"ids": [], "total": 0, "truncated": False}

    result = _plain_projection(
        build_canonical_result_projection(
            execution, artifact_metadata=metadata, scope=_scope()
        )
    )

    assert result["analysis_result"]["conditions"] == []
    assert result["analysis_result"]["insights"] == []
    assert result["canonical_result"]["evidence_audit"]["finding_records"] == []
    assert result["identity"]["result_id"] == RESULT_ID


def test_large_channels_and_catalogs_are_bounded_with_explicit_source_metadata() -> None:
    execution = _execution()
    execution["sii_result"]["temporal_analysis"] = {
        f"metric-{index}": ["x" * 4_000 for _ in range(40)]
        for index in range(300)
    }
    execution["analysis_result"]["normalized_telemetry"]["signals"] = [
        {"source_column": f"signal-{index}", "description": "y" * 4_000}
        for index in range(200)
    ]

    projection = build_canonical_result_projection(
        execution, artifact_metadata=_metadata(), scope=_scope()
    )
    result = _plain_projection(projection)
    temporal_metadata = result["projection"]["technical_channels"]["temporal_analysis"]

    assert temporal_metadata["truncated"] is True
    assert temporal_metadata["source_path"] == "sii_result.temporal_analysis"
    assert temporal_metadata["canonical_result_id"] == RESULT_ID
    assert temporal_metadata["selected_bytes"] <= MAX_TECHNICAL_CHANNEL_BYTES
    assert len(result["analysis_result"]["normalized_telemetry"]["signals"]) <= 64
    assert result["projection"]["shared"]["truncated"] is True
    assert projection.shared_envelope_bytes <= MAX_SHARED_ENVELOPE_BYTES
    assert projection.technical_channels_bytes <= MAX_TECHNICAL_CHANNELS_BYTES


def test_projection_fails_closed_on_version_scope_or_digest_mismatch() -> None:
    metadata = _metadata()
    metadata["analysis_schema_version"] = "wrong"
    with pytest.raises(
        CanonicalResultProjectionError,
        match="canonical_result_projection_analysis_schema_version_mismatch",
    ):
        build_canonical_result_projection(
            _execution(), artifact_metadata=metadata, scope=_scope()
        )

    wrong_scope = _scope()
    wrong_scope["source_ingestion_run_id"] = "wrong-run"
    with pytest.raises(
        CanonicalResultProjectionError,
        match="canonical_result_projection_source_ingestion_run_id_mismatch",
    ):
        build_canonical_result_projection(
            _execution(), artifact_metadata=_metadata(), scope=wrong_scope
        )

    metadata = _metadata()
    metadata["payload_digest"] = "not-a-digest"
    with pytest.raises(
        CanonicalResultProjectionError,
        match="canonical_result_projection_payload_digest_invalid",
    ):
        build_canonical_result_projection(
            _execution(), artifact_metadata=metadata, scope=_scope()
        )


def test_projection_is_deterministic_and_does_not_mutate_exact_execution() -> None:
    execution = _execution()
    original = json.loads(json.dumps(execution))

    first = build_canonical_result_projection(
        execution, artifact_metadata=_metadata(), scope=_scope()
    )
    second = build_canonical_result_projection(
        execution, artifact_metadata=_metadata(), scope=_scope()
    )

    assert execution == original
    assert canonical_projection_digest(first) == canonical_projection_digest(second)
    assert first.projection_bytes == second.projection_bytes


def test_measurable_consequence_survives_canonical_projection_without_recalculation():
    from neraium_consequence import quantify_consequence
    execution = _execution()
    consequence = dict(quantify_consequence(
        [{"timestamp": 0, "observed": 30, "expected": 20},
         {"timestamp": 60, "observed": 30, "expected": 20}],
        profile_key="water_gpm", finding_id="condition-1", source_relationship_ids=["rel: exact "],
    ))
    execution["analysis_result"]["conditions"][0]["measurable_consequence"] = consequence
    projection = build_canonical_result_projection(execution, artifact_metadata=_metadata(), scope=_scope())
    assert projection.product_result["analysis_result"]["conditions"][0]["measurable_consequence"] == consequence
