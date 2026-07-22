from pathlib import Path


def test_backend_deploy_opens_the_declared_container_port_and_preserves_healthcheck_quotes() -> None:
    workflow = (Path(__file__).parents[1] / ".github/workflows/deploy-backend.yml").read_text(encoding="utf-8")

    assert '--port "$API_CONTAINER_PORT"' in workflow
    assert '--source-group "$LOAD_BALANCER_SECURITY_GROUP_ID"' in workflow
    assert '--arg HEALTHCHECK_COMMAND' in workflow
    assert 'urllib.request.urlopen(\'http://127.0.0.1:${API_CONTAINER_PORT}/api/health\'' in workflow
    assert '"command": ["CMD-SHELL", $HEALTHCHECK_COMMAND]' in workflow
