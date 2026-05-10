import { Component, useCallback, useEffect, useRef, useState } from "react";
import {
 API_BASE_URL,
 apiFetch,
 API_CONFIG_WARNING,
} from "./config";
import CommandOverviewWorkspace from "./components/CommandOverviewWorkspace";
import DataConnectionsWorkspace from "./components/DataConnectionsWorkspace";
import EvidenceTrailWorkspace from "./components/EvidenceTrailWorkspace";
import FacilitySystemsWorkspace from "./components/FacilitySystemsWorkspace";
import IntelligenceConsoleWorkspace from "./components/IntelligenceConsoleWorkspace";
import {
  CompactList,
  EmptyState,
  InterventionGrid,
  MetricGrid,
  Panel,
  StatusDot,
  WhyPanel,
} from "./components/workspacePrimitives";
import {
  buildConfidenceBasis,
  buildFleetSummary,
  buildGuidanceForItem,
  buildStructuralExplanation,
  connectorStatusTone,
  formatConfidenceLabel,
  formatConnectorStatus,
  formatFacilityPlainState,
  formatOperationalLabel,
  formatRoomDecisionState,
  formatScoreReadiness,
  processingTraceLines,
  runnerTraceLines,
} from "./viewModels/operationalHelpers";
import {
  buildIntakeStages,
  buildUploadRequestError,
  classifyUploadError,
  isUploadProcessing,
  normalizeErrorMessage,
  normalizeUploadStatus,
  operatorUploadMessage,
  readJsonPayload,
  uploadStateMessage,
} from "./viewModels/uploadFlow";
import * as uploadStateView from "./viewModels/uploadState";
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
  {
    id: "evidence-trail",
    label: "Evidence Trail",
    eyebrow: "Evidence",
    description: "Run history, explanations, warnings, errors, and report export.",
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
  const [intelligenceStatus, setIntelligenceStatus] = useState(uploadStateView.buildEmptyIntelligenceStatus());
  const [engineIdentity, setEngineIdentity] = useState(null);
  const [backendError, setBackendError] = useState(API_CONFIG_WARNING);
  const [latestUploadResult, setLatestUploadResult] = useState(null);
  const [latestUploadSnapshot, setLatestUploadSnapshot] = useState(uploadStateView.buildEmptyLatestUploadSnapshot());
  const [evidenceRefreshKey, setEvidenceRefreshKey] = useState(0);
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
        setIntelligenceStatus(payload.intelligence_status ?? uploadStateView.buildEmptyIntelligenceStatus());
        setSystemsState("ready");
        setBackendError(API_CONFIG_WARNING);
        return true;
      }
      throw new Error("Facility systems payload was incomplete.");
    } catch (error) {
      setSystems(FALLBACK_SYSTEMS);
      setFacilityIntelligence(null);
      setIntelligenceStatus(uploadStateView.buildEmptyIntelligenceStatus());
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
      setLatestUploadSnapshot(payload ?? uploadStateView.buildEmptyLatestUploadSnapshot());
      const latestResult = payload?.latest_result;
      if (uploadStateView.hasFullUploadResult(latestResult)) {
        setLatestUploadResult(latestResult);
        return true;
      }
      setLatestUploadResult(null);
      return false;
    } catch {
      setLatestUploadSnapshot(uploadStateView.buildEmptyLatestUploadSnapshot());
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
  const roomContext = uploadStateView.deriveRoomContext(latestUploadResult);
  const timeCoverage = uploadStateView.deriveTimeCoverage(latestUploadResult);
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
          Panel={Panel}
          MetricGrid={MetricGrid}
          CompactList={CompactList}
          InterventionGrid={(props) => (
            <InterventionGrid
              {...props}
              buildGuidanceForItem={buildGuidanceForItem}
              formatRoomDecisionState={formatRoomDecisionState}
            />
          )}
          WhyPanel={(props) => (
            <WhyPanel
              {...props}
              buildConfidenceBasis={buildConfidenceBasis}
              buildStructuralExplanation={buildStructuralExplanation}
              buildGuidanceForItem={buildGuidanceForItem}
              formatRoomDecisionState={formatRoomDecisionState}
              formatConfidenceLabel={formatConfidenceLabel}
              formatClockTime={formatClockTime}
            />
          )}
          buildGuidanceForItem={buildGuidanceForItem}
          formatFacilityPlainState={formatFacilityPlainState}
          formatScoreReadiness={formatScoreReadiness}
          latestUploadSnapshot={latestUploadSnapshot}
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
          roomContext={roomContext}
          liveOps={liveOps}
          selectedInterventionId={selectedInterventionId}
          onSelectIntervention={setSelectedInterventionId}
          buildFleetSummary={buildFleetSummary}
          buildGuidanceForItem={buildGuidanceForItem}
          formatOperationalTone={formatOperationalTone}
          systemRoomContext={systemRoomContext}
        />
      );
    }

    if (activeWorkspace === "data-connections") {
      return (
        <DataConnectionsWorkspace
          accessCode={apiAccessCode}
          apiFetch={apiFetch}
          apiStatus={apiStatus}
          latestUploadSnapshot={latestUploadSnapshot}
          latestUploadResult={latestUploadResult}
          roomContext={roomContext}
          liveOps={liveOps}
          onUploadComplete={async () => {
            await loadLatestUploadState();
            await loadFacilitySystems();
            await loadEngineIdentity();
            setEvidenceRefreshKey((current) => current + 1);
          }}
          formatClockTime={formatClockTime}
        />
      );
    }

    if (activeWorkspace === "evidence-trail") {
      return (
        <EvidenceTrailWorkspace
          apiFetch={apiFetch}
          readJsonPayload={readJsonPayload}
          normalizeErrorMessage={normalizeErrorMessage}
          formatClockTime={formatClockTime}
          Panel={Panel}
          MetricGrid={MetricGrid}
          CompactList={CompactList}
          EmptyState={EmptyState}
          accessCode={apiAccessCode}
          refreshKey={evidenceRefreshKey}
        />
      );
    }

    return (
      <IntelligenceConsoleWorkspace
        latestUploadResult={latestUploadResult}
        liveOps={liveOps}
        engineIdentity={engineIdentity}
        intelligenceStatus={intelligenceStatus}
        formatRelationshipPair={formatRelationshipPair}
        relationshipDetail={relationshipDetail}
        relationshipConsistencyLabel={relationshipConsistencyLabel}
        runnerTraceLines={runnerTraceLines}
        processingTraceLines={processingTraceLines}
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

const OverviewWorkspace = CommandOverviewWorkspace;
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

async function buildProtectedRequestMessage(response) {
  const payload = await readJsonPayload(response);
  return normalizeErrorMessage(payload?.message ?? payload?.error) || "Session expired. Refresh workspace.";
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
    { label: "Neraium Score", primary: "No active result", secondary: "Complete an upload to calculate a score.", series: [], tone: "info" },
    { label: "Operating State", primary: "No data connected yet", secondary: "This updates from the latest completed upload.", series: [], tone: "info" },
    { label: "Primary Room", primary: "Awaiting upload", secondary: "Room context appears after ingestion completes.", series: [], tone: "info" },
    { label: "Drift", primary: "Awaiting upload", secondary: "Drift and alerts appear after a completed upload.", series: [], tone: "info" },
  ];
}

function buildEmptyOverviewMetrics(systems, systemsState) {
  return [
    { label: "Facility Stability", value: "No data connected yet" },
    { label: "Rooms Under Review", value: 0 },
    { label: "Telemetry Cadence", value: "Awaiting upload" },
    { label: "Systems in Scope", value: systemsState === "ready" ? `${systems.length} monitored` : `${systems.length} defined` },
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

export default App;



