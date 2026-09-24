# Connector Foundation Phase 2 candidate review

Date: 2026-09-24. Branch: `fix/deterministic-governed-output`.
Baseline HEAD: `d79cdb6222203e9313b6b4fc9a294a38d5f7c976`.

Decision: **CONNECTOR_FOUNDATION_BLOCKED_ANALYTICAL_CHANGE**.

This is a review-only record. Production/test candidate files were not changed. The Phase 1 stop record is preserved; this review qualifies Phase 2's implementation readiness claims. Two defects prevent commit readiness.

## Findings

### F1 — P2: native-quality capture changes analytical admission

`backend/app/connectors/https_telemetry.py:890` forwards original JSON quality into the new scalar-only envelope field. The old producer stringified it as reported quality. Inputs with quality `[]`, `{}`, or `["good"]` previously reached the existing admission policy and were admitted as good; now they raise `payload_observation_invalid` before that policy runs. The fetch path quarantines the observation. Optional provenance capture therefore removes previously eligible analytical input.

A differential probe loaded HEAD's ingestion module and `_observation` function and compared them with the candidate using the same existing test mapping and raw record: tag `AHU-1.SAT`, source time `2026-08-25T07:00:00-04:00`, value 77.0, unit degF. For each of the three quality shapes above HEAD accepts one good observation with normalized value 25.0, while the candidate raises the connector error. Nine other cases (absent, empty string, GOOD, UNCERTAIN, SUSPECT, BAD, INVALID, UNKNOWN, numeric zero) preserve admission counts/states, digests and values.

Required correction: preserve the existing reported-quality/admission path when optional native capture cannot represent a source shape. Add differential regression coverage. Do not change the analytical policy to resolve this. No fix was made during review.

### F2 — P2: migration verification accepts missing constraints

`backend/db/migrations/preserve_telemetry_source_representation.py:62` checks ledger membership, nullable columns and types, but not the new CHECK constraints. In disposable PostgreSQL, dropping both `*_source_representation_check` constraints inside a transaction still allowed `verify()` to succeed. A subsequent update to `source_representation='{}'::jsonb` was accepted despite its missing version. The transaction was rolled back.

`ADD COLUMN IF NOT EXISTS` also skips the inline constraint if that column already exists. Startup trusts this verifier, so it can report readiness for an incomplete schema. Required correction: verify required constraints and fail closed for incomplete/pre-existing schema states, with negative tests. No fix was made during review.

## Production hunk review

All production changes have Phase 2 purposes; none establishes another canonical ingestion authority. Supporting imports/exports belong to the corresponding changes below.

| Production hunk | Purpose and effect | Disposition |
| --- | --- | --- |
| connectors/base.py: native quality/acquisition fields and validation | Optional scalar provenance and aware UTC acquisition; no numerical or identity replacement. | Required; HTTPS producer coupling causes F1. |
| connectors/base.py: optional discovery/acquisition methods | Safe nonretryable unsupported-operation failures replace mandatory fake implementations. | Retain; no write interface. |
| connectors/https_telemetry.py: receipt clock/signature/emission | Samples acquisition after response receipt/decoding, shared by that response's records. | Retain. |
| connectors/https_telemetry.py: native quality emission | Preserves original scalar quality separately from legacy string; structured input now fails. | Correct F1. |
| services/telemetry_domain.py: SourceQualityState | Descriptive source vocabulary separate from analytical admission vocabulary. | Retain. |
| services/telemetry_ingestion.py: version/quality mapper/typed payload/validator/freezing | Closed provenance payload reuses existing scalar encoder; no new analytical value or digest authority. | Retain. |
| services/telemetry_ingestion.py: prepared fields and accepted/rejected construction | Propagates nullable provenance/acquisition through both ledgers. | Retain. |
| services/telemetry_repository.py: provenance helper and INSERT columns | Validates/persists JSONB and aware acquisition timestamp; old callers remain nullable. | Retain. |
| services/telemetry_repository.py: rejected nonfinite original-value conversion | JSON-compatible text for rejected NaN/infinities; typed provenance preserves classification. | Retain; no accepted arithmetic change. |
| services/telemetry_repository.py: duplicate rejection/conflict update | Copies source details; retains first nonnull provenance/acquisition independently. | Retain; no UUID/digest change. |
| services/telemetry_repository.py: internal read projections | Exposes reconstruction fields internally; analytical eligible SELECT excludes additions. | Retain. |
| services/telemetry_runtime.py: readiness call | Requires 006 without applying it at startup. | Retain after F2 correction. |
| migration 006: DDL/prerequisite/ledger/verify/downgrade | Nullable reconstruction columns after 005, no backfill, explicit downgrade refusal. | Required; correct F2. |

Except for F1, these changes add provenance or safe optional SDK behavior without changing analytical input. No hunk changes semantic/source/behavioral identity, observation UUID allocation, source-record digest version, mathematical processing, canonical result format or historical interpretation. New provenance is additive; replay keeps its existing analytical projection. F1 prevents end-to-end compatibility certification despite unchanged engine code.

## Quality / admission contract

| Report | Source quality | Existing admission for otherwise valid data |
| --- | --- | --- |
| Absent, no native code | NULL | Good/eligible |
| GOOD / existing good aliases | good | Good/eligible |
| UNCERTAIN / SUSPECT | uncertain | Rejected under existing policy |
| BAD / INVALID | bad | Rejected under existing policy |
| UNKNOWN / unrecognized text | unknown | Rejected under existing policy |
| Empty string | unknown | Legacy good admission retained |
| Native code only, report absent | unknown | Missing-report admission retained; no guessed native meaning |

Native quality is retained separately on accepted and rejected observations. Future adapters must map known native meanings explicitly; persisting native codes is not an implicit admission rule. The admission helper is unchanged; F1 is an upstream compatibility defect.

## Source representation and clocks

Typed source provenance preserves supported Python scalars: integer text, Decimal text, finite float hexadecimal value, booleans, strings, null and timestamp text. Nonfinite floats retain classification. Original units and source timestamp text remain in existing fields. Existing explicit unit conversion and float-based analytical values are unchanged.

This does not preserve original network bytes/JSON lexical spelling, arbitrary objects, or NaN payload bits. Unsupported values retain a type marker, not full contents. Shape validation is not a general decoder proving every typed string is lexically valid. Do not describe analytical arithmetic or all source representations as lossless.

Source time belongs to the originating observation. Acquisition is connector response receipt/read completion when known, nullable otherwise, never fabricated from source time. Ingress remains existing ingestion/persistence time. Worker/retry/session clocks remain execution metadata. No clock substitutes for another.

## Identity / provenance and projection trace

Connector envelope → prepared observation/rejection → repository ledgers → internal reconstruction projections. Analytical eligible SELECT and `ObservationLineage.from_observation` enumerate pre-existing fields and exclude the additions. Analytical windows, result artifacts and canonical replay retain their existing contracts.

New source representation and acquisition time are observational provenance, not direct source/semantic/behavioral identity inputs and not execution-metadata envelope fields. Underlying raw value/reported quality already participate in source-record/v1; adding typed copies does not change its digest. Existing source-owned connection/run/window bindings remain authoritative under the validated-candidate architectural identity decision. Observation UUID allocation is unchanged. Rejection conflict handling retains first-known provenance/acquisition rather than every retry clock.

Closed provenance shape excludes configuration/credential containers. It does not detect secrets embedded in arbitrary scalar strings; adapters must still exclude credentials. Workspace/site authorization and safe customer error projection are unchanged.

## Migration / historical compatibility

006 follows 005 using the existing ledger and advisory lock. Both accepted/rejected ledgers receive nullable JSONB and TIMESTAMPTZ fields, without defaults, historical UPDATEs or fabricated backfill. Fresh constraints enforce object/version. Historical rows retain NULL additions. Apply-twice and PostgreSQL round trips passed. Downgrade explicitly refuses; recovery is forward-only and must preserve evidence. Runtime verifies rather than applies. F2 means readiness verification is incomplete.

Only a new disposable PostgreSQL 16 container/database was used. No application, staging or production database was migrated.

## SDK / read-only status

Existing capability enumeration remains authoritative and read-only. Unsupported discovery/incremental/backfill operations fail safely instead of requiring fake methods. Validation, health and descriptors remain mandatory. No protocol assumptions, adapter implementation, write/control/setpoint/actuation interfaces were added. Neraium remains outside the control path; human review remains authoritative.

## Test-only corrections

- Upload login fixture supplies trusted Origin `https://app.neraium.com`, required by HEAD's existing unsafe-cookie request-origin middleware. Identity/replay/authorization assertions remain intact; security policy is unchanged.
- Measurable Consequence expected execution metadata includes `contract_version: execution-metadata.v1`, already emitted by HEAD's authoritative runtime metadata contract. Production semantics and equality assertion remain intact.
- Scheduler test expects HEAD's public health shape (`status`, `service`) and checks startup/running state internally. Existing startup/shutdown/role assertions remain. No production health behavior changed.
- New scalar ingestion/connector/persistence tests are relevant but omit F1's structured-quality compatibility cases. Migration tests cover prerequisites, readiness, downgrade refusal and positive integration but omit F2's missing constraints.

## Focused verification

Ran repository `.venv/bin/python -m pytest -q` on these selected modules:

```
tests/test_telemetry_ingestion.py
tests/test_telemetry_ingestion_repository.py
tests/test_https_telemetry_connector.py
tests/test_telemetry_connector_contract.py
tests/test_telemetry_migrations.py
tests/test_telemetry_scheduler.py
tests/test_phase4_upload_system_identity.py
tests/test_measurable_consequence.py
tests/test_telemetry_lineage.py
tests/test_authority_identity.py
tests/test_telemetry_analysis_handoff.py
tests/test_telemetry_canonical_result_persistence.py
tests/test_governed_output_determinism.py
tests/test_aletheia_retirement.py
```

Result: 232 passed, 2 skipped (explicit PostgreSQL DSN checks), 2 warnings. Both skipped checks were subsequently executed against disposable PostgreSQL: 2 passed. `tests/test_telemetry_source_persistence.py -m integration` with its disposable DSN: 1 passed. Total: **235 passing tests**, none of the selected checks left unexecuted.

Additional probes: 12-case baseline admission differential (9 equivalent, 3 regressions: F1); negative PostgreSQL missing-constraint readiness probe (false success and invalid representation accepted: F2). Passing existing tests do not negate these findings.

HEAD/candidate AST comparison confirmed unchanged `_digest_scalar`, `stable_source_record_digest`, `_reported_quality_decision`, scheduler `_observation_record` and `_rejection_record`. Byte comparison confirmed unchanged analytical window, lineage, result artifact, authority identity, units, timestamps, output semantics and Measurable Consequence modules. No protected analytical code changed. No broad suite or performance workload was run.

Supporting local outputs: `/tmp/neraium-connector-phase2-review.4J5Px1/` (`focused.xml`, `postgres.xml`, `extra-postgres.xml`, `admission-probe.json`, `migration-probe.json`, `freeze-probe.json`). These temporary artifacts are not proposed commit contents.

## Reviewed inventory and hashes

Classification denotes purpose, not approval of defective hunks. All 13 tracked changed files and four supplied untracked architecture/implementation files are listed below. Phase 1 is prior-phase context. The 9,410 unrelated untracked file paths in the starting manifest were excluded. No unexplained production change was found.

| Path | Classification | SHA-256 |
| --- | --- | --- |
| `backend/app/connectors/base.py` | REQUIRED_PRODUCTION_CHANGE | `fa5a201fa89a455f99169478593ab7a559499cfb9515460c32417c346cc0f298` |
| `backend/app/connectors/https_telemetry.py` | REQUIRED_PRODUCTION_CHANGE | `06a3c8d922236db945e07c2bb55910f9fae1ab5ccde1ee7fe5197069ca7200ee` |
| `backend/app/services/telemetry_domain.py` | REQUIRED_PRODUCTION_CHANGE | `97f72ccfc0b048ebeff38c4d66a40d57a24414bcdd6770cb56adb4676acddb9b` |
| `backend/app/services/telemetry_ingestion.py` | REQUIRED_PRODUCTION_CHANGE | `e282326f24bd6e760ae48fcae0eb58cb397bb7da5d95da27e16d57638fcbb4b5` |
| `backend/app/services/telemetry_repository.py` | REQUIRED_PRODUCTION_CHANGE | `29b51786c552291ada41464bed3d4e028d5489b4619162b407ceda080814811a` |
| `backend/app/services/telemetry_runtime.py` | REQUIRED_PRODUCTION_CHANGE | `e0c71f3c6b7dbb33a2159003be9a856e5aa241575636c683b320438b16949933` |
| `tests/test_https_telemetry_connector.py` | REQUIRED_TEST | `bbba18a4cd3d5e05fd403b0556332c7f4902ff659bd1276fbc1203664dd3154c` |
| `tests/test_measurable_consequence.py` | REQUIRED_TEST | `d6ca13721ecc177f901530ed18aa5d4b5b1c4a3f9692081c77f1aeb317f0b150` |
| `tests/test_phase4_upload_system_identity.py` | REQUIRED_TEST | `5997920b7ce3bff0c8a5421463c6706af39bab6cc6313fccc543147d55c8fd98` |
| `tests/test_telemetry_connector_contract.py` | REQUIRED_TEST | `92890862d57a1f31dc60af1c54ea43ed2881ffef75a23b52f8e265ed20a944ef` |
| `tests/test_telemetry_ingestion.py` | REQUIRED_TEST | `cf52f2caffd93fc24c83b1909c2e9f71f7bf6d6ded0468bf642c2806a1f63c2a` |
| `tests/test_telemetry_migrations.py` | REQUIRED_TEST | `d62fbf64ab43054a90accbdc124606e5ef3c5b3bc683e86fcf96b994fe0f4ad4` |
| `tests/test_telemetry_scheduler.py` | REQUIRED_TEST | `fa52acf27a7f2cfe82d8638e49df74d12291824df3ab4fe8e64525240664580a` |
| `backend/db/migrations/preserve_telemetry_source_representation.py` | REQUIRED_MIGRATION | `dea39b44c956221a697b47466c3e02e4dde39e6e7c2d8da7575cd901e7d054c8` |
| `tests/test_telemetry_source_persistence.py` | REQUIRED_TEST | `d634aa84762fcde2839cec7c8cc3c47068dbb653a163d47b0a5c78d90c6e5b0d` |
| `docs/architecture/connector-foundation-phase1.md` | ARCHITECTURE_DOCUMENTATION | `ea89302cb50d50d36e664790bf3e04365d15cf37be9abd4884d272e027ea5dc0` |
| `docs/architecture/connector-foundation-phase2.md` | ARCHITECTURE_DOCUMENTATION | `34637c2530c72624b3be0f0715cb6504b6327761cd1b4f8b7bd462dcc899990c` |

This candidate record is the sole review addition, classified ARCHITECTURE_DOCUMENTATION. Its own hash is excluded to avoid a self-referential manifest. All 17 supplied candidate files match their starting hashes.

## Commit readiness / next action

No commit set is approved. The inventory is exact review scope, not a staging instruction. Proposed message reserved for a corrected, approved candidate: `feat: establish connector ingestion foundation`.

Correct F1 and F2 in a subsequent implementation task, add the missing focused regressions, then re-review the new hashes. Do not start adapters or deploy migration 006 as part of this review. No staging, commit or push occurred.

Final review checks: `git diff --check` and added-record whitespace check were clean; index remained empty. The disposable PostgreSQL container and its anonymous volume were removed after verification. No application database was accessed.

---

## Correction addendum — 2026-09-24

The decision above is the **historical failed candidate**, not a claim that it
passed initially. This addendum reviews only the authorized corrections to F1/F2
and their directly affected Phase 2 code/tests/documentation.

Current narrow review decision: **CONNECTOR_FOUNDATION_READY_FOR_COMMIT**.
Baseline HEAD remains `d79cdb6222203e9313b6b4fc9a294a38d5f7c976`, branch
`fix/deterministic-governed-output`. The index was empty; the existing Phase 2
worktree was preserved as the starting candidate. No unrelated artifact was used.

### Reproduction before editing

Both findings were reproduced before production edits. HEAD's adapter function
and ingestion module were evaluated with the same configured source and mapping
as the starting candidate. Four structured cases failed (including the additional
`{"good":""}` case); ten other cases matched. Adapter reports, prepared source
provenance, admission state, accepted/rejected counts, eligibility and source
record digest were recorded for each case. HEAD has no Phase 2 provenance payload;
the starting candidate fails before preparation for the four structured cases.

Disposable PostgreSQL was initialized with the existing migrations and tested
before edits: pristine state verified; missing columns, wrong types and wrong
nullability failed; missing/weakened/unvalidated source CHECKs and a default on
acquisition incorrectly verified. Every corruption was rolled back.

### F1 correction and separation of authorities

The native envelope field now accepts JSON lists/objects within the existing
reported/native length bound, alongside existing scalar types. Credential-shaped
keys remain rejected recursively. The prepared source payload stores structured
native quality as a JSON text value with a `json` type marker, accepted only in
`native_quality`. Its descriptive source quality is UNKNOWN regardless of legacy
admission. The JSON validator preserves the closed shape and credential boundary.

No HTTPS report conversion, `_reported_quality_decision`, source-record digest,
observation allocation or analytical numerical conversion was changed. Structured
values are not interpreted as protocol status; legacy admission continues to use
the original string report. The added provenance is neither source identity nor
semantic/behavioral identity. Acquisition and runtime metadata remain excluded
from the existing source-record projection.

### Repeated admission probe

The corrected candidate matches HEAD for all 14 cases below. All other mapping,
source time, value and unit checks use the same valid input (77 degF → 25.0).
The two JSON collections and two additional legacy-good structures previously
failed at the envelope. No other input changed its analytical decision.

| Source input | Adapter report | Corrected native provenance / source quality | Admission / eligible | Digest vs HEAD |
| --- | --- | --- | --- | --- |
| `null` | `None` | `{"type":"null","value":null}` / `None` | `good` / `True` | unchanged |
| `""` | `` | `{"type":"str","value":""}` / `unknown` | `good` / `True` | unchanged |
| `"GOOD"` | `GOOD` | `{"type":"str","value":"GOOD"}` / `good` | `good` / `True` | unchanged |
| `"UNCERTAIN"` | `UNCERTAIN` | `{"type":"str","value":"UNCERTAIN"}` / `uncertain` | `invalid_value` / `False` | unchanged |
| `"SUSPECT"` | `SUSPECT` | `{"type":"str","value":"SUSPECT"}` / `uncertain` | `invalid_value` / `False` | unchanged |
| `"BAD"` | `BAD` | `{"type":"str","value":"BAD"}` / `bad` | `invalid_value` / `False` | unchanged |
| `"INVALID"` | `INVALID` | `{"type":"str","value":"INVALID"}` / `bad` | `invalid_value` / `False` | unchanged |
| `"UNKNOWN"` | `UNKNOWN` | `{"type":"str","value":"UNKNOWN"}` / `unknown` | `format_invalid` / `False` | unchanged |
| `0` | `0` | `{"type":"int","value":"0"}` / `good` | `good` / `True` | unchanged |
| `[]` | `[]` | `{"type":"json","value":"[]"}` / `unknown` | `good` / `True` | unchanged |
| `{}` | `{}` | `{"type":"json","value":"{}"}` / `unknown` | `good` / `True` | unchanged |
| `["good"]` | `['good']` | `{"type":"json","value":"[\"good\"]"}` / `unknown` | `good` / `True` | unchanged |
| `{"good": ""}` | `{'good': ''}` | `{"type":"json","value":"{\"good\":\"\"}"}` / `unknown` | `good` / `True` | unchanged |
| `missing` | `None` | `{"type":"null","value":null}` / `None` | `good` / `True` | unchanged |

The focused tests additionally cover structured `['bad']` and `{'status':'bad'}`:
source quality remains unknown while legacy admission rejects them. Acquisition
and worker metadata variations leave source identity unchanged. Accepted and
rejected structured provenance was round-tripped through PostgreSQL.

### F2 correction and repeated incomplete-state probes

Verification now checks each column's PostgreSQL type, nullability, absence of a
default and absence of a generated expression. It locates CHECK constraints via
catalog relation identity, without assuming generated names, and requires a
validated canonical parsed/deparsed expression enforcing the actual DDL's
nullable-object/version contract. The `IS TRUE` guard matters: without it a
missing version can satisfy PostgreSQL CHECK through SQL NULL.

The verifier does not run supplied expressions against production observations,
create test tables at startup, alter schema, or repair rows. DDL/apply/ordering/
downgrade policy are unchanged. A pre-existing column skipped by IF NOT EXISTS
cannot certify without the required constraint. Canonically equivalent formatting,
quoted identifiers, extra parentheses, explicit text casts and renamed constraints
were tested and pass. Unrecognized expression rewrites fail closed rather than
being assumed equivalent.

| State, tested on both ledgers | Starting verifier | Corrected verifier |
| --- | --- | --- |
| Pristine | Pass | Pass |
| Missing source column | Fail | Fail |
| Missing acquisition column | Fail | Fail |
| Wrong source type | Fail | Fail |
| Wrong acquisition type | Fail | Fail |
| Source NOT NULL | Fail | Fail |
| Acquisition NOT NULL | Fail | Fail |
| Missing source CHECK | Incorrect pass | Fail |
| Object-only weakened CHECK | Incorrect pass | Fail |
| NOT VALID CHECK | Incorrect pass | Fail |
| Acquisition default | Incorrect pass | Fail |

Additional focused tests establish failure for absent ledger entry, source default,
generated acquisition, wrong-version CHECK, missing NULL guard and pre-existing
unconstrained columns. The original missing-constraint probe and all original
corruption cases were repeated after correction and behaved as required.

### Exact focused verification

1. `.venv/bin/python -m pytest -q tests/test_telemetry_quality_compatibility.py tests/test_telemetry_ingestion.py tests/test_https_telemetry_connector.py tests/test_telemetry_connector_contract.py`: **103 passed**, 2 warnings.
2. With explicit disposable PostgreSQL DSNs, `.venv/bin/python -m pytest -q tests/test_telemetry_source_migration.py tests/test_telemetry_source_persistence.py -m integration`: **32 passed**, 2 warnings. Databases initially had no telemetry schema; historical NULL behavior, both ledgers, duplicate replay and structured provenance round trips passed.
3. With the explicit disposable PostgreSQL DSN, `.venv/bin/python -m pytest -q tests/test_telemetry_ingestion_repository.py tests/test_telemetry_migrations.py tests/test_telemetry_lineage.py tests/test_authority_identity.py tests/test_telemetry_analysis_handoff.py tests/test_telemetry_canonical_result_persistence.py tests/test_governed_output_determinism.py tests/test_measurable_consequence.py tests/test_aletheia_retirement.py`: **110 passed**, 2 warnings.

Total: **245 passing focused tests**, no skips/failures. No full suite, large-data
campaign or performance workload ran. Before/after probe outputs and JUnit files
are local supporting evidence in `/tmp/neraium-phase2-blocker-fix/`, outside the
proposed commit set. The admission script compares committed HEAD with the saved
starting-candidate code or corrected candidate, excluding additive provenance
from its compatibility equality assertion.

AST comparisons with HEAD confirmed unchanged scalar digest encoder, source-record
digest, admission policy, and scheduler accepted/rejected record allocation.
Eight protected analytical/identity/lineage/result/units/timestamp/output modules
also match HEAD byte-for-byte. No request-origin, authentication, scope, safe-error,
read-only or credential policy was weakened.

### Narrow change disposition and limitations

| Changed during correction | Purpose |
| --- | --- |
| backend/app/connectors/base.py | Permit bounded structured native quality without the admission regression; retain credential rejection. |
| backend/app/services/telemetry_ingestion.py | Persist uninterpreted structured quality and mark its source meaning unknown, independently of admission. |
| backend/db/migrations/preserve_telemetry_source_representation.py | Fail closed for incomplete column/constraint contracts. |
| tests/test_telemetry_quality_compatibility.py | Fixed HEAD admission outcomes, separate provenance assertions, identity and validation regressions. |
| tests/test_telemetry_source_migration.py | Fresh/corrupted PostgreSQL schema, canonical constraint equivalence and missing-ledger coverage. |
| tests/test_telemetry_source_persistence.py | Accepted/rejected structured quality durable round trips. |
| docs/architecture/connector-foundation-phase2.md | Architecture correction addendum. |
| docs/architecture/connector-foundation-phase2-candidate.md | Preserve failed review and record this correction review. |

No other starting candidate file changed. New tests are REQUIRED_TEST; the three
production/migration edits correct only F1/F2; documentation records both review
outcomes. The rest of the Phase 2 foundation was not redesigned.

Limitations: JSON provenance retains parsed structures, not original wire bytes;
analytical arithmetic remains float-based. Credential-shaped structures remain
prohibited. PostgreSQL 16 canonical deparse was verified; an unrecognized logical
rewrite or different server rendering fails closed and requires review. The
verifier is not a general SQL theorem prover. The existing forward-only migration
policy remains; no application migration or adapter development is authorized.

### Updated candidate hashes and proposed scope

The hashes below supersede the initial failed-candidate hashes for the corrected
snapshot. The exact proposed implementation/documentation set is the original
review inventory plus the two new regression modules and this candidate record.
Unrelated untracked artifacts remain excluded. The candidate record's own hash is
excluded to avoid self-reference. Proposed message:
`feat: establish connector ingestion foundation`.

| Candidate file | SHA-256 |
| --- | --- |
| `backend/app/connectors/base.py` | `a46cb91b54fffd1e186797e5d2244f2e846bd738d86889615734a08dfd4efc67` |
| `backend/app/connectors/https_telemetry.py` | `06a3c8d922236db945e07c2bb55910f9fae1ab5ccde1ee7fe5197069ca7200ee` |
| `backend/app/services/telemetry_domain.py` | `97f72ccfc0b048ebeff38c4d66a40d57a24414bcdd6770cb56adb4676acddb9b` |
| `backend/app/services/telemetry_ingestion.py` | `699da660a5e0c8b2cf5f9da2f1f196a8e083b3b4b11b9c9bc95b60293d342abc` |
| `backend/app/services/telemetry_repository.py` | `29b51786c552291ada41464bed3d4e028d5489b4619162b407ceda080814811a` |
| `backend/app/services/telemetry_runtime.py` | `e0c71f3c6b7dbb33a2159003be9a856e5aa241575636c683b320438b16949933` |
| `tests/test_https_telemetry_connector.py` | `bbba18a4cd3d5e05fd403b0556332c7f4902ff659bd1276fbc1203664dd3154c` |
| `tests/test_measurable_consequence.py` | `d6ca13721ecc177f901530ed18aa5d4b5b1c4a3f9692081c77f1aeb317f0b150` |
| `tests/test_phase4_upload_system_identity.py` | `5997920b7ce3bff0c8a5421463c6706af39bab6cc6313fccc543147d55c8fd98` |
| `tests/test_telemetry_connector_contract.py` | `92890862d57a1f31dc60af1c54ea43ed2881ffef75a23b52f8e265ed20a944ef` |
| `tests/test_telemetry_ingestion.py` | `cf52f2caffd93fc24c83b1909c2e9f71f7bf6d6ded0468bf642c2806a1f63c2a` |
| `tests/test_telemetry_migrations.py` | `d62fbf64ab43054a90accbdc124606e5ef3c5b3bc683e86fcf96b994fe0f4ad4` |
| `tests/test_telemetry_scheduler.py` | `fa52acf27a7f2cfe82d8638e49df74d12291824df3ab4fe8e64525240664580a` |
| `backend/db/migrations/preserve_telemetry_source_representation.py` | `5a93d36dd354dc61e309a182b41273ff7e5bd2b88795066fe680c1c64488a621` |
| `tests/test_telemetry_source_persistence.py` | `88860135d13df3beb6cefe2d2c7899df4b0848ae9851d4fef0cdcf47291a5171` |
| `docs/architecture/connector-foundation-phase1.md` | `ea89302cb50d50d36e664790bf3e04365d15cf37be9abd4884d272e027ea5dc0` |
| `docs/architecture/connector-foundation-phase2.md` | `dac2ed78d0fe80ecb7e0e93b18f9d0e250d230e83eea8b801da745c50beeaad8` |
| `tests/test_telemetry_quality_compatibility.py` | `9e7225557d1e0ed68b1a9053a94ac001c66dfc51df7fdcc35d71c8cf2cc48ce7` |
| `tests/test_telemetry_source_migration.py` | `d0cf198c8f90cbb026134ecb56daab3dcb9679e511840946c0bbbd2458853ba3` |

Final narrow review: `git diff --check` and whitespace checks for added files
passed. Start/end hashes confirmed only the six existing files listed in the
correction disposition changed, plus the two new regression modules. The index
remained empty. The disposable PostgreSQL container and its anonymous volume were
removed after verification. No application database was accessed; no staging,
commit or push occurred. Next action is user review of this corrected candidate;
commit and migration deployment remain separate actions.
