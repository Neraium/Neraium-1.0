# Neraium Evidence-Governance Architecture

## Status

This document is the normative architecture specification for the evidence-governance layer in Neraium 1.0.

Implementation status labels used below:

- **Existing**: implemented in the current repository.
- **Existing / extend**: current mechanism exists but must be brought under this contract.
- **Specified**: architecture is frozen; implementation is not yet complete.
- **Deferred**: intentionally outside the current authority boundary.

## Core doctrine

1. **Maturity does not authorize physical action. It authorizes software authority.**
2. **Historical decisions are reconstructed under the evidence and policy that existed when they were made.** Historical audit records are never rewritten to match later knowledge; later knowledge is appended through new versioned objects and supersession links.
3. **Neraium does not trust adaptation merely because the system itself proposed it.** Adaptation requires evidence maturity and explicit authority-policy permission.
4. **Evidence is produced by analytics, not authorized by analytics.** No analytical module may directly grant itself downstream authority.
5. **Maturity describes evidentiary development, not probability or truth.**
6. **Lifecycle describes what a finding is doing, independently of maturity.**
7. **Authority determines what software is permitted to do with the evidence.**
8. **Audit history records what was known and permitted at the time.** Later evidence appends to history rather than rewriting it.

Neraium remains read-only and human-in-the-loop. This architecture governs software-side evidence handling, finding evolution, model adaptation eligibility, and auditability. It does not authorize physical control actions.

## System architecture

```text
Context Registry
        ↓
Analytical Evidence
        ↓
Evidence Maturity
        ↓
Finding Lifecycle
        ↓
Authority Policy
        ↓
Authority Decision Record
        ↓
Presentation / Audit
```

Cross-cutting controls apply across every layer:

- versioning
- provenance
- evidence dependencies
- cryptographic integrity (future; not yet claimed)

## Layer 0: Context Registry

**Status: Existing / extend**

The Context Registry is a shared, versioned, provenance-aware dependency used by all downstream layers. It records infrastructure identity, operating context, external anchors, engineering constraints, maintenance and calibration events, commissioning references, baseline/model history, and other admissible context.

Every context object must carry, as applicable:

- stable identity
- source
- effective time
- validity interval
- verification status
- system scope
- provenance
- version
- supersession reference

Context is evidence, not unquestioned truth. A maintenance record, telemetry-derived event, configured engineering prior, and commissioning reference may have different verification status and provenance.

## Layer 1: Analytical Engine

**Status: Existing**

The analytical engine produces deterministic evidence objects from telemetry and admissible context. Current analytical capabilities include signal drift, relationship analysis, covariance/Mahalanobis evidence, temporal analysis, multiscale analysis, expected-behavior residuals, behavioral graph comparison, physics-informed evidence, and related deterministic outputs.

Analytical outputs that participate in governance must declare at minimum:

- evidence family
- analytical method
- source signals
- source time/window
- derivation dependencies
- assumption set
- provenance reference

Analytical modules produce evidence only. They do not decide evidence maturity, finding lifecycle, operator escalation, baseline adaptation, or finding closure.

## Evidence families

**Status: Specified**

Canonical evidence families are:

- `signal_location`
- `relational`
- `covariance_geometry`
- `temporal`
- `expected_response`
- `multiscale`
- `physics_external`
- `instrumentation`
- `trend`

Multiple metrics derived from the same underlying mathematical structure do not automatically count as independent corroboration. For example, covariance-matrix movement and Mahalanobis displacement are both `covariance_geometry` evidence.

## Layer 2: Evidence Maturity Engine

**Status: Specified**

The Evidence Maturity Engine evaluates a finding-specific evidence object over time.

### Maturity ladder

- **L0 Observed**: a deviation has been observed but required persistence has not been established.
- **L1 Persistent**: the observation survives the applicable fixed and/or elapsed-time persistence gates.
- **L2 Corroborated**: the persistent observation has support from sufficiently independent evidence families according to the dependency rules.
- **L3 Characterized**: the behavior of the change has been characterized, such as step, drift, oscillation, recovery, or propagation candidate.
- **L4 Context-Qualified**: the characterized evidence has applicable external context sufficient to authorize further software-policy evaluation.

Maturity is not monotonic. It may regress when persistence disappears, corroboration is lost, trajectory changes, an anchor is invalidated, or later evidence limits the finding.

Maturity is evidence-specific and finding-specific, never a global system confidence score.

## Layer 3: Finding Lifecycle Engine

**Status: Existing / extend**

Finding lifecycle is orthogonal to maturity. A finding can therefore be represented as states such as `L3 / recovering` or `L2 / persistent`.

Canonical lifecycle states are specified as:

- `new`
- `persistent`
- `recovering`
- `adapted`
- `externally_explained`
- `unresolved`
- `superseded`
- `closed`

Lifecycle history is append-only and versioned. A finding may recover or regress without erasing the evidence that previously caused elevation.

## Layer 4: Authority Policy Engine

**Status: Specified**

The Authority Policy Engine decides what software is permitted to do with a finding under the policy version in force at decision time.

Possible authority outcomes include:

- `permitted`
- `deferred`
- `blocked`
- `human_review_required`
- `released`
- `escalated`

Low-maturity structural evidence should generally **defer** adaptation while additional evidence is gathered rather than create an irreversible lock. Mature structural evidence may block automatic adaptation or require human review.

### Tier A: state-location adaptation

**Status: Specified**

Tier A is bounded adaptation where state location changes while structural evidence remains sufficiently consistent. Eligibility may include mean/offset movement with materially intact relationship and covariance structure, no unresolved instrumentation concern, no contradictory physics evidence, and an admissible evolution rate.

Tier A may become automatically permissible only when the applicable policy and evidence maturity allow it.

### Tier B: structural adaptation

**Status: Specified**

Tier B covers material graph, covariance-structure, expected-response, or other structural changes. Tier B is not automatically learned merely because the new state is stable. It requires stricter policy gates and may require explicit human review.

## Layer 5: Authority Decision Record

**Status: Specified**

Every consequential software-authority decision must create an immutable, append-only `AuthorityDecision` record.

Required fields:

```text
AuthorityDecision:
  decision_id
  finding_id
  decision_timestamp
  effective_timestamp
  policy_id
  policy_version
  evidence_snapshot_ids
  context_snapshot_id
  dependency_graph_snapshot_id
  maturity_at_decision
  lifecycle_state_at_decision
  requested_operation
  decision_outcome
  decision_reasons
  limiting_evidence
  contradicting_evidence
  active_model_before
  candidate_model
  active_model_after
  human_review:
    required
    status
    reviewer_identity
    reviewed_at
    rationale
  supersedes_decision_id
  source_run_id
```

Policy itself is versioned. Historical decisions are reconstructed under the policy, evidence, model state, and context that existed when they were made.

If later evidence invalidates a context anchor or changes a finding interpretation, the original AuthorityDecision remains intact. New context, lifecycle, maturity, and authority records are appended and may supersede earlier records.

## Layer 6: Presentation and Audit

**Status: Existing / extend**

Presentation consumes the canonical evidence-governance records. It must not manufacture authority or collapse independent evidence into a probabilistic confidence score.

The system should be able to answer, for any material finding or model transition:

- What was observed?
- When was it observed?
- Against which baseline/model version?
- Under which operating context?
- Which evidence families supported it?
- Which evidence objects were dependent on one another?
- How did maturity change?
- How did lifecycle state change?
- Which authority decision was made?
- Under which policy version?
- Why was adaptation permitted, deferred, blocked, released, or escalated?
- Was human review required or performed?
- What later evidence changed the interpretation?

## Evidence dependency graph

**Status: Specified**

Evidence dependencies are first-class. Each evidence object records the upstream observations and evidence objects from which it was derived. The maturity engine uses the dependency graph together with evidence-family classification to avoid false corroboration.

Corroboration must not be awarded merely because two metrics have different names. Dependency and family rules determine whether support is sufficiently independent.

## Immutability and versioning

**Status: Existing / extend**

Historical audit objects describe what happened under the evidence and policy available at that time. They are never rewritten to match later knowledge.

Later invalidation of an anchor, model assumption, or human-supplied context creates a new versioned object and the appropriate supersession or invalidation record. Historical authority decisions remain reconstructable.

## Cryptographic integrity boundary

**Status: Deferred**

The current evidence-governance architecture specifies application-level append-only, timestamped, versioned provenance and decision traceability.

Do not claim cryptographic non-repudiation until signing, attestation, key-management, tamper-evident storage, and verification controls are implemented and validated.

## Regulatory and assurance positioning

This architecture is compliance-enabling, not a substitute for a customer's compliance program or certification process. Neraium may describe its versioned evidence, decision traceability, provenance, and human-review controls factually. It must not claim compliance or certification with a regulatory or assurance regime unless the required controls have actually been implemented, validated, and independently established where applicable.

## Initial implementation sequence

The first implementation tranche is intentionally limited to governance foundations and must not silently alter current analytical severity, compatibility results, or baseline-learning behavior.

1. Canonical `EvidenceObject` contract and evidence-family taxonomy.
2. Evidence dependency representation and independence rules.
3. `AuthorityDecision` contract and append-only storage contract.
4. Maturity v1: L0 Observed, L1 Persistent, L2 Corroborated.
5. Finding lifecycle integration and versioned lifecycle events.
6. Context Registry v1 around existing identity, mode, model-history, event, and engineering-prior context.
7. Only after the above: L3 trajectory characterization, trend evidence, L4 context qualification, Tier A/Tier B authority integration.

## Implementation invariant

No existing analytical module may be modified to make a new authoritative baseline, escalation, or finding-closure decision until the evidence-governance contracts and tests for that authority path are in place.
