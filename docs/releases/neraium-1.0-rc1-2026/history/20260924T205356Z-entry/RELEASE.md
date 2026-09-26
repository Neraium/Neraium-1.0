# Neraium 1.0 RC1 — release preparation blocked

Date: 2026-09-24. Branch: `fix/deterministic-governed-output`. Pre-release HEAD: `a4ea0a992841d281e19de8119ecd1275a0d7e654`.

Current certified behavior is frozen. Neraium analyzes telemetry/evidence outside the control path; read-only, no equipment write-backs or actuation; evidence rather than diagnosis, human review authoritative.

Accepted stack: #1 snapshot schema/important-column hoisting; #2 operating-context matching without unnecessary presentation descriptors; #3 invocation-local exact timestamp projection reuse (ACCEPT_WITH_LIMITATIONS: targeted gain, end-to-end within noise); #5 immutable normalized telemetry metadata hoisting. #4 runner-vector experiment remains rejected and absent.

RELEASE_BLOCKED_REPRODUCIBILITY: `tests/test_complete_upload_semantics.py::test_retained_146_leaf_inventory_is_exhaustive` requires three absent files. It is an ordinary unmarked test and CI runs `python -m pytest tests`. A proposed commit containing this certification test without its required evidence cannot reproduce the test contract. No fixture reconstruction, test edits or production fixes were attempted. Complete secret audit, release boundary, packaging checks and commit preparation remain pending.

This folder records a stopped release preparation, not a release approval. No stage/commit/tag/merge/push and no certification/scale workload occurred.
