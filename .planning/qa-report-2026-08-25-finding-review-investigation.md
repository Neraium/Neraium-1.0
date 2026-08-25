# QA Report: Finding Review and Investigation

> Date: 2026-08-25
> Flows tested: 4
> Passed: 4
> Failed: 0
> Browser: Chromium
> Viewports: 1440 × 900, 390 × 844, and 320 × 664

## Results

### Flow 1: Operations Brief to evidence trace

- Steps: Opened the current Operations Brief, expanded evidence and limitations, opened Finding Review, Investigation, Evidence Record, and Trace mode.
- Expected: The brief remains compact, Review contains decision guidance, and Investigation exposes materially deeper evidence and lineage.
- Actual: Navigation and progressive disclosure worked at every step. Baseline/current/change values, source identifiers, evidence records, local timestamps, and canonical SII evidence rendered from the fixture data.
- Result: PASS
- Screenshots: `.planning/screenshots/operations-review-investigation/finding-desktop.png`, `review-desktop.png`, `investigation-desktop.png`

### Flow 2: Mobile scanning and responsive layout

- Steps: Opened the same workflow at 390 × 844 and the long-name variant at 320 × 664.
- Expected: The finding card fits within a mobile viewport, retains a comfortable primary touch target, safely wraps long identifiers, and has no horizontal overflow.
- Actual: Card height remained below 650 px, all tested content stayed within its card, long names reflowed, and document overflow was no more than one pixel.
- Result: PASS
- Screenshots: `.planning/screenshots/operations-review-investigation/finding-mobile-390.png`, `review-mobile-390.png`, `investigation-mobile-390.png`

### Flow 3: Timestamp and accessibility behavior

- Steps: Rendered facility context in `America/Los_Angeles`, checked generated/timeline evidence, and ran axe against the brief, Review, and Investigation at desktop and mobile widths.
- Expected: Human-facing timestamps use facility-local time while raw values remain in technical metadata; no serious or critical accessibility violations.
- Actual: `2026-07-26T10:00:00Z` rendered as `Jul 26, 2026 · 3:00 AM PDT`, with the exact source timestamp retained in metadata/tooltips. Axe reported no serious or critical violations.
- Result: PASS

### Flow 4: Shared workflow entry points

- Steps: Opened Investigation and Evidence Record from the shared maintenance workflow and facility-authorized finding flow.
- Expected: Existing historical/workspace navigation remains supported and reaches the new evidence hierarchy.
- Actual: Both paths reached Investigation, exposed relationship evidence, and continued to the technical evidence record without enabling unsupported workflow behavior.
- Result: PASS

## Visual Verification

| Route | Result | Notes |
| --- | --- | --- |
| `/sites/current` | PASS | Compact dark finding card; primary Investigate action; progressive evidence disclosure. |
| `/findings/flow-response` | PASS | Classification explanation and four decision sections render cleanly. |
| `/investigations/flow-response` | PASS | Baseline/current/change, timeline, context, source signals, and lineage are visibly deeper than Review. |
| `/evidence/flow-response` | PASS | Existing evidence record and authoritative SII disclosure remain reachable. |

The Playwright-managed local frontend and backend servers were stopped after each run. The repository does not include `scripts/codex-app-artifacts.js`, so screenshots could not be added to a Codex artifact manifest; the durable files above remain available directly.
