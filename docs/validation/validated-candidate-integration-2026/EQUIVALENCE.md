# Equivalence — not yet certified for the corrected final candidate

Previous stopped audit: [history](history-before-human-authority/EQUIVALENCE.md).

The one complete 10K gate executed two uploads. Complete current v2 semantic content and digest matched exactly between them. Both evidence-store hashes and all four provenance links matched result_digest; both generated zero Aletheia EVP records and had no active gate.

Retained SOURCE comparison failed: 11 of 12 analytical component groups matched; governed conditions/insights/consequences/narratives did not. The numerical graph/evidence, source identity/bytes, analytical state, persistence/recurrence, operating context, sufficiency, canonical replay and other analytical modules matched. See [gate-diagnosis.json](gate-diagnosis.json) and [gate-mismatches.json](gate-mismatches.json).

The 25 snapshot differences came from lexical sorting of affected signal lists: flow_gpm,load_pct,pressure_psi instead of flow_gpm,pressure_psi,load_pct. This flowed to recommendation text, localization, two content-addressed evidence IDs, and consequence source-tag order. No difference in consequence quantity or qualification was found in the saved outputs; nevertheless the complete governed objects were unequal.

A read-only comparison of saved complete outputs against the repaired historical reference found 78 differing paths: repeated projections of those ordering differences, their result-hash consequences, and an attempt_id reintroduced by terminal publication after encoding. [full-retained-mismatches.json](full-retained-mismatches.json) retains every difference. This supplementary inspection is not another gate execution and does not turn the failed gate into a pass.

The final code restores SOURCE affected-signal order and serializes terminal attempt correlation at its actual producer boundary. Small regressions pass. Final review also binds alias exclusion to the declared producer contract and preserves that contract through projection. No complete workload was rerun after these edits. Final full analytical equivalence therefore remains UNVERIFIED.

The frozen comparator/bridge/worker were not changed after observing output. [GATE_POLICY.md](GATE_POLICY.md) and [pre-gate-freeze.json](pre-gate-freeze.json) remain the original declarations. There are no new comparison exclusions. Historical records retain their original bytes and hashes; the retained complete-upload source hash was independently verified as af079f08cf0f6adfeec5058b0bf324f13498f208db0afb5c46f44731363212fa.

Protected numerical/storage/package implementations remain byte-identical to SOURCE. UTC/schema/artifact TARGET improvements remain intact. This supports the focused reconciliation but is not a substitute for a successful complete gate.


## Final certification authorization — 2026-09-24: STATIC PRECHECK FAILED

INTEGRATION_VALIDATION_FAILED — stopped before workload execution. No final TARGET run 1 or run 2 was launched; no final repeat or SOURCE equivalence result exists.

The required unchanged semantic comparator check fails for `backend/app/services/output_semantics.py`:

- Pre-first-gate frozen SHA-256: `dd2480dcfb89dbab6a10fd8f66f6bdc60986345c23a07a1a4a7639d00110483c`.
- Current SHA-256: `8127748ff4fa0cb625c8b24a722f803ea5e8c4480620cc57da9a6dac7a5d4c33`.

The existing reconciliation notes document a post-gate change binding comparator alias selection to the declared producer/version contract instead of mutable runtime metadata. This may enforce the intended identity architecture, but does not satisfy this authorization's explicit requirement that the semantic comparator have not been modified after the previous failed gate. No claim of comparator weakening or new exclusions is inferred solely from the hash difference. The earlier statement that the comparator remained unchanged is not supported by the frozen hash. The gate test, retained worker, version/build bridge, upload encoder and GATE_POLICY.md do match their pre-gate hashes.

`git diff --check` passed. All 717 corrected TARGET manifest entries and all 2,696 retained SOURCE manifest entries matched before this record update. This preserves the recorded optimization stack (#1/#2/#3/#5 present, #3 ACCEPT_WITH_LIMITATIONS, #4 absent), four target-only behaviors, ranking/identity architecture, both corrections, retirement and historical compatibility; it does not supply new dynamic certification. No production edits, tests, complete workload, 500K, 1M, LBNL, full suite, commit, merge or push occurred. SOURCE was read only.

The first integration gate and all its mismatch evidence remain intact: it exposed affected-signal ordering differences and subsequent saved-output inspection exposed terminal attempt_id reinsertion. Its corrected candidate still requires certification. This final authorization stopped at static precheck, rather than executing a second integration gate. No analytical difference in a new result can be reported because no new result was produced.

Next action: resolve the frozen-comparator prerequisite against the documented producer-contract correction before authorizing workload execution. Do not change the final architecture or silently replace the freeze.

Retained SOURCE performance only: 500,000 observations, 3 signals, 1,500,000 scalar telemetry values, median 121.610119 seconds. This has not been independently reproduced in Neraium-1.0.


## Final corrected-candidate certification — 2026-09-24

**INTEGRATION_CERTIFIED**

This supersedes the pending status and static-prerequisite stop above. The first integration gate remains a failed retained-SOURCE comparison, exposing affected-signal ordering and subsequent saved-output discovery of terminal attempt_id reinsertion. Its evidence is untouched. The intervening authorization executed no workload. This final authorization executed exactly one existing complete 10K repeat gate, after prospective freezing of the current authorized comparator.

### Prerequisite and immutable declaration

[PREREQUISITE_RESOLUTION.md](final-certification/PREREQUISITE_RESOLUTION.md) documents the exact old/current comparator hashes, retained chronology, evidence limits and authority. The prior freeze followed the initial architecture reconciliation but preceded post-gate corrections. A separate documented alias-rule correction makes producer/version authority replace mutable runtime alias descriptions. No production code changed for certification. The historical hash remains preserved; no exact historical comparator byte copy was found, so no byte-complete reconstructed diff is claimed.

The current comparator, unchanged worker/test/bridge and corrected candidate were frozen before workload execution in [PREDECLARED_CONTRACT.json](final-certification/PREDECLARED_CONTRACT.json), [COMPARATOR_HASHES.json](final-certification/COMPARATOR_HASHES.json) and [CANDIDATE_HASHES.json](final-certification/CANDIDATE_HASHES.json). All prospective frozen files remained unchanged.

### A. TARGET repeat determinism

One pytest node, `tests/test_complete_upload_semantics.py::test_complete_10000_upload_repeat`: **1 passed** (53.16 seconds including comparison/serialization). Two complete uploads, each 10,000 observations / 3 signals / 30,000 scalar values. Production processing times were 18.564092244952917 and 18.516366760944948 seconds; these correctness samples are not a scale benchmark. Resource monitor observed 370,106,368 bytes peak process-group RSS; no resource stop.

Complete semantic content and digest match exactly: `bd70db4d53f6a28d262834e1f7cd5e55a8bf3f6661f0a0c6a17720496ddbf907`. Evidence-store hashes and all four provenance links equal result_digest `e41a27d2c2b953b13321fdc0d54207f75ec76f8c14b9158c8297619d24566aac`. Full outputs, evidence records and empty EVP audit logs are preserved in [gate/](final-certification/gate/); [GATE.json](final-certification/gate/GATE.json), [JUnit](final-certification/complete-10k-tests.xml) and [execution record](final-certification/execution.json) record the pass.

### B. Retained SOURCE analytical equivalence

All 12 analytical component groups match both retained SOURCE snapshots (warmup and 1). Complete repaired pre-retirement SOURCE output equals current TARGET semantic content after only the unchanged predeclared version/build bridge and two previously declared Aletheia removals. No unexplained analytical difference remains. Historical v1 identity/version declarations and SOURCE build provenance are translated prospectively for comparison; historical bytes and hashes are not changed or asserted identical to v2 hashes.

The comparison includes graph, numerical evidence, supplied ranking and primary, persistence/recurrence, context/qualification, sufficiency, governed summaries/state, source/behavioral identity, canonical replay and evidence references. The prior affected-signal mismatch is gone: all 243 affected_signals occurrences match. Both Measurable Consequence objects match completely, including references, status and values; both have status `not_quantifiable`. This does not assert new quantifiable consequences.

### Runtime identity, ranking and integrity

The returned results contain no top-level attempt_id. The retained worker produced the same runtime attempt alias (`production-benchmark`) in both runs, while live runtime metadata differed. An initial saved-output inspection expected distinct aliases and failed that assumption; no gate or comparator was changed or rerun. The predeclared saved-output mutation check then explicitly changed only typed runtime attempt/run/job/upload/request/session/generation metadata and permitted execution aliases: semantic and result digests remained identical. Changing raw-source identity or source-owned analysis_id changed identity. [Saved-output verification](final-certification/saved-output-verification.json) retains this limitation and exact checks.

Analytical ranking uses evidence-only tuples with supplied-order exact ties, with no ID winner selection. The 10K workload is not an exact-tie experiment: existing passing focused tie/identity regressions and unchanged inspected implementation establish those edge cases; no broad campaign was rerun. All four target-only behaviors and both post-gate corrections remain. Canonical evidence/replay and provenance passed within this gate's exercised path; historical canonical artifact readers/identity validation remain unchanged.

Optimization #1/#2/#3/#5 remain present; #3 retains ACCEPT_WITH_LIMITATIONS; #4 absent, checked by runner function equality to validated SOURCE. Zero new Aletheia EVPs and no active gate in either output; historical reader retained. Read-only/non-actuating architecture unchanged, with required local evidence persistence only.

[Final integrity](final-certification/final-integrity.json) verifies 840 frozen candidate source files, 8 comparator/worker/bridge files, all prospective declaration files and all 2,696 SOURCE manifest entries unchanged. Prior failure evidence remains intact. `git diff --check` passed. No production edits, second gate, broad suite, 500K, 1M, LBNL, commit, merge, push or security hardening.

### Performance and next action

Neraium-1.0 contains the validated optimization stack and has passed complete semantic integration certification. Retained SOURCE performance: 500,000 observations, 3 signals, 1,500,000 scalar telemetry values, median 121.610119 seconds. This remains performance evidence from the validated SOURCE candidate and has not been independently reproduced in Neraium-1.0.

Certification is complete. Await a separate instruction for subsequent work; no scale workload or security hardening is authorized here.
