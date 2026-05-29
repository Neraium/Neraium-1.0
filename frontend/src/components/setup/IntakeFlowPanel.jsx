import { Panel } from "../workspacePrimitives";
import { JSON_UPLOAD_SCHEMA_EXAMPLE } from "./setupConstants";

export default function IntakeFlowPanel({
  handleUpload,
  uploadInputRef,
  handleFileSelection,
  selectedFiles,
  latestUploadSnapshot,
  pendingUploadKind,
  selectedFileSize,
  uploadReadinessMessage,
  isUploadProcessing,
  uploadState,
  openFilePicker,
  uploadJob,
  latestMessage,
  visibleProgressPercent,
  propagationLabel,
  uploadTransfer,
  formatFileSize,
  formatTransferSpeed,
  uploadStateMessage,
  setCopyState,
  copyState,
  isJsonSchemaOpen,
  setIsJsonSchemaOpen,
  batchResults = [],
  onRetryFailedUploads,
  onReprocessCurrentBatch,
}) {
  const failedCount = batchResults.filter((entry) => entry.status === "failed").length;
  const successCount = batchResults.filter((entry) => entry.status === "success").length;
  const siiContractFailed = uploadJob?.error_type === "sii_completion_missing" || String(latestMessage || "").toLowerCase().includes("sii completion");
  const hasSelectedFiles = selectedFiles?.length > 0;
  const hasUploadError = uploadState === "error" || uploadState === "failed";
  const hasValidationError = uploadState === "validation_error";

  return (
    <>
      <Panel title="Upload Data" className="span-7 workspace-hero-panel upload-ops-panel">
        <form className="intake-flow intake-flow--ops" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <div>
              <h3>Upload</h3>
            </div>
          </div>
          <input ref={uploadInputRef} accept=".csv,.json,text/csv,application/json" id="csv-upload" type="file" multiple className="intake-flow__input" onChange={handleFileSelection} />
          <div className="upload-file-card">
            <div className="upload-file-card__main">
              <span className="upload-file-card__label">Telemetry source</span>
              <strong>{selectedFiles?.length ? (selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files selected`) : latestUploadSnapshot?.last_filename ?? "No file selected"}</strong>
              <p>{selectedFiles?.length ? `${pendingUploadKind.toUpperCase()} - ${selectedFileSize}` : "Select a file to continue."}</p>
            </div>
            <div className="upload-file-card__actions upload-file-card__actions--responsive">
              <button data-testid="onboarding-demo-csv-option" className="command-button" type="button" onClick={() => openFilePicker("csv")}>Select CSV</button>
              <button className="command-button" type="submit" disabled={!selectedFiles?.length}>
                {isUploadProcessing(uploadState) ? "Processing" : "Process Upload"}
              </button>
              <button
                className="secondary-command-button"
                type="button"
                disabled={isUploadProcessing(uploadState)}
                onClick={() => setIsJsonSchemaOpen((current) => !current)}
              >
                {isJsonSchemaOpen ? "Close Advanced" : "Advanced"}
              </button>
            </div>
          </div>
          {hasValidationError || hasUploadError ? (
            <div className="upload-partial-alert" role="alert" aria-live="assertive">
              <strong>{hasValidationError ? "Upload Validation Error" : "Upload Processing Error"}</strong>
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
          <div className={`intake-flow__status intake-flow__status--${uploadJob?.error ? "error" : isUploadProcessing(uploadState) ? "active" : "idle"}`}>
            <span className="intake-flow__progress">{isUploadProcessing(uploadState) && <span className="upload-spinner" aria-hidden="true" />}{uploadJob?.progress_label || latestMessage}</span>
            <span>{propagationLabel || uploadStateMessage(uploadState)}</span>
            {visibleProgressPercent !== null && (
              <>
                <div className="upload-progress-meter" aria-label="Telemetry intake progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={visibleProgressPercent} role="progressbar">
                  <span style={{ width: `${visibleProgressPercent}%` }} />
                </div>
                <span className="metadata-text">{propagationLabel || uploadJob?.progress_label || latestMessage}</span>
              </>
            )}
            {uploadTransfer && <span>{`${formatFileSize(uploadTransfer.loaded)} of ${formatFileSize(uploadTransfer.total)} at ${formatTransferSpeed(uploadTransfer.speedBytesPerSecond)}.`}</span>}
            {batchResults.length > 0 && (
              <div className="intake-flow__batch-results">
                <span>{`Batch: ${successCount} succeeded, ${failedCount} failed, ${batchResults.length - successCount - failedCount} pending.`}</span>
                {failedCount > 0 && (
                  <div className="upload-partial-alert" role="status" aria-live="polite">
                    <strong>Partial Success</strong>
                    <span>{`${successCount} succeeded, ${failedCount} failed. Retry failed files to complete the session.`}</span>
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
            )}
          </div>
        </form>
        {isJsonSchemaOpen ? (
          <div className="connector-json-hint">
            <div className="connector-json-hint__header">
              <p className="section-token">Developer / Integration Tools</p>
              <div className="connector-json-hint__actions">
                <button className="secondary-command-button" type="button" onClick={() => openFilePicker("json")}>
                  Use JSON
                </button>
                <button className="secondary-command-button" type="button" onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(JSON_UPLOAD_SCHEMA_EXAMPLE);
                    setCopyState("copied");
                  } catch {
                    setCopyState("error");
                  }
                }}>
                  {copyState === "copied" ? "Copied" : copyState === "error" ? "Copy failed" : "Copy Example"}
                </button>
                <button className="secondary-command-button" type="button" onClick={() => setIsJsonSchemaOpen((current) => !current)}>
                  Hide Advanced
                </button>
              </div>
            </div>
            {isJsonSchemaOpen ? <pre className="connector-json-hint__code">{JSON_UPLOAD_SCHEMA_EXAMPLE}</pre> : null}
          </div>
        ) : null}
      </Panel>
      
    </>
  );
}
