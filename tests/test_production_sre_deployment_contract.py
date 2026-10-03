"""Guard the image-only SRE rollout against Production V2 config drift."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/deploy-production-sre-v2.py"
spec = importlib.util.spec_from_file_location("sre_deploy", SCRIPT)
assert spec and spec.loader
sre_deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sre_deploy)


def task_definition(role: str = "api") -> dict:
    return {
        "family": "neraium-prod-" + role,
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "taskRoleArn": "arn:aws:iam::680779862188:role/app",
        "executionRoleArn": "arn:aws:iam::680779862188:role/execution",
        "volumes": [],
        "containerDefinitions": [{
            "name": role,
            "image": "repository@" + sre_deploy.BASE_DIGEST,
            "environment": [
                {"name": "APP_ENV", "value": "prod"},
                {"name": "NERAIUM_PROCESS_ROLE", "value": role},
                {"name": "NERAIUM_TELEMETRY_EXECUTION_IDENTITY_VERSION", "value": "physical-endpoint-keyed.v2"},
                {"name": "NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED", "value": "true"},
                {"name": "NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES", "value": "false"},
                {"name": "NERAIUM_TELEMETRY_EXECUTOR_URL", "value": "https://10.40.32.20:8443"},
                {"name": "NERAIUM_TELEMETRY_EXECUTOR_CA_PEM", "value": "synthetic-ca"},
                {"name": "NERAIUM_TELEMETRY_EXECUTOR_AUTH_SECRET_ARN", "value": "arn:aws:secretsmanager:us-east-2:680779862188:secret:neraium/prod/connector-executor-auth-example"},
            ],
            "secrets": [
                {"name": "NERAIUM_TELEMETRY_DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:us-east-2:680779862188:secret:neraium/prod/telemetry-database-url-example"},
                {"name": "NERAIUM_RUNTIME_DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:us-east-2:680779862188:secret:neraium/prod/telemetry-database-url-example"},
                *([{"name": "NERAIUM_API_TOKEN", "valueFrom": "arn:aws:secretsmanager:us-east-2:680779862188:secret:api-token-example"}] if role == "api" else []),
            ],
        }],
    }


@pytest.mark.parametrize("role", ["api", "worker"])
def test_image_only_candidate_keeps_v2_bindings(role: str) -> None:
    original = task_definition(role)
    expected = sre_deploy.certified_bindings(original, role)
    candidate = sre_deploy.image_only_registration(original, "repository@sha256:new", set(original))
    assert candidate["containerDefinitions"][0]["image"] == "repository@sha256:new"
    assert sre_deploy.certified_bindings(candidate, role) == expected
    assert original["containerDefinitions"][0]["image"].endswith(sre_deploy.BASE_DIGEST)


@pytest.mark.parametrize("name,value", [
    ("NERAIUM_TELEMETRY_EXECUTION_IDENTITY_VERSION", "concept-keyed.v1"),
    ("NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED", "false"),
    ("NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES", "true"),
    ("NERAIUM_TELEMETRY_EXECUTOR_URL", "https://example.invalid"),
    ("NERAIUM_TELEMETRY_EXECUTOR_CA_PEM", ""),
])
def test_unsafe_runtime_boundary_fails_closed(name: str, value: str) -> None:
    definition = task_definition()
    for item in definition["containerDefinitions"][0]["environment"]:
        if item["name"] == name:
            item["value"] = value
    with pytest.raises(RuntimeError):
        sre_deploy.certified_bindings(definition, "api")


def test_missing_runtime_database_binding_fails_closed() -> None:
    definition = task_definition()
    definition["containerDefinitions"][0]["secrets"] = [
        item for item in definition["containerDefinitions"][0]["secrets"]
        if item["name"] != "NERAIUM_RUNTIME_DATABASE_URL"
    ]
    with pytest.raises(RuntimeError, match="runtime_database_binding_changed"):
        sre_deploy.certified_bindings(definition, "api")


@pytest.mark.parametrize("role", ["api", "worker"])
def test_github_workflow_rejects_v2_boundary_drift(role: str, tmp_path: Path) -> None:
    workflow = (SCRIPT.parents[1] / ".github/workflows/deploy-backend.yml").read_text()
    match = re.search(
        rf"jq -e --slurpfile before current-{role}-task-definition\.json '([\s\S]*?)' next-{role}-task-definition\.json",
        workflow,
    )
    assert match, "workflow V2 contract check missing"
    program = match.group(1)
    original = task_definition(role)
    before = tmp_path / "before.json"
    before.write_text(json.dumps(original))
    candidate = sre_deploy.image_only_registration(original, "repository@sha256:new", set(original))

    def check(definition: dict) -> int:
        target = tmp_path / "candidate.json"
        target.write_text(json.dumps(definition))
        return subprocess.run(
            ["jq", "-e", "--slurpfile", "before", str(before), program, str(target)],
            check=False, capture_output=True, text=True,
        ).returncode

    assert check(candidate) == 0
    candidate["containerDefinitions"][0]["secrets"][0]["valueFrom"] = "changed"
    assert check(candidate) != 0
    candidate = sre_deploy.image_only_registration(original, "repository@sha256:new", set(original))
    for item in candidate["containerDefinitions"][0]["environment"]:
        if item["name"] == "NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED":
            item["value"] = "false"
    assert check(candidate) != 0


def test_legacy_workflow_cannot_auto_roll_out_older_image() -> None:
    workflow = (SCRIPT.parents[1] / ".github/workflows/deploy-backend.yml").read_text()
    legacy_dockerfile = (SCRIPT.parents[1] / "infra/production/Dockerfile.connector-overlay").read_text()
    assert "  workflow_dispatch:" in workflow
    assert "  push:" not in workflow
    assert 'grep -Fxq "FROM $CERTIFIED_IMAGE" infra/production/Dockerfile.connector-overlay' in workflow
    assert f"FROM {sre_deploy.ECR_PREFIX.split(':sre-v2-')[0]}@{sre_deploy.BASE_DIGEST}" not in legacy_dockerfile
