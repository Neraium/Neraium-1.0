"""Central public-HTTPS authorization policy for telemetry connectors.

This module does not execute requests.  It produces a validated request target
and immutable transport requirements that the HTTPS connector must honor.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Iterable, Mapping, Protocol, Sequence
from urllib.parse import SplitResult, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit


class TelemetryEgressError(ValueError):
    """Stable network-policy denial without destination or resolver details."""

    def __init__(self, code: str, message: str = "Telemetry destination is not allowed.") -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class HostResolver(Protocol):
    def resolve(self, hostname: str, port: int) -> Sequence[str]: ...


class SocketHostResolver:
    def resolve(self, hostname: str, port: int) -> Sequence[str]:
        try:
            answers = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except OSError:
            raise TelemetryEgressError("dns_resolution_failed") from None
        return tuple(str(answer[4][0]) for answer in answers)


@dataclass(frozen=True, slots=True)
class TelemetryRequestLimits:
    timeout_seconds: float = 15.0
    max_response_bytes: int = 5 * 1024 * 1024
    max_pages: int = 50
    max_records: int = 50_000
    max_query_parameters: int = 20
    max_url_length: int = 4_096

    def __post_init__(self) -> None:
        if not 1.0 <= float(self.timeout_seconds) <= 30.0:
            raise TelemetryEgressError("timeout_out_of_bounds")
        if not 1_024 <= self.max_response_bytes <= 10 * 1024 * 1024:
            raise TelemetryEgressError("response_budget_out_of_bounds")
        if not 1 <= self.max_pages <= 100:
            raise TelemetryEgressError("page_budget_out_of_bounds")
        if not 1 <= self.max_records <= 100_000:
            raise TelemetryEgressError("record_budget_out_of_bounds")
        if not 1 <= self.max_query_parameters <= 50:
            raise TelemetryEgressError("query_budget_out_of_bounds")
        if not 256 <= self.max_url_length <= 8_192:
            raise TelemetryEgressError("url_budget_out_of_bounds")


@dataclass(frozen=True, slots=True)
class AuthorizedTelemetryRequest:
    url: str
    hostname: str
    port: int
    resolved_addresses: tuple[str, ...]
    method: str = "GET"
    follow_redirects: bool = False
    trust_env: bool = False
    verify_tls: bool = True


_ALLOWED_HEADERS = frozenset({"accept", "authorization", "user-agent", "x-api-key"})
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]{1,64}$")
_QUERY_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_SENSITIVE_QUERY_NAME_RE = re.compile(
    r"(?:authorization|credential|password|passwd|secret|token|api[_-]?key|access[_-]?code)",
    re.IGNORECASE,
)


def _normalize_hostname(hostname: str) -> str:
    value = str(hostname or "").rstrip(".").lower()
    if not value or len(value) > 253 or "\x00" in value or "\\" in value:
        raise TelemetryEgressError("invalid_hostname")
    try:
        normalized = value.encode("idna").decode("ascii")
    except UnicodeError:
        raise TelemetryEgressError("invalid_hostname") from None
    if normalized == "localhost" or normalized.endswith(".localhost"):
        raise TelemetryEgressError("unsafe_destination")
    return normalized


def _validated_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(str(value).split("%", 1)[0])
    except ValueError:
        raise TelemetryEgressError("dns_response_invalid") from None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        if not address.ipv4_mapped.is_global:
            raise TelemetryEgressError("unsafe_destination")
    # ``is_global`` has changed semantics between Python releases for some
    # multicast ranges, so enumerate every forbidden class as well.
    if (
        not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise TelemetryEgressError("unsafe_destination")
    return address.compressed


def _origin(parts: SplitResult) -> tuple[str, str, int]:
    return (parts.scheme, _normalize_hostname(parts.hostname or ""), parts.port or 443)


class TelemetryEgressPolicy:
    """Authorize fixed GET requests to public HTTPS/443 destinations."""

    def __init__(
        self,
        *,
        resolver: HostResolver | None = None,
        limits: TelemetryRequestLimits | None = None,
    ) -> None:
        self._resolver = resolver or SocketHostResolver()
        self.limits = limits or TelemetryRequestLimits()

    def normalize_url(self, url: str) -> str:
        raw = str(url or "").strip()
        if not raw or len(raw) > self.limits.max_url_length:
            raise TelemetryEgressError("invalid_url")
        if any(character in raw for character in ("\r", "\n", "\t", "\\")):
            raise TelemetryEgressError("invalid_url")
        try:
            parts = urlsplit(raw)
            port = parts.port
        except ValueError:
            raise TelemetryEgressError("invalid_url") from None
        if parts.scheme.lower() != "https":
            raise TelemetryEgressError("https_required")
        if not parts.netloc or parts.username is not None or parts.password is not None:
            raise TelemetryEgressError("userinfo_not_allowed")
        if parts.fragment:
            raise TelemetryEgressError("fragment_not_allowed")
        if port not in (None, 443):
            raise TelemetryEgressError("port_not_allowed")
        hostname = _normalize_hostname(parts.hostname or "")
        try:
            literal = ipaddress.ip_address(hostname)
        except ValueError:
            literal = None
        if literal is not None:
            _validated_ip(str(literal))
        host_for_url = f"[{hostname}]" if ":" in hostname else hostname
        netloc = host_for_url if port is None else f"{host_for_url}:443"
        path = parts.path or "/"
        if not path.startswith("/") or path.startswith("//"):
            raise TelemetryEgressError("invalid_path")
        query_pairs = parse_qsl(parts.query, keep_blank_values=True)
        if len(query_pairs) > self.limits.max_query_parameters:
            raise TelemetryEgressError("query_budget_exceeded")
        if any(_SENSITIVE_QUERY_NAME_RE.search(name) for name, _ in query_pairs):
            raise TelemetryEgressError("credential_query_not_allowed")
        return urlunsplit(("https", netloc, path, parts.query, ""))

    def validate_headers(self, headers: Mapping[str, str] | None) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for name, value in (headers or {}).items():
            clean_name = str(name).strip().lower()
            if not _HEADER_NAME_RE.fullmatch(clean_name) or clean_name not in _ALLOWED_HEADERS:
                raise TelemetryEgressError("header_not_allowed")
            clean_value = str(value)
            if not clean_value or len(clean_value) > 8_192 or "\r" in clean_value or "\n" in clean_value:
                raise TelemetryEgressError("header_value_invalid")
            normalized[clean_name] = clean_value
        return normalized

    def authorize_request(
        self,
        url: str,
        *,
        method: str = "GET",
        headers: Mapping[str, str] | None = None,
    ) -> AuthorizedTelemetryRequest:
        if str(method).upper() != "GET":
            raise TelemetryEgressError("method_not_allowed")
        self.validate_headers(headers)
        normalized = self.normalize_url(url)
        parts = urlsplit(normalized)
        hostname = _normalize_hostname(parts.hostname or "")
        try:
            answers = self._resolver.resolve(hostname, 443)
        except TelemetryEgressError:
            raise
        except Exception:
            raise TelemetryEgressError("dns_resolution_failed") from None
        if not answers:
            raise TelemetryEgressError("dns_resolution_failed")
        # Reject the whole destination if even one A/AAAA response is unsafe.
        addresses = tuple(sorted({_validated_ip(answer) for answer in answers}))
        return AuthorizedTelemetryRequest(
            url=normalized,
            hostname=hostname,
            port=443,
            resolved_addresses=addresses,
        )

    def build_relative_url(
        self,
        origin_url: str,
        relative_path: str,
        *,
        query: Mapping[str, str | int | float | bool] | None = None,
    ) -> str:
        origin = urlsplit(self.normalize_url(origin_url))
        relative = str(relative_path or "").strip()
        if (
            not relative
            or len(relative) > 2_048
            or any(character in relative for character in ("\r", "\n", "\\"))
        ):
            raise TelemetryEgressError("invalid_relative_path")
        parsed = urlsplit(relative)
        if parsed.scheme or parsed.netloc or parsed.fragment or relative.startswith("//"):
            raise TelemetryEgressError("pagination_target_not_allowed")
        if query and parsed.query:
            raise TelemetryEgressError("ambiguous_query")
        if query is not None:
            if len(query) > self.limits.max_query_parameters:
                raise TelemetryEgressError("query_budget_exceeded")
            pairs: list[tuple[str, str]] = []
            for key, value in query.items():
                clean_key = str(key)
                if not _QUERY_NAME_RE.fullmatch(clean_key):
                    raise TelemetryEgressError("query_name_invalid")
                if _SENSITIVE_QUERY_NAME_RE.search(clean_key):
                    raise TelemetryEgressError("credential_query_not_allowed")
                clean_value = str(value)
                if len(clean_value) > 1_024 or "\r" in clean_value or "\n" in clean_value:
                    raise TelemetryEgressError("query_value_invalid")
                pairs.append((clean_key, clean_value))
            relative = urlunsplit(("", "", parsed.path, urlencode(pairs), ""))
        candidate = self.normalize_url(
            urljoin(urlunsplit((origin.scheme, origin.netloc, "/", "", "")), relative)
        )
        if _origin(urlsplit(candidate)) != _origin(origin):
            raise TelemetryEgressError("pagination_origin_mismatch")
        return candidate

    def pagination_url(self, current_url: str, relative_target: str) -> str:
        # Absolute links are intentionally refused even when they name the same
        # host, eliminating parser and credential-forwarding ambiguity.
        target = str(relative_target or "").strip()
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or parsed.fragment or target.startswith("//"):
            raise TelemetryEgressError("pagination_target_not_allowed")
        current = self.normalize_url(current_url)
        candidate = self.normalize_url(urljoin(current, target))
        if _origin(urlsplit(candidate)) != _origin(urlsplit(current)):
            raise TelemetryEgressError("pagination_origin_mismatch")
        return candidate

    @staticmethod
    def reject_redirect(*, status_code: int, location: str | None = None) -> None:
        del location
        if 300 <= int(status_code) < 400:
            raise TelemetryEgressError("redirect_not_allowed")


def require_request_budget(
    *,
    limits: TelemetryRequestLimits,
    pages: int,
    records: int,
    response_bytes: int,
) -> None:
    """Fail before accepting a response that exceeds a whole-run budget."""
    checks: Iterable[tuple[bool, str]] = (
        (0 <= pages <= limits.max_pages, "page_budget_exceeded"),
        (0 <= records <= limits.max_records, "record_budget_exceeded"),
        (0 <= response_bytes <= limits.max_response_bytes, "response_budget_exceeded"),
    )
    for allowed, code in checks:
        if not allowed:
            raise TelemetryEgressError(code)
