from __future__ import annotations

import pytest

from app.services.telemetry_egress import (
    TelemetryEgressError,
    TelemetryEgressPolicy,
    TelemetryRequestLimits,
    require_request_budget,
)


class StaticResolver:
    def __init__(self, *answers: str) -> None:
        self.answers = answers
        self.calls: list[tuple[str, int]] = []

    def resolve(self, hostname: str, port: int):
        self.calls.append((hostname, port))
        return self.answers


class RebindingResolver:
    def __init__(self) -> None:
        self.calls = 0

    def resolve(self, hostname: str, port: int):
        del hostname, port
        self.calls += 1
        return ["93.184.216.34"] if self.calls == 1 else ["169.254.169.254"]


@pytest.mark.parametrize(
    "url,code",
    [
        ("http://telemetry.example.test/data", "https_required"),
        ("ftp://telemetry.example.test/data", "https_required"),
        ("https://telemetry.example.test:8443/data", "port_not_allowed"),
        ("https://user:pass@telemetry.example.test/data", "userinfo_not_allowed"),
        ("https://telemetry.example.test/data#fragment", "fragment_not_allowed"),
        ("https://localhost/data", "unsafe_destination"),
        ("https://api.localhost/data", "unsafe_destination"),
        ("https://telemetry.example.test\\@169.254.169.254/data", "invalid_url"),
    ],
)
def test_url_policy_rejects_unsafe_syntax(url: str, code: str) -> None:
    policy = TelemetryEgressPolicy(resolver=StaticResolver("93.184.216.34"))
    with pytest.raises(TelemetryEgressError) as error:
        policy.authorize_request(url)
    assert error.value.code == code


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "169.254.169.254",
        "0.0.0.0",
        "224.0.0.1",
        "192.0.2.1",
        "255.255.255.255",
        "::",
        "::1",
        "fe80::1",
        "fc00::1",
        "ff02::1",
        "2001:db8::1",
        "::ffff:127.0.0.1",
        "::ffff:169.254.169.254",
    ],
)
def test_every_non_global_ipv4_and_ipv6_class_is_rejected(address: str) -> None:
    policy = TelemetryEgressPolicy(resolver=StaticResolver(address))
    with pytest.raises(TelemetryEgressError) as error:
        policy.authorize_request("https://telemetry.example.test/data")
    assert error.value.code == "unsafe_destination"


def test_all_a_and_aaaa_answers_must_be_public() -> None:
    resolver = StaticResolver("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946", "10.1.2.3")
    policy = TelemetryEgressPolicy(resolver=resolver)
    with pytest.raises(TelemetryEgressError) as error:
        policy.authorize_request("https://TELEMETRY.EXAMPLE.TEST./data")
    assert error.value.code == "unsafe_destination"
    assert resolver.calls == [("telemetry.example.test", 443)]


def test_dns_is_revalidated_for_every_request_to_reduce_rebinding_risk() -> None:
    resolver = RebindingResolver()
    policy = TelemetryEgressPolicy(resolver=resolver)
    first = policy.authorize_request("https://telemetry.example.test/data")
    assert first.resolved_addresses == ("93.184.216.34",)
    assert first.follow_redirects is False
    assert first.trust_env is False
    assert first.verify_tls is True
    with pytest.raises(TelemetryEgressError) as error:
        policy.authorize_request("https://telemetry.example.test/data?page=2")
    assert error.value.code == "unsafe_destination"
    assert resolver.calls == 2


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
def test_only_read_only_get_is_allowed(method: str) -> None:
    policy = TelemetryEgressPolicy(resolver=StaticResolver("93.184.216.34"))
    with pytest.raises(TelemetryEgressError) as error:
        policy.authorize_request("https://telemetry.example.test/data", method=method)
    assert error.value.code == "method_not_allowed"


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "metadata.internal"},
        {"Connection": "keep-alive"},
        {"Proxy-Authorization": "Basic canary"},
        {"X-Forwarded-Host": "metadata.internal"},
        {"Transfer-Encoding": "chunked"},
        {"X-Custom-User-Header": "unsafe"},
        {"Authorization": "Bearer valid\r\nHost: metadata.internal"},
    ],
)
def test_unsafe_or_arbitrary_headers_are_rejected(headers: dict[str, str]) -> None:
    policy = TelemetryEgressPolicy(resolver=StaticResolver("93.184.216.34"))
    with pytest.raises(TelemetryEgressError):
        policy.authorize_request("https://telemetry.example.test/data", headers=headers)


def test_relative_path_and_bounded_query_stay_on_the_configured_origin() -> None:
    policy = TelemetryEgressPolicy(resolver=StaticResolver("93.184.216.34"))
    url = policy.build_relative_url(
        "https://Telemetry.Example.Test/api/",
        "v1/readings",
        query={"cursor": "opaque value", "limit": 100},
    )
    assert url == "https://telemetry.example.test/v1/readings?cursor=opaque+value&limit=100"
    authorized = policy.authorize_request(url, headers={"Accept": "application/json"})
    assert authorized.hostname == "telemetry.example.test"


@pytest.mark.parametrize("name", ["token", "api_key", "password", "clientSecret"])
def test_credentials_cannot_be_embedded_in_urls(name: str) -> None:
    policy = TelemetryEgressPolicy(resolver=StaticResolver("93.184.216.34"))
    with pytest.raises(TelemetryEgressError) as error:
        policy.build_relative_url(
            "https://telemetry.example.test", "/readings", query={name: "canary"}
        )
    assert error.value.code == "credential_query_not_allowed"


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example.test/next",
        "https://telemetry.example.test/next",
        "//evil.example.test/next",
        "\\\\evil.example.test\\next",
    ],
)
def test_pagination_rejects_absolute_or_network_targets(target: str) -> None:
    policy = TelemetryEgressPolicy(resolver=StaticResolver("93.184.216.34"))
    with pytest.raises(TelemetryEgressError):
        policy.pagination_url("https://telemetry.example.test/data?page=1", target)


def test_relative_pagination_preserves_the_current_resource_path() -> None:
    policy = TelemetryEgressPolicy(resolver=StaticResolver("93.184.216.34"))
    assert policy.pagination_url(
        "https://telemetry.example.test/data?page=1", "?page=2"
    ) == "https://telemetry.example.test/data?page=2"


def test_redirects_are_always_rejected_without_inspecting_location() -> None:
    with pytest.raises(TelemetryEgressError) as error:
        TelemetryEgressPolicy.reject_redirect(
            status_code=302, location="https://169.254.169.254/latest/meta-data"
        )
    assert error.value.code == "redirect_not_allowed"


def test_limits_and_run_budget_are_bounded() -> None:
    limits = TelemetryRequestLimits(
        timeout_seconds=10,
        max_response_bytes=2048,
        max_pages=2,
        max_records=10,
    )
    require_request_budget(limits=limits, pages=2, records=10, response_bytes=2048)
    with pytest.raises(TelemetryEgressError) as error:
        require_request_budget(limits=limits, pages=3, records=10, response_bytes=2048)
    assert error.value.code == "page_budget_exceeded"

    with pytest.raises(TelemetryEgressError) as error:
        TelemetryRequestLimits(timeout_seconds=31)
    assert error.value.code == "timeout_out_of_bounds"


def test_error_text_never_echoes_destination_or_resolver_details() -> None:
    class ExplodingResolver:
        def resolve(self, hostname: str, port: int):
            raise RuntimeError(f"resolver leaked {hostname}:{port} canary")

    policy = TelemetryEgressPolicy(resolver=ExplodingResolver())
    with pytest.raises(TelemetryEgressError) as error:
        policy.authorize_request("https://sensitive-host.example.test/private?cursor=canary")
    rendered = f"{error.value!r} {error.value}"
    assert error.value.code == "dns_resolution_failed"
    assert "sensitive-host" not in rendered
    assert "canary" not in rendered
