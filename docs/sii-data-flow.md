# SII Data Flow

Facility Command now prefers backend SII intelligence fields before local fallback logic.

## Backend driven

- `/api/facility/systems` returns `intelligence` and `intelligence_status`.
- `/api/data/upload` returns `sii_intelligence` derived from parsed telemetry, baseline analysis, engine evidence, operator report, and driver attribution.
- `/api/intelligence/status` reports whether SII is loaded, the current source, mode, active room count, and present evidence fields.

## Frontend flow

- Facility systems, room cards, Neraium Score, time window, primary driver, why flagged, what to check, confidence basis, relationship evidence, and structural explanation are read from `sii_intelligence` or `intelligence` when present.
- Upload-derived SII has priority over sample facility SII.
- Local simulated room rotation is retained only as a fallback when backend SII is unavailable.

## Remaining fallback areas

- Empty states and offline backend states use local fallback copy.
- If an older backend omits a specific SII field, the frontend fills only that missing field with a clearly local fallback helper.
