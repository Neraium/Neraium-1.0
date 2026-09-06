# Evidence-governance foundation v1

This implements the first tranche of [the normative architecture](EVIDENCE_GOVERNANCE_ARCHITECTURE.md). It introduces contracts and explicit local helpers, with no governance call added to SII, upload processing, APIs, frontend presentation, baseline learning, escalation, or finding closure. Current analytical authority is unchanged. L0–L2 evaluations are non-authoritative in this tranche; recording even a `permitted` decision executes nothing.

## Implemented contracts

`backend/app/governance/contracts.py` defines the nine canonical evidence families, `EvidenceObject`, source windows, typed observation/evidence references, provenance, lifecycle vocabulary, `AuthorityDecision`, human review, and minimal context/policy/model audit snapshots. These are Pydantic contracts, consistent with the existing evidence-package conventions. `as_dict()`, `model_dump_json()`, and `model_validate_json()` support transport and replay. Unknown fields, unsupported schema versions, invalid families, naive timestamps, and non-finite payload numbers are rejected. Each inline payload is limited to 65,536 UTF-8 bytes; larger analytical results use an immutable `result_ref`.

Evidence, graph, maturity, decision, and audit-snapshot IDs use the full SHA-256 digest of canonical JSON excluding the ID itself. Supplied content IDs are checked. Caller-supplied timestamps normalize to UTC; there is no implicit clock or randomness. Evidence set fields and graph node collections are sorted; other sequences preserve their declared order. Changes to times, policy versions, provenance, result contents, or dependencies produce new IDs. Evidence versions above one require an exact `supersedes` ID. IDs identify individual snapshots, not a mutable finding or model identity.

Top-level records are frozen. Nested JSON payloads are ordinary JSON containers: storage revalidates serialized copies and returns defensive copies, so changing a caller's object cannot rewrite persisted history. Digest IDs provide deterministic comparison, not authentication or tamper-proof storage.

## Dependencies and maturity

`dependencies.py` stores full evidence nodes and exact raw observation references. `derived_from` is the canonical edge representation; `edges()`, `upstream()`, `lineage()`, and `shared_upstream()` expose it. Construction sorts nodes, rejects duplicate IDs, mismatched scopes, dangling/wrong-kind edges, and cycles. `topological_order()` also validates externally prepared adjacency maps before migration.

Independence v1 requires distinct families and complete declared lineage on every evidence ancestor. Unknown or empty lineage cannot establish independence. All declared inputs are treated conservatively as material: shared ancestors (including an ancestor/descendant pair), raw acquisition sources, source signals, context references, assumptions, or covariance sources reject a pair. Covariance evidence must declare `covariance_source_id`; covariance divergence and Mahalanobis displacement never corroborate as different families. Raw reference aliases with a common `source_id` also reject. The pair result retains exact shared IDs and reason codes. This is a declared-lineage eligibility rule, not a statistical independence test or causal assertion. Completeness is an explicit migration assertion and cannot be inferred merely from the absence of listed edges.

`maturity.py` evaluates only evidence explicitly associated with one finding. Its input includes versioned, finding-specific `PersistenceGate` results with fixed-observation or elapsed-time basis, support IDs, and reasons. This adapter contract preserves applicable analytical gate results without replacing existing persistence calculations. No gates or any failed gate means L0. All applicable gates passing means L1. L2 additionally needs an independent pair that includes evidence supporting persistence. Two unrelated independent extras cannot elevate a third persistent observation. No evidence is an error, not an invented L0 finding.

Every evaluation retains the finding, time, relevant and supporting IDs, graph snapshot, gate results, pair results, and rule version. It does not read a previous maturity or assume monotonic progression: lost corroboration gives L1 and lost persistence gives L0. There are no probability, confidence, diagnosis, health, or authority fields in maturity. L3/L4 can extend the level vocabulary and evaluator version without changing the record structure; v1 deliberately rejects unsupported levels rather than interpreting them.

## Authority history and replay

`authority_store.py` follows the behavioral model store's existing `latest_payloads` ledger convention. The runtime implementation uses `mutate_latest_payload` transactions, with no cache or non-atomic fallback. An in-memory implementation has the same append/retrieval contract and a lock. Storage requires the existing server-supplied `AuthenticatedPhase4Scope`, separately from analytical `system_scope`. There is no new table or persistence service. Lifecycle migration `014_governance_lifecycle_events` extends the existing event-type CHECK constraint using the repository's transactional table-rebuild migration, preserving original rows, indexes, uniqueness, and append-only triggers.

`append_decision(scope, decision, basis)` atomically stores the decision and its `DecisionBasis`: complete evidence/graph and maturity snapshots, original lifecycle event, and context/policy/model snapshots. Required references, scope, policy identity/version, lifecycle identity/state, decision-time knowledge, and replayed maturity must match. Model fields reference immutable snapshots, never active pointers. `get_record()` retrieves the exact original decision and basis; `history()` orders records by append sequence and can filter by finding. Effective time does not reorder history.

Exact retries are idempotent. Existing IDs cannot be rebound to different content. Supersession requires an existing decision for the same finding and operation and rejects branching successors. Later knowledge appends a new decision and basis; superseded records remain unchanged. Append failure propagates and does not return a successful local-only record. No authority-policy evaluator, permission consumer, or model-mutation method is implemented.

The ledger retains the governance evidence contents and the exact declared raw/result/provenance references. Callers remain responsible for archiving externally referenced immutable raw observations and large result artifacts; this tranche does not implement a raw-data archive, a Context Registry, external identity attestation, or verification of supplied provenance. Snapshot retention is unbounded within each system ledger, matching the existing ledger approach; production pagination/partitioning and retention policy remain future work.

## Lifecycle integration

`finding_workflow.record_governance_lifecycle()` adds an explicitly invoked `governance_lifecycle_recorded` event to the existing scoped finding event log. It reuses finding IDs, transaction locking, idempotency, and optimistic event versions. `previous_event_id` must identify the most recent governance lifecycle event; the first event has no predecessor. Governance lifecycle events share the log's version sequence with operator events, so lifecycle versions may have gaps. `governance_lifecycle_history()` returns the original payloads in version order.

This is an event foundation, not a second workflow state machine. All eight future lifecycle states are representable. No maturity is inferred from lifecycle, and no lifecycle transition is inferred from maturity. Explicitly appending such an event increments ordinary log version/activity metadata, but does not change operator status, priority, escalation, resolution, or source evidence. No live caller or route is added.

## Specified but inactive

L3 characterization, L4 context qualification, Context Registry services, trend analytics, authority-policy execution, Tier A/Tier B adaptation, automatic escalation/closure, and runtime analytical adapters remain inactive. Existing baseline-learning and operator behavior are preserved. Maturity can eventually support software-authority evaluation; it never authorizes physical action. Neraium remains read-only and human-in-the-loop.

Application-level append-only validation and provenance are implemented. Cryptographic non-repudiation, signing, key management, attestation, tamper-evident storage, and independent integrity verification are not implemented. Database administrators or code using unrelated low-level write APIs can alter storage; this is not tamper-proof storage. No regulatory compliance or certification is claimed.

## Verification

Focused tests are `tests/test_evidence_governance.py`, `tests/test_governance_audit_boundaries.py`, `tests/test_governance_lifecycle.py`, and `tests/test_governance_compatibility.py`. They cover deterministic round trips, family validation, DAG traversal/rejection, conservative corroboration, L0–L2 regression, decision replay and supersession, policy/timestamp preservation, concurrent append/failure handling, scope isolation, and lifecycle independence. Audit boundary tests reject source windows ending after decision time and preserve historical rows during migration. Any declared covariance source must belong to the evidence's lineage, including for non-covariance families. The compatibility regression hashes the complete existing stable SII result, including its compatibility payload, against base commit `31fc1556`. Execution timing/performance diagnostics are excluded and the wall-clock-generated runner upload ID is normalized; analytical fields are retained.

Run with the repository backend dependencies installed:

```sh
python -m pytest tests/test_evidence_governance.py tests/test_governance_audit_boundaries.py tests/test_governance_compatibility.py tests/test_governance_lifecycle.py -q
python -m pytest tests/test_sii*.py tests/test_behavioral_model*.py tests/test_finding*.py tests/test_behavioral_baseline_workflow.py tests/test_adaptive_learning.py tests/test_phase3_auth_runtime.py -q
python -m pytest tests/test_shared_maintenance_workflow.py -q
git diff --check
```
