import { buildIntakeStages, normalizeUploadStatus as normalizeUploadLifecycle } from "../../viewModels/uploadFlow";
import { Panel } from "../workspacePrimitives";

const hiddenFileInputStyle = {
  position: "absolute",
  width: "1px",
  height: "1px",
  padding: 0,
  margin: "-1px",
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0,
};

function clampPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return "";
  if (value < 60) return `${Math.ceil(value)} sec remaining`;
  return `${Math.ceil(value / 60)} min remaining`;
}

function normalizeStatusText(value) {
  return String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\.{2,}$/g, "")
    .replace(/[.。]+$/g, "")
    .toLowerCase();
}

function primaryJobStatus(uploadJob, uploadState) {
  return normalizeUploadLifecycle(
    uploadJob?.processing_state
      ?? uploadJob?.processingState
      ?? uploadJob?.status
      ?? uploadState
  );
}

function uploadViewState({ uploadState, hasSelectedFiles, isUploadProcessing }) {
  const normalized = normalizeUploadLifecycle(uploadState);
  if (["failed", "error", "validation_error", "cancelled", "timeout"].includes(normalized)) return "failed";
  if (normalized === "complete") return "complete";
  if (normalized === "uploading") return "uploading";
  if (isUploadProcessing(uploadState)) return "analyzing";
  if (hasSelectedFiles || normalized === "validated") return "fileSelected";
  return "noFile";
}

function operatorStatusText({ viewState, uploadJob, uploadState, latestMessage }) {
  if (viewState === "uploading") return "Uploading CSV...";
  if (viewState === "complete") return "Analysis Complete";
  if (viewState === "finalizing") return "Finalizing results...";
  if (viewState === "failed") return "Analysis failed";

  const normalized = primaryJobStatus(uploadJob, uploadState);
  if (["building_fingerprint", "baseline_modeling", "structural_scoring"].includes(normalized)) {
    return "Building operating fingerprint...";
  }
  if (["writing_state", "cognition_ready", "saving_result"].includes(normalized)) {
    return "Generating results...";
  }
  if (["accepted", "queued", "validating_schema", "parsing", "processing"].includes(normalized)) {
    return "Processing telemetry...";
  }

  const cleanMessage = String(latestMessage || "").trim();
  return cleanMessage || "Processing telemetry...";
}

function resolveMainPercent({ viewState, uploadState, uploadJob, uploadTransfer, visibleProgressPercent }) {
  if (viewState === "complete") return 100;
  if (viewState === "finalizing") return 99;
  if (viewState === "uploading") {
    return clampPercent(uploadTransfer?.percent ?? visibleProgressPercent ?? 0);
  }
  if (viewState === "analyzing") {
    const jobPercent = uploadJob?.propagation_progress
      ?? uploadJob?.propagationProgress
      ?? uploadJob?.percent
      ?? uploadJob?.progress;
    const fallback = jobPercent ?? visibleProgressPercent ?? 0;
    return Math.min(99, clampPercent(fallback));
  }
  if (["failed", "error", "validation_error", "cancelled", "timeout"].includes(normalizeUploadLifecycle(uploadState))) return 100;
  return 0;
}

function estimateRemaining(uploadTransfer) {
  return formatDuration(
    uploadTransfer?.estimatedSecondsRemaining
      ?? uploadTransfer?.estimateSecondsRemaining
      ?? uploadTransfer?.remainingSeconds
      ?? uploadTransfer?.etaSeconds
  );
}

function valueOrDash(value) {
  const text = String(value ?? "").trim();
  return text || "--";
}

function isFinalAnalysisResult(value) {
  return Boolean(
    value
    && typeof value === "object"
    && Array.isArray(value.systems)
    && Array.isArray(value.insights)
  );
}

function finalAnalysisResult(latestUploadSnapshot, uploadJob) {
  const candidates = [
    latestUploadSnapshot?.latest_result?.analysis_result,
    latestUploadSnapshot?.analysis_result,
    latestUploadSnapshot?.current_upload?.result?.analysis_result,
    uploadJob?.latest_result?.analysis_result,
    uploadJob?.result?.analysis_result,
    uploadJob?.analysis_result,
    uploadJob?.result,
  ];
  return candidates.find(isFinalAnalysisResult) ?? null;
}

function completionSummary({ analysisResult }) {
  const fingerprint = analysisResult?.fingerprint ?? {};
  const fingerprintStatus = valueOrDash(
    fingerprint?.status
      ?? fingerprint?.drift_status
      ?? fingerprint?.label
      ?? "Established"
  );

  return [
    { label: "Systems identified", value: String(analysisResult.systems.length) },
    { label: "Insights found", value: String(analysisResult.insights.length) },
    { label: "Fingerprint status", value: fingerprintStatus },
  ];
}

function buildAdvancedRows({ uploadJob, uploadTransfer, propagationLabel, queuedWorkerDetail, latestMessage }) {
  const rawError = uploadJob?.error ?? uploadJob?.detail ?? uploadJob?.message;
  return [
    ["Upload ID", uploadJob?.job_id ?? uploadJob?.id],
    ["Stage name", uploadJob?.processing_state ?? uploadJob?.processingState ?? uploadJob?.status],
    ["Timing", uploadJob?.processing_time_seconds ? `${uploadJob.processing_time_seconds}s` : null],
    ["Transfer", uploadTransfer?.label],
    ["Finalization", uploadJob?.result_available ? "Result available" : uploadJob?.first_usable_available ? "First result available" : null],
    ["Worker", queuedWorkerDetail],
    ["Stage detail", propagationLabel],
    ["Raw message", latestMessage],
    ["Raw error", uploadJob?.error_type || uploadJob?.error ? rawError : null],
  ].filter(([, value]) => String(value ?? "").trim());
}

function AdvancedDetails({ latestUploadSnapshot, uploadJob, uploadState, uploadTransfer, propagationLabel, queuedWorkerDetail, latestMessage }) {
  const rows = buildAdvancedRows({ uploadJob, uploadTransfer, propagationLabel, queuedWorkerDetail, latestMessage });
  const stages = buildIntakeStages(
    latestUploadSnapshot?.latest_result ?? null,
    uploadJob?.processing_state ?? uploadJob?.status ?? uploadState,
    null,
    uploadJob,
  );
  const compactStages = stages.filter((stage) => ["active", "failed", "complete"].includes(stage.state));

  if (!rows.length && !compactStages.length) return null;

  return (
    <details className="upload-advanced-details">
      <summary>Advanced Details</summary>
      {rows.length ? (
        <dl className="upload-advanced-details__grid">
          {rows.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{String(value)}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {compactStages.length ? (
        <ol className="upload-advanced-details__stages" aria-label="Pipeline stages">
          {compactStages.map((stage) => (
            <li key={`${stage.title}-${stage.state}`}>
              <strong>{stage.title}</strong>
              <span>{stage.state}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </details>
  );
}

export default function IntakeFlowPanel({
  handleUpload,
  uploadInputRef,
  handleFileSelection,
  selectedFiles,
  latestUploadSnapshot,
  pendingUploadKind,
  selectedFileSize,
  isUploadProcessing,
  uploadState,
  openFilePicker,
  uploadJob,
  latestMessage,
  visibleProgressPercent,
  propagationLabel,
  queuedWorkerDetail = "",
  uploadTransfer,
  uploadStateMessage,
  batchResults = [],
  onRetryFailedUploads,
  onResetWorkspace,
  onViewResults,
}) {
  void uploadStateMessage;
  void batchResults;

  const hasSelectedFiles = selectedFiles?.length > 0;
  const selectedFileLabel = hasSelectedFiles
    ? (selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files selected`)
    : "No CSV selected";
  const fileKind = String(pendingUploadKind || "csv").toUpperCase();
  const rawViewState = uploadViewState({ uploadState, hasSelectedFiles, isUploadProcessing });
  const analysisResult = finalAnalysisResult(latestUploadSnapshot, uploadJob);
  const viewState = rawViewState === "complete" && !analysisResult ? "finalizing" : rawViewState;
  const statusText = operatorStatusText({ viewState, uploadJob, uploadState, latestMessage });
  const mainPercent = resolveMainPercent({ viewState, uploadState, uploadJob, uploadTransfer, visibleProgressPercent });
  const remaining = estimateRemaining(uploadTransfer);
  const errorMessage = String(latestMessage || "Choose another CSV and try again.").trim();
  const summary = analysisResult ? completionSummary({ analysisResult }) : [];
  const showProgress = viewState === "uploading" || viewState === "analyzing" || viewState === "finalizing";

  const chooseFileButtonText = hasSelectedFiles ? "Choose Another File" : "Choose CSV";

  return (
    <Panel title="Analyze System" className="span-7 upload-ops-panel">
      <form className={`intake-flow intake-flow--simple intake-flow--${viewState}`} onSubmit={handleUpload}>
        <input data-testid="csv-upload-input" ref={uploadInputRef} accept=".csv,text/csv" id="csv-upload" type="file" multiple className="intake-flow__input" style={hiddenFileInputStyle} onChange={handleFileSelection} />

        {(viewState === "noFile" || viewState === "fileSelected") ? (
          <section className="upload-simple-card" aria-label="Selected CSV">
            <div className="upload-simple-card__file">
              <strong>{selectedFileLabel}</strong>
              <span>{hasSelectedFiles ? `${fileKind} - ${selectedFileSize}` : "Choose a CSV to analyze."}</span>
            </div>
            <div className="upload-simple-actions">
              <button type="button" className="secondary-command-button" onClick={() => openFilePicker("csv")}>{chooseFileButtonText}</button>
              {hasSelectedFiles ? (
                <button data-testid="process-upload-button" className="command-button" type="submit" disabled={isUploadProcessing(uploadState)}>
                  Upload and Analyze
                </button>
              ) : null}
            </div>
          </section>
        ) : null}

        {showProgress ? (
          <section className="upload-simple-card upload-simple-card--processing" aria-live="polite" aria-label="Analysis progress">
            <div className="upload-simple-card__file">
              <strong>{selectedFileLabel}</strong>
              <span>{fileKind} - {selectedFileSize}</span>
            </div>
            <div className="upload-progress-summary">
              <span>{statusText}</span>
              <strong>{mainPercent}% complete</strong>
            </div>
            <div
              className="upload-progress-meter upload-progress-meter--single"
              aria-label={`Analysis ${mainPercent}% complete`}
              aria-valuemin="0"
              aria-valuemax="100"
              aria-valuenow={mainPercent}
              role="progressbar"
            >
              <span style={{ width: `${mainPercent}%` }} />
            </div>
            {remaining ? <p className="upload-simple-note">{remaining}</p> : null}
          </section>
        ) : null}

        {viewState === "complete" ? (
          <section className="upload-simple-card upload-simple-card--complete" aria-label="Analysis complete">
            <div className="upload-complete-header">
              <h3>Analysis Complete</h3>
              <span>{selectedFileLabel}</span>
            </div>
            <div className="upload-result-summary">
              {summary.map((item) => (
                <div key={item.label} className="upload-result-summary__item">
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
            <div className="upload-simple-actions">
              <button type="button" className="command-button" onClick={onViewResults}>View Results</button>
              <button type="button" className="secondary-command-button" onClick={onResetWorkspace}>Analyze Another CSV</button>
            </div>
          </section>
        ) : null}

        {viewState === "failed" ? (
          <section className="upload-simple-card upload-simple-card--failed" role="alert" aria-live="assertive">
            <div className="upload-complete-header">
              <h3>Analysis failed</h3>
              <span>{hasSelectedFiles ? selectedFileLabel : "No CSV selected"}</span>
            </div>
            <p className="upload-error-message">{errorMessage}</p>
            <div className="upload-simple-actions">
              <button type="button" className="command-button" onClick={() => onRetryFailedUploads?.()} disabled={!hasSelectedFiles}>Retry</button>
              <button type="button" className="secondary-command-button" onClick={() => openFilePicker("csv")}>Choose Another File</button>
            </div>
          </section>
        ) : null}

        <AdvancedDetails
          latestUploadSnapshot={latestUploadSnapshot}
          uploadJob={uploadJob}
          uploadState={uploadState}
          uploadTransfer={uploadTransfer}
          propagationLabel={propagationLabel}
          queuedWorkerDetail={queuedWorkerDetail}
          latestMessage={normalizeStatusText(latestMessage) === normalizeStatusText(statusText) ? "" : latestMessage}
        />
      </form>
    </Panel>
  );
}
