# Repository threat model

Scope: current integration-certified worktree, not a deployed-system penetration test. Baseline in raw/BASELINE.json includes branch, HEAD, 1,101 file hashes and certification references; status/diff and 146 router declarations are retained separately. Environment files are hashed, not copied or printed. No reset/stash/clean.

Data flow: external telemetry or browser → authenticated routers (`routers/data.py`, `routers/telemetry.py`) → bounded contracts/upload validators → normalization (`engine/sii_inputs.py`, `services/historical_ingestion.py`) → SII/governed analysis → evidence/provenance and canonical artifact encoding → scoped runtime/PostgreSQL/object persistence → scoped evidence/replay/result API → React rendering. Legacy global connectors are gated outside development/test. HTTPS connector egress separately validates destinations and pins resolved addresses.

Trust boundaries: untrusted client bytes/headers and filenames; session/service authentication; server-resolved workspace/Phase 4 scope; uploaded source versus normalized data; analysis versus persisted canonical artifact; local filesystem versus database/object store; backend JSON versus browser; container versus host/network; secret references versus resolved credentials. User-supplied IDs do not establish workspace membership. Source-owned IDs and execution IDs have different producer contracts.

Assets: customer telemetry; topology/context; source artifacts; evidence packages and governed results; source/model identity and provenance; authentication secrets/session state; operational logs; runtime databases. Adversaries: unauthenticated Internet client; malicious authenticated tenant/operator; hostile same-site browser origin; compromised upstream; user with local volume access; compromised deployment identity. Availability, confidentiality, tenant isolation and integrity all matter despite no equipment control path.

Read-only/no actuation is an existing architecture boundary, not a confidentiality guarantee. Human review remains authoritative. No security change may touch analysis, thresholds, sampling, identity, canonical bytes, rankings or consequence.
