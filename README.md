# Neraium

**Systemic Infrastructure Intelligence for engineering teams.**

Neraium is a read-only intelligence layer that learns how operational systems behave over time and recognizes when that behavior fundamentally changes.

Rather than monitoring isolated signals against fixed thresholds, Neraium evaluates relationships among signals, establishes a behavioral baseline, and surfaces persistent changes that appear meaningful enough for engineering review.

The platform is designed to give engineers an extra set of eyes across complex operational data without taking control away from them.

> **Neraium provides visibility. The human provides judgment.**

---

## What Neraium Is

Neraium is a platform for **Systemic Infrastructure Intelligence (SII)**.

It works with operational data already collected through sources such as:

- Historians
- Building automation systems
- SCADA systems
- Approved databases
- Exported CSV, TXT, or JSON telemetry
- Read-only data connectors

Neraium is currently focused on telemetry-heavy infrastructure, with commercial water systems, central plants, resorts, aquatic facilities, filtration systems, pump networks, and mechanical infrastructure as primary use cases.

The same relationship-based intelligence can extend to other operational environments where many signals interact continuously.

---

## Core Product Principles

### Read-only by design

Neraium does not control equipment, change setpoints, or write commands back to operational systems.

### Human in the loop

Neraium identifies and explains meaningful changes. Engineers determine what those changes mean and what action, if any, should be taken.

### Relationship-based intelligence

Traditional alarms typically evaluate individual readings against fixed limits. Neraium evaluates how signals behave together.

Examples include:

- Pump power relative to flow
- Pressure relative to filter differential pressure
- Valve position relative to system response
- Chiller power relative to cooling demand
- Cooling-tower performance relative to ambient conditions
- Makeup-water demand relative to occupancy or load

These relationships can shift even when individual readings remain within normal alarm limits.

### Persistence over noise

Neraium is not intended to flag every fluctuation. It prioritizes changes that persist and appear meaningful enough for engineering review.

### Explainable findings

Every finding should show what changed, where it changed, which signals were involved, what evidence supports it, and where investigation should begin.

### Evidence-bounded certainty

Neraium should never present a finding with more certainty than the combined strength of the data quality, operating-context match, persistence, and relationship evidence supports.

---

## How Neraium Works

A typical analysis workflow is:

1. Import or connect approved operational telemetry.
2. Validate timestamps, numeric signals, completeness, and data quality.
3. Establish a baseline for how signals normally behave together.
4. Compare a later period or live data against that learned behavior.
5. Identify persistent changes in relationships among signals.
6. Rank the most meaningful findings for engineering review.
7. Present supporting evidence, time windows, contributing signals, and investigation guidance.
8. Preserve evidence and replay artifacts for later review.

The platform is built around a simple principle:

> **Know the operating context, verify the data, detect persistent relationship change, explain the evidence, then suggest where to investigate.**

---

## Historical Proof of Value

Before live deployment, Neraium can establish a baseline from an earlier historical period and analyze a later historical period against it.

This allows an engineering team to evaluate the platform using its own operational data before approving a live connection.

A historical proof-of-value analysis can help determine:

- Whether the findings are meaningful
- Whether the evidence makes operational sense
- Whether relationship changes were visible before an incident or operational problem became obvious
- Whether existing alarms or individual trend reviews missed useful context
- Whether a live deployment would provide practical value

This workflow is read-only and does not require Neraium to control or modify the customer system.

---

## What a Finding Shows

A Neraium finding can include:

- What changed
- Where it changed
- Which signals were involved
- The baseline and recent behavior
- Persistence duration
- Confidence and confidence rationale
- Data-quality conditions
- Supporting evidence
- Contributing relationships
- Possible operational explanations
- Why the change may matter
- A timeline of the change
- Recommended first checks
- Source time ranges and evidence references

The current explanation layer already supports relationship grouping, confidence labeling, evidence summaries, possible operational causes, activity timelines, and recommended investigation steps.

---

## Current Platform Capabilities

### Telemetry ingestion and validation

- CSV, TXT, and JSON upload paths
- Timestamp profiling
- Numeric-signal profiling
- Missing and invalid value handling
- Row acceptance and drop reporting
- Irregular-sampling detection
- Stuck or constant sensor identification
- Baseline reliability checks

### Behavioral analysis

- Historical baseline creation
- Baseline-versus-recent comparison
- Multivariable relationship analysis
- Persistent change detection
- Relationship grouping
- Drift and instability assessment
- Evidence-backed confidence handling

### Engineering findings

- Prioritized findings
- What-changed summaries
- Affected systems and signals
- Possible operational causes
- Operational-impact explanations
- Recommended investigation steps
- First-check guidance
- Relationship activity timelines
- Evidence summaries and source ranges

### Investigation and evidence

- Engineering Findings view
- Investigation drawer and workspace
- Systems view
- Behavior Baseline view
- Evidence replay support
- Persisted evidence records
- Audit events
- Analysis history

### Data access and operations

- Read-only connector setup
- Connector testing and health visibility
- Backend worker processing
- Runtime observability
- Authentication and role boundaries
- Production-oriented AWS ECS/Fargate preparation
- Continuous backend and frontend validation through GitHub Actions

---

## Current Product Surfaces

The operator workspace includes:

- **Command Center**
- **Systems**
- **Engineering Findings**
- **Behavior Baseline**
- **Datasets & Connectors**
- **Analysis Details**

The product is structured to help an engineer move from system status, to a prioritized finding, to supporting evidence, to a focused investigation path.

---

## Finding Classification Direction

Neraium is being strengthened so findings can distinguish among different classes of change rather than presenting every result as a generic anomaly.

The target first-class classifications are:

### Known operational change

The shift aligns with a documented schedule change, equipment staging change, maintenance event, setpoint change, special event, or other known operating condition.

### Possible instrumentation issue

The evidence is more consistent with sensor drift, flatlining, timing misalignment, recalibration, missing data, or disagreement between related measurements.

### Unexplained systemic change

The relationship changed persistently, the data appears trustworthy, comparable operating conditions were evaluated, and no known operational change explains the shift.

### Insufficient evidence

A possible change was observed, but the available data or operating context is not strong enough to support a reliable interpretation.

These classifications are intended to make findings more useful and more honest, not to claim root cause.

---

## Near-Term Product Priorities

The next major product work is focused on strengthening the foundation before adding more advanced recommendations.

### 1. Operating-mode awareness

Compare recent behavior against historically comparable conditions such as:

- Day versus night
- Weekday versus weekend
- Summer versus winter
- High load versus low load
- One-pump versus two-pump operation
- Normal operation versus backwash or maintenance
- Different equipment staging configurations
- Known schedule and setpoint states

### 2. Signal-level sensor health

Extend current data-quality checks into clearer per-signal assessments for:

- Flatlining
- Dropout
- Missingness
- Timing misalignment
- Possible recalibration
- Gradual divergence from related signals
- Irregular sampling
- Frozen or duplicated readings

### 3. Transparent finding classification

Make operating-context match, data confidence, sensor health, persistence, and relationship evidence first-class fields in every finding.

### 4. Relationship timelines

Show how a relationship moved from baseline-aligned behavior to persistent change over time.

### 5. Evidence-linked investigation guidance

Provide short, editable, probabilistic next checks tied directly to the available evidence without diagnosing root cause.

### 6. Engineer feedback

Capture outcomes such as confirmed issue, known operational change, instrumentation issue, useful monitoring, not useful, or investigation pending.

Feedback should improve ranking, presentation, suppression of known conditions, and investigation guidance without silently rewriting the core relationship model.

### 7. Domain starter packs and portfolio intelligence

Provide conditional relationship templates for common resort, water-system, and central-plant use cases, followed later by multi-system and multi-facility comparison views.

---

## What Neraium Does Not Do

Neraium does not:

- Control equipment
- Change setpoints
- Replace alarms
- Replace engineering judgment
- Predict exact failures
- Confirm root cause on its own
- Guarantee that every developing problem will be detected
- Treat engineering heuristics as universal physical laws

Neraium provides evidence and direction for review. The engineer remains responsible for interpretation, inspection, and action.

---

## Repository Structure

```text
backend/    FastAPI application, telemetry processing, analysis services, evidence, connectors, workers, and runtime operations
frontend/   Vite React operator workspace and investigation interface
docs/       Architecture, deployment, pilot, validation, and implementation notes
scripts/    Local development, build, and validation helpers
tests/      Backend regression, reliability, upload, and analysis coverage
```

---

## Technical Architecture

### Backend

The backend is a FastAPI application with services for:

- Upload ingestion and validation
- Behavioral baseline creation
- Relationship analysis
- SII processing
- Evidence persistence
- Replay artifacts
- Audit events
- Read-only data connections
- Authentication and authorization
- Worker processing
- Runtime observability

Important API areas include:

- `GET /api/health`
- `GET /api/app`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/facility/systems`
- `POST /api/data/upload`
- Upload status and replay endpoints
- Evidence and audit endpoints
- Connector and readiness endpoints

Runtime state is written under `NERAIUM_RUNTIME_DIR`.

### Frontend

The frontend is a Vite React application for engineering and operator workflows.

It supports:

- Telemetry import
- Processing visibility
- Command-center status
- System discovery
- Engineering findings
- Investigation workflows
- Behavior baseline review
- Evidence and analysis details
- Historical analysis reopening
- Connector configuration

The frontend runs locally at:

```text
http://127.0.0.1:3010
```

The backend runs locally at:

```text
http://127.0.0.1:8010
```

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- npm

---

## Backend Setup

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

---

## Frontend Setup

```powershell
cd frontend
npm install
npm run dev
```

---

## Common Environment Variables

Production should explicitly configure runtime storage, authentication, CORS, workers, and deployment settings.

Common variables include:

- `APP_ENV`
- `BACKEND_HOST`
- `BACKEND_PORT`
- `CORS_ORIGINS`
- `CORS_ORIGIN_REGEX`
- `NERAIUM_RUNTIME_DIR`
- `NERAIUM_PROCESS_ROLE`
- `NERAIUM_START_BACKGROUND_WORKERS`
- `NERAIUM_START_DATA_POLLER`
- `NERAIUM_MAX_UPLOAD_SIZE_BYTES`
- `NERAIUM_MAX_PENDING_UPLOAD_JOBS`
- `NERAIUM_UPLOAD_STATE_BUCKET`
- `NERAIUM_AUTH_DATABASE_URL`
- `VITE_API_BASE_URL`

---

## Tests and Validation

Run backend tests from the repository root:

```powershell
$env:PYTHONPATH = ".\backend"
python -m pytest tests
```

Run frontend validation from the frontend directory:

```powershell
cd frontend
npm run lint
npm run build
npm run test
```

Helper scripts are available from the repository root:

```powershell
.\scripts\start-backend.ps1
.\scripts\start-frontend.ps1
.\scripts\test-backend.ps1
.\scripts\build-frontend.ps1
```

GitHub Actions validates backend tests, frontend linting, frontend builds, frontend tests, and security-related checks on pushes and pull requests.

---

## Reliability and Evidence Guardrails

The current platform includes reliability hardening for messy operational telemetry.

Implemented guardrails include:

- Structured reliability ratings
- Rows received, used, and dropped
- Missing and invalid numeric conditions
- Stuck-sensor detection
- Irregular-sampling detection
- Baseline reliability checks
- Confidence caps when data quality is weak
- Evidence records with variables, timestamps, source rows, and baseline/recent metrics
- Frontend suppression of unsupported SII claims when evidence or reliability requirements are not met

Relevant documentation includes:

- `docs/sii_robustness_assessment.md`
- `docs/sii_math_audit.md`
- `docs/platform_strengthening_plan.md`
- `docs/PRODUCTION_ACCEPTANCE_CHECKLIST.md`
- `docs/PRODUCTION_OPERATOR_FLOW_CHECKLIST.md`

---

## Deployment

Neraium includes AWS deployment preparation for API and worker services using ECS/Fargate and ECR.

Deployment and operational notes are available in:

- `docs/AWS_DEPLOYMENT.md`
- `docs/DEPLOYMENT_RUNBOOK.md`
- `docs/OPERATIONS.md`
- `docs/PRODUCTION_ACCEPTANCE_CHECKLIST.md`

Production deployments should use durable shared storage, explicit authentication configuration, appropriate role boundaries, and verified multi-instance behavior.

---

## Current Status

Neraium 1.0 is the active production-oriented foundation for read-only Systemic Infrastructure Intelligence workflows.

The platform currently supports telemetry ingestion, validation, historical baseline creation, relationship-based behavioral analysis, evidence-backed findings, confidence handling, investigation guidance, replay artifacts, audit logging, read-only connectors, authentication, runtime observability, CI validation, and cloud deployment preparation.

The immediate product direction is to strengthen operating-mode awareness, signal-level sensor health, finding classification, relationship timelines, evidence-linked investigation guidance, and engineer feedback.

---

## Vision

Neraium is building a general-purpose intelligence layer for complex operational systems.

The goal is not to replace engineers or automate judgment. The goal is to help engineering teams see persistent changes earlier, understand the evidence faster, and know where to begin investigating before a developing problem becomes an obvious operational failure.

> **An extra set of eyes for engineers.**
