# Production Operator Flow Checklist

Use this checklist before pilot walkthroughs and operator acceptance sessions. Neraium is read-only: it learns normal operating behavior from representative historical data and presents evidence for engineer review. It does not autonomously control equipment, guarantee predictions, or replace engineers.

## Responsive workspace

- Operations Brief, Systems, Findings, Investigations, and Data use their current navigation labels.
- Primary actions, stage status, and error recovery remain readable without horizontal overflow on supported mobile, tablet, and desktop widths.
- Keyboard focus is visible and every interactive control has an accessible name.
- Long site, system, signal, and file names wrap or truncate without hiding the action or expanding the viewport.
- Sample or demonstration data is explicitly labeled and never presented as production evidence.

## Required baseline flow

1. Open `Data` or select `Import Historical Dataset`.
2. Confirm the `Establish Initial Baseline` heading.
3. Choose representative historical CSV data.
4. Select `Continue`.
5. Observe Upload Data, Validate Signals, Learn Relationships, Establish Baseline, and Begin Learning.
6. Open the established baseline or return to Operations Brief.

## Upload and processing semantics

- A completed file transfer remains complete if a later import stage fails.
- Only the stage that actually failed is labeled `Failed`.
- Later stages that did not run are labeled `Not started`.
- `Retry Import` retries processing of the stored file without another object upload.
- `Choose Another File` starts a new upload.
- Status polling reaches a terminal complete or failed state and survives refresh.
- Empty and oversized files return structured, actionable errors.
- Server-unavailable messages distinguish a temporary service problem from a file or transfer problem.
- Processing details disclose useful status without exposing stack traces, secrets, or raw private payloads.

## Learning claims

- Copy states that Neraium learns normal operating behavior from representative historical data.
- Temporary abnormalities do not redefine normal without persistent, verified operating history.
- Findings remain evidence-linked and state limitations when evidence is insufficient.
- The UI does not claim autonomous control, guaranteed prediction, a root-cause diagnosis, or replacement of engineers.

## Connector flow

- Connection configuration validates the endpoint and keeps secrets out of browser storage and logs.
- Test Connection reports loading, confirmed success, timeout, authentication, network, and invalid-response states accurately.
- Poll Once uses backend ingestion and does not fabricate findings when analysis output is unavailable.
- Start Polling prevents duplicate starts, exposes a stop control, and recovers from backend unavailability.

## Screenshot requirements

- Mobile: Operations Brief, Data, baseline import, processing, success, and processing failure.
- Tablet: portrait and landscape Operations Brief and baseline import.
- Desktop: Operations Brief, Findings or Investigations, Data, and smoke endpoint output.
- Include sample-mode screenshots only when the sample state is visibly labeled.

## Pass criteria

- The required workflow completes without browser console errors.
- `/api/health` and `/api/ready` pass smoke checks.
- Upload-session creation, object transfer, completion, status polling, retry, and refresh hydration meet their API contracts.
- The 413 guardrail is confirmed for oversized uploads.
- A 503 path is confirmed in staging/local or explicitly documented when unsafe to induce in production.
- No production view silently falls back to sample data.
- All operational conclusions are evidence-linked or state their uncertainty.

## Fail criteria

- A completed transfer is described as an upload failure.
- More than the actual failed stage is labeled `Failed`.
- Retry Import uploads the file again or Choose Another File reuses the prior upload.
- Production UI fabricates evidence or strengthens an unsupported claim.
- Any secret appears in UI, logs, metrics, or an exported artifact.
- Mobile layout overflows or hides a primary action.

## Logging guidance

- Preserve request IDs and correlation IDs in backend logs.
- Log upload-session creation, transfer completion, processing success/failure, retry, polling, and guardrail rejection.
- Keep logs structured and concise.
- Never log credentials, bearer tokens, full connection secrets, or raw private payloads unless explicitly approved for local debugging.
