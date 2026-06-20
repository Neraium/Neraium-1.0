import { Suspense, lazy } from "react";

import AppErrorBoundary from "./AppErrorBoundary";
import DataConnectionsWorkspace from "./DataConnectionsWorkspace";
import SystemTopologyWorkspace from "./SystemTopologyWorkspace";
import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";

const StructuralReplayWorkspace = lazy(() => import("./StructuralReplayWorkspace"));
const GovernanceAdminWorkspace = lazy(() => import("./GovernanceAdminWorkspace"));
const ObservationCenterWorkspace = lazy(() => import("./ObservationCenterWorkspace"));
const HelpChangelogWorkspace = lazy(() => import("./HelpChangelogWorkspace"));

function renderLoadingPanel(title, message) {
  return (
    <div className="workspace-grid">
      <Panel title={title} className="span-12">
        <p className="narrative-text">{message}</p>
      </Panel>
    </div>
  );
}

function WorkspaceWithBackControl({ appReady, errorBoundaryResetKey, handleBackToGate, handleRetryWorkspace, children }) {
  return (
    <AppErrorBoundary resetKey={errorBoundaryResetKey} onRetry={handleRetryWorkspace}>
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
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
          {children}
        </div>
      </div>
    </AppErrorBoundary>
  );
}

export default function AppWorkspaceRouter({
  activeWorkspace,
  appReady,
  errorBoundaryResetKey,
  apiFetch,
  accessCode,
  apiStatus,
  liveOps,
  historianReplayState,
  currentSession,
  canonicalFinding,
  gateProcessing,
  effectiveLatestUploadResult,
  effectiveLatestUploadSnapshot,
  hasActiveSession,
  hasCurrentUploadResult,
  hasResumedSession,
  hasRealSiiOutput,
  roomContext,
  domainMode,
  domainDetection,
  formatClockTime,
  handleBackToGate,
  handleRetryWorkspace,
  handleGateUploadComplete,
  handleResetDemo,
  handleResumePreviousSession,
  handleReplayFrameChange,
  handleReplayModeChange,
  handleSignOut,
  setActiveWorkspace,
}) {
  if (activeWorkspace === "data-connections") {
    return (
      <WorkspaceWithBackControl
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleBackToGate={handleBackToGate}
        handleRetryWorkspace={handleRetryWorkspace}
      >
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
      </WorkspaceWithBackControl>
    );
  }

  if (activeWorkspace === "historical-replay") {
    return (
      <WorkspaceWithBackControl
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleBackToGate={handleBackToGate}
        handleRetryWorkspace={handleRetryWorkspace}
      >
        <Suspense fallback={renderLoadingPanel("Loading Replay", "Preparing replay workspace...")}>
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
      </WorkspaceWithBackControl>
    );
  }

  if (activeWorkspace === "governance-admin") {
    return (
      <WorkspaceWithBackControl
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleBackToGate={handleBackToGate}
        handleRetryWorkspace={handleRetryWorkspace}
      >
        <Suspense fallback={renderLoadingPanel("Loading Governance", "Preparing governance workspace...")}>
          <GovernanceAdminWorkspace
            apiFetch={apiFetch}
            accessCode={accessCode}
            Panel={Panel}
            EmptyState={EmptyState}
            onBackToGate={() => setActiveWorkspace("system-body")}
          />
        </Suspense>
      </WorkspaceWithBackControl>
    );
  }

  if (activeWorkspace === "observation-center") {
    return (
      <WorkspaceWithBackControl
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleBackToGate={handleBackToGate}
        handleRetryWorkspace={handleRetryWorkspace}
      >
        <Suspense fallback={renderLoadingPanel("Loading Findings", "Preparing findings...")}>
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
      </WorkspaceWithBackControl>
    );
  }

  if (activeWorkspace === "help-changelog") {
    return (
      <WorkspaceWithBackControl
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleBackToGate={handleBackToGate}
        handleRetryWorkspace={handleRetryWorkspace}
      >
        <Suspense fallback={renderLoadingPanel("Loading Help", "Preparing help and changelog workspace...")}>
          <HelpChangelogWorkspace
            onBackToGate={() => setActiveWorkspace("system-body")}
            onWorkspaceNavigate={setActiveWorkspace}
          />
        </Suspense>
      </WorkspaceWithBackControl>
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
