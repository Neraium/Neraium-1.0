# Evidence Package Correlation v1

Status: implemented architecture contract
Schema family: `neraium.evidence-package-correlation.v1`
API resource: related package set

## Purpose

Evidence Package Correlation v1 preserves evidence-supported relationships
between separately produced analytical packages. It lets an operator see that
two persisted findings belong to the same scoped system and share a supported
temporal, canonical-signal, or explicit analytical-pattern dimension.

Correlation is not root-cause analysis. It does not merge packages, revise
their evidence, infer topology, convert time ordering into causality, or learn
from interventions.

## Current repository ownership

Current Neraium persists completed baseline-comparison analyses and exposes a
first-class `EvidencePackage` through `/api/data/evidence-packages/{package_id}`.
The package, lifecycle, fingerprint, exact historical matching, approximate
similarity, and historical-pattern classification remain independently owned.
Correlation consumes an immutable projection of the completed analytical
package and persists its own sidecars.

The package ID remains `EvidencePackage.id`. Correlation never replaces it.
The operator lifecycle (`OPEN`, `ACKNOWLEDGED`, or `RESOLVED`) is mutable,
independent review state and is excluded from the analytical content hash.
Changing lifecycle state therefore neither creates nor invalidates a package
relationship.

Correlation owns:

- one immutable source projection per package;
- one immutable pair record per supported canonical package pair; and
- a pure read view for one package and its valid pair records.

There is no persisted mutable group, root package, parent package, or causal
direction.

## Allowed persisted inputs

The source projector copies only fields already present on the completed
package:

- package ID, schema version, revision, creation time, and latest evaluation
  time;
- organization, workspace, system, site/facility, and equipment identity when
  explicitly present;
- the explicit comparison observation window in
  `operating_context.comparison_window`;
- the explicit comparison-state label or non-unknown comparison state type;
- explicit `canonical_signal_ids`, when a future compatible package supplies
  them;
- explicit `analytical_pattern_ids` or `historical_pattern_ids`, when a future
  compatible package supplies them; and
- a deterministic SHA-256 hash of the complete analytical package excluding
  only its independently mutable operator lifecycle.

Naive persisted observation timestamps produced by the current timestamp
profiler are interpreted as UTC. Offset-aware values are normalized to UTC.

Current package variable names are not treated as canonical signal IDs.
Fingerprint identity, exact matches, approximate similarity, descriptive
historical-pattern classification, scores, severity, confidence, free text,
filenames, and tag-name similarity are not relationship anchors.

## Deterministic eligibility

Packages are evaluated in lexical package-ID order. A relationship is eligible
only when:

1. both sources represent valid completed `evidence-package-v1` analytical
   packages;
2. package IDs are distinct;
3. organization, workspace, and system IDs are present and equal;
4. explicit facility/equipment IDs do not conflict when both packages provide
   them; and
5. at least one supported anchor exists:
   - overlapping observation windows;
   - non-overlapping observation windows separated by at most 86,400 seconds;
   - at least one identical explicit canonical signal ID; or
   - at least one identical explicit analytical/historical pattern ID.

Same-system identity is required but not sufficient. Matching operating
context is supporting evidence but not sufficient.

Temporal classifications are:

- `overlapping_observation_window`
- `temporally_adjacent`
- `not_supported`
- `unavailable`

Operating-context classifications are `compatible`, `different`, or
`unavailable`.

Supported relationship facts use this fixed presentation priority:

1. `shared_canonical_signal`
2. `overlapping_observation_window`
3. `temporally_adjacent`
4. `related_analytical_pattern`
5. `compatible_operating_context` (supporting only)
6. `same_system` (scope fact, supporting only)

There is no numeric correlation confidence score. Priority selects a stable
explanation order, not severity or probability.

## Identity, evidence references, and validation

`relationship_id` is UUIDv5 over the relationship schema version, exact tenant,
workspace, and system IDs, and the two package IDs in lexical order. The pair
has no direction.

Evidence references identify the package fields used, for example:

```text
evidence-package:<package_id>#system_id
evidence-package:<package_id>#operating_context.comparison_window.start
```

Each pair stores both source hashes. Reads rebuild the allowed projection from
the persisted package, verify its hash and scope, rebuild the pair calculation,
and require byte-equivalent canonical JSON. Missing, stale, malformed,
cross-scope, or inconsistent sidecars fail closed; a partially trusted
candidate is never returned.

Expected limitations are versioned enums:

- `package_lifecycle_ineligible`
- `legacy_package_without_correlation_projection`
- `missing_required_scope`
- `observation_window_unavailable`
- `operating_context_unavailable`
- `canonical_signal_identity_unavailable`
- `analytical_pattern_identity_unavailable`
- `related_package_projection_missing`
- `stale_or_corrupt_correlation_sidecar`
- `no_relationship_anchor`

## Persistence and GET purity

Projection runs only after the current completed-analysis write path has
persisted the package and its package-ID lookup. Correlation publication
failure is logged and never rolls back or obscures the completed analysis.

Sidecars use the current scoped analysis-state repository:

```text
scopes/<scope>/baseline-analyses/package-correlation/sources/<package_id>
scopes/<scope>/baseline-analyses/package-correlation/relationships/<relationship_id>
```

That repository retains the current local JSON mirror, runtime `latest_payloads`
database, and configured shared S3 behavior. Split API/worker deployments must
configure the existing `NERAIUM_UPLOAD_STATE_BUCKET` on both roles so the API
can read sidecars published by the worker. Sidecars do not enter the legacy
evidence-run store.

Records are treated as insert-only. An equivalent retry is idempotent; a
conflicting source or pair is logged and does not overwrite the previously read
canonical value. Runtime SQLite uses an atomic `INSERT ... ON CONFLICT DO
NOTHING`, shared S3 uses `If-None-Match: *`, and local-only storage uses an
atomic create-if-absent link. Deterministic IDs therefore make equivalent
concurrent writers converge on the same storage key across the current
deployment modes.

`GET` does not create directories, initialize tables, write audit events,
generate missing projections, discover new pairs, repair stale state, open raw
uploads, run analysis, or invoke fingerprint/historical calculations. Legacy
packages without a write-time source projection remain explicitly unavailable.

## API

Authenticated route:

```text
GET /api/data/evidence-packages/{package_id}/related-packages
```

Stable operation ID: `getEvidencePackageRelatedPackagesV1`.

The response contains:

- `schema_version`
- `package_id`
- `correlation_status`
- `related_packages`
- `limitations`
- `provenance`

Status is one of `unavailable`, `insufficient_evidence`,
`no_supported_relationship`, or `related_packages_found`. Out-of-scope package
identity returns `404` through the existing authenticated dataset-scope lookup.

Related packages are ordered by strongest relationship priority, candidate
observation start, and lexical package ID. Relationship facts, IDs, evidence
references, and limitations use canonical ordering. Repeated reads over
unchanged persisted state return equivalent JSON values.

## Frontend behavior

The current evidence-record workspace shows the selected package separately
from related packages. It displays the exact supported dimensions, source
field references, limitations, and explicit empty/unavailable states. The UI
always includes this non-claim:

> Related evidence does not establish cause, propagation, diagnosis, or
> equipment failure.

## Explicitly excluded from v1

- root-cause or fault diagnosis;
- causal parent/child graphs;
- propagation or downstream-effect inference;
- topology discovery or name-based topology inference;
- intervention outcome learning;
- CMMS or work-order linkage;
- technician feedback;
- recurrence inference owned by correlation;
- approximate matching invented by correlation; and
- mutable correlation groups or cross-scope organizational learning.
