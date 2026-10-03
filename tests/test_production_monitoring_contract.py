from __future__ import annotations

import subprocess
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_monitoring_scripts_are_syntactically_valid():
    for script in ("scripts/bootstrap-production-aws.sh", "scripts/configure-production-monitoring.sh"):
        subprocess.run(["bash", "-n", str(ROOT / script)], check=True)


def test_aws_monitoring_has_persistent_external_failure_detection():
    script = read("scripts/configure-production-monitoring.sh")

    assert "containerInsights,value=enabled" in script
    assert "RunningTaskCount" in script
    assert "HealthyHostCount" in script
    assert "TargetResponseTime" in script
    assert "HTTPCode_Target_5XX_Count" in script
    assert "evaluation-periods 5" in script
    assert "datapoints-to-alarm 5" in script
    assert "auth_database_credentials_refresh_failed" in script
    assert "auth_database_secret_probe_failed" in script
    assert "upload_worker_iteration_failed" in script
    assert "--alarm-actions \"$INFRA_ALERT_TOPIC_ARN\"" in script
    assert "--ok-actions \"$INFRA_ALERT_TOPIC_ARN\"" in script
    for signal in (
        "StatusCheckFailed",
        "telemetry_scheduler_iteration_failed",
        "telemetry_scheduler_lag_high",
        "telemetry_ingestion_page_failed",
        "connector_executor_",
        "telemetry_analysis_failed",
        "telemetry_v2_persistence_failed",
        "telemetry_v2_retrieval_failed",
        "telemetry_v2_retrieval_completed",
    ):
        assert signal in script


def test_task_role_and_deployment_enable_in_application_monitoring():
    bootstrap = read("scripts/bootstrap-production-aws.sh")
    baseline = json.loads(read("docs/operations/first-customer-production-baseline-2026-10-03.json"))

    assert '"Action": ["sns:Publish"]' in bootstrap
    assert '"Action": ["secretsmanager:DescribeSecret"]' in bootstrap
    assert '"ecs:DescribeServices", "elasticloadbalancing:DescribeTargetHealth"' in bootstrap
    assert "./scripts/configure-production-monitoring.sh" in bootstrap
    env = baseline["services"]["api"]["configuration"]
    assert env["NERAIUM_INFRA_MONITOR_ENABLED"] == "true"
    assert env["NERAIUM_INFRA_ALERT_SNS_TOPIC_ARN"] == baseline["sns_topic_arn"]
    assert env["NERAIUM_ALB_TARGET_GROUP_ARN"] == baseline["services"]["api"]["topology"]["loadBalancers"][0]["targetGroupArn"]
    assert baseline["monitoring"]["all_actions_enabled"] is True


def test_notification_adapters_and_deduplication_contract_are_present():
    notifications = read("backend/app/services/infrastructure_notifications.py")
    health = read("backend/app/services/production_health.py")

    for adapter in ("ConsoleNotificationAdapter", "SnsNotificationAdapter", "EmailNotificationAdapter"):
        assert f"class {adapter}" in notifications
    assert 'JsonWebhookNotificationAdapter("slack"' in notifications
    assert 'JsonWebhookNotificationAdapter("teams"' in notifications
    assert 'JsonWebhookNotificationAdapter("webhook"' in notifications
    assert 'active_incident_id' in health
    assert 'event_type": "recovery"' in health
    assert 'notification_sent_at' in health
