import { Suspense, lazy } from "react";

import AppErrorBoundary from "./AppErrorBoundary";
import SkipToMainContent from "./SkipToMainContent";
import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";

const HomePage = lazy(() => import("./HomePage"));
const DataConnectionsWorkspace = lazy(() => import("./DataConnectionsWorkspace"));
const OperationalWorkflowWorkspace = lazy(() => import("./OperationalWorkflowWorkspace"));
const SystemStoryWorkspace = lazy(() => import("./SystemStoryWorkspace"));
const GovernanceAdminWorkspace = lazy(() => import("./GovernanceAdminWorkspace"));
const ObservationCenterWorkspace = lazy(() => import("./ObservationCenterWorkspace"));
const HelpChangelogWorkspace = lazy(() => import("./HelpChangelogWorkspace"));

function renderLoadingPanel(title, message) {
  return (
    <div className="workspace-grid workspace-loading-shell" role="status" aria-live="polite" aria-atomic="true">
      <Panel title={title} className="span-12 workspace-loading-panel">
        <p className="narrative-text">{message}</p>
        <div className="workspace-loading-panel__meter" aria-hidden="true">
          <span />
        </div>
      </Panel>
    </div>
  );
}

function WorkspaceWithBackControl({
  appReady,
  errorBoundaryResetKey,
  handleBackToGate,
  handleRetryWorkspace,
  contextLabel,
  onHelp,
  children,
}) {
  return (
    <AppErrorBoundary resetKey={errorBoundaryResetKey} onRetry={handleRetryWorkspace}>
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
        <SkipToMainContent />
        <div className="workspace-shell-with-back">
          <nav className="workspace-back-control" aria-label="Workspace navigation">
            <div className="workspace-back-control__context">
              <button
                type="button"
                className="workspace-back-control__button"
                onClick={handleBackToGate}
                aria-label="Back to Command Center"
              >
                Command Center
              </button>
              {contextLabel ? <span className="workspace-back-control__breadcrumb" aria-current="page">{contextLabel}</span> : null}
            </div>
            <div className="workspace-back-control__meta">
              <span className="workspace-back-control__product"><strong>Neraium</strong> · SII intelligence · Read-only</span>
              {typeof onHelp === "function" ? (
                <button type="button" className="workspace-back-control__help" onClick={onHelp}>Help</button>
              ) : null}
            </div>
          </nav>
          <main id="main-content" className="workspace-route-main" aria-label="Neraium platform workspace" tabIndex={-1}>
            <h1 className="sr-only">Neraium Platform Workspace</h1>
            {children}
          </main>
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
  signOutPending = false,
  currentUser = null,
  setActiveWorkspace,
  pendingUploadFiles = [],
  setPendingUploadFiles = () => {},
  resultsNavigationKey = 0,
}) {
  if (activeWorkspace === "home") {
    return (
      <AppErrorBoundary resetKey={errorBoundaryResetKey} onRetry={handleRetryWorkspace}>
        <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
          <Suspense fallback={renderLoadingPanel("Preparing operations workspace", "Checking access and loading facility context...")}>
            <HomePage onLaunchWorkspace={() => setActiveWorkspace("system-body")} />
          </Suspense>
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
        contextLabel="Datasets & Connectors"
        onHelp={() => setActiveWorkspace("help-changelog")}
      >
        <Suspense fallback={renderLoadingPanel("Preparing telemetry intake", "Loading dataset validation and connector status...")}>
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
            currentUser={currentUser}
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
        contextLabel="Analysis Details"
        onHelp={() => setActiveWorkspace("help-changelog")}
      >
        <Suspense fallback={renderLoadingPanel("Loading investigation record", "Preparing analysis history, evidence, and diagnostics...")}>
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

  if (activeWorkspace === "governance-admin" && currentUser?.role !== "admin") {
    return (
      <WorkspaceWithBackControl
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleBackToGate={handleBackToGate}
        handleRetryWorkspace={handleRetryWorkspace}
        contextLabel="Administration"
        onHelp={() => setActiveWorkspace("help-changelog")}
      >
        <EmptyState title="Administrator access required" body="Your account can review operational results, but only administrators can manage users, sessions, and governance records." />
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
        contextLabel="Administration"
        onHelp={() => setActiveWorkspace("help-changelog")}
      >
        <Suspense fallback={renderLoadingPanel("Loading administration", "Preparing access controls and governance records...")}>
          <GovernanceAdminWorkspace
            apiFetch={apiFetch}
            accessCode={accessCode}
            Panel={Panel}
            EmptyState={EmptyState}
            onBackToGate={() => setActiveWorkspace("system-body")}
            currentUser={currentUser}
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
        contextLabel="Insights"
        onHelp={() => setActiveWorkspace("help-changelog")}
      >
        <Suspense fallback={renderLoadingPanel("Loading investigation", "Prioritizing findings and preparing evidence...")}>
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
        contextLabel="Help & Status"
      >
        <Suspense fallback={renderLoadingPanel("Loading support status", "Checking service status and operator guidance...")}>
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
        <Suspense fallback={renderLoadingPanel("Opening Command Center", "Prioritizing findings and loading facility state...")}>
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
            signOutPending={signOutPending}
            currentUser={currentUser}
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
              currentUser={currentUser}
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
