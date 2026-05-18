import { Panel, WorkflowStages } from "../workspacePrimitives";
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
  uploadTransfer,
  formatFileSize,
  formatTransferSpeed,
  uploadStateMessage,
  setCopyState,
  copyState,
  isJsonSchemaOpen,
  setIsJsonSchemaOpen,
  intakeStages,
  batchResults = [],
  onRetryFailedUploads,
  onReprocessCurrentBatch,
}) {
  const jsonIngestion = uploadJob?.result_summary?.json_ingestion;
  const hasJsonDiagnostics = Boolean(
    jsonIngestion
    && (
      Number.isFinite(jsonIngestion.readings_received)
      || Number.isFinite(jsonIngestion.readings_accepted)
      || Number.isFinite(jsonIngestion.readings_rejected)
    )
  );
  const rejectionSummary = jsonIngestion?.rejection_reasons
    ? Object.entries(jsonIngestion.rejection_reasons)
      .filter(([, count]) => Number(count) > 0)
      .map(([reason, count]) => `${reason.replaceAll("_", " ")}: ${count}`)
      .slice(0, 4)
    : [];
  const failedCount = batchResults.filter((entry) => entry.status === "failed").length;
  const successCount = batchResults.filter((entry) => entry.status === "success").length;
  const siiContractFailed = uploadJob?.error_type === "sii_completion_missing" || String(latestMessage || "").toLowerCase().includes("sii completion");

  return (
    <>
      <Panel title="Upload Data" className="span-7 workspace-hero-panel upload-ops-panel">
        <form className="intake-flow intake-flow--ops" onSubmit={handleUpload}>
          <div className="intake-flow__header">
            <div>
              <p className="section-token">Historian Pilot Intake</p>
              <h3>Acquire - Normalize - Baseline - Analyze</h3>
            </div>
            <p>Upload a historian export for read-only pilot intake and structural analysis.</p>
          </div>
          <input ref={uploadInputRef} accept=".csv,text/csv" id="csv-upload" type="file" multiple className="intake-flow__input" onChange={handleFileSelection} />
          <div className="upload-file-card">
            <div className="upload-file-card__main">
              <span className="upload-file-card__label">Telemetry source</span>
              <strong>{selectedFiles?.length ? (selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files selected`) : latestUploadSnapshot?.last_filename ?? "No file selected"}</strong>
              <p>{selectedFiles?.length ? `${pendingUploadKind.toUpperCase()} batch - ${selectedFileSize}` : "Choose CSV or JSON telemetry export."}</p>
              <p>{uploadReadinessMessage(selectedFiles?.[0] ?? null)}</p>
            </div>
            <div className="upload-file-card__actions">
              <button data-testid="onboarding-demo-csv-option" className="secondary-command-button" type="button" disabled={isUploadProcessing(uploadState)} onClick={() => openFilePicker("csv")}>Select CSV</button>
              <button className="secondary-command-button" type="button" disabled={isUploadProcessing(uploadState)} onClick={() => openFilePicker("json")}>Select JSON</button>
              <button className="command-button" type="submit" disabled={!selectedFiles?.length || isUploadProcessing(uploadState)}>
                {isUploadProcessing(uploadState) ? "Processing" : `Process ${pendingUploadKind.toUpperCase()}`}
              </button>
            </div>
          </div>
          <div className={`intake-flow__status intake-flow__status--${uploadJob?.error ? "error" : isUploadProcessing(uploadState) ? "active" : "idle"}`}>
            <span className="intake-flow__progress">{isUploadProcessing(uploadState) && <span className="upload-spinner" aria-hidden="true" />}{uploadJob?.progress_label || latestMessage}</span>
            <span>{uploadJob?.job_id ? `Job ${uploadJob.job_id}` : uploadStateMessage(uploadState)}</span>
            {visibleProgressPercent !== null && (
              <div className="upload-progress-meter" aria-label="Telemetry intake progress" aria-valuemin="0" aria-valuemax="100" aria-valuenow={visibleProgressPercent} role="progressbar">
                <span style={{ width: `${visibleProgressPercent}%` }} />
              </div>
            )}
            {uploadTransfer && <span>{`${formatFileSize(uploadTransfer.loaded)} of ${formatFileSize(uploadTransfer.total)} at ${formatTransferSpeed(uploadTransfer.speedBytesPerSecond)}.`}</span>}
            {hasJsonDiagnostics && (
              <span>
                {`JSON accepted ${jsonIngestion.readings_accepted ?? 0}/${jsonIngestion.readings_received ?? 0} readings`}
                {Number(jsonIngestion.readings_rejected ?? 0) > 0 ? ` (${jsonIngestion.readings_rejected} rejected).` : "."}
              </span>
            )}
            {rejectionSummary.length > 0 && (
              <span>{`Rejected details: ${rejectionSummary.join(" | ")}`}</span>
            )}
            {Array.isArray(jsonIngestion?.parsing_notes) && jsonIngestion.parsing_notes.length > 0 && (
              <span>{jsonIngestion.parsing_notes.slice(0, 2).join(" ")}</span>
            )}
            {batchResults.length > 0 && (
              <div className="intake-flow__batch-results">
                <span>{`Batch: ${successCount} succeeded, ${failedCount} failed, ${batchResults.length - successCount - failedCount} pending.`}</span>
                {batchResults.map((entry) => (
                  <span key={entry.id}>{`${entry.fileName}: ${entry.status}${entry.message ? ` - ${entry.message}` : ""}`}</span>
                ))}
                {failedCount > 0 && (
                  <button className="secondary-command-button" type="button" onClick={onRetryFailedUploads} disabled={isUploadProcessing(uploadState)}>
                    Retry Failed Files
                  </button>
                )}
                {siiContractFailed && (
                  <button className="secondary-command-button" type="button" onClick={onReprocessCurrentBatch} disabled={isUploadProcessing(uploadState)}>
                    Reprocess Job
                  </button>
                )}
              </div>
            )}
          </div>
        </form>
        <div className="connector-json-hint">
          <div className="connector-json-hint__header">
            <p className="section-token">JSON upload schema</p>
            <div className="connector-json-hint__actions">
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
                {isJsonSchemaOpen ? "Hide Schema" : "Show Schema"}
              </button>
            </div>
          </div>
          {isJsonSchemaOpen && <pre className="connector-json-hint__code">{JSON_UPLOAD_SCHEMA_EXAMPLE}</pre>}
        </div>
      </Panel>
      <Panel title="Model Construction State" className="span-5 upload-cognition-state">
        <WorkflowStages items={intakeStages} />
      </Panel>
    </>
  );
}
