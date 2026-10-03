#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-2}"
ECS_CLUSTER="${ECS_CLUSTER:-neraium-prod-cluster}"
ECS_API_SERVICE="${ECS_API_SERVICE:-neraium-prod-api-service}"
ECS_WORKER_SERVICE="${ECS_WORKER_SERVICE:-neraium-prod-worker-service}"
API_LOG_GROUP="${API_LOG_GROUP:-/ecs/neraium-prod-api}"
WORKER_LOG_GROUP="${WORKER_LOG_GROUP:-/ecs/neraium-prod-worker}"
CONNECTOR_EXECUTOR_INSTANCE_ID="${CONNECTOR_EXECUTOR_INSTANCE_ID:-i-081d0aba82dba64e7}"
INFRA_ALERT_TOPIC_NAME="${INFRA_ALERT_TOPIC_NAME:-neraium-prod-infrastructure-alerts}"
INFRA_ALERT_EMAILS="${NERAIUM_INFRA_ALERT_EMAILS:-}"

INFRA_ALERT_TOPIC_ARN="${NERAIUM_INFRA_ALERT_SNS_TOPIC_ARN:-$(aws sns create-topic \
  --name "$INFRA_ALERT_TOPIC_NAME" \
  --region "$AWS_REGION" \
  --query TopicArn \
  --output text)}"

aws sns tag-resource \
  --resource-arn "$INFRA_ALERT_TOPIC_ARN" \
  --tags Key=Application,Value=Neraium Key=Environment,Value=production Key=Purpose,Value=self-monitoring \
  --region "$AWS_REGION" >/dev/null

if [[ -n "$INFRA_ALERT_EMAILS" ]]; then
  IFS=',' read -r -a alert_emails <<< "$INFRA_ALERT_EMAILS"
  subscriptions="$(aws sns list-subscriptions-by-topic \
    --topic-arn "$INFRA_ALERT_TOPIC_ARN" \
    --region "$AWS_REGION" \
    --query 'Subscriptions[?Protocol==`email`].Endpoint' \
    --output text)"
  for raw_email in "${alert_emails[@]}"; do
    email="$(echo "$raw_email" | xargs)"
    [[ -n "$email" ]] || continue
    if ! grep -Fqx "$email" <<< "$(tr '\t' '\n' <<< "$subscriptions")"; then
      aws sns subscribe \
        --topic-arn "$INFRA_ALERT_TOPIC_ARN" \
        --protocol email \
        --notification-endpoint "$email" \
        --region "$AWS_REGION" >/dev/null
    fi
  done
fi

aws ecs update-cluster-settings \
  --cluster "$ECS_CLUSTER" \
  --settings name=containerInsights,value=enabled \
  --region "$AWS_REGION" >/dev/null

services_json="$(aws ecs describe-services \
  --cluster "$ECS_CLUSTER" \
  --services "$ECS_API_SERVICE" "$ECS_WORKER_SERVICE" \
  --region "$AWS_REGION")"

if [[ "$(jq '.failures | length' <<< "$services_json")" != "0" ]]; then
  echo "Cannot configure monitoring because required ECS services are missing." >&2
  exit 1
fi

API_TARGET_GROUP_ARN="${API_TARGET_GROUP_ARN:-$(jq -r --arg api "$ECS_API_SERVICE" '.services[] | select(.serviceName == $api) | .loadBalancers[0].targetGroupArn' <<< "$services_json")}"
if [[ -z "$API_TARGET_GROUP_ARN" || "$API_TARGET_GROUP_ARN" == "null" ]]; then
  echo "API target group ARN could not be resolved." >&2
  exit 1
fi

load_balancer_arn="$(aws elbv2 describe-target-groups \
  --target-group-arns "$API_TARGET_GROUP_ARN" \
  --region "$AWS_REGION" \
  --query 'TargetGroups[0].LoadBalancerArns[0]' \
  --output text)"
if [[ -z "$load_balancer_arn" || "$load_balancer_arn" == "None" ]]; then
  echo "API load balancer ARN could not be resolved." >&2
  exit 1
fi

target_group_dimension="targetgroup/${API_TARGET_GROUP_ARN#*:targetgroup/}"
load_balancer_dimension="${load_balancer_arn#*:loadbalancer/}"

put_alarm() {
  aws cloudwatch put-metric-alarm "$@" \
    --alarm-actions "$INFRA_ALERT_TOPIC_ARN" \
    --ok-actions "$INFRA_ALERT_TOPIC_ARN" \
    --region "$AWS_REGION"
}

for service in "$ECS_API_SERVICE" "$ECS_WORKER_SERVICE"; do
  label="api"
  [[ "$service" == "$ECS_WORKER_SERVICE" ]] && label="worker"
  put_alarm \
    --alarm-name "neraium-prod-${label}-tasks-unavailable" \
    --alarm-description "Neraium production ${label} service has no running task for three consecutive minutes." \
    --namespace ECS/ContainerInsights \
    --metric-name RunningTaskCount \
    --dimensions Name=ClusterName,Value="$ECS_CLUSTER" Name=ServiceName,Value="$service" \
    --statistic Minimum \
    --period 60 \
    --evaluation-periods 3 \
    --datapoints-to-alarm 3 \
    --threshold 1 \
    --comparison-operator LessThanThreshold \
    --treat-missing-data breaching
done

put_alarm \
  --alarm-name neraium-prod-connector-executor-status-failed \
  --alarm-description "SEV2: connector executor EC2 status check failed for two of three minutes; scheduled telemetry may stop. Inspect EC2 instance status and /var/log/neraium-connector-executor.log. Runbook: docs/operations/sre-hardening.md#connector-executor-unavailable." \
  --namespace AWS/EC2 \
  --metric-name StatusCheckFailed \
  --dimensions Name=InstanceId,Value="$CONNECTOR_EXECUTOR_INSTANCE_ID" \
  --statistic Maximum \
  --period 60 \
  --evaluation-periods 3 \
  --datapoints-to-alarm 2 \
  --threshold 1 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data breaching

put_alarm \
  --alarm-name neraium-prod-api-no-healthy-alb-targets \
  --alarm-description "Neraium production ALB has no healthy API target for five consecutive minutes." \
  --namespace AWS/ApplicationELB \
  --metric-name HealthyHostCount \
  --dimensions Name=LoadBalancer,Value="$load_balancer_dimension" Name=TargetGroup,Value="$target_group_dimension" \
  --statistic Minimum \
  --period 60 \
  --evaluation-periods 5 \
  --datapoints-to-alarm 5 \
  --threshold 1 \
  --comparison-operator LessThanThreshold \
  --treat-missing-data breaching

put_alarm \
  --alarm-name neraium-prod-api-slow \
  --alarm-description "Neraium production API target p95 latency exceeds two seconds for five consecutive minutes." \
  --namespace AWS/ApplicationELB \
  --metric-name TargetResponseTime \
  --dimensions Name=LoadBalancer,Value="$load_balancer_dimension" Name=TargetGroup,Value="$target_group_dimension" \
  --extended-statistic p95 \
  --period 60 \
  --evaluation-periods 5 \
  --datapoints-to-alarm 5 \
  --threshold 2 \
  --comparison-operator GreaterThanThreshold \
  --treat-missing-data notBreaching

put_alarm \
  --alarm-name neraium-prod-api-target-5xx \
  --alarm-description "Neraium production API returned five or more target 5xx responses in three of five minutes." \
  --namespace AWS/ApplicationELB \
  --metric-name HTTPCode_Target_5XX_Count \
  --dimensions Name=LoadBalancer,Value="$load_balancer_dimension" Name=TargetGroup,Value="$target_group_dimension" \
  --statistic Sum \
  --period 60 \
  --evaluation-periods 5 \
  --datapoints-to-alarm 3 \
  --threshold 5 \
  --comparison-operator GreaterThanOrEqualToThreshold \
  --treat-missing-data notBreaching

put_log_alarm() {
  local log_group="$1"
  local filter_name="$2"
  local filter_pattern="$3"
  local metric_name="$4"
  local alarm_name="$5"
  local description="$6"
  aws logs put-metric-filter \
    --log-group-name "$log_group" \
    --filter-name "$filter_name" \
    --filter-pattern "$filter_pattern" \
    --metric-transformations metricName="$metric_name",metricNamespace=Neraium/Production,metricValue=1,defaultValue=0 \
    --region "$AWS_REGION"
  put_alarm \
    --alarm-name "$alarm_name" \
    --alarm-description "$description" \
    --namespace Neraium/Production \
    --metric-name "$metric_name" \
    --statistic Sum \
    --period 60 \
    --evaluation-periods 5 \
    --datapoints-to-alarm 3 \
    --threshold 1 \
    --comparison-operator GreaterThanOrEqualToThreshold \
    --treat-missing-data notBreaching
}

put_log_alarm "$API_LOG_GROUP" \
  neraium-auth-database-failure \
  '"readiness_dependency_failed" "auth_store"' \
  AuthenticationDatabaseFailures \
  neraium-prod-auth-database-failures \
  "Authentication database readiness failed in three of five minutes."

put_log_alarm "$API_LOG_GROUP" \
  neraium-credential-refresh-failure \
  '"auth_database_credentials_refresh_failed"' \
  CredentialRefreshFailures \
  neraium-prod-credential-refresh-failures \
  "Managed database credential refresh failed in three of five minutes."

put_log_alarm "$API_LOG_GROUP" \
  neraium-secrets-access-failure \
  '"auth_database_secret_probe_failed"' \
  SecretsManagerAccessFailures \
  neraium-prod-secrets-access-failures \
  "Secrets Manager access failed in three of five minutes."

put_log_alarm "$WORKER_LOG_GROUP" \
  neraium-worker-iteration-failure \
  '"upload_worker_iteration_failed"' \
  WorkerIterationFailures \
  neraium-prod-worker-iteration-failures \
  "Upload worker iteration failed in three of five minutes."

put_log_alarm "$WORKER_LOG_GROUP" \
  neraium-telemetry-scheduler-failure \
  '"telemetry_scheduler_iteration_failed"' \
  TelemetrySchedulerFailures \
  neraium-prod-telemetry-scheduler-failures \
  "SEV2: telemetry scheduler iteration failed in three of five minutes; ingestion may stall. Inspect worker log and DB connectivity. Runbook: docs/operations/sre-hardening.md#worker-unavailable."

put_log_alarm "$WORKER_LOG_GROUP" \
  neraium-telemetry-scheduler-lag \
  '"telemetry_scheduler_lag_high"' \
  TelemetrySchedulerLagHigh \
  neraium-prod-telemetry-scheduler-lag-high \
  "SEV2: claimed telemetry work was over ten minutes overdue in three of five minutes; ingestion delayed. Inspect worker task count and due-work backlog. Runbook: docs/operations/sre-hardening.md#telemetry-ingestion-failing."

put_log_alarm "$WORKER_LOG_GROUP" \
  neraium-telemetry-ingestion-failure \
  '"telemetry_ingestion_page_failed"' \
  TelemetryIngestionFailures \
  neraium-prod-telemetry-ingestion-failures \
  "SEV2: ingestion page failed in three of five minutes; new telemetry may be delayed. Inspect error_code in worker logs. Runbook: docs/operations/sre-hardening.md#telemetry-ingestion-failing."

put_log_alarm "$WORKER_LOG_GROUP" \
  neraium-connector-repeated-failure \
  '"telemetry_ingestion_page_failed" "connector_executor_"' \
  ConnectorExecutorFailures \
  neraium-prod-connector-executor-repeated-failures \
  "SEV2: repeated connector executor fetch failures in three of five minutes; telemetry may be delayed. Check EC2 executor status and worker error_code. Runbook: docs/operations/sre-hardening.md#connector-executor-unavailable."

put_log_alarm "$WORKER_LOG_GROUP" \
  neraium-telemetry-analysis-failure \
  '"telemetry_analysis_failed"' \
  TelemetryAnalysisFailures \
  neraium-prod-v2-analysis-failures \
  "SEV2: analysis failed in three of five minutes; V2 results may be unavailable. Inspect worker analysis failure logs. Runbook: docs/operations/sre-hardening.md#v2-execution-failing."

put_log_alarm "$WORKER_LOG_GROUP" \
  neraium-v2-persistence-failure \
  '"telemetry_v2_persistence_failed"' \
  TelemetryV2PersistenceFailures \
  neraium-prod-v2-persistence-failures \
  "SEV2: V2 persistence failed in three of five minutes; completed results may not be durable. Inspect DB and worker logs. Runbook: docs/operations/sre-hardening.md#result-persistence-or-retrieval-failing."

put_log_alarm "$API_LOG_GROUP" \
  neraium-v2-retrieval-failure \
  '"telemetry_v2_retrieval_failed"' \
  TelemetryV2RetrievalFailures \
  neraium-prod-v2-retrieval-failures \
  "SEV2: V2 result retrieval failed in three of five minutes; customers may not see saved results. Inspect API logs and DB. Runbook: docs/operations/sre-hardening.md#result-persistence-or-retrieval-failing."

put_success_metric() {
  aws logs put-metric-filter \
    --log-group-name "$1" \
    --filter-name "$2" \
    --filter-pattern "$3" \
    --metric-transformations metricName="$4",metricNamespace=Neraium/Production,metricValue=1 \
    --region "$AWS_REGION"
}

put_success_metric "$WORKER_LOG_GROUP" neraium-connector-fetch-completed \
  '"telemetry_connector_fetch_completed"' ConnectorFetchCompleted
put_success_metric "$WORKER_LOG_GROUP" neraium-ingestion-run-completed \
  '"telemetry_ingestion_run_completed"' TelemetryIngestionCompleted
put_success_metric "$WORKER_LOG_GROUP" neraium-analysis-completed \
  '"telemetry_analysis_completed"' TelemetryAnalysisCompleted
put_success_metric "$WORKER_LOG_GROUP" neraium-v2-persistence-completed \
  '"telemetry_v2_persistence_completed"' TelemetryV2PersistenceCompleted
put_success_metric "$API_LOG_GROUP" neraium-v2-retrieval-completed \
  '"telemetry_v2_retrieval_completed"' TelemetryV2RetrievalCompleted

printf 'INFRA_ALERT_TOPIC_ARN=%s\n' "$INFRA_ALERT_TOPIC_ARN"
printf 'API_TARGET_GROUP_ARN=%s\n' "$API_TARGET_GROUP_ARN"
printf 'Configured production alarms for ALB, ECS, EC2 connector executor, database dependencies, ingestion, analysis, persistence, and retrieval.\n'
