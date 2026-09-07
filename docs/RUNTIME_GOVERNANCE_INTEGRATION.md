# Runtime governance integration

This integration connects the existing Phase 1–3 contracts to production persistence and presentation. It adds no authority executor. Analytical SII outputs, operator workflow status, severity, consequence calculations, and existing baseline/model writers retain their existing semantics.

## Live-path audit

| Runtime | Analytical and persistence path | Previous disconnect | Integration point |
|---|---|---|---|
| Upload | upload_jobs → evaluate_sii (through upload compatibility runner) → analysis_result → upload_evidence.build_evidence_record_from_result → evidence_runs → finding_cases → finding/result API | Immutable finding snapshots existed, but no governance adapter or authority admission ran | evidence_store.upsert_evidence_run requests governance only when creating a new finding case; upload finalization copies the persisted governance projection into its completed result |
| Existing scheduled live worker (legacy surface) | normalized_telemetry → live_windows → live_intelligence.analyze_live_window → existing pilot relationship/persistence analysis → live_analysis._complete_run → live_findings + live_analysis_runs | latest live evidence was updated without freezing a governance basis per run | govern_live_findings runs inside the same SQLite writer transaction as finding/run completion |
| Connector | ingestion observations → CanonicalAnalysisWindow → run_analysis_window → evaluate_sii → canonical analysis_result → compressed canonical artifact → TelemetryCanonicalResultService → product projection | The canonical artifact and lineage were immutable, but contained no governed condition basis | govern_connector_execution decorates analysis_result before canonical artifact persistence; result retrieval transports the frozen field |

Normal production navigation uses Data and the Operations Brief. The previously retired legacy Live Monitoring route remains retired; this change does not reenable it. The existing scheduled worker is covered in addition to the current upload/connector paths.

The scheduled live adapter uses the existing approved behavioral model relationship/persistence entry points; it does not substitute SII scores or create another analytical engine. Connector conditions remain owned by their canonical result, accessible through that result's existing detail route. They are not duplicated into the separate upload finding table. Their governance identity uses the existing deterministic evidence_finding_id helper with the canonical window ID and condition ID.

Existing evidence includes canonical conditions/relationships, their evidence_refs and source windows, upload traceability/input/result hashes, connector observation-lineage records, and per-run live analytics JSON. Existing workflow events are separate from analytical finding state. Consequence already belongs to canonical conditions; governance retains that output as a separate field. Existing behavioral-model versions/snapshots and approved baseline references provide model provenance. All these inputs are reused.

## Analytical mapping and explicit limits

runtime_governance.adapt_relationships maps retained, finding-owned relationship comparisons into canonical EvidenceObjects in the relational family. It retains real source signal names, numeric comparisons, original baseline/recent window references, available source-row timestamps, source run, result reference, provenance, and bounded fixed-window persistence support. The raw SII relationship format's supporting_metric_pairs also supplies real signal identities.

An ObservationReference points to the retained analytical input/result snapshot. It does not claim that invented raw observation IDs exist. Connector source references resolve to canonical artifacts with the existing complete observation-lineage API. The adapter does not duplicate raw telemetry. Shared windows, sources, signals, assumptions and dependencies remain shared under Phase 1–3 independence rules.

Only the existing pilot_assessment fixed-window gate is admitted: at least two supporting windows and at least 60% support after the first supported window. Window bounds, measurements and the supplied gate assertion are checked. Narrative persistence, confidence, relationship counts, frontend labels and consequence never become maturity gates. Unknown chronological bounds limit evidence; supplied future timestamps reject evaluation. Timezone-free product display ranges are retained as reported_window, never interpreted as UTC; connector/live source windows come from normalized observations.

At most 24 relationships, 32 source-window references per relationship and 128 persistence windows are admitted. Canonical EvidenceObject/AuditSnapshot payload limits remain enforced. A complete runtime snapshot is capped at 512 KiB; excessive data fails closed, rather than silently awarding maturity from a truncated basis.

The current common finding contracts preserve relational ownership. Run-level covariance, temporal, multiscale, expected-response, physics, instrumentation and trend channels cannot be assigned to an arbitrary finding merely because they occurred in the same run. They remain visible in existing evidence views but are not relabeled as independent governance support. Consequently this adapter currently produces Observed or Persistent. The existing L0–L4 evaluator is used unchanged: Corroborated, Characterized and Context-qualified are not fabricated. Existing narrative trajectories are not the multi-family TrajectoryCharacterization contract and therefore remain unavailable as governance characterization.

## Context, policy, and non-execution

The Context Registry receives real server-bound system identity, or the authenticated scheduled runtime's persisted system configuration identity. Identity changes append versions; creation/availability and effective timestamps are retained separately. Identity is never an L4 external anchor. The evaluator also consumes the scoped registry's existing known context history, including invalidations. No synthetic maintenance/calibration/setpoint record, verified operating mode, engineering constraint or physics anchor is created from presentation text. Missing context remains unknown.

The runtime policy is registered as runtime-observation-only, version 1, when first needed. It requests evaluation of adaptation, requires L4 and persistent lifecycle, requires human review, and treats unresolved instrumentation, physics and evolution-rate checks as fail-closed gates. The existing PolicyRegistry selects policy versions and AuthorityDecisionStore atomically rechecks both policy/context selections. An expired successor cannot fall back to an older policy.

Tier classification comes from the existing classifier. Relational structural change may classify Tier B, but cannot auto-permit. The rate gate remains unknown; no Tier A eligibility shortcut is introduced. The runtime does not propose an adaptation candidate, admit a human review, approve Tier B, activate a model/baseline, or consume an authority outcome as an execution token. Phase 3 execution remains disabled. Existing Phase 3 adversarial tests continue to enforce that human approval cannot waive safety gates.

A Phase 2 decision requires immutable model/baseline references. Scheduled live evaluation freezes the actual approved model document inside the model audit snapshot when it fits the existing bound. Connector results bind the model/version/snapshot and baseline version actually emitted by SII. Uploads require their retained baseline ID and content hash. Missing or unarchivable model references leave authority_decision null with an explicit limitation; evidence/maturity can still be retained. Existing external model archival integrity remains the Phase 2 trust boundary.

## Persistence and replay

The existing latest_payloads ledger storage is reused for context, policy, AuthorityDecision and an append-only finding/run snapshot index. TransactionGovernanceStore adapts the existing store to the host SQLite writer transaction; it does not implement another policy, maturity or adaptation evaluator. Upload and scheduled live lifecycle records use the existing finding_workflow_events log and its version/idempotency/predecessor checks. They never change operator workflow status. Scheduled lifecycle snapshots reflect the existing persisted finding state independently of maturity, including a resolved state when a run supplies no new changed evidence.

Each snapshot retains graph, maturity/persistence, context basis/qualification, lifecycle, tier classification, consequence, exact policy/decision basis when admissible, source reference and timestamps. Exact retries return the original snapshot; changed inputs under the same finding/run identity conflict. Later runs append, including maturity regression. Historical reads do not call adapters or current registries. Existing historical finding sources are not rewritten or backfilled. The database's source-immutability trigger remains intact.

Invalid governance input rolls back its partial context/policy/lifecycle work using a savepoint and retains an unavailable outcome. A valid analytical result is not discarded because it cannot support governance. Storage failures propagate; there is no permissive fallback. Connector governance admission and connector artifact publication may use different storage backends: a failed artifact publication can leave an inert governance audit record, but cannot expose a completed result or execute authority. Retry uses the original frozen record. There is no cross-database atomicity claim.

The frozen decision's audit_record can be validated using parse_decision, parse_basis and basis.validate_for(decision); replay_maturity reconstructs the retained evaluation. None reads current context or policy. Application-level append-only provenance is not cryptographic non-repudiation. Ledger retention/partitioning remains the existing governance architecture's limitation.

## API and Demo-Neraium handoff

No other repository is changed. Demo-Neraium should consume these server fields directly:

| Existing API/result | Field |
|---|---|
| GET /api/findings/{finding_id}, finding list entries | governance |
| Existing live finding detail/list | governance |
| Completed upload result | governance[source_finding_key] |
| Existing connector canonical result detail | product_result.governance[condition_id] |
| Immutable connector artifact | analysis_result.governance[condition_id] |

Unavailable validation outcomes can also include a bounded rejection_code (for example policy_expired_at_decision). Every envelope has schema_version = runtime-governance-v1, status (evaluated or unavailable), source_run_id, maturity_label (nullable), context_label, authority_label and execution_authorized=false. No snapshot is synthesized on historical reads.

Normal operator fields:

- maturity_label: Observed, Persistent, Corroborated, Characterized or Context-qualified, supplied by the backend; unavailable is null.
- maturity.reasons and lifecycle.state, when evaluated.
- context_label and context_qualification.
- consequence: the existing measurable consequence output, separate from maturity/authority.
- authority_label: Observation only.
- adaptation: null when no authority evaluation is available; otherwise status, label, reason, reasons, candidate_ref=null and execution_authorized=false. This is eligibility evaluation, not an activated model or a proposed Phase 3 candidate.

Audit fields, when available:

- graph.evidence and graph.observations, including evidence_family, source_signals, source_window, derived_from, provenance, source_run_id, payload.metrics, payload.source_windows, payload.source_evidence_refs, payload.reported_window and payload.limitations.
- maturity (the unchanged v2 contract), including persistence, pair_evaluations, trajectory (currently null), context_basis and context_qualification.
- lifecycle, classification.assessments, limitations and consequence.
- authority_decision, including policy_id/version, decision_outcome/reasons, limiting_evidence, contradicting_evidence, model references and human_review.
- audit_record.decision and audit_record.basis for exact Phase 2 replay.
- history on finding detail projections: append-ordered frozen runtime snapshots.
- review_history=[] and candidate_ref=null reflect that no runtime Phase 3 review/candidate path is enabled.

The frontend adds a restrained governance layer to existing cards/evidence views. Plain-language maturity and authority are display fields, not frontend calculations. Existing navigation/layouts and measurable-consequence placement remain. Audit JSON and details stay behind disclosure; there is no approval or activation button.

## Validation and adversarial review

Validation used Python 3.12.3 and the repository backend dependencies (`pip check`: no broken requirements). Frontend setup used `npm run setup:codex` and the lockfile.

- Final runtime adapter tests: **27 passed**. Includes a full normalized telemetry → real SII → canonical condition → governance integration, real live persistence, authenticated upload persistence, API/artifact replay, explicit limited evidence, missing siblings, future windows/context, immutable retries and lifecycle/maturity independence.
- One broad backend run covered all governance/adversarial tests, finding/API and canonical-result tests, consequence, SII, model/baseline, adaptive-learning, operational lifecycle and maintenance regressions: **688 passed; one existing 15-second comparison-upload polling test timed out while still saving**. Its unchanged isolated rerun passed; the combined final recheck of that test plus all 27 adapter tests reported **28 passed**. No test deadline was relaxed.
- A targeted pass after lifecycle/window integration changes covered runtime governance, telemetry handoff, finding workflow and live analysis: **59 passed**.
- Frontend: lint, production build and the unchanged performance budgets passed; **563 tests in 65 files passed**. Audit details load on disclosure. The engineering bundle remains within its existing raw and gzip budgets.
- Chromium: **2 passed**, covering the server-supplied governance layer, lazy audit disclosure, absence of approval/activation controls, and the existing 390×844 progressive evidence layout/overflow check.
- `git diff --check`: passed. No governance execution consumer or model/baseline writer was added.

Broad backend command (output captured, not streamed):

```sh
python -m pytest tests/test_runtime_governance.py tests/test_evidence_governance.py tests/test_governance*.py tests/test_finding*.py tests/test_live_analysis_phase2.py tests/test_telemetry_analysis_service.py tests/test_telemetry_result*.py tests/test_telemetry_canonical_result*.py tests/test_measurable_consequence.py tests/test_consequence*.py backend/tests/test_consequence_quantification.py tests/test_sii*.py tests/test_behavioral_model*.py tests/test_behavioral_baseline_workflow.py tests/test_adaptive_learning.py tests/test_operational_lifecycle.py tests/test_shared_maintenance_workflow.py -q --disable-warnings
```

Final focused recheck:

```sh
python -m pytest tests/test_behavioral_baseline_workflow.py::test_completed_comparison_uses_distinct_dataset_and_analysis_ids_and_scopes_findings tests/test_runtime_governance.py -q --disable-warnings
```

The complete diff received a read-only adversarial review after implementation and targeted corrections. Reviewed boundaries included authenticated scope, non-authoritative frontend inputs, source windows/availability, shared lineage, source limitations, stale policy/context, immutable source triggers, concurrent append conflicts, historical retries, lifecycle independence, consequence separation and non-execution. Review corrections preserved normalized source timestamps, independent lifecycle state, explicit unavailable outcomes and the existing frontend budget.

CRITICAL: none. HIGH: none. MEDIUM: none. LOW: the existing 15-second polling test remains sensitive to validation timing; its isolated rerun passed. Documented limits remain: relational-only admission, no supported multi-family trajectory, no new external-context verification adapter, no runtime Phase 3 candidate/review admission, existing external archival trust and ledger retention, and no distributed transaction across connector storage and the governance ledger.

**NO BLOCKING FINDINGS.**
