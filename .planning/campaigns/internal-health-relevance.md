# Campaign: Internal Outcome-Grounded Health Relevance

Status: complete
Started: 2026-08-26T00:00:00Z
Direction: Implement and validate the approved internal-only Health Relevance architecture without changing production SII, findings, evidence ranking, behavioral memory, customer APIs, frontend, infrastructure, or remote state.

## Claimed Scope

- `backend/app/services/runtime_db.py`
- `backend/app/services/validated_outcomes.py`
- `backend/app/services/health_relevance.py`
- `backend/app/services/health_relevance_methods.py`
- `backend/app/services/health_relevance_benchmark.py`
- `scripts/inspect_health_relevance.py`
- `tests/fixtures/health_relevance_benchmark.json`
- `tests/test_health_relevance_*.py`
- `tests/test_validated_outcome*.py`
- `.planning/architecture-internal-health-relevance.md`
- `.planning/campaigns/internal-health-relevance.md`

## Phases

1. [complete] Build: implement migration 012 and immutable four-table schema
2. [complete] Build: implement scoped validated-outcome and linkage revision services
3. [complete] Build: implement frozen manifests, state thresholds, relevance versions, provenance, and staleness
4. [complete] Build: implement exactly two pure experimental methods
5. [complete] Wire: implement deterministic A-P benchmark and exact-scope read-only CLI
6. [complete] Verify: run focused/full validation, Citadel QA applicability review, security/diff/git checks, and final method evaluation

## Phase End Conditions

| Phase | Required end conditions | validator_retries_remaining |
|---|---|---:|
| 1 | `command_passes:PYTHONPATH=backend pytest -q tests/test_health_relevance_migrations.py`; exactly four new tables, migration idempotence, append-only triggers, and no existing-table semantic change | 3 |
| 2 | `command_passes:PYTHONPATH=backend pytest -q tests/test_validated_outcomes.py tests/test_validated_outcome_links.py`; exact-scope lifecycle, idempotency, dedup, source authority, denominator, correction/retraction, and link integrity pass | 3 |
| 3 | `command_passes:PYTHONPATH=backend pytest -q tests/test_health_relevance_state_machine.py tests/test_health_relevance_provenance.py`; all approved state boundaries, identity epochs, version rules, and staleness pass | 3 |
| 4 | `command_passes:PYTHONPATH=backend pytest -q tests/test_health_relevance_methods.py`; registry contains exactly two methods, identical manifests are consumed, and sparse/negative/contradictory/information behavior passes | 3 |
| 5 | `command_passes:PYTHONPATH=backend pytest -q tests/test_health_relevance_benchmark.py tests/test_health_relevance_authorization.py`; deterministic A-P benchmark, isolation, provenance inspection, and read-only CLI pass | 3 |
| 6 | `command_passes:git diff --check`; focused suites and repository validation pass or exact environment/pre-existing limitations are evidenced; no prohibited integration/import edge or unrelated path is present | 3 |

## Exit Evidence

| Phase | Evidence type | Required | Artifact | Status |
|---|---|---:|---|---|
| 1 | test | yes | focused migration output in Feature Ledger | complete |
| 2 | test | yes | outcome/link focused output in Feature Ledger | complete |
| 3 | test | yes | state/provenance focused output in Feature Ledger | complete |
| 4 | test | yes | exactly-two-method output in Feature Ledger | complete |
| 5 | test | yes | deterministic benchmark/auth output in Feature Ledger | complete |
| 6 | validation | yes | full validation output in Feature Ledger | complete |

## Feature Ledger

| Feature | Status | Phase | Notes |
|---|---|---:|---|
| Approved Phase 2 architecture | complete | 0 | Four-table append-only model, exactly two methods, conservative thresholds, CLI-only inspection |
| Four-table migration 012 | complete | 1 | Exactly four append-only ledgers; 18 combined migration/schema tests passed; no backfill or existing-table semantic change |
| Validated outcomes and links | complete | 2 | Immutable revisions, exact scope, policy-gated authority, conservative deduplication, explicit stable denominator, correction/retraction, and idempotency; combined focused suite green |
| Frozen state and provenance | complete | 3 | Exact identity epochs, context gates, canonical-incident counting, append-only versions/contributions, 180-day freshness, and no-op version rules |
| Bayesian/shrinkage method | complete | 4 | Beta(2,2), primary Tier A/B and supplemental A-D views, 90% interval, sensitivity output, and transparent contribution handling |
| Outcome-conditioned information method | complete | 4 | Inspectable 2x2 table, Jeffreys smoothing, normalized information, and deterministic fixed-seed permutation reference |
| Benchmark and inspection | complete | 5 | Synthetic deterministic Cases A-P, identical frozen manifests, neither method forced as winner, and exact-scope read-only CLI |
| Focused validation | complete | 6 | 100/100 Health Relevance tests passed; compileall and `git diff --check` passed |
| Full backend regression | complete-with-unrelated-baseline-failures | 6 | 1,133 passed, 1 skipped; stale OpenAPI count expected 169 vs runtime 170 and existing upload timing guard failed in isolation on Python 3.12; no changed API/upload files |
| Frontend/Citadel QA regression | complete | 6 | ESLint passed, 472/472 unit tests passed, production build passed, Chromium desktop/mobile smoke 2/2 passed; no Health Relevance UI or HTTP surface exists |

## Decision Log

- 2026-08-26: Implement only the approved four entities and exactly two methods.
  Reason: Explicit user contract and internal-only safety boundary.
- 2026-08-26: Do not create checkpoints with `git stash --include-untracked`.
  Reason: Phase 1/2 planning artifacts are untracked user campaign work; stashing them would hide or interfere with approved inputs. Checkpoint recovery is `none` and changes remain locally inspectable.
- 2026-08-26: No HTTP route, frontend integration, deployment, production migration, commit, push, PR, or merge.
  Reason: Explicit campaign constraints.
- 2026-08-26: Named maintenance/inspection/fault/repair sources default to Tier B unless an exact versioned source-authority policy promotes them to Tier A.
  Reason: A self-described source category is not proof of independent authority.
- 2026-08-26: Repeated outcome families from one canonical incident preserve state/provenance diversity but contribute only one method unit per incident/information cell.
  Reason: Prevent one incident from inflating recurrence or either experimental method.
- 2026-08-26: Overlapping explicit comparison windows in one protocol are deterministically suppressed while adjacent windows remain distinct.
  Reason: Prevent stable-operation denominator inflation without inferring stability from silence.

## Active Context

Campaign implementation and validation complete. The internal-only boundary is intact; no production integration or remote action was performed.

## Continuation State

Phase: complete
Sub-step: final report
Files modified: only claimed internal service, migration, CLI, test/fixture, and planning paths
Blocking: none
checkpoint-phase-1: none (preserving approved untracked planning artifacts)
checkpoint-phase-2: none (preserving approved untracked planning artifacts)
