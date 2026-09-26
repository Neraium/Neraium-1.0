# Relationship authority implementation preflight

Decision: `RELATIONSHIP_AUTHORITY_BLOCKED_EXACT_BINDING`

## Baseline and scope

- Branch: `fix/deterministic-governed-output`
- HEAD: `f01d5475967eef8b2f7dd0d05a7b631f79586e25`
- Tracked worktree and index were clean before review.
- Repository AGENTS.md was read.
- No production or test edits were made. No staging, commit, push, cleanup,
  broad validation campaign, or temporal-state continuation was performed.

The approved boundary is graph-owned assessment -> exact assertion binding ->
scoped qualification. The preflight did not establish the middle link for the
existing finding candidates. No heuristic association was implemented.

## Reproduction

Executed the existing synthetic supplied-reference fixture with 16 rows using
`evaluate_sii(**contract(16))`, importing `contract` from
`tests/test_sii_supplied_reference.py`. The diagnostic used
`PYTHONDONTWRITEBYTECODE=1` and printed field presence, not source measurements.

Result: two selected relationship candidates and three dynamic graph edges.

Both selected candidates lacked all of:

- `id`, `relationship_id`, `evidence_id`, `relationship_evidence_ref`
- `reference_dataset_id`, `source_dataset_id`, `signal_units`
- `edge_basis`, `mode_conditioning`

Each graph edge retained `id`, `reference_dataset_id`, `source_dataset_id`, and
`signal_units`. The graph basis was `global_relationship_model`. Its temporal
state identity retained columns, basis, baseline correlation/window, mode,
reference dataset ID, and signal units.

Candidate `evidence_refs` contained baseline/recent window summaries, column,
display name, role and source rows. Source-row anchors contained source row,
timestamp and window. They were not graph-assessment references.

## Source evidence

- `backend/app/services/relationship_baselines.py`,
  `build_relationship_baseline`: the raw graph edge receives an ID; the separately
  constructed selected candidate does not retain that ID or a producer-owned
  evidence reference. Both retain measurement summaries and row anchors.
- `backend/app/engine/sii_engine.py`: supplied-reference dataset and unit
  provenance is added to graph edges, not selected candidates.
- `backend/app/services/analysis_explanations.py`, `build_insights`: selected
  candidates become grouped findings; contributions receive positional IDs.
- `relationship_persistence_info`: grouped signal membership currently supplies
  the persistence boolean. This implementation remains unchanged.

## Missing contract

A producer-carried reference must connect the selected assertion to its source
relationship evidence, with result/reference/comparison scope sufficient to
resolve the exact graph assessment. Pair-only edge IDs are not sufficient across
references or comparison bases. The link must survive graph enrichment and
candidate projection, and reject a different mode-conditioned comparison.

This is a missing retained binding, not proof that a nonmathematical producer
contract extension is impossible. It exposes a prerequisite left unresolved by
the earlier design-ready decision. A consumer-side match on names, measurements,
positions or row anchors is not implemented as a replacement.

An unavailable result would be safe for an unbound record, but an implementation
that only makes these candidates unavailable would not demonstrate the required
positive correction for graph-supported finding assertions.

## Deferred implementation surface

Subject to resolving the producer binding: a relationship authority contract;
finding construction and classification adapters; condition propagation guards;
consequence ownership and original-finding guards; versioned canonical projection;
and focused tests. No production file was changed or approved by this preflight.
The producer linkage must be specified before an exact production patch list can
be finalized.

## Expected behavior and invariants

Intended future changes remain limited to proxy-dependent qualification,
grouping/primary invariance, condition scope, and consequence ownership rejection.
Graph mathematics, reducer outputs, thresholds, recurrence, context, ranking,
consequence mathematics and temporal-state handling must remain unchanged.

No new claims were generated. No deterministic claim identity or downstream
ownership implementation was validated. No historical classification, consequence,
or evidence was rewritten. No customer telemetry or restricted diagnostics are
included in this artifact.

## Validation and disposition

- Baseline branch/HEAD and clean tracked status: verified.
- Small real-engine synthetic identity diagnostic: completed as described above.
- Production/test diff: empty.
- `git diff --check`: passed before artifact creation; repeated after creation.
- Mandatory controlled implementation cases, route tests, consequence invariants,
  security tests and replay tests: not run; implementation stopped at preflight.

Next action: specify the producer-owned assertion-to-evidence reference and its
reference/comparison scope, then resume implementation. Do not substitute a
heuristic join or change analytical mathematics.
