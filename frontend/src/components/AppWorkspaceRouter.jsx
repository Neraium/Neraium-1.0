import { Suspense, lazy } from "react";

import AppErrorBoundary from "./AppErrorBoundary";
import HomePage from "./HomePage";
import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";

const DataConnectionsWorkspace = lazy(() => import("./DataConnectionsWorkspace"));
const OperationalWorkflowWorkspace = lazy(() => import("./OperationalWorkflowWorkspace"));
const SystemStoryWorkspace = lazy(() => import("./SystemStoryWorkspace"));
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
              aria-label="Back to Workspace"
            >
              Back to Workspace
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
  handleReopenHistoricalAnalysis,
  handleDeleteHistoricalAnalysis,
  handleReplayFrameChange,
  handleReplayModeChange,
  handleSignOut,
  setActiveWorkspace,
  pendingUploadFiles = [],
  setPendingUploadFiles = () => {},
  resultsNavigationKey = 0,
}) {
  if (activeWorkspace === "home") {
    return (
      <AppErrorBoundary resetKey={errorBoundaryResetKey} onRetry={handleRetryWorkspace}>
        <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
          <HomePage onLaunchWorkspace={() => setActiveWorkspace("system-body")} />
        </div>
      </AppErrorBoundary>
    );
  }

  if (activeWorkspace === "data-connections") {
    return (
      <WorkspaceWithBackControl
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleBackToGate={handleBackToGate}
        handleRetryWorkspace={handleRetryWorkspace}
      >
        <Suspense fallback={renderLoadingPanel("Loading Telemetry Workspace", "Preparing telemetry intake...")}>
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
            sessionStore={liveOps.session}
            onResetDemo={handleResetDemo}
            formatClockTime={formatClockTime}
            initialSelectedFiles={pendingUploadFiles}
            onInitialSelectedFilesConsumed={() => setPendingUploadFiles([])}
            autoStartInitialFiles={pendingUploadFiles.length > 0}
          />
        </Suspense>
      </WorkspaceWithBackControl>
    );
  }

  if (activeWorkspace === "system-story") {
    return (
      <WorkspaceWithBackControl
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleBackToGate={handleBackToGate}
        handleRetryWorkspace={handleRetryWorkspace}
      >
        <Suspense fallback={renderLoadingPanel("Loading Advanced Details", "Preparing behavior diagnostics...")}>
          <SystemStoryWorkspace
            apiFetch={apiFetch}
            accessCode={accessCode}
            expertMode={true}
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
        <Suspense fallback={renderLoadingPanel("Loading Technical Admin", "Preparing technical admin workspace...")}>
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
        <Suspense fallback={renderLoadingPanel("Loading Insights", "Preparing insights...")}>
          <ObservationCenterWorkspace
            apiFetch={apiFetch}
            accessCode={accessCode}
            canonicalFinding={canonicalFinding}
            currentSession={currentSession}
            onBackToGate={() => setActiveWorkspace("system-body")}
            onReviewEvidence={() => setActiveWorkspace("observation-center")}
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
        <Suspense fallback={renderLoadingPanel("Loading Technical", "Preparing technical workspace...")}>
          <HelpChangelogWorkspace
            apiStatus={apiStatus}
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
        <Suspense fallback={renderLoadingPanel("Loading Command Center", "Preparing system overview...")}>
          <OperationalWorkflowWorkspace
            liveOps={{
              ...liveOps,
              replayOverlay: historianReplayState.frame ?? null,
              canonicalFinding,
            }}
            replayFrame={historianReplayState.frame}
            currentSession={currentSession}
            canonicalFinding={canonicalFinding}
            effectiveLatestUploadResult={effectiveLatestUploadResult}
            effectiveLatestUploadSnapshot={effectiveLatestUploadSnapshot}
            roomContext={roomContext}
            domainMode={domainMode}
            domainDetection={domainDetection}
            gateProcessing={gateProcessing}
            resultsNavigationKey={resultsNavigationKey}
            onWorkspaceNavigate={setActiveWorkspace}
            onSignOut={handleSignOut}
            onCsvSelected={(files) => {
              setPendingUploadFiles(files);
              setActiveWorkspace("data-connections");
            }}
            onResumePreviousSession={handleResumePreviousSession}
            onReopenHistoricalAnalysis={handleReopenHistoricalAnalysis}
            onDeleteHistoricalAnalysis={handleDeleteHistoricalAnalysis}
          />
          {pendingUploadFiles.length > 0 ? (
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
              sessionStore={liveOps.session}
              onResetDemo={handleResetDemo}
              formatClockTime={formatClockTime}
              initialSelectedFiles={pendingUploadFiles}
              autoStartInitialFiles={true}
              headless={true}
            />
          ) : null}
        </Suspense>
      </div>
    </AppErrorBoundary>
  );
}
