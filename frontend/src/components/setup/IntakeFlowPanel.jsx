import { Panel } from "../workspacePrimitives";

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
  const showSecondaryProgressText = secondaryProgressText && secondaryProgressText !== primaryProgressText;
  const selectedFileLabel = selectedFiles?.length
    ? (selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files selected`)
    : latestUploadSnapshot?.last_filename ?? "No file selected";
  const shouldShowBatchSummary = batchResults.length > 1 || failedCount > 0 || siiContractFailed;

  return (
    <Panel title="Upload Data" className="span-7 workspace-hero-panel upload-ops-panel">
      <form className="intake-flow intake-flow--ops" onSubmit={handleUpload}>
        <input ref={uploadInputRef} accept=".csv,text/csv" id="csv-upload" type="file" multiple className="intake-flow__input" onChange={handleFileSelection} />
        <div className="upload-file-card">
          <div className="upload-file-card__main">
            <strong>{selectedFileLabel}</strong>
            <p>{selectedFiles?.length ? `${pendingUploadKind.toUpperCase()} - ${selectedFileSize}` : "Select a CSV telemetry file to begin."}</p>
          </div>
          <div className="upload-file-card__actions upload-file-card__actions--responsive">
            <button data-testid="onboarding-demo-csv-option" className="command-button" type="button" onClick={() => openFilePicker("csv")}>Choose File</button>
            <button className="command-button" type="submit" disabled={!selectedFiles?.length}>
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
            {primaryProgressText ? <span className="intake-flow__progress">{isUploadProcessing(uploadState) && <span className="upload-spinner" aria-hidden="true" />}{primaryProgressText}</span> : null}
            {showSecondaryProgressText ? <span>{secondaryProgressText}</span> : null}
            {queuedWorkerDetail ? <span className="metadata-text">{queuedWorkerDetail}</span> : null}
            {visibleProgressPercent !== null ? (
              <div className="upload-progress-meter" aria-label="Upload progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={visibleProgressPercent} role="progressbar">
                <span style={{ width: `${visibleProgressPercent}%` }} />
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