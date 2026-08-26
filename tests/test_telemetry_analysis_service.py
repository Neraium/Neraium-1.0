from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services import telemetry_analysis_window
from app.services.phase4_scope import ServerBoundSystemIdentityV2
from app.services.telemetry_analysis_service import (
    deterministic_analysis_window_id,
    process_ingestion_run,
    run_post_ingestion_analysis,
)
from app.services.telemetry_domain import TelemetryScopeRef


DIGEST = "a" * 64
SIGNAL_ID = "9fa5d454-6b13-5f59-99d1-7f6fb0a3e07f"


def _scope() -> TelemetryScopeRef:
    from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id

    return TelemetryScopeRef(
        tenant_scope_id="tenant-a",
        workspace_id="ws-facility-a",
        resource_scope_id=canonical_phase4_resource_scope_id(
            "tenant-a", "ws-facility-a"
        ),
        facility_id="ws-facility-a",
    )


def _observation(
    index: int,
    timestamp: datetime,
    *,
    system_id: str = "system-a",
    asset_id: str | None = "asset-a",
    digest: str = DIGEST,
    run_id: str = "run-a",
) -> dict:
    return {
        "id": f"observation-{system_id}-{index}",
        "connection_id": "connection-a",
        "ingestion_run_id": run_id,
        "external_signal_id": f"external-{system_id}",
        "mapping_id": f"mapping-{system_id}",
        "mapping_revision": 2,
        "canonical_concept_id": SIGNAL_ID,
        "canonical_signal_name": "pressure",
        "system_id": system_id,
        "asset_id": asset_id,
        "external_tag_id": f"vendor.{system_id}.pressure",
        "source_timestamp_raw": timestamp.isoformat(),
        "source_timezone": "UTC",
        "source_offset": "+00:00",
        "timestamp_normalization_version": "timestamp-normalization.v1",
        "observed_at_utc": timestamp,
        "original_unit": "psi",
        "normalized_value": 100.0 + index,
        "canonical_unit": "kPa",
        "conversion_id": "pressure:psi-to-kpa",
        "conversion_version": "unit-normalization.v1",
        "quality_state": "good",
        "ingestion_disposition": "accepted",
        "analysis_eligible": True,
        "source_record_digest": f"{index + 1:064x}",
        "mapping_authority_digest": digest,
    }


class FakeAnalysisRepository:
    def __init__(self, observations: list[dict], *, authority_available: bool = True) -> None:
        self.observations = observations
        self.authority_available = authority_available
        self.windows: dict[str, dict] = {}
        self.query_calls: list[dict] = []
        self.transitions: list[tuple[str, str]] = []

    def resolve_analysis_authority_snapshot(
        self, scope, *, system_id, asset_id, authority_digest
    ):
        if not self.authority_available:
            return None
        return ServerBoundSystemIdentityV2(
            system_id=system_id,
            resource_scope_id=scope.resource_scope_id,
            authority_record_digest=authority_digest,
        )

    def get_analysis_window(self, scope, *, window_id):
        return self.windows.get(window_id)

    def list_analysis_eligible_observations(self, scope, **kwargs):
        self.query_calls.append(kwargs)
        selected = list(self.observations)
        if kwargs.get("source_run_id") is not None:
            selected = [
                item
                for item in selected
                if item["ingestion_run_id"] == kwargs["source_run_id"]
            ]
        if kwargs.get("system_id") is not None:
            selected = [
                item for item in selected if item["system_id"] == kwargs["system_id"]
            ]
        if "asset_id" in kwargs and kwargs.get("system_id") is not None:
            selected = [
                item for item in selected if item.get("asset_id") == kwargs["asset_id"]
            ]
        if kwargs.get("authority_digest") is not None:
            selected = [
                item
                for item in selected
                if item.get("mapping_authority_digest") == kwargs["authority_digest"]
            ]
        if kwargs.get("window_start") is not None:
            selected = [
                item
                for item in selected
                if item["observed_at_utc"] >= kwargs["window_start"]
            ]
        if kwargs.get("window_end") is not None:
            selected = [
                item
                for item in selected
                if item["observed_at_utc"] < kwargs["window_end"]
            ]
        return selected

    def persist_analysis_window(
        self, scope, *, window_record, observation_links
    ):
        existing = self.windows.get(window_record["id"])
        if existing is not None:
            return existing
        stored = {**dict(window_record), "status": window_record["status"]}
        stored["observation_links"] = [dict(item) for item in observation_links]
        self.windows[window_record["id"]] = stored
        return stored

    def update_analysis_window_status(
        self,
        scope,
        *,
        window_id,
        expected_status,
        target_status,
        reason_code=None,
    ):
        record = self.windows[window_id]
        assert record["status"] == expected_status
        record["status"] = target_status
        if reason_code is not None:
            record.setdefault("quality_summary", {})[
                "status_reason_code"
            ] = reason_code
        self.transitions.append((expected_status, target_status))
        return record

    def claim_analysis_window_execution(
        self, scope, *, window_id, claim_token, claimed_at, claim_expires_at
    ):
        record = self.windows[window_id]
        assert record["status"] == "eligible"
        record.update(
            {
                "status": "running",
                "execution_claim_token": claim_token,
                "execution_claim_expires_at": claim_expires_at,
                "execution_attempt_count": int(record.get("execution_attempt_count") or 0) + 1,
            }
        )
        self.transitions.append(("eligible", "running"))
        return record

    def recover_stale_analysis_window_execution(
        self, scope, *, window_id, recovered_at
    ):
        record = self.windows[window_id]
        expiry = record.get("execution_claim_expires_at")
        if record["status"] == "running" and (expiry is None or expiry <= recovered_at):
            record["status"] = "failed"
            record.setdefault("quality_summary", {})[
                "status_reason_code"
            ] = "telemetry_analysis_execution_claim_expired"
            return record
        return None

    def finish_analysis_window_execution(
        self,
        scope,
        *,
        window_id,
        claim_token,
        completed_at,
        target_status,
        reason_code=None,
        result_digest=None,
        result_metadata=None,
        evidence_lineage=None,
    ):
        record = self.windows[window_id]
        assert record["status"] == "running"
        assert record["execution_claim_token"] == claim_token
        record["status"] = target_status
        record["result_digest"] = result_digest
        record["result_metadata"] = dict(result_metadata or {})
        record["evidence_lineage"] = dict(evidence_lineage or {})
        if reason_code is not None:
            record.setdefault("quality_summary", {})["status_reason_code"] = reason_code
        self.transitions.append(("running", target_status))
        return record


def _engine(calls: list[dict]):
    def evaluate(**kwargs):
        calls.append(kwargs)
        return {
            "status": "limited",
            "compatibility": {},
            "processing_trace": {},
            "evidence_fusion": {
                "evidence_inventory": [{"evidence_id": "evidence-pressure-1"}]
            },
            "findings": [{"finding_id": "finding-pressure-1"}],
        }

    return evaluate


def test_operational_service_persists_lineage_and_calls_sii_once(monkeypatch) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    repository = FakeAnalysisRepository(
        [_observation(0, start), _observation(1, start + timedelta(minutes=1))]
    )
    calls: list[dict] = []

    result = run_post_ingestion_analysis(
        repository=repository,
        scope=_scope(),
        connection_id="connection-a",
        source_run_id="run-a",
        system_id="system-a",
        asset_id="asset-a",
        window_start=start,
        window_end=start + timedelta(minutes=2),
        persisted_authority_digest=DIGEST,
        evaluator=_engine(calls),
    )

    assert result.status == "completed"
    assert len(calls) == 1
    assert repository.query_calls[0]["asset_filter_applied"] is True
    assert repository.transitions == [
        ("eligible", "running"),
        ("running", "completed"),
    ]
    assert len(repository.windows[result.window_id]["observation_links"]) == 2
    assert repository.windows[result.window_id]["result_digest"]
    assert "evidence-pressure-1" in repository.windows[result.window_id][
        "evidence_lineage"
    ]["evidence_ids"]
    assert "finding-pressure-1" in repository.windows[result.window_id][
        "evidence_lineage"
    ]["finding_ids"]
    assert result.execution is not None
    assert result.execution.analysis_result["upload_id"] == ""


def test_completed_window_is_idempotent_without_second_sii_call(monkeypatch) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    observations = [_observation(0, start), _observation(1, start + timedelta(minutes=1))]
    repository = FakeAnalysisRepository(observations)
    calls: list[dict] = []
    arguments = {
        "repository": repository,
        "scope": _scope(),
        "connection_id": "connection-a",
        "source_run_id": "run-a",
        "system_id": "system-a",
        "asset_id": "asset-a",
        "window_start": start,
        "window_end": start + timedelta(minutes=2),
        "persisted_authority_digest": DIGEST,
        "evaluator": _engine(calls),
    }

    first = run_post_ingestion_analysis(**arguments)
    second = run_post_ingestion_analysis(**arguments)

    assert first.status == second.status == "completed"
    assert second.reused_existing is True
    assert len(calls) == 1


def test_stale_authority_persists_ineligible_without_sii(monkeypatch) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    repository = FakeAnalysisRepository(
        [_observation(0, start), _observation(1, start + timedelta(minutes=1))],
        authority_available=False,
    )
    calls: list[dict] = []

    result = run_post_ingestion_analysis(
        repository=repository,
        scope=_scope(),
        connection_id="connection-a",
        source_run_id="run-a",
        system_id="system-a",
        asset_id="asset-a",
        window_start=start,
        window_end=start + timedelta(minutes=2),
        persisted_authority_digest=DIGEST,
        evaluator=_engine(calls),
    )

    assert result.status == "ineligible"
    assert result.reason_code == "telemetry_analysis_shared_authority_snapshot_unavailable"
    assert calls == []
    assert repository.windows[result.window_id]["status"] == "ineligible"


def test_engine_failure_is_sanitized_and_does_not_escape_to_ingestion(monkeypatch) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    repository = FakeAnalysisRepository(
        [_observation(0, start), _observation(1, start + timedelta(minutes=1))]
    )
    calls = 0

    def fail(**kwargs):
        nonlocal calls
        calls += 1
        raise RuntimeError("vendor payload and credential-shaped detail")

    result = run_post_ingestion_analysis(
        repository=repository,
        scope=_scope(),
        connection_id="connection-a",
        source_run_id="run-a",
        system_id="system-a",
        asset_id="asset-a",
        window_start=start,
        window_end=start + timedelta(minutes=2),
        persisted_authority_digest=DIGEST,
        evaluator=fail,
    )

    assert result.status == "failed"
    assert result.reason_code == "telemetry_analysis_execution_failed"
    assert calls == 1
    assert repository.transitions[-1] == ("running", "failed")
    assert "vendor" not in repr(repository.windows[result.window_id])
    assert repository.windows[result.window_id]["quality_summary"][
        "status_reason_code"
    ] == "telemetry_analysis_execution_failed"


def test_process_ingestion_run_derives_and_handles_multiple_groups(monkeypatch) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    repository = FakeAnalysisRepository(
        [
            _observation(0, start),
            _observation(1, start + timedelta(minutes=1)),
            _observation(2, start, system_id="system-b", asset_id="asset-b"),
            _observation(
                3,
                start + timedelta(minutes=1),
                system_id="system-b",
                asset_id="asset-b",
            ),
        ]
    )
    calls: list[dict] = []

    result = process_ingestion_run(
        repository=repository,
        scope=_scope(),
        connection_id="connection-a",
        source_run_id="run-a",
        evaluator=_engine(calls),
    )

    assert result.status == "completed"
    assert len(result.windows) == 2
    assert len(calls) == 2
    assert repository.query_calls[0] == {
        "connection_id": "connection-a",
        "source_run_id": "run-a",
        "system_id": None,
        "asset_id": None,
        "asset_filter_applied": False,
        "window_start": None,
        "window_end": None,
        "authority_digest": None,
        "limit": 5_000,
    }
    assert {call["config"]["infrastructure_identity"]["system_id"] for call in calls} == {
        "system-a",
        "system-b",
    }


def test_process_run_keeps_system_level_and_asset_rows_in_distinct_windows(
    monkeypatch,
) -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    repository = FakeAnalysisRepository(
        [
            _observation(0, start, asset_id=None),
            _observation(1, start + timedelta(minutes=1), asset_id=None),
            _observation(2, start, asset_id="asset-a"),
            _observation(3, start + timedelta(minutes=1), asset_id="asset-a"),
        ]
    )
    calls: list[dict] = []

    result = process_ingestion_run(
        repository=repository,
        scope=_scope(),
        connection_id="connection-a",
        source_run_id="run-a",
        evaluator=_engine(calls),
    )

    assert result.status == "completed"
    assert len(result.windows) == 2
    assert {
        call["config"]["infrastructure_identity"]["asset_id"] for call in calls
    } == {None, "asset-a"}
    assert sorted(
        len(repository.windows[item.window_id]["observation_links"])
        for item in result.windows
    ) == [2, 2]


def test_window_identity_is_stable_and_scope_bound() -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    kwargs = {
        "scope": _scope(),
        "connection_id": "connection-a",
        "source_run_id": "run-a",
        "system_id": "system-a",
        "asset_id": "asset-a",
        "window_start": start,
        "window_end": start + timedelta(minutes=2),
        "authority_digest": DIGEST,
    }
    assert deterministic_analysis_window_id(**kwargs) == deterministic_analysis_window_id(
        **kwargs
    )


def test_run_selection_limit_fails_closed_without_partial_sii(monkeypatch) -> None:

    class OverflowRepository(FakeAnalysisRepository):
        def list_analysis_eligible_observations(self, scope, **kwargs):
            raise RuntimeError("telemetry_analysis_observation_limit_exceeded")

    calls: list[dict] = []
    result = process_ingestion_run(
        repository=OverflowRepository([]),
        scope=_scope(),
        connection_id="connection-a",
        source_run_id="run-a",
        evaluator=_engine(calls),
    )

    assert result.status == "ineligible"
    assert result.reason_code == "telemetry_analysis_observation_limit_exceeded"
    assert result.windows == ()
    assert calls == []


def test_cross_run_rolling_window_uses_trigger_and_prior_observations() -> None:
    trigger_at = datetime(2026, 8, 25, 12, tzinfo=UTC)
    repository = FakeAnalysisRepository(
        [
            _observation(0, trigger_at - timedelta(minutes=5), run_id="run-prior"),
            _observation(1, trigger_at, run_id="run-trigger"),
        ]
    )
    calls: list[dict] = []

    result = process_ingestion_run(
        repository=repository,
        scope=_scope(),
        connection_id="connection-a",
        source_run_id="run-trigger",
        evaluator=_engine(calls),
    )

    assert result.status == "completed"
    assert len(calls) == 1
    persisted = repository.windows[result.windows[0].window_id]
    assert {
        item["observation_id"] for item in persisted["observation_links"]
    } == {"observation-system-a-0", "observation-system-a-1"}
    assert persisted["evidence_lineage"]["contributing_ingestion_run_ids"] == [
        "run-prior",
        "run-trigger",
    ]
    assert repository.query_calls[1]["source_run_id"] is None


def test_expired_running_claim_fails_closed_without_second_sii_call() -> None:
    start = datetime(2026, 8, 25, tzinfo=UTC)
    repository = FakeAnalysisRepository(
        [_observation(0, start), _observation(1, start + timedelta(minutes=1))]
    )
    window_id = deterministic_analysis_window_id(
        scope=_scope(),
        connection_id="connection-a",
        source_run_id="run-a",
        system_id="system-a",
        asset_id="asset-a",
        window_start=start,
        window_end=start + timedelta(minutes=2),
        authority_digest=DIGEST,
    )
    repository.windows[window_id] = {
        "id": window_id,
        "status": "running",
        "execution_claim_token": "claim-a",
        "execution_claim_expires_at": start - timedelta(seconds=1),
        "execution_attempt_count": 1,
        "quality_summary": {},
    }
    calls: list[dict] = []

    result = run_post_ingestion_analysis(
        repository=repository,
        scope=_scope(),
        connection_id="connection-a",
        source_run_id="run-a",
        system_id="system-a",
        asset_id="asset-a",
        window_start=start,
        window_end=start + timedelta(minutes=2),
        persisted_authority_digest=DIGEST,
        evaluator=_engine(calls),
        clock=lambda: start,
    )

    assert result.status == "failed"
    assert result.reason_code == "telemetry_analysis_execution_claim_expired"
    assert result.reused_existing is True
    assert calls == []
    assert repository.windows[window_id]["execution_attempt_count"] == 1
