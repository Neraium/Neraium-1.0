#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-2}"
UPLOAD_STATE_BUCKET="${UPLOAD_STATE_BUCKET:?UPLOAD_STATE_BUCKET is required}"
APP_TASK_ROLE_NAME="${APP_TASK_ROLE_NAME:-neraium-prod-task-app-role}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
APP_TASK_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${APP_TASK_ROLE_NAME}"
TRUST_POLICY_FILE="$(mktemp)"
INLINE_POLICY_FILE="$(mktemp)"
cleanup() {
  rm -f "$TRUST_POLICY_FILE" "$INLINE_POLICY_FILE"
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

echo "Ensuring S3 bucket ${UPLOAD_STATE_BUCKET} in ${AWS_REGION}"
if ! aws s3api head-bucket --bucket "$UPLOAD_STATE_BUCKET" 2>/dev/null; then
  if [ "$AWS_REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$UPLOAD_STATE_BUCKET"
  else
    aws s3api create-bucket       --bucket "$UPLOAD_STATE_BUCKET"       --region "$AWS_REGION"       --create-bucket-configuration "LocationConstraint=${AWS_REGION}"
  fi
fi

aws s3api put-bucket-versioning   --bucket "$UPLOAD_STATE_BUCKET"   --versioning-configuration Status=Enabled >/dev/null

echo "Ensuring IAM role ${APP_TASK_ROLE_NAME}"
if ! aws iam get-role --role-name "$APP_TASK_ROLE_NAME" >/dev/null 2>&1; then
  aws iam create-role     --role-name "$APP_TASK_ROLE_NAME"     --assume-role-policy-document "file://${TRUST_POLICY_FILE}" >/dev/null
fi

aws iam update-assume-role-policy   --role-name "$APP_TASK_ROLE_NAME"   --policy-document "file://${TRUST_POLICY_FILE}"

aws iam put-role-policy   --role-name "$APP_TASK_ROLE_NAME"   --policy-name neraium-upload-state-access   --policy-document "file://${INLINE_POLICY_FILE}"

echo "UPLOAD_STATE_BUCKET=${UPLOAD_STATE_BUCKET}"
echo "APP_TASK_ROLE_NAME=${APP_TASK_ROLE_NAME}"
echo "APP_TASK_ROLE_ARN=${APP_TASK_ROLE_ARN}"
