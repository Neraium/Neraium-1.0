# Results progressive-disclosure implementation design

**Campaign:** `results-progressive-disclosure`

**Date:** 2026-08-25

**Input:** `.planning/research/results-progressive-disclosure-audit.md` (accepted)

**Boundary:** frontend presentation only; no SII semantic changes and no telemetry connectors, secrets, repositories, registries, normalization, workers, migrations, or security changes

## Outcome and decisions

Implement one source-to-presentation boundary:

`buildEngineeringReasoningModel -> explicit projectors -> Results -> Review -> Investigation -> Evidence`

The existing engineering model remains the source normalizer. Components below it receive only their depth projection. Evidence is moved, not deleted.

Key decisions:

1. **Pure JavaScript projectors, not CSS hiding.** Add `frontend/src/viewModels/resultsPresentation.js`. Every projector constructs a new object from an allowlist; it never spreads `model`, `model.result`, a finding, a workflow object, or an evidence package.
2. **Exact route identity.** `/findings/:id`, `/investigations/:id`, and `/evidence/:id` all require an exact `finding.id`. No detail route may fall back to `model.selectedFinding`, `model.relationships[0]`, another site, or another run.
3. **Insufficient is not unavailable.** `insufficient` means the source explicitly withheld a conclusion. `unavailable` means identity was not found or required source structure is missing/malformed. The latter must not look like an evidence result.
4. **Same path for live and historical sources.** Once `analysisBelongsToBaseline` accepts a result, both current and `/analyses/:run` results call the same model builder and projectors. Historical compaction may make a deep channel unavailable; the projector states that absence and never recreates it.
5. **Complete audit projection at the final depth.** Evidence Record may be dense and may retain exact channel payloads, but it receives a purpose-built evidence projection, not the whole result DTO.
6. **Historical ingestion review stays separate.** `HistoricalIngestionReview` is the data-trust/mapping lifecycle. Its signal IDs, units, exclusions, and trust evidence do not belong to finding depth rules and must not be folded into Results, Review, Investigation, or Evidence projections.
7. **Scope precedes payload.** Every package and every SII channel is projected with an explicit, source-backed scope. An analysis/run package or system/run SII channel may be shown as related context at Evidence depth, but it is never silently promoted to finding provenance.
8. **Package identity is not finding identity by default.** `model.result.evidence_package` is analysis-level in production. Its ID and immutable details must not enter a finding-owned `identity` or `lineage.provenance` unless an explicit source field links that exact package ID to that exact finding. Otherwise it is labeled run-scoped related evidence, or unavailable.

Rejected alternatives:

- Passing the full finding/model and concealing sections: fields remain available to the wrong component and future additions leak by default.
- Four independent normalizers: they would drift and could calculate different meanings from one source.
- A single aggregate confidence score: it violates the evidence contract and would imply attribution from change support.
- Borrowing a global relationship when a finding lacks one: it can attach another finding's evidence.
- Treating the sole analysis package as the selected finding's package: the package builder can select the first eligible relationship and first finding independently, so route selection, title similarity, array position, or “only package in the run” is not ownership evidence.

## Exact file plan

### Add

- `frontend/src/viewModels/resultsPresentation.js` — all four projectors, shared runtime guards, exact identity resolver, relationship/package association resolvers, scope-labeled channel extraction, and exported key allowlists.
- `frontend/src/viewModels/__tests__/resultsPresentation.test.js` — runtime contracts, canary leakage tests, malformed variants, route identity, two-finding association isolation, live/history parity, and channel completeness.
- `frontend/src/components/engineering/EvidenceAssessment.jsx` — restrained seven-dimension Review block that accepts only `assessment`.

### Change

- `frontend/src/viewModels/engineeringReasoning.js` — remove `context.relationships[0]` as a finding relationship fallback; only embedded finding relationships or explicitly matching relationship IDs may enter `finding.relationships`; retain explicit raw finding/package and finding/relationship reference fields for the association resolver without converting them into ownership.
- `frontend/src/components/EngineeringReasoningWorkspace.jsx` — build memoized projections, make all three detail routes exact, and pass projection-only props.
- `frontend/src/components/engineering/OperationsBrief.jsx` — consume `ResultsProjection`; remove raw gap rows and duplicate escalation evidence.
- `frontend/src/components/engineering/FindingSummary.jsx` — consume `ResultFindingCardProjection`; remove evidence disclosure, next-action guidance, classification/workflow DTOs, and secondary action menu.
- `frontend/src/components/engineering/FindingCaseWorkspaces.jsx` — render Review, Investigation, and Evidence from their projections; split investigation-safe channel summaries from the complete SII/audit record.
- `frontend/src/components/setup/IntakeFlowPanel.jsx` — comparison completion says “Analysis complete” and shows projected counts/systems before the Open Results action; baseline completion remains unchanged.
- `frontend/src/styles/engineering-reasoning.css` — summary-card, assessment, investigation, evidence, and responsive constraints.
- `frontend/src/styles/upload-intelligence.css` — calm comparison-completion summary layout only.
- `frontend/src/components/engineering/FindingSummary.test.js` — replace tests that require early evidence with compact-card inclusion/exclusion tests.
- `frontend/src/components/engineering/FindingCaseWorkspaces.test.js` — decision/deep/audit DOM boundaries and unavailable-channel rendering.
- `frontend/src/components/EngineeringReasoningWorkspace.test.js` — route identity, stable/insufficient/unavailable, source parity, and DOM leakage.
- `frontend/src/components/DataConnectionsWorkspace.stale-progress.test.js` — comparison-complete counts and omission of technical completion metrics.
- `frontend/tests/e2e/engineering-reasoning.spec.js` — full four-depth traversal and measurements at phone/tablet/desktop.
- `frontend/tests/e2e/analysis-complete-layout.spec.js` — calm analysis completion plus stable/insufficient variants.
- `frontend/tests/e2e/frontend-resilience.spec.js` — malformed collections and unknown Review routes.

`frontend/src/components/setup/HistoricalIngestionReview.jsx` and its tests are inspected but intentionally unchanged. If `IntakeFlowPanel` reorders it, preserve it as a separately labeled data-trust lifecycle and preserve all existing behavior.

## Source boundary and relationship scoping

Projector signatures:

```js
projectResults(model, reviewRecords, options = {})
projectFindingReview(model, requestedFindingId, reviewRecord)
projectInvestigation(model, requestedFindingId, reviewRecord)
projectEvidenceRecord(model, requestedFindingId, reviewRecord)
```

`options.sourceMode` is `"live" | "historical"` for tests/diagnostics only and must not expose a run identifier in Results cards. All functions accept unknown input, use `Array.isArray`, finite-number checks, plain-object checks, bounded text/list helpers, and return a discriminated variant without throwing.

Before projection, change `buildFinding` relationship ownership:

- accept `supporting_relationships`, `contributing_relationships`, or `relationships` embedded on that raw finding;
- optionally accept global rows only when the raw finding carries an explicit `relationship_id`, `relationship_ids`, `title_evidence_relationship_id`, or an equivalent direct ID that exactly equals the normalized row ID;
- do not infer ownership from list order, selected finding, title similarity, or a single global relationship;
- when no owned row exists, retain an empty relationship list and let Investigation/Evidence expose the channel as unavailable.

### Production package ownership constraint

The current package is not intrinsically finding-scoped:

- `build_evidence_package` reads one analysis identity and then separately takes the first eligible result relationship and the first condition/finding (`backend/app/services/evidence_package.py:461-491`, `:822-863`).
- The package schema contains analysis/system/baseline/dataset identity but no finding ID (`backend/app/services/evidence_package.py:331-360`).
- The legacy compatibility path adds `evidence_package_id` only to the first projected finding (`backend/app/services/evidence_package.py:989-999`). That explicit field is usable for that exact finding, but the existence of `result.evidence_package` alone is not.
- The current Evidence route reads `model.result.evidence_package.id` for every selected finding (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:17-19`, `:382-401`). The new projector must close that cross-finding attribution path.

Define one fail-closed `resolvePackageAssociation(model, exactFinding)` helper. It returns exactly one of:

```js
PackageAssociation =
  | {
      scope: "finding",
      scopeLabel: "Package explicitly linked to this finding",
      sourcePath: string,
      packageId: string,
      immutableDetails: object,
      relationshipLink: { state: "matched" | "unavailable", sourcePath: string | null, relationshipId: string | null }
    }
  | {
      scope: "run",
      scopeLabel: "Related package for this analysis run — not finding provenance",
      sourcePath: "model.result.evidence_package",
      packageId: string,
      immutableDetails: object,
      relationshipLink: { state: "matched" | "different" | "unavailable", sourcePath: string | null, relationshipId: string | null }
    }
  | {
      scope: "related",
      scopeLabel: "Related package explicitly referenced by this finding — not finding provenance",
      sourcePath: string,
      packageId: string,
      immutableDetails: object | null,
      relationshipLink: { state: "matched" | "different" | "unavailable", sourcePath: string | null, relationshipId: string | null }
    }
  | {
      scope: "unavailable",
      scopeLabel: "No package is explicitly attributable to this finding",
      sourcePath: null,
      packageId: null,
      immutableDetails: null,
      relationshipLink: { state: "unavailable", sourcePath: null, relationshipId: null }
    };
```

Association rules are verifiable and never positional:

1. Normalize IDs as non-empty exact strings; do not case-fold, slugify, or compare display text.
2. `scope: "finding"` is allowed only when an explicit source field on the exact raw/normalized finding (`evidence_package_id`, `evidencePackageId`, or a documented equivalent direct-reference field) exactly equals `model.result.evidence_package.id`, or when a future package field explicitly names the exact finding ID and the package's run identity also matches the current result. Record the exact `sourcePath`. A package ID in a workflow/review record is not accepted unless that record also proves the same exact source finding identity.
3. A result-level package with an exact package ID and an `analysis_id` exactly matching the current result's `comparison_analysis_id`/`analysis_run_id` may be `scope: "run"` when rule 2 is not satisfied. Render it only in a visually separate “Related run package” block with the scope label and source path above its ID/details. Never copy its ID/details into finding `identity`, `lineage.provenance`, export ownership, or an unlabeled package section.
4. `scope: "related"` is allowed only for an explicit finding field such as `related_evidence_package_ids` or a documented correlation response that identifies the current package and related package. It is contextual evidence, never the finding's immutable record. Do not infer it from matching system, signals, title, relationship values, route, array order, or there being one package.
5. If package shape/ID/run identity is missing or mismatched, return `unavailable`. If a finding explicitly references package A while the loaded result contains package B, do not expose B as finding or related provenance; record the mismatch as an unavailable package limitation.
6. Relationship association is independent. A package primary relationship is `matched` only when its `source_model_edge_id` exactly equals a finding-owned relationship ID, or when an explicit finding relationship-reference field exactly identifies that package relationship. Equal source/target names, values, or list position are not sufficient. A finding-linked package may therefore have `relationshipLink.state: "unavailable"`; do not fill the finding's relationship channel from it.

`buildFinding` may carry direct source references in a dedicated non-rendered `sourceAssociations` object, for example `{ evidencePackageId, relatedEvidencePackageIds, relationshipIds, sourcePaths }`. It must not put a package ID in `technicalIdentity`, `identity`, or provenance merely because the result has a package. Projectors consume the references and emit only the scoped association above.

## Shared runtime primitives

```js
// Every value is a new plain object/array; no source object references.
AssessmentValue = {
  value: string,             // source label, or "Unavailable" / "Not established"
  state: "supported" | "limited" | "unknown"
}

ChannelState = {
  state: "available" | "limited" | "unavailable",
  reason: string             // empty only when available
}

EvidenceScope = "finding" | "relationship" | "system" | "run"

ScopedSource = {
  scope: EvidenceScope,
  scopeLabel: string,        // rendered; e.g. "Analysis-run evidence — not finding-specific"
  sourcePath: string
}

Action = {
  label: string,
  route: string              // canonical local path only
}

UnavailableVariant = {
  contractVersion: "results-presentation.v1",
  depth: "results" | "review" | "investigation" | "evidence",
  variant: "unavailable",
  title: "Result unavailable" | "Finding unavailable" | "Investigation unavailable" | "Evidence record unavailable",
  explanation: string,
  backAction: Action | null
}
```

Never put the requested unknown identity into user-visible text. `Object.freeze` exported allowlist arrays; unit tests compare exact keys at every nested level.

## ResultsProjection contract

```js
ResultsProjection = ResultsReady | ResultsInsufficient | ResultsProcessing | ResultsUnavailable

ResultsReady = {
  contractVersion: "results-presentation.v1",
  depth: "results",
  variant: "ready",
  outcome: "analysis_complete" | "stable",
  eyebrow: "Operations Summary",
  headline: string,
  explanation: string,
  systemLabel: string,
  counts: {
    findingsForReview: number,
    systemsRepresented: number
  },
  cards: ResultFindingCardProjection[]
}

ResultFindingCardProjection = {
  findingKey: string,             // opaque route key; never displayed
  systemContext: string,
  assetContext: string | null,
  title: string,
  behavior: string,               // one bounded system-behavior sentence
  priority: string,               // workflow effective priority, then existing classification review priority; otherwise "Not assigned"
  changeConfidence: string,       // finding.confidenceDimensions.changeDetection.level, then finding.tier
  materialLimitation: string | null,
  reviewState: string | null,
  assignment: string | null,
  primaryAction: { label: "Review finding", route: `/findings/${encodedFindingKey}` }
}

ResultsInsufficient = {
  contractVersion: "results-presentation.v1",
  depth: "results",
  variant: "insufficient",
  outcome: "insufficient",
  eyebrow: "Operations Summary",
  headline: "Insufficient evidence",
  explanation: string,            // one human sentence from material limitation/sufficiency reason
  systemLabel: string,
  counts: { findingsForReview: 0, systemsRepresented: number },
  improvement: string | null,     // only source-backed history/comparability need
  auditAction: Action | null       // only when an exact scoped finding exists
}

ResultsProcessing = {
  contractVersion: "results-presentation.v1",
  depth: "results",
  variant: "processing",
  headline: "Analysis in progress",
  explanation: string
}
```

Stable is a `ready` result with `outcome: "stable"`, both counts zero, no cards, headline `No supported material behavioral change.`, and one concise explanation. It renders no empty evidence panels.

Allowed Results keys are exactly those above. Forbidden at any nesting level: `rawVariables`, `rawSource`, `rawTarget`, `technicalIdentity`, `relationships`, `relationshipEvidence`, `comparison`, `baselineValue`, `currentValue`, `signedChange`, `absoluteChange`, `metric`, sample counts, windows, timestamps, evidence refs/objects, gaps/signals, lineage, provenance, engine/version/build/config hashes, package/run/upload/dataset IDs, SII/phase payloads, corroborating relationship lists, investigation guidance, full classification, full workflow, outcome/history, trace, and `result`.

Field sources:

| Results field | Source order |
|---|---|
| finding key | exact `finding.id` |
| system/asset | `finding.location.system`; asset from `asset` then `subsystem`; system fallback `finding.system` |
| title | existing normalized `finding.title` |
| behavior | `finding.observedChange`, one sentence, max 180 characters |
| priority | `reviewRecord.priority`, `reviewRecord.recommendedPriority`, `classificationPresentation.reviewPriority`, else `Not assigned` |
| change confidence | `confidenceDimensions.changeDetection.level`, `confidenceContract.change_detection.level`, `finding.tier`, else `Unavailable` |
| limitation | `primaryLimitation` only when non-empty and material; max 120 characters |
| workflow | normalized state label and assignment label only |
| system count | unique non-empty card `systemContext` values; do not use raw signal/system IDs |

## FindingReviewProjection contract

```js
FindingReviewProjection = ReviewReady | ReviewInsufficient | ReviewUnavailable

ReviewReady = {
  contractVersion: "results-presentation.v1",
  depth: "review",
  variant: "ready",
  identity: { findingKey: string },
  header: { systemContext: string, title: string, reviewState: string | null },
  whatChanged: string,
  whyAttention: string[],          // 1..3 concise, deduplicated points
  assessment: {
    changeConfidence: AssessmentValue,
    evidenceQuality: AssessmentValue,
    causeAttribution: AssessmentValue,
    persistence: AssessmentValue,
    operatingContext: AssessmentValue,
    corroboration: AssessmentValue,
    evidenceSufficiency: AssessmentValue
  },
  materialLimitation: string | null,
  checks: { label: string }[],     // 0..3; non-diagnostic source-backed checks
  primaryAction: { label: "Open investigation", route: `/investigations/${encodedFindingKey}` }
}

ReviewInsufficient = same top-level keys, with `variant: "insufficient"`, `whatChanged` equal to
"A supported material behavioral change cannot be shown from the available evidence.", bounded source-backed reasons in `whyAttention`, independent assessment values, optional material limitation, `checks: []`, and an Investigation action only if finding-scoped engineering evidence exists.
```

Assessment mapping remains independent:

- change confidence: `confidenceDimensions.changeDetection.level` / `confidenceContract.change_detection.level` / tier;
- evidence quality: `confidenceDimensions.evidenceQuality.level` / `classificationPresentation.dataConfidence.rating`;
- cause/attribution: `confidenceDimensions.interpretation.attribution_status` / `confidenceContract.interpretation.attribution_status`; absent is `Not established`, never inferred from high confidence;
- persistence: `classificationPresentation.persistence.label` / `confidenceContract.persistence.status`;
- operating context: `confidenceDimensions.operatingContext.status` / `classificationPresentation.operatingMode.match`;
- corroboration: `corroboration.corroboration_strength`, optionally a non-technical `N relationships` suffix only on Review; no relationship list;
- evidence sufficiency: explicit source sufficiency when present, else `Insufficient` when classification type/status is insufficient, `Supported for review` for a ready governed finding, otherwise `Unavailable`.

`whyAttention` uses existing `whyItMatters`, classification reasons, then normalized visible supporting prose, but never values/IDs. Checks use normalized `classificationPresentation.investigationGuidance[].check` and stay capped at three. Do not invent a generic engineering instruction.

Forbidden Review keys/content: relationship DTOs, baseline/current numeric comparisons, metric names, chart/node data, raw/canonical IDs, samples, exact windows/timestamps, lineage/provenance, engine/package metadata, full workflow panel, outcome/history/trace, full classification reasons panel, alternative-explanation dump, or technical assumptions.

## InvestigationProjection contract

```js
InvestigationProjection = InvestigationReady | InvestigationInsufficient | InvestigationUnavailable

InvestigationReady = {
  contractVersion: "results-presentation.v1",
  depth: "investigation",
  variant: "ready",
  identity: { findingKey: string },
  header: { systemContext: string, title: string, reviewState: string | null },
  primaryComparison: InvestigationRelationship | null,
  relationships: InvestigationRelationship[],
  relationshipMap: { nodes: { id: string, label: string }[], edges: { id: string, sourceId: string, targetId: string, state: string }[] } | null,
  systemEvidence: InvestigationChannel[],
  persistence: { state: ChannelState, summary: string, supportTrend: string, windowDescription: string | null },
  operatingContext: { state: ChannelState, baselineMode: string, currentMode: string, comparability: string, reasons: string[] },
  dataQuality: { state: ChannelState, summary: string, limitations: string[], signalHealth: { signal: string, status: string }[] },
  timeline: { label: string, detail: string }[],
  sourceSignals: { display: string, sourceId: string }[],
  lineageSummary: { source: string, baselineWindow: string, currentWindow: string, evidenceRefs: string[] },
  primaryAction: { label: "Open evidence record", route: `/evidence/${encodedFindingKey}` }
}

InvestigationRelationship = {
  id: string,
  source: { display: string, sourceId: string },
  target: { display: string, sourceId: string },
  metricChannel: string,
  baseline: number | null,
  current: number | null,
  signedChange: number | null,
  magnitude: number | null,
  direction: string,
  baselineSamples: number | null,
  currentSamples: number | null,
  windows: { baselineStart: string | null, baselineEnd: string | null, currentStart: string | null, currentEnd: string | null }[],
  persistence: string | null,
  support: string | null
}

InvestigationChannel = {
  key: "multivariate" | "temporal" | "lag" | "mutual_information" | "behavioral_evolution" | "expected_behavior" | "propagation" | "physics",
  label: string,
  state: ChannelState,
  scope: EvidenceScope,
  scopeLabel: string,
  sourcePath: string,
  summary: string,
  metrics: { label: string, value: string | number }[]
}
```

Only include numeric values that are finite in the source. A channel unavailable from the source returns `state: "unavailable"` with a neutral reason; it does not receive zero/normal defaults. Every available Investigation channel renders its `scopeLabel` adjacent to the heading; a system/run source cannot use a finding-specific heading or prose. Investigation channels source, in order, from finding-scoped normalized evidence and these existing result paths when present:

- multivariate: `model.result.sii_result.covariance_analysis`, then its compatibility equivalent;
- temporal/lag/MI: `model.result.sii_result.temporal_analysis`, `model.result.temporal_math`, `model.result.sii_intelligence.temporal_math`, or `model.result.engine_result.temporal_math`; MI is `mutual_information_drift`, lag is `lagged_relationships`;
- behavioral evolution/expected behavior/propagation/physics: corresponding `model.result.sii_result.*` sections or the existing `model.siiEvidence.phase_4` summaries;
- persistence/context/quality: finding normalized fields first, then SII evidence summary sections.

Scope resolution for every Investigation and Evidence channel is exact:

- content embedded on the exact finding is `finding` scope;
- an owned relationship selected by the explicit relationship-ID rules is `relationship` scope;
- a result/SII container with an explicit `system_id` exactly equal to the finding's explicit system ID is `system` scope;
- `model.siiEvidence` and `model.result.sii_result.*`/compatibility paths are `run` scope unless their own payload carries an exact finding or owned-relationship reference; the selected finding's system label, shared signals, or route selection cannot narrow that scope;
- malformed or contradictory scope identifiers make the channel unavailable rather than broader or narrower by inference.

The current normalizer obtains `model.siiEvidence` from analysis/result-level `sii_evidence` and assigns that same object to each finding (`frontend/src/viewModels/engineeringReasoning.js:333-335`, `:592`, `:735-767`). Therefore those channels default to `run`, not `finding`. Each rendered run/system channel uses a prominent label such as `Analysis-run evidence — not finding-specific` or `System-scoped evidence — supports context, not finding ownership`. This label is required in both Investigation summaries and Evidence payload sections, not just in a tooltip or technical disclosure.

Investigation deliberately labels the metric channel; it never labels all system evidence as correlation. It omits raw engine payloads, full evidence package, complete provenance, audit/workflow history, result hashes, version/build metadata, replay JSON, full SII record, and exact package internals.

`InvestigationInsufficient` retains exact identity/header, source-backed limitation/context/data-quality summaries, and channel states, but no numeric relationship is invented. Unknown or malformed identity is `unavailable`, not insufficient.

## EvidenceRecordProjection contract

```js
EvidenceRecordProjection = EvidenceReady | EvidenceInsufficient | EvidenceUnavailable

EvidenceReady = {
  contractVersion: "results-presentation.v1",
  depth: "evidence",
  variant: "ready",
  identity: {
    findingKey: string,
    findingId: string,
    workflowFindingId: string | null,
    conditionId: string | null,
    runId: string | null,
    uploadId: string | null,
    datasetId: string | null,
    baselineId: string | null,
    systemId: string | null,
    assetId: string | null
  },
  header: { systemContext: string, title: string, reviewState: string | null },
  timestamps: { generatedAt: string | null, firstDetectedAt: string | null, sourceRanges: object[] },
  signals: { display: string, rawId: string | null, canonicalId: string | null }[],
  exactRelationships: object[],
  channels: EvidenceChannel[],
  classifications: { classification: object | null, confidenceContract: object | null, alternatives: string[] },
  sufficiency: { status: string, reasons: string[] },
  limitations: { material: string[], technical: string[], contradictions: string[] },
  lineage: { sourceRows: object[], evidenceWindows: object[], evidenceRefs: string[], traceability: object | null, findingProvenance: object | null },
  engine: { name: string | null, version: string | null, schemaVersion: string | null, buildCommit: string | null, configurationHash: string | null, inputHash: string | null, resultHash: string | null },
  package: PackageAssociation,
  audit: { caseState: string | null, caseHistory: object[], outcome: object | null, review: object | null, trace: object[] },
  actions: { exportRunId: string | null, exportScopeLabel: "Analysis-run export — not finding-specific" | null, traceRoute: "/trace" | null }
}

EvidenceChannel = {
  key: string,
  label: string,
  state: ChannelState,
  scope: EvidenceScope,
  scopeLabel: string,
  sourcePath: string,
  payload: object | object[] | null
}
```

Evidence `payload` is a recursively copied JSON-safe object from one named allowlisted channel, not `model.result`. Strip functions and prototype-bearing objects; preserve zero, false, empty arrays, exact numeric precision, identifiers, and UTC strings. Do not normalize absence to success. Every available channel renders `scopeLabel` and `sourcePath` before its payload. `EvidenceInsufficient` has the same record structure where an exact finding exists, sets `variant: "insufficient"`, retains every available technical channel with its real scope, and records insufficiency reasons. Thus insufficient evidence remains auditable without claiming that run evidence is finding provenance.

Build one channel row for every currently available source below and an unavailable row for the core channels (relationships, multivariate, temporal, lag, MI, persistence, operating context, data quality, lineage) when absent:

- normalized complete finding-owned relationships (`relationship` scope) and `model.siiEvidence.relationship_changes` (`run` by default) as separately labeled sources;
- `model.result.sii_result.relationship_analysis`, `relationship_graph`, `covariance_analysis`, `temporal_analysis`, `multiscale_analysis`, `persistence_analysis`, `operating_modes`, `uncertainty`, `data_conditions`, `evidence_fusion`, `behavioral_model`, `expected_behavior`, `behavioral_evolution`, `behavioral_snapshots`, `event_memory`, `spectral_analysis`, `dynamical_stability`, `network_stability`, `bayesian_evidence`, `propagation_analysis`, `physics_reasoning`/`physics_evidence`;
- temporal subchannels `mutual_information_drift` and `lagged_relationships` from the selected temporal source;
- `model.siiEvidence` sections: relationship changes, operating context, persistence, uncertainty, data quality, sensor health, configured-prior observations, Phase 4, and provenance, each explicitly `run`/`system` unless a direct finding or relationship reference proves narrower scope;
- result `traceability`, `processing_trace`, ingestion/data quality, and exact identity/timestamp fields when present, with result-level sources labeled `run`;
- result `evidence_package` only through `resolvePackageAssociation`; never also copy it into a generic channel or finding lineage.

If two paths contain a channel, retain both with distinct `sourcePath` values; do not silently merge different engines or make Pearson the primary truth. Do not fabricate canonical signal IDs: use a source-provided canonical ID/mapping only; otherwise `canonicalId: null`.

Rendering rules for the `package` block:

- `finding`: heading `Package explicitly linked to this finding`; package ID and immutable details may be presented as finding provenance, while the independently resolved `relationshipLink` still controls whether its primary relationship can support this finding's relationship section.
- `run`: heading `Related package for this analysis run`; show the required `not finding provenance` label and `sourcePath` immediately above the ID/details. Do not place the ID beside Finding ID, do not call it “this finding's package,” and do not use it to load related-package correlation as though the selected finding owns it.
- `related`: heading `Related evidence package`; show the explicit reference source and `not finding provenance` label. It cannot populate finding identity, lineage, or owned relationships.
- `unavailable`: render one restrained unavailable row; render no package ID, immutable panel, related-package request, or empty technical grid.

`lineage.findingProvenance` contains only source rows/references explicitly associated to the exact finding or its owned relationships. Package provenance from a `run` or `related` association stays inside the labeled package block. Likewise, `actions.exportRunId` is visibly analysis-run scoped and is not described as exporting an immutable finding package.

## Route ownership and source parity

In `EngineeringReasoningWorkspace`:

```js
const detailRoute = ["finding", "investigation", "evidence"].includes(route);
const requestedId = pathIdentity(["findings", "investigations", "evidence"]);
const exactFinding = requestedId
  ? model.findings.find((item) => item.id === requestedId) ?? null
  : null;
```

- A detail path without a non-empty ID resolves to its overview, never a selected finding.
- A non-empty unknown ID renders the matching depth's unavailable projection.
- `openFinding`, `openInvestigation`, and `openEvidence` accept a projected `findingKey`, not a full finding.
- Insufficient global Results may expose Evidence only if the projector has an exact scoped finding key. Otherwise no action.
- `/analyses/:run` must continue to pass `analysisBelongsToBaseline`; mismatch renders unavailable and never the latest current result.
- A live result object and a restored historical record containing the same source payload must deep-equal after projection except optional `sourceMode`, which is not rendered.
- Compacted history with missing channels produces unavailable channel states and never consults current live data.
- Resolving an exact finding never changes package/channel scope. Route ownership proves which finding was requested; it does not prove that an analysis package or SII object belongs to that finding.
- When multiple findings share a run, project each from the same immutable source independently. A direct package/relationship reference on finding A must not appear as finding-owned identity, lineage, relationship evidence, related-package loading input, or export identity on finding B.

## Component migration sequence

1. Add projectors and contract tests. Do not change markup until key allowlists, variants, exact identity, package/relationship association, scope labeling, and channel extraction pass.
2. Remove unrelated relationship fallback in `engineeringReasoning.js`, retain only explicit source association references, and prove a finding without an owned relationship or exact package link receives neither.
3. Memoize Results projection in the workspace; convert Operations Brief, `/findings`, `/systems/:name`, and `/investigations` overview to compact cards. Remove `TechnicalSummary` from first-level system results.
4. Convert Finding Review and add `EvidenceAssessment`. Keep any workflow mutation in `/work`; Review retains only the compact state label.
5. Convert Investigation. Render comparisons/charts from projected relationships and compact system-evidence channels with visible scope labels. Remove the full SII record and audit disclosures.
6. Convert Evidence Record. Render complete scope-labeled channels, finding provenance, classification/sufficiency/limitations, explicitly scoped package associations, and audit actions. Gate related-package loading on `package.scope === "finding"`; a run/related package may be displayed only as labeled context and is not a finding-owned query key.
7. Change comparison upload completion copy/counts and then update responsive styles and E2E.

At each step, no component at a shallower depth may import a deeper projector or receive `model`, `result`, `finding`, `rawCase`, or evidence DTO props.

## Visual and responsive constraints

At 390px viewport width:

- Results content width `<= viewport width`; assert `document.documentElement.scrollWidth <= innerWidth`.
- Target compact card height: **<= 300px** for a two-line title/behavior and optional limitation; hard regression ceiling **340px**. This replaces the current 650px allowance.
- Card has one primary action; no nested `<details>`, evidence list, classification panel, or action menu.
- Vertical card gap 12px; padding 14–16px; title max two/three wrapped lines; behavior max three wrapped lines.
- Primary button minimum 44px touch height but `width:auto`; do not create a full-card oversized button unless text wrapping requires it.
- Two card headers must appear within a 780px vertical scan from the first card top.
- Evidence assessment is one flat block: one column at <=720px, two columns at tablet/desktop, no nested panels; long values use `overflow-wrap:anywhere`.
- Investigation/Evidence grids become one column at <=720px; tables/lists wrap or use deliberate contained scrolling only at the audit depth. Raw IDs use `overflow-wrap:anywhere`, never widen the document.

Tablet (768x1024): Results still uses compact cards and does not add categories; assessment may use two columns. Desktop (1440x900): width is used for baseline/current comparisons, relationship map, and readable audit grids, not extra Results/Review evidence.

Measure and record for each route/viewport: `scrollWidth`, `clientWidth`, first result card height, page `scrollHeight`, primary action bounding box, and clipped elements (`right > innerWidth` or `left < 0`).

## Test design and canaries

Create one rich two-finding fixture with unmistakable, non-overlapping values:

- raw IDs `RAW_SIGNAL_RESULTS_CANARY_A`, `CANONICAL_SIGNAL_CANARY_A`;
- metric `pearson_correlation`, baseline `0.918273`, current `0.314159`, samples `997/443`;
- timestamp `2026-08-25T05:23:56.206210+00:00`;
- finding A: ID `FINDING_RESULTS_CANARY_A`, owned relationship ID `RELATIONSHIP_RESULTS_CANARY_A`, lineage `LINEAGE_RESULTS_CANARY_A`, raw/canonical signals ending `_A`, and explicit `evidence_package_id: PACKAGE_RESULTS_CANARY_A`;
- finding B: ID `FINDING_RESULTS_CANARY_B`, owned relationship ID `RELATIONSHIP_RESULTS_CANARY_B`, lineage `LINEAGE_RESULTS_CANARY_B`, raw/canonical signals ending `_B`, and no package link;
- analysis package `PACKAGE_RESULTS_CANARY_A` with `analysis_id` matching the fixture run and `primary_relationship.source_model_edge_id: RELATIONSHIP_RESULTS_CANARY_A`; engine `ENGINE_RESULTS_CANARY`;
- long guidance `GUIDANCE_RESULTS_CANARY` and detailed corroboration `CORROBORATION_RESULTS_CANARY`;
- MI and lag canaries plus multivariate, persistence, context, classification, sufficiency, and audit values.

Projection tests:

1. Assert exact recursive key allowlists for each variant.
2. JSON-stringified Results excludes every technical canary; Review excludes raw IDs/metrics/timestamps/lineage/engine/package and caps reasons/checks.
3. Review renders all seven independent assessment labels; high change confidence coexists with `Cause / attribution: Not established`.
4. Investigation contains finding-owned exact comparison, samples, windows, source IDs, MI/lag/multivariate summaries, context, persistence, quality, and lineage summary; excludes package/engine/audit canaries; every run/system SII channel exposes its exact scope label and source path.
5. Evidence for finding A contains all exact A canaries and all available source channels, including false/zero values. Its package has `scope: "finding"`, exact package source path, and a matched relationship link. Every SII channel has one of the allowed scopes and renders `scopeLabel`/`sourcePath`.
6. Missing arrays/objects, `NaN`, invalid dates, prototype-bearing values, and malformed channels do not throw and produce unavailable states.
7. Two-finding package/relationship isolation canary: project A then B from the same run. A owns only relationship A and may own package A through its exact direct link. B owns only relationship B; it must not contain relationship A, A lineage, package A in `identity`/`lineage`, or a finding-scoped package. If package A's analysis identity matches the run, B may contain it only once as `package.scope: "run"` with the exact `Related package for this analysis run — not finding provenance` label and `sourcePath: "model.result.evidence_package"`; its `relationshipLink` is `different` or `unavailable`, it cannot populate B's relationship channel, and it cannot trigger related-package loading. Removing the package's run identity makes B's package `unavailable`, not finding/related.
8. Unknown IDs are unavailable for Review, Investigation, and Evidence; no unknown value or other finding text appears.
9. Explicit insufficient classification remains insufficient at every applicable depth and keeps complete available audit data in Evidence.
10. Stable Results has no cards/technical panels. Same live/historical source yields the same projection, including association scopes. Historical missing fields stay unavailable and never borrow a package/channel from live state.
11. Adversarial association variants do not narrow scope: package title/system/signal/value equality, single-package/single-relationship arrays, array reordering, and route selection cannot associate package A or relationship A to finding B. An explicit mismatched package ID produces `unavailable` plus a limitation and does not leak the loaded package ID.
12. DOM tests assert package ID A is shown under finding A's explicit package heading; under finding B it is either absent or appears only under the prominent related-run heading/label. Package A never appears in B's identity/lineage, and a mocked related-package API is not called from B. DOM tests also assert every rendered run/system SII block includes its scope label.

DOM tests repeat the canary assertions because a clean projection can still be miswired. Replace the existing summary test that requires “Requested next action,” context, and “Evidence and limitations.”

## E2E routes, viewports, and measurements

Use locked Playwright dependencies; in a fresh environment first run `cd frontend && npm run setup:codex`.

For each viewport `390x844`, `768x1024`, and `1440x900`:

1. Open `/analyses/forensic-job` (historical route fixture) and `/sites/current` (live parity fixture).
2. Assert calm `Analysis complete`, `1 finding deserves review`, and `1 system represented`; assert no technical canaries.
3. Measure first card height (`<=340px`, target <=300px), scan distance to second card header when the two-card fixture is used, and no overflow/clipping.
4. Open `/findings/:id`; assert the seven assessment dimensions and no deep canaries.
5. Open `/investigations/:id`; assert baseline/current, source signals, samples/windows, relevant multi-channel evidence, visible run/system scope labels, and no package/engine/audit canaries.
6. Open both fixture Evidence routes. Assert exact per-finding metrics/IDs/lineage and all available scope-labeled channels. Finding A shows package A as explicitly linked; finding B never shows package A as its identity/provenance and, if shown, uses only the prominent analysis-run-related/not-finding-provenance block. Assert the related-package request is not issued for finding B.
7. Capture full-page screenshots under `.planning/screenshots/results-progressive-disclosure/{phone,tablet,desktop}/`.
8. Run stable and insufficient fixtures; assert no empty technical panels and insufficient tone does not use urgent/escalation styling.
9. Direct-open unknown `/findings/workspace-b-secret`, `/investigations/workspace-b-secret`, and `/evidence/workspace-b-secret`; each says unavailable and shows neither another finding nor the secret ID.

## Implementation slices and end conditions

### Slice 0 — baseline

- Record current focused unit/E2E status before edits.
- End: no application change; baseline failures documented rather than masked.

### Slice 1 — runtime contracts

- Add projector and tests; remove unrelated relationship fallback.
- End: exact key/canary/malformed/identity/parity tests pass; the two-finding relationship/package canary proves no cross-finding attribution; all run/system channels carry rendered scope/source labels; `git diff --check` passes; existing model tests pass.

### Slice 2 — Results and completion states

- Convert summary/list cards and comparison terminal screen.
- End: Results DOM contains only allowed fields; stable/insufficient states are calm; 390px card <=340px and no overflow; focused frontend tests pass.

### Slice 3 — Review

- Add flat evidence assessment; remove full classification/workflow panels.
- End: seven dimensions remain distinct, reasons 1–3, checks <=3, cause not inferred, and no deep canaries.

### Slice 4 — Investigation and Evidence

- Convert both depths; complete all currently available Evidence channels.
- End: Investigation materially deepens evidence without audit internals; Evidence retains exact finding provenance and scope-labeled related run/system evidence; package IDs/details enter finding identity/provenance only through an exact explicit link; missing evidence is unavailable and never borrowed.

### Slice 5 — responsive QA and full validation

- Update E2E, capture screenshots, and record measurements.
- End: phone/tablet/desktop full hierarchy passes without clipping/overflow; card budget passes; stable/insufficient/unknown paths pass.

### Slice 6 — package

- Review `git diff`, confirm no excluded backend/telemetry files, and write the review package.
- End: formatting/lint/build/tests/E2E/backend contracts/Citadel validation/diff-check pass, or exact pre-existing failures are documented; branch is uncommitted and independently mergeable.

## Validation commands

```bash
cd frontend && npm run lint:ci
cd frontend && npm run build
cd frontend && npm test -- --run
cd frontend && npm run test:e2e -- --project=chromium
python -m pytest tests/test_analysis_result_contract.py tests/test_finding_confidence_contract.py tests/test_evidence_package.py
git diff --check
```

There is no separate frontend typecheck script; Vite build is the production import/compile check. Do not use ad hoc `npm exec` installs. No backend code change is planned; the listed backend tests are compatibility checks only.

## Compatibility and future telemetry integration

This branch continues to consume the current analysis result shape. The concurrent telemetry implementation may later add generic source/canonical identity fields or compact list endpoints. Integrate them only at `buildEngineeringReasoningModel`/`resultsPresentation.js`: preserve the projector contracts, select new fields into an allowed depth, and add a canary test. Do not add connectors, registries, normalization, ingestion, migrations, secrets, or security code here. Unknown future result fields are excluded from Results/Review/Investigation by construction and may appear in Evidence only after an explicitly allowlisted source path is added.

## Risks and mitigations

- **Historical compaction omits audit channels:** same projector reports channel unavailable; it never consults current state.
- **Projection accidentally changes intelligence meaning:** values are copied/labeled, not recomputed; no new scores, thresholds, diagnosis, or causal claims.
- **Evidence completeness regresses as channels evolve:** explicit channel registry plus all-source-path tests fail when a supported channel is not projected.
- **Analysis package is misattributed across findings:** exact package/run/relationship association rules, a non-finding `run` presentation, and the two-finding canary prevent array order or route selection from becoming provenance.
- **Run/system SII evidence reads as finding-specific:** required `scope`, `scopeLabel`, and `sourcePath` fields are asserted in projection and DOM tests; malformed/contradictory scopes fail unavailable.
- **Workflow actions disappear from Review:** analytical Review keeps only compact state; assignment/resolution remains in canonical `/work` workflow.
- **Mobile height regresses with long content:** bounded text/list contracts plus measured 340px ceiling.
- **A future DTO leaks shallowly:** exact recursive key tests and technical canaries make extra fields fail closed.
