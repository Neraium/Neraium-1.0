# Production results progressive-disclosure audit

**Campaign:** `results-progressive-disclosure`
**Date:** 2026-08-25
**Scope:** Read-only audit of production result surfaces in the clean results-cleanup worktree
**Confidence:** High for the active Engineering Reasoning workspace; medium for legacy/adjacent surfaces whose routes remain reachable but are not part of the primary navigation

## Executive summary

The intended hierarchy already has canonical routes:

`Results / Operations Summary -> Finding Review -> Investigation -> Evidence Record`

The implementation does not yet have canonical data boundaries. `buildEngineeringReasoningModel` builds one large model containing the raw result, full findings, relationships, SII evidence, gaps, timeline, trace, and search objects, and every depth receives that model or a full finding (`frontend/src/viewModels/engineeringReasoning.js:735-767`, `frontend/src/components/EngineeringReasoningWorkspace.jsx:273-300`). First-level cards hide some fields visually, but they still consume deep evidence, and collapsed sections place investigation content in the summary DOM. Investigation and Evidence Record also substantially overlap because both render the complete SII record and technical metadata.

The safest production change is to normalize the evidence source once, then create explicit, depth-safe projections. Components should accept those projections rather than a full finding/result and should render an explicit unavailable/insufficient variant when evidence is missing. Technical evidence should move deeper, not be discarded. No SII intelligence semantics or backend telemetry infrastructure needs to change.

## Route and state inventory

| User surface/state | Canonical route / entry | Main components | Current source | Audit result |
|---|---|---|---|---|
| Operations Brief / Results | `/sites/current`, `/analyses/:run` | `EngineeringReasoningWorkspace`, `OperationsBrief`, `FindingSummary` | Full engineering model and full findings | Active; summary cards contain review/investigation content and raw gap identifiers |
| Systems list | `/systems` | `SystemsOverview`, `FindingSummary` | Full engineering model/findings | Active; compact list, but uses prohibited “monitored systems” wording |
| System findings | `/systems/:name` | `SystemOverview`, `FindingSummary`, `TechnicalSummary` | Full model/result | Active; exposes technical run/evidence coverage on a first-level route |
| Findings list | `/findings` | `FindingsOverview`, `FindingSummary` | Full findings | Active; same oversized card contract as Operations Brief |
| Finding Review | `/findings/:id` | `FindingReviewWorkspace`, classification/workflow panels | Full finding | Active; decision content exists but is surrounded by a full classification panel and workflow detail |
| Investigations list | `/investigations` | `InvestigationOverview`, `FindingSummary` | Full findings | Active; repeats the Findings list rather than presenting a distinct queue purpose |
| Investigation | `/investigations/:id` | `InvestigationWorkspace`, comparison/evidence/SII/metadata panels | Full finding/model | Active; contains valid engineering evidence plus audit-only internals |
| Evidence Record | `/evidence/:id` | `EvidenceRecordWorkspace`, lineage/SII/technical/audit panels | Full finding/model | Active; densest route, but not yet a demonstrably complete record of every channel |
| Trace | `/trace` | `TraceWorkspace` | Full model trace | Active auxiliary audit route; effectively a fifth evidence depth |
| Work queue | `/work` | `WorkFindingCard`, `OperationalFindingBrief` | Projected work item retaining `rawCase` | Active adjacent workflow surface; cards are appropriately compact but the model still carries the full case |
| Analysis complete | upload completion and `/analyses/:run` | `IntakeFlowPanel`, then Operations Brief | Full upload result/history record | Active; completion screen leads with dataset/evidence counts instead of calm review triage |
| Stable / no material change | Operations Brief and `/findings` | quiet state / empty state | Presentation state | Active and mostly concise |
| Insufficient evidence | Operations Brief fallback | state notice | Presentation state plus selected finding fallback | Active legitimate result, but its Evidence action can use a hidden selected finding |
| Malformed/unknown evidence | deep routes | scoped unavailable state | route/model resolution | Investigation/Evidence mostly safe; Finding Review can silently fall back to another finding |
| Observation Center | `/workspace/insights` | `ObservationCenterWorkspace` | canonical finding plus up to 200 full evidence runs | Reachable adjacent legacy result surface; collapses summary, review, engineering evidence, workflow, charts, and audit into one page |
| Legacy System Body results | dormant topology path | `SystemBodyWorkspace` | full result | Not in the primary app path; must not be reused because it is evidence-heavy and includes heuristic “possible causes”/checks |

Top-level routing is defined by `frontend/src/AuthenticatedApp.jsx:31-50`. Concrete engineering routes and route parsing are in `frontend/src/components/EngineeringReasoningWorkspace.jsx:21-49`; handlers are at `:434-480` and the surface switch is at `:630-677`. Historical routes are produced and identity-checked by `frontend/src/viewModels/baselineSelection.js:69-134`.

## Surface audit and evidence ownership

### 1. Analysis complete and historical/post-analysis results

The comparison upload terminal screen currently says “Comparison Dataset Ready” and displays dataset/time/signals/relationship count, data quality, and a confidence summary before the user opens results (`frontend/src/components/setup/IntakeFlowPanel.jsx:290-355`, `:679-714`). Opening results routes to `/analyses/:analysisRunId` (`frontend/src/AuthenticatedApp.jsx:370-390`) and then renders the same Operations Brief after a strict baseline/analysis identity check.

Historical records preserve full results/snapshots even after compaction (`frontend/src/viewModels/analysisHistory.js:30-77`, `:253-326`), and reopening restores that full record (`frontend/src/hooks/useWorkspaceSessionController.js:405-421`). This is appropriate for persistence but not an appropriate presentation contract.

**Move to the Results projection:** terminal status, number of findings deserving review, number of represented systems, compact projected cards, and a calm stable/insufficient variant. Keep dataset dimensions and relationship/evidence counts in Investigation or Evidence Record. The historical route should project the selected immutable historical source exactly as the live route does; it should not create a separate evidence hierarchy.

### 2. Operations Brief / first-level Results

`OperationsBrief` derives counts and ranking from the full model/result (`frontend/src/components/engineering/OperationsBrief.jsx:12-26`, `:42-59`) and renders sectioned full finding objects through `FindingSummary` (`:103-118`). The compact visual shell is sound, but the card currently owns too much:

- requested next action, “Why attention,” workflow summary, confidence, operating context, up to three supporting evidence records, and limitations (`frontend/src/components/engineering/FindingSummary.jsx:35-79`);
- a secondary-actions menu in addition to the primary review action (`:75`);
- priority inferred from escalation/ranking when not explicitly projected (`:41-42`);
- collapsed evidence remains in the summary DOM, so CSS concealment is acting as the depth boundary.

Operations Brief adds a second escalation banner that repeats the primary title/evidence and hard-codes a “Strong mode match” assertion (`frontend/src/components/engineering/OperationsBrief.jsx:94-101`). Monitoring issues expose `issue.signals?.[0]`, a raw source identifier, on the first result screen (`:111-114`). This is the clearest direct evidence leak.

**Retain here only:** system/asset context, concise title, one system-behavior sentence, priority, change confidence, an optional one-line material limitation, compact assignment/review state where useful, and one primary action. Retain summary counts/status. Remove the duplicate escalation banner or re-express only non-duplicative projected triage content. Do not render raw signal IDs, evidence lists, context panels, exact evidence values, or long next-step guidance.

### 3. Findings lists, system findings, and investigation list

Site, system, findings, and investigations overviews all reuse `FindingSummary` with full findings (`frontend/src/components/EngineeringReasoningWorkspace.jsx:143-195`). This duplicates both presentation and oversized consumption.

The system detail additionally renders `TechnicalSummary`, which exposes evidence coverage, relationship record count, run ID, and processing notes on `/systems/:name` (`frontend/src/components/EngineeringReasoningWorkspace.jsx:100-117`, `:147-165`). A system with no finding can still show the technical panel. These fields belong in Investigation/Evidence, not the system result summary.

The Systems list says “monitored systems” (`frontend/src/components/EngineeringReasoningWorkspace.jsx:169-174`). Use “modeled systems” or “systems represented”; Neraium is not an individual-sensor monitoring product.

**Ownership:** all first-level lists should consume the same compact `ResultFindingCardProjection`. System detail may include system identity and compact findings, but technical coverage/run metadata moves deeper. `/investigations` may remain an operational queue, but it should not imply a different evidence depth merely by repeating the same result cards.

### 4. Finding Review: decision layer

The route already contains the requested core sections: What changed, Why attention, Important limitations, What to check first, and Open investigation (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:316-341`). Guidance is already capped at three (`:319`, `:333`).

Depth problems:

- `FindingClassificationSummary` renders a large 7–9 fact classification panel containing confidence, cause, evidence quality, context, persistence, operational state, trend, corroboration, and priority (`frontend/src/components/operational/FindingClassificationSummary.jsx:109-156`). The dimensions are valuable, but the full panel repeats header/status/priority and violates the restrained assessment requirement.
- Review renders only one “why” string rather than 1–3 short evidence-backed points (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:323`, `:331`).
- Important limitations render even when non-material (`:332`).
- Review also contains full review controls, a large workflow panel, and collapsed full classification reasoning (`:336-338`). These create workflow/audit density on the decision layer.

**Retain here:** one system-level What changed explanation; 1–3 short reasons; one restrained Evidence assessment that keeps change confidence, evidence quality, cause/attribution, persistence, operating context, corroboration, and evidence sufficiency independent; one material limitation only when needed; at most three non-diagnostic checks; one Open Investigation action. Do not include raw metrics, charts, identifiers, lineage, engine metadata, full classification reasoning, or audit/workflow internals.

### 5. Investigation: engineering evidence

Investigation contains the correct engineering evidence primitives: primary Baseline -> Current comparison, complete relationship list, condition evolution/persistence/comparability, exact-window timeline, operating context, supporting relationships, data quality, source signals, lineage summary, and a relationship graph (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:343-368`). Relationship rows include magnitude, sample counts, evidence window, and source signals (`:155-181`). The comparison component handles missing numeric values with “unavailable” (`:119-135`).

Depth problems:

- The full `SiiEvidenceRecord` is rendered here and again in Evidence Record. It includes engine/source, exact metrics, operating context, persistence, data quality/sensor health, phase 3/4/propagation, and provenance (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:65-102`, `:369`). Investigation needs system/multivariate evidence, not the complete audit record.
- Audit/workflow/replay disclosures expose exact run ID, outcome JSON, generated time, trace, full classification, technical assumptions/identities, and conflicts/unconfirmed IDs (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:370-377`). Most belong only in Evidence Record.
- `TechnicalAnalysisMetadata` exposes raw values and technical identities (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:284-309`).
- Primary relationship selection falls back from the finding to `model.relationships[0]` (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:346`). Evidence Record repeats the fallback at `:384`. When a finding has no relationship, this can display unrelated global evidence and violates safe failure.

**Retain here:** finding-scoped primary/supporting relationship changes, baseline/current values and direction, relevant metric-channel label, multivariate/system evidence where present, temporal/lag/MI evidence where present, persistence, windows, context/mode detail, comparability, sample counts, source signals, data quality, and lineage summary. Use an Investigation-safe SII projection. Never substitute a relationship from another finding; display an explicit unavailable block.

### 6. Evidence Record: complete audit layer

Evidence Record currently includes comparison, supporting evidence, lineage, windows/generated times, related evidence packages, export/trace, full SII record, technical identities/values, and audit history (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:382-405`). This is the correct home for complete provenance and internal metadata.

Completeness gaps in the rendered record:

- it shows a primary comparison rather than demonstrably complete relationship evidence;
- temporal/lag and mutual-information evidence are not explicit unless buried in SII/exports;
- evidence sufficiency, technical limitations, and classifications are not presented as a complete audit set;
- raw/canonical identifiers are partial and dispersed;
- Review prose and Investigation comparison/support content are repeated rather than organized as one immutable record.

**Reserve here:** all raw and canonical identifiers, exact UTC timestamps, exact metrics for every available evidence channel, complete relationship/multivariate/temporal/lag/MI/persistence/operating-mode evidence, sample counts, full lineage, classifications, evidence sufficiency, engine/version metadata, immutable package details, technical limitations, and audit history. Absence should be recorded as absent/unavailable, never synthesized.

`/trace` currently exposes derived source/version trace data (`frontend/src/components/EngineeringReasoningWorkspace.jsx:198-209`, `frontend/src/viewModels/engineeringReasoning.js:711-722`). Treat it as an auxiliary Evidence Record action, not another user-facing content depth.

## Stable, insufficient, and failure states

Presentation state normalization distinguishes processing, no dataset, legacy, dataset ready, insufficient evidence, no meaningful changes, and analysis complete (`frontend/src/viewModels/operationsBrief.js:224-235`).

- **Stable/no material change:** Operations Brief and Findings are concise (`frontend/src/components/engineering/OperationsBrief.jsx:77-86`, `frontend/src/components/EngineeringReasoningWorkspace.jsx:184`). Preserve “No supported material behavioral change” plus one explanation. Do not render empty technical panels.
- **Insufficient evidence:** The current state is correctly calm and non-urgent, with a concise need-for-more-evidence explanation (`frontend/src/components/EngineeringReasoningWorkspace.jsx:622-628`, `:665-677`). However, “Review Evidence” can open the Evidence route for `model.selectedFinding` even when the global state withholds that finding (`:622-625`). The projection should carry an optional, explicitly scoped audit target or omit the action.
- **Malformed evidence:** array/number normalizers and finding presentation defaults prevent common crashes. `normalizeFindingPresentation` returns structured fallback values and an insufficient-evidence classification (`frontend/src/viewModels/operatorFinding.js:522-603`). The UI must distinguish “source says insufficient” from “payload malformed/unavailable.”
- **Unknown deep links:** Investigation and Evidence use a scoped unavailable state (`frontend/src/components/EngineeringReasoningWorkspace.jsx:87-97`, `:288-296`, `:664`). Finding Review is omitted from `routeRequiresExactFinding`, so `/findings/unknown` can fall back to `model.selectedFinding` and show the wrong case (`:288-296`). All three detail routes must require exact finding identity.

## Field/consumer and repetition matrix

| Field/category | Current early consumer | Repeated deeper | Required owner |
|---|---|---|---|
| Title, system, priority/status | all `FindingSummary` lists (`frontend/src/components/engineering/FindingSummary.jsx:35-79`) | every case header (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:216-223`) | Results; concise context may repeat in headers |
| Why attention / supporting evidence | `frontend/src/components/engineering/FindingSummary.jsx:61-72` | Review, Investigation, Evidence | Review owns reasons; Investigation owns detailed supporting relationships; Evidence owns complete set |
| Operating context | collapsed summary card (`frontend/src/components/engineering/FindingSummary.jsx:65-72`) | classification, Investigation, SII Record | Review owns restrained assessment; Investigation owns detail; Evidence owns exact record |
| Limitation | summary details and Review always | classification/technical disclosures | one compact material limitation on Results; decision-impacting limitation on Review; complete limitations on Evidence |
| Long next action/guidance | summary (`frontend/src/components/engineering/FindingSummary.jsx:61`) | Review and Investigation disclosures | Review only, max three non-diagnostic checks |
| Raw gap/source IDs | Operations Brief issue (`frontend/src/components/engineering/OperationsBrief.jsx:111-114`) | Investigation/Evidence | Investigation source signals; Evidence complete raw/canonical IDs |
| Exact relationship values / sample counts/windows | system technical summary and card evidence indirectly | Investigation and Evidence | Investigation comparison; Evidence exact complete record |
| Full SII evidence | Investigation (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:369`) | Evidence (`:399`) | Investigation-safe multivariate summary; complete record only in Evidence |
| Lineage | Investigation (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:366`; `frontend/src/components/engineering/EvidenceLineage.jsx:30-58`) | Evidence (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:397`) | summary in Investigation; complete lineage in Evidence |
| Classification | full panel in Review | Investigation disclosure | restrained independent assessment in Review; complete classification in Evidence |
| Workflow/audit | Review workflow (`frontend/src/components/engineering/FindingCaseWorkspaces.jsx:336-338`) | Investigation disclosures and Evidence audit | compact review state on Results/Review; operational workflow in `/work`; audit history in Evidence |
| Run/package/engine metadata | system TechnicalSummary and Investigation | Evidence/Trace | Evidence only |

The largest repetition clusters are: the same full `FindingSummary` across four lists; header/title/status across all detail routes; supporting evidence across Summary/Review/Investigation/Evidence; comparison across Investigation/Evidence; full SII record across Investigation/Evidence; workflow/classification across Review/Investigation; and lineage across Investigation/Evidence.

## Oversized data consumers

### Frontend

- `buildEngineeringReasoningModel` returns raw `result`, SII evidence, full findings, systems, relationships, nodes, gaps, timeline, trace, and search objects (`frontend/src/viewModels/engineeringReasoning.js:735-767`).
- Each `buildFinding` contains summary prose plus raw supporting evidence, contradictions/limitations, recommendations, comparison, all relationships, display/raw variables, technical identities, engineering prior, evidence objects, outcome/history/classification, confidence dimensions, trajectory/corroboration/context/sensor health, alternatives/persistence/guidance/timeline/ranges/timestamps, and SII evidence (`frontend/src/viewModels/engineeringReasoning.js:469-595`).
- Each normalized relationship carries raw/display IDs, metric, baseline/current/deltas, samples, references/objects, persistence, and windows (`frontend/src/viewModels/engineeringReasoning.js:312-330`).
- `EngineeringReasoningWorkspace` passes the same model/findings into all depths (`frontend/src/components/EngineeringReasoningWorkspace.jsx:273-300`, `:630-677`).
- Work queue normalization creates a compact view but retains `workflow` and `rawCase` (`frontend/src/viewModels/workQueue.js:123-195`).
- Observation Center fetches/stores large evidence-run records and mixes them with the active finding (`frontend/src/components/ObservationCenterWorkspace.jsx:369-446`).

### API boundaries that amplify over-consumption

- Finding list responses include full `FindingCaseResponse.evidence: dict[str, Any]` (`backend/app/models/api_models.py:467-481`); workflow materialization preserves hashes/provenance/full finding (`backend/app/services/finding_workflow.py:133-150`, `:538-648`).
- `fetchFindings` returns both the full case and workflow (`frontend/src/services/api/findingsApi.js:165-207`).
- `EvidenceRunResponse` is a dense audit contract (`backend/app/models/api_models.py:266-345`), and `/api/evidence/runs` returns full records for list use (`backend/app/routers/evidence.py:21-34`). Engineering workspace fetches 100 (`frontend/src/components/EngineeringReasoningWorkspace.jsx:321-331`); Observation Center fetches 50 and retains up to 200 (`frontend/src/components/ObservationCenterWorkspace.jsx:369-446`).
- Latest upload returns a broadly typed full latest result (`backend/app/models/api_models.py:237-263`, `backend/app/routers/data.py:1820-1877`).

This UX branch should introduce frontend projections without altering backend or telemetry semantics. A future integration point can add compact finding/evidence-run list endpoints after the concurrent backend work lands.

## Recommended explicit presentation contracts

Normalize the engine/evidence source once, then project it through a new view-model boundary (for example `frontend/src/viewModels/resultsPresentation.js`). Do not pass `model.result` or a full finding into summary/review components.

### `ResultsProjection`

- discriminated state: `analysis_complete | stable | insufficient | processing | unavailable`;
- counts: findings deserving review, systems represented;
- cards: opaque finding route key, system/asset context, concise title, one behavioral sentence, explicit priority, change confidence, optional compact material limitation, compact review/assignment state, primary action;
- no raw IDs, exact metrics, samples, windows/timestamps, context detail, evidence lists, lineage, engine/package metadata, detailed guidance, or full classification.

### `FindingReviewProjection`

- exact finding identity and concise header;
- `whatChanged` and 1–3 `whyAttention` points;
- independent assessment values for change confidence, evidence quality, cause/attribution, persistence, operating context, corroboration, and evidence sufficiency;
- optional material limitation;
- up to three non-diagnostic checks and Open Investigation action;
- no relationships DTO, chart data, raw metrics/IDs, lineage, engine metadata, or full workflow/audit object.

### `InvestigationProjection`

- exact finding identity;
- finding-scoped primary/supporting relationship changes with baseline/current, magnitude/direction, metric-channel label, samples, windows, and source signals;
- multivariate/system, temporal/lag, mutual-information, persistence, and operating-mode evidence only when source evidence provides it;
- comparability, data quality, and lineage summary;
- explicit unavailable reason for missing/malformed channels; never fall back to unrelated global evidence;
- no full evidence package, raw audit history, engine/version internals, replay/outcome JSON, or complete provenance.

### `EvidenceRecordProjection`

- immutable evidence/finding/package identities;
- complete raw/canonical identifiers, exact UTC timestamps, exact channel metrics, complete relationships, multivariate/temporal/lag/MI/persistence/mode evidence, samples, full source lineage, classifications, sufficiency, engine/version, package internals, technical limitations, and audit metadata;
- retain unknown/absent fields explicitly without fabrication.

All projectors should return discriminated safe variants (`ready`, `insufficient`, `unavailable`) and use exact route identity. Runtime contract tests are warranted because this frontend is JavaScript rather than statically typed. Projection tests should use canary deep fields to prove they cannot cross shallower boundaries.

## Mobile and desktop audit

At `<=720px`, the engineering layout stacks grids, reduces padding, and maintains 44px touch targets (`frontend/src/styles/engineering-reasoning.css:1510-1605`). There is no obvious structural horizontal-overflow defect in the primary hierarchy. The problem is vertical density: every collapsed/stacked summary-card block remains part of the card contract, so multiple findings are not genuinely scannable.

Current mobile E2E allows a first card height below 650px at 390px and screenshots Summary, Review, and Investigation (`frontend/tests/e2e/engineering-reasoning.spec.js:203-237`). That threshold is too permissive for multiple-card scanning. The same flow does not validate Evidence Record at phone width or the entire hierarchy at tablet width. Desktop width is restrained by existing max-width layout, but desktop currently uses available space to display more classification/evidence categories on Review rather than improve comparison readability.

Required responsive assertions:

- at approximately 390px, at least two compact result-card headers are scannable in a normal viewport/short scroll; use a materially lower card-height budget after design implementation;
- no horizontal overflow at Results, Review, Investigation, and Evidence;
- no raw technical IDs on Results; assessment values wrap/stack without nested-panel sprawl;
- buttons remain comfortable touch targets without full-width oversized treatment unless layout requires it;
- tablet and desktop traverse the complete hierarchy, including Evidence Record;
- measure total scroll burden and clipping, not screenshots alone.

## Existing coverage and regression gaps

Useful current coverage:

- stable state (`frontend/src/components/EngineeringReasoningWorkspace.test.js:440-446`);
- insufficient analysis-complete layout (`frontend/tests/e2e/analysis-complete-layout.spec.js:1-36`);
- malformed collection resilience (`frontend/tests/e2e/frontend-resilience.spec.js:13-35`);
- deep unknown Investigation/Evidence safety (`frontend/src/components/EngineeringReasoningWorkspace.test.js:133-140`);
- Investigation values/samples/source IDs and Evidence exact values/IDs (`frontend/src/components/engineering/FindingCaseWorkspaces.test.js:95-111`, `frontend/src/components/EngineeringReasoningWorkspace.test.js:368-398`);
- responsive summary flow and accessibility at desktop/390px (`frontend/tests/e2e/engineering-reasoning.spec.js:180-237`, `:282-298`);
- desktop/phone overflow and raw-marker absence on Operations Brief (`frontend/tests/e2e/command-center-analysis-record.spec.js:24-37`).

Tests that currently encode the wrong depth should be replaced: `frontend/src/components/engineering/FindingSummary.test.js:37-57` requires next action, context, three evidence items, and limitation; `frontend/tests/e2e/engineering-reasoning.spec.js:144-170` opens the summary card’s Evidence disclosure.

Add regression tests proving:

1. Results projection/DOM excludes raw signal IDs, exact relationship metrics, sample counts, exact UTC timestamps, complete lineage, engine/package metadata, detailed corroboration, long guidance, and full classification.
2. Review contains the seven independent assessment dimensions, 1–3 reasons, optional material limitation, and <=3 checks, while excluding raw IDs/metrics/charts/lineage/engine metadata.
3. Investigation contains finding-scoped comparisons, samples/windows/source signals, context/comparability/persistence/data quality, relevant multichannel evidence, and summary lineage, while excluding complete package/audit internals.
4. Evidence Record retains complete provenance, exact identifiers/times/metrics, classifications, sufficiency, limitations, engine/version, and all available evidence channels.
5. Missing/malformed payloads produce safe unavailable variants and never borrow another finding’s evidence; unknown Finding Review routes are scoped unavailable.
6. Stable and insufficient states render no empty technical panels and insufficient evidence is not styled as urgent equipment failure.
7. Two or more findings remain scannable at 390px; full hierarchy has no overflow at phone/tablet/desktop.

## Adjacent surfaces and compatibility boundaries

- `WorkFindingCard` is a good compact operational precedent (`frontend/src/components/work/WorkFindingCard.jsx:4-24`). `OperationalFindingBrief` should remain workflow-focused and link to canonical Investigation/Evidence instead of copying analytical depth (`frontend/src/components/work/OperationalFindingBrief.jsx:125-165`).
- Observation Center (`frontend/src/components/ObservationCenterWorkspace.jsx:849-1124`) currently combines history cards, possible explanations, relationships, checks, analysis detail, quality, event history, interventions, charts, notification stats, variable labels, and evidence sources. If retained, route its review/evidence actions into canonical projected surfaces; do not make it a parallel evidence hierarchy.
- Legacy `SystemBodyWorkspace` exposes full Health/Insights/Evidence/Actions/Data Quality/Analysis Details and heuristic contributors/checks (`frontend/src/components/workspaces/SystemBody/SystemBodyWorkspace.jsx:137-144`, `:325-579`, `:645-699`). It is not the production design target and should not be reused.
- Baseline detail and Historical Ingestion Review are data-trust/baseline lifecycle surfaces, not finding results. Their sample/signal details are appropriate in that separate context (`frontend/src/components/BaselineDetailView.jsx:137-203`).
- Do not implement connectors, secrets, repositories, registries, normalization, ingestion workers, migrations, or telemetry security here. New backend fields should later enter through the source normalizer and be selectively projected, never spread directly into components.

## Recommended implementation order

1. Add pure projection functions and contract tests, including malformed/unknown variants.
2. Convert Operations Brief, findings/system lists, and historical completion to `ResultsProjection`; remove duplicate/technical early panels.
3. Convert Finding Review to its decision projection and exact-route identity.
4. Split Investigation-safe evidence from the full Evidence Record; remove unrelated relationship fallback.
5. Complete Evidence Record rendering for all evidence channels already present in the source DTO.
6. Align Observation Center/work actions with canonical routes without redesigning their backend semantics.
7. Replace tests that require early evidence; add phone/tablet/desktop depth and overflow gates.

## Audit conclusion

No technical evidence needs deletion. The production issue is ownership: the same large result/finding objects cross every route, and components decide depth ad hoc. Explicit source-to-depth projections will make “simple first, deep on demand” enforceable, keep change confidence distinct from evidence quality/persistence/context/corroboration/cause/sufficiency, preserve complete audit lineage, and prevent future backend fields from leaking onto first-level screens.
