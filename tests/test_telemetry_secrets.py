from __future__ import annotations

import json
from datetime import UTC, datetime
import re

import pytest
from fastapi.encoders import jsonable_encoder

from app.services.telemetry_secrets import (
    AwsSecretsManagerTelemetryStore,
    MemoryTelemetrySecretStore,
    SecretBinding,
    TelemetrySecretError,
    TrustedPreprovisionedSecretBinding,
)
from app.engine.sii.behavioral_model_contract import canonical_phase4_resource_scope_id


class FakeSecretsManager:
    def __init__(self) -> None:
        self.secret_string = json.dumps({"token": "canary-one"})
        self.version = "version-1"
        self.tags = [
            {"Key": "neraium:managed-by", "Value": "telemetry-connections"},
            {"Key": "neraium:resource-scope-id", "Value": "scope-a"},
            {"Key": "neraium:connection-id", "Value": "connection-a"},
        ]
        self.calls: list[tuple[str, dict]] = []

    def describe_secret(self, **kwargs):
        self.calls.append(("describe_secret", kwargs))
        return {
            "Tags": self.tags,
            "VersionIdsToStages": {self.version: ["AWSCURRENT"]},
            "LastChangedDate": datetime(2026, 8, 25, tzinfo=UTC),
        }

    def get_secret_value(self, **kwargs):
        self.calls.append(("get_secret_value", kwargs))
        return {"SecretString": self.secret_string}

    def create_secret(self, **kwargs):
        self.calls.append(("create_secret", kwargs))
        self.secret_string = kwargs["SecretString"]
        self.tags = kwargs["Tags"]
        return {
            "ARN": "arn:aws:secretsmanager:us-east-1:123456789012:secret:"
            "neraium/prod/telemetry-connections/scope-a/connection-a-AbCd12"
        }

    def update_secret(self, **kwargs):
        self.calls.append(("update_secret", kwargs))
        self.secret_string = kwargs["SecretString"]
        self.version = "version-2"
        return {"VersionId": self.version}


@pytest.fixture
def reference() -> str:
    return (
        "arn:aws:secretsmanager:us-east-1:123456789012:secret:"
        "neraium/prod/telemetry-connections/scope-a/connection-a-AbCd12"
    )


def trusted_binding(
    reference: str,
    *,
    resource_scope_id: str = "scope-a",
    connection_id: str = "connection-a",
    expected_version_marker: str = "version-1",
) -> TrustedPreprovisionedSecretBinding:
    return TrustedPreprovisionedSecretBinding(
        resource_scope_id=resource_scope_id,
        connection_id=connection_id,
        internal_reference=reference,
        expected_version_marker=expected_version_marker,
    )


def test_preprovisioned_binding_is_opaque_and_public_metadata_is_safe(reference: str) -> None:
    client = FakeSecretsManager()
    store = AwsSecretsManagerTelemetryStore(client=client, environment="prod")

    request = trusted_binding(reference)
    binding = store.bind_preprovisioned(request)

    assert reference not in repr(request)
    with pytest.raises(AttributeError, match="immutable"):
        request._internal_reference = "memory:retargeted"  # type: ignore[misc]
    assert reference not in repr(binding)
    public = binding.public_metadata().as_dict()
    assert public == {
        "credentials_configured": True,
        "credential_version": "version-1",
        "credentials_updated_at": "2026-08-25T00:00:00+00:00",
    }
    assert reference not in json.dumps(public)
    assert "internal_reference" not in public
    fields = binding.internal_persistence_fields()
    assert reference not in repr(fields)
    with pytest.raises(TypeError):
        json.dumps(fields)
    with pytest.raises(ValueError):
        jsonable_encoder(fields)


def test_preprovisioned_binding_enforces_namespace_and_owner(reference: str) -> None:
    client = FakeSecretsManager()
    store = AwsSecretsManagerTelemetryStore(client=client, environment="prod")
    with pytest.raises(TelemetrySecretError, match="Telemetry credentials") as error:
        store.bind_preprovisioned(
            trusted_binding(reference, resource_scope_id="scope-b")
        )
    assert error.value.code == "secret_ownership_mismatch"

    with pytest.raises(TelemetrySecretError) as error:
        store.bind_preprovisioned(
            trusted_binding(
                "arn:aws:secretsmanager:us-east-1:123456789012:secret:other/app"
            )
        )
    assert error.value.code == "secret_reference_not_allowed"


def test_preprovisioned_binding_requires_trusted_contract_and_exact_current_version(
    reference: str,
) -> None:
    client = FakeSecretsManager()
    store = AwsSecretsManagerTelemetryStore(client=client, environment="prod")

    with pytest.raises(TelemetrySecretError) as trust_error:
        store.bind_preprovisioned(reference)  # type: ignore[arg-type]
    assert trust_error.value.code == "trusted_secret_binding_required"

    with pytest.raises(TelemetrySecretError) as version_error:
        store.bind_preprovisioned(
            trusted_binding(reference, expected_version_marker="unapproved-version")
        )
    assert version_error.value.code == "secret_version_mismatch"
    assert reference not in repr(version_error.value)

    client.version = ""
    with pytest.raises(TelemetrySecretError) as invalid_version_error:
        store.bind_preprovisioned(
            trusted_binding(reference, expected_version_marker="version-1")
        )
    assert invalid_version_error.value.code == "secret_version_invalid"


def test_resolve_cache_and_auth_failure_force_a_secret_refresh(reference: str) -> None:
    client = FakeSecretsManager()
    store = AwsSecretsManagerTelemetryStore(client=client, environment="prod", cache_ttl_seconds=60)
    binding = store.bind_preprovisioned(trusted_binding(reference))
    assert store.resolve(binding).get_required("token") == "canary-one"

    client.secret_string = json.dumps({"token": "canary-two"})
    assert store.resolve(binding).get_required("token") == "canary-one"
    assert store.resolve_after_auth_failure(binding).get_required("token") == "canary-two"
    assert [name for name, _ in client.calls].count("get_secret_value") == 2


def test_cache_identity_cannot_be_reused_to_retarget_credentials(reference: str) -> None:
    second_reference = reference.replace("connection-a-AbCd12", "connection-a-EfGh34")

    class RoutedClient(FakeSecretsManager):
        def get_secret_value(self, **kwargs):
            self.calls.append(("get_secret_value", kwargs))
            token = "first-canary" if kwargs["SecretId"] == reference else "second-canary"
            return {"SecretString": json.dumps({"token": token})}

    client = RoutedClient()
    store = AwsSecretsManagerTelemetryStore(client=client, environment="prod")
    first = store.bind_preprovisioned(trusted_binding(reference))
    assert store.resolve(first).get_required("token") == "first-canary"

    retargeted = SecretBinding.from_internal_persistence(
        binding_id=first.binding_id,
        provider="aws_secrets_manager",
        resource_scope_id=first.resource_scope_id,
        connection_id=first.connection_id,
        internal_reference=second_reference,
        version_marker=first.version_marker,
    )
    assert store.resolve(retargeted).get_required("token") == "second-canary"
    assert [name for name, _ in client.calls].count("get_secret_value") == 2


def test_provider_errors_and_secret_objects_do_not_leak_canaries(reference: str, caplog) -> None:
    class FailingClient(FakeSecretsManager):
        def get_secret_value(self, **kwargs):
            raise RuntimeError(f"provider exploded {reference} canary-value")

    client = FailingClient()
    store = AwsSecretsManagerTelemetryStore(client=client, environment="prod")
    binding = store.bind_preprovisioned(trusted_binding(reference))
    with pytest.raises(TelemetrySecretError) as error:
        store.resolve(binding)
    combined = f"{error.value!r} {error.value} {caplog.text}"
    assert error.value.code == "secret_read_failed"
    assert reference not in combined
    assert "canary-value" not in combined


def test_dynamic_writes_are_disabled_until_explicitly_enabled() -> None:
    store = AwsSecretsManagerTelemetryStore(client=FakeSecretsManager(), environment="prod")
    with pytest.raises(TelemetrySecretError) as error:
        store.create(
            resource_scope_id="scope-a",
            connection_id="connection-a",
            values={"token": "never-written"},
        )
    assert error.value.code == "dynamic_secret_writes_disabled"


def test_dynamic_create_and_update_use_only_narrow_secret_operations() -> None:
    client = FakeSecretsManager()
    store = AwsSecretsManagerTelemetryStore(
        client=client, environment="prod", dynamic_writes_enabled=True
    )
    binding = store.create(
        resource_scope_id="scope-a", connection_id="connection-a", values={"token": "create-canary"}
    )
    updated = store.update(binding, values={"token": "update-canary"})

    assert updated.binding_id == binding.binding_id
    assert updated.public_metadata().credentials_configured is True
    assert {name for name, _ in client.calls} <= {
        "create_secret", "update_secret", "get_secret_value", "describe_secret"
    }
    create_call = next(kwargs for name, kwargs in client.calls if name == "create_secret")
    assert create_call["Name"].startswith("neraium/prod/telemetry-connections/scope-")
    assert re.fullmatch(r"[A-Za-z0-9/_+=.@-]+", create_call["Name"])
    assert ":" not in create_call["Name"]
    assert json.loads(create_call["SecretString"]) == {"token": "create-canary"}


def test_dynamic_create_hashes_actual_phase4_scope_and_preserves_authority_in_tags() -> None:
    resource_scope_id = canonical_phase4_resource_scope_id(
        "tenant-production-a",
        "ws-facility-production-a",
    )
    connection_id = "00000000-0000-0000-0000-000000000001"
    first_client = FakeSecretsManager()
    second_client = FakeSecretsManager()
    first_store = AwsSecretsManagerTelemetryStore(
        client=first_client,
        environment="prod",
        dynamic_writes_enabled=True,
    )
    second_store = AwsSecretsManagerTelemetryStore(
        client=second_client,
        environment="prod",
        dynamic_writes_enabled=True,
    )

    first_store.create(
        resource_scope_id=resource_scope_id,
        connection_id=connection_id,
        values={"token": "first-canary"},
    )
    second_store.create(
        resource_scope_id=resource_scope_id,
        connection_id=connection_id,
        values={"token": "second-canary"},
    )
    first_call = next(kwargs for name, kwargs in first_client.calls if name == "create_secret")
    second_call = next(kwargs for name, kwargs in second_client.calls if name == "create_secret")

    assert first_call["Name"] == second_call["Name"]
    assert resource_scope_id not in first_call["Name"]
    assert connection_id not in first_call["Name"]
    assert ":" not in first_call["Name"]
    assert re.fullmatch(r"[A-Za-z0-9/_+=.@-]+", first_call["Name"])
    tags = {tag["Key"]: tag["Value"] for tag in first_call["Tags"]}
    assert tags["neraium:resource-scope-id"] == resource_scope_id
    assert tags["neraium:connection-id"] == connection_id


def test_memory_backend_requires_explicit_test_opt_in_and_checks_ownership() -> None:
    with pytest.raises(RuntimeError, match="test-only"):
        MemoryTelemetrySecretStore()

    store = MemoryTelemetrySecretStore(allow_test_backend=True)
    reference = store.provision_for_test(
        resource_scope_id="scope-a", connection_id="connection-a", values={"token": "memory-canary"}
    )
    binding = store.bind_preprovisioned(
        trusted_binding(reference, expected_version_marker="1")
    )
    assert store.resolve(binding).get_required("token") == "memory-canary"
    with pytest.raises(TelemetrySecretError) as error:
        store.bind_preprovisioned(
            trusted_binding(
                reference,
                resource_scope_id="scope-b",
                expected_version_marker="1",
            )
        )
    assert error.value.code == "secret_ownership_mismatch"


def test_cross_provider_binding_is_rejected(reference: str) -> None:
    client = FakeSecretsManager()
    store = AwsSecretsManagerTelemetryStore(client=client, environment="prod")
    binding = SecretBinding.from_internal_persistence(
        binding_id="binding-a",
        provider="test_memory",
        resource_scope_id="scope-a",
        connection_id="connection-a",
        internal_reference=reference,
    )
    with pytest.raises(TelemetrySecretError) as error:
        store.resolve(binding)
    assert error.value.code == "secret_provider_mismatch"


def test_persisted_aws_binding_without_version_fails_closed(reference: str) -> None:
    store = AwsSecretsManagerTelemetryStore(client=FakeSecretsManager(), environment="prod")
    binding = SecretBinding.from_internal_persistence(
        binding_id="binding-a",
        provider="aws_secrets_manager",
        resource_scope_id="scope-a",
        connection_id="connection-a",
        internal_reference=reference,
        version_marker=None,
    )
    with pytest.raises(TelemetrySecretError) as error:
        store.resolve(binding)
    assert error.value.code == "secret_version_invalid"
    assert reference not in repr(error.value)
