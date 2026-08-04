# Evidence Package Fingerprinting Foundation v1

## Ownership and purpose

`evidence-package-fingerprint-v1` is a separately versioned derived sidecar owned by
the completed-analysis persistence service. It records a SHA-256 identity for the
normalized analytical structure already supported by an immutable
`evidence-package-v1`. It does not modify that package. Package persistence finishes
before the fingerprint sidecar and its scoped index are published.

The package UUIDv5 identifies one scoped analysis instance. The fingerprint ID is a
namespaced SHA-256 digest of structure and may be shared by different packages. An
exact-match observation has a third deterministic SHA-256 ID covering the evaluated
package, prior package, algorithm version, and evaluation basis. None of these IDs
is substituted for another.

## Canonical inputs and evidence

Algorithm `evidence-package-canonical-sha256-v1` uses only validated package-owned
fields: organization/workspace/system scope; condition type; exact persisted primary
signal identities; relationship type and directionality; baseline and comparison
strength; signed and absolute change; optional quantified persistence; supported
operating-context metrics; package semantic/calculation versions; and the supporting
evidence references for included features. Correlation is symmetric and its signal
IDs are lexicographically ordered. Other relationship types are directed and retain
left-to-right order. Exact source-column identities are used when no canonical signal
ID exists; display-label guessing is forbidden.

Maps are serialized as UTF-8 JSON with sorted keys and compact separators.
Semantically unordered collections are sorted by their declared IDs or canonical
roles; semantically ordered structures retain order. Finite numbers are converted
to decimal text rounded to eight fractional places with round-half-even, with
insignificant trailing zeroes removed. NaN and infinity are rejected. The algorithm
version is part of the digest namespace, so a version change creates a distinct
identity.

Every included feature cites persisted supporting evidence. Evidence quality remains
explicit and is never merged with conflicting or uncertain evidence. Missing values
are listed as unavailable and never replaced by zero or a fallback constant.
Baseline/comparison strength and both change measures are required; persistence and
operating context are optional and may remain unavailable. Organization, workspace,
system identity, condition, both signal identities, relationship type, and the four
required numeric measures are necessary for an available fingerprint. Failure of a
required dimension yields an explicit unavailable sidecar without a canonical digest.

## Scope and time eligibility

Exact matching requires the current authenticated tenant and workspace, identical
persisted system identity, and identical fingerprint algorithm version. Missing
system identity is insufficient scope evidence. Filenames, labels, inferred assets,
and cross-customer candidates are never fallbacks.

Candidates must have a valid timezone-aware `latest_evaluated_at` strictly earlier
than the evaluated package. Self and future matches are excluded. Missing or invalid
evaluation timestamps make evaluation unavailable. This ordering is package
completion/evaluation ordering only; it is not physical-event or fault-onset order.

Zero eligible prior packages yields `insufficient_history`. Eligible available
history with no equal digest yields `no_exact_match`; one or more equal digests yields
`exact_match`. Missing required scope, timestamp, fingerprint evidence, or a stale
index reference yields `unavailable`. “No exact match” only describes eligible,
available history and does not claim the behavior never occurred. Prior results are
ordered by evaluation timestamp and package ID.

## Persistence, provenance, compatibility, and read purity

Fingerprint records are stored by tenant/workspace package ID and indexed by
tenant/workspace/system/algorithm version. Publishing is locked, idempotent, and
merge-based so retries and concurrent completions do not duplicate or lose entries.
An existing valid record is immutable. A stale or scope-invalid index reference fails
closed. Repair/rebuild, if introduced, must be an explicit write operation; GET never
creates, repairs, or migrates records.

The sidecar records its schema and algorithm versions, package revision, source
schema, evidence references, and creation source. Legacy packages and packages with
unavailable fingerprints remain readable. `evidence-package-v1`, UUIDv5/package
number/revision 1, baseline identity, timeline, confidence, limitations, empty
hypotheses, replay references, lifecycle sidecar, legacy projection, and repeat-GET
behavior remain unchanged.

## Non-claims and deferred work

A fingerprint or exact match is not similarity, recurrence, diagnosis, cause,
severity, topology, propagation, lifecycle state, intervention outcome, or recovery
evidence. Lifecycle status is not a feature and does not affect eligibility.

The Structural Memory Engine is not reused: its fixed profiles, fallback values,
similarity weights, archetypes, topology/propagation inputs, and outcome data violate
this evidence-owned exact-digest contract. Approximate similarity, recurrence
classification, parent-child packages, condition-wide graph fingerprinting (until a
canonical condition object is package-owned), topology, propagation, interventions,
field feedback, CMMS, and organizational learning are deferred.
