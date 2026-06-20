import { Suspense, lazy, useCallback, useEffect, useMemo, useState } from "react";
import { apiFetch } from "./config";
import { ENABLE_ADMISSION_GATE } from "./config";
import SystemTopologyWorkspace from "./components/SystemTopologyWorkspace";
import DataConnectionsWorkspace from "./components/DataConnectionsWorkspace";
import { EmptyState, MetricGrid, Panel } from "./components/workspacePrimitives";
import AppErrorBoundary from "./components/AppErrorBoundary";
import useFacilityRuntime from "./hooks/useFacilityRuntime";
import useWorkspaceSessionController, { readStoredAllowPersistedLatest } from "./hooks/useWorkspaceSessionController";
import { classifyDataFreshness, deriveIntelligenceMode } from "./viewModels/systemState";
import { buildSessionStore } from "./viewModels/sessionState";
import { logoutUser } from "./services/api/authApi";

const StructuralReplayWorkspace = lazy(() => import("./components/StructuralReplayWorkspace"));
const GovernanceAdminWorkspace = lazy(() => import("./components/GovernanceAdminWorkspace"));
const ObservationCenterWorkspace = lazy(() => import("./components/ObservationCenterWorkspace"));
const HelpChangelogWorkspace = lazy(() => import("./components/HelpChangelogWorkspace"));

function App() {
  const accessCode = "";
  const [activeWorkspace, setActiveWorkspace] = useState("system-body");
  const [appReady, setAppReady] = useState(false);
  const initialAllowPersistedLatest = readStoredAllowPersistedLatest();

  const {
    apiStatus,
    systems,
    systemsState,
    intelligenceStatus,
    latestUploadResult,
    latestUploadSnapshot,
    sessionStore,
    domainDetection,
    setIsDemoMode,
    loadFacilitySystems,
    loadLatestUploadState,
    allowPersistedLatest,
    setAllowPersistedLatest,
    clearUploadSessionState,
    telemetryTick,
    domainMode,
  } = useFacilityRuntime({
    hasAccess: true,
    accessCode,
    formatClockTime,
    formatEndpoint,
    buildProtectedRequestMessage,
    initialAllowPersistedLatest,
  });

  const resolvedSessionStore = useMemo(() => sessionStore ?? buildSessionStore({
    snapshot: latestUploadSnapshot,
    latest_result: latestUploadResult,
    session_state: latestUploadSnapshot?.session_state ?? (latestUploadResult ? "verified" : (latestUploadSnapshot?.status ?? "empty")),
  }, { loaded: true }), [latestUploadResult, latestUploadSnapshot, sessionStore]);

  const {
    historianReplayState,
    errorBoundaryResetKey,
    effectiveLatestUploadResult,
    effectiveLatestUploadSnapshot,
    hasCurrentUploadResult,
    hasResumedSession,
    hasActiveSession,
    hasRealSiiOutput,
    roomContext,
    currentSession,
    canonicalFinding,
    telemetrySession,
    gateProcessing,
    handleReplayFrameChange,
    handleReplayModeChange,
    handleGateUploadComplete,
    handleResumePreviousSession,
    handleResetDemo,
    handleBackToGate,
    handleRetryWorkspace,
  } = useWorkspaceSessionController({
    activeWorkspace,
    setActiveWorkspace,
    apiFetch,
    accessCode,
    sessionStore: resolvedSessionStore,
    loadFacilitySystems,
    loadLatestUploadState,
    allowPersistedLatest,
    setAllowPersistedLatest,
    clearUploadSessionState,
    setIsDemoMode,
  });

  const liveOps = useMemo(() => {
    const intelligence = effectiveLatestUploadResult?.sii_intelligence ?? null;
    const governance =
      intelligence?.aletheia_gate
      ?? intelligence?.distributed_cognition_governance
      ?? effectiveLatestUploadResult?.distributed_cognition_governance
      ?? null;
    const admittedState = String(governance?.admitted_state ?? "").toUpperCase();
    const gateOutcome = String(governance?.gate_outcome ?? "").toUpperCase();
    const hasPass = ENABLE_ADMISSION_GATE && gateOutcome === "PASS" && ["WATCH", "ALERT"].includes(admittedState);
    const uploadTone = deriveUploadTone(effectiveLatestUploadResult);

    const heartbeatSource = telemetrySession.heartbeatAt;
    const hasTelemetryHeartbeat = Boolean(heartbeatSource);
    const facilityTone = hasTelemetryHeartbeat
      ? (hasPass
        ? admittedState === "ALERT"
          ? "critical"
          : "watch"
        : uploadTone)
      : telemetrySession.sessionMode === "persisted"
        ? "watch"
        : "empty";

    const intelligenceMode = hasTelemetryHeartbeat
      ? deriveIntelligenceMode({
        hasRealSiiOutput,
        latestUploadSnapshot: effectiveLatestUploadSnapshot,
      })
      : "empty";
    const connectionSummary = heartbeatSource
      ? `Updated ${formatClockTime(heartbeatSource)} CT`
      : null;
    const connectionStatusLine = apiStatus.state === "online"
      ? telemetrySession.statusLabel
      : "Connection degraded";
    const dataFreshness = classifyDataFreshness({
      heartbeatAt: heartbeatSource,
      online: apiStatus.state === "online",
    });
    const siiVerification = {
      verified: Boolean(hasRealSiiOutput || effectiveLatestUploadSnapshot?.sii_completed === true),
      artifacts: effectiveLatestUploadSnapshot?.sii_completion_artifacts || {},
    };

    return {
      facilityTone,
      intelligenceMode,
      connectionTone: apiStatus.state === "online" ? "online" : "degraded",
      connectionSummary,
      connectionStatusLine,
      lastDataHeartbeat: heartbeatSource,
      dataFreshness,
      siiVerification,
      primaryWindow: {
        label: governance?.affected_subsystem ?? roomContext.primary,
        window: governance?.elapsed_operational_duration ?? "Governed window active",
      },
      findings: hasPass
        ? [{ detail: governance?.why_summary ?? canonicalFinding.summary ?? "Admitted governed finding active." }]
        : (canonicalFinding.exists ? [{ detail: canonicalFinding.summary }] : []),
      interventionItems: hasPass
        ? [{
          label: governance?.affected_subsystem ?? roomContext.primary,
          recommendation: governance?.operator_focus ?? "Review admitted structural relationship path.",
          window: governance?.elapsed_operational_duration ?? "Governed window active",
          confidence: 90,
          relationshipEvidence: [governance?.affected_relationship_path ?? "Admitted relationship path"],
        }]
        : (canonicalFinding.exists ? [{
          label: roomContext.primary,
          recommendation: canonicalFinding.reviewNext,
          window: canonicalFinding.technicalDetails?.find((item) => item.label === "Behavior duration")?.value ?? "Current observation",
          confidence: canonicalFinding.confidence === "High" ? 90 : canonicalFinding.confidence === "Moderate" ? 70 : 50,
          relationshipEvidence: canonicalFinding.supportingEvidence ?? [],
        }] : []),
      relationshipRows: effectiveLatestUploadResult?.baseline_analysis?.relationship_drift ?? [],
      distributed_cognition_governance: governance,
      sourceIntelligence: intelligence,
      latestUploadResult: effectiveLatestUploadResult,
      latestUploadSnapshot: effectiveLatestUploadSnapshot,
      currentSession,
      telemetrySession,
      session: resolvedSessionStore,
      systems,
      systemsState,
      intelligenceStatus,
      telemetryTick,
    };
  }, [apiStatus.state, canonicalFinding, currentSession, effectiveLatestUploadResult, effectiveLatestUploadSnapshot, hasRealSiiOutput, intelligenceStatus, resolvedSessionStore, roomContext.primary, systems, systemsState, telemetrySession, telemetryTick]);

  const handleSignOut = useCallback(async () => {
    await logoutUser();
  }, []);


  useEffect(() => {
    if (typeof document === "undefined") return;
    if (domainMode) {
      document.documentElement.setAttribute("data-domain-mode", domainMode);
    } else {
      document.documentElement.removeAttribute("data-domain-mode");
    }
  }, [domainMode]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    setAppReady(true);
    window.__NERAIUM_APP_READY__ = true;
  }, []);

  function renderWithBackControl(content) {
    return (
      <AppErrorBoundary resetKey={errorBoundaryResetKey} onRetry={handleRetryWorkspace}>
        <div className="workspace-shell-with-back" style={{ minHeight: "100svh" }}>
          <div className="workspace-back-control" aria-label="Workspace navigation">
            <button
              type="button"
              className="system-gate__settings-action"
              onClick={handleBackToGate}
              aria-label="Back to Gate"
            >
              Back to Gate
            </button>
          </div>
          {content}
        </div>
      </AppErrorBoundary>
    );
  }

  if (activeWorkspace === "data-connections") {
    return renderWithBackControl(
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
      <DataConnectionsWorkspace
        accessCode={accessCode}
        apiFetch={apiFetch}
        apiStatus={apiStatus}
        latestUploadSnapshot={effectiveLatestUploadSnapshot}
        latestUploadResult={effectiveLatestUploadResult}
        hasActiveSession={hasActiveSession}
        hasResumedSession={hasResumedSession}
        hasCurrentUploadResult={hasCurrentUploadResult}
        hasRealSiiOutput={hasRealSiiOutput}
        roomContext={roomContext}
        onUploadComplete={handleGateUploadComplete}
        onResetDemo={handleResetDemo}
        onResumePreviousSession={handleResumePreviousSession}
        formatClockTime={formatClockTime}
      />
      </div>
    );
  }

  if (activeWorkspace === "historical-replay") {
    return renderWithBackControl(
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
      <Suspense fallback={<div className="workspace-grid"><Panel title="Loading Replay" className="span-12"><p className="narrative-text">Preparing replay workspace...</p></Panel></div>}>
        <StructuralReplayWorkspace
          apiFetch={apiFetch}
          accessCode={accessCode}
          expertMode={false}
          normalizeErrorMessage={(value) => String(value ?? "")}
          formatClockTime={formatClockTime}
          Panel={Panel}
          MetricGrid={MetricGrid}
          EmptyState={EmptyState}
          hasActiveSession={hasActiveSession}
          hasCurrentUploadResult={hasCurrentUploadResult}
          hasResumedSession={hasResumedSession}
          hasRealSiiOutput={hasRealSiiOutput}
          currentSession={currentSession}
          canonicalFinding={canonicalFinding}
          domainMode={domainMode}
          onReplayFrameChange={handleReplayFrameChange}
          onReplayModeChange={handleReplayModeChange}
        />
      </Suspense>
      </div>
    );
  }

  if (activeWorkspace === "governance-admin") {
    return renderWithBackControl(
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
      <Suspense fallback={<div className="workspace-grid"><Panel title="Loading Governance" className="span-12"><p className="narrative-text">Preparing governance workspace...</p></Panel></div>}>
        <GovernanceAdminWorkspace
          apiFetch={apiFetch}
          accessCode={accessCode}
          Panel={Panel}
          EmptyState={EmptyState}
        onBackToGate={() => setActiveWorkspace("system-body")}
        />
      </Suspense>
      </div>
    );
  }

  if (activeWorkspace === "observation-center") {
    return renderWithBackControl(
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
        <Suspense fallback={<div className="workspace-grid"><Panel title="Loading Findings" className="span-12"><p className="narrative-text">Preparing findings...</p></Panel></div>}>
          <ObservationCenterWorkspace
            apiFetch={apiFetch}
            accessCode={accessCode}
            canonicalFinding={canonicalFinding}
            currentSession={currentSession}
            onBackToGate={() => setActiveWorkspace("system-body")}
            onReviewEvidence={() => setActiveWorkspace("historical-replay")}
            onWorkspaceNavigate={setActiveWorkspace}
          />
        </Suspense>
      </div>
    );
  }

  if (activeWorkspace === "help-changelog") {
    return renderWithBackControl(
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
        <Suspense fallback={<div className="workspace-grid"><Panel title="Loading Help" className="span-12"><p className="narrative-text">Preparing help and changelog workspace...</p></Panel></div>}>
          <HelpChangelogWorkspace
            onBackToGate={() => setActiveWorkspace("system-body")}
            onWorkspaceNavigate={setActiveWorkspace}
          />
        </Suspense>
      </div>
    );
  }

  return (
    <AppErrorBoundary resetKey={errorBoundaryResetKey} onRetry={handleRetryWorkspace}>
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
      <SystemTopologyWorkspace
      liveOps={{
        ...liveOps,
        replayOverlay: historianReplayState.frame ?? null,
        canonicalFinding,
      }}
      replayFrame={historianReplayState.frame}
      selectedTarget={null}
      onSelectTarget={() => {}}
      apiFetch={apiFetch}
      accessCode={accessCode}
      onWorkspaceNavigate={setActiveWorkspace}
      onSignOut={handleSignOut}
      onUploadComplete={handleGateUploadComplete}
      domainMode={domainMode}
      domainDetection={domainDetection}
      gateProcessing={gateProcessing}
      />
    </div>
    </AppErrorBoundary>
  );
}


function deriveUploadTone(result) {
  if (!result) return "stable";
  const operatingState = String(result?.operating_state ?? result?.sii_intelligence?.facility_state ?? "").toLowerCase();
  const urgency = String(result?.drift_status ?? result?.sii_intelligence?.urgency ?? "").toLowerCase();

  if (!operatingState && !urgency) return "stable";
  if (operatingState.includes("needs action") || urgency === "unstable" || operatingState.includes("unstable")) return "critical";
  if (operatingState.includes("drift") || urgency === "elevated" || operatingState.includes("degrad")) return "warning";
  if (operatingState.includes("needs review") || urgency === "review" || operatingState.includes("review")) return "review";
  if (operatingState.includes("stable") || operatingState.includes("monitor")) return "stable";
  return "stable";
}

function formatClockTime(value) {
  if (!value) return "Unavailable";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "Unavailable";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function formatEndpoint(url) {
  try {
    return new URL(url).host;
  } catch {
    return String(url ?? "");
  }
}

async function buildProtectedRequestMessage(response) {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
  } catch {
    // Ignore parse failures and use fallback.
  }
  return "Session expired. Refresh workspace.";
}

export default App;
