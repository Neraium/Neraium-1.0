# Implemented controls

Six confirmed boundary findings addressed; five existing production files edited and one HTTP middleware module added. No analytical/service evidence encoders or comparator edits.

- **S01:** core/http_boundary.py counts actual ASGI request bytes before forwarding excess to parsers; rejects malformed/duplicate/oversized Content-Length without receiving a body. General budget 1 MiB; telemetry uses configured budget; the two direct multipart paths use existing configured file cap plus 1 MiB aggregate form overhead. Existing endpoint file-only cap remains. Unknown/misdeclared-length streams cannot bypass counting. Excess input is not drained; no unbounded body buffering is introduced. Framework closes partial multipart files, verified by test. This is not a global concurrency/disk quota.
- **S02:** core/security.py treats staging as strict authentication/role environment; auth.py always marks staging session cookies Secure. Development/test compatibility is unchanged.
- **S03:** Origin/Referer checked before cookie-authenticated unsafe requests. Accept exact API origin, explicit CORS origins or full regex matches; reject opaque/suffix-spoofed origins. Production/staging cookie writes without either provenance header fail closed. Login rejects hostile Origin and cross-site Fetch Metadata. Header-only service clients without cookies can omit browser headers. Operators using scripted cookie writes must supply a trusted Origin/Referer; header credentials are preferable for machine clients.
- **S04:** security.py/data.py use request.client supplied by trusted ASGI proxy normalization, never raw X-Forwarded-For for audit/fallback bucket identity. Deployment must configure trusted proxy peers and restrict direct access.
- **S05:** shared header helper adds existing nosniff/frame/referrer/CSP/HSTS policy to boundary/header rejections and generic 500s; API and legacy result aliases now emit Cache-Control: no-store. Payloads and canonical bytes are untouched. CORS preflight responses contain no private result body and remain middleware-owned.
- **S06:** production direct auth PostgreSQL URLs require sslmode=require/verify-ca/verify-full; managed-secret validation already required TLS. Certificate/hostname validation remains deployment responsibility: require alone is not verify-full.

Existing workspace authorization fixture now sends a browser Origin for cookie writes; its assertions are unchanged. No dependency, engine, frontend, Dockerfile or deployment workflow modification.

Review evidence: raw/campaign-diff-review.txt, raw/changed-files.json and frozen baseline. Initial failed boundary tests are retained; middleware ordering was corrected before final security/analytical testing and before the gate.
