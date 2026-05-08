import { useCallback, useEffect, useRef, useState } from "react";
import {
  API_BASE_URL,
  API_CONFIG_WARNING,
  APP_ACCESS_CODE,
  APP_ACCESS_CONFIG_WARNING,
  HAS_APP_ACCESS_CODE,
} from "./config";
import "./styles.css";

const WORKSPACES = [
  {
    id: "overview",
    label: "Facility Command",
    eyebrow: "Command",
    description: "System status, room priority, and the next operator move.",
  },
  {
    id: "facility-systems",
    label: "Facility Systems",
    eyebrow: "Systems",
    description: "Room climate, irrigation, and crop-cycle pressure across the facility.",
  },
  {
    id: "data-intake",
    label: "Telemetry Intake",
    eyebrow: "Intake",
    description: "Connect facility telemetry to improve confidence, timing, and traceability.",
  },
  {
    id: "evidence-reports",
    label: "Evidence & Reports",
    eyebrow: "Evidence",
    description: "Room evidence, operator briefs, and action support.",
  },
  {
    id: "intelligence-console",
    label: "Intelligence Console",
    eyebrow: "Console",
    description: "Structural diagnostics, relationship evidence, and confidence basis.",
  },
];

const FALLBACK_SYSTEMS = [
  {
    name: "HVAC",
    scope: "Room temperature control, equipment activity, and zone balancing.",
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
  "Room Climate Trend Summary",
  "System Coupling Review",
  "Grower Action Report",
];

const DEMO_ROOMS = [
  { name: "Flower Room 1", cultivar: "Gush Mintz", cycle: "Flower week 5", irrigation: "Pulse cycle 04", zone: "North bay" },
  { name: "Flower Room 2", cultivar: "GDP", cycle: "Flower week 7", irrigation: "Pulse cycle 05", zone: "South bay" },
  { name: "Veg Room A", cultivar: "Cap Junky", cycle: "Vegetative day 19", irrigation: "Feed hold", zone: "Propagation lane" },
];

const OPERATIONAL_TONES = ["nominal", "review", "elevated", "unstable"];
const ACCESS_SESSION_KEY = "neraium_access_granted";
const OPERATIONAL_CADENCE_MS = 30000;

function App() {
  const [hasAccess, setHasAccess] = useState(() => (
    HAS_APP_ACCESS_CODE && window.sessionStorage.getItem(ACCESS_SESSION_KEY) === "true"
  ));
  const [activeWorkspace, setActiveWorkspace] = useState("overview");
  const [isWorkspaceMenuOpen, setIsWorkspaceMenuOpen] = useState(false);
  const [telemetryTick, setTelemetryTick] = useState(0);
  const [selectedInterventionId, setSelectedInterventionId] = useState(null);
  const [operatorActions, setOperatorActions] = useState({});
  const [apiStatus, setApiStatus] = useState({
    state: "checking",
    label: "Sync pending",
    detail: "Establishing facility sync.",
    checkedAt: null,
    attemptCount: 0,
    endpoint: formatEndpoint(API_BASE_URL),
    message: "",
  });
  const [systems, setSystems] = useState(FALLBACK_SYSTEMS);
  const [systemsState, setSystemsState] = useState("loading");
  const [backendError, setBackendError] = useState(API_CONFIG_WARNING);
  const [latestUploadResult, setLatestUploadResult] = useState(null);
  const workspaceRef = useRef(null);
  const healthCheckAttemptsRef = useRef(0);

  const checkApiHealth = useCallback(async (trigger = "scheduled") => {
    if (!hasAccess) {
      return false;
    }

    const checkTime = new Date();
    const attemptCount = healthCheckAttemptsRef.current + 1;
    healthCheckAttemptsRef.current = attemptCount;

    try {
      const response = await fetch(`${API_BASE_URL}/api/health`);
      if (!response.ok) {
        throw new Error(`Unexpected response: ${response.status}`);
      }

      const payload = await response.json();
      if (payload.status !== "ok") {
        throw new Error("Health response was not ok.");
      }

      setApiStatus({
        state: "online",
        label: "API Connected",
        detail: `Last sync ${formatClockTime(checkTime)} CT.`,
        checkedAt: checkTime.toISOString(),
        attemptCount,
        endpoint: formatEndpoint(API_BASE_URL),
        message: trigger === "scheduled" ? "Live telemetry feed current." : "Facility sync refreshed.",
      });
      setBackendError(API_CONFIG_WARNING);
      return true;
    } catch {
      setApiStatus({
        state: "offline",
        label: "API Offline",
        detail: "Backend connection unavailable. System data could not be loaded.",
        checkedAt: checkTime.toISOString(),
        attemptCount,
        endpoint: formatEndpoint(API_BASE_URL),
        message: "Backend connection unavailable. System data could not be loaded.",
      });
      setBackendError("Backend connection unavailable. System data could not be loaded.");
      return false;
    }
  }, [hasAccess]);

  const loadFacilitySystems = useCallback(async () => {
    if (!hasAccess) {
      return false;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/facility/systems`);
      if (!response.ok) {
        throw new Error(`Unexpected response: ${response.status}`);
      }

      const payload = await response.json();
      if (Array.isArray(payload.systems)) {
        setSystems(payload.systems);
        setSystemsState("ready");
        setBackendError(API_CONFIG_WARNING);
        return true;
      }
      throw new Error("Facility systems payload was incomplete.");
    } catch {
      setSystems(FALLBACK_SYSTEMS);
      setSystemsState("fallback");
      setBackendError("Backend connection unavailable. System data could not be loaded.");
      return false;
    }
  }, [hasAccess]);

  const retryBackendConnection = useCallback(async () => {
    const isHealthy = await checkApiHealth("retry");
    if (isHealthy) {
      await loadFacilitySystems();
    }
  }, [checkApiHealth, loadFacilitySystems]);

  useEffect(() => {
    if (!hasAccess) {
      return undefined;
    }

    checkApiHealth("startup");
    const intervalId = window.setInterval(() => {
      checkApiHealth("interval");
    }, 20000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [checkApiHealth, hasAccess]);

  useEffect(() => {
    if (!hasAccess) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      setTelemetryTick((current) => current + 1);
    }, OPERATIONAL_CADENCE_MS);

    return () => window.clearInterval(intervalId);
  }, [hasAccess]);

  useEffect(() => {
    if (!hasAccess) {
      return;
    }

    loadFacilitySystems();
  }, [hasAccess, loadFacilitySystems]);

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
    const nextId = liveOps.interventionItems[0]?.id ?? null;
    if (!nextId) {
      if (selectedInterventionId !== null) {
        setSelectedInterventionId(null);
      }
      return;
    }

    const stillExists = liveOps.interventionItems.some((item) => item.id === selectedInterventionId);
    if (!stillExists) {
      setSelectedInterventionId(nextId);
    }
  }, [liveOps.interventionItems, selectedInterventionId]);

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

  function handleOperatorAction(targetId, action) {
    setOperatorActions((current) => ({
      ...current,
      [targetId]: {
        action,
        at: new Date().toISOString(),
      },
    }));
  }

  function handleAccessGranted() {
    window.sessionStorage.setItem(ACCESS_SESSION_KEY, "true");
    setHasAccess(true);
  }

  function handleLockApp() {
    window.sessionStorage.removeItem(ACCESS_SESSION_KEY);
    setHasAccess(false);
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
          selectedInterventionId={selectedInterventionId}
          onSelectIntervention={setSelectedInterventionId}
          onNavigateWorkspace={setActiveWorkspace}
          operatorActions={operatorActions}
          onOperatorAction={handleOperatorAction}
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
          selectedInterventionId={selectedInterventionId}
          onSelectIntervention={setSelectedInterventionId}
          onNavigateWorkspace={setActiveWorkspace}
          operatorActions={operatorActions}
          onOperatorAction={handleOperatorAction}
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
          selectedInterventionId={selectedInterventionId}
          operatorActions={operatorActions}
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
          selectedInterventionId={selectedInterventionId}
          operatorActions={operatorActions}
          onOperatorAction={handleOperatorAction}
        />
      );
    }

    return (
      <IntelligenceConsoleWorkspace
        latestUploadResult={latestUploadResult}
        apiStatus={apiStatus}
        roomContext={roomContext}
        liveOps={liveOps}
        selectedInterventionId={selectedInterventionId}
        onSelectIntervention={setSelectedInterventionId}
        onNavigateWorkspace={setActiveWorkspace}
        operatorActions={operatorActions}
        onOperatorAction={handleOperatorAction}
      />
    );
  }

  if (!hasAccess) {
    return (
      <AccessGate
        onAccessGranted={handleAccessGranted}
        configWarning={APP_ACCESS_CONFIG_WARNING}
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
          onLockApp={handleLockApp}
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

        {backendError && (
          <BackendErrorPanel
            message={backendError}
            isConfigWarning={backendError === API_CONFIG_WARNING}
            onRetry={retryBackendConnection}
          />
        )}

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
          onLockApp={handleLockApp}
          onSelectWorkspace={handleWorkspaceSelect}
        />
      </aside>
    </main>
  );
}

function AccessGate({ onAccessGranted, configWarning }) {
  const [accessCode, setAccessCode] = useState("");
  const [accessError, setAccessError] = useState("");
  const isLockedByConfig = !HAS_APP_ACCESS_CODE;

  function handleSubmit(event) {
    event.preventDefault();
    if (isLockedByConfig || accessCode.trim() !== APP_ACCESS_CODE) {
      setAccessError("Access code not recognized.");
      return;
    }

    setAccessError("");
    onAccessGranted();
  }

  return (
    <main className="access-shell">
      <section className="access-panel" aria-labelledby="access-title">
        <div className="access-brand">
          <div className="brand-mark">N</div>
          <span>Private operations access</span>
        </div>
        <div className="access-copy">
          <p className="eyebrow">Neraium Access</p>
          <h1 id="access-title">Systemic Infrastructure Intelligence</h1>
          <p>Enter access code to continue.</p>
        </div>

        <form className="access-form" onSubmit={handleSubmit}>
          <label htmlFor="access-code">Access code</label>
          <input
            id="access-code"
            type="password"
            value={accessCode}
            onChange={(event) => {
              setAccessCode(event.target.value);
              setAccessError("");
            }}
            disabled={isLockedByConfig}
            autoComplete="current-password"
          />
          <button className="command-button" type="submit" disabled={isLockedByConfig}>
            Continue
          </button>
        </form>

        {(accessError || configWarning) && (
          <p className="access-error">{isLockedByConfig ? configWarning : accessError}</p>
        )}
      </section>
    </main>
  );
}

function WorkspaceNavigationContent({
  activeWorkspace,
  roomContext,
  timeCoverage,
  liveOps,
  onLockApp,
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
        <p className="sidebar-kicker">Persistent state</p>
        <SidebarTelemetry label="Data source" value={liveOps.dataSourceLabel} />
        <SidebarTelemetry label="Primary room" value={roomContext.primary} />
        <SidebarTelemetry label="Time coverage" value={timeCoverage.summary} />
        <SidebarTelemetry label="Facility state" value={liveOps.facilityStateLabel} />
        <SidebarTelemetry label="Findings" value={`${liveOps.findings.length} active`} />
        <SidebarTelemetry label="Last sync" value={liveOps.connectionSummary} />
      </div>

      <div className="sidebar-footer">
        <StatusDot tone={liveOps.connectionTone} />
        <div>
          <p>{liveOps.connectionStatusLine}</p>
          <span>{liveOps.connectionActionHint}</span>
        </div>
        <button className="lock-app-button" type="button" onClick={onLockApp}>
          Lock app
        </button>
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
          <span className={`top-status__signal top-status__signal--${liveOps.connectionTone}`} aria-label={liveOps.connectionStatusLine}>
            <StatusDot tone={liveOps.connectionTone} />
          </span>
          {liveOps.connectionActionHint && (
            <span className="top-status__meta-copy top-status__meta-copy--actionable">{liveOps.connectionActionHint}</span>
          )}
        </div>
      </div>

      <div className="status-rack">
        <StatusChip
          label="Backend"
          value={apiStatus.state === "online" ? "API Connected" : "API Offline"}
          tone={apiStatus.state === "online" ? "nominal" : "offline"}
        />
        <StatusChip label="Primary room" value={roomContext.primary} tone={liveOps.facilityTone} />
        <StatusChip
          label="Data source"
          value={liveOps.dataSourceLabel}
          tone="info"
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
          label="State"
          value={latestUploadResult?.engine_result ? formatEngineResult(latestUploadResult.engine_result.overall_result) : liveOps.facilityStateLabel}
          tone={latestUploadResult?.engine_result?.overall_result ?? liveOps.facilityTone}
        />
        <StatusChip
          label="Last sync"
          value={liveOps.connectionSummary}
          tone={liveOps.connectionTone}
        />
      </div>
    </header>
  );
}

function OverviewWorkspace({
  liveOps,
  selectedInterventionId,
  onSelectIntervention,
  onNavigateWorkspace,
  operatorActions,
  onOperatorAction,
}) {
  const findings = liveOps.findings.slice(0, 3);
  const selectedRoom = liveOps.interventionItems.find((item) => item.id === selectedInterventionId) ?? liveOps.interventionItems[0];
  const primaryRoom = liveOps.primaryWindow ?? selectedRoom;
  const heroHeadline = formatFacilityPlainState(liveOps.facilityTone, primaryRoom);
  const heroSubline = liveOps.heroSubline ?? "Neraium is monitoring the current facility state.";
  const roomCount = liveOps.interventionItems.length;

  return (
    <div className="workspace-grid workspace-grid--overview workspace-grid--overview-simple workspace-grid--operator-flow">
      <Panel
        title="Operating State"
        subtitle="Facility state, priority room, time, and next operator move."
        className="span-12 overview-panel overview-panel--hero overview-panel--command"
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
              <p className="countdown-hero__readiness">{formatScoreReadiness(liveOps.neraiumScore)}</p>
              <p className="countdown-hero__context">{liveOps.scoreContext}</p>
            </div>
            <div className="countdown-hero__window">
              <span>Time</span>
              <strong>{primaryRoom?.window ?? "Monitoring"}</strong>
              <p>Before {primaryRoom?.label ?? "the facility"} needs intervention.</p>
              <p className="countdown-hero__context">{primaryRoom?.primaryAction ?? primaryRoom?.recommendation ?? "Continue monitoring"}</p>
            </div>
          </div>

          <div className="operating-state-next">
            <span>Next operator move</span>
            <strong>{primaryRoom?.primaryAction ?? primaryRoom?.recommendation ?? "Continue monitoring"}</strong>
            <p>{primaryRoom?.whyHeadline ?? liveOps.windowContext}</p>
          </div>
        </div>
      </Panel>

      <Panel
        title="Rooms"
        subtitle={`${roomCount} rooms monitored. Priority rooms shown first.`}
        className="span-8 overview-panel overview-panel--rooms overview-panel--room-first"
      >
        <InterventionGrid
          items={liveOps.interventionItems}
          selectedId={selectedRoom?.id ?? null}
          onSelect={onSelectIntervention}
          compact
          limit={4}
        />
      </Panel>

      <Panel
        title="Selected room detail"
        subtitle="Why it matters and what to do next."
        className="span-4 overview-panel overview-panel--findings overview-panel--detail"
      >
        <WhyPanel
          item={selectedRoom}
          findings={findings}
          actionStatus={operatorActions[selectedRoom?.targetId ?? selectedRoom?.id]}
          compact
        />

        <div className="room-first-actions">
          <button className="secondary-command-button" type="button" onClick={() => onNavigateWorkspace("facility-systems")}>
            Open system detail
          </button>
          <button className="secondary-command-button" type="button" onClick={() => onNavigateWorkspace("evidence-reports")}>
            View evidence
          </button>
        </div>
      </Panel>
    </div>
  );
}
function FacilitySystemsWorkspace({
  systems,
  systemsState,
  roomContext,
  liveOps,
  selectedInterventionId,
  onSelectIntervention,
  onNavigateWorkspace,
  operatorActions,
  onOperatorAction,
}) {
  const telemetryCards = liveOps.telemetryCards;
  const driftRows = liveOps.driftRows;
  const relationshipRows = liveOps.relationshipRows;
  const roomTransitions = liveOps.roomTransitions;
  const irrigationPanel = telemetryCards.find((card) => card.label === "Irrigation") ?? null;
  const systemsFocus = liveOps.interventionItems.find((item) => item.id === selectedInterventionId) ?? liveOps.interventionItems[0] ?? null;
  const fleetSummary = buildFleetSummary(liveOps.interventionItems, liveOps.neraiumScore, liveOps.facilityTone);

  return (
    <div className="workspace-grid workspace-grid--systems">
      <Panel
        title="Facility overview"
        subtitle="Start with the full grow, then move into the room that needs attention."
        className="span-8"
      >
        <FleetSummary summary={fleetSummary} />
      </Panel>

      <Panel
        title="Rooms to review"
        subtitle="Ranked by time remaining."
        className="span-4"
      >
        <TargetSelector
          items={liveOps.interventionItems}
          selectedId={systemsFocus?.id ?? null}
          onSelect={onSelectIntervention}
        />
      </Panel>

      <Panel
        title="Selected room"
        subtitle="Why this intervention window is moving."
        className="span-3"
      >
        <WhyPanel
          item={systemsFocus}
          findings={liveOps.findings.slice(0, 3)}
          actionStatus={operatorActions[systemsFocus?.id]}
          onSeeWhatsWrong={() => onNavigateWorkspace("facility-systems")}
          onLogIntervention={(id) => onOperatorAction(id, "log")}
          onIgnorePattern={(id) => onOperatorAction(id, "ignore")}
        />
      </Panel>

      <Panel
        title="Room drivers"
        subtitle="Climate, irrigation, and cycle signals affecting the current window."
        className="span-6"
      >
        <TelemetryCardGrid cards={telemetryCards.slice(0, 6)} />
      </Panel>

      <Panel
        title="Room transitions"
        subtitle="Changes affecting timing."
        className="span-3"
      >
        <TimelineFeed items={roomTransitions} />
      </Panel>

      <Panel
        title="Room trend by channel"
        subtitle="Baseline movement by grow-room significance."
        className="span-5"
      >
        <DriftMonitor rows={driftRows} />
      </Panel>

      <Panel
        title="Relationship shifts"
        subtitle="Paired changes most likely to shift confidence."
        className="span-3"
      >
        <RelationshipMonitor rows={relationshipRows} />
      </Panel>

      <Panel
        title="Irrigation context"
        subtitle="Cycle state and grower review notes."
        className="span-4"
      >
        <TelemetryCardGrid cards={irrigationPanel ? [irrigationPanel] : []} compact />
        <CompactList
          items={liveOps.irrigationNotes}
          emptyText="Awaiting additional room telemetry."
        />
      </Panel>

      <Panel
        title="Systems in scope"
        subtitle="Source coverage and room context behind active decisions."
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

function DataIntakeWorkspace({ latestUploadResult, onUploadComplete, roomContext, liveOps, selectedInterventionId }) {
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
      setUploadError(
        error instanceof TypeError
          ? "Backend connection unavailable. System data could not be loaded."
          : error.message,
      );
      setUploadState("error");
    }
  }

  const intakeStages = uploadResult
    ? buildIntakeStages(uploadResult, uploadState, roomContext)
    : liveOps.intakeStages;
  const intakeFocus = liveOps.interventionItems.find((item) => item.id === selectedInterventionId) ?? liveOps.interventionItems[0] ?? null;

  return (
    <div className="workspace-grid workspace-grid--intake">
      <Panel
        title="Telemetry intake"
        subtitle="Connect facility data so timing becomes more precise."
        className="span-7"
      >
        <form className="intake-flow" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <p className="section-token">Batch source</p>
            <h3>Cultivation telemetry export</h3>
            <p>
              Upload room, irrigation, HVAC, or sensor-network CSV batches to improve confidence,
              shorten ambiguity, and replace simulated monitoring with live facility data.
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
        title="Decision readiness"
        subtitle="What must be true before Neraium can tighten the window."
        className="span-5"
      >
        <WorkflowStages items={intakeStages} />
      </Panel>

      <Panel
        title="Room mapping"
        subtitle="Facility context already connected."
        className="span-4"
      >
        <SchemaMappingPanel result={uploadResult} roomContext={roomContext} />
      </Panel>

      <Panel
        title="Confidence inputs"
        subtitle="Checks that govern how much Neraium should trust the upload."
        className="span-4"
      >
        <VerificationPanel result={uploadResult} />
      </Panel>

      <Panel
        title="Evidence readiness"
        subtitle="What is usable for explanation and action."
        className="span-4"
      >
        <EvidenceExtractionPanel result={uploadResult} />
      </Panel>

      <Panel
        title="Expected impact"
        subtitle="How the current upload changes timing and confidence."
        className="span-5"
      >
        <WhyPanel item={intakeFocus} findings={liveOps.findings.slice(0, 3)} />
      </Panel>

      <Panel
        title="Baseline comparison"
        subtitle="Current room trend extracted from the batch."
        className="span-7"
      >
        {uploadResult ? (
          <DriftMonitor rows={uploadResult.baseline_analysis.column_drift} detailed />
        ) : (
          <EmptyState
            compact
            title="Baseline established from current telemetry surface"
            body="Live telemetry feed is active. Manual upload remains available if you want to validate a room export."
          />
        )}
      </Panel>
    </div>
  );
}

function EvidenceReportsWorkspace({
  latestUploadResult,
  roomContext,
  setActiveWorkspace,
  liveOps,
  selectedInterventionId,
  operatorActions,
  onOperatorAction,
}) {
  const latestReport = latestUploadResult?.operator_report;
  const findings = liveOps.findings;
  const evidenceLines = liveOps.evidenceLines;
  const observations = liveOps.observations;
  const reportFocus =
    liveOps.actionQueue.find((item) => item.id === selectedInterventionId)
    ?? liveOps.interventionItems.find((item) => item.id === selectedInterventionId)
    ?? liveOps.actionQueue[0]
    ?? liveOps.interventionItems[0]
    ?? null;

  return (
    <div className="workspace-grid workspace-grid--evidence">
      <Panel
        title="Executive brief"
        subtitle="What is happening, why it matters, and the next move."
        className="span-7"
      >
        <ExecutiveBrief
          focus={reportFocus}
          report={latestReport}
          observations={observations}
          roomContext={roomContext}
          facilityTone={liveOps.facilityTone}
        />
      </Panel>

      <Panel
        title="Why and confidence"
        subtitle="The reasoning behind the current recommendation."
        className="span-5"
      >
        <WhyPanel
          item={reportFocus}
          findings={findings.slice(0, 3)}
          actionStatus={operatorActions[reportFocus?.targetId ?? reportFocus?.id]}
          onSeeWhatsWrong={() => setActiveWorkspace("facility-systems")}
          onLogIntervention={(id) => onOperatorAction(id, "log")}
          onIgnorePattern={(id) => onOperatorAction(id, "ignore")}
        />
      </Panel>

      <Panel
        title="Technical evidence"
        subtitle="Expandable traces, observations, and source detail beneath the brief."
        className="span-5"
      >
        <TechnicalEvidencePanel
          evidenceLines={evidenceLines}
          observations={observations}
          report={latestReport}
          timeline={liveOps.timeline}
        />
      </Panel>

      <Panel
        title="Report outputs"
        subtitle="Limitations and exported brief surfaces."
        className="span-3"
      >
        {latestReport ? (
          <CompactList items={[...latestReport.limitations, ...REPORT_TEMPLATES]} emptyText="No report output available." />
        ) : (
          <CompactList items={liveOps.reportNotes} emptyText="Awaiting additional room telemetry." />
        )}
      </Panel>

      <Panel
        title="Supporting findings"
        subtitle="Evidence-backed notes and a direct path back to intake."
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
            Refine Intake
          </button>
        </div>
      </Panel>
    </div>
  );
}

function IntelligenceConsoleWorkspace({
  liveOps,
  selectedInterventionId,
  onSelectIntervention,
  onNavigateWorkspace,
  operatorActions,
  onOperatorAction,
}) {
  const telemetryCards = liveOps.telemetryCards;
  const driftRows = liveOps.driftRows;
  const relationshipRows = liveOps.relationshipRows;
  const timeline = liveOps.timeline;
  const findings = liveOps.findings;
  const consoleEvents = liveOps.consoleEvents;
  const queueItems = liveOps.actionQueue.slice(0, 4);

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel
        title="Live decision stream"
        subtitle="The channels currently driving intervention timing."
        className="span-6"
      >
        <TelemetryCardGrid cards={telemetryCards} />
      </Panel>

      <Panel
        title="Action queue"
        subtitle="Priority-ranked grower actions."
        className="span-3"
      >
        <ActionQueue
          items={queueItems}
          selectedId={selectedInterventionId ?? queueItems[0]?.id ?? null}
          onSelect={onSelectIntervention}
        />
      </Panel>

      <Panel
        title="Room trend feed"
        subtitle="Changes shortening the current window."
        className="span-3"
      >
        <DriftFeed rows={driftRows} />
      </Panel>

      <Panel
        title="Relationship shifts"
        subtitle="Paired changes affecting confidence."
        className="span-3"
      >
        <RelationshipMonitor rows={relationshipRows} />
      </Panel>

      <Panel
        title="Grower notices"
        subtitle="Short-form findings and review notices."
        className="span-3"
      >
        <FeedList items={findings.slice(0, 6)} emptyText="Monitoring active telemetry feed." />
      </Panel>

      <Panel
        title="Selected action"
        subtitle="Next grower action with evidence."
        className="span-3"
      >
        <WhyPanel
          item={queueItems.find((item) => item.id === selectedInterventionId) ?? queueItems[0] ?? null}
          findings={findings.slice(0, 3)}
          actionStatus={operatorActions[(queueItems.find((item) => item.id === selectedInterventionId) ?? queueItems[0])?.targetId ?? selectedInterventionId ?? queueItems[0]?.id]}
          onSeeWhatsWrong={() => onNavigateWorkspace("facility-systems")}
          onLogIntervention={(id) => onOperatorAction(id, "log")}
          onIgnorePattern={(id) => onOperatorAction(id, "ignore")}
        />
      </Panel>

      <Panel
        title="Recent changes"
        subtitle="Events that changed decision timing."
        className="span-4"
      >
        <TimelineFeed items={timeline} />
      </Panel>

      <Panel
        title="Evidence terminal"
        subtitle="Streaming traces behind the current action surface."
        className="span-5"
      >
        <EvidenceConsole lines={consoleEvents} animated />
      </Panel>

      <Panel
        title="Connection diagnostics"
        subtitle="Sync state, last confirmed update, and grower guidance."
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
        { label: "Numeric channels", value: result ? result.data_quality.numeric_column_count : "Live telemetry feed" },
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
          title: "Grower report",
          detail: result?.operator_report ? "Current findings report available." : "Manual upload remains optional.",
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
    return <EmptyState title="No room trend review available" body="Awaiting additional room telemetry." compact />;
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
    return <EmptyState title="No room trend feed" body="Monitoring active telemetry feed." compact />;
  }

  return (
    <FeedList
      items={rows.map((row) => ({
        title: row.column,
        detail: `${row.direction} movement with ${row.percent_change === null ? row.absolute_change : `${row.percent_change}%`} change.`,
        tone: row.drift_flag,
      }))}
      emptyText="Awaiting room trend output."
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
    systemsState === "ready" ? "Live facility sync" : "Local fallback surface",
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

function InterventionGrid({ items, selectedId, onSelect, compact = false, limit = 6 }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No intervention windows available" body="Monitoring active telemetry feed." compact />;
  }

  return (
    <div className={`intervention-grid ${compact ? "intervention-grid--compact-command" : ""}`}>
      {items.slice(0, limit).map((item, index) => (
        <button
          className={`intervention-card intervention-card--${item.tone} ${selectedId === item.id ? "intervention-card--selected" : ""}`}
          key={item.id}
          type="button"
          onClick={() => onSelect(item.id)}
        >
          <div className="intervention-card__header">
            <div>
              <span>{item.label}</span>
              <strong>{item.decisionLabel ?? formatRoomDecisionState(item.tone, index)}</strong>
            </div>
            <StatusDot tone={item.tone ?? "info"} />
          </div>
          <div className="intervention-card__window">
            <span>Time</span>
            <strong>{item.window}</strong>
          </div>
          <p>{compact ? item.primaryAction ?? item.recommendation : item.shortDetail ?? item.summary}</p>
          {!compact && (
            <div className="intervention-card__footer">
              <span className={`overview-pill overview-pill--${item.tone}`}>{item.primaryAction ?? item.recommendation}</span>
            </div>
          )}
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
          <strong>{item.shortTitle ?? item.title}</strong>
          <p>{item.shortDetail ?? item.detail}</p>
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

function MorningCheck({ items, operatorActions, onSelect, onLogCondition }) {
  if (!items || items.length === 0) {
    return <EmptyState title="Morning check unavailable" body="Monitoring active telemetry feed." compact />;
  }

  return (
    <div className="morning-check">
      {items.slice(0, 4).map((item) => {
        const actionState = operatorActions[item.id];
        return (
          <div className={`morning-check__row morning-check__row--${item.tone}`} key={item.id}>
            <button className="morning-check__summary" type="button" onClick={() => onSelect(item.id)}>
              <div className="morning-check__identity">
                <StatusDot tone={item.tone} />
                <div>
                  <span>{item.label}</span>
                  <strong>{item.window}</strong>
                </div>
              </div>
              <div className="morning-check__meta">
                <span className={`overview-pill overview-pill--${item.tone}`}>{item.recommendation}</span>
                <p>{item.baselineContext ?? item.change}</p>
              </div>
            </button>
            <div className="morning-check__actions">
              <button className="command-button command-button--compact" type="button" onClick={() => onLogCondition(item.id)}>
                Log conditions
              </button>
              <button className="link-action" type="button" onClick={() => onSelect(item.id)}>
                Open room
              </button>
            </div>
            {actionState?.action === "log" && (
              <p className="morning-check__status">
                Conditions logged at {formatClockTime(actionState.at)} CT.
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

function WhyPanel({
  item,
  findings,
  actionStatus,
  compact = false,
}) {
  if (!item) {
    return <EmptyState title="No active explanation" body="Monitoring active telemetry feed." compact />;
  }

  const confidenceBasis = item.confidenceBasis ?? buildConfidenceBasis(item, findings);
  const supportingEvidence = item.supportingEvidence ?? item.drivers ?? findings.map((entry) => entry.detail).slice(0, 3);
  const contributingSignals = item.contributingSignals ?? [];
  const structuralExplanation = item.structuralExplanation ?? buildStructuralExplanation(item);

  return (
    <div className={`why-panel ${compact ? "why-panel--compact" : ""}`}>
      <div className="why-panel__summary">
        <div>
          <span className="section-token">Selected room</span>
          <h3>{item.label ?? item.shortTitle ?? item.title}</h3>
          <p>{item.decisionLabel ?? formatRoomDecisionState(item.tone)}. {item.window}</p>
        </div>
        <span className={`overview-pill overview-pill--${item.tone ?? "info"}`}>{item.primaryAction ?? item.recommendation}</span>
      </div>

      <div className="why-panel__section">
        <span className="section-token">Why it matters</span>
        <p className="why-panel__headline">{item.whyHeadline ?? item.summary ?? item.detail}</p>
      </div>

      <ProgressionStrip tone={item.tone ?? "info"} compact={compact} />

      {!compact && (
        <div className="why-panel__section structural-explanation">
          <span className="section-token">Structural explanation</span>
          {structuralExplanation.map((line) => (
            <p key={line}>{line}</p>
          ))}
        </div>
      )}

      {!compact && item.likelyDriver && (
        <div className="why-panel__section">
          <span className="section-token">Likely driver</span>
          <p>{item.likelyDriver}</p>
          {contributingSignals.length > 0 && (
            <div className="signal-chip-row">
              {contributingSignals.map((signal) => (
                <span className="signal-chip" key={signal}>{signal}</span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="why-panel__section">
        <span className="section-token">Confidence basis</span>
        <p>{formatConfidenceLabel(item.confidence)} confidence. {confidenceBasis}</p>
      </div>

      {!compact && (
        <div className="why-panel__chain">
          {supportingEvidence.map((driver) => (
            <div className="why-panel__driver" key={driver}>
              <StatusDot tone={item.tone ?? "info"} />
              <span>{driver}</span>
            </div>
          ))}
        </div>
      )}

      <div className="why-panel__recommendation">
        <span>Next move</span>
        <strong>{item.primaryAction ?? item.recommendation ?? "Continue monitoring"}</strong>
      </div>

      {!compact && (
        <div className="why-panel__baseline">
          <span className="section-token">Baseline</span>
          <p>{item.baselineContext ?? item.change ?? "Current room state remains inside the expected operating band."}</p>
        </div>
      )}
      {actionStatus && (
        <p className="why-panel__action-status">
          {actionStatus.action === "log"
            ? `Intervention logged at ${formatClockTime(actionStatus.at)} CT.`
            : "Pattern ignored for the current walkthrough."}
        </p>
      )}
    </div>
  );
}

function ProgressionStrip({ tone, compact = false }) {
  const stages = ["Stable", "Drift observed", "Decision window", "Intervention horizon"];
  const activeIndex = tone === "unstable" ? 3 : tone === "elevated" ? 2 : tone === "review" ? 1 : 0;

  return (
    <div className={`progression-strip ${compact ? "progression-strip--compact" : ""}`} aria-label="Room movement progression">
      {stages.map((stage, index) => (
        <div
          className={`progression-strip__stage ${index <= activeIndex ? "progression-strip__stage--active" : ""}`}
          key={stage}
        >
          <span />
          <strong>{stage}</strong>
        </div>
      ))}
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
    return <EmptyState title="No system map available" body="Awaiting active room monitoring." compact />;
  }

  return (
    <div className="topology-map">
      <div className="topology-map__hub">
        <span>Facility</span>
        <strong>Neraium room map</strong>
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
          emptyText="No grower checks were generated."
          title="Grower checks"
        />
      </div>
    </div>
  );
}

function FleetSummary({ summary }) {
  return (
    <div className="fleet-summary">
      <div className={`fleet-summary__hero fleet-summary__hero--${summary.tone}`}>
        <span className="section-token">Facility score</span>
        <strong>{summary.score}</strong>
        <p>{summary.summary}</p>
      </div>
      <div className="fleet-summary__grid">
        {summary.metrics.map((metric) => (
          <div className={`overview-summary-cell overview-summary-cell--${metric.tone}`} key={metric.label}>
            <div className="overview-summary-cell__header">
              <span>{metric.label}</span>
              <StatusDot tone={metric.tone} />
            </div>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function TargetSelector({ items, selectedId, onSelect }) {
  return (
    <div className="target-selector">
      {items.slice(0, 5).map((item) => (
        <button
          className={`target-selector__item target-selector__item--${item.tone} ${selectedId === item.id ? "target-selector__item--selected" : ""}`}
          key={item.id}
          type="button"
          onClick={() => onSelect(item.id)}
        >
          <div className="target-selector__header">
            <span>{item.label}</span>
            <StatusDot tone={item.tone} />
          </div>
          <strong>{item.window}</strong>
          <p>{item.recommendation}</p>
        </button>
      ))}
    </div>
  );
}

function ExecutiveBrief({ focus, report, observations, roomContext, facilityTone }) {
  if (!focus) {
    return <EmptyState title="No executive brief available" body="Monitoring active telemetry feed." />;
  }

  const briefPoints = report?.recommended_operator_checks?.slice(0, 3)
    ?? observations.slice(0, 3);

  return (
    <div className="panel-stack">
      <StatusBanner
        title={focus.title}
        subtitle={focus.whyHeadline ?? focus.summary}
        tone={focus.tone ?? facilityTone}
      />
      <MetricGrid
        metrics={[
          { label: "Time remaining", value: focus.window },
          { label: "Confidence", value: `${focus.confidence}%` },
          { label: "Primary room", value: roomContext.primary },
          { label: "Next move", value: focus.recommendation },
        ]}
        compact
      />
      <CompactList
        items={briefPoints}
        emptyText="No executive observations available."
        title="Executive takeaways"
      />
    </div>
  );
}

function TechnicalEvidencePanel({ evidenceLines, observations, report, timeline }) {
  return (
    <div className="technical-evidence">
      <details className="technical-evidence__section" open>
        <summary>Evidence terminal</summary>
        <EvidenceConsole lines={evidenceLines} />
      </details>
      <details className="technical-evidence__section">
        <summary>Room observations</summary>
        <CompactList items={observations} emptyText="No room observations available." />
      </details>
      <details className="technical-evidence__section">
        <summary>Timeline detail</summary>
        <TimelineFeed items={timeline.slice(0, 6)} />
      </details>
      <details className="technical-evidence__section">
        <summary>Report limitations</summary>
        <CompactList
          items={report?.limitations ?? REPORT_TEMPLATES}
          emptyText="No report limitations available."
        />
      </details>
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

function BackendErrorPanel({ message, isConfigWarning, onRetry }) {
  return (
    <section className={`backend-error-panel ${isConfigWarning ? "backend-error-panel--warning" : ""}`} aria-live="polite">
      <div>
        <span>{isConfigWarning ? "Configuration warning" : "Backend connection"}</span>
        <strong>{message}</strong>
      </div>
      <button className="command-button command-button--compact" type="button" onClick={onRetry}>
        Retry
      </button>
    </section>
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
      secondary: "Live telemetry feed active.",
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
      detail: `Live telemetry feed active. ${roomContext.primary} remains the primary review lane.`,
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
      title: "Facility sync delayed",
      detail: "Using the last confirmed state. Check facility WiFi if room changes stop syncing.",
      tone: "elevated",
    });
  }

  if (!result) {
    alerts.push({
      title: "Data source: Live telemetry feed",
      detail: "Manual upload is available if you want to validate a room export.",
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
      title: "Grower check",
      detail: check,
      tone: "review",
    });
  });

  return alerts.length > 0
    ? alerts
    : [
        {
          title: "No active grower alerts",
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
      label: "Data source",
      value: result ? latestManualSourceLabel(result) : "Live telemetry feed",
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
      "evidence.console=monitoring_sample_telemetry",
      "schema.mapping=no_facility_upload_connected",
      "grower.report=awaiting_room_exports",
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
    return "Elevated room trend requires review";
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
        detail: index === 2 ? `Baseline established for ${roomContext.primary}.` : "Live telemetry feed is active. Manual upload remains available.",
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
    return "Review needed";
  }
  return "Not ready";
}

function formatEngineResult(result) {
  if (result === "elevated") {
    return "Elevated";
  }
  if (result === "needs_review") {
    return "Review needed";
  }
  return "Normal";
}

function formatEndpoint(endpoint) {
  if (!endpoint) {
    return "API base URL missing";
  }
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
    ? `Updated ${formatClockTime(apiStatus.checkedAt)} CT`
    : "Sync initializing";
  const connectionStatusLine = apiStatus.state === "online"
    ? connectionSummary
    : `${connectionSummary}. Using last confirmed state.`;
  const connectionActionHint = apiStatus.state === "online"
    ? ""
    : "Check facility WiFi if room changes stop syncing.";

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
      heroHeadline: heroHeadlineFromTone(facilityTone),
      heroSubline: heroSublineFromTone(facilityTone, roomContext.primary),
      readinessLabel: formatReadiness(result?.data_quality?.readiness),
      connectionTone,
      connectionLabel: "Live telemetry feed",
      connectionDetail: apiStatus.detail,
      connectionSummary,
      connectionStatusLine,
      connectionActionHint,
      dataSourceLabel: latestManualSourceLabel(result),
      neraiumScore: calculateNeraiumScore(facilityTone, interventionItems, true),
      scoreNarrative: summarizeScoreNarrative(facilityTone, interventionItems),
      scoreContext: buildScoreContext(calculateNeraiumScore(facilityTone, interventionItems, true), facilityTone, interventionItems),
      windowContext: buildWindowContext(interventionItems[0], roomContext),
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
        "Review recommended for irrigation variance only where the room trend persists across the active window.",
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
      heroHeadline: heroHeadlineFromTone(facilityTone),
      heroSubline: heroSublineFromTone(facilityTone, primaryWindow?.label ?? roomStates[0]?.name ?? "the facility"),
      readinessLabel: "Monitoring active telemetry feed",
      connectionTone,
      connectionLabel: "Live telemetry feed",
      connectionDetail: apiStatus.state === "online"
        ? "Live telemetry feed active. Manual upload is available if you want to validate a room export."
        : "Using the last confirmed facility state until live sync resumes.",
      connectionSummary,
      connectionStatusLine,
      connectionActionHint,
      dataSourceLabel: "Live telemetry feed",
      neraiumScore: calculateNeraiumScore(facilityTone, interventionItems, false),
      scoreNarrative: summarizeScoreNarrative(facilityTone, interventionItems),
      scoreContext: buildScoreContext(calculateNeraiumScore(facilityTone, interventionItems, false), facilityTone, interventionItems),
      windowContext: buildWindowContext(interventionItems[0], roomContext),
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
      detail: `${room.cycle} | ${room.irrigationState} | room temperature ${room.hvacDrift.toFixed(2)}F off baseline.`,
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
  const attribution = result?.driver_attribution;
  const irrigationTone = result?.cultivation_mapping?.categories?.irrigation?.length ? "review" : "info";

  const items = [
    {
      id: "upload-hvac-balance",
      label: attribution?.room ?? roomContext.primary,
      title: `${attribution?.room ?? roomContext.primary} intervention window`,
      shortTitle: attribution?.room ?? roomContext.primary,
      status: "HVAC balance review",
      window: windowLabelFromTone(facilityTone),
      tone: attributionTone(attribution, facilityTone),
      confidence: confidenceFromAttribution(attribution, facilityTone),
      summary: attribution?.likely_driver
        ? `${attribution.likely_driver} is the likely driver based on available telemetry.`
        : engineSignals[0]?.message ?? "Uploaded telemetry indicates the current room should remain within an active review window.",
      detail: `Current upload places ${attribution?.room ?? roomContext.primary} in the primary review lane.`,
      shortDetail: attribution?.likely_driver
        ? `Likely driver: ${attribution.likely_driver}.`
        : engineSignals[0]?.message ?? "Current upload is tightening the review window.",
      whyHeadline: attribution?.supporting_evidence?.[0]
        ?? engineSignals[0]?.message
        ?? "Current room trend and readiness signals are tightening the available intervention window.",
      drivers: attribution?.supporting_evidence ?? buildWhyDrivers(result, telemetryCards, roomContext),
      driverAttribution: attribution,
      likelyDriver: attribution?.likely_driver,
      contributingSignals: attribution?.contributing_signals,
      confidenceBasis: attribution?.confidence_basis,
      supportingEvidence: attribution?.supporting_evidence,
      structuralExplanation: buildUploadedStructuralExplanation(attribution, engineSignals),
      decisionLabel: decisionLabelFromTone(facilityTone, 0),
      baselineContext: buildUploadBaselineContext(roomContext, facilityTone),
      recommendation: recommendationFromTone(facilityTone),
      primaryAction: attribution?.next_operator_move ?? primaryActionFromTone(facilityTone),
      actions: actionSetFromTone(facilityTone),
      impact: impactFromTone(facilityTone),
      change: "Updated from active upload",
      rankLabel: "Priority 01",
    },
    {
      id: "upload-irrigation-recovery",
      label: roomContext.secondary,
      title: `${roomContext.secondary} review horizon`,
      shortTitle: roomContext.secondary,
      status: "Irrigation recovery",
      window: windowLabelFromTone(irrigationTone),
      tone: irrigationTone,
      confidence: confidenceFromTone(irrigationTone, true),
      summary: columnReview[0]
        ? `${columnReview[0].column} requires review before the next irrigation cycle change.`
        : "Irrigation variance remains a secondary review lane until more room telemetry is uploaded.",
      detail: roomContext.irrigation,
      shortDetail: columnReview[0]
        ? `${columnReview[0].column} should be validated before the next cycle change.`
        : "Irrigation balance remains a scheduled review item.",
      whyHeadline: "Current irrigation behavior is not yet critical, but it is close enough to justify scheduled review.",
      drivers: [
        `Current irrigation context: ${roomContext.irrigation}.`,
        "Baseline established from current upload.",
        "Review is being prioritized over passive monitoring.",
      ],
      structuralExplanation: [
        "Irrigation response is being compared against recent room behavior.",
        "Cycle settling remains the current operating state.",
        "Room behavior is moving earlier than its recent baseline.",
      ],
      decisionLabel: "Validate irrigation balance",
      baselineContext: `${roomContext.secondary} typically holds a longer recovery window. Current irrigation recovery is shortening.`,
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
      shortTitle: "Facility telemetry",
      status: "Upload continuity",
      window: apiStatusWindow(result),
      tone: "info",
      confidence: 68,
      summary: "Uploaded telemetry is connected, but additional room context will improve intervention precision.",
      detail: result?.filename ?? "Live telemetry feed active",
      shortDetail: "Additional room coverage will improve decision confidence.",
      whyHeadline: "The facility is connected, but the confidence of longer-range decisions improves as room coverage deepens.",
      drivers: [
        `${result.row_count} rows and ${result.column_count} columns parsed in memory.`,
        `${result.cultivation_mapping?.mapped_column_count ?? 0} mapped columns currently in scope.`,
        "Awaiting additional room telemetry where facility context is partial.",
      ],
      structuralExplanation: [
        "Traceability is improving as room coverage deepens.",
        "Relationship evidence is limited until more facility telemetry is connected.",
        "Infrastructure movement remains under observation.",
      ],
      decisionLabel: "Continue monitoring",
      baselineContext: "Facility-level confidence improves as room coverage deepens and more week-specific context is connected.",
      recommendation: "Continue monitoring",
      primaryAction: "Acknowledge",
      actions: ["Acknowledge", "Schedule", "Escalate", "Ignore"],
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
      shortTitle: room.name,
      status: room.cycle,
      window: interventionWindowFromRoom(room),
      tone: room.tone,
      confidence: confidenceFromRoom(room),
      summary: `${room.irrigationState}. Room behavior is shortening against its recent baseline while room temperature response remains visible.`,
      detail: `${room.cycle} in ${room.zone}.`,
      shortDetail: compactRoomSummary(room),
      whyHeadline: whyHeadlineFromRoom(room),
      drivers: buildDriversFromRoom(room),
      structuralExplanation: buildStructuralExplanationFromRoom(room, index),
      baselineContext: baselineContextFromRoom(room),
      recommendation: recommendationFromTone(room.tone),
      primaryAction: primaryActionFromRoom(room, index),
      decisionLabel: decisionLabelFromTone(room.tone, index),
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
      targetId: item.id,
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
    return `${urgentCount} room window${urgentCount === 1 ? "" : "s"} shortened enough to warrant immediate grower attention.`;
  }
  return "Most rooms remain controllable, with review concentrated in a narrow set of rooms.";
}

function buildScoreContext(score, facilityTone, interventionItems) {
  const facilityAverage = facilityTone === "nominal" ? 74 : facilityTone === "review" ? 68 : facilityTone === "elevated" ? 62 : 58;
  const trendDelta = facilityTone === "nominal" ? 2 : facilityTone === "review" ? -1 : facilityTone === "elevated" ? -4 : -7;
  const trendArrow = trendDelta >= 0 ? "+" : "";
  return `Facility confidence ${facilityAverage} | Goal 80+ | Trend ${trendArrow}${trendDelta} pts since yesterday`;
}

function latestManualSourceLabel(result) {
  return result?.filename ? "Manual data upload connected" : "Live telemetry feed";
}

function baselineContextFromRoom(room) {
  if (room.cycle.toLowerCase().includes("week 7")) {
    return `${room.cultivar} ${room.cycle.toLowerCase()} typically holds 12 to 18 hours. This room is shortening.`;
  }
  if (room.cycle.toLowerCase().includes("week 5")) {
    return `${room.cultivar} ${room.cycle.toLowerCase()} typically stays inside a 4 to 6 day review window. This room is steady.`;
  }
  return `${room.cultivar} ${room.cycle.toLowerCase()} typically stabilizes after irrigation. This room is inside that band.`;
}

function buildUploadBaselineContext(roomContext, facilityTone) {
  if (facilityTone === "unstable" || facilityTone === "elevated") {
    return `${roomContext.primary} usually holds a longer intervention window at this stage. Current upload shows it shortening.`;
  }
  if (facilityTone === "review") {
    return `${roomContext.primary} is still inside a manageable week-level operating band, but the current window is getting tighter.`;
  }
  return `${roomContext.primary} remains inside its expected operating band for the current room cycle.`;
}

function buildWindowContext(item, roomContext) {
  if (!item) {
    return `Typical monitored rooms hold longer review windows once room context is established.`;
  }
  return item.baselineContext ?? `${roomContext.primary} is being compared against its expected room-cycle operating band.`;
}

function compactRoomSummary(room) {
  if (room.tone === "unstable") {
    return `${room.irrigationState}. Room behavior is shortening against its recent baseline.`;
  }
  if (room.tone === "elevated") {
    return `${room.irrigationState}. Humidity recovery is slowing relative to baseline.`;
  }
  if (room.tone === "review") {
    return `${room.irrigationState}. Monitor transition stability through the next room check.`;
  }
  return `${room.irrigationState}. The room remains inside a comfortable intervention horizon.`;
}

function buildFleetSummary(interventionItems, score, tone) {
  const unstable = interventionItems.filter((item) => item.tone === "unstable").length;
  const elevated = interventionItems.filter((item) => item.tone === "elevated").length;
  const review = interventionItems.filter((item) => item.tone === "review").length;

  return {
    score,
    tone,
    summary: unstable > 0
      ? `${unstable} room${unstable === 1 ? "" : "s"} need immediate attention right now.`
      : elevated > 0
        ? `${elevated} room${elevated === 1 ? "" : "s"} are shortening the current intervention horizon.`
        : "The facility remains inside a comfortable intervention horizon.",
    metrics: [
      { label: "Immediate", value: unstable || 0, tone: unstable > 0 ? "unstable" : "nominal" },
      { label: "Scheduled", value: elevated || 0, tone: elevated > 0 ? "elevated" : "nominal" },
      { label: "Review", value: review || 0, tone: review > 0 ? "review" : "nominal" },
      { label: "Rooms", value: interventionItems.length, tone: "info" },
    ],
  };
}

function buildWhyDrivers(result, telemetryCards, roomContext) {
  const firstCards = telemetryCards.slice(0, 2);
  return [
    firstCards[0] ? `${firstCards[0].label} currently reading ${firstCards[0].primary}.` : `Primary room context: ${roomContext.primary}.`,
    firstCards[1] ? `${firstCards[1].label} currently reading ${firstCards[1].primary}.` : `Secondary room context: ${roomContext.secondary}.`,
    result?.operator_report?.recommended_operator_checks?.[0] ?? "Recommended next move is based on the current room readiness and trend pattern.",
  ];
}

function interventionWindowFromRoom(room) {
  if (room.tone === "unstable") {
    return "8 hours";
  }
  if (room.tone === "elevated") {
    return "5 days";
  }
  if (room.tone === "review") {
    return "12 days";
  }
  return "5 weeks";
}

function whyHeadlineFromRoom(room) {
  if (room.tone === "unstable") {
    return `${room.name} has limited time before the room environment needs operator action.`;
  }
  if (room.tone === "elevated") {
    return `${room.name} is trending toward intervention as humidity recovery slows against baseline.`;
  }
  if (room.tone === "review") {
    return `${room.name} is still controllable, but the next decision window is now close enough to plan around.`;
  }
  return `${room.name} is healthy and currently operating with a comfortable intervention horizon.`;
}

function buildDriversFromRoom(room) {
  return [
    room.hvacDrift > 1.25
      ? `Room temperature response is ${room.hvacDrift.toFixed(2)}F off baseline and needs comparison against HVAC activity.`
      : "Room temperature response remains within expected behavior.",
    room.instability > 1.1
      ? `Humidity recovery is slowing relative to baseline, with stability reading ${room.instability.toFixed(2)}.`
      : "Environmental relationships remain stable.",
    `${room.irrigationState}. Cycle settling remains the current operating state.`,
  ];
}

function buildUploadedStructuralExplanation(attribution, engineSignals) {
  if (attribution?.driver_category === "humidity_control") {
    return [
      "Temperature recovery is decoupling from humidity stabilization.",
      "Relationship persistence observed across recent monitoring windows.",
      "Room behavior is moving earlier than its recent baseline.",
    ];
  }
  if (attribution?.driver_category === "sensor_network") {
    return [
      "Telemetry continuity is limiting structural confidence.",
      "Room relationships need cleaner source coverage before attribution tightens.",
      "Traceability is the next operating constraint.",
    ];
  }
  if (engineSignals?.length) {
    return [
      "Room behavior is moving against its recent baseline.",
      "Relationship evidence is being held as supporting context.",
      "Infrastructure does not fail suddenly. It moves.",
    ];
  }
  return [
    "Environmental relationships remain stable.",
    "Room behavior is staying within its recent baseline.",
    "Infrastructure does not fail suddenly. It moves.",
  ];
}

function buildStructuralExplanation(item) {
  if (item?.likelyDriver) {
    return [
      `${item.likelyDriver} is being treated as the likely driver to check first.`,
      item.confidenceBasis ?? "Supporting evidence is being compared across room signals.",
      "Infrastructure does not fail suddenly. It moves.",
    ];
  }
  if (item?.tone === "unstable") {
    return [
      "Temperature recovery is decoupling from humidity stabilization.",
      "Relationship persistence observed across 3 monitoring windows.",
      "Room behavior is moving earlier than its recent baseline.",
    ];
  }
  if (item?.tone === "elevated") {
    return [
      "Airflow response is lagging behind room temperature recovery.",
      "Relationship persistence observed across 2 monitoring windows.",
      "Room behavior is shortening against its recent baseline.",
    ];
  }
  if (item?.tone === "review") {
    return [
      "Drift is visible, but the room remains controllable.",
      "Transition stability should be watched through the next operating window.",
      "Environmental relationships remain mostly stable.",
    ];
  }
  return [
    "Room temperature response remains within expected behavior.",
    "Environmental relationships remain stable.",
    "Cycle settling remains the current operating state.",
  ];
}

function buildStructuralExplanationFromRoom(room, index = 0) {
  if (room.tone === "unstable") {
    return [
      "Temperature recovery is decoupling from humidity stabilization.",
      "Relationship persistence observed across 3 monitoring windows.",
      "Room behavior is moving earlier than its recent baseline.",
    ];
  }
  if (room.tone === "elevated") {
    return [
      index % 2 === 0
        ? "Airflow response is lagging behind room temperature recovery."
        : "Environmental coupling is shifting across the current room cycle.",
      "Relationship persistence observed across 2 monitoring windows.",
      "Room behavior is shortening against its recent baseline.",
    ];
  }
  if (room.tone === "review") {
    return [
      "Drift is visible, but the room remains controllable.",
      "Transition stability should be watched through the next operating window.",
      "Environmental relationships remain mostly stable.",
    ];
  }
  return [
    "Room temperature response remains within expected behavior.",
    "Environmental relationships remain stable.",
    "Cycle settling remains the current operating state.",
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

function confidenceFromAttribution(attribution, fallbackTone) {
  if (!attribution) {
    return confidenceFromTone(fallbackTone, true);
  }
  if (attribution.attribution_confidence === "high") {
    return 88;
  }
  if (attribution.attribution_confidence === "medium") {
    return 74;
  }
  return 58;
}

function attributionTone(attribution, fallbackTone) {
  if (!attribution) {
    return fallbackTone;
  }
  if (attribution.severity === "action") {
    return "unstable";
  }
  if (attribution.severity === "review") {
    return "review";
  }
  return "info";
}

function recommendationFromTone(tone) {
  if (tone === "unstable") {
    return "Act now";
  }
  if (tone === "elevated") {
    return "Schedule room review";
  }
  if (tone === "review") {
    return "Review room";
  }
  return "Room is fine";
}

function primaryActionFromTone(tone) {
  if (tone === "unstable") {
    return "Stabilize environment";
  }
  if (tone === "elevated") {
    return "Adjust before next cycle";
  }
  if (tone === "review") {
    return "Check room conditions";
  }
  return "Continue monitoring";
}

function primaryActionFromRoom(room, index = 0) {
  if (room.tone === "unstable") {
    return "Stabilize environment";
  }
  if (room.tone === "elevated") {
    return index % 2 === 0 ? "Investigate airflow response" : "Review environmental coupling";
  }
  if (room.tone === "review") {
    return index % 2 === 0 ? "Observe drift" : "Monitor transition stability";
  }
  if (room.irrigationState.toLowerCase().includes("feed")) {
    return "Validate irrigation balance";
  }
  return "Continue monitoring";
}

function decisionLabelFromTone(tone, index = 0) {
  if (tone === "unstable") {
    return "Decision window";
  }
  if (tone === "elevated") {
    return index % 2 === 0 ? "Airflow response" : "Coupling review";
  }
  if (tone === "review") {
    return index % 2 === 0 ? "Drift observed" : "Transition watch";
  }
  return "Stable";
}

function actionSetFromTone(tone) {
  const actions = ["Acknowledge", "Schedule", "Escalate", "Ignore"];
  if (tone === "unstable") {
    return ["Escalate", "Schedule", "Acknowledge", "Ignore"];
  }
  return actions;
}

function impactFromTone(tone) {
  if (tone === "unstable") {
    return "High crop impact";
  }
  if (tone === "elevated") {
    return "Material crop impact";
  }
  if (tone === "review") {
    return "Moderate crop impact";
  }
  return "Low crop impact";
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

function heroHeadlineFromTone(tone) {
  if (tone === "unstable") {
    return "Immediate intervention planning is required.";
  }
  if (tone === "elevated") {
    return "Intervention windows are tightening.";
  }
  if (tone === "review") {
    return "Facility health remains controlled.";
  }
  return "The facility is operating with time to spare.";
}

function heroSublineFromTone(tone, focusLabel) {
  if (tone === "unstable") {
    return `${focusLabel} is now inside an immediate decision window, but the rest of the facility remains visible and controllable.`;
  }
  if (tone === "elevated") {
    return `${focusLabel} is shortening the current intervention horizon, giving growers time to act before the room becomes disruptive.`;
  }
  if (tone === "review") {
    return `${focusLabel} needs planned attention, while the broader facility stays inside a manageable operating envelope.`;
  }
  return "Current telemetry indicates a comfortable intervention horizon across the monitored facility.";
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
      primary: `${maxDrift.toFixed(2)}F off baseline`,
      secondary: `${unstableRooms} room${unstableRooms === 1 ? "" : "s"} under review`,
      series: roomStates.map((room) => room.hvacDrift * 10),
      tone: maxDrift > 1.7 ? "unstable" : maxDrift > 1.25 ? "elevated" : "review",
    },
    {
      label: "Airflow",
      primary: `${cycleValue(94, tick, 5, 0).toFixed(0)}% equipment activity`,
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
  const time = new Date(Date.now() - tick * OPERATIONAL_CADENCE_MS);
  return [
    {
      time: formatClockTime(time),
      title: "Environmental transition detected",
      detail: `${roomStates[1].name} humidity recovery slowed after irrigation cycle handoff.`,
      tone: roomStates[1].tone,
    },
    {
      time: formatClockTime(new Date(time.getTime() + 5 * 60000)),
      title: "Room climate review opened",
      detail: `${roomStates[0].name} supply temperature moved ${roomStates[0].hvacDrift.toFixed(2)}F off baseline.`,
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
      title: "Grower review notice",
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
      title: "Live telemetry feed active",
      detail: "Using the last confirmed facility state while live sync resumes.",
      tone: "info",
    });
  }
  alertRooms.slice(0, 2).forEach((room) => {
    items.push({
      title: `${room.name} requires review`,
      detail: `${room.irrigationState}. Room temperature is ${room.hvacDrift.toFixed(2)}F off baseline with climate stability at ${room.instability.toFixed(2)}.`,
      tone: room.tone,
    });
  });
  items.push({
    title: "Monitoring active telemetry feed",
    detail: "Sample telemetry will remain active until uploaded facility exports replace the current surface.",
    tone: "info",
  });
  return items.slice(0, 4);
}

function buildSimulatedFindings(roomStates) {
  return roomStates.flatMap((room) => ([
    {
      title: `${room.name} telemetry review`,
      detail: `${room.cycle} with ${room.irrigationState.toLowerCase()} and room temperature ${room.hvacDrift.toFixed(2)}F off baseline.`,
      tone: room.tone,
    },
    {
      title: `${room.name} evidence event`,
      detail: `Climate stability ${room.instability.toFixed(2)} recorded against current room baseline.`,
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
      direction: room.hvacDrift > 1.1 ? "temperature rising" : "stable recovery",
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
      change: roomStates[0].hvacDrift > 1.4 ? "Supply temperature elevated" : "Supply tracking nominal",
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
      detail: "Live telemetry feed is active and maintaining current workspace state.",
      state: "standby",
      tone: "info",
    },
    {
      title: "Header and schema detection",
      detail: `Last sync checked ${formatClockTime(apiStatus.checkedAt ?? new Date())} CT.`,
      state: "monitoring",
      tone: apiStatus.state === "online" ? "nominal" : "review",
    },
    {
      title: "Timestamp and room context review",
      detail: `Baseline room context held on ${roomContext.primary} while telemetry feed advances through live sample cadence ${tick}.`,
      state: "active",
      tone: "info",
    },
    {
      title: "Baseline and evidence extraction",
      detail: "Awaiting uploaded room exports to replace simulated evidence and room trend relationships.",
      state: "standby",
      tone: "review",
    },
  ];
}

function buildSimulatedEvidenceLines(roomStates, tick, apiStatus) {
  return [
    `console.mode=frontend_simulation`,
    `connection.state=${apiStatus.state}`,
    `connection.last_check=${formatClockTime(apiStatus.checkedAt ?? new Date())}`,
    `room.primary=${roomStates[0].name}`,
    `room.transition=${roomStates[1].name}:humidity_recovery_review`,
    `room.temperature_review=${roomStates[0].hvacDrift.toFixed(2)}F_off_baseline`,
    `irrigation.state=${roomStates[0].irrigationState.replace(/ /g, "_").toLowerCase()}`,
    `evidence.sequence=${tick}`,
    `grower.notice=review_recommended_for_irrigation_variance`,
  ];
}

function buildSimulatedConsoleEvents(roomStates, tick, apiStatus) {
  return [
    `telemetry.link=${apiStatus.state}`,
    `telemetry.sequence=${tick}`,
    `event.room_transition=${roomStates[1].name.replace(/ /g, "_").toLowerCase()}`,
    `event.room_temperature_delta=${roomStates[0].hvacDrift.toFixed(2)}`,
    `event.climate_stability=${roomStates[1].instability.toFixed(2)}`,
    `event.irrigation_cycle=${roomStates[0].irrigationState.replace(/ /g, "_").toLowerCase()}`,
    `event.review_notice=grower_review_open`,
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
      title: apiStatus.state === "online" ? "Live telemetry current" : "Sync delayed",
      detail: apiStatus.state === "online"
        ? `Last sync ${formatClockTime(checkedAt)} CT.`
        : `Last confirmed state held from ${formatClockTime(checkedAt)} CT.`,
      tone: apiStatus.state === "online" ? "nominal" : "elevated",
    },
    {
      title: apiStatus.state === "online" ? "Telemetry monitor" : "Grower action",
      detail: apiStatus.state === "online"
        ? "Live telemetry feed is current."
        : "Check facility WiFi if room changes stop syncing.",
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

function formatFacilityPlainState(tone, primaryRoom) {
  if (tone === "unstable") {
    return `${primaryRoom?.label ?? "One room"} needs action`;
  }
  if (tone === "elevated" || tone === "review") {
    return `${primaryRoom?.label ?? "One room"} has drift observed`;
  }
  return "Facility is stable";
}

function formatScoreReadiness(score) {
  if (score >= 86) {
    return "Operating readiness is strong.";
  }
  if (score >= 72) {
    return "Operating readiness is good, with one room to watch.";
  }
  if (score >= 58) {
    return "Operating readiness is tightening.";
  }
  return "Operating readiness needs attention.";
}

function formatRoomDecisionState(tone, index = 0) {
  if (tone === "unstable") {
    return "Decision window";
  }
  if (tone === "elevated" || tone === "review") {
    return decisionLabelFromTone(tone, index);
  }
  return "Fine";
}

function formatConfidenceLabel(score) {
  if ((score ?? 0) >= 82) {
    return "High";
  }
  if ((score ?? 0) >= 68) {
    return "Medium";
  }
  return "Developing";
}

function buildConfidenceBasis(item, findings) {
  const drivers = item?.drivers ?? findings.map((entry) => entry.detail).slice(0, 3);
  if (drivers.length >= 2) {
    return `Based on ${drivers[0].toLowerCase()} and ${drivers[1].toLowerCase()}.`;
  }
  if (drivers.length === 1) {
    return `Based on ${drivers[0].toLowerCase()}.`;
  }
  return "Based on current room climate trend, sync recency, and baseline behavior.";
}

function average(values) {
  return values.reduce((sum, value) => sum + value, 0) / Math.max(values.length, 1);
}

function formatColumnsRequiringReview(columnsRequiringReview) {
  return columnsRequiringReview.map((item) => `${item.column}: ${item.reasons.join(" ")}`);
}

export default App;
