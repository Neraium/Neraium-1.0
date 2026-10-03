#!/usr/bin/env python3
"""Deploy the SRE-only V2 overlay by changing only certified ECS image references.

This intentionally does not use the generic backend workflow's repository
variables or rewrite task environment and secret bindings.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
import subprocess
import sys

import boto3


REGION = "us-east-2"
CLUSTER = "neraium-prod-cluster"
API_SERVICE = "neraium-prod-api-service"
WORKER_SERVICE = "neraium-prod-worker-service"
BASE_TASKS = {
    API_SERVICE: "arn:aws:ecs:us-east-2:680779862188:task-definition/neraium-prod-api:338",
    WORKER_SERVICE: "arn:aws:ecs:us-east-2:680779862188:task-definition/neraium-prod-worker:332",
}
BASE_DIGEST = "sha256:d57f44d3f1af85d6a6eddfcf29c8b99198a63cd5de58ae21408d7fae90594816"
SRE_COMMIT = "74a542562f4569f9e72c58a0efcd96ff0801b2af"
ECR_PREFIX = "680779862188.dkr.ecr.us-east-2.amazonaws.com/neraium-prod-api:sre-v2-"
TOPIC_ARN = "arn:aws:sns:us-east-2:680779862188:neraium-prod-infrastructure-alerts"


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise RuntimeError(reason)


def certified_bindings(task_definition: dict, role: str) -> dict:
    """Validate the live V2 boundary and return a comparison-only fingerprint."""
    containers = task_definition["containerDefinitions"]
    _require(len(containers) == 1, "unexpected_container_count")
    container = containers[0]
    env = {item["name"]: item["value"] for item in container.get("environment", [])}
    secrets = {item["name"]: item["valueFrom"] for item in container.get("secrets", [])}
    _require(env.get("APP_ENV") == "prod", "production_environment_missing")
    _require(env.get("NERAIUM_PROCESS_ROLE") == role, "process_role_changed")
    _require(env.get("NERAIUM_TELEMETRY_EXECUTION_IDENTITY_VERSION") == "physical-endpoint-keyed.v2", "v2_identity_missing")
    _require(env.get("NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED") == "true", "controlled_egress_missing")
    _require(env.get("NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES") == "false", "dynamic_secret_writes_enabled")
    _require(env.get("NERAIUM_TELEMETRY_EXECUTOR_URL") == "https://10.40.32.20:8443", "executor_endpoint_changed")
    _require(bool(env.get("NERAIUM_TELEMETRY_EXECUTOR_CA_PEM")), "executor_ca_missing")
    auth = env.get("NERAIUM_TELEMETRY_EXECUTOR_AUTH_SECRET_ARN", "")
    _require(auth.startswith("arn:aws:secretsmanager:us-east-2:680779862188:secret:neraium/prod/connector-executor-auth-"), "executor_auth_reference_changed")
    database = secrets.get("NERAIUM_TELEMETRY_DATABASE_URL", "")
    _require(database.startswith("arn:aws:secretsmanager:us-east-2:680779862188:secret:neraium/prod/telemetry-database-url-"), "telemetry_database_binding_missing")
    _require(secrets.get("NERAIUM_RUNTIME_DATABASE_URL") == database, "runtime_database_binding_changed")
    _require(bool(secrets.get("NERAIUM_API_TOKEN")) if role == "api" else True, "api_token_binding_missing")
    _require(task_definition.get("networkMode") == "awsvpc", "network_mode_changed")
    _require("FARGATE" in task_definition.get("requiresCompatibilities", []), "fargate_boundary_changed")
    return {
        "environment": deepcopy(container.get("environment", [])),
        "secrets": deepcopy(container.get("secrets", [])),
        "executor_ca_sha256": hashlib.sha256(env["NERAIUM_TELEMETRY_EXECUTOR_CA_PEM"].encode()).hexdigest(),
        "task_role": task_definition.get("taskRoleArn"),
        "execution_role": task_definition.get("executionRoleArn"),
        "network_mode": task_definition.get("networkMode"),
        "volumes": deepcopy(task_definition.get("volumes", [])),
    }


def image_only_registration(task_definition: dict, image_uri: str, allowed_fields: set[str]) -> dict:
    """Construct ECS registration input from the live definition, changing only image."""
    original = {key: deepcopy(value) for key, value in task_definition.items() if key in allowed_fields}
    candidate = deepcopy(original)
    _require(len(candidate["containerDefinitions"]) == 1, "unexpected_container_count")
    candidate["containerDefinitions"][0]["image"] = image_uri
    comparison = deepcopy(candidate)
    comparison["containerDefinitions"][0]["image"] = original["containerDefinitions"][0]["image"]
    _require(comparison == original, "task_definition_not_image_only")
    return candidate


def _services(ecs) -> dict:
    response = ecs.describe_services(cluster=CLUSTER, services=[API_SERVICE, WORKER_SERVICE])
    _require(not response.get("failures"), "ecs_service_lookup_failed")
    return {service["serviceName"]: service for service in response["services"]}


def _running_digest(ecs, service_name: str) -> set[str]:
    task_arns = ecs.list_tasks(cluster=CLUSTER, serviceName=service_name, desiredStatus="RUNNING")["taskArns"]
    _require(len(task_arns) == 1, "running_task_count_unexpected")
    tasks = ecs.describe_tasks(cluster=CLUSTER, tasks=task_arns)["tasks"]
    return {container.get("imageDigest", "") for task in tasks for container in task.get("containers", [])}


def _health() -> None:
    for endpoint in ("health", "ready"):
        subprocess.run(
            ["curl", "--fail", "--silent", "--show-error", "--max-time", "10", "https://app.neraium.com/api/" + endpoint],
            stdout=subprocess.DEVNULL, check=True,
        )


def _dependencies() -> None:
    rds = boto3.client("rds", region_name=REGION)
    ec2 = boto3.client("ec2", region_name=REGION)
    db = rds.describe_db_instances(DBInstanceIdentifier="neraium-prod-postgres")["DBInstances"][0]
    _require(db["DBInstanceStatus"] == "available", "production_database_unavailable")
    host = ec2.describe_instance_status(InstanceIds=["i-081d0aba82dba64e7"], IncludeAllInstances=True)["InstanceStatuses"][0]
    _require(host["InstanceState"]["Name"] == "running", "connector_executor_not_running")
    _require(host["SystemStatus"]["Status"] == "ok" and host["InstanceStatus"]["Status"] == "ok", "connector_executor_status_failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-uri", required=True)
    parser.add_argument("--apply", action="store_true", help="Register image-only revisions and update both services")
    args = parser.parse_args()
    _require(args.image_uri == ECR_PREFIX + SRE_COMMIT, "image_tag_not_sre_commit")
    expected_digest = None
    deployment_image_uri = args.image_uri
    if args.apply:
        ecr = boto3.client("ecr", region_name=REGION)
        tag = args.image_uri.rsplit(":", 1)[1]
        image = ecr.describe_images(repositoryName="neraium-prod-api", imageIds=[{"imageTag": tag}])["imageDetails"][0]
        expected_digest = image["imageDigest"]
        deployment_image_uri = args.image_uri.rsplit(":", 1)[0] + "@" + expected_digest
    ecs = boto3.client("ecs", region_name=REGION)
    services = _services(ecs)
    allowed = set(ecs.meta.service_model.operation_model("RegisterTaskDefinition").input_shape.members)
    candidates = {}
    fingerprints = {}
    for name, role in ((API_SERVICE, "api"), (WORKER_SERVICE, "worker")):
        service = services[name]
        _require(service["taskDefinition"] == BASE_TASKS[name], "certified_task_revision_changed")
        _require(service["desiredCount"] == service["runningCount"] == 1, "production_service_unhealthy")
        _require(_running_digest(ecs, name) == {BASE_DIGEST}, "certified_image_digest_changed")
        definition = ecs.describe_task_definition(taskDefinition=BASE_TASKS[name])["taskDefinition"]
        _require(BASE_DIGEST in definition["containerDefinitions"][0]["image"], "certified_image_reference_changed")
        fingerprints[name] = certified_bindings(definition, role)
        candidates[name] = image_only_registration(definition, deployment_image_uri, allowed)
        _require(certified_bindings(candidates[name], role) == fingerprints[name], "v2_binding_changed_in_candidate")
    def binding(fingerprint: dict, name: str) -> str:
        return next(item["valueFrom"] for item in fingerprint["secrets"] if item["name"] == name)

    _require(
        binding(fingerprints[API_SERVICE], "NERAIUM_TELEMETRY_DATABASE_URL")
        == binding(fingerprints[WORKER_SERVICE], "NERAIUM_TELEMETRY_DATABASE_URL"),
        "api_worker_database_binding_mismatch",
    )
    _health()
    _dependencies()
    sns = boto3.client("sns", region_name=REGION)
    subscriptions = sns.list_subscriptions_by_topic(TopicArn=TOPIC_ARN)["Subscriptions"]
    _require(any(item["Protocol"] == "email" and item["Endpoint"] == "craig@neraium.com" and item["SubscriptionArn"].startswith("arn:aws:sns:") for item in subscriptions), "operator_subscription_unconfirmed")
    print(json.dumps({"preflight": "PASS", "certified_api": BASE_TASKS[API_SERVICE], "certified_worker": BASE_TASKS[WORKER_SERVICE], "image_only": True, "v2_bindings_preserved": True, "apply": args.apply}))
    if not args.apply:
        return 0
    registered = {}
    updated = False
    try:
        for name, role in ((WORKER_SERVICE, "worker"), (API_SERVICE, "api")):
            created = ecs.register_task_definition(**candidates[name])["taskDefinition"]
            _require(certified_bindings(created, role) == fingerprints[name], "registered_v2_binding_changed")
            registered[name] = created["taskDefinitionArn"]
        for name in (WORKER_SERVICE, API_SERVICE):
            updated = True
            ecs.update_service(cluster=CLUSTER, service=name, taskDefinition=registered[name])
        ecs.get_waiter("services_stable").wait(cluster=CLUSTER, services=[API_SERVICE, WORKER_SERVICE], WaiterConfig={"Delay": 15, "MaxAttempts": 40})
        after = _services(ecs)
        for name in (API_SERVICE, WORKER_SERVICE):
            _require(after[name]["taskDefinition"] == registered[name], "service_revision_mismatch")
            _require(after[name]["desiredCount"] == after[name]["runningCount"] == 1, "service_not_stable")
            _require(_running_digest(ecs, name) == {expected_digest}, "deployed_digest_mismatch")
        _health()
        _dependencies()
        print(json.dumps({"deployment": "PASS", "api_task_definition": registered[API_SERVICE], "worker_task_definition": registered[WORKER_SERVICE], "image_digest": expected_digest}))
        return 0
    except Exception:
        if updated:
            for name in (API_SERVICE, WORKER_SERVICE):
                ecs.update_service(cluster=CLUSTER, service=name, taskDefinition=BASE_TASKS[name])
            ecs.get_waiter("services_stable").wait(cluster=CLUSTER, services=[API_SERVICE, WORKER_SERVICE], WaiterConfig={"Delay": 15, "MaxAttempts": 40})
            restored = _services(ecs)
            for name in (API_SERVICE, WORKER_SERVICE):
                _require(restored[name]["taskDefinition"] == BASE_TASKS[name], "rollback_revision_mismatch")
                _require(restored[name]["desiredCount"] == restored[name]["runningCount"] == 1, "rollback_service_unstable")
                _require(_running_digest(ecs, name) == {BASE_DIGEST}, "rollback_digest_mismatch")
            _health()
            _dependencies()
            print(json.dumps({"deployment": "ROLLED_BACK", "api_task_definition": BASE_TASKS[API_SERVICE], "worker_task_definition": BASE_TASKS[WORKER_SERVICE]}))
        raise


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print(json.dumps({"deployment": "FAILED", "reason_type": type(error).__name__, "reason": str(error) if isinstance(error, RuntimeError) else "see_operator_logs"}), file=sys.stderr)
        sys.exit(1)
