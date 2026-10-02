"""Production V2 prerequisites and the explicit migration command."""

from dataclasses import replace

import pytest

from app.core.config import Settings, validate_settings
from db.migrations import apply_telemetry


def test_v2_production_settings_fail_closed_until_required_configuration_is_present(tmp_path) -> None:
    base = Settings(
        app_env="production", backend_host="127.0.0.1", backend_port=8010,
        cors_origins=["https://app.neraium.com"], runtime_dir=tmp_path,
        telemetry_execution_identity_version="physical-endpoint-keyed.v2",
    )
    with pytest.raises(ValueError, match="TELEMETRY_DATABASE_URL"):
        validate_settings(base)
    database = replace(base, telemetry_database_url="postgresql://user:pass@db.example.test/neraium?sslmode=require")
    with pytest.raises(ValueError, match="TELEMETRY_SECRET_REGION"):
        validate_settings(database)
    region = replace(database, telemetry_secret_region="us-east-2")
    with pytest.raises(ValueError, match="TELEMETRY_CONTROLLED_EGRESS_ENABLED"):
        validate_settings(region)
    controlled = replace(region, telemetry_controlled_egress_enabled=True)
    with pytest.raises(ValueError, match="isolated connector executor"):
        validate_settings(controlled)
    executor = replace(controlled,
        telemetry_executor_url="https://10.40.32.20:8443",
        telemetry_executor_ca_pem="-----BEGIN CERTIFICATE-----\ncert\n-----END CERTIFICATE-----",
        telemetry_executor_auth_secret_arn="arn:aws:secretsmanager:us-east-2:000000000000:secret:executor-auth",
    )
    validate_settings(executor)
    with pytest.raises(ValueError, match="forbids NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES"):
        validate_settings(replace(executor,
                                  telemetry_dynamic_secret_writes_enabled=True))
    validate_settings(replace(base, telemetry_execution_identity_version="concept-keyed.v1"))


def test_telemetry_migration_command_requires_database(monkeypatch) -> None:
    monkeypatch.delenv("NERAIUM_TELEMETRY_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="telemetry_database_not_configured"):
        apply_telemetry.main()
