from __future__ import annotations

from datetime import UTC, datetime
import logging
import threading

from fastapi.testclient import TestClient
import pytest

from app.connectors.base import (
    ConnectorCheckpoint,
    ConnectorFailureKind,
    ConnectorPage,
    RawObservationEnvelope,
    TelemetryConnectorError,
)
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id
from app.core.config import Settings, validate_settings
from app.main import create_app
from app.services.telemetry_domain import TelemetryScopeRef
from app.services.telemetry_repository import TelemetryLeaseLost
from app.services.telemetry_scheduler import TelemetryScheduler
from app.services.telemetry_ingestion import prepare_connector_page
from app.services.telemetry_units import UNIT_NORMALIZATION_VERSION
from app.services import worker_heartbeat


NOW = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)


def _scope(tenant: str = "tenant-a", workspace: str = "facility-a") -> TelemetryScopeRef:
    return TelemetryScopeRef(
        tenant_scope_id=tenant,
        workspace_id=workspace,
        resource_scope_id=canonical_phase4_resource_scope_id(tenant, workspace),
        facility_id=workspace,
    )


class FakeProvider:
    def __init__(self, page: ConnectorPage | None = None, error: Exception | None = None):
        self.page = page or ConnectorPage()
        self.error = error
        self.contexts = []
        self.backfills = []

    def fetch_incremental(self, context, *, checkpoint=None):
        self.contexts.append((context, checkpoint))
        if self.error:
            raise self.error
        return self.page

    def fetch_backfill(self, context, *, time_range, checkpoint=None):
        self.backfills.append((context, time_range, checkpoint))
        if self.error:
            raise self.error
        return self.page


class FakeProviders:
    def __init__(self, provider: FakeProvider):
        self.provider = provider
        self.requests = []

    def get(self, connector_type, *, configuration=None):
        self.requests.append((connector_type, configuration))
        return self.provider


class FakeRepository:
    def __init__(self, *, snapshot=None, claims=None):
        scope = _scope()
        self.claims = list(claims or [_claim(scope)])
        self.snapshot = snapshot or _snapshot(scope)
        self.persisted = []
        self.completed = []
        self.continued = []
        self.renewals = []
        self.failures = []
        self.claim_calls = []
        self.raise_on_persist = None

    def claim_next_due_work(self, **kwargs):
        self.claim_calls.append(kwargs)
        return self.claims.pop(0) if self.claims else None

    def load_ingestion_snapshot(self, scope, **kwargs):
        return self.snapshot

    def persist_ingestion_page(self, scope, **kwargs):
        if self.raise_on_persist:
            raise self.raise_on_persist
        self.persisted.append((scope, kwargs))
        return {"checkpoint_revision": kwargs["expected_checkpoint_revision"] + 1}

    def complete_ingestion_work(self, scope, **kwargs):
        self.completed.append((scope, kwargs))
        return {}

    def continue_ingestion_work(self, scope, **kwargs):
        self.continued.append((scope, kwargs))
        return {}

    def renew_lease(self, scope, **kwargs):
        self.renewals.append((scope, kwargs))
        return True

    def record_ingestion_failure(self, scope, **kwargs):
        self.failures.append((scope, kwargs))
        return {"status": "pending" if kwargs.get("retryable") else "failed"}


def _claim(scope: TelemetryScopeRef, **overrides):
    value = {
        "scope": scope,
        "connection_id": "connection-a",
        "run_id": "run-a",
        "lease_token": "lease-a",
        "run_mode": "incremental",
        "checkpoint_mode": "incremental",
    }
    value.update(overrides)
    return value


def _snapshot(scope: TelemetryScopeRef, **connection_overrides):
    connection = {
        "id": "connection-a",
        "tenant_scope_id": scope.tenant_scope_id,
        "workspace_id": scope.workspace_id,
        "resource_scope_id": scope.resource_scope_id,
        "facility_id": scope.facility_id,
        "connector_type": "https_telemetry",
        "safe_config": {"base_url": "https://telemetry.example.test"},
        "polling_interval_seconds": 60,
        "enabled": True,
    }
    connection.update(connection_overrides)
    return {
        "scope": scope,
        "connection": connection,
        "secret_binding": None,
        "mappings": [],
        "checkpoint": {"revision": 2, "cursor_payload": {"cursor": "old"}},
    }


def _normalized(**overrides):
    value = {
        "observations": (),
        "rejections": (),
        "next_checkpoint": ConnectorCheckpoint(cursor="next"),
        "received_count": 0,
        "high_watermark_utc": NOW,
        "has_more": False,
    }
    value.update(overrides)
    return value


def _scheduler(
    repository,
    provider=None,
    *,
    normalize_page=None,
    analyze_run=None,
    heartbeat=None,
    now=None,
    lease_heartbeat_interval_seconds=None,
):
    return TelemetryScheduler(
        repository=repository,
        providers=FakeProviders(provider or FakeProvider()),
        normalize_page=normalize_page or (lambda **kwargs: _normalized()),
        analyze_run=analyze_run,
        worker_id="worker-a",
        now=now or (lambda: NOW),
        jitter=lambda: 0.5,
        heartbeat=heartbeat or (lambda **kwargs: True),
        lease_heartbeat_interval_seconds=lease_heartbeat_interval_seconds,
    )


def test_claims_normalizes_and_atomically_persists_one_page_checkpoint() -> None:
    repository = FakeRepository()
    provider = FakeProvider(ConnectorPage(next_checkpoint=ConnectorCheckpoint(cursor="next")))
    normalizer_calls = []
    scheduler = _scheduler(
        repository,
        provider,
        normalize_page=lambda **kwargs: normalizer_calls.append(kwargs) or _normalized(),
    )

    result = scheduler.run_once()

    assert result.outcome == "processed"
    assert repository.claim_calls[0]["worker_id"] == "worker-a"
    assert len(provider.contexts) == 1
    context, checkpoint = provider.contexts[0]
    assert context.resource_scope_id == _scope().resource_scope_id
    assert dict(context.configuration) == {"base_url": "https://telemetry.example.test"}
    assert checkpoint.cursor == "old"
    assert normalizer_calls[0]["scope"] == _scope()
    persisted = repository.persisted[0][1]
    assert persisted["expected_checkpoint_revision"] == 2
    assert persisted["cursor_payload"] == {"cursor": "next"}
    assert persisted["high_water_at"] == NOW
    assert len(persisted["checkpoint_before_digest"]) == 64
    assert len(persisted["checkpoint_after_digest"]) == 64
    assert persisted["checkpoint_before_digest"] != persisted["checkpoint_after_digest"]
    assert len(repository.completed) == 1


def test_final_normalizer_records_are_serialized_for_repository_contract() -> None:
    scope = _scope()
    connection_id = "00000000-0000-0000-0000-000000000001"
    run_id = "00000000-0000-0000-0000-000000000002"
    snapshot = _snapshot(scope)
    snapshot["connection"]["id"] = connection_id
    snapshot["mappings"] = [
        {
            "external_tag_id": "AHU-1.SAT",
            "external_signal_id": "00000000-0000-0000-0000-000000000101",
            "mapping_id": "00000000-0000-0000-0000-000000000201",
            "revision": 1,
            "mapped_by": "operator@example.test",
            "mapped_at": NOW,
            "authority_digest": "a" * 64,
            "system_id": "ahu-1",
            "asset_id": "sat-1",
            "canonical_concept_id": "00000000-0000-0000-0000-000000000301",
            "canonical_signal_name": "supply_air_temperature",
            "source_unit": "degF",
            "canonical_unit": "degC",
            "expected_dimension": "temperature",
            "conversion_id": "f_to_c",
            "conversion_version": UNIT_NORMALIZATION_VERSION,
            "source_timezone": "UTC",
            "provenance": "manual",
        }
    ]
    repository = FakeRepository(
        snapshot=snapshot,
        claims=[
            _claim(scope, connection_id=connection_id, run_id=run_id)
        ],
    )
    provider = FakeProvider(
        ConnectorPage(
            observations=(
                RawObservationEnvelope(
                    external_tag_id="AHU-1.SAT",
                    external_tag_name="Supply air temperature",
                    source_timestamp=NOW,
                    raw_value=77,
                    reported_unit="degF",
                    reported_quality="good",
                ),
            )
        )
    )

    result = _scheduler(
        repository,
        provider,
        normalize_page=prepare_connector_page,
    ).run_once()

    assert result.outcome == "processed"
    observation = repository.persisted[0][1]["observations"][0]
    assert observation["canonical_concept_id"].endswith("0301")
    assert observation["ingestion_disposition"] == "accepted"
    assert observation["quality_state"] == "good"
    assert "scope" not in observation


def test_expired_work_can_be_reclaimed_after_restart_without_overlap() -> None:
    scope = _scope()
    repository = FakeRepository(claims=[_claim(scope), None])
    first = _scheduler(repository)
    second = _scheduler(repository)

    assert first.run_once().outcome == "processed"
    assert second.run_once().outcome == "idle"
    assert len(repository.persisted) == 1


def test_has_more_requeues_same_run_and_only_final_page_completes() -> None:
    scope = _scope()
    claim = _claim(scope)
    repository = FakeRepository(claims=[claim, dict(claim)])
    provider = FakeProvider(
        ConnectorPage(
            next_checkpoint=ConnectorCheckpoint(cursor="page-2"),
            has_more=True,
        )
    )
    scheduler = _scheduler(
        repository,
        provider,
        normalize_page=lambda **kwargs: _normalized(
            next_checkpoint=kwargs["page"].next_checkpoint,
            has_more=kwargs["page"].has_more,
        ),
    )

    first = scheduler.run_once()

    assert first.outcome == "continued"
    assert repository.completed == []
    assert repository.continued[0][1]["run_id"] == "run-a"
    assert repository.continued[0][1]["next_attempt_at"] == NOW

    repository.snapshot["checkpoint"] = {
        "revision": 3,
        "cursor_payload": {"cursor": "page-2"},
        "high_water_at": NOW,
    }
    provider.page = ConnectorPage(has_more=False)
    second = scheduler.run_once()

    assert second.outcome == "processed"
    assert len(repository.completed) == 1
    assert repository.completed[0][1]["run_id"] == "run-a"


def test_has_more_without_checkpoint_progress_fails_permanently() -> None:
    repository = FakeRepository()
    provider = FakeProvider(
        ConnectorPage(
            next_checkpoint=ConnectorCheckpoint(cursor="old"),
            has_more=True,
        )
    )

    result = _scheduler(
        repository,
        provider,
        normalize_page=lambda **kwargs: _normalized(
            next_checkpoint=kwargs["page"].next_checkpoint,
            has_more=True,
        ),
    ).run_once()

    assert result.outcome == "failed"
    assert result.error_code == "telemetry_continuation_checkpoint_invalid"
    assert repository.persisted == []
    assert repository.continued == []
    assert repository.failures[0][1]["retryable"] is False


def test_final_page_invokes_analysis_once_before_ingestion_completion() -> None:
    repository = FakeRepository()
    calls = []

    def analyze_run(**kwargs):
        assert len(repository.persisted) == 1
        assert repository.completed == []
        calls.append(kwargs)
        return {"status": "completed"}

    result = _scheduler(repository, analyze_run=analyze_run).run_once()

    assert result.outcome == "processed"
    assert result.analysis_status == "completed"
    assert len(calls) == 1
    assert calls[0]["repository"] is repository
    assert calls[0]["scope"] == _scope()
    assert calls[0]["connection_id"] == "connection-a"
    assert calls[0]["source_run_id"] == "run-a"
    assert len(repository.completed) == 1


def test_final_page_renews_lease_and_schedules_from_post_analysis_clock() -> None:
    repository = FakeRepository()
    events = []
    clock = iter(
        (
            NOW,
            NOW.replace(second=10),
            NOW.replace(minute=5),
        )
    )
    original_renew = repository.renew_lease
    original_complete = repository.complete_ingestion_work

    def renew(scope, **kwargs):
        events.append(("renew", kwargs["now"]))
        return original_renew(scope, **kwargs)

    def analyze(**kwargs):
        events.append(("analyze", kwargs["source_run_id"]))
        return {"status": "completed"}

    def complete(scope, **kwargs):
        events.append(("complete", kwargs["completed_at"]))
        return original_complete(scope, **kwargs)

    repository.renew_lease = renew
    repository.complete_ingestion_work = complete
    result = _scheduler(
        repository,
        analyze_run=analyze,
        now=lambda: next(clock),
    ).run_once()

    assert result.analysis_status == "completed"
    assert [event[0] for event in events] == ["renew", "analyze", "complete"]
    completion = repository.completed[0][1]
    assert completion["completed_at"] == NOW.replace(minute=5)
    assert completion["next_attempt_at"] == NOW.replace(minute=6)


def test_recovered_final_run_reuses_completed_window_without_second_evaluator() -> None:
    scope = _scope()
    repository = FakeRepository(claims=[_claim(scope), _claim(scope)])

    class IdempotentAnalysis:
        def __init__(self):
            self.completed_runs = set()
            self.evaluator_calls = 0

        def __call__(self, **kwargs):
            source_run_id = kwargs["source_run_id"]
            if source_run_id not in self.completed_runs:
                self.evaluator_calls += 1
                self.completed_runs.add(source_run_id)
            return {"status": "completed"}

    analysis = IdempotentAnalysis()
    scheduler = _scheduler(repository, analyze_run=analysis)

    first = scheduler.run_once()
    second = scheduler.run_once()

    assert first.analysis_status == "completed"
    assert second.analysis_status == "completed"
    assert analysis.evaluator_calls == 1
    assert len(repository.completed) == 2


def test_ineligible_analysis_does_not_invoke_evaluator_or_retry_ingestion() -> None:
    repository = FakeRepository()
    evaluator_calls = []

    def analyze_run(**kwargs):
        del kwargs
        return {"status": "ineligible", "evaluator_calls": len(evaluator_calls)}

    result = _scheduler(repository, analyze_run=analyze_run).run_once()

    assert result.analysis_status == "ineligible"
    assert evaluator_calls == []
    assert len(repository.completed) == 1
    assert repository.failures == []


@pytest.mark.parametrize("analysis_status", ["failed", "partial"])
def test_noncompleted_analysis_still_completes_without_connector_retry(
    analysis_status,
) -> None:
    repository = FakeRepository()

    result = _scheduler(
        repository,
        analyze_run=lambda **kwargs: {"status": analysis_status},
    ).run_once()

    assert result.analysis_status == analysis_status
    assert len(repository.completed) == 1
    assert repository.failures == []


def test_continuation_page_never_invokes_analysis() -> None:
    repository = FakeRepository()
    provider = FakeProvider(
        ConnectorPage(
            next_checkpoint=ConnectorCheckpoint(cursor="page-2"),
            has_more=True,
        )
    )

    result = _scheduler(
        repository,
        provider,
        normalize_page=lambda **kwargs: _normalized(
            next_checkpoint=kwargs["page"].next_checkpoint,
            has_more=True,
        ),
        analyze_run=lambda **kwargs: (_ for _ in ()).throw(
            AssertionError("analysis must wait for the final page")
        ),
    ).run_once()

    assert result.outcome == "continued"
    assert result.analysis_status is None
    assert repository.completed == []
    assert len(repository.continued) == 1


def test_lease_loss_never_advances_or_records_failure() -> None:
    repository = FakeRepository()
    repository.raise_on_persist = TelemetryLeaseLost("do-not-persist")

    result = _scheduler(repository).run_once()

    assert result.outcome == "lease_lost"
    assert repository.completed == []
    assert repository.failures == []


def test_disable_after_claim_releases_without_fetch_or_reschedule() -> None:
    scope = _scope()
    repository = FakeRepository(snapshot=_snapshot(scope, enabled=False))
    provider = FakeProvider()

    result = _scheduler(repository, provider).run_once()

    assert result.outcome == "disabled"
    assert provider.contexts == []
    assert repository.persisted == []
    assert repository.completed[0][1]["next_attempt_at"] is None


def test_transient_connector_failure_uses_persisted_retry_policy() -> None:
    repository = FakeRepository()
    provider = FakeProvider(
        error=TelemetryConnectorError(
            "provider_temporarily_unavailable",
            kind=ConnectorFailureKind.NETWORK,
            retryable=True,
            retry_after_seconds=17,
        )
    )

    result = _scheduler(repository, provider).run_once()

    assert result.outcome == "retry_scheduled"
    assert result.error_code == "provider_temporarily_unavailable"
    failure = repository.failures[0][1]
    assert failure["retryable"] is True
    assert failure["retry_after_seconds"] == 17
    assert failure["retry_jitter"] == 0.5
    assert failure["error_summary"] is None


def test_long_analysis_renews_connection_lease_until_handoff_returns() -> None:
    repository = FakeRepository()
    guardian_renewed = threading.Event()
    original_renew = repository.renew_lease

    def renew(scope, **kwargs):
        result = original_renew(scope, **kwargs)
        if len(repository.renewals) >= 2:
            guardian_renewed.set()
        return result

    repository.renew_lease = renew

    def analyze_run(**_kwargs):
        assert guardian_renewed.wait(1.0)
        return {"status": "completed"}

    result = _scheduler(
        repository,
        analyze_run=analyze_run,
        lease_heartbeat_interval_seconds=0.01,
    ).run_once()

    assert result.outcome == "processed"
    assert result.analysis_status == "completed"
    assert len(repository.renewals) >= 2
    assert len(repository.completed) == 1


def test_analysis_lease_guardian_failure_fails_closed_before_completion() -> None:
    repository = FakeRepository()
    guardian_attempted = threading.Event()

    def renew(scope, **kwargs):
        repository.renewals.append((scope, kwargs))
        if len(repository.renewals) == 1:
            return True
        guardian_attempted.set()
        return False

    repository.renew_lease = renew

    def analyze_run(**_kwargs):
        assert guardian_attempted.wait(1.0)
        return {"status": "completed"}

    result = _scheduler(
        repository,
        analyze_run=analyze_run,
        lease_heartbeat_interval_seconds=0.01,
    ).run_once()

    assert result.outcome == "lease_lost"
    assert repository.completed == []


def test_retry_with_persisted_range_continues_same_bounded_backfill() -> None:
    scope = _scope()
    repository = FakeRepository(
        claims=[
            _claim(
                scope,
                run_mode="retry",
                checkpoint_mode="backfill",
                range_start=datetime(2026, 8, 24, tzinfo=UTC),
                range_end=datetime(2026, 8, 25, tzinfo=UTC),
            )
        ]
    )
    provider = FakeProvider(
        ConnectorPage(
            next_checkpoint=ConnectorCheckpoint(cursor="backfill-page-2"),
            has_more=True,
        )
    )

    result = _scheduler(
        repository,
        provider,
        normalize_page=lambda **kwargs: _normalized(
            next_checkpoint=kwargs["page"].next_checkpoint,
            has_more=kwargs["page"].has_more,
        ),
    ).run_once()

    assert result.outcome == "continued"
    assert provider.contexts == []
    assert len(provider.backfills) == 1
    assert provider.backfills[0][1].start_at == datetime(2026, 8, 24, tzinfo=UTC)
    assert provider.backfills[0][1].end_at == datetime(2026, 8, 25, tzinfo=UTC)
    assert repository.continued[0][1]["run_id"] == "run-a"
    assert repository.completed == []


def test_permanent_failure_does_not_retry_or_leak_unsafe_error(caplog) -> None:
    repository = FakeRepository()
    provider = FakeProvider(
        error=TelemetryConnectorError(
            "https://user:plaintext-password@example.test",
            kind=ConnectorFailureKind.AUTHENTICATION,
            retryable=False,
            safe_message="plaintext-password",
        )
    )

    with caplog.at_level(logging.WARNING):
        result = _scheduler(repository, provider).run_once()

    assert result.error_code == "telemetry_scheduler_internal_error"
    failure = repository.failures[0][1]
    assert failure["retryable"] is False
    assert failure["error_summary"] is None
    assert "plaintext-password" not in caplog.text


def test_normalizer_contract_type_error_is_permanent() -> None:
    repository = FakeRepository()

    result = _scheduler(
        repository,
        normalize_page=lambda **kwargs: (_ for _ in ()).throw(
            TypeError("mapping_snapshot_required")
        ),
    ).run_once()

    assert result.outcome == "failed"
    assert result.error_code == "mapping_snapshot_required"
    assert repository.failures[0][1]["retryable"] is False


def test_scope_mismatch_fails_closed_without_provider_context_invention() -> None:
    claimed_scope = _scope()
    other_scope = _scope("tenant-b", "facility-b")
    repository = FakeRepository(
        claims=[_claim(claimed_scope)],
        snapshot=_snapshot(other_scope),
    )
    provider = FakeProvider()

    result = _scheduler(
        repository,
        provider,
        normalize_page=lambda **kwargs: _normalized(
            next_checkpoint=kwargs["page"].next_checkpoint,
            has_more=kwargs["page"].has_more,
        ),
    ).run_once()

    assert result.outcome == "failed"
    assert provider.contexts == []
    assert repository.persisted == []
    assert repository.failures[0][1]["retryable"] is False


def test_scheduler_thread_start_stop_is_idempotent_and_bounded() -> None:
    repository = FakeRepository(claims=[])
    heartbeat_seen = threading.Event()
    scheduler = _scheduler(
        repository,
        heartbeat=lambda **kwargs: heartbeat_seen.set() or True,
    )

    assert scheduler.start() is True
    assert scheduler.start() is False
    assert heartbeat_seen.wait(timeout=1)
    assert scheduler.stop(timeout_seconds=1) is True
    assert scheduler.stop(timeout_seconds=1) is True


def test_lifespan_starts_scheduler_only_for_worker_roles(monkeypatch, tmp_path) -> None:
    class LifecycleScheduler:
        running = False

        def __init__(self):
            self.calls = []

        def start(self):
            self.calls.append("start")
            self.running = True
            return True

        def stop(self, *, timeout_seconds):
            self.calls.append(("stop", timeout_seconds))
            self.running = False
            return True

    class Runtime:
        available = True

        def __init__(self, scheduler):
            self.scheduler = scheduler

        def verify_readiness(self):
            return True

    monkeypatch.setattr("app.main.start_upload_worker", lambda: None)
    monkeypatch.setattr("app.main.stop_upload_worker", lambda **kwargs: True)

    api_scheduler = LifecycleScheduler()
    monkeypatch.setattr(
        "app.main.build_telemetry_runtime", lambda settings: Runtime(api_scheduler)
    )
    api_settings = Settings(
        app_env="development",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://127.0.0.1:3010"],
        runtime_dir=tmp_path / "api",
        process_role="api",
        start_background_workers=True,
    )
    with TestClient(create_app(api_settings)):
        pass
    assert api_scheduler.calls == []

    worker_scheduler = LifecycleScheduler()
    monkeypatch.setattr(
        "app.main.build_telemetry_runtime", lambda settings: Runtime(worker_scheduler)
    )
    worker_settings = Settings(
        app_env="development",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://127.0.0.1:3010"],
        runtime_dir=tmp_path / "worker",
        process_role="worker",
        start_background_workers=True,
        shutdown_timeout_seconds=0.25,
    )
    with TestClient(create_app(worker_settings)) as client:
        assert client.get("/api/health").json()["telemetry_worker_started"] is True
    assert worker_scheduler.calls == ["start", ("stop", 0.25)]


def test_telemetry_heartbeat_uses_a_separate_status_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    monkeypatch.delenv("NERAIUM_UPLOAD_STATE_BUCKET", raising=False)
    monkeypatch.setattr(worker_heartbeat, "_LAST_WRITE_MONOTONIC", 0.0)
    monkeypatch.setattr(worker_heartbeat, "_TELEMETRY_LAST_WRITE_MONOTONIC", 0.0)

    assert worker_heartbeat.publish_worker_heartbeat(force=True, processed_job=True)
    assert worker_heartbeat.publish_telemetry_worker_heartbeat(
        force=True, processed_page=True
    )

    upload = worker_heartbeat.read_worker_heartbeat()
    telemetry = worker_heartbeat.read_telemetry_worker_heartbeat()
    assert upload["processed_job"] is True
    assert "processed_page" not in upload
    assert telemetry["processed_page"] is True
    assert "processed_job" not in telemetry


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"telemetry_scheduler_poll_interval_seconds": 0.01}, "POLL_INTERVAL"),
        ({"telemetry_scheduler_lease_seconds": 29}, "LEASE_SECONDS"),
        ({"telemetry_worker_heartbeat_interval_seconds": 301}, "HEARTBEAT_INTERVAL"),
    ],
)
def test_scheduler_settings_are_bounded(override, message) -> None:
    settings = Settings(
        app_env="development",
        backend_host="127.0.0.1",
        backend_port=8010,
        cors_origins=["http://127.0.0.1:3010"],
        **override,
    )

    with pytest.raises(ValueError, match=message):
        validate_settings(settings)
