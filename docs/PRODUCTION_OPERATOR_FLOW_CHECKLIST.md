# Production Operator Flow Checklist

Use this checklist before commercial water-system pilot walkthroughs and operator acceptance sessions. Production outputs must come from backend SII analysis. If output is unavailable, the UI should show "Awaiting SII analysis" instead of a fabricated state.

## Mobile Checklist

- First screen shows current infrastructure health without horizontal scroll.
- Urgency, suspected location, operational runway, evidence quality, and latest update are readable within 3 to 5 seconds.
- Upload, Test Connection, Poll Once, Start Polling, Evidence Trail, Historical Replay, and Export Evidence controls are touch-friendly.
- Sample mode is explicitly labeled when enabled and never appears as live production SII output.
- Error messages are readable, actionable, and do not expose stack traces or secrets.
- Capture screenshots for System Health, Data Connections, Evidence Trail, Historical Replay, and Export Evidence.

## Tablet Checklist

- Layout uses balanced panels and does not stretch a phone layout across the full width.
- System Health remains above raw chart detail.
- Workflow controls remain visible and grouped in the intended order.
- Evidence Trail cards, replay controls, and export actions do not overflow.
- Capture portrait and landscape screenshots for the full operator flow.

## Desktop Checklist

- Command surface feels calm, premium, and operator-focused.
- Evidence and operational meaning are prioritized over raw telemetry density.
- Backend health, readiness, and intake state are visible without debug clutter.
- Keyboard focus states are visible for primary operator controls.
- Capture screenshots for operator review and deployment records.

## Required Operator Flow

1. Upload commercial water-system CSV.
2. Configure API connection credentials and URL.
3. Test Connection.
4. Poll Once.
5. Start Polling.
6. Open Evidence Trail.
7. Open Historical Replay.
8. Export Evidence.

## Upload Flow

- Accepts valid CSV telemetry and returns a queued upload state.
- Empty files return a structured error.
- Oversize files return HTTP 413 with `upload_too_large`.
- Upload progress reaches terminal `COMPLETE` or `FAILED` state.
- Completed upload writes SII state and evidence trail metadata.

## API Config Flow

- URL validation catches missing or malformed endpoints.
- Secrets are masked in UI and logs.
- No secret is stored in localStorage.
- Connection errors explain whether the issue is auth, network, timeout, or invalid response.

## Test Connection

- Shows loading state while request is active.
- Times out safely.
- Shows success state only when backend confirms the connection.
- Shows actionable failure copy without stack traces.

## Poll Once

- Runs through backend ingestion and SII processing.
- Does not fabricate dashboard values when SII output is unavailable.
- Evidence and latest state update only after backend result is received.

## Start Polling

- Prevents duplicate polling starts.
- Shows active polling state and stop control.
- Recovers cleanly from backend unavailability.
- Logs polling start, stop, success, and failure with request correlation where available.

## Evidence Trail

- Shows what changed, when it changed, and which evidence supports the conclusion.
- Failed runs remain audit-visible with safe error detail.
- Latest run and historical runs are distinguishable.

## Historical Replay

- Replay controls are visible and usable on mobile, tablet, and desktop.
- Empty state explains that SII history is not available yet.
- Replay does not invent events when evidence is missing.

## Export Evidence

- Export includes run ID, timestamps, source metadata, and evidence summary.
- Export does not include credentials, tokens, or raw secrets.
- Export errors are structured and operator-readable.

## Screenshot Requirements

- Mobile: System Health first screen, Data Connections, Evidence Trail, Replay, Export.
- Tablet: portrait and landscape System Health, workflow controls, Evidence Trail.
- Desktop: command surface, Data Connections, Evidence Trail, smoke endpoint output.
- Include sample mode screenshots only if clearly labeled as sample mode.

## Pass Criteria

- Required workflow completes without browser console errors.
- `/api/health` and `/api/ready` pass smoke checks.
- 413 guardrail is confirmed for oversize uploads.
- 503 guardrail is confirmed or documented as safely untestable in production.
- No production view silently falls back to sample data.
- All operational conclusions are evidence-linked or show uncertainty.

## Fail Criteria

- Production UI shows fabricated state instead of "Awaiting SII analysis".
- Any secret appears in UI, logs, metrics, or exported evidence.
- Mobile layout overflows or hides primary operator controls.
- Upload, polling, Evidence Trail, Replay, or Export flow is blocked.
- Backend returns HTML error pages for production API endpoints.

## Logging Guidance

- Preserve request IDs and correlation IDs in backend logs.
- Log upload acceptance, upload rejection, SII processing success, SII processing failure, polling events, replay access, and export events.
- Keep logs structured and concise.
- Never log credentials, bearer tokens, full connection secrets, or raw private payloads unless explicitly approved for a local debugging session.
