# Analysis Result Contract

Neraium analysis endpoints expose one canonical `AnalysisResult` object at `analysis_result`.
Legacy fields can remain for compatibility, but frontend rendering should prefer this contract.

## Canonical SII Source

Uploaded telemetry is evaluated once through `app.engine.sii_engine.evaluate_sii`. The raw canonical evidence object is available at top-level `sii_result` with engine identity `neraium_sii/v2`.

`analysis_result` remains the frontend-oriented presentation and evidence-index contract derived from canonical Phase 1 compatibility fields. Phase 2 empirical-threshold, graph, mode-conditioned baseline, adaptive-persistence, multiscale, and temporal sections are active supporting evidence. Phase 3 physics-informed reasoning and transparent evidence fusion are active downstream evidence-enrichment sections. Neither phase independently determines `analysis_result` findings, state, severity, or confidence. Evidence records may expose Phase 2 support at `phase_2_supporting_evidence`.

The canonical `sii_result` may include:

- `data_conditions`
- `operating_modes`
- `signal_drift`
- `relationship_analysis`
- `relationship_graph`
- `covariance_analysis`
- `temporal_analysis`
- `multiscale_analysis`
- `persistence_analysis`
- `physics_reasoning`
- `physics_evidence` (backward-compatible alias of `physics_reasoning`)
- `evidence_fusion`
- `uncertainty`
- `processing_trace`

Clients may continue reading legacy top-level fields for compatibility, but no client should trigger or infer a second analytical pass.

## Phase 3 Physics Reasoning

`physics_reasoning` is produced by `backend/app/engine/sii/physics_reasoning.py` after every Phase 2 analytical module. The engine contains no domain priors. Callers supply priors at `config.physics_reasoning_config.priors`; `config.engineering_priors` remains an accepted configuration alias.

Every configured prior defines:

- `id`, `name`, `description`, and `domain`
- `equipment_types`
- `required_signals`
- `required_relationships`
- `required_operating_modes`
- `prerequisites`
- `expected_behavior`
- `validity_conditions`
- `confidence_modifier`
- `limitations`
- `reasoning_template`

`prerequisites`, `validity_conditions`, and `expected_behavior.conditions` use declarative selectors. A condition contains `source`, `path`, optional `where`, optional `field`, `operator`, expected `value`, optional `quantifier`, and a human-authored behavioral `description`. Supported logic is explicit `all` or `any`; supported quantifiers are `all`, `any`, and `none`. Comparison operators are `eq`, `not_eq`, `in`, `not_in`, `contains`, `not_contains`, `contains_all`, `intersects`, `exists`, `truthy`, `falsy`, `gt`, `gte`, `lt`, and `lte`.

The evaluator first checks equipment context, required telemetry, relationship availability, operating mode, prerequisites, and validity. If any required applicability evidence is absent or unsatisfied, the prior returns `status: not_applicable`, records exact reasons, does not evaluate expected behavior, and contributes no evidence. An applicable prior returns `supported`, `contradicted`, or `indeterminate`, with source paths, operators, expected values, observed values, supporting evidence, contradictory evidence, limitations, reasoning trace, and its unchanged configured confidence modifier. A confidence modifier is descriptive metadata: it is never applied, aggregated, normalized, or treated as probability.

The section contains:

- `status`
- `evaluated_priors`
- `applicable_priors`
- `supporting_priors`
- `contradictory_priors`
- `indeterminate_priors`
- `ignored_priors`
- `limitations`
- `reasoning_trace`

No configured priors is a valid limited state (`no_configured_engineering_priors`); the engine does not supply a fallback assumption.

## Phase 3 Transparent Evidence Fusion

`evidence_fusion` is produced by `backend/app/engine/sii/evidence_fusion.py` after physics reasoning. It receives and preserves the canonical outputs from signal drift, relationship analysis, operating modes, physics reasoning, adaptive persistence, temporal analysis, multiscale analysis, relationship graph, covariance analysis, data quality, sensor health, and uncertainty.

Every source module is retained in `evidence_inventory` with its full payload, originating module, source status, limitations, uncertainty, processing trace, and one explicit classification: `Supporting`, `Limiting`, `Contradictory`, or `Neutral`. Complete statistical module outputs remain neutral unless the source explicitly classifies them; limited or failed module states remain limiting. Physics-condition evidence retains its configured-expectation classification. No averaging, weighting, voting, Bayesian update, probability estimate, rank, or opaque confidence calculation occurs.

For each applicable, conclusive engineering prior, fusion creates a deterministic behavioral observation from the configured reasoning template. Every observation exposes:

- contributing analytical modules
- supporting, limiting, and contradictory evidence
- all evaluated engineering priors
- ignored priors and exact reasons
- analytical uncertainty
- source evidence identifiers and module statuses in its processing trace
- `engineering_interpretation: null`
- `human_review_required: true`
- explicit false flags for causal interpretation and maintenance recommendations

Observations describe consistency or inconsistency with configured behavior only. They are not findings, failure declarations, diagnoses, predictions, remaining-life estimates, or recommendations.

## Schema

Required top-level fields:

- `analysis_id`: stable id for this analysis run.
- `upload_id`: id of the uploaded telemetry source.
- `source_file`: uploaded CSV filename.
- `generated_at`: ISO timestamp when the contract was generated.
- `data_quality`: upload readiness, warning, integrity, and normalized telemetry summary.
- `executive_summary`: short operator summary for the Overview screen.
- `systems[]`: detected systems or telemetry groups with evidence-backed changes.
- `relationships[]`: relationship graph edges with strength, confidence, deltas, window, and evidence refs.
- `fingerprint`: baseline/current behavior summary, drift status, confidence, deviations, explanation, and evidence refs.
- `insights[]`: evidence-backed findings only.
- `recommendations[]`: evidence-backed operator checks only.
- `evidence_index`: reusable evidence objects keyed by `evidence_id`.
- `uncertainty`: data limitations, sensor-health limitations, temporal limitations, and module failures that affect interpretation.
- `processing_trace`: execution metadata including engine version, modules attempted, completed, limited, and failed, rows used, operating modes used, scales used, Phase 3 activation/effect, prior and observation counts, and runtime.
- `warnings[]`: safe display warnings.
- `errors[]`: failed-state errors.

Empty, processing, missing, and failed states must still return this shape with empty arrays and a `status` such as `empty`, `processing`, `missing`, or `failed`.

## Evidence Model

Every evidence item is stored once in `evidence_index`:

- `evidence_id`
- `type`
- `description`
- `source_tags`
- `metric_delta`
- `relationship_delta`
- `time_window`
- `confidence`
- `calculation_method`

`insights`, `relationships`, `fingerprint`, and `recommendations` reference evidence by id through `evidence_refs`.
The frontend must resolve refs through `evidence_index`; it should not display findings whose refs do not resolve.

## Normalized Telemetry

The normalized telemetry layer is built from the already parsed upload rows. It does not re-read the CSV.
Each normalized record contains:

- `timestamp`
- `tag_name`
- `value`
- `unit`
- `source_column`
- `quality`
- `missing_value_flags`
- `sampling_interval`
- `detected_metric_type`

The public contract includes a bounded `records` sample plus tag summaries so large uploads do not inflate result payloads.

## Relationship Graph

Canonical `relationships[]` contains changed relationship edges derived from telemetry windows:

- `source`
- `target`
- `relationship_type`
- `strength`
- `confidence`
- `baseline_strength`
- `current_strength`
- `change_percent`
- `supporting_metrics`
- `time_window`
- `evidence_refs`

Relationship evidence is currently derived from baseline and recent telemetry windows using correlation-based relationship changes together with graph-level structural analysis.

## Fingerprint Model

`fingerprint` summarizes:

- normal operating behavior
- current behavior
- drift status
- largest deviations
- confidence and confidence score
- supporting evidence refs
- plain-language explanation

Fingerprint summarizes canonical signal, relationship, persistence, covariance, and temporal evidence used to describe current system behavior. Fingerprint evidence must include at least the baseline/current window context and any metric or relationship deviations used in the explanation.

## Engineering Finding Context

Finding fields are additive. Current `insights[]` may include:

- `classification`: deterministic `type`, display `label`, classification `confidence`, evidence-linked `reasons`, `alternative_explanations`, `certainty_limit`, and `rule_version`.
- `data_confidence`: qualitative rating, summary, limitations, and affected signals.
- `sensor_health[]`: per-signal health plus evidence-backed conditions.
- `operating_mode`: baseline/recent labels, match strength, confidence, recorded differences, and reasons.
- `mode_conditioned_baseline`: selected comparison mode, match confidence, fallback status, baseline-selection explanation, and comparable rows or periods.
- `persistence`: fixed, adaptive, and temporal persistence status, support flags, supporting signals, elapsed-time or row-count basis, and summary.
- `multiscale`: eligible scales, agreeing and conflicting signals, cross-scale classification, and interpretation.
- `relationship_evidence`: paired sample support, relationship-change measurements, graph-level structural metrics, and evidence refs.
- `investigation_guidance[]`: ordered, frontend-safe checks with `rank`, `check`, evidence-linked `reason`, `category`, and `editable`.
- `activity_timeline[]`: source-bounded evidence events. Events use source `time`, `start`/`end`, or an explicit `period_label`; consumers must not infer missing dates.
- `certainty_limit`, `alternative_explanations`, and `data_limitations`.

Canonical classification types are `known_operational_change`, `possible_instrumentation_issue`, `unexplained_systemic_change`, and `insufficient_evidence`. Supported guidance categories are `instrumentation`, `controls`, `operating_context`, `physical_system`, `data_quality`, and `documentation`.

`recommended_investigation[]` and `recommended_first_action` remain populated as text compatibility views of `investigation_guidance`. Clients should prefer `investigation_guidance` when present.

Historical canonical payloads may not contain these fields. Frontends must use `insufficient_evidence` presentation or an explicitly unclassified legacy state, show unavailable context, and explain that contextual classification was not recorded. They must never infer `unexplained_systemic_change` from legacy severity or confidence.

## Frontend Usage Rules

- Overview renders `executive_summary` only for completed analysis.
- Insights render insight explanation plus resolved evidence.
- Systems render `systems[]` and relationship changes.
- Fingerprint renders drift explanation, confidence, and resolved evidence.
- More renders data quality, source file, uncertainty, processing trace, warnings, errors, and analysis metadata.
- Phase 2 supporting evidence may be displayed only as supporting context unless and until the finding contract explicitly promotes it to authoritative finding logic.
- Phase 3 engineering observations may be displayed only as traceable behavioral context. A client must not relabel them as diagnoses, causes, predictions, decisions, or recommendations.
- Never render placeholder findings, generic pending-verification text, demo systems, fake recommendations, or stale previous analysis as the current result.
- If a field is unavailable, hide it instead of showing placeholder copy.
