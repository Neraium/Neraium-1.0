# Neraium 1.0 RC1 — release preparation reviewed

Date: 2026-09-24. Branch: `fix/deterministic-governed-output`. Pre-release HEAD: `a4ea0a992841d281e19de8119ecd1275a0d7e654`.

Current certified behavior is frozen. Neraium analyzes telemetry/evidence outside the control path; read-only, no equipment write-backs or actuation; evidence rather than diagnosis, human review authoritative.

Accepted stack: #1 snapshot schema/important-column hoisting; #2 operating-context matching without unnecessary presentation descriptors; #3 invocation-local exact timestamp projection reuse (ACCEPT_WITH_LIMITATIONS: targeted gain, end-to-end within noise); #5 immutable normalized telemetry metadata hoisting. #4 runner-vector experiment remains rejected and absent.

Initial decision: RELEASE_BLOCKED_REPRODUCIBILITY, retained verbatim in history/20260924T205356Z-entry/. The blocker is resolved by an explicit, hash-verified historical certification suite; see HISTORICAL_CERTIFICATION.md and REPRODUCIBILITY_AUDIT.json. Ordinary product tests and frozen analytical/security behavior are preserved.

Release boundary and exact proposed staging paths are recorded in FILE_MANIFEST.json and PROPOSED_COMMIT.md. Release readiness is limited to the checks in RELEASE_READINESS.json; no full regression or new certification campaign is claimed. No staging, commit, tag, merge, or push occurred.
