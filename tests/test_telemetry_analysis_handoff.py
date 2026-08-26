from __future__ import annotations

from datetime import UTC, datetime, timedelta
import inspect
from types import SimpleNamespace

import pytest

from app.engine.sii.behavioral_model_contract import AuthenticatedPhase4Scope
from app.services import telemetry_analysis_window as analysis_window
from app.services.phase4_scope import (
    ServerBoundSystemIdentity,
    ServerBoundSystemIdentityV2,
)
from app.services.telemetry_lineage import ObservationLineage


DIGEST = "a" * 64
SIGNAL = "9fa5d454-6b13-5f59-99d1-7f6fb0a3e07f"


def _scope() -> AuthenticatedPhase4Scope:
    return AuthenticatedPhase4Scope(tenant_scope_id="tenant-a", workspace_id="ws-facility-a")


def _identity(scope: AuthenticatedPhase4Scope | None = None) -> ServerBoundSystemIdentityV2:
    scope = scope or _scope()
    return ServerBoundSystemIdentityV2(
        system_id="system-a",
        resource_scope_id=scope.resource_scope_id,
        authority_record_digest=DIGEST,
    )


def _lineage(index: int, timestamp: datetime, *, signal_id: str = SIGNAL) -> ObservationLineage:
    return ObservationLineage(
        observation_id=f"observation-{index}",
        connection_id="connection-a",
        ingestion_run_id="run-a",
        external_signal_id=f"external-signal-{index}",
        mapping_id="mapping-a",
        mapping_revision=2,
        canonical_signal_id=signal_id,
        canonical_signal_name="pressure",
        system_id="system-a",
        asset_id="asset-a",
        external_tag_id="vendor.pressure",
        source_timestamp_raw=timestamp.isoformat(),
        source_timezone="UTC",
        source_offset="+00:00",
        timestamp_normalization_version="timestamp-normalization.v1",
        observed_at_utc=timestamp,
        original_unit="psi",
        canonical_unit="kPa",
        conversion_id="pressure:psi-to-kpa",
        conversion_version="unit-normalization.v1",
        source_record_digest=f"{index + 1:064x}",
        mapping_authority_digest=DIGEST,
    )


def _window() -> analysis_window.CanonicalAnalysisWindow:
    scope = _scope()
    start = datetime(2026, 8, 25, tzinfo=UTC)
    rows = (
        {"observed_at_utc": start.isoformat(), SIGNAL: 100.0},
        {"observed_at_utc": (start + timedelta(minutes=1)).isoformat(), SIGNAL: 101.0},
    )
    return analysis_window.CanonicalAnalysisWindow(
        window_id="window-a",
        source_kind="telemetry_connector",
        source_run_id="run-a",
        phase4_scope=scope,
        phase4_system_identity=_identity(scope),
        asset_id="asset-a",
        columns=("observed_at_utc", SIGNAL),
        rows=rows,
        numeric_profiles=(
            {
                "column": SIGNAL,
                "count": 2,
                "missing_count": 0,
                "non_numeric_count": 0,
                "constant_or_stuck": False,
            },
        ),
        timestamp_column="observed_at_utc",
        numeric_columns=(SIGNAL,),
        telemetry_signal_catalog={
            SIGNAL: {
                "canonical_signal_id": SIGNAL,
                "canonical_signal_name": "pressure",
                "display_name": "Pressure",
                "canonical_unit": "kPa",
                "engineering_units": "kPa",
                "column": SIGNAL,
            }
        },
        ingestion_report={},
        normalization_report={},
        data_quality={"status": "ready", "readiness": "ready"},
        sensor_health={},
        operating_mode={},
        observation_lineage=(_lineage(0, start), _lineage(1, start + timedelta(minutes=1))),
    )


def _resolved(identity: ServerBoundSystemIdentityV2):
    return SimpleNamespace(available=True, identity=identity, reason="resolved")


def test_analysis_window_calls_sii_once_with_only_server_identity(monkeypatch) -> None:
    window = _window()
    calls = []

    def evaluator(**kwargs):
        calls.append(kwargs)
        return {"status": "limited", "compatibility": {}, "processing_trace": {}}

    execution = analysis_window.run_analysis_window(window, evaluator=evaluator)

    assert len(calls) == 1
    assert calls[0]["phase4_scope"] == window.phase4_scope
    assert calls[0]["config"]["infrastructure_identity"] == {
        "tenant_id": "tenant-a",
        "workspace_id": "ws-facility-a",
        "resource_scope_id": window.phase4_scope.resource_scope_id,
        "facility_id": "ws-facility-a",
        "system_id": "system-a",
        "asset_id": "asset-a",
    }
    assert execution.analysis_result["upload_id"] == ""
    assert execution.analysis_result["source_file"] == ""
    assert execution.analysis_result["analysis_metadata"]["generated_from"] == "canonical_normalized_observations"
    assert execution.analysis_result["telemetry_lineage"]["lineage_digest"]


def test_analysis_window_does_not_retry_engine_errors(monkeypatch) -> None:
    window = _window()
    calls = 0

    def evaluator(**kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("provider details must not escape")

    with pytest.raises(
        analysis_window.AnalysisWindowExecutionError,
        match="telemetry_analysis_engine_execution_failed",
    ):
        analysis_window.run_analysis_window(window, evaluator=evaluator)
    assert calls == 1


def test_mismatched_shared_authority_snapshot_prevents_window_construction() -> None:
    scope = _scope()
    start = datetime(2026, 8, 25, tzinfo=UTC)
    with pytest.raises(
        analysis_window.AnalysisWindowValidationError,
        match="shared_authority_snapshot_mismatch",
    ):
        analysis_window.build_canonical_analysis_window(
            window_id="window-stale",
            source_run_id="run-a",
            scope=scope,
            system_id="system-a",
            asset_id="asset-a",
            persisted_authority_digest="b" * 64,
            phase4_system_identity=_identity(scope),
            observations=[
                _observation(0, SIGNAL, start, 1.0),
                _observation(1, SIGNAL, start + timedelta(minutes=1), 2.0),
            ],
        )


def test_v1_upload_identity_is_rejected_before_analysis() -> None:
    scope = _scope()
    v1 = ServerBoundSystemIdentity(
        system_id="system-a",
        dataset_scope_storage_id="upload-storage-a",
        authority_record_digest=DIGEST,
    )
    template = _window()
    with pytest.raises(
        analysis_window.AnalysisWindowValidationError,
        match="system_identity_v2_required",
    ):
        analysis_window.CanonicalAnalysisWindow(
            window_id=template.window_id,
            source_kind=template.source_kind,
            source_run_id=template.source_run_id,
            phase4_scope=scope,
            phase4_system_identity=v1,  # type: ignore[arg-type]
            asset_id=template.asset_id,
            columns=template.columns,
            rows=template.rows,
            numeric_profiles=template.numeric_profiles,
            timestamp_column=template.timestamp_column,
            numeric_columns=template.numeric_columns,
            telemetry_signal_catalog=template.telemetry_signal_catalog,
            ingestion_report={},
            normalization_report={},
            data_quality={},
            sensor_health={},
            operating_mode={},
            observation_lineage=template.observation_lineage,
        )


def _observation(index: int, signal_id: str, timestamp: datetime, value: float) -> dict:
    return {
        **_lineage(index, timestamp, signal_id=signal_id).as_dict(),
        "id": f"observation-{index}",
        "canonical_concept_id": signal_id,
        "observed_at_utc": timestamp,
        "normalized_value": value,
        "quality_state": "good",
        "analysis_eligible": True,
    }


def test_canonical_pivot_rejects_duplicates_and_enforces_coverage(monkeypatch) -> None:
    scope = _scope()
    identity = _identity(scope)
    start = datetime(2026, 8, 25, tzinfo=UTC)
    duplicate = [
        _observation(0, SIGNAL, start, 1.0),
        _observation(1, SIGNAL, start, 2.0),
    ]
    with pytest.raises(analysis_window.AnalysisWindowValidationError, match="pivot_duplicate"):
        analysis_window.build_canonical_analysis_window(
            window_id="window-duplicate",
            source_run_id="run-a",
            scope=scope,
            system_id="system-a",
            asset_id="asset-a",
            persisted_authority_digest=DIGEST,
            phase4_system_identity=identity,
            observations=duplicate,
        )

    sparse_signal = "4385267d-f840-59c4-ba65-06a6726e3189"
    observations = [
        _observation(index, SIGNAL, start + timedelta(minutes=index), float(index))
        for index in range(4)
    ]
    observations.append(_observation(10, sparse_signal, start, 20.0))
    window = analysis_window.build_canonical_analysis_window(
        window_id="window-coverage",
        source_run_id="run-a",
        scope=scope,
        system_id="system-a",
        asset_id="asset-a",
        persisted_authority_digest=DIGEST,
        phase4_system_identity=identity,
        observations=observations,
        minimum_signal_observations=2,
        minimum_signal_coverage=0.75,
    )
    assert window.numeric_columns == (SIGNAL,)
    assert all(item.canonical_signal_id == SIGNAL for item in window.observation_lineage)


def test_source_payload_cannot_override_authoritative_identity(monkeypatch) -> None:
    scope = _scope()
    identity = _identity(scope)
    start = datetime(2026, 8, 25, tzinfo=UTC)
    window = analysis_window.build_canonical_analysis_window(
        window_id="window-source-authority",
        source_run_id="run-a",
        scope=scope,
        system_id="system-a",
        asset_id="asset-a",
        persisted_authority_digest=DIGEST,
        phase4_system_identity=identity,
        observations=[
            _observation(0, SIGNAL, start, 1.0),
            _observation(1, SIGNAL, start + timedelta(minutes=1), 2.0),
        ],
        ingestion_report={
            "tenant_id": "attacker",
            "workspace_id": "ws-attacker",
            "system_id": "attacker-system",
            "provider_page_count": 1,
        },
    )
    captured = {}

    def evaluator(**kwargs):
        captured.update(kwargs["config"])
        return {"status": "limited", "compatibility": {}, "processing_trace": {}}

    analysis_window.run_analysis_window(window, evaluator=evaluator)
    assert captured["ingestion_report"] == {"provider_page_count": 1}
    assert captured["infrastructure_identity"]["system_id"] == "system-a"


def test_handoff_module_has_no_upload_parser_dependency() -> None:
    source = inspect.getsource(analysis_window)
    assert "app.services.upload_jobs" not in source
    assert "process_csv_content" not in source
