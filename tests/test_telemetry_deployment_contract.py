from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_telemetry_migration_entrypoint_is_forward_only_and_ordered() -> None:
    source = read("backend/db/migrate_telemetry.py")
    ast.parse(source)

    assert "(apply_002, apply_003, apply_004, apply_005)" in source
    assert "(verify_002, verify_003, verify_004, verify_005)" in source
    assert "rollback" not in source.lower()
    assert "get_settings().telemetry_database_url" in source
    assert 'os.getenv("NERAIUM_TELEMETRY_APPLICATION_DATABASE_URL", "")' in source
    assert source.count("for verifier in (verify_002, verify_003, verify_004, verify_005)") == 2


def test_production_tasks_receive_telemetry_dsn_only_as_a_secret() -> None:
    workflow = read(".github/workflows/deploy-backend.yml")

    assert workflow.count(
        '{"name": "NERAIUM_TELEMETRY_DATABASE_URL", "valueFrom": $TELEMETRY_DATABASE_URL_SECRET_ARN}'
    ) == 2
    assert '{"name": "NERAIUM_TELEMETRY_DATABASE_URL", "value":' not in workflow
    assert "TELEMETRY_DATABASE_URL_SECRET_ARN: ${{ vars.NERAIUM_TELEMETRY_DATABASE_URL_SECRET_ARN }}" in workflow
    assert "TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN: ${{ vars.NERAIUM_TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN }}" in workflow


def test_production_telemetry_rollout_is_fail_closed() -> None:
    workflow = read(".github/workflows/deploy-backend.yml")
    migration_position = workflow.index("Apply and verify telemetry schema before service rollout")
    service_position = workflow.index("Update ECS services to new task definitions")

    assert migration_position < service_position
    assert '["python", "-m", "db.migrate_telemetry"]' in workflow
    assert 'test "$MIGRATION_EXIT_CODE" = "0"' in workflow
    assert '{"name": "NERAIUM_TELEMETRY_APPLICATION_DATABASE_URL", "valueFrom": $APPLICATION_SECRET_ARN}' in workflow
    assert 'test "$RDS_NETWORK_READY" = "true"' in workflow
    assert '{"name": "NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES", "value": "false"}' in workflow
    assert '{"name": "NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED", "value": "false"}' in workflow


def test_bootstrap_grants_only_read_access_to_connection_secrets() -> None:
    bootstrap = read("scripts/bootstrap-production-aws.sh")

    assert "neraium/prod/telemetry-connections/*" in bootstrap
    assert '["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"]' in bootstrap
    assert "secretsmanager:CreateSecret" not in bootstrap
    assert "secretsmanager:UpdateSecret" not in bootstrap
    assert "secretsmanager:DeleteSecret" not in bootstrap
    assert "secretsmanager:ListSecrets" not in bootstrap
