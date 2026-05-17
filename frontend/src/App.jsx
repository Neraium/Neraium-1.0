import { useCallback, useEffect, useMemo, useState } from "react";
import {
 API_BASE_URL,
 apiFetch,
 API_CONFIG_WARNING,
} from "./config";
import DataConnectionsWorkspace from "./components/DataConnectionsWorkspace";
import StructuralReplayWorkspace from "./components/StructuralReplayWorkspace";
import SystemTopologyWorkspace from "./components/SystemTopologyWorkspace";
import DriftTimelineWorkspace from "./components/DriftTimelineWorkspace";
import EvidenceConsoleWorkspace from "./components/EvidenceConsoleWorkspace";
import FleetWorkspace from "./components/FleetWorkspace";
import StructuralOntologyWorkspace from "./components/StructuralOntologyWorkspace";
import EcosystemWorkspace from "./components/EcosystemWorkspace";
import DistributedCognitionWorkspace from "./components/DistributedCognitionWorkspace";
import OperatorTrainingWorkspace from "./components/OperatorTrainingWorkspace";
import InfrastructureBehaviorScienceWorkspace from "./components/InfrastructureBehaviorScienceWorkspace";
import OperatorCognitionTrainingWorkspace from "./components/OperatorCognitionTrainingWorkspace";
import StructuralCognitionResearchWorkspace from "./components/StructuralCognitionResearchWorkspace";
import OperatorWorkflowWorkspace from "./components/OperatorWorkflowWorkspace";
import CultivationMissionControl from "./components/cultivation/CultivationMissionControl";
import CultivationEvidenceWorkspace from "./components/cultivation/CultivationEvidenceWorkspace";
import PropagationWorkspace from "./components/PropagationWorkspace";
import AppShell from "./components/AppShell";
import AppErrorBoundary from "./components/AppErrorBoundary";
import {
  EmptyState,
  MetricGrid,
  Panel,
  StatusDot,
} from "./components/workspacePrimitives";
import {
  formatOperationalLabel,
} from "./viewModels/operationalHelpers";
import { buildOperationalContext as buildFacilityOperationalState } from "./viewModels/operationalState";
import {
  buildIntakeStages,
  normalizeErrorMessage,
} from "./viewModels/uploadFlow";
import { normalizeOperationalState } from "./viewModels/operationalUiState";
import * as uploadStateView from "./viewModels/uploadState";
import { INTAKE_STAGES, REPORT_TEMPLATES } from "./config/workspaces";
import useWorkspaceNavigation from "./hooks/useWorkspaceNavigation";
import useFacilityRuntime from "./hooks/useFacilityRuntime";
import { resetDemoSession } from "./services/api/uploadApi";

function App() { 
  const hasAccess = true;
  const apiAccessCode = "";
  const [evidenceRefreshKey, setEvidenceRefreshKey] = useState(0);
  const [preferredEvidenceRunId, setPreferredEvidenceRunId] = useState(null);
  const [selectedTopologyTarget, setSelectedTopologyTarget] = useState(null);
  const [driftHistory, setDriftHistory] = useState([]);
  const [autoReplay, setAutoReplay] = useState({ key: 0, targetTone: "nominal", active: false });
  const [sessionIntent, setSessionIntent] = useState("neutral");
  const {
    telemetryTick,
    apiStatus,
    systems,
    systemsState,
    intelligenceStatus,
    latestUploadResult,
    latestUploadSnapshot,
    demoScenario,
    setDemoScenario,
    isDemoMode,
    setIsDemoMode,
    loadFacilitySystems,
    loadLatestUploadState,
    setAllowPersistedLatest,
  } = useFacilityRuntime({
    hasAccess,
    accessCode: apiAccessCode,
    formatClockTime,
    formatEndpoint,
    buildProtectedRequestMessage,
  });
  const onWorkspaceSelect = useCallback((workspaceId) => {
    if (workspaceId !== "drift-timeline" && autoReplay.active) {
      setAutoReplay((current) => ({ ...current, active: false }));
    }
  }, [autoReplay.active]);
  const {
    activeWorkspace,
    setActiveWorkspace,
    activeConfig,
    expertMode,
    setExpertMode,
    visibleWorkspaces,
    isWorkspaceMenuOpen,
    setIsWorkspaceMenuOpen,
    workspaceRef,
    workspaceDrawerRef,
    handleWorkspaceSelect,
  } = useWorkspaceNavigation({ onWorkspaceSelect });
  const hasRealSiiOutput = useMemo(
    () => uploadStateView.hasFullUploadResult(latestUploadResult),
    [latestUploadResult],
  );
  const hasCurrentUploadResult = sessionIntent === "current" && hasRealSiiOutput;
  const hasResumedSession = sessionIntent === "resumed" && hasRealSiiOutput;
  const hasActiveSession = hasCurrentUploadResult || hasResumedSession;
  const effectiveLatestUploadResult = hasActiveSession ? latestUploadResult : null;
  const effectiveLatestUploadSnapshot = hasActiveSession
    ? latestUploadSnapshot
    : uploadStateView.buildEmptyLatestUploadSnapshot();
  const roomContext = useMemo(() => uploadStateView.deriveRoomContext(effectiveLatestUploadResult), [effectiveLatestUploadResult]);
  const timeCoverage = useMemo(() => uploadStateView.deriveTimeCoverage(effectiveLatestUploadResult), [effectiveLatestUploadResult]);
  const runtimeLiveOps = useMemo(() => buildFacilityOperationalState({ 
    result: effectiveLatestUploadResult,
    latestUploadSnapshot: effectiveLatestUploadSnapshot,
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
  }), [apiStatus, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, intelligenceStatus, roomContext, systems, systemsState, telemetryTick]); 
  const liveOps = runtimeLiveOps;
  const relationshipMagnitude = useMemo(
    () => (liveOps.relationshipRows ?? [])
      .map((row) => Number(row.pair_weight ?? row.change))
      .filter((value) => Number.isFinite(value))
      .reduce((sum, value) => sum + Math.abs(value), 0),
    [liveOps.relationshipRows],
  );
  const driftMagnitude = useMemo(
    () => (liveOps.driftRows ?? [])
      .map((row) => Number(row.absolute_change))
      .filter((value) => Number.isFinite(value))
      .reduce((sum, value) => sum + Math.abs(value), 0),
    [liveOps.driftRows],
  );
  const baselineDistance = useMemo(
    () => Number((relationshipMagnitude + driftMagnitude).toFixed(3)),
    [driftMagnitude, relationshipMagnitude],
  );

  useEffect(() => {
    const stamp = formatClockTime(new Date());

    setDriftHistory((current) => {
      const previousTone = current.length > 0 ? current[current.length - 1].tone : "nominal";
      const previousRank = previousTone === "unstable" || previousTone === "elevated" ? 2 : previousTone === "review" ? 1 : 0;
      const escalateToReview = baselineDistance >= 0.16;
      const escalateToSeparation = baselineDistance >= 0.36;
      const deescalateToReview = baselineDistance <= 0.31;
      const deescalateToStable = baselineDistance <= 0.11;

      let smoothedTone = previousTone;
      if (previousRank <= 0) {
        smoothedTone = escalateToReview ? "review" : "nominal";
      } else if (previousRank === 1) {
        if (escalateToSeparation) {
          smoothedTone = "elevated";
        } else if (deescalateToStable) {
          smoothedTone = "nominal";
        } else {
          smoothedTone = "review";
        }
      } else {
        smoothedTone = deescalateToReview ? "review" : "elevated";
      }

      const velocity = current.length > 0
        ? Number((baselineDistance - current[current.length - 1].distance).toFixed(3))
        : 0;
      const acceleration = current.length > 1
        ? Number((velocity - current[current.length - 1].velocity).toFixed(3))
        : 0;
      const next = [...current, { stamp, distance: baselineDistance, velocity, acceleration, tone: smoothedTone }];
      return next.slice(-48);
    });
  }, [baselineDistance, liveOps.connectionSummary, telemetryTick]);

  const handleResetDemo = useCallback(async () => {
    try {
      await resetDemoSession({ apiFetch, accessCode: apiAccessCode });
    } catch {
      // Continue with client reset even if backend reset is unavailable.
    }

    if (typeof window !== "undefined") {
      try {
        const keysToRemove = [];
        for (let index = 0; index < window.localStorage.length; index += 1) {
          const key = window.localStorage.key(index);
          if (key && key.toLowerCase().includes("neraium")) {
            keysToRemove.push(key);
          }
        }
        keysToRemove.forEach((key) => window.localStorage.removeItem(key));
        window.sessionStorage.clear();
      } catch {
        // Ignore storage cleanup failures to avoid blocking reset UX.
      }
    }

    setIsDemoMode(false);
    setDemoScenario("drift");
    setDriftHistory([]);
    setPreferredEvidenceRunId(null);
    setSelectedTopologyTarget(null);
    setSessionIntent("neutral");
    setAllowPersistedLatest(false);
    await loadLatestUploadState({ includePersisted: false });
    await loadFacilitySystems();
    setActiveWorkspace("data-connections");
  }, [apiAccessCode, apiFetch, loadFacilitySystems, loadLatestUploadState, setActiveWorkspace, setAllowPersistedLatest, setDemoScenario, setIsDemoMode]);

  const handleResumePreviousSession = useCallback(async () => {
    setAllowPersistedLatest(true);
    const hasResult = await loadLatestUploadState({ includePersisted: true });
    setSessionIntent(hasResult ? "resumed" : "neutral");
    await loadFacilitySystems();
    setActiveWorkspace("system-body");
  }, [loadFacilitySystems, loadLatestUploadState, setActiveWorkspace, setAllowPersistedLatest]);

  function renderActiveWorkspace() { 
    if (activeWorkspace === "cultivation-mission-control") {
      return (
        <CultivationMissionControl
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          isDemoMode={isDemoMode}
          expertMode={expertMode}
          onRunPilotDemo={() => {
            setActiveWorkspace("cultivation-mission-control");
          }}
          hasUploadedTelemetry={hasActiveSession}
          Panel={Panel}
          MetricGrid={MetricGrid}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "cultivation-evidence") {
      return (
        <CultivationEvidenceWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          Panel={Panel}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "propagation-map") {
      return (
        <PropagationWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          isDemoMode={isDemoMode}
          expertMode={expertMode}
          normalizeErrorMessage={normalizeErrorMessage}
          Panel={Panel}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "operator-workflow") {
      return (
        <OperatorWorkflowWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          normalizeErrorMessage={normalizeErrorMessage}
          formatClockTime={formatClockTime}
          Panel={Panel}
          MetricGrid={MetricGrid}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "system-body") { 
      return <SystemTopologyWorkspace liveOps={liveOps} selectedTarget={selectedTopologyTarget} onSelectTarget={setSelectedTopologyTarget} />; 
    } 
 
    if (activeWorkspace === "drift-timeline") { 
      return (
        <DriftTimelineWorkspace
          liveOps={liveOps}
          driftHistory={driftHistory}
          autoReplay={autoReplay}
          latestUploadResult={effectiveLatestUploadResult}
          latestUploadSnapshot={effectiveLatestUploadSnapshot}
          hasActiveSession={hasActiveSession}
          hasCurrentUploadResult={hasCurrentUploadResult}
          isDemoMode={isDemoMode}
        />
      ); 
    } 

    if (activeWorkspace === "data-connections") {
      return (
        <DataConnectionsWorkspace
          accessCode={apiAccessCode}
          apiFetch={apiFetch}
          apiStatus={apiStatus}
          latestUploadSnapshot={effectiveLatestUploadSnapshot}
          latestUploadResult={effectiveLatestUploadResult}
          hasActiveSession={hasActiveSession}
          hasResumedSession={hasResumedSession}
          hasCurrentUploadResult={hasCurrentUploadResult}
          hasRealSiiOutput={hasRealSiiOutput}
          roomContext={roomContext}
          onUploadComplete={async () => {
            setIsDemoMode(false);
            setAllowPersistedLatest(true);
            setDriftHistory([]);
            const hasResult = await loadLatestUploadState({ includePersisted: true });
            setSessionIntent(hasResult ? "current" : "neutral");
            await loadFacilitySystems();
            setEvidenceRefreshKey((current) => current + 1);
            setActiveWorkspace("drift-timeline");
            setAutoReplay((current) => ({
              key: current.key + 1,
              targetTone: "nominal",
              active: true,
            }));
          }}
          onResetDemo={handleResetDemo}
          onResumePreviousSession={handleResumePreviousSession}
          formatClockTime={formatClockTime}
        />
      );
    }

    if (activeWorkspace === "historical-replay") {
      return (
        <StructuralReplayWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          expertMode={expertMode}
          normalizeErrorMessage={normalizeErrorMessage}
          formatClockTime={formatClockTime}
          Panel={Panel}
          MetricGrid={MetricGrid}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "fleet-view") {
      return (
        <FleetWorkspace
          liveOps={liveOps}
          latestUploadSnapshot={effectiveLatestUploadSnapshot}
          driftHistory={driftHistory}
          isDemoMode={isDemoMode}
          demoScenario={demoScenario}
          telemetryTick={telemetryTick}
          onOpenFacility={(facility) => {
            setPreferredEvidenceRunId(facility?.runId ?? null);
            setActiveWorkspace("historical-replay");
            setIsWorkspaceMenuOpen(false);
          }}
        />
      );
    }

    if (activeWorkspace === "structural-ontology") {
      return (
        <StructuralOntologyWorkspace
          intelligence={effectiveLatestUploadResult?.sii_intelligence ?? null}
          Panel={Panel}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "ecosystem-workspace") {
      return (
        <EcosystemWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          formatClockTime={formatClockTime}
          Panel={Panel}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "distributed-cognition") {
      return (
        <DistributedCognitionWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          Panel={Panel}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "operator-training") {
      return (
        <OperatorTrainingWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          Panel={Panel}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "behavior-science") {
      return (
        <InfrastructureBehaviorScienceWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          Panel={Panel}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "operator-cognition-training") {
      return (
        <OperatorCognitionTrainingWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          Panel={Panel}
          EmptyState={EmptyState}
        />
      );
    }

    if (activeWorkspace === "structural-cognition-research") {
      return (
        <StructuralCognitionResearchWorkspace
          apiFetch={apiFetch}
          accessCode={apiAccessCode}
          Panel={Panel}
          EmptyState={EmptyState}
        />
      );
    }
 
    return <EvidenceConsoleWorkspace liveOps={liveOps} selectedTarget={selectedTopologyTarget} />; 
  } 

  return (
    <AppErrorBoundary>
      <AppShell
        activeWorkspace={activeWorkspace}
        workspaceRef={workspaceRef}
        workspaceDrawerRef={workspaceDrawerRef}
        visibleWorkspaces={visibleWorkspaces}
        expertMode={expertMode}
        onToggleExpertMode={() => setExpertMode((current) => !current)}
        activeConfig={activeConfig}
        apiStatus={apiStatus}
        latestUploadResult={effectiveLatestUploadResult}
        roomContext={roomContext}
        timeCoverage={timeCoverage}
        liveOps={liveOps}
        onSelectWorkspace={handleWorkspaceSelect}
        isWorkspaceMenuOpen={isWorkspaceMenuOpen}
        setIsWorkspaceMenuOpen={setIsWorkspaceMenuOpen}
        isDemoMode={isDemoMode}
        onToggleDemoMode={() => {}}
        demoScenario={demoScenario}
        onSetDemoScenario={setDemoScenario}
        renderActiveWorkspace={renderActiveWorkspace}
        formatReadiness={formatReadiness}
        formatIntelligenceSourceLabel={formatIntelligenceSourceLabel}
        deriveTriageSummary={deriveTriageSummary}
      />
    </AppErrorBoundary>
  );
}

function TopStatusBar({
  activeConfig,
  apiStatus,
  latestUploadResult,
  roomContext,
  timeCoverage,
  liveOps,
  isDemoMode,
  onToggleDemoMode,
  demoScenario,
  onSetDemoScenario,
}) {
  const intelligenceLabel = formatIntelligenceSourceLabel(liveOps.intelligenceMode);
  const triageSummary = deriveTriageSummary(liveOps, roomContext);
  const uiState = normalizeOperationalState(liveOps.facilityTone);
  return (
    <header className="top-status"> 
      <div className="top-status__title"> 
        <p className="eyebrow">Neraium Command • {activeConfig.eyebrow}</p> 
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

      <div className={`top-status__brief top-status__brief--${liveOps.facilityTone} ui-state-surface ui-state-surface--${uiState}`}>
        <article className="top-status__brief-item">
          <span>What&apos;s wrong</span>
          <strong>{triageSummary.problem}</strong>
        </article>
        <article className="top-status__brief-item">
          <span>Where</span>
          <strong>{triageSummary.where}</strong>
        </article>
        <article className="top-status__brief-item top-status__brief-item--wide">
          <span>Why we think that</span>
          <p>{triageSummary.why}</p>
        </article>
        <article className="top-status__brief-item top-status__brief-item--wide">
          <span>Human read</span>
          <p>{triageSummary.human}</p>
        </article>
      </div>

      <div className="status-rack">
        <StatusChip
          label="Severity"
          value={liveOps.facilityStateLabel}
          tone={liveOps.facilityTone}
        />
        <StatusChip
          label="Primary room"
          value={roomContext.primary}
          tone={liveOps.facilityTone}
        />
        <StatusChip
          label="Next inspect"
          value={liveOps.primaryWindow?.label ?? "Facility overview"}
          tone={liveOps.primaryWindow?.tone ?? "info"}
        />
        <StatusChip
          label="Projected lead time"
          value={liveOps.primaryWindow?.window ?? "Monitoring"}
          tone={liveOps.primaryWindow?.tone ?? liveOps.connectionTone}
        />
        <StatusChip
          label="What changed"
          value={latestUploadResult?.data_quality ? formatReadiness(latestUploadResult.data_quality?.readiness) : liveOps.readinessLabel}
          tone={latestUploadResult?.data_quality?.readiness ?? liveOps.connectionTone}
        />
        <button className="secondary-command-button" type="button" onClick={onToggleDemoMode}>
          {isDemoMode ? "Sample On" : "Sample Off"}
        </button>
        {isDemoMode && (
          <>
            <button className={`secondary-command-button ${demoScenario === "stable" ? "is-active" : ""}`} type="button" onClick={() => onSetDemoScenario("stable")}>
              Stable
            </button>
            <button className={`secondary-command-button ${demoScenario === "drift" ? "is-active" : ""}`} type="button" onClick={() => onSetDemoScenario("drift")}>
              Drift
            </button>
            <button className={`secondary-command-button ${demoScenario === "separation" ? "is-active" : ""}`} type="button" onClick={() => onSetDemoScenario("separation")}>
              Separation
            </button>
          </>
        )}
      </div>
    </header>
  );
}

function deriveTriageSummary(liveOps, roomContext) {
  const tone = liveOps.facilityTone;
  const firstFinding = liveOps.findings?.[0];
  const secondFinding = liveOps.findings?.[1];
  const firstEvidence = liveOps.evidenceLines?.find(Boolean);
  const firstRelationship = liveOps.relationshipRows?.[0]?.detail;
  const recommendation = liveOps.interventionItems?.[0]?.recommendation;
  const focusRoom = roomContext?.primary ?? liveOps.primaryWindow?.label ?? "Facility overview";
  const why = firstFinding?.detail
    || firstRelationship
    || firstEvidence
    || liveOps.heroSubline
    || "The platform is comparing live system behavior against the facility's recent operating baseline.";

  if (tone === "nominal" || tone === "info") {
    return {
      problem: "No active failure signal right now.",
      where: focusRoom,
      why,
      human: recommendation || "The structure looks steady, but we are still watching for early relationship shifts before they become hard failures.",
    };
  }

  return {
    problem: firstFinding?.title || liveOps.facilityStateLabel || "System behavior is off baseline.",
    where: liveOps.primaryWindow?.label || focusRoom,
    why,
    human: recommendation || secondFinding?.detail || liveOps.connectionActionHint || "This is an operational reasoning signal, not just a threshold breach, so the app is flagging the pattern before the room becomes harder to control.",
  };
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
    facility_state: "Baseline Pending",
    room_state: "Baseline Pending",
    urgency: "nominal",
    intervention_window: "Baseline Pending",
    neraium_score: null,
    primary_room: "Awaiting uploaded telemetry",
    priority_room: null,
    primary_driver: "Awaiting uploaded telemetry",
    supporting_evidence: ["No active telemetry session is available yet."],
    relationship_evidence: [],
    structural_explanation: ["Awaiting completed runner output."],
    confidence_basis: "Awaiting completed runner output",
    recommended_operator_review: "Awaiting uploaded telemetry",
    next_operator_move: "Awaiting uploaded telemetry",
    what_to_check: ["Connect telemetry or upload a dataset"],
    why_flagged: "No active telemetry session",
    baseline_comparison: "Baseline Pending",
    observed_persistence: "Baseline Pending",
    projected_time_to_failure: "Baseline Pending",
    projected_time_to_failure_hours: null,
    last_updated: new Date().toISOString(),
    rooms: [],
    structural_memory: { memory_matches: [], active_fingerprint: null, retrieval_status: "pending" },
    active_fingerprint: null,
    active_archetypes: [],
    causality_graph: { nodes: [], edges: [], dominant_pathways: [], source_localization: null },
    counterfactuals: { progression_scenarios: [], uncertainty_ranges: {}, structural_continuation_pathways: [] },
    facility_cognition: { facility_cognition_state: "Awaiting facility cognition", global_structural_pressure_score: 0, subsystem_pressure: { subsystems: {} } },
    operator_explanation_v2: {
      summary: "Awaiting structural cognition output.",
      active_archetypes: [],
      propagation_pathways: [],
      structural_memory_matches: [],
      subsystem_causality_summary: [],
      counterfactual_continuation_windows: {},
      recovery_convergence_indicators: [],
    },
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
    active_archetypes: Array.isArray(intelligence.active_archetypes) ? intelligence.active_archetypes : safe.active_archetypes,
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
  return "No Active Session";
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
  if (mode === "sample") {
    return "Sample mode";
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
  if (mode === "sample") {
    return "sample";
  }
  if (mode === "processing") {
    return "processing";
  }
  if (mode === "empty") {
    return "no_data";
  }
  return mode ?? "unknown";
}

function buildDemoLiveOps(tick = 0, scenario = "drift") {
  const phase = tick % 4;
  const tone = scenario === "stable"
    ? "nominal"
    : scenario === "separation"
      ? "elevated"
      : (phase <= 1 ? "review" : "elevated");
  const drift = scenario === "stable"
    ? 0.09
    : scenario === "separation"
      ? 0.82
      : (phase <= 1 ? 0.42 : 0.71);
  const headline = scenario === "stable"
    ? "Facility relationships are coherent and stable."
    : scenario === "separation"
      ? "Structural separation is propagating across zones."
      : "Thermal-humidity coupling is weakening before endpoint alarms.";
  const subline = scenario === "stable"
    ? "All major zone relationships are operating inside baseline tolerance."
    : scenario === "separation"
      ? "HVAC, irrigation, and airflow clusters are fragmenting from baseline."
      : "HVAC and irrigation signals are decoupling while room metrics still look nominal.";
  return {
    useDemoTelemetry: true,
    intelligenceMode: "sample",
    facilityTone: tone,
    facilityStateLabel: tone === "nominal" ? "Stable structure" : tone === "elevated" ? "Structural separation forming" : "Relationship drift detected",
    heroTag: "Sample scenario",
    heroHeadline: headline,
    heroSubline: subline,
    readinessLabel: "Operational Intelligence Active",
    connectionTone: "nominal",
    connectionLabel: "Sample stream",
    connectionDetail: "Synthetic operational state for walkthroughs.",
    connectionSummary: "Sample loop active",
    connectionStatusLine: "Sample mode enabled. Production outputs are paused in this view.",
    connectionActionHint: "Switch sample mode off to return to backend SII telemetry.",
    dataSourceLabel: "Sample facility",
    neraiumScore: tone === "nominal" ? 93 : tone === "elevated" ? 46 : 74,
    scoreNarrative: tone === "nominal"
      ? "Structural integrity is holding with low drift velocity."
      : "Structural drift is accumulating faster than endpoint thresholds.",
    scoreContext: "Sample score tracks relationship integrity rather than raw sensor values.",
    windowContext: "Intervention window is compressing from 2 days toward 8 hours.",
    primaryWindow: { label: "Flower Room 1", tone, status: "Drift window", window: "12 hours" },
    interventionItems: [{
      id: "demo-hvac-irrigation",
      label: "Flower Room 1",
      title: "HVAC x Irrigation coupling",
      status: tone === "nominal" ? "Stable Structure" : "Relationship Drift",
      window: tone === "nominal" ? "3 weeks" : "12 hours",
      tone,
      confidence: 88,
      summary: tone === "nominal"
        ? "Thermal-humidity coupling remains inside baseline tolerance."
        : "Thermal-humidity coupling has weakened persistently over the last 8 hours.",
      recommendation: tone === "nominal"
        ? "Continue monitoring structural coherence."
        : "Inspect airflow and irrigation timing overlap.",
      supportingEvidence: [
        tone === "nominal"
          ? "HVAC recovery timing remains within 2 minutes of baseline."
          : "HVAC recovery lags humidity stabilization by 14 minutes vs baseline.",
        tone === "nominal"
          ? "Irrigation response variance remains below 5%."
          : "Irrigation event response variance increased 29% in current window.",
      ],
      relationshipEvidence: [ 
        tone === "nominal" 
          ? "temperature_supply::humidity_room correlation remains stable at 0.84" 
          : "temperature_supply::humidity_room correlation dropped from 0.82 to 0.41", 
        tone === "nominal"
          ? "hvac_runtime::irrigation_cycle correlation remains stable at 0.66"
          : "hvac_runtime::irrigation_cycle correlation dropped from 0.67 to 0.18",
      ],
    }],
    actionQueue: [],
    topologyNodes: [],
    alerts: [{ title: tone === "nominal" ? "Stable structure" : "Hidden drift", detail: tone === "nominal" ? "System coherence is within normal operating bounds." : "No hard threshold breach yet, but structure is separating.", tone }],
    findings: [
      { title: tone === "nominal" ? "Coherence confirmed" : "HVAC-Irrigation tension", detail: tone === "nominal" ? "Coupling has remained stable across monitored windows." : "Coupling drift has persisted across multiple windows.", tone },
      { title: "Velocity", detail: tone === "nominal" ? "Drift velocity remains flat." : "Drift acceleration turned positive in last two cycles.", tone: "review" },
      { title: "Intervention posture", detail: tone === "nominal" ? "No immediate action required." : "System still controllable if addressed now.", tone: "nominal" },
    ],
    timeline: [],
    telemetryCards: [],
    summaryTelemetry: [],
    overviewMetrics: [],
    roomCards: [],
    roomTransitions: [],
    driftRows: [{
      column: "structural_distance",
      direction: "up",
      drift_flag: tone,
      baseline_average: 0.12,
      recent_average: drift,
      absolute_change: Number((drift - 0.12).toFixed(3)),
      detail: "Distance from baseline is rising with positive acceleration.",
    }],
    relationshipRows: [
      {
        pair_key: "hvac_runtime::irrigation_cycle",
        pair_categories: ["hvac", "irrigation"],
        pair_weight: tone === "nominal" ? 0.04 : 0.49,
        columns: ["hvac_runtime", "irrigation_cycle"],
        baseline_correlation: 0.67,
        recent_correlation: tone === "nominal" ? 0.66 : 0.18,
        change: tone === "nominal" ? -0.01 : -0.49,
        tone,
        detail: "HVAC runtime and irrigation cycle relationship drifted from baseline.",
      },
      {
        pair_key: "temperature_supply::humidity_room",
        pair_categories: ["temperature", "humidity"],
        pair_weight: tone === "nominal" ? 0.03 : 0.41,
        columns: ["temperature_supply", "humidity_room"],
        baseline_correlation: 0.82,
        recent_correlation: tone === "nominal" ? 0.84 : 0.41,
        change: tone === "nominal" ? 0.02 : -0.41,
        tone: "review",
        detail: "Temperature and humidity coupling is degrading gradually.",
      },
    ],
    irrigationNotes: [],
    systemRows: [],
    intakeStages: [],
    evidenceLines: [
      "sample.mode=true",
      `sample.structural_distance=${drift}`,
      `sample.scenario=${scenario}`,
    ],
    consoleEvents: [],
    observations: [],
    reportNotes: [],
    connectionEvents: [],
  };
}

export default App;

