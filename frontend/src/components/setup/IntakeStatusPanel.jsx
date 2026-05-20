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
  adaptiveLearning = {},
  latestRunId = null,
  feedbackState = { status: "idle", category: null, message: "" },
  onOperatorFeedback = null,
  uploadJob = null,
  latestUploadResult = null,
}) {
  const showAnalysis = hasActiveSession && hasRealSiiOutput && (hasCurrentUploadResult || hasResumedSession);
  const calibration = adaptiveLearning?.calibration ?? {};
  const adaptiveBaseline = adaptiveLearning?.adaptive_baseline ?? {};
  const eventMemory = adaptiveLearning?.event_memory ?? {};
  const feedbackHistory = eventMemory?.recent_feedback_history ?? [];
  const feedbackOptions = adaptiveLearning?.operator_feedback_options ?? [];
  const hasFeedbackData = feedbackHistory.length > 0 || Boolean(latestRunId);
  const sessionState = showAnalysis ? uploadStateView.connectionStateLabel(latestStatus, uploadState, displayUploadError) : "No Active Session";
  const learningStatus = adaptiveLearning?.learning_status ?? "warming_up";
  const baselineAge = adaptiveBaseline?.baseline_age?.label ?? "Unavailable";
  const calibrationConfidence = calibration?.calibration_confidence ?? null;
  const similarEvents = eventMemory?.historical_similar_events ?? 0;
  const timings = latestUploadResult?.processing_stats?.timings ?? uploadJob?.timings ?? {};
  const parseSeconds = timings?.parse_seconds ?? null;
  const baselineSeconds = timings?.baseline_build_seconds ?? null;
  const scoreSeconds = timings?.structural_scoring_seconds ?? null;
  const totalSeconds = timings?.total_job_seconds ?? latestUploadResult?.processing_stats?.engine_runtime_seconds ?? uploadJob?.processing_duration_seconds ?? null;
  const processingMode = latestUploadSnapshot?.history?.[0]?.upload_processing_mode ?? uploadJob?.result_summary?.upload_processing_mode ?? null;
  const ingestRequestId = uploadJob?.ingest_request_id ?? null;
  const requestId = uploadJob?.request_id ?? null;
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
      <Panel title="Adaptive Context" className="span-5 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
        <MetricGrid
          metrics={[
            { label: "Learning Status", value: learningStatus },
            { label: "Baseline Age", value: baselineAge },
            { label: "Calibration Confidence", value: calibrationConfidence },
            { label: "Historical Similar Events", value: similarEvents },
          ]}
          compact
        />
      </Panel>
      {showAnalysis ? (
        <Panel title="Recent Structural Analysis" className="span-12 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
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
      {hasFeedbackData ? (
        <Panel title="Operator Feedback History" className="span-6 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
          <CompactList
            items={feedbackHistory.map((item) => `${item.feedback_category ?? item.category ?? "feedback"}${item.feedback_recorded_at ? ` at ${item.feedback_recorded_at}` : ""}`)}
            emptyText="No operator feedback recorded yet."
          />
          {latestRunId && typeof onOperatorFeedback === "function" ? (
            <div className="intake-flow__controls">
              {feedbackOptions.map((option) => (
                <button
                  key={option}
                  type="button"
                  className={feedbackState?.category === option && feedbackState?.status === "submitting" ? "command-button" : "secondary-command-button"}
                  onClick={() => onOperatorFeedback(option)}
                  disabled={feedbackState?.status === "submitting"}
                >
                  {labelFeedbackOption(option)}
                </button>
              ))}
            </div>
          ) : null}
          {feedbackState?.message ? <p className="narrative-text">{feedbackState.message}</p> : null}
        </Panel>
      ) : null}
      <Panel title="Processing Breakdown" className="span-6 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
        <MetricGrid
          metrics={[
            { label: "Processing Mode", value: processingMode === "hash_cache_reused" ? "Hash Cache Reused" : processingMode ? "Full Processing" : "Unavailable" },
            { label: "Parse (s)", value: parseSeconds },
            { label: "Baseline (s)", value: baselineSeconds },
            { label: "Scoring (s)", value: scoreSeconds },
            { label: "Total (s)", value: totalSeconds },
          ]}
          compact
        />
      </Panel>
      <Panel title="Trace Correlation" className="span-6 uploaded-intelligence-panel uploaded-intelligence-panel--delta">
        <CompactList
          items={[
            `Upload Job ID: ${latestRunId ?? "n/a"}`,
            `Ingest Request ID: ${ingestRequestId ?? "n/a"}`,
            `Last Poll Request ID: ${requestId ?? "n/a"}`,
          ]}
          emptyText="No trace identifiers available."
        />
      </Panel>
    </>
  );
}

function labelFeedbackOption(value) {
  return {
    confirmed_issue: "Confirmed Issue",
    useful_warning: "Useful Warning",
    expected_behavior: "Expected Behavior",
    false_positive: "False Positive",
    maintenance_event: "Maintenance Event",
    ignore: "Ignore",
  }[value] ?? value;
}
