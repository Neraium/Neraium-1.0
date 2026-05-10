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
import { buildOperationalContext as buildFacilityOperationalState } from "./viewModels/operationalState";
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
        message: trigger === "scheduled" ? "Backend sync current." : "Facility sync refreshed.",
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
        setIntelligenceStatus(payload.intelligence_status ?? uploadStateView.buildEmptyIntelligenceStatus());
        setSystemsState("ready");
        setBackendError(API_CONFIG_WARNING);
        return true;
      }
      throw new Error("Facility systems payload was incomplete.");
    } catch (error) {
      setSystems(FALLBACK_SYSTEMS);
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
  const liveOps = buildFacilityOperationalState({
    result: latestUploadResult,
    latestUploadSnapshot,
    apiStatus,
    roomContext,
    systems,
    systemsState,
    intelligenceStatus,
    tick: telemetryTick,
  }, {
    apiStatusWindow,
    actionSetFromTone,
    attributionTone,
    buildConnectionStateStages: uploadStateView.buildConnectionStateStages,
    buildGuidanceFromAttribution,
    buildGuidanceFromCategory,
    buildIntakeStages,
    buildOperationalTranslation,
    buildRoomObservations,
    buildUploadBaselineContext,
    confidenceFromAttribution,
    confidenceFromTone,
    decisionLabelFromTone,
    deriveFacilityStability,
    deriveTimeCoverage: uploadStateView.deriveTimeCoverage,
    formatCategory,
    formatClockTime,
    formatEngineResult,
    formatIntelligenceModeValue,
    formatIntelligenceSourceLabel,
    formatOperationalLabel,
    formatReadiness,
    hasFullUploadResult: uploadStateView.hasFullUploadResult,
    heroHeadlineFromTone,
    heroSublineFromTone,
    impactFromTone,
    inferOperationalCategory,
    isTechnicalEvidenceText,
    mapOperationalTone,
    mapSiiUrgency,
    normalizeFacilityIntelligence,
    operatorMoveFromGuidance,
    recommendationFromTone,
    relationshipDetail,
    reportTemplates: REPORT_TEMPLATES,
    systemRoomContext,
    tonePriority,
    translateEvidenceLine,
    windowLabelFromTone,
    buildWindowContext,
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
            <div className="mobile-status-bar__copy">
              <p className="brand-name">Neraium</p>
              <p className="mobile-status-bar__workspace">{activeConfig.label}</p>
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
            <span>Menu</span>
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
        <div className="workspace-drawer__header">
          <div>
            <p className="sidebar-kicker">Navigation</p>
            <strong>{activeConfig.label}</strong>
          </div>
          <button
            className="workspace-drawer__close"
            type="button"
            aria-label="Close workspace menu"
            onClick={() => setIsWorkspaceMenuOpen(false)}
          >
            Close
          </button>
        </div>
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
    `Grow cycle context: ${roomContext.cycle}.`,
    `Irrigation context: ${roomContext.irrigation}.`,
  ];

  if (result?.operator_report?.time_coverage?.first_timestamp && result?.operator_report?.time_coverage?.last_timestamp) {
    observations.push(
      `Observed time coverage runs from ${result.operator_report.time_coverage.first_timestamp} to ${result.operator_report.time_coverage.last_timestamp}.`,
    );
  }

  return observations;
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
  return "No active result";
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

function buildWhyDrivers(result, telemetryCards, roomContext) {
  const firstCards = telemetryCards.slice(0, 2);
  return [
    firstCards[0] ? `${firstCards[0].label} currently reading ${firstCards[0].primary}.` : `Primary room context: ${roomContext.primary}.`,
    firstCards[1] ? `${firstCards[1].label} currently reading ${firstCards[1].primary}.` : `Secondary room context: ${roomContext.secondary}.`,
    result?.operator_report?.recommended_operator_checks?.[0] ?? "Recommended next move is based on the current room readiness and trend pattern.",
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

function operatorMoveFromGuidance(guidance) {
  return guidance?.nextMove ?? "Continue monitoring";
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



