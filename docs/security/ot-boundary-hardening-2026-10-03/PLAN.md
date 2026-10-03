# OT boundary hardening candidate

Production reconstruction matches the preceding audit. `prechange.json` retains
non-secret AWS configuration, grants, running tasks, recovery state and rollback
references. Environment values unrelated to reviewed configuration are omitted.
No secret values were requested. Starting source: `d1052d04`.

## Minimum change plan, established before implementation

1. Resource policy: an immutable server-owned manifest authorizes origin, GET,
   exact paths or single path-segment patterns, query names/values, authentication
   scheme, pagination, credential binding and full customer scope. Browser
   configuration selects a policy ID; it cannot supply or expand the policy.
   Missing/malformed policies deny. Recheck every retry and continuation before
   credentials are sent. Preserve public DNS pinning, TLS, receipt bounds and
   redirect rejection. The only shipped approval is the actual synthetic
   `GET /telemetry` endpoint, with no queries and no customer credentials.
2. Network: prepare a CloudFormation candidate for private Secrets Manager,
   Logs, ECR, SNS, ECS and ELB endpoints plus S3 gateway access. A replacement
   application SG allows only RDS:5432, executor:8443, private endpoints:443 and
   the regional S3 prefix list:443. Retain ALB ingress and explicitly add the
   replacement group to database/executor ingress. Do not attach it live until
   endpoint/DNS/S3 policies and all legitimate notification/monitor dependencies
   are qualified. NAT presence must not substitute for restricted SG egress.
3. Identity: prepare a new app-role policy with explicit master-secret and
   customer-source-secret value denials, keeping required upload/notification
   permissions. Auth needs a separate DML identity; existing runtime telemetry
   credentials remain separate. Add schema verification without runtime DDL and
   an offline migration command. Do not change live credentials or grants here.
4. Host: retain the installed-rule verification gap. Prepare restrictive broker
   UID and child rules, explicit IPv6 denial, minimum capabilities, private DNS
   exceptions and IMDSv2. Root/container network and resolver behavior require
   an isolated host qualification; do not apply an unqualified bootstrap script.
5. Credential permission: customer policies require an operator-owned evidence
   reference attesting independently read-only upstream permissions. This is an
   admission requirement, never proof that the attestation is true. Public
   synthetic policy is explicitly identified and cannot carry customer secrets.

## Production-affecting stages and rollback

| Stage | Pre-change state | Change | Functional/security checks | Rollback criterion |
| --- | --- | --- | --- | --- |
| Resource policy | Existing connections lack policy selectors | Reviewed selectors for known synthetic connections; immutable manifest in candidate image | Synthetic retrieval succeeds; same-host control paths and query escalation deny | Restore previous executor image/task pair if telemetry fails; no allow-all fallback |
| Private service access | NAT and broad app SG | Endpoints, S3 route/policy, replacement SG; qualify then attach to tasks | Secrets/auth, S3 uploads, logs, SNS, monitoring, worker and API; arbitrary egress denial | Restore saved SG associations/task definitions if required access fails |
| DB identity | App retrieves rotating RDS master secret | Provision auth DML role/secret separately; migrate schemas offline; switch binding; deny master | Login/session/membership CRUD; migration ledger SELECT; DDL/admin deny | Restore old task/binding only under controlled incident approval; preserve both identities/data |
| Executor host | Root broker, child owner firewall | Qualified host identity/egress candidate, IMDSv2, immutable policy | TLS health, synthetic fetch, DNS, child/root/metadata denials | Restore saved instance configuration/image; no in-place firewall improvisation |

## Stop gates

The certified release implementation permits image/source overlays only and
rejects protected connector/auth source and topology changes. This candidate
therefore requires separate source, image, infrastructure and DB recertification.
Do not change the frozen profile to silence a guard. Do not push, build/publish
an uncertified image, register tasks, migrate production or deploy here.

Before a future rollout require committed/reachable source, successful focused
tests, reproducible qualified image, retained rollback definitions, healthy
recovery/alarms and stable 1/1/0 services. A live DB migration cannot be established
confidently from configuration reads: stop before live credential changes.
