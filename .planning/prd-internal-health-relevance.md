# PRD: Internal Outcome-Grounded Health Relevance

> Description: Internally learn, within one authorized system and from explicitly validated real-world outcomes, which parts of learned behavioral structure repeatedly prove useful for understanding system health while preserving uncertainty, context, provenance, and non-causal discipline.
> Author: Neraium
> Date: 2026-08-26
> Status: Checkpoint 1 draft; Phase 1 audit complete; design and implementation not approved
> Mode: feature

## Problem

Neraium already ranks current relationship-change evidence through deterministic relationship importance and learns stable empirical signal/relationship structure through behavioral memory. Neither capability records whether a specific structural subject repeatedly proved useful when real-world outcomes were later validated.

Operators and engineers can record finding feedback, field reports, work orders, and resolutions, and evidence packages preserve detailed analytical lineage. Those records are not yet a normalized outcome truth model: validation status, independence, reliability, temporal linkage, context, negative exposure, deduplication, and per-subject contribution are incomplete. Treating them as labels without a separate validation boundary would amplify confirmation and survivorship bias.

The requested capability is a strictly internal experimental sidecar. It must learn outcome-grounded historical usefulness for one tenant/facility/system only and must not affect customer-facing scores, findings, SII, behavioral memory, or production prioritization.

## Users

1. Authorized Neraium internal researchers/engineers evaluating experimental relevance methods and provenance.
2. Authorized data stewards validating or correcting outcome records and their evidence links.

Customers and normal customer UI are not users of Health Relevance.

## Distinction from existing capabilities

| Capability | Question answered | Inputs | Persistence | Authorized effect |
|---|---|---|---|---|
| Relationship importance / System Relevance | Which current relationship changes deserve attention? | Telemetry structure, magnitude, samples, data/context factors | Preserved in results/evidence | Current evidence/finding ordering |
| Behavioral memory | What empirical signal/relationship structure characterizes accepted operation in this system/context? | Gated telemetry and model history | Versioned models, snapshots, event refs | Expected-behavior evidence and memory only |
| Internal Health Relevance | Which structural subjects repeatedly prove useful across validated outcomes in this exact system/context? | Validated outcomes, explicit links, positive/negative evidence, context, provenance | Separate append-only relevance versions/contributions | Experimental internal inspection only |

Health Relevance is meaningfully distinct. If implementation later reveals that outcome contributions merely reproduce relationship importance without incremental, stable, outcome-grounded information, the experiment must report that result and remain disconnected rather than forcing adoption.

## Core features

1. **Validated outcome ledger:** Persist typed, tenant/facility/system-scoped outcome facts with explicit validation state, source, actors, reliability, temporal windows, structured metadata, and correction/retraction lineage.
2. **Outcome-to-evidence linkage:** Link each eligible outcome to canonical findings, evidence packages/runs, structural subjects, behavioral model versions, and bounded temporal/context roles without causal language.
3. **Inspectable relevance history:** Maintain append-only, context-specific relevance versions for signals, relationships, assets/equipment, and subsystems with positive, negative, contradictory, excluded, and duplicate-suppressed contributions.
4. **Exactly two experimental methods:** Evaluate Bayesian/shrinkage updating and an outcome-conditioned information measure on the same deterministic benchmark and preserve all method inputs, configuration, uncertainty, and component evidence.
5. **Internal governance and inspection:** Enforce fail-closed authorization/isolation and provide a permission-gated internal provenance inspection path only if needed, with no normal customer UI or production decision integration.

## Required outcome model

Supported typed outcomes:

- confirmed maintenance event;
- inspection result;
- confirmed fault;
- confirmed degraded condition;
- repair;
- component replacement;
- operator-confirmed explanation;
- return toward expected behavior after intervention;
- expected/no-fault confirmation; and
- false-positive/not-useful review outcome.

Every record must preserve:

- tenant, facility, system, and asset/equipment where applicable;
- immutable outcome ID and schema version;
- event timestamp or bounded window;
- typed pre-outcome, outcome-period, post-intervention, and recovery windows where applicable;
- source type and source record ID;
- reporter, validator, validation status/time, provenance, and reliability/confidence basis;
- related finding/evidence IDs and structured metadata;
- confirmation-bias flags (independent, post-Neraium discovery, retrospective, maintenance-system sourced, operator-confirmed); and
- correction/supersession/retraction lineage.

Free-text notes remain metadata and cannot automatically produce an outcome type, validation status, or relevance contribution. Telemetry alone cannot validate an outcome.

## Required linkage model

```text
Validated outcome
  -> outcome link (scope + temporal role + provenance)
  -> finding case(s)
  -> evidence run / Evidence Package revision
  -> signal / relationship / asset / subsystem
  -> Behavioral Digital Model ID/version + context fingerprint
```

Links are explicit many-to-many records. A link records whether it is direct, human-reviewed, or derived; its confidence/basis; and its role in pre-outcome, outcome, post-intervention, or recovery evidence. Temporal overlap or recovery association must never be described as causal.

## Internal relevance representation

The state key is:

```text
tenant + facility + system + subject_type + subject_id + context_fingerprint + method_version
```

Each version preserves:

- support and validated-outcome counts;
- recurrence across deduplicated incidents;
- outcome diversity;
- temporal and context consistency;
- context coverage;
- positive, negative, neutral, and contradictory evidence;
- provenance independence mix;
- uncertainty;
- state (`insufficient_outcome_evidence`, `emerging_relevance`, `supported_relevance`, `contradictory_evidence`);
- last updated and all schema/method/configuration/threshold versions; and
- exact contributing and excluded outcome links with reasons.

No opaque scalar is required. If Phase 2 proposes an internal summary value, all components and contribution records must remain inspectable, and the value cannot enter customer responses or production decisions.

## Exactly two experimental methods

### 1. Bayesian/shrinkage relevance updating

Use approved, versioned priors and shrink sparse evidence toward insufficient relevance. Preserve positive/negative evidence, posterior uncertainty, context, provenance strata, and every outcome contribution. Do not reinterpret existing SII or relationship confidence as probabilities or likelihoods.

### 2. Outcome-conditioned information measure

Use a regularized information-gain/mutual-information measure based on transparent contingency counts for structural subject state/presence versus validated outcome class, within the same context and including stable/negative comparison windows. Preserve smoothing/bias correction, effective sample size, uncertainty, and exclusions.

No third method will be implemented. Survival/time-to-event association, hierarchical models, standalone recurrence weighting, and precision/recall contribution are documentation-only candidates.

## Minimum-evidence policy for design

Numeric thresholds are not approved in Phase 1. Phase 2 must propose, justify, and boundary-test configurable thresholds for:

- minimum validated outcomes;
- minimum recurrence across distinct incidents/windows;
- positive-to-negative balance;
- contradictory-evidence range;
- context coverage; and
- outcome diversity.

Before any `supported_relevance` state, policy must require more than one event, complete same-system identity and lineage, explicit eligible validation, deduplication, both positive and negative evidence handling, context-bounded support, and independence/confirmation-bias provenance. Missing denominator, provenance, identity, or context keeps the state insufficient or emerging. One event cannot produce strong relevance.

## Negative evidence requirements

The capability must learn from, and visibly retain:

- false-positive and not-useful reviews;
- expected/no-fault confirmations;
- unrelated maintenance;
- interventions with no observed change in the linked behavior;
- stable operation/exposure windows; and
- contradictory positive and negative outcomes.

Positive evidence is never silently deleted when negative evidence arrives, and negative evidence is never treated as absence of data.

## Context conditioning

Relevance may be conditioned on operating mode, load, season, staging state, environmental context, and system configuration. Each context fingerprint must cite source fields and mapping versions. Evidence from high-load operation cannot create global relevance or relevance in an unobserved mode. Context pooling, if ever proposed, requires separate explicit approval; the default is no pooling.

## Authorization and isolation

- Every table/read/write includes explicit `scope_storage_id`, tenant, facility, and system checks.
- Resource lookup fails closed and returns an opaque not-found response for unauthorized scope.
- Background processing restores immutable scope before accessing records.
- Link creation verifies scope/system on both ends; matching IDs are insufficient.
- Human-readable names, raw tags, and similarity are never authorization boundaries.
- No tenant, customer, facility, fleet, or system aggregation is allowed.
- The legacy adaptive-learning/default-site storage and unscoped latest-payload patterns are forbidden for this capability.

## Confirmation-bias controls

- Record reporter and validator separately.
- Preserve whether the outcome was independently documented, discovered after Neraium review, retrospective, maintenance-system sourced, or operator-confirmed.
- Record window/link selection actor, timestamp, method, and retrospective status.
- Deduplicate one real-world incident represented by multiple findings/packages/events.
- Keep independently documented and Neraium-influenced support separately inspectable.
- Require negative/stable exposure; finding-triggered feedback alone cannot establish strong relevance.
- Preserve corrections and retractions append-only.

## Out of scope

- Customer-facing health scores, rankings, diagnoses, causal root-cause claims, or internal-value leakage.
- Changes to production SII weighting, thresholds, finding semantics, classifications, prioritization, evidence ranking, compute allocation, behavioral-memory behavior, or customer workflow.
- Cross-customer, fleet, or cross-system learning.
- Automatic labeling from notes, telemetry-only outcome validation, or causal inference.
- Deployment; AWS, IAM, DNS, production database, infrastructure, or production configuration changes.
- Automatic commit, push, PR, merge, or mainline landing.
- More than two implemented experimental relevance methods.

## Technical decisions introduced by this feature

- **Backend:** Isolated Python service modules because the existing backend is Python and Health Relevance must remain disconnected from production SII paths.
- **Database:** Non-destructive append-only SQLite/runtime schema additions in the existing migration mechanism because finding/evidence workflow already uses scoped runtime persistence; final table design requires Checkpoint 2 approval.
- **Auth:** Reuse request workspace resolution and add an internal permission gate because normal customer roles must not gain access merely through ordinary evidence permissions.
- **Frontend:** None because no customer-facing surface is authorized.
- **Deployment:** None; local/internal experiment only.
- **Dependencies:** Prefer none; both methods should be deterministic and testable with repository-locked dependencies. Any new dependency requires Checkpoint 2 justification.

## Architecture boundary

The feature is a scoped sidecar over existing immutable finding/evidence identities. A validated-outcome service owns outcome eligibility and correction history; a linkage service proves same-scope/system evidence and structural references; two method implementations consume the same frozen contribution dataset; a relevance service writes append-only versions and contribution provenance. An internal benchmark/inspection layer reads those versions. No edge from this sidecar points back into SII, relationship importance, finding creation/classification, behavioral model updates, or customer UI.

## Integration points expected after Checkpoint 2

### Existing files likely modified

- `backend/app/services/runtime_db.py` for approved non-destructive schema additions and indexes.
- `backend/app/models/api_models.py` only if an internal inspection API is approved.
- `backend/app/main.py` or router registration only if a permission-gated internal endpoint is approved.

### New files likely created

- `backend/app/services/validated_outcomes.py`
- `backend/app/services/health_relevance.py`
- one module per selected method, or one module exposing exactly two named method classes
- `backend/app/services/health_relevance_benchmark.py`
- optionally `backend/app/routers/internal_health_relevance.py`
- focused test files for migrations, outcome/linkage, methods, thresholds, benchmarks, provenance, authorization, and tenant isolation

### Existing data reused read-only

- `finding_cases` and `finding_workflow_events`
- `evidence_runs` and Evidence Package v1/correlation projections
- Facility Context v1
- behavioral model/snapshot identities and relationship/signal references
- workspace/dataset scope and audit conventions

### Proposed new tables

- `validated_outcomes`
- `validated_outcome_links`
- `health_relevance_versions`
- `health_relevance_contributions`

No frontend file and no production scoring file should change.

## Phase plan and hard checkpoints

### Phase 1 — audit only (complete)

- Audit existing behavior, data, gaps, reuse, new entities, distinction, bias, isolation, and protected production behavior.
- Produce only this PRD and `.planning/research/internal-health-relevance-audit.md`.
- Stop at Checkpoint 1.

### Phase 2 — model design (not approved)

- Finalize schemas, state representation, the two method specifications, benchmark, thresholds and boundary cases, acceptance criteria, migration/service/auth boundaries, and expected implementation files.
- Do not write migrations or implementation.
- Stop at Checkpoint 2.

### Phase 3 — implementation (not approved)

- Implement only the approved sidecar data model, services, exactly two methods, deterministic benchmark, provenance, and internal inspection capability.
- Do not connect results to production SII, findings, behavioral memory, or customer UI.

### Phase 4 — validation (not approved)

- Run formatting, lint/type checks, migration/auth/isolation/outcome/linkage/sparse/negative/context/contradiction/threshold/version/provenance/confirmation-bias tests, deterministic benchmarks, Citadel QA as applicable, and `git diff --check`.
- Do not deploy or merge.

## Acceptance criteria

The approved implementation must deterministically satisfy:

1. **Repeated validated degradation:** Five validated degradation outcomes repeatedly linked to Relationship R in consistent context and without meaningful contradiction move R beyond insufficient evidence, increase support across versions, and expose every outcome and explanation.
2. **One isolated event:** One confirmed event cannot create strong relevance; uncertainty remains explicit.
3. **Repeated false positives:** Negative evidence accumulates, prevents strong relevance, and does not delete prior positive evidence.
4. **Context specificity:** High-load usefulness remains high-load-only; no global relevance is inferred.
5. **Contradiction:** Approved positive/negative balance in the contradictory band produces contradictory/uncertain state and exposes both sides.
6. **Recovery:** Intervention and return-toward-behavior windows remain linked as association without causal language.
7. **Irrelevant frequent signal:** Frequency without validated outcome association cannot create Health Relevance.
8. **Sparse context:** Narrow, poorly sampled context remains emerging/uncertain until approved context-coverage thresholds pass.

Additional mandatory conditions:

- existing tests have zero new failures;
- type/lint checks have zero new errors;
- migrations are non-destructive and reversible by forward correction;
- authorization and tenant/facility/system isolation tests prove fail-closed behavior;
- two and only two experimental methods execute;
- same frozen benchmark inputs and contribution records are used for both methods;
- all scores/states are reproducible from inspectable inputs and versioned configuration;
- no customer API/UI output contains Health Relevance;
- no SII, finding, evidence-ranking, behavioral-memory, or production prioritization output changes; and
- nothing is deployed, merged, or pushed without separate explicit authorization and direct verification.

## Benchmark evaluation dimensions

Compare the two approved methods on:

- stability under repeated equivalent evidence;
- sparse-data behavior;
- interpretability;
- contradictory evidence;
- context specificity;
- negative-evidence behavior;
- false-positive resistance;
- version-to-version stability; and
- deterministic reproducibility.

The benchmark reports method behavior; it must not silently select a production winner. Any later production use requires a separate approved task.

## End conditions for the full feature

- [ ] Final Phase 2 architecture and thresholds receive explicit approval.
- [ ] Typed validated outcomes preserve scope, validation, provenance, reliability, windows, links, and correction history.
- [ ] Outcome links prove same tenant/facility/system and preserve finding/evidence/structure/model/context lineage.
- [ ] Relevance state versions preserve all required positive, negative, contradictory, context, uncertainty, and provenance components.
- [ ] Exactly two method classes are implemented and run on identical deterministic contribution data.
- [ ] Acceptance cases A-H pass.
- [ ] Authorization, tenant/facility/system isolation, migration, threshold-boundary, versioning, provenance, and confirmation-bias tests pass.
- [ ] Existing tests pass with zero new failures.
- [ ] Typecheck/lint pass with zero new errors.
- [ ] `git diff --check` passes.
- [ ] No customer-facing or production decision behavior changes.
- [ ] No deployment, infrastructure change, automatic merge, or unverified git/remote claim occurs.

## Risks

- Human review after Neraium exposure can create circular confirmation.
- Finding-triggered data can omit stable/no-fault denominators and amplify survivorship bias.
- Duplicate findings/work orders can inflate recurrence.
- Weak facility/asset/signal identity can attach an outcome to the wrong subject.
- Global/default latest-payload keys can break tenant/system isolation.
- Context sparsity can look like strong relevance if generalized globally.
- Outcome text and UI language can overstate validation.
- Reliability weighting can masquerade as probability if not explicitly calibrated.
- Recovery after intervention can be misread as causal.
- An internal endpoint can leak experimental values unless separately permission-gated and response-audited.
- Future consumers may treat experimental state as production authority without a hard architectural disconnect.

## Open questions for Checkpoint 2

1. Which roles may report, validate, correct, and retract each outcome type?
2. Must any outcome types require an independent validator?
3. Which maintenance/inspection systems are approved authoritative sources?
4. What defines one incident for deduplication?
5. What negative/stable exposure source provides the denominator?
6. What context dimensions and coverage are mandatory by system type?
7. What exact configurable state thresholds and boundary cases are approved?
8. How should independently documented versus Neraium-influenced evidence affect eligibility or uncertainty?
9. Is an internal CLI sufficient, or is a permission-gated endpoint required?
10. What retention, redaction, and deletion policy applies to human outcome metadata?
11. Which signal/relationship identity versions must an outcome link bind to?
12. What explicit evidence would ever justify an evidence-channel subject type?

## Checkpoint 1 recommendation

Proceed to Phase 2 design only after explicit approval. The capability is distinct, but its value depends on creating a trustworthy outcome and linkage boundary first. No existing feedback count, relationship score, or telemetry event should be relabeled as Health Relevance.

---HANDOFF---
- PRD: Internal Outcome-Grounded Health Relevance
- Document: `.planning/prd-internal-health-relevance.md`
- Audit: `.planning/research/internal-health-relevance-audit.md`
- Status: needs explicit Checkpoint 1 approval
- Next: Phase 2 model design only after approval
- Reversibility: green — Phase 1 created only the two planning documents
---
