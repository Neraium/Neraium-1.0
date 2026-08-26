# Architecture: Internal Outcome-Grounded Health Relevance

> Feature: Internal Outcome-Grounded Health Relevance
> Date: 2026-08-26
> Status: Checkpoint 2 design; no implementation approved
> Mode: feature
> Authoritative inputs: `.planning/prd-internal-health-relevance.md` and `.planning/research/internal-health-relevance-audit.md`

## 1. Decision summary

Health Relevance remains a separate, internal, outcome-grounded sidecar. It does not replace or modify the existing relationship-importance behavior that serves the System Relevance role, and it does not change behavioral memory, SII, findings, evidence ranking, customer APIs, or customer UI.

The design retains the four approved persistence entities without renaming them:

1. `validated_outcomes`
2. `validated_outcome_links`
3. `health_relevance_versions`
4. `health_relevance_contributions`

The first two are immutable revision ledgers rather than mutable current-state rows. This refines their shape, not their entity boundary. Corrections, retractions, validation decisions, and link changes append revisions. The latest effective revision is resolved deterministically.

Exactly two experimental method classes are selected:

1. Bayesian/shrinkage relevance updating
2. Outcome-conditioned information measure

They consume the same frozen, exact-scope evidence snapshot. No third method, production consumer, broadly exposed HTTP endpoint, frontend surface, or cross-system aggregation is part of this architecture.

All thresholds in this document are **initial conservative experimental values requiring calibration against field outcomes**. They are safety-oriented starting hypotheses, not empirically validated operating constants.

## 2. System boundary

### 2.1 Exact distinction from System Relevance

| Capability | Question | Inputs | Time horizon | Output effect |
|---|---|---|---|---|
| Existing relationship importance / System Relevance | Which current relationship changes deserve attention? | Telemetry relationship change, confidence, persistence, scope, novelty, data quality, metric heuristics | Current analysis | Orders current relationship/finding evidence |
| Behavioral memory | What empirical structure characterizes accepted behavior? | Gated telemetry, modes, signal and relationship history | Model history | Updates expected-behavior memory |
| Internal Health Relevance | Which exact structural subjects repeatedly proved useful across explicitly validated outcomes in this system and context? | Validated outcomes, explicit links, comparison windows, negative evidence, provenance, version identity | Outcome history | Internal experimental evidence profile only |

Health Relevance is genuinely distinct because its truth boundary is a validated real-world outcome rather than telemetry magnitude, current evidence importance, or accepted-operation memory. It remains distinct even when the same relationship ID appears in all three capabilities.

### 2.2 Allowed data flow

```text
existing scoped identity + finding/evidence/model references (read only)
                              |
                              v
validated outcome revisions -> reviewed linkage revisions
                              |
                              v
                 frozen contribution snapshot
                       /              \
                      v                v
             Bayesian method    information method
                       \              /
                        v            v
                  immutable relevance versions
                              |
                              v
                 internal read-only CLI inspection
```

There is deliberately no edge from Health Relevance back to SII, relationship importance, finding creation/classification, evidence ordering, behavioral-model learning, customer APIs, or frontend code.

### 2.3 Non-causal language contract

The service and CLI may state that a subject was `associated_with`, `observed_during`, `observed_before`, `observed_after`, `recurred_with`, or `returned_toward_reference_after` a validated outcome or intervention. They must not state that a signal, relationship, asset, subsystem, repair, or intervention caused an outcome or recovery.

## 3. Key architecture decisions

### 3.1 Persistence shape

**Selected:** four normalized, scope-explicit, append-only entities with revision semantics.

Why:

- preserves exact outcome, link, version, and contribution provenance;
- supports foreign keys and same-scope integrity checks;
- keeps corrections and retractions inspectable;
- makes both experimental methods reproducible from the same inputs; and
- follows existing append-only workflow and audit conventions.

Rejected alternatives:

- **One JSON payload in `latest_payloads`:** rejected because the underlying key space is not an authorization boundary, row-level lineage is weak, and concurrent/versioned contributions are difficult to inspect safely.
- **Mutable outcome and current-relevance rows:** rejected because corrections would erase the evidence state used by prior versions.
- **Embedding all contributions inside `health_relevance_versions`:** rejected because it weakens foreign-key checks, queryable provenance, deduplication inspection, and deterministic method comparison.

### 3.2 Outcome and link revisions

**Selected:** `validated_outcomes` and `validated_outcome_links` each contain a logical ID plus immutable numbered revisions. The effective state is the highest valid revision for that logical ID.

Rejected alternatives:

- **In-place status updates:** lose the exact validation/correction state used by an older relevance version.
- **Separate history tables:** add two more persistence entities without improving the append-only model; the approved four-table boundary can represent revisions directly.

### 3.3 Source authority treatment

**Selected:** preserve categorical authority strata and apply promotion gates, not fractional pseudo-count weights.

Why: no field calibration exists that would justify treating a maintenance record as, for example, 0.8 events and an operator confirmation as 0.3 events. Raw counts stay raw. Primary and supplemental method views remain separate.

Rejected alternatives:

- **Undocumented numeric reliability weights:** would look probabilistic without empirical calibration.
- **Treat all validated sources equally:** would allow confirmation influenced by Neraium to manufacture strong support.
- **Exclude all human validation:** would discard useful but appropriately limited evidence.

### 3.4 Stable-operation denominator

**Selected:** stable/no-fault evidence exists only as an explicit, validated observation unit created under a versioned observation protocol or authoritative inspection. Absence of a finding is never an observation.

Rejected alternatives:

- **No finding means stable:** confounds missing analysis, missing telemetry, suppression, and true stability.
- **Telemetry alone establishes stability:** violates the outcome-validation boundary.
- **Finding-triggered negative feedback only:** leaves survivorship and selection bias unbounded.

### 3.5 Incident deduplication

**Selected:** deterministic exact-key deduplication, possible-duplicate quarantine, and no fuzzy auto-merge.

Rejected alternatives:

- **Text/time/asset similarity merge:** can silently collapse distinct incidents.
- **Count every record independently:** allows one work order represented by several findings to inflate recurrence.
- **Manual-only dedup with no deterministic keys:** produces non-reproducible method inputs.

### 3.6 System/reference version binding

**Selected:** every contribution binds to exact system identity, context schema, subject mapping, evidence package/run identity, behavioral model/reference identity, and a compatibility epoch. Pooling is allowed only inside an explicitly proven compatibility epoch; material changes start a new epoch.

Rejected alternatives:

- **Pool by human-readable system or asset name:** unsafe for tenant isolation and identity drift.
- **Pool every behavioral version automatically:** can hide material schema/configuration changes.
- **Never combine adjacent versions:** preserves safety but discards valid recurrence across explicitly compatible model revisions. Exact source versions remain visible even when the compatibility predicate permits a shared epoch.

### 3.7 Internal inspection surface

**Selected:** a read-only `argparse` CLI over the internal service, with exact workspace/system arguments and existing service-token workspace resolution.

Rejected alternatives:

- **Customer or normal authenticated API:** broadens disclosure and creates an accidental product contract.
- **New internal HTTP router:** unnecessary for the experiment and adds authorization/response-leakage surface.
- **Direct SQL inspection:** bypasses scope validation and provenance rendering rules.

No HTTP route or frontend model is planned. A future endpoint would require separate approval and threat review.

## 4. Final outcome model

### 4.1 Outcome types and structured disposition

The typed outcome vocabulary is:

- `confirmed_maintenance_event`
- `inspection_result`
- `confirmed_fault`
- `confirmed_degraded_condition`
- `repair`
- `component_replacement`
- `operator_confirmed_explanation`
- `return_toward_expected_behavior`
- `expected_no_fault_confirmation`
- `false_positive_not_useful`
- `stable_operation_observation`

`stable_operation_observation` is the only refinement to the Phase 1 type list. It is necessary to distinguish a protocol-complete denominator observation from an incidental no-finding interval. It does not add a fifth entity.

The outcome type alone does not determine a positive or negative contribution. A validator must select a structured `health_disposition` from:

- `degraded`
- `fault_confirmed`
- `expected_behavior`
- `no_fault`
- `not_useful`
- `explained`
- `intervention_recorded`
- `recovery_observed`
- `unrelated_maintenance`
- `no_observed_behavior_change`
- `stable_observation`
- `indeterminate`

For example, a maintenance event is neutral unless the validated disposition and reviewed evidence link establish whether it was related, unrelated, followed by recovery, or followed by no observed behavior change. This prevents maintenance frequency from becoming positive support automatically.

### 4.2 Validation lifecycle

Each logical outcome progresses through appended revisions:

```text
pending -> validated
pending -> rejected
validated -> corrected (new validated revision)
validated -> retracted
validated -> superseded by another logical outcome
```

Only the latest effective `validated` revision is eligible. A correction produces a new relevance input snapshot and version. A retraction excludes the record in the next version; it does not become negative evidence and does not delete the older contribution.

Free text may support an outcome but cannot choose its type, disposition, validation state, source authority, identity, temporal windows, or links.

### 4.3 Provenance categories and authority strata

`provenance_categories_json` is a validated set that can contain:

- `independently_documented_outcome`
- `maintenance_system_sourced`
- `inspection_sourced`
- `retrospective_label`
- `operator_confirmed_after_neraium_review`
- `other_explicitly_validated_human_outcome`

The deterministic authority classification is:

| Tier | Rule | Primary-method eligibility | Promotion effect |
|---|---|---|---|
| A: authoritative independent | Independently documented, stable external record ID, and maintenance/inspection/fault/repair source that existed independently of Neraium review | Yes | Can satisfy authoritative-source gate |
| B: independent validated | Independently documented or independently validated human evidence, but without a Tier A system record | Yes | Can satisfy independence count, but not the Tier A minimum |
| C: limited retrospective | Retrospective label or other human outcome lacking demonstrated contemporaneous independence | Supplemental only | Cannot by itself produce supported relevance |
| D: Neraium-influenced | Operator-confirmed after Neraium review or discovered through the reviewed Neraium finding | Supplemental only | Cannot satisfy independence or method-primary gates |

When categories conflict, the more bias-exposed tier wins unless the source timestamps prove the independent record predated Neraium review. Reporter and validator remain distinct fields even when the same actor performed both roles. Same-actor validation is permitted to remain inspectable but is Tier C or D and cannot independently promote support.

No authority tier is converted into a fractional probability or event count.

### 4.4 `validated_outcomes`

This table is an immutable revision ledger.

| Field group | Required fields and rules |
|---|---|
| Revision identity | `outcome_revision_id` primary key, `outcome_id`, `revision > 0`, `supersedes_revision_id`, unique `(scope_storage_id, outcome_id, revision)` |
| Scope | `scope_storage_id`, `tenant_id`, `facility_id`, `system_id` all required; `asset_equipment_id` nullable only when the outcome is genuinely system-wide |
| Schema/type | `outcome_schema_version`, `outcome_type`, `outcome_family`, `health_disposition`, `validation_status` |
| Time | `occurred_start_at`, `occurred_end_at`, optional versioned `windows_json` for pre-outcome, outcome, post-intervention, recovery |
| Source | `source_category`, `source_system`, `source_record_id`, `source_record_version`, `source_recorded_at`, `source_identity_hash` |
| Actors | `reported_by`, `reported_at`, `validated_by`, `validated_at`, `validation_basis_json` |
| Bias/authority | `provenance_categories_json`, `authority_tier`, `reliability_class`, `reliability_basis_json` |
| Incident | `canonical_incident_key`, `dedup_status`, `possible_duplicate_of_json`, `dedup_basis_json` |
| Stable denominator | `observation_protocol_json` nullable; required for `stable_operation_observation` and protocol-derived no-fault confirmation |
| Metadata | `structured_metadata_json`, `metadata_schema_version`; text fields cannot populate typed fields |
| Audit/idempotency | `actor`, `recorded_at`, `idempotency_key`, `request_fingerprint`; existing `audit_events` records the write action |

Database checks constrain enumerations, JSON validity, time ordering, positive revision numbers, and stable-observation protocol presence. Append-only/no-delete triggers mirror `finding_workflow_events`. Every lookup includes the entire exact scope and system, not the logical ID alone.

### 4.5 Outcome families

Outcome diversity is calculated from versioned semantic families rather than raw enum count:

- `degradation_or_fault`
- `inspection_confirmation`
- `maintenance_or_intervention`
- `repair_or_replacement`
- `recovery`
- `expected_or_no_fault`
- `not_useful_or_false_positive`
- `validated_explanation`

The family mapping is stored in the threshold/method configuration version. Renaming an enum does not silently change historical diversity.

### 4.6 Source interface boundary

Phase 3 may expose only an internal typed service function, not a CMMS/inspection connector:

```text
append_candidate(
  authorized_scope,
  source_envelope,
  typed_outcome_payload,
  actor,
  idempotency_key,
  request_fingerprint
) -> immutable outcome revision
```

`source_envelope` carries source category/system/record identity/version/time and provenance assertions. `typed_outcome_payload` carries explicit enum values, windows, context, asset/system identity, and structured validation metadata. The service validates these fields but does not fetch, poll, infer from, or assign authority to an external system merely because its name is present. A source becomes Tier A only after its source category and independence rules are explicitly configured and versioned. No source integration is implemented in this campaign.

## 5. Final linkage model

### 5.1 Canonical path

```text
outcome revision
  -> link revision
  -> finding case (optional for explicit stable observations)
  -> evidence run + Evidence Package content hash/revision
  -> exact subject identity
  -> exact behavioral/reference/model identity
  -> exact context fingerprint and temporal role
```

A stable observation may have no finding, but it must have an explicit observation protocol and an evaluable evidence/reference window. A positive or negative finding review must link to its canonical finding and evidence identity when those exist.

### 5.2 `validated_outcome_links`

This table is also an immutable revision ledger.

| Field group | Required fields and rules |
|---|---|
| Revision identity | `link_revision_id` primary key, `link_id`, `revision > 0`, `supersedes_revision_id`, unique `(scope_storage_id, link_id, revision)` |
| Outcome | `outcome_id`, `outcome_revision_id`; foreign key to the exact immutable revision |
| Scope | repeated `scope_storage_id`, `tenant_id`, `facility_id`, `system_id`; must exactly equal the outcome and referenced evidence scope |
| Existing lineage | nullable `finding_id`, `evidence_run_id`, `evidence_package_id`, `evidence_package_revision`, `evidence_content_hash` |
| Subject | `subject_type` in `signal`, `relationship`, `asset_equipment`, `subsystem`; `subject_id`, `subject_mapping_version` |
| System/reference binding | `behavioral_model_id`, `behavioral_model_version`, `behavioral_snapshot_id`, `baseline_reference_id`, `baseline_reference_version`, `telemetry_schema_fingerprint`, `system_configuration_fingerprint`, `compatibility_epoch` |
| Context | `context_schema_version`, `context_json`, `context_fingerprint`, `context_episode_id`, `context_source_refs_json` |
| Time | `temporal_role` in pre-outcome, outcome-period, post-intervention, recovery, stable-comparison; `window_start_at`, `window_end_at` |
| Link provenance | `link_origin` in direct-source, human-reviewed, deterministic-reference; `link_basis_json`, `linked_by`, `linked_at`, `retrospective_window_selection` |
| Subject observation | `subject_state` in active-changed, present-aligned, absent-evaluable, not-evaluable; `observation_basis_json` |
| Lifecycle | `link_status` in pending, active, rejected, retracted, superseded; idempotency and request fingerprint |

At least one immutable evidence/reference anchor is required. A generic polymorphic target ID is not used because it cannot provide meaningful SQLite foreign-key integrity. Explicit nullable identifiers make each hop inspectable, and the service checks the required combination for each link type.

Link confidence is categorical (`direct`, `reviewed`, `limited`) with a textual/structured basis; it is not multiplied into evidence as a numeric probability. `limited` links remain inspectable but cannot contribute to a supported state.

### 5.3 Temporal roles

- `pre_outcome`: subject observation before the validated outcome window.
- `outcome_period`: overlap with the validated outcome window.
- `post_intervention`: after a recorded intervention.
- `recovery`: return toward the exact cited learned reference after intervention.
- `stable_comparison`: explicit protocol-complete expected/no-fault observation.

Temporal adjacency changes association metadata only. It never changes language to a causal claim.

## 6. Stable-operation denominator and observation rule

### 6.1 Eligible denominator unit

One denominator unit is one **predeclared, non-overlapping observation window** for the exact scope, system, compatibility epoch, context fingerprint, and subject evaluability rule. It is eligible only when all of these are true:

1. a versioned `protocol_id` and `protocol_version` declare the window before evaluation, or an authoritative inspection explicitly validates the window;
2. the expected signal/reference set and sampling cadence are declared;
3. at least 80% of expected samples are present after approved quality filtering;
4. the subject can be classified as active-changed, present-aligned, or absent-evaluable; `not-evaluable` is excluded;
5. operating context and configuration identity are complete;
6. the observation has an explicit validated `stable_operation_observation` or `expected_no_fault_confirmation` outcome revision;
7. overlapping protocol windows collapse to one denominator unit by deterministic window identity; and
8. the record preserves validator, source, protocol completion, missingness, and all exclusions.

The 80% telemetry-completeness value is an initial experimental data-quality floor: it tolerates limited acquisition loss while preventing heavily missing windows from being treated as stable. It must be calibrated by system and protocol before any production use.

### 6.2 Denominator states

For the information method, each eligible observation unit records:

- outcome class: `validated_health_outcome` or `explicit_comparison`;
- subject state: `active_changed` or `not_active_changed`; and
- evaluation status: `eligible` or an explicit exclusion reason.

For the Bayesian method, a comparison window in which the subject is active-changed is negative/counterevidence. A comparison window in which the subject is not active-changed supplies coverage but not a Bayesian negative event. Both remain visible.

No finding, no operator comment, or missing telemetry creates zero denominator units.

## 7. Conservative incident identity and deduplication

### 7.1 Source identity rule

When an authoritative source supplies stable identity, the unique source identity is:

```text
scope_storage_id
+ facility_id
+ system_id
+ source_system
+ source_record_id
+ source_record_version
```

The tuple is hashed only for indexing; the source fields remain inspectable. Re-delivery with the same idempotency key and request fingerprint is a no-op. Same key with a different fingerprint fails.

### 7.2 Canonical incident key

Two validated outcome records share a canonical incident only when all required exact fields match:

- identical scope, facility, and system;
- identical authoritative external incident/work-order ID, or an explicit human adjudication ID;
- compatible outcome family;
- identical asset/equipment identity when either record is asset-specific; and
- overlapping or explicitly linked occurrence windows.

Multiple outcomes may belong to one incident without being duplicates: for example, a fault, repair, and recovery can share an incident key but retain distinct outcome IDs and families. Recurrence counts the incident once; diversity may count the distinct validated families once each.

### 7.3 Uncertain duplicates

Time proximity, text similarity, shared tags, or similar evidence is never enough to merge. Such records receive `possible_duplicate`, point to candidates, and remain separate immutable records. They are excluded from promotion and recurrence until an explicit adjudication revision marks them distinct or assigns a canonical incident key. The exclusion is a contribution with reason `possible_duplicate_unresolved`, not a silent drop.

Confirmed duplicate source revisions remain preserved, but only the canonical effective outcome contributes per subject/context/method snapshot.

## 8. Identity, context, and version binding

### 8.1 Exact state identity

The state key is:

```text
scope_storage_id
+ tenant_id
+ facility_id
+ system_id
+ subject_type
+ subject_id
+ subject_mapping_version
+ context_fingerprint
+ compatibility_epoch
+ method_class
+ method_version
+ threshold_config_version
```

No query may omit scope, facility, or system. Human-readable names and raw tags are display metadata only.

### 8.2 Compatibility epoch

A compatibility epoch is explicit, versioned evidence that adjacent references can be evaluated together. It requires unchanged:

- `scope_storage_id`, facility, and system identity;
- subject canonical ID and mapping semantics;
- telemetry schema fingerprint for the subject;
- relevant equipment membership;
- context schema and bucket semantics; and
- baseline/behavioral reference semantics.

A material schema change, subject remap, equipment reassignment, configuration change, reference reset, or explicit invalidation creates a new epoch. Evidence does not cross epochs. The new epoch starts at insufficient evidence even if historical epochs were supported.

If exact reference/version identity is missing, the outcome remains in the ledger but its contribution is excluded with `reference_binding_incomplete`. It cannot be placed in an anonymous or default epoch.

### 8.3 Context conditioning

Context fingerprints preserve canonical, versioned values for:

- operating mode;
- load band;
- season;
- staging state;
- environmental band; and
- system configuration fingerprint.

The system-specific context schema declares which dimensions are required and how continuous values are bucketed. `unknown` is an explicit stratum, not a wildcard. No global relevance state is created in this task, and no pooling occurs across context fingerprints.

Context coverage has three inspectable components:

1. **metadata completeness:** percentage of eligible directional/comparison units with all required context dimensions;
2. **episode recurrence:** number of distinct non-overlapping context episodes; and
3. **protocol completion:** completed eligible stable windows divided by predeclared stable windows.

Supported relevance requires at least 80% metadata completeness, at least two context episodes, and at least 80% protocol completion when a stable protocol defines scheduled windows. These are conservative experimental floors, not empirical claims.

## 9. Internal relevance representation

### 9.1 `health_relevance_versions`

One immutable row represents one subject/context/epoch/method result at one input watermark.

| Field group | Required fields |
|---|---|
| Identity | `relevance_version_id`, `state_key_hash`, monotonic `version`, exact scope/system/subject/context/epoch fields |
| Method | `method_class`, `method_version`, `method_config_version`; database check and registry allow only the two selected classes |
| Input snapshot | `input_snapshot_id`, `input_manifest_hash`, `outcome_watermark`, `link_watermark`, `previous_version_id` |
| Counts | raw outcomes, eligible outcomes, canonical incidents, recurrence, positive, negative, neutral, comparison windows, exclusions, duplicate-suppressed records |
| Diversity/context | outcome family counts, context metadata completeness, episode count, protocol completion, temporal consistency |
| Authority | Tier A/B/C/D counts, independent count, Neraium-influenced count, same-actor validation count |
| State | `evidence_state`, `evidence_direction`, `state_reason_codes_json`, `freshness_status` |
| Method result | transparent `method_components_json`, `uncertainty_json`; no required opaque scalar |
| Configuration | outcome schema, context schema, threshold config, authority rules, dedup rules, compatibility rules and hashes |
| Time/provenance | first/last evidence time, computed time, created actor/process, code/build version |

Latest state is queried by `(state key, version DESC)`. No mutable current-state table is added.

### 9.2 `health_relevance_contributions`

Each immutable contribution explains how an exact outcome/link revision was treated by one relevance version.

Required fields include:

- `contribution_id`, deterministically derived from relevance version, outcome revision, link revision, and contribution role;
- exact scope, system, subject, context, and compatibility epoch repeated for defensive checking;
- `relevance_version_id`, `outcome_id`, `outcome_revision_id`, `link_id`, `link_revision_id`;
- canonical incident key and outcome family;
- evidence treatment: `positive`, `negative`, `neutral`, `comparison`, `contradictory`, `excluded`, or `duplicate_suppressed`;
- subject state and temporal role;
- authority tier and provenance categories;
- method input cell/count and method-specific component, if any;
- inclusion/exclusion reason code;
- exact finding/evidence/model/reference hashes; and
- creation process/config/input-manifest hashes.

Positive evidence is never overwritten by a later negative contribution. Retractions and corrections cause a new version whose contribution ledger explains why earlier inputs were excluded or replaced.

### 9.3 Evidence states

The design uses the four required fail-closed states plus one explicit negative-dominant state:

- `insufficient_outcome_evidence`
- `emerging_relevance`
- `supported_relevance`
- `contradictory_evidence`
- `not_supported_by_outcomes`

`not_supported_by_outcomes` is the only state-list refinement. It prevents repeated validated false positives from being mislabeled as merely sparse and prevents negative-dominant evidence from being called “emerging relevance.” It is an evidence result, not a claim that the subject is universally irrelevant.

Every state also carries `evidence_direction` (`positive_dominant`, `negative_dominant`, `mixed`, `indeterminate`) and `freshness_status` (`current`, `stale`, `superseded_epoch`).

## 10. Evidence counting rules

For one state key and frozen snapshot:

- `V` = distinct eligible validated outcome revisions after canonical-incident handling;
- `I` = distinct canonical incident keys;
- `P` = distinct incidents in which the subject is active-changed and the validated disposition is positive support;
- `N` = distinct incidents/windows in which the subject is active-changed and the validated disposition is false-positive, not-useful, expected/no-fault, unrelated, no observed response, or stable comparison;
- `D` = explicit eligible comparison windows, including subject-active and subject-not-active cells;
- `Q_all = P_all / (P_all + N_all)` across every eligible authority tier when the denominator is nonzero;
- `Q_primary = P_primary / (P_primary + N_primary)` across Tier A/B evidence when the denominator is nonzero;
- `F` = distinct eligible outcome families;
- `A` = Tier A outcome count;
- `AB` = Tier A plus Tier B independent outcome count.

One outcome can link to several subjects, but it counts at most once per subject/context/method snapshot. Several findings/packages for one outcome cannot multiply the count. Several outcome types in one incident can increase family diversity, but they cannot increase incident recurrence.

Promotion requires both `Q_primary` and `Q_all` to pass the positive-balance threshold. Contradiction is fail-closed: either the primary evidence or all eligible evidence entering the contradictory band can produce `contradictory_evidence` when that stratum meets the count prerequisites. This keeps Tier C/D evidence from manufacturing support while ensuring lower-authority negative evidence is not silently ignored.

## 11. State machine and initial thresholds

### 11.1 Eligibility gates

Before state evaluation, a contribution must have:

- latest effective `validated` outcome revision;
- latest effective active link revision;
- exact matching scope, facility, system, subject, context, and compatibility epoch;
- resolved canonical incident identity with no unresolved possible duplicate;
- complete source, actor, validation, and authority provenance;
- exact finding/evidence/reference lineage required by its link type;
- an evaluable subject state; and
- no free-text-derived typed fields.

Failure is recorded as an excluded contribution. It never becomes a zero or a negative event.

### 11.2 Threshold configuration v1 proposal

| Threshold | Initial value | Justification and limitation |
|---|---:|---|
| Emerging minimum validated outcomes | `V >= 3` | Prevents one or two incidents from looking learned while permitting early inspection; conservative hypothesis, not field-calibrated |
| Emerging recurrence | `I >= 2` | Requires repetition beyond one incident; still explicitly weak |
| Supported minimum validated outcomes | `V >= 5` | Aligns with acceptance Case A and prevents strong state after a small anecdote; five is not an empirical reliability claim |
| Supported recurrence | `I >= 3` | Requires three distinct incident episodes after deduplication |
| Supported positive balance | `Q_primary >= 0.75` and `Q_all >= 0.75` | Requires positives to outnumber direct counterevidence at least three-to-one in both independent and full evidence views; initial safety margin requiring calibration |
| Contradictory band | `0.40 <= Q_primary <= 0.60` or `0.40 <= Q_all <= 0.60`, with `P >= 2`, `N >= 2`, `P + N >= 5` inside the triggering stratum | Treats a near-even mix as unresolved while requiring both sides and enough directional evidence |
| Negative-dominant unsupported | `Q_primary <= 0.25` or `Q_all <= 0.25`, with `N >= 4`, `I >= 3` inside the triggering stratum | Makes repeated false-positive/no-fault evidence explicit instead of sparse |
| Context metadata completeness | `>= 0.80` | Prevents claims from mostly unknown context; initial data-quality floor |
| Context episode coverage | `>= 2` distinct episodes | Prevents one narrow episode from constituting context support |
| Stable protocol completion | `>= 0.80` | Prevents selective completion of scheduled comparison windows |
| Explicit comparison denominator | `D >= 2` | Positive-only histories cannot become supported; two controls are a minimum safety gate, not adequate calibration |
| Outcome diversity | `F >= 2` positive-support families | A single family can reach emerging but not supported, matching Case A without overstating generality |
| Independent evidence | `AB >= 2`, including `A >= 1` | Requires independent recurrence and at least one higher-authority maintenance/inspection/fault/repair record |
| Context schema | all configured required dimensions present for at least 80% of eligible units | Unknown is a separate context and caps state below supported |
| Bayesian method support | primary 90% credible lower bound `>= 0.60` | Conservative evidence-strength check; must be benchmark-calibrated |
| Information method support | adjusted normalized information `>= 0.10` and above the deterministic 95th-percentile permutation null | Combines a minimum effect-size hypothesis with a false-positive screen; both values are experimental |

### 11.3 State evaluation order

1. If identity, scope, reference binding, context schema, or validation provenance is incomplete, state is `insufficient_outcome_evidence`.
2. If `V < 3` or `I < 2`, state is `insufficient_outcome_evidence`.
3. If contradiction prerequisites hold and either `Q_primary` or `Q_all` is between 0.40 and 0.60 inclusive, state is `contradictory_evidence`.
4. If the negative-dominant threshold holds, state is `not_supported_by_outcomes`.
5. If every supported count, recurrence, balance, context, denominator, diversity, authority, and selected-method threshold passes, state is `supported_relevance`.
6. Otherwise state is `emerging_relevance`, with reason codes naming every failed supported gate.

Thus five same-family degradation outcomes advance beyond insufficient but remain emerging until diversity and comparison gates pass. A strong-looking method statistic cannot bypass a count, authority, context, or denominator gate.

### 11.4 Threshold boundary cases

Each test isolates the named gate while all other gates are passing.

| Gate | Just below | At/just above | Expected transition |
|---|---|---|---|
| Emerging outcomes | `V=2` | `V=3` | insufficient -> emerging |
| Emerging recurrence | `I=1` | `I=2` | insufficient -> emerging |
| Supported outcomes | `V=4` | `V=5` | emerging -> supported if all other gates pass |
| Supported recurrence | `I=2` | `I=3` | emerging -> supported |
| Positive balance | `Q=0.7499` | `Q=0.7500` | emerging -> eligible for supported |
| Contradictory lower edge | `Q=0.3999` | `Q=0.4000` | negative/mixed result -> contradictory when count prerequisites pass |
| Contradictory upper edge | `Q=0.6000` | `Q=0.6001` | contradictory -> emerging mixed |
| Negative-dominant balance | `Q=0.2501` | `Q=0.2500` | emerging mixed -> not supported when `N` and `I` pass |
| Negative count | `N=3` | `N=4` | emerging negative -> not supported |
| Context completeness | `0.7999` | `0.8000` | emerging -> eligible for supported |
| Context episodes | `1` | `2` | emerging -> eligible for supported |
| Stable protocol completion | `0.7999` | `0.8000` | emerging -> eligible for supported |
| Comparison denominator | `D=1` | `D=2` | emerging -> eligible for supported |
| Outcome diversity | `F=1` | `F=2` | emerging -> eligible for supported |
| Independent evidence | `AB=1` | `AB=2` | emerging -> eligible for supported, still requires `A>=1` |
| Tier A evidence | `A=0` | `A=1` | emerging -> eligible for supported |
| Bayesian lower bound | `0.5999` | `0.6000` | emerging -> eligible for Bayesian-supported |
| Information floor | `0.0999` | `0.1000` | emerging -> eligible for information-supported if null test also passes |
| Permutation screen | equal to null 95th percentile | strictly greater than null 95th percentile | emerging -> eligible for information-supported |
| Data completeness per denominator window | `0.7999` | `0.8000` | window excluded -> eligible window |

Discrete production fixtures will use integer contingency tables; direct state-evaluator unit tests may inject exact decimal summaries to prove inclusive/exclusive boundaries.

## 12. Staleness and decay

Evidence is never numerically decayed or deleted in this experiment. No field evidence supports a decay half-life, and silently weakening historical facts would make versions difficult to reproduce.

Instead:

- a version is `current` through 180 days after its latest eligible outcome or comparison window;
- it is `stale` immediately after 180 days without new eligible evidence;
- staleness is a qualifier and inspection warning, not a rewritten historical state;
- a stale version cannot be described as evidence of current health and cannot be selected for any future production action;
- a material identity/reference change sets the older epoch to `superseded_epoch`; the new epoch starts insufficient; and
- new eligible, corrected, or retracted evidence creates a new version and recomputes freshness.

The 180-day default is an initial experimental review horizon chosen to force periodic revalidation without pretending old evidence is false. It must be replaced by a system/context-specific cadence after field calibration. Boundary tests use exactly 180 days (`current`) and 180 days plus one microsecond (`stale`). Seasonal contexts remain separate and do not justify cross-season pooling.

## 13. Version-update rules

A new pair of method versions is created only when the frozen input or interpretation changes:

- a validated outcome revision becomes eligible, corrected, retracted, rejected, or superseded;
- a link revision becomes active, corrected, retracted, or superseded;
- a possible duplicate is adjudicated;
- a context mapping or compatibility epoch changes;
- the outcome-family, authority, threshold, denominator, method, or schema configuration changes; or
- an explicit recomputation request cites a new code/build version.

No version is created when the input manifest hash, all configuration hashes, code version, and state key are identical. Concurrent creation uses a transaction and unique `(state_key_hash, version)` constraint. Both methods receive the same `input_snapshot_id` and input manifest. They create separate relevance versions with the same source watermark.

Every new version points to `previous_version_id`. Contributions are regenerated from the frozen manifest rather than incrementally mutating old rows. This is intentionally less storage-efficient but deterministic and inspectable at experimental scale.

Corrections and retractions never rewrite prior versions. A retracted positive is excluded in the next snapshot, not converted to a negative. Negative evidence must itself be an explicitly validated outcome/observation.

## 14. Exactly two experimental methods

### 14.1 Shared method contract

Both classes implement one internal contract:

```text
evaluate(frozen_snapshot, method_config) -> components, uncertainty, contributions
```

The registry has a hard allowlist containing exactly:

- `bayesian_shrinkage_v1`
- `outcome_conditioned_information_v1`

The snapshot owns eligibility, deduplication, scope, context, authority, and cell classification. Methods cannot query the database independently, relink evidence, or change denominators. This guarantees an identical evidence basis.

### 14.2 Method 1: Bayesian/shrinkage relevance updating

Primary analysis uses only Tier A and Tier B evidence. Tier C and D evidence is reported in a supplemental sensitivity posterior and cannot promote a supported state.

For subject-active directional incidents:

```text
prior: Beta(2, 2)
posterior: Beta(2 + P_primary, 2 + N_primary)
```

The symmetric Beta(2,2) prior is a transparent, mildly skeptical experimental prior that shrinks one-event histories toward indifference. It is not a production-calibrated prior. The result exposes posterior parameters, mean, median, 90% credible interval, prior sensitivity, raw primary counts, supplemental counts, and every contribution. Existing SII confidence values and source reliability labels never become likelihoods.

Supported relevance requires the common state gates plus a primary 90% credible lower bound of at least 0.60. This method is expected to behave well under sparse evidence and contradiction, but it does not directly measure discrimination against subject-absent comparison windows; that limitation is why the second method is evaluated.

### 14.3 Method 2: outcome-conditioned information measure

Within an exact context and compatibility epoch, build this transparent 2x2 table:

| | Validated health outcome | Explicit stable/negative comparison |
|---|---:|---:|
| Subject active-changed | `a` | `b` |
| Subject not active-changed but evaluable | `c` | `d` |

`not-evaluable` windows are excluded with reasons. Counts are canonical observation units, not telemetry sample counts.

The method applies Jeffreys smoothing (`0.5` per cell), computes mutual information, and normalizes by validated-outcome entropy. It reports the unsmoothed table, smoothed table, entropies, raw and adjusted normalized information, effective sample size, exclusion counts, and uncertainty. A deterministic fixed-seed permutation procedure builds the no-association reference; the seed, iteration count, ordering, and algorithm version are stored. No association is described as causal.

Supported relevance requires all common state gates, adjusted normalized information of at least 0.10, and an observed result strictly above the deterministic 95th-percentile permutation null. The 0.5 smoothing, 0.10 floor, and 95th-percentile screen are experimental choices requiring benchmark and field calibration.

### 14.4 Comparison dimensions

The deterministic benchmark compares, without choosing a production winner:

- state stability as equivalent evidence is appended;
- sparse-data uncertainty;
- inspectability of each contribution;
- response to mixed positive and negative evidence;
- context-specific behavior;
- stable/no-fault denominator use;
- resistance to frequent but uninformative subjects;
- sensitivity to Tier C/D evidence;
- correction/retraction behavior; and
- version-to-version deterministic reproducibility.

Documentation-only, not implemented: survival/time-to-event association, hierarchical models, standalone recurrence weighting, and precision/recall contribution.

## 15. Service boundaries

### 15.1 Validated outcome service

Responsibilities:

- validate typed input and exact scope;
- append outcome revisions with existing idempotency/audit conventions;
- derive categorical authority from inspectable provenance rules;
- resolve latest effective revisions;
- apply deterministic source identity/dedup statuses; and
- expose frozen eligible outcome records to the relevance service.

It does not ingest from CMMS, inspection, or other external systems in this task. Future adapters must call its typed interface and require separate approval.

### 15.2 Linkage service

Responsibilities:

- append and resolve link revisions;
- verify outcome, finding, evidence, subject, facility, system, context, and reference identity on both ends;
- classify temporal role and subject evaluability without causal wording;
- quarantine incomplete or possible-duplicate records; and
- reuse existing evidence/finding lookup and hash conventions.

### 15.3 Relevance service

Responsibilities:

- build one frozen input manifest per exact state key;
- enforce common eligibility/count/context/authority/denominator gates;
- invoke the exactly two hard-allowlisted methods;
- append versions and contributions transactionally;
- resolve latest authorized versions; and
- render provenance-safe internal inspection output.

It has no import or call path from production SII, finding, evidence-ranking, or behavioral-memory services.

### 15.4 Benchmark service

Responsibilities:

- load deterministic synthetic fixtures;
- run both methods on identical frozen snapshots;
- assert state, counts, provenance, uncertainty, and non-causal language;
- compare stability metrics; and
- emit a local machine-readable and human-readable report without changing product state.

## 16. Authorization and isolation model

### 16.1 Reused controls

- `DatasetScope` and `scope_storage_id` remain the tenant/workspace storage boundary.
- `resolve_workspace_context(..., auth_source="service_token")` and the existing exact workspace allowlist provide the internal CLI workspace gate.
- current opaque-not-found behavior is reused for unauthorized or mismatched resources.
- `audit_events`, request IDs, idempotency-key semantics, evidence hashes, and append-only triggers are reused.
- existing `finding_cases`, `evidence_runs`, Facility Context, and behavioral references remain read-only identity/lineage sources.

No duplicate identity registry, audit ledger, permission database, or idempotency subsystem is introduced.

### 16.2 Internal service rules

- Every read/write method receives an already resolved immutable `DatasetScope`, exact `facility_id`, and exact `system_id`.
- Queries include `scope_storage_id`, tenant, facility, and system predicates even when a globally unique logical ID is supplied.
- Links fail if either end has missing or unequal scope/system identity.
- Background or benchmark work carries and revalidates an immutable scope envelope before opening scoped records.
- Collection/list operations require exact system and context; no all-tenant, all-facility, fleet, or cross-system listing exists.
- Matching raw tags, names, subject IDs, or hashes never grant access.
- Unauthorized and nonexistent IDs return the same opaque result.

The action matrix reuses the existing `viewer`/`operator`/`admin` role ordering but adds no new role or permission store:

| Action | Required existing context |
|---|---|
| Append a pending candidate through the internal service | `service_token` auth source, existing `admin` role, exact allowlisted workspace |
| Validate, correct, retract, supersede, or adjudicate a duplicate | `service_token` auth source, existing `admin` role, exact allowlisted workspace, named actor and basis |
| Build relevance versions/benchmarks | internal process carrying the previously authorized immutable scope envelope |
| Inspect through CLI | `service_token` auth source, existing `admin` role, exact allowlisted workspace, exact system/context |
| Normal customer session or public-readonly request | no access |

Reporter/validator separation is preserved rather than globally mandated. If the same actor reports and validates, the outcome is capped at Tier C/D and cannot satisfy independent-evidence gates. Tier A requires a pre-existing independent source record plus an explicit validation actor/basis.

### 16.3 CLI rules

The planned CLI is read-only. It requires explicit workspace, facility, system, subject type, subject ID, context, and method arguments. It resolves an existing service identity and exact workspace allowlist before accessing data. It cannot list workspaces, discover systems, write outcomes, change validation, trigger production jobs, or expose results over HTTP.

Normal customer session and public-readonly auth paths do not reach Health Relevance inspection. No frontend or router registration changes are expected.

## 17. Migration plan for Phase 3, if approved

The next runtime migration would be `012_internal_health_relevance` in the existing `RUNTIME_SCHEMA_MIGRATIONS` mechanism.

It would:

1. create the four new tables only;
2. add enum/JSON/time/revision constraints, explicit scope columns, composite uniqueness, and foreign keys where SQLite supports exact existing identities;
3. add scope/system/state-key/version/source-identity/input-snapshot indexes;
4. add no-update/no-delete triggers to all four tables;
5. add no Health Relevance columns to existing production tables;
6. perform no backfill from finding feedback, evidence projections, adaptive learning, telemetry, or behavioral events; and
7. record the migration only after the transactional schema succeeds.

The migration is non-destructive. Rollback is by forward correction/feature disuse, not destructive table removal. Empty and migration-011 databases must converge to the same schema. No production database is touched during this campaign.

Suggested indexes:

- outcome latest revision by exact scope/system/outcome/version;
- unique authoritative source identity within exact scope/system;
- outcome status/time and canonical incident within exact scope/system;
- link latest revision by exact scope/system/link/version;
- link by outcome revision and subject/context/epoch;
- relevance latest version by exact state key/version;
- relevance by shared input snapshot and method;
- contributions by relevance version and by exact outcome/link revision.

## 18. Deterministic benchmark and acceptance cases

All fixtures use synthetic tenant/facility/system IDs, fixed timestamps, fixed context/reference versions, fixed method seeds, and no network or production data.

| Case | Fixture | Required assertions |
|---|---|---|
| A: repeated degradation | Five validated degradation outcomes across at least three incidents, Relationship R active in consistent context, no direct counterevidence | State advances beyond insufficient; support/version history increases; all five outcomes visible; if only one family is present it remains emerging with diversity reason |
| B: isolated event | One confirmed event | Insufficient, explicit uncertainty, no strong state in either method |
| C: repeated false positives | Repeated validated not-useful/false-positive outcomes involving R | Negative evidence retained; not-supported or emerging-negative state; positives remain visible |
| D: context specificity | R informative only in high-load context | High-load state only; normal-load and global states absent |
| E: contradiction | Positive and negative evidence at `Q=0.40`, `0.50`, and `0.60` with count prerequisites | Contradictory state; both sides and inclusive boundaries visible |
| F: recovery | Intervention plus validated return toward cited learned reference | Post-intervention/recovery linkage retained; association-only language; no causal claim |
| G: frequent irrelevant signal | Signal S active frequently in both outcome and explicit comparison windows | No supported relevance; information measure near null; frequency alone has no effect |
| H: sparse context | Positive evidence in one narrow episode or below 80% context completeness | Emerging/insufficient with exact context-coverage reason |
| I: provenance authority | Same evidence counts once as Tier A/B and once as Tier D-only fixture | Independent fixture may satisfy authority gate; Tier D-only fixture is capped emerging |
| J: explicit stable denominator | One fixture has no findings but no protocol; another has two validated protocol windows | First adds no denominator; second adds exactly two explicit comparison units |
| K: deduplication | Exact repeated source record, three related outcome types in one incident, and one fuzzy possible duplicate | Exact redelivery no-op; recurrence is one incident; families remain distinct; fuzzy candidate is quarantined |
| L: identity/version binding | Same R ID across compatible and materially changed model/reference versions | Compatible versions share only an approved epoch; material change starts an insufficient new epoch; no silent blend |
| M: correction/retraction | Positive outcome is corrected then retracted | Immutable prior versions remain; next version excludes it rather than turning it negative |
| N: staleness | Last eligible evidence exactly 180 days old and then 180 days plus one microsecond | Current at boundary; stale immediately above; historical state unchanged |
| O: source replay/idempotency | Same source identity/key and same/different request fingerprint | Same payload is no-op; different payload fails and is audited |
| P: isolation | Same logical IDs in two scopes/facilities/systems | No cross-scope read/link/version; opaque failure; no aggregation |

Threshold tests in section 11.4 are additional mandatory unit fixtures, not replacements for A-P.

### 18.1 Method comparison outputs

The benchmark report contains per case and method:

- state and reason codes;
- raw/eligible/deduplicated counts;
- context and authority gates;
- positive, negative, comparison, neutral, excluded, and duplicate-suppressed contributions;
- method components and uncertainty;
- input manifest/config hashes;
- deterministic repeat-run equality;
- change from prior version; and
- non-causal language lint result.

It does not select a production method. A later decision may say which method performed better experimentally, but production influence remains a separate approval.

## 19. Acceptance criteria for Phase 3/4

- All benchmark cases A-P and every threshold boundary test pass deterministically.
- Exactly two method classes are registered and executed.
- Both methods consume the same frozen input snapshot and preserve exact contribution provenance.
- One event cannot exceed insufficient evidence.
- Five repeated same-context outcomes advance beyond insufficient without bypassing diversity, authority, denominator, or method gates.
- Explicit negative evidence accumulates; absence of findings does not.
- Context and materially different reference epochs never pool.
- Tier D operator-after-review evidence cannot independently produce supported relevance.
- Corrections/retractions and duplicate handling remain append-only and reproducible.
- Authorization tests prove tenant, facility, system, subject, and context isolation with opaque failures.
- Migration tests prove empty/011 upgrade, idempotence, constraints, indexes, triggers, and no existing-table semantic changes.
- Provenance inspection reconstructs every state from exact outcome/link revisions and configuration.
- No HTTP customer response, frontend output, SII result, finding, evidence order, or behavioral-memory result changes.
- Existing repository tests have zero new failures; lint/type/import checks have zero new errors; `git diff --check` passes.
- No deployment, infrastructure mutation, production database change, commit, push, PR, or merge occurs without separate authorization.

## 20. Expected implementation file tree

Only these files are expected to be created or modified after Checkpoint 2 approval:

```text
backend/
  app/
    services/
      runtime_db.py                                      [modify: migration 012 only]
      validated_outcomes.py                              [new]
      health_relevance.py                                [new]
      health_relevance_methods.py                        [new: exactly two method classes]
      health_relevance_benchmark.py                      [new]
scripts/
  inspect_health_relevance.py                            [new: read-only internal CLI]
tests/
  fixtures/
    health_relevance_benchmark.json                      [new]
  test_health_relevance_migrations.py                    [new]
  test_validated_outcomes.py                             [new]
  test_validated_outcome_links.py                        [new]
  test_health_relevance_state_machine.py                 [new]
  test_health_relevance_methods.py                       [new]
  test_health_relevance_benchmark.py                     [new]
  test_health_relevance_authorization.py                 [new]
  test_health_relevance_provenance.py                    [new]
```

No `backend/app/main.py`, router, API model, frontend, SII, relationship-baseline, finding-classification, evidence-ranking, behavioral-memory, deployment, or infrastructure file is expected to change.

## 21. Component breakdown

| Component | Owns | Depends on | Must not do |
|---|---|---|---|
| `validated_outcomes.py` | typed revision lifecycle, authority, exact dedup, idempotency | runtime DB, DatasetScope, audit events | source integration, free-text labeling, scoring |
| `health_relevance.py` | links, frozen snapshot, common gates, versions, contributions, inspection model | validated outcomes, existing read-only finding/evidence/identity lookups | modify findings/SII/memory; cross-system queries |
| `health_relevance_methods.py` | exactly two pure evaluators | frozen snapshot contract only | DB access, linking, source weighting invention, third method |
| `health_relevance_benchmark.py` | deterministic synthetic evaluation/report | service and two methods | production data, production winner selection |
| `inspect_health_relevance.py` | exact-scope read-only provenance view | existing service-token workspace resolution, relevance service | HTTP exposure, writes, discovery/list-all |
| `runtime_db.py` migration | four tables, indexes, constraints, append-only triggers | existing migration ledger | backfill, existing semantic changes |

## 22. Phased implementation plan after approval

### Phase 0: Baseline and boundary proof

Work:

- capture repository/branch/status/remote evidence;
- record targeted existing test baseline;
- add an import-dependency guard plan proving no production module imports Health Relevance; and
- verify no implementation files are already modified by unrelated work.

Machine-verifiable end conditions:

- `git status --short --branch` and `git remote -v` recorded;
- targeted existing finding/evidence/workspace/migration tests pass;
- no unrelated staged path exists;
- no new type/import errors; and
- existing tests have zero new failures.

### Phase 1: Schema and immutable contracts

Depends on: Phase 0.

Work:

- implement migration 012 and typed internal contracts;
- add constraints, indexes, triggers, and migration tests; and
- prove no backfill or existing-table mutation.

Machine-verifiable end conditions:

- empty and migration-011 databases converge;
- repeat initialization is idempotent;
- update/delete trigger tests fail closed;
- cross-scope composite uniqueness and FK tests pass;
- no existing schema semantics change;
- no new type/import errors; and
- existing tests have zero new failures.

### Phase 2: Outcome and linkage services

Depends on: Phase 1.

Work:

- implement immutable outcome/link revisions, authority strata, exact dedup, idempotency, audit reuse, and scope/reference checks;
- implement explicit stable observation protocol validation; and
- exclude incomplete/free-text/telemetry-only candidate labels.

Machine-verifiable end conditions:

- outcome lifecycle, correction, retraction, idempotency, dedup, stable-denominator, and linkage tests pass;
- tenant/facility/system mismatch tests fail opaquely;
- no arbitrary note produces a typed validated outcome;
- no new type/import errors; and
- existing tests have zero new failures.

### Phase 3: Frozen snapshot and state machine

Depends on: Phase 2.

Work:

- implement exact state keys, compatibility epochs, context conditioning, common evidence counts, thresholds, freshness, versions, and contribution ledgers.

Machine-verifiable end conditions:

- every section 11.4 boundary test passes;
- correction/retraction/version-update/no-op rules pass;
- context and material-version non-pooling tests pass;
- repeated false-positive and operator-only histories cannot become supported;
- no new type/import errors; and
- existing tests have zero new failures.

### Phase 4: Exactly two methods

Depends on: Phase 3.

Work:

- implement the Bayesian and information evaluators only;
- enforce hard registry cardinality of two; and
- preserve primary/supplemental provenance and deterministic uncertainty.

Machine-verifiable end conditions:

- registry test equals the exact two approved method IDs;
- both consume identical input snapshot hashes;
- sparse, negative, contradiction, context, irrelevant-frequency, and repeat-run tests pass;
- no method accesses persistence directly;
- no new type/import errors; and
- existing tests have zero new failures.

### Phase 5: Benchmark and internal inspection

Depends on: Phase 4.

Work:

- implement benchmark A-P and boundary fixtures;
- implement exact-scope read-only CLI; and
- add provenance reconstruction and non-causal-language checks.

Machine-verifiable end conditions:

- all A-P benchmark assertions pass twice with byte-equivalent normalized output;
- CLI rejects missing scope/system/context and unauthorized workspace;
- CLI has no write subcommand and no HTTP registration exists;
- provenance reconstructs each state from stored revisions/config;
- no new type/import errors; and
- existing tests have zero new failures.

### Phase 6: Validation only

Depends on: Phase 5.

Work:

- run formatting, focused and full test/lint/type/build checks, migration/auth/isolation suites, deterministic benchmark, Citadel QA applicability review, and diff hygiene;
- inspect every changed/staged path; and
- report git state without committing, pushing, merging, or deploying unless separately authorized.

Machine-verifiable end conditions:

- relevant focused pytest suites pass;
- `./scripts/validate_repo.sh` passes or any environment-only unavailable check is reported with exact evidence;
- benchmark outputs are deterministic;
- import/dependency guard proves no production consumer edge;
- `git diff --check` passes;
- no secret, cache, screenshot, runtime database, generated state, or unrelated path is included;
- no new type errors and existing tests have zero new failures; and
- direct git/remote checks support every reported repository-state claim.

## 23. Dependency graph

```text
Phase 0 baseline
      |
      v
Phase 1 schema/contracts
      |
      v
Phase 2 outcomes + links
      |
      v
Phase 3 snapshot + state machine
      |
      v
Phase 4 exactly two methods
      |
      v
Phase 5 benchmark + read-only CLI
      |
      v
Phase 6 validation
```

The method implementations are parallel to one another within Phase 4 but share one approved snapshot contract. The CLI waits for the relevance read model. No phase depends on a frontend, router, source-system integration, infrastructure, or production consumer.

## 24. Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Confirmation after Neraium review | Circular evidence appears strong | Authority strata, primary/supplemental separation, Tier D promotion cap |
| Missing stable denominator | Survivorship bias | Explicit protocol/inspection observation units; silence yields zero units |
| Duplicate incidents | Inflated recurrence | Exact source keys, canonical incidents, possible-duplicate quarantine |
| System/reference identity drift | Evidence blends across materially different systems | Exact scope/reference fields, compatibility epochs, fail-closed missing version |
| Context sparsity | Narrow mode appears general | No global state, exact fingerprints, coverage and episode gates |
| Reliability weights look probabilistic | False precision | Categorical strata and hard gates; no fractional counts |
| Recovery language becomes causal | Misleading internal conclusions | Association-only vocabulary and benchmark language lint |
| Internal values leak to customers | Unapproved product semantics | Read-only CLI, no router/frontend/API model, dependency guard |
| Thresholds are mistaken for validated science | Overconfidence | Versioned configs, explicit experimental labels, boundary tests, calibration requirement |
| Stale evidence is treated as current | Historical relevance misused | Visible freshness qualifier and no current-health language |
| Corrections erase history | Irreproducible results | Immutable revisions, frozen manifests, append-only versions/contributions |
| Method implementation expands | More than two experiments | Exact registry check and file-level ownership |

## 25. Unresolved questions requiring later evidence, not Phase 2 invention

These do not block the internal design but cap evidence at emerging until answered:

1. Which named maintenance and inspection sources are approved as Tier A?
2. Which system-specific context dimensions and observation protocols are authoritative?
3. What field-calibrated thresholds should replace the conservative v1 defaults?
4. What system-specific freshness cadence should replace the 180-day default?
5. What human-outcome retention/redaction rules apply beyond existing audit retention?
6. Which material reference changes can receive an approved compatibility-epoch mapping?
7. Who operationally adjudicates possible duplicates and corrections?

No source integration, retention-system change, or cross-system compatibility inference is authorized in this task.

## 26. Future integration boundary

Documentation only: Health Relevance might later inform evidence ranking, investigation/search-space prioritization, compute allocation, tie-breaking, or deeper-analysis selection. Each would require a separate approved production task, calibration evidence, safety review, customer-semantics review, and explicit integration architecture.

Cross-system or fleet intelligence is not designed or authorized here. Silence never authorizes pooling.

---HANDOFF---
- Architecture: Internal Outcome-Grounded Health Relevance
- Document: `.planning/architecture-internal-health-relevance.md`
- Status: Checkpoint 2 design awaiting explicit approval
- Selected methods: Bayesian/shrinkage and outcome-conditioned information; exactly two
- Persistence: four approved append-only entities retained
- Interface: internal read-only CLI; no HTTP or frontend
- Next: Phase 3 implementation only after explicit approval
- Reversibility: green — Phase 2 adds one planning document only
---
