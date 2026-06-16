# Operator Experience

## Design philosophy

Neraium is an evidence platform.

It presents structural observations, confidence, and supporting evidence.

It does not provide operational recommendations or prescribe actions.

## Language rules

Operator-facing copy must answer four questions quickly:
- What happened?
- Why is this important?
- How confident is the system?
- What evidence supports it?

The first viewport should prioritize status, confidence, observation summary, why it matters, review next, and a route to supporting evidence.

## Allowed terminology

Use these labels in operator UI:
- `Normal`
- `Behavior Change Detected`
- `Critical Change`
- `Low`
- `Moderate`
- `High`
- `Current observation`
- `Current analysis`
- `Current operating pattern`
- `Behavior has persisted for X days`
- `Supporting evidence`
- `Historical comparison evidence`
- `Observation method`

## Disallowed terminology

Do not expose these backend or implementation terms in operator UI:
- `relationship divergence`
- `replay/relationship evidence`
- `relationship evidence`
- `State Group A`
- `Deformation Age`
- `Observation grammar`
- `latest_result`
- `upload_state`

## Canonical finding contract

Every operator surface should render the same canonical finding object.

Required fields:
- `exists`
- `status`
- `confidence`
- `summary`
- `whyItMatters`
- `reviewNext`
- `supportingEvidence`
- `technicalDetails`
- `dataQuality`
- `historicalComparison`
- `evidenceButtonLabel`
- `emptyState`

Empty state values are fixed:
- `No current observations.`
- `Telemetry is being monitored.`
- `No structural changes detected.`

## Screen hierarchy

Gate:
- Show current status, confidence, summary, why it matters, review next, and a direct evidence route.
- Keep technical details secondary.

Findings:
- Mirror the canonical finding used by Gate.
- Show supporting evidence, technical details, and data quality behind collapsed sections.

Review Finding:
- Reuse the canonical finding summary and evidence.
- Add historical evidence detail without changing the primary interpretation.

Evidence:
- Reuse the canonical finding status, confidence, summary, and review-next framing.
- Keep replay controls and deeper traceability below the operator summary.

## Remaining UX improvements

Areas still worth improving without changing backend behavior:
- Reduce decorative vertical space further on small iPhone Safari viewports.
- Add explicit scroll anchoring from `Review Evidence` actions into the replay evidence section.
- Extend sanitization coverage to any future operator-facing exports or changelog summaries.
