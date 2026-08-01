import { Suspense, lazy } from "react";

import AppErrorBoundary from "./AppErrorBoundary";
import SkipToMainContent from "./SkipToMainContent";
import { EmptyState, Panel } from "./workspacePrimitives";
import { extractTelemetryBoundaryMeta } from "../viewModels/uploadState";

const GovernanceAdminWorkspace = lazy(() => import("./GovernanceAdminWorkspace"));
const MonitoringWorkspace = lazy(() => import("./MonitoringWorkspace"));

function LoadingState() {
  return <div className="monitoring-route-loading" role="status" aria-live="polite">Loading monitoring state…</div>;
}

function AdminRoute({ appReady, errorBoundaryResetKey, handleRetryWorkspace, setActiveWorkspace, apiFetch, accessCode, currentUser }) {
  return (
    <AppErrorBoundary resetKey={errorBoundaryResetKey} onRetry={handleRetryWorkspace} errorContext={{ workspaceId: "governance-admin" }}>
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
        <SkipToMainContent />
        <main id="main-content" className="workspace-route-main" tabIndex={-1}>
          <button type="button" className="monitoring-back" onClick={() => setActiveWorkspace("status")}>Back to Status</button>
          {currentUser?.role !== "admin" ? (
            <EmptyState title="Administrator access required" body="Only administrators can manage users, sessions, and internal diagnostics." />
          ) : (
            <Suspense fallback={<LoadingState />}>
              <GovernanceAdminWorkspace apiFetch={apiFetch} accessCode={accessCode} Panel={Panel} EmptyState={EmptyState} onBackToGate={() => setActiveWorkspace("status")} currentUser={currentUser} />
            </Suspense>
          )}
        </main>
      </div>
    </AppErrorBoundary>
  );
}

export default function AppWorkspaceRouter({
  activeWorkspace,
  datasetScopeKey,
  appReady,
  errorBoundaryResetKey,
  apiFetch,
  accessCode,
  apiStatus,
  liveOps,
  currentSession,
  canonicalFinding,
  gateProcessing,
  effectiveLatestUploadResult,
  effectiveLatestUploadSnapshot,
  domainDetection,
  handleRetryWorkspace,
  handleGateUploadComplete,
  handleSignOut,
  signOutPending = false,
  currentUser = null,
  setActiveWorkspace,
  pendingUploadFiles = [],
  setPendingUploadFiles = () => {},
}) {
  const errorContext = extractTelemetryBoundaryMeta(effectiveLatestUploadSnapshot, effectiveLatestUploadResult);

  if (activeWorkspace === "governance-admin") {
    return <AdminRoute appReady={appReady} errorBoundaryResetKey={errorBoundaryResetKey} handleRetryWorkspace={handleRetryWorkspace} setActiveWorkspace={setActiveWorkspace} apiFetch={apiFetch} accessCode={accessCode} currentUser={currentUser} />;
  }

  return (
    <AppErrorBoundary resetKey={`${errorBoundaryResetKey}:${datasetScopeKey}`} onRetry={handleRetryWorkspace} errorContext={{ ...errorContext, workspaceId: activeWorkspace }}>
      <div data-testid="app-ready-root" data-app-ready={appReady ? "1" : "0"}>
        <Suspense fallback={<LoadingState />}>
          <MonitoringWorkspace
            key={`monitoring:${datasetScopeKey}`}
            activeWorkspace={activeWorkspace}
            accessCode={accessCode}
            apiFetch={apiFetch}
            liveOps={{ ...liveOps, apiStatus }}
            currentSession={currentSession}
            canonicalFinding={canonicalFinding}
            gateProcessing={gateProcessing}
            effectiveLatestUploadResult={effectiveLatestUploadResult}
            effectiveLatestUploadSnapshot={effectiveLatestUploadSnapshot}
            domainDetection={domainDetection}
            onWorkspaceNavigate={setActiveWorkspace}
            onSignOut={handleSignOut}
            signOutPending={signOutPending}
            currentUser={currentUser}
            onUploadComplete={handleGateUploadComplete}
            pendingUploadFiles={pendingUploadFiles}
            setPendingUploadFiles={setPendingUploadFiles}
          />
        </Suspense>
      </div>
    </AppErrorBoundary>
  );
}
