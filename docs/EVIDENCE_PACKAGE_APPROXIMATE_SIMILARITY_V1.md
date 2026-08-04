# Evidence Package Explainable Approximate Similarity v1

## Purpose and ownership

The backend Evidence Package service owns a pure-read comparison of persisted,
eligible `evidence-package-fingerprint-v1` sidecars. It reports evidence-backed
structural resemblance and how the score was assembled. The fingerprint
foundation continues to own fingerprint creation, identity, indexing, and exact
historical matching. A GET never creates, repairs, or mutates a package or sidecar.

## Exact and approximate similarity

Exact matching retains canonical SHA-256 equality and is unchanged. Approximate
similarity uses `evidence-package-explainable-weighted-v1`; it compares selected
fingerprint features and exposes every component. Approximate results do not alter
exact-match results and are not package identity.

## Scope and temporal eligibility

Both sidecars must be persisted and available under the authenticated tenant and
workspace and have the same persisted system identity. The candidate package must
have completed strictly before the evaluated package. Self, simultaneous, and
future packages are excluded from eligible history. Invalid scope, stale index
data, invalid timestamps, or incompatible sidecars make the read unavailable
rather than broadening scope. No eligible candidates yields `insufficient_history`.

## Dimensions, ordering, and weights

Dimensions always appear in this order. Their weights are fixed and sum to 1.00:

| Dimension | Weight | Definition |
| --- | ---: | --- |
| System identity | 0.20 | Exact tenant, workspace, and system equality; inequality excludes comparison. |
| Primary signal pair | 0.20 | Exact equality of canonical signal IDs. |
| Relationship type | 0.10 | Exact relationship-type equality. |
| Relationship direction | 0.10 | Exact directed ordering; not applicable when both relationships are symmetric. |
| Relationship strength similarity | 0.12 | `1 - min(abs(comparison_strength difference), 1)`. |
| Relationship change magnitude | 0.10 | `1 - min(abs(absolute_change difference), 1)`. |
| Relationship change direction | 0.08 | Exact equality of positive, negative, or zero sign. |
| Persistence similarity | 0.05 | Same bounded numeric-distance formula, only when quantified for both. |
| Operating-context compatibility | 0.05 | Mean bounded distance for common canonical roles and values, only when available for both. |

No other dimension is supported. Unsupported examples include lifecycle state,
confidence, limitation count, timeline shape, package number, titles, topology,
propagation, hypotheses, interventions, and any Structural Memory Engine feature.

## Minimum evidence, unavailable data, and thresholds

Each dimension returns its name, status, score, weight, evidence references,
unavailable reason, and exclusion reason. Missing data is `unavailable` (or
`not_applicable`) and never becomes zero. The overall score is exactly
`sum(score * weight)` over supported dimensions. Missing weights are **not
renormalized**, so operating context can add supported evidence but cannot
manufacture resemblance. At least 0.80 configured weight must remain supported;
otherwise no score is returned and limitations include
`insufficient_similarity_evidence`.

An overall score of at least 0.60 is `supported_similarity`; a lower score is
`no_supported_similarity`. These are reporting thresholds, not classifications.
Operating-context v1 has no evidence-backed categorical exclusion rule; a future
compatible algorithm may exclude a comparison only when explicit contradictory
context evidence exists.

## Explainability and compatibility

Responses identify evaluated and candidate packages and fingerprints, schema and
algorithm versions, ordered dimensions, supported/unavailable/excluded names,
limitations, and eligibility/scope/temporal/formula provenance. Decimal inputs
come from deterministic fingerprint serialization, and output rounds to eight
places. A reviewer can reproduce the score directly from returned scores and
weights. Revision 1, UUID/package identities, package numbers, analytical
immutability, lifecycle, timeline, confidence, limitations, replay, tenant
isolation, and deterministic serialization remain unchanged.

## Non-claims and deferred work

Similarity does not determine or imply recurrence, duplicate incidents, a shared
failure mode, equipment failure, root cause, diagnosis, topology, propagation, or
parent/child relationships. It does not use archetypes, prototype memory banks,
demonstration fingerprints, long-horizon memory, or experimental hard-coded
memory scoring. Classification of historical patterns is explicitly deferred.
