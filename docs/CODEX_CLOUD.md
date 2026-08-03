# Run Neraium in Codex Cloud (No AWS)

This development path runs the full frontend, API, background upload worker, and
local persistence entirely inside the Codex workspace. It does not require AWS
credentials, an AWS account, Docker, or a network connection to AWS. Production
deployment files and AWS behavior are unchanged.

## Setup and start

From the repository root:

```bash
./scripts/setup-codex.sh
./scripts/run-codex.sh
```

Open port **3010** from the Codex port preview. Keep the start script running in
its terminal. It builds the frontend, exposes it on `0.0.0.0:3010`, and proxies
same-origin `/api` requests to a backend bound privately to `127.0.0.1:8010`.
Stopping the script stops both processes.

The setup script intentionally uses the repository lock files:

- Python packages come from `backend/requirements-dev.txt` in `.venv`.
- Frontend packages use `npm ci` and `frontend/package-lock.json`.

Python 3.11 is selected by default to match the supported runtime. Set
`PYTHON_BIN` to another Python 3.11 executable if it has a different name.

## Local replacements for AWS development dependencies

| Production dependency | Codex development equivalent |
| --- | --- |
| ECS API and worker tasks | One local `monolith` process with the background worker enabled |
| RDS PostgreSQL / Secrets Manager | The application's local SQLite auth store under `.codex-runtime/` |
| S3 shared upload state and queue | Local runtime SQLite and filesystem state under `.codex-runtime/` |
| Amplify/static origin and API routing | Vite preview server with a local `/api` reverse proxy |
| CloudWatch/infrastructure monitoring | Disabled; backend console logs remain available |
| External telemetry poller | Disabled unless a developer explicitly tests a local source |
| SNS/webhook/SMTP notification delivery | Disabled by empty local delivery configuration |

`run-codex.sh` removes AWS credential, S3 bucket, RDS secret, and database URL
variables inherited by the shell and disables EC2 metadata lookup. This prevents
an accidentally configured Codex environment from reaching AWS. Runtime data is
disposable and can be reset with `rm -rf .codex-runtime` while the app is stopped.

## Supported local workflows and limitations

The local stack supports authentication storage, the frontend workspaces,
multipart telemetry upload, queued background processing, results, evidence,
replay, local connectors, and the API health/observability surfaces. Direct API
uploads up to the configured multipart limit use only local storage.

The browser-to-S3 large-upload-session path is intentionally unavailable because
it is an AWS production feature. Use the normal multipart upload path for Codex
development. Split-role/multi-instance durability, RDS behavior, AWS alarms, and
real notification delivery are also outside this local mode; their mocked/unit
tests remain part of repository validation.

## Verification

With the application running, verify both the proxied API and frontend through
the single exposed port:

```bash
curl --fail http://127.0.0.1:3010/api/health
curl --fail http://127.0.0.1:3010/
```

Run the repository validation suite separately:

```bash
./scripts/validate_repo.sh
```

For browser tests in a fresh Codex environment, follow the repository requirement
to run `cd frontend && npm run setup:codex` before `npm run test:e2e`.
