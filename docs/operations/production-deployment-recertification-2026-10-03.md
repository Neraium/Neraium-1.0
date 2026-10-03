# Production baseline freeze and release recertification — 2026-10-03

## Scope and authority

Starting repository and remote `origin/fix/deterministic-governed-output` HEAD:
`2f60d98777e5a86c82397ba93e22ac83454fe0cf`.
SRE implementation: `74a542562f4569f9e72c58a0efcd96ff0801b2af`.
The SRE closeout is retained unchanged at
[`sre-closeout-2026-10-03.md`](sre-closeout-2026-10-03.md), SHA-256
`a79fb85da4386e7e44be76fb575f3cd7eb4bc84c6057449ee12cb62ed34cebe7`.

The governed first-customer profile is
[`first-customer-production-baseline-2026-10-03.json`](first-customer-production-baseline-2026-10-03.json),
SHA-256 `654ddfcff25c35c9ab99e3d52b3babaaa090f91e402e1873eb4d526d666704ec`.
Its observation revision describes the deployed application source; this
recertification commit changes release tooling, tests and documentation only.
No application source, formulas, findings, evidence governance, customer records,
credentials or live service configuration were changed.

## Production observations

Profile frozen at `2026-10-03T07:30:04.657886+00:00`. Complete canonical
verification and fresh read-only probe passed at
`2026-10-03T07:45:42.671084+00:00`; final JSON health/configuration/monitoring
verification passed at `2026-10-03T07:52:44.435420+00:00`.
Current-template preservation plan passed at
`2026-10-03T07:53:51.318857+00:00`, without AWS writes.

| Gate | Evidence/result |
| --- | --- |
| API | `neraium-prod-api:339`, ACTIVE, one COMPLETED deployment, desired/running/pending `1/1/0` |
| Worker | `neraium-prod-worker:333`, ACTIVE, one COMPLETED deployment, desired/running/pending `1/1/0` |
| Both serving images | `680779862188.dkr.ecr.us-east-2.amazonaws.com/neraium-prod-api@sha256:635d76fd2ff022bc2b9036ca4f1ca5153651a0b6b749cc8ff19cba347a06fa0b` |
| Identity | `physical-endpoint-keyed.v2`, both roles, PASS |
| Egress/dynamic writes | Controlled egress `true`, dynamic secret writes `false`, firewall READY/IN_SYNC |
| API health/readiness | HTTP 200; `neraium-api` JSON status `ok` / `ready` |
| RDS | `neraium-prod-postgres` available; rotating auth ARN/endpoint match deployed bindings |
| Executor | EC2 system/instance checks OK; certified HTTPS URL/auth ARN/CA hash retained; CA-verified `/health` PASS |
| Database bindings | Runtime and telemetry secret ARNs unchanged; exact references in profile |
| Monitoring | 17/17 alarms OK and actions enabled, alarm and OK destinations preserved; five API and eleven worker metric filters match frozen fingerprint |
| Application events | API `production_health_evaluated` and serving-worker `worker_loop_started` observed in their own streams |
| Synthetic persistence/scope | Existing V2 verified projection and digest retrieved; foreign scope rejected; read-only PostgreSQL transactions; PASS |

The fresh combined TLS/synthetic verification task was
`arn:aws:ecs:us-east-2:680779862188:task/neraium-prod-cluster/4d9ec7a96b7841348899a7d743adb969`,
exit code zero. An earlier direct executor health task
`e8d9a6aae9db4d7f80bc638941739988` also exited zero. These temporary tasks stopped;
no serving task definition was registered or service rolled out.

SNS subscription is confirmed:
`arn:aws:sns:us-east-2:680779862188:neraium-prod-infrastructure-alerts:aae5659b-3a48-4a2f-a316-f88e3bcdc318`.
Existing controlled alert message `ae28c9db-0463-57b8-81bb-aae1a3d5d7f2` was
human-confirmed at `craig@neraium.com`, subject
“Neraium production SRE controlled alert test 2026-10-03”, reported receipt
11:49 PM local time (timezone unspecified). No new receipt is claimed.

One strict production check failed at `2026-10-03T07:41:28.494134+00:00` with
`rds_unavailable`. AWS RDS events record automatic backup start at
`07:40:05.940000 UTC` and finish at `07:43:08.009000 UTC`. Availability and all
gates subsequently passed. No deployment proceeded during the failed gate and no
restoration was necessary. The availability requirement was not weakened.

## Generic workflow correction

The former generic workflow was fail-closed on the obsolete
`Dockerfile.connector-overlay` lineage. It compared against a pre-SRE digest
(`d57f44d3…`) instead of the current SRE-certified runtime. Its remaining
implementation independently reconstructed API/worker environment and secret
bindings from repository variables, read executor TLS secret material, ran
bootstrap/migration logic, and maintained a second deployment implementation.
Earlier unsafe defaults and incomplete V2 bindings motivated that hard stop.
Removing only the hard stop would not have recertified this path.

The replacement manual workflow uses the canonical `production_release.py` for
build, provenance certification, plan and rollout. The historical SRE executable
is a compatibility entrypoint to the same coordinator. The stale connector and
SRE Dockerfiles remain historical references; the production workflow invokes
neither. Production remains manual; dispatch now defaults to a plan.
Source must be a full commit reachable from the approved remote branch. Candidate
source is tested in a clean detached worktree.

All task configuration and service topology are fingerprinted. Candidate creation
changes only immutable image reference and build marker. Explicit V2, egress,
secret-write, runtime/telemetry binding, executor URL/auth/CA and process-role
guards complement complete configuration preservation. Actual alarms and metric
filters are fingerprinted and checked before/after deployment. AWS account,
image repository, region, source label/manifest, runtime lineage and source bytes
are checked. Both new image layers must contain only the committed source and
release manifest; runtime file writes, uncommitted files, symlinks and whiteouts
are rejected. ECR tag/digest agreement is checked before rollout.

Existing runtime Python is conservatively frozen except the public application-info
route. Protected code, dependency, schema or configuration changes require a
separately reviewed recertification; the workflow has no bypass. This is a
bounded certified release path, not approval of arbitrary future code changes.

## Verification and regression

- Deployment/configuration/provenance/rollback/workflow/monitoring contracts:
  **74 passed**, zero skipped, 33.17 seconds, two existing dependency warnings.
  One intermediate test failure came from mocking `subprocess.run` globally,
  intercepting the earlier Git lookup. Its fixture was corrected to exercise
  the actual unapproved-remote guard; no production guard was relaxed.
- Clean-checkout product suites: **253 passed, 1 skipped**, 111.68 seconds,
  two dependency warnings. Coverage includes health, scheduler, V2 projection and
  persistence, authorization, authenticated scope, runtime grants, production
  configuration, connectors, SSRF and evidence/governance boundaries. The
  optional database fixture lacked `NERAIUM_TEST_TELEMETRY_RUNTIME_DSN`; the fresh
  production synthetic read-only persistence/scope probe passed independently.
- Prior focused SRE closeout: **96 passed, 1 skipped**, retained as historical
  evidence; not represented as a new run.
- Real isolated build/certification at `2026-10-03T07:52:44.435003+00:00`:
  PASS. Source `2f60d98777e5a86c82397ba93e22ac83454fe0cf`, 406 committed
  backend files; source manifest SHA-256
  `35af2cd3858316ced81326c64ede5bdb716ddcbc9fd241f1cde761172cab8bc1`.
  Local image ID `0c6b036c8a7a`; no ECR push or deployment. Runtime lineage,
  configuration, both overlay layers, embedded profile manifest and all source
  bytes passed certification. An earlier isolated container imported V2/connector
  modules with network disabled and a read-only filesystem.
- Actual serving task templates passed the image/build-marker-only preservation
  plan. No AWS registration, update or probe occurs in the dry-run coordinator.
  Positive rollout and failure/restoration orchestration were behavior-tested
  using isolated fakes; no live rollout was performed merely for certification.
- Workflow YAML parsing and every Bash step syntax: PASS.
- `git diff --check` and `git diff --cached --check`: PASS. Exact staged
  name-status/diff review: PASS; only the twelve task-owned files are staged.

The executable release procedure, postflight gates, automatic rollback, emergency
rollback commands, evidence requirements and stop conditions are in
[`production-release-v2.md`](production-release-v2.md).
Rollback pair remains API `339` / worker `333` at the current certified digest.

## Hygiene and existing SRE gates

The initial dirty inventory contained **17,286 entries**: two tracked historical
ingestion files and 17,284 untracked files. Inventory SHA-256:
`5963360ebc7765b2f5d59e1d1e6325b59229ce6e9394ecafa754e16eaa2f9ee5`.
Every initial path retained its size/mtime; both tracked file byte hashes matched.
Historical ingestion/review authority, research, benchmarks, validation, generated
and experimental work are excluded from the commit. No broad staging is allowed.

The original isolated point-in-time restore drill PASS and cleanup confirmation
remain governed by the SRE closeout. No second restore was performed. The
temporary restored RDS instance and security group were also verified absent
during this closeout.

**Capacity baseline is an initial idle baseline only. Saturation, concurrency,
ingestion throughput, and maximum production rate have NOT been established.**

Other non-blocking limits: connector SSM remains disconnected despite successful
direct TLS health; no production failure/alarm transition was deliberately
induced; fresh authenticated customer API reads were not performed; human alert
receipt is preserved evidence; hosted GitHub workflow execution and a new live
rollout were not necessary for this task and were not performed.

## Conclusion

GENERIC PRODUCTION DEPLOYMENT RECERTIFIED: YES, within the frozen release profile.

FIRST-CUSTOMER PRODUCTION BASELINE FROZEN: YES.

READY FOR CONTROLLED FIRST CUSTOMER OPERATIONS: YES.

Remaining blockers: none. Next engineering action: review the next committed
candidate against the frozen profile and run the manual release workflow with
`apply=false`; separately recertify any protected code/configuration change before
an applied release. Do not infer a production capacity limit from this freeze.
