# Corrected resource binding independent certification

Baseline: fix/deterministic-governed-output at a922c496fa2baeac63b7c882a640d8e6b58caa90.
Decision: RESOURCE_BINDING_CERTIFIED_FOR_COMMIT
ANALYTICAL_MATH_CHANGED: NO

This review verifies the corrected worktree directly; the candidate report's earlier
conclusion and test counts were not treated as certification evidence.

## Ownership and attacks

Resource authority requires the complete certified relationship_source_ref,
relationship_evidence_ref, and relationship_assessment_binding tuple, exact
resource integrity, an authorized result registry, eligible assessment and temporal
persistence. Producer source lineage is copied from the actual selected edge,
relationship memory, model and expected series. Unique final assessment resolution
uses source lineage, never names, relationship IDs, groups, ranking, primary status,
contribution unions or persistent_columns. Signal names are consistency checks only.

Independent in-memory probes reproduced conflicting raw relationship_source_evidence
and weak/limited fallback operating context for both conditions and insights.
All six direct/attachment pairs returned not_quantifiable. Attachment independently
checks the full projection, checks ownership/window/provenance/context compatibility,
and still evaluates the selected original; neither side can restore rejected authority.

Focused tests passed for A/A eligibility, A/B rejection, multiple resources,
contribution and broad-original attacks, missing/stale/ambiguous/tampered bindings,
no-temporal and failure fallback, group/ranking/primary invariance, historical reads
without reconstruction, quality/sufficiency/context gates, and certified exact
relationship component-substitution attacks.

## Numerical invariance and freeze

An independent eligible comparison executed the committed baseline adapter with
unbound resource inputs and the current adapter with explicitly bound inputs.
Complete output equality held after removing only newly added binding/lineage
metadata from current provenance. No pre-existing analytical field was normalized.
Cumulative amount remained exactly 12839.999999999996, over 21600 seconds.
The focused suite also passed committed-adapter gate comparisons, expected-model
training/evaluation equality, exact attachment equality and protected AST checks.

Reviewed every production diff. Existing consequence integration and qualification
calculations, relationship/graph/persistence/recurrence calculations, thresholds,
context semantics, ranking, governance, telemetry admission, Presentation Phase 1,
control and temporal-state continuation are unchanged. New consumer restrictions
are ownership enforcement. The certified relationship binding implementation is
unchanged. No new authorization capability or customer-unsafe metadata was added;
hashes remain integrity seals within already-authorized result reads.

## Propagation

Producer tests exercise actual source -> provisional memory -> model training ->
expected series -> final resource binding. Static review confirms current memory
updates retain the selected edge source and clear missing lineage, and engine
finalization occurs after relationship finalization before canonical construction.

An independent bound-positive probe verified canonical condition ownership and
quantified consequence, JSON storage/read equality, upload consequence preservation,
connector ownership/resource/consequence preservation, and equal connector retry
digests. A first diagnostic invocation passed the product dictionary instead of the
required projection object to canonical_projection_digest; corrected probe passed.
This was a probe API error, not a production defect. Existing real engine/upload/
connector/replay and bounded transport tests passed. Projection copies existing
ownership; it does not reconstruct it. Historical missing ownership stays absent.

## Verification

Command:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=backend:tests .venv/bin/python -m pytest -q tests/test_resource_relationship_binding.py tests/test_measurable_consequence.py tests/test_relationship_assessment_binding.py tests/test_relationship_binding_ownership.py tests/test_relationship_evidence_binding.py tests/test_sii_evidence_transport.py tests/test_sii_phase4_primitives.py tests/test_sii_phase4_orchestrator.py
```

Result: 155 passed, 2 warnings, 78.64 seconds. No broad regression, external-data,
large-volume or performance campaigns were run. git diff --check passed, and new
allowlisted files were independently whitespace-checked. Index remained empty.
No production/test changes, repairs, staging, commits, pushes, merges or deployment
were performed during certification. Only this artifact was created.

Defects: none found within the certified scope.

## Exact commit allowlist

PRODUCTION

- `backend/app/services/resource_relationship_binding.py`
- `backend/app/engine/sii/behavioral_model.py`
- `backend/app/engine/sii/phase4.py`
- `backend/app/engine/sii/expected_behavior.py`
- `backend/app/engine/sii_engine.py`
- `backend/app/services/measurable_consequence.py`
- `backend/app/services/analysis_result_contract.py`

TESTS

- `tests/resource_binding_cases.py`
- `tests/test_resource_relationship_binding.py`
- `tests/test_measurable_consequence.py`
- `tests/test_relationship_evidence_binding.py`

REVIEW EVIDENCE

- `docs/reviews/relationship-authority/resource-binding-candidate.md`
- `docs/reviews/relationship-authority/resource-binding-corrected-certification.md`

All other untracked review/validation files are excluded, including earlier certification artifacts.

Recommended commit subject: `fix: require exact resource assessment ownership for consequences`

Next action: commit only the allowlist when explicitly authorized; certification does not authorize staging or commit.

## Certified file SHA-256

- `60e9f659685d7008823b5f9a3dc81cb29bdfc30a8415ecc832e762aafd223c02`  `backend/app/services/resource_relationship_binding.py`
- `7d3d9a046a8c14a40eae3c952c90a8cb9f1f285329c6f81371c66d0584ec7506`  `backend/app/engine/sii/behavioral_model.py`
- `2396eb4ccdb02cb9720d4b662c99af4dc2af50cd617a10279242dfd294e4b06a`  `backend/app/engine/sii/phase4.py`
- `9f2c2aed495d34cc4760c02327ca61c8aaf846cc2015d6acdf1b7bd83f719683`  `backend/app/engine/sii/expected_behavior.py`
- `a649798de534bd935a218fc7f22955984c5cf90be144d08a9fe336c63999315a`  `backend/app/engine/sii_engine.py`
- `f55ea7a2edfddf491f8b484afa4f46d09783abf56479d75459f19f3a4aa62f50`  `backend/app/services/measurable_consequence.py`
- `4b7a0fd63bf572be101766704c6f83c810ee122ee76e2d0e86f20840b3bab5bf`  `backend/app/services/analysis_result_contract.py`
- `471e0540ba62c72ecad1dc46e6131891f3fda36b37aa991430b0c3f1cb82fe43`  `tests/resource_binding_cases.py`
- `4d6c3459efd2de6837f795b092fb4dc566d7f5744887e54c95ac5c19faf99e5b`  `tests/test_resource_relationship_binding.py`
- `e401634891e3c96696d7fcbd4603e929693733cea5e13f85a357282b06ea504d`  `tests/test_measurable_consequence.py`
- `a32cb14f7cb91956c6470ce0272d9f04c1867ab2d2e5e9e12b45aab1c529a348`  `tests/test_relationship_evidence_binding.py`
- `3545a22946864399031027379fa336ff3ee478f5ed267643f0ade72d7f36ee14`  `docs/reviews/relationship-authority/resource-binding-candidate.md`
