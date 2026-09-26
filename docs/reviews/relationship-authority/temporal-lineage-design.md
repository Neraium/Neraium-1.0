# Governed cross-analysis relationship lineage design

Status: `TEMPORAL_LINEAGE_DESIGN_READY_FOR_REVIEW`

Baseline reviewed: `a75b7c1ef572b3c926e8fd00db3691d69e84e112` on
`fix/deterministic-governed-output`; `origin/fix/deterministic-governed-output`
matches. This is a design artifact only. No production code or tests changed.

## CURRENT IDENTITY MODEL

Three existing identities answer result-local questions and remain unchanged:

- `relationship_source_ref` identifies the producer-issued source calculation in
  one result.
- `relationship_evidence_ref` identifies the finalized evidence record in that
  result's registry.
- `relationship_assessment_binding` binds that source and evidence to the
  authorized result scope.

The source calculation is created in `relationship_baselines.py` and
`mode_conditioned_baseline.py`. Its source ID hashes selected baseline and
current observations, units, selection, method and measurement. It is expected
to change as observations change. The finalized evidence registry is result
local and scope-bound. Resource binding copies the exact source used by the
resource producer and resolves it only inside that registry.

The temporal reducer currently uses a caller-owned dictionary keyed by sorted
column names. Its identity compares columns, edge basis, baseline correlation
and window, mode data, reference dataset and units. It returns bounded reducer
observations but does not load or persist them. `evaluate_sii` accepts the state;
the production upload pipeline currently calls it without prior state.

## WHY CURRENT IDS CANNOT CONTINUE STATE

The result-local source ID cannot be the cross-run key: its current-observation
digest changes on each legitimate run. The evidence ref and assessment binding
are likewise issued per result. Conversely, the reducer's sorted-column key is
not a governed identity: it has no authenticated scope, stable canonical signal
identity, relationship semantic version or explicit assessment lineage. Its
compatibility fields are useful reducer checks, but do not prove ownership.

The current generated telemetry catalog keys records by input column and holds
classification/display data. That is not a stable canonical signal identity.
The telemetry lineage subsystem has `canonical_signal_id`, but the relationship
producer does not currently resolve or bind its edge endpoints to those IDs.
Therefore no existing production identity is sufficient for automatic
cross-analysis continuation.

## PROPOSED LINEAGE CONTRACT

Add a producer-owned, versioned `relationship_lineage_ref` to a relationship
assessment candidate. It is distinct from all three result-local ownership
fields and from temporal state. It is an opaque deterministic hash over a
canonical semantic identity payload, not an authorization capability.

Conceptual payload (`relationship-lineage.v1`):

```json
{
  "contract": "relationship-lineage.v1",
  "scope_ref": "relationship-scope.v1:<digest>",
  "relationship_semantics": "linear_correlation.v1",
  "assessment_basis": "global_relationship_model",
  "endpoints": ["canonical-signal-id-1", "canonical-signal-id-2"]
}
```

For the current Pearson producer, endpoints are an unordered, canonically
sorted pair because correlation is symmetric. A future directed relationship
must use a new semantic contract with explicit source/target roles; it cannot
reuse this v1 identity. The lineage ref is issued while the producer still owns
the actual selected edge and its validated canonical endpoint mappings. Missing,
ambiguous or conflicting endpoint identity means no lineage ref and no
continuation.

The lineage identifies a family of assessments that may be continuation
candidates. A separate compatibility descriptor determines whether this exact
prior state can be consumed now. It includes the existing reducer identity and
assessment-context compatibility dimensions described below.

## PRODUCER AUTHORITY

Issue the lineage in the relationship producer/finalization path, after the
selected relationship edge and its producer semantics are known and before
downstream projection. Resolve canonical endpoints from the authorized
telemetry mapping/lineage used to create the rows. Do not derive them from
display labels, raw names, grouping, contribution lists, ranking or primary
selection.

The producer has access to the actual edge method, selected mode/fallback path,
scope and source evidence. Resource finalization, canonical result assembly,
connector projection and storage are consumers: they may copy or verify lineage
metadata, but may not invent it. The current relationship evidence finalizer
remains authoritative for the separate exact result-local source/evidence/
assessment tuple.

## SEMANTIC IDENTITY INPUTS

Minimum lineage hash inputs:

1. Authorized scope digest covering the authenticated workspace/site/system
   boundary. A result-local placeholder scope is not sufficient for persistent
   cross-run state.
2. Canonical endpoint IDs, sorted for the current symmetric Pearson contract.
3. Relationship semantic type/version (`linear_correlation.v1`), not a display
   `relationship_type` string copied from presentation.
4. Assessment basis (`global_relationship_model` versus
   `mode_conditioned_relationships`). The successful global basis and
   `global_relationship_model_failure_fallback` are distinct; fallback is
   ineligible for continuation under current semantics.
5. Lineage contract version.

Operating-mode ID/features are not in the base global relationship identity.
They are explicit compatibility dimensions. For a mode-conditioned assessment,
the assessed mode identity and exact producer selection features are included
in the lineage identity because they define which historical population the
relationship describes. Missing mode identity means no mode lineage.

Baseline dataset/model ID, baseline window and baseline measurement, canonical
units, reducer method/version, and operating-context compatibility are checked
in the state compatibility descriptor rather than used to create a new lineage
family. A mismatch resets continuation. This lets the lineage mean “same
governed relationship candidate” while preventing a reducer from extending a
different fixed baseline or context.

The contract does not include runtime IDs, current observation contents, source
row positions, current ranking, group membership, primary selection, result
ordering or presentation fields. Exact current observation content remains in
the result-local source evidence.

## OPERATING CONTEXT / MODE RULES

- Global and mode-conditioned assessments require distinct lineage. The graph
  chooses one basis for its edge set; the same columns under the other basis
  cannot borrow state.
- Within mode-conditioned assessment, mode identity and selection features
  participate in lineage. A different or unavailable mode does not continue.
- Global operating-context values (baseline/recent mode and governed context
  match fields) are compatibility dimensions. A changed context invalidates
  the existing fixed-baseline history; it does not silently qualify the old
  history for reuse.
- Fallback evidence cannot continue successful global history or mode history.
  Current finalization explicitly makes graph-failure fallback temporal evidence
  unavailable, and the authority adapter requires exact temporal evidence.
  Fallback remains unavailable for continuation even if a future fallback
  producer emits a lineage-shaped record, unless a separately reviewed contract
  changes that rule.
- A change in mode/context therefore fails closed and starts with insufficient
  history under a newly compatible assessment. This preserves reducer identity
  and does not change context mathematics.

## TEMPORAL STATE ENVELOPE

Store a versioned, bounded state envelope separate from assertion ownership:

```json
{
  "schema": "relationship-temporal-state.v1",
  "scope_ref": "relationship-scope.v1:<digest>",
  "lineage_ref": "relationship-lineage.v1:<digest>",
  "compatibility_digest": "relationship-temporal-compat.v1:<digest>",
  "reducer": "relationship_temporal_evidence.v1",
  "head_event_ref": "<digest of final retained governed observation>",
  "observations": [],
  "state_digest": "relationship-temporal-state.v1:<digest>"
}
```

Each bounded observation carries only reducer-required governed evidence:

- deterministic event ref derived from lineage ref plus exact result-local
  evidence ref and governed window identity;
- result-local `relationship_source_ref`, `relationship_evidence_ref`, and
  assessment binding as provenance references, validated against the
  authorized source result when state is admitted;
- governed `observed_at` and the baseline/current window timestamps;
- signed correlation delta, edge confidence, data-quality factor, eligibility
  and acceptability fields consumed by the existing reducer;
- source dataset reference and bounded source-row anchors only where required
  by the existing governed evidence contract.

Keep at most the reducer's existing eight observations. Do not store a computed
persistence boolean, classification, ranking, condition, group, primary result,
presentation copy, telemetry rows or unrestricted evidence registry. The
existing reducer remains the sole calculator of temporal persistence.

Canonical serialization uses the repository canonical JSON contract: sorted
object keys, preserved array order, finite numbers only, explicit schema/domain
versions and no lossy coercion. Digests are integrity checks, not signatures;
the authorized state store remains the trust boundary.

## COMPATIBILITY RULES

State is consumable only when all checks pass:

1. Caller authorization resolves the exact workspace/site/system scope and it
   equals the state scope.
2. The current producer independently issues the same lineage ref.
3. The compatibility digest matches exact reducer method/version, basis,
   semantic contract, fixed baseline identity/window/value, units and
   assessment-context dimensions.
4. Every retained source result/evidence tuple resolves in its authorized result
   registry; missing/tampered ownership makes the state unavailable.
5. The history is bounded, internally ordered and has one unambiguous head.
6. The new governed event timestamp follows the head. Exact replay of an
   identical event is idempotent; a conflicting duplicate, older event or
   ambiguous prior head is not appended and receives no historical continuation.

Do not search and select among several states by nearest timestamp or matching
signals. Lookup is by exact scope plus lineage; if storage returns multiple
current heads, fail closed.

## ATTACK ANALYSIS

| Attack | Required result |
| --- | --- |
| Same pair names in different sites | Scope digest differs; no continuation. Names alone never identify endpoints. |
| Reversed relationship direction | Current Pearson is symmetric and has no direction to reverse; canonical unordered endpoints match only this symmetric contract. Any directed semantic contract uses ordered roles and a new version. |
| Same signals, different relationship type | Semantic type/version differs; no continuation. |
| Global versus mode-conditioned | Basis and mode contract differ; no continuation. |
| Successful global versus graph-failure fallback | Fallback has no continuation authority and cannot consume successful state. |
| Ranking, primary selection or grouping changes | No effect; these are absent from identity and state compatibility. |
| Connector restart | No effect if authorized canonical mappings, scope and stored governed state are unchanged. |
| Retry/replay | Same exact evidence/window yields same event ref; exact replay is idempotent and cannot add a vote. |
| Runtime IDs change | No effect; they are excluded. |
| A attempts to consume B state | Different endpoint lineage yields different ref; exact source/evidence ownership is independently validated. |
| Same marginal signals, changed relationship structure | The new pair/semantic endpoints do not match A's lineage; no union or signal-level transfer. |
| Relationship semantic definition changes | Semantic version changes; incompatible state is unavailable. |
| Workspace/site/system mismatch | Scope check fails before state use. |
| Historical record lacks lineage | Read remains valid; it supplies no continuation state and is not reconstructed. |
| Lineage metadata tampered | Recompute deterministic digest and producer/source references; mismatch fails closed. A digest is not protection against a compromised trusted writer. |
| Multiple prior states for one lineage | Ambiguous heads fail closed; do not rank or choose one. |
| Out-of-order analyses | Older event cannot replace/extend the current head. Reducer chronology rules remain in force. |
| Duplicate/replayed analysis execution | Exact evidence event is idempotent; conflicting same-window evidence is rejected and cannot vote twice. |

## DETERMINISM / REPLAY

Lineage and state identity use only canonical producer semantics, authorized
scope, exact governed evidence references and event/window timestamps already
used by the temporal reducer. Process, worker, connector, request, retry and
execution-clock values are excluded. Mapping input order is normalized at the
producer. Ranking, primary selection, grouping and presentation order cannot
alter lookup or state contents. Connector serialization must preserve contract
fields exactly; it cannot reconstruct missing lineage.

## HISTORICAL COMPATIBILITY

Historical results without `relationship_lineage_ref` remain readable as-is.
No result migration, rewrite, replay or name-based reconstruction is required.
They are unavailable as continuation parents. New metadata is prospective and
additive. Existing exact result-local ownership fields keep their current
meaning and verification path.

## SECURITY / AUTHORIZATION

The lineage ref and state digest are unkeyed integrity identifiers, not access
tokens or authorization. State lookup must occur only after the existing
authenticated result/system scope is established. Scope is checked both in the
key and envelope. Do not put credentials, secrets, tokens, process/runtime IDs,
paths, raw telemetry or an unrestricted registry into the envelope. Raw
observations remain governed by the existing source evidence contract; state
contains only its bounded reducer fields and references.

## ANALYTICAL FREEZE

`ANALYTICAL_MATH_CHANGED: NO`

This design adds identity, compatibility validation, bounded state transport
and persistence only. Relationship/graph calculations, persistence and
recurrence reducers, thresholds, eligibility, quality, context semantics,
classification, corroboration, ranking/primary, consequence calculations,
telemetry admission, governance and control/actuation remain frozen.

## IMPLEMENTATION SURFACE

No implementation is included here. A later implementation should be limited
to:

1. canonical endpoint identity resolution at the relationship producer;
2. a small lineage contract/finalizer, separate from result-local evidence
   binding;
3. a bounded, scoped temporal-state repository with exact-head/idempotent event
   semantics;
4. state load/validation before graph reduction and state write only after the
   governed result/evidence is finalized;
5. mechanical copying through canonical result, authorized storage and
   connector transport;
6. focused adversarial tests for ownership, scope, compatibility, replay,
   fallback, transport and historical reads.

The current in-memory `relationship_persistence_state` remains caller-owned
until such a repository is authorized and implemented. No consumer should infer
state from other stored outputs.

## MIGRATION REQUIREMENT

No historical migration is required or allowed. New lineage and state are
prospective. Storage needs a new versioned state record keyed by authenticated
scope and lineage, with atomic head update or equivalent compare-and-swap
semantics. If the selected authorized repository cannot provide isolated scoped
reads and deterministic idempotent writes, continuation must remain unavailable;
do not fall back to local files, result scans, or reconstruction.

## BLOCKERS

- Current relationship producers use column strings and generated catalog
  entries, not a required stable canonical signal ID. The existing telemetry
  mapping/lineage authority must be connected at the producer boundary; absent
  or ambiguous mappings must disable continuation.
- Production has no relationship temporal-state persistence/read path. The
  state repository and atomic latest-head behavior need a separately reviewed
  storage contract.
- Scope must be authenticated and non-placeholder. Direct/internal
  `result-local` evaluations cannot seed shared cross-run state.

These are explicit implementation prerequisites, not reasons to guess an
identity from names or to expand the current result-local binding contracts.

## DECISION

`TEMPORAL_LINEAGE_DESIGN_READY_FOR_REVIEW`

## NEXT ACTION

Review the semantic identity and scoped state-store contract. Only after approval
of canonical endpoint authority and storage should a focused implementation
candidate be prepared. Keep temporal continuation out of production until those
prerequisites can be proven and tested.
