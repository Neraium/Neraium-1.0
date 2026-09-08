# Replay availability and synthetic consequence smoke

Investigated against production commit `ae6b2d7428a36e8ad5f253182fbbb0518d33c45d`.

## Exact 404 root cause

The saved post-deployment probes requested:

- `/api/data/replay/4cca0e6a3edf45da9bee63951d09483e`
- `/api/data/replay/7a95d38ac7fe460c8fb8b04a9eddd2eb`

Both returned `404: Replay was not found.` The corresponding historical intake
results returned 200 and contained this envelope at both `replay_timeline` and
`sii_intelligence.replay_timeline`:

```json
{
  "source": "not_generated",
  "replay_ready": false,
  "frame_count": 0,
  "meta": {"frame_count": 0, "optional": true, "reason": "inline_replay_disabled"},
  "timeline": []
}
```

The service-scope result had the same envelope before deployment. Local source
of the observations: `/tmp/neraium-deploy-ae6b2d74/evidence/after-admin/` and
`after-service/`, with the pre-rollout comparison in `prerollout-service/`.
These captured payloads are not committed because they contain operational data.
The regression uses only the empty envelope above with a synthetic run ID.

Request path:

1. `ReplayWorkspace.jsx` constructs `/api/data/replay/{job_id}`.
2. `main.py` mounts `data.router` at `/api`; `data_replay` is registered.
3. `resolve_upload_artifacts(job_id)` performs the scoped, per-job result lookup,
   including immutable terminal results and scoped historical fallbacks.
4. `build_replay_payload_from_result` reads the persisted replay timeline.
5. `data_replay` returns 404 when there are no frames.

`upload_pipeline._inline_replay_generation_enabled()` defaults to **false outside
pytest**, unless `NERAIUM_INLINE_REPLAY_GENERATION` explicitly enables it. Its
production branch persists `_empty_optional_replay(..., "inline_replay_disabled")`.
Thus these are absent artifacts, not valid artifacts hidden by routing, a key
mismatch, frontend URL construction, or canonical evidence linkage. The default
pytest behavior explains why upload tests with generated replay did not establish
production replay availability.

No lookup or deployment configuration change is justified by these examples.
Missing artifacts continue to return 404. We do not synthesize replacement
historical frames, rerun analysis, rewrite recorded hashes, or enable replay
production-wide. Valid top-level and nested historical artifacts resolve through
both replay URL families, covered by real persistence/API regression tests.

The separate product-boundary defect found during this proof is fixed:
`/api/replay/{job_id}` and the live timeline/frame/range routes now apply the same
existing `product_evidence` projection as `/api/data/replay/{job_id}`. The evidence
response schema also excludes `primary_drivers` during serialization while still
accepting that field when parsing historical records.

## Fixture contract

The opt-in module is `backend/datasets/verification_consequence.py`, in the
existing datasets tree already copied by both production Dockerfiles. No startup
hook, public seed endpoint, connector, control action, or configuration migration
is added.

| Field | Explicit value |
| --- | --- |
| Run | `synthetic-water-consequence-v1` |
| System | `synthetic-test-only-water-system` |
| Scope principal | `service-token` |
| Scope workspace | `synthetic-consequence-verification-only` |
| Source type | `verification_fixture` |
| Flow signal/tag | `synthetic.water.flow-gpm` |
| Predictor signal/tag | `synthetic.test.load` |
| Relationship | `synthetic.water.flow-to-test-load` |
| Finding | `synthetic-water-finding-v1` |
| Evidence | `synthetic-water-evidence-v1` |
| Resource/profile/unit | `water` / `water_gpm` / `gpm` |
| Timestamps | 2026-09-01 00:00 through 06:00 UTC, seven exact hourly samples |
| Expected behavior | `100 + 2 × test load` gpm, load = 0 through 6 |
| Observed behavior | `110 + 2 × test load` gpm |
| Maximum gap | 3,600 seconds; accept one scheduled interval, never bridge a missing sample |
| Gap provenance | `signal_catalog`, `explicit_maximum_interval_gap_v1`, `synthetic-no-connector` |
| Support | `high`, explicitly a fixture assumption |
| Method | `timestamp_aware_trapezoidal_integration`, version `1.0.0` |
| Result | `quantified`, `above_expected`, **+3,600 gal over 21,600 seconds** |

Arithmetic: `10 gal/min × 21,600 s ÷ 60 = 3,600 gal`, six contributing intervals,
zero skipped intervals. There is no unit conversion or floating-point tolerance
in the exact amount assertion.

All five flags (`synthetic`, `verification_only`, `non_customer`,
`non_production_control`, `non_actuating`) are true in the source, replay metadata,
and signal provenance. The finding title and limitations explicitly label the
fixture. Model validation, persistence and support are declared test assumptions;
this certifies consequence handling, not a learned customer model or detection.
No Siemens Building X data, customer telemetry, inferred resource, inferred
cadence, or inferred maximum gap is involved.

The seeder fixes the service principal and workspace; it accepts no customer scope
argument. It writes a per-run upload result, scoped evidence row and finding case.
It does not publish latest-upload state or overwrite the global legacy evidence
JSON mirror. Normal customer sessions cannot read it even when they request the
same workspace label; normal service-token default views also exclude it.

## Explicit smoke commands

From a checkout with the locked backend dependencies installed, inspect the
fixture without seeding:

```bash
PYTHONPATH=backend python -m datasets.verification_consequence > /tmp/synthetic-water.json
```

After this change is separately approved and deployed, seed **on the API runtime**
using its configured upload-state storage and runtime database:

```bash
python -m datasets.verification_consequence --seed
```

Do not seed only on an isolated worker filesystem: Findings/evidence must exist
in the API's configured runtime database. Repeated seeding reads existing records
without rebuilding or rewriting them. Conflicting or incomplete records fail
closed for inspection. A different fixture requires a new version/run ID.
Run one seeder at a time. This command is opt-in and was not run on production
as part of this change.

For HTTP smoke, set `NERAIUM_API_TOKEN` through the existing secret mechanism.
The verifier uses HTTPS, does not follow redirects, and supplies the fixed
`X-Neraium-Workspace-Id`. It makes only GET requests:

```bash
PYTHONPATH=backend python -m datasets.verification_consequence --verify-url https://api.neraium.com > /tmp/synthetic-consequence-proof.json
node scripts/verify-consequence-projection.mjs < /tmp/synthetic-consequence-proof.json
```

The report must show HTTP 200 for replay, replay alias, intake result, evidence
and Finding detail. Both replay routes must return seven persisted frames and
exactly the canonical consequence in `meta.measurable_consequence`, explicitly
scoped to the entire recorded finding window. The verifier compares the full
consequence, including provenance and max-gap policy, across all five responses.
The Node check executes the shipped frontend selector against the HTTP result;
the compact UI projection retains measured facts and IDs, while detailed
provenance remains in the API report. It does not integrate or infer anything.

## Focused verification

`tests/test_verification_consequence.py` exercises the real production-auth HTTP
routes with local persistence and simulated shared S3 persistence. It clears
upload caches; the S3 case also switches to a fresh local upload directory. It
then makes analytical, replay-generation and persistence writers raise on call,
proves repeated reads and reseeding, and compares full artifact/evidence digests
before and after. Historical top-level/nested replay and genuinely missing
artifacts are tested separately. The full API payloads reject cause, driver,
attribution, diagnosis, leak, waste, savings, cost and remediation output keys.

Validation is local TestClient plus Node projection proof, not a deployed smoke
or browser test. Production seeding and HTTP verification remain a later
operational step; the existing historical 404s remain correct absent-artifact
responses. No merge or deployment was performed.

Validation completed for this change: **65 focused tests passed** (19 fixture /
replay-boundary tests, 7 replay API tests, 8 bounded data-replay tests, 9 consequence
certification tests, 12 historical attribution tests, 10 product evidence tests).
The 50,000-row upload test was explicitly deselected. Commands:

```bash
PYTHONPATH=backend APP_ENV=test python -m pytest -q tests/test_verification_consequence.py tests/test_replay_api.py tests/test_historical_attribution_boundary.py tests/test_consequence_certification.py tests/test_data_replay.py -k 'not historian_style_csv_upload'
PYTHONPATH=backend APP_ENV=test python -m pytest -q tests/test_product_evidence_contract.py
python -m ruff check backend/datasets/verification_consequence.py tests/test_verification_consequence.py
python -m ruff check --select E9,F63,F7,F82 backend/app/routers/replay.py backend/app/models/api_models.py
python -m compileall -q backend/datasets/verification_consequence.py backend/app/routers/replay.py backend/app/models/api_models.py tests/test_verification_consequence.py
node --check scripts/verify-consequence-projection.mjs
git diff --check
```

The schema-specific test was added and run separately after the initial 54-test
batch; the commands above reproduce all 65 together. Ruff 0.15.0 ran from an
isolated temporary tool install, without changing repository dependencies.
No full local suites, frontend test suite, browsers, Docker, PostgreSQL or
benchmarks were run. The existing frontend selector was executed twice against
actual local HTTP responses (once per persistence backend), without frontend
code changes.
