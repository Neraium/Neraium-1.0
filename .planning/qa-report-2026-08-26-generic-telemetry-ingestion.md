# QA Report: Production Data Connections

> Date: 2026-08-26
> Environment: local production build with controlled synthetic API responses
> Browser: Chromium
> Flows tested: 2
> Passed: 2
> Failed: 0
> Screenshots: `.planning/screenshots/generic-telemetry-ingestion/`

## Results

### Desktop: production telemetry onboarding

- Steps: opened Data Connections; verified historical upload was absent; created a read-only HTTPS connection; submitted a write-only bearer credential; validated reachability/authentication; discovered telemetry; selected a facility-defined system and equipment asset; explicitly mapped the signal concept/unit/timezone/cadence; enabled continued analysis; reviewed multidimensional connection health.
- Expected: the system-first flow completes without database intervention, the credential disappears after submission, unmapped signals remain excluded from analysis, and health is not reduced to a one-time authentication result.
- Actual: all assertions passed. The enabled connection reported separate credentials, endpoint, telemetry, mapping, freshness, and data-quality facets.
- Accessibility: axe found 0 violations within the production Data Connections workspace.
- Result: PASS
- Screenshot: `.planning/screenshots/generic-telemetry-ingestion/data-connections-desktop.png`

### 390px: responsive production telemetry onboarding

- Steps: repeated the same create → credential → validate → discover → map → enable → health flow at a 390 × 844 viewport.
- Expected: the complete flow remains usable with progressive disclosure, no document-level horizontal overflow, and no historical-upload-first surface.
- Actual: all interaction assertions passed; document width stayed within `window.innerWidth`; the setup, connection registry, and health facets reflowed to one column.
- Accessibility: axe found 0 violations within the production Data Connections workspace.
- Result: PASS
- Screenshot: `.planning/screenshots/generic-telemetry-ingestion/data-connections-390.png`

## Visual verification

| Route | Viewport | Result | Notes |
|---|---:|---|---|
| `/workspace/data-sources` | 1280px | PASS | Full-page capture shows setup progress, scoped registry, health, mapping, reference preparation, runs, and sanitized errors without overlap or blank panels. |
| `/workspace/data-sources` | 390px | PASS | Viewport capture shows legible single-column controls and connection/health state; full interaction flow and overflow assertion also passed. |

## Notes

- The flow uses controlled synthetic non-production telemetry data and route interception; it does not touch production, AWS, IAM, DNS, or a production database.
- The repository does not contain `scripts/codex-app-artifacts.js`, so screenshot manifest registration was unavailable. The screenshots and this report are present at the paths above.
- The repository-locked setup reported one existing high-severity npm audit item; no dependency mutation or audit fix was attempted as part of this UI phase.
