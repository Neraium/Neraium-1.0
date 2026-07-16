import { MetricGrid, Panel } from "../workspacePrimitives";

export default function IntakeStatusPanel({
  uploadStateView,
  latestStatus,
  uploadState,
  displayUploadError,
  apiStatus,
  latestUploadSnapshot,
  formatClockTime,
  baselineMessage,
  hasActiveSession,
  hasResumedSession,
  hasCurrentUploadResult,
  onResumePreviousSession,
  onOpenUpload,
  uploadJob = null,
  latestUploadResult = null,
}) {
  const showAnalysis = hasActiveSession && (hasCurrentUploadResult || hasResumedSession);
  const sessionState = showAnalysis ? uploadStateView.connectionStateLabel(latestStatus, uploadState, displayUploadError, latestUploadSnapshot) : "No Dataset Analyzed";
  const timings = latestUploadResult?.processing_stats?.timings ?? uploadJob?.timings ?? {};
  const parseSeconds = timings?.parse_seconds ?? null;
  const baselineSeconds = timings?.baseline_build_seconds ?? null;
  const scoreSeconds = timings?.structural_scoring_seconds ?? null;
  const totalSeconds = timings?.total_job_seconds ?? latestUploadResult?.processing_stats?.engine_runtime_seconds ?? uploadJob?.processing_duration_seconds ?? null;
  const processingPath = latestUploadSnapshot?.history?.[0]?.upload_processing_mode ?? uploadJob?.result_summary?.upload_processing_mode ?? null;
  const activeFilename = latestUploadSnapshot?.history?.[0]?.filename ?? null;
  const baselineReference = activeFilename
    ? `${activeFilename} (behavior baseline)`
    : "Awaiting telemetry file";
  const queuePending = Number(apiStatus?.queue?.pending ?? 0);
  const queueOldestPendingSeconds = Number(apiStatus?.queue?.oldest_pending_age_seconds ?? NaN);
  const queueOldestPending = Number.isFinite(queueOldestPendingSeconds)
    ? `${Math.max(0, Math.round(queueOldestPendingSeconds))}s`
    : "n/a";
  return (
    <>
      <Panel title="Status" className="span-7 uploaded-intelligence-panel">
        <MetricGrid
          metrics={[
            { label: "Session", value: sessionState },
            { label: "Analysis Service", value: apiStatus.label },
            { label: "Pending Analyses", value: queuePending },
            { label: "Longest Wait", value: queueOldestPending },
            { label: "Last Analysis", value: showAnalysis && latestUploadSnapshot?.last_processed_at ? formatClockTime(latestUploadSnapshot.last_processed_at) : null },
            { label: "Baseline", value: baselineMessage },
          ]}
        />
      </Panel>
      <Panel title="Processing" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
        <MetricGrid
          metrics={[
            { label: "Analysis path", value: processingPath === "hash_cache_reused" ? "Reused Result" : processingPath ? "New Analysis" : "Not available" },
            { label: "Parse (s)", value: parseSeconds },
            { label: "Baseline (s)", value: baselineSeconds },
            { label: "Scoring (s)", value: scoreSeconds },
            { label: "Total (s)", value: totalSeconds },
          ]}
          compact
        />
      </Panel>
      {showAnalysis ? (
        <Panel title="Latest System Review" className="span-12 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
          <MetricGrid
            metrics={[
              { label: "Telemetry File", value: latestUploadSnapshot?.history?.[0]?.filename ?? "Awaiting telemetry file" },
              { label: "Baseline Source", value: baselineReference },
              { label: "Change movement", value: latestUploadSnapshot?.history?.[0]?.diff?.neraium_score_delta },
              { label: "System read", value: latestUploadSnapshot?.history?.[0]?.operating_state },
            ]}
            compact
          />
        </Panel>
      ) : (
        <Panel title="No Active System Review" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
          <div className="intake-flow__controls">
            <button type="button" className="command-button" onClick={onOpenUpload}>Analyze Another Dataset</button>
            <button type="button" className="secondary-command-button" onClick={onResumePreviousSession}>Resume Previous Analysis</button>
          </div>
        </Panel>
      )}
    </>
  );
}
