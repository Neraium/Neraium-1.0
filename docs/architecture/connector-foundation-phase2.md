# Connector foundation Phase 2: additive source provenance

Decision: extend the existing production boundary in place. The user authorized
separating source-reported quality from analytical admission on 2026-09-24.
The [Phase 1 stop record](connector-foundation-phase1.md) remains unchanged as
historical evidence. Baseline branch `fix/deterministic-governed-output`, HEAD
`d79cdb6222203e9313b6b4fc9a294a38d5f7c976`; tracked worktree/index were clean.
Unrelated untracked artifacts were not incorporated.

## Resolution and compatibility

| Previous gap | Authoritative resolution | Compatibility |
| --- | --- | --- |
| Source quality conflated with admission | `SourceQualityState` describes the source; existing `TelemetryQualityState` still governs admission. | `_reported_quality_decision`, numerical normalization and evidence sufficiency are unchanged. |
| Native quality lost on accepted-row persistence | Persist a typed native code and the existing adapter report in a versioned source-provenance payload on both accepted and rejected rows. | Existing `reported_quality` and its v1 digest interpretation are retained. |
| No acquisition time | Optional aware `acquired_at_utc` on the raw envelope and prepared records, persisted separately. | Missing capture stays null; source time is never a fallback. |
| Source values lose type on JSON persistence | Reuse the existing typed scalar encoding for durable source representation. | Finite `original_value` and analytical `normalized_value` are unchanged; rejected nonfinite JSON markers are described below. |
| SDK forces unsupported acquisition methods | Discovery, incremental and backfill methods have safe, nonretryable unsupported-operation defaults. | Descriptors remain explicit and read-only; validate/health remain mandatory. No new transport capability or adapter is introduced. |

The canonical path is still `RawObservationEnvelope -> prepare_connector_page ->
normalized_observations -> existing analytical window`. This is not a second
canonical observation model, ingestion authority or analytical representation.

## Source quality and unchanged admission

Quality classification is descriptive; it does not make any source eligible.
Existing mapping, timestamp, unit and numerical validation still apply.

| Existing adapter `reported_quality` | Source quality | Existing admission quality / result |
| --- | --- | --- |
| Not supplied (`None`), no native code | null (not supplied) | good / eligible if other checks pass |
| `good`, `normal`, `ok`, `pass`, `passed`, `true`, `valid`, `0` | good | good / eligible if other checks pass |
| `uncertain`, `suspect`, `questionable`, `poor` | uncertain | invalid_value / rejected |
| `old`, `stale` | uncertain | stale / rejected |
| `bad`, `invalid`, `error`, `fault` | bad | invalid_value / rejected |
| `unknown` or an unrecognized code | unknown | format_invalid / rejected |
| Existing missing/offline/no-data tokens | unknown | missing / rejected |
| Empty text | unknown (supplied but uninformative) | legacy good / eligible if other checks pass |

When only `native_quality` is supplied and there is no adapter report, source
quality is unknown: no protocol meaning is guessed. The legacy absent-report
admission rule still applies. An adapter that recognizes bad or suspect native
quality must continue supplying the corresponding `reported_quality`; the native
field is a preservation field, not an alternate admission channel. The existing
HTTPS provider always retains its previous text conversion in `reported_quality`
and additionally captures the original scalar quality code. Future protocol
adapters must explicitly test their native-code-to-report mapping.

## Durable representation

Migration `006_preserve_telemetry_source_representation` adds only two nullable
columns to each of `telemetry.normalized_observations` and
`telemetry.observation_rejections`:

- `source_representation JSONB`: closed, versioned source-provenance fields.
- `acquired_at_utc TIMESTAMPTZ`: connector read/receipt completion time.

Example source representation (not a replacement telemetry schema):

```json
{
  "contract_version": "neraium.telemetry.source-representation/v1",
  "value": {"type": "decimal", "value": "9007199254740993.000"},
  "native_quality": {"type": "int", "value": "192"},
  "reported_quality": {"type": "str", "value": "good"},
  "quality_state": "good"
}
```

The scalar encoding reuses `telemetry_ingestion._digest_scalar` without modifying
that function or the source-record digest. Integers use decimal strings; Decimal
values retain their decimal spelling/exponent; finite floats use Python hex
representation (including signed zero); booleans remain booleans; strings remain
strings; absent values use `{"type":"null","value":null}`. Nonfinite floats
have explicit textual markers. Invalid unsupported objects retain only their
Python type identifier, never arbitrary object payloads. A datetime value on a
rejected record retains its ISO representation. This preserves the connector's
scalar representation, not original network packet bytes or JSON lexical
whitespace. Float precision already lost during a provider's JSON decode is not
recoverable and is not claimed to be recovered.

PostgreSQL JSONB cannot encode NaN/infinity as numbers. For rejected observations
only, the legacy `original_value` JSON scalar stores a textual marker while the
new typed representation retains the native float type and exact nonfinite
classification. Without that serialization adjustment these source rejections
would fail durable page persistence. Admission remains `invalid_value`; accepted
numerical values are not altered. The PostgreSQL test covers all three markers.

Analytical numbers remain the existing floats. Boolean and nonnumeric operational
states remain rejected numerical inputs, but their typed source values are now
reconstructable in the rejection ledger. Units and original source timestamps
remain in their existing columns with their existing normalization contracts.

Both prepared dataclasses freeze the source representation. The repository
validates its version and closed scalar shape before SQL serialization. Existing
page/record/byte budgets still apply; no throughput claim is introduced.

## Acquisition and persistence time

`acquired_at_utc` is actual connector receipt/read completion. The existing HTTPS
connector samples its injected clock after a complete response has been received
and decoded, before mapping the response records. All observations from that
response share that acquisition instant. Historical retrieval records the time of
retrieval, not the time the source says the measurement occurred. Other providers
that do not capture it leave it absent. Aware offsets normalize to UTC; naive
acquisition times are rejected as connector contract errors.

Original source time and `observed_at_utc` remain unchanged. Prepared ingress time
retains its current behavior; the database's existing `ingested_at_utc DEFAULT
NOW()` remains the durable accepted-row persistence time. Rejections retain
existing first/last-seen persistence times. Acquisition does not substitute for
any of those timestamps and never changes source-time validation.

## Identity and consumer trace

The [certified decision](../validation/validated-candidate-integration-2026/ARCHITECTURAL_DECISION.md)
remains authoritative. Observation UUID allocation, source-record v1 digest,
source-owned connection/ingestion/window identities, behavioral identity and
historical artifacts do not change.

- Raw value and existing reported-quality inputs already participate in the v1
  source digest; preserving their representation does not create a new identity.
- Additional native quality is provenance of the adapter's existing report,
  not a new digest input. V1 deduplication intentionally keeps its historical
  interpretation. A changed native code alone cannot create a second identity if
  the existing source digest/provider-event uniqueness contract says it is the
  same record.
- Acquisition time is operational provenance, never source/semantic identity or
  analytical chronology. Worker/retry timing never enters source representation.
- Source-owned runs/windows are not reclassified as execution metadata.
- No new fields are added to analytical lineage, governed output or result
  artifacts, so persisting these fields cannot change their semantic projection.

Affected producer/consumer trace:

1. Existing HTTPS response -> existing raw envelope (native code and acquisition).
2. `prepare_connector_page` -> both prepared dataclasses (typed provenance).
3. Existing scheduler dataclass projection -> repository writer; no new queue,
   UUID allocator, or scheduler identity is introduced.
4. `persist_ingestion_page` -> both ledgers in the existing page/checkpoint
   transaction, including database-conflict duplicate rejections.
5. Scoped `list_observations` / `list_ingestion_errors` expose provenance to
   internal readers. Observation listing also exposes the existing durable
   ingress timestamp for comparison.
6. `list_analysis_eligible_observations`, persisted result-lineage joins,
   `ObservationLineage`, analytical-window construction and immutable replay
   remain on their existing enumerated fields. The source additions are excluded.
7. Customer error projection (`TelemetryBackfillService.public_error`) remains
   enumerated and does not expose this internal source representation.

Accepted conflicts do not overwrite admitted observations. Rejection upserts
retain the first non-null source representation and first non-null acquisition
capture, while existing counters and first/last-seen behavior continue unchanged.
Those are first captured provenance values, not a history of all acquisition
attempts. An actual new receipt may fill previously absent provenance during the
normal rejection-upsert path; the migration itself never populates historical
rows or invents earlier capture times.

## Migration and security

The forward-only migration requires migration 005, uses the existing ledger and
advisory-lock pattern, and is idempotent. No default, backfill, data rewrite or
identity migration occurs. Existing rows have SQL nulls for never-captured facts.
Old writers can omit both columns. New runtime readiness requires migration 006
before the updated writer runs. Apply it through the existing migration `apply`
interface before deploying the updated runtime; startup does not run migrations.
Downgrade refuses destructive provenance removal.

Workspace/facility authorization, scoped joins and secret bindings are unchanged.
The new payload has no arbitrary metadata/configuration fields and is excluded
from dataclass representations and customer error exports. Adapters must still
never place secrets inside scalar telemetry values; a closed shape is not a
secret detector. Credential-shaped mappings cannot be supplied as native quality.
No write/control operation, source remediation or adapter driver was added.

## Baseline failure determination

The six upload identity/replay tests omitted Origin on production cookie-authenticated
mutations. `HttpBoundaryMiddleware._unsafe_cookie_origin` correctly rejects them.
The shared login helper now sets the already-authorized
`Origin: https://app.neraium.com` for subsequent requests. The security policy is
unchanged. The intended workspace/system/replay assertions remain intact.

The Measurable Consequence expected fixture omitted the marker required by the
certified `execution-metadata.v1` envelope. Only that expected fixture was updated.
Production consequence, output semantics and comparison logic are unchanged.
Both repaired modules passed: **35 tests**.

The focused scheduler gate exposed one further stale test: its lifecycle assertion
read `telemetry_worker_started` from public `/api/health`. The committed liveness
contract and health tests intentionally expose only `status` and `service`.
The test now checks that public shape, the same internal startup flag, and the
fake scheduler's running state. Its start/stop and API-versus-worker assertions
remain. This test-only correction makes the relevant lifecycle gate usable; no
health endpoint or security behavior was changed.

## Verification

Focused tests cover source-quality compatibility, typed values and native codes,
acquisition/source/ingress separation, absent captures, unchanged digests and
lineage, duplicate replay, read-only optional operations, trusted-origin fixtures,
and the additive migration. A dedicated PostgreSQL integration test runs actual
repository writes/reads, verifies old rows remain unchanged with null additions,
applies the migration twice, checks accepted/rejected source reconstruction and
conflict retries, and proves analytical SQL projections exclude the additions.
It requires `NERAIUM_TEST_SOURCE_POSTGRES_DSN` pointing to an empty disposable
database and is invoked with `-m integration`; it refuses an existing telemetry
schema. No application database migration or performance workload was run.

Completed verification:

- Repaired baseline modules: **35 passed** (upload system identity/replay and
  Measurable Consequence).
- Connector/preparation checks including the new tests: **82 passed** (ingestion,
  SDK contract and HTTPS acquisition). The later native-only-quality case also
  passed in the regression selection below.
- Focused regression selection: initially **151 passed, 1 stale scheduler test
  failed, 2 database checks skipped**. The corrected scheduler test and public
  liveness contract both passed in a two-test follow-up. Both skipped migration
  checks then passed against the isolated PostgreSQL database. Thus every case
  in that 154-case selection has a passing final result; the selection was not
  rerun wholesale after the test-only correction.
- The 154-case selection covers `test_telemetry_ingestion`,
  `test_telemetry_ingestion_repository`, `test_telemetry_scheduler`,
  `test_telemetry_lineage`, `test_telemetry_migrations`,
  `test_telemetry_canonical_result_persistence`, `test_governed_output_determinism`,
  `test_authority_identity`, and `test_telemetry_backfill`.
- New real PostgreSQL migration/source round-trip test: **1 passed**. An initial
  test-seeding tuple/SQL-array mismatch was corrected to a list; production SQL
  was not changed for that fixture issue.
- After adding rejected nonfinite scalar serialization, the PostgreSQL test
  passed again with NaN and both infinities, and all **35 repository tests** passed.
- Reviewed tracked and new-file diffs; `git diff --check`, new-file whitespace
  checks and compilation of changed production Python modules passed.

No outstanding test failures remain in these focused checks. No broad suite,
performance workload, commit, push or application deployment was performed.

## Implemented files and next action

Production changes are limited to `connectors/base.py`, `connectors/https_telemetry.py`,
`services/telemetry_domain.py`, `services/telemetry_ingestion.py`,
`services/telemetry_repository.py`, `services/telemetry_runtime.py` under
`backend/app`, plus `backend/db/migrations/preserve_telemetry_source_representation.py`.
The corresponding focused tests and the three stale test fixtures described above
were updated; `tests/test_telemetry_source_persistence.py` supplies the real database
check. This decision record is new; Phase 1 is preserved.

No architectural conflict remains for these representation gaps. Review and apply
migration 006 before deploying the updated runtime. Protocol adapters, subscription
transport and additional capability families remain separate future work.

## Candidate blocker corrections (2026-09-24)

The first Phase 2 candidate did **not** pass review. Its failed decision and
reproductions remain in [the candidate record](connector-foundation-phase2-candidate.md).
The correction addendum there records the subsequent scoped verification.

The HTTPS adapter already stringifies source quality for legacy admission and
source-record/v1. Phase 2's scalar-only native field inadvertently rejected
structured inputs before that unchanged policy could run. The envelope now also
accepts bounded JSON lists/objects as native quality; credential-shaped fields
remain forbidden. In prepared provenance only, these encode as
`{"type":"json","value":"<JSON text>"}` and source quality is always `unknown`.
For example, `[]`, `{}`, and `["good"]` retain legacy good admission without
claiming GOOD source quality. `["bad"]` remains rejected under legacy admission
while its uninterpreted source quality is unknown. Missing/null quality retains
absent provenance and legacy admission. The adapter report, source digest,
observation UUID allocation and analytical numerical value are unchanged.

The JSON text retains the parsed source structure, not original network bytes or
JSON number spelling. It is supported only for native quality, not as an alternate
analytical value. Native/source quality remains reconstruction provenance, not a
new eligibility or identity authority.

006 previously verified only ledger membership and nullable column types. It now
also rejects defaults/generated columns that could invent provenance and requires
a validated CHECK on each ledger matching PostgreSQL's canonical deparse of the
actual object/version/null-safe expression. Constraint names, input whitespace,
redundant parentheses and explicit text casts are not authoritative; PostgreSQL
normalizes them. Missing, weakened, wrong-version, NULL-bypass and NOT VALID checks
fail closed. This is verification only: DDL, migration order, additive NULL behavior
and forward-only policy remain unchanged. No historical evidence is rewritten or
backfilled. PostgreSQL 16 was tested; a materially different server deparse or an
unrecognized logically equivalent predicate fails closed and requires review.

Focused correction verification: 103 connector/ingestion tests, 32 disposable
PostgreSQL tests and 110 existing contract regressions passed (245 total). All 14
HEAD/candidate admission probes now match admission, eligibility, numerical value
and source digest; the original four structured regressions are resolved. No
application database was migrated; no adapter, security policy or analytical
semantics were changed.
