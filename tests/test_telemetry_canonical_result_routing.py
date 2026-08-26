from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import MappingProxyType, SimpleNamespace
from typing import Any

import pytest

from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.models.telemetry_api_models import (
    CanonicalAnalysisLineageResponse,
    CanonicalAnalysisResultResponse,
    CanonicalAnalysisResultsListResponse,
)
from app.services.telemetry_analysis_window import AnalysisWindowExecution
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_lineage import ObservationLineage, build_lineage_summary
from app.services.telemetry_result_artifact import build_canonical_result_artifact
from app.services.telemetry_result_service import (
    TelemetryCanonicalResultService,
    TelemetryCanonicalResultServiceError,
)


TENANT = "tenant-a"
FACILITY = "ws-facility-a"
CONNECTION_ID = "00000000-0000-4000-8000-000000000011"
SOURCE_RUN_ID = "00000000-0000-4000-8000-000000000012"
WINDOW_ID = "00000000-0000-5000-8000-000000000013"
SYSTEM_ID = "system-a"
ASSET_ID = "asset-a"
AUTHORITY_DIGEST = "b" * 64


def _scope(tenant: str = TENANT, facility: str = FACILITY) -> TelemetryScopeRef:
    return TelemetryScopeRef(
        tenant_scope_id=tenant,
        workspace_id=facility,
        resource_scope_id=canonical_phase4_resource_scope_id(tenant, facility),
        facility_id=facility,
    )


def _lineage(index: int, observed_at: datetime) -> ObservationLineage:
    return ObservationLineage(
        observation_id=f"00000000-0000-4000-8000-{index + 20:012d}",
        connection_id=CONNECTION_ID,
        ingestion_run_id=SOURCE_RUN_ID,
        external_signal_id=f"00000000-0000-4000-8000-{index + 30:012d}",
        mapping_id=f"00000000-0000-4000-8000-{index + 40:012d}",
        mapping_revision=1,
        canonical_signal_id=f"00000000-0000-4000-8000-{index + 50:012d}",
        canonical_signal_name=f"signal-{index}",
        system_id=SYSTEM_ID,
        asset_id=ASSET_ID,
        external_tag_id=f"tag-{index}",
        source_timestamp_raw=observed_at.isoformat(),
        source_timezone="UTC",
        source_offset="+00:00",
        timestamp_normalization_version="timestamps.v1",
        observed_at_utc=observed_at,
        original_unit="kW",
        canonical_unit="kW",
        conversion_id="kw_to_kw",
        conversion_version="units.v1",
        source_record_digest=f"{index + 1:064x}",
        mapping_authority_digest=AUTHORITY_DIGEST,
    )


def _fixture(state: str = "stable") -> tuple[
    AnalysisWindowExecution, Any, list[ObservationLineage]
]:
    started = datetime(2026, 8, 26, tzinfo=UTC)
    lineage = [_lineage(0, started), _lineage(1, started + timedelta(minutes=1))]
    lineage_summary = {
        **build_lineage_summary(lineage),
        "window_id": WINDOW_ID,
        "source_kind": "connector",
        "source_run_id": SOURCE_RUN_ID,
    }
    conditions = (
        []
        if state == "stable"
        else [
            {
                "id": "finding-insufficient-1",
                "status": "insufficient",
                "title": "Evidence is limited",
                "limitations": ["Window coverage is limited."],
            }
        ]
    )
    analysis_result = {
        "schema_version": "analysis-result-v1",
        "status": "complete",
        "analysis_id": WINDOW_ID,
        "upload_id": "",
        "source_file": "",
        "generated_at": started.isoformat(),
        "systems": [{"id": SYSTEM_ID, "name": "System A"}],
        "conditions": conditions,
        "insights": [],
        "relationships": [],
        "recommendations": [],
        "warnings": [],
        "errors": [],
        "evidence_index": {},
        "data_quality": {"coverage": 1.0},
        "sii_evidence": {"status": state},
        "telemetry_lineage": lineage_summary,
        "analysis_metadata": {
            "contract_version": "analysis-result-v1",
            "run_id": SOURCE_RUN_ID,
        },
        "normalized_telemetry": {
            "record_count": 2,
            "records": [
                {"tag": "power", "value": 10.0},
                {"tag": "power", "value": 11.0},
            ],
            "signals": [{"name": "power", "unit": "kW"}],
        },
    }
    execution = AnalysisWindowExecution(
        window_id=WINDOW_ID,
        source_kind="connector",
        source_run_id=SOURCE_RUN_ID,
        sii_result=MappingProxyType(
            {
                "status": state,
                "engine": {"name": "sii", "version": "test"},
                "temporal_analysis": {"status": state, "sample_count": 2},
            }
        ),
        analysis_result=MappingProxyType(analysis_result),
        telemetry_lineage=MappingProxyType(lineage_summary),
    )
    return execution, build_canonical_result_artifact(execution), lineage


class _DurableRepository:
    def __init__(self, state: str = "stable") -> None:
        execution, artifact, lineage = _fixture(state)
        self.execution = execution
        self.artifact = artifact
        self.lineage = lineage
        self.scope = _scope()
        self.reads = 0
        self.metadata_reads = 0
        self.full_lineage_reads = 0
        started = datetime(2026, 8, 26, tzinfo=UTC)
        self.row = {
            "id": artifact.result_id,
            "tenant_scope_id": self.scope.tenant_scope_id,
            "workspace_id": self.scope.workspace_id,
            "resource_scope_id": self.scope.resource_scope_id,
            "facility_id": self.scope.facility_id,
            "analysis_window_id": WINDOW_ID,
            "connection_id": CONNECTION_ID,
            "source_ingestion_run_id": SOURCE_RUN_ID,
            "system_id": SYSTEM_ID,
            "asset_id": ASSET_ID,
            "window_start": started,
            "window_end": started + timedelta(minutes=2),
            "authority_digest": AUTHORITY_DIGEST,
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
            "created_at": started,
            "result_metadata": {"status": state},
        }

    def _authorized(self, scope) -> bool:
        return scope.resource_scope_id == self.scope.resource_scope_id

    def get_ingestion_run(self, scope, *, run_id):
        if not self._authorized(scope) or run_id != SOURCE_RUN_ID:
            return None
        return {"id": SOURCE_RUN_ID, "connection_id": CONNECTION_ID}

    def list_analysis_result_artifacts(
        self, scope, *, connection_id, source_run_id, limit
    ):
        if (
            not self._authorized(scope)
            or connection_id != CONNECTION_ID
            or source_run_id != SOURCE_RUN_ID
        ):
            return []
        summary = deepcopy(self.row)
        summary.pop("payload")
        return [summary][:limit]

    def get_analysis_result_artifact(self, scope, **identity):
        self.reads += 1
        if not self._authorized(scope):
            return None
        expected = {
            "connection_id": CONNECTION_ID,
            "source_run_id": SOURCE_RUN_ID,
            "system_id": SYSTEM_ID,
            "asset_id": ASSET_ID,
            "result_id": self.artifact.result_id,
        }
        return deepcopy(self.row) if identity == expected else None

    def get_analysis_result_artifact_metadata(self, scope, **identity):
        self.metadata_reads += 1
        row = self.get_analysis_result_artifact(scope, **identity)
        if row is None:
            return None
        self.reads -= 1
        row.pop("payload")
        return row

    def list_analysis_result_lineage_records(self, scope, **identity):
        self.full_lineage_reads += 1
        if not self._authorized(scope):
            return []
        records = []
        for item in self.lineage:
            record = item.as_dict()
            record["observed_at_utc"] = item.observed_at_utc
            records.append(record)
        return records


def _service(repository: _DurableRepository) -> TelemetryCanonicalResultService:
    runtime = SimpleNamespace(repository=repository)
    runtime.require_available = lambda: runtime
    return TelemetryCanonicalResultService(runtime)


@pytest.mark.parametrize("state", ["stable", "insufficient"])
def test_restart_retrieval_uses_only_durable_artifact_for_all_terminal_states(
    state: str,
) -> None:
    repository = _DurableRepository(state)
    persisted_result_id = repository.artifact.result_id
    persisted_digest = repository.artifact.payload_digest
    del repository.execution

    restarted_service = _service(repository)
    listed = restarted_service.list_results(
        _scope(),
        connection_id=CONNECTION_ID,
        source_run_id=SOURCE_RUN_ID,
    )
    retrieved = restarted_service.get_result(
        _scope(),
        connection_id=CONNECTION_ID,
        source_run_id=SOURCE_RUN_ID,
        system_id=SYSTEM_ID,
        asset_id=ASSET_ID,
        result_id=persisted_result_id,
    )

    assert listed[0]["result_id"] == persisted_result_id
    CanonicalAnalysisResultsListResponse.model_validate({"results": listed})
    CanonicalAnalysisResultResponse.model_validate(retrieved)
    assert retrieved["result_id"] == persisted_result_id
    assert retrieved["payload_digest"] == persisted_digest
    assert retrieved["lineage_verified"] is True
    assert retrieved["product_result"]["result_id"] == persisted_result_id
    assert retrieved["product_result"]["analysis_result"]["conditions"] == (
        []
        if state == "stable"
        else [
            {
                "id": "finding-insufficient-1",
                "status": "insufficient",
                "title": "Evidence is limited",
                "limitations": ["Window coverage is limited."],
            }
        ]
    )
    assert "records" not in retrieved["product_result"]["analysis_result"][
        "normalized_telemetry"
    ]
    assert retrieved["product_result"]["sii_result"]["temporal_analysis"][
        "sample_count"
    ] == 2


def test_tenant_system_asset_and_result_mismatches_all_fail_closed() -> None:
    repository = _DurableRepository()
    service = _service(repository)
    base = {
        "connection_id": CONNECTION_ID,
        "source_run_id": SOURCE_RUN_ID,
        "system_id": SYSTEM_ID,
        "asset_id": ASSET_ID,
        "result_id": repository.artifact.result_id,
    }

    cases = [
        (_scope("tenant-b", "ws-facility-b"), base),
        (_scope(), {**base, "system_id": "wrong-system"}),
        (_scope(), {**base, "asset_id": "wrong-asset"}),
        (
            _scope(),
            {**base, "result_id": "00000000-0000-5000-8000-000000000099"},
        ),
    ]
    for scope, identity in cases:
        with pytest.raises(
            TelemetryCanonicalResultServiceError,
            match="Analysis result not found",
        ) as raised:
            service.get_result(scope, **identity)
        assert raised.value.status_code == 404


def test_verified_lineage_is_exact_and_paginated_without_artifact_access() -> None:
    repository = _DurableRepository()
    service = _service(repository)
    identity = {
        "connection_id": CONNECTION_ID,
        "source_run_id": SOURCE_RUN_ID,
        "system_id": SYSTEM_ID,
        "asset_id": ASSET_ID,
        "result_id": repository.artifact.result_id,
    }

    first = service.get_lineage_page(_scope(), **identity, limit=1, cursor=None)
    artifact_reads_after_first = repository.reads
    second = service.get_lineage_page(
        _scope(), **identity, limit=1, cursor=first["next_cursor"]
    )

    assert first["lineage_verified"] is second["lineage_verified"] is True
    assert first["observation_lineage_digest"] == repository.artifact.observation_lineage_digest
    assert [*first["records"], *second["records"]] == [
        item.as_dict() for item in repository.lineage
    ]
    assert second["next_cursor"] is None
    assert repository.reads == artifact_reads_after_first == 0
    assert repository.metadata_reads == 2
    assert repository.full_lineage_reads == 2
    CanonicalAnalysisLineageResponse.model_validate(first)
    CanonicalAnalysisLineageResponse.model_validate(second)
