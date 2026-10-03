import { Suspense, lazy, useEffect, useRef } from "react";
import "../styles/product-polish.css";

import AppErrorBoundary from "./AppErrorBoundary";
import WorkspaceShell from "./WorkspaceShell";
import WorkspaceLoadingState from "./WorkspaceLoadingState";
import { EmptyState, MetricGrid, Panel } from "./workspacePrimitives";
import { extractTelemetryBoundaryMeta } from "../viewModels/uploadState";

const HomePage = lazy(() => import("./HomePage"));
const DataConnectionsWorkspace = lazy(() => import("./DataConnectionsWorkspace"));
const EngineeringReasoningWorkspace = lazy(() => import("./EngineeringReasoningWorkspace"));
const SystemStoryWorkspace = lazy(() => import("./SystemStoryWorkspace"));
const GovernanceAdminWorkspace = lazy(() => import("./GovernanceAdminWorkspace"));
const ObservationCenterWorkspace = lazy(() => import("./ObservationCenterWorkspace"));
const HelpChangelogWorkspace = lazy(() => import("./HelpChangelogWorkspace"));

function renderLoadingPanel(title, message) {
  return <WorkspaceLoadingState label={title} detail={message} fullScreen />;
}

function WorkspaceWithContext({
  appReady,
  errorBoundaryResetKey,
  handleRetryWorkspace,
  contextLabel,
  errorContext,
  activeWorkspace,
  onNavigate,
  currentUser,
  onSignOut,
  signOutPending,
  workspaceSession,
  currentWorkspace,
  onWorkspaceChange,
  children,
}) {
  const mainRef = useRef(null);
  useEffect(() => {
    mainRef.current?.focus({ preventScroll: true });
  }, [activeWorkspace]);
  return (
    <AppErrorBoundary resetKey={errorBoundaryResetKey} onRetry={handleRetryWorkspace} errorContext={{ ...errorContext, workspaceId: activeWorkspace }}>
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
        <WorkspaceShell activeNavigation={activeWorkspace} onNavigate={onNavigate} currentUser={currentUser} onSignOut={onSignOut} signOutPending={signOutPending} workspaceSession={workspaceSession} currentWorkspace={currentWorkspace} onWorkspaceChange={onWorkspaceChange} mainRef={mainRef} mainId="main-content" mainLabel="Neraium platform workspace" topbarContent={<div className="forensic-topbar__site"><span>{currentWorkspace?.display_name ?? "Personal workspace"}</span><small>Read-only</small></div>}>
          <nav className="workspace-context-trail" aria-label="Context trail">
            <button type="button" onClick={() => onNavigate("site")}>System Status</button>
            <span aria-hidden="true">/</span><span aria-current="page">{contextLabel}</span>
          </nav>
            {children}
        </WorkspaceShell>
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
  canonicalConnectorResult = null,
  hasActiveSession,
  hasCurrentUploadResult,
  hasResumedSession,
  hasRealSiiOutput,
  roomContext,
  domainMode,
  domainDetection,
  formatClockTime,
  handleRetryWorkspace,
  handleGateUploadComplete,
  handleOpenConnectorAnalysisResult = () => {},
  activeUploadAttempt = null,
  handleUploadAttemptStarted = () => null,
  handleUploadAttemptIdentified = () => {},
  handleResetDemo,
  handleResumePreviousSession,
  handleReopenHistoricalAnalysis,
  handleDeleteHistoricalAnalysis,
  handleReplayFrameChange,
  handleReplayModeChange,
  handleSignOut,
  signOutPending = false,
  currentUser = null,
  workspaceSession = null,
  currentWorkspace = null,
  onWorkspaceChange = () => {},
  setActiveWorkspace,
  selectedBaselineIdentity = null,
  comparisonBaselineIdentity = null,
  selectedAnalysisIdentity = null,
  activeBaselineIdentity = null,
  datasetScopeKey = "anonymous",
  onBaselineSelected = () => false,
  onBaselineClosedForComparison = () => false,
  pendingUploadFiles = [],
  setPendingUploadFiles = () => {},
  resultsNavigationKey = 0,
}) {
  const errorContext = extractTelemetryBoundaryMeta(effectiveLatestUploadSnapshot, effectiveLatestUploadResult);
  const currentResultIdentity = String(
    canonicalConnectorResult?.result_id
      ?? effectiveLatestUploadResult?.dataset_id
      ?? effectiveLatestUploadResult?.job_id
      ?? effectiveLatestUploadResult?.run_id
      ?? effectiveLatestUploadSnapshot?.dataset_id
      ?? effectiveLatestUploadSnapshot?.job_id
      ?? "empty",
  );
  const presentationIdentityKey = [
    datasetScopeKey,
    activeUploadAttempt?.attemptId ?? "no-attempt",
    selectedAnalysisIdentity?.analysisRunId ?? currentResultIdentity,
    resultsNavigationKey,
  ].join(":");
  const workspaceContextProps = { workspaceSession, currentWorkspace, onWorkspaceChange, currentUser, onNavigate: setActiveWorkspace, onSignOut: handleSignOut, signOutPending };

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
      <WorkspaceWithContext
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleRetryWorkspace={handleRetryWorkspace}
        contextLabel="Data"
        errorContext={errorContext}
        activeWorkspace={activeWorkspace}
        {...workspaceContextProps}
      >
        <Suspense fallback={renderLoadingPanel("Opening Data Connections", "Loading facility-scoped telemetry sources and system mappings...")}>
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
            onOpenAnalysisResult={handleOpenConnectorAnalysisResult}
            activeUploadAttempt={activeUploadAttempt}
            onUploadAttemptStarted={handleUploadAttemptStarted}
            onUploadAttemptIdentified={handleUploadAttemptIdentified}
            onOpenBaseline={(identity, options = {}) => onBaselineSelected(identity, { replace: options.replace === true })}
            onCloseBaseline={onBaselineClosedForComparison}
            onReturnToPortfolio={() => setActiveWorkspace("system-body")}
            selectedBaselineIdentity={selectedBaselineIdentity}
            activeBaselineIdentity={comparisonBaselineIdentity ?? activeBaselineIdentity}
            comparisonMode={Boolean(comparisonBaselineIdentity?.baselineId)}
            autoOpenBaselineReady={true}
            datasetScopeKey={datasetScopeKey}
            currentWorkspace={currentWorkspace}
            sessionStore={liveOps.session}
            onResetDemo={handleResetDemo}
            formatClockTime={formatClockTime}
            currentUser={currentUser}
            initialSelectedFiles={pendingUploadFiles}
            onInitialSelectedFilesConsumed={() => setPendingUploadFiles([])}
            autoStartInitialFiles={pendingUploadFiles.length > 0}
          />
        </Suspense>
      </WorkspaceWithContext>
    );
  }

  if (activeWorkspace === "system-story") {
    return (
      <WorkspaceWithContext
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleRetryWorkspace={handleRetryWorkspace}
        contextLabel="Historical replay"
        errorContext={errorContext}
        activeWorkspace={activeWorkspace}
        {...workspaceContextProps}
      >
        <Suspense fallback={renderLoadingPanel("Loading investigation record", "Preparing analysis history, evidence, and diagnostics...")}>
          <SystemStoryWorkspace
            key={`story:${presentationIdentityKey}`}
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
      </WorkspaceWithContext>
    );
  }

  if (activeWorkspace === "governance-admin" && currentUser?.role !== "admin") {
    return (
      <WorkspaceWithContext
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleRetryWorkspace={handleRetryWorkspace}
        contextLabel="Administration"
        errorContext={errorContext}
        activeWorkspace={activeWorkspace}
        {...workspaceContextProps}
      >
        <EmptyState title="Administrator access required" body="This workspace is limited to administrators." actionLabel="Return to Portfolio" onAction={() => setActiveWorkspace("system-body")} />
      </WorkspaceWithContext>
    );
  }

  if (activeWorkspace === "governance-admin") {
    return (
      <WorkspaceWithContext
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleRetryWorkspace={handleRetryWorkspace}
        contextLabel="Administration"
        errorContext={errorContext}
        activeWorkspace={activeWorkspace}
        {...workspaceContextProps}
      >
        <Suspense fallback={renderLoadingPanel("Loading administration", "Preparing access controls and governance records...")}>
          <GovernanceAdminWorkspace
            apiFetch={apiFetch}
            accessCode={accessCode}
            Panel={Panel}
            EmptyState={EmptyState}
            onBackToGate={() => setActiveWorkspace("system-body")}
            currentUser={currentUser}
            currentWorkspace={currentWorkspace}
          />
        </Suspense>
      </WorkspaceWithContext>
    );
  }

  if (activeWorkspace === "observation-center") {
    return (
      <WorkspaceWithContext
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleRetryWorkspace={handleRetryWorkspace}
        contextLabel="Historical review"
        errorContext={errorContext}
        activeWorkspace={activeWorkspace}
        {...workspaceContextProps}
      >
        <Suspense fallback={renderLoadingPanel("Loading investigation", "Prioritizing findings and preparing evidence...")}>
          <ObservationCenterWorkspace
            key={`insights:${datasetScopeKey}`}
            apiFetch={apiFetch}
            accessCode={accessCode}
            datasetScopeKey={datasetScopeKey}
            canonicalFinding={canonicalFinding}
            currentSession={currentSession}
            onBackToGate={() => setActiveWorkspace("system-body")}
            onReviewEvidence={() => setActiveWorkspace("observation-center")}
          />
        </Suspense>
      </WorkspaceWithContext>
    );
  }

  if (activeWorkspace === "help-changelog") {
    return (
      <WorkspaceWithContext
        appReady={appReady}
        errorBoundaryResetKey={errorBoundaryResetKey}
        handleRetryWorkspace={handleRetryWorkspace}
        contextLabel="Help & Status"
        errorContext={errorContext}
        activeWorkspace={activeWorkspace}
        {...workspaceContextProps}
      >
        <Suspense fallback={renderLoadingPanel("Loading support status", "Checking service status and operator guidance...")}>
          <HelpChangelogWorkspace
            apiStatus={apiStatus}
            onBackToGate={() => setActiveWorkspace("system-body")}
            onWorkspaceNavigate={setActiveWorkspace}
          />
        </Suspense>
      </WorkspaceWithContext>
    );
  }

  return (
    <AppErrorBoundary resetKey={errorBoundaryResetKey} onRetry={handleRetryWorkspace} errorContext={{ ...errorContext, workspaceId: activeWorkspace }}>
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
        <Suspense fallback={renderLoadingPanel("Opening engineering workspace", "Preparing site evidence and relationship context...")}>
          <EngineeringReasoningWorkspace
            key={`engineering:${presentationIdentityKey}`}
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
            canonicalConnectorResult={canonicalConnectorResult}
            roomContext={roomContext}
            domainMode={domainMode}
            domainDetection={domainDetection}
            gateProcessing={gateProcessing}
            resultsNavigationKey={resultsNavigationKey}
            activeUploadAttempt={activeUploadAttempt}
            datasetScopeKey={datasetScopeKey}
            comparisonAnalysisId={selectedAnalysisIdentity?.analysisRunId ?? null}
            onWorkspaceNavigate={setActiveWorkspace}
            onSignOut={handleSignOut}
            signOutPending={signOutPending}
            currentUser={currentUser}
            workspaceSession={workspaceSession}
            currentWorkspace={currentWorkspace}
            onWorkspaceChange={onWorkspaceChange}
            apiFetch={apiFetch}
            onCsvSelected={(files) => {
              handleUploadAttemptStarted({ files, workflow: "create_baseline" });
              setPendingUploadFiles(files);
              setActiveWorkspace("data-connections");
            }}
            onResumePreviousSession={handleResumePreviousSession}
            onReopenHistoricalAnalysis={handleReopenHistoricalAnalysis}
            onDeleteHistoricalAnalysis={handleDeleteHistoricalAnalysis}
            onRetryLatestTelemetry={handleRetryWorkspace}
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
              activeUploadAttempt={activeUploadAttempt}
              onUploadAttemptStarted={handleUploadAttemptStarted}
              onUploadAttemptIdentified={handleUploadAttemptIdentified}
              sessionStore={liveOps.session}
              onResetDemo={handleResetDemo}
              formatClockTime={formatClockTime}
              currentUser={currentUser}
              initialSelectedFiles={pendingUploadFiles}
              autoStartInitialFiles={true}
              headless={true}
              datasetScopeKey={datasetScopeKey}
            />
          ) : null}
        </Suspense>
      </div>
    </AppErrorBoundary>
  );
}
