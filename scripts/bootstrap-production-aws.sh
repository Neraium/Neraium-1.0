#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-2}"
UPLOAD_STATE_BUCKET="${UPLOAD_STATE_BUCKET:?UPLOAD_STATE_BUCKET is required}"
APP_TASK_ROLE_NAME="${APP_TASK_ROLE_NAME:-neraium-prod-task-app-role}"
TASK_EXECUTION_ROLE_NAME="${TASK_EXECUTION_ROLE_NAME:-neraium-prod-ecs-task-execution-role}"
API_TOKEN_SECRET_ARN="${API_TOKEN_SECRET_ARN:?API_TOKEN_SECRET_ARN is required}"
AUTH_DATABASE_URL_SECRET_ARN="${AUTH_DATABASE_URL_SECRET_ARN:?AUTH_DATABASE_URL_SECRET_ARN is required}"
AUTH_DATABASE_SECRET_ARN="${AUTH_DATABASE_SECRET_ARN:?AUTH_DATABASE_SECRET_ARN is required}"
AUTH_DATABASE_KMS_KEY_ARN="${AUTH_DATABASE_KMS_KEY_ARN:?AUTH_DATABASE_KMS_KEY_ARN is required}"
TELEMETRY_DATABASE_URL_SECRET_ARN="${TELEMETRY_DATABASE_URL_SECRET_ARN:?TELEMETRY_DATABASE_URL_SECRET_ARN is required}"
TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN="${TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN:?TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN is required}"
NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN="${NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN:?NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN is required}"
API_LOG_GROUP="${API_LOG_GROUP:-/ecs/neraium-prod-api}"
WORKER_LOG_GROUP="${WORKER_LOG_GROUP:-/ecs/neraium-prod-worker}"
ECS_CLUSTER="${ECS_CLUSTER:-neraium-prod-cluster}"
ECS_API_SERVICE="${ECS_API_SERVICE:-neraium-prod-api-service}"
ECS_WORKER_SERVICE="${ECS_WORKER_SERVICE:-neraium-prod-worker-service}"
INFRA_ALERT_TOPIC_NAME="${INFRA_ALERT_TOPIC_NAME:-neraium-prod-infrastructure-alerts}"
NERAIUM_INFRA_ALERT_EMAILS="${NERAIUM_INFRA_ALERT_EMAILS:-}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
INFRA_ALERT_TOPIC_ARN="$(aws sns create-topic --name "$INFRA_ALERT_TOPIC_NAME" --region "$AWS_REGION" --query TopicArn --output text)"
APP_TASK_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${APP_TASK_ROLE_NAME}"
TASK_EXECUTION_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${TASK_EXECUTION_ROLE_NAME}"
TRUST_POLICY_FILE="$(mktemp)"
INLINE_POLICY_FILE="$(mktemp)"
EXECUTION_INLINE_POLICY_FILE="$(mktemp)"
EXECUTION_SECRETS_POLICY_FILE="$(mktemp)"
UPLOAD_CORS_FILE="$(mktemp)"
CURRENT_CORS_FILE="$(mktemp)"
UPLOAD_LIFECYCLE_FILE="$(mktemp)"
CURRENT_LIFECYCLE_FILE="$(mktemp)"
cleanup() {
  rm -f "$TRUST_POLICY_FILE" "$INLINE_POLICY_FILE" "$EXECUTION_INLINE_POLICY_FILE" "$EXECUTION_SECRETS_POLICY_FILE" "$UPLOAD_CORS_FILE" "$CURRENT_CORS_FILE" "$UPLOAD_LIFECYCLE_FILE" "$CURRENT_LIFECYCLE_FILE"
}
trap cleanup EXIT

cat > "$TRUST_POLICY_FILE" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": "ecs-tasks.amazonaws.com"},
      "Action": "sts:AssumeRole"
    }
  ]
}
JSON

cat > "$INLINE_POLICY_FILE" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": ["arn:aws:s3:::${UPLOAD_STATE_BUCKET}"]
    },
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:PutObjectTagging", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::${UPLOAD_STATE_BUCKET}/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:GetSecretValue"],
      "Resource": ["${AUTH_DATABASE_SECRET_ARN}"]
    },
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:DescribeSecret"],
      "Resource": ["${AUTH_DATABASE_SECRET_ARN}"]
    },
    {
      "Effect": "Allow",
      "Action": ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue"],
      "Resource": ["arn:aws:secretsmanager:${AWS_REGION}:${ACCOUNT_ID}:secret:neraium/prod/telemetry-connections/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["kms:Decrypt"],
      "Resource": ["${AUTH_DATABASE_KMS_KEY_ARN}"]
    },
    {
      "Effect": "Allow",
      "Action": ["sns:Publish"],
      "Resource": ["${INFRA_ALERT_TOPIC_ARN}"]
    },
    {
      "Effect": "Allow",
      "Action": ["ecs:DescribeServices", "elasticloadbalancing:DescribeTargetHealth"],
      "Resource": "*"
    }
  ]
}
JSON

cat > "$EXECUTION_INLINE_POLICY_FILE" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": [
        "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:${API_LOG_GROUP}:*",
        "arn:aws:logs:${AWS_REGION}:${ACCOUNT_ID}:log-group:${WORKER_LOG_GROUP}:*"
      ]
    }
  ]
}
JSON

cat > "$EXECUTION_SECRETS_POLICY_FILE" <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": [
        "${API_TOKEN_SECRET_ARN}",
        "${AUTH_DATABASE_URL_SECRET_ARN}",
        "${TELEMETRY_DATABASE_URL_SECRET_ARN}",
        "${TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN}",
        "${NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN}"
      ]
    }
  ]
}
JSON

echo "Ensuring S3 bucket ${UPLOAD_STATE_BUCKET} in ${AWS_REGION}"
if ! aws s3api head-bucket --bucket "$UPLOAD_STATE_BUCKET" 2>/dev/null; then
  if [ "$AWS_REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$UPLOAD_STATE_BUCKET"
  else
    aws s3api create-bucket \
      --bucket "$UPLOAD_STATE_BUCKET" \
      --region "$AWS_REGION" \
      --create-bucket-configuration "LocationConstraint=${AWS_REGION}"
  fi
fi

aws s3api put-bucket-versioning \
  --bucket "$UPLOAD_STATE_BUCKET" \
  --versioning-configuration Status=Enabled >/dev/null

if ! aws s3api get-bucket-cors \
  --bucket "$UPLOAD_STATE_BUCKET" > "$CURRENT_CORS_FILE" 2>/dev/null; then
  printf '%s\n' '{"CORSRules":[]}' > "$CURRENT_CORS_FILE"
fi
jq '{
  CORSRules: ([.CORSRules[]? | select(.ID != "neraium-browser-large-upload")] + [{
    ID: "neraium-browser-large-upload",
    AllowedOrigins: ["https://app.neraium.com"],
    AllowedMethods: ["PUT"],
    AllowedHeaders: ["content-type", "if-none-match", "x-amz-tagging"],
    ExposeHeaders: ["ETag"],
    MaxAgeSeconds: 3600
  }])
}' "$CURRENT_CORS_FILE" > "$UPLOAD_CORS_FILE"
aws s3api put-bucket-cors \
  --bucket "$UPLOAD_STATE_BUCKET" \
  --cors-configuration "file://${UPLOAD_CORS_FILE}" >/dev/null

if ! aws s3api get-bucket-lifecycle-configuration \
  --bucket "$UPLOAD_STATE_BUCKET" > "$CURRENT_LIFECYCLE_FILE" 2>/dev/null; then
  printf '%s\n' '{"Rules":[]}' > "$CURRENT_LIFECYCLE_FILE"
fi
jq '{
  Rules: ([.Rules[]? | select(.ID != "neraium-orphaned-upload-source-expiry")] + [{
    ID: "neraium-orphaned-upload-source-expiry",
    Status: "Enabled",
    Filter: {Tag: {Key: "neraium-upload-source", Value: "true"}},
    Expiration: {Days: 7},
    NoncurrentVersionExpiration: {NoncurrentDays: 7}
  }])
}' "$CURRENT_LIFECYCLE_FILE" > "$UPLOAD_LIFECYCLE_FILE"
aws s3api put-bucket-lifecycle-configuration \
  --bucket "$UPLOAD_STATE_BUCKET" \
  --lifecycle-configuration "file://${UPLOAD_LIFECYCLE_FILE}" >/dev/null

echo "Ensuring CloudWatch log groups"
aws logs create-log-group --log-group-name "$API_LOG_GROUP" --region "$AWS_REGION" 2>/dev/null || true
aws logs create-log-group --log-group-name "$WORKER_LOG_GROUP" --region "$AWS_REGION" 2>/dev/null || true

echo "Ensuring IAM role ${APP_TASK_ROLE_NAME}"
if ! aws iam get-role --role-name "$APP_TASK_ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role \
    --role-name "$APP_TASK_ROLE_NAME" \
    --assume-role-policy-document "file://${TRUST_POLICY_FILE}" >/dev/null
fi

aws iam update-assume-role-policy \
  --role-name "$APP_TASK_ROLE_NAME" \
  --policy-document "file://${TRUST_POLICY_FILE}"

aws iam put-role-policy \
  --role-name "$APP_TASK_ROLE_NAME" \
  --policy-name neraium-upload-state-access \
  --policy-document "file://${INLINE_POLICY_FILE}"

echo "Ensuring ECS task execution role ${TASK_EXECUTION_ROLE_NAME}"
if ! aws iam get-role --role-name "$TASK_EXECUTION_ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role \
    --role-name "$TASK_EXECUTION_ROLE_NAME" \
    --assume-role-policy-document "file://${TRUST_POLICY_FILE}" >/dev/null
fi

aws iam update-assume-role-policy \
  --role-name "$TASK_EXECUTION_ROLE_NAME" \
  --policy-document "file://${TRUST_POLICY_FILE}"

aws iam attach-role-policy \
  --role-name "$TASK_EXECUTION_ROLE_NAME" \
  --policy-arn "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy" >/dev/null || true

aws iam put-role-policy \
  --role-name "$TASK_EXECUTION_ROLE_NAME" \
  --policy-name neraium-cloudwatch-logs-access \
  --policy-document "file://${EXECUTION_INLINE_POLICY_FILE}"

aws iam put-role-policy \
  --role-name "$TASK_EXECUTION_ROLE_NAME" \
  --policy-name neraium-secretsmanager-access \
  --policy-document "file://${EXECUTION_SECRETS_POLICY_FILE}"

echo "UPLOAD_STATE_BUCKET=${UPLOAD_STATE_BUCKET}"
echo "APP_TASK_ROLE_NAME=${APP_TASK_ROLE_NAME}"
echo "APP_TASK_ROLE_ARN=${APP_TASK_ROLE_ARN}"
echo "TASK_EXECUTION_ROLE_NAME=${TASK_EXECUTION_ROLE_NAME}"
echo "TASK_EXECUTION_ROLE_ARN=${TASK_EXECUTION_ROLE_ARN}"
echo "API_TOKEN_SECRET_ARN=${API_TOKEN_SECRET_ARN}"
echo "AUTH_DATABASE_URL_SECRET_ARN=${AUTH_DATABASE_URL_SECRET_ARN}"
echo "AUTH_DATABASE_SECRET_ARN=${AUTH_DATABASE_SECRET_ARN}"
echo "AUTH_DATABASE_KMS_KEY_ARN=${AUTH_DATABASE_KMS_KEY_ARN}"
echo "TELEMETRY_DATABASE_URL_SECRET_ARN is configured"
echo "TELEMETRY_MIGRATION_DATABASE_URL_SECRET_ARN is configured"
echo "NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN=${NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN}"
echo "API_LOG_GROUP=${API_LOG_GROUP}"
echo "WORKER_LOG_GROUP=${WORKER_LOG_GROUP}"
echo "INFRA_ALERT_TOPIC_ARN=${INFRA_ALERT_TOPIC_ARN}"

AWS_REGION="$AWS_REGION" \
ECS_CLUSTER="$ECS_CLUSTER" \
ECS_API_SERVICE="$ECS_API_SERVICE" \
ECS_WORKER_SERVICE="$ECS_WORKER_SERVICE" \
API_LOG_GROUP="$API_LOG_GROUP" \
WORKER_LOG_GROUP="$WORKER_LOG_GROUP" \
INFRA_ALERT_TOPIC_NAME="$INFRA_ALERT_TOPIC_NAME" \
NERAIUM_INFRA_ALERT_SNS_TOPIC_ARN="$INFRA_ALERT_TOPIC_ARN" \
NERAIUM_INFRA_ALERT_EMAILS="$NERAIUM_INFRA_ALERT_EMAILS" \
./scripts/configure-production-monitoring.sh
