import { CompactList, MetricGrid, Panel } from "../workspacePrimitives";

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
  onResumePreviousSession,
  onOpenUpload,
  adaptiveLearning = {},
  latestRunId = null,
  feedbackState = { status: "idle", category: null, message: "" },
  onOperatorFeedback = null,
  uploadJob = null,
  latestUploadResult = null,
}) {
  const showAnalysis = hasActiveSession && (hasCurrentUploadResult || hasResumedSession);
  const sessionState = showAnalysis ? uploadStateView.connectionStateLabel(latestStatus, uploadState, displayUploadError) : "No Active Session";
  const timings = latestUploadResult?.processing_stats?.timings ?? uploadJob?.timings ?? {};
  const parseSeconds = timings?.parse_seconds ?? null;
  const baselineSeconds = timings?.baseline_build_seconds ?? null;
  const scoreSeconds = timings?.structural_scoring_seconds ?? null;
  const totalSeconds = timings?.total_job_seconds ?? latestUploadResult?.processing_stats?.engine_runtime_seconds ?? uploadJob?.processing_duration_seconds ?? null;
  const processingMode = latestUploadSnapshot?.history?.[0]?.upload_processing_mode ?? uploadJob?.result_summary?.upload_processing_mode ?? null;
  const activeFilename = latestUploadSnapshot?.history?.[0]?.filename ?? latestUploadResult?.filename ?? null;
  const baselineReference = activeFilename
    ? `${activeFilename} (internal baseline)`
    : "Awaiting uploaded telemetry";
  return (
    <>
      <Panel title="Intake Status" className="span-7 uploaded-intelligence-panel">
        <MetricGrid
          metrics={[
            { label: "Session", value: sessionState },
            { label: "Control Plane", value: apiStatus.label },
            { label: "Last Analysis", value: showAnalysis && latestUploadSnapshot?.last_processed_at ? formatClockTime(latestUploadSnapshot.last_processed_at) : null },
            { label: "Baseline", value: baselineMessage },
            { label: "Operational Mode", value: showAnalysis ? latestUploadSnapshot?.scenario : null },
            { label: "Environment", value: roomContext.primary },
          ]}
        />
      </Panel>
      <Panel title="Processing" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
        <MetricGrid
          metrics={[
            { label: "Mode", value: processingMode === "hash_cache_reused" ? "Cache Reused" : processingMode ? "Full Processing" : "Unavailable" },
            { label: "Parse (s)", value: parseSeconds },
            { label: "Baseline (s)", value: baselineSeconds },
            { label: "Scoring (s)", value: scoreSeconds },
            { label: "Total (s)", value: totalSeconds },
          ]}
          compact
        />
      </Panel>
      {showAnalysis ? (
        <Panel title="Recent Structural Analysis" className="span-12 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
          <MetricGrid
            metrics={[
              { label: "Active Model", value: latestUploadSnapshot?.history?.[0]?.filename ?? "Awaiting uploaded telemetry" },
              { label: "Baseline Reference", value: baselineReference },
              { label: "Score Movement", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta },
              { label: "Structural Read", value: latestUploadSnapshot?.history?.[0]?.operating_state },
            ]}
            compact
          />
          <CompactList items={uploadDiffSummary.lines} emptyText="Awaiting meaningful structural change." />
        </Panel>
      ) : (
        <Panel title="No Active Structural Analysis" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
          <div className="intake-flow__controls">
            <button type="button" className="command-button" onClick={onOpenUpload}>Upload Data</button>
            <button type="button" className="secondary-command-button" onClick={onResumePreviousSession}>Resume Previous Session</button>
          </div>
        </Panel>
      )}
    </>
  );
}
