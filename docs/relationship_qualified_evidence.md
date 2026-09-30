# Conditional relationship qualification

`evaluate_sii(..., relationship_acquisition_profile=profile)` admits a caller-declared
acquisition model. This optional argument is independent of telemetry columns and
does not relax the paired boundary's timestamp, units, size, or numeric checks.
It is not an attestation that independence is true. Unknown/invalid assumptions
produce limited qualification; no row-count or value-uniqueness fallback exists.

The old votes, eight-observation/30-day horizon, six supporters, direction
agreement and `persistence_factor` remain descriptive. Their original result is
`directional_persistence_supported`. `qualified_persistence_supported`,
`temporal_persistence_supported` and `persistent_relationship_change` require
qualified support. Existing abrupt and relationship-strength promotion gates are
unchanged. Limited qualification alone does not suppress the abrupt route.

## Input profile

Version `relationship-acquisition.v1` requires:

* `assessment_id`, `acquisition_profile_id`, `independence_basis`: nonempty IDs and
  a documented justification for independent acquisition groups conditional on context.
* `dependence_assumption`: `independent_groups_conditional_on_context_and_schedule`.
* `schedule_assumption`: `predeclared_noninformative`.
* `coverage_period_seconds`: positive finite operating coverage period T.
* `pairs`: predeclared unique column/context pairs, defining assurance multiplicity.

Each pair has `columns` (two names), `signal_units`, `signal_bounds` (finite
instrumentation bounds in those units), `bounds_basis` (instrumentation specification),
and `context`: `{context_id, basis, selection}`. `selection` must equal the existing
producer's exact selection descriptor: `{}` for a declared homogeneous global
population, or `{mode_id, features}` for the existing like-mode selection.
The engine does not assign or infer the acquisition model's context.

Each pair also contains `reference` and an ordered `comparisons` array. Each
window declares `start`, `end`, `source_locator` (immutable source), and ordered
`observations`: `{timestamp, acquisition_id, group_id}` for every selected row.
Each comparison has a unique `slot_id`; its array position fixes its budget.
Reference observations additionally have `epoch_id`, with `reference.epochs`
declaring `{epoch_id,start,end}`. At least two nonoverlapping complete epochs are
required. Every row belongs to exactly one epoch. Acquisitions and coverage must
match the declared schedule exactly. Reference coverage is at least 2T and each
epoch/comparison at least T. Values may repeat; acquisition IDs must not repeat.
An independence group may contain arbitrarily dependent readings, including
readings spanning reference epochs. It cannot provide new comparison support
after being used in the reference or an earlier comparison.

Missing rows/values, invalid times, unassigned reference rows, unknown bounds or
units, and invalid profiles fail qualification. Existing paired validation may
reject malformed telemetry before qualification. No interpolation is performed.

## Calculation and immutable reference

For group counts n_b and N rows, K_eff = N² / sum(n_b²). With assurance budget a,
epsilon = sqrt(log(10/a)/(2 K_eff)). Bounds-normalized X,Y in [0,1] yield simultaneous
intervals for X,Y,X²,Y²,XY. The implementation outward-rounds normalization,
summation, radius, variance/covariance and correlation interval arithmetic;
variance upper bounds are capped at 1/4. Undefined variance is insufficient;
unresolved positive variance is limited.

The assessment budget is 1/20, allocated equally among P pairs. The pooled
reference receives 1/(80P); each of K epochs receives 1/(80PK); comparison slot j
receives 1/(40Pj(j+1)). These are conditional statistical bounds, not probabilities
of faults or product false-positive rates. Acquisition profiles and slots must
be declared before outcomes are examined; caller state must be carried forward.

A sufficient reference has complete valid inputs, existing reference quality
gates, pooled interval width <= 0.15, all epoch intervals defined, and no epoch
difference interval entirely above +0.15 or below -0.15. Epoch equivalence is
recorded, not required. The immutable comparison envelope is the hull of the
pooled and all epoch intervals. It describes declared historical populations;
it does not certify stationarity or finer-scale stability.

Reference quality is assessed with the existing baseline/data-quality and sensor
health routines using the reference alone. It is never improved by comparisons.
The reference estimate, epoch intervals, differences, incompatibility witnesses,
envelope, exact input/profile identities, assurance allocation and quality are
calculated once per caller-carried reference identity. Subsequent calls check
the supplied reference/profile identity and reuse the stored reference evidence.
Changing identity with a retained qualification ledger fails closed.

Every comparison interval [L,U] is contrasted with the full frozen envelope
[R_L,R_U], giving [L-R_U,U-R_L]. A qualified direction requires this entire interval
to clear +0.15 or -0.15 and existing quality/eligibility gates. Missing scheduled
windows remain neutral in the qualified horizon. Identical retries add nothing;
conflicting/old retries and overlapping/reused acquisitions cannot qualify.
The retained comparison evidence includes the eligibility, confidence and quality
values used at admission. Every qualified vote must still satisfy the current
existing gates; intersecting independent directional and interval vote counts is
insufficient. Retries under changed gate parameters are conflicting retries.
Older comparison state without these gate values supplies no qualified vote.

## State and provenance

The version-2 temporal state retains the unchanged directional observations and
one `qualified_evidence` object per relationship. That object contains the frozen
reference, its ID/hash, profile justification, bounds, assurance allocation,
current bounded comparison history and a lifetime acquisition/group/slot ledger.
The lifetime ledger is deliberately not discarded with the eight-window horizon.
This increases state size. There is no hidden persistent store and no write from
the evaluation path. Forging or dropping caller-owned state is outside the
integrity contract; evidence bindings identify the supplied state and sources.
Malformed retained qualification state becomes an explicit limited tombstone;
subsequent calls cannot silently reuse its credit or reconstruct its reference.
A version-2 supported assertion requires sufficient reference provenance and
consistent directional/qualified support fields at the evidence-binding boundary.

The producer-issued evidence registry includes the qualification state and the
current directional/qualified assessment. Each source keeps its selected-input
hash; each qualification window records acquisition IDs, timestamps, source
locator, group counts, weights, effective information, moment intervals and budget.
Immutable source data must remain retrievable by the caller: hashes cannot
reconstruct observations. Display rounding never determines qualification.

Development inputs lacking a profile retain their directional evidence but have
limited qualified support. Reporting all such cases as negative in a binary
scorer is not evidence of improved detection accuracy; abstentions must be shown.
