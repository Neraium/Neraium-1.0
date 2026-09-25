# Canonical relationship authority ownership correction

Baseline: `774892e4cfa237195bee51714ae789c061086380` on
`fix/deterministic-governed-output`.

Decision: RELATIONSHIP_AUTHORITY_CORRECTED_READY_FOR_CERTIFICATION

ANALYTICAL_MATH_CHANGED: NO

## Defect and correction

The canonical builder previously copied prospective scoped findings from a cached
explanation. A cached persistence/classification from persistent A could therefore
be published under nonpersistent B's otherwise valid ownership tuple.

Canonical construction now rebuilds prospective scoped findings with the existing
`build_relationship_findings` adapter using producer relationship assertions and
the exact certified registry. The retained baseline assertion fallback is the
same source used by explanation construction. Cached persistence, classification,
confidence and ownership fields cannot override or suppress that qualification.
Missing producer assertions or invalid registry/scope/binding yield no scoped
finding; the cache cannot restore it. Rebuilt findings also supply the original
inputs to the existing exact consequence attachment gate.

This does not reconstruct historical/unversioned output or saved canonical reads.
No producer, reducer, threshold, recurrence, context, quality, sufficiency,
corroboration, governance, ranking, primary selection, resource contract,
consequence mathematics, presentation or temporal-state handling changed.

## Regression evidence

Eight new regression cases failed against the previous candidate before the fix:

- A-to-B cached persistence/classification/confidence transfer with B owner intact.
- Reverse transfer attempting to suppress persistent A.
- Missing cached scoped findings.
- Tampered cached binding and persistence.
- Missing producer registry, incompatible scope, tampered producer binding, and
  absent producer relationship assertions despite a valid-looking cached finding.

All eight pass after the fix, with source inputs unchanged. Additional checks
verify retained baseline assertions and fail if historical construction or saved
canonical retrieval invokes requalification.

## Focused verification

Command 1, **78 passed**, two warnings, 76.20 seconds:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q tests/test_relationship_authority.py tests/test_analysis_result_contract.py tests/test_resource_relationship_binding.py --junitxml=/tmp/relationship-authority-canonical-correction.xml
```

Command 2, **2 passed**, two warnings, 1.14 seconds:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q tests/test_relationship_authority.py::test_canonical_requalification_uses_retained_baseline_assertions tests/test_relationship_authority.py::test_historical_and_stored_results_do_not_requalify --junitxml=/tmp/relationship-authority-canonical-compatibility.xml
```

The latter two tests were added after command 1 collected, and were run separately.
Together these runs cover all 28 authority tests, the existing 17-case matrix,
analysis-result/upload integration, connector transport/retry preservation, exact
resource ownership attacks, consequence numerical/gate invariance, and historical
compatibility. No failures remain in these runs. The previously independently
confirmed baseline corroboration-ordering failure was not rerun or modified.

The only implementation/test files changed relative to the source hashes in
`authority-verification.json` are `analysis_result_contract.py` and
`test_relationship_authority.py`. That earlier artifact is retained as historical
evidence for the pre-correction candidate; its hashes for these two files are
superseded by this correction. All other candidate files and unrelated work were
preserved. Diff reviewed and `git diff --check` passed; new-file whitespace checks
also passed.

No full regression, external-data, scale or performance campaign ran. Nothing was
staged, committed, pushed, merged, tagged or deployed. No blocker identified;
next action is independent recertification of the corrected candidate.
