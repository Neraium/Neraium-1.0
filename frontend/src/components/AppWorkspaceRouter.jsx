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
    <div className="workspace-grid workspace-loading-shell">
      <Panel title={title} className="span-12 workspace-loading-panel">
        <p className="narrative-text">{message}</p>
        <div className="workspace-loading-panel__meter" aria-hidden="true">
          <span />
        </div>
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
              className="workspace-back-control__button"
              onClick={handleBackToGate}
              aria-label="Back to Command Center"
            >
              Back to Command Center
            </button>
            <span>Read-only operational intelligence</span>
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
        <Suspense fallback={renderLoadingPanel("Loading Data Sources", "Preparing telemetry analysis workflow...")}>
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
        <Suspense fallback={renderLoadingPanel("Opening Command Center", "Preparing operational status...")}>
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
