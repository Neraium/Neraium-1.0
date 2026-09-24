# Final S08 focused tests

**27 security cases passed**: 26 S08 cases plus one retained CSV export preservation check. **15 retained analytical cases passed**. Exact IDs: `raw/s08-final/passing-cases.json`.

S08 uses real scoped persistence for historical failure records and adversarial strings containing `/home/ubuntu/...`, database URLs/passwords, internal IPs, Authorization/Bearer tokens, Python class names, SQL fragments and multiline traceback text. Tests cover list/detail/latest/integrity, JSON/CSV/Markdown/PDF exports/packages, interpretation input, mutation responses, embedded latest evidence, raw capture preservation, unchanged stored payload bytes, safe categories/timestamps/references, admin forensic access/audit/no-store, anonymous/viewer/operator/cross-scope rejection, forged development roles and successful API/export preservation.

Raw evidence: `security-tests.xml` initially had 23 passes and one test decoding error (PDF binary header incorrectly decoded as UTF-8). The fixture now uses lossless Latin-1 byte inspection; no production change was needed. The PDF case and two additional HTTP checks passed in `analytical-and-followup.xml` alongside 14 analytical checks (17 passes). `retained-final.xml` adds behavioral source identity and retained CSV protection (2 passes). Initial failure evidence retained; totals deduplicated. No existing tests weakened.

Exactly one final S08 10K gate invocation passed (`complete-10k-tests.xml`). The earlier closeout gate remains separate historical evidence; it was not overwritten or rerun. No full suite, new browser campaign, 500K/1M/LBNL or scale benchmark.


---

## Earlier closeout record (retained historical evidence)

# Focused verification

57 unique backend security cases passed, 17 frontend auth/health API unit cases passed, and 14 retained analytical cases passed. Exact backend case IDs: raw/passing-cases.json. XML/log evidence retained, including the initial failing fixture. No browser/E2E test, full suite, scale workload or dependency install was needed.

Backend evidence: security-tests.xml (35 passed); security-followup.xml (11 passed, one fixture expected connector 400 but production correctly returned retired 410); analytical-and-followup.xml (14 analytical plus corrected fixture passed); boundary-final.xml (12 passed); presentation-final.xml (3 passed). Unique count deduplicates reruns. The correction asserts production 410 before isolating the retained local compatibility handler; it does not weaken the retirement control. Frontend: locked local npm test -- --run src/services/api/authApi.test.js src/services/api/healthApi.test.js (17 passed).

Coverage: cookie login/me/logout and flags; non-authenticating management handles; revoke one/all, pagination, invalid credentials and viewer denial; all four spreadsheet prefixes/control characters and unchanged raw record; initial/upload/connector failures, status/SSE/latest errors, unknown error shapes, safe logging and success preservation; minimal public health including 503, authorized verbose/admin details, unauthorized diagnostics, retained Origin/stream-cleanup controls.

One unchanged test_complete_10000_upload_repeat passed (raw/complete-10k-tests.xml). Freeze: raw/GATE_PREDECLARATION.json. Results do not establish sanitization of raw failed evidence exports: the source trace identifies this residual gap without altering evidence bytes.
