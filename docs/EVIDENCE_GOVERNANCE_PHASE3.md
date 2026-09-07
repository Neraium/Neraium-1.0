# Evidence-governance Phase 3

Phase 3 adds explicitly invoked, non-executing adaptation planning in
`backend/app/governance/adaptation.py`. No API, analytics adapter or model writer
calls this workflow. Phase 1/2 evaluators and historical schemas remain unchanged.

## Candidate and transition contract

A content-addressed candidate freezes a validated, previously stored Phase 2
adaptation decision and its complete basis: authenticated tenant/workspace/system,
exact policy, context history/facts, dependency graph, evidence, maturity, finding
lifecycle, and model snapshots. Candidate model and baseline references must be
nonempty and the candidate snapshot must differ from the active snapshot.

The immutable transition contract retains `active_before`, `candidate`,
`active_after`, and `rollback_reference`. The after snapshot and rollback reference
must equal the exact before snapshot. This is a retained rollback target, not a
rollback executor or a claim that an external model archive has been verified.
`execution_authorized` can only be false. No live model is read or activated.

## Workflow and human review

`AdaptationWorkflow.propose` admits a candidate from a stored decision.
`advance` accepts evaluate, request_review, review, or supersede. Lifecycle states
are candidate_proposed, deferred, human_review_required, approved, rejected,
superseded, and applied. Applied is vocabulary only: there is no admission or
execution path to it. Maturity stays in the frozen decision and is never rewritten.
Approved represents software eligibility only, never an execution token.

Every append checks an exact predecessor under the existing storage transaction.
Concurrent or duplicate review submissions have one winner; the loser receives a
conflict and must read history. A deferred request can be explicitly requested
again. Rejected and superseded candidates are terminal. Supersession names an
existing candidate for the same finding, with no backward proposal chronology;
old records remain intact.

Review requires an explicit pending request, approve/reject/defer disposition,
rationale, timestamp, and reviewer identity/provenance. The host injects an
`authenticate_review(scope, system, credential)` callback that verifies current
review authorization. The returned Reviewer must match the authenticated scope.
The default is disabled. A payload name or self-declared Reviewer is not accepted
as a credential by the workflow itself. The host callback and clock are trusted
integration dependencies, never request parameters. There is no production auth
adapter in this tranche. Review time is obtained inside the writer transaction;
regressing clocks fail. Existing scope objects retain their Phase 2 host-attested
trust boundary. This is application provenance, not cryptographic attestation.

Human approval is recorded even when safety gates defer eligibility. It cannot
resolve an upstream analytical concern, change evidence, or waive policy. Tier B
always requires review and never receives automatic approval. Unclassified
candidates remain deferred. Unresolved finding states fail closed independently
of policy permissiveness. Every non-location safety assessment must be explicitly
absent; unknown is never treated as absent. Existing transitive lineage checks
and independent Phase 2 replay remain authoritative.

Registry and authority-ledger reads occur in the same transaction as each new
candidate/evaluation/request/review append. Changed policy/context selections,
expired policy/context, superseded decisions, scope mismatch, and later knowledge
cannot authorize a stale review. Stale reviews must use a newly admitted decision
and candidate; they cannot refresh the old basis. Supersession itself is an audit
operation and can retire a stale candidate without granting permission.

`replay_adaptation` validates retained event chains, chronology, scope bindings,
review-request references, safety reasons and lifecycle results against the frozen
basis. It never queries current registries or reauthenticates historical actors.
It verifies recorded authentication metadata, not the truth of an external actor
assertion. Historical replay remains deterministic after later policy/context
changes and supersession.

## Rate gate decision

No new admissible rate method is enabled. This is deliberate: existing governance
policies do not define a measurement-unit-specific rate bound, acceptable sampling
gaps, measurement uncertainty, or validated regime assumptions. An elapsed-time
slope or median pairwise slope alone cannot prove a safe bounded evolution rate:
it can hide excursions between irregular samples, opposing slopes, or small-time
noise amplification. Introducing such a statistic as an absent-rate assertion
would weaken Phase 2 rather than establish admissibility.

Mann–Kendall remains a rank trend test, never a rate estimator. Unknown, unsupported,
limited, or insufficient rate evidence remains unknown. Consequently Tier A is
still ineligible and approved/applied states are currently unreachable through
normal admission. A future versioned rate/policy/adapter contract must specify
units, window, missingness, irregular-spacing limits, measurement-error bounds,
threshold provenance, and adversarial validation before this gate can pass. This
tranche makes no cause, health, failure, or RUL claim.

## Non-interference and limits

The consumer search found only internal governance evaluators/stores and the
existing finding-workflow lifecycle serialization helpers consuming
`app.governance` contracts. The latter remain audit-only. Existing legacy
adaptive-learning and baseline/model activation paths do not consume Phase 3
outputs and are unchanged. No physical writes, setpoints, control actions,
customer-system actuation, operator escalation changes, SII semantic changes, or
regulatory/certification claims are added.

The workflow uses both existing in-memory and SQLite runtime storage backends;
there is no schema migration. Storage and external reference integrity retain the
Phase 2 trust boundary. Review-auth integration, validated rate admission, live
finding freshness adapters, immutable external model archival verification and
transactional model activation/rollback remain disabled or deferred. These gaps
are why this tranche has representational authority only.

## Verification

Focused adversarial tests are in `tests/test_governance_phase3.py`, parameterized
across both storage backends. Existing Phase 2 adversarial tests retain coverage
for conflicting ancestry, incomplete lineage, future knowledge, and unknown rate
assertions. Exact delivery commands and results are recorded in the PR.
