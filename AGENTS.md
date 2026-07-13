# Codex rules for this repository

## File editing policy

Patch-based editing is broken in this environment.

- NEVER use the built-in patch helper.
- NEVER use `apply_patch`.
- NEVER use `git apply`.
- NEVER check whether any patch helper is available.
- Do not retry patch-based editing with absolute paths, relative paths, different syntax, or alternate wrappers.
- Edit files only with ordinary shell tools or scripts.
- Preferred methods:
  - Python scripts that read, modify, and rewrite files
  - `cat > file <<'EOF'`
  - `perl -0pi`
  - `sed` only for small, safe replacements
- Before writing, verify the target file exists.
- If an editing tool fails once, do not retry the same method; switch immediately to another non-patch method.
- Do not pause to explain patch-tool failures unless they prevent completion of the requested work.
- After editing, inspect `git diff` and run `git diff --check`.
- Finish requested implementation work with the appropriate build/tests, commit, and push unless the user says otherwise.

## Frontend test environment

- Before running frontend browser or end-to-end tests in a fresh Codex environment, run `cd frontend && npm run setup:codex`.
- This installs locked frontend dependencies and the Chromium browser required by Playwright.
- Do not attempt ad hoc `npm exec --package=...` fallbacks when dependencies are missing; use the repository setup script.
