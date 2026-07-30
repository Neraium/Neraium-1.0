import { useState } from "react";

import {
  buildIntakeStages,
  normalizeUploadStatus as normalizeUploadLifecycle,
  uploadErrorPresentation,
} from "../../viewModels/uploadFlow";
import { Panel } from "../workspacePrimitives";
import "../../styles/operational-workflow.css";
import "../../styles/upload-intelligence.css";

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

const INITIAL_BASELINE_WORKFLOW = [
  "Upload Data",
  "Validate Signals",
  "Learn Relationships",
  "Establish Baseline",
  "Begin Learning",
];

export const INITIAL_BASELINE_STAGES = [
  {
    id: "upload",
    label: "Upload",
    description: "Securely transferring historical operating data.",
  },
  {
    id: "validate",
    label: "Validate",
    description: "Verifying dataset integrity, timestamps, signal consistency, and data quality.",
  },
  {
    id: "learn",
    label: "Learn",
    description: "Learning how the infrastructure normally behaves by identifying persistent operating relationships across the dataset.",
  },
  {
    id: "ready",
    label: "Baseline Ready",
    description: "Initial operating model successfully established.",
  },
];

const COMPARISON_STAGES = [
  {
    id: "upload",
    label: "Upload",
    description: "Securely transferring the comparison dataset.",
  },
  {
    id: "validate",
    label: "Validate",
    description: "Verifying timestamps, signal consistency, and data quality.",
  },
  {
    id: "evaluate",
    label: "Evaluate",
    description: "Evaluating recorded operation against the active learned model.",
  },
  {
    id: "ready",
    label: "Results Ready",
    description: "The comparison dataset is ready for engineering review.",
  },
];

const FAILED_IMPORT_STAGES = [
  { id: "import", label: "Import Dataset" },
  { id: "validate", label: "Validate Signals" },
  { id: "learn", label: "Learn Relationships" },
  { id: "baseline", label: "Establish Baseline" },
  { id: "monitor", label: "Begin Learning" },
];

const UPLOAD_STATES = new Set([
  "accepted",
  "pending",
  "queued",
  "uploading",
]);

const VALIDATE_STATES = new Set([
  "validated",
  "validating",
  "validating_schema",
  "checking_structure",
  "checking_signal_quality",
  "mapping",
  "mapping_signals",
  "detecting_variables",
  "detecting_schema_signals",
  "parsing",
  "cleaning_imputing_data",
  "profiling_data_quality",
  "baseline_validating",
  "baseline_quality_assessment",
]);

function clampPercent(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 0;
  return Math.max(0, Math.min(100, Math.round(numeric)));
}

function normalizeStatusText(value) {
  return String(value || "")
    .trim()
    .replace(/\s+/g, " ")
    .replace(/\.{2,}$/g, "")
    .replace(/[.。]+$/g, "")
    .toLowerCase();
}

function normalizeStageText(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
}

function primaryJobStatus(uploadJob, uploadState) {
  return normalizeUploadLifecycle(
    uploadJob?.processing_state
      ?? uploadJob?.processingState
      ?? uploadJob?.propagation_stage
      ?? uploadJob?.propagationStage
      ?? uploadJob?.status
      ?? uploadState
  );
}

function rawJobStatus(uploadJob, uploadState) {
  return normalizeStageText(
    uploadJob?.propagation_stage
      ?? uploadJob?.propagationStage
      ?? uploadJob?.processing_state
      ?? uploadJob?.processingState
      ?? uploadJob?.status
      ?? uploadState
  );
}

function uploadViewState({ uploadState, hasSelectedFiles, isUploadProcessing }) {
  const normalized = normalizeUploadLifecycle(uploadState);
  if (normalized === "completion_error") return "completion_error";
  if (["failed", "error", "validation_error", "cancelled", "timeout"].includes(normalized)) return "failed";
  if (["save_complete", "complete"].includes(normalized)) return "complete";
  if (["saving_results", "navigation_pending"].includes(normalized)) return "finalizing";
  if (normalized === "uploading") return "uploading";
  if (isUploadProcessing(uploadState)) return "processing";
  if (hasSelectedFiles || normalized === "validated") return "fileSelected";
  return "noFile";
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

function resolveMainPercent({ viewState, uploadJob, uploadTransfer, visibleProgressPercent }) {
  if (viewState === "complete") return 100;
  if (viewState === "finalizing") return 99;
  if (viewState === "uploading") {
    return clampPercent(uploadTransfer?.percent ?? visibleProgressPercent ?? 0);
  }
  if (viewState === "processing") {
    const backendPercent = uploadJob?.propagation_progress
      ?? uploadJob?.propagationProgress
      ?? uploadJob?.percent
      ?? uploadJob?.progress
      ?? visibleProgressPercent
      ?? 0;
    return Math.min(99, clampPercent(backendPercent));
  }
  return 0;
}

export function resolveBaselineProcessingStage({
  viewState,
  uploadJob,
  uploadState,
  uploadTransfer,
  comparison = false,
}) {
  const stages = comparison ? COMPARISON_STAGES : INITIAL_BASELINE_STAGES;
  if (viewState === "complete") return { ...stages[3], index: 3 };
  if (viewState === "finalizing") return { ...stages[2], index: 2 };
  if (viewState === "uploading") {
    return uploadTransfer?.stage === "validating"
      ? { ...stages[1], index: 1 }
      : { ...stages[0], index: 0 };
  }

  const raw = rawJobStatus(uploadJob, uploadState);
  const normalized = normalizeStageText(primaryJobStatus(uploadJob, uploadState));
  if (UPLOAD_STATES.has(raw) || UPLOAD_STATES.has(normalized)) return { ...stages[0], index: 0 };
  if (VALIDATE_STATES.has(raw) || VALIDATE_STATES.has(normalized)) return { ...stages[1], index: 1 };
  return { ...stages[2], index: 2 };
}

function firstDefined(...values) {
  return values.find((value) => value !== null && value !== undefined && value !== "");
}

function titleCase(value) {
  const text = String(value || "").trim().replaceAll("_", " ").replaceAll("-", " ");
  if (!text) return "";
  return text.replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatUtcTimestamp(value) {
  const date = new Date(String(value || ""));
  if (!Number.isFinite(date.getTime())) return "";
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
}

function formatTimeRange(start, end) {
  const formattedStart = formatUtcTimestamp(start);
  const formattedEnd = formatUtcTimestamp(end);
  if (!formattedStart && !formattedEnd) return "Not reported";
  if (!formattedStart) return `Through ${formattedEnd} UTC`;
  if (!formattedEnd) return `From ${formattedStart} UTC`;
  return `${formattedStart} – ${formattedEnd} UTC`;
}

function countCollection(value) {
  if (Array.isArray(value)) return value.length;
  if (value && typeof value === "object") return Object.keys(value).length;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function dataQualityLabel(dataQuality, suitability) {
  const rating = titleCase(firstDefined(
    dataQuality?.reliability_rating,
    dataQuality?.rating,
    dataQuality?.readiness,
    dataQuality?.analysis_gate_state,
  ));
  const score = Number(firstDefined(dataQuality?.reliability_score, dataQuality?.score));
  const base = rating || (Number.isFinite(score) ? "Assessed" : titleCase(suitability?.decision));
  if (base && Number.isFinite(score)) return `${base} · ${Math.round(score)}/100`;
  return base || "Not reported";
}

function learningConfidenceLabel(candidate, suitability, dataQuality) {
  const explicit = firstDefined(
    candidate?.learning_confidence,
    candidate?.confidence,
    dataQuality?.data_confidence?.score,
    dataQuality?.data_confidence?.confidence,
    suitability?.score,
  );
  const numeric = Number(explicit);
  if (Number.isFinite(numeric)) {
    const normalized = numeric > 0 && numeric <= 1 ? Math.round(numeric * 100) : Math.round(numeric);
    return `${Math.max(0, Math.min(100, normalized))}/100`;
  }
  return titleCase(explicit);
}

export function baselineCompletionSummary({
  result,
  analysisResult,
  uploadJob,
  selectedFileLabel,
}) {
  const candidate = result?.candidate_model ?? {};
  const source = candidate?.source ?? result?.source ?? {};
  const telemetrySchema = candidate?.telemetry_schema ?? result?.telemetry_schema ?? {};
  const timestampProfile = candidate?.timestamp_quality
    ?? result?.timestamp_quality
    ?? analysisResult?.timestamp_profile
    ?? uploadJob?.timestamp_profile
    ?? {};
  const dataQuality = candidate?.data_quality
    ?? result?.data_quality
    ?? analysisResult?.data_quality
    ?? uploadJob?.data_quality
    ?? {};
  const relationshipGraph = candidate?.relationship_graph
    ?? result?.relationship_graph
    ?? analysisResult?.relationship_graph
    ?? {};
  const suitability = result?.baseline_suitability ?? candidate?.suitability ?? {};
  const sourceRange = analysisResult?.source_time_ranges?.[0] ?? {};
  const signalCount = firstDefined(
    countCollection(telemetrySchema?.numeric_columns),
    countCollection(telemetrySchema?.signal_catalog),
    countCollection(candidate?.signal_characteristics),
    dataQuality?.numeric_column_count,
    analysisResult?.telemetry_signal_count,
    analysisResult?.signals_analyzed,
  );
  const relationshipCount = firstDefined(
    countCollection(relationshipGraph?.edges),
    countCollection(analysisResult?.relationships),
    analysisResult?.relationships_learned,
  );
  const confidence = learningConfidenceLabel(candidate, suitability, dataQuality);
  const rows = [
    {
      label: "Dataset",
      value: firstDefined(result?.filename, source?.filename, uploadJob?.filename, selectedFileLabel, "Not reported"),
    },
    {
      label: "Time range",
      value: formatTimeRange(
        firstDefined(timestampProfile?.first_timestamp, sourceRange?.baseline_start, sourceRange?.current_start),
        firstDefined(timestampProfile?.last_timestamp, sourceRange?.baseline_end, sourceRange?.current_end),
      ),
    },
    {
      label: "Signals analyzed",
      value: signalCount === null || signalCount === undefined ? "Not reported" : String(signalCount),
    },
    {
      label: "Relationships learned",
      value: relationshipCount === null || relationshipCount === undefined ? "Not reported" : String(relationshipCount),
    },
    {
      label: "Data quality",
      value: dataQualityLabel(dataQuality, suitability),
    },
  ];
  if (confidence) rows.push({ label: "Learning confidence", value: confidence });
  return rows;
}

function edgeProgress({ percent, stageIndex, edgeIndex, complete }) {
  if (complete) return 0;
  if (stageIndex < 1) return 100;
  if (stageIndex === 1) return edgeIndex < 3 ? 0 : 100;
  const learnedEdges = Math.max(4, Math.ceil((clampPercent(percent) / 100) * NETWORK_EDGES.length));
  return edgeIndex < learnedEdges ? 0 : 100;
}

const NETWORK_NODES = [
  { x: 34, y: 68, r: 4, stage: 0 },
  { x: 79, y: 30, r: 5, stage: 0 },
  { x: 88, y: 97, r: 4, stage: 0 },
  { x: 145, y: 64, r: 7, stage: 1 },
  { x: 202, y: 29, r: 4, stage: 1 },
  { x: 212, y: 98, r: 5, stage: 1 },
  { x: 277, y: 63, r: 4, stage: 2 },
  { x: 256, y: 111, r: 3, stage: 2 },
  { x: 266, y: 18, r: 3, stage: 2 },
];

const NETWORK_EDGES = [
  "M34 68L79 30",
  "M34 68L88 97",
  "M79 30L145 64",
  "M88 97L145 64",
  "M79 30L202 29",
  "M145 64L202 29",
  "M145 64L212 98",
  "M88 97L212 98",
  "M202 29L277 63",
  "M212 98L277 63",
  "M202 29L266 18",
  "M212 98L256 111",
];

function RelationshipLearningVisual({ percent, stage, complete = false }) {
  const stageIndex = stage?.index ?? 0;
  return (
    <div className={`baseline-learning-visual${complete ? " is-complete" : ""}`} aria-hidden="true">
      <div className="baseline-learning-visual__label">
        <span>Signals</span>
        <span>Learned operating model</span>
      </div>
      <svg viewBox="0 0 310 132" focusable="false">
        <defs>
          <filter id="baseline-node-glow" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="2.4" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <g className="baseline-learning-visual__ghosts">
          {NETWORK_EDGES.map((path) => <path key={`ghost-${path}`} d={path} />)}
        </g>
        <g className="baseline-learning-visual__edges">
          {NETWORK_EDGES.map((path, index) => (
            <path
              key={path}
              d={path}
              pathLength="100"
              style={{ "--edge-offset": edgeProgress({ percent, stageIndex, edgeIndex: index, complete }) }}
            />
          ))}
        </g>
        <g className="baseline-learning-visual__nodes" filter="url(#baseline-node-glow)">
          {NETWORK_NODES.map((node, index) => {
            const visible = complete || stageIndex >= node.stage;
            return (
              <g key={`${node.x}-${node.y}`} className={visible ? "is-visible" : ""} style={{ "--node-index": index }}>
                <circle className="baseline-learning-visual__node-ring" cx={node.x} cy={node.y} r={node.r + 5} />
                <circle className="baseline-learning-visual__node" cx={node.x} cy={node.y} r={node.r} />
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}

function BaselineWorkflow() {
  return (
    <ol className="baseline-learning-path" aria-label="How Neraium establishes its initial baseline">
      {INITIAL_BASELINE_WORKFLOW.map((label, index) => (
        <li key={label}>
          <span aria-hidden="true">{index + 1}</span>
          <strong>{label}</strong>
        </li>
      ))}
    </ol>
  );
}

function DatasetFileRow({ filename, size, status }) {
  const fullLabel = `${filename}, ${size}, ${status}`;
  return (
    <div className="upload-dataset-file" title={filename} aria-label={fullLabel}>
      <span className="upload-dataset-file__icon" aria-hidden="true" />
      <span className="upload-dataset-file__identity">
        <strong>{filename}</strong>
        <small>{size}</small>
      </span>
      <span className="upload-dataset-file__status">{status}</span>
    </div>
  );
}

function ProcessingPanel({
  comparison,
  dataset,
  percent,
  stage,
  uploadJob,
  uploadState,
  uploadTransfer,
  propagationLabel,
  queuedWorkerDetail,
  latestMessage,
  latestUploadSnapshot,
}) {
  const stages = comparison ? COMPARISON_STAGES : INITIAL_BASELINE_STAGES;
  return (
    <section
      className="baseline-processing-panel"
      aria-live="polite"
      aria-label={`${comparison ? "Comparison dataset" : "Initial baseline"} processing: ${stage.label}`}
    >
      <header className="baseline-processing-panel__header">
        <div>
          <span className="baseline-processing-panel__eyebrow">{comparison ? "Comparison workflow" : "Initial learning"}</span>
          <h3>{stage.label}</h3>
          <p>{stage.description}</p>
        </div>
        <p className="baseline-processing-panel__dataset"><span>Dataset</span><strong>{dataset}</strong></p>
      </header>
      <div className="baseline-processing-panel__body">
        <div
          className="baseline-stage-track"
          role="progressbar"
          aria-label={`${stage.label}, stage ${stage.index + 1} of ${stages.length}`}
          aria-valuemin="1"
          aria-valuemax={stages.length}
          aria-valuenow={stage.index + 1}
          aria-valuetext={stage.label}
        >
          <ol>
            {stages.map((item, index) => {
              const state = index < stage.index ? "complete" : index === stage.index ? "active" : "pending";
              return (
                <li key={item.id} className={`baseline-stage-track__item baseline-stage-track__item--${state}`} aria-current={state === "active" ? "step" : undefined}>
                  <span className="baseline-stage-track__marker" aria-hidden="true">{state === "complete" ? "✓" : index + 1}</span>
                  <div>
                    <strong>{item.label}</strong>
                    <p>{item.description}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
        <RelationshipLearningVisual percent={percent} stage={stage} />
      </div>
      {!comparison ? (
        <p className="baseline-processing-panel__policy">
          Continuous learning starts from this model. Temporary abnormalities never redefine normal without persistent, verified operating history.
        </p>
      ) : null}
      <AdvancedDetails
        latestUploadSnapshot={latestUploadSnapshot}
        uploadJob={uploadJob}
        uploadState={uploadState}
        uploadTransfer={uploadTransfer}
        propagationLabel={propagationLabel}
        queuedWorkerDetail={queuedWorkerDetail}
        latestMessage={latestMessage}
      />
    </section>
  );
}

function buildAdvancedRows({ uploadJob, uploadTransfer, propagationLabel, queuedWorkerDetail, latestMessage }) {
  const failed = ["failed", "error", "timeout", "cancelled"].includes(
    String(uploadJob?.processing_state ?? uploadJob?.processingState ?? uploadJob?.status ?? "").toLowerCase(),
  );
  return [
    ["Selected baseline ID", uploadJob?.baselineId],
    ["Completed job ID", uploadJob?.jobId ?? uploadJob?.job_id],
    ["Dataset ID", uploadJob?.datasetId ?? uploadJob?.dataset_id],
    ["Portfolio ID", uploadJob?.portfolioId],
    ["State source", uploadJob?.state_source ? String(uploadJob.state_source).replaceAll("_", " ") : null],
    ["Backend state", uploadJob?.processing_state ?? uploadJob?.processingState ?? uploadJob?.status],
    ["Elapsed time", uploadJob?.processing_time_seconds ? `${uploadJob.processing_time_seconds}s` : null],
    ["Transfer", uploadTransfer?.label],
    ["Worker", queuedWorkerDetail],
    ["Current operation", propagationLabel],
    ["System message", latestMessage],
    ...(failed ? [
      ["Error code", uploadJob?.errorCode ?? uploadJob?.error_code ?? uploadJob?.error_type],
      ["Failure stage", uploadJob?.stage ?? uploadJob?.failed_stage],
      ["Technical message", uploadJob?.technicalMessage ?? uploadJob?.technical_message],
      ["HTTP status", uploadJob?.response_status],
      ["Request ID", uploadJob?.request_id],
      ["Timestamp", uploadJob?.diagnostic_timestamp],
    ] : []),
  ].filter(([, value]) => String(value ?? "").trim());
}

function AdvancedDetails({
  latestUploadSnapshot,
  uploadJob,
  uploadState,
  uploadTransfer,
  propagationLabel,
  queuedWorkerDetail,
  latestMessage,
}) {
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
      <summary>
        <span className="upload-advanced-details__summary-label"><i aria-hidden="true" />Processing details</span>
        <span className="upload-advanced-details__chevron" aria-hidden="true" />
      </summary>
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
        <ol className="upload-advanced-details__stages" aria-label="Backend processing stages">
          {compactStages.map((item) => (
            <li key={`${item.title}-${item.state}`}>
              <strong>{item.title}</strong>
              <span>{item.state}</span>
            </li>
          ))}
        </ol>
      ) : null}
    </details>
  );
}

function RecoverySummary({ viewState, hasSelectedFiles, selectedFileLabel, uploadJob, errorMessage }) {
  const rows = viewState === "completion_error"
    ? [
      ["What happened", "The baseline was saved, but the operating workspace did not open."],
      ["What is preserved", "The learned model remains stored and can be opened again."],
      ["Next action", "Open the baseline again. If the workspace remains unavailable, refresh and retry."],
    ]
    : [
      ["What happened", errorMessage || "Neraium could not finish establishing the initial baseline."],
      ["What is preserved", hasSelectedFiles ? `${selectedFileLabel} remains selected for retry.` : "No dataset is currently selected."],
      ["Next action", uploadJob?.job_id ? "Retry this job. If it has expired, choose the source dataset again." : "Check the source file and choose the dataset again."],
    ];
  return (
    <dl className="upload-recovery-summary">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function failedImportStageRows(uploadJob = {}) {
  const failedStage = String(uploadJob?.stage ?? uploadJob?.failed_stage ?? uploadJob?.failedStage ?? "").trim().toLowerCase();
  const failedIndex = {
    import: 0,
    upload_transfer: 0,
    authentication: 0,
    dataset_creation: 0,
    file_storage: 0,
    baseline_job_creation: 0,
    csv_parsing: 1,
    validation: 1,
    relationship_learning: 2,
    baseline_relationship_learning: 2,
    baseline_processing: 3,
    baseline_creation: 3,
    server: 3,
    unexpected: 0,
  }[failedStage] ?? 0;
  return FAILED_IMPORT_STAGES.map((stage, index) => ({
    ...stage,
    state: index < failedIndex ? "complete" : index === failedIndex ? "failed" : "not-started",
    status: index < failedIndex ? "Complete" : index === failedIndex ? "Failed" : "Not started",
  }));
}

function SuccessState({
  comparison,
  summary,
  onOpenBaseline,
  onImportComparisonDataset,
  onViewResults,
  onResetWorkspace,
  latestUploadSnapshot,
  uploadJob,
  uploadState,
  uploadTransfer,
  propagationLabel,
  queuedWorkerDetail,
  latestMessage,
  baselineNavigationPending = false,
}) {
  if (comparison) {
    return (
      <section className="baseline-success" aria-labelledby="comparison-ready-heading" aria-live="polite">
        <header className="baseline-success__header">
          <span className="baseline-success__check" aria-hidden="true">✓</span>
          <div>
            <p className="baseline-success__eyebrow">Comparison workflow complete</p>
            <h3 id="comparison-ready-heading">Comparison Dataset Ready</h3>
          </div>
        </header>
        <dl className="baseline-success__summary">
          {summary.map((item) => <div key={item.label}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}
        </dl>
        <div className="upload-simple-actions upload-completion-actions">
          <button type="button" className="command-button upload-completion-actions__primary" onClick={onViewResults}>Open Results</button>
          <button type="button" className="secondary-command-button upload-completion-actions__secondary" onClick={onResetWorkspace}>Import Another Dataset</button>
        </div>
      </section>
    );
  }

  return (
    <section className="baseline-success" aria-labelledby="baseline-ready-heading" aria-live="polite">
      <header className="baseline-success__header baseline-success__header--with-model">
        <span className="baseline-success__check" aria-hidden="true">✓</span>
        <div>
          <p className="baseline-success__eyebrow">Initial learning complete</p>
          <h3 id="baseline-ready-heading">Initial Baseline Established</h3>
        </div>
        <div className="baseline-success__model" role="img" aria-label="Stable learned relationship network">
          <RelationshipLearningVisual percent={100} stage={{ index: 3 }} complete />
        </div>
      </header>
      <dl className="baseline-success__summary" aria-label="Initial baseline summary">
        {summary.map((item) => (
          <div key={item.label}>
            <dt>{item.label}</dt>
            <dd>{item.value}</dd>
          </div>
        ))}
      </dl>
      <div className="baseline-success__explanation">
        <p>Neraium has established its initial understanding of how this infrastructure normally behaves.</p>
        <p>This learned operating model becomes the foundation for continuous learning. Future historical datasets and live telemetry will be evaluated against this understanding.</p>
        <p>As verified operating history grows, Neraium continuously refines its understanding of normal while preserving enough historical context to detect meaningful and persistent changes in system behavior.</p>
      </div>
      <div className="upload-simple-actions upload-completion-actions">
        <button
          type="button"
          className="command-button upload-completion-actions__primary"
          onClick={onOpenBaseline}
          disabled={baselineNavigationPending}
          aria-disabled={baselineNavigationPending}
        >
          {baselineNavigationPending ? "Opening Baseline…" : "Open Baseline"}
        </button>
        <button type="button" className="secondary-command-button upload-completion-actions__secondary" onClick={onImportComparisonDataset}>Import Comparison Dataset</button>
      </div>
      <AdvancedDetails
        latestUploadSnapshot={latestUploadSnapshot}
        uploadJob={uploadJob}
        uploadState={uploadState}
        uploadTransfer={uploadTransfer}
        propagationLabel={propagationLabel}
        queuedWorkerDetail={queuedWorkerDetail}
        latestMessage={latestMessage}
      />
    </section>
  );
}

export default function IntakeFlowPanel({
  handleUpload,
  uploadInputRef,
  handleFileSelection,
  selectedFiles,
  latestUploadSnapshot,
  analysisResult: suppliedAnalysisResult = null,
  baselineResult = null,
  workflow = "create_baseline",
  selectedFileSize,
  fileValidationError = "",
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
  onChooseAnotherFile,
  onViewResults,
  onOpenBaseline,
  onReturnToPortfolio,
  baselineNavigationPending = false,
  onImportComparisonDataset,
}) {
  void uploadStateMessage;
  void batchResults;
  const [isDragActive, setIsDragActive] = useState(false);
  const comparison = workflow === "analyze_new_data";
  const hasSelectedFiles = selectedFiles?.length > 0;
  const selectedFileLabel = hasSelectedFiles
    ? (selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files selected`)
    : "No file selected";
  const rawViewState = uploadViewState({ uploadState, hasSelectedFiles, isUploadProcessing });
  const analysisResult = suppliedAnalysisResult ?? finalAnalysisResult(latestUploadSnapshot, uploadJob);
  const baselineCompletion = Boolean(baselineResult?.baselineId ?? baselineResult?.candidate_model);
  const viewState = rawViewState === "complete" && !analysisResult && !baselineCompletion ? "finalizing" : rawViewState;
  const showProgress = ["uploading", "processing", "finalizing"].includes(viewState);
  const mainPercent = resolveMainPercent({ viewState, uploadJob, uploadTransfer, visibleProgressPercent });
  const processingStage = resolveBaselineProcessingStage({
    viewState,
    uploadJob,
    uploadState,
    uploadTransfer,
    comparison,
  });
  const failurePresentation = uploadErrorPresentation({
    ...(uploadJob ?? {}),
    message: latestMessage || uploadJob?.message || uploadJob?.error,
  });
  const errorMessage = String(
    viewState === "failed"
      ? failurePresentation.message
      : latestMessage || "Check the source dataset and try again.",
  ).trim();
  const failedStages = failedImportStageRows(uploadJob);
  const summary = baselineCompletionSummary({
    result: baselineResult,
    analysisResult,
    uploadJob,
    selectedFileLabel,
  });
  const submitWorkflow = comparison ? "analyze_new_data" : "create_baseline";
  const title = comparison ? "Import Comparison Dataset" : "Establish Initial Baseline";
  const subtitle = comparison
    ? "Upload verified operating history to evaluate it against Neraium's active learned model. This workflow does not automatically redefine normal."
    : "Upload representative historical operating data so Neraium can learn how the system normally behaves.";

  function handleUploadDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
    setIsDragActive(true);
  }

  function handleUploadDragLeave(event) {
    if (event.relatedTarget && event.currentTarget.contains(event.relatedTarget)) return;
    setIsDragActive(false);
  }

  function handleUploadDrop(event) {
    event.preventDefault();
    setIsDragActive(false);
    handleFileSelection(event);
  }

  return (
    <Panel title={title} className="span-7 upload-ops-panel upload-ops-panel--command">
      <form
        className={`intake-flow intake-flow--simple intake-flow--${viewState}${comparison ? " intake-flow--comparison" : ""}`}
        onSubmit={(event) => handleUpload(event, submitWorkflow)}
        aria-busy={showProgress}
      >
        <p className="intake-flow__subtitle">{subtitle}</p>
        <input
          data-testid="csv-upload-input"
          ref={uploadInputRef}
          accept=".csv,text/csv"
          id="csv-upload"
          type="file"
          multiple
          className="intake-flow__input"
          style={hiddenFileInputStyle}
          aria-label="Choose historical operating dataset CSV files"
          tabIndex={-1}
          onChange={handleFileSelection}
        />

        {!comparison && ["noFile", "fileSelected"].includes(viewState) ? <BaselineWorkflow /> : null}

        {["noFile", "fileSelected"].includes(viewState) ? (
          <section
            className={`upload-analysis-card upload-analysis-card--baseline${isDragActive ? " upload-analysis-card--drag-active" : ""}`}
            aria-label={comparison ? "Comparison dataset import" : "Historical dataset for initial baseline"}
            onDragOver={handleUploadDragOver}
            onDragLeave={handleUploadDragLeave}
            onDrop={handleUploadDrop}
          >
            <div className="upload-analysis-card__content">
              <div className="upload-analysis-card__copy">
                <p className="upload-analysis-card__eyebrow">{comparison ? "Verified later history" : "SOURCE OPERATING HISTORY"}</p>
                <h3>{comparison ? "Choose a comparison dataset" : "Upload historical data"}</h3>
                {comparison ? (
                  <p className="upload-analysis-card__description">
                    Neraium will evaluate this history against the active model without treating temporary conditions as a new normal.
                  </p>
                ) : null}
              </div>

              {hasSelectedFiles ? (
                <DatasetFileRow filename={selectedFileLabel} size={selectedFileSize} status={fileValidationError ? "Unsupported" : "Ready"} />
              ) : (
                <button type="button" className="baseline-file-dropzone" onClick={() => openFilePicker("csv")}>
                  <span className="baseline-file-dropzone__icon" aria-hidden="true" />
                  <span>
                    <strong>Choose historical dataset</strong>
                    <small>CSV, SCADA export, or historian export</small>
                  </span>
                </button>
              )}

              {fileValidationError ? <p className="upload-error-message" role="alert">{fileValidationError}</p> : null}

              {hasSelectedFiles || !comparison ? (
                <div className="upload-simple-actions upload-analysis-card__actions upload-baseline-card__actions">
                  <button
                    data-testid="process-upload-button"
                    name="workflow"
                    value={submitWorkflow}
                    className="command-button upload-baseline-card__primary"
                    type="submit"
                    disabled={Boolean(fileValidationError) || isUploadProcessing(uploadState)}
                    aria-disabled={Boolean(fileValidationError) || isUploadProcessing(uploadState)}
                    title={fileValidationError || (isUploadProcessing(uploadState) ? "A dataset workflow is already in progress." : undefined)}
                  >
                    {comparison ? "Evaluate Against Baseline" : "Continue"}
                  </button>
                  {hasSelectedFiles ? <button type="button" className="baseline-file-replace" onClick={() => openFilePicker("csv")}>Replace file</button> : null}
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

        {showProgress ? (
          <ProcessingPanel
            comparison={comparison}
            dataset={selectedFileLabel}
            percent={mainPercent}
            stage={processingStage}
            uploadJob={uploadJob}
            uploadState={uploadState}
            uploadTransfer={uploadTransfer}
            propagationLabel={propagationLabel}
            queuedWorkerDetail={queuedWorkerDetail}
            latestMessage={normalizeStatusText(latestMessage) === normalizeStatusText(processingStage.description) ? "" : latestMessage}
            latestUploadSnapshot={latestUploadSnapshot}
          />
        ) : null}

        {viewState === "complete" ? (
          <SuccessState
            comparison={comparison}
            summary={summary}
            onOpenBaseline={onOpenBaseline ?? onViewResults}
            baselineNavigationPending={baselineNavigationPending}
            onImportComparisonDataset={onImportComparisonDataset ?? onResetWorkspace}
            onViewResults={onViewResults}
            onResetWorkspace={onResetWorkspace}
            latestUploadSnapshot={latestUploadSnapshot}
            uploadJob={uploadJob}
            uploadState={uploadState}
            uploadTransfer={uploadTransfer}
            propagationLabel={propagationLabel}
            queuedWorkerDetail={queuedWorkerDetail}
            latestMessage={latestMessage}
          />
        ) : null}

        {viewState === "completion_error" ? (
          <section className="baseline-failure" role="alert" aria-live="assertive">
            <header>
              <span aria-hidden="true">!</span>
              <div>
                <p>Recovery required</p>
                <h3>Baseline Created, Workspace Not Opened</h3>
              </div>
            </header>
            <p className="upload-error-message">{errorMessage}</p>
            <RecoverySummary viewState={viewState} hasSelectedFiles={hasSelectedFiles} selectedFileLabel={selectedFileLabel} uploadJob={uploadJob} errorMessage={errorMessage} />
            <div className="upload-simple-actions">
              <button type="button" className="command-button" onClick={onOpenBaseline ?? onViewResults} disabled={baselineNavigationPending} aria-disabled={baselineNavigationPending}>{baselineNavigationPending ? "Opening Baseline…" : "Open Baseline"}</button>
              <button type="button" className="secondary-command-button" onClick={onReturnToPortfolio ?? onResetWorkspace}>Return to Portfolio</button>
            </div>
          </section>
        ) : null}

        {viewState === "failed" ? (
          <section className="baseline-failure" role="alert" aria-live="assertive">
            <header>
              <span aria-hidden="true">!</span>
              <div>
                <p>{failurePresentation.title}</p>
                <h3>{failurePresentation.heading}</h3>
              </div>
            </header>
            <p className="upload-error-message">{errorMessage}</p>
            {failurePresentation.fileStored || failurePresentation.transferSucceeded ? (
              <p className="upload-transfer-complete">
                <strong>File uploaded</strong>
                <span>{uploadTransfer?.label || `${selectedFileLabel} was transferred and stored successfully.`}</span>
              </p>
            ) : null}
            <ol className="failed-import-stages" aria-label="Import workflow status">
              {failedStages.map((stage) => (
                <li key={stage.id} className={`failed-import-stages__item failed-import-stages__item--${stage.state}`}>
                  <span aria-hidden="true">{stage.state === "complete" ? "✓" : stage.state === "failed" ? "!" : "–"}</span>
                  <strong>{stage.label}</strong>
                  <small>{stage.status}</small>
                </li>
              ))}
            </ol>
            <div className="upload-simple-actions">
              {failurePresentation.retryable ? (
                <button type="button" className="command-button" onClick={() => onRetryFailedUploads?.()} disabled={!hasSelectedFiles && !uploadJob?.job_id}>Retry Processing</button>
              ) : null}
              <button type="button" className="secondary-command-button" onClick={onChooseAnotherFile ?? (() => openFilePicker("csv"))}>Choose Another File</button>
            </div>
            <AdvancedDetails
              latestUploadSnapshot={latestUploadSnapshot}
              uploadJob={uploadJob}
              uploadState={uploadState}
              uploadTransfer={uploadTransfer}
              propagationLabel={propagationLabel}
              queuedWorkerDetail={queuedWorkerDetail}
              latestMessage={latestMessage}
            />
          </section>
        ) : null}
      </form>
    </Panel>
  );
}
