# Review package: Results progressive disclosure

Date: 2026-08-25
Branch: `agent/results-progressive-disclosure`
Status: implementation complete; local verification exceptions documented

## Delivered behavior

- Results/Operations Summary shows the operational finding first: what changed, why attention is warranted, change confidence, the material limitation, workflow context, and one Review action.
- Finding Review keeps seven evidence dimensions independent and presents up to three evidence-linked investigation checks without diagnosis or causal claims.
- Investigation exposes finding-owned comparisons, persistence, operating context, data quality, timelines, source signals, and explicitly labeled run-scoped evidence channels.
- Evidence Record retains exact identities, timestamps, relationships, supporting statements/items, technical channels, classifications, sufficiency, limitations, lineage, engine/build metadata, package association, audit history, export, and trace access.
- Stable, insufficient, malformed, unknown, and unauthorized states remain calm and fail closed.
- Deep finding workspaces are loaded on demand, keeping the initial Engineering route within its established performance budget.

## Evidence discipline

- Components consume depth-specific allowlisted projections rather than the full model/result DTO.
- Exact route identity is required at every detail depth.
- Finding relationships cannot borrow an unrelated global relationship.
- Evidence packages are labeled finding-, related-, run-, or unavailable-scoped from explicit source identity.
- Finding-owned `supporting_evidence` and structured `evidence_items` are preserved at Evidence depth.
- No automatic diagnosis, root-cause claim, causal claim, exact failure timing, control recommendation, or action automation was added.

## Primary implementation files

- `frontend/src/viewModels/resultsPresentation.js`
- `frontend/src/viewModels/engineeringReasoning.js`
- `frontend/src/components/EngineeringReasoningWorkspace.jsx`
- `frontend/src/components/engineering/OperationsBrief.jsx`
- `frontend/src/components/engineering/FindingSummary.jsx`
- `frontend/src/components/engineering/FindingCaseWorkspaces.jsx`
- `frontend/src/components/setup/IntakeFlowPanel.jsx`
- `frontend/src/styles/engineering-reasoning.css`

## Verification summary

| Check | Result |
|---|---|
| Frontend unit suite | 490 passed |
| Focused final projection/workspace units | 39 passed |
| Lint | passed |
| Production build | passed |
| Engineering performance budget | passed: 570,634 / 588,800 raw; 146,718 / 158,720 gzip |
| Backend evidence contracts | 16 passed |
| Results progressive-disclosure Chromium | 5 passed |
| Full Chromium | 63 passed, 1 unrelated baseline-ingestion timeout |
| Responsive screenshots | 12 captured and reviewed |
| Diff whitespace check | passed |

The aggregate performance command remains nonzero because Live Monitoring exceeds raw budget and Data Sources exceeds raw/gzip budgets. These are outside the Results cleanup; Engineering itself is below budget.

## Review focus

1. Confirm that the concise card and Review language works for operations, facilities, reliability, energy/sustainability, asset management, and engineering audiences.
2. Confirm that run-scoped evidence labels are sufficiently explicit and package attribution never implies finding ownership without a direct source link.
3. Confirm Evidence Record density is acceptable as the deliberately complete final depth.
4. Review the unrelated baseline-ingestion timeout separately before treating the repository-wide Chromium command as green.

No commit, push, merge, deployment, or modification of another worktree was performed.
