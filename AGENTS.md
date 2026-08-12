# Repository guidance

## Changes and verification

- Make focused changes and preserve unrelated user work.
- After editing, review `git diff` and run `git diff --check`.
- Run the relevant tests or build checks for the changes.
- Do not commit or push unless explicitly requested.

## Frontend browser tests

- In a fresh Codex environment, run `cd frontend && npm run setup:codex` before browser or end-to-end tests.
- Use the repository locked dependencies; do not use ad hoc `npm exec` fallbacks when dependencies are missing.

## Review guidelines

- Prioritize correctness, security, regressions, and missing verification.
- Keep review findings focused and actionable.
