# Certified Production V2 release procedure

The canonical backend release implementation is `scripts/production_release.py`.
The manual `deploy-backend.yml` workflow and the historical SRE command wrapper
both invoke it. Production releases must use this implementation.

## Authority and supported changes

The governed profile is
[`first-customer-production-baseline-2026-10-03.json`](first-customer-production-baseline-2026-10-03.json).
It freezes the actual first-customer-ready configuration, source hashes, image,
service topology, monitoring configuration and rollback pair. See
[`sre-closeout-2026-10-03.md`](sre-closeout-2026-10-03.md) for the original operational certification.

The release path overlays **committed backend source** onto the exact certified
runtime image. It preserves installed dependencies, user, environment, entrypoint
and command. Existing runtime Python is protected by the profile, except the
public application-info route. New committed source files and changes to that
route or non-runtime documentation are supported. Changes to protected runtime
code, dependencies, schema, task configuration or service topology require
separate review and recertification of the profile. There is no override flag.
This deliberately bounded release certification does not approve arbitrary
changes to analytical formulas, authorization, governance or monitoring.

## Pre-deployment checks

1. Fetch the approved branch; record local/remote HEAD and dirty inventory.
   Choose a full 40-character source SHA reachable from
   `origin/fix/deterministic-governed-output`. Review its exact diff. Never build
   from the dirty working directory. Leave unrelated work untouched.
2. Read the frozen profile and previous release evidence. Confirm the current
   task pair and immutable image digest still match. A previous successful
   release requires a reviewed profile refresh before another release.
3. Install verification dependencies from `backend/requirements-dev.txt` in an
   isolated environment. Run the release-tooling contracts listed in the workflow,
   plus the workflow's candidate product suites from a clean detached worktree
   at the requested source SHA. Investigate failures; never weaken tests.
4. Run `git diff --check`. Confirm the AWS identity is account `680779862188`,
   region `us-east-2`. Existing ECR/ECS/CloudWatch permissions and the current
   secret bindings are required. No credential values belong in evidence.
5. Verify live production, including the optional temporary read-only probe:

   ```bash
   python scripts/production_release.py verify --probe --evidence release-preflight.json
   ```

The verifier checks API/worker identity and separation, a single completed
deployment per service, desired/running/pending `1/1/0`, exact task configuration
and service topology, serving image digest, API JSON health/readiness, RDS
availability and rotating auth binding, executor host health, controlled-egress
firewall readiness, confirmed SNS subscription, exact metric-filter/alarm
configuration, enabled alarm/OK actions and all alarms `OK`.

It requires `physical-endpoint-keyed.v2`, controlled egress `true`, dynamic secret
writes `false`, both runtime/telemetry database secret bindings, the certified
HTTPS executor URL, authentication secret ARN and CA hash. Full task fingerprints
also preserve IAM roles, TLS/auth settings, health checks, resource limits,
ports, log configuration, monitoring flags and all other existing configuration.
No legacy V1 defaults are reconstructed.

API `production_health_evaluated` and current-worker `worker_loop_started` events
must be observable in their own log streams. The probe verifies the executor's
CA-validated `/health`, reads only the known synthetic V2 certification execution
under PostgreSQL read-only transactions, checks its verified projection/digest,
and requires foreign-scope rejection. It emits a retrieval-completed event.
It performs no ingestion or customer query and prints no result payload.

## Build, plan and apply

Preferred procedure: dispatch **Release certified Production V2 backend** on
`fix/deterministic-governed-output` with the reviewed full `source_sha` and
`apply=false`. Review the retained evidence. Dispatch the same SHA with
`apply=true` only when the plan and operational gates pass. The workflow serializes
releases and never cancels an in-progress rollout.

Equivalent commands, using the full reviewed SHA in `RELEASE_SHA`:

```bash
python scripts/production_release.py build --source-sha "$RELEASE_SHA" --push --evidence release-build.json
IMAGE_URI=$(python -c 'import json; print(json.load(open("release-build.json"))["image_uri"])')
python scripts/production_release.py deploy --source-sha "$RELEASE_SHA" --image-uri "$IMAGE_URI" --evidence release-plan.json
python scripts/production_release.py deploy --source-sha "$RELEASE_SHA" --image-uri "$IMAGE_URI" --apply --evidence release-deployment.json
```

Build and plan publish a certified candidate image but do not update services.
Omit `--push` for an isolated local build with no ECR write. `verify --probe`
launches one temporary task; plain `verify` performs reads and health requests.
`deploy` without `--apply` performs no AWS writes.

The build context contains only committed, regular backend files; symlinks,
submodules, credential files, runtime databases and protected-file changes are
rejected. The image has a source SHA label and manifest binding the source hashes,
certified base image and frozen profile hash. Certification checks the base
filesystem-layer ancestry, both overlay layers (only committed source/manifest
paths and bytes; no runtime changes, symlinks or whiteouts), runtime configuration,
manifest and every committed
backend file without running the candidate. ECR's `release-<full SHA>` tag must
resolve to the requested digest in the approved production repository. ECS always
receives the immutable digest reference. Mutable tags and another account,
repository or region are rejected.

The coordinator validates both candidates before registration, probes the current
production state and rereads it immediately before writes. Only image and
`NERAIUM_BUILD_SHA` change. It rolls the worker first, waits for ECS stability,
verifies its digest/configuration and startup event, then rolls the API. It
rechecks all production gates, TLS/synthetic persistence/scope and monitoring
events afterward. It does not bootstrap infrastructure, migrate data, create
secrets or rebuild task definitions from defaults.

## Post-deployment checks and retained evidence

Retain the workflow's `production-v2-release-evidence` artifact and record:

- UTC timestamps, reviewed source/local/remote SHA, source/profile hashes and
  image manifest/provenance; approved ECR digest and API/worker task ARNs.
- Preflight, intermediate worker and final stability/configuration checks;
  `/api/health` and `/api/ready` certified JSON success, executor TLS probe and RDS
  `available` status; exact database/auth/TLS bindings by ARN/hash only.
- Enabled alarm/OK actions, all 17 alarms and API/worker metric-filter fingerprints,
  confirmed SNS destination, API/worker application events and synthetic probe task
  ARN/exit code. Existing human-confirmed SNS receipt remains historical evidence;
  never claim a new email receipt without evidence.
- Focused deployment, production configuration, health, scheduler, connector,
  V2 persistence/retrieval, authorization/scope and governance test totals,
  explicit skips, diff checks, exact changed files and untouched-work inventory.
- Rollback task pair, any failed gate and restoration checks.

After a successful code release, make a separately reviewed update to the governed
profile's source/runtime observations and rollback pair. Reconstruct actual AWS
state, repeat the gates and commit/push the evidence. Do not hand-edit hashes to
silence a failed guard. The first-customer freeze remains retained in Git history.

## Stop and rollback

Stop on any missing/inconsistent configuration, unapproved source/image,
protected-source change, unstable service, invalid health response, unavailable
RDS, executor/TLS failure, firewall drift, missing monitoring event/filter/alarm,
disabled action, unconfirmed SNS subscription, failed scope/persistence check or
test failure. An automatic RDS backup can make the strict availability gate fail;
retain the failure and rerun preflight only after AWS reports `available`.

If a rollout fails, the coordinator stops progression, restores both preflight
task revisions, waits for stability and repeats production and read-only probe
checks. A recovered rollout still returns failure. If restoration fails, stop and
escalate the exact failed gate; do not force a green result.

The frozen rollback pair for the next release is API `neraium-prod-api:339` and
worker `neraium-prod-worker:333`, both using digest
`sha256:635d76fd2ff022bc2b9036ca4f1ca5153651a0b6b749cc8ff19cba347a06fa0b`.
Emergency restoration, if the coordinator cannot complete it:

```bash
aws ecs update-service --region us-east-2 --cluster neraium-prod-cluster --service neraium-prod-api-service --task-definition neraium-prod-api:339
aws ecs update-service --region us-east-2 --cluster neraium-prod-cluster --service neraium-prod-worker-service --task-definition neraium-prod-worker:333
aws ecs wait services-stable --region us-east-2 --cluster neraium-prod-cluster --services neraium-prod-api-service neraium-prod-worker-service
python scripts/production_release.py verify --probe --evidence release-restoration.json
```

Use the retained preflight pair instead once a newer baseline has been certified.
Never rotate credentials, run a migration or change security groups as an image
rollback. Preserve failure evidence and verify health after restoration.

## Operational limits

Readiness is for controlled first customer operations under the certified V2
architecture. Capacity baseline is an initial idle baseline only. Saturation,
concurrency, ingestion throughput, and maximum production rate have NOT been
established. Existing restore-drill and alert-receipt evidence is preserved;
this release certification does not repeat a destructive recovery or induce
production failures. The GitHub workflow was validated locally; no live workflow
application or production rollout was performed for this baseline freeze.
