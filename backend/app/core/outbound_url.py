from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit, urlunsplit


_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "metadata", "metadata.google.internal"}


def _is_public_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(value.split("%", 1)[0]).is_global
    except ValueError:
        return False


def validate_outbound_http_url(
    value: str,
    *,
    resolve_dns: bool = True,
    resolver: Callable[..., list[tuple[Any, ...]]] = socket.getaddrinfo,
) -> str:
    url = str(value or "").strip()
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        raise ValueError("Outbound URL is invalid.") from None
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("Outbound URL must use http or https.")
    if not parsed.hostname:
        raise ValueError("Outbound URL must include a hostname.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Outbound URL must not contain embedded credentials.")

    hostname = parsed.hostname.rstrip(".").lower()
    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise ValueError("Outbound URL cannot target a local or private network address.")

    try:
        literal_address = ipaddress.ip_address(hostname.split("%", 1)[0])
    except ValueError:
        literal_address = None
    if literal_address is not None and not literal_address.is_global:
        raise ValueError("Outbound URL cannot target a local or private network address.")

    if resolve_dns and literal_address is None:
        try:
            answers = resolver(hostname, port or (443 if parsed.scheme.lower() == "https" else 80), type=socket.SOCK_STREAM)
        except OSError:
            raise ValueError("Outbound URL hostname could not be resolved.") from None
        addresses = {str(answer[4][0]) for answer in answers if len(answer) >= 5 and answer[4]}
        if not addresses or any(not _is_public_address(address) for address in addresses):
            raise ValueError("Outbound URL cannot resolve to a local or private network address.")
    return url


def sanitize_url_for_display(value: str) -> str:
    url = str(value or "").strip()
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname or ""
        port = parsed.port
    except ValueError:
        return "configured"
    if not parsed.scheme or not hostname:
        return "configured"
    host = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "", "", ""))
