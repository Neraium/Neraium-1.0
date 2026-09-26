# Temporal continuation prerequisite review

Baseline: `a75b7c1ef572b3c926e8fd00db3691d69e84e112` on
`fix/deterministic-governed-output`.

Decision: `TEMPORAL_PREREQUISITES_READY_FOR_IMPLEMENTATION`

This is an independent prerequisite review and implementation plan. No
production code or tests changed. Continuation is not implemented by this
artifact.

## CANONICAL ENDPOINT AUTHORITY

The authorized connector path already has canonical endpoint identity before
relationship analysis:

1. A system authority snapshot resolves approved telemetry mappings. Each
   mapping carries a canonical concept UUID, system, asset, revision and
   authority digest. Connector/external signal names are source locators, not
   the canonical identity.
2. Ingestion stamps accepted observations with `canonical_signal_id` (the
   canonical concept ID), mapping revision and authority digest. The durable
   `ObservationLineage` contract records those values per observation.
3. `build_canonical_analysis_window` selects observations matching the
   server-bound system/asset and authority digest, validates lineage, and pivots
   rows using `canonical_signal_id` as the actual numeric column key. It rejects
   duplicate canonical-signal/timestamp cells and conflicting canonical name or
   unit metadata.
4. Global relationship baselines calculate their existing Pearson edges from
   those canonical-ID columns. The mode-conditioned producer consumes those
   same columns and records the exact selected mode/features. Graph construction
   retains those columns and records its chosen edge basis. The relationship
   evidence finalizer then binds the assessment to result-local source/evidence/
   assessment ownership as before.

Canonical concept IDs are server-owned database identities, not generated from
vendor names. They remain stable when the same concept is mapped from another
connector, provided the authoritative mapping points to the same canonical
concept. They are scoped for use by the relationship lineage through the full
authenticated telemetry scope; the IDs alone do not establish scope or
authorization. A mapping can intentionally map different external names to the
same concept. A single analysis window uses one server-bound authority digest;
missing, stale or conflicting mapping provenance is rejected before analysis.
The exact signal-ID-to-column map can be passed from the already validated
canonical window to lineage finalization. No relationship math or endpoint
ordering needs to change: current Pearson calculations remain symmetric, while
lineage canonicalizes the endpoint-ID pair as unordered and sorted.

This guarantee applies to the canonical telemetry-analysis-window path. Legacy
uploads and direct/internal analysis calls that only have arbitrary column
names lack this authority and must receive `CONTINUATION_UNAVAILABLE`; their
current-run analysis remains unchanged. Do not infer canonical IDs for them.

## ENDPOINT PROPAGATION PATH

The smallest propagation is to make the validated canonical endpoint map
available alongside the existing rows/catalog to the relationship evidence
finalizer. The canonical analysis window already owns `numeric_columns`, keyed
by canonical ID, and observation lineage that proves each ID under the selected
system authority digest. Keep this as internal producer metadata; there is no
need to add IDs to relationship calculations because their `columns` already
contain those canonical IDs on this path.

For generic input paths, the producer may accept an explicit validated mapping
from source column to canonical signal ID. It must require a one-to-one resolved
identity for each analyzed endpoint within the selected authority snapshot.
Missing or ambiguous mappings suppress lineage only, not the edge calculation.

## LINEAGE CONTRACT REVIEW

Keep `relationship_lineage_ref` separate from
`relationship_source_ref`, `relationship_evidence_ref`,
`relationship_assessment_binding`, and temporal state.

Minimum `relationship-lineage.v1` identity:

- authenticated scope ref;
- canonical endpoint IDs, sorted because current Pearson is symmetric;
- relationship semantic contract/version (`linear_correlation.v1`);
- assessment basis;
- lineage contract version.

Mode-conditioned lineage additionally includes the producer-issued mode ID and
the exact canonical selection-feature descriptor. Global lineage has an
explicit global basis with no mode identity. Graph-failure fallback has a
distinct fallback basis and is ineligible to consume or advance successful
state. Do not include current measurements, names, mapping revision, connector
IDs, groups, rank, primary, or runtime IDs in lineage identity. Mapping
authority digest is checked when resolving endpoint IDs for the current run;
it is provenance/compatibility, not the stable relationship identity, so an
approved mapping revision to the same canonical IDs need not fork the lineage.

The scope ref must bind the complete authenticated analysis boundary, not only
the current Phase 4 tenant/workspace digest: include `TelemetryScopeRef` fields
(tenant scope, workspace, resource scope, facility), server-bound `system_id`,
and `asset_id` where analyses are asset-filtered. This is a necessary precision
to prevent same-site/system endpoint reuse across separate asset scopes. A
`result-local` placeholder is never eligible.

## COMPATIBILITY CONTRACT

Before reducer input is admitted, compute/validate a canonical compatibility
descriptor and require exact equality for:

- temporal reducer contract/version and parameters;
- relationship semantic contract and assessment basis;
- lineage ref and exact authenticated scope/system/asset;
- fixed baseline identity: authoritative reference dataset/model identity,
  baseline start/end and baseline correlation value;
- canonical units for both endpoints;
- source/reference semantics used by the reducer;
- global operating-context identity used by the existing reducer; for
  mode-conditioned assessment, exact mode ID and selected feature descriptor.

The current reducer state identity specifically compares canonical `columns`,
`basis`, `baseline_correlation`, `baseline_start`, `baseline_end`, `mode`,
`reference_dataset_id` and `signal_units`. Keep those existing comparisons
intact and bind them in the compatibility descriptor. Reducer version/threshold
changes invalidate prior state rather than silently reinterpreting it. Any
missing or unequal field makes prior state unavailable. Context changes reset
continuation; no context mathematics changes.

## STATE EVENT IDENTITY

Do not use the analysis-window UUID as the sole event identity: its preimage
includes connector/source-run identity and therefore does not identify exact
governed evidence across a replay under another run ID.

Use an event ref derived deterministically from lineage ref, exact
`relationship_source_ref` (which commits to selected observations and
measurement), and canonical governed baseline/current window timestamps. The
source ref contains no process/request/retry IDs. Also enforce a unique
`(lineage_ref, baseline/current window interval)` admission key: if the interval
already exists with the same source ref, treat it as an idempotent replay; if it
exists with a different source ref, reject it as conflicting evidence and do
not count it twice. Event time is the governed window end already consumed by
the reducer. This detects out-of-order intervals without wall-clock metadata.

## EXISTING STORAGE CAPABILITIES

The existing `PostgreSQLTelemetryRepository` is suitable as the authorized
transactional persistence authority for this state:

- every repository operation receives `TelemetryScopeRef`; SQL predicates bind
  resource scope, tenant scope, workspace and facility, with system/asset also
  explicit on analysis records;
- `telemetry.analysis_windows` has a unique scoped window identity and
  claim/status transitions that prevent duplicate execution of one window;
- `telemetry.analysis_result_artifacts` has scoped uniqueness and immutable
  result payload semantics;
- `finish_analysis_window_execution` publishes the canonical artifact and
  terminal analysis-window state in one PostgreSQL transaction, locking and
  validating the claimed window/artifact state;
- repository writes use PostgreSQL transactions, unique constraints and row
  locks. These are sufficient primitives for a single scoped lineage-head row
  with compare-and-swap validation in the same transaction as result
  publication.

Existing facilities do not yet store relationship temporal state, and
per-window claims do not serialize different windows for the same lineage. Do
not use SQLite `latest_payloads`, local files, result scans, or connector
buffers for production continuation. No new persistence system is needed; add
the narrowly scoped state contract to the existing PostgreSQL telemetry
repository/table abstraction.

## PROPOSED STATE REPOSITORY

Add one current-head row per `(resource_scope_id, tenant_scope_id,
workspace_id, facility_id, system_id, asset_id, relationship_lineage_ref)` in
the telemetry schema. Store a bounded versioned JSON state, state digest,
compatibility digest, head event ref/time, and monotonically incremented storage
revision. A unique constraint enforces one logical row/head. The row is not
authorization: every operation must still receive and validate the authenticated
scope and system authority snapshot.

No separate unbounded event table is needed for the reducer's eight-window
horizon. Exact event/interval refs and the bounded observations travel in the
state row. The immutable canonical result artifact retains the exact source and
assessment evidence to audit those references.

## CONCURRENCY / IDEMPOTENCY

Load state and its storage revision before reduction. At completion, one
repository transaction must:

1. validate the current analysis-window execution claim;
2. lock/create the lineage-head row by its full unique scope key;
3. compare the row revision/head event with the expected revision/head loaded
   before reduction;
4. validate compatibility, event/interval uniqueness and timestamp ordering;
5. append the current governed event to the existing reducer state and bound it
   to the reducer's existing maximum history;
6. update the head and publish the canonical result artifact plus completed
   window atomically.

An exact already-admitted event is idempotent and cannot vote twice. A
conflicting same-interval event, revision/head mismatch or older timestamp
must not publish a result whose persistence used a stale/incompatible state and
must not advance the head. The caller may retry the deterministic reduction
against the new head when the event is chronologically admissible; otherwise
the window fails closed without a temporal authority result. Two concurrent
transactions cannot both advance from the same expected head because the row
lock/unique key serializes the compare-and-update.

## AUTHORIZATION

Repository APIs require authenticated `TelemetryScopeRef` and separately
server-bound system/asset authority. The SQL key includes all scope dimensions,
system and asset; row envelope scope must exactly match. Cross-scope lookup is
not exposed as a fallback. Lineage and state digests are unkeyed integrity
identifiers only. Exact result-local source/evidence/assessment resolution
remains required before state consumption and for each newly finalized
assessment.

## HISTORICAL COMPATIBILITY

Records without lineage remain readable. No migration, replay, name-based
reconstruction or state seeding from historical records is permitted. Only
prospective canonical telemetry analyses with complete current lineage can
create or consume state.

## ATTACK REVIEW

1. Same raw names across sites: names are not identity; authenticated scope and
   canonical IDs separate state.
2. Ambiguous canonical endpoint: producer suppresses lineage; analysis proceeds
   without continuation.
3. Reversed directed relationship: current Pearson is symmetric; any future
   directed contract uses ordered endpoints and a new semantic version.
4. Semantic-version crossover: relationship semantic version changes lineage
   and compatibility.
5. Global/mode borrowing: distinct basis and mode identity prevent it.
6. Success/fallback borrowing: fallback cannot load or advance successful
   state.
7. A/B borrowing: distinct canonical endpoint pair and scope-keyed state.
8–10. Ranking/primary/grouping mutations: not part of identity or repository
   key.
11–12. Retry/replay: exact source/window event is idempotent; conflicting
   interval evidence is rejected.
13. Concurrent head advancement: transaction row lock and expected revision
   allow at most one writer; stale result publication is rolled back.
14. Out-of-order analysis: governed interval ordering rejects it; it cannot
   replace the newer head.
15. Scope mismatch: SQL key and envelope validation fail closed.
16–17. Tampered lineage/state: canonical digest and producer/result-local
   ownership validation reject mismatch; hashes do not defend against a
   compromised authorized writer.
18. Historical record without lineage: readable, never a state parent.
19–20. Connector restart and runtime-ID changes: exact canonical evidence,
   scope and governed timestamps determine identity; runtime metadata is
   excluded.

## ANALYTICAL FREEZE

`ANALYTICAL_MATH_CHANGED: NO`

The plan adds canonical identity propagation, lineage/state contracts and
transactional transport only. It does not change relationship or graph math,
either reducer, thresholds, eligibility, quality, context semantics,
classification, corroboration, ranking/primary, consequences, telemetry
admission, governance, control or presentation.

## IMPLEMENTATION PLAN

Implementation is authorized only for the canonical telemetry analysis-window
path described above. Legacy upload/direct paths stay continuation-unavailable.

### PHASE A — Canonical endpoint identity propagation

- **Production files:** `backend/app/services/telemetry_analysis_window.py`,
  `backend/app/services/telemetry_analysis_service.py`, and the narrow handoff
  into `backend/app/engine/sii_engine.py`.
- **Contract:** explicit internal endpoint map from each analyzed column to
  canonical signal ID, system/asset and validated mapping-authority digest.
- **Tests:** mapped connector observations retain IDs through pivot; mapping
  ambiguity/staleness suppresses continuation metadata; ordinary current-run
  relationship outputs remain equal.
- **Failure:** no/ambiguous mapping means no lineage/state use; analysis still
  runs unchanged.
- **Freeze:** no numeric rows, edge order or calculations change.

### PHASE B — Relationship lineage issuance and verification

- **Production files:** new
  `backend/app/services/relationship_lineage.py`, plus
  `backend/app/services/relationship_evidence_binding.py` only for mechanical
  inclusion/verification metadata, and producer finalization in
  `backend/app/engine/sii_engine.py`.
- **Contract:** scoped deterministic lineage payload/ref, with global/mode/fallback
  separation; retain all three exact result-local ownership fields unchanged.
- **Tests:** deterministic lineage under mapping order/retry/runtime changes;
  distinct scope/endpoints/basis/mode/semantic versions; missing/tampered refs;
  exact source/evidence ownership still required.
- **Failure:** invalid lineage unavailable; no current analysis failure.
- **Freeze:** identifiers only; no analytical field change.

### PHASE C — Scoped temporal-state repository

- **Production files:** telemetry schema migration and
  `backend/app/services/telemetry_repository.py`; repository protocol in
  `backend/app/services/telemetry_analysis_service.py`.
- **Contract:** one unique current-head row keyed by full authenticated scope,
  system, asset and lineage; bounded state, compatibility digest, event/head
  refs, storage revision.
- **Tests:** scope isolation, unique head, transactional CAS, rollback, bounded
  encoding, idempotent exact event, conflicting event and concurrent writers.
- **Failure:** any missing, duplicate or ambiguous head fails closed.
- **Freeze:** no reducer/state semantics change.

### PHASE D — Validated state load into the existing persistence reducer

- **Production files:** `backend/app/services/telemetry_analysis_service.py`,
  `backend/app/services/telemetry_analysis_window.py`, and the state handoff to
  `backend/app/engine/sii_engine.py`.
- **Contract:** authenticate scope, validate lineage/compatibility and exact
  retained result-local evidence ownership before passing the existing state
  mapping to `evaluate_sii`.
- **Tests:** each compatibility dimension mismatch abstains; A cannot read B;
  global/mode/fallback cannot cross; historical records do not seed.
- **Failure:** pass no prior state; existing reducer reports insufficient
  history.
- **Freeze:** call the reducer unchanged.

### PHASE E — Post-finalization governed state write

- **Production files:** `backend/app/services/telemetry_analysis_service.py`,
  `backend/app/services/telemetry_repository.py`, and the narrow atomic
  completion operation.
- **Contract:** derive deterministic event identity from exact source ref and
  governed window; validate final relationship evidence ownership; CAS state
  and publish result atomically.
- **Tests:** retries, same-window duplicate/conflict, competing windows,
  out-of-order events, stale CAS and artifact rollback.
- **Failure:** no stale temporal result is published and no head advances.
- **Freeze:** only reducer output from existing math may be persisted.

### PHASE F — Canonical/storage/connector propagation

- **Production files:** `backend/app/services/analysis_result_contract.py`,
  `backend/app/services/telemetry_result_artifact.py`,
  `backend/app/services/telemetry_result_service.py`, and
  `backend/app/services/telemetry_result_projection.py` only where state or
  lineage is required for authorized transport.
- **Contract:** mechanical copy of lineage and bounded governed state refs;
  never reconstruct. Do not expose complete state in an unauthorized product
  projection.
- **Tests:** JSON artifact/read, upload, connector restart/replay, bounded
  projection and absence/tamper behavior.
- **Failure:** missing transport metadata disables continuation; historical
  read remains intact.
- **Freeze:** no presentation or analytical derivation.

### PHASE G — Focused adversarial certification

- **Production files:** none expected; test additions limited to focused suites
  such as `tests/test_relationship_lineage.py`,
  `tests/test_relationship_temporal_state_repository.py`,
  `tests/test_relationship_temporal_persistence.py`, and
  `tests/test_relationship_evidence_binding.py`.
- **Contract:** certify the 20 attack classes in this review and existing exact
  resource/consequence ownership after continuation.
- **Failure:** any failed ownership, scope, concurrency, determinism,
  compatibility or historical test blocks enablement.
- **Freeze:** require `ANALYTICAL_MATH_CHANGED: NO` and compare existing reducer
  output on the same explicit incoming state.

## BLOCKERS

No prerequisite blocker found for the authorized canonical telemetry
analysis-window path. Arbitrary upload/direct paths do not have authoritative
canonical endpoint IDs and remain unavailable for continuation. The production
state row and transaction integration are new code in the existing authorized
PostgreSQL telemetry repository, not an existing temporal-state service; the
existing scoped transaction, unique-key, row-lock and atomic result-publication
primitives are sufficient for the planned implementation. Phase E must preserve
the fail-closed stale-head rule before any candidate is enabled.

## NEXT ACTION

Review and authorize Phase A implementation on the canonical telemetry path.
Keep legacy/direct analysis continuation-unavailable. No continuation behavior
is active until Phases A–G are implemented and certified.
