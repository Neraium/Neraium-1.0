# Amazon Bedrock interpretation layer

Neraium may use Amazon Bedrock as an optional downstream interpretation layer for completed Evidence Packages.

## Architectural boundary

The Neraium analysis/evidence pipeline remains authoritative. Bedrock does not calculate structural change, confidence, persistence, severity, hypotheses, or root cause. It receives an already-built governed Evidence Package and produces operator/engineering language from that evidence.

The integration rejects packages whose governance metadata says raw telemetry is included. The model prompt also requires uncertainty, limitations, and hypotheses to remain explicitly qualified.

## Configuration

Bedrock remains disabled by default outside the isolated staging cluster. The staging API task already exposes `NERAIUM_ECS_CLUSTER=neraium-staging-cluster`, so staging enables Bedrock automatically once its dedicated IAM policy is applied. An explicit `NERAIUM_BEDROCK_ENABLED=false` always disables it, including in staging.

- `NERAIUM_BEDROCK_ENABLED=true|false` explicitly controls model invocation and overrides the staging default.
- `NERAIUM_BEDROCK_MODEL_ID` selects the Bedrock model. Default: `amazon.nova-micro-v1:0`.
- `NERAIUM_BEDROCK_REGION` selects the Bedrock runtime region. If omitted, `AWS_REGION` or `AWS_DEFAULT_REGION` is used.
- `NERAIUM_BEDROCK_MAX_TOKENS` defaults to `700`.
- `NERAIUM_BEDROCK_TEMPERATURE` defaults to `0.1`.

Use an IAM role attached to the runtime rather than long-lived AWS access keys. Staging uses `.planning/neraium-staging-bedrock-interpretation-policy.json`, which grants only `bedrock:InvokeModel` for `amazon.nova-micro-v1:0` in `us-east-2`. Apply it as a separate inline policy to `neraium-staging-task-app-role`; the existing pinned runtime supplemental policy remains unchanged.

## Intended flow

`telemetry -> Neraium analysis -> Evidence Package -> Bedrock interpretation -> operator/engineering presentation`

The returned object records `authoritative_source=neraium_evidence_package` and `model_role=interpretation_only` so downstream consumers can distinguish generated explanatory language from Neraium evidence.

## Cost and failure behavior

No Bedrock call occurs unless the interpretation endpoint is invoked and Bedrock is enabled for that runtime. Bedrock failures raise an interpretation-layer error; they do not modify or invalidate the underlying Evidence Package.
