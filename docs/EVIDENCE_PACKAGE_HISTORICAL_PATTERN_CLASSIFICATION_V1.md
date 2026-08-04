# Evidence Package Historical Pattern Classification v1

## Purpose and ownership

Historical Pattern Classification v1 is a separately versioned, read-only Evidence Package projection. It answers only what the governed eligible prior package record supports about the presence of a persisted analytical pattern. The Evidence Package repository owns composition; Fingerprinting v1, Exact Historical Matching v1, and Explainable Approximate Similarity v1 retain ownership of identity, eligibility, comparison, and evidence.

This is deliberately called **historical pattern classification**, not recurrence. A historical match supports only that a materially similar persisted analytical pattern exists in the eligible prior record. It does not prove that the same physical condition, failure mode, cause, or incident occurred again.

## Sources, eligibility, and lineage

The only analytical inputs are the existing pure reads for exact historical matching and explainable approximate similarity. The classifier does not recompute fingerprints, dimensions, weights, thresholds, candidate eligibility, temporal ordering, or scope. Source integrity failures propagate closed as `unavailable`. Evidence references are copied from the governed exact observations or approximate dimensions; the classification rule is provenance, not telemetry evidence. Exact and approximate evidence remains distinguishable.

Eligibility is therefore exactly the governed tenant, workspace, system, compatible-algorithm, persisted-sidecar, and strictly-earlier evaluation-time policy of those services. Self and future packages are excluded there. Lifecycle state is not an input: OPEN, ACKNOWLEDGED, and RESOLVED packages remain equally eligible when their analytical evidence is otherwise eligible.

## Statuses and precedence

The strict `evidence-package-historical-pattern-classification-v1` model permits `not_evaluated`, `insufficient_history`, `unavailable`, `no_supported_historical_pattern`, `exact_historical_match`, and `similar_historical_pattern` only. Normal package reads return one of the latter five; `not_evaluated` is reserved for typed interchange compatibility.

Deterministic precedence is:

1. a valid exact match;
2. a supported approximate match when no exact match exists;
3. no supported pattern when eligible history and governed comparisons are available;
4. insufficient history when no eligible earlier package exists;
5. unavailable when governed inputs cannot be completed.

Integrity failure overrides favorable evidence and returns `unavailable`; it is never silently discarded. Candidate exclusions and insufficient-similarity-evidence results do not establish a pattern. A valid no-supported-similarity result can support `no_supported_historical_pattern`. Exact, supported-approximate, no-supported, insufficient-evidence, and excluded counts remain separate.

`insufficient_history` means only that the eligible historical record is insufficient. `no_supported_historical_pattern` means only: “No supported historical pattern was found in the eligible available history.” It makes no assertion about behavior outside that record. `unavailable` covers a missing evaluated sidecar, invalid timestamp, missing/corrupt/stale governed result, or invalid scope.

## Strongest match and time

Exact matches precede approximate matches. Multiple exact matches preserve Exact Matching v1 ordering. Approximate matches use highest overall similarity, then the **earliest** prior package evaluation/completion timestamp, then package ID. Lifecycle, maintenance outcome, and diagnosis never rank a match.

Persisted evaluation/completion time is record ordering only - not physical onset, causal order, propagation order, or a failure sequence. The interpretation is: “An earlier eligible Evidence Package contains the same canonical pattern,” not a claim about an event happening before.

Approximate support preserves supported, unavailable, and excluded dimensions plus supported and required weight. Exact observation IDs and approximate algorithm versions remain separately labeled.

## Compatibility and read purity

This projection does not modify `evidence-package-v1`, UUIDv5 package identity, package number, revision 1, exact baseline identity, analytical contents, lifecycle, timeline, confidence, limitations, hypotheses, replay references, sidecars, or earlier match/similarity output. It adds no migration and rewrites no package. Reads are deterministic and perform no persistence, repair, or sidecar generation. Legacy packages remain readable through existing routes; a legacy package without its persisted sidecar receives explicit `unavailable` classification.

## Non-claims and deferred work

The classification is not evidence of a shared physical incident, condition, equipment defect, failure mode, root cause, repair, diagnosis, causal linkage, topology, or propagation. It does not interpret RESOLVED as recovery or successful repair.

Physical recurrence policy, parent-child package relationships, field feedback, post-intervention validation, maintenance/CMMS integration, hypotheses, topology, propagation, diagnosis, and organizational learning are deferred. None is inferred or implemented by v1.
