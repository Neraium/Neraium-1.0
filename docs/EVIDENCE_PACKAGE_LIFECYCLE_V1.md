# Evidence Package Lifecycle v1

## Philosophy and architecture audit

Evidence Package Lifecycle v1 records what happened operationally after an
Evidence Package was created. It does not reinterpret the package, strengthen a
conclusion, or fill an analytical unknown. Evidence remains before conclusions,
and `unknown` remains a valid analytical outcome.

The pre-existing `status` field is an analytical package classification
(`active` for the currently supported persistent comparison); it is not used as
workflow state. The package also already had analytical provenance, a revision,
an evidence timeline, supporting evidence, multidimensional confidence,
limitations, hypotheses, stable UUIDv5 identity, and replay evidence. Lifecycle
therefore uses a separate `lifecycle` object and does not duplicate or alter any
of those fields. Lifecycle provenance is likewise separate from analytical
`provenance`.

## State and event model

Lifecycle v1 supports exactly three states:

- `OPEN`: the default created state, with no user acknowledgement.
- `ACKNOWLEDGED`: a user has operationally acknowledged the package for
  investigation; this does not express agreement with the finding.
- `RESOLVED`: an operational resolution was recorded; this does not claim that
  equipment was repaired, the finding was correct, or behavior returned to its
  baseline.

The corresponding append-only events are `package_created`,
`package_acknowledged`, and `package_resolved`. Each event preserves an
`event_id`, persisted `timestamp`, explicit `actor` (`system`, `user`, or
`unknown`), `event_type`, `reason`, and `metadata`. Current lifecycle status is
the state represented by the latest event; it is never derived from evidence.
Event identifiers are deterministic UUIDv5 values over persisted event content
and sequence.

## Immutability and persistence

The original package's evidence, analytical timeline, confidence, limitations,
provenance, identity, schema version, and revision remain immutable. Lifecycle
events are stored in a tenant-scoped sidecar record. Reads merge that operational
record into a response copy; they do not write, generate timestamps, increment
the package revision, or mutate the completed analysis. The automatic creation
event uses the analysis's already-persisted completion timestamp. Transition
requests must provide their timestamp and actor explicitly.

Legacy `evidence-package-v1` records without a lifecycle object remain readable.
Their default creation lifecycle is deterministically projected from package
identity and the persisted package creation timestamp, without a GET-time write.
Routes, package UUID, schema version, revision, and legacy finding projection are
unchanged. New lifecycle events are accepted through the package-scoped event
route and appear through the existing analysis and Evidence Package reads.

## Finding-level workflow

The package lifecycle remains the compatibility contract for package-scoped acknowledgement and resolution. The additive finding-level assignment, inspection, feedback, and validation sidecar is documented in [Finding Workflow v1](FINDING_WORKFLOW_V1.md). Its compatibility writer projects unambiguous single-finding run-level changes without duplicating events. Historical multi-finding run assignments remain package scoped because there is no reliable basis for choosing a finding.

## Deferred roadmap

Package Lifecycle v1 itself does not add investigation progress, parts waiting,
reopening, duplicate, or deferred states. Finding Workflow v1 adds only the
lightweight finding-scoped fields described in its contract. Recurrence
classification, parent-child packages, CMMS records, parts and labor, scheduling,
hypotheses, topology, and governance remain future roadmap work and must not be
inferred from lifecycle or workflow metadata.
