# Product evidence boundary

Neraium reports observed behavior, relationship changes, operating context,
persistence, evidence support, limitations, and mathematically supported measurable
consequence. It does not determine why a physical condition occurred. Cause,
diagnosis, ranked physical hypotheses and automatic corrective action are not
product outputs. Renaming attribution as an explanation, driver or mechanism
does not make it evidence.

This correction follows a fresh reproduction on main
`757267e445cc9d9e9f1c01388ed18915df73e012`: `build_analysis_explanation` generated
`likely_cause` with no cause input. That legacy behavior **predates PR #125**.

## Trace and correction

| Boundary | Source | Current behavior |
|---|---|---|
| GENERATED | `services/analysis_explanations.py`: `build_insights`, `water_interpreted_insights`, `build_operator_interpretation` | No cause fields or tag-name-derived physical mechanisms; observed relationships and supporting evidence remain |
| GENERATED | `water_intelligence/interpreter.py` | No prior-derived hypothetical explanations or associated inferred checks; metric/context/support calculations remain |
| GENERATED | `services/driver_attribution.py`, `subsystem_motifs.py`, `sii_runner.py` | Retired narrative/action/ranking fields are null/empty; attribution categories are not promoted into runner evidence; internal grouping and scoring inputs are unchanged |
| GENERATED | `services/finding_confidence.py`, `finding_classification.py` | Attribution status is null; alternative explanations are empty; evidence, classification and confidence calculations remain |
| GENERATED | `services/bedrock_interpreter.py` | Optional model instruction permits recorded observations only; explicit attribution responses are rejected; tests use a fake client |
| STORED | Upload result JSON, canonical analysis, evidence/finding snapshots | New product results omit retired conclusions before publication; historical blobs and their integrity hashes are not migrated or rewritten |
| PROJECTED | `analysis_result_contract`, `telemetry_result_projection`, `finding_workflow`, `evidence_package`, data read routes and evidence exports | Current projections discard legacy conclusion fields without recalculating evidence or consequence |
| PROJECTED | Frontend `engineeringReasoning`, `resultsPresentation`, `evidenceDashboardProjection` | Historical attribution fields are ignored; six independent evidence assessment dimensions remain |
| DISPLAYED | Evidence dashboard, finding classification/assessment, replay, Observation Center, System Body | Cause badges, attribution assessment, heuristic causes and associated accessibility text are removed; existing navigation and evidence detail remain |
| COMPATIBILITY-ONLY | Historical JSON, prior definitions, feedback identifiers, optional schema fields | Readable without schema migration; historical analytical attribution is not promoted into current views |

`product_evidence_contract.product_evidence` and the frontend `productEvidence`
projection remove named legacy conclusion fields on copied product payloads.
They are compatibility boundaries, not replacements for removing generation.
They do not rewrite strings, telemetry column names, immutable consequence facts,
source identifiers, or provenance. Historical storage is not altered by reads.

Nullable/empty compatibility values remain where existing callers expect them:
`attribution_status`, `likely_driver`, `next_operator_move`,
`counterfactual_driver_ranking`, and water/classification alternatives. The schema's
`primary_drivers` may still parse as an empty list. Legacy feedback keys such as
`environmental_cause` still accept human-authored history; current labels describe
an observation. Exception `cause` chains, service diagnostics and false/null engine
boundary flags are not physical conclusions and are retained.

The standalone `neraium-consequence` package and its immutable dependency pin are
unchanged. Canonical consequence objects are preserved exactly, including
`not_quantifiable`, source IDs, timestamp evidence, methodology and limitations.
The correction does not enable connector resource mapping or configure acquisition
gap limits.

## Regression evidence

`tests/test_product_evidence_contract.py` covers the original fresh reproduction,
persistent multiple-signal relationship evidence, deterministic evaluation,
historical canonical compatibility (including the old driver-to-title fallback), stored-record/API/export isolation, unchanged
quantified and insufficient consequence behavior, and literal signal/provenance
identifiers. `test_analysis_result_contract.py` additionally checks the complete
CSV runtime result. Current frontend projection and renderer tests inject legacy
attribution and assert that it never becomes text or accessibility output.

The same controlled CSV was also executed on the merged mainline and correction
worktrees. Captured baseline analysis, relationship model, data quality, persistence
assessment, selected SII evidence channels and canonical consequences were equal.
This comparison is regression evidence, not the outstanding full quantified
telemetry-to-UI deployment proof.

Local validation includes 88 affected backend tests, 162 canonical/API/persistence/
consequence tests in the earlier focused pass (these sets overlap), all 539 frontend
unit tests, frontend lint/build/performance budgets, and 15 Chromium checks.
Chromium covers seven viewport sizes, progressive disclosure, evidence navigation,
unknown-identity isolation, accessibility, and quantified/insufficient consequence
rendering. The old browser fixture now explicitly selects its saved analysis,
matching main's existing rule that persisted latest results must not auto-activate.
The full configured backend suite and PR checks are recorded separately in the PR.

After this correction is merged, the separate consequence workstream still needs
fresh Cases A/B/C, explicit connector resource configuration, acquisition-specific
gap limits, full persistence/replay/API/UI proof and a deployment-readiness verdict.
An open correction PR does not certify current main.
