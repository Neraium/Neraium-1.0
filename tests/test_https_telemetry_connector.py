from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Callable

import httpx
import pytest

from app.connectors.base import (
    BoundedBackfillRange,
    ConnectorCheckpoint,
    ConnectorExecutionContext,
    ConnectorFailureKind,
    TelemetryConnectorError,
)
from app.connectors.https_telemetry import HttpsTelemetryConnector
from app.services.telemetry_egress import TelemetryEgressPolicy, TelemetryRequestLimits
from app.services.telemetry_secrets import MemoryTelemetrySecretStore


class StaticResolver:
    def __init__(self, *answers: str) -> None:
        self.answers = answers
        self.calls = 0

    def resolve(self, hostname: str, port: int):
        assert hostname == "telemetry.example.test"
        assert port == 443
        self.calls += 1
        return self.answers


class SequencedResolver:
    def __init__(self, *answers: str) -> None:
        self.answers = answers
        self.calls = 0

    def resolve(self, hostname: str, port: int):
        assert hostname == "telemetry.example.test"
        assert port == 443
        answer = self.answers[self.calls]
        self.calls += 1
        return (answer,)


def configuration(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "base_url": "https://telemetry.example.test",
        "request_path": "/v1/readings",
        "records_path": "data.records",
        "timestamp_field": "observed_at",
        "value_field": "value",
        "external_tag_id_field": "tag.id",
        "external_tag_name_field": "tag.name",
        "unit_field": "unit",
        "quality_field": "quality",
        "event_id_field": "event_id",
        "max_retries": 2,
    }
    value.update(overrides)
    return value


def context(config: dict[str, Any], *, binding=None) -> ConnectorExecutionContext:
    return ConnectorExecutionContext(
        connection_id="connection-a",
        resource_scope_id="scope-a",
        configuration=config,
        secret_binding=binding,
    )


def connector(
    handler,
    *,
    resolver=None,
    store=None,
    sleeps=None,
    sleeper: Callable[[float], None] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> HttpsTelemetryConnector:
    resolver = resolver or StaticResolver("93.184.216.34")
    sleeps = sleeps if sleeps is not None else []
    return HttpsTelemetryConnector(
        egress_policy=TelemetryEgressPolicy(resolver=resolver),
        secret_store=store,
        transport=httpx.MockTransport(handler),
        sleeper=sleeper or sleeps.append,
        jitter=lambda low, high: high,
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        monotonic=monotonic if monotonic is not None else time.monotonic,
    )


def payload(*, cursor=None):
    return {
        "data": {
            "records": [
                {
                    "observed_at": "2026-01-01T00:00:00-05:00",
                    "value": 12.5,
                    "tag": {"id": "CHWP1_KW", "name": "Pump 1 Power"},
                    "unit": "kW",
                    "quality": "good",
                    "event_id": "event-1",
                }
            ],
            "next": cursor,
        }
    }


def test_incremental_read_preserves_raw_source_fields_and_uses_only_get() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=payload())

    result = connector(handler).fetch_incremental(context(configuration()))
    assert len(result.observations) == 1
    observation = result.observations[0]
    assert observation.external_tag_id == "CHWP1_KW"
    assert observation.external_tag_name == "Pump 1 Power"
    assert observation.source_timestamp == "2026-01-01T00:00:00-05:00"
    assert observation.raw_value == 12.5
    assert observation.reported_unit == "kW"
    assert requests[0].method == "GET"
    assert requests[0].url == "https://93.184.216.34/v1/readings"
    assert requests[0].headers["host"] == "telemetry.example.test"
    assert requests[0].extensions["sni_hostname"] == "telemetry.example.test"
    assert requests[0].content == b""
    assert "authorization" not in requests[0].headers


@pytest.mark.parametrize(
    "address,expected_url",
    [
        ("93.184.216.34", "https://93.184.216.34/v1/readings"),
        (
            "2606:2800:220:1:248:1893:25c8:1946",
            "https://[2606:2800:220:1:248:1893:25c8:1946]/v1/readings",
        ),
    ],
)
def test_transport_target_is_pinned_to_an_authorized_address_without_losing_tls_identity(
    address: str,
    expected_url: str,
) -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=payload())

    connector(handler, resolver=StaticResolver(address)).fetch_incremental(
        context(configuration())
    )

    assert captured[0].url == expected_url
    assert captured[0].headers["host"] == "telemetry.example.test"
    assert captured[0].extensions["sni_hostname"] == "telemetry.example.test"


def test_each_retry_is_reauthorized_and_pinned_to_its_newly_approved_address() -> None:
    resolver = SequencedResolver(
        "93.184.216.34",
        "2606:2800:220:1:248:1893:25c8:1946",
    )
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if len(captured) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=payload())

    connector(handler, resolver=resolver).fetch_incremental(context(configuration()))

    assert [request.url.host for request in captured] == [
        "93.184.216.34",
        "2606:2800:220:1:248:1893:25c8:1946",
    ]
    assert {request.headers["host"] for request in captured} == {
        "telemetry.example.test"
    }
    assert {request.extensions["sni_hostname"] for request in captured} == {
        "telemetry.example.test"
    }
    assert resolver.calls == 2


def test_discovery_is_explicit_and_deduplicates_tags() -> None:
    body = payload()
    body["data"]["records"].append(dict(body["data"]["records"][0], value=13.0))
    result = connector(lambda request: httpx.Response(200, json=body)).discover_signals(
        context(configuration())
    )
    assert len(result.observations) == 2
    assert [(item.external_tag_id, item.reported_unit) for item in result.signals] == [
        ("CHWP1_KW", "kW")
    ]


def test_one_malformed_record_does_not_destroy_the_valid_remainder() -> None:
    body = payload()
    body["data"]["records"].insert(
        0,
        {"observed_at": "2026-01-01T00:00:00Z", "value": 1.0, "tag": {}},
    )
    result = connector(lambda request: httpx.Response(200, json=body)).fetch_incremental(
        context(configuration())
    )
    assert [item.external_tag_id for item in result.observations] == ["CHWP1_KW"]
    assert [(item.record_index, item.code) for item in result.issues] == [
        (0, "payload_field_missing")
    ]


def test_cursor_pagination_is_same_origin_and_reauthorized_each_page() -> None:
    resolver = StaticResolver("93.184.216.34")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        cursor = request.url.params.get("cursor")
        return httpx.Response(200, json=payload(cursor="next-2" if cursor is None else None))

    result = connector(handler, resolver=resolver).fetch_incremental(
        context(
            configuration(
                next_cursor_path="data.next",
                cursor_query_parameter="cursor",
                page_size_query_parameter="limit",
                page_size=250,
            )
        )
    )
    assert len(result.observations) == 2
    assert result.pages_read == 2
    assert dict(requests[0].url.params) == {"limit": "250"}
    assert dict(requests[1].url.params) == {"limit": "250", "cursor": "next-2"}
    assert resolver.calls == 2


def test_relative_page_links_cannot_redirect_off_origin() -> None:
    with pytest.raises(TelemetryConnectorError) as error:
        connector(
            lambda request: httpx.Response(
                200,
                json={**payload(), "links": {"next": "https://evil.example/data"}},
            )
        ).fetch_incremental(context(configuration(next_page_path="links.next")))
    assert error.value.code == "pagination_target_not_allowed"
    assert "evil" not in str(error.value)


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_refreshes_secret_once_then_fails_permanently(status: int) -> None:
    store = MemoryTelemetrySecretStore(allow_test_backend=True)
    binding = store.create(
        resource_scope_id="scope-a",
        connection_id="connection-a",
        values={"access_token": "canary-secret"},
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.headers["authorization"] == "Bearer canary-secret"
        return httpx.Response(status, text="credential canary-secret rejected")

    with pytest.raises(TelemetryConnectorError) as error:
        connector(handler, store=store).fetch_incremental(
            context(configuration(authentication_scheme="bearer"), binding=binding)
        )
    assert error.value.code == "authentication_failed"
    assert error.value.kind is ConnectorFailureKind.AUTHENTICATION
    assert error.value.retryable is False
    assert "canary" not in str(error.value)
    assert calls == 2


def test_rate_limit_honors_bounded_retry_after_and_recovers() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"retry-after": "9999"})
        return httpx.Response(200, json=payload())

    result = connector(handler, sleeps=sleeps).fetch_incremental(
        context(configuration(max_retry_after_seconds=7))
    )
    assert result.retry_count == 1
    assert sleeps == [7.0]


def test_timeout_retry_is_bounded_and_errors_are_sanitized() -> None:
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("https://secret-host.example?token=canary", request=request)

    with pytest.raises(TelemetryConnectorError) as error:
        connector(handler, sleeps=sleeps).fetch_incremental(
            context(configuration(max_retries=2))
        )
    assert error.value.code == "network_retry_exhausted"
    assert error.value.retryable is True
    assert len(sleeps) == 2
    assert "canary" not in str(error.value)


def test_retry_budget_is_shared_across_all_pages() -> None:
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls in {1, 3}:
            return httpx.Response(503)
        return httpx.Response(200, json=payload(cursor="next" if calls == 2 else None))

    with pytest.raises(TelemetryConnectorError) as error:
        connector(handler, sleeps=sleeps).fetch_incremental(
            context(
                configuration(
                    max_retries=1,
                    next_cursor_path="data.next",
                    cursor_query_parameter="cursor",
                )
            )
        )

    assert error.value.code == "provider_retry_exhausted"
    assert calls == 3
    assert sleeps == [0.5]


def test_elapsed_time_budget_is_shared_across_all_pages() -> None:
    elapsed = 0.0

    def monotonic() -> float:
        return elapsed

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal elapsed
        elapsed += 0.6
        cursor = request.url.params.get("cursor")
        return httpx.Response(200, json=payload(cursor="next" if cursor is None else None))

    with pytest.raises(TelemetryConnectorError) as error:
        connector(handler, monotonic=monotonic).fetch_incremental(
            context(
                configuration(
                    timeout_seconds=1,
                    next_cursor_path="data.next",
                    cursor_query_parameter="cursor",
                )
            )
        )

    assert error.value.code == "elapsed_time_budget_exceeded"
    assert error.value.kind is ConnectorFailureKind.BUDGET


def test_backoff_budget_is_shared_across_all_pages() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls in {1, 3}:
            return httpx.Response(503)
        return httpx.Response(200, json=payload(cursor="next" if calls == 2 else None))

    with pytest.raises(TelemetryConnectorError) as error:
        connector(handler).fetch_incremental(
            context(
                configuration(
                    max_retries=2,
                    max_retry_after_seconds=0.5,
                    next_cursor_path="data.next",
                    cursor_query_parameter="cursor",
                )
            )
        )

    assert error.value.code == "retry_backoff_budget_exceeded"
    assert error.value.kind is ConnectorFailureKind.BUDGET
    assert calls == 3


def test_redirect_malformed_payload_and_response_budget_fail_closed() -> None:
    cases = [
        (httpx.Response(302, headers={"location": "/other"}), "redirect_not_allowed"),
        (httpx.Response(200, content=b"not-json"), "payload_invalid_json"),
        (
            httpx.Response(200, headers={"content-length": "99999999"}, content=b"[]"),
            "response_budget_exceeded",
        ),
    ]
    for response, code in cases:
        with pytest.raises(TelemetryConnectorError) as error:
            connector(lambda request, response=response: response).fetch_incremental(
                context(configuration())
            )
        assert error.value.code == code


@pytest.mark.parametrize(
    "unsafe",
    [
        {"method": "POST"},
        {"body": {"write": True}},
        {"headers": {"Authorization": "canary"}},
        {"api_key": "canary"},
        {"static_query": {"token": "canary"}},
    ],
)
def test_browser_cannot_supply_method_body_headers_or_secret_values(unsafe: dict[str, Any]) -> None:
    with pytest.raises(TelemetryConnectorError) as error:
        connector(lambda request: httpx.Response(200, json=payload())).fetch_incremental(
            context(configuration(**unsafe))
        )
    assert error.value.kind is ConnectorFailureKind.CONFIGURATION
    assert "canary" not in str(error.value)


@pytest.mark.parametrize(
    "unsafe_path",
    ["api_token", "nested.clientSecret", "credentials.value", "authorization"],
)
def test_response_mapping_cannot_select_credential_shaped_fields(unsafe_path: str) -> None:
    with pytest.raises(TelemetryConnectorError) as error:
        connector(lambda request: httpx.Response(200, json=payload())).fetch_incremental(
            context(configuration(metadata_fields=[unsafe_path]))
        )
    assert error.value.code == "field_credential_path_not_allowed"


def test_connection_limits_cannot_exceed_central_egress_ceiling() -> None:
    policy = TelemetryEgressPolicy(
        resolver=StaticResolver("93.184.216.34"),
        limits=TelemetryRequestLimits(max_pages=1),
    )
    provider = HttpsTelemetryConnector(
        egress_policy=policy,
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload())),
    )
    with pytest.raises(TelemetryConnectorError) as error:
        provider.fetch_incremental(context(configuration(max_pages=2)))
    assert error.value.code == "central_egress_limit_exceeded"


def test_health_does_not_claim_reachability_for_invalid_configuration_or_payload() -> None:
    provider = connector(lambda request: httpx.Response(200, content=b"not-json"))
    invalid_config = provider.health(context(configuration(method="GET")))
    assert invalid_config.reachable is False
    assert invalid_config.authenticated is False
    invalid_payload = provider.health(context(configuration()))
    assert invalid_payload.reachable is False
    assert invalid_payload.authenticated is False


def test_bounded_backfill_uses_only_approved_time_parameters() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=payload())

    connector(handler).fetch_backfill(
        context(
            configuration(
                start_time_query_parameter="start",
                end_time_query_parameter="end",
            )
        ),
        time_range=BoundedBackfillRange(
            start_at=datetime(2026, 1, 1, tzinfo=UTC),
            end_at=datetime(2026, 1, 2, tzinfo=UTC),
        ),
    )
    assert captured[0].url.params["start"] == "2026-01-01T00:00:00+00:00"
    assert captured[0].url.params["end"] == "2026-01-02T00:00:00+00:00"


def test_max_pages_returns_resumable_checkpoint_without_unbounded_reads() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=payload(cursor=f"cursor-{calls}"))

    result = connector(handler).fetch_incremental(
        context(
            configuration(
                next_cursor_path="data.next",
                cursor_query_parameter="cursor",
                max_pages=2,
            )
        )
    )
    assert calls == 2
    assert result.has_more is True
    assert result.next_checkpoint == ConnectorCheckpoint(cursor="cursor:cursor-2")
