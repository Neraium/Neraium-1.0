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
}) {
  return (
    <>
      <Panel title="Intake Status" className="span-7 uploaded-intelligence-panel">
        <MetricGrid
          metrics={[
            { label: "Active Session", value: uploadStateView.connectionStateLabel(latestStatus, uploadState, displayUploadError) },
            { label: "Control Plane", value: apiStatus.label },
            { label: "Analysis Active", value: latestUploadSnapshot?.last_processed_at ? formatClockTime(latestUploadSnapshot.last_processed_at) : "No Active Session" },
            { label: "Signal Origin", value: latestUploadSnapshot?.result_source ? "Telemetry import" : "Awaiting uploaded telemetry" },
            { label: "Baseline", value: baselineMessage },
            { label: "Primary Environment", value: roomContext.primary },
            { label: "Operational Mode", value: latestUploadSnapshot?.scenario ?? "Awaiting uploaded telemetry" },
            { label: "Session Tick", value: latestUploadSnapshot?.current_tick ?? "Pending activation" },
          ]}
        />
      </Panel>
      <Panel title="Recent Structural Analysis" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
        <MetricGrid
          metrics={[
            { label: "Active Model", value: latestUploadSnapshot?.history?.[0]?.filename ?? "Awaiting uploaded telemetry" },
            { label: "Baseline Reference", value: latestUploadSnapshot?.history?.[1]?.filename ?? "Awaiting uploaded telemetry" },
            { label: "Score Movement", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta ?? "No Active Session" },
            { label: "Structural Read", value: latestUploadSnapshot?.history?.[0]?.operating_state ?? "No Active Session" },
          ]}
          compact
        />
        <CompactList items={uploadDiffSummary.lines} emptyText="Awaiting meaningful structural change." />
      </Panel>
    </>
  );
}
