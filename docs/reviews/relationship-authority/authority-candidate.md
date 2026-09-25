# Relationship persistence authority candidate — recovered execution

Baseline: `774892e4cfa237195bee51714ae789c061086380` on
`fix/deterministic-governed-output`.

Decision: RELATIONSHIP_AUTHORITY_CANDIDATE_READY_FOR_REVIEW

ANALYTICAL_MATH_CHANGED: NO

## Recovery

Read AGENTS.md, the current diff, both new implementation/test files, and the
relationship-authority preflight and resource-binding review artifacts. The
earlier binding blockers concern older baselines; both exact relationship and
resource ownership contracts are committed in the supplied baseline.

The interrupted work already contained the prospective version marker, exact
relationship persistence adapter, scoped finding construction, grouped insight
and condition guards, canonical consequence attachment, upload integration, and
17-case matrix. All six modified production files and both new files were
preserved. The pytest cache listed the candidate tests with no failures, but no
candidate result log or source fingerprint established which final bytes had
passed. Historical resource-binding certification was reused as prerequisite
evidence, not counted as validation of this new authority candidate.

Remaining work completed here: add scoped findings/version to the connector's
bounded canonical projection; test upload/connector preservation and retry
determinism; narrowly allow the exact new version import/assignment in the
existing analytical AST freeze check; finish focused verification and this report.
Unrelated review, validation, security and script artifacts were not changed.

## Authority boundary

Only the certified exact source/evidence/assessment tuple resolves persistence.
The record must be eligible and its own temporal assessment must establish
persistence. Each finding is qualified separately from the selected relationship
assertion, before grouping or ranking. Group persistence is not assessed; no
group vote, primary relationship, signal persistence, recurrence, or overlapping
condition supplies relationship authority. Conflicting duplicate qualifications
fail closed. Consequences retain the committed exact resource ownership gates.

The version marker enables this prospectively. Unmarked historical explanations
retain committed behavior and stored canonical results remain read-only.
The connector copies bounded scoped findings without reconstruction. The full
registry remains in the authorized canonical artifact, as before.

No relationship, graph, persistence, recurrence, confidence or classification
mathematics changed. Context, quality, sufficiency, corroboration, governance,
ranking and primary selection remain independent. No presentation templates,
temporal continuation, thresholds or consequence calculations changed.

## Mandatory matrix

| Case | Scenario | Result |
| --- | --- | --- |
| 1 | Persistent relationship alone | PASS |
| 2 | Persistent plus stable member | PASS |
| 3 | Persistent plus transient member | PASS |
| 4 | Persistent plus alternating member | PASS |
| 5 | Persistent plus sparse/ineligible member | PASS |
| 6 | Multiple individually persistent relationships | PASS |
| 7 | Mixed stable/transient/alternating/sparse members | PASS |
| 8 | Recurrence cannot establish persistence | PASS |
| 9 | Abrupt single-window promotion cannot establish persistence | PASS |
| 10 | Independent context, quality and sensor-health ceilings | PASS |
| 11 | Global fallback with its own temporal evidence | PASS |
| 12 | Graph-failure fallback without temporal authority | PASS |
| 13 | Grouping invariance | PASS |
| 14 | Ranking/order/primary invariance | PASS |
| 15 | Overlapping condition cannot borrow classification/ownership | PASS |
| 16 | Exact consequence owner accepted; other owner/group rejected | PASS |
| 17 | Identical signal persistence, different relationship outcomes | PASS |

Additional candidate checks passed for missing/conflicting bindings, exact
historical explanation equality, canonical read preservation, and scoped
upload/connector transport with equal retry digests.

## Verification

Run 1: **49 passed**, two warnings, 73.27 seconds:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q tests/test_relationship_authority.py tests/test_analysis_result_contract.py tests/test_measurable_consequence.py tests/test_sii_evidence_transport.py --junitxml=/tmp/relationship-authority-resumed.xml
```

This run collected before the additional transport test was added. That test
was executed in run 2. No production file covered by run 1 changed afterward.

Run 2: **41 passed, 1 pre-existing failure**, two warnings, 22.52 seconds:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q tests/test_relationship_authority.py::test_scoped_authority_survives_upload_and_connector_transport tests/test_relationship_evidence_binding.py::test_existing_calculation_ast_unchanged_except_binding_metadata tests/test_relationship_evidence_binding.py::test_real_engine_upload_storage_and_connector_projection tests/test_relationship_evidence_binding.py::test_real_connector_generation_retains_registry_and_retries tests/test_relationship_evidence_binding.py::test_real_upload_compatibility_path_preserves_binding tests/test_resource_relationship_binding.py::test_eligible_numerical_and_existing_gate_invariance_against_committed_adapter tests/test_condition_intelligence.py tests/test_telemetry_result_projection.py --junitxml=/tmp/relationship-authority-completion.xml
```

`test_multiple_connected_relationships_form_one_corroborated_condition` expects
alphabetically sorted affected signals. The committed producer preserves a
different order. Executed the baseline `condition_corroboration.py` directly as a
registered temporary Python module, using that test's four relationships:
complete baseline and candidate corroboration outputs were equal, and the
baseline also failed the sorted-order assertion. No correction to unrelated
corroboration behavior or weakening of that assertion was made.

Initial invocation named a nonexistent condition test file and collected zero
tests; corrected to the actual test module. The first baseline diagnostic needed
registration in `sys.modules` for dataclasses; the corrected diagnostic passed.
These invocation errors are not product failures.

Consequence numerical/gate equality against the committed adapter passed,
including the existing approximately 12,840-unit fixture. Analytical AST checks
passed. Exact relationship/resource contracts and protected reducers/classifiers
have no diff from the supplied baseline. Tracked diff reviewed; `git diff --check`
and whitespace checks on new candidate files passed. Source hashes and test
outcomes are retained in `authority-verification.json` for future recovery.

Only focused unit/integration checks ran, including the existing bounded
projection unit test. No full regression, LBNL, wastewater, large-volume or
performance campaign ran. No staging, commit, push, merge, tag or deployment.

## Candidate file set

- `backend/app/engine/sii_engine.py`
- `backend/app/services/relationship_authority.py`
- `backend/app/services/analysis_explanations.py`
- `backend/app/services/analysis_result_contract.py`
- `backend/app/services/condition_corroboration.py`
- `backend/app/services/measurable_consequence.py`
- `backend/app/services/upload_jobs.py`
- `backend/app/services/telemetry_result_projection.py`
- `tests/test_relationship_authority.py`
- `tests/test_relationship_evidence_binding.py`
- This report and `authority-verification.json`.

No candidate blocker found. The pre-existing corroboration test failure remains
disclosed. Next action: review this candidate; no commit is authorized.
