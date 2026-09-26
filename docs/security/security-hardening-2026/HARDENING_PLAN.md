# Ranked plan before implementation

1. S01: enforce actual received byte budget before parsers receive excess bytes; high unauthenticated availability impact; low analytical risk. Keep existing JSON/telemetry/file caps and bounded multipart overhead; no content rewriting.
2. S02: close staging authentication bypass; direct customer-data exposure; shared-environment access policy only.
3. S03: reject untrusted Origin/Referer for cookie writes; protect login from hostile Origin; browser boundary only, no new auth platform. Non-cookie service clients remain supported.
4. S06: require TLS selection for direct production auth DB; configuration-only change.
5. S04: stop trusting raw forwarding headers for audit/fallback rate identity; rely on explicitly trusted reverse proxy ASGI normalization.
6. S05: consistent boundary security headers and no-store for private API responses; no JSON/result changes.

No analytical source, comparator, optimization, source identity, canonical encoding, frontend interpretation or evidence hashing changes. No dependencies added. Deferred S07/S08 need a separate scoped API/storage design; S09–S12 need deployment/supply-chain/privacy follow-up. No changes to evidence bytes as a workaround.

Tests: focused new abuse tests plus selected existing auth/scope/path/egress tests (tens); minimal determinism/provenance/replay/consequence/retirement selection; then exactly one existing complete 10K node. Compare its saved result directly to certified TARGET semantics, in addition to existing SOURCE bridge checks. Freeze comparison paths/hashes before gate. No 500K/1M/LBNL/full suite.

Design reference: [OWASP CSRF prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) documents Origin/Referer validation and why SameSite alone is not a universal protection. Implementation follows actual cookie/CORS configuration, not a new analytical contract.
