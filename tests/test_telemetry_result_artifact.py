from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from types import MappingProxyType
import zlib

import pytest

from app.services.telemetry_analysis_window import AnalysisWindowExecution
from app.services.telemetry_result_artifact import (
    ARTIFACT_SCHEMA_VERSION,
    PAYLOAD_ENCODING,
    CanonicalResultArtifactError,
    build_canonical_result_artifact,
    decode_canonical_result_artifact,
)

LINEAGE_DIGEST = "a" * 64


def _execution(
    *,
    marker: str = "original",
    analysis_schema: str = "analysis-result-v1",
    analysis_contract: str = "analysis-result-v1",
) -> AnalysisWindowExecution:
    return AnalysisWindowExecution(
        window_id="00000000-0000-5000-8000-000000000101",
        source_kind="connector",
        source_run_id="00000000-0000-4000-8000-000000000202",
        sii_result=MappingProxyType(
            {
                "engine": {"name": "sii", "version": "2.4.1"},
                "status": "complete",
                "marker": marker,
                "behavioral_model": {
                    "contract_version": "behavioral-model.v1",
                    "model_id": "model-actual",
                    "model_version": "v7",
                    "snapshot_id": "snapshot-current",
                    "baseline_state": {"active_version": "baseline-v3"},
                },
                "behavioral_snapshots": {
                    "current_snapshot_id": "snapshot-current",
                    "previous_snapshot_id": "snapshot-previous",
                    "model_version": "v7",
                    "rollback_reference": "snapshot-previous",
                },
                "findings": [
                    {
                        "finding_id": "finding-engine",
                        "evidence_ids": ["evidence-engine"],
                    }
                ],
            }
        ),
        analysis_result=MappingProxyType(
            {
                "schema_version": analysis_schema,
                "status": "complete",
                "analysis_id": "00000000-0000-5000-8000-000000000101",
                "analysis_metadata": {
                    "contract_version": analysis_contract,
                    "run_id": "00000000-0000-4000-8000-000000000202",
                },
                "conditions": [{"id": "condition-1", "evidence_refs": ["evidence-1"]}],
                "insights": [{"id": "insight-1"}],
                "evidence_index": {"evidence-1": {"value": 42}},
                "sii_evidence": {
                    "provenance": {
                        "baseline_id": "baseline-actual",
                        "baseline_version": "baseline-v3",
                    }
                },
                "normalized_telemetry": {
                    "records": [{"signal": "power", "value": 42.0}]
                },
            }
        ),
        telemetry_lineage=MappingProxyType(
            {
                "contract_version": "telemetry-window-lineage-summary.v1",
                "window_id": "00000000-0000-5000-8000-000000000101",
                "source_kind": "connector",
                "source_run_id": "00000000-0000-4000-8000-000000000202",
                "observation_count": 2,
                "lineage_digest": LINEAGE_DIGEST,
            }
        ),
    )


def test_canonical_artifact_is_deterministic_and_round_trips_exact_execution() -> None:
    execution = _execution()

    first = build_canonical_result_artifact(execution)
    second = build_canonical_result_artifact(execution)

    assert first.result_id == second.result_id
    assert first.payload_digest == second.payload_digest
    assert first.payload == second.payload
    assert first.artifact_schema_version == ARTIFACT_SCHEMA_VERSION
    assert first.payload_encoding == PAYLOAD_ENCODING
    assert first.payload_uncompressed_bytes == len(zlib.decompress(first.payload))
    assert first.payload_stored_bytes == len(first.payload)
    assert first.serialization_ms >= 0
    assert deepcopy(first) is first
    assert decode_canonical_result_artifact(first) == execution.as_dict()


def test_payload_mutation_changes_digest_but_same_window_keeps_result_identity() -> (
    None
):
    original = build_canonical_result_artifact(_execution(marker="original"))
    mutated = build_canonical_result_artifact(_execution(marker="mutated"))

    assert mutated.result_id == original.result_id
    assert mutated.payload_digest != original.payload_digest
    assert mutated.payload != original.payload


def test_artifact_preserves_actual_versions_references_and_generated_ids() -> None:
    artifact = build_canonical_result_artifact(
        _execution(
            analysis_schema="analysis-schema-actual",
            analysis_contract="analysis-contract-actual",
        )
    )

    assert artifact.execution_contract_version == "analysis-window-execution.v1"
    assert artifact.analysis_schema_version == "analysis-schema-actual"
    assert artifact.analysis_contract_version == "analysis-contract-actual"
    assert artifact.engine_name == "sii"
    assert artifact.engine_version == "2.4.1"
    assert artifact.observation_count == 2
    assert artifact.observation_lineage_digest == LINEAGE_DIGEST
    assert set(artifact.finding_ids["ids"]) == {
        "condition-1",
        "finding-engine",
        "insight-1",
    }
    assert set(artifact.evidence_ids["ids"]) == {"evidence-1", "evidence-engine"}
    references = {
        (item["source_path"], item["value"])
        for item in artifact.reference_metadata["references"]
    }
    assert (
        "sii_result.behavioral_model.model_id",
        "model-actual",
    ) in references
    assert (
        "sii_result.behavioral_model.baseline_state.active_version",
        "baseline-v3",
    ) in references
    assert (
        "sii_result.behavioral_snapshots.current_snapshot_id",
        "snapshot-current",
    ) in references
    assert (
        "analysis_result.sii_evidence.provenance.baseline_id",
        "baseline-actual",
    ) in references


def test_non_finite_payload_is_rejected() -> None:
    execution = _execution()
    non_finite = replace(
        execution,
        sii_result=MappingProxyType({**execution.sii_result, "invalid": float("nan")}),
    )

    with pytest.raises(
        CanonicalResultArtifactError, match="canonical_result_payload_not_json"
    ):
        build_canonical_result_artifact(non_finite)


def test_engine_datetime_values_are_canonicalized_for_durable_json() -> None:
    execution = _execution()
    generated_at = datetime(2026, 8, 26, 12, 34, 56, tzinfo=UTC)
    with_engine_datetime = replace(
        execution,
        sii_result=MappingProxyType(
            {**execution.sii_result, "evidence": {"generated_at": generated_at}}
        ),
    )

    artifact = build_canonical_result_artifact(with_engine_datetime)

    assert decode_canonical_result_artifact(artifact)["sii_result"]["evidence"][
        "generated_at"
    ] == generated_at.isoformat()


def test_oversize_payload_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.telemetry_result_artifact.MAX_CANONICAL_RESULT_BYTES", 128
    )

    with pytest.raises(
        CanonicalResultArtifactError, match="canonical_result_payload_too_large"
    ):
        build_canonical_result_artifact(_execution())


def test_decode_rejects_indexed_schema_version_mismatch() -> None:
    artifact = build_canonical_result_artifact(_execution())
    mismatched = replace(artifact, analysis_schema_version="not-the-payload-schema")

    with pytest.raises(
        CanonicalResultArtifactError,
        match="canonical_result_analysis_schema_version_mismatch",
    ):
        decode_canonical_result_artifact(mismatched)


def test_decode_rejects_digest_or_noncanonical_payload() -> None:
    artifact = build_canonical_result_artifact(_execution())
    payload_value = decode_canonical_result_artifact(artifact)
    noncanonical = json.dumps(payload_value, sort_keys=False, indent=2).encode("utf-8")
    repacked = replace(
        artifact,
        payload=zlib.compress(noncanonical, level=9),
        payload_digest=hashlib.sha256(noncanonical).hexdigest(),
        payload_uncompressed_bytes=len(noncanonical),
        payload_stored_bytes=len(zlib.compress(noncanonical, level=9)),
    )

    with pytest.raises(
        CanonicalResultArtifactError, match="canonical_result_payload_not_canonical"
    ):
        decode_canonical_result_artifact(repacked)

    with pytest.raises(
        CanonicalResultArtifactError, match="canonical_result_payload_digest_mismatch"
    ):
        decode_canonical_result_artifact(replace(artifact, payload_digest="0" * 64))


def test_canonical_artifact_replays_full_consequence_provenance():
    from neraium_consequence import quantify_consequence
    execution = _execution()
    analysis = deepcopy(dict(execution.analysis_result))
    consequence = dict(quantify_consequence(
        [{"timestamp": "1970-01-01T01:00:00+01:00", "observed": 30, "expected": 20},
         {"timestamp": 60, "observed": 30, "expected": 20}],
        profile_key="water_gpm", source_relationship_ids=["rel: exact "], finding_id="condition-1",
    ))
    analysis["conditions"][0]["measurable_consequence"] = consequence
    execution = replace(execution, analysis_result=MappingProxyType(analysis))
    artifact = build_canonical_result_artifact(execution)
    replay = decode_canonical_result_artifact(artifact)
    assert replay["analysis_result"]["conditions"][0]["measurable_consequence"] == consequence
    assert build_canonical_result_artifact(execution).payload_digest == artifact.payload_digest
