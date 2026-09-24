# Human architecture authority — 2026-09-24

The user's supplied decisions supersede the earlier unresolved conclusions prospectively. The prior decision is preserved verbatim in [history](history-before-human-authority/ARCHITECTURAL_DECISION.md); the ranking and identity investigations remain evidence, not current blockers.

| Previous conflict | Authoritative rule | Required current implementation | Historical compatibility |
|---|---|---|---|
| Supplied order versus stable ID analytical tie-break | SOURCE_SUPPLIED_ORDER_AUTHORITATIVE | Descending importance, absolute delta, confidence; exact ties retain supplied position. IDs never select an analytical winner. | Decode persisted primaries unchanged. No replay reranking. |
| Source versus execution identity | Typed responsibility by producer/version/derivation/consumer | Current governed-output-semantics.v2; generic execution analysis/run/job/upload correlation excluded through declared producer paths, connector windows/runs source-owned, established complete-upload v2 durable upload ownership retained. Content evidence references bind source evidence, never generic attempt IDs. | Frozen source-v1 and target-v1 semantic readers. No stored bytes/version strings/hashes changed. |
| Phase 4 aliases | Explicit source identity, otherwise observation digest | Retain target config.source_run_id, content fallback, runtime run/job trace and UTC attribution. | Stored behavioral snapshots and canonical artifacts are read, not regenerated. |
| Missing source time | Execution clocks cannot create source evidence | Retain target no-completion-clock source-window fallback. Qualification formulas unchanged; missing-time cases follow their actual evidence. | Historical qualification/results remain as stored. |

Current semantic content is every field of the governed schema except the declared producer-owned runtime envelope and compatibility aliases. Source observations, chronology, source bindings, behavioral snapshots, state, evidence, qualification and consequence remain included. Provenance is retained; only expressly declared execution correlation is omitted from the semantic projection. Exact artifact hashes continue to cover all stored bytes.

The existing complete-upload-evidence.v2 producer establishes durable upload/job ownership (dataset routes, immutable evidence references and retries), unlike arbitrary engine attempt IDs. Connector-window.v1 establishes analysis-window and source-ingestion ownership. New output records carry their producer contract explicitly. An absent producer contract defaults to execution correlation, not inferred source ownership from a key name.

v1 is historically ambiguous: complete-upload v2 and explicitly marked execution envelopes establish SOURCE origin; TARGET v1 has its original runtime alias namespace. Standalone ambiguous legacy values can explicitly request source-v1 or target-v1 interpretation. These readers never upgrade or mutate records. Historical canonical replay retains exact bytes without invoking either ranker.

Validation is pending. This decision authorizes reconciliation, not a premature equivalence claim.

## Final implementation responsibilities

| Responsibility | Current binding |
|---|---|
| SEMANTIC | Explicit governed v2 schema, including analytical values, ranks, ordered evidence, source windows, sufficiency, state, consequence and declared source/provenance bindings. Exclude only declared execution envelopes and producer-specific compatibility aliases. Runtime alias descriptions cannot redefine this schema. |
| SOURCE_IDENTITY | Dataset/baseline/window/observation identity, raw-input digest, connector source ingestion and window IDs; durable complete-upload v2 ownership; paired-reference.v1 analysis ID derived from comparison/reference hashes. |
| BEHAVIORAL_IDENTITY / evidence | Existing model/schema/version/snapshot lineage, source-bound snapshot derivation, and deterministic evidence references. No identity is added to analytical ranking. |
| PROVENANCE | Original source/ownership, versions, source chronology, evidence references, build/configuration and integrity hashes remain reconstructable. Source ownership remains bound where its producer requires it. |
| EXECUTION_METADATA | Generic analysis/run/job/upload correlation, actual generation clocks and profiling; upload request/session/attempt correlation. Operational terminal summaries retain attempt identity for retry control; current analytical result artifacts store it in runtime metadata. |

Canonical projections retain identity_contract. Terminal publication re-encodes current output after assigning attempt_id and uses runtime-aware attempt readers; historical versions bypass this change. Historical bytes, hashes and source ownership are not rewritten.

Two retained TARGET sorts were proven to feed governed recommendations, evidence IDs and consequence source-tag references. They are therefore not harmless representation and have been removed from localize_condition and _corroboration_result. Canonical shared-signal sets, stable fallback IDs and lexical condition-system identity remain; supplied analytical order is preserved.

## Validation status — authority resolved, complete validation pending

The single authorized complete 10K gate failed retained-reference equivalence. The two current executions were internally semantically identical. Small regressions pass after the signal-order and terminal-runtime corrections, but the corrected final candidate has not run a complete gate. There is no renewed architecture question. A further complete gate requires authorization because the user's one-gate allowance has been consumed. Do not claim promotion validation from internal determinism alone.
