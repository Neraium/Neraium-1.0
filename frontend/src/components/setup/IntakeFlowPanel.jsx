import { buildIntakeStages, normalizeUploadStatus as normalizeUploadLifecycle } from "../../viewModels/uploadFlow";
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

  if (["complete", "completed", "success"].includes(state) || processingState === "complete") return "Analysis ready.";
  if (["error", "failed", "validation_error"].includes(state)) return "Telemetry needs attention.";
  if (state === "uploading") return "Sending telemetry.";
  if (workerState === "starting" || processingState === "queued") return "Telemetry received. Waiting for analysis to begin.";
  if (workerState === "running" || workerState === "active" || state === "running_sii") return "Processing telemetry. Building system story.";
  if (state === "validated") return "File selected. Upload is required before analysis.";
  return "Analysis status unavailable.";
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

function formatLifecycleHeadline(value, fallback) {
  const normalized = normalizeUploadLifecycle(value);
  const labels = {
    idle: "Awaiting upload",
    validated: "Ready to upload",
    uploading: "Uploading telemetry",
    accepted: "Validating CSV",
    queued: "Queued for analysis",
    validating_schema: "Validating CSV",
    parsing: "Normalizing telemetry",
    baseline_modeling: "Identifying systems",
    processing: "Normalizing telemetry",
    structural_scoring: "Mapping relationships",
    building_fingerprint: "Building fingerprint",
    writing_state: "Generating insights",
    cognition_ready: "Saving result",
    generating_replay: "Finalizing report",
    complete: "Ready to review",
    failed: "Needs attention",
    error: "Needs attention",
    validation_error: "Validation issue",
    cancelled: "Cancelled",
    timeout: "Timed out",
  };
  return labels[normalized] ?? String(fallback || "Awaiting upload").replace(/\.\.\.$/, "");
}

function buildWorkflowRail({ hasSelectedFiles, stageProgress }) {
  const activeStage = stageProgress.activeStage;
  const stages = [
    { id: "select", label: "Select file" },
    { id: "upload", label: "Upload" },
    { id: "analyze", label: "Analyze" },
    { id: "review", label: "Review" },
  ];

  return stages.map((stage, index) => {
    let state = "pending";
    if (index === 0) {
      state = hasSelectedFiles || ["upload", "processing", "complete"].includes(activeStage) ? "complete" : "active";
    }
    if (index === 1) {
      if (activeStage === "upload") state = "active";
      if (["processing", "complete"].includes(activeStage)) state = "complete";
    }
    if (index === 2) {
      if (activeStage === "processing") state = "active";
      if (activeStage === "complete") state = "complete";
    }
    if (index === 3) {
      if (activeStage === "complete") state = "active";
    }
    return {
      ...stage,
      state,
    };
  });
}

function formatRowCount(value) {
  const count = Number(value);
  if (!Number.isFinite(count) || count <= 0) return "Rows pending";
  return `${count.toLocaleString()} rows`;
}

function buildSupportFacts({ selectedFiles, selectedFileLabel, selectedFileSize, pendingUploadKind, uploadStatusLabel, latestUploadSnapshot, uploadJob }) {
  const currentUpload = latestUploadSnapshot?.current_upload ?? null;
  const latestRows = currentUpload?.row_count ?? currentUpload?.rows_received ?? uploadJob?.rows_received ?? 0;
  return [
    {
      label: selectedFiles?.length ? "Selected file" : "Next step",
      value: selectedFiles?.length ? "CSV selected" : currentUpload?.filename ?? "Choose telemetry CSV",
      detail: selectedFiles?.length ? `${String(pendingUploadKind || "csv").toUpperCase()} ready • ${selectedFileSize}` : "Pick a telemetry export to start the pipeline.",
    },
    {
      label: "Current stage",
      value: formatLifecycleHeadline(uploadJob?.processing_state ?? uploadJob?.status ?? null, uploadStatusLabel),
      detail: "Progress reflects backend milestones instead of placeholder timers.",
    },
    {
      label: "Latest accepted batch",
      value: formatRowCount(latestRows),
      detail: currentUpload?.filename ?? "No completed upload saved yet.",
    },
    {
      label: "Result readiness",
      value: uploadJob?.result_available || normalizeUploadLifecycle(uploadJob?.status ?? uploadJob?.processing_state) === "complete" ? "Ready to review" : "Awaiting analysis",
      detail: uploadJob?.result_available
        ? "Core result can be opened even if final report artifacts continue in the background."
        : "Systems, fingerprint, and insight generation complete before review opens.",
    },
  ];
}

function buildRunOutputs({ latestUploadSnapshot, hasSelectedFiles }) {
  const rowCount = latestUploadSnapshot?.current_upload?.row_count ?? latestUploadSnapshot?.latest_result?.row_count ?? 0;
  const outputs = [
    "Identified systems and grouped operating behaviors.",
    "Relationship mapping and fingerprint drift summary.",
    "Operator-ready insights with recommended checks.",
    "Data quality and completeness context so the result stays trustworthy.",
  ];
  if (rowCount > 0) {
    outputs.push(`The latest accepted batch includes ${Number(rowCount).toLocaleString()} telemetry rows.`);
  } else if (hasSelectedFiles) {
    outputs.push("The selected file becomes the baseline for the next analysis run.");
  }
  return outputs;
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
  uploadDebug,
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
    : "No telemetry file selected";
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
    ? [["Telemetry transfer", stageProgress.uploadPercent]]
    : ["processing", "complete"].includes(stageProgress.activeStage)
      ? [["Telemetry transfer", stageProgress.uploadPercent], ["Analysis", stageProgress.processingPercent]]
      : [];
  const shouldShowStatusBlock = shouldShowUploadStatus || shouldShowBatchSummary;
  const errorMessage = String(latestMessage || (hasValidationError ? "Select a valid telemetry file." : "Analysis failed. Select a new file and try again.")).trim();
  const showUploadDebug = import.meta.env.DEV;
  const workflowRail = buildWorkflowRail({ hasSelectedFiles, stageProgress });
  const pipelineStages = buildIntakeStages(latestUploadSnapshot?.latest_result ?? null, uploadJob?.processing_state ?? uploadJob?.status ?? uploadState, null, uploadJob);
  const supportFacts = buildSupportFacts({ selectedFiles, selectedFileLabel, selectedFileSize, pendingUploadKind, uploadStatusLabel, latestUploadSnapshot, uploadJob });
  const runOutputs = buildRunOutputs({ latestUploadSnapshot, hasSelectedFiles });

  return (
    <Panel title="Analyze System" subtitle="Upload telemetry and generate an operator-ready system report" className="span-7 workspace-hero-panel upload-ops-panel">
      <form className="intake-flow intake-flow--ops" onSubmit={handleUpload}>
        <input data-testid="csv-upload-input" ref={uploadInputRef} accept=".csv,text/csv" id="csv-upload" type="file" multiple className="intake-flow__input" style={hiddenFileInputStyle} onChange={handleFileSelection} />

        <div className="intake-flow__hero">
          <div className="intake-flow__hero-copy">
            <span className="section-token">Operational intake</span>
            <h3>Move from CSV to system-level findings</h3>
            <p>Upload a telemetry export and Neraium will validate it, map systems, build the operating fingerprint, and return an operator-ready result without forcing manual column-by-column interpretation.</p>
          </div>
          {visibleProgressPercent !== null && Number.isFinite(Number(visibleProgressPercent)) ? (
            <div className="intake-flow__hero-badge" aria-label={`Overall progress ${visibleProgressPercent}%`}>
              <strong>{visibleProgressPercent}%</strong>
              <span>Pipeline progress</span>
            </div>
          ) : null}
        </div>

        <div className="upload-file-card">
          <div className="upload-file-card__main">
            <strong>{selectedFileLabel}</strong>
            <p>{selectedFiles?.length ? `${String(pendingUploadKind || "csv").toUpperCase()} • ${selectedFileSize}` : "Select a telemetry file to begin."}</p>
          </div>
          <div className="upload-file-card__actions upload-file-card__actions--responsive">
            <button data-testid="onboarding-demo-csv-option" className="command-button" type="button" onClick={() => openFilePicker("csv")}>Choose Telemetry File</button>
            <button data-testid="process-upload-button" className="command-button" type="submit" disabled={!selectedFiles?.length || isUploadProcessing(uploadState)}>
              {isUploadProcessing(uploadState) ? "Processing telemetry" : hasSelectedFiles ? "Upload and Analyze" : "Analyze System"}
            </button>
          </div>
        </div>

        <div className="intake-stage-rail" aria-label="Upload and review workflow">
          {workflowRail.map((stage, index) => (
            <div key={stage.id} className={`intake-stage-rail__item intake-stage-rail__item--${stage.state}`}>
              <span className="intake-stage-rail__index">{index + 1}</span>
              <strong>{stage.label}</strong>
            </div>
          ))}
        </div>

        {hasValidationError || hasUploadError ? (
          <div className="upload-partial-alert" role="alert" aria-live="assertive" style={alertLayoutStyle}>
            <strong>{hasValidationError ? "File not ready" : "Analysis failed"}</strong>
            <p style={alertMessageStyle}>{errorMessage}</p>
            <div className="intake-flow__controls">
              <button
                type="button"
                className="secondary-command-button"
                onClick={() => openFilePicker("csv")}
              >
                Select New Telemetry File
              </button>
              {hasSelectedFiles ? (
                <button
                  type="button"
                  className="command-button"
                  onClick={() => onRetryFailedUploads?.()}
                >
                  Retry Analysis
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
              <div className="upload-stage-progress" style={stageWrapStyle} aria-label="Telemetry transfer and analysis progress">
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
                    <strong>Some telemetry files failed</strong>
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
                    Rebuild System Story
                  </button>
                )}
              </div>
            ) : null}
          </div>
        ) : null}

        <div className="intake-flow__workflow-grid">
          <section className="intake-flow__support-card intake-flow__support-card--wide" aria-label="Backend milestones">
            <div className="intake-flow__support-header">
              <div>
                <span className="section-token">Pipeline</span>
                <h3>Backend milestones</h3>
                <p>Each milestone reflects the actual analysis pipeline so operators can tell whether the run is validating data, building the fingerprint, or saving the result.</p>
              </div>
            </div>
            <div className="intake-stage-list" role="list">
              {pipelineStages.map((stage, index) => {
                const detailText = normalizeStatusText(stage.detail) === normalizeStatusText(uploadStatusLabel)
                  ? "Current backend stage is active."
                  : stage.detail;
                return (
                  <div key={`${stage.title}-${index}`} className={`intake-stage-list__item intake-stage-list__item--${stage.state}`} role="listitem">
                    <span className="intake-stage-list__index">{index + 1}</span>
                    <div>
                      <div className="intake-stage-list__heading">
                        <strong>{stage.title}</strong>
                        <span className={`intake-stage-list__status intake-stage-list__status--${stage.state}`}>{stage.state}</span>
                      </div>
                      <p>{detailText}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="intake-flow__support-card" aria-label="Run snapshot">
            <div className="intake-flow__support-header">
              <div>
                <span className="section-token">Snapshot</span>
                <h3>Current run at a glance</h3>
                <p>The selected file, current stage, and latest accepted upload stay visible while analysis runs.</p>
              </div>
            </div>
            <div className="intake-flow__fact-grid">
              {supportFacts.map((fact) => (
                <div key={fact.label} className="intake-flow__fact">
                  <span>{fact.label}</span>
                  <strong>{fact.value}</strong>
                  <p>{fact.detail}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="intake-flow__support-card" aria-label="Analysis outputs">
            <div className="intake-flow__support-header">
              <div>
                <span className="section-token">Outputs</span>
                <h3>What this run returns</h3>
                <p>The goal is a usable system report, not just a processed file.</p>
              </div>
            </div>
            <ul className="intake-output-list">
              {runOutputs.map((item) => (
                <li key={item}>
                  <strong>{item}</strong>
                </li>
              ))}
            </ul>
          </section>
        </div>

        {showUploadDebug ? (
          <div
            className="upload-debug-panel"
            style={{
              display: "grid",
              gap: "6px",
              marginTop: "10px",
              padding: "10px 12px",
              border: "1px solid rgba(255, 255, 255, 0.08)",
              borderRadius: "8px",
              background: "rgba(255, 255, 255, 0.03)",
              fontSize: "0.78rem",
              overflowWrap: "anywhere",
            }}
          >
            <strong>Upload Debug</strong>
            <span><strong>apiBaseConfig:</strong> {uploadDebug?.apiBaseConfig || "(same-origin)"}</span>
            <span><strong>runtimeApiBase:</strong> {uploadDebug?.runtimeApiBaseUrl || "(same-origin)"}</span>
            <span><strong>routeMode:</strong> {uploadDebug?.routeMode || "same-origin"}</span>
            <span><strong>uploadUrl:</strong> {uploadDebug?.uploadUrl || "n/a"}</span>
            <span><strong>response status:</strong> {uploadDebug?.responseStatus ?? "n/a"}</span>
            <span><strong>response body/error:</strong> {uploadDebug?.responseBodyOrError || "n/a"}</span>
          </div>
        ) : null}

        <details className="upload-secondary-actions">
          <summary>Analysis options</summary>
          <button type="button" className="secondary-command-button" onClick={onResetWorkspace}>Clear Analysis</button>
        </details>
      </form>
    </Panel>
  );
}
