"""Server-owned resource approvals; request configuration can only select an ID.

This policy is an application/executor admission control, not a substitute for
an independent gateway, upstream permissions or process-level network isolation.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlsplit

from app.services.telemetry_egress import TelemetryEgressError, TelemetryEgressPolicy

VERSION = "neraium.telemetry-resource-policy.v1"
SCOPE_FIELDS = ("tenant_scope_id", "workspace_id", "facility_id", "resource_scope_id", "connection_id")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_QUERY_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_SEGMENT = re.compile(r"^[A-Za-z0-9_-]+$")


def _deny(code: str = "resource_policy_invalid") -> None:
    raise TelemetryEgressError(code)


def _path(value: Any, *, pattern: bool = False) -> str:
    # Reject encoded/separator/dot aliases instead of guessing how a provider
    # or intermediary normalizes them. Patterns permit one ASCII segment only.
    if not isinstance(value, str) or not value.startswith("/") or len(value) > 2048:
        _deny()
    if any(c in value for c in "%\\?#*") or any(ord(c) < 33 or ord(c) > 126 for c in value):
        _deny()
    segments = value[1:].split("/")
    if value != "/" and any(not s or s in {".", ".."} for s in segments):
        _deny()
    for segment in segments:
        if "{" in segment or "}" in segment:
            if not pattern or segment != "{segment}":
                _deny()
    return value


def _matches(path: str, pattern: str) -> bool:
    left, right = path.split("/"), pattern.split("/")
    return len(left) == len(right) and all(
        bool(_SEGMENT.fullmatch(a)) if b == "{segment}" else a == b
        for a, b in zip(left, right)
    )


@dataclass(frozen=True)
class TelemetryResourcePolicy:
    origin: str
    paths: tuple[str, ...]
    query: Mapping[str, tuple[int, tuple[str, ...] | None]]
    allow_pagination: bool
    authentication_scheme: str
    scope: Mapping[str, str] | None
    credential: Mapping[str, str] | None
    read_only_evidence: str | None

    def authorize_request(self, url: str, *, method: str = "GET") -> None:
        if method != "GET":
            _deny("method_not_allowed")
        normalized = TelemetryEgressPolicy().normalize_url(url)
        parts = urlsplit(normalized)
        actual = f"https://{parts.hostname}:443"
        if actual != self.origin:
            _deny("resource_origin_not_allowed")
        path = _path(parts.path)
        if not any(_matches(path, p) for p in self.paths):
            _deny("resource_path_not_allowed")
        try:
            pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True,
                              max_num_fields=50, errors="strict")
        except (ValueError, UnicodeError):
            _deny("resource_query_not_allowed")
        if len({name for name, _ in pairs}) != len(pairs):
            _deny("resource_query_not_allowed")
        for name, value in pairs:
            rule = self.query.get(name)
            if rule is None or len(value) > rule[0] or any(ord(c) < 32 for c in value):
                _deny("resource_query_not_allowed")
            if rule[1] is not None and value not in rule[1]:
                _deny("resource_query_not_allowed")


class TelemetryResourcePolicyRegistry:
    """Immutable approval registry supplied by reviewed startup/image wiring."""

    def __init__(self, manifest: Mapping[str, Any]) -> None:
        try:
            if set(manifest) != {"version", "policies"} or manifest["version"] != VERSION:
                _deny()
            raw = manifest["policies"]
            if not isinstance(raw, dict) or not raw or len(raw) > 100:
                _deny()
            self._policies = MappingProxyType({self._identifier(k): self._parse(v) for k, v in raw.items()})
        except (TypeError, ValueError, KeyError, AttributeError):
            _deny()

    @staticmethod
    def _identifier(value: Any) -> str:
        if not isinstance(value, str) or not _ID.fullmatch(value):
            _deny()
        return value

    @staticmethod
    def _parse(raw: Any) -> TelemetryResourcePolicy:
        required = {"origin", "method", "paths", "query", "allow_pagination", "authentication_scheme", "kind"}
        if not isinstance(raw, dict) or not required.issubset(raw) or set(raw) - (required | {"scope", "credential", "read_only_evidence"}):
            _deny()
        origin_url = TelemetryEgressPolicy().normalize_url(raw["origin"])
        origin = urlsplit(origin_url)
        if origin.path != "/" or origin.query or raw["method"] != "GET":
            _deny()
        paths = raw["paths"]
        if not isinstance(paths, list) or not 1 <= len(paths) <= 32:
            _deny()
        paths = tuple(_path(p, pattern=True) for p in paths)
        query = raw["query"]
        if not isinstance(query, dict) or len(query) > 20:
            _deny()
        rules = {}
        for name, rule in query.items():
            if not isinstance(name, str) or not _QUERY_NAME.fullmatch(name) or not isinstance(rule, dict):
                _deny()
            if set(rule) - {"max_length", "values"} or type(rule.get("max_length")) is not int or not 1 <= rule["max_length"] <= 1024:
                _deny()
            values = rule.get("values")
            if "values" in rule and (not isinstance(values, list) or not 1 <= len(values) <= 100 or any(not isinstance(v, str) or len(v) > rule["max_length"] for v in values)):
                _deny()
            rules[name] = (rule["max_length"], tuple(values) if values is not None else None)
        if type(raw["allow_pagination"]) is not bool or raw["authentication_scheme"] not in {"none", "bearer", "api_key"}:
            _deny()
        scope = credential = evidence = None
        if raw["kind"] == "customer":
            scope, credential, evidence = raw.get("scope"), raw.get("credential"), raw.get("read_only_evidence")
            if not isinstance(scope, dict) or set(scope) != set(SCOPE_FIELDS) or any(not isinstance(v, str) or not v.strip() or len(v) > 256 for v in scope.values()):
                _deny()
            if not isinstance(credential, dict) or set(credential) != {"binding_id", "provider", "reference"} or any(not isinstance(v, str) or not v.strip() or len(v) > 2048 for v in credential.values()):
                _deny()
            if credential["provider"] != "aws_secrets_manager" or raw["authentication_scheme"] == "none":
                _deny()
            if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 2048:
                _deny("read_only_credential_evidence_required")
            scope, credential = MappingProxyType(dict(scope)), MappingProxyType(dict(credential))
        elif raw["kind"] != "synthetic" or raw["authentication_scheme"] != "none" or any(k in raw for k in ("scope", "credential", "read_only_evidence")):
            _deny()
        return TelemetryResourcePolicy(f"https://{origin.hostname}:443", paths, MappingProxyType(rules), raw["allow_pagination"], raw["authentication_scheme"], scope, credential, evidence)

    def authorize_job(self, job: Mapping[str, Any]) -> TelemetryResourcePolicy:
        try:
            config = job["configuration"]
            policy_id = self._identifier(config.get("resource_policy_id"))
            policy = self._policies.get(policy_id)
            if policy is None:
                _deny("resource_policy_not_configured")
            base = urlsplit(TelemetryEgressPolicy().normalize_url(config["base_url"]))
            if base.path != "/" or base.query or f"https://{base.hostname}:443" != policy.origin:
                _deny("resource_origin_not_allowed")
            if config.get("authentication_scheme", "none") != policy.authentication_scheme:
                _deny("resource_authentication_mismatch")
            credential = job.get("credential")
            if policy.scope is not None:
                if any(job.get(k) != v for k, v in policy.scope.items()):
                    _deny("resource_scope_mismatch")
                if not isinstance(credential, Mapping) or any(credential.get(k) != v for k, v in policy.credential.items()):
                    _deny("resource_credential_mismatch")
                if credential.get("resource_scope_id") != job["resource_scope_id"] or credential.get("connection_id") != job["connection_id"] or not credential.get("version_marker"):
                    _deny("resource_credential_mismatch")
            elif credential is not None:
                _deny("resource_credential_mismatch")
            if not policy.allow_pagination and (job.get("checkpoint") or config.get("next_page_path") or config.get("next_cursor_path")):
                _deny("resource_pagination_not_allowed")
            _path(config["request_path"])
            url = TelemetryEgressPolicy().build_relative_url(config["base_url"], config["request_path"], query=config.get("static_query") or {})
            policy.authorize_request(url)
            return policy
        except TelemetryEgressError:
            raise
        except (TypeError, ValueError, KeyError, AttributeError):
            _deny()

    def authorize_context(self, context: Any) -> TelemetryResourcePolicy:
        binding = context.secret_binding
        return self.authorize_job({
            **{field: getattr(context, field, None) for field in SCOPE_FIELDS},
            "configuration": context.configuration,
            "credential": None if binding is None else {
                "binding_id": binding.binding_id, "provider": binding.provider,
                "reference": binding._internal_reference, "version_marker": binding.version_marker,
                "resource_scope_id": binding.resource_scope_id, "connection_id": binding.connection_id,
            },
        })

    @classmethod
    def load(cls) -> "TelemetryResourcePolicyRegistry":
        path = Path(os.environ.get("NERAIUM_TELEMETRY_RESOURCE_POLICY_FILE", str(Path(__file__).with_name("telemetry_resource_policies.json"))))
        try:
            if not path.is_absolute():
                _deny()
            if path.stat().st_size > 256 * 1024:
                _deny()
            # No fallback on missing, invalid, oversized or duplicate-key files.
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        _deny()
                    result[key] = value
                return result
            return cls(json.loads(path.read_bytes(), object_pairs_hook=unique))
        except (OSError, ValueError, TypeError):
            _deny()
