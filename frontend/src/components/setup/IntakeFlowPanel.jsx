import { Panel } from "../workspacePrimitives";

function normalizeStatusText(value) {
  return String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\.{2,}$/g, "")
    .replace(/[.。]+$/g, "")
    .toLowerCase();
}

function buildStatusLines({ primaryProgressText, secondaryProgressText, queuedWorkerDetail }) {
  const lines = [];
  const seen = [];

  [primaryProgressText, secondaryProgressText, queuedWorkerDetail].forEach((value) => {
    const text = String(value || "").trim();
    if (!text) return;

    const normalized = normalizeStatusText(text);
    if (!normalized) return;

    const isDuplicate = seen.some((existing) => (
      existing === normalized
      || existing.includes(normalized)
      || normalized.includes(existing)
    ));

    if (!isDuplicate) {
      seen.push(normalized);
      lines.push(text);
    }
  });

  return lines;
}

function clampPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

function firstFinitePercent(...values) {
  const value = values.find((candidate) => Number.isFinite(Number(candidate)));
  return value === undefined ? null : clampPercent(value);
}

function uploadProgressStage(uploadState, uploadJob) {
  const state = String(uploadState || "").toLowerCase();
  const workerState = String(uploadJob?.worker_state || uploadJob?.workerState || "").toLowerCase();
  const processingState = String(uploadJob?.processing_state || uploadJob?.processingState || "").toLowerCase();

  if (["complete", "completed", "success"].includes(state) || processingState === "complete") return "Upload complete.";
  if (["error", "failed", "validation_error"].includes(state)) return "Upload needs attention.";
  if (state === "uploading") return "Uploading.";
  if (workerState === "starting" || processingState === "queued") return "Upload received. Waiting for processing to begin.";
  if (workerState === "running" || workerState === "active" || state === "running_sii") return "Analyzing telemetry. This can continue in the background.";
  if (state === "validated") return "Ready to upload.";
  return "Upload status unavailable.";
}

function customerUploadMessage({ uploadStageMessage, uploadTransfer, statusLines }) {
  const transferPercent = Number(uploadTransfer?.percent);
  if (uploadTransfer?.label && (!Number.isFinite(transferPercent) || transferPercent < 100)) return uploadTransfer.label;
  return statusLines[0] || uploadStageMessage;
}

function resolveStageProgress({ uploadState, uploadJob, uploadTransfer }) {
  const state = String(uploadState || "").toLowerCase();
  const processingState = String(uploadJob?.processing_state || uploadJob?.processingState || "").toLowerCase();
  const status = String(uploadJob?.status || "").toLowerCase();
  const isActiveProgressState = ["uploading", "running_sii", "processing", "complete"].includes(state);
  const isUploading = state === "uploading";
  const isComplete = isActiveProgressState && (["complete", "completed", "success"].includes(state) || processingState === "complete" || status === "complete");
  const isProcessing = isActiveProgressState && !isUploading && !isComplete;
  const uploadPercent = isProcessing || isComplete ? 100 : isUploading ? clampPercent(uploadTransfer?.percent ?? 0) : 0;
  const backendPercent = firstFinitePercent(
    uploadJob?.propagation_progress,
    uploadJob?.propagationProgress,
    uploadJob?.progress,
    uploadJob?.percent,
  );
  const processingPercent = isComplete ? 100 : isProcessing ? Math.min(99, backendPercent ?? 1) : 0;

  return {
    uploadPercent,
    processingPercent,
    activeStage: isComplete ? "complete" : isProcessing ? "processing" : isUploading ? "upload" : "idle",
  };
}

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

const stageWrapStyle = {
  display: "grid",
  gap: "10px",
  width: "100%",
  marginTop: "10px",
};

const stageRowStyle = {
  display: "grid",
  gap: "6px",
};

const stageHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "10px",
  color: "var(--text-secondary)",
  fontSize: "0.72rem",
  fontWeight: 800,
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const progressTrackStyle = {
  width: "100%",
  height: "10px",
  overflow: "hidden",
  borderRadius: "999px",
  background: "rgba(255, 255, 255, 0.08)",
  boxShadow: "inset 0 0 0 1px rgba(255, 255, 255, 0.06)",
};

const progressFillStyle = {
  display: "block",
  height: "100%",
  minWidth: "0",
  borderRadius: "inherit",
  background: "linear-gradient(90deg, rgba(197, 146, 60, 0.98), rgba(244, 210, 132, 0.98))",
  transition: "width 320ms ease",
};

const alertLayoutStyle = {
  display: "grid",
  gap: "12px",
  alignItems: "start",
};

const alertMessageStyle = {
  display: "block",
  margin: 0,
  lineHeight: 1.45,
  overflowWrap: "anywhere",
};

export default function IntakeFlowPanel({
  handleUpload,
  uploadInputRef,
  handleFileSelection,
  selectedFiles,
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
  onReprocessCurrentBatch,
  onResetWorkspace,
}) {
  const failedCount = batchResults.filter((entry) => entry.status === "failed").length;
  const successCount = batchResults.filter((entry) => entry.status === "success").length;
  const siiContractFailed = uploadJob?.error_type === "sii_completion_missing" || String(latestMessage || "").toLowerCase().includes("sii completion");
  const hasSelectedFiles = selectedFiles?.length > 0;
  const hasUploadError = uploadState === "error" || uploadState === "failed";
  const hasValidationError = uploadState === "validation_error";
  const hasTerminalUploadIssue = hasUploadError || hasValidationError;
  const primaryProgressText = String(uploadJob?.progress_label || latestMessage || "").trim();
  const secondaryProgressText = String(propagationLabel || uploadStateMessage(uploadState) || "").trim();
  const statusLines = buildStatusLines({
    primaryProgressText,
    secondaryProgressText: hasTerminalUploadIssue ? "" : secondaryProgressText,
    queuedWorkerDetail: hasTerminalUploadIssue ? "" : queuedWorkerDetail,
  });
  const selectedFileLabel = selectedFiles?.length
    ? (selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files selected`)
    : "No file selected";
  const shouldShowBatchSummary = batchResults.length > 1 || failedCount > 0 || siiContractFailed;
  const uploadStageMessage = uploadProgressStage(uploadState, uploadJob);
  const uploadStatusLabel = customerUploadMessage({ uploadStageMessage, uploadTransfer, statusLines });
  const activeUploadProgressState = ["uploading", "running_sii", "processing", "complete"].includes(String(uploadState || "").toLowerCase());
  const hasCurrentJob = Boolean(uploadJob?.job_id ?? uploadJob?.id ?? uploadJob?.status ?? uploadJob?.processing_state ?? uploadJob?.processingState);
  const hasActiveTransfer = Boolean(uploadTransfer) && Number.isFinite(Number(uploadTransfer?.percent));
  const hasCurrentProgressSource = hasCurrentJob || hasActiveTransfer;
  const shouldShowUploadStatus = !hasTerminalUploadIssue && (hasSelectedFiles || (activeUploadProgressState && hasCurrentProgressSource));
  const stageProgress = resolveStageProgress({ uploadState, uploadJob, uploadTransfer });
  const shouldShowStageBars = !hasTerminalUploadIssue && activeUploadProgressState && hasCurrentProgressSource;
  const stageProgressRows = stageProgress.activeStage === "upload"
    ? [["Upload", stageProgress.uploadPercent]]
    : ["processing", "complete"].includes(stageProgress.activeStage)
      ? [["Upload", stageProgress.uploadPercent], ["Processing", stageProgress.processingPercent]]
      : [];
  const shouldShowStatusBlock = shouldShowUploadStatus || shouldShowBatchSummary;
  const errorMessage = String(latestMessage || (hasValidationError ? "Select a valid telemetry file." : "Upload failed. Select a new file and try again.")).trim();

  return (
    <Panel title="Upload Data" className="span-7 workspace-hero-panel upload-ops-panel">
      <form className="intake-flow intake-flow--ops" onSubmit={handleUpload}>
        <input data-testid="csv-upload-input" ref={uploadInputRef} accept=".csv,text/csv" id="csv-upload" type="file" multiple className="intake-flow__input" style={hiddenFileInputStyle} onChange={handleFileSelection} />
        <div className="upload-file-card">
          <div className="upload-file-card__main">
            <strong>{selectedFileLabel}</strong>
            <p>{selectedFiles?.length ? `${pendingUploadKind.toUpperCase()} - ${selectedFileSize}` : "Select a CSV telemetry file to begin."}</p>
          </div>
          <div className="upload-file-card__actions upload-file-card__actions--responsive">
            <button data-testid="onboarding-demo-csv-option" className="command-button" type="button" onClick={() => openFilePicker("csv")}>Choose File</button>
            <button data-testid="process-upload-button" className="command-button" type="submit" disabled={!selectedFiles?.length || isUploadProcessing(uploadState)}>
              {isUploadProcessing(uploadState) ? "Processing" : "Upload Data"}
            </button>
          </div>
        </div>
        {hasValidationError || hasUploadError ? (
          <div className="upload-partial-alert" role="alert" aria-live="assertive" style={alertLayoutStyle}>
            <strong>{hasValidationError ? "File not ready" : "Upload failed"}</strong>
            <p style={alertMessageStyle}>{errorMessage}</p>
            <div className="intake-flow__controls">
              <button
                type="button"
                className="secondary-command-button"
                onClick={() => openFilePicker("csv")}
              >
                Select New File
              </button>
              {hasSelectedFiles ? (
                <button
                  type="submit"
                  className="command-button"
                >
                  Retry Upload
                </button>
              ) : null}
            </div>
          </div>
        ) : null}
        {shouldShowStatusBlock ? (
          <div className={`intake-flow__status intake-flow__status--${uploadJob?.error ? "error" : isUploadProcessing(uploadState) ? "active" : "idle"}`}>
            {shouldShowUploadStatus ? (
              <span className="intake-flow__progress" aria-live="polite">
                {isUploadProcessing(uploadState) ? <span className="upload-spinner" aria-hidden="true" /> : null}
                {uploadStatusLabel}
              </span>
            ) : null}
            {shouldShowStageBars ? (
              <div className="upload-stage-progress" style={stageWrapStyle} aria-label="Upload and processing progress">
                {stageProgressRows.map(([label, percent]) => (
                  <div className="upload-stage-progress__row" style={stageRowStyle} key={label}>
                    <div className="upload-stage-progress__header" style={stageHeaderStyle}>
                      <span>{label}</span>
                      <strong>{percent}%</strong>
                    </div>
                    <div
                      className="upload-progress-meter"
                      style={progressTrackStyle}
                      aria-label={`${label} ${percent}% complete`}
                      aria-valuemin="0"
                      aria-valuemax="100"
                      aria-valuenow={percent}
                      role="progressbar"
                    >
                      <span style={{ ...progressFillStyle, width: `${percent}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
            {shouldShowBatchSummary ? (
              <div className="intake-flow__batch-results">
                <span>{`Batch: ${successCount} succeeded, ${failedCount} failed, ${batchResults.length - successCount - failedCount} pending.`}</span>
                {failedCount > 0 && (
                  <div className="upload-partial-alert" role="status" aria-live="polite">
                    <strong>Some files failed</strong>
                    <span>{`${successCount} succeeded, ${failedCount} failed. Retry the failed files.`}</span>
                  </div>
                )}
                {failedCount > 0 && (
                  <button className="secondary-command-button" type="button" onClick={onRetryFailedUploads}>
                    Retry Failed Files
                  </button>
                )}
                {siiContractFailed && (
                  <button className="secondary-command-button" type="button" onClick={onReprocessCurrentBatch}>
                    Reprocess Job
                  </button>
                )}
              </div>
            ) : null}
          </div>
        ) : null}
        <details className="upload-secondary-actions">
          <summary>Workspace options</summary>
          <button type="button" className="secondary-command-button" onClick={onResetWorkspace}>Clear Upload Workspace</button>
        </details>
      </form>
    </Panel>
  );
}
