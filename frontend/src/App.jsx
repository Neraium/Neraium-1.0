import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "./config";
import "./styles.css";

const WORKSPACES = [
  {
    id: "overview",
    label: "Overview",
    eyebrow: "Summary",
    description: "Facility-wide operational awareness, alerts, ingest activity, and top findings.",
  },
  {
    id: "facility-systems",
    label: "Facility Systems",
    eyebrow: "Systems",
    description: "Environmental systems review, room telemetry, drift, and sensor relationships.",
  },
  {
    id: "data-intake",
    label: "Data Intake",
    eyebrow: "Intake",
    description: "Procedural CSV intake, validation, schema review, baseline comparison, and evidence state.",
  },
  {
    id: "evidence-reports",
    label: "Evidence & Reports",
    eyebrow: "Evidence",
    description: "Findings review, evidence analysis, timeline playback, room observations, and report output.",
  },
  {
    id: "intelligence-console",
    label: "Intelligence Console",
    eyebrow: "Console",
    description: "Live monitoring, drift feed, relationship changes, event stream, and evidence terminal.",
  },
];

const FALLBACK_SYSTEMS = [
  {
    name: "HVAC",
    scope: "Temperature conditioning, runtime behavior, and room balancing.",
  },
  {
    name: "Humidity control",
    scope: "Dehumidification, humidification, and moisture stability.",
  },
  {
    name: "Airflow",
    scope: "Circulation, pressure movement, and room exchange behavior.",
  },
  {
    name: "Irrigation",
    scope: "Irrigation timing, cycle review, and environmental response context.",
  },
  {
    name: "Lighting",
    scope: "Photoperiod windows, fixture response, and environmental coupling.",
  },
  {
    name: "Sensor network",
    scope: "Room sensors, gateway exports, and telemetry continuity.",
  },
];

const TELEMETRY_CHANNELS = [
  "temperature",
  "humidity",
  "CO2",
  "HVAC",
  "airflow",
  "irrigation",
  "lighting",
  "sensor network",
];

const INTAKE_STAGES = [
  "Batch receipt",
  "Header and schema detection",
  "Timestamp and room context review",
  "Baseline and evidence extraction",
];

const REPORT_TEMPLATES = [
  "Environmental Drift Summary",
  "System Coupling Review",
  "Operator Action Report",
];

const DEMO_ROOMS = [
  { name: "Flower Room 1", cycle: "Flower week 5", irrigation: "Pulse cycle 04", zone: "North bay" },
  { name: "Flower Room 2", cycle: "Flower week 7", irrigation: "Pulse cycle 05", zone: "South bay" },
  { name: "Veg Room A", cycle: "Vegetative day 19", irrigation: "Feed hold", zone: "Propagation lane" },
];

const OPERATIONAL_TONES = ["nominal", "review", "elevated", "unstable"];

function App() {
  const [activeWorkspace, setActiveWorkspace] = useState("overview");
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const [telemetryTick, setTelemetryTick] = useState(0);
  const [apiStatus, setApiStatus] = useState({
    state: "checking",
    label: "Checking backend",
    detail: "Establishing API telemetry link.",
    checkedAt: null,
    attemptCount: 0,
    endpoint: formatEndpoint(API_BASE_URL),
    message: "",
  });
  const [systems, setSystems] = useState(FALLBACK_SYSTEMS);
  const [systemsState, setSystemsState] = useState("loading");
  const [latestUploadResult, setLatestUploadResult] = useState(null);
  const workspaceRef = useRef(null);
  const healthCheckAttemptsRef = useRef(0);

  useEffect(() => {
    let isActive = true;

    async function checkApiHealth(trigger = "scheduled") {
      const checkTime = new Date();
      const attemptCount = healthCheckAttemptsRef.current + 1;
      healthCheckAttemptsRef.current = attemptCount;

      try {
        const response = await fetch(`${API_BASE_URL}/api/health`);
        if (!response.ok) {
          throw new Error(`Unexpected response: ${response.status}`);
        }

        const payload = await response.json();
        if (isActive) {
          setApiStatus({
            state: "online",
            label: "Telemetry link established",
            detail: `${payload.service} responded ${payload.status} at ${formatClockTime(checkTime)}.`,
            checkedAt: checkTime.toISOString(),
            attemptCount,
            endpoint: formatEndpoint(API_BASE_URL),
            message: trigger === "scheduled" ? "Connection monitor active." : `Connection check triggered by ${trigger}.`,
          });
        }
      } catch (error) {
        if (isActive) {
          setApiStatus({
            state: "offline",
            label: "Backend reconnecting",
            detail: `No response from ${formatEndpoint(API_BASE_URL)} at ${formatClockTime(checkTime)}.`,
            checkedAt: checkTime.toISOString(),
            attemptCount,
            endpoint: formatEndpoint(API_BASE_URL),
            message: error instanceof Error ? error.message : "Connection check failed.",
          });
        }
      }
    }

    checkApiHealth("startup");
    const intervalId = window.setInterval(() => {
      checkApiHealth("interval");
    }, 20000);

    return () => {
      isActive = false;
      window.clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      setTelemetryTick((current) => current + 1);
    }, 4200);

    return () => window.clearInterval(intervalId);
  }, []);

  useEffect(() => {
    let isActive = true;

    async function loadFacilitySystems() {
      try {
        const response = await fetch(`${API_BASE_URL}/api/facility/systems`);
        if (!response.ok) {
          throw new Error(`Unexpected response: ${response.status}`);
        }

        const payload = await response.json();
        if (isActive && Array.isArray(payload.systems)) {
          setSystems(payload.systems);
          setSystemsState("ready");
        }
      } catch {
        if (isActive) {
          setSystems(FALLBACK_SYSTEMS);
          setSystemsState("fallback");
        }
      }
    }

    loadFacilitySystems();

    return () => {
      isActive = false;
    };
  }, []);

  const activeConfig = WORKSPACES.find((workspace) => workspace.id === activeWorkspace) ?? WORKSPACES[0];
  const roomContext = deriveRoomContext(latestUploadResult);
  const timeCoverage = deriveTimeCoverage(latestUploadResult);
  const useDemoTelemetry = apiStatus.state !== "online" || !latestUploadResult;
  const liveOps = buildOperationalContext({
    result: latestUploadResult,
    apiStatus,
    roomContext,
    systems,
    systemsState,
    tick: telemetryTick,
    useDemoTelemetry,
  });

  useEffect(() => {
    if (workspaceRef.current) {
      workspaceRef.current.scrollTo({ top: 0, behavior: "auto" });
    }
  }, [activeWorkspace]);

  useEffect(() => {
    if (!isWorkspaceMenuOpen) {
      return undefined;
    }

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setIsWorkspaceMenuOpen(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isWorkspaceMenuOpen]);

  function handleWorkspaceSelect(workspaceId) {
    setActiveWorkspace(workspaceId);
    setIsWorkspaceMenuOpen(false);
  }

  function renderActiveWorkspace() {
    if (activeWorkspace === "overview") {
      return (
        <OverviewWorkspace
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
          systems={systems}
          systemsState={systemsState}
          roomContext={roomContext}
          liveOps={liveOps}
        />
      );
    }

    if (activeWorkspace === "facility-systems") {
      return (
        <FacilitySystemsWorkspace
          systems={systems}
          systemsState={systemsState}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          liveOps={liveOps}
        />
      );
    }

    if (activeWorkspace === "data-intake") {
      return (
        <DataIntakeWorkspace
          latestUploadResult={latestUploadResult}
          onUploadComplete={setLatestUploadResult}
          roomContext={roomContext}
          liveOps={liveOps}
        />
      );
    }

    if (activeWorkspace === "evidence-reports") {
      return (
        <EvidenceReportsWorkspace
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          setActiveWorkspace={setActiveWorkspace}
          liveOps={liveOps}
        />
      );
    }

    return (
      <IntelligenceConsoleWorkspace
        latestUploadResult={latestUploadResult}
        apiStatus={apiStatus}
        roomContext={roomContext}
        liveOps={liveOps}
      />
    );
  }

  return (
    <main className="platform-shell">
      <aside className="platform-sidebar" aria-label="Workspace navigation">
        <WorkspaceNavigationContent
          activeWorkspace={activeWorkspace}
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          timeCoverage={timeCoverage}
          liveOps={liveOps}
          onSelectWorkspace={handleWorkspaceSelect}
        />
      </aside>

      <div className="platform-main">
        <header className="mobile-status-bar">
          <div className="mobile-status-bar__brand">
            <div className="brand-mark">N</div>
            <div>
              <p className="brand-name">Neraium</p>
              <p className="brand-subtitle">Cultivation infrastructure intelligence</p>
            </div>
          </div>
          <button
            className="workspace-menu-button"
            type="button"
            aria-expanded={isWorkspaceMenuOpen}
            aria-controls="mobile-workspace-drawer"
            onClick={() => setIsWorkspaceMenuOpen((current) => !current)}
          >
            <span className="workspace-menu-button__icon" aria-hidden="true">
              |||
            </span>
            <span>Workspaces</span>
          </button>
        </header>

        <TopStatusBar
          activeConfig={activeConfig}
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          timeCoverage={timeCoverage}
          liveOps={liveOps}
        />

        <section
          key={activeWorkspace}
          ref={workspaceRef}
          className="platform-workspace"
          aria-labelledby="page-title"
        >
          {renderActiveWorkspace()}
        </section>
      </div>

      <div
        className={`workspace-drawer-backdrop ${isWorkspaceMenuOpen ? "workspace-drawer-backdrop--open" : ""}`}
        hidden={!isWorkspaceMenuOpen}
        onClick={() => setIsWorkspaceMenuOpen(false)}
      />
      <aside
        className={`workspace-drawer ${isWorkspaceMenuOpen ? "workspace-drawer--open" : ""}`}
        id="mobile-workspace-drawer"
        aria-label="Workspace drawer"
        aria-hidden={!isWorkspaceMenuOpen}
      >
        <WorkspaceNavigationContent
          activeWorkspace={activeWorkspace}
          apiStatus={apiStatus}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          timeCoverage={timeCoverage}
          liveOps={liveOps}
          onSelectWorkspace={handleWorkspaceSelect}
        />
      </aside>
    </main>
  );
}

function WorkspaceNavigationContent({
  activeWorkspace,
  apiStatus,
  latestUploadResult,
  roomContext,
  timeCoverage,
  liveOps,
  onSelectWorkspace,
}) {
  return (
    <>
      <div className="sidebar-brand-shell">
        <div className="sidebar-brand">
          <div className="brand-mark">N</div>
          <div>
            <p className="brand-name">Neraium</p>
            <p className="brand-subtitle">Cultivation infrastructure intelligence</p>
          </div>
        </div>
        <span className="brand-edition">Operations Edition</span>
      </div>

      <div className="sidebar-section">
        <p className="sidebar-kicker">Workspaces</p>
        <nav className="workspace-nav">
          {WORKSPACES.map((workspace) => (
            <button
              className={`workspace-nav__item ${activeWorkspace === workspace.id ? "workspace-nav__item--active" : ""}`}
              key={workspace.id}
              type="button"
              aria-current={activeWorkspace === workspace.id ? "page" : undefined}
              onClick={() => onSelectWorkspace(workspace.id)}
            >
              <span className="workspace-nav__label">{workspace.label}</span>
              <span className="workspace-nav__detail">{workspace.description}</span>
            </button>
          ))}
        </nav>
      </div>

      <div className="sidebar-section sidebar-section--terminal">
        <p className="sidebar-kicker">Persistent telemetry</p>
        <SidebarTelemetry label="API target" value={formatEndpoint(API_BASE_URL)} />
        <SidebarTelemetry label="Primary room" value={roomContext.primary} />
        <SidebarTelemetry label="Time coverage" value={timeCoverage.summary} />
        <SidebarTelemetry label="Facility state" value={liveOps.facilityStateLabel} />
        <SidebarTelemetry label="Findings" value={`${liveOps.findings.length} active`} />
        <SidebarTelemetry label="Last check" value={liveOps.connectionSummary} />
      </div>

      <div className="sidebar-footer">
        <StatusDot tone={liveOps.connectionTone} />
        <div>
          <p>{liveOps.connectionLabel}</p>
          <span>{liveOps.connectionDetail}</span>
        </div>
      </div>
    </>
  );
}

function Panel({ title, subtitle, className = "", children }) {
  return (
    <section className={`ops-panel ${className}`.trim()}>
      <div className="ops-panel__header">
        <p className="section-token">{title}</p>
        <h2>{subtitle}</h2>
      </div>
      <div className="ops-panel__body">{children}</div>
    </section>
  );
}

function TopStatusBar({ activeConfig, apiStatus, latestUploadResult, roomContext, timeCoverage, liveOps }) {
  return (
    <header className="top-status">
      <div className="top-status__title">
        <p className="eyebrow">{activeConfig.eyebrow}</p>
        <h1 id="page-title">{activeConfig.label}</h1>
        <p>{activeConfig.description}</p>
        <div className="top-status__meta">
          <span className={`overview-pill overview-pill--${liveOps.connectionTone}`}>{liveOps.connectionLabel}</span>
          <span className="top-status__meta-copy">{liveOps.connectionSummary}</span>
        </div>
      </div>

      <div className="status-rack">
        <StatusChip label="Connectivity" value={liveOps.connectionLabel} tone={liveOps.connectionTone} />
        <StatusChip label="Room or zone" value={roomContext.primary} tone={liveOps.facilityTone} />
        <StatusChip
          label="Upload batch"
          value={latestUploadResult?.filename ?? "No facility upload connected"}
          tone={latestUploadResult ? "nominal" : "info"}
        />
        <StatusChip
          label="Readiness"
          value={latestUploadResult ? formatReadiness(latestUploadResult.data_quality.readiness) : liveOps.readinessLabel}
          tone={latestUploadResult?.data_quality?.readiness ?? liveOps.facilityTone}
        />
        <StatusChip
          label="Time coverage"
          value={timeCoverage.summary}
          tone={timeCoverage.hasCoverage ? "nominal" : "info"}
        />
        <StatusChip
          label="Operational result"
          value={latestUploadResult?.engine_result ? formatEngineResult(latestUploadResult.engine_result.overall_result) : liveOps.facilityStateLabel}
          tone={latestUploadResult?.engine_result?.overall_result ?? liveOps.facilityTone}
        />
      </div>
    </header>
  );
}

function OverviewWorkspace({ liveOps }) {
  const [selectedActionId, setSelectedActionId] = useState(liveOps.actionQueue[0]?.id ?? null);
  const [selectedNodeId, setSelectedNodeId] = useState(liveOps.topologyNodes[0]?.id ?? null);

  const findings = liveOps.findings.slice(0, 3);
  const selectedAction = liveOps.actionQueue.find((item) => item.id === selectedActionId) ?? liveOps.actionQueue[0];
  const selectedNode = liveOps.topologyNodes.find((item) => item.id === selectedNodeId) ?? liveOps.topologyNodes[0];
  const heroHeadline = liveOps.primaryWindow?.headline ?? "Intervention timing is stable.";
  const heroSubline = liveOps.primaryWindow?.subline ?? "Neraium is monitoring the current facility state.";
  const roomCount = liveOps.topologyNodes.length;
  const overviewSummary = [
    { label: "Telemetry", value: liveOps.connectionLabel, tone: liveOps.connectionTone },
    { label: "Operational state", value: liveOps.facilityStateLabel, tone: liveOps.facilityTone },
    { label: "Latest ingest", value: liveOps.connectionSummary, tone: "info" },
    { label: "Rooms monitored", value: `${roomCount}`, tone: "nominal" },
  ];

  return (
    <div className="workspace-grid workspace-grid--overview workspace-grid--overview-simple">
      <Panel
        title="Facility command"
        subtitle="Time remaining, trust, and the next decision to make."
        className="span-8 overview-panel overview-panel--hero"
      >
        <div className="overview-hero">
          <div className="overview-hero__lead">
            <span className={`overview-pill overview-pill--${liveOps.facilityTone}`}>{liveOps.heroTag}</span>
            <h2 className="overview-hero__headline">{heroHeadline}</h2>
            <p>{heroSubline}</p>
          </div>
          <div className="countdown-hero">
            <div className="countdown-hero__score">
              <span>Neraium score</span>
              <strong>{liveOps.neraiumScore}</strong>
              <p>{liveOps.scoreNarrative}</p>
            </div>
            <div className="countdown-hero__window">
              <span>Primary intervention window</span>
              <strong>{liveOps.primaryWindow?.window ?? "Monitoring active telemetry feed"}</strong>
              <p>{liveOps.primaryWindow?.detail ?? liveOps.connectionDetail}</p>
            </div>
          </div>
          <div className="overview-summary-grid">
            {overviewSummary.map((item) => (
              <div className={`overview-summary-cell overview-summary-cell--${item.tone}`} key={item.label}>
                <div className="overview-summary-cell__header">
                  <span>{item.label}</span>
                  <StatusDot tone={item.tone} />
                </div>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        </div>
      </Panel>

      <Panel
        title="Action queue"
        subtitle="Ranked by urgency, impact, and trust."
        className="span-4 overview-panel overview-panel--events"
      >
        <ActionQueue
          items={liveOps.actionQueue}
          selectedId={selectedAction?.id ?? null}
          onSelect={setSelectedActionId}
        />
      </Panel>

      <Panel
        title="Intervention windows"
        subtitle="How long you have before each monitored room needs attention."
        className="span-8 overview-panel overview-panel--rooms"
      >
        <InterventionGrid
          items={liveOps.interventionItems}
          selectedId={selectedNode?.id ?? null}
          onSelect={setSelectedNodeId}
        />
      </Panel>

      <Panel
        title="Why this matters"
        subtitle="Causal chain, confidence, and the recommended next move."
        className="span-4 overview-panel overview-panel--findings"
      >
        <WhyPanel item={selectedAction ?? selectedNode} findings={findings} />
      </Panel>

      <Panel
        title="System topology"
        subtitle="Facility-wide situational awareness without the dashboard noise."
        className="span-8 overview-panel overview-panel--rooms"
      >
        <TopologyMap
          nodes={liveOps.topologyNodes}
          selectedId={selectedNode?.id ?? null}
          onSelect={setSelectedNodeId}
        />
      </Panel>

      <Panel
        title="Recent changes"
        subtitle="Only the operational shifts that changed decision timing."
        className="span-4 overview-panel overview-panel--events"
      >
        <TimelineFeed items={liveOps.timeline.slice(0, 5)} />
      </Panel>
    </div>
  );
}

function FacilitySystemsWorkspace({ systems, systemsState, latestUploadResult, roomContext, liveOps }) {
  const telemetryCards = liveOps.telemetryCards;
  const driftRows = liveOps.driftRows;
  const relationshipRows = liveOps.relationshipRows;
  const roomTransitions = liveOps.roomTransitions;
  const irrigationPanel = telemetryCards.find((card) => card.label === "Irrigation") ?? null;

  return (
    <div className="workspace-grid workspace-grid--systems">
      <Panel
        title="HVAC and environmental telemetry"
        subtitle="Current telemetry strips and time-series placeholders across monitored environmental channels."
        className="span-8"
      >
        <TelemetryCardGrid cards={telemetryCards.slice(0, 6)} />
      </Panel>

      <Panel
        title="Irrigation review"
        subtitle="Cycle state, response variance, and operator review recommendations."
        className="span-4"
      >
        <TelemetryCardGrid cards={irrigationPanel ? [irrigationPanel] : []} compact />
        <CompactList
          items={liveOps.irrigationNotes}
          emptyText="Awaiting additional room telemetry."
        />
      </Panel>

      <Panel
        title="Room and zone telemetry"
        subtitle="Current room-level context and transition surface."
        className="span-3"
      >
        <TimelineFeed items={roomTransitions} />
      </Panel>

      <Panel
        title="Operational drift"
        subtitle="Baseline versus active-window movement across room telemetry."
        className="span-6"
      >
        <DriftMonitor rows={driftRows} />
      </Panel>

      <Panel
        title="Sensor relationships"
        subtitle="Paired signal changes and relational stability review."
        className="span-3"
      >
        <RelationshipMonitor rows={relationshipRows} />
      </Panel>

      <Panel
        title="Systems table"
        subtitle="Operational systems, room context, and source-state coverage."
        className="span-12"
      >
        <SystemsMatrix
          systems={systems}
          systemsState={systemsState}
          roomContext={roomContext}
          rows={liveOps.systemRows}
        />
      </Panel>
    </div>
  );
}

function DataIntakeWorkspace({ latestUploadResult, onUploadComplete, roomContext, liveOps }) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);

  async function handleUpload(event) {
    event.preventDefault();
    if (!selectedFile) {
      setUploadError("Choose a CSV file exported from facility or sensor systems.");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    setUploadState("uploading");
    setUploadError("");
    setUploadResult(null);

    try {
      const response = await fetch(`${API_BASE_URL}/api/data/upload`, {
        method: "POST",
        body: formData,
      });
      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.detail ?? "CSV upload could not be validated.");
      }

      setUploadResult(payload);
      onUploadComplete(payload);
      setUploadState("complete");
    } catch (error) {
      setUploadError(error.message);
      setUploadState("error");
    }
  }

  const intakeStages = uploadResult
    ? buildIntakeStages(uploadResult, uploadState, roomContext)
    : liveOps.intakeStages;

  return (
    <div className="workspace-grid workspace-grid--intake">
      <Panel
        title="CSV intake workflow"
        subtitle="Procedural intake for telemetry exports, parsing, validation, and evidence extraction."
        className="span-7"
      >
        <form className="intake-flow" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <p className="section-token">Batch source</p>
            <h3>Cultivation telemetry export</h3>
            <p>
              Upload room, irrigation, HVAC, or sensor-network CSV batches for deterministic parsing,
              baseline review, and operational evidence extraction.
            </p>
          </div>

          <div className="intake-flow__controls">
            <input
              accept=".csv,text/csv"
              id="csv-upload"
              type="file"
              onChange={(event) => {
                setSelectedFile(event.target.files?.[0] ?? null);
                setUploadError("");
              }}
            />
            <button className="command-button" type="submit" disabled={uploadState === "uploading"}>
              {uploadState === "uploading" ? "Validating batch" : "Validate batch"}
            </button>
          </div>

          <div className="intake-flow__status">
            <span>{selectedFile ? selectedFile.name : "No file selected"}</span>
            <span>{uploadStateMessage(uploadState)}</span>
          </div>

          {uploadError && <p className="form-error">{uploadError}</p>}
        </form>
      </Panel>

      <Panel
        title="Validation stages"
        subtitle="Traceable intake stages for schema, parsing, and evidence readiness."
        className="span-5"
      >
        <WorkflowStages items={intakeStages} />
      </Panel>

      <Panel
        title="Schema detection and room mapping"
        subtitle="Detected room context, mapped columns, and schema output from the active batch."
        className="span-4"
      >
        <SchemaMappingPanel result={uploadResult} roomContext={roomContext} />
      </Panel>

      <Panel
        title="Validation checks"
        subtitle="Current batch verification summary and procedural checkpoints."
        className="span-4"
      >
        <VerificationPanel result={uploadResult} />
      </Panel>

      <Panel
        title="Evidence extraction state"
        subtitle="Current extraction status for baseline evidence, findings, and report generation."
        className="span-4"
      >
        <EvidenceExtractionPanel result={uploadResult} />
      </Panel>

      <Panel
        title="Baseline comparison"
        subtitle="Current baseline review and operational drift extraction from the active batch."
        className="span-12"
      >
        {uploadResult ? (
          <DriftMonitor rows={uploadResult.baseline_analysis.column_drift} detailed />
        ) : (
          <EmptyState
            title="Baseline established from current telemetry surface"
            body="No facility upload connected. Demo monitoring remains active until room exports are uploaded."
          />
        )}
      </Panel>
    </div>
  );
}

function EvidenceReportsWorkspace({ latestUploadResult, roomContext, setActiveWorkspace, liveOps }) {
  const latestReport = latestUploadResult?.operator_report;
  const findings = liveOps.findings;
  const timeline = liveOps.timeline;
  const evidenceLines = liveOps.evidenceLines;
  const observations = liveOps.observations;

  return (
    <div className="workspace-grid workspace-grid--evidence">
      <Panel
        title="Findings report"
        subtitle="Analytical review surface for findings, checks, and evidence-backed observations."
        className="span-7"
      >
        {latestReport ? (
          <OperatorReportPanel report={latestReport} />
        ) : (
          <EmptyState
            title="Monitoring active telemetry feed"
            body="Operational evidence is updating from live demo telemetry until a facility upload is connected."
          />
        )}
      </Panel>

      <Panel
        title="Evidence review"
        subtitle="Audit-ready evidence references, source sections, and extraction traces."
        className="span-5"
      >
        <EvidenceConsole lines={evidenceLines} />
      </Panel>

      <Panel
        title="Timeline playback"
        subtitle="Timestamp-heavy playback for ingest, readiness, and findings progression."
        className="span-4"
      >
        <TimelineFeed items={timeline} />
      </Panel>

      <Panel
        title="Room observations"
        subtitle="Current room and zone observations grounded in the active batch."
        className="span-4"
      >
        <CompactList items={observations} emptyText="No room observations available." />
      </Panel>

      <Panel
        title="Limitations and exported reports"
        subtitle="Current limitations and exported report surface for the active session."
        className="span-4"
      >
        {latestReport ? (
          <CompactList items={[...latestReport.limitations, ...REPORT_TEMPLATES]} emptyText="No report output available." />
        ) : (
          <CompactList items={liveOps.reportNotes} emptyText="Awaiting additional room telemetry." />
        )}
      </Panel>

      <Panel
        title="Operational notes"
        subtitle="Current findings and navigation back to intake review."
        className="span-12"
      >
        <div className="evidence-action-row">
          <CompactList
            items={findings.slice(0, 6).map((item) => `${item.title}: ${item.detail}`)}
            emptyText="Awaiting evidence-linked findings."
            inline
          />
          <div className="evidence-action-row__meta">
            <StatusDot tone={liveOps.facilityTone} />
            <span>{liveOps.connectionSummary}</span>
          </div>
          <button className="command-button command-button--secondary" type="button" onClick={() => setActiveWorkspace("data-intake")}>
            Open Data Intake
          </button>
        </div>
      </Panel>
    </div>
  );
}

function IntelligenceConsoleWorkspace({ liveOps }) {
  const telemetryCards = liveOps.telemetryCards;
  const driftRows = liveOps.driftRows;
  const relationshipRows = liveOps.relationshipRows;
  const timeline = liveOps.timeline;
  const findings = liveOps.findings;
  const consoleEvents = liveOps.consoleEvents;

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel
        title="Live telemetry"
        subtitle="Current channel strips and environmental monitoring surface."
        className="span-6"
      >
        <TelemetryCardGrid cards={telemetryCards} />
      </Panel>

      <Panel
        title="Drift feed"
        subtitle="Current drift transitions and baseline movement across telemetry channels."
        className="span-2"
      >
        <DriftFeed rows={driftRows} />
      </Panel>

      <Panel
        title="Relationship changes"
        subtitle="Current paired-sensor changes and relational events."
        className="span-2"
      >
        <RelationshipMonitor rows={relationshipRows} />
      </Panel>

      <Panel
        title="Operational notices"
        subtitle="Current findings and monitoring notices."
        className="span-2"
      >
        <FeedList items={findings.slice(0, 6)} emptyText="Monitoring active telemetry feed." />
      </Panel>

      <Panel
        title="Live event stream"
        subtitle="Session-wide operational events, ingest progression, and room transitions."
        className="span-4"
      >
        <TimelineFeed items={timeline} />
      </Panel>

      <Panel
        title="Evidence terminal"
        subtitle="Streaming evidence and operational terminal output."
        className="span-5"
      >
        <EvidenceConsole lines={consoleEvents} animated />
      </Panel>

      <Panel
        title="Connection diagnostics"
        subtitle="Backend link state, reconnect cadence, and readable failure detail."
        className="span-3"
      >
        <FeedList items={liveOps.connectionEvents} emptyText="Connection diagnostics unavailable." />
      </Panel>
    </div>
  );
}

function WorkflowStages({ items }) {
  return (
    <div className="workflow-list">
      {items.map((item) => (
        <div className="workflow-step" key={item.title}>
          <StatusDot tone={item.tone} />
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
          <span>{item.state}</span>
        </div>
      ))}
    </div>
  );
}

function SchemaMappingPanel({ result, roomContext }) {
  return (
    <MetricGrid
      metrics={[
        { label: "Primary room", value: roomContext.primary },
        { label: "Secondary lane", value: roomContext.secondary },
        {
          label: "Mapped columns",
          value: result ? result.cultivation_mapping.mapped_column_count : "Awaiting facility upload",
        },
        {
          label: "Unknown columns",
          value: result ? result.cultivation_mapping.unknown_column_count : "Awaiting facility upload",
        },
      ]}
      compact
    />
  );
}

function VerificationPanel({ result }) {
  return (
    <MetricGrid
      metrics={[
        {
          label: "Readiness",
          value: result ? formatReadiness(result.data_quality.readiness) : "Awaiting facility upload",
        },
        { label: "Rows parsed", value: result ? result.row_count : "Monitoring active telemetry feed" },
        { label: "Timestamp context", value: result?.detected_timestamp_column ?? "Awaiting additional room telemetry" },
        { label: "Numeric channels", value: result ? result.data_quality.numeric_column_count : "No upload connected" },
      ]}
      compact
    />
  );
}

function EvidenceExtractionPanel({ result }) {
  return (
    <FeedList
      items={[
        {
          title: "Baseline evidence",
          detail: result ? `${result.baseline_analysis.columns_analyzed} columns analyzed.` : "Monitoring active telemetry feed.",
          tone: result ? "nominal" : "info",
        },
        {
          title: "Engine evidence",
          detail: result?.engine_result ? `${result.engine_result.evidence.length} evidence items.` : "Awaiting additional room telemetry.",
          tone: result?.engine_result ? "nominal" : "review",
        },
        {
          title: "Operator report",
          detail: result?.operator_report ? "Current findings report available." : "No facility upload connected.",
          tone: result?.operator_report ? "nominal" : "info",
        },
      ]}
      emptyText="Monitoring evidence stream."
    />
  );
}

function MetricGrid({ metrics, compact = false }) {
  return (
    <div className={`metric-grid ${compact ? "metric-grid--compact" : ""}`}>
      {metrics.map((metric) => (
        <div className="metric-cell" key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </div>
      ))}
    </div>
  );
}

function FeedList({ items, emptyText, inline = false }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No active items" body={emptyText} compact />;
  }

  return (
    <div className={`feed-list ${inline ? "feed-list--inline" : ""}`}>
      {items.map((item, index) => (
        <div className="feed-item" key={`${item.title ?? item}-${index}`}>
          <StatusDot tone={item.tone ?? "muted"} />
          <div>
            <strong>{item.title ?? item}</strong>
            {item.detail && <p>{item.detail}</p>}
          </div>
        </div>
      ))}
    </div>
  );
}

function TimelineFeed({ items }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No timeline events" body="Monitoring active telemetry feed." compact />;
  }

  return (
    <div className="timeline-list">
      {items.map((item, index) => (
        <div className="timeline-item" key={`${item.time}-${item.title}-${index}`}>
          <StatusDot tone={item.tone} />
          <span className="timeline-item__time">{item.time}</span>
          <div>
            <strong>{item.title}</strong>
            <p>{item.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function TelemetryCardGrid({ cards, compact = false }) {
  if (!cards || cards.length === 0) {
    return <EmptyState title="No telemetry available" body="Awaiting additional room telemetry." compact />;
  }

  return (
    <div className={`telemetry-grid ${compact ? "telemetry-grid--compact" : ""}`}>
      {cards.map((card) => (
        <div className="telemetry-card" key={card.label}>
          <div className="telemetry-card__header">
            <span>{card.label}</span>
            <StatusDot tone={card.tone} />
          </div>
          <strong>{card.primary}</strong>
          <p>{card.secondary}</p>
          <MiniSeries values={card.series} tone={card.tone} />
        </div>
      ))}
    </div>
  );
}

function MiniSeries({ values, tone }) {
  if (!values || values.length === 0) {
    return <div className="mini-series mini-series--empty">No live series</div>;
  }

  const maxValue = Math.max(...values, 1);

  return (
    <div className="mini-series">
      {values.map((value, index) => (
        <span
          className={`mini-series__bar mini-series__bar--${tone}`}
          key={`${value}-${index}`}
          style={{ height: `${Math.max((value / maxValue) * 100, 16)}%` }}
        />
      ))}
    </div>
  );
}

function DriftMonitor({ rows, detailed = false }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title="No drift review available" body="Awaiting additional room telemetry." compact />;
  }

  const maxMagnitude = Math.max(
    ...rows.map((row) => Math.abs(row.percent_change ?? row.absolute_change ?? 0)),
    1,
  );

  return (
    <div className="drift-list">
      {rows.map((row) => {
        const magnitude = Math.abs(row.percent_change ?? row.absolute_change ?? 0);
        const width = Math.max((magnitude / maxMagnitude) * 100, 6);

        return (
          <div className="drift-row" key={row.column}>
            <div className="drift-row__meta">
              <span>{row.column}</span>
              <strong>
                {row.percent_change === null ? row.absolute_change : `${row.percent_change}%`}
              </strong>
            </div>
            <div className="drift-row__track">
              <span
                className={`drift-row__fill drift-row__fill--${row.drift_flag}`}
                style={{ width: `${width}%` }}
              />
            </div>
            <div className="drift-row__status">
              <span>{row.direction}</span>
              <span>{row.drift_flag}</span>
            </div>
            {detailed && row.warnings?.length > 0 && (
              <p className="drift-row__detail">{row.warnings.join(" ")}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function DriftFeed({ rows }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title="No drift feed" body="Monitoring active telemetry feed." compact />;
  }

  return (
    <FeedList
      items={rows.map((row) => ({
        title: row.column,
        detail: `${row.direction} movement with ${row.percent_change === null ? row.absolute_change : `${row.percent_change}%`} change.`,
        tone: row.drift_flag,
      }))}
      emptyText="Awaiting drift output."
    />
  );
}

function RelationshipMonitor({ rows }) {
  if (!rows || rows.length === 0) {
    return <EmptyState title="No relationship changes" body="Awaiting paired room telemetry." compact />;
  }

  return (
    <div className="relationship-list">
      {rows.map((row, index) => (
        <div className="relationship-row" key={`${row.columns.join("-")}-${index}`}>
          <div className="relationship-row__header">
            <span>{row.columns.join(" x ")}</span>
            <StatusDot tone={row.tone ?? "info"} />
          </div>
          <strong>{row.change}</strong>
          <p>
            baseline {row.baseline_correlation} to active {row.recent_correlation}
          </p>
        </div>
      ))}
    </div>
  );
}

function AlertList({ alerts }) {
  if (!alerts || alerts.length === 0) {
    return <EmptyState title="No active alerts" body="Current rooms remain within monitored thresholds." compact />;
  }

  return <FeedList items={alerts} emptyText="No active alerts." />;
}

function SystemsMatrix({ systems, systemsState, roomContext, rows }) {
  const tableRows = rows ?? systems.map((system) => [
    system.name,
    system.scope,
    systemRoomContext(system.name, roomContext),
    systemsState === "ready" ? "Backend placeholder endpoint" : "Local fallback surface",
  ]);

  return (
    <DataTable
      columns={["System", "Operational review scope", "Room or zone context", "Source state"]}
      rows={tableRows}
    />
  );
}

function ZoneSummaryGrid({ items }) {
  return (
    <div className="zone-summary-grid">
      {items.map((item) => (
        <div className={`zone-summary-card zone-summary-card--${item.tone ?? "info"}`} key={item.label}>
          <div className="zone-summary-card__header">
            <span>{item.label}</span>
            <StatusDot tone={item.tone ?? "info"} />
          </div>
          <strong>{item.value}</strong>
          <p>{item.detail}</p>
        </div>
      ))}
    </div>
  );
}

function RoomHealthGrid({ rooms }) {
  if (!rooms || rooms.length === 0) {
    return <EmptyState title="No room health available" body="Awaiting active room monitoring." compact />;
  }

  return (
    <div className="room-health-grid">
      {rooms.map((room) => (
        <div className={`room-health-card room-health-card--${room.tone ?? "info"}`} key={room.label}>
          <div className="room-health-card__header">
            <div>
              <span>{room.label}</span>
              <strong>{room.value}</strong>
            </div>
            <StatusDot tone={room.tone ?? "info"} />
          </div>
          <p>{room.detail}</p>
          <div className="room-health-card__footer">
            <span className={`overview-pill overview-pill--${room.tone ?? "info"}`}>{room.value}</span>
            <span className="room-health-card__trend">Recent activity monitored</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function InterventionGrid({ items, selectedId, onSelect }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No intervention windows available" body="Monitoring active telemetry feed." compact />;
  }

  return (
    <div className="intervention-grid">
      {items.slice(0, 6).map((item) => (
        <button
          className={`intervention-card intervention-card--${item.tone} ${selectedId === item.id ? "intervention-card--selected" : ""}`}
          key={item.id}
          type="button"
          onClick={() => onSelect(item.id)}
        >
          <div className="intervention-card__header">
            <div>
              <span>{item.label}</span>
              <strong>{item.window}</strong>
            </div>
            <ConfidenceDial score={item.confidence} tone={item.tone} />
          </div>
          <p>{item.summary}</p>
          <div className="intervention-card__footer">
            <span className={`overview-pill overview-pill--${item.tone}`}>{item.recommendation}</span>
            <span className="room-health-card__trend">{item.change}</span>
          </div>
        </button>
      ))}
    </div>
  );
}

function ActionQueue({ items, selectedId, onSelect }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No queued actions" body="Current rooms remain within monitored thresholds." compact />;
  }

  return (
    <div className="action-queue">
      {items.slice(0, 5).map((item) => (
        <button
          className={`action-queue__item action-queue__item--${item.tone} ${selectedId === item.id ? "action-queue__item--selected" : ""}`}
          key={item.id}
          type="button"
          onClick={() => onSelect(item.id)}
        >
          <div className="action-queue__header">
            <span>{item.rankLabel}</span>
            <StatusDot tone={item.tone} />
          </div>
          <strong>{item.title}</strong>
          <p>{item.detail}</p>
          <div className="action-queue__meta">
            <span>{item.window}</span>
            <span>{item.impact}</span>
            <span>{item.confidence}% confidence</span>
          </div>
          <div className="action-queue__actions">
            {item.actions.map((action) => (
              <span
                className={`queue-action-pill ${action === item.primaryAction ? "queue-action-pill--primary" : ""}`}
                key={action}
              >
                {action}
              </span>
            ))}
          </div>
        </button>
      ))}
    </div>
  );
}

function WhyPanel({ item, findings }) {
  if (!item) {
    return <EmptyState title="No active explanation" body="Monitoring active telemetry feed." compact />;
  }

  return (
    <div className="why-panel">
      <div className="why-panel__summary">
        <div>
          <span className="section-token">Primary explanation</span>
          <h3>{item.title ?? item.label}</h3>
        </div>
        <ConfidenceDial score={item.confidence ?? 72} tone={item.tone ?? "info"} large />
      </div>
      <p className="why-panel__headline">{item.whyHeadline ?? item.summary ?? item.detail}</p>
      <div className="why-panel__chain">
        {(item.drivers ?? findings.map((entry) => entry.detail).slice(0, 3)).map((driver) => (
          <div className="why-panel__driver" key={driver}>
            <StatusDot tone={item.tone ?? "info"} />
            <span>{driver}</span>
          </div>
        ))}
      </div>
      <div className="why-panel__recommendation">
        <span>Recommended next move</span>
        <strong>{item.recommendation ?? item.primaryAction ?? "Continue monitoring"}</strong>
      </div>
    </div>
  );
}

function ConfidenceDial({ score, tone, large = false }) {
  const normalized = Math.max(0, Math.min(score ?? 0, 100));
  return (
    <div
      className={`confidence-dial confidence-dial--${tone} ${large ? "confidence-dial--large" : ""}`}
      style={{ "--confidence-value": `${normalized}%` }}
    >
      <div className="confidence-dial__inner">
        <strong>{normalized}%</strong>
        <span>confidence</span>
      </div>
    </div>
  );
}

function TopologyMap({ nodes, selectedId, onSelect }) {
  if (!nodes || nodes.length === 0) {
    return <EmptyState title="No system topology available" body="Awaiting active room monitoring." compact />;
  }

  return (
    <div className="topology-map">
      <div className="topology-map__hub">
        <span>Facility</span>
        <strong>Neraium control surface</strong>
      </div>
      <div className="topology-map__nodes">
        {nodes.map((node) => (
          <button
            className={`topology-node topology-node--${node.tone} ${selectedId === node.id ? "topology-node--selected" : ""}`}
            key={node.id}
            type="button"
            onClick={() => onSelect(node.id)}
          >
            <span>{node.label}</span>
            <strong>{node.window}</strong>
            <p>{node.status}</p>
          </button>
        ))}
      </div>
    </div>
  );
}

function OperatorReportPanel({ report }) {
  return (
    <div className="panel-stack">
      <StatusBanner
        title={report.title}
        subtitle={report.summary}
        tone={report.data_readiness}
      />

      <MetricGrid
        metrics={[
          { label: "Readiness", value: formatReadiness(report.data_readiness) },
          {
            label: "Timestamp column",
            value: report.time_coverage.detected_timestamp_column ?? "Not detected",
          },
          {
            label: "Sample interval",
            value: report.time_coverage.estimated_sample_interval ?? "Not available",
          },
          {
            label: "Evidence sources",
            value: report.source_sections_used.length,
          },
        ]}
        compact
      />

      <div className="two-column-block">
        <CompactList
          items={report.key_observations}
          emptyText="No observations were generated."
          title="Observations"
        />
        <CompactList
          items={report.recommended_operator_checks}
          emptyText="No operator checks were generated."
          title="Operator checks"
        />
      </div>
    </div>
  );
}

function CompactList({ items, emptyText, title, inline = false }) {
  return (
    <div className={`compact-list-block ${inline ? "compact-list-block--inline" : ""}`}>
      {title && <p className="section-token">{title}</p>}
      {items && items.length > 0 ? (
        <ul className={`compact-list ${inline ? "compact-list--inline" : ""}`}>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : (
        <p className="empty-copy">{emptyText}</p>
      )}
    </div>
  );
}

function EvidenceConsole({ lines, animated = false }) {
  return (
    <div className={`evidence-console ${animated ? "evidence-console--animated" : ""}`}>
      {lines.map((line, index) => (
        <div className="evidence-console__line" key={`${line}-${index}`}>
          <span>{line}</span>
        </div>
      ))}
    </div>
  );
}

function DataTable({ columns, rows }) {
  return (
    <div className="table-shell">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={`${rowIndex}-${columns[0]}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${rowIndex}-${cellIndex}`}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EmptyState({ title, body, compact = false }) {
  return (
    <div className={`empty-state ${compact ? "empty-state--compact" : ""}`}>
      <strong>{title}</strong>
      <p>{body}</p>
    </div>
  );
}

function StatusBanner({ title, subtitle, tone }) {
  return (
    <div className={`status-banner status-banner--${tone}`}>
      <StatusDot tone={tone} />
      <div>
        <strong>{title}</strong>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}

function StatusChip({ label, value, tone }) {
  return (
    <div className={`status-chip status-chip--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SidebarTelemetry({ label, value }) {
  return (
    <div className="sidebar-telemetry">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusDot({ tone }) {
  return <span className={`status-dot status-dot--${tone}`} />;
}

function buildTelemetryCards(result) {
  if (!result) {
    return TELEMETRY_CHANNELS.map((channel) => ({
      label: formatCategory(channel),
      primary: "Monitoring standby",
      secondary: "No facility upload connected.",
      series: [],
      tone: "info",
    }));
  }

  const mapping = result.cultivation_mapping?.categories ?? {};
  const profilesByColumn = new Map(
    (result.numeric_profiles ?? []).map((profile) => [profile.column, profile]),
  );
  const driftByColumn = new Map(
    (result.baseline_analysis?.column_drift ?? []).map((row) => [row.column, row]),
  );

  return TELEMETRY_CHANNELS.map((channel) => {
    const mappedColumns = mapping[channel] ?? [];
    const profile = mappedColumns.map((column) => profilesByColumn.get(column)).find(Boolean);
    const drift = mappedColumns.map((column) => driftByColumn.get(column)).find(Boolean);

    if (!profile) {
      return {
        label: formatCategory(channel),
        primary: mappedColumns.length > 0 ? "Mapped without numeric profile" : "Awaiting additional room telemetry",
        secondary:
          mappedColumns.length > 0
            ? mappedColumns.join(", ")
            : "No uploaded channel mapped to this system category yet.",
        series: [],
        tone: "info",
      };
    }

    return {
      label: formatCategory(channel),
      primary: `${profile.average} avg`,
      secondary: `${profile.column} | ${profile.missing_percent}% missing`,
      series: buildSeries(profile, drift),
      tone: mapOperationalTone(drift?.drift_flag ?? profile.variability ?? "normal"),
    };
  });
}

function buildSeries(profile, drift) {
  const values = [profile.min, profile.average, profile.max]
    .filter((value) => typeof value === "number")
    .map((value) => Math.abs(value));

  if (drift && typeof drift.absolute_change === "number") {
    values.push(Math.abs(drift.absolute_change));
  }

  return values;
}

function buildOperationalTimeline(result, apiStatus, roomContext) {
  const items = [];

  if (apiStatus) {
    items.push({
      time: "Session",
      title: apiStatus.label,
      detail: apiStatus.detail,
      tone: apiStatus.state,
    });
  }

  if (!result) {
    items.push({
      time: "Standby",
      title: "Monitoring active telemetry feed",
      detail: `No facility upload connected. ${roomContext.primary} remains the primary review lane.`,
      tone: "info",
    });
    items.push({
      time: "Standby",
      title: "Awaiting additional room telemetry",
      detail: "Upload room exports to replace simulated operational monitoring with current facility data.",
      tone: "review",
    });
    return items;
  }

  const timeCoverage = deriveTimeCoverage(result);
  items.push({
    time: timeCoverage.first ?? "Batch start",
    title: "Time coverage opened",
    detail: `Detected ${result.detected_timestamp_column ?? "row-order"} timeline context.`,
    tone: "online",
  });
  items.push({
    time: "Batch",
    title: "Ingest validated",
    detail: `${result.row_count} rows and ${result.column_count} columns parsed in memory.`,
    tone: "online",
  });
  items.push({
    time: "Batch",
    title: "Room context resolved",
    detail: roomContext.primary,
    tone: "muted",
  });
  items.push({
    time: "Review",
      title: "Readiness assessed",
      detail: formatReadiness(result.data_quality.readiness),
      tone: mapOperationalTone(result.data_quality.readiness),
    });
  items.push({
    time: "Review",
      title: "Mapping coverage",
      detail: `${result.cultivation_mapping.mapped_column_count} mapped columns across cultivation systems.`,
      tone: result.cultivation_mapping.mapped_column_count > 0 ? "nominal" : "info",
    });
  if (result.engine_result) {
    items.push({
      time: timeCoverage.last ?? "Findings",
      title: "Operational findings generated",
      detail: formatEngineResult(result.engine_result.overall_result),
      tone: mapOperationalTone(result.engine_result.overall_result),
    });
  }
  return items;
}

function buildFindingsFeed(result) {
  if (!result) {
    return [];
  }

  const items = [];
  const signals = result.engine_result?.signals ?? [];
  const observations = result.operator_report?.key_observations ?? [];
  const reviewColumns = result.operator_report?.columns_requiring_review ?? [];

  signals.slice(0, 4).forEach((signal) => {
    items.push({
      title: "Engine signal",
      detail: signal.message,
      tone: mapOperationalTone(signal.level ?? result.engine_result?.overall_result ?? "info"),
    });
  });

  observations.slice(0, 3).forEach((observation) => {
    items.push({
      title: "Observation",
      detail: observation,
      tone: "info",
    });
  });

  reviewColumns.slice(0, 3).forEach((item) => {
    items.push({
      title: "Column review",
      detail: `${item.column}: ${item.reasons.join(" ")}`,
      tone: "review",
    });
  });

  return items;
}

function buildAlertItems(result, apiStatus) {
  const alerts = [];

  if (apiStatus.state !== "online") {
    alerts.push({
      title: "Backend link unavailable",
      detail: apiStatus.detail,
      tone: "elevated",
    });
  }

  if (!result) {
    alerts.push({
      title: "No facility upload connected",
      detail: "Monitoring active telemetry feed until room exports are uploaded.",
      tone: "info",
    });
    return alerts;
  }

  (result.warnings ?? []).slice(0, 2).forEach((warning) => {
    alerts.push({
      title: "Batch warning",
      detail: warning,
      tone: "review",
    });
  });

  (result.engine_result?.limitations ?? []).slice(0, 2).forEach((limitation) => {
    alerts.push({
      title: "Review limitation",
      detail: limitation,
      tone: "info",
    });
  });

  (result.operator_report?.recommended_operator_checks ?? []).slice(0, 2).forEach((check) => {
    alerts.push({
      title: "Operator check",
      detail: check,
      tone: "review",
    });
  });

  return alerts.length > 0
    ? alerts
    : [
        {
          title: "No active operator alerts",
          detail: "Current upload remains within monitored operational baselines.",
          tone: "nominal",
        },
      ];
}

function buildOverviewMetrics(result, apiStatus, systems, systemsState) {
  return [
    {
      label: "Facility stability",
      value: result?.engine_result ? deriveFacilityStability(result) : "Monitoring active telemetry feed",
    },
    {
      label: "Active alerts",
      value: buildAlertItems(result, apiStatus).length,
    },
    {
      label: "Ingestion state",
      value: result ? formatReadiness(result.data_quality.readiness) : "No facility upload connected",
    },
    {
      label: "Systems in scope",
      value: systemsState === "ready" ? `${systems.length} live` : `${systems.length} placeholder`,
    },
  ];
}

function buildZoneSummary(roomContext) {
  return [
    {
      label: "Primary room",
      value: roomContext.primary,
      detail: "Current room or zone inferred from active upload context.",
      tone: "nominal",
    },
    {
      label: "Secondary lane",
      value: roomContext.secondary,
      detail: "Cross-room review placeholder for facility operations.",
      tone: "info",
    },
    {
      label: "Grow cycle",
      value: roomContext.cycle,
      detail: "Cycle context remains placeholder until facility metadata is connected.",
      tone: "review",
    },
    {
      label: "Irrigation review",
      value: roomContext.irrigation,
      detail: "Irrigation context reflects mapped channels when present.",
      tone: "review",
    },
  ];
}

function buildRoomTransitions(result, roomContext) {
  const items = [
    {
      time: "Transition",
      title: "Primary room context",
      detail: roomContext.primary,
      tone: "nominal",
    },
    {
      time: "Transition",
      title: "Secondary review lane",
      detail: roomContext.secondary,
      tone: "info",
    },
    {
      time: "Transition",
      title: "Irrigation context",
      detail: roomContext.irrigation,
      tone: "review",
    },
  ];

  if (result?.timestamp_profile?.estimated_sample_interval) {
    items.push({
      time: "Timing",
      title: "Sample interval",
      detail: result.timestamp_profile.estimated_sample_interval,
      tone: "nominal",
    });
  }

  return items;
}

function buildEvidenceConsole(result) {
  if (!result) {
    return [
      "evidence.console=monitoring_demo_telemetry",
      "schema.mapping=no_facility_upload_connected",
      "operator.report=awaiting_room_exports",
    ];
  }

  const lines = [
    `batch.file=${result.filename}`,
    `data.readiness=${result.data_quality.readiness}`,
    `rows=${result.row_count}`,
    `columns=${result.column_count}`,
    `mapping.coverage=${result.cultivation_mapping.coverage_percent}%`,
  ];

  (result.operator_report?.source_sections_used ?? []).forEach((section) => {
    lines.push(`report.source=${section}`);
  });

  (result.operator_report?.columns_requiring_review ?? []).slice(0, 4).forEach((item) => {
    lines.push(`review.column=${item.column}`);
  });

  (result.engine_result?.audit_trace ?? []).slice(0, 12).forEach((entry) => {
    lines.push(`engine.audit=${entry}`);
  });

  return lines;
}

function buildConsoleEvents(result, apiStatus, roomContext) {
  const lines = [
    `console.link=${apiStatus.label}`,
    `console.room=${roomContext.primary}`,
    `console.secondary=${roomContext.secondary}`,
    `console.irrigation=${roomContext.irrigation}`,
  ];

  if (result) {
    lines.push(`console.batch=${result.filename}`);
    lines.push(`console.readiness=${result.data_quality.readiness}`);
    (result.engine_result?.signals ?? []).slice(0, 6).forEach((signal) => {
      lines.push(`signal.event=${signal.message}`);
    });
  } else {
    lines.push("console.batch=no_facility_upload_connected");
  }

  return [...lines, ...buildEvidenceConsole(result).slice(0, 10)];
}

function buildRelationshipRows(result) {
  const evidence = result?.engine_result?.evidence ?? [];
  return evidence
    .filter((item) => item.type === "relationship_change")
    .map((item) => ({
      ...item,
      tone: mapOperationalTone(item.level ?? "review"),
    }));
}

function buildRoomObservations(result, roomContext) {
  const observations = [
    `Primary room or zone context: ${roomContext.primary}.`,
    `Secondary review lane: ${roomContext.secondary}.`,
    `Grow cycle placeholder: ${roomContext.cycle}.`,
    `Irrigation context: ${roomContext.irrigation}.`,
  ];

  if (result?.operator_report?.time_coverage?.first_timestamp && result?.operator_report?.time_coverage?.last_timestamp) {
    observations.push(
      `Observed time coverage runs from ${result.operator_report.time_coverage.first_timestamp} to ${result.operator_report.time_coverage.last_timestamp}.`,
    );
  }

  return observations;
}

function deriveRoomContext(result) {
  if (!result) {
    return {
      primary: "Flower Room 1",
      secondary: "Flower Room 2",
      cycle: "Mixed flowering rooms",
      irrigation: "Pulse cycle under review",
    };
  }

  const roomColumn = result.columns.find((column) => {
    const normalized = column.toLowerCase();
    return normalized.includes("room") || normalized.includes("zone");
  });
  const cycleColumn = result.columns.find((column) => {
    const normalized = column.toLowerCase();
    return normalized.includes("cycle") || normalized.includes("stage") || normalized.includes("phase");
  });

  const roomValues = roomColumn
    ? result.preview_rows.map((row) => row[roomColumn]).filter(Boolean)
    : [];
  const cycleValues = cycleColumn
    ? result.preview_rows.map((row) => row[cycleColumn]).filter(Boolean)
    : [];
  const irrigationMapped = result.cultivation_mapping?.categories?.irrigation?.length ?? 0;

  return {
    primary: roomValues[0] ?? "Room context not present in upload",
    secondary: roomValues[1] ?? "Awaiting additional room telemetry",
    cycle: cycleValues[0] ?? "Cycle metadata unavailable",
    irrigation: irrigationMapped > 0 ? "Irrigation channels mapped" : "Awaiting irrigation telemetry",
  };
}

function deriveTimeCoverage(result) {
  if (!result?.timestamp_profile) {
    return {
      hasCoverage: false,
      summary: "Awaiting room timestamps",
    };
  }

  const first = result.timestamp_profile.first_timestamp;
  const last = result.timestamp_profile.last_timestamp;

  return {
    hasCoverage: Boolean(first || last),
    summary:
      first && last
        ? `${first} to ${last}`
        : result.timestamp_profile.estimated_sample_interval ?? "Timestamp range unavailable",
  };
}

function deriveFacilityStability(result) {
  const overallResult = result.engine_result?.overall_result;
  if (overallResult === "normal") {
    return "Nominal environmental stability";
  }
  if (overallResult === "elevated") {
    return "Elevated drift requires review";
  }
  if (overallResult === "needs_review") {
    return "Review recommended for irrigation variance";
  }
  return "Monitoring active telemetry feed";
}

function buildIntakeStages(result, uploadState, roomContext) {
  return INTAKE_STAGES.map((stage, index) => {
    if (uploadState === "uploading") {
      return {
        title: stage,
        detail: index === 0 ? "Batch is being validated." : "Pending upstream stage completion.",
        state: index === 0 ? "active" : "queued",
        tone: index === 0 ? "info" : "review",
      };
    }

    if (!result) {
      return {
        title: stage,
        detail: index === 2 ? `Baseline established for ${roomContext.primary}.` : "No facility upload connected. Monitoring active telemetry feed.",
        state: "standby",
        tone: index === 3 ? "review" : "info",
      };
    }

    const details = [
      `${result.filename} received for in-memory parsing.`,
      `${result.columns.length} headers detected across the uploaded batch.`,
      `Room context resolved as ${roomContext.primary}.`,
      `${result.engine_result ? "Evidence extracted and findings generated." : "Evidence generation pending."}`,
    ];

    return {
      title: stage,
      detail: details[index],
      state: "complete",
      tone: index === 3 && !result.engine_result ? "review" : "nominal",
    };
  });
}

function systemRoomContext(systemName, roomContext) {
  const normalized = systemName.toLowerCase();
  if (normalized.includes("irrigation")) {
    return roomContext.irrigation;
  }
  if (normalized.includes("sensor")) {
    return roomContext.primary;
  }
  return roomContext.secondary;
}

function formatCategory(category) {
  if (category === "CO2") {
    return category;
  }
  return category
    .split(" ")
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
}

function uploadStateMessage(uploadState) {
  if (uploadState === "uploading") {
    return "Validation in progress";
  }
  if (uploadState === "complete") {
    return "Batch validation complete";
  }
  if (uploadState === "error") {
    return "Validation needs attention";
  }
  return "Awaiting file selection";
}

function formatReadiness(readiness) {
  if (readiness === "ready") {
    return "Ready";
  }
  if (readiness === "needs_review") {
    return "Needs review";
  }
  return "Not ready";
}

function formatEngineResult(result) {
  if (result === "elevated") {
    return "Elevated";
  }
  if (result === "needs_review") {
    return "Needs review";
  }
  return "Normal";
}

function formatEndpoint(endpoint) {
  return endpoint.replace("http://", "").replace("https://", "");
}

function formatClockTime(input) {
  const value = input instanceof Date ? input : new Date(input);
  return value.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function mapOperationalTone(value) {
  if (!value) {
    return "info";
  }
  if (["normal", "ready", "online", "low", "nominal"].includes(value)) {
    return "nominal";
  }
  if (["needs_review", "review", "watch", "checking"].includes(value)) {
    return "review";
  }
  if (["elevated", "high", "offline"].includes(value)) {
    return "elevated";
  }
  if (["unstable", "critical"].includes(value)) {
    return "unstable";
  }
  if (value === "muted") {
    return "info";
  }
  return value;
}

function cycleValue(base, tick, range = 6, precision = 1) {
  const value = base + Math.sin(tick / 2.2 + base / 7) * range + Math.cos(tick / 3.5 + base / 11) * (range / 2);
  return Number(value.toFixed(precision));
}

function buildOperationalContext({ result, apiStatus, roomContext, systems, systemsState, tick, useDemoTelemetry }) {
  const connectionTone = apiStatus.state === "online" ? "nominal" : "elevated";
  const connectionSummary = apiStatus.checkedAt
    ? `${formatClockTime(apiStatus.checkedAt)} CT | attempt ${apiStatus.attemptCount}`
    : "Connection check initializing";

  if (!useDemoTelemetry) {
    const telemetryCards = buildTelemetryCards(result);
    const facilityTone = mapOperationalTone(result?.engine_result?.overall_result ?? result?.data_quality?.readiness ?? "nominal");
    const interventionItems = buildUploadedInterventionItems(result, roomContext, telemetryCards, facilityTone);
    const actionQueue = buildActionQueue(interventionItems);
    const primaryWindow = interventionItems[0] ?? null;
    return {
      useDemoTelemetry: false,
      facilityTone,
      facilityStateLabel: formatEngineResult(result?.engine_result?.overall_result ?? "normal"),
      heroTag: facilityTone === "nominal" ? "Control window established" : "Decision window tightening",
      readinessLabel: formatReadiness(result?.data_quality?.readiness),
      connectionTone,
      connectionLabel: apiStatus.label,
      connectionDetail: apiStatus.detail,
      connectionSummary,
      neraiumScore: calculateNeraiumScore(facilityTone, interventionItems, true),
      scoreNarrative: summarizeScoreNarrative(facilityTone, interventionItems),
      primaryWindow,
      interventionItems,
      actionQueue,
      topologyNodes: buildTopologyNodes(interventionItems),
      alerts: buildAlertItems(result, apiStatus),
      findings: buildFindingsFeed(result),
      timeline: buildOperationalTimeline(result, apiStatus, roomContext),
      telemetryCards,
      summaryTelemetry: telemetryCards,
      overviewMetrics: buildOverviewMetrics(result, apiStatus, systems, systemsState),
      roomCards: buildZoneSummary(roomContext),
      roomTransitions: buildRoomTransitions(result, roomContext),
      driftRows: (result?.baseline_analysis?.column_drift ?? []).map((row) => ({
        ...row,
        drift_flag: mapOperationalTone(row.drift_flag),
      })),
      relationshipRows: buildRelationshipRows(result),
      irrigationNotes: [
        `Irrigation context: ${roomContext.irrigation}.`,
        "Baseline established from current upload.",
        "Review recommended for irrigation variance only where drift persists across the active window.",
      ],
      systemRows: systems.map((system) => [
        system.name,
        system.scope,
        systemRoomContext(system.name, roomContext),
        systemsState === "ready" ? "Backend feed active" : "Local fallback surface",
      ]),
      intakeStages: buildIntakeStages(result, "complete", roomContext),
      evidenceLines: buildEvidenceConsole(result),
      consoleEvents: buildConsoleEvents(result, apiStatus, roomContext),
      observations: buildRoomObservations(result, roomContext),
      reportNotes: REPORT_TEMPLATES,
      connectionEvents: buildConnectionEvents(apiStatus, tick),
    };
  }

  const roomStates = DEMO_ROOMS.map((room, index) => {
    const temperature = cycleValue(72 + index * 2, tick + index, 2.4, 1);
    const humidity = cycleValue(57 - index * 3, tick + index * 2, 3.2, 1);
    const co2 = Math.round(cycleValue(905 + index * 65, tick + index * 3, 42, 0));
    const hvacDrift = Number(cycleValue(0.8 + index * 0.55, tick + index * 4, 0.9, 2));
    const instability = Number(Math.abs(cycleValue(0.9 + index * 0.4, tick + index * 2, 0.7, 2)));
    const tone = resolveRoomTone(hvacDrift, instability, index, tick);
    return {
      ...room,
      temperature,
      humidity,
      co2,
      hvacDrift,
      instability,
      tone,
      irrigationState: ["Pulse active", "Cycle settling", "Valve hold", "Recovery window"][(tick + index) % 4],
    };
  });

  const telemetryCards = buildSimulatedTelemetryCards(roomStates, tick);
  const roomTransitions = buildSimulatedRoomTransitions(roomStates, tick);
  const driftRows = buildSimulatedDriftRows(roomStates, tick);
  const findings = buildSimulatedFindings(roomStates, tick);
  const connectionEvents = buildConnectionEvents(apiStatus, tick);
  const timeline = [
    ...connectionEvents.slice(0, 2),
    ...buildSimulatedTimeline(roomStates, tick),
  ].slice(0, 8);
  const facilityTone = roomStates.some((room) => room.tone === "unstable")
    ? "unstable"
    : roomStates.some((room) => room.tone === "elevated")
      ? "elevated"
    : roomStates.some((room) => room.tone === "review")
        ? "review"
        : "nominal";
  const interventionItems = buildSimulatedInterventionItems(roomStates);
  const actionQueue = buildActionQueue(interventionItems);
  const primaryWindow = interventionItems[0] ?? null;

  return {
    useDemoTelemetry: true,
    facilityTone,
    facilityStateLabel: formatOperationalLabel(facilityTone),
    heroTag: facilityTone === "nominal" ? "Intervention horizon open" : "Priority review active",
    readinessLabel: "Monitoring active telemetry feed",
    connectionTone,
    connectionLabel: apiStatus.state === "online" ? "Telemetry link established" : "Backend reconnecting",
    connectionDetail: apiStatus.state === "online"
      ? "Operational demo telemetry will stand down once facility uploads are present."
      : `Reconnect monitor active for ${apiStatus.endpoint}.`,
    connectionSummary,
    neraiumScore: calculateNeraiumScore(facilityTone, interventionItems, false),
    scoreNarrative: summarizeScoreNarrative(facilityTone, interventionItems),
    primaryWindow,
    interventionItems,
    actionQueue,
    topologyNodes: buildTopologyNodes(interventionItems),
    alerts: buildSimulatedAlerts(roomStates, apiStatus, tick),
    findings,
    timeline,
    telemetryCards,
    summaryTelemetry: telemetryCards.slice(0, 4),
    overviewMetrics: buildSimulatedOverviewMetrics(roomStates, systems, systemsState),
    roomCards: roomStates.map((room) => ({
      label: room.name,
      value: formatOperationalLabel(room.tone),
      detail: `${room.cycle} | ${room.irrigationState} | HVAC drift ${room.hvacDrift.toFixed(2)}F.`,
      tone: room.tone,
    })),
    roomTransitions,
    driftRows,
    relationshipRows: buildSimulatedRelationshipRows(roomStates, tick),
    irrigationNotes: [
      `${roomStates[0].name}: ${roomStates[0].irrigationState}.`,
      "Review recommended for irrigation variance when humidity recovery exceeds the active window.",
      "Environmental transition detected between flowering rooms during the latest cycle change.",
    ],
    systemRows: buildSimulatedSystemRows(systems, roomStates, systemsState, apiStatus),
    intakeStages: buildSimulatedIntakeStages(apiStatus, tick, roomContext),
    evidenceLines: buildSimulatedEvidenceLines(roomStates, tick, apiStatus),
    consoleEvents: buildSimulatedConsoleEvents(roomStates, tick, apiStatus),
    observations: buildSimulatedObservations(roomStates),
    reportNotes: [
      "Monitoring active telemetry feed",
      "Baseline established from current facility state",
      "Awaiting additional room telemetry",
    ],
    connectionEvents,
  };
}

function buildUploadedInterventionItems(result, roomContext, telemetryCards, facilityTone) {
  const engineSignals = result?.engine_result?.signals ?? [];
  const columnReview = result?.operator_report?.columns_requiring_review ?? [];
  const irrigationTone = result?.cultivation_mapping?.categories?.irrigation?.length ? "review" : "info";

  const items = [
    {
      id: "upload-hvac-balance",
      label: roomContext.primary,
      title: `${roomContext.primary} intervention window`,
      status: "HVAC balance review",
      window: windowLabelFromTone(facilityTone),
      tone: facilityTone,
      confidence: confidenceFromTone(facilityTone, true),
      summary: engineSignals[0]?.message ?? "Uploaded telemetry indicates the current room should remain within an active review window.",
      detail: `Current upload places ${roomContext.primary} in the primary review lane.`,
      whyHeadline: engineSignals[0]?.message ?? "Current drift and readiness signals are tightening the available intervention window.",
      drivers: buildWhyDrivers(result, telemetryCards, roomContext),
      recommendation: recommendationFromTone(facilityTone),
      primaryAction: primaryActionFromTone(facilityTone),
      actions: actionSetFromTone(facilityTone),
      impact: impactFromTone(facilityTone),
      change: "Updated from active upload",
      rankLabel: "Priority 01",
    },
    {
      id: "upload-irrigation-recovery",
      label: roomContext.secondary,
      title: `${roomContext.secondary} review horizon`,
      status: "Irrigation recovery",
      window: windowLabelFromTone(irrigationTone),
      tone: irrigationTone,
      confidence: confidenceFromTone(irrigationTone, true),
      summary: columnReview[0]
        ? `${columnReview[0].column} requires review before the next irrigation cycle change.`
        : "Irrigation variance remains a secondary review lane until more room telemetry is uploaded.",
      detail: roomContext.irrigation,
      whyHeadline: "Current irrigation behavior is not yet critical, but it is close enough to justify scheduled review.",
      drivers: [
        `Current irrigation context: ${roomContext.irrigation}.`,
        "Baseline established from current upload.",
        "Review is being prioritized over passive monitoring.",
      ],
      recommendation: recommendationFromTone(irrigationTone),
      primaryAction: primaryActionFromTone(irrigationTone),
      actions: actionSetFromTone(irrigationTone),
      impact: impactFromTone(irrigationTone),
      change: "Review horizon opened",
      rankLabel: "Priority 02",
    },
    {
      id: "upload-telemetry-continuity",
      label: "Facility telemetry",
      title: "Telemetry continuity window",
      status: "Upload continuity",
      window: apiStatusWindow(result),
      tone: "info",
      confidence: 68,
      summary: "Uploaded telemetry is connected, but additional room context will improve intervention precision.",
      detail: result?.filename ?? "No facility upload connected",
      whyHeadline: "The facility is connected, but the confidence of longer-range decisions improves as room coverage deepens.",
      drivers: [
        `${result.row_count} rows and ${result.column_count} columns parsed in memory.`,
        `${result.cultivation_mapping?.mapped_column_count ?? 0} mapped columns currently in scope.`,
        "Awaiting additional room telemetry where facility context is partial.",
      ],
      recommendation: "Continue monitoring",
      primaryAction: "Acknowledge",
      actions: ["Acknowledge", "Schedule Maintenance", "Escalate", "Ignore Pattern"],
      impact: "Facility-wide confidence",
      change: "Latest ingest synchronized",
      rankLabel: "Priority 03",
    },
  ];

  return items;
}

function buildSimulatedInterventionItems(roomStates) {
  return roomStates
    .map((room, index) => ({
      id: `room-${index + 1}`,
      label: room.name,
      title: `${room.name} intervention window`,
      status: room.cycle,
      window: interventionWindowFromRoom(room),
      tone: room.tone,
      confidence: confidenceFromRoom(room),
      summary: `${room.irrigationState}. HVAC drift is ${room.hvacDrift.toFixed(2)}F and instability is ${room.instability.toFixed(2)} against the current room baseline.`,
      detail: `${room.cycle} in ${room.zone}.`,
      whyHeadline: whyHeadlineFromRoom(room),
      drivers: buildDriversFromRoom(room),
      recommendation: recommendationFromTone(room.tone),
      primaryAction: primaryActionFromTone(room.tone),
      actions: actionSetFromTone(room.tone),
      impact: impactFromTone(room.tone),
      change: room.tone === "nominal" ? "Stable over the last cycle" : "Decision window shortened this cycle",
      rankLabel: `Priority 0${index + 1}`,
    }))
    .sort((a, b) => tonePriority(a.tone) - tonePriority(b.tone));
}

function buildActionQueue(interventionItems) {
  return interventionItems
    .map((item, index) => ({
      ...item,
      id: `action-${item.id}`,
      rankLabel: `Priority ${String(index + 1).padStart(2, "0")}`,
      title: item.title,
      detail: item.summary,
    }))
    .sort((a, b) => tonePriority(a.tone) - tonePriority(b.tone));
}

function buildTopologyNodes(interventionItems) {
  return interventionItems.slice(0, 6).map((item) => ({
    id: item.id,
    label: item.label,
    window: item.window,
    status: item.status,
    tone: item.tone,
    confidence: item.confidence,
    summary: item.summary,
    whyHeadline: item.whyHeadline,
    drivers: item.drivers,
    recommendation: item.recommendation,
    change: item.change,
  }));
}

function calculateNeraiumScore(facilityTone, interventionItems, hasUpload) {
  const base = facilityTone === "nominal"
    ? 92
    : facilityTone === "review"
      ? 78
      : facilityTone === "elevated"
        ? 63
        : 49;
  const confidenceLift = Math.round(average(interventionItems.map((item) => item.confidence)) / 12);
  const uploadLift = hasUpload ? 4 : 0;
  return Math.max(0, Math.min(base + confidenceLift + uploadLift, 100));
}

function summarizeScoreNarrative(facilityTone, interventionItems) {
  const urgentCount = interventionItems.filter((item) => item.tone === "elevated" || item.tone === "unstable").length;
  if (facilityTone === "nominal") {
    return "The facility remains inside a comfortable intervention horizon.";
  }
  if (urgentCount > 0) {
    return `${urgentCount} intervention window${urgentCount === 1 ? "" : "s"} shortened enough to warrant immediate operator attention.`;
  }
  return "Most systems remain controllable, with review concentrated in a narrow set of rooms.";
}

function buildWhyDrivers(result, telemetryCards, roomContext) {
  const firstCards = telemetryCards.slice(0, 2);
  return [
    firstCards[0] ? `${firstCards[0].label} currently reading ${firstCards[0].primary}.` : `Primary room context: ${roomContext.primary}.`,
    firstCards[1] ? `${firstCards[1].label} currently reading ${firstCards[1].primary}.` : `Secondary room context: ${roomContext.secondary}.`,
    result?.operator_report?.recommended_operator_checks?.[0] ?? "Recommended next move is based on the current upload readiness and drift pattern.",
  ];
}

function interventionWindowFromRoom(room) {
  if (room.tone === "unstable") {
    return `${Math.max(4, Math.round(14 - room.instability * 3))} hours`;
  }
  if (room.tone === "elevated") {
    return `${Math.max(1, Math.round(3 + room.hvacDrift * 2))} days`;
  }
  if (room.tone === "review") {
    return `${Math.max(4, Math.round(8 + room.hvacDrift * 4))} days`;
  }
  return `${Math.max(2, Math.round(3 + room.instability * 2))} weeks`;
}

function whyHeadlineFromRoom(room) {
  if (room.tone === "unstable") {
    return `${room.name} has hours, not days, before environmental instability becomes an operator problem.`;
  }
  if (room.tone === "elevated") {
    return `${room.name} is trending toward intervention and should be scheduled before the next cycle compounds the drift.`;
  }
  if (room.tone === "review") {
    return `${room.name} is still controllable, but the next decision window is now close enough to plan around.`;
  }
  return `${room.name} is healthy and currently operating with a comfortable intervention horizon.`;
}

function buildDriversFromRoom(room) {
  return [
    `Bearing room temperature equivalent drift is ${room.hvacDrift.toFixed(2)}F over the current review window.`,
    `Environmental instability is ${room.instability.toFixed(2)} relative to this room's recent baseline.`,
    `${room.irrigationState} is the current operating state for ${room.name}.`,
  ];
}

function confidenceFromRoom(room) {
  if (room.tone === "unstable") {
    return 95;
  }
  if (room.tone === "elevated") {
    return 86;
  }
  if (room.tone === "review") {
    return 74;
  }
  return 64;
}

function confidenceFromTone(tone, hasUpload = false) {
  const base = tone === "unstable"
    ? 93
    : tone === "elevated"
      ? 84
      : tone === "review"
        ? 72
        : tone === "nominal"
          ? 66
          : 61;
  return hasUpload ? Math.min(base + 5, 98) : base;
}

function recommendationFromTone(tone) {
  if (tone === "unstable") {
    return "Immediate attention required";
  }
  if (tone === "elevated") {
    return "Schedule maintenance window";
  }
  if (tone === "review") {
    return "Review recommended";
  }
  return "No action needed";
}

function primaryActionFromTone(tone) {
  if (tone === "unstable") {
    return "Escalate";
  }
  if (tone === "elevated") {
    return "Schedule Maintenance";
  }
  if (tone === "review") {
    return "Acknowledge";
  }
  return "Ignore Pattern";
}

function actionSetFromTone(tone) {
  const actions = ["Acknowledge", "Schedule Maintenance", "Escalate", "Ignore Pattern"];
  if (tone === "unstable") {
    return ["Escalate", "Schedule Maintenance", "Acknowledge", "Ignore Pattern"];
  }
  return actions;
}

function impactFromTone(tone) {
  if (tone === "unstable") {
    return "High business impact";
  }
  if (tone === "elevated") {
    return "Material business impact";
  }
  if (tone === "review") {
    return "Moderate business impact";
  }
  return "Low business impact";
}

function windowLabelFromTone(tone) {
  if (tone === "unstable") {
    return "8 hours";
  }
  if (tone === "elevated") {
    return "2 days";
  }
  if (tone === "review") {
    return "6 days";
  }
  if (tone === "nominal") {
    return "3 weeks";
  }
  return "Monitoring";
}

function apiStatusWindow(result) {
  if (!result) {
    return "Monitoring";
  }
  return result.data_quality?.readiness === "ready" ? "2 weeks" : "5 days";
}

function tonePriority(tone) {
  if (tone === "unstable") {
    return 0;
  }
  if (tone === "elevated") {
    return 1;
  }
  if (tone === "review") {
    return 2;
  }
  if (tone === "nominal") {
    return 3;
  }
  return 4;
}

function resolveRoomTone(hvacDrift, instability, index, tick) {
  if (instability > 1.8 || (index === 1 && tick % 7 === 0)) {
    return "unstable";
  }
  if (hvacDrift > 1.55 || instability > 1.45) {
    return "elevated";
  }
  if (hvacDrift > 0.95 || instability > 1.1) {
    return "review";
  }
  return "nominal";
}

function buildSimulatedTelemetryCards(roomStates, tick) {
  const avgTemp = average(roomStates.map((room) => room.temperature));
  const avgHumidity = average(roomStates.map((room) => room.humidity));
  const avgCo2 = average(roomStates.map((room) => room.co2));
  const maxDrift = Math.max(...roomStates.map((room) => room.hvacDrift));
  const unstableRooms = roomStates.filter((room) => room.tone === "unstable" || room.tone === "elevated").length;

  return [
    {
      label: "Temperature",
      primary: `${avgTemp.toFixed(1)}F`,
      secondary: `${roomStates[0].name} to ${roomStates[2].name} live spread`,
      series: roomStates.map((room) => room.temperature),
      tone: maxDrift > 1.5 ? "elevated" : "nominal",
    },
    {
      label: "Humidity",
      primary: `${avgHumidity.toFixed(1)}% RH`,
      secondary: `${unstableRooms > 0 ? "Recovery lag detected" : "Room recovery nominal"}`,
      series: roomStates.map((room) => room.humidity),
      tone: unstableRooms > 0 ? "review" : "nominal",
    },
    {
      label: "CO2",
      primary: `${Math.round(avgCo2)} ppm`,
      secondary: `${roomStates[1].name} currently carries peak enrichment`,
      series: roomStates.map((room) => room.co2),
      tone: "info",
    },
    {
      label: "HVAC",
      primary: `${maxDrift.toFixed(2)}F drift`,
      secondary: `${unstableRooms} room${unstableRooms === 1 ? "" : "s"} under review`,
      series: roomStates.map((room) => room.hvacDrift * 10),
      tone: maxDrift > 1.7 ? "unstable" : maxDrift > 1.25 ? "elevated" : "review",
    },
    {
      label: "Airflow",
      primary: `${cycleValue(94, tick, 5, 0).toFixed(0)}% runtime`,
      secondary: "Transition dampers modulating between flowering zones",
      series: Array.from({ length: 6 }, (_, index) => 78 + ((tick + index * 7) % 18)),
      tone: "info",
    },
    {
      label: "Irrigation",
      primary: roomStates[0].irrigationState,
      secondary: `${roomStates[0].name} next review in ${12 - (tick % 6)} min`,
      series: Array.from({ length: 6 }, (_, index) => 24 + ((tick + index * 3) % 22)),
      tone: roomStates.some((room) => room.tone === "unstable") ? "review" : "nominal",
    },
  ];
}

function buildSimulatedTimeline(roomStates, tick) {
  const time = new Date(Date.now() - tick * 4200);
  return [
    {
      time: formatClockTime(time),
      title: "Environmental transition detected",
      detail: `${roomStates[1].name} humidity recovery slowed after irrigation cycle handoff.`,
      tone: roomStates[1].tone,
    },
    {
      time: formatClockTime(new Date(time.getTime() + 5 * 60000)),
      title: "HVAC drift review opened",
      detail: `${roomStates[0].name} supply temperature drift moved to ${roomStates[0].hvacDrift.toFixed(2)}F.`,
      tone: roomStates[0].tone,
    },
    {
      time: formatClockTime(new Date(time.getTime() + 11 * 60000)),
      title: "Ingestion monitor heartbeat",
      detail: "Telemetry watcher confirmed active room feed continuity across current facility lanes.",
      tone: "info",
    },
    {
      time: formatClockTime(new Date(time.getTime() + 17 * 60000)),
      title: "Operator review notice",
      detail: "Review recommended for irrigation variance before next flowering cycle change.",
      tone: "review",
    },
  ];
}

function buildSimulatedAlerts(roomStates, apiStatus) {
  const alertRooms = roomStates.filter((room) => room.tone !== "nominal");
  const items = [];
  if (apiStatus.state !== "online") {
    items.push({
      title: "No facility upload connected",
      detail: `Frontend monitoring is active while reconnect attempts continue for ${apiStatus.endpoint}.`,
      tone: "info",
    });
  }
  alertRooms.slice(0, 2).forEach((room) => {
    items.push({
      title: `${room.name} requires review`,
      detail: `${room.irrigationState}. HVAC drift ${room.hvacDrift.toFixed(2)}F with instability index ${room.instability.toFixed(2)}.`,
      tone: room.tone,
    });
  });
  items.push({
    title: "Monitoring active telemetry feed",
    detail: "Demo telemetry will remain active until uploaded facility exports replace the current surface.",
    tone: "info",
  });
  return items.slice(0, 4);
}

function buildSimulatedFindings(roomStates) {
  return roomStates.flatMap((room) => ([
    {
      title: `${room.name} telemetry review`,
      detail: `${room.cycle} with ${room.irrigationState.toLowerCase()} and ${room.hvacDrift.toFixed(2)}F HVAC drift.`,
      tone: room.tone,
    },
    {
      title: `${room.name} evidence event`,
      detail: `Environmental instability index ${room.instability.toFixed(2)} recorded against current room baseline.`,
      tone: room.tone === "nominal" ? "info" : room.tone,
    },
  ])).slice(0, 6);
}

function buildSimulatedDriftRows(roomStates) {
  return roomStates.flatMap((room) => ([
    {
      column: `${room.name} temperature`,
      percent_change: Number((room.hvacDrift * 2.4).toFixed(1)),
      absolute_change: room.hvacDrift,
      drift_flag: room.tone,
      direction: room.hvacDrift > 1.1 ? "upward drift" : "stable recovery",
      warnings: room.tone === "nominal" ? [] : [`Review recommended for ${room.name.toLowerCase()} HVAC balancing.`],
    },
    {
      column: `${room.name} humidity`,
      percent_change: Number((room.instability * 5.8).toFixed(1)),
      absolute_change: Number((room.instability * 1.6).toFixed(2)),
      drift_flag: room.tone === "nominal" ? "review" : room.tone,
      direction: room.instability > 1.1 ? "recovery lag" : "nominal stabilization",
      warnings: room.instability > 1.1 ? ["Environmental transition detected after latest irrigation cycle."] : [],
    },
  ])).slice(0, 6);
}

function buildSimulatedRelationshipRows(roomStates, tick) {
  return [
    {
      columns: ["humidity", "irrigation"],
      change: tick % 2 === 0 ? "Recovery slope widening" : "Recovery returning to baseline",
      baseline_correlation: "0.74",
      recent_correlation: tick % 2 === 0 ? "0.59" : "0.68",
      tone: tick % 2 === 0 ? "review" : "nominal",
    },
    {
      columns: ["HVAC", "temperature"],
      change: roomStates[0].hvacDrift > 1.4 ? "Supply drift elevated" : "Supply tracking nominal",
      baseline_correlation: "0.81",
      recent_correlation: roomStates[0].hvacDrift > 1.4 ? "0.63" : "0.77",
      tone: roomStates[0].hvacDrift > 1.4 ? "elevated" : "nominal",
    },
    {
      columns: ["CO2", "airflow"],
      change: "Relationship change observed during room transition",
      baseline_correlation: "0.66",
      recent_correlation: "0.52",
      tone: "info",
    },
  ];
}

function buildSimulatedOverviewMetrics(roomStates, systems, systemsState) {
  const roomsUnderReview = roomStates.filter((room) => room.tone !== "nominal").length;
  return [
    {
      label: "Facility stability",
      value: roomsUnderReview > 1 ? "Environmental transition detected" : "Monitoring active telemetry feed",
    },
    {
      label: "Rooms under review",
      value: roomsUnderReview,
    },
    {
      label: "Telemetry cadence",
      value: "4.2 second refresh",
    },
    {
      label: "Systems in scope",
      value: systemsState === "ready" ? `${systems.length} monitored` : `${systems.length} local surfaces`,
    },
  ];
}

function buildSimulatedSystemRows(systems, roomStates, systemsState, apiStatus) {
  return systems.map((system, index) => {
    const room = roomStates[index % roomStates.length];
    const stateLabel = room.tone === "nominal" ? "Monitoring active telemetry feed" : `${formatOperationalLabel(room.tone)} in ${room.name}`;
    return [
      system.name,
      system.scope,
      `${room.name} | ${room.zone}`,
      apiStatus.state === "online" && systemsState === "ready" ? "Backend feed active" : stateLabel,
    ];
  });
}

function buildSimulatedIntakeStages(apiStatus, tick, roomContext) {
  return [
    {
      title: "Batch receipt",
      detail: "No facility upload connected. Frontend telemetry simulation is maintaining live workspace state.",
      state: "standby",
      tone: "info",
    },
    {
      title: "Header and schema detection",
      detail: `Connection monitor last checked ${formatClockTime(apiStatus.checkedAt ?? new Date())} for ${apiStatus.endpoint}.`,
      state: "monitoring",
      tone: apiStatus.state === "online" ? "nominal" : "review",
    },
    {
      title: "Timestamp and room context review",
      detail: `Baseline room context held on ${roomContext.primary} while telemetry feed advances through live demo cadence ${tick}.`,
      state: "active",
      tone: "info",
    },
    {
      title: "Baseline and evidence extraction",
      detail: "Awaiting uploaded room exports to replace simulated evidence and drift relationships.",
      state: "standby",
      tone: "review",
    },
  ];
}

function buildSimulatedEvidenceLines(roomStates, tick, apiStatus) {
  return [
    `console.mode=frontend_simulation`,
    `connection.endpoint=${apiStatus.endpoint}`,
    `connection.last_check=${formatClockTime(apiStatus.checkedAt ?? new Date())}`,
    `room.primary=${roomStates[0].name}`,
    `room.transition=${roomStates[1].name}:humidity_recovery_review`,
    `hvac.review=${roomStates[0].hvacDrift.toFixed(2)}F_drift`,
    `irrigation.state=${roomStates[0].irrigationState.replace(/ /g, "_").toLowerCase()}`,
    `evidence.sequence=${tick}`,
    `operator.notice=review_recommended_for_irrigation_variance`,
  ];
}

function buildSimulatedConsoleEvents(roomStates, tick, apiStatus) {
  return [
    `telemetry.link=${apiStatus.state}`,
    `telemetry.sequence=${tick}`,
    `event.room_transition=${roomStates[1].name.replace(/ /g, "_").toLowerCase()}`,
    `event.hvac_drift=${roomStates[0].hvacDrift.toFixed(2)}`,
    `event.environmental_instability=${roomStates[1].instability.toFixed(2)}`,
    `event.irrigation_cycle=${roomStates[0].irrigationState.replace(/ /g, "_").toLowerCase()}`,
    `event.review_notice=operator_review_open`,
    ...buildSimulatedEvidenceLines(roomStates, tick, apiStatus),
  ];
}

function buildSimulatedObservations(roomStates) {
  return roomStates.map((room) => (
    `${room.name} in ${room.zone} is ${formatOperationalLabel(room.tone).toLowerCase()} with ${room.irrigationState.toLowerCase()}.`
  ));
}

function buildSimulatedRoomTransitions(roomStates, tick) {
  return roomStates.map((room, index) => ({
    time: formatClockTime(new Date(Date.now() - (index + 1) * 7 * 60000 - tick * 500)),
    title: `${room.name} transition`,
    detail: `${room.irrigationState} | ${room.zone} | ${room.temperature.toFixed(1)}F / ${room.humidity.toFixed(1)}% RH`,
    tone: room.tone,
  }));
}

function buildConnectionEvents(apiStatus, tick) {
  const checkedAt = apiStatus.checkedAt ?? new Date().toISOString();
  return [
    {
      title: apiStatus.state === "online" ? "Backend monitoring active" : "Reconnect attempt queued",
      detail: `${apiStatus.endpoint} checked ${formatClockTime(checkedAt)} CT.`,
      tone: apiStatus.state === "online" ? "nominal" : "elevated",
    },
    {
      title: "Connection diagnostics",
      detail: `${apiStatus.message || "Connection monitor active."} Attempt ${apiStatus.attemptCount || tick + 1}.`,
      tone: apiStatus.state === "online" ? "info" : "review",
    },
  ];
}

function formatOperationalLabel(tone) {
  if (tone === "nominal") {
    return "Nominal";
  }
  if (tone === "review") {
    return "Review";
  }
  if (tone === "elevated") {
    return "Elevated";
  }
  if (tone === "unstable") {
    return "Unstable";
  }
  return "Monitoring";
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);
}

function formatColumnsRequiringReview(columnsRequiringReview) {
  return columnsRequiringReview.map((item) => `${item.column}: ${item.reasons.join(" ")}`);
}

export default App;
