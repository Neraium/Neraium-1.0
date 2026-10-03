# Production database privilege separation assessment

**Decision: BLOCKED.** Production privilege separation was not activated. The
private RDS database is unreachable from this environment, so production roles,
ownership, grants, functions and migration compatibility remain unknown. The
existing release coordinator rejects an auth runtime secret change, and the
shared storage initializer still requires schema CREATE. These are material
qualification failures. No production DB, IAM, secret, task definition, service
or network mutation occurred. No secret values were retrieved, printed or saved.

This is an evidence-only repository change. It does not supply a qualified
deployment candidate. Work stopped before production mutation under the requested
phase 4 and phase 7 gates. Auth-only qualification cannot establish the requested
API and worker security claims.

## Current repository and production state

The assessed source is `43553130e63bf36aa9d4ff748318d7c1e8519492` on
`fix/deterministic-governed-output`. The live origin branch was checked with
`git ls-remote` and contained the same commit. The two dirty tracked files at
entry were `backend/app/routers/historical_ingestion.py` and
`backend/app/services/historical_ingestion.py`. Both remain excluded from this
change. Existing untracked validation and research files remain excluded.

[evidence.json](evidence.json) records observation times, exact task/secret/role
ARNs, task configuration and topology fingerprints, the read ledger, protected
file hashes, and the checks below. It contains configuration and metadata only.
Task configuration and service topology match the retained
[readiness evidence](../ot-cutover-readiness-2026-10-03/evidence/final/production-services.json).
No material drift was found in the compared serving configuration and IAM policy
documents. The prior readiness reports, snapshots and auth harness are retained
untracked workspace evidence, not content at the assessed source commit. Their
hashes and provenance are recorded, and the auth harness used here is copied
into this assessment for reproducibility. Unknown database catalog state is
explicitly **not** treated as a matching or empty catalog.

| Item | Current observation |
| --- | --- |
| API | `neraium-prod-api:339`, ACTIVE, desired/running/pending 1/1/0, one COMPLETED deployment |
| Worker | `neraium-prod-worker:333`, ACTIVE, desired/running/pending 1/1/0, one COMPLETED deployment |
| Serving image | `sha256:635d76fd2ff022bc2b9036ca4f1ca5153651a0b6b749cc8ff19cba347a06fa0b` |
| Shared task role | `neraium-prod-task-app-role` |
| Execution role | `neraium-prod-ecs-task-execution-role` |
| API auth binding | RDS master secret `rds!db-71cfd5f5-506d-48e5-8794-52b72aa2f4df-ZmbBKT` |
| API and worker storage bindings | `NERAIUM_TELEMETRY_DATABASE_URL` and `NERAIUM_RUNTIME_DATABASE_URL` both reference `neraium/prod/telemetry-database-url-1B15Li` |
| Worker auth binding | None; the worker still shares the task role that permits master retrieval |
| RDS | Standalone `neraium-prod-postgres`, available, private, PostgreSQL 16.14, master username `postgres`; no cluster identifier |
| Backups | Retention 7 days; available automated snapshot `rds:neraium-prod-postgres-2026-10-03-07-40`; latest restorable time recorded; restore drill not established |
| TLS configuration | API auth `sslmode=require`; RDS parameter group `default.postgres16`, in sync; configured `rds.force_ssl=1`, `ssl=1`, minimum TLSv1.2; RDS CA `rds-ca-rsa2048-g1` |
| Actual TLS sessions | Not inspected; telemetry/runtime DSN values were not retrieved |
| Monitoring | Frozen monitoring fingerprint matches; 17 alarms OK with actions enabled |
| Public API | Canonical read-only check passes `/api/health` and `/api/ready` |
| Logs | No `permission denied` matches in the current API/worker streams over the checked one-hour window; this bounded filter is not persistence qualification |
| Catalog inventory | Unavailable: endpoint resolves to `10.40.3.9`, TCP 5432 times out |

Production users/roles beyond the RDS master username, transitive role membership,
schema/table/sequence/function owners and ACLs, default privileges, SECURITY
DEFINER functions, RLS policies, and live migration ledgers were **not obtained**.
No controlled reachable admin runner was established by repository release
tooling. No tunnel, SSM command through the connector, new ECS task, or network
exception was created to bypass that limitation.

## Runtime and migration privilege models

The following auth model is derived from
[auth_store.py](../../../backend/app/services/auth_store.py) and the retained
auth checks. It is a candidate for the existing `public` auth objects, subject to
the missing production catalog review. It is not an approved combined production
grant set.

| Runtime operation | Smallest code-derived auth authority |
| --- | --- |
| Database and schema access | CONNECT to the intended existing database; USAGE on `public` |
| Users, workspaces and memberships | SELECT, INSERT, UPDATE on `auth_users`, `auth_workspaces`, `auth_workspace_members` |
| Sessions and expiry cleanup | SELECT, INSERT, UPDATE, DELETE on `auth_sessions` |
| Migration verification | SELECT only on `auth_schema_migrations` |
| Transactions and locks | Ordinary transactions, row locks, `hashtext`, `pg_advisory_xact_lock` |
| Sequences | None for auth: IDs are application-assigned text |
| LISTEN and NOTIFY | No requirement found in the inspected auth, telemetry repository and shared PostgreSQL adapter |
| Temporary tables | No runtime requirement found in those inspected paths |
| DDL and migration | No runtime grant; production startup must verify and fail closed |

The proposed auth LOGIN has NOSUPERUSER, NOCREATEDB, NOCREATEROLE,
NOREPLICATION, NOBYPASSRLS, NOINHERIT, no memberships, no owned objects, and no
grant options. Effective CREATE and TEMP privileges, unrelated schema access,
unreviewed functions and administrative memberships must be absent. Direct
REVOKE cannot remove PUBLIC or membership-derived access; ownership conveys DDL
authority. These checks require the actual catalog before any ACL change.
[PostgreSQL privilege semantics](https://www.postgresql.org/docs/16/ddl-priv.html)
and [role membership](https://www.postgresql.org/docs/16/role-membership.html).

The current [auth grant candidate](../../../infra/production/auth-runtime-grants.sql)
still grants unnecessary DELETE on the three non-session tables, reuses an
existing role without full inventory, and does not reconcile CONNECT, PUBLIC,
TEMP, functions or default privileges. It was left unchanged because production
inventory and full qualification failed.

API and worker also require shared finding/evidence/governance/queue storage in
`neraium_runtime`, and telemetry DML in `telemetry`. Auth privileges alone cannot
satisfy those paths. `telemetry_repository.py` uses SELECT/INSERT/UPDATE,
checkpoint DELETE, row locks, and advisory locks using `hashtext` and
`hashtextextended`. Migration ledgers and immutable catalog/artifact tables must
not receive blanket write grants. The shared storage SQL defines identity
sequences and a trigger function; their production owners, ACLs and precise
sequence/function requirements remain unqualified. No blanket table, sequence,
function or cross-schema grant is proposed.

Migration/admin authority must belong to a separate release-only identity with
ownership/DDL for the reviewed application objects. Role/credential provisioning
requires separate controlled administrative authority; ordinary migrators need
not have cluster administration. Neither identity belongs in API, worker or
connector roles/bindings. Current mechanisms are:

- [migrate_auth_schema.py](../../../scripts/migrate_auth_schema.py): explicit
  `NERAIUM_AUTH_MIGRATION_DSN`, transaction, advisory lock 173514001, three auth
  migration IDs, bounded outcome messages. It is locally idempotent, but its
  production execution path and current schema compatibility are unqualified.
- [apply_telemetry.py](../../../backend/db/migrations/apply_telemetry.py): nine
  ordered migration modules. It consumes a DSN named
  `NERAIUM_TELEMETRY_DATABASE_URL`; that variable name does not ensure a separate
  admin identity. Live ledger state and one-shot release execution were not
  qualified. Ordinary telemetry readiness performs structural verification.
- [runtime_postgres.py](../../../backend/app/services/runtime_postgres.py): shared
  storage `initialize()` acquires advisory lock 173514002 and executes schema/table
  DDL, including during production startup. This must be separated into explicit
  admin migration and runtime verification before cutover.

These adapters open psycopg connections per operation rather than using a
connection pool. Auth caches its managed DSN and retries one credential refresh
after password authentication rejection. Telemetry/shared storage receive DSNs
through ECS environment secret injection; no equivalent live credential refresh
was found in their connection factories. Rotation/reconnect qualification for
the proposed credentials has not been completed.

## Disposable database qualification

Application source was extracted with `git archive HEAD`; dirty historical
files and unrelated untracked files were not test inputs. The retained security
harness is a separate hashed input. The database had
`--network none`, no published ports, and local trust authentication. The probe
process shared only its network namespace, with read-only source mounts and no
forwarded production DSNs or AWS environment.

The fixture reports PostgreSQL **16.15**, while RDS reports **16.14**. It is a
fresh synthetic catalog, not an RDS restore; it does not qualify production TLS,
RDS extensions/roles, customer data or credential rotation.

The retained [auth qualifier](qualify_auth_baseline.py)
passed **24 checks**: separate migration identity and idempotence, auth runtime
schema verification, users/workspaces/memberships/sessions, transactions/advisory
locks, CREATE/ALTER/DROP/role/database/TEMP denials, ledger write denials, and
rejection of PUBLIC CREATE and an admin SET ROLE membership. That script first
uses the broader existing auth grant candidate, then revokes unnecessary DELETE
and checks startup and user DELETE denial. It does not rerun every positive path
after narrowing, and does not qualify the other application schemas.

[probe_runtime_startup.py](probe_runtime_startup.py) adds five SQLSTATE `42501`
checks for schema DROP, ownership change, administrative membership GRANT,
extension creation and unrelated schema access. Unauthorized table GRANT/REVOKE
produce no ACL change; PostgreSQL can complete such statements with warnings,
so the probe checks the actual resulting privileges rather than requiring an
exception for a harmless no-op.

The same probe installs the entire current shared schema as a separate local
migration role, grants the runtime schema USAGE and migration-ledger SELECT,
then invokes `initialize()` as the runtime identity in `APP_ENV=prod`.
**Initialization fails with SQLSTATE `42501`** at:

```sql
CREATE TABLE IF NOT EXISTS postgres_runtime_migrations (version INTEGER PRIMARY KEY)
```

The table and version 1 already exist. Granting CREATE to make this pass would
violate the requested runtime model. Telemetry persistence, finding/evidence
persistence and ordinary worker operations were not qualified under a complete
narrow identity. Local qualification is therefore **incomplete and blocked**.

For reproduction, first start a fresh network-none `postgres:16-alpine` container
with `POSTGRES_DB=neraium` and `POSTGRES_HOST_AUTH_METHOD=trust`. Run the referenced
auth qualifier followed by this probe in its network namespace. Mount the
committed `backend` and `infra/production/auth-runtime-grants.sql` at
`/qualification`, set `PYTHONPATH=/qualification/backend`, and use the retained
local image `neraium-ot-vuln:after` as the Python/dependency runner. Exact image
IDs and script/source hashes are retained. Never use these trust DSNs against a
production service. The disposable database was removed after the checks.

## Rolling deployment and rollback gates

The required A through K ordering cannot currently be executed safely through
repository release tooling. An in-memory copy of the live API definition with
only the auth secret ARN changed is rejected with
`certified_task_configuration_changed`. The coordinator additionally requires
the auth secret ARN to equal RDS `MasterUserSecret.SecretArn`, changes only image
and build marker, and deploys worker before API. Its rollback restores task
definitions only. It cannot perform the requested API-first credential/IAM
transition or its coordinated rollback. No coordinator bypass was added.

Current repository auth startup rejects administrative identities. Retained
readiness evidence records that the unchanged serving image runs auth migrations
and requires its master path. The new image and dedicated auth binding must
therefore move together; substituting only a credential or only an image is not
a qualified transition.

Once these blockers are resolved, the required sequence remains: A create the
dedicated runtime role; B store a separate runtime secret; C apply reviewed
minimum grants; D qualify that identity; E register image and secret together;
F deploy API then worker; G verify behavior; H verify DDL/privilege denial;
I confirm every old task drained; J remove ordinary task-role master access;
K verify the exact retained rollback path. Production execution must also
preserve the user's production sequence of grants before secret storage. Role,
grants and secret provisioning are completed before any serving-task change.

Old tasks must keep the existing master binding/permissions throughout coexistence.
New tasks must use only dedicated runtime credentials, execute no schema
migrations, and have no fallback to master. No shared master-secret deny, KMS
revocation, private-DNS or endpoint policy change may strand old tasks. This task
made no network changes. There is no qualified new task pair to deploy today.

| Failure before master access removal | Required rollback behavior once a coordinator is qualified |
| --- | --- |
| Runtime role or grant failure | Abort provisioning transaction; keep current services and master identity; capture actual catalog outcome before retry |
| Secret binding failure | Do not deploy; retain original task definitions and credentials; never overwrite/rotate the master secret to fix a runtime binding |
| API startup failure | Restore API `neraium-prod-api:339` with original binding and unchanged IAM; retain worker `:333`; verify health/ready |
| Worker startup failure | Restore worker `neraium-prod-worker:333` and the qualified API pair; verify both services and existing monitoring |
| Missing runtime privilege | Restore the known task pair; derive and qualify the missing ordinary privilege before retry; never grant ownership/admin as a workaround |
| Schema incompatibility | Stop before rollout; no runtime migration, destructive downgrade or automatic restore over current data; resolve compatibility under separate admin execution |

After master access removal, the old API revision also needs its original IAM
policy and KMS path restored through controlled admin execution. Exact current
inline policies, names and ARNs are retained in `evidence.json`; their restoration
and the full post-cutover rollback have **not** been rehearsed. No rollback
credential, task definition, image or policy was revoked/deleted. The current
pair remains ACTIVE and healthy. This is rollback preservation, not proof of a
future credential-transition rollback.

## Secrets and production preconditions

IAM simulations were run separately for each exact ARN/action and checked against
the requested resource. The shared application role allows GetSecretValue and
DescribeSecret on the RDS master secret. The execution role and connector role
have implicit deny for that master secret. The execution role allows retrieval
of the telemetry/runtime DSN secret; the connector role has implicit deny for
that secret. These are identity-policy simulations, not live retrieval with
task credentials or complete SCP/key/endpoint enforcement evidence.

No dedicated `neraium/prod/auth-runtime-*` secret was found in the inspected
metadata. A legacy `neraium/prod/auth-database-url` secret remains allowed to the
execution role, and `neraium/prod/telemetry-migration-database-url` exists. Their
database identities were not read or classified; secret names are not proof of
least privilege. The inspected master/telemetry secrets have no resource policy.
The master uses RDS-managed rotation; no runtime rotation mechanism was qualified.
All values remain undisclosed. The executor has no application DB secret allow
in the inspected role policies, but SQL denial was not tested from that host.

| Production prerequisite | Result |
| --- | --- |
| Qualified candidate committed and present at origin | NOT MET; this commit records evidence only; no push |
| Targeted complete privilege tests and disposable qualification | NOT MET; partial auth checks pass; shared startup fails |
| Healthy backup status and RDS state | Observed healthy; isolated restore qualification not established |
| Stable ECS API and worker | PASS for current pair |
| Known rollback definitions | PASS for current pair; transition rollback unqualified |
| Healthy existing monitoring | PASS, 17 alarms OK/actions enabled, frozen fingerprint matches |
| No unresolved migration incompatibility | NOT MET; live catalogs/ledgers unknown; runtime DDL remains |
| Safe repository release tooling | NOT MET; changed auth binding rejected; image-only worker-first coordinator |

No live role, grants, secret, IAM policy, task definition or deployment was created.
No production DDL attempts or functional writes were run. Customer/frontend,
telemetry and finding/evidence paths were not newly exercised; current API health
and readiness passing are not substituted for those checks.

## Assurance claims

Only production evidence can mark the requested claims PROVEN. None is marked
PROVEN here.

| SECURITY CLAIM | CONTROL | ENFORCEMENT LAYER | TEST | RESULT | EVIDENCE | ROLLBACK | RESIDUAL RISK |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ordinary Neraium runtime does not possess database master privileges. | Dedicated runtime credentials and narrow grants | PostgreSQL and Secrets Manager/IAM | Live bindings, IAM simulation, catalog inventory | NOT PROVEN; master binding and allow remain | `production.ecs`, `production.secrets_iam_checks`, catalog unavailable | Current pair and master path preserved | Actual effective DB privilege inventory missing |
| Runtime tasks cannot perform schema DDL. | No ownership/CREATE/admin membership; verification startup | PostgreSQL and application startup | 24 auth checks, five added denials, shared storage probe | NOT PROVEN; shared startup requires CREATE locally | `local.auth`, `local.storage` | No live ACL changes; current tasks remain | Entire API/worker privilege qualification incomplete |
| Schema migration requires a separate administrative identity. | Explicit release migration and no serving DDL | Application and release execution | Offline auth migration, shared storage startup, coordinator probe | NOT PROVEN; shared startup DDL remains | `local`, `release_coordinator_probe` | No live migration; existing schemas/data untouched | Separate complete admin execution path unqualified |
| API/worker cannot retrieve the RDS master secret after cutover. | Remove master allow and enforce dedicated runtime binding after drain | Secrets Manager/IAM and deployment coordinator | Exact-ARN role simulations and task binding probe | NOT PROVEN; no cutover; shared role allows master | `production.secrets_iam_checks`, `release_coordinator_probe` | Original IAM and ACTIVE task definitions retained | No post-cutover denial or rollback rehearsal |

## Scope and retained files

Only this directory is included in the assessment commit:

- `REPORT.md`
- `evidence.json`
- `probe_runtime_startup.py`
- `qualify_auth_baseline.py`
- `MANIFEST.json`

`MANIFEST.json` hashes the report, retained evidence, local probe and referenced
qualification/source files. Protected historical-ingestion file hashes and their
git diff hash were checked before and after the evidence write. No application,
IaC, release-tooling or historical-ingestion file was edited. No existing
untracked validation/research artifact was staged. Resolve the resulting evidence
commit with `git log -1 --format=%H -- docs/security/database-privilege-separation-2026-10-03`.
