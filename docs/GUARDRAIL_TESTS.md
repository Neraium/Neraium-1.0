# Guardrail Tests

These tests confirm production safety behavior without generating unsafe load. Run them against local or staging first. Do not perform uncontrolled load testing against production.

## Oversize Upload Guardrail

Expected response: HTTP 413 with `upload_too_large`.

Create a generated CSV in `.tmp/`. The `.tmp/` and `tmp/` directories are ignored by git.

```bash
mkdir -p .tmp
node -e "const fs=require('fs'); const p='.tmp/oversize-upload.csv'; const s=fs.createWriteStream(p); s.write('timestamp,value\n'); for (let i=0;i<3000000;i++) s.write('2026-05-01T00:00:00Z,75\n'); s.end();"
```

Upload it with Git Bash:

```bash
BASE_URL=${BASE_URL:-http://127.0.0.1:8000}
curl -i -X POST "$BASE_URL/api/data/upload" \
  -F "file=@.tmp/oversize-upload.csv;type=text/csv"
```

Pass criteria:

- Status code is `413`.
- JSON body includes `error_type` equal to `upload_too_large`.
- No partial upload file remains queued for processing.
- Backend log records an oversize rejection without leaking file contents.

Recovery expectation:

- Normal uploads still succeed immediately after the rejected upload.
- `/api/ready` remains healthy unless another dependency is degraded.

## Queue Saturation Guardrail

Expected response: HTTP 503 with `upload_queue_saturated` and a `Retry-After` header.

Safe local method:

- Run the backend locally with a very small queue limit, for example `NERAIUM_MAX_PENDING_UPLOAD_JOBS=1`.
- Hold or simulate one pending job locally.
- Attempt a second upload.

Safe staging method:

- Use a staging environment only.
- Coordinate with the operator responsible for the environment.
- Keep the queue limit intentionally low for the test window.
- Submit only the minimum number of uploads required to confirm the 503 behavior.

Pass criteria:

- Status code is `503`.
- JSON body includes `error_type` equal to `upload_queue_saturated`.
- Response includes `Retry-After`.
- Queue recovers after the pending job completes or the queue is cleared.

What not to do:

- Do not run unbounded concurrent uploads against production.
- Do not use production customer data for guardrail stress tests.
- Do not bypass authentication or network controls to force saturation.
- Do not leave generated oversize files in tracked paths.

## Evidence Integrity Checks

- Rejected uploads must not create completed evidence runs.
- Failed processing runs may create failed evidence records with safe error detail.
- Exported evidence must not include secrets, tokens, or raw credentials.
- Operator UI must show uncertainty when SII output is unavailable.
