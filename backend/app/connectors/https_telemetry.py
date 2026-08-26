"""Hardened, generic public-HTTPS telemetry retrieval provider.

Only GET requests are issued. All destinations are re-authorized immediately
before every attempt, redirects and environment proxies are disabled, and
credential headers are constructed solely from a server-resolved opaque
secret binding.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
import json
import random
import re
import time
from typing import Any, Callable, Mapping, Sequence

import httpx

from app.connectors.base import (
    BoundedBackfillRange,
    ConnectorCheckpoint,
    ConnectorExecutionContext,
    ConnectorFailureKind,
    ConnectorPage,
    ConnectorProviderDescriptor,
    ConnectorRecordIssue,
    ConnectorValidationResult,
    DiscoveredSignal,
    ProviderHealthResult,
    RawObservationEnvelope,
    TelemetryConnector,
    TelemetryConnectorError,
)
from app.services.telemetry_domain import (
    ConnectorCapability,
    ConnectorType,
    is_sensitive_telemetry_key,
    reject_sensitive_telemetry_fields,
)
from app.services.telemetry_egress import (
    AuthorizedTelemetryRequest,
    TelemetryEgressError,
    TelemetryEgressPolicy,
    TelemetryRequestLimits,
    require_request_budget,
)
from app.services.telemetry_secrets import (
    ResolvedSecret,
    TelemetrySecretError,
    TelemetrySecretStore,
)


_FIELD_PATH_RE = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){0,15}$")
_QUERY_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_RETRYABLE_STATUS = frozenset({408, 429, 500, 502, 503, 504})
_PERMANENT_AUTH_STATUS = frozenset({401, 403})
_MAX_BACKFILL_DAYS = 366
_ALLOWED_CONFIG_KEYS = frozenset(
    {
        "base_url",
        "request_path",
        "static_query",
        "authentication_scheme",
        "records_path",
        "timestamp_field",
        "value_field",
        "external_tag_id_field",
        "external_tag_name_field",
        "display_label_field",
        "unit_field",
        "quality_field",
        "event_id_field",
        "metadata_fields",
        "next_cursor_path",
        "cursor_query_parameter",
        "next_page_path",
        "page_size_query_parameter",
        "page_size",
        "start_time_query_parameter",
        "end_time_query_parameter",
        "timeout_seconds",
        "max_response_bytes",
        "max_pages",
        "max_records",
        "max_retries",
        "max_retry_after_seconds",
    }
)


@dataclass(frozen=True, slots=True)
class _HttpsConfig:
    base_url: str
    request_path: str
    static_query: Mapping[str, str | int | float | bool]
    authentication_scheme: str
    records_path: str | None
    timestamp_field: str
    value_field: str
    external_tag_id_field: str
    external_tag_name_field: str | None
    display_label_field: str | None
    unit_field: str | None
    quality_field: str | None
    event_id_field: str | None
    metadata_fields: tuple[str, ...]
    next_cursor_path: str | None
    cursor_query_parameter: str | None
    next_page_path: str | None
    page_size_query_parameter: str | None
    page_size: int | None
    start_time_query_parameter: str | None
    end_time_query_parameter: str | None
    limits: TelemetryRequestLimits
    max_retries: int
    max_retry_after_seconds: float

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> _HttpsConfig:
        try:
            reject_sensitive_telemetry_fields(
                raw,
                code="unsafe_https_connector_configuration",
                path="configuration",
            )
        except ValueError as error:
            raise _configuration_error("credential_fields_not_allowed") from error
        unknown = set(raw) - _ALLOWED_CONFIG_KEYS
        if unknown:
            raise _configuration_error("unknown_configuration_field")
        try:
            serialized_size = len(json.dumps(dict(raw), default=str).encode("utf-8"))
        except (TypeError, ValueError):
            raise _configuration_error("configuration_not_serializable") from None
        if serialized_size > 64 * 1024:
            raise _configuration_error("configuration_too_large")

        base_url = _required_string(raw, "base_url", maximum=2_048)
        request_path = _required_string(raw, "request_path", maximum=2_048)
        if not request_path.startswith("/") or request_path.startswith("//"):
            raise _configuration_error("request_path_invalid")
        authentication_scheme = str(raw.get("authentication_scheme") or "none").strip().lower()
        if authentication_scheme not in {"none", "bearer", "api_key"}:
            raise _configuration_error("authentication_scheme_invalid")

        static_query = raw.get("static_query") or {}
        if not isinstance(static_query, Mapping):
            raise _configuration_error("static_query_invalid")
        normalized_query: dict[str, str | int | float | bool] = {}
        for raw_name, value in static_query.items():
            name = str(raw_name)
            if not _QUERY_NAME_RE.fullmatch(name):
                raise _configuration_error("query_parameter_name_invalid")
            if not isinstance(value, (str, int, float, bool)) or len(str(value)) > 1_024:
                raise _configuration_error("query_parameter_value_invalid")
            normalized_query[name] = value

        field_names: dict[str, str | None] = {}
        for key in (
            "records_path",
            "external_tag_name_field",
            "display_label_field",
            "unit_field",
            "quality_field",
            "event_id_field",
            "next_cursor_path",
            "next_page_path",
        ):
            field_names[key] = _optional_field_path(raw.get(key), key=key)
        for key in ("timestamp_field", "value_field", "external_tag_id_field"):
            field_names[key] = _required_field_path(raw, key)

        if field_names["next_cursor_path"] and field_names["next_page_path"]:
            raise _configuration_error("pagination_modes_conflict")
        cursor_parameter = _optional_query_name(raw.get("cursor_query_parameter"))
        if bool(field_names["next_cursor_path"]) != bool(cursor_parameter):
            raise _configuration_error("cursor_pagination_incomplete")

        page_size_parameter = _optional_query_name(raw.get("page_size_query_parameter"))
        page_size_value = raw.get("page_size")
        page_size: int | None = None
        if page_size_value is not None:
            if isinstance(page_size_value, bool):
                raise _configuration_error("page_size_invalid")
            try:
                page_size = int(page_size_value)
            except (TypeError, ValueError):
                raise _configuration_error("page_size_invalid") from None
            if not 1 <= page_size <= 10_000:
                raise _configuration_error("page_size_invalid")
        if bool(page_size_parameter) != bool(page_size):
            raise _configuration_error("page_size_configuration_incomplete")

        metadata_fields = raw.get("metadata_fields") or ()
        if not isinstance(metadata_fields, (list, tuple)) or len(metadata_fields) > 20:
            raise _configuration_error("metadata_fields_invalid")
        normalized_metadata = tuple(
            _required_field_path({"field": value}, "field") for value in metadata_fields
        )

        limits = TelemetryRequestLimits(
            timeout_seconds=float(raw.get("timeout_seconds", 15.0)),
            max_response_bytes=int(raw.get("max_response_bytes", 5 * 1024 * 1024)),
            max_pages=int(raw.get("max_pages", 50)),
            max_records=int(raw.get("max_records", 50_000)),
        )
        max_retries = int(raw.get("max_retries", 2))
        max_retry_after = float(raw.get("max_retry_after_seconds", 30.0))
        if not 0 <= max_retries <= 3:
            raise _configuration_error("retry_limit_invalid")
        if not 0.0 <= max_retry_after <= 60.0:
            raise _configuration_error("retry_after_limit_invalid")

        return cls(
            base_url=base_url,
            request_path=request_path,
            static_query=normalized_query,
            authentication_scheme=authentication_scheme,
            records_path=field_names["records_path"],
            timestamp_field=str(field_names["timestamp_field"]),
            value_field=str(field_names["value_field"]),
            external_tag_id_field=str(field_names["external_tag_id_field"]),
            external_tag_name_field=field_names["external_tag_name_field"],
            display_label_field=field_names["display_label_field"],
            unit_field=field_names["unit_field"],
            quality_field=field_names["quality_field"],
            event_id_field=field_names["event_id_field"],
            metadata_fields=normalized_metadata,
            next_cursor_path=field_names["next_cursor_path"],
            cursor_query_parameter=cursor_parameter,
            next_page_path=field_names["next_page_path"],
            page_size_query_parameter=page_size_parameter,
            page_size=page_size,
            start_time_query_parameter=_optional_query_name(raw.get("start_time_query_parameter")),
            end_time_query_parameter=_optional_query_name(raw.get("end_time_query_parameter")),
            limits=limits,
            max_retries=max_retries,
            max_retry_after_seconds=max_retry_after,
        )


@dataclass(slots=True)
class _FetchBudget:
    """Aggregate retry, backoff, and elapsed-time budget for one fetch."""

    deadline: float
    max_retries: int
    max_backoff_seconds: float
    retries_used: int = 0
    backoff_seconds: float = 0.0
    auth_refreshed: bool = False

    def remaining_seconds(self, monotonic: Callable[[], float]) -> float:
        remaining = self.deadline - monotonic()
        if remaining <= 0.0:
            raise _budget_error("elapsed_time_budget_exceeded")
        return remaining

    def reserve_backoff(
        self,
        delay: float,
        *,
        monotonic: Callable[[], float],
    ) -> None:
        remaining_elapsed = self.remaining_seconds(monotonic)
        if (
            self.backoff_seconds + delay > self.max_backoff_seconds
            or delay >= remaining_elapsed
        ):
            raise _budget_error("retry_backoff_budget_exceeded")
        self.backoff_seconds += delay


class HttpsTelemetryConnector(TelemetryConnector):
    """First production connector: bounded read-only JSON over public HTTPS."""

    def __init__(
        self,
        *,
        egress_policy: TelemetryEgressPolicy | None = None,
        secret_store: TelemetrySecretStore | None = None,
        transport: httpx.BaseTransport | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._egress_policy = egress_policy or TelemetryEgressPolicy()
        self._secret_store = secret_store
        self._transport = transport
        self._sleeper = sleeper
        self._jitter = jitter
        self._now = now
        self._monotonic = monotonic

    @classmethod
    def descriptor(cls) -> ConnectorProviderDescriptor:
        return ConnectorProviderDescriptor(
            connector_type=ConnectorType.HTTPS_TELEMETRY,
            display_name="HTTPS telemetry API",
            description="Read telemetry from a bounded public HTTPS JSON API.",
            capabilities=frozenset(
                {
                    ConnectorCapability.VALIDATE,
                    ConnectorCapability.DISCOVER_SIGNALS,
                    ConnectorCapability.INCREMENTAL_POLLING,
                    ConnectorCapability.BOUNDED_BACKFILL,
                    ConnectorCapability.HEALTH_CHECK,
                }
            ),
            production_available=True,
        )

    def validate(self, context: ConnectorExecutionContext) -> ConnectorValidationResult:
        page = self._fetch(context, operation="validate", checkpoint=None, time_range=None)
        return ConnectorValidationResult(
            valid=True,
            reachable=True,
            authenticated=True,
            observations_sampled=len(page.observations),
        )

    def discover_signals(
        self,
        context: ConnectorExecutionContext,
        *,
        checkpoint: ConnectorCheckpoint | None = None,
    ) -> ConnectorPage:
        page = self._fetch(context, operation="discovery", checkpoint=checkpoint, time_range=None)
        seen: set[str] = set()
        signals: list[DiscoveredSignal] = []
        for observation in page.observations:
            if observation.external_tag_id in seen:
                continue
            seen.add(observation.external_tag_id)
            signals.append(
                DiscoveredSignal(
                    external_tag_id=observation.external_tag_id,
                    external_tag_name=observation.external_tag_name,
                    reported_unit=observation.reported_unit,
                )
            )
        return ConnectorPage(
            observations=page.observations,
            signals=tuple(signals),
            issues=page.issues,
            next_checkpoint=page.next_checkpoint,
            has_more=page.has_more,
            pages_read=page.pages_read,
            response_bytes=page.response_bytes,
            retry_count=page.retry_count,
        )

    def fetch_incremental(
        self,
        context: ConnectorExecutionContext,
        *,
        checkpoint: ConnectorCheckpoint | None = None,
    ) -> ConnectorPage:
        return self._fetch(context, operation="incremental", checkpoint=checkpoint, time_range=None)

    def fetch_backfill(
        self,
        context: ConnectorExecutionContext,
        *,
        time_range: BoundedBackfillRange,
        checkpoint: ConnectorCheckpoint | None = None,
    ) -> ConnectorPage:
        if time_range.end_at - time_range.start_at > timedelta(days=_MAX_BACKFILL_DAYS):
            raise _configuration_error("backfill_range_too_large")
        return self._fetch(
            context,
            operation="backfill",
            checkpoint=checkpoint,
            time_range=time_range,
        )

    def health(self, context: ConnectorExecutionContext) -> ProviderHealthResult:
        try:
            self.validate(context)
        except TelemetryConnectorError as error:
            return ProviderHealthResult(
                # Only an authentication rejection or upstream HTTP status
                # proves the destination answered. Configuration, payload,
                # budget, and network failures remain conservatively unknown.
                reachable=error.kind
                in {
                    ConnectorFailureKind.AUTHENTICATION,
                    ConnectorFailureKind.PROVIDER,
                    ConnectorFailureKind.RATE_LIMITED,
                },
                authenticated=error.kind
                in {
                    ConnectorFailureKind.PROVIDER,
                    ConnectorFailureKind.RATE_LIMITED,
                },
                provider_healthy=False,
                checked_at=self._now(),
                code=error.code,
            )
        return ProviderHealthResult(
            reachable=True,
            authenticated=True,
            provider_healthy=True,
            checked_at=self._now(),
            code="healthy",
        )

    def _fetch(
        self,
        context: ConnectorExecutionContext,
        *,
        operation: str,
        checkpoint: ConnectorCheckpoint | None,
        time_range: BoundedBackfillRange | None,
    ) -> ConnectorPage:
        try:
            config = _HttpsConfig.from_mapping(context.configuration)
            # Destination authorization remains centralized in the injected
            # policy. Per-connection limits may only reduce transport/run
            # budgets and are enforced independently below.
            policy = self._egress_policy
            central_limits = policy.limits
            if (
                config.limits.timeout_seconds > central_limits.timeout_seconds
                or config.limits.max_response_bytes > central_limits.max_response_bytes
                or config.limits.max_pages > central_limits.max_pages
                or config.limits.max_records > central_limits.max_records
            ):
                raise _configuration_error("central_egress_limit_exceeded")
            query = dict(config.static_query)
            if config.page_size_query_parameter and config.page_size is not None:
                query[config.page_size_query_parameter] = config.page_size
            if time_range is not None:
                if not config.start_time_query_parameter or not config.end_time_query_parameter:
                    raise _configuration_error("backfill_parameters_not_configured")
                query[config.start_time_query_parameter] = time_range.start_at.isoformat()
                query[config.end_time_query_parameter] = time_range.end_at.isoformat()
            current_url = policy.build_relative_url(config.base_url, config.request_path, query=query)
        except TelemetryConnectorError:
            raise
        except TelemetryEgressError as error:
            raise _egress_connector_error(error) from None
        except (TypeError, ValueError):
            raise _configuration_error("configuration_invalid") from None

        cursor = checkpoint.cursor if checkpoint is not None else None
        if cursor:
            if cursor.startswith("path:"):
                try:
                    current_url = policy.pagination_url(current_url, cursor[5:])
                except TelemetryEgressError as error:
                    raise _egress_connector_error(error) from None
            elif cursor.startswith("cursor:") and config.cursor_query_parameter:
                query[config.cursor_query_parameter] = cursor[7:]
                try:
                    current_url = policy.build_relative_url(
                        config.base_url,
                        config.request_path,
                        query=query,
                    )
                except TelemetryEgressError as error:
                    raise _egress_connector_error(error) from None
            else:
                raise _configuration_error("checkpoint_cursor_invalid")

        budget = _FetchBudget(
            deadline=self._monotonic() + config.limits.timeout_seconds,
            max_retries=config.max_retries,
            max_backoff_seconds=config.max_retry_after_seconds,
        )
        secret = self._resolve_secret(context, config)
        observations: list[RawObservationEnvelope] = []
        issues: list[ConnectorRecordIssue] = []
        records_seen = 0
        total_bytes = 0
        total_retries = 0
        pages_read = 0
        next_checkpoint: ConnectorCheckpoint | None = None
        has_more = False

        while True:
            payload, response_bytes, retries, secret = self._request_json(
                policy=policy,
                url=current_url,
                config=config,
                context=context,
                secret=secret,
                budget=budget,
            )
            pages_read += 1
            total_bytes += response_bytes
            total_retries += retries
            records = _extract_records(payload, config.records_path)
            record_offset = records_seen
            records_seen += len(records)
            try:
                require_request_budget(
                    limits=config.limits,
                    pages=pages_read,
                    records=records_seen,
                    response_bytes=total_bytes,
                )
            except TelemetryEgressError as error:
                raise _budget_error(error.code) from None
            for record_index, record in enumerate(records):
                try:
                    observations.append(_observation(record, config))
                except TelemetryConnectorError as error:
                    issues.append(
                        ConnectorRecordIssue(
                            record_index=record_offset + record_index,
                            code=error.code,
                            safe_message=error.safe_message,
                        )
                    )
            budget.remaining_seconds(self._monotonic)

            pagination = _pagination_checkpoint(payload, config)
            if pagination is None:
                has_more = False
                next_checkpoint = ConnectorCheckpoint(
                    cursor=None,
                    high_water_at=checkpoint.high_water_at if checkpoint else None,
                )
                break
            has_more = True
            next_checkpoint = pagination
            if pages_read >= config.limits.max_pages:
                break
            try:
                if pagination.cursor and pagination.cursor.startswith("path:"):
                    current_url = policy.pagination_url(current_url, pagination.cursor[5:])
                elif pagination.cursor and pagination.cursor.startswith("cursor:"):
                    query[config.cursor_query_parameter or ""] = pagination.cursor[7:]
                    current_url = policy.build_relative_url(
                        config.base_url,
                        config.request_path,
                        query=query,
                    )
                else:
                    raise _configuration_error("pagination_cursor_invalid")
            except TelemetryEgressError as error:
                raise _egress_connector_error(error) from None

        return ConnectorPage(
            observations=tuple(observations),
            issues=tuple(issues),
            next_checkpoint=next_checkpoint,
            has_more=has_more,
            pages_read=pages_read,
            response_bytes=total_bytes,
            retry_count=total_retries,
        )

    def _resolve_secret(
        self,
        context: ConnectorExecutionContext,
        config: _HttpsConfig,
    ) -> ResolvedSecret | None:
        if config.authentication_scheme == "none":
            return None
        if context.secret_binding is None or self._secret_store is None:
            raise TelemetryConnectorError(
                "credentials_not_configured",
                kind=ConnectorFailureKind.NOT_CONFIGURED,
                safe_message="Telemetry credentials are not configured.",
            )
        try:
            return self._secret_store.resolve(context.secret_binding)
        except TelemetrySecretError:
            raise TelemetryConnectorError(
                "credentials_unavailable",
                kind=ConnectorFailureKind.AUTHENTICATION,
                safe_message="Telemetry credentials are unavailable.",
            ) from None

    def _request_json(
        self,
        *,
        policy: TelemetryEgressPolicy,
        url: str,
        config: _HttpsConfig,
        context: ConnectorExecutionContext,
        secret: ResolvedSecret | None,
        budget: _FetchBudget,
    ) -> tuple[Any, int, int, ResolvedSecret | None]:
        retries_at_start = budget.retries_used
        while True:
            budget.remaining_seconds(self._monotonic)
            headers = _request_headers(config, secret)
            try:
                authorized = policy.authorize_request(url, method="GET", headers=headers)
            except TelemetryEgressError as error:
                raise _egress_connector_error(error) from None
            try:
                response, content = self._execute_request(
                    authorized,
                    headers=headers,
                    limits=config.limits,
                    timeout_seconds=budget.remaining_seconds(self._monotonic),
                )
                budget.remaining_seconds(self._monotonic)
            except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError):
                if budget.retries_used >= budget.max_retries:
                    raise TelemetryConnectorError(
                        "network_retry_exhausted",
                        kind=ConnectorFailureKind.NETWORK,
                        retryable=True,
                        safe_message="Telemetry source could not be reached within the retry limit.",
                    ) from None
                self._backoff(
                    budget.retries_used,
                    retry_after=None,
                    config=config,
                    budget=budget,
                )
                budget.retries_used += 1
                continue
            except httpx.HTTPError:
                raise TelemetryConnectorError(
                    "network_request_failed",
                    kind=ConnectorFailureKind.NETWORK,
                    retryable=False,
                    safe_message="Telemetry source could not be reached.",
                ) from None

            status = response.status_code
            try:
                policy.reject_redirect(status_code=status, location=response.headers.get("location"))
            except TelemetryEgressError as error:
                raise _egress_connector_error(error) from None
            if status in _PERMANENT_AUTH_STATUS:
                if (
                    not budget.auth_refreshed
                    and context.secret_binding is not None
                    and self._secret_store is not None
                ):
                    try:
                        secret = self._secret_store.resolve_after_auth_failure(context.secret_binding)
                    except TelemetrySecretError:
                        raise TelemetryConnectorError(
                            "authentication_failed",
                            kind=ConnectorFailureKind.AUTHENTICATION,
                            safe_message="Telemetry source authentication failed.",
                        ) from None
                    budget.auth_refreshed = True
                    continue
                raise TelemetryConnectorError(
                    "authentication_failed",
                    kind=ConnectorFailureKind.AUTHENTICATION,
                    safe_message="Telemetry source authentication failed.",
                )
            if status in _RETRYABLE_STATUS:
                retry_after = _retry_after_seconds(
                    response.headers.get("retry-after"),
                    now=self._now(),
                    maximum=config.max_retry_after_seconds,
                )
                if budget.retries_used >= budget.max_retries:
                    kind = (
                        ConnectorFailureKind.RATE_LIMITED
                        if status == 429
                        else ConnectorFailureKind.PROVIDER
                    )
                    raise TelemetryConnectorError(
                        "provider_retry_exhausted",
                        kind=kind,
                        retryable=True,
                        safe_message="Telemetry source did not recover within the retry limit.",
                        retry_after_seconds=retry_after,
                    )
                self._backoff(
                    budget.retries_used,
                    retry_after=retry_after,
                    config=config,
                    budget=budget,
                )
                budget.retries_used += 1
                continue
            if status < 200 or status >= 300:
                raise TelemetryConnectorError(
                    "provider_request_rejected",
                    kind=ConnectorFailureKind.PROVIDER,
                    safe_message="Telemetry source rejected the read request.",
                )
            try:
                payload = json.loads(content)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise TelemetryConnectorError(
                    "payload_invalid_json",
                    kind=ConnectorFailureKind.PAYLOAD,
                    safe_message="Telemetry source returned an invalid response.",
                ) from None
            return payload, len(content), budget.retries_used - retries_at_start, secret

    def _execute_request(
        self,
        authorized: AuthorizedTelemetryRequest,
        *,
        headers: Mapping[str, str],
        limits: TelemetryRequestLimits,
        timeout_seconds: float,
    ) -> tuple[httpx.Response, bytes]:
        # Authorization and connection must use the same DNS result. Sending
        # the approved IP as the URL host prevents httpcore from resolving the
        # attacker-controlled hostname again, while Host and sni_hostname keep
        # HTTP routing and TLS certificate verification bound to the original
        # authorized origin.
        origin_url = httpx.URL(authorized.url)
        pinned_url = origin_url.copy_with(host=authorized.resolved_addresses[0])
        request_headers = dict(headers)
        request_headers["host"] = origin_url.netloc.decode("ascii")
        timeout = httpx.Timeout(min(limits.timeout_seconds, timeout_seconds))
        with httpx.Client(
            timeout=timeout,
            transport=self._transport,
            follow_redirects=authorized.follow_redirects,
            trust_env=authorized.trust_env,
            verify=authorized.verify_tls,
        ) as client:
            with client.stream(
                authorized.method,
                pinned_url,
                headers=request_headers,
                extensions={"sni_hostname": authorized.hostname},
            ) as response:
                declared = response.headers.get("content-length")
                if declared is not None:
                    try:
                        declared_size = int(declared)
                    except ValueError:
                        raise TelemetryConnectorError(
                            "content_length_invalid",
                            kind=ConnectorFailureKind.PAYLOAD,
                            safe_message="Telemetry source returned an invalid response.",
                        ) from None
                    if declared_size < 0 or declared_size > limits.max_response_bytes:
                        raise _budget_error("response_budget_exceeded")
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > limits.max_response_bytes:
                        raise _budget_error("response_budget_exceeded")
                return response, bytes(body)

    def _backoff(
        self,
        attempt: int,
        *,
        retry_after: float | None,
        config: _HttpsConfig,
        budget: _FetchBudget,
    ) -> None:
        ceiling = min(0.5 * (2**attempt), config.max_retry_after_seconds)
        delay = retry_after if retry_after is not None else self._jitter(0.0, ceiling)
        bounded_delay = min(max(delay, 0.0), config.max_retry_after_seconds)
        budget.reserve_backoff(bounded_delay, monotonic=self._monotonic)
        self._sleeper(bounded_delay)
        budget.remaining_seconds(self._monotonic)


def _configuration_error(code: str) -> TelemetryConnectorError:
    return TelemetryConnectorError(
        code,
        kind=ConnectorFailureKind.CONFIGURATION,
        safe_message="Telemetry connector configuration is invalid.",
    )


def _budget_error(code: str) -> TelemetryConnectorError:
    return TelemetryConnectorError(
        code,
        kind=ConnectorFailureKind.BUDGET,
        safe_message="Telemetry retrieval exceeded a configured safety limit.",
    )


def _egress_connector_error(error: TelemetryEgressError) -> TelemetryConnectorError:
    return TelemetryConnectorError(
        error.code,
        kind=ConnectorFailureKind.CONFIGURATION,
        safe_message="Telemetry destination is not allowed.",
    )


def _required_string(raw: Mapping[str, Any], key: str, *, maximum: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise _configuration_error(f"{key}_invalid")
    return value.strip()


def _optional_field_path(value: Any, *, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _FIELD_PATH_RE.fullmatch(value):
        raise _configuration_error(f"{key}_invalid")
    if any(is_sensitive_telemetry_key(segment) for segment in value.split(".")):
        raise _configuration_error(f"{key}_credential_path_not_allowed")
    return value


def _required_field_path(raw: Mapping[str, Any], key: str) -> str:
    value = _optional_field_path(raw.get(key), key=key)
    if value is None:
        raise _configuration_error(f"{key}_required")
    return value


def _optional_query_name(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _QUERY_NAME_RE.fullmatch(value):
        raise _configuration_error("query_parameter_name_invalid")
    return value


def _at_path(payload: Any, path: str | None, *, required: bool = False) -> Any:
    if path is None:
        return payload
    current = payload
    for segment in path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            if required:
                raise TelemetryConnectorError(
                    "payload_field_missing",
                    kind=ConnectorFailureKind.PAYLOAD,
                    safe_message="Telemetry source response does not match the approved field mapping.",
                )
            return None
        current = current[segment]
    return current


def _extract_records(payload: Any, records_path: str | None) -> list[Mapping[str, Any]]:
    records = _at_path(payload, records_path, required=records_path is not None)
    if not isinstance(records, list) or not all(isinstance(item, Mapping) for item in records):
        raise TelemetryConnectorError(
            "payload_records_invalid",
            kind=ConnectorFailureKind.PAYLOAD,
            safe_message="Telemetry source response does not contain a valid record list.",
        )
    return records


def _observation(record: Mapping[str, Any], config: _HttpsConfig) -> RawObservationEnvelope:
    tag_id = _at_path(record, config.external_tag_id_field, required=True)
    tag_name = (
        _at_path(record, config.external_tag_name_field, required=False)
        if config.external_tag_name_field
        else tag_id
    )
    metadata = {
        field: _at_path(record, field, required=False)
        for field in config.metadata_fields
    }
    try:
        return RawObservationEnvelope(
            external_tag_id=str(tag_id or ""),
            external_tag_name=str(tag_name or tag_id or ""),
            source_timestamp=_at_path(record, config.timestamp_field, required=True),
            raw_value=_at_path(record, config.value_field, required=True),
            reported_unit=(
                str(_at_path(record, config.unit_field, required=False))
                if config.unit_field and _at_path(record, config.unit_field, required=False) is not None
                else None
            ),
            reported_quality=(
                str(_at_path(record, config.quality_field, required=False))
                if config.quality_field and _at_path(record, config.quality_field, required=False) is not None
                else None
            ),
            provider_event_id=(
                str(_at_path(record, config.event_id_field, required=False))
                if config.event_id_field and _at_path(record, config.event_id_field, required=False) is not None
                else None
            ),
            metadata=metadata,
        )
    except (TypeError, ValueError):
        raise TelemetryConnectorError(
            "payload_observation_invalid",
            kind=ConnectorFailureKind.PAYLOAD,
            safe_message="Telemetry source returned an invalid observation.",
        ) from None


def _pagination_checkpoint(payload: Any, config: _HttpsConfig) -> ConnectorCheckpoint | None:
    if config.next_page_path:
        target = _at_path(payload, config.next_page_path, required=False)
        if target in (None, ""):
            return None
        if not isinstance(target, str) or len(target) > 2_048:
            raise TelemetryConnectorError(
                "pagination_value_invalid",
                kind=ConnectorFailureKind.PAYLOAD,
                safe_message="Telemetry source returned an invalid pagination value.",
            )
        return ConnectorCheckpoint(cursor=f"path:{target}")
    if config.next_cursor_path:
        cursor = _at_path(payload, config.next_cursor_path, required=False)
        if cursor in (None, ""):
            return None
        if not isinstance(cursor, (str, int)) or len(str(cursor)) > 2_000:
            raise TelemetryConnectorError(
                "pagination_value_invalid",
                kind=ConnectorFailureKind.PAYLOAD,
                safe_message="Telemetry source returned an invalid pagination value.",
            )
        return ConnectorCheckpoint(cursor=f"cursor:{cursor}")
    return None


def _request_headers(config: _HttpsConfig, secret: ResolvedSecret | None) -> dict[str, str]:
    headers = {"accept": "application/json", "user-agent": "Neraium-Telemetry/1"}
    if config.authentication_scheme == "none":
        return headers
    if secret is None:
        raise TelemetryConnectorError(
            "credentials_unavailable",
            kind=ConnectorFailureKind.AUTHENTICATION,
            safe_message="Telemetry credentials are unavailable.",
        )
    try:
        if config.authentication_scheme == "bearer":
            headers["authorization"] = f"Bearer {secret.get_required('access_token')}"
        elif config.authentication_scheme == "api_key":
            headers["x-api-key"] = secret.get_required("api_key")
    except TelemetrySecretError:
        raise TelemetryConnectorError(
            "credential_field_missing",
            kind=ConnectorFailureKind.AUTHENTICATION,
            safe_message="Telemetry credentials are incomplete.",
        ) from None
    return headers


def _retry_after_seconds(value: str | None, *, now: datetime, maximum: float) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                return None
            seconds = (parsed.astimezone(UTC) - now.astimezone(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(max(seconds, 0.0), maximum)


# Concise alias used by registry wiring and provider-development docs.
HTTPSConnector = HttpsTelemetryConnector


__all__ = ["HTTPSConnector", "HttpsTelemetryConnector"]
