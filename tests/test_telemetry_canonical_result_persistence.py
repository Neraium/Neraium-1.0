from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_repository import (
    PostgreSQLTelemetryRepository,
    TelemetryResultArtifactConflict,
)
from app.services.telemetry_result_artifact import (
    CanonicalResultArtifact,
    canonical_result_id,
)


WINDOW_ID = "00000000-0000-5000-8000-000000000040"
SOURCE_RUN_ID = "00000000-0000-4000-8000-000000000020"
RESULT_ID = canonical_result_id(
    window_id=WINDOW_ID,
    execution_contract_version="analysis-window-execution.v1",
)
CLAIM_TOKEN = "00000000-0000-4000-8000-000000000050"
NOW = datetime(2026, 8, 26, tzinfo=UTC)


class _Cursor:
    def __init__(self, connection: "_Connection") -> None:
        self.connection = connection
        self.description: list[Any] = []

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.connection.statements.append((sql, params))

    def fetchone(self) -> Any:
        return self.connection.fetches.pop(0) if self.connection.fetches else None

    def fetchall(self) -> list[Any]:
        return list(self.connection.fetches.pop(0)) if self.connection.fetches else []


class _Connection:
    def __init__(self, fetches: list[Any]) -> None:
        self.fetches = list(fetches)
        self.statements: list[tuple[str, object]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> _Cursor:
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        return None


def _scope() -> TelemetryScopeRef:
    return TelemetryScopeRef(
        tenant_scope_id="tenant-a",
        workspace_id="ws-facility-a",
        resource_scope_id=canonical_phase4_resource_scope_id(
            "tenant-a", "ws-facility-a"
        ),
        facility_id="ws-facility-a",
    )


def _artifact() -> CanonicalResultArtifact:
    return CanonicalResultArtifact(
        result_id=RESULT_ID,
        analysis_window_id=WINDOW_ID,
        source_run_id=SOURCE_RUN_ID,
        artifact_schema_version="telemetry-canonical-result-artifact.v1",
        execution_contract_version="analysis-window-execution.v1",
        analysis_schema_version="analysis-result-v1",
        analysis_contract_version="analysis-result-v1",
        engine_name="sii",
        engine_version="1",
        reference_metadata={"references": [], "total": 0, "truncated": False},
        observation_count=2,
        observation_lineage_digest="f" * 64,
        finding_ids={"ids": ["finding-a"], "total": 1, "truncated": False},
        evidence_ids={"ids": ["evidence-a"], "total": 1, "truncated": False},
        payload_encoding="zlib+canonical-json.v1",
        payload_digest="d" * 64,
        payload_uncompressed_bytes=10,
        payload_stored_bytes=7,
        serialization_ms=1.25,
        payload=b"payload",
    )


def _stored_artifact(artifact: CanonicalResultArtifact) -> dict[str, Any]:
    return {
        "id": artifact.result_id,
        "analysis_window_id": WINDOW_ID,
        "source_ingestion_run_id": SOURCE_RUN_ID,
        "artifact_schema_version": artifact.artifact_schema_version,
        "execution_contract_version": artifact.execution_contract_version,
        "analysis_schema_version": artifact.analysis_schema_version,
        "analysis_contract_version": artifact.analysis_contract_version,
        "engine_name": artifact.engine_name,
        "engine_version": artifact.engine_version,
        "reference_metadata": dict(artifact.reference_metadata),
        "observation_count": artifact.observation_count,
        "observation_lineage_digest": artifact.observation_lineage_digest,
        "finding_ids": dict(artifact.finding_ids),
        "evidence_ids": dict(artifact.evidence_ids),
        "payload_encoding": artifact.payload_encoding,
        "payload_digest": artifact.payload_digest,
        "payload_uncompressed_bytes": artifact.payload_uncompressed_bytes,
        "payload_stored_bytes": artifact.payload_stored_bytes,
        "serialization_ms": artifact.serialization_ms,
        "payload": artifact.payload,
    }


def _finish(
    connection: _Connection, artifact: CanonicalResultArtifact
) -> dict[str, Any]:
    return PostgreSQLTelemetryRepository(
        lambda: connection
    ).finish_analysis_window_execution(
        _scope(),
        window_id=WINDOW_ID,
        claim_token=CLAIM_TOKEN,
        completed_at=NOW,
        target_status="completed",
        result_digest=artifact.payload_digest,
        result_metadata={"status": "stable"},
        evidence_lineage={
            "observation_count": artifact.observation_count,
            "observation_lineage_digest": artifact.observation_lineage_digest,
        },
        result_artifact=artifact,
    )


def test_artifact_and_window_completion_commit_atomically() -> None:
    artifact = _artifact()
    connection = _Connection(
        [
            {"id": RESULT_ID},
            _stored_artifact(artifact),
            {"id": WINDOW_ID, "status": "completed", "result_digest": "d" * 64},
        ]
    )

    completed = _finish(connection, artifact)

    assert completed["status"] == "completed"
    assert completed["canonical_result_id"] == RESULT_ID
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert "INSERT INTO telemetry.analysis_result_artifacts" in connection.statements[0][0]
    assert "UPDATE telemetry.analysis_windows" in connection.statements[2][0]


def test_identical_existing_artifact_is_reused_without_duplicate() -> None:
    artifact = _artifact()
    connection = _Connection(
        [
            None,
            _stored_artifact(artifact),
            {"id": WINDOW_ID, "status": "completed", "result_digest": "d" * 64},
        ]
    )

    completed = _finish(connection, artifact)

    assert completed["canonical_result_id"] == RESULT_ID
    assert connection.commits == 1
    insert_sql = connection.statements[0][0]
    assert "ON CONFLICT" in insert_sql
    assert len([sql for sql, _ in connection.statements if "INSERT INTO telemetry.analysis_result_artifacts" in sql]) == 1


def test_divergent_artifact_for_same_window_rolls_back_and_never_completes() -> None:
    stored = _artifact()
    divergent = replace(
        stored,
        payload=b"changed",
        payload_stored_bytes=7,
        payload_digest="e" * 64,
    )
    connection = _Connection([None, _stored_artifact(stored)])

    with pytest.raises(
        TelemetryResultArtifactConflict,
        match="telemetry_analysis_result_artifact_conflict",
    ):
        _finish(connection, divergent)

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert not any(
        "UPDATE telemetry.analysis_windows" in sql for sql, _ in connection.statements
    )


def test_artifact_for_another_window_is_rejected_before_storage() -> None:
    other_window_id = "00000000-0000-5000-8000-000000000041"
    artifact = replace(
        _artifact(),
        analysis_window_id=other_window_id,
        result_id=canonical_result_id(
            window_id=other_window_id,
            execution_contract_version="analysis-window-execution.v1",
        ),
    )
    connection = _Connection([])

    with pytest.raises(
        ValueError, match="telemetry_analysis_result_window_id_mismatch"
    ):
        _finish(connection, artifact)

    assert connection.statements == []
    assert connection.commits == 0
    assert connection.rollbacks == 0


def test_completed_transition_requires_a_canonical_artifact() -> None:
    repository = PostgreSQLTelemetryRepository(lambda: _Connection([]))

    with pytest.raises(
        ValueError, match="telemetry_analysis_result_artifact_required"
    ):
        repository.finish_analysis_window_execution(
            _scope(),
            window_id=WINDOW_ID,
            claim_token=CLAIM_TOKEN,
            completed_at=NOW + timedelta(seconds=1),
            target_status="completed",
            result_digest="d" * 64,
            result_metadata={},
            evidence_lineage={},
        )


def test_exact_result_and_lineage_reads_require_every_scope_predicate() -> None:
    result_connection = _Connection([{"id": RESULT_ID, "payload": b"payload"}])
    repository = PostgreSQLTelemetryRepository(lambda: result_connection)

    result = repository.get_analysis_result_artifact(
        _scope(),
        connection_id="00000000-0000-4000-8000-000000000010",
        source_run_id="00000000-0000-4000-8000-000000000020",
        system_id="system-a",
        asset_id=None,
        result_id=RESULT_ID,
    )

    assert result == {"id": RESULT_ID, "payload": b"payload"}
    result_sql = result_connection.statements[0][0]
    for predicate in (
        "a.resource_scope_id = %s",
        "a.tenant_scope_id = %s",
        "a.workspace_id = %s",
        "a.facility_id = %s",
        "a.connection_id = %s::UUID",
        "a.source_ingestion_run_id = %s::UUID",
        "a.system_id = %s",
        "a.asset_id IS NOT DISTINCT FROM %s",
        "a.id = %s::UUID",
        "w.status = 'completed'",
        "w.result_digest = a.payload_digest",
    ):
        assert predicate in result_sql
    assert "ORDER BY" not in result_sql
    assert "LIMIT 1" not in result_sql

    metadata_connection = _Connection([{"id": RESULT_ID}])
    metadata = PostgreSQLTelemetryRepository(
        lambda: metadata_connection
    ).get_analysis_result_artifact_metadata(
        _scope(),
        connection_id="00000000-0000-4000-8000-000000000010",
        source_run_id=SOURCE_RUN_ID,
        system_id="system-a",
        asset_id=None,
        result_id=RESULT_ID,
    )
    assert metadata == {"id": RESULT_ID}
    metadata_sql = metadata_connection.statements[0][0]
    assert "a.payload_digest" in metadata_sql
    assert "a.payload," not in metadata_sql
    assert "a.payload FROM" not in metadata_sql
    assert "a.asset_id IS NOT DISTINCT FROM %s" in metadata_sql

    lineage_connection = _Connection([[]])
    PostgreSQLTelemetryRepository(
        lambda: lineage_connection
    ).list_analysis_result_lineage_records(
        _scope(),
        connection_id="00000000-0000-4000-8000-000000000010",
        source_run_id="00000000-0000-4000-8000-000000000020",
        system_id="system-a",
        asset_id=None,
        result_id=RESULT_ID,
    )
    lineage_sql = lineage_connection.statements[0][0]
    assert "telemetry.analysis_window_observations" in lineage_sql
    assert "telemetry.normalized_observations" in lineage_sql
    assert "ORDER BY o.id" in lineage_sql
    assert "LIMIT 5001" in lineage_sql
    assert "a.asset_id IS NOT DISTINCT FROM %s" in lineage_sql
