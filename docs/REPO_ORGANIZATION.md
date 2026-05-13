# Neraium 1.0 Repository Organization

This document defines how the repo should be organized going forward so frontend, backend, deployment, runtime, and documentation changes do not keep getting mixed together.

## Current top-level layout

```text
backend/      FastAPI API, runtime services, upload processing, SII runners, worker logic
frontend/     Vite React application, workspaces, UI components, CSS, client config
docs/         Architecture, deployment notes, repo organization, operator documentation
scripts/      Local helper scripts for dev, build, test, and deployment support
tests/        Backend and integration tests
.github/      GitHub Actions workflows
Dockerfile    Backend container image definition
docker-compose.yml  Local container orchestration when needed
```

## Target organization rules

### Backend

Backend code belongs under `backend/app/`.

Recommended structure:

```text
backend/app/
  core/          Settings, security, shared config
  models/        API response/request models
  routers/       FastAPI route modules only
  services/      Business logic, runtime state, upload jobs, SII execution
  runtime/       Local runtime state only. Do not commit generated runtime files.
```

Rules:

- Route files should stay thin and call `services/` for real work.
- Upload limits, runtime paths, CORS, process role, and worker settings belong in `backend/app/core/config.py`.
- Long-running upload processing should stay in services/workers, not directly in route handlers.
- Runtime outputs should be gitignored unless they are intentional fixtures.

### Frontend

Frontend code belongs under `frontend/src/`.

Recommended structure:

```text
frontend/src/
  components/       Reusable React components and workspace views
  viewModels/       Data shaping and UI-ready operational state builders
  styles/           All CSS split by purpose
  config.js         API base URL and client config
  App.jsx           App shell and workspace routing only
  main.jsx          React bootstrapping and global style imports only
```

Rules:

- `App.jsx` should stay as an app shell. Large workspace UIs belong in `components/`.
- Data transformation belongs in `viewModels/`, not inside components.
- CSS should be consolidated into `frontend/src/styles/` instead of adding loose root-level patch files.
- Desktop-only CSS must use `@media (min-width: 1101px)`.
- Mobile-only CSS must use `@media (max-width: 1100px)`.
- Do not append duplicate imports to `main.jsx`; keep style import order intentional.

### CSS cleanup target

Current emergency CSS should be consolidated into this structure:

```text
frontend/src/styles/
  base.css              Tokens, typography, reset, app shell base
  layout.css            Platform shell, workspace grids, status bars
  sidebar.css           Desktop sidebar and mobile drawer
  workspaces.css        Shared workspace panels/cards/tables/buttons
  system-body.css       System Body orb, metrics, evidence layout
  data-connections.css  Upload, REST connection, diagnostics views
  mobile.css            Mobile-specific overrides only
```

Import order in `main.jsx` should become:

```js
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/sidebar.css";
import "./styles/workspaces.css";
import "./styles/system-body.css";
import "./styles/data-connections.css";
import "./styles/mobile.css";
```

### Deployment

Deployment files should be isolated and named by environment.

Recommended structure:

```text
deploy/
  ecs/
    task-definition-api.json
    task-definition-worker.json
    service-api.md
  github-actions/
    backend-deploy.md
```

Rules:

- GitHub Actions should only trigger from committed source changes.
- ECS task definitions should not be edited manually in the console without reflecting the change in repo config.
- API and worker roles should be explicit through environment variables.

### Scripts

Scripts should be grouped by purpose:

```text
scripts/
  dev/
    start-backend.ps1
    start-frontend.ps1
    start-local-monolith.sh
  test/
    test-backend.ps1
    build-frontend.ps1
  deploy/
    deploy-backend.sh
```

### Branching workflow

Use this branch for active stabilization:

```text
aws-stable-api-worker-split
```

Recommended workflow:

```bash
git status
git pull
# make focused change
git add <changed files>
git commit -m "Short focused message"
git push
```

Avoid mixing CSS emergency fixes, backend upload changes, and AWS deployment changes in the same commit.

## Cleanup sequence

1. Stabilize the current branch.
2. Move loose CSS files into `frontend/src/styles/`.
3. Update `main.jsx` to import CSS from the new style modules only.
4. Split `App.jsx` further by moving header, sidebar, and drawer into components.
5. Add a `frontend/src/components/navigation/` folder for sidebar/mobile drawer components.
6. Add smoke tests for upload flow and frontend build.
7. Remove obsolete emergency patch files after visual verification.

## Files to prioritize next

High-priority cleanup targets:

```text
frontend/src/App.jsx
frontend/src/neraium-hardening.css
frontend/src/desktop-orb-top.css
frontend/src/mobile-restore.css
frontend/src/components/DataConnectionsWorkspace.jsx
frontend/src/components/SystemTopologyWorkspace.jsx
backend/app/core/config.py
backend/app/routers/data.py
backend/app/services/upload_jobs.py
```

## Definition of clean

The repo is considered clean when:

- Frontend layout CSS is split by purpose, not by emergency patch history.
- `App.jsx` is mostly routing and shared state, not large layout markup.
- Upload limits and backend settings are clearly controlled by environment variables.
- Desktop and mobile layout rules are separated and do not fight each other.
- Runtime files are not committed.
- The README tells a new developer exactly how to run backend, frontend, tests, and deploy safely.
