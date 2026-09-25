# Context-comparison qualification correction

Decision: **PRESENTATION_PHASE1_CORRECTED_READY_FOR_CERTIFICATION**

Baseline: `fix/deterministic-governed-output`, HEAD `1bc6d9e031264991ce9cc7ea6bee2ac51b070626`. No commit, push, merge, tag or deployment was performed.

## Blocking defect and reproduction

The preceding `final-adversarial-review.md` remains unchanged. Its semantic blocker was real: a strong general operating-mode match was displayed without the engine's limited like-mode comparison and global fallback qualification.

`tests/presentation_phase1_context_case.py` reproduces this with the existing controlled 16-row fixture and an explicit constant `pump_status` signal. No customer telemetry is used. The real engine records general match `strong`, mode-conditioned status `limited`, `used_global_fallback=true`, `fallback_reason=insufficient_recent_mode_rows`, and graph `edge_basis=global_relationship_model`.

The controlled result's existing classification is `possible_instrumentation_issue`; fallback does not create or change that classification. Its three graph edges are neither promoted nor persistent, its primary relationship list is empty, and its consequence status is `not_quantifiable`.

## Correction and provenance

The shared transport-only helper now optionally exposes `comparison_qualification`:

- `edge_basis` copies the known value from `sii_result.relationship_graph.edge_basis`.
- `mode_conditioned_baseline.status`, `.used_global_fallback`, and `.fallback_reason` copy existing values from `sii_result.operating_modes.mode_conditioned_baseline`.

These are separate sources; neither infers the other. Known engine codes are explicitly allowlisted, fallback is a strict boolean, and explicit null reasons remain null. Unknown strings are omitted: engine failure paths can put raw exception text into the reason field. No runtime, forensic, authorization or credential dictionaries are exposed. No missing historical values are reconstructed.

The disclosure remains bounded to 12 edges and 48 KiB. Qualification is included before the existing byte-budget check; whole trailing observations are removed deterministically with accurate omission counts. Source order and analytical ranking remain unchanged.

The collapsed relationship evidence shows, adjacent to operating context:

- General operating-mode match: strong
- Comparison basis: Global relationship model
- Like-mode comparison status: Limited
- Global fallback used: Yes
- Comparison limitation: Too few recent samples in this operating mode.

Known codes receive explicit customer-facing labels; unknown reasons never render raw text. There is no new card, severity, finding, physical magnitude or consequence semantic. The primary assessment is unchanged.

## Regression and transport verification

`tests/test_presentation_phase1_context.py` evaluates the real engine and verifies the exact qualification across compact upload hydration, explicit analysis retrieval, scoped explicit analysis retrieval, and connector result projection. Retrieval is tested with engine re-execution disabled. It checks source immutability, unchanged analysis/identity, missing historical fields, restricted-field canaries, deterministic map order, volatile-metadata independence, and deterministic byte-budget truncation.

`frontend/tests/fixtures/presentation-phase1-context-fallback.json` retains the engine-derived disclosure and invariants. Backend tests recompute it; frontend unit and Chromium tests consume it. The UI tests require the general match and fallback qualification together. The new mobile Chromium case also checks default collapse, unchanged assessment, no horizontal overflow and no control inputs. The original desktop and mobile cases remain covered.

Three existing transport tests initially failed because upload and connector fixtures supplied different mode evidence. Their inputs were aligned; no production route change was needed. Original A–D artifacts are preserved; their tests compare the original fields separately from this additive qualification.

## Analytical invariants and determinism

A clean `git archive` of authoritative HEAD, with only the controlled test helper supplied, independently reproduced exactly the current classification, primary selection, graph promotion, graph persistence, finding persistence, measurable-consequence objects and semantic digests:

```text
analytical: b973f98207ebf3576d9f88d6a13ed5f944f1253358860fef949b380687c2edad
graph:      e525c41d9557b8532d244fbb758436f9b81433b052a49a239422a234347b01cc
```

The new presentation fields remain outside analytical identity. No stored result is rewritten and no migration is needed. Historical absence remains absence. Existing reference windows, context matching, classification, admission, ranking, primary selection, recurrence/persistence reducers and consequence qualification are unchanged. Physical magnitude, all-signal persistence qualification and production relationship-state handoff remain deferred and untouched.

## Validation results

- 35 unique focused backend checks passed across the correction, Phase 1, SII transport and connector projection suites. The initial combined run passed 32 and identified the three fixture mismatches described above; after alignment, all 16 Phase 1 checks passed on rerun.
- 61 frontend tests passed across relationship observations, workspace, dashboard and measurable consequence.
- 3 Chromium cases passed: original A desktop, original B mobile, and real-engine fallback mobile. Locked `npm run setup:codex` ran first; the production build passed during browser startup.
- Focused ESLint passed for the changed component and unit tests.
- Independent baseline invariant comparison passed. Map-order/volatile-metadata and bounded-serialization regression checks passed.
- `git diff --check` passed. No broad campaign or benchmark ran.

## Final candidate review

Byte comparison of 204 tracked backend files in engine/services/routers/core/models against HEAD found differences only in the three previously changed presentation/API files. AST comparison limits those changes to the two explicit retrieval functions, connector projection and compact upload projection. Analytical mathematics did not change.

This correction changes only the new observation helper and disclosure component, focused tests/controlled fixtures, and review documentation. Existing transport integration, authentication, workspace/site boundaries, read-only architecture and analytical implementations are unchanged. The complete tracked diff and new candidate source were inspected; no unrelated cleanup, dependency changes, debug instrumentation, credentials or customer telemetry were introduced.

The original cases, baseline/restart verification records and adversarial review remain retained as history. Next action: independently certify the corrected candidate before considering a commit.
