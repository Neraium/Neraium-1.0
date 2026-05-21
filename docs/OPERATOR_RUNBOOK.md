# Neraium Operator Runbook (Lean)

Purpose:
- Keep operation decisions simple and consistent.
- Avoid overreaction when telemetry identity confidence is low.

## 1) If system identity is `unknown` (low confidence)

Condition:
- `system_identity.claim_made = false`
- `telemetry_profile = unknown`

Action:
1. Do not treat output as domain-specific (pool/cultivation/HVAC/electrical).
2. Validate source mapping and telemetry labels first.
3. Collect additional telemetry before operational changes.

## 2) If room state is `Insufficient telemetry`

Condition:
- Room `room_state = Insufficient telemetry`

Action:
1. Confirm room/system tags are present and consistent.
2. Confirm timestamp continuity and sample cadence.
3. Re-upload after minimum telemetry window is met.

## 3) If room urgency is `review`

Action:
1. Compare flagged room signals to facility logs for the same window.
2. Perform non-disruptive checks listed in `what_to_check`.
3. Monitor next upload before corrective changes, unless policy requires immediate review.

## 4) If room urgency is `unstable`

Action:
1. Prioritize checks in `what_to_check` for that room.
2. Validate cross-signal behavior (relationship evidence) before intervention.
3. Log intervention and re-check with a follow-up upload window.

## 5) Default alert thresholds (starting point)

Use `/api/observability/summary` and `/api/observability/metrics`.

- `neraium_unknown_profile_rate > 0.15` -> Warning
- `neraium_sparse_upload_rate > 0.20` -> Warning
- `neraium_flagged_room_rate > 0.35` -> Warning

Notes:
- These are operational defaults, not scientific limits.
- Tune thresholds after 1-2 weeks of real usage.
