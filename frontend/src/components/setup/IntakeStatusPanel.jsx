import { MetricGrid, Panel, CompactList } from "../workspacePrimitives";

export default function IntakeStatusPanel({
  uploadStateView,
  latestStatus,
  uploadState,
  displayUploadError,
  apiStatus,
  latestUploadSnapshot,
  formatClockTime,
  baselineMessage,
  roomContext,
  uploadDiffSummary,
  hasActiveSession,
  hasResumedSession,
  hasCurrentUploadResult,
  hasRealSiiOutput,
  onResumePreviousSession,
  onOpenUpload,
}) {
  const showAnalysis = hasActiveSession && hasRealSiiOutput && (hasCurrentUploadResult || hasResumedSession);
  return (
    <>
      <Panel title="Intake Status" className="span-7 uploaded-intelligence-panel">
        <MetricGrid
          metrics={[
            { label: "Active Session", value: showAnalysis ? uploadStateView.connectionStateLabel(latestStatus, uploadState, displayUploadError) : "No Active Session" },
            { label: "Control Plane", value: apiStatus.label },
            { label: "Analysis Active", value: showAnalysis && latestUploadSnapshot?.last_processed_at ? formatClockTime(latestUploadSnapshot.last_processed_at) : null },
            { label: "Signal Origin", value: showAnalysis && latestUploadSnapshot?.result_source ? "Telemetry import" : null },
            { label: "Baseline", value: baselineMessage },
            { label: "Primary Environment", value: roomContext.primary },
            { label: "Operational Mode", value: showAnalysis ? latestUploadSnapshot?.scenario : null },
            { label: "Session Tick", value: showAnalysis ? latestUploadSnapshot?.current_tick : null },
          ]}
        />
      </Panel>
      {showAnalysis ? (
        <Panel title="Recent Structural Analysis" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
          <MetricGrid
            metrics={[
              { label: "Active Model", value: latestUploadSnapshot?.history?.[0]?.filename ?? "Awaiting uploaded telemetry" },
              { label: "Baseline Reference", value: latestUploadSnapshot?.history?.[1]?.filename },
              { label: "Score Movement", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta },
              { label: "Structural Read", value: latestUploadSnapshot?.history?.[0]?.operating_state },
            ]}
            compact
          />
          <CompactList items={uploadDiffSummary.lines} emptyText="Awaiting meaningful structural change." />
        </Panel>
      ) : (
        <Panel title="No Active Structural Analysis" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
          <p className="narrative-text">Upload telemetry or connect a historian source to begin baseline comparison.</p>
          <div className="intake-flow__controls">
            <button type="button" className="command-button" onClick={onOpenUpload}>Upload Data</button>
            <button type="button" className="secondary-command-button" onClick={onResumePreviousSession}>Resume Previous Session</button>
          </div>
        </Panel>
      )}
    </>
  );
}
