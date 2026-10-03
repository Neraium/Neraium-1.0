#!/usr/bin/env python3
"""Canonical Production V2 release: certified runtime, committed source, image-only ECS rollout."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import tarfile
import time

import boto3

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "docs/operations/first-customer-production-baseline-2026-10-03.json"
METHOD = "certified-runtime-source-overlay.v1"
APPROVED_REF = "origin/fix/deterministic-governed-output"
REGISTRATION_FIELDS = {
    "family", "taskRoleArn", "executionRoleArn", "networkMode", "containerDefinitions",
    "volumes", "placementConstraints", "requiresCompatibilities", "cpu", "memory",
    "pidMode", "ipcMode", "proxyConfiguration", "inferenceAccelerators",
    "ephemeralStorage", "runtimePlatform", "enableFaultInjection",
}
TOPOLOGY_FIELDS = (
    "serviceName", "clusterArn", "desiredCount", "launchType", "capacityProviderStrategy",
    "platformVersion", "networkConfiguration", "loadBalancers", "deploymentConfiguration",
    "schedulingStrategy", "enableExecuteCommand", "serviceRegistries",
)
ALARM_VOLATILE = {"StateValue", "StateReason", "StateReasonData", "StateUpdatedTimestamp",
                  "StateTransitionedTimestamp", "AlarmConfigurationUpdatedTimestamp"}


class GateError(RuntimeError):
    pass


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise GateError(reason)


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def task_input(task: dict) -> dict:
    return {k: deepcopy(v) for k, v in task.items() if k in REGISTRATION_FIELDS}


def task_fingerprint(task: dict) -> str:
    normalized = task_input(task)
    for container in normalized["containerDefinitions"]:
        container.pop("image", None)
        container["environment"] = sorted(
            [x for x in container.get("environment", []) if x["name"] != "NERAIUM_BUILD_SHA"],
            key=lambda x: x["name"],
        )
        container["secrets"] = sorted(container.get("secrets", []), key=lambda x: x["name"])
    return digest(normalized)


def topology(service: dict) -> dict:
    return {k: deepcopy(service[k]) for k in TOPOLOGY_FIELDS if k in service}


def mappings(items: list, field: str) -> dict:
    require(len({x["name"] for x in items}) == len(items), "duplicate_configuration_name")
    return {x["name"]: x[field] for x in items}


def validate_task(task: dict, role: str, profile: dict) -> None:
    frozen = profile["services"][role]
    require(task.get("family") == "neraium-prod-" + role, "service_family_changed")
    require(len(task["containerDefinitions"]) == 1, "container_topology_changed")
    container = task["containerDefinitions"][0]
    require(container["name"] == role, "container_role_changed")
    env = mappings(container.get("environment", []), "value")
    secrets = mappings(container.get("secrets", []), "valueFrom")
    for key, value in {"APP_ENV": "prod", "NERAIUM_PROCESS_ROLE": role,
                       "NERAIUM_TELEMETRY_EXECUTION_IDENTITY_VERSION": "physical-endpoint-keyed.v2",
                       "NERAIUM_TELEMETRY_CONTROLLED_EGRESS_ENABLED": "true",
                       "NERAIUM_TELEMETRY_DYNAMIC_SECRET_WRITES": "false"}.items():
        require(env.get(key) == value, "invalid_" + key)
    require(env.get("NERAIUM_TELEMETRY_EXECUTOR_URL") == profile["executor"]["url"], "executor_url_changed")
    require(env.get("NERAIUM_TELEMETRY_EXECUTOR_AUTH_SECRET_ARN") == profile["executor"]["auth_secret_arn"], "executor_auth_changed")
    require(hashlib.sha256(env.get("NERAIUM_TELEMETRY_EXECUTOR_CA_PEM", "").encode()).hexdigest()
            == profile["executor"]["ca_sha256"], "executor_tls_trust_changed")
    for name in ("NERAIUM_TELEMETRY_DATABASE_URL", "NERAIUM_RUNTIME_DATABASE_URL"):
        require(secrets.get(name) == profile["database_secret_arn"], "database_binding_changed")
    require(task_fingerprint(task) == frozen["task_configuration_sha256"], "certified_task_configuration_changed")


def candidate_task(task: dict, image: str, revision: str, role: str, profile: dict) -> dict:
    validate_task(task, role, profile)
    require(re.fullmatch(re.escape(profile["ecr_repository_uri"]) + r"@sha256:[0-9a-f]{64}", image) is not None,
            "image_must_be_approved_repository_digest")
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None, "full_source_sha_required")
    candidate = task_input(task)
    container = candidate["containerDefinitions"][0]
    container["image"] = image
    container["environment"] = [x for x in container.get("environment", []) if x["name"] != "NERAIUM_BUILD_SHA"]
    container["environment"].append({"name": "NERAIUM_BUILD_SHA", "value": revision})
    validate_task(candidate, role, profile)
    return candidate


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def source_manifest(revision: str, profile: dict) -> dict:
    require(re.fullmatch(r"[0-9a-f]{40}", revision) is not None, "full_source_sha_required")
    require(git("rev-parse", revision + "^{commit}").decode().strip() == revision, "source_commit_invalid")
    require(subprocess.run(["git", "merge-base", "--is-ancestor", revision, APPROVED_REF], cwd=ROOT).returncode == 0,
            "source_not_on_approved_remote_branch")
    files = {}
    for line in git("ls-tree", "-r", "--format=%(objectmode) %(path)", revision, "--", "backend").decode().splitlines():
        mode, path = line.split(" ", 1)
        require(mode in {"100644", "100755"}, "source_symlink_or_submodule_rejected")
        name = Path(path).name
        require(not (name.startswith(".env") and name != ".env.example")
                and Path(path).suffix not in {".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3"},
                "credential_or_runtime_file_in_source")
        files[path] = hashlib.sha256(git("show", revision + ":" + path)).hexdigest()
    require(files, "source_backend_missing")
    require(set(profile["source_manifest"]).issubset(files), "source_deletion_requires_recertification")
    for path, expected in profile["protected_source"].items():
        require(files.get(path) == expected, "protected_source_change_requires_recertification:" + path)
    return files


def registry_command(profile: dict, arguments: list[str]) -> None:
    """Use short-lived ECR credentials in a temporary Docker config, never stdout."""
    import base64
    ecr = boto3.client("ecr", region_name=profile["region"])
    token = ecr.get_authorization_token()["authorizationData"][0]
    username, password = base64.b64decode(token["authorizationToken"]).decode().split(":", 1)
    with tempfile.TemporaryDirectory(prefix="neraium-ecr-auth-") as authdir:
        subprocess.run(["docker", "--config", authdir, "login", "--username", username, "--password-stdin",
                        profile["ecr_repository_uri"].split("/", 1)[0]], input=password.encode(),
                       stdout=subprocess.DEVNULL, check=True)
        subprocess.run(["docker", "--config", authdir, *arguments], check=True)


def build_image(revision: str, profile: dict, push: bool = False) -> dict:
    files = source_manifest(revision, profile)
    tag = profile["ecr_repository_uri"] + ":release-" + revision
    metadata = {"method": METHOD, "source_sha": revision, "base_image": profile["image_uri"],
                "baseline_sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(), "source_manifest": files}
    with tempfile.TemporaryDirectory(prefix="neraium-release-build-") as directory:
        context = Path(directory)
        for path in files:
            target = context / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(git("show", revision + ":" + path))
        (context / "neraium-release.json").write_text(json.dumps(metadata, sort_keys=True))
        (context / "Dockerfile").write_text(
            "FROM " + profile["image_uri"] + "\nUSER root\n"
            "COPY --chown=neraium:neraium backend/ /app/\n"
            "COPY --chown=neraium:neraium neraium-release.json /app/neraium-release.json\nUSER neraium\n"
        )
        registry_command(profile, ["build", "--label", "org.opencontainers.image.revision=" + revision,
                                  "--label", "com.neraium.release.method=" + METHOD, "-t", tag, str(context)])
    certify_image(tag, revision, profile)
    result = {"source_sha": revision, "local_image": tag, "source_manifest_sha256": digest(files)}
    if push:
        ecr = boto3.client("ecr", region_name=profile["region"])
        registry_command(profile, ["push", tag])
        details = ecr.describe_images(repositoryName="neraium-prod-api", imageIds=[{"imageTag": "release-" + revision}])["imageDetails"][0]
        result["image_uri"] = profile["ecr_repository_uri"] + "@" + details["imageDigest"]
    return result


def validate_overlay_layer(layer, allowed: dict[str, str]) -> None:
    directories = {str(parent) for name in allowed for parent in Path(name).parents if str(parent) != "."}
    for member in layer:
        name = member.name.removeprefix("./").rstrip("/")
        require(".." not in Path(name).parts and not name.startswith("/"), "image_layer_path_invalid")
        if member.isdir():
            require(name in directories, "image_layer_directory_outside_source")
        else:
            require(member.isfile() and name in allowed and not member.mode & 0o6000,
                    "image_layer_change_outside_source")
            require(hashlib.sha256(layer.extractfile(member).read()).hexdigest() == allowed[name],
                    "image_layer_content_not_committed")


def certify_overlay_layers(image: str, base_layer_count: int, allowed: dict[str, str]) -> None:
    with tempfile.TemporaryDirectory(prefix="neraium-layer-verify-") as directory:
        path = str(Path(directory) / "image.tar")
        subprocess.run(["docker", "image", "save", "--output", path, image], check=True)
        with tarfile.open(path) as archive:
            manifests = json.load(archive.extractfile("manifest.json"))
            require(len(manifests) == 1 and len(manifests[0]["Layers"]) == base_layer_count + 2,
                    "image_overlay_layer_count_invalid")
            for name in manifests[0]["Layers"][base_layer_count:]:
                with tarfile.open(fileobj=archive.extractfile(name)) as layer:
                    validate_overlay_layer(layer, allowed)


def certify_image(image: str, revision: str, profile: dict) -> None:
    files = source_manifest(revision, profile)
    config = json.loads(subprocess.check_output(["docker", "image", "inspect", image]))[0]
    base = json.loads(subprocess.check_output(["docker", "image", "inspect", profile["image_uri"]]))[0]
    require(config["RootFS"]["Layers"][:len(base["RootFS"]["Layers"])] == base["RootFS"]["Layers"], "certified_runtime_ancestry_missing")
    for field in ("User", "Env", "Entrypoint", "Cmd"):
        require(config["Config"].get(field) == base["Config"].get(field), "image_runtime_configuration_changed")
    labels = config["Config"].get("Labels") or {}
    require(labels.get("org.opencontainers.image.revision") == revision
            and labels.get("com.neraium.release.method") == METHOD, "image_provenance_labels_invalid")
    container = subprocess.check_output(["docker", "create", image]).decode().strip()
    try:
        with tempfile.TemporaryDirectory(prefix="neraium-image-verify-") as directory:
            destination = Path(directory)
            subprocess.run(["docker", "cp", container + ":/app/.", str(destination)], check=True)
            expected = {"method": METHOD, "source_sha": revision, "base_image": profile["image_uri"],
                        "baseline_sha256": hashlib.sha256(BASELINE.read_bytes()).hexdigest(), "source_manifest": files}
            require(json.loads((destination / "neraium-release.json").read_text()) == expected, "image_release_manifest_invalid")
            for path, checksum in files.items():
                actual = destination / path.removeprefix("backend/")
                require(actual.is_file() and not actual.is_symlink()
                        and hashlib.sha256(actual.read_bytes()).hexdigest() == checksum,
                        "image_source_content_mismatch:" + path)
            allowed = {"app/" + path.removeprefix("backend/"): checksum for path, checksum in files.items()}
            allowed["app/neraium-release.json"] = hashlib.sha256((destination / "neraium-release.json").read_bytes()).hexdigest()
            certify_overlay_layers(image, len(base["RootFS"]["Layers"]), allowed)
    finally:
        subprocess.run(["docker", "rm", container], check=True, stdout=subprocess.DEVNULL)


def monitoring_fingerprint(alarms: list, filters: dict) -> str:
    stable_alarms = [{k: v for k, v in a.items() if k not in ALARM_VOLATILE} for a in alarms]
    # AWS now returns the optional default explicitly. Both absent and boolean
    # false evaluate original ingested logs; true and all other values remain
    # fingerprinted. Preserve the certified hash without accepting drift in
    # filter semantics, transformations, alarms or delivery destinations.
    stable_filters = {role: [{k: v for k, v in f.items() if k not in {"creationTime", "logGroupName"}
                             and not (k == "applyOnTransformedLogs" and v is False)}
                            for f in values] for role, values in filters.items()}
    return digest({"alarms": sorted(stable_alarms, key=lambda a: a["AlarmName"]),
                   "filters": {role: sorted(values, key=lambda f: f["filterName"]) for role, values in stable_filters.items()}})


def validate_health_response(body: bytes, endpoint: str) -> None:
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        raise GateError("api_" + endpoint + "_invalid_response") from None
    require(isinstance(payload, dict) and payload.get("service") == "neraium-api"
            and payload.get("status") == {"health": "ok", "ready": "ready"}[endpoint],
            "api_" + endpoint + "_invalid_response")


class Production:
    def __init__(self, profile: dict):
        self.profile = profile
        self.session = boto3.Session(region_name=profile["region"])
        self.ecs = self.session.client("ecs")

    def snapshot(self) -> dict:
        p = self.profile
        require(self.session.client("sts").get_caller_identity()["Account"] == p["account_id"], "aws_account_mismatch")
        response = self.ecs.describe_services(cluster=p["cluster"], services=[s["service_name"] for s in p["services"].values()])
        require(not response.get("failures"), "service_lookup_failed")
        result = {}
        for role, frozen in p["services"].items():
            matches = [s for s in response["services"] if s["serviceName"] == frozen["service_name"]]
            require(len(matches) == 1, "service_missing")
            service = matches[0]
            task = self.ecs.describe_task_definition(taskDefinition=service["taskDefinition"])["taskDefinition"]
            ids = self.ecs.list_tasks(cluster=p["cluster"], serviceName=frozen["service_name"], desiredStatus="RUNNING")["taskArns"]
            running = self.ecs.describe_tasks(cluster=p["cluster"], tasks=ids)["tasks"] if ids else []
            result[role] = {"service": service, "task": task, "running": running}
        return result

    def check(self, state: dict, revisions: dict | None = None, image: str | dict | None = None) -> dict:
        p = self.profile
        for role, current in state.items():
            service, task, running = current["service"], current["task"], current["running"]
            frozen = p["services"][role]
            expected = revisions[role] if revisions else frozen["task_definition"]
            require(service["taskDefinition"] == expected, "serving_revision_drift")
            require(service["status"] == "ACTIVE" and service["desiredCount"] == service["runningCount"] == 1
                    and service["pendingCount"] == 0, "service_counts_unhealthy")
            require(len(service["deployments"]) == 1 and service["deployments"][0].get("rolloutState") == "COMPLETED", "deployment_not_complete")
            require(digest(topology(service)) == frozen["service_topology_sha256"], "service_topology_drift")
            validate_task(task, role, p)
            expected_image = image[role] if isinstance(image, dict) else (image or p["image_uri"])
            require(task["containerDefinitions"][0]["image"] == expected_image, "task_image_drift")
            require(len(running) == 1 and running[0]["taskDefinitionArn"] == expected
                    and running[0]["lastStatus"] == "RUNNING"
                    and {c.get("imageDigest") for c in running[0]["containers"]} == {expected_image.split("@", 1)[1]}, "running_image_or_revision_drift")
        for endpoint in ("health", "ready"):
            body = subprocess.check_output(["curl", "--fail", "--silent", "--show-error", "--max-time", "10",
                                            p["api_url"] + "/api/" + endpoint])
            validate_health_response(body, endpoint)
        rds = self.session.client("rds").describe_db_instances(DBInstanceIdentifier=p["rds_instance"])["DBInstances"][0]
        require(rds["DBInstanceStatus"] == "available", "rds_unavailable")
        auth = mappings(state["api"]["task"]["containerDefinitions"][0]["environment"], "value")
        require(rds["MasterUserSecret"]["SecretArn"] == auth["NERAIUM_AUTH_DATABASE_SECRET_ARN"]
                and rds["Endpoint"]["Address"] == auth["NERAIUM_AUTH_DATABASE_HOST"], "rotating_auth_database_binding_drift")
        host = self.session.client("ec2").describe_instance_status(InstanceIds=[p["executor"]["instance_id"]], IncludeAllInstances=True)["InstanceStatuses"]
        require(len(host) == 1 and host[0]["SystemStatus"]["Status"] == host[0]["InstanceStatus"]["Status"] == "ok", "executor_host_unhealthy")
        firewall = self.session.client("network-firewall").describe_firewall(FirewallName=p["firewall_name"])["FirewallStatus"]
        require(firewall["Status"] == "READY" and firewall["ConfigurationSyncStateSummary"] == "IN_SYNC", "controlled_egress_unhealthy")
        subscriptions = self.session.client("sns").list_subscriptions_by_topic(TopicArn=p["sns_topic_arn"])["Subscriptions"]
        require(any(s["SubscriptionArn"] == p["sns_subscription_arn"] and s["Endpoint"] == p["operator_email"] for s in subscriptions), "operator_subscription_missing")
        alarms = self.session.client("cloudwatch").describe_alarms(AlarmNamePrefix="neraium-prod-")["MetricAlarms"]
        filters = {role: self.session.client("logs").describe_metric_filters(logGroupName=frozen["log_group"])["metricFilters"] for role, frozen in p["services"].items()}
        require(monitoring_fingerprint(alarms, filters) == p["monitoring_configuration_sha256"], "monitoring_configuration_drift")
        require(all(a["ActionsEnabled"] and p["sns_topic_arn"] in a["AlarmActions"] and p["sns_topic_arn"] in a["OKActions"]
                    and a["StateValue"] == "OK" for a in alarms), "production_alarm_gate_failed")
        return {"health": "PASS", "ready": "PASS", "rds": "available", "alarms_ok": len(alarms), "v2_configuration": "PASS"}

    def probe(self, state: dict) -> dict:
        p = self.profile
        api = state["api"]["service"]
        code = (ROOT / "scripts/production_release_probe.py").read_text()
        response = self.ecs.run_task(cluster=p["cluster"], taskDefinition=api["taskDefinition"], launchType="FARGATE",
                                    networkConfiguration=api["networkConfiguration"], count=1,
                                    overrides={"containerOverrides": [{"name": "api", "command": ["python", "-c", code]}]})
        require(not response.get("failures") and len(response.get("tasks", [])) == 1, "verification_task_launch_failed")
        arn = response["tasks"][0]["taskArn"]
        self.ecs.get_waiter("tasks_stopped").wait(cluster=p["cluster"], tasks=[arn], WaiterConfig={"Delay": 6, "MaxAttempts": 40})
        task = self.ecs.describe_tasks(cluster=p["cluster"], tasks=[arn])["tasks"][0]
        require(task["containers"][0].get("exitCode") == 0, "tls_synthetic_persistence_scope_probe_failed")
        return {"task_arn": arn, "exit_code": 0, "tls_and_synthetic_v2_scope": "PASS"}

    def wait(self) -> None:
        self.ecs.get_waiter("services_stable").wait(cluster=self.profile["cluster"],
            services=[s["service_name"] for s in self.profile["services"].values()], WaiterConfig={"Delay": 15, "MaxAttempts": 40})

    def post_events(self, state: dict) -> None:
        logs = self.session.client("logs")
        for role, event in (("api", "production_health_evaluated"), ("worker", "worker_loop_started")):
            stream = "ecs/" + role + "/" + state[role]["running"][0]["taskArn"].rsplit("/", 1)[1]
            observed = False
            for _ in range(12):
                arguments = {"startTime": int((time.time() - 300) * 1000)} if role == "api" else {}
                response = logs.filter_log_events(logGroupName=self.profile["services"][role]["log_group"],
                                                 logStreamNames=[stream], filterPattern='"' + event + '"', **arguments)
                if response["events"]:
                    observed = True
                    break
                time.sleep(5)
            require(observed, "new_task_monitoring_event_missing:" + role)


def deploy(production, image: str, revision: str, profile: dict, apply: bool = False) -> dict:
    before = production.snapshot()
    checks = production.check(before)
    candidates = {role: candidate_task(item["task"], image, revision, role, profile) for role, item in before.items()}
    result = {"source_sha": revision, "image_uri": image, "preflight": checks, "apply": apply,
              "rollback_revisions": {role: item["service"]["taskDefinition"] for role, item in before.items()}}
    if not apply:
        result["plan"] = "PASS: image and build marker only; no AWS writes"
        return result
    result["preflight_probe"] = production.probe(before)
    # Re-read immediately before registration to detect an intervening rollout.
    production.check(production.snapshot())
    changed = False
    revisions = {}
    try:
        for role in ("worker", "api"):
            registered = production.ecs.register_task_definition(**candidates[role])["taskDefinition"]
            validate_task(registered, role, profile)
            revisions[role] = registered["taskDefinitionArn"]
        for role in ("worker", "api"):
            changed = True
            production.ecs.update_service(cluster=profile["cluster"], service=profile["services"][role]["service_name"], taskDefinition=revisions[role])
            production.wait()
            if role == "worker":
                intermediate = production.snapshot()
                production.check(intermediate, {"worker": revisions["worker"], "api": result["rollback_revisions"]["api"]},
                                 {"worker": image, "api": profile["image_uri"]})
                production.post_events(intermediate)
        after = production.snapshot()
        result["postflight"] = production.check(after, revisions, image)
        result["postflight_probe"] = production.probe(after)
        production.post_events(after)
        result["task_definitions"] = revisions
        result["deployment"] = "PASS"
        return result
    except Exception as error:
        result["status"] = "FAIL"
        result["reason"] = str(error) if isinstance(error, GateError) else type(error).__name__
        if changed:
            try:
                for role in ("api", "worker"):
                    production.ecs.update_service(cluster=profile["cluster"], service=profile["services"][role]["service_name"], taskDefinition=result["rollback_revisions"][role])
                production.wait()
                restored = production.snapshot()
                result["rollback_checks"] = production.check(restored)
                result["rollback_probe"] = production.probe(restored)
                result["rollback"] = "PASS"
            except Exception as rollback_error:
                result["rollback"] = "FAIL"
                result["rollback_reason"] = str(rollback_error) if isinstance(rollback_error, GateError) else type(rollback_error).__name__
        else:
            result["rollback"] = "not_required_no_service_change"
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "certify-image", "verify", "deploy"))
    parser.add_argument("--source-sha")
    parser.add_argument("--image-uri")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    profile = json.loads(BASELINE.read_text())
    result = {"observed_at": datetime.now(timezone.utc).isoformat(), "command": args.command}
    try:
        if args.command == "build":
            result.update(build_image(args.source_sha or "", profile, args.push))
        elif args.command == "certify-image":
            certify_image(args.image_uri or "", args.source_sha or "", profile)
            result["image_certification"] = "PASS"
        elif args.command == "verify":
            production = Production(profile)
            state = production.snapshot()
            result["checks"] = production.check(state)
            production.post_events(state)
            if args.probe:
                result["probe"] = production.probe(state)
        else:
            revision, image = args.source_sha or "", args.image_uri or ""
            require(re.fullmatch(re.escape(profile["ecr_repository_uri"]) + r"@sha256:[0-9a-f]{64}", image) is not None,
                    "image_must_be_approved_repository_digest")
            source_manifest(revision, profile)
            ecr = boto3.client("ecr", region_name=profile["region"])
            known = ecr.describe_images(repositoryName="neraium-prod-api", imageIds=[{"imageTag": "release-" + revision}])["imageDetails"][0]
            require(image.endswith("@" + known["imageDigest"]), "release_tag_digest_mismatch")
            registry_command(profile, ["pull", profile["image_uri"]])
            registry_command(profile, ["pull", image])
            certify_image(image, revision, profile)
            result.update(deploy(Production(profile), image, revision, profile, args.apply))
        result["status"] = result.get("status", "PASS")
    except Exception as error:
        result["status"] = "FAIL"
        result["reason"] = str(error) if isinstance(error, GateError) else type(error).__name__
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
