from __future__ import annotations

import json
import logging
import math
import os
import shutil
import statistics
import tempfile
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from app.core.config import Settings
from app.services.auth_store import auth_dependency_telemetry, auth_store_available, probe_auth_secret_metadata
from app.services.infrastructure_notifications import InfrastructureNotificationEngine
from app.services.runtime_db import db_connection, queue_operational_metrics
from app.services.service_status import STARTUP_STATUS
from app.services.worker_heartbeat import read_worker_heartbeat

try:
    import boto3  # type: ignore
except Exception:  # pragma: no cover
    boto3 = None

logger = logging.getLogger(__name__)
UTC = timezone.utc
SUBSYSTEMS = ("api", "auth", "runtime_db", "workers", "uploads", "notifications", "storage", "secrets")
_STATUS_RANK = {"healthy": 0, "degraded": 1, "critical": 2}
_API_REQUEST_METRICS: deque[tuple[float, float, int, str]] = deque(maxlen=1000)
_API_METRICS_LOCK = threading.RLock()


@dataclass(frozen=True)
class PersistencePolicy:
    consecutive_failures: int
    minimum_duration_seconds: float


DEFAULT_POLICIES: dict[str, PersistencePolicy] = {
    "api_availability": PersistencePolicy(5, 240),
    "api_latency": PersistencePolicy(5, 240),
    "auth_connectivity": PersistencePolicy(3, 120),
    "auth_latency": PersistencePolicy(5, 240),
    "runtime_db_connectivity": PersistencePolicy(3, 120),
    "runtime_db_latency": PersistencePolicy(5, 240),
    "secrets_manager_access": PersistencePolicy(3, 120),
    "credential_refresh": PersistencePolicy(3, 120),
    "ecs_api_tasks": PersistencePolicy(3, 120),
    "alb_targets": PersistencePolicy(5, 240),
    "ecs_worker_tasks": PersistencePolicy(3, 120),
    "worker_heartbeat": PersistencePolicy(3, 120),
    "queue_processing": PersistencePolicy(3, 300),
    "runtime_storage": PersistencePolicy(3, 120),
    "critical_dependencies": PersistencePolicy(3, 120),
    "notification_delivery": PersistencePolicy(3, 120),
}


@dataclass(frozen=True)
class HealthObservation:
    key: str
    subsystem: str
    status: str
    evidence: list[str]
    recommended_first_check: str
    impact: str
    latency_ms: float | None = None
    confidence: str = "high"
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _percentile(values: Iterable[float], point: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * point) - 1))
    return round(ordered[index], 2)


def record_api_request_metric(*, duration_ms: float, status_code: int, path: str) -> None:
    if path in {"/health", "/api/health", "/api/ready", "/api/infrastructure/health"}:
        return
    with _API_METRICS_LOCK:
        _API_REQUEST_METRICS.append((time.time(), float(duration_ms), int(status_code), str(path)))


def api_request_metrics_snapshot(window_seconds: float = 300.0) -> dict[str, Any]:
    cutoff = time.time() - max(float(window_seconds), 1.0)
    with _API_METRICS_LOCK:
        rows = [row for row in _API_REQUEST_METRICS if row[0] >= cutoff]
    durations = [row[1] for row in rows]
    errors = [row for row in rows if row[2] >= 500]
    return {
        "sample_count": len(rows),
        "p50_ms": _percentile(durations, 0.50),
        "p95_ms": _percentile(durations, 0.95),
        "server_error_count": len(errors),
        "server_error_rate": round(len(errors) / len(rows), 4) if rows else 0.0,
    }


def _classify_alb_target_states(states: list[str]) -> tuple[str, int, list[str]]:
    """Treat rollout draining/unused targets as neutral while a healthy target is serving."""
    healthy = states.count("healthy")
    active_failures = [state for state in states if state not in {"healthy", "draining", "unused"}]
    if healthy == 0:
        return "critical", healthy, active_failures
    if active_failures:
        return "degraded", healthy, active_failures
    return "healthy", healthy, active_failures


class ProductionHealthProbe:
    """Collect sanitized production dependency observations without exposing credentials."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self._aws_clients: dict[str, Any] = {}

    def _client(self, service: str):
        if service not in self._aws_clients:
            if boto3 is None:
                raise RuntimeError("boto3 is unavailable")
            self._aws_clients[service] = boto3.client(service, region_name=os.getenv("AWS_REGION") or None)
        return self._aws_clients[service]

    @staticmethod
    def _timed(operation: Callable[[], Any]) -> tuple[Any, float]:
        started = time.perf_counter()
        result = operation()
        return result, round((time.perf_counter() - started) * 1000, 2)

    def _api_observations(self) -> list[HealthObservation]:
        startup_failures = list(STARTUP_STATUS.get("failed_modules") or [])
        startup_ok = bool(STARTUP_STATUS.get("startup_complete")) and not startup_failures
        request_metrics = api_request_metrics_snapshot()
        p95 = request_metrics.get("p95_ms")
        latency_status = "degraded" if p95 is not None and p95 >= 2000 else "healthy"
        error_rate = float(request_metrics.get("server_error_rate") or 0.0)
        if error_rate >= 0.10 and int(request_metrics.get("sample_count") or 0) >= 10:
            latency_status = "critical"
        return [
            HealthObservation(
                key="api_availability",
                subsystem="api",
                status="healthy" if startup_ok else "critical",
                evidence=["API process startup is complete."] if startup_ok else [
                    "API process startup is incomplete or a required module failed.",
                    *[f"Startup failure: {failure}" for failure in startup_failures[:5]],
                ],
                recommended_first_check="Inspect the API ECS task events and /ecs/neraium-prod-api logs.",
                impact="API requests may be unavailable." if not startup_ok else "No current API availability impact.",
            ),
            HealthObservation(
                key="api_latency",
                subsystem="api",
                status=latency_status,
                evidence=[
                    f"API p95 latency is {p95:.0f} ms across {request_metrics['sample_count']} recent requests."
                    if p95 is not None else "No non-health API requests were observed in the last five minutes.",
                    f"Recent server error rate is {error_rate:.1%}.",
                ],
                recommended_first_check="Compare ALB target response time with API task CPU, memory, and dependency latency.",
                impact="API responses are slow or failing." if latency_status != "healthy" else "No sustained API latency impact.",
                latency_ms=p95,
                metadata=request_metrics,
            ),
        ]

    def _database_observations(self) -> list[HealthObservation]:
        observations: list[HealthObservation] = []
        try:
            available, latency = self._timed(auth_store_available)
            status = "healthy" if available else "critical"
            if available and latency >= 1500:
                status = "degraded"
            observations.extend([
                HealthObservation(
                    key="auth_connectivity",
                    subsystem="auth",
                    status="healthy" if available else "critical",
                    evidence=[
                        f"Authentication database connectivity probe completed in {latency:.0f} ms."
                        if available else "Authentication database connectivity probe returned unavailable."
                    ],
                    recommended_first_check="Verify RDS availability, the managed credential secret, and authentication task logs.",
                    impact="Users cannot authenticate or validate sessions." if not available else "Authentication is available.",
                    latency_ms=latency,
                ),
                HealthObservation(
                    key="auth_latency",
                    subsystem="auth",
                    status=status,
                    evidence=[f"Authentication database latency is {latency:.0f} ms."],
                    recommended_first_check="Inspect RDS load, connections, locks, and network latency from the API tasks.",
                    impact="Authentication requests may be delayed." if status != "healthy" else "Authentication latency is within threshold.",
                    latency_ms=latency,
                ),
            ])
        except Exception as error:
            observations.extend([
                HealthObservation(
                    key="auth_connectivity",
                    subsystem="auth",
                    status="critical",
                    evidence=[f"Authentication database probe failed ({type(error).__name__})."],
                    recommended_first_check="Verify RDS credentials and Secrets Manager rotation, then inspect authentication logs.",
                    impact="Users may be unable to sign in or validate sessions.",
                ),
                HealthObservation(
                    key="auth_latency",
                    subsystem="auth",
                    status="critical",
                    evidence=["Authentication latency could not be measured because the database probe failed."],
                    recommended_first_check="Restore authentication database connectivity before investigating latency.",
                    impact="Authentication is unavailable.",
                ),
            ])

        try:
            def query_runtime_db() -> bool:
                with db_connection() as connection:
                    return connection.execute("SELECT 1 AS ready").fetchone() is not None

            runtime_available, latency = self._timed(query_runtime_db)
            latency_status = "degraded" if runtime_available and latency >= 1000 else ("healthy" if runtime_available else "critical")
            observations.extend([
                HealthObservation(
                    key="runtime_db_connectivity",
                    subsystem="runtime_db",
                    status="healthy" if runtime_available else "critical",
                    evidence=[f"Runtime database connectivity probe completed in {latency:.0f} ms."],
                    recommended_first_check="Inspect the runtime volume/database and API task filesystem health.",
                    impact="Upload state and runtime records may be unavailable." if not runtime_available else "Runtime database is available.",
                    latency_ms=latency,
                ),
                HealthObservation(
                    key="runtime_db_latency",
                    subsystem="runtime_db",
                    status=latency_status,
                    evidence=[f"Runtime database latency is {latency:.0f} ms."],
                    recommended_first_check="Inspect runtime storage I/O, locks, and available disk space.",
                    impact="Runtime state operations may be delayed." if latency_status != "healthy" else "Runtime database latency is within threshold.",
                    latency_ms=latency,
                ),
            ])
        except Exception as error:
            observations.extend([
                HealthObservation(
                    key="runtime_db_connectivity",
                    subsystem="runtime_db",
                    status="critical",
                    evidence=[f"Runtime database probe failed ({type(error).__name__})."],
                    recommended_first_check="Inspect the runtime mount, database file permissions, and API task logs.",
                    impact="Upload state and runtime records may be unavailable.",
                ),
                HealthObservation(
                    key="runtime_db_latency",
                    subsystem="runtime_db",
                    status="critical",
                    evidence=["Runtime database latency could not be measured because connectivity failed."],
                    recommended_first_check="Restore runtime database connectivity before investigating latency.",
                    impact="Runtime state operations are unavailable.",
                ),
            ])
        return observations

    def _secret_observations(self) -> list[HealthObservation]:
        if not os.getenv("NERAIUM_AUTH_DATABASE_SECRET_ARN", "").strip():
            return [
                HealthObservation(
                    key="secrets_manager_access",
                    subsystem="secrets",
                    status="healthy",
                    evidence=["Authentication uses a direct database URL; managed RDS secret probing is not configured."],
                    recommended_first_check="Review the configured authentication database credential source.",
                    impact="No managed secret dependency is active.",
                    confidence="medium",
                ),
                HealthObservation(
                    key="credential_refresh",
                    subsystem="secrets",
                    status="healthy",
                    evidence=["Managed credential refresh is not required for the configured authentication backend."],
                    recommended_first_check="Review the authentication database credential source.",
                    impact="No managed refresh cycle is active.",
                    confidence="medium",
                ),
            ]

        observations: list[HealthObservation] = []
        try:
            metadata, latency = self._timed(probe_auth_secret_metadata)
            age = metadata.get("age_seconds")
            evidence = [f"Secrets Manager metadata probe completed in {latency:.0f} ms."]
            if age is not None:
                evidence.append(f"The active database secret version is approximately {int(age)} seconds old.")
            if metadata.get("rotation_enabled") is False:
                evidence.append("Automatic rotation is not reported as enabled for the authentication secret.")
            observations.append(HealthObservation(
                key="secrets_manager_access",
                subsystem="secrets",
                status="healthy",
                evidence=evidence,
                recommended_first_check="Inspect the managed RDS secret rotation state and task-role access.",
                impact="Secrets Manager access is available.",
                latency_ms=latency,
                metadata=metadata,
            ))
        except Exception as error:
            observations.append(HealthObservation(
                key="secrets_manager_access",
                subsystem="secrets",
                status="critical",
                evidence=[f"Secrets Manager access probe failed ({type(error).__name__})."],
                recommended_first_check="Verify task-role secretsmanager permissions, KMS decrypt access, and the RDS managed secret state.",
                impact="Rotated authentication credentials cannot be refreshed.",
            ))

        telemetry = auth_dependency_telemetry()
        refresh_failures = int(telemetry.get("consecutive_refresh_failures") or 0)
        refresh_status = "critical" if refresh_failures > 0 else "healthy"
        last_success = telemetry.get("last_refresh_success_at")
        observations.append(HealthObservation(
            key="credential_refresh",
            subsystem="secrets",
            status=refresh_status,
            evidence=[
                f"Credential refresh has failed {refresh_failures} consecutive attempt(s)."
                if refresh_failures else "No unresolved managed credential refresh failure is recorded.",
                f"Last successful credential refresh: {last_success}." if last_success else "No credential refresh timestamp has been recorded in this task yet.",
            ],
            recommended_first_check="Verify RDS credentials and Secrets Manager rotation, then inspect auth_database_credentials_refresh logs.",
            impact="Authentication may continue using stale credentials." if refresh_status != "healthy" else "Credential refresh is operating normally.",
            metadata=telemetry,
        ))
        return observations

    def _queue_and_worker_observations(self, now: datetime) -> list[HealthObservation]:
        observations: list[HealthObservation] = []
        try:
            metrics = queue_operational_metrics()
            pending_age = float(metrics.get("oldest_pending_age_seconds") or 0.0)
            processing_age = float(metrics.get("oldest_processing_age_seconds") or 0.0)
            pending = int(metrics.get("pending") or 0)
            processing = int(metrics.get("processing") or 0)
            status = "healthy"
            evidence = [f"Queue depth is {pending} pending and {processing} processing job(s)."]
            if processing and processing_age >= 900:
                status = "critical"
                evidence.append(f"Oldest processing job has not advanced for {processing_age:.0f} seconds.")
            elif pending and pending_age >= 300:
                status = "degraded"
                evidence.append(f"Oldest pending job has waited {pending_age:.0f} seconds.")
            else:
                evidence.append("No queue stall threshold is currently exceeded.")
            observations.append(HealthObservation(
                key="queue_processing",
                subsystem="uploads",
                status=status,
                evidence=evidence,
                recommended_first_check="Inspect the worker heartbeat, ECS worker task, and oldest queued upload record.",
                impact="Uploads are delayed or stalled." if status != "healthy" else "Upload queue processing is within threshold.",
                metadata=metrics,
            ))
        except Exception as error:
            observations.append(HealthObservation(
                key="queue_processing",
                subsystem="uploads",
                status="critical",
                evidence=[f"Upload queue metrics could not be read ({type(error).__name__})."],
                recommended_first_check="Verify shared S3 queue access and worker/API task-role permissions.",
                impact="Upload queue state cannot be validated.",
            ))

        heartbeat = read_worker_heartbeat()
        observed_at = _parse_time((heartbeat or {}).get("observed_at"))
        age_seconds = (now - observed_at).total_seconds() if observed_at else None
        heartbeat_ok = bool(
            heartbeat
            and observed_at
            and age_seconds is not None
            and age_seconds <= float(getattr(self.settings, "worker_heartbeat_timeout_seconds", 180.0))
            and heartbeat.get("status") == "healthy"
        )
        observations.append(HealthObservation(
            key="worker_heartbeat",
            subsystem="workers",
            status="healthy" if heartbeat_ok else "critical",
            evidence=[
                f"Worker heartbeat is {max(age_seconds or 0, 0):.0f} seconds old."
                if observed_at else "No upload worker heartbeat is available.",
                f"Worker build: {(heartbeat or {}).get('build_sha') or 'unknown'}.",
            ],
            recommended_first_check="Inspect the ECS worker task status and /ecs/neraium-prod-worker logs.",
            impact="Background uploads may not be processed." if not heartbeat_ok else "Background upload worker is reporting normally.",
            metadata={"heartbeat": heartbeat, "age_seconds": round(age_seconds, 2) if age_seconds is not None else None},
        ))
        return observations

    def _storage_observation(self) -> HealthObservation:
        runtime_dir = Path(self.settings.runtime_dir)
        try:
            runtime_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix=".health-", dir=runtime_dir, delete=True) as probe:
                probe.write(b"neraium-health")
                probe.flush()
                os.fsync(probe.fileno())
            usage = shutil.disk_usage(runtime_dir)
            free_percent = usage.free / usage.total if usage.total else 0.0
            status = "critical" if usage.free < 512 * 1024 * 1024 or free_percent < 0.05 else "healthy"
            return HealthObservation(
                key="runtime_storage",
                subsystem="storage",
                status=status,
                evidence=[
                    "Runtime directory write/fsync probe succeeded.",
                    f"Runtime storage has {usage.free // (1024 * 1024)} MiB free ({free_percent:.1%}).",
                ],
                recommended_first_check="Inspect the ECS runtime mount, filesystem permissions, and free space.",
                impact="Runtime writes may fail." if status != "healthy" else "Runtime storage is writable with adequate free space.",
                metadata={"free_bytes": usage.free, "total_bytes": usage.total, "free_percent": round(free_percent, 4)},
            )
        except Exception as error:
            return HealthObservation(
                key="runtime_storage",
                subsystem="storage",
                status="critical",
                evidence=[f"Runtime directory write probe failed ({type(error).__name__})."],
                recommended_first_check="Inspect the ECS runtime volume mount and task filesystem permissions.",
                impact="Runtime state, queues, or uploads may fail to persist.",
            )

    def _aws_observations(self, now: datetime) -> list[HealthObservation]:
        if self.settings.app_env not in {"prod", "production"}:
            return []
        cluster = os.getenv("NERAIUM_ECS_CLUSTER", "").strip()
        api_service = os.getenv("NERAIUM_ECS_API_SERVICE", "").strip()
        worker_service = os.getenv("NERAIUM_ECS_WORKER_SERVICE", "").strip()
        target_group_arn = os.getenv("NERAIUM_ALB_TARGET_GROUP_ARN", "").strip()
        observations: list[HealthObservation] = []
        if not cluster or not api_service or not worker_service:
            missing = [name for name, value in (("cluster", cluster), ("api service", api_service), ("worker service", worker_service)) if not value]
            for key, subsystem in (("ecs_api_tasks", "api"), ("ecs_worker_tasks", "workers")):
                observations.append(HealthObservation(
                    key=key,
                    subsystem=subsystem,
                    status="degraded",
                    evidence=[f"AWS self-inspection configuration is incomplete: {', '.join(missing)} missing."],
                    recommended_first_check="Verify the production task definition includes ECS monitor resource names.",
                    impact="The application cannot validate ECS task counts.",
                    confidence="low",
                ))
        else:
            try:
                response = self._client("ecs").describe_services(cluster=cluster, services=[api_service, worker_service])
                by_name = {service.get("serviceName"): service for service in response.get("services") or []}
                for service_name, key, subsystem, label in (
                    (api_service, "ecs_api_tasks", "api", "API"),
                    (worker_service, "ecs_worker_tasks", "workers", "worker"),
                ):
                    service = by_name.get(service_name) or {}
                    desired = int(service.get("desiredCount") or 0)
                    running = int(service.get("runningCount") or 0)
                    pending = int(service.get("pendingCount") or 0)
                    recent_starts = 0
                    for event in service.get("events") or []:
                        created = _parse_time(event.get("createdAt"))
                        message = str(event.get("message") or "").lower()
                        if created and created >= now - timedelta(minutes=15) and "has started" in message:
                            recent_starts += 1
                    status = "healthy" if desired > 0 and running >= desired else "critical"
                    if status == "healthy" and recent_starts >= 3:
                        status = "degraded"
                    evidence = [f"ECS {label} service has {running}/{desired} running task(s) and {pending} pending."]
                    if recent_starts >= 3:
                        evidence.append(f"ECS reported {recent_starts} task start events in the last 15 minutes.")
                    observations.append(HealthObservation(
                        key=key,
                        subsystem=subsystem,
                        status=status,
                        evidence=evidence,
                        recommended_first_check=f"Inspect the {label} service deployment, stopped task reasons, and CloudWatch logs.",
                        impact=f"The {label} service has insufficient healthy tasks." if status == "critical" else ("Repeated task replacement is occurring." if status == "degraded" else f"The {label} service task count is stable."),
                        metadata={"desired": desired, "running": running, "pending": pending, "recent_start_events": recent_starts},
                    ))
            except Exception as error:
                for key, subsystem, label in (("ecs_api_tasks", "api", "API"), ("ecs_worker_tasks", "workers", "worker")):
                    observations.append(HealthObservation(
                        key=key,
                        subsystem=subsystem,
                        status="critical",
                        evidence=[f"ECS {label} service probe failed ({type(error).__name__})."],
                        recommended_first_check="Verify task-role ecs:DescribeServices permission and ECS service availability.",
                        impact=f"{label.title()} task health cannot be validated.",
                    ))

        if not target_group_arn:
            observations.append(HealthObservation(
                key="alb_targets",
                subsystem="api",
                status="degraded",
                evidence=["ALB target group ARN is not available to the application monitor."],
                recommended_first_check="Verify the API task definition includes NERAIUM_ALB_TARGET_GROUP_ARN.",
                impact="The application cannot validate ALB target health.",
                confidence="low",
            ))
        else:
            try:
                response = self._client("elbv2").describe_target_health(TargetGroupArn=target_group_arn)
                descriptions = response.get("TargetHealthDescriptions") or []
                states = [str(item.get("TargetHealth", {}).get("State") or "unknown") for item in descriptions]
                status, healthy, active_failures = _classify_alb_target_states(states)
                observations.append(HealthObservation(
                    key="alb_targets",
                    subsystem="api",
                    status=status,
                    evidence=[f"ALB reports {healthy}/{len(states)} healthy API target(s).", f"Target states: {', '.join(states) or 'none'}."],
                    recommended_first_check="Inspect target health reasons, API /api/health responses, and ECS task networking.",
                    impact="The load balancer cannot route API traffic." if status == "critical" else ("API capacity is reduced." if status == "degraded" else "ALB targets are healthy."),
                    metadata={"healthy": healthy, "total": len(states), "states": states, "active_failures": active_failures},
                ))
            except Exception as error:
                observations.append(HealthObservation(
                    key="alb_targets",
                    subsystem="api",
                    status="critical",
                    evidence=[f"ALB target health probe failed ({type(error).__name__})."],
                    recommended_first_check="Verify task-role elasticloadbalancing:DescribeTargetHealth permission and target group state.",
                    impact="ALB target health cannot be validated.",
                ))
        return observations

    def collect(self, now: datetime | None = None) -> list[HealthObservation]:
        observed_at = now or _utc_now()
        observations = [
            *self._api_observations(),
            *self._database_observations(),
            *self._secret_observations(),
            *self._queue_and_worker_observations(observed_at),
            self._storage_observation(),
            *self._aws_observations(observed_at),
        ]
        failed_modules = list(STARTUP_STATUS.get("failed_modules") or [])
        observations.append(HealthObservation(
            key="critical_dependencies",
            subsystem="api",
            status="critical" if failed_modules else "healthy",
            evidence=[f"Required startup dependency failed: {item}" for item in failed_modules] or ["No required startup dependency failure is recorded."],
            recommended_first_check="Inspect startup failures in the API task logs and the affected dependency.",
            impact="One or more critical platform dependencies are unavailable." if failed_modules else "Critical startup dependencies are available.",
        ))
        return observations


class ProductionHealthEvaluator:
    """Persist failure evidence, open one incident after policy thresholds, and close it once."""

    STATE_KEY = "infrastructure/production-health-state.json"
    NOTIFICATION_MARKER_PREFIX = "infrastructure/production-health-notifications/"

    def __init__(
        self,
        *,
        state_path: Path,
        notifier: InfrastructureNotificationEngine,
        policies: dict[str, PersistencePolicy] | None = None,
        state_bucket: str | None = None,
        s3_client: Any | None = None,
    ):
        self.state_path = Path(state_path)
        self.state_bucket = str(state_bucket or "").strip()
        self.notifier = notifier
        self.policies = {**DEFAULT_POLICIES, **(policies or {})}
        self._lock = threading.RLock()
        self._s3_client = s3_client
        self._state = self._load_state()

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"version": 1, "signals": {}, "incidents": [], "notifications": [], "last_snapshot": None}

    @staticmethod
    def _validated_state(raw: bytes | str) -> dict[str, Any]:
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("Unsupported production health state payload.")
        return {**ProductionHealthEvaluator._empty_state(), **payload}

    def _client(self):
        if self._s3_client is None:
            if boto3 is None:
                raise RuntimeError("boto3 is required for shared production health state.")
            self._s3_client = boto3.client("s3", region_name=os.getenv("AWS_REGION") or None)
        return self._s3_client

    @staticmethod
    def _error_code(error: Exception) -> str:
        return str(getattr(error, "response", {}).get("Error", {}).get("Code", ""))

    def _load_state(self) -> dict[str, Any]:
        if self.state_bucket:
            try:
                response = self._client().get_object(Bucket=self.state_bucket, Key=self.STATE_KEY)
                return self._validated_state(response["Body"].read())
            except Exception as error:
                if self._error_code(error) in {"NoSuchKey", "404", "NotFound"}:
                    return self._empty_state()
                raise RuntimeError("Shared production health state could not be loaded.") from error
        try:
            return self._validated_state(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return self._empty_state()

    def _save_state(self) -> None:
        body = json.dumps(self._state, indent=2, sort_keys=True).encode("utf-8")
        if self.state_bucket:
            self._client().put_object(
                Bucket=self.state_bucket,
                Key=self.STATE_KEY,
                Body=body,
                ContentType="application/json",
                ServerSideEncryption="AES256",
            )
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_bytes(body)
        os.replace(temporary, self.state_path)

    def _claim_notification(self, event: dict[str, Any]) -> bool:
        if not self.state_bucket:
            return True
        incident_id = str(event.get("incident_id") or "unknown")
        event_type = str(event.get("event_type") or "transition")
        key = f"{self.NOTIFICATION_MARKER_PREFIX}{incident_id}/{event_type}.json"
        try:
            self._client().put_object(
                Bucket=self.state_bucket,
                Key=key,
                Body=json.dumps({
                    "incident_id": incident_id,
                    "event_type": event_type,
                    "claimed_at": _iso(_utc_now()),
                }, separators=(",", ":")).encode("utf-8"),
                ContentType="application/json",
                ServerSideEncryption="AES256",
                IfNoneMatch="*",
            )
            return True
        except Exception as error:
            if self._error_code(error) in {"PreconditionFailed", "412", "ConditionalRequestConflict", "409"}:
                return False
            logger.exception(
                "infrastructure_notification_claim_failed",
                extra={"event": "infrastructure_notification_claim_failed", "incident_id": incident_id},
            )
            return False

    @staticmethod
    def _category(observation: HealthObservation, *, recovery: bool = False) -> str:
        if recovery:
            return "Infrastructure Healthy"
        if observation.status == "critical":
            return "Infrastructure Critical"
        if observation.key.endswith("latency") or observation.confidence == "low":
            return "Infrastructure Review"
        return "Infrastructure Degraded"

    @staticmethod
    def _incident_event(incident: dict[str, Any], observation: HealthObservation, *, recovery: bool) -> dict[str, Any]:
        return {
            "event_type": "recovery" if recovery else "opened",
            "category": ProductionHealthEvaluator._category(observation, recovery=recovery),
            "incident_id": incident["incident_id"],
            "subsystem": observation.subsystem,
            "signal": observation.key,
            "started_at": incident["started_at"],
            "what_changed": (
                f"{observation.subsystem.replace('_', ' ').title()} recovered after persistent degradation."
                if recovery else observation.evidence[0]
            ),
            "evidence": observation.evidence,
            "recommended_first_check": observation.recommended_first_check,
            "impact": "The previously reported infrastructure impact has recovered." if recovery else observation.impact,
        }

    def _find_incident(self, incident_id: str | None) -> dict[str, Any] | None:
        if not incident_id:
            return None
        return next((item for item in self._state["incidents"] if item.get("incident_id") == incident_id), None)

    def evaluate(self, observations: list[HealthObservation], now: datetime | None = None) -> dict[str, Any]:
        observed_at = (now or _utc_now()).astimezone(UTC)
        events: list[tuple[dict[str, Any], dict[str, Any]]] = []
        with self._lock:
            if self.state_bucket:
                self._state = self._load_state()
            for observation in observations:
                policy = self.policies.get(observation.key, PersistencePolicy(3, 120))
                signal = self._state["signals"].setdefault(observation.key, {
                    "consecutive_failures": 0,
                    "first_failure_at": None,
                    "last_observed_at": None,
                    "last_status": "healthy",
                    "active_incident_id": None,
                })
                signal["last_observed_at"] = _iso(observed_at)
                signal["last_status"] = observation.status
                signal["last_evidence"] = observation.evidence
                active = self._find_incident(signal.get("active_incident_id"))

                if observation.status == "healthy":
                    if active and active.get("status") == "active":
                        active["status"] = "resolved"
                        active["resolved_at"] = _iso(observed_at)
                        active["recovery_evidence"] = observation.evidence
                        event = self._incident_event(active, observation, recovery=True)
                        events.append((event, active))
                    signal.update({"consecutive_failures": 0, "first_failure_at": None, "active_incident_id": None})
                    continue

                previous_status = str(signal.get("previous_failure_status") or "")
                if not signal.get("first_failure_at") or previous_status == "healthy":
                    signal["first_failure_at"] = _iso(observed_at)
                    signal["consecutive_failures"] = 1
                else:
                    signal["consecutive_failures"] = int(signal.get("consecutive_failures") or 0) + 1
                signal["previous_failure_status"] = observation.status
                first_failure = _parse_time(signal.get("first_failure_at")) or observed_at
                elapsed = max(0.0, (observed_at - first_failure).total_seconds())
                persistent = (
                    int(signal["consecutive_failures"]) >= policy.consecutive_failures
                    and elapsed >= policy.minimum_duration_seconds
                )
                if persistent and (not active or active.get("status") != "active"):
                    incident_id = f"{observation.key}:{int(first_failure.timestamp())}"
                    incident = {
                        "incident_id": incident_id,
                        "signal": observation.key,
                        "subsystem": observation.subsystem,
                        "severity": observation.status,
                        "category": self._category(observation),
                        "status": "active",
                        "started_at": _iso(first_failure),
                        "detected_at": _iso(observed_at),
                        "resolved_at": None,
                        "evidence": observation.evidence,
                        "recommended_first_check": observation.recommended_first_check,
                        "impact": observation.impact,
                        "consecutive_failures": signal["consecutive_failures"],
                        "notification_sent_at": None,
                        "delivery_results": [],
                    }
                    self._state["incidents"].append(incident)
                    self._state["incidents"] = self._state["incidents"][-200:]
                    signal["active_incident_id"] = incident_id
                    event = self._incident_event(incident, observation, recovery=False)
                    events.append((event, incident))

            notification_status = self.notifier.status()
            failed_deliveries = [item for item in notification_status.get("last_delivery_results") or [] if not item.get("delivered")]
            notification_observation = HealthObservation(
                key="notification_delivery",
                subsystem="notifications",
                status="degraded" if failed_deliveries else "healthy",
                evidence=(
                    [f"{len(failed_deliveries)} configured notification adapter(s) failed on the last transition."]
                    if failed_deliveries else [f"Configured notification adapters: {', '.join(notification_status.get('configured_adapters') or ['console'])}."]
                ),
                recommended_first_check="Verify the failing notification endpoint, credentials, and network access.",
                impact="Some operators may not receive infrastructure notifications." if failed_deliveries else "Notification delivery has no recorded failure.",
                metadata=notification_status,
            )
            all_observations = [*observations, notification_observation]
            snapshot = self._build_snapshot(all_observations, observed_at)
            self._state["last_snapshot"] = snapshot
            self._save_state()

        for event, incident in events:
            if not self._claim_notification(event):
                continue
            results = self.notifier.dispatch(event)
            with self._lock:
                record = {
                    **event,
                    "sent_at": _iso(observed_at),
                    "delivery_results": results,
                }
                self._state["notifications"].append(record)
                self._state["notifications"] = self._state["notifications"][-200:]
                incident["delivery_results"] = results
                if event["event_type"] == "opened":
                    incident["notification_sent_at"] = _iso(observed_at)
                else:
                    incident["recovery_notification_sent_at"] = _iso(observed_at)
                self._state["last_snapshot"] = self._build_snapshot(
                    [*observations, HealthObservation(
                        key="notification_delivery",
                        subsystem="notifications",
                        status="degraded" if any(not result.get("delivered") for result in results) else "healthy",
                        evidence=[
                            "One or more notification adapters failed on the latest state transition."
                            if any(not result.get("delivered") for result in results)
                            else "Latest infrastructure state transition was delivered to configured adapters."
                        ],
                        recommended_first_check="Inspect infrastructure notification delivery logs.",
                        impact="Some notification channels may have missed the transition." if any(not result.get("delivered") for result in results) else "Notification delivery succeeded.",
                        metadata={"configured_adapters": self.notifier.status().get("configured_adapters"), "last_delivery_results": results},
                    )],
                    observed_at,
                )
                self._save_state()
        return self.snapshot()

    def _build_snapshot(self, observations: list[HealthObservation], observed_at: datetime) -> dict[str, Any]:
        subsystems: dict[str, dict[str, Any]] = {}
        for subsystem in SUBSYSTEMS:
            selected = [item for item in observations if item.subsystem == subsystem]
            worst = max(selected, key=lambda item: _STATUS_RANK.get(item.status, 0), default=None)
            subsystems[subsystem] = {
                "status": worst.status if worst else "healthy",
                "evidence": [evidence for item in selected for evidence in item.evidence],
                "latency_ms": max((item.latency_ms for item in selected if item.latency_ms is not None), default=None),
                "checks": {item.key: item.as_dict() for item in selected},
            }
        overall = max((item.status for item in observations), key=lambda status: _STATUS_RANK.get(status, 0), default="healthy")
        current_failures = [
            signal for signal in self._state["signals"].values()
            if signal.get("first_failure_at") and signal.get("last_status") != "healthy"
        ]
        degraded_since = min((signal["first_failure_at"] for signal in current_failures), default=None)
        active_incidents = [item for item in self._state["incidents"] if item.get("status") == "active"]
        confidence = "high"
        if any(item.confidence == "low" for item in observations):
            confidence = "medium"
        return {
            "overall_status": overall,
            "category": (
                "Infrastructure Critical" if overall == "critical" else
                "Infrastructure Degraded" if overall == "degraded" else
                "Infrastructure Healthy"
            ),
            "subsystems": subsystems,
            "evidence": [evidence for item in observations if item.status != "healthy" for evidence in item.evidence],
            "degraded_since": degraded_since,
            "confidence": confidence,
            "observed_at": _iso(observed_at),
            "current_alerts": active_incidents,
            "pending_validation": [
                {
                    "signal": key,
                    "status": signal.get("last_status"),
                    "first_failure_at": signal.get("first_failure_at"),
                    "consecutive_failures": signal.get("consecutive_failures"),
                    "policy": asdict(self.policies.get(key, PersistencePolicy(3, 120))),
                }
                for key, signal in self._state["signals"].items()
                if signal.get("last_status") != "healthy" and not signal.get("active_incident_id")
            ],
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._state.get("last_snapshot")
            if snapshot is None:
                now = _utc_now()
                snapshot = self._build_snapshot([], now)
            copied = json.loads(json.dumps(snapshot))
            copied["incidents"] = list(reversed(self._state["incidents"][-100:]))
            copied["notification_history"] = list(reversed(self._state["notifications"][-100:]))
            return copied


class ProductionHealthMonitor:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.probe = ProductionHealthProbe(settings)
        self.notifier = InfrastructureNotificationEngine.from_settings(settings)
        self.evaluator = ProductionHealthEvaluator(
            state_path=Path(settings.runtime_dir) / "production_health_state.json",
            notifier=self.notifier,
            state_bucket=os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", ""),
        )
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="neraium-production-health-monitor")
        self._thread.start()
        logger.info("production_health_monitor_started", extra={"event": "production_health_monitor_started"})

    def stop(self, timeout_seconds: float = 10.0) -> bool:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=max(float(timeout_seconds), 0.0))
        stopped = self._thread is None or not self._thread.is_alive()
        if stopped:
            self._thread = None
            logger.info("production_health_monitor_stopped", extra={"event": "production_health_monitor_stopped"})
        return stopped

    def evaluate_once(self) -> dict[str, Any]:
        observations = self.probe.collect()
        snapshot = self.evaluator.evaluate(observations)
        logger.info(
            "production_health_evaluated",
            extra={
                "event": "production_health_evaluated",
                "overall_status": snapshot.get("overall_status"),
                "active_incident_count": len(snapshot.get("current_alerts") or []),
                "pending_validation_count": len(snapshot.get("pending_validation") or []),
            },
        )
        return snapshot

    def _loop(self) -> None:
        interval = max(float(getattr(self.settings, "infrastructure_monitor_interval_seconds", 60.0)), 5.0)
        while not self._stop.is_set():
            try:
                self.evaluate_once()
            except Exception:
                logger.exception("production_health_evaluation_failed", extra={"event": "production_health_evaluation_failed"})
            self._stop.wait(interval)

    def snapshot(self) -> dict[str, Any]:
        return self.evaluator.snapshot()


_MONITOR_LOCK = threading.RLock()
_MONITOR: ProductionHealthMonitor | None = None


def start_production_health_monitor(settings: Settings) -> bool:
    global _MONITOR
    if not bool(getattr(settings, "infrastructure_monitor_enabled", False)):
        return False
    if str(settings.process_role).lower() not in {"api", "all", "monolith"}:
        return False
    with _MONITOR_LOCK:
        if _MONITOR is None:
            _MONITOR = ProductionHealthMonitor(settings)
        _MONITOR.start()
    return True


def stop_production_health_monitor(timeout_seconds: float = 10.0) -> bool:
    global _MONITOR
    with _MONITOR_LOCK:
        if _MONITOR is None:
            return True
        stopped = _MONITOR.stop(timeout_seconds)
        if stopped:
            _MONITOR = None
        return stopped


def production_health_snapshot(settings: Settings | None = None) -> dict[str, Any]:
    with _MONITOR_LOCK:
        if _MONITOR is not None:
            snapshot = _MONITOR.snapshot()
            snapshot["monitoring_enabled"] = True
            return snapshot
    if settings is None:
        now = _utc_now()
        return {
            "overall_status": "healthy",
            "category": "Infrastructure Healthy",
            "subsystems": {subsystem: {"status": "healthy", "evidence": [], "latency_ms": None, "checks": {}} for subsystem in SUBSYSTEMS},
            "evidence": [],
            "degraded_since": None,
            "confidence": "low",
            "observed_at": _iso(now),
            "current_alerts": [],
            "pending_validation": [],
            "incidents": [],
            "notification_history": [],
            "monitoring_enabled": False,
        }
    evaluator = ProductionHealthEvaluator(
        state_path=Path(settings.runtime_dir) / "production_health_state.json",
        notifier=InfrastructureNotificationEngine.from_settings(settings),
        state_bucket=os.getenv("NERAIUM_UPLOAD_STATE_BUCKET", ""),
    )
    snapshot = evaluator.snapshot()
    snapshot["monitoring_enabled"] = bool(getattr(settings, "infrastructure_monitor_enabled", False))
    return snapshot
