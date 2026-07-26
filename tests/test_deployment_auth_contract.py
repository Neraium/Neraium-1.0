from pathlib import Path


def test_backend_deploy_opens_the_declared_container_port_and_preserves_healthcheck_quotes() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/deploy-backend.yml").read_text(encoding="utf-8")

    assert '--port "$API_CONTAINER_PORT"' in workflow
    assert '--source-group "$LOAD_BALANCER_SECURITY_GROUP_ID"' in workflow
    assert '--arg HEALTHCHECK_COMMAND' in workflow
    assert 'urllib.request.urlopen(\'http://127.0.0.1:${API_CONTAINER_PORT}/api/health\'' in workflow
    assert '"command": ["CMD-SHELL", $HEALTHCHECK_COMMAND]' in workflow


def test_backend_deploy_uses_the_rotating_rds_secret_for_auth() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github/workflows/deploy-backend.yml").read_text(encoding="utf-8")
    bootstrap = (root / "scripts/bootstrap-production-aws.sh").read_text(encoding="utf-8")

    assert '--db-instance-identifier "$RDS_AUTH_INSTANCE_ID"' in workflow
    assert "MasterUserSecret.SecretArn" in workflow
    assert '{"name": "NERAIUM_AUTH_DATABASE_SECRET_ARN", "value": $AUTH_DATABASE_SECRET_ARN}' in workflow
    assert '{"name": "NERAIUM_AUTH_DATABASE_HOST", "value": $AUTH_DATABASE_HOST}' in workflow
    assert '{"name": "NERAIUM_AUTH_DATABASE_URL", "valueFrom":' not in workflow
    assert '"Action": ["secretsmanager:GetSecretValue"]' in bootstrap
    assert '"Action": ["kms:Decrypt"]' in bootstrap
