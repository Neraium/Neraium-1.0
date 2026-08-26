"""Server-only credential storage for telemetry connections.

The public API must never serialize :class:`SecretBinding` instances.  A binding
contains the opaque persistence handle needed by workers, while
``public_metadata`` deliberately exposes only non-sensitive state.
"""

from __future__ import annotations

import json
from hashlib import sha256
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping, Protocol

logger = logging.getLogger(__name__)

_PROVIDER_AWS = "aws_secrets_manager"
_PROVIDER_MEMORY = "test_memory"
_MANAGED_BY_TAG = "neraium:managed-by"
_SCOPE_TAG = "neraium:resource-scope-id"
_CONNECTION_TAG = "neraium:connection-id"
_MANAGED_BY_VALUE = "telemetry-connections"
_REFERENCE_RE = re.compile(
    r"^arn:(?:aws|aws-us-gov|aws-cn):secretsmanager:[a-z0-9-]+:[0-9]{12}:secret:(?P<name>.+)$"
)


class TelemetrySecretError(RuntimeError):
    """A stable, sanitized secret-store failure safe for logs and APIs."""

    def __init__(self, code: str, message: str = "Telemetry credentials are unavailable.") -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


@dataclass(frozen=True, slots=True)
class SecretPublicMetadata:
    """The complete set of secret metadata allowed in a public response."""

    credentials_configured: bool
    version_marker: str | None = None
    updated_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "credentials_configured": self.credentials_configured,
            "credential_version": self.version_marker,
            "credentials_updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class InternalSecretBindingFields:
    """Persistence-only binding fields with a redaction-safe representation.

    This object is deliberately not a ``dict`` and therefore is not directly
    JSON serializable. Repository code must explicitly select each field it
    persists, which keeps the internal reference out of public/audit metadata.
    """

    __slots__ = (
        "_binding_id",
        "_provider",
        "_internal_reference",
        "_version_marker",
        "_updated_at",
    )

    def __init__(
        self,
        *,
        binding_id: str,
        provider: str,
        internal_reference: str,
        version_marker: str | None,
        updated_at: datetime | None,
    ) -> None:
        self._binding_id = binding_id
        self._provider = provider
        self._internal_reference = internal_reference
        self._version_marker = version_marker
        self._updated_at = updated_at

    def __getitem__(self, key: str) -> Any:
        if key == "binding_id":
            return self._binding_id
        if key == "provider":
            return self._provider
        if key == "internal_reference":
            return self._internal_reference
        if key == "version_marker":
            return self._version_marker
        if key == "updated_at":
            return self._updated_at
        raise KeyError(key)

    def __repr__(self) -> str:
        return "InternalSecretBindingFields([REDACTED])"

    __str__ = __repr__


class TrustedPreprovisionedSecretBinding:
    """Internal-operations input for binding a pre-provisioned secret.

    Public request models must never construct or accept this type. Requiring
    a version marker makes binding an optimistic assertion about the exact
    secret approved by deployment operations, while normal secret rotation
    remains supported after the binding has been established.
    """

    __slots__ = (
        "resource_scope_id",
        "connection_id",
        "expected_version_marker",
        "_internal_reference",
        "_sealed",
    )

    def __init__(
        self,
        *,
        resource_scope_id: str,
        connection_id: str,
        internal_reference: str,
        expected_version_marker: str,
    ) -> None:
        object.__setattr__(
            self,
            "resource_scope_id",
            _safe_scope_segment(resource_scope_id, field="resource scope"),
        )
        object.__setattr__(
            self,
            "connection_id",
            _safe_scope_segment(connection_id, field="connection"),
        )
        reference = str(internal_reference or "").strip()
        if not reference or len(reference) > 2_048:
            raise TelemetrySecretError("secret_reference_not_allowed")
        version = str(expected_version_marker or "").strip()
        if not version or len(version) > 512:
            raise TelemetrySecretError("secret_version_invalid")
        object.__setattr__(self, "expected_version_marker", version)
        object.__setattr__(self, "_internal_reference", reference)
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("Trusted secret binding requests are immutable.")
        object.__setattr__(self, name, value)

    def __repr__(self) -> str:
        return (
            "TrustedPreprovisionedSecretBinding("
            f"resource_scope_id={self.resource_scope_id!r}, "
            f"connection_id={self.connection_id!r}, "
            f"expected_version_marker={self.expected_version_marker!r}, "
            "internal_reference=[REDACTED])"
        )

    __str__ = __repr__


class SecretBinding:
    """Opaque server-side link from a connection to a managed secret.

    The reference is intentionally private and omitted from ``repr``.  The
    persistence helpers are explicitly named as internal-only operations so a
    caller cannot mistake them for an API serializer.
    """

    __slots__ = (
        "binding_id",
        "provider",
        "resource_scope_id",
        "connection_id",
        "version_marker",
        "updated_at",
        "_internal_reference",
        "_sealed",
    )

    def __init__(
        self,
        *,
        binding_id: str,
        provider: str,
        resource_scope_id: str,
        connection_id: str,
        internal_reference: str,
        version_marker: str | None,
        updated_at: datetime | None,
    ) -> None:
        if not internal_reference:
            raise ValueError("A server-managed secret reference is required.")
        object.__setattr__(self, "binding_id", str(binding_id))
        object.__setattr__(self, "provider", str(provider))
        object.__setattr__(self, "resource_scope_id", str(resource_scope_id))
        object.__setattr__(self, "connection_id", str(connection_id))
        object.__setattr__(self, "version_marker", str(version_marker) if version_marker else None)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "_internal_reference", str(internal_reference))
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name: str, value: Any) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("Secret bindings are immutable.")
        object.__setattr__(self, name, value)

    def __repr__(self) -> str:
        return (
            "SecretBinding("
            f"binding_id={self.binding_id!r}, provider={self.provider!r}, "
            f"resource_scope_id={self.resource_scope_id!r}, connection_id={self.connection_id!r}, "
            f"version_marker={self.version_marker!r}, updated_at={self.updated_at!r})"
        )

    @classmethod
    def from_internal_persistence(
        cls,
        *,
        binding_id: str,
        provider: str,
        resource_scope_id: str,
        connection_id: str,
        internal_reference: str,
        version_marker: str | None = None,
        updated_at: datetime | None = None,
    ) -> "SecretBinding":
        return cls(
            binding_id=binding_id,
            provider=provider,
            resource_scope_id=resource_scope_id,
            connection_id=connection_id,
            internal_reference=internal_reference,
            version_marker=version_marker,
            updated_at=updated_at,
        )

    def internal_persistence_fields(self) -> InternalSecretBindingFields:
        """Return DB-only fields; never pass this object to an API or logger."""
        return InternalSecretBindingFields(
            binding_id=self.binding_id,
            provider=self.provider,
            internal_reference=self._internal_reference,
            version_marker=self.version_marker,
            updated_at=self.updated_at,
        )

    def public_metadata(self) -> SecretPublicMetadata:
        return SecretPublicMetadata(
            credentials_configured=True,
            version_marker=self.version_marker,
            updated_at=self.updated_at,
        )


class ResolvedSecret:
    """Redaction-safe resolved material for server-side connector use only."""

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, str]) -> None:
        self._values = {str(key): str(value) for key, value in values.items()}

    def __repr__(self) -> str:
        return "ResolvedSecret([REDACTED])"

    __str__ = __repr__

    def get_required(self, key: str) -> str:
        value = self._values.get(key)
        if value is None or value == "":
            raise TelemetrySecretError("secret_field_missing")
        return value

    def get_optional(self, key: str) -> str | None:
        return self._values.get(key)


class TelemetrySecretStore(Protocol):
    def bind_preprovisioned(
        self, request: TrustedPreprovisionedSecretBinding
    ) -> SecretBinding: ...

    def create(
        self, *, resource_scope_id: str, connection_id: str, values: Mapping[str, str]
    ) -> SecretBinding: ...

    def update(self, binding: SecretBinding, *, values: Mapping[str, str]) -> SecretBinding: ...

    def resolve(self, binding: SecretBinding, *, force_refresh: bool = False) -> ResolvedSecret: ...

    def resolve_after_auth_failure(self, binding: SecretBinding) -> ResolvedSecret: ...


def _safe_scope_segment(value: str, *, field: str) -> str:
    normalized = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", normalized):
        raise TelemetrySecretError("invalid_secret_ownership", f"Invalid {field} for credential binding.")
    return normalized


def _aws_safe_name_segment(value: str, *, label: str) -> str:
    """Derive a deterministic AWS-safe opaque name segment.

    Authoritative scope and connection identifiers remain complete only in
    ownership tags; secret names use fixed-size hashes and contain no colons.
    """

    digest = sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{label}-{digest}"


def _normalized_values(values: Mapping[str, str]) -> dict[str, str]:
    if not values or len(values) > 20:
        raise TelemetrySecretError("invalid_secret_payload")
    normalized: dict[str, str] = {}
    total_bytes = 0
    for key, value in values.items():
        clean_key = str(key or "").strip()
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", clean_key):
            raise TelemetrySecretError("invalid_secret_payload")
        if not isinstance(value, str) or not value or len(value) > 16_384:
            raise TelemetrySecretError("invalid_secret_payload")
        total_bytes += len(clean_key.encode("utf-8")) + len(value.encode("utf-8"))
        normalized[clean_key] = value
    if total_bytes > 32_768:
        raise TelemetrySecretError("invalid_secret_payload")
    return normalized


def _parse_secret_payload(secret_string: Any) -> ResolvedSecret:
    if not isinstance(secret_string, str):
        raise TelemetrySecretError("secret_payload_invalid")
    try:
        decoded = json.loads(secret_string)
    except (TypeError, ValueError):
        raise TelemetrySecretError("secret_payload_invalid") from None
    if not isinstance(decoded, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in decoded.items()
    ):
        raise TelemetrySecretError("secret_payload_invalid")
    return ResolvedSecret(decoded)


def _reference_name(reference: str) -> str:
    match = _REFERENCE_RE.fullmatch(reference)
    if match:
        # Secrets Manager appends a six-character suffix to ARNs returned for
        # named secrets; ownership is still verified independently with tags.
        return match.group("name")
    return reference


def _current_version_marker(response: Mapping[str, Any]) -> str:
    versions = response.get("VersionIdsToStages")
    current: list[str] = []
    if isinstance(versions, Mapping):
        current = sorted(
            str(version_id)
            for version_id, stages in versions.items()
            if isinstance(stages, (list, tuple)) and "AWSCURRENT" in stages
        )
    if len(current) != 1 or not current[0] or len(current[0]) > 512:
        raise TelemetrySecretError("secret_version_invalid")
    return current[0]


class AwsSecretsManagerTelemetryStore:
    """Least-privilege AWS Secrets Manager implementation.

    ``dynamic_writes_enabled`` is intentionally false by default.  Production
    can bind pre-provisioned secrets until create/update IAM is explicitly
    approved and deployed.
    """

    def __init__(
        self,
        *,
        client: Any,
        environment: str,
        dynamic_writes_enabled: bool = False,
        cache_ttl_seconds: float = 60.0,
        clock: Any = time.monotonic,
    ) -> None:
        environment = _safe_scope_segment(environment, field="environment").lower()
        self._client = client
        self._prefix = f"neraium/{environment}/telemetry-connections/"
        self._dynamic_writes_enabled = bool(dynamic_writes_enabled)
        self._cache_ttl_seconds = min(max(float(cache_ttl_seconds), 0.0), 300.0)
        self._clock = clock
        self._cache: dict[str, tuple[float, ResolvedSecret]] = {}
        self._lock = threading.RLock()

    def _describe_owned(
        self, *, reference: str, resource_scope_id: str, connection_id: str
    ) -> dict[str, Any]:
        name = _reference_name(reference)
        if not name.startswith(self._prefix):
            raise TelemetrySecretError("secret_reference_not_allowed")
        try:
            response = self._client.describe_secret(SecretId=reference)
        except Exception:
            logger.warning(
                "telemetry_secret_metadata_failed",
                extra={"event": "telemetry_secret_metadata_failed", "reason": "provider_error"},
            )
            raise TelemetrySecretError("secret_metadata_unavailable") from None
        if not isinstance(response, Mapping):
            raise TelemetrySecretError("secret_metadata_unavailable")
        tags = {
            str(tag.get("Key")): str(tag.get("Value"))
            for tag in response.get("Tags", [])
            if isinstance(tag, Mapping) and tag.get("Key") is not None
        }
        expected = {
            _MANAGED_BY_TAG: _MANAGED_BY_VALUE,
            _SCOPE_TAG: resource_scope_id,
            _CONNECTION_TAG: connection_id,
        }
        if any(tags.get(key) != value for key, value in expected.items()):
            raise TelemetrySecretError("secret_ownership_mismatch")
        return response

    @staticmethod
    def _binding_from_response(
        *,
        reference: str,
        response: Mapping[str, Any],
        resource_scope_id: str,
        connection_id: str,
        binding_id: str | None = None,
    ) -> SecretBinding:
        version_marker = _current_version_marker(response)
        changed_at = response.get("LastChangedDate")
        if isinstance(changed_at, datetime):
            updated_at = changed_at if changed_at.tzinfo else changed_at.replace(tzinfo=UTC)
        else:
            updated_at = None
        return SecretBinding(
            binding_id=binding_id or str(uuid.uuid4()),
            provider=_PROVIDER_AWS,
            resource_scope_id=resource_scope_id,
            connection_id=connection_id,
            internal_reference=reference,
            version_marker=version_marker,
            updated_at=updated_at,
        )

    def bind_preprovisioned(
        self, request: TrustedPreprovisionedSecretBinding
    ) -> SecretBinding:
        if not isinstance(request, TrustedPreprovisionedSecretBinding):
            raise TelemetrySecretError("trusted_secret_binding_required")
        scope = request.resource_scope_id
        connection = request.connection_id
        reference = request._internal_reference
        response = self._describe_owned(
            reference=reference,
            resource_scope_id=scope,
            connection_id=connection,
        )
        if _current_version_marker(response) != request.expected_version_marker:
            raise TelemetrySecretError("secret_version_mismatch")
        return self._binding_from_response(
            reference=reference,
            response=response,
            resource_scope_id=scope,
            connection_id=connection,
        )

    def create(
        self, *, resource_scope_id: str, connection_id: str, values: Mapping[str, str]
    ) -> SecretBinding:
        if not self._dynamic_writes_enabled:
            raise TelemetrySecretError("dynamic_secret_writes_disabled")
        scope = _safe_scope_segment(resource_scope_id, field="resource scope")
        connection = _safe_scope_segment(connection_id, field="connection")
        payload = _normalized_values(values)
        scope_name = _aws_safe_name_segment(scope, label="scope")
        connection_name = _aws_safe_name_segment(connection, label="connection")
        name = f"{self._prefix}{scope_name}/{connection_name}"
        try:
            response = self._client.create_secret(
                Name=name,
                SecretString=json.dumps(payload, separators=(",", ":"), sort_keys=True),
                Tags=[
                    {"Key": _MANAGED_BY_TAG, "Value": _MANAGED_BY_VALUE},
                    {"Key": _SCOPE_TAG, "Value": scope},
                    {"Key": _CONNECTION_TAG, "Value": connection},
                ],
            )
        except Exception:
            logger.warning(
                "telemetry_secret_create_failed",
                extra={"event": "telemetry_secret_create_failed", "reason": "provider_error"},
            )
            raise TelemetrySecretError("secret_write_failed") from None
        reference = str(response.get("ARN") or name)
        described = self._describe_owned(
            reference=reference,
            resource_scope_id=scope,
            connection_id=connection,
        )
        return self._binding_from_response(
            reference=reference,
            response=described,
            resource_scope_id=scope,
            connection_id=connection,
        )

    def _assert_binding(self, binding: SecretBinding) -> None:
        if binding.provider != _PROVIDER_AWS:
            raise TelemetrySecretError("secret_provider_mismatch")
        if not binding.version_marker or len(binding.version_marker) > 512:
            raise TelemetrySecretError("secret_version_invalid")
        response = self._describe_owned(
            reference=binding._internal_reference,
            resource_scope_id=binding.resource_scope_id,
            connection_id=binding.connection_id,
        )
        # A stored marker is intentionally not pinned across normal rotation,
        # but provider metadata must still identify exactly one current version.
        _current_version_marker(response)

    def update(self, binding: SecretBinding, *, values: Mapping[str, str]) -> SecretBinding:
        if not self._dynamic_writes_enabled:
            raise TelemetrySecretError("dynamic_secret_writes_disabled")
        payload = _normalized_values(values)
        self._assert_binding(binding)
        try:
            self._client.update_secret(
                SecretId=binding._internal_reference,
                SecretString=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            )
        except Exception:
            logger.warning(
                "telemetry_secret_update_failed",
                extra={"event": "telemetry_secret_update_failed", "reason": "provider_error"},
            )
            raise TelemetrySecretError("secret_write_failed") from None
        with self._lock:
            self._cache.pop(self._cache_key(binding), None)
        described = self._describe_owned(
            reference=binding._internal_reference,
            resource_scope_id=binding.resource_scope_id,
            connection_id=binding.connection_id,
        )
        updated = self._binding_from_response(
            reference=binding._internal_reference,
            response=described,
            resource_scope_id=binding.resource_scope_id,
            connection_id=binding.connection_id,
            binding_id=binding.binding_id,
        )
        return updated

    def resolve(self, binding: SecretBinding, *, force_refresh: bool = False) -> ResolvedSecret:
        if binding.provider != _PROVIDER_AWS:
            raise TelemetrySecretError("secret_provider_mismatch")
        now = float(self._clock())
        cache_key = self._cache_key(binding)
        with self._lock:
            cached = self._cache.get(cache_key)
            if not force_refresh and cached is not None and cached[0] > now:
                return cached[1]
        self._assert_binding(binding)
        try:
            response = self._client.get_secret_value(SecretId=binding._internal_reference)
            resolved = _parse_secret_payload(response.get("SecretString"))
        except TelemetrySecretError:
            raise
        except Exception:
            logger.warning(
                "telemetry_secret_resolve_failed",
                extra={"event": "telemetry_secret_resolve_failed", "reason": "provider_error"},
            )
            raise TelemetrySecretError("secret_read_failed") from None
        with self._lock:
            self._cache[cache_key] = (now + self._cache_ttl_seconds, resolved)
        return resolved

    @staticmethod
    def _cache_key(binding: SecretBinding) -> str:
        """Bind cache entries to the full opaque persisted identity.

        The digest prevents references from appearing in diagnostics while a
        reference/version retarget cannot reuse another binding's cached value.
        """

        material = "\x00".join(
            (
                binding.binding_id,
                binding.provider,
                binding.resource_scope_id,
                binding.connection_id,
                binding.version_marker or "",
                binding._internal_reference,
            )
        )
        return sha256(material.encode("utf-8")).hexdigest()

    def resolve_after_auth_failure(self, binding: SecretBinding) -> ResolvedSecret:
        """Bypass the cache once after upstream authentication is rejected."""
        return self.resolve(binding, force_refresh=True)


class MemoryTelemetrySecretStore:
    """Explicitly enabled, process-local fake for unit tests only."""

    def __init__(self, *, allow_test_backend: bool = False) -> None:
        if not allow_test_backend:
            raise RuntimeError("The memory telemetry secret backend is test-only.")
        self._values: dict[str, dict[str, str]] = {}
        self._owners: dict[str, tuple[str, str]] = {}
        self._versions: dict[str, int] = {}

    def bind_preprovisioned(
        self, request: TrustedPreprovisionedSecretBinding
    ) -> SecretBinding:
        if not isinstance(request, TrustedPreprovisionedSecretBinding):
            raise TelemetrySecretError("trusted_secret_binding_required")
        reference = request._internal_reference
        if self._owners.get(reference) != (
            request.resource_scope_id,
            request.connection_id,
        ):
            raise TelemetrySecretError("secret_ownership_mismatch")
        if str(self._versions.get(reference)) != request.expected_version_marker:
            raise TelemetrySecretError("secret_version_mismatch")
        return self._binding(reference, request.resource_scope_id, request.connection_id)

    def provision_for_test(
        self, *, resource_scope_id: str, connection_id: str, values: Mapping[str, str]
    ) -> str:
        reference = f"memory:{uuid.uuid4()}"
        self._values[reference] = _normalized_values(values)
        self._owners[reference] = (resource_scope_id, connection_id)
        self._versions[reference] = 1
        return reference

    def create(
        self, *, resource_scope_id: str, connection_id: str, values: Mapping[str, str]
    ) -> SecretBinding:
        reference = self.provision_for_test(
            resource_scope_id=resource_scope_id,
            connection_id=connection_id,
            values=values,
        )
        return self._binding(reference, resource_scope_id, connection_id)

    def _binding(
        self,
        reference: str,
        scope: str,
        connection: str,
        *,
        binding_id: str | None = None,
    ) -> SecretBinding:
        return SecretBinding(
            binding_id=binding_id or str(uuid.uuid4()),
            provider=_PROVIDER_MEMORY,
            resource_scope_id=scope,
            connection_id=connection,
            internal_reference=reference,
            version_marker=str(self._versions[reference]),
            updated_at=datetime.now(UTC),
        )

    def _assert_owned(self, binding: SecretBinding) -> None:
        if binding.provider != _PROVIDER_MEMORY:
            raise TelemetrySecretError("secret_provider_mismatch")
        if self._owners.get(binding._internal_reference) != (
            binding.resource_scope_id,
            binding.connection_id,
        ):
            raise TelemetrySecretError("secret_ownership_mismatch")

    def update(self, binding: SecretBinding, *, values: Mapping[str, str]) -> SecretBinding:
        self._assert_owned(binding)
        reference = binding._internal_reference
        self._values[reference] = _normalized_values(values)
        self._versions[reference] += 1
        return self._binding(
            reference,
            binding.resource_scope_id,
            binding.connection_id,
            binding_id=binding.binding_id,
        )

    def resolve(self, binding: SecretBinding, *, force_refresh: bool = False) -> ResolvedSecret:
        del force_refresh
        self._assert_owned(binding)
        return ResolvedSecret(self._values[binding._internal_reference])

    def resolve_after_auth_failure(self, binding: SecretBinding) -> ResolvedSecret:
        return self.resolve(binding, force_refresh=True)
