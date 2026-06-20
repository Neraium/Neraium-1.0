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

function clampUploadPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

function uploadProgressStage(uploadState, uploadJob) {
  const state = String(uploadState || "").toLowerCase();
  const workerState = String(uploadJob?.worker_state || uploadJob?.workerState || "").toLowerCase();
  const processingState = String(uploadJob?.processing_state || uploadJob?.processingState || "").toLowerCase();

  if (["complete", "completed", "success"].includes(state) || processingState === "complete") return "Complete";
  if (["error", "failed", "validation_error"].includes(state)) return "Needs attention";
  if (state === "uploading") return "Uploading";
  if (workerState === "starting" || processingState === "queued") return "Queued";
  if (workerState === "running" || workerState === "active" || state === "running_sii") return "Processing";
  if (state === "validated") return "Ready";
  return "Upload status";
}

function customerUploadMessage({ uploadStage, uploadTransfer, statusLines }) {
  if (uploadTransfer?.label) return uploadTransfer.label;
  if (uploadStage === "Queued") return "Upload received. Waiting for processing to begin.";
  if (uploadStage === "Processing") return "Analyzing telemetry. This can continue in the background.";
  if (uploadStage === "Complete") return "Upload complete.";
  return statusLines.at(-1) || uploadStage;
}

const meterShellStyle = {
  display: "grid",
  gap: "10px",
  width: "100%",
  marginTop: "10px",
  padding: "14px",
  border: "1px solid rgba(154, 183, 193, 0.16)",
  borderRadius: "16px",
  background: "rgba(7, 13, 23, 0.42)",
};

const meterHeaderStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
  gap: "12px",
};

const meterTitleStyle = {
  color: "var(--text-primary)",
  fontSize: "1rem",
  fontWeight: 800,
  letterSpacing: "0.01em",
  textTransform: "none",
};

const meterPercentStyle = {
  color: "var(--text-primary)",
  fontSize: "1.35rem",
  fontWeight: 900,
  lineHeight: 1,
};

const progressTrackStyle = {
  width: "100%",
  height: "14px",
  overflow: "hidden",
  borderRadius: "999px",
  background: "rgba(255, 255, 255, 0.1)",
  boxShadow: "inset 0 0 0 1px rgba(255, 255, 255, 0.08)",
};

const progressFillBaseStyle = {
  display: "block",
  height: "100%",
  minWidth: "8px",
  borderRadius: "inherit",
  background: "linear-gradient(90deg, rgba(197, 146, 60, 0.98), rgba(244, 210, 132, 0.98))",
  transition: "width 320ms ease",
};

const meterCopyStyle = {
  margin: 0,
  color: "var(--text-secondary)",
  fontSize: "0.9rem",
  lineHeight: 1.35,
};

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
  onReprocessCurrentBatch,
  onResetWorkspace,
}) {
  const failedCount = batchResults.filter((entry) => entry.status === "failed").length;
  const successCount = batchResults.filter((entry) => entry.status === "success").length;
  const siiContractFailed = uploadJob?.error_type === "sii_completion_missing" || String(latestMessage || "").toLowerCase().includes("sii completion");
  const hasSelectedFiles = selectedFiles?.length > 0;
  const hasUploadError = uploadState === "error" || uploadState === "failed";
  const hasValidationError = uploadState === "validation_error";
  const primaryProgressText = String(uploadJob?.progress_label || latestMessage || "").trim();
  const secondaryProgressText = String(propagationLabel || uploadStateMessage(uploadState) || "").trim();
  const statusLines = buildStatusLines({ primaryProgressText, secondaryProgressText, queuedWorkerDetail });
  const selectedFileLabel = selectedFiles?.length
    ? (selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files selected`)
    : latestUploadSnapshot?.last_filename ?? "No file selected";
  const shouldShowBatchSummary = batchResults.length > 1 || failedCount > 0 || siiContractFailed;
  const uploadProgressPercent = clampUploadPercent(visibleProgressPercent);
  const uploadStage = uploadProgressStage(uploadState, uploadJob);
  const showUploadProgressBar = hasSelectedFiles || isUploadProcessing(uploadState) || hasValidationError || hasUploadError || Boolean(uploadJob);
  const uploadStatusLabel = customerUploadMessage({ uploadStage, uploadTransfer, statusLines });
  const shouldShowPlainStatus = !showUploadProgressBar && statusLines.length > 0;

  return (
    <Panel title="Upload Data" className="span-7 workspace-hero-panel upload-ops-panel">
      <form className="intake-flow intake-flow--ops" onSubmit={handleUpload}>
        <input data-testid="csv-upload-input" ref={uploadInputRef} accept=".csv,text/csv" id="csv-upload" type="file" multiple className="intake-flow__input" onChange={handleFileSelection} />
        <div className="upload-file-card">
          <div className="upload-file-card__main">
            <strong>{selectedFileLabel}</strong>
            <p>{selectedFiles?.length ? `${pendingUploadKind.toUpperCase()} - ${selectedFileSize}` : "Select a CSV telemetry file to begin."}</p>
          </div>
          <div className="upload-file-card__actions upload-file-card__actions--responsive">
            <button data-testid="onboarding-demo-csv-option" className="command-button" type="button" onClick={() => openFilePicker("csv")}>Choose File</button>
            <button data-testid="process-upload-button" className="command-button" type="submit" disabled={!selectedFiles?.length}>
              {isUploadProcessing(uploadState) ? "Processing" : "Upload Data"}
            </button>
          </div>
        </div>
        {hasValidationError || hasUploadError ? (
          <div className="upload-partial-alert" role="alert" aria-live="assertive">
            <strong>{hasValidationError ? "File not ready" : "Upload failed"}</strong>
            <span>{latestMessage}</span>
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
        {isUploadProcessing(uploadState) || hasValidationError || hasUploadError || visibleProgressPercent !== null || batchResults.length > 0 ? (
          <div className={`intake-flow__status intake-flow__status--${uploadJob?.error ? "error" : isUploadProcessing(uploadState) ? "active" : "idle"}`}>
            {showUploadProgressBar ? (
              <div className="upload-status-meter" style={meterShellStyle} aria-live="polite">
                <div className="upload-status-meter__header" style={meterHeaderStyle}>
                  <span style={meterTitleStyle}>{uploadStage}</span>
                  <strong style={meterPercentStyle}>{uploadProgressPercent}%</strong>
                </div>
                <div
                  className="upload-progress-meter"
                  style={progressTrackStyle}
                  aria-label={`Upload status: ${uploadProgressPercent}% complete`}
                  aria-valuemin="0"
                  aria-valuemax="100"
                  aria-valuenow={uploadProgressPercent}
                  role="progressbar"
                >
                  <span style={{ ...progressFillBaseStyle, width: `${uploadProgressPercent}%` }} />
                </div>
                <p style={meterCopyStyle}>{uploadStatusLabel}</p>
              </div>
            ) : null}
            {shouldShowPlainStatus ? (
              <span className="intake-flow__progress">
                {isUploadProcessing(uploadState) ? <span className="upload-spinner" aria-hidden="true" /> : null}
                {statusLines.at(-1)}
              </span>
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
