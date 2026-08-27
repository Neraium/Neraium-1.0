# Reconciled Authority Phase A Trace

Date: 2026-08-27

Authority: reconciliation commit `837a4839972e5a1a34fca2436ffb489988e10f1d` in `/home/ubuntu/Neraium-1.0-architecture-reconciliation`.

Every reconciliation citation below was read with `git show 837a4839972e5a1a34fca2436ffb489988e10f1d:<path>`. No older working-tree draft is an implementation input.

## Binding boundary

The authority order is canonical observation -> P0.2 chronology/reference -> frozen unchanged SII -> P0.3 logical truth -> P1.2 physical representation -> bounded backend projections (`.planning/research/reconciled-architecture-authority-stack.md`, "Governing decision" and "Boundary ledger"). P0.1 retains the existing native connector result identity, bytes, digest, lineage, and exact historical lookup.

Phase A is pure contracts, identity namespaces, golden vectors, fixtures, and validators. It has no migration, persistence, publication, replay, scheduler, routing, frontend, AWS, deployment, or analytical-math work (`.planning/research/reconciled-implementation-plan.md`, "Phase A"). Runtime transitions and cutover remain later phases.

## Identity rules

The final identity ledger in `.planning/research/reconciled-identity-contract.md` is authoritative where older source summaries differ:

- New deterministic identities use UUIDv5, distinct namespaces, declared-order `typed-length-prefixed-utf8.v1` equality bytes, UTC ISO-8601 microseconds, typed null, and typed digest triples.
- Canonical observation UUID allocation is unchanged; Phase A adds only a typed wrapper around the existing UUID and exact scope.
- Native P0.1 result identity calls the existing `canonical_result_id` producer and namespace. It is not reimplemented.
- Chronology slot excludes run, cursor, polling, observation UUID, worker, retry, and publication time.
- Chronology execution is derived before P0.1 result, Phase 4 plan, and package; later records may bind those values without changing it.
- Authority execution excludes package ID/digest. The final ledger tuple is full scope, native terminal source and typed digest, chronology execution, and authority/determination/configuration versions.
- Analytical reference is independently derived from immutable reference state before authority publication. Display aliases never participate.
- Finding identity excludes position, title, confidence, workflow, package, and presentation grouping.
- Evidence facts are execution-bound but not finding-bound. Evidence bindings join exact same-execution facts to findings with a role and qualification contract.
- Package, section, object-locator, workflow, projection, and latest-locator identities never derive upstream analytical truth.

## Existing repository reuse points

- P0.1 result identity and bytes: `backend/app/services/telemetry_result_artifact.py` (`canonical_result_id`, `_RESULT_ID_NAMESPACE`, artifact canonical serialization).
- Existing P0.1 window identity remains in `backend/app/services/telemetry_analysis_service.py` (`deterministic_analysis_window_id`).
- Existing authenticated tenant/workspace/resource/facility values remain represented by `TelemetryScopeRef` in `backend/app/services/telemetry_domain.py`; the Phase A authority scope extends the logical dimensions without altering that production type.
- Existing server-bound system authority remains in `backend/app/services/phase4_scope.py`.
- Classification and confidence version constants remain owned by `backend/app/services/finding_classification.py` and `backend/app/services/finding_confidence.py`; Phase A bindings reference them and do not invoke or change their mathematics.

## Contract hierarchy frozen for Phase A

The new pure hierarchy is concentrated in five flat service modules consistent with the repository:

1. `authority_contract_common.py`: canonical immutable values, typed digests, versions, scope, limitations/provenance/integrity/completeness, unresolved governance inputs.
2. `authority_identity.py`: the directed typed identity graph and namespace constants, including the unchanged P0.1 adapter.
3. `telemetry_event_time.py`: P0.2-facing chronology value/reference interfaces and state vocabulary only.
4. `analytical_authority_contract.py`: P0.3 logical analysis/finding/evidence/binding/terminal/projection contracts.
5. `canonical_authority_package.py`: P1.2 package metadata, section, object-index, integrity, and completeness descriptors only.

No existing production consumer is imported into or rewired to these modules during Phase A.

## Scope and fail-closed rules

The common scope carries tenant, workspace, resource scope, facility, connection, system, exact asset/null, and applicable native result, authority execution, and finding identity. Scope levels are explicit; equality is exact at the declared level. Asset null is a typed null, never empty or wildcard. No constructor performs scope inference, cross-connection resolution, or raw/global ID lookup. The deterministic scope digest covers the complete declared level (`reconciled-identity-contract.md`, "Rules" and "Namespace and serialization requirements"; `reconciled-projection-contracts.md`, "Universal contract").

## Chronology interface

The P0.3/P1.2-facing reference carries the P0.2-supplied slot/execution, generations, mode, predecessor/reference, frozen event-time bounds, manifest/input digest, expected progress revision, configuration/version identity, processing disposition, and finalization state. It validates and binds supplied values only. It has no scheduler, state transition, readiness clock, or processing-time fallback (`reconciled-storage-migration-plan.md`, chronology execution record; `reconciled-publication-protocol.md`, finalization; `reconciled-architecture-authority-stack.md`, final chronology contract).

## Logical and physical invariants

- `AuthoritativeAnalysis` binds one terminal native source, full scope, one chronology reference, one analytical reference, one terminal outcome, exact finding set, exact evidence set, versions, limitations, provenance, integrity, and complete canonical authority.
- `findings_present` requires a positive finding count. Stable, insufficient, failure, and ineligible require zero. Insufficient Evidence is not enriched.
- Every finding carries exactly one classification, confidence, and persistence binding. Classification is bound to `deterministic_finding_classification_v3`; confidence to `finding-confidence-v1`; no aggregate confidence is created.
- Non-lossless confidence/persistence mapping, new consolidation, and threshold/similarity continuation expose a P0.5 dependency instead of choosing a producer or mathematics.
- Narrative and workflow text are not evidence. Facts and bindings are typed, immutable, exact-scope, exact-execution records.
- Canonical authority/package completeness is complete or unavailable; only bounded projections may be partial. Digests remain typed by algorithm and contract, so P0.1, authority, package, section, object, and ETag values are not interchangeable.
- P1.2 package identity excludes package bytes/digest. Metadata, section descriptors, scoped object locators, version bundle, integrity, and completeness are pure records only; no persistence or compression pipeline is implemented.

## Required unresolved governance

The following use `configured | required_but_unresolved` and fail closed until configured. Phase A assigns roles, never production values or named people:

- Product / System Behavior Owner: evaluation cadence, UTC origin, partial-edge policy, overlapping-context learning policy.
- Connector / Data Quality Owner: source-specific allowed lateness or completeness assertion, and future-skew configuration.
- Security / Administrative Owner: replay authorization, hard limits, audit retention, remediation/promotion authority.
- Migration / Operations Owner: existing-stream reconstruction versus clean-generation enrollment.
- Product / Compatibility Owner: legacy labels, retention, package terminology, deprecation.
- Validation Owner: sustained parity duration/sample/scopes and cutover evidence.

## Later-phase boundary

P0.2 A-Z and P0.3 AT-R01-AT-R36 receive separate coverage maps. Phase A claims only representability, deterministic identity, exact-scope, cardinality, binding, completeness, and fail-closed invariants. It does not claim runtime transition, crash recovery, storage, publication, routing, parity, learning, or cutover risk closure.
