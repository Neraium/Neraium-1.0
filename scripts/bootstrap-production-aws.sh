#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-2}"
UPLOAD_STATE_BUCKET="${UPLOAD_STATE_BUCKET:?UPLOAD_STATE_BUCKET is required}"
APP_TASK_ROLE_NAME="${APP_TASK_ROLE_NAME:-neraium-prod-task-app-role}"
TASK_EXECUTION_ROLE_NAME="${TASK_EXECUTION_ROLE_NAME:-neraium-prod-ecs-task-execution-role}"
API_TOKEN_SECRET_ARN="${API_TOKEN_SECRET_ARN:?API_TOKEN_SECRET_ARN is required}"
AUTH_DATABASE_URL_SECRET_ARN="${AUTH_DATABASE_URL_SECRET_ARN:?AUTH_DATABASE_URL_SECRET_ARN is required}"
NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN="${NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN:?NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN is required}"
API_LOG_GROUP="${API_LOG_GROUP:-/ecs/neraium-prod-api}"
WORKER_LOG_GROUP="${WORKER_LOG_GROUP:-/ecs/neraium-prod-worker}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
APP_TASK_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${APP_TASK_ROLE_NAME}"
TASK_EXECUTION_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${TASK_EXECUTION_ROLE_NAME}"
TRUST_POLICY_FILE="$(mktemp)"
INLINE_POLICY_FILE="$(mktemp)"
EXECUTION_INLINE_POLICY_FILE="$(mktemp)"
EXECUTION_SECRETS_POLICY_FILE="$(mktemp)"
cleanup() {
  rm -f "$TRUST_POLICY_FILE" "$INLINE_POLICY_FILE" "$EXECUTION_INLINE_POLICY_FILE" "$EXECUTION_SECRETS_POLICY_FILE"
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
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::${UPLOAD_STATE_BUCKET}/*"]
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
echo "NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN=${NERAIUM_BOOTSTRAP_ADMIN_PASSWORD_SECRET_ARN}"
echo "API_LOG_GROUP=${API_LOG_GROUP}"
echo "WORKER_LOG_GROUP=${WORKER_LOG_GROUP}"
