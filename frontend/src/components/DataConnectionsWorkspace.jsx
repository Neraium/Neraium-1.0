import { lazy, Suspense } from "react";
import TelemetryConnectionsWorkspace from "./TelemetryConnectionsWorkspace";

const HistoricalImportWorkspace = lazy(() => import("./HistoricalImportWorkspace"));

export default function DataConnectionsWorkspace(props) {
  const compatibilityHistoricalFlow = Boolean(
    props.headless
      || props.selectedBaselineIdentity?.baselineId
      || props.comparisonMode
      || props.autoStartInitialFiles
      || props.initialSelectedFiles?.length
      || props.hasActiveSession
      || props.hasResumedSession,
  );

  if (compatibilityHistoricalFlow) {
    return (
      <Suspense fallback={<div className="data-connections-workspace" role="status">Opening restricted historical workflow…</div>}>
        <HistoricalImportWorkspace {...props} />
      </Suspense>
    );
  }

  return (
    <TelemetryConnectionsWorkspace
      apiFetch={props.apiFetch}
      accessCode={props.accessCode}
      currentUser={props.currentUser}
      currentWorkspace={props.currentWorkspace}
      datasetScopeKey={props.datasetScopeKey}
    />
  );
}
