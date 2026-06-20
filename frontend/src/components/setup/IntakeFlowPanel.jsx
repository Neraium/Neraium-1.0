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
  if (uploadTransfer?.label) return uploadTransfer.label;
  return statusLines.at(-1) || uploadStageMessage;
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
  const uploadStageMessage = uploadProgressStage(uploadState, uploadJob);
  const uploadStatusLabel = customerUploadMessage({ uploadStageMessage, uploadTransfer, statusLines });
  const shouldShowUploadStatus = hasSelectedFiles || isUploadProcessing(uploadState) || hasValidationError || hasUploadError || Boolean(uploadJob) || visibleProgressPercent !== null;

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
            {shouldShowUploadStatus ? (
              <span className="intake-flow__progress" aria-live="polite">
                {isUploadProcessing(uploadState) ? <span className="upload-spinner" aria-hidden="true" /> : null}
                {uploadStatusLabel}
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
