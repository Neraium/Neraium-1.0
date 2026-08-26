# Structural-facade leftover-language audit

Date: 2026-08-26

Scope: customer-facing backend payload/projection code, frontend production code, affected tests, and relevant Markdown documentation.
Terms: causal/causality/caused, root cause, counterfactual, failure-time/RUL variants, multi-site/facility variants, federation, simulation, persistent cognition, and behavioral/digital twin.

## Result

No production frontend reads a removed structural-facade field. `projected_time_to_failure*` and `distributed_cognition_governance` remain only in negative compatibility tests. The normal upload/sample authority does not emit the removed causality, counterfactual, synthetic fleet, cognition-memory, twin, simulation, federation, training, certification, or static-reference packages.

The audit retains and explicitly classifies four unresolved compatibility/review seams instead of silently changing them: `counterfactual_driver_ranking`, `causal_evidence`, compatibility `evidence_lineage`, and separately mounted cognition/distributed/ecosystem endpoints.

## Legitimate qualified production language

The following hits describe bounded evidence or machine-readable false/non-causal flags. They do not assert cause:

- `backend/app/engine/sii/behavioral_graph.py`, `behavioral_model.py`, `event_memory.py`, `expected_behavior.py`, `mode_conditioned_baseline.py`, `multiscale_analysis.py`, `propagation_analysis.py`, and `relationship_graph.py`: qualified production behavioral/relationship evidence with explicit non-causal limitations and `causal_claim: false`-style fields.
- `backend/app/engine/sii/evidence_fusion.py`, `backend/app/services/analysis_result_contract.py`: transport boolean fields recording that causal interpretation/proof was not supplied.
- `backend/app/services/evidence_package.py`, `evidence_package_fingerprint.py`, and `baseline_analysis_repository.py`: temporal ordering and historical-pattern evidence explicitly labeled non-causal.
- `backend/app/services/health_relevance.py` and its benchmark: separately governed production boundary with non-causal safeguards; unchanged by P0.6.

## Explicit limitations and disclaimers

- `frontend/src/viewModels/operationalHelpers.js`, `operatorFinding.js`, and `frontend/src/components/HelpChangelogWorkspace.jsx`: tell customers that evidence does not establish root cause or causality.
- `backend/app/engine/explanations.py`, `sii_engine.py`, `backend/app/services/analysis_explanations.py`, `bedrock_interpreter.py`, `finding_classification.py`, `investigation_guidance.py`, and `operator_report.py`: prevent causal, diagnostic, or failure-prediction overstatement.
- `frontend/src/components/engineering/InvestigationOutcome.jsx`: “Root cause confirmed” is an operator-recorded investigation outcome, not an SII-generated analytical classification.
- Production/contract documentation with these terms uses them as prohibitions or limitations: `ACTIVE_ANALYSIS_PATH.md`, `ANALYSIS_RESULT_CONTRACT.md`, `ARCHITECTURE.md`, `BEDROCK_INTERPRETATION.md`, the `EVIDENCE_PACKAGE_*` documents, `HISTORICAL_DATA_INGESTION_TRUST_V1.md`, `INTELLIGENCE_CONTRACT.md`, `OPERATING_CONTEXT_V1.md`, `PRODUCT_LANGUAGE.md`, `sii_architecture.md`, `sii_math_audit.md`, `sii_math_specification.md`, `sii_mathematical_refinement.md`, `sii_phase2_main_audit.md`, and `sii_robustness_assessment.md`.

## Internal or experimental

- `backend/app/services/structural_cognition.py` and its imported cognition, causality, counterfactual, federation, simulation, twin, training, ontology, search, and static-memory modules: retained research implementation with no default upload/sample caller.
- `backend/api/cognition_contracts.py`, `distributed_cognition.py`, and `ecosystem.py`: separately mounted legacy/research surfaces; authority remains `review_required` and they are not used by the default upload result.
- `backend/app/routers/replay.py` `live_causal`: explicit pre-existing alternate replay mode metadata, not the normal upload replay and not a causal proof claim.
- Research documents are now labeled internal/experimental or future at their entry point: `behavioral_infrastructure_laboratory.md`, `cultivation_structural_cognition.md`, `infrastructure_cognition_federation.md`, `long_horizon_structural_memory.md`, `operator_cognition_training.md`, `sii_behavioral_twin_model.md`, `sii_cross_domain_structural_intelligence.md`, `sii_distributed_cognition_network.md`, `sii_federated_cognition_exchange.md`, `sii_operational_reasoning_simulation.md`, `sii_operator_cognition_training.md`, `sii_research_ecosystem.md`, `sii_structural_cognition_graph.md`, and `sii_structural_evolution_search.md`.
- `foundational_reasoning_substrate.md` and `hospitality-aquatic-adaptive-layer.md` are research/domain design material; the central `SII_AUTHORITY_BOUNDARIES.md` governs their non-production interpretation.

## Static or reference

- The following documents are explicitly labeled static reference: `sii_ecosystem_standard.md`, `sii_evidence_lineage_standard.md`, `sii_interoperability_standard.md`, `sii_operational_language.md`, `sii_read_only_integration_standard.md`, `sii_reference_architecture.md`, and `sii_runtime_standard.md`.
- `sii_evolving_ontology_governance.md` and `autonomous_ontology_governance.md` are labeled internal/experimental and static reference.
- `SII_AUTHORITY_BOUNDARIES.md` records the four-way production, internal/experimental, static/reference, and future classification. Hits in that document describe prohibited or deferred capability, not shipped functionality.

## Test-only

- Frontend negative compatibility fixtures: `DiagnosticsPanel.test.jsx` and `SystemTopologyWorkspace.test.js` prove removed prediction/governance fields are ignored.
- `EngineeringReasoningWorkspace.test.js` “multi-site portfolio” uses distinct persisted site evidence, not the synthetic facade network.
- `LiveMonitoringWorkspace.test.js` and `evidenceCorrelation.test.js` exercise non-causal wording/flags.
- Backend component/contract fixtures in `test_bedrock_interpreter.py`, `test_cognition_coherence.py`, `test_distributed_cognition_api.py`, `test_engine.py`, `test_engineering_finding_classification.py`, evidence-package tests, finding-guidance tests, Health Relevance tests, replay tests, SII phase tests, `test_structural_cognition.py`, `test_structural_framework.py`, and `test_temporal_math_engine.py` either verify limitations or independently test retained internal research code.

## Historical documentation of removed or unrelated behavior

- `.planning/research/structural-facade-authority-audit.md` and `structural-facade-consumer-map.md` document the removed behavior and approved dispositions.
- `AUDIT_SWEEP_2026-05-21.md`, `CSV_UPLOAD_503_ROOT_CAUSE.md`, `JOB_PROGRESS_BENCHMARK.md`, `UPLOAD_REFRESH_STATE_RECONCILIATION.md`, `database-migrations.md`, and `upload_state_integrity_refactor.md` use “root cause” for historical software incidents or implementation analysis, not customer SII conclusions.
- `SII_MATH_STACK_IMPLEMENTATION_PLAN.md` and `sii_validation_plan.md` describe planned/validation work, not default customer authority.

## Unresolved and requiring review

1. `counterfactual_driver_ranking` and nested `counterfactual_effect` remain in driver attribution and `sii_intelligence` because Phase 1 classified the mixed package as `review_required`. Current values carry ordinary ranked evidence or explicit unknowns; the name remains capability-signaling.
2. `causal_evidence` remains a component name in `backend/app/engine/temporal_math.py` and `backend/app/services/sii_runner.py`. Its value is confidence-weighted instability, not an approved causal contract. Phase 3 did not rename it because doing so would change a production math/compatibility contract outside the approved facade cleanup.
3. Compatibility `evidence_lineage` remains by binding decision. Its legacy content can contain `propagation_confirmations` and static-memory references. Formal production traceability, source windows, and bounded SII evidence remain separate.
4. The mounted cognition/distributed/ecosystem endpoints remain customer-reachable depending on deployment configuration. Their authority/access redesign is outside the default-upload Phase 3 scope and must not be mistaken for production upload evidence.

These four seams explain all remaining capability-signaling hits in the measured upload or customer-facing backend surface. They are not silently endorsed as qualified production claims.
