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
}) {
  const showAnalysis = hasActiveSession && hasRealSiiOutput && (hasCurrentUploadResult || hasResumedSession);
  const calibration = adaptiveLearning?.calibration ?? {};
  const adaptiveBaseline = adaptiveLearning?.adaptive_baseline ?? {};
  const eventMemory = adaptiveLearning?.event_memory ?? {};
  const patternRecognition = adaptiveLearning?.pattern_recognition ?? {};
  const feedbackHistory = eventMemory?.recent_feedback_history ?? [];
  const feedbackOptions = adaptiveLearning?.operator_feedback_options ?? [];
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
            { label: "Learning Status", value: adaptiveLearning?.learning_status ?? "warming_up" },
            { label: "Baseline Age", value: adaptiveBaseline?.baseline_age?.label ?? "Unavailable" },
            { label: "Calibration Confidence", value: calibration?.calibration_confidence ?? null },
            { label: "Historical Similar Events", value: eventMemory?.historical_similar_events ?? 0 },
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
      <Panel title="Adaptive Learning" className="span-6 uploaded-intelligence-panel">
        <MetricGrid
          metrics={[
            { label: "Operational Fingerprint", value: adaptiveLearning?.site_key ?? "Site memory pending" },
            { label: "Sensitivity Adjustment", value: calibration?.sensitivity_adjustment ?? 0 },
            { label: "Nuisance Suppression", value: calibration?.nuisance_alert_suppression ?? 0 },
            { label: "Feedback Events", value: feedbackHistory.length },
          ]}
          compact
        />
        <CompactList
          items={(patternRecognition?.interpretive_archetypes ?? []).map((item) => `${item.name}: ${item.signal}`)}
          emptyText="Interpretive archetypes will appear after governed evidence memory accumulates."
        />
      </Panel>
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
