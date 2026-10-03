# Undeployed security candidate and required qualification

Decision: BLOCKED for live customer connectivity. Current Neraium-controlled
API/worker egress and master-secret access remain unchanged. This work prepares
repository controls; it does not establish effective production isolation.

## Resource policy contract

`backend/app/services/telemetry_resource_policies.json` is server-owned image
configuration. The sole shipped profile is `synthetic-v2`: the actual approved
HTTPS/443 origin, GET, exact `/telemetry`, no query, no pagination, no credentials.
Connection configuration must select `resource_policy_id`. Missing/unknown IDs,
missing files, duplicate JSON keys, malformed manifests and malformed requests
deny. There is no compatibility fallback to arbitrary resources.

An optional absolute `NERAIUM_TELEMETRY_RESOURCE_POLICY_FILE` selects an immutable
reviewed file at startup, never a browser path. Mount it read-only in both client
and executor; the broker passes only that location to the credential-free child.
The broker independently rejects configuration outside the HTTPS schema. The
connector rechecks resources for every retry and pagination request before
transmission, while retaining public-address DNS validation, IP pinning, TLS,
no proxies, no redirects and receipt/response budgets.

Paths are exact or contain a `{segment}` matching one ASCII alphanumeric,
underscore or hyphen segment. Wildcards, percent encoding, dot traversal,
double slashes and embedded query/fragment aliases deny. This conservative
contract must be separately reviewed if an actual provider needs encoded paths.
Query rules enumerate allowed names, maximum lengths and optional exact values;
duplicates deny. Dynamic cursor/time/limit parameters are checked too. Enabling
pagination never expands origin, path or query authority.

Customer profiles require exact tenant/workspace/facility/resource/connection
scope, authentication scheme and credential binding/provider/reference plus a
`read_only_evidence` reference. That reference records an operator approval; it
does not prove the upstream permissions. No customer profile ships here. Before
approving one, retain independent upstream denial evidence and an external
resource gateway or independently read-only replica with no control network
route. The host/firewall/DNS allowlist must undergo matching recertification.
Shared signing authority remains a trusted API boundary: a compromised signer
can construct another fully matching approved job. Use a separate executor and
exact secret allowlist per customer; do not claim independent tenant identity
authorization from HMAC or manifest equality alone.

## Network qualification and exact cutover order

The CloudFormation candidate does not replace ECS services or attach its new SG
automatically. All credential/DNS cutovers default off. Do not apply it through
the existing image-only release path. Separately review a change set and costs.

1. Retain the prechange snapshot and active rollback task definitions API `:339`
   and worker `:333`. Inventory task/execution/instance IAM, resource and KMS
   policies. The current task/execution role pair, ALB, RDS and executor IDs are
   in `prechange.json`; supply them explicitly, never recreate roles from defaults.
2. Qualify the template in an isolated matching environment. Required private
   services are Secrets Manager, ECR API/Docker, Logs, SNS, ECS and ELB for current
   notification/monitoring calls, and CloudWatch where used. S3 gateway policy
   permits the existing upload bucket and ECR layer downloads. No SMTP/webhook
   destinations were configured in current task environments. New integrations
   need reviewed access through a controlled service, not general Internet egress.
3. Stage endpoints with private DNS off. Before enabling VPC-wide private DNS,
   qualify the executor NACL: current private-address denies would otherwise
   block AWS endpoint connections. Add only reviewed endpoint-subnet/IP TCP/443
   exceptions and matching return traffic; retain controller/private defaults.
   The root firewall candidate resolves only the reviewed AWS service names.
   Verify actual destination IPs and endpoint principal/resource policies.
4. Qualify the DNS domain inventory, including service CNAME chains, existing
   database and any shared-VPC consumers, before DNS association. Retain a
   fail-closed `FirewallFailOpen=DISABLED` resolver configuration. The template
   does not change that account setting. Do not broaden to arbitrary domains
   to make an incomplete inventory pass.
5. Enable qualified endpoints/DNS. Test image pull, secret retrieval, logs,
   upload CRUD, notifications, monitor reads, authentication and worker loops.
   Then replace the old task SG association with the candidate SG; do not leave
   both attached, because SG permissions combine. Its only egress is database
   5432, executor 8443, approved private endpoints 443 and regional S3 443.
   Verify effective route/NACL/SG/DNS configuration and arbitrary destination
   denial in a controlled isolated network fixture before production cutover.
6. Preserve NAT for unrelated consumers if required; the new task SG prevents
   use of it for arbitrary traffic. Retain all alarm/log delivery paths. Restore
   saved task/SG associations on functional failure; preserve evidence and stop.

AWS references: [endpoint configuration](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ec2-vpcendpoint.html),
[S3 gateway access](https://docs.aws.amazon.com/vpc/latest/privatelink/vpc-endpoints-s3.html),
[DNS firewall rules](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-properties-route53resolver-firewallrulegroup-firewallrule.html).
CloudFormation `ValidateTemplate` passed; this does not certify deployment,
permissions, DNS inventory, networking or functionality.

## Database credential separation: STOP before live migration

Current auth reads the rotating RDS master secret. Production auth startup now
requires migrated schemas and a nonadministrative identity, reads the migration
ledger and rejects privileged roles, admin-role memberships, CREATE, ownership
and ledger writes. It does not run DDL. The separate
`scripts/migrate_auth_schema.py` command requires an explicitly supplied secure
`NERAIUM_AUTH_MIGRATION_DSN`; failures do not print driver/credential details.

Before any live identity change:

1. Verify backup availability and recovery drill. Inventory table/schema owners,
   PUBLIC grants, role memberships, functions, RLS, existing sessions and all
   runtime statements. Qualify this inventory on a restored isolated database.
2. Run auth migrations using the controlled migration identity. Apply the
   candidate `auth-runtime-grants.sql` only after owner/PUBLIC grant review.
   Revoke inappropriate inherited/PUBLIC permissions through a separately
   reviewed migration; direct REVOKE does not cancel inherited permissions.
   Confirm CONNECT and schema USAGE, four auth tables' DML and ledger SELECT.
   Deny DDL, ownership, TRUNCATE, admin roles and privileged function execution.
3. Provision a dedicated managed auth-runtime credential through a secure
   credential workflow. No password is present in candidate SQL or CloudFormation.
   Test rotation, reconnect, login/session/user/membership operations and denial
   of database administration. Keep telemetry/runtime DB identities separate;
   do not grant the connector broker any database identity.
4. Separately recertify the auth secret binding, IAM and release guard. The
   existing `production_release.py` explicitly requires the RDS master-secret
   binding, so it cannot safely deploy this separation. Replace that contract
   through reviewed recertification, not a bypass or edited frozen hash.
5. Switch the new task binding, verify health/operations, then enable the
   explicit master/source-secret deny policy and remove old allow grants.
   Retain old identity/binding and rollback definitions under controlled admin
   authority until recovery is qualified. Never give the runtime migration access.

No database credentials, roles, permissions, schemas or data changed in this pass.

## Executor host qualification

SSM reports ConnectionLost. Installed host rules, service state and capabilities
remain UNVERIFIED. Current EC2 configuration proves IMDSv2 required, IPv6 IMDS
disabled, hop limit 2. The candidate launch template specifies hop limit 1 for
qualified host-network replacement; it does not update the existing instance.

The bootstrap candidate retains root only for secret retrieval and UID/GID
transition, with SETUID/SETGID capabilities, no-new-privileges, read-only container
filesystem, root-only TLS/replay files and no child AWS environment. It restricts
new root connections to DNS, IMDS, self-health and reviewed AWS IPs:443. Root
IMDS access is intentional; exact executor-role secret denials limit its authority.
The child remains restricted to the approved synthetic IPs:443 and resolver.
IPv6 is denied for both. Refresh inserts completed deny-by-default chains before
removing old hooks and never flushes an attached IPv6 chain.

Local fake-tool execution checks refresh and packet-policy behavior without
altering networking. Real kernel, reboot/refresh failures, DNS/SNI behavior,
instance policy, endpoint NACL and metadata/capability denials still need isolated
host qualification. Inherited established connections need draining/restart at
cutover; host owner rules alone do not constrain new arbitrary UIDs from a
compromised root broker. Independently enforce SG/NACL/firewall/IAM restrictions.

## Deployment stop

Candidate source changes protected files, schema initialization semantics,
resource configuration and infrastructure. The existing certified release path
does not authorize this topology. No image was published, no task registered,
no deployment performed and no origin push made. Require separate complete
recertification before a future controlled release. Production health inspection
is retained separately and is not post-deployment verification.
