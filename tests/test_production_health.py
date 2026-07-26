from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.production_health import (
    HealthObservation,
    PersistencePolicy,
    ProductionHealthEvaluator,
    _classify_alb_target_states,
)

UTC = timezone.utc


class RecordingNotifier:
    def __init__(self):
        self.events = []

    def dispatch(self, event):
        self.events.append(event)
        return [{"adapter": "test", "delivered": True, "detail": "recorded"}]

    def status(self):
        return {"configured_adapters": ["test"], "last_delivery_results": []}


class FakeS3Error(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeS3:
    def __init__(self):
        self.objects = {}

    def get_object(self, *, Bucket, Key):
        try:
            body = self.objects[(Bucket, Key)]
        except KeyError as error:
            raise FakeS3Error("NoSuchKey") from error
        return {"Body": io.BytesIO(body)}

    def put_object(self, *, Bucket, Key, Body, IfNoneMatch=None, **kwargs):
        object_key = (Bucket, Key)
        if IfNoneMatch == "*" and object_key in self.objects:
            raise FakeS3Error("PreconditionFailed")
        self.objects[object_key] = bytes(Body)
        return {"ETag": "test"}


def observation(key: str, subsystem: str, status: str = "critical", *, evidence: str | None = None):
    return HealthObservation(
        key=key,
        subsystem=subsystem,
        status=status,
        evidence=[evidence or f"{key} failed."],
        recommended_first_check=f"Check {subsystem} first.",
        impact=f"{subsystem} is impacted.",
    )


def evaluate_sequence(tmp_path, key, subsystem, *, count, duration, status="critical"):
    notifier = RecordingNotifier()
    evaluator = ProductionHealthEvaluator(
        state_path=tmp_path / f"{key}.json",
        notifier=notifier,
        policies={key: PersistencePolicy(count, duration)},
    )
    started = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    snapshots = []
    step = duration / max(count - 1, 1)
    for index in range(count):
        snapshots.append(evaluator.evaluate(
            [observation(key, subsystem, status)],
            now=started + timedelta(seconds=step * index),
        ))
    return evaluator, notifier, snapshots, started


@pytest.mark.parametrize(
    ("key", "subsystem", "count", "duration", "status", "evidence"),
    [
        ("auth_connectivity", "auth", 3, 120, "critical", "Authentication database unavailable."),
        ("secrets_manager_access", "secrets", 3, 120, "critical", "Secrets rotation access failed."),
        ("credential_refresh", "secrets", 3, 120, "critical", "Expired credentials could not be refreshed."),
        ("worker_heartbeat", "workers", 3, 120, "critical", "Worker heartbeat stopped after a crash."),
        ("queue_processing", "uploads", 3, 300, "degraded", "Upload queue has not advanced for five minutes."),
        ("api_availability", "api", 5, 240, "critical", "API readiness probes repeatedly failed."),
        ("runtime_db_latency", "runtime_db", 5, 240, "degraded", "Runtime database latency exceeded threshold."),
        ("api_latency", "api", 5, 240, "degraded", "API p95 latency exceeded threshold."),
    ],
)
def test_failure_simulations_alert_only_after_persistence(
    tmp_path, key, subsystem, count, duration, status, evidence
):
    notifier = RecordingNotifier()
    evaluator = ProductionHealthEvaluator(
        state_path=tmp_path / f"{key}.json",
        notifier=notifier,
        policies={key: PersistencePolicy(count, duration)},
    )
    started = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    step = duration / max(count - 1, 1)

    for index in range(count - 1):
        snapshot = evaluator.evaluate(
            [observation(key, subsystem, status, evidence=evidence)],
            now=started + timedelta(seconds=step * index),
        )
        assert snapshot["current_alerts"] == []
        assert notifier.events == []

    snapshot = evaluator.evaluate(
        [observation(key, subsystem, status, evidence=evidence)],
        now=started + timedelta(seconds=duration),
    )

    assert len(snapshot["current_alerts"]) == 1
    assert snapshot["current_alerts"][0]["signal"] == key
    assert len(notifier.events) == 1
    assert notifier.events[0]["event_type"] == "opened"
    expected_category = "Infrastructure Critical" if status == "critical" else (
        "Infrastructure Review" if key.endswith("latency") else "Infrastructure Degraded"
    )
    assert notifier.events[0]["category"] == expected_category


def test_repeated_failure_deduplicates_and_recovery_notifies_once(tmp_path):
    evaluator, notifier, snapshots, started = evaluate_sequence(
        tmp_path,
        "auth_connectivity",
        "auth",
        count=3,
        duration=120,
    )
    assert len(snapshots[-1]["current_alerts"]) == 1
    assert len(notifier.events) == 1

    for minute in (3, 4, 5):
        evaluator.evaluate(
            [observation("auth_connectivity", "auth")],
            now=started + timedelta(minutes=minute),
        )
    assert len(notifier.events) == 1

    recovered = evaluator.evaluate(
        [observation("auth_connectivity", "auth", "healthy", evidence="Authentication database recovered.")],
        now=started + timedelta(minutes=6),
    )
    assert recovered["current_alerts"] == []
    assert recovered["incidents"][0]["status"] == "resolved"
    assert [event["event_type"] for event in notifier.events] == ["opened", "recovery"]
    assert notifier.events[-1]["category"] == "Infrastructure Healthy"

    evaluator.evaluate(
        [observation("auth_connectivity", "auth", "healthy", evidence="Authentication remains healthy.")],
        now=started + timedelta(minutes=7),
    )
    assert len(notifier.events) == 2


def test_incident_state_survives_evaluator_restart(tmp_path):
    state_path = tmp_path / "health.json"
    notifier = RecordingNotifier()
    policy = {"worker_heartbeat": PersistencePolicy(3, 120)}
    first = ProductionHealthEvaluator(state_path=state_path, notifier=notifier, policies=policy)
    started = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    for minute in range(3):
        first.evaluate([observation("worker_heartbeat", "workers")], now=started + timedelta(minutes=minute))

    restarted_notifier = RecordingNotifier()
    restarted = ProductionHealthEvaluator(state_path=state_path, notifier=restarted_notifier, policies=policy)
    snapshot = restarted.evaluate(
        [observation("worker_heartbeat", "workers")],
        now=started + timedelta(minutes=3),
    )

    assert len(snapshot["current_alerts"]) == 1
    assert restarted_notifier.events == []


def test_shared_state_survives_task_replacement_and_deduplicates_notifications(tmp_path):
    shared_s3 = FakeS3()
    policy = {"worker_heartbeat": PersistencePolicy(3, 120)}
    first_notifier = RecordingNotifier()
    first = ProductionHealthEvaluator(
        state_path=tmp_path / "first.json",
        notifier=first_notifier,
        policies=policy,
        state_bucket="health-bucket",
        s3_client=shared_s3,
    )
    started = datetime(2026, 7, 25, 12, 0, tzinfo=UTC)
    for minute in range(3):
        first.evaluate([observation("worker_heartbeat", "workers")], now=started + timedelta(minutes=minute))
    assert [event["event_type"] for event in first_notifier.events] == ["opened"]

    replacement_notifier = RecordingNotifier()
    replacement = ProductionHealthEvaluator(
        state_path=tmp_path / "replacement.json",
        notifier=replacement_notifier,
        policies=policy,
        state_bucket="health-bucket",
        s3_client=shared_s3,
    )
    active = replacement.evaluate(
        [observation("worker_heartbeat", "workers")],
        now=started + timedelta(minutes=3),
    )
    assert len(active["current_alerts"]) == 1
    assert replacement_notifier.events == []

    recovered = replacement.evaluate(
        [observation("worker_heartbeat", "workers", "healthy", evidence="Worker recovered.")],
        now=started + timedelta(minutes=4),
    )
    assert recovered["current_alerts"] == []
    assert recovered["incidents"][0]["status"] == "resolved"
    assert [event["event_type"] for event in replacement_notifier.events] == ["recovery"]

    final_notifier = RecordingNotifier()
    final = ProductionHealthEvaluator(
        state_path=tmp_path / "final.json",
        notifier=final_notifier,
        policies=policy,
        state_bucket="health-bucket",
        s3_client=shared_s3,
    )
    final_snapshot = final.evaluate(
        [observation("worker_heartbeat", "workers", "healthy", evidence="Worker remains healthy.")],
        now=started + timedelta(minutes=5),
    )
    assert final_snapshot["incidents"][0]["status"] == "resolved"
    assert final_notifier.events == []
    marker_keys = [key for bucket, key in shared_s3.objects if "production-health-notifications" in key]
    assert len(marker_keys) == 2


def test_infrastructure_health_endpoint_is_structured(client: TestClient):
    response = client.get("/api/infrastructure/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"] in {"healthy", "degraded", "critical"}
    assert set(payload["subsystems"]) == {
        "api", "auth", "runtime_db", "workers", "uploads", "notifications", "storage", "secrets"
    }
    assert isinstance(payload["incidents"], list)
    assert isinstance(payload["current_alerts"], list)


def test_alb_rollout_targets_do_not_create_false_degradation():
    assert _classify_alb_target_states(["healthy", "draining"]) == ("healthy", 1, [])
    assert _classify_alb_target_states(["healthy", "unused"]) == ("healthy", 1, [])
    assert _classify_alb_target_states(["healthy", "unhealthy"]) == ("degraded", 1, ["unhealthy"])
    assert _classify_alb_target_states(["draining"]) == ("critical", 0, [])


def test_worker_heartbeat_is_sanitized_and_readable(monkeypatch, tmp_path):
    from app.services import worker_heartbeat

    monkeypatch.delenv("NERAIUM_UPLOAD_STATE_BUCKET", raising=False)
    monkeypatch.setenv("NERAIUM_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("NERAIUM_PROCESS_ROLE", "worker")
    monkeypatch.setenv("NERAIUM_BUILD_SHA", "abcdef1234567890")
    monkeypatch.setattr(worker_heartbeat, "_LAST_WRITE_MONOTONIC", 0.0)

    assert worker_heartbeat.publish_worker_heartbeat(status="healthy", processed_job=True, force=True)
    payload = worker_heartbeat.read_worker_heartbeat()

    assert payload is not None
    assert payload["status"] == "healthy"
    assert payload["processed_job"] is True
    assert payload["build_sha"] == "abcdef123456"
    assert set(payload) == {"status", "observed_at", "process_role", "build_sha", "processed_job", "error_type"}
    assert "password" not in str(payload).lower()
    assert "secret" not in str(payload).lower()
