import { Component, useCallback, useEffect, useRef, useState } from "react";
import {
 API_BASE_URL,
 apiFetch,
 API_CONFIG_WARNING,
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
    id: "data-connections",
    label: "Data Connections",
    eyebrow: "Connectors",
    description: "Upload telemetry, check connection health, and review the latest ingestion state.",
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
  "SII engine processing",
  "Evidence and state write",
  "Complete",
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
const OPERATIONAL_CADENCE_MS = 30000;

function App() {
  const hasAccess = true;
  const apiAccessCode = "";
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
  const [facilityIntelligence, setFacilityIntelligence] = useState(null);
  const [intelligenceStatus, setIntelligenceStatus] = useState(buildEmptyIntelligenceStatus());
  const [engineIdentity, setEngineIdentity] = useState(null);
  const [backendError, setBackendError] = useState(API_CONFIG_WARNING);
  const [latestUploadResult, setLatestUploadResult] = useState(null);
  const [latestUploadSnapshot, setLatestUploadSnapshot] = useState(buildEmptyLatestUploadSnapshot());
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
      const response = await apiFetch("/api/health", { accessCode: apiAccessCode });
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
  }, [apiAccessCode, hasAccess]);

  const loadFacilitySystems = useCallback(async () => {
    if (!hasAccess) {
      return false;
    }

    try {
      const response = await apiFetch("/api/facility/systems", { accessCode: apiAccessCode });
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          throw new Error(await buildProtectedRequestMessage(response));
        }
        throw new Error(`Unexpected response: ${response.status}`);
      }

      const payload = await response.json();
      if (Array.isArray(payload.systems)) {
        setSystems(payload.systems);
        setFacilityIntelligence(payload.intelligence ? normalizeFacilityIntelligence(payload.intelligence) : null);
        setIntelligenceStatus(payload.intelligence_status ?? buildEmptyIntelligenceStatus());
        setSystemsState("ready");
        setBackendError(API_CONFIG_WARNING);
        return true;
      }
      throw new Error("Facility systems payload was incomplete.");
    } catch (error) {
      setSystems(FALLBACK_SYSTEMS);
      setFacilityIntelligence(null);
      setIntelligenceStatus(buildEmptyIntelligenceStatus());
      setSystemsState("fallback");
      setBackendError(normalizeErrorMessage(error?.message ?? error) || "Backend connection unavailable. System data could not be loaded.");
      return false;
    }
  }, [apiAccessCode, hasAccess]);

  const loadEngineIdentity = useCallback(async () => {
    if (!hasAccess) {
      return false;
    }

    try {
      const response = await apiFetch("/api/intelligence/engine-identity", { accessCode: apiAccessCode });
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          throw new Error(await buildProtectedRequestMessage(response));
        }
        throw new Error(`Unexpected response: ${response.status}`);
      }

      setEngineIdentity(await response.json());
      return true;
    } catch (error) {
      setEngineIdentity(null);
      if (normalizeErrorMessage(error?.message ?? error) === "Session expired. Refresh workspace.") {
        setBackendError("Session expired. Refresh workspace.");
      }
      return false;
    }
  }, [apiAccessCode, hasAccess]);

  const loadLatestUploadState = useCallback(async () => {
    if (!hasAccess) {
      return false;
    }

    try {
      const response = await apiFetch("/api/data/latest-upload", { accessCode: apiAccessCode });
      if (!response.ok) {
        throw new Error(`Unexpected response: ${response.status}`);
      }

      const payload = await response.json();
      setLatestUploadSnapshot(payload ?? buildEmptyLatestUploadSnapshot());
      const latestResult = payload?.latest_result;
      if (hasFullUploadResult(latestResult)) {
        setLatestUploadResult(latestResult);
        return true;
      }
      setLatestUploadResult(null);
      return false;
    } catch {
      setLatestUploadSnapshot(buildEmptyLatestUploadSnapshot());
      setLatestUploadResult(null);
      return false;
    }
  }, [apiAccessCode, hasAccess]);

  const retryBackendConnection = useCallback(async () => {
    const isHealthy = await checkApiHealth("retry");
    if (isHealthy) {
      await loadFacilitySystems();
      await loadEngineIdentity();
    }
  }, [checkApiHealth, loadEngineIdentity, loadFacilitySystems]);

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
    loadEngineIdentity();
    loadLatestUploadState();
  }, [hasAccess, loadEngineIdentity, loadFacilitySystems, loadLatestUploadState]);

  const activeConfig = WORKSPACES.find((workspace) => workspace.id === activeWorkspace) ?? WORKSPACES[0];
  const roomContext = deriveRoomContext(latestUploadResult);
  const timeCoverage = deriveTimeCoverage(latestUploadResult);
  const liveOps = buildOperationalContext({
    result: latestUploadResult,
    latestUploadSnapshot,
    apiStatus,
    roomContext,
    systems,
    systemsState,
    facilityIntelligence,
    intelligenceStatus,
    tick: telemetryTick,
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
        />
      );
    }

    if (activeWorkspace === "data-connections") {
      return (
        <DataConnectionsWorkspace
          accessCode={apiAccessCode}
          apiStatus={apiStatus}
          latestUploadSnapshot={latestUploadSnapshot}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          liveOps={liveOps}
          onUploadComplete={async () => {
            await loadLatestUploadState();
            await loadFacilitySystems();
            await loadEngineIdentity();
          }}
        />
      );
    }

    return (
      <IntelligenceConsoleWorkspace
        latestUploadResult={latestUploadResult}
        apiStatus={apiStatus}
        roomContext={roomContext}
        liveOps={liveOps}
        engineIdentity={engineIdentity}
        intelligenceStatus={intelligenceStatus}
      />
    );
  }

  return (
    <AppErrorBoundary>
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

        {backendError && (
          <BackendErrorPanel
            message={normalizeErrorMessage(backendError)}
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
          onSelectWorkspace={handleWorkspaceSelect}
        />
      </aside>
    </main>
    </AppErrorBoundary>
  );
}

class AppErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error) {
    console.error("Neraium UI recovered from render error", error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="access-shell">
          <section className="access-panel" aria-labelledby="recovery-title">
            <div className="access-brand">
              <div className="brand-mark">N</div>
              <span>System recovery</span>
            </div>
            <div className="access-copy">
              <p className="eyebrow">Neraium</p>
              <h1 id="recovery-title">System view is recovering.</h1>
              <p>Backend processing is still available. Refresh the page to reload the latest stable state.</p>
            </div>
            <button className="command-button" type="button" onClick={() => window.location.reload()}>
              Refresh view
            </button>
          </section>
        </main>
      );
    }
    return this.props.children;
  }
}

function WorkspaceNavigationContent({
  activeWorkspace,
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
  const intelligenceLabel = formatIntelligenceSourceLabel(liveOps.intelligenceMode);
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
          <span className={`sii-source-chip sii-source-chip--${liveOps.intelligenceMode}`}>
            {intelligenceLabel}
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
          label="Readiness"
          value={latestUploadResult?.data_quality ? formatReadiness(latestUploadResult.data_quality?.readiness) : liveOps.readinessLabel}
          tone={latestUploadResult?.data_quality?.readiness ?? liveOps.facilityTone}
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
  const primaryGuidance = buildGuidanceForItem(primaryRoom);
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
            <div className="operator-guidance-brief">
              <p><b>Primary driver:</b> {primaryGuidance.primaryDriver}</p>
              <p><b>Why Neraium flagged this:</b> {primaryGuidance.whyFlagged}</p>
              <ul>
                {primaryGuidance.whatToCheck.slice(0, 3).map((check) => (
                  <li key={check}>{check}</li>
                ))}
              </ul>
            </div>
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
          onOperatorAction={onOperatorAction}
          compact
        />

        <div className="room-first-actions">
          <button className="secondary-command-button" type="button" onClick={() => onNavigateWorkspace("facility-systems")}>
            Open system detail
          </button>
          <button className="secondary-command-button" type="button" onClick={() => onNavigateWorkspace("intelligence-console")}>
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
}) {
  const telemetryCards = liveOps.telemetryCards;
  const driftRows = liveOps.driftRows;
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
        title="Room drivers"
        subtitle="Climate, irrigation, and cycle signals affecting the current window."
        className="span-8"
      >
        <TelemetryCardGrid cards={telemetryCards.slice(0, 6)} />
      </Panel>

      <Panel
        title="Room trend by channel"
        subtitle="Baseline movement by grow-room significance."
        className="span-6"
      >
        <DriftMonitor rows={driftRows} />
      </Panel>

      <Panel
        title="Irrigation context"
        subtitle="Cycle state and grower review notes."
        className="span-6"
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

function DataConnectionsWorkspace({
  accessCode,
  apiStatus,
  latestUploadSnapshot,
  latestUploadResult,
  roomContext,
  liveOps,
  onUploadComplete,
}) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadState, setUploadState] = useState("idle");
  const [uploadError, setUploadError] = useState("");
  const [uploadResult, setUploadResult] = useState(latestUploadResult);
  const [uploadJob, setUploadJob] = useState(null);
  const uploadJobIdRef = useRef(null);
  const pollTimerRef = useRef(null);
  const pollFailureCountRef = useRef(0);
  const [connectorTypes, setConnectorTypes] = useState([]);
  const [connectorHealth, setConnectorHealth] = useState([]);
  const [connectorError, setConnectorError] = useState("");
  const [restForm, setRestForm] = useState({
    source_id: "customer-rest",
    system_id: "facility-rest",
    endpoint: "",
    method: "GET",
    token: "",
    records_path: "",
  });
  const [restResult, setRestResult] = useState(null);
  const [restBusy, setRestBusy] = useState("");

  const loadConnectorData = useCallback(async () => {
    try {
      const [typesResponse, healthResponse] = await Promise.all([
        apiFetch("/api/connectors/types", { accessCode }),
        apiFetch("/api/connectors/health", { accessCode }),
      ]);
      const [typesPayload, healthPayload] = await Promise.all([
        readJsonPayload(typesResponse),
        readJsonPayload(healthResponse),
      ]);
      if (!typesResponse.ok) {
        throw new Error(typesPayload?.detail ?? `Unexpected response: ${typesResponse.status}`);
      }
      if (!healthResponse.ok) {
        throw new Error(healthPayload?.detail ?? `Unexpected response: ${healthResponse.status}`);
      }
      setConnectorTypes(typesPayload?.types ?? []);
      setConnectorHealth(healthPayload?.connectors ?? []);
      setConnectorError("");
    } catch (error) {
      setConnectorError(normalizeErrorMessage(error?.message ?? error));
    }
  }, [accessCode]);

  useEffect(() => () => {
    if (pollTimerRef.current) {
      window.clearTimeout(pollTimerRef.current);
    }
  }, []);

  useEffect(() => {
    setUploadResult(latestUploadResult);
  }, [latestUploadResult]);

  useEffect(() => {
    loadConnectorData();
  }, [loadConnectorData]);

  async function handleUpload(event) {
    event.preventDefault();
    if (!selectedFile) {
      setUploadError("Choose a CSV telemetry file to upload.");
      return;
    }

    const formData = new FormData();
    formData.append("file", selectedFile);

    setUploadState("uploading");
    setUploadError("");
    setUploadJob(null);
    uploadJobIdRef.current = null;
    pollFailureCountRef.current = 0;

    try {
      const response = await apiFetch("/api/data/upload", {
        accessCode,
        method: "POST",
        body: formData,
      });
      const payload = await readJsonPayload(response);

      if (!response.ok) {
        throw buildUploadRequestError(response, payload, "upload");
      }

      if (!payload?.job_id) {
        throw buildUploadRequestError(response, { ...payload, error_type: "upload_session_missing", message: "Upload state unavailable." }, "upload");
      }

      uploadJobIdRef.current = payload.job_id;
      setUploadJob(payload);
      setUploadState(normalizeUploadStatus(payload.status));
      pollUploadStatus(payload.job_id);
    } catch (error) {
      const classified = classifyUploadError(error, "upload");
      setUploadError(classified.message);
      setUploadState(classified.state);
      console.warn(
        "telemetry_upload_failure",
        `message=${classified.message}`,
        `status=${classified.status ?? "n/a"}`,
        `error_type=${classified.errorType ?? "n/a"}`,
      );
    }
  }

  async function pollUploadStatus(jobId) {
    const pollingJobId = jobId || uploadJobIdRef.current;
    if (!pollingJobId) {
      setUploadError("Upload state unavailable.");
      setUploadState("error");
      return;
    }

    try {
      const response = await apiFetch(`/api/data/upload-status/${pollingJobId}`, { accessCode });
      const payload = await readJsonPayload(response);

      if (!response.ok) {
        throw buildUploadRequestError(response, payload, "poll");
      }

      pollFailureCountRef.current = 0;
      uploadJobIdRef.current = payload.job_id ?? pollingJobId;
      setUploadJob(payload);
      const nextStatus = normalizeUploadStatus(payload.status);
      setUploadState(nextStatus);
      if (isUploadProcessing(nextStatus)) {
        setUploadError("");
      }

      if (nextStatus === "complete") {
        const latestResponse = await apiFetch("/api/data/latest-upload", { accessCode });
        const latestPayload = latestResponse.ok ? await readJsonPayload(latestResponse) : payload.result_summary;
        const latestResult = latestPayload?.latest_result;
        const completedPayload = {
          ...(hasFullUploadResult(latestResult) ? latestResult : {}),
          ...(latestPayload ?? {}),
          filename: latestPayload?.last_filename ?? payload.filename,
          row_count: latestPayload?.rows_processed ?? payload.rows_processed,
          column_count: latestPayload?.columns_detected ?? payload.columns_detected,
          job_status: payload,
        };
        setUploadResult(completedPayload);
        await onUploadComplete(completedPayload);
        await loadConnectorData();
        return;
      }

      if (nextStatus === "failed") {
        setUploadError(operatorUploadMessage({
          status: response.status,
          errorType: payload.error_type ?? "sii_processing_failure",
          detail: payload.error,
          phase: "poll",
        }));
        return;
      }

      pollTimerRef.current = window.setTimeout(() => pollUploadStatus(pollingJobId), 2000);
    } catch (error) {
      const classified = classifyUploadError(error, "poll");
      console.warn("telemetry_polling_failure", { ...classified, jobId: pollingJobId, attempts: pollFailureCountRef.current + 1 });
      if (classified.retryable && pollFailureCountRef.current < 30) {
        pollFailureCountRef.current += 1;
        setUploadState((current) => isUploadProcessing(current) ? current : "running_sii");
        setUploadError(classified.message);
        pollTimerRef.current = window.setTimeout(
          () => pollUploadStatus(pollingJobId),
          Math.min(2000 + pollFailureCountRef.current * 1500, 12000),
        );
        return;
      }
      setUploadError(classified.finalMessage ?? classified.message);
      setUploadState(classified.retryable ? "error" : classified.state);
    }
  }

  async function handleRestAction(mode) {
    setRestBusy(mode);
    setConnectorError("");
    const payload = {
      ...restForm,
      records_path: restForm.records_path.trim() || null,
      token: restForm.token.trim() || null,
    };
    try {
      const response = await apiFetch(mode === "test" ? "/api/connectors/rest/test" : "/api/connectors/rest/ingest", {
        accessCode,
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await readJsonPayload(response);
      if (!response.ok) {
        throw new Error(result?.detail ?? result?.message ?? `Unexpected response: ${response.status}`);
      }
      setRestResult(result);
      await loadConnectorData();
    } catch (error) {
      setConnectorError(normalizeErrorMessage(error?.message ?? error));
    } finally {
      setRestBusy("");
    }
  }

  const healthyCount = connectorHealth.filter((item) => item.connection_status === "ready").length;
  const totalSensors = connectorHealth.reduce((sum, item) => sum + (item.sensors_detected ?? 0), 0);
  const totalRecords = connectorHealth.reduce((sum, item) => sum + (item.records_ingested ?? 0), 0);
  const intakeStages = uploadJob
    ? buildIntakeStages(uploadResult, uploadState, roomContext, uploadJob)
    : uploadResult
      ? buildIntakeStages(uploadResult, uploadState, roomContext, null)
      : buildConnectionStateStages({ latestUploadSnapshot, uploadState, uploadError, roomContext });
  const latestStatus = latestUploadSnapshot?.status ?? "empty";
  const latestMessage = normalizeErrorMessage(
    uploadError
      || uploadJob?.error
      || uploadJob?.message
      || uploadJob?.progress_label
      || latestUploadSnapshot?.message
      || uploadStateMessage(uploadState),
  );

  return (
    <div className="workspace-grid workspace-grid--connections">
      <Panel
        title="Data Connections"
        subtitle="Upload facility telemetry and keep ingestion status visible."
        className="span-7"
      >
        <form className="intake-flow" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <p className="section-token">Telemetry upload</p>
            <h3>Upload Telemetry File</h3>
            <p>
              Upload a production CSV export to refresh Neraium score, operating state, room context,
              drift evidence, and timestamps across the workspace.
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
            <button className="command-button" type="submit" disabled={isUploadProcessing(uploadState)}>
              {isUploadProcessing(uploadState) ? "Upload processing" : "Upload Telemetry File"}
            </button>
          </div>

          <div className="intake-flow__status">
            <span>{selectedFile ? selectedFile.name : (latestUploadSnapshot?.last_filename ?? "No data connected yet")}</span>
            <span className="intake-flow__progress">
              {isUploadProcessing(uploadState) && <span className="upload-spinner" aria-hidden="true" />}
              {latestMessage}
            </span>
          </div>

          {uploadError && <p className="form-error">{normalizeErrorMessage(uploadError)}</p>}
        </form>
      </Panel>

      <Panel
        title="Ingestion State"
        subtitle="Visible upload lifecycle and latest active result."
        className="span-5"
      >
        <WorkflowStages items={intakeStages} />
      </Panel>

      <Panel
        title="Latest Sync"
        subtitle="Current upload status, backend connectivity, and active result source."
        className="span-12"
      >
        <MetricGrid
          metrics={[
            { label: "State", value: connectionStateLabel(latestStatus, uploadState, uploadError) },
            { label: "Backend/API", value: apiStatus.label },
            { label: "Latest sync", value: latestUploadSnapshot?.last_processed_at ? formatClockTime(latestUploadSnapshot.last_processed_at) : "No data connected yet" },
            { label: "Result source", value: latestUploadSnapshot?.result_source ? "File upload" : "Awaiting upload" },
            { label: "File", value: latestUploadSnapshot?.last_filename ?? uploadJob?.filename ?? "Awaiting upload" },
            { label: "Rows", value: latestUploadSnapshot?.rows_processed ?? uploadJob?.rows_processed ?? "Pending" },
            { label: "Columns", value: latestUploadSnapshot?.columns_detected ?? uploadJob?.columns_detected ?? "Pending" },
            { label: "Primary room", value: roomContext.primary },
          ]}
        />
      </Panel>

      <Panel
        title="Connector command"
        subtitle="Customer telemetry ingestion status across file, API, and industrial connector lanes."
        className="span-12"
      >
        <MetricGrid
          metrics={[
            { label: "Connector types", value: connectorTypes.length || "Pending" },
            { label: "Ready connectors", value: healthyCount },
            { label: "Sensors detected", value: totalSensors || "Pending" },
            { label: "Records ingested", value: totalRecords || "Pending" },
          ]}
        />
      </Panel>

      <Panel
        title="Connector registry"
        subtitle="Operational status, sync posture, and validation surface for each integration type."
        className="span-7"
      >
        <div className="connector-status-list">
          {connectorHealth.map((connector) => (
            <div className="connector-status-card" key={connector.connector_type}>
              <div className="connector-status-card__header">
                <div>
                  <p className="section-token">{connector.connector_type}</p>
                  <h3>{connector.display_name}</h3>
                </div>
                <span className={`connector-status-pill connector-status-pill--${connectorStatusTone(connector.connection_status)}`}>
                  {formatConnectorStatus(connector.connection_status)}
                </span>
              </div>
              <MetricGrid
                metrics={[
                  { label: "Last sync", value: connector.last_sync_time ? formatClockTime(connector.last_sync_time) : "Awaiting sync" },
                  { label: "Sensors", value: connector.sensors_detected ?? 0 },
                  { label: "Records", value: connector.records_ingested ?? 0 },
                  { label: "Mode", value: connector.functional ? "Functional" : "Scaffolded" },
                ]}
                compact
              />
              {connector.masked_configuration && Object.keys(connector.masked_configuration).length > 0 && (
                <div className="connector-detail-list">
                  {Object.entries(connector.masked_configuration).map(([key, value]) => (
                    <div className="connector-detail-row" key={key}>
                      <span>{key}</span>
                      <strong>{typeof value === "object" ? JSON.stringify(value) : String(value)}</strong>
                    </div>
                  ))}
                </div>
              )}
              {(connector.warnings?.length > 0 || connector.errors?.length > 0) && (
                <div className="connector-issues">
                  {[...(connector.warnings ?? []), ...(connector.errors ?? [])].slice(0, 4).map((item) => (
                    <p key={item}>{item}</p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Panel>

      <Panel
        title="Upload result"
        subtitle="The latest completed upload that is driving the dashboard."
        className="span-5"
      >
        <MetricGrid
          metrics={[
            { label: "Neraium score", value: latestUploadResult?.sii_intelligence?.neraium_score ?? "No active result" },
            { label: "Operating state", value: latestUploadResult?.sii_intelligence?.facility_state ?? "No active result" },
            { label: "Drift status", value: latestUploadResult?.sii_intelligence?.urgency ?? "No active result" },
            { label: "Timestamp coverage", value: deriveTimeCoverage(latestUploadResult).summary },
          ]}
          compact
        />
        <CompactList
          items={latestUploadResult?.sii_intelligence?.supporting_evidence ?? [latestUploadSnapshot?.message ?? "No data connected yet."]}
          emptyText="No data connected yet."
        />
      </Panel>

      <Panel
        title="REST connector"
        subtitle="Validate remote telemetry APIs, mask secrets, and normalize JSON payloads."
        className="span-12"
      >
        <form className="connector-rest-grid" onSubmit={(event) => event.preventDefault()}>
          <label>
            <span>Endpoint</span>
            <input
              type="url"
              value={restForm.endpoint}
              onChange={(event) => setRestForm((current) => ({ ...current, endpoint: event.target.value }))}
              placeholder="https://customer.example.com/telemetry"
            />
          </label>
          <label>
            <span>HTTP method</span>
            <select
              value={restForm.method}
              onChange={(event) => setRestForm((current) => ({ ...current, method: event.target.value }))}
            >
              <option value="GET">GET</option>
              <option value="POST">POST</option>
            </select>
          </label>
          <label>
            <span>Source ID</span>
            <input
              type="text"
              value={restForm.source_id}
              onChange={(event) => setRestForm((current) => ({ ...current, source_id: event.target.value }))}
            />
          </label>
          <label>
            <span>System ID</span>
            <input
              type="text"
              value={restForm.system_id}
              onChange={(event) => setRestForm((current) => ({ ...current, system_id: event.target.value }))}
            />
          </label>
          <label>
            <span>Token</span>
            <input
              type="password"
              value={restForm.token}
              onChange={(event) => setRestForm((current) => ({ ...current, token: event.target.value }))}
              placeholder="Bearer token"
            />
          </label>
          <label>
            <span>Records path</span>
            <input
              type="text"
              value={restForm.records_path}
              onChange={(event) => setRestForm((current) => ({ ...current, records_path: event.target.value }))}
              placeholder="data.records"
            />
          </label>
          <div className="connector-form__actions">
            <button className="secondary-command-button" type="button" disabled={restBusy === "test"} onClick={() => handleRestAction("test")}>
              {restBusy === "test" ? "Testing" : "Test connection"}
            </button>
            <button className="command-button" type="button" disabled={restBusy === "ingest"} onClick={() => handleRestAction("ingest")}>
              {restBusy === "ingest" ? "Ingesting" : "Ingest connector data"}
            </button>
          </div>
        </form>

        <div className="connector-rest-output">
          <MetricGrid
            metrics={[
              { label: "Connection", value: restResult?.connection_status ? formatConnectorStatus(restResult.connection_status) : "Awaiting validation" },
              { label: "Sensors", value: restResult?.sensors_detected ?? "Pending" },
              { label: "Records", value: restResult?.records_ingested ?? "Pending" },
              { label: "Last sync", value: restResult?.last_sync_time ? formatClockTime(restResult.last_sync_time) : "Awaiting validation" },
            ]}
            compact
          />
          {restResult?.masked_configuration && (
            <div className="connector-detail-list">
              {Object.entries(restResult.masked_configuration).map(([key, value]) => (
                <div className="connector-detail-row" key={key}>
                  <span>{key}</span>
                  <strong>{typeof value === "object" ? JSON.stringify(value) : String(value)}</strong>
                </div>
              ))}
            </div>
          )}
          {restResult?.warnings?.length > 0 && (
            <div className="connector-issues">
              {restResult.warnings.slice(0, 4).map((warning) => <p key={warning}>{warning}</p>)}
            </div>
          )}
        </div>
      </Panel>

      {connectorError && (
        <Panel
          title="Connector response"
          subtitle="Operator-friendly validation feedback."
          className="span-12"
        >
          <p className="form-error">{connectorError}</p>
        </Panel>
      )}
    </div>
  );
}

function IntelligenceConsoleWorkspace({
  latestUploadResult,
  liveOps,
  engineIdentity,
  intelligenceStatus,
}) {
  const driftRows = liveOps.driftRows;
  const relationshipRows = liveOps.relationshipRows;
  const timeline = liveOps.timeline;

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel
        title="Room trend feed"
        subtitle="Changes shortening the current window."
        className="span-4"
      >
        <DriftFeed rows={driftRows} />
      </Panel>

      <Panel
        title="Relationship shifts"
        subtitle="Paired changes affecting confidence."
        className="span-4"
      >
        <RelationshipMonitor rows={relationshipRows} />
      </Panel>

      <Panel
        title="Recent changes"
        subtitle="Events that changed decision timing."
        className="span-4"
      >
        <TimelineFeed items={timeline} />
      </Panel>

      <Panel
        title="Engine identity"
        subtitle="Production SII pipeline provenance."
        className="span-12"
      >
        <EngineIdentityPanel
          identity={engineIdentity}
          latestUploadResult={latestUploadResult}
          intelligenceStatus={intelligenceStatus}
        />
      </Panel>
    </div>
  );
}

function EngineIdentityPanel({ identity, latestUploadResult, intelligenceStatus }) {
  const trace = latestUploadResult?.processing_trace ?? null;
  const runnerResult = latestUploadResult?.sii_runner_result ?? null;
  const version = identity?.engine_version ?? trace?.engine_version ?? "Awaiting backend identity";
  const modulePath = identity?.production_runner ?? identity?.engine_module ?? runnerResult?.runner_module ?? "Awaiting backend identity";
  const source = intelligenceStatus?.source ?? "none";
  const lastProcessed = intelligenceStatus?.last_processed_at ?? "Awaiting upload";
  const runnerAvailable = identity?.runner_available ?? runnerResult?.runner_used ?? false;

  return (
    <details className="engine-identity-panel">
      <summary>
        <span>
          <strong>{identity?.engine_name ?? "Neraium SII"}</strong>
          <small>{runnerAvailable ? "Production SII runner available" : "Production SII runner pending"}</small>
        </span>
        <span>{source}</span>
      </summary>
      <MetricGrid
        metrics={[
          { label: "Engine version", value: version },
          { label: "Core engine", value: identity?.core_engine ?? runnerResult?.core_engine ?? "SIIEngine" },
          { label: "Production runner", value: modulePath },
          { label: "Source", value: source },
          { label: "Last processed", value: lastProcessed },
          {
            label: "Validation family",
            value: identity?.same_engine_family_as_validation ? "Yes" : "Pending",
          },
        ]}
      />
      <div className="evidence-console evidence-console--static">
        {(runnerResult ? runnerTraceLines(runnerResult) : trace ? processingTraceLines(trace) : ["processing_trace=awaiting_upload"]).map((line) => (
          <div className="evidence-console__line" key={line}>{line}</div>
        ))}
      </div>
    </details>
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
          {Array.isArray(card.technicalDetails) && card.technicalDetails.length > 0 && (
            <details className="technical-detail-panel technical-detail-panel--card">
              <summary>View evidence</summary>
              <div className="technical-detail-panel__lines">
                {card.technicalDetails.slice(0, 5).map((line, index) => (
                  <code key={`${line}-${index}`}>{line}</code>
                ))}
              </div>
            </details>
          )}
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
    return <EmptyState title="No consistency shifts" body="Awaiting paired room telemetry." compact />;
  }

  return (
    <div className="relationship-list">
      {rows.map((row, index) => {
        const columns = row.columns ?? [];
        return (
          <div className="relationship-row" key={`${columns.join("-")}-${index}`}>
            <div className="relationship-row__header">
              <span>{formatRelationshipPair(columns, index)}</span>
              <StatusDot tone={row.tone ?? "info"} />
            </div>
            <strong>{relationshipDetail(row)}</strong>
            <p>{relationshipConsistencyLabel(row)}</p>
            {Array.isArray(row.technicalDetails) && row.technicalDetails.length > 0 && (
              <details className="technical-detail-panel technical-detail-panel--compact">
                <summary>Technical detail</summary>
                <div className="technical-detail-panel__lines">
                  {row.technicalDetails.slice(0, 4).map((line, detailIndex) => (
                    <code key={`${line}-${detailIndex}`}>{line}</code>
                  ))}
                </div>
              </details>
            )}
          </div>
        );
      })}
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
    systemsState === "ready" ? "Live facility sync" : "Backend connection unavailable",
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
      {items.slice(0, limit).map((item, index) => {
        const guidance = buildGuidanceForItem(item);
        return (
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
            <p>{compact ? item.primaryAction ?? item.recommendation : guidance.primaryDriver}</p>
            {!compact && (
              <div className="intervention-card__footer">
                <span className={`overview-pill overview-pill--${item.tone}`}>{item.primaryAction ?? item.recommendation}</span>
              </div>
            )}
          </button>
        );
      })}
    </div>
  );
}

function ActionQueue({ items, selectedId, onSelect }) {
  if (!items || items.length === 0) {
    return <EmptyState title="No queued actions" body="Current rooms remain within monitored thresholds." compact />;
  }

  return (
    <div className="action-queue">
      {items.slice(0, 5).map((item) => {
        const guidance = buildGuidanceForItem(item);
        return (
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
          <p>{item.primaryAction ?? item.recommendation}</p>
          <p className="action-queue__driver">{guidance.primaryDriver}</p>
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
        );
      })}
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
                <span className={`overview-pill overview-pill--${item.tone}`}>{item.primaryAction ?? item.recommendation}</span>
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
  onOperatorAction,
  compact = false,
}) {
  if (!item) {
    return <EmptyState title="No active explanation" body="Monitoring active telemetry feed." compact />;
  }

  const confidenceBasis = item.confidenceBasis ?? buildConfidenceBasis(item, findings);
  const supportingEvidence = Array.isArray(item.supportingEvidence)
    ? item.supportingEvidence
    : Array.isArray(item.drivers)
      ? item.drivers
      : (findings ?? []).map((entry) => entry.detail).filter(Boolean).slice(0, 3);
  const contributingSignals = item.contributingSignals ?? [];
  const structuralExplanation = Array.isArray(item.structuralExplanation) && item.structuralExplanation.length > 0
    ? item.structuralExplanation
    : buildStructuralExplanation(item);
  const guidance = buildGuidanceForItem(item);
  const technicalDetails = Array.isArray(item.technicalDetails) ? item.technicalDetails : [];

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

      <div className="why-panel__section guidance-driver">
        <span className="section-token">Primary driver</span>
        <p>{guidance.primaryDriver}</p>
      </div>

      <div className="why-panel__section guidance-flag">
        <span className="section-token">Why Neraium flagged this</span>
        <p>{guidance.whyFlagged}</p>
      </div>

      {compact ? (
        <ProgressionStrip tone={item.tone ?? "info"} compact />
      ) : (
        <div className="why-panel__section observed-progression">
          <span className="section-token">Observed progression</span>
          <ProgressionStrip tone={item.tone ?? "info"} detailed />
        </div>
      )}

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

      <div className="why-panel__section guidance-checks">
        <span className="section-token">What to check</span>
        <ul>
          {(guidance.whatToCheck ?? ["Continue monitoring"]).slice(0, compact ? 3 : 4).map((check) => (
            <li key={check}>{check}</li>
          ))}
        </ul>
      </div>

      {technicalDetails.length > 0 && (
        <details className="technical-detail-panel">
          <summary>Technical detail</summary>
          <div className="technical-detail-panel__lines">
            {technicalDetails.slice(0, compact ? 5 : 10).map((line, index) => (
              <code key={`${line}-${index}`}>{line}</code>
            ))}
          </div>
        </details>
      )}

      {onOperatorAction && (
        <OperatorActionControls
          actionStatus={actionStatus}
          targetId={item.targetId ?? item.id}
          onOperatorAction={onOperatorAction}
        />
      )}

      {!compact && (
        <div className="why-panel__baseline">
          <span className="section-token">Baseline</span>
          <p>{item.baselineContext ?? item.change ?? "Current room state remains inside the expected operating band."}</p>
        </div>
      )}
      {actionStatus && !onOperatorAction && (
        <p className="why-panel__action-status">
          {actionStatus.action === "log"
            ? `Intervention logged at ${formatClockTime(actionStatus.at)} CT.`
            : "Pattern ignored for the current walkthrough."}
        </p>
      )}
    </div>
  );
}

function OperatorActionControls({ actionStatus, targetId, onOperatorAction }) {
  const actions = [
    { id: "acknowledge", label: "Acknowledge" },
    { id: "review", label: "Under review" },
    { id: "taken", label: "Action taken" },
  ];

  return (
    <div className="operator-action-controls" aria-label="Operator action status">
      {actions.map((action) => (
        <button
          className={`operator-action-button ${actionStatus?.action === action.id ? "operator-action-button--active" : ""}`}
          key={action.id}
          type="button"
          onClick={() => onOperatorAction(targetId, action.id)}
        >
          {action.label}
        </button>
      ))}
      {actionStatus && (
        <p className="operator-action-status">
          {formatOperatorActionLabel(actionStatus.action)} at {formatClockTime(actionStatus.at)} CT.
        </p>
      )}
    </div>
  );
}

function ProgressionStrip({ tone, compact = false, detailed = false }) {
  const stages = detailed
    ? [
        "Stable environmental recovery",
        "Early airflow inconsistency",
        "Slower humidity stabilization",
        "Compressed intervention horizon",
      ]
    : ["Stable recovery", "Airflow watch", "Humidity recovery", "Window tightening"];
  const activeIndex = tone === "unstable" ? 3 : tone === "elevated" ? 2 : tone === "review" ? 1 : 0;

  return (
    <div
      className={`progression-strip ${compact ? "progression-strip--compact" : ""} ${detailed ? "progression-strip--detailed" : ""}`}
      aria-label="Room movement progression"
    >
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
          <p>{item.primaryAction ?? item.recommendation}</p>
          <p className="target-selector__driver">{buildGuidanceForItem(item).primaryDriver}</p>
        </button>
      ))}
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
  const safeMessage = normalizeErrorMessage(message);
  return (
    <section className={`backend-error-panel ${isConfigWarning ? "backend-error-panel--warning" : ""}`} aria-live="polite">
      <div>
        <span>{isConfigWarning ? "Configuration warning" : "Backend connection"}</span>
        <strong>{safeMessage}</strong>
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

  if (!hasFullUploadResult(result)) {
    items.push({
      time: "Standby",
      title: "Telemetry batch processing",
      detail: `SII processing is active. ${roomContext.primary} remains on the last confirmed state until the runner writes new findings.`,
      tone: "info",
    });
    items.push({
      time: "Standby",
      title: "Awaiting completed runner output",
      detail: "Facility Command will update after the completed SII state is available.",
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
    detail: formatReadiness(result.data_quality?.readiness),
    tone: mapOperationalTone(result.data_quality?.readiness),
  });
  items.push({
    time: "Review",
    title: "Mapping coverage",
    detail: `${result.cultivation_mapping?.mapped_column_count ?? 0} mapped columns across cultivation systems.`,
    tone: (result.cultivation_mapping?.mapped_column_count ?? 0) > 0 ? "nominal" : "info",
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
      label: "Uploaded rooms",
      value: result?.room_summary?.room_count ?? result?.sii_intelligence?.rooms?.length ?? "Live",
    },
    {
      label: "Systems in scope",
      value: systemsState === "ready" ? `${systems.length} live` : `${systems.length} placeholder`,
    },
  ];
}

function buildZoneSummary(roomContext) {
  const uploadedRooms = Array.isArray(roomContext.uploadedRooms) ? roomContext.uploadedRooms : [];
  if (uploadedRooms.length > 0) {
    return uploadedRooms.slice(0, 8).map((room, index) => ({
      label: index === 0 ? "Primary room" : `Uploaded room ${index + 1}`,
      value: room,
      detail: `${uploadedRooms.length} room${uploadedRooms.length === 1 ? "" : "s"} detected in the latest upload.`,
      tone: index === 0 ? "nominal" : "info",
    }));
  }
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
  if (!hasFullUploadResult(result)) {
    return [
      "evidence.console=telemetry_processing",
      "schema.mapping=awaiting_completed_runner_output",
      "grower.report=last_confirmed_state_preserved",
    ];
  }

  const lines = [
    `batch.file=${result.filename}`,
    `data.readiness=${result.data_quality?.readiness ?? "processing"}`,
    `rows=${result.row_count}`,
    `columns=${result.column_count}`,
    `mapping.coverage=${result.cultivation_mapping?.coverage_percent ?? 0}%`,
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

  if (hasFullUploadResult(result)) {
    lines.push(`console.batch=${result.filename}`);
    lines.push(`console.readiness=${result.data_quality?.readiness ?? "processing"}`);
    (result.engine_result?.signals ?? []).slice(0, 6).forEach((signal) => {
      lines.push(`signal.event=${signal.message}`);
    });
  } else {
    lines.push("console.batch=telemetry_processing");
  }

  return [...lines, ...buildEvidenceConsole(result).slice(0, 10)];
}

function buildRelationshipRows(result) {
  const evidence = result?.engine_result?.evidence ?? [];
  return evidence
    .filter((item) => item.type === "relationship_change")
    .map((item) => ({
      ...item,
      detail: translateEvidenceLine(relationshipDetail(item), inferOperationalCategory(item.columns?.join(" "), item.detail)),
      tone: mapOperationalTone(item.level ?? "review"),
      technicalDetails: [
        item.detail && `detail=${item.detail}`,
        item.baseline_correlation !== undefined && `baseline_correlation=${item.baseline_correlation}`,
        item.recent_correlation !== undefined && `recent_correlation=${item.recent_correlation}`,
        item.columns && `columns=${item.columns.join(",")}`,
      ].filter(Boolean),
    }));
}

function formatRelationshipPair(columns = [], index = 0) {
  const labels = columns.map(displayFieldName).filter(Boolean);
  if (labels.length >= 2) {
    return `${labels[0]} and ${labels[1]}`;
  }
  if (labels.length === 1) {
    return labels[0];
  }
  return `Environmental coupling ${index + 1}`;
}

function relationshipDetail(row) {
  if (row.detail) {
    return polishEvidenceLanguage(row.detail);
  }
  const labels = (row.columns ?? []).map((column) => displayFieldName(column).toLowerCase());
  const joined = labels.join(" ");
  if (joined.includes("intervention window")) {
    return "Intervention windows are shortening as environmental recovery slows.";
  }
  if (joined.includes("humidity") && (joined.includes("airflow") || joined.includes("air movement"))) {
    return "Airflow response consistency weakened during active climate periods.";
  }
  if (joined.includes("humidity")) {
    return "Humidity recovery is becoming less stable after environmental transitions.";
  }
  if (joined.includes("airflow") || joined.includes("air movement")) {
    return "Air movement behavior is diverging from this room's recent operating pattern.";
  }
  return "Environmental coupling is less consistent than the room's recent baseline.";
}

function relationshipConsistencyLabel(row) {
  const baseline = row.baseline_correlation ?? row.baselineConsistency;
  const recent = row.recent_correlation ?? row.activeConsistency;
  if (baseline === undefined || recent === undefined) {
    return "Relationship consistency is being compared against recent room behavior.";
  }
  return `Relationship consistency moved from ${baseline} baseline to ${recent} active.`;
}

function displayFieldName(field) {
  const normalized = String(field ?? "")
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();
  const aliases = {
    intervention_window_hours: "intervention window",
    "intervention window hours": "intervention window",
    airflow: "airflow",
    hvac_runtime: "HVAC runtime",
    co2: "CO2",
    recent_baseline: "recent baseline",
  };
  if (aliases[normalized]) {
    return aliases[normalized];
  }
  return normalized.replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function polishEvidenceLanguage(text) {
  return String(text ?? "")
    .replace(/relationship strength/gi, "relationship consistency")
    .replace(/intervention_window_hours/gi, "intervention window")
    .replace(/changed with room conditions/gi, "became less consistent during changing room conditions")
    .replace(/relationship changed compared to baseline/gi, "relationship consistency became less consistent than the room's recent baseline")
    .replace(/changed relationship strength between the baseline and recent windows/gi, "showed less consistent recovery between the baseline and active windows");
}

function isTechnicalEvidenceText(value) {
  const text = String(value ?? "").toLowerCase();
  return [
    "siiengineadapter",
    "unified sii",
    "sii core",
    "structural_drift",
    "structural drift score",
    "relational_stability",
    "transition_pressure",
    "instability score",
    "telemetry history depth",
    "numeric telemetry channels",
    "covariance",
    "adapter",
    "core engine",
    "baseline_window",
    "recent_window",
  ].some((pattern) => text.includes(pattern));
}

function humanizeDriverCategory(value) {
  const normalized = String(value ?? "")
    .replace(/[^a-z0-9]+/gi, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  const labels = {
    airflow_restriction: "Airflow restriction",
    airflow_response: "Airflow restriction",
    humidity_control: "Humidity recovery instability",
    humidity_coupling_shift: "Humidity recovery instability",
    humidity_recovery: "Humidity recovery instability",
    hvac_instability: "Temperature recovery instability",
    thermal_consistency: "Temperature recovery instability",
    irrigation_timing: "Irrigation timing shift",
    irrigation_balance: "Irrigation recovery shift",
    lighting_schedule: "Lighting schedule influence",
    sensor_network: "Telemetry continuity gap",
    telemetry_continuity: "Telemetry continuity gap",
    environmental_coupling: "Environmental coupling shift",
    room_pressure: "Room pressure imbalance",
    unknown_system_drift: "Environmental behavior shift",
  };
  if (labels[normalized]) {
    return labels[normalized];
  }
  return String(value ?? "Environmental behavior shift")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function inferOperationalCategory(...values) {
  const text = values.filter(Boolean).join(" ").toLowerCase();
  if (text.includes("airflow") || text.includes("air movement") || text.includes("pressure") || text.includes("fan") || text.includes("vent")) {
    return "airflow_restriction";
  }
  if (text.includes("humid") || text.includes("moisture") || text.includes("dehumid")) {
    return "humidity_coupling_shift";
  }
  if (text.includes("temperature") || text.includes("thermal") || text.includes("hvac")) {
    return "hvac_instability";
  }
  if (text.includes("irrigation") || text.includes("feed") || text.includes("substrate")) {
    return "irrigation_timing";
  }
  if (text.includes("sensor") || text.includes("telemetry") || text.includes("coverage")) {
    return "sensor_network";
  }
  return "environmental_coupling";
}

function translateEvidenceLine(value, fallbackCategory = "environmental_coupling") {
  const text = String(value ?? "").trim();
  if (!text) {
    return "Evidence is still being assembled from room telemetry.";
  }
  const category = inferOperationalCategory(fallbackCategory, text);
  const lower = text.toLowerCase();
  if (lower.includes("siiengineadapter") && lower.includes("numeric telemetry channels")) {
    return "Telemetry coverage is sufficient to compare room behavior against recent operating patterns.";
  }
  if (lower.includes("unified sii core") || lower.includes("regime") || lower.includes("urgency")) {
    return "Environmental behavior is moving away from recent baseline patterns.";
  }
  if (lower.includes("instability score") || lower.includes("structural drift")) {
    return "Instability and structural drift are visible enough to guide inspection.";
  }
  if (lower.includes("confidence") && lower.includes("telemetry history depth")) {
    return "The available history is strong enough to support an operator review.";
  }
  if (lower.includes("latest structural drift")) {
    return "Structural drift is visible against the recent baseline.";
  }
  if (lower.includes("transition pressure")) {
    return "The room is moving through a transition with less recovery margin than normal.";
  }
  if (lower.includes("environmental coupling")) {
    return "Environmental recovery behavior is no longer stabilizing at its normal rate.";
  }
  if (lower.includes("baseline")) {
    return polishEvidenceLanguage(text);
  }
  return buildGuidanceFromCategory(category).whyFlagged;
}

function buildOperationalTranslation({
  driver,
  driverCategory,
  why,
  evidence = [],
  relationships = [],
  confidenceBasis,
  baselineContext,
  urgency,
  window,
}) {
  const category = driverCategory ?? inferOperationalCategory(driver, why, evidence.join(" "), relationships.join(" "));
  const baseGuidance = buildGuidanceFromCategory(
    category === "airflow_restriction" ? "airflow_response"
      : category === "humidity_coupling_shift" ? "humidity_recovery"
        : category === "hvac_instability" ? "thermal_consistency"
          : category === "irrigation_timing" ? "irrigation_balance"
            : category === "sensor_network" ? "telemetry_continuity"
              : "environmental_coupling",
  );
  const technicalDetails = [
    driver && `primary_driver=${driver}`,
    driverCategory && `driver_category=${driverCategory}`,
    why && `why_flagged=${why}`,
    confidenceBasis && `confidence_basis=${confidenceBasis}`,
    baselineContext && `baseline_context=${baselineContext}`,
    urgency && `urgency=${urgency}`,
    window && `intervention_window=${window}`,
    ...evidence.map((line, index) => `supporting_evidence_${index + 1}=${line}`),
    ...relationships.map((line, index) => `relationship_evidence_${index + 1}=${line}`),
  ].filter(Boolean);
  const operatorEvidence = evidence
    .filter(Boolean)
    .map((line) => translateEvidenceLine(line, category))
    .filter((line, index, list) => list.indexOf(line) === index);
  const operatorRelationships = relationships
    .filter(Boolean)
    .map((line) => translateEvidenceLine(line, category))
    .filter((line, index, list) => list.indexOf(line) === index);

  return {
    category,
    primaryDriver: humanizeDriverCategory(category),
    whyFlagged: isTechnicalEvidenceText(why)
      ? translateEvidenceLine(why, category)
      : (why || baseGuidance.whyFlagged),
    nextMove: baseGuidance.nextMove,
    whatToCheck: baseGuidance.whatToCheck,
    confidenceBasis: isTechnicalEvidenceText(confidenceBasis)
      ? "Telemetry evidence is strong enough to prioritize an operator inspection."
      : (confidenceBasis || "Evidence is being compared against recent room behavior."),
    baselineContext: isTechnicalEvidenceText(baselineContext)
      ? "Current room behavior is moving away from recent operating patterns."
      : (baselineContext || "Current room behavior is being compared against recent baseline patterns."),
    supportingEvidence: operatorEvidence.length > 0
      ? operatorEvidence
      : [baseGuidance.whyFlagged],
    relationshipEvidence: operatorRelationships.length > 0
      ? operatorRelationships
      : ["Airflow-to-humidity coupling is being compared against recent baseline behavior."],
    technicalDetails,
  };
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
  if (!result || !Array.isArray(result.columns)) {
    const summaryRooms = extractRoomSummaryNames(result);
    if (summaryRooms.length > 0) {
      return {
        primary: summaryRooms[0],
        secondary: summaryRooms[1] ?? `${summaryRooms.length} uploaded rooms`,
        cycle: "Mixed uploaded rooms",
        irrigation: "Irrigation context pending",
        uploadedRooms: summaryRooms,
        roomCount: summaryRooms.length,
      };
    }
    return {
      primary: "No data connected yet",
      secondary: "Upload a telemetry file to activate room context",
      cycle: "Cycle metadata unavailable",
      irrigation: "Irrigation context unavailable",
      uploadedRooms: [],
      roomCount: 0,
    };
  }

  const summaryRooms = extractRoomSummaryNames(result);
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
  const uploadedRooms = summaryRooms.length > 0 ? summaryRooms : uniqueValues(roomValues);

  return {
    primary: uploadedRooms[0] ?? "Room context not present in upload",
    secondary: uploadedRooms[1] ?? (uploadedRooms.length > 1 ? `${uploadedRooms.length} uploaded rooms` : "Awaiting additional room telemetry"),
    cycle: cycleValues[0] ?? "Cycle metadata unavailable",
    irrigation: irrigationMapped > 0 ? "Irrigation channels mapped" : "Awaiting irrigation telemetry",
    uploadedRooms,
    roomCount: uploadedRooms.length,
  };
}

function extractRoomSummaryNames(result) {
  const rooms = result?.room_summary?.rooms;
  if (!Array.isArray(rooms)) {
    return [];
  }
  return uniqueValues(rooms.map((room) => room?.room).filter(Boolean));
}

function uniqueValues(values) {
  return [...new Set(values.map((value) => String(value).trim()).filter(Boolean))];
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

function hasFullUploadResult(result) {
  return Boolean(result?.data_quality && result?.engine_result && result?.cultivation_mapping);
}

function buildEmptyLatestUploadSnapshot() {
  return {
    status: "empty",
    source: "none",
    message: "No data connected yet.",
    last_filename: null,
    rows_processed: 0,
    columns_detected: 0,
    last_processed_at: null,
    runner_module: null,
    core_engine: null,
    state_available: false,
    connection_status: "no_data",
    result_source: null,
    latest_result: null,
  };
}

function buildEmptyIntelligenceStatus() {
  return {
    engine_loaded: true,
    source: "none",
    last_processed_at: null,
    active_rooms_count: 0,
    evidence_fields_present: [],
    mode: "empty",
    status: "no_data",
  };
}

function normalizeFacilityIntelligence(intelligence) {
  const safe = {
    source: "processing",
    mode: "processing",
    facility_state: "Processing",
    room_state: "Processing",
    urgency: "review",
    intervention_window: "Processing",
    neraium_score: null,
    primary_room: "Processing uploaded telemetry",
    priority_room: null,
    primary_driver: "SII engine is analyzing uploaded telemetry",
    supporting_evidence: ["Telemetry batch processing is underway."],
    relationship_evidence: [],
    structural_explanation: ["Awaiting completed runner output."],
    confidence_basis: "Awaiting completed runner output",
    recommended_operator_review: "Processing uploaded telemetry",
    next_operator_move: "Processing uploaded telemetry",
    what_to_check: ["Wait for SII processing to complete"],
    why_flagged: "Telemetry batch processing",
    baseline_comparison: "Awaiting completed runner output",
    observed_persistence: "Awaiting completed runner output",
    last_updated: new Date().toISOString(),
    rooms: [],
  };
  if (!intelligence || typeof intelligence !== "object") {
    return safe;
  }
  const rooms = Array.isArray(intelligence.rooms) ? intelligence.rooms : [];
  return {
    ...safe,
    ...intelligence,
    rooms,
    source: intelligence.source ?? safe.source,
    mode: intelligence.mode ?? safe.mode,
    facility_state: intelligence.facility_state ?? safe.facility_state,
    primary_driver: intelligence.primary_driver ?? safe.primary_driver,
    supporting_evidence: Array.isArray(intelligence.supporting_evidence) ? intelligence.supporting_evidence : safe.supporting_evidence,
    relationship_evidence: Array.isArray(intelligence.relationship_evidence) ? intelligence.relationship_evidence : safe.relationship_evidence,
    structural_explanation: Array.isArray(intelligence.structural_explanation) ? intelligence.structural_explanation : safe.structural_explanation,
    what_to_check: Array.isArray(intelligence.what_to_check) ? intelligence.what_to_check : safe.what_to_check,
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

function buildIntakeStages(result, uploadState, roomContext, job = null) {
  const activeIndex = uploadStageIndex(uploadState);
  return INTAKE_STAGES.map((stage, index) => {
    if (job || [...["failed"], ...["uploading", "queued", "parsing", "baseline_modeling", "running_sii", "writing_state"]].includes(normalizeUploadStatus(uploadState))) {
      const normalizedStatus = normalizeUploadStatus(uploadState);
      return {
        title: stage,
        detail: uploadStageDetail(stage, index, job, roomContext),
        state: normalizedStatus === "failed"
          ? index <= activeIndex ? "failed" : "queued"
          : index < activeIndex ? "complete" : index === activeIndex ? "active" : "queued",
        tone: normalizedStatus === "failed" && index <= activeIndex ? "unstable" : index <= activeIndex ? "info" : "review",
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
      `${result.filename ?? result.last_filename ?? "Telemetry batch"} received for processing.`,
      `${result.columns?.length ?? result.columns_detected ?? result.column_count ?? 0} headers detected across the uploaded batch.`,
      `Room context resolved as ${roomContext.primary}.`,
      "SII engine processing complete.",
      "Evidence and facility state were written.",
      "Facility Command refreshed from latest uploaded state.",
    ];

    return {
      title: stage,
      detail: details[index],
      state: "complete",
      tone: index === 3 && !result.engine_result ? "review" : "nominal",
    };
  });
}

function uploadStageIndex(uploadState) {
  return {
    uploading: 0,
    queued: 0,
    parsing: 1,
    baseline_modeling: 2,
    running_sii: 3,
    writing_state: 4,
    complete: 5,
    failed: 4,
  }[uploadState] ?? 0;
}

function uploadStageDetail(stage, index, job, roomContext) {
  const jobStatus = normalizeUploadStatus(job?.status);
  if (jobStatus === "failed" && index === uploadStageIndex("failed")) {
    return job.error ?? "Telemetry processing failed.";
  }
  if (jobStatus === "complete") {
    return index === 5
      ? "Facility Command is using the latest uploaded runner state."
      : "Stage complete.";
  }
  const details = [
    job?.message ?? "Telemetry batch received.",
    jobStatus === "parsing" ? job.progress_label : "Waiting for header and schema detection.",
    jobStatus === "baseline_modeling" ? job.progress_label : `Room context will resolve against ${roomContext.primary}.`,
    jobStatus === "running_sii" ? job.progress_label : "Telemetry processing will continue after baseline modeling.",
    jobStatus === "writing_state" ? job.progress_label : "Facility state will be written after telemetry processing.",
    "Completion will refresh Facility Command.",
  ];
  return details[index] ?? stage;
}

function normalizeUploadStatus(status) {
  const normalized = String(status ?? "").toLowerCase();
  const aliases = {
    pending: "queued",
    queued: "queued",
    parsing: "parsing",
    baseline_modeling: "baseline_modeling",
    running_sii: "running_sii",
    generating_evidence: "writing_state",
    writing_state: "writing_state",
    complete: "complete",
    failed: "failed",
    not_found: "error",
  };
  return aliases[normalized] ?? normalized;
}

function isUploadProcessing(status) {
  return ["uploading", "queued", "parsing", "baseline_modeling", "running_sii", "writing_state"].includes(normalizeUploadStatus(status));
}

async function readJsonPayload(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

async function buildProtectedRequestMessage(response) {
  const payload = await readJsonPayload(response);
  return normalizeErrorMessage(payload?.message ?? payload?.error) || "Session expired. Refresh workspace.";
}

function normalizeErrorMessage(error) {
  if (!error) {
    return "Unknown error";
  }
  if (typeof error === "string") {
    return error;
  }
  if (error.message) {
    return normalizeErrorMessage(error.message);
  }
  if (error.detail) {
    return normalizeErrorMessage(error.detail);
  }
  if (typeof error === "object") {
    return JSON.stringify(error);
  }
  return "Unexpected processing error";
}

function buildUploadRequestError(response, payload, phase) {
  const errorType = payload?.error_type ?? payload?.detail?.error_type ?? null;
  const isMissingStatusDuringPoll = phase === "poll" && response.status === 404 && errorType === "upload_session_missing";
  return {
    name: "UploadRequestError",
    status: response.status,
    phase,
    errorType,
    detail: normalizeErrorMessage(payload?.message ?? payload?.detail?.message ?? payload?.detail ?? payload?.error ?? ""),
    retryable: response.status === 408 || response.status === 409 || response.status === 425 || response.status === 429 || response.status >= 500 || (phase === "poll" && (response.status === 401 || response.status === 403)) || isMissingStatusDuringPoll,
  };
}

function classifyUploadError(error, phase) {
  if (error?.name === "UploadRequestError") {
    const isAuthDuringPolling = phase === "poll" && (error.status === 401 || error.status === 403);
    const isMissingStatusDuringPoll = phase === "poll" && error.status === 404 && error.errorType === "upload_session_missing";
    return {
      state: isAuthDuringPolling || isMissingStatusDuringPoll || (phase === "poll" && error.retryable) ? "running_sii" : "error",
      retryable: phase === "poll" && error.retryable,
      status: error.status,
      errorType: error.errorType,
      finalMessage: isMissingStatusDuringPoll
        ? "Upload status unavailable. The backend may have restarted or another ECS task may be serving polling."
        : null,
      message: operatorUploadMessage({
        status: error.status,
        errorType: error.errorType,
        detail: error.detail,
        phase,
      }),
    };
  }
  if (error instanceof TypeError) {
    return {
      state: phase === "poll" ? "running_sii" : "error",
      retryable: phase === "poll",
      status: null,
      errorType: "network",
      message: phase === "poll"
        ? "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time."
        : "Secure telemetry ingestion unavailable.",
    };
  }
  return {
    state: "error",
    retryable: false,
    status: null,
    errorType: null,
    message: operatorUploadMessage({
      status: null,
      errorType: null,
      detail: error?.message,
      phase,
    }),
  };
}

function operatorUploadMessage({ status, errorType, detail, phase }) {
  if (errorType === "auth" || errorType === "auth_session_expired" || status === 401 || status === 403) {
    return phase === "poll"
      ? "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time."
      : "Telemetry processing session could not be validated.";
  }
  if (errorType === "upload_session_missing") {
    if (phase === "poll") {
      return "Telemetry batch processing in progress. Waiting for upload status to become available.";
    }
    return "Upload state unavailable.";
  }
  if (errorType === "job_not_found" || status === 404) {
    return "Upload processing interrupted.";
  }
  if (errorType === "sii_processing_failure") {
    return detail ? `SII processing failure: ${normalizeErrorMessage(detail)}` : "SII processing failure.";
  }
  if (status === 408 || status === 425 || status === 429 || status >= 500) {
    return "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time.";
  }
  if (phase === "poll") {
    return "Telemetry batch processing in progress. Large telemetry uploads may require additional processing time.";
  }
  return typeof detail === "string" && detail.trim()
    ? detail
    : "Upload processing interrupted.";
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
  const normalized = normalizeUploadStatus(uploadState);
  if (normalized === "uploading") {
    return "Telemetry batch received";
  }
  if (normalized === "queued") {
    return "Processing queued";
  }
  if (normalized === "parsing") {
    return "Header and schema detection";
  }
  if (normalized === "baseline_modeling") {
    return "Baseline modeling";
  }
  if (normalized === "running_sii") {
    return "Telemetry batch processing in progress";
  }
  if (normalized === "writing_state") {
    return "Writing facility state";
  }
  if (normalized === "complete") {
    return "Batch processing complete";
  }
  if (normalized === "error") {
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

function mapSiiUrgency(value) {
  const normalized = String(value ?? "").toLowerCase();
  if (normalized === "action" || normalized === "unstable" || normalized.includes("action")) {
    return "unstable";
  }
  if (normalized === "elevated") {
    return "elevated";
  }
  if (normalized === "review" || normalized.includes("drift")) {
    return "review";
  }
  if (normalized === "nominal" || normalized === "stable") {
    return "nominal";
  }
  return "info";
}

function formatIntelligenceSourceLabel(mode) {
  if (mode === "live") {
    return "Latest upload";
  }
  if (mode === "processing") {
    return "Upload processing";
  }
  return "No upload connected";
}

function cycleValue(base, tick, range = 6, precision = 1) {
  const value = base + Math.sin(tick / 2.2 + base / 7) * range + Math.cos(tick / 3.5 + base / 11) * (range / 2);
  return Number(value.toFixed(precision));
}

function buildSiiOperationalContext({
  intelligence,
  intelligenceStatus,
  result,
  latestUploadSnapshot,
  apiStatus,
  roomContext,
  systems,
  systemsState,
  tick,
  connectionTone,
  connectionSummary,
  connectionStatusLine,
  connectionActionHint,
}) {
  const safeIntelligence = normalizeFacilityIntelligence(intelligence);
  const fullResult = hasFullUploadResult(result) ? result : null;
  const facilityTone = mapSiiUrgency(safeIntelligence.urgency);
  const interventionItems = buildSiiInterventionItems(safeIntelligence);
  const primaryWindow = interventionItems[0] ?? null;
  const telemetryCards = fullResult ? buildTelemetryCards(fullResult) : buildSiiTelemetryCards(safeIntelligence);
  const actionQueue = buildActionQueue(interventionItems);
  const score = safeIntelligence.neraium_score ?? calculateNeraiumScore(facilityTone, interventionItems, Boolean(fullResult));

  return {
    useDemoTelemetry: false,
    intelligenceMode: safeIntelligence.mode ?? intelligenceStatus?.mode ?? (fullResult ? "live" : "empty"),
    facilityTone,
    facilityStateLabel: safeIntelligence.facility_state ?? formatOperationalLabel(facilityTone),
    heroTag: facilityTone === "nominal" ? "SII state stable" : "SII drift observed",
    heroHeadline: heroHeadlineFromTone(facilityTone),
    heroSubline: safeIntelligence.why_flagged ?? heroSublineFromTone(facilityTone, safeIntelligence.primary_room ?? roomContext.primary),
    readinessLabel: fullResult ? formatReadiness(fullResult.data_quality?.readiness) : "Operational Intelligence Active",
    connectionTone,
    connectionLabel: formatIntelligenceSourceLabel(safeIntelligence.mode ?? intelligenceStatus?.mode),
    connectionDetail: apiStatus.detail,
    connectionSummary,
    connectionStatusLine,
    connectionActionHint,
    dataSourceLabel: fullResult ? latestManualSourceLabel(fullResult) : (latestUploadSnapshot?.result_source ? "File upload" : "No data connected"),
    neraiumScore: score,
    scoreNarrative: summarizeScoreNarrative(facilityTone, interventionItems),
    scoreContext: safeIntelligence.observed_persistence && !isTechnicalEvidenceText(safeIntelligence.observed_persistence)
      ? safeIntelligence.observed_persistence
      : "Room behavior is being compared against recent operating patterns.",
    windowContext: safeIntelligence.baseline_comparison ?? buildWindowContext(primaryWindow, roomContext),
    primaryWindow,
    interventionItems,
    actionQueue,
    topologyNodes: buildTopologyNodes(interventionItems),
    alerts: fullResult ? buildAlertItems(fullResult, apiStatus) : buildSiiAlerts(safeIntelligence),
    findings: fullResult ? buildFindingsFeed(fullResult) : buildSiiFindings(safeIntelligence),
    timeline: fullResult ? buildOperationalTimeline(fullResult, apiStatus, roomContext) : buildSiiTimeline(safeIntelligence, apiStatus, tick),
    telemetryCards,
    summaryTelemetry: telemetryCards.slice(0, 4),
    overviewMetrics: buildOverviewMetrics(fullResult, apiStatus, systems, systemsState),
    roomCards: buildSiiRoomCards(safeIntelligence),
    roomTransitions: fullResult ? buildRoomTransitions(fullResult, roomContext) : buildSiiRoomTransitions(safeIntelligence),
    driftRows: fullResult
      ? (fullResult?.baseline_analysis?.column_drift ?? []).map((row) => ({
          ...row,
          drift_flag: mapOperationalTone(row.drift_flag),
        }))
      : buildSiiDriftRows(safeIntelligence),
    relationshipRows: fullResult ? buildRelationshipRows(fullResult) : buildSiiRelationshipRows(safeIntelligence),
    irrigationNotes: safeIntelligence.what_to_check ?? [],
    systemRows: systems.map((system) => [
      system.name,
      system.scope,
      systemRoomContext(system.name, roomContext),
      systemsState === "ready" ? "Facility feed active" : "Backend connection unavailable",
    ]),
    intakeStages: fullResult ? buildIntakeStages(fullResult, "complete", roomContext) : buildConnectionStateStages({ latestUploadSnapshot, uploadState: "idle", uploadError: "", roomContext }),
    evidenceLines: fullResult ? buildEvidenceConsole(fullResult) : buildSiiEvidenceLines(safeIntelligence),
    consoleEvents: fullResult ? buildConsoleEvents(fullResult, apiStatus, roomContext) : buildSiiConsoleEvents(safeIntelligence, apiStatus),
    observations: fullResult ? buildRoomObservations(fullResult, roomContext) : [
      safeIntelligence.why_flagged,
      safeIntelligence.baseline_comparison,
      safeIntelligence.confidence_basis,
    ].filter(Boolean),
    reportNotes: [
      "Operational intelligence is active",
      `Mode: ${formatIntelligenceModeValue(safeIntelligence.mode)}`,
      `Evidence fields: ${(intelligenceStatus?.evidence_fields_present ?? []).length}`,
    ],
    connectionEvents: buildConnectionEvents(apiStatus, tick),
  };
}

function buildOperationalContext({ result, latestUploadSnapshot, apiStatus, roomContext, systems, systemsState, facilityIntelligence, intelligenceStatus, tick }) {
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

  const fullResult = hasFullUploadResult(result) ? result : null;
  const apiIntelligence = fullResult?.sii_intelligence ?? facilityIntelligence;
  if (apiIntelligence) {
    return buildSiiOperationalContext({
      intelligence: apiIntelligence,
      intelligenceStatus,
      result: fullResult,
      latestUploadSnapshot,
      apiStatus,
      roomContext,
      systems,
      systemsState,
      tick,
      connectionTone,
      connectionSummary,
      connectionStatusLine,
      connectionActionHint,
    });
  }

  if (fullResult) {
    const telemetryCards = buildTelemetryCards(fullResult);
    const facilityTone = mapOperationalTone(fullResult.engine_result?.overall_result ?? fullResult.data_quality?.readiness ?? "nominal");
    const interventionItems = buildUploadedInterventionItems(fullResult, roomContext, telemetryCards, facilityTone);
    const actionQueue = buildActionQueue(interventionItems);
    const primaryWindow = interventionItems[0] ?? null;
    return {
      useDemoTelemetry: false,
      intelligenceMode: "live",
      facilityTone,
      facilityStateLabel: formatEngineResult(fullResult.engine_result?.overall_result ?? "normal"),
      heroTag: facilityTone === "nominal" ? "Control window established" : "Decision window tightening",
      heroHeadline: heroHeadlineFromTone(facilityTone),
      heroSubline: heroSublineFromTone(facilityTone, roomContext.primary),
      readinessLabel: formatReadiness(fullResult.data_quality?.readiness),
      connectionTone,
      connectionLabel: "Live telemetry feed",
      connectionDetail: apiStatus.detail,
      connectionSummary,
      connectionStatusLine,
      connectionActionHint,
      dataSourceLabel: latestManualSourceLabel(fullResult),
      neraiumScore: calculateNeraiumScore(facilityTone, interventionItems, true),
      scoreNarrative: summarizeScoreNarrative(facilityTone, interventionItems),
      scoreContext: buildScoreContext(calculateNeraiumScore(facilityTone, interventionItems, true), facilityTone, interventionItems),
      windowContext: buildWindowContext(interventionItems[0], roomContext),
      primaryWindow,
      interventionItems,
      actionQueue,
      topologyNodes: buildTopologyNodes(interventionItems),
      alerts: buildAlertItems(fullResult, apiStatus),
      findings: buildFindingsFeed(fullResult),
      timeline: buildOperationalTimeline(fullResult, apiStatus, roomContext),
      telemetryCards,
      summaryTelemetry: telemetryCards,
      overviewMetrics: buildOverviewMetrics(fullResult, apiStatus, systems, systemsState),
      roomCards: buildZoneSummary(roomContext),
      roomTransitions: buildRoomTransitions(fullResult, roomContext),
      driftRows: (fullResult.baseline_analysis?.column_drift ?? []).map((row) => ({
        ...row,
        drift_flag: mapOperationalTone(row.drift_flag),
      })),
      relationshipRows: buildRelationshipRows(fullResult),
      irrigationNotes: [
        `Irrigation context: ${roomContext.irrigation}.`,
        "Baseline established from current upload.",
        "Review recommended for irrigation variance only where the room trend persists across the active window.",
      ],
      systemRows: systems.map((system) => [
        system.name,
        system.scope,
        systemRoomContext(system.name, roomContext),
        systemsState === "ready" ? "Backend feed active" : "Backend connection unavailable",
      ]),
      intakeStages: buildIntakeStages(fullResult, "complete", roomContext),
      evidenceLines: buildEvidenceConsole(fullResult),
      consoleEvents: buildConsoleEvents(fullResult, apiStatus, roomContext),
      observations: buildRoomObservations(fullResult, roomContext),
      reportNotes: REPORT_TEMPLATES,
      connectionEvents: buildConnectionEvents(apiStatus, tick),
    };
  }
  return buildEmptyOperationalContext({
    latestUploadSnapshot,
    apiStatus,
    roomContext,
    systems,
    systemsState,
    tick,
    connectionTone,
    connectionSummary,
    connectionStatusLine,
    connectionActionHint,
  });
}

function buildEmptyOperationalContext({
  latestUploadSnapshot,
  apiStatus,
  roomContext,
  systems,
  systemsState,
  tick,
  connectionTone,
  connectionSummary,
  connectionStatusLine,
  connectionActionHint,
}) {
  const message = latestUploadSnapshot?.message ?? "No data connected yet.";
  const items = [{
    id: "connect-data",
    label: "Connect telemetry",
    detail: "Upload a telemetry file in Data Connections to activate dashboard values.",
    tone: "info",
    window: "Awaiting upload",
    impact: "No active result",
    actions: ["Upload"],
    technicalDetails: [
      `latest_upload_status=${latestUploadSnapshot?.status ?? "empty"}`,
      `api_status=${apiStatus.state}`,
    ],
  }];
  return {
    useDemoTelemetry: false,
    intelligenceMode: "empty",
    facilityTone: "info",
    facilityStateLabel: "No data connected yet",
    heroTag: "Awaiting telemetry",
    heroHeadline: "Upload telemetry to activate live facility intelligence.",
    heroSubline: message,
    readinessLabel: "No active upload",
    connectionTone,
    connectionLabel: "No upload connected",
    connectionDetail: apiStatus.detail,
    connectionSummary,
    connectionStatusLine,
    connectionActionHint,
    dataSourceLabel: "Awaiting upload",
    neraiumScore: null,
    scoreNarrative: "Neraium score will appear after a completed upload.",
    scoreContext: "No completed upload is available yet.",
    windowContext: "Upload a telemetry file to establish the operating window.",
    primaryWindow: items[0],
    interventionItems: items,
    actionQueue: [],
    topologyNodes: [],
    alerts: [{ title: "No data connected yet", detail: message, tone: "info" }],
    findings: [{ title: "Upload required", detail: "Dashboard cards will update when a telemetry file finishes processing.", tone: "info" }],
    timeline: buildConnectionEvents(apiStatus, tick),
    telemetryCards: buildEmptyTelemetryCards(),
    summaryTelemetry: buildEmptyTelemetryCards().slice(0, 4),
    overviewMetrics: buildEmptyOverviewMetrics(systems, systemsState),
    roomCards: [{ label: "Primary room", value: roomContext.primary, detail: roomContext.secondary, tone: "info" }],
    roomTransitions: [],
    driftRows: [],
    relationshipRows: [],
    irrigationNotes: ["No telemetry has been processed yet."],
    systemRows: systems.map((system) => [
      system.name,
      system.scope,
      systemRoomContext(system.name, roomContext),
      systemsState === "ready" ? "Awaiting connected telemetry" : "Backend connection unavailable",
    ]),
    intakeStages: buildConnectionStateStages({ latestUploadSnapshot, uploadState: "idle", uploadError: "", roomContext }),
    evidenceLines: [
      "connection.state=no_data",
      `api.state=${apiStatus.state}`,
      "latest_result=unavailable",
    ],
    consoleEvents: [
      `telemetry.link=${apiStatus.state}`,
      "telemetry.status=no_data",
      "event.awaiting_upload=true",
    ],
    observations: [message],
    reportNotes: ["No data connected yet", "Upload required before facility intelligence can run"],
    connectionEvents: buildConnectionEvents(apiStatus, tick),
  };
}

function buildEmptyTelemetryCards() {
  return [
    { label: "Neraium score", primary: "No active result", secondary: "Complete an upload to calculate score.", series: [], tone: "info" },
    { label: "Operating state", primary: "No data connected yet", secondary: "Facility state will populate from the latest completed upload.", series: [], tone: "info" },
    { label: "Primary room", primary: "Awaiting upload", secondary: "Room context will populate from uploaded telemetry.", series: [], tone: "info" },
    { label: "Drift status", primary: "Awaiting upload", secondary: "Drift and alert status require a completed upload.", series: [], tone: "info" },
  ];
}

function buildEmptyOverviewMetrics(systems, systemsState) {
  return [
    { label: "Facility stability", value: "No data connected yet" },
    { label: "Rooms under review", value: 0 },
    { label: "Telemetry cadence", value: "Awaiting upload" },
    { label: "Systems in scope", value: systemsState === "ready" ? `${systems.length} monitored` : `${systems.length} defined` },
  ];
}

function buildConnectionStateStages({ latestUploadSnapshot, uploadState, uploadError, roomContext }) {
  const normalizedState = normalizeUploadStatus(uploadError ? "failed" : uploadState);
  const latestStatus = String(latestUploadSnapshot?.status ?? "empty").toLowerCase();
  const currentState = isUploadProcessing(normalizedState)
    ? "Upload processing"
    : uploadError
      ? "Upload failed"
      : latestStatus === "active"
        ? "Latest result active"
        : "No data connected yet";
  return [
    {
      title: "No data connected yet",
      detail: latestStatus === "empty" ? "No completed telemetry upload is available." : "A completed upload is already available.",
      state: latestStatus === "empty" ? "active" : "complete",
      tone: latestStatus === "empty" ? "info" : "nominal",
    },
    {
      title: "Upload processing",
      detail: isUploadProcessing(normalizedState)
        ? "Telemetry file received and processing is underway."
        : "Upload a telemetry file to start ingestion.",
      state: isUploadProcessing(normalizedState) ? "active" : (latestStatus === "active" || uploadError ? "complete" : "standby"),
      tone: isUploadProcessing(normalizedState) ? "review" : "info",
    },
    {
      title: "Upload complete",
      detail: latestStatus === "active"
        ? `${latestUploadSnapshot?.last_filename ?? "Latest upload"} completed and refreshed ${roomContext.primary}.`
        : "Waiting for the next completed upload.",
      state: latestStatus === "active" ? "complete" : "standby",
      tone: latestStatus === "active" ? "nominal" : "info",
    },
    {
      title: "Upload failed",
      detail: uploadError ? normalizeErrorMessage(uploadError) : "Operator-friendly upload errors appear here if processing fails.",
      state: uploadError ? "active" : "standby",
      tone: uploadError ? "elevated" : "info",
    },
    {
      title: "Latest result active",
      detail: latestStatus === "active"
        ? `Dashboard is using ${latestUploadSnapshot?.last_filename ?? "the latest upload"} as the active result source.`
        : "Dashboard will switch to the newest completed upload automatically.",
      state: latestStatus === "active" ? "active" : "standby",
      tone: latestStatus === "active" ? "nominal" : "info",
    },
  ];
}

function connectionStateLabel(latestStatus, uploadState, uploadError) {
  if (uploadError || normalizeUploadStatus(uploadState) === "failed") {
    return "Upload failed";
  }
  if (isUploadProcessing(uploadState)) {
    return "Upload processing";
  }
  if (String(latestStatus).toLowerCase() === "active") {
    return "Latest result active";
  }
  return "No data connected yet";
}

function buildUploadedInterventionItems(result, roomContext, telemetryCards, facilityTone) {
  const engineSignals = result?.engine_result?.signals ?? [];
  const columnReview = result?.operator_report?.columns_requiring_review ?? [];
  const attribution = result?.driver_attribution;
  const irrigationTone = result?.cultivation_mapping?.categories?.irrigation?.length ? "review" : "info";
  const attributionGuidance = buildGuidanceFromAttribution(attribution, facilityTone);
  const attributionTechnicalDetails = [
    attribution?.driver_category && `driver_category=${attribution.driver_category}`,
    attribution?.likely_driver && `likely_driver=${attribution.likely_driver}`,
    attribution?.confidence_basis && `confidence_basis=${attribution.confidence_basis}`,
    attribution?.attribution_confidence && `attribution_confidence=${attribution.attribution_confidence}`,
    ...(attribution?.supporting_evidence ?? []).map((line, index) => `supporting_evidence_${index + 1}=${line}`),
    ...(engineSignals ?? []).slice(0, 4).map((signal, index) => `engine_signal_${index + 1}=${signal.message}`),
  ].filter(Boolean);

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
      summary: attributionGuidance.primaryDriver,
      detail: `Current upload places ${attribution?.room ?? roomContext.primary} in the primary review lane.`,
      shortDetail: attributionGuidance.primaryDriver,
      whyHeadline: attribution?.supporting_evidence?.[0]
        ? translateEvidenceLine(attribution.supporting_evidence[0], attribution?.driver_category)
        : engineSignals[0]?.message
          ? translateEvidenceLine(engineSignals[0].message, attribution?.driver_category)
          : "Current room trend and readiness signals are tightening the available intervention window.",
      drivers: (attribution?.supporting_evidence ?? buildWhyDrivers(result, telemetryCards, roomContext))
        .map((line) => translateEvidenceLine(line, attribution?.driver_category)),
      driverAttribution: attribution,
      likelyDriver: attribution?.likely_driver,
      contributingSignals: attribution?.contributing_signals,
      confidenceBasis: attribution?.confidence_basis && isTechnicalEvidenceText(attribution.confidence_basis)
        ? "Telemetry evidence is strong enough to prioritize an operator inspection."
        : attribution?.confidence_basis,
      supportingEvidence: (attribution?.supporting_evidence ?? []).map((line) => translateEvidenceLine(line, attribution?.driver_category)),
      structuralExplanation: buildUploadedStructuralExplanation(attribution, engineSignals).map((line) => translateEvidenceLine(line, attribution?.driver_category)),
      technicalDetails: attributionTechnicalDetails,
      guidance: attributionGuidance,
      decisionLabel: decisionLabelFromTone(facilityTone, 0),
      baselineContext: buildUploadBaselineContext(roomContext, facilityTone),
      recommendation: recommendationFromTone(facilityTone),
      primaryAction: operatorMoveFromGuidance(attributionGuidance),
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
      guidance: buildGuidanceFromCategory("irrigation_balance"),
      decisionLabel: "Validate irrigation balance",
      baselineContext: `${roomContext.secondary} typically holds a longer recovery window. Current irrigation recovery is shortening.`,
      recommendation: recommendationFromTone(irrigationTone),
      primaryAction: operatorMoveFromGuidance(buildGuidanceFromCategory("irrigation_balance")),
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
      guidance: buildGuidanceFromCategory("telemetry_continuity"),
      decisionLabel: "Continue monitoring",
      baselineContext: "Facility-level confidence improves as room coverage deepens and more week-specific context is connected.",
      recommendation: "Continue monitoring",
      primaryAction: operatorMoveFromGuidance(buildGuidanceFromCategory("telemetry_continuity")),
      actions: ["Acknowledge", "Schedule", "Escalate", "Ignore"],
      impact: "Facility-wide confidence",
      change: "Latest ingest synchronized",
      rankLabel: "Priority 03",
    },
  ];

  return items;
}

function buildSiiInterventionItems(intelligence) {
  const rooms = Array.isArray(intelligence.rooms) && intelligence.rooms.length > 0
    ? intelligence.rooms
    : [intelligence];
  return rooms.map((room, index) => {
    const tone = mapSiiUrgency(room.urgency ?? intelligence.urgency);
    const rawSupportingEvidence = room.supporting_evidence ?? intelligence.supporting_evidence ?? [];
    const rawRelationshipEvidence = room.relationship_evidence ?? intelligence.relationship_evidence ?? [];
    const translation = buildOperationalTranslation({
      driver: room.primary_driver ?? intelligence.primary_driver,
      driverCategory: room.driver_category ?? intelligence.driver_category,
      why: room.why_flagged ?? intelligence.why_flagged,
      evidence: rawSupportingEvidence,
      relationships: rawRelationshipEvidence,
      confidenceBasis: room.confidence_basis ?? intelligence.confidence_basis,
      baselineContext: room.baseline_comparison ?? intelligence.baseline_comparison,
      urgency: room.urgency ?? intelligence.urgency,
      window: room.intervention_window ?? intelligence.intervention_window,
    });
    const guidance = {
      nextMove: room.recommended_operator_review ?? intelligence.recommended_operator_review ?? "Continue monitoring",
      primaryDriver: translation.primaryDriver,
      whyFlagged: translation.whyFlagged,
      whatToCheck: room.what_to_check ?? intelligence.what_to_check ?? translation.whatToCheck,
    };
    return {
      id: `sii-room-${index + 1}`,
      label: room.room ?? intelligence.primary_room ?? "Current room",
      title: `${room.room ?? intelligence.primary_room ?? "Current room"} SII state`,
      shortTitle: room.room ?? intelligence.primary_room ?? "Current room",
      status: room.room_state ?? intelligence.facility_state ?? "Monitoring",
      window: room.intervention_window ?? intelligence.intervention_window ?? "Monitoring",
      tone,
      confidence: room.confidence ?? confidenceFromTone(tone, intelligence.mode === "live"),
      summary: guidance.primaryDriver,
      detail: translation.baselineContext,
      shortDetail: guidance.primaryDriver,
      whyHeadline: guidance.whyFlagged,
      drivers: translation.supportingEvidence,
      supportingEvidence: translation.supportingEvidence,
      relationshipEvidence: translation.relationshipEvidence,
      structuralExplanation: (room.structural_explanation ?? intelligence.structural_explanation ?? [])
        .map((line) => translateEvidenceLine(line, translation.category)),
      confidenceBasis: translation.confidenceBasis,
      technicalDetails: translation.technicalDetails,
      guidance,
      baselineContext: translation.baselineContext,
      recommendation: guidance.nextMove,
      primaryAction: guidance.nextMove,
      decisionLabel: room.room_state ?? intelligence.facility_state ?? decisionLabelFromTone(tone, index),
      actions: actionSetFromTone(tone),
      impact: impactFromTone(tone),
      change: isTechnicalEvidenceText(room.observed_persistence ?? intelligence.observed_persistence)
        ? translateEvidenceLine(room.observed_persistence ?? intelligence.observed_persistence, translation.category)
        : (room.observed_persistence ?? intelligence.observed_persistence ?? "Evidence active"),
      rankLabel: `Priority ${String(index + 1).padStart(2, "0")}`,
    };
  }).sort((a, b) => tonePriority(a.tone) - tonePriority(b.tone));
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
      guidance: buildGuidanceFromRoom(room, index),
      baselineContext: baselineContextFromRoom(room),
      recommendation: recommendationFromTone(room.tone),
      primaryAction: operatorMoveFromGuidance(buildGuidanceFromRoom(room, index)),
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

function buildSiiTelemetryCards(intelligence) {
  const translation = buildOperationalTranslation({
    driver: intelligence.primary_driver,
    driverCategory: intelligence.driver_category,
    why: intelligence.why_flagged,
    evidence: intelligence.supporting_evidence ?? [],
    relationships: intelligence.relationship_evidence ?? [],
    confidenceBasis: intelligence.confidence_basis,
    baselineContext: intelligence.baseline_comparison,
    urgency: intelligence.urgency,
    window: intelligence.intervention_window,
  });
  return [
    {
      label: "Primary driver",
      primary: translation.primaryDriver,
      secondary: translation.whyFlagged,
      series: [72, 74, 76, 75, 78, 80],
      tone: mapSiiUrgency(intelligence.urgency),
      technicalDetails: translation.technicalDetails,
    },
    {
      label: "Relationship evidence",
      primary: translation.relationshipEvidence[0] ?? "Relationship evidence limited",
      secondary: translation.confidenceBasis,
      series: [60, 61, 63, 62, 64, 66],
      tone: "info",
      technicalDetails: translation.technicalDetails,
    },
    {
      label: "Intervention window",
      primary: intelligence.intervention_window ?? "Monitoring",
      secondary: translation.baselineContext,
      series: [80, 78, 76, 73, 71, 69],
      tone: mapSiiUrgency(intelligence.urgency),
      technicalDetails: translation.technicalDetails,
    },
  ];
}

function buildSiiRoomCards(intelligence) {
  return (intelligence.rooms ?? [intelligence]).map((room) => ({
    label: room.room ?? intelligence.primary_room ?? "Current room",
    value: room.room_state ?? intelligence.facility_state ?? "Monitoring",
    detail: buildOperationalTranslation({
      driver: room.primary_driver ?? intelligence.primary_driver,
      why: room.why_flagged ?? intelligence.why_flagged,
      evidence: room.supporting_evidence ?? intelligence.supporting_evidence ?? [],
      relationships: room.relationship_evidence ?? intelligence.relationship_evidence ?? [],
    }).primaryDriver,
    tone: mapSiiUrgency(room.urgency ?? intelligence.urgency),
  }));
}

function buildSiiAlerts(intelligence) {
  const translation = buildOperationalTranslation({
    driver: intelligence.primary_driver,
    why: intelligence.why_flagged,
    evidence: intelligence.supporting_evidence ?? [],
    relationships: intelligence.relationship_evidence ?? [],
  });
  return [
    {
      title: intelligence.facility_state ?? "SII state active",
      detail: translation.whyFlagged,
      tone: mapSiiUrgency(intelligence.urgency),
    },
  ];
}

function buildSiiFindings(intelligence) {
  const translation = buildOperationalTranslation({
    driver: intelligence.primary_driver,
    driverCategory: intelligence.driver_category,
    why: intelligence.why_flagged,
    evidence: intelligence.supporting_evidence ?? [],
    relationships: intelligence.relationship_evidence ?? [],
    confidenceBasis: intelligence.confidence_basis,
  });
  return [
    {
      title: "Primary driver",
      detail: translation.primaryDriver,
      tone: mapSiiUrgency(intelligence.urgency),
    },
    {
      title: "Why flagged",
      detail: translation.whyFlagged,
      tone: "info",
    },
    ...(intelligence.what_to_check ?? []).slice(0, 2).map((check) => ({
      title: "What to check",
      detail: check,
      tone: "info",
    })),
  ];
}

function buildSiiTimeline(intelligence, apiStatus, tick) {
  const translation = buildOperationalTranslation({
    driver: intelligence.primary_driver,
    why: intelligence.why_flagged,
    evidence: intelligence.supporting_evidence ?? [],
    relationships: intelligence.relationship_evidence ?? [],
  });
  return [
    {
      time: formatClockTime(intelligence.last_updated ?? apiStatus.checkedAt ?? new Date(Date.now() - tick * OPERATIONAL_CADENCE_MS).toISOString()),
      title: "Operational intelligence updated",
      detail: isTechnicalEvidenceText(intelligence.observed_persistence)
        ? translateEvidenceLine(intelligence.observed_persistence, translation.category)
        : (intelligence.observed_persistence ?? translation.whyFlagged),
      tone: mapSiiUrgency(intelligence.urgency),
    },
  ];
}

function buildSiiRoomTransitions(intelligence) {
  return (intelligence.structural_explanation ?? []).slice(0, 3).map((detail, index) => ({
    title: index === 0 ? "Operational explanation" : "Relationship movement",
    detail: translateEvidenceLine(detail, inferOperationalCategory(intelligence.primary_driver, intelligence.why_flagged)),
    tone: mapSiiUrgency(intelligence.urgency),
  }));
}

function buildSiiDriftRows(intelligence) {
  return [
    {
      column: "SII baseline comparison",
      direction: "observed",
      drift_flag: mapSiiUrgency(intelligence.urgency),
      baseline_average: 0,
      recent_average: 0,
      detail: buildOperationalTranslation({
        driver: intelligence.primary_driver,
        baselineContext: intelligence.baseline_comparison,
        why: intelligence.why_flagged,
      }).baselineContext,
    },
  ];
}

function buildSiiRelationshipRows(intelligence) {
  return (intelligence.relationship_evidence ?? []).map((detail, index) => ({
    columns: ["environmental coupling", "recent baseline"],
    change: relationshipDetail({ detail }),
    tone: mapSiiUrgency(intelligence.urgency),
    detail: translateEvidenceLine(detail, inferOperationalCategory(intelligence.primary_driver, intelligence.why_flagged)),
    technicalDetails: [`relationship_evidence_${index + 1}=${detail}`],
  }));
}

function buildSiiEvidenceLines(intelligence) {
  return [
    `sii.source=${intelligence.source ?? "sii_engine"}`,
    `sii.mode=${formatIntelligenceModeValue(intelligence.mode)}`,
    `sii.score=${intelligence.neraium_score ?? "unavailable"}`,
    `sii.primary_driver=${intelligence.primary_driver ?? "unavailable"}`,
    ...(intelligence.supporting_evidence ?? []).slice(0, 4).map((line, index) => `sii.evidence_${index + 1}=${line}`),
  ];
}

function buildSiiConsoleEvents(intelligence, apiStatus) {
  return [
    `event.sii_mode=${formatIntelligenceModeValue(intelligence.mode)}`,
    `event.api_state=${apiStatus.state}`,
    `event.active_rooms=${intelligence.rooms?.length ?? 0}`,
    ...buildSiiEvidenceLines(intelligence),
  ];
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
      : "Environmental coupling remains stable.",
    `${room.irrigationState}. Cycle settling remains the current operating state.`,
  ];
}

function buildUploadedStructuralExplanation(attribution, engineSignals) {
  if (attribution?.driver_category === "humidity_control") {
    return [
      "Temperature recovery is decoupling from humidity stabilization.",
      "Environmental coupling is less consistent than the room's recent baseline.",
      "Room recovery behavior is compressing the intervention horizon.",
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
    "Environmental coupling remains stable.",
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
      "Environmental coupling is less consistent than the room's recent baseline.",
      "Room recovery behavior is compressing the intervention horizon.",
    ];
  }
  if (item?.tone === "elevated") {
    return [
      "Airflow response consistency weakened during active climate periods.",
      "Humidity recovery is becoming less stable after environmental transitions.",
      "Room recovery behavior is compressing the intervention horizon.",
    ];
  }
  if (item?.tone === "review") {
    return [
      "Drift is visible, but the room remains controllable.",
      "Transition stability should be watched through the next operating window.",
      "Environmental coupling remains mostly consistent.",
    ];
  }
  return [
    "Room temperature response remains within expected behavior.",
    "Environmental coupling remains stable.",
    "Cycle settling remains the current operating state.",
  ];
}

function buildStructuralExplanationFromRoom(room, index = 0) {
  if (room.tone === "unstable") {
    return [
      "Temperature recovery is decoupling from humidity stabilization.",
      "Environmental coupling is less consistent than the room's recent baseline.",
      "Room recovery behavior is compressing the intervention horizon.",
    ];
  }
  if (room.tone === "elevated") {
    return [
      index % 2 === 0
        ? "Airflow response consistency weakened during active climate periods."
        : "Environmental coupling is shifting across the current room cycle.",
      "Humidity recovery is becoming less stable after environmental transitions.",
      "Room recovery behavior is compressing the intervention horizon.",
    ];
  }
  if (room.tone === "review") {
    return [
      "Drift is visible, but the room remains controllable.",
      "Transition stability should be watched through the next operating window.",
      "Environmental coupling remains mostly consistent.",
    ];
  }
  return [
    "Room temperature response remains within expected behavior.",
    "Environmental coupling remains stable.",
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
    return "Investigate delayed environmental recovery";
  }
  if (tone === "elevated") {
    return "Review environmental coupling";
  }
  if (tone === "review") {
    return "Observe drift against baseline";
  }
  return "Continue monitoring";
}

function primaryActionFromTone(tone) {
  if (tone === "unstable") {
    return "Investigate delayed environmental recovery";
  }
  if (tone === "elevated") {
    return "Review environmental coupling";
  }
  if (tone === "review") {
    return "Observe drift against baseline";
  }
  return "Continue monitoring";
}

function primaryActionFromRoom(room, index = 0) {
  return operatorMoveFromGuidance(buildGuidanceFromRoom(room, index));
}

function operatorMoveFromGuidance(guidance) {
  return guidance?.nextMove ?? "Continue monitoring";
}

function buildGuidanceForItem(item) {
  if (item?.guidance) {
    return item.guidance;
  }
  if (item?.driverAttribution) {
    return buildGuidanceFromAttribution(item.driverAttribution, item.tone);
  }
  if (item?.likelyDriver) {
    return buildGuidanceFromLikelyDriver(item.likelyDriver);
  }
  if (item?.label?.toLowerCase().includes("irrigation") || item?.status?.toLowerCase().includes("irrigation")) {
    return buildGuidanceFromCategory("irrigation_balance");
  }
  if (item?.tone === "unstable") {
    return buildGuidanceFromCategory("humidity_recovery");
  }
  if (item?.tone === "elevated") {
    return buildGuidanceFromCategory("airflow_response");
  }
  if (item?.tone === "review") {
    return buildGuidanceFromCategory("environmental_coupling");
  }
  return buildGuidanceFromCategory("stable_monitoring");
}

function buildGuidanceFromRoom(room, index = 0) {
  if (room.irrigationState.toLowerCase().includes("feed")) {
    return buildGuidanceFromCategory("irrigation_balance");
  }
  if (room.tone === "unstable") {
    return buildGuidanceFromCategory(room.instability > 1.12 ? "humidity_recovery" : "thermal_consistency");
  }
  if (room.tone === "elevated") {
    return buildGuidanceFromCategory(index % 2 === 0 ? "airflow_response" : "environmental_coupling");
  }
  if (room.tone === "review") {
    return buildGuidanceFromCategory(index % 2 === 0 ? "environmental_coupling" : "room_pressure");
  }
  return buildGuidanceFromCategory("stable_monitoring");
}

function buildGuidanceFromAttribution(attribution, fallbackTone) {
  if (!attribution) {
    return buildGuidanceFromCategory(fallbackTone === "unstable" ? "humidity_recovery" : "environmental_coupling");
  }
  const category = attribution.driver_category === "humidity_control"
    ? "humidity_recovery"
    : attribution.driver_category === "hvac_instability"
      ? "thermal_consistency"
      : attribution.driver_category === "airflow_restriction"
        ? "airflow_response"
        : attribution.driver_category === "irrigation_timing"
          ? "irrigation_balance"
          : attribution.driver_category === "sensor_network"
            ? "telemetry_continuity"
            : "environmental_coupling";
  const guidance = buildGuidanceFromCategory(category);
  return {
    ...guidance,
    primaryDriver: humanizeDriverCategory(attribution.driver_category ?? category),
    whyFlagged: attribution.supporting_evidence?.[0]
      ? translateEvidenceLine(attribution.supporting_evidence[0], category)
      : guidance.whyFlagged,
    nextMove: attribution.next_operator_move && !isGenericOperatorMove(attribution.next_operator_move)
      ? attribution.next_operator_move
      : guidance.nextMove,
  };
}

function buildGuidanceFromLikelyDriver(likelyDriver) {
  const normalized = likelyDriver.toLowerCase();
  if (normalized.includes("humid") || normalized.includes("moisture")) {
    return buildGuidanceFromCategory("humidity_recovery");
  }
  if (normalized.includes("airflow") || normalized.includes("pressure")) {
    return buildGuidanceFromCategory("airflow_response");
  }
  if (normalized.includes("temperature") || normalized.includes("hvac") || normalized.includes("thermal")) {
    return buildGuidanceFromCategory("thermal_consistency");
  }
  if (normalized.includes("irrigation") || normalized.includes("feed")) {
    return buildGuidanceFromCategory("irrigation_balance");
  }
  return buildGuidanceFromCategory("environmental_coupling");
}

function buildGuidanceFromCategory(category) {
  const guidance = {
    humidity_recovery: {
      nextMove: "Review humidity recovery behavior",
      primaryDriver: "Humidity recovery is lagging behind recent room behavior.",
      whyFlagged: "Humidity recovery has remained slower than recent room behavior across recent monitoring windows.",
      whatToCheck: [
        "Review dehumidification response",
        "Check room moisture load",
        "Compare recent recovery time to normal room behavior",
      ],
    },
    airflow_response: {
      nextMove: "Inspect airflow response",
      primaryDriver: "Airflow response appears to be recovering slower than recent baseline.",
      whyFlagged: "Room recovery suggests airflow response is not matching recent environmental behavior.",
      whatToCheck: [
        "Inspect airflow path",
        "Check fan response consistency",
        "Review room exchange behavior",
      ],
    },
    thermal_consistency: {
      nextMove: "Review thermal consistency",
      primaryDriver: "Temperature recovery is no longer matching humidity stabilization.",
      whyFlagged: "Temperature and humidity are no longer recovering together the way this room normally does.",
      whatToCheck: [
        "Review temperature recovery",
        "Check cooling response stability",
        "Compare hot spots against recent room behavior",
      ],
    },
    irrigation_balance: {
      nextMove: "Check irrigation balance",
      primaryDriver: "Irrigation balance is changing during the recovery window.",
      whyFlagged: "Recovery behavior after feed events is shifting compared to recent room baseline.",
      whatToCheck: [
        "Review irrigation timing",
        "Check runoff or substrate response if available",
        "Compare recovery behavior after feed events",
      ],
    },
    environmental_coupling: {
      nextMove: "Review environmental coupling",
      primaryDriver: "Environmental coupling is becoming less consistent.",
      whyFlagged: "Temperature and humidity recovery appear less consistent across recent monitoring windows.",
      whatToCheck: [
        "Compare temperature and humidity recovery together",
        "Review room transition behavior",
        "Check whether recovery timing is moving earlier than normal",
      ],
    },
    room_pressure: {
      nextMove: "Inspect room pressure stability",
      primaryDriver: "Room pressure stability appears to be affecting recovery behavior.",
      whyFlagged: "Room behavior is moving earlier than its recent operating baseline.",
      whatToCheck: [
        "Inspect room pressure stability",
        "Review door and room sealing behavior",
        "Compare room exchange behavior to recent baseline",
      ],
    },
    telemetry_continuity: {
      nextMove: "Review telemetry continuity",
      primaryDriver: "Telemetry coverage is limiting confidence in the current room explanation.",
      whyFlagged: "Connected signals suggest more room coverage is needed before confidence tightens.",
      whatToCheck: [
        "Confirm room telemetry coverage",
        "Review missing or stale readings",
        "Compare connected signals against expected room sources",
      ],
    },
    stable_monitoring: {
      nextMove: "Continue monitoring",
      primaryDriver: "Environmental coupling remains consistent compared to recent baseline.",
      whyFlagged: "Room behavior remains visible and controllable across recent monitoring windows.",
      whatToCheck: [
        "Continue routine room walk",
        "Watch recovery timing after the next transition",
        "Review changes only if the window shortens",
      ],
    },
  };
  return guidance[category] ?? guidance.environmental_coupling;
}

function isGenericOperatorMove(move) {
  const normalized = move.toLowerCase();
  return normalized.includes("stabilize environment")
    || normalized.includes("needs review")
    || normalized.includes("check room")
    || normalized.includes("fix environment")
    || normalized.includes("optimize conditions")
    || normalized.includes("adjust before next cycle");
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
  return result?.data_quality?.readiness === "ready" ? "2 weeks" : "5 days";
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
      change: tick % 2 === 0
        ? "Humidity recovery is becoming less stable after environmental transitions."
        : "Humidity recovery is returning toward the room baseline.",
      baseline_correlation: "0.74",
      recent_correlation: tick % 2 === 0 ? "0.59" : "0.68",
      tone: tick % 2 === 0 ? "review" : "nominal",
    },
    {
      columns: ["HVAC", "temperature"],
      change: roomStates[0].hvacDrift > 1.4
        ? "Environmental coupling is less consistent than the room's recent baseline."
        : "Temperature response remains consistent with recent room behavior.",
      baseline_correlation: "0.81",
      recent_correlation: roomStates[0].hvacDrift > 1.4 ? "0.63" : "0.77",
      tone: roomStates[0].hvacDrift > 1.4 ? "elevated" : "nominal",
    },
    {
      columns: ["CO2", "airflow"],
      change: "Air movement behavior became less consistent during changing room conditions.",
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
      detail: `Baseline room context held on ${roomContext.primary} while telemetry feed advances through live telemetry cadence ${tick}.`,
      state: "active",
      tone: "info",
    },
    {
      title: "SII engine processing",
      detail: "Awaiting uploaded room exports before SII engine processing starts.",
      state: "standby",
      tone: "review",
    },
    {
      title: "Evidence and state write",
      detail: "Runner state will refresh Facility Command after processing completes.",
      state: "standby",
      tone: "review",
    },
    {
      title: "Complete",
      detail: "Upload completion will replace baseline telemetry with uploaded runner state.",
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

function processingTraceLines(trace) {
  return [
    `sii_pipeline_ran=${Boolean(trace.sii_pipeline_ran)}`,
    `driver_attribution_ran=${Boolean(trace.driver_attribution_ran)}`,
    `engine_module=${trace.engine_module ?? "unknown"}`,
    `engine_version=${trace.engine_version ?? "unknown"}`,
    `rows_processed=${trace.rows_processed ?? 0}`,
    `columns_analyzed=${trace.columns_analyzed ?? 0}`,
    `evidence_count=${trace.evidence_count ?? 0}`,
    `git_commit=${trace.git_commit ?? "unknown"}`,
  ];
}

function runnerTraceLines(result) {
  return [
    `runner_used=${Boolean(result.runner_used)}`,
    `runner_module=${result.runner_module ?? "unknown"}`,
    `core_engine=${result.core_engine ?? "unknown"}`,
    `rows_processed=${result.rows_processed ?? 0}`,
    `columns_used=${Array.isArray(result.columns_used) ? result.columns_used.length : 0}`,
    `sensor_vector_count=${result.sensor_vector_count ?? 0}`,
    `latest_regime=${result.latest_state?.regime ?? result.output_summary?.latest_regime ?? "unknown"}`,
    `same_exact_fd004_validation_runner=false`,
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

function formatOperatorActionLabel(action) {
  if (action === "acknowledge") {
    return "Acknowledged";
  }
  if (action === "review") {
    return "Under review";
  }
  if (action === "taken") {
    return "Action taken";
  }
  if (action === "log") {
    return "Intervention logged";
  }
  return "Status updated";
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

function formatIntelligenceModeValue(mode) {
  if (mode === "live") {
    return "active";
  }
  if (mode === "processing") {
    return "processing";
  }
  if (mode === "empty") {
    return "no_data";
  }
  return mode ?? "unknown";
}

function formatConnectorStatus(status) {
  const value = String(status ?? "not_configured").replace(/_/g, " ");
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function connectorStatusTone(status) {
  if (status === "ready") {
    return "nominal";
  }
  if (status === "degraded") {
    return "review";
  }
  if (status === "offline") {
    return "elevated";
  }
  return "muted";
}

export default App;



