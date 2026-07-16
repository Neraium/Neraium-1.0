import { Component, useEffect, useRef, useState } from "react";

import { buildIntakeStages, normalizeUploadStatus as normalizeUploadLifecycle } from "../../viewModels/uploadFlow";
import OperationalOrb from "../operational/OperationalOrb";
import { Panel } from "../workspacePrimitives";
import "../../styles/operational-workflow.css";

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
  if (normalized === "completion_error") return "completion_error";
  if (["failed", "error", "validation_error", "cancelled", "timeout"].includes(normalized)) return "failed";
  if (["save_complete", "complete"].includes(normalized)) return "complete";
  if (["saving_results", "navigation_pending"].includes(normalized)) return "finalizing";
  if (normalized === "uploading") return "uploading";
  if (isUploadProcessing(uploadState)) return "analyzing";
  if (hasSelectedFiles || normalized === "validated") return "fileSelected";
  return "noFile";
}

function operatorStatusText({ viewState, uploadJob, uploadState, latestMessage }) {
  const cleanMessage = String(latestMessage || "").trim();
  if (viewState === "uploading") return "Uploading Historical Data...";
  if (viewState === "complete") return "Analysis Complete";
  if (viewState === "finalizing") {
    const normalized = primaryJobStatus(uploadJob, uploadState);
    if (normalized === "saving_results") return "Persisting Behavioral Baseline";
    if (normalized === "navigation_pending") return "Opening Results";
    return "Generating Operational Insights...";
  }
  if (viewState === "failed") return "Upload Error";
  if (viewState === "completion_error") return "Results View Unavailable";
  if (/temporarily unavailable/i.test(cleanMessage)) return cleanMessage;

  const normalized = primaryJobStatus(uploadJob, uploadState);
  if (["writing_state", "cognition_ready", "saving_result"].includes(normalized)) {
    return "Generating Operational Insights...";
  }
  if (["building_fingerprint", "baseline_modeling", "building_baseline", "structural_scoring", "running_sii", "accepted", "queued", "validating_schema", "parsing", "processing"].includes(normalized)) {
    return "Learning the Facility Behavior...";
  }

  return cleanMessage || "Learning the Facility Behavior...";
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
  if (["failed", "error", "validation_error", "cancelled", "timeout", "completion_error"].includes(normalizeUploadLifecycle(uploadState))) return 100;
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

function formatFingerprintStatus(value) {
  const text = valueOrDash(value)
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (text === "--") return text;
  if (/^changed$/i.test(text)) return "Changed";
  if (/^established$/i.test(text)) return "Established";
  if (/^stable$/i.test(text)) return "Stable";
  return text.charAt(0).toUpperCase() + text.slice(1);
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
  const baselineStatus = formatFingerprintStatus(
    fingerprint?.status
      ?? fingerprint?.drift_status
      ?? fingerprint?.label
      ?? "Established"
  );

  return [
    { label: "Systems", value: String(analysisResult.systems.length) },
    { label: "Insights", value: String(analysisResult.insights.length) },
    { label: "Baseline", value: baselineStatus },
  ];
}

const BASELINE_NETWORK_STAGES = [
  {
    id: "evidence",
    label: "Collecting Operational Evidence",
    shortLabel: "Evidence",
    states: ["uploading", "queued", "accepted", "validating_schema", "parsing", "validated"],
  },
  {
    id: "relationships",
    label: "Discovering Operational Relationships",
    shortLabel: "Relationships",
    states: ["processing", "baseline_modeling"],
  },
  {
    id: "organization",
    label: "Organizing System Behavior",
    shortLabel: "Organization",
    states: ["running_sii", "structural_scoring", "building_baseline", "building_fingerprint"],
  },
  {
    id: "baseline",
    label: "Establishing Behavioral Baseline",
    shortLabel: "Baseline",
    states: ["writing_state", "cognition_ready", "saving_result", "saving_results"],
  },
];

// Keep the legacy storage keys so existing compatibility-mode sessions recover without migration.
const BASELINE_NETWORK_RECOVERY_KEY = "neraium.upload_fingerprint.compatibility_mode";
const BASELINE_NETWORK_REPORTED_KEY = "neraium.upload_fingerprint.compatibility_reported";
const BASELINE_NETWORK_MOUNT_KEY = "neraium.upload_fingerprint.mounts";

const BASELINE_NETWORK_NODES = [
  { id: "evidence-1", x: 54, y: 88, r: 5, phase: 0, kind: "evidence" },
  { id: "evidence-2", x: 80, y: 142, r: 4, phase: 0, kind: "evidence" },
  { id: "evidence-3", x: 112, y: 72, r: 4, phase: 0, kind: "evidence" },
  { id: "evidence-4", x: 142, y: 120, r: 5, phase: 0, kind: "evidence" },
  { id: "evidence-5", x: 104, y: 200, r: 4, phase: 0, kind: "evidence" },
  { id: "evidence-6", x: 162, y: 184, r: 3.5, phase: 0, kind: "evidence" },
  { id: "relation-1", x: 222, y: 96, r: 5, phase: 1, kind: "relationship" },
  { id: "relation-2", x: 246, y: 172, r: 5, phase: 1, kind: "relationship" },
  { id: "relation-3", x: 292, y: 132, r: 4, phase: 1, kind: "relationship" },
  { id: "relation-4", x: 322, y: 202, r: 3.5, phase: 1, kind: "relationship" },
  { id: "system-1", x: 372, y: 84, r: 6, phase: 2, kind: "system" },
  { id: "system-2", x: 398, y: 148, r: 5, phase: 2, kind: "system" },
  { id: "system-3", x: 442, y: 104, r: 5, phase: 2, kind: "system" },
  { id: "system-4", x: 468, y: 184, r: 5, phase: 2, kind: "system" },
  { id: "system-5", x: 500, y: 138, r: 4, phase: 2, kind: "system" },
  { id: "baseline-1", x: 564, y: 92, r: 4.5, phase: 3, kind: "baseline" },
  { id: "baseline-2", x: 566, y: 188, r: 4.5, phase: 3, kind: "baseline" },
  { id: "baseline-endpoint", x: 626, y: 140, r: 8, phase: 3, kind: "endpoint" },
];

const BASELINE_NETWORK_LINKS = [
  { phase: 0, path: "M54 88L112 72L142 120L80 142L104 200L162 184" },
  { phase: 0, path: "M54 88L80 142M112 72L80 142M142 120L162 184" },
  { phase: 1, path: "M112 72C154 64 188 76 222 96" },
  { phase: 1, path: "M142 120C180 124 208 145 246 172" },
  { phase: 1, path: "M162 184C196 200 222 194 246 172" },
  { phase: 1, path: "M222 96L292 132L246 172L322 202" },
  { phase: 1, path: "M222 96C250 118 260 138 246 172" },
  { phase: 2, path: "M292 132C326 110 342 94 372 84" },
  { phase: 2, path: "M292 132C334 142 360 146 398 148" },
  { phase: 2, path: "M322 202C360 196 424 190 468 184" },
  { phase: 2, path: "M372 84L442 104L398 148L468 184L500 138L442 104" },
  { phase: 2, path: "M398 148L500 138M442 104L468 184" },
  { phase: 3, path: "M442 104C500 84 528 82 564 92" },
  { phase: 3, path: "M468 184C506 198 532 198 566 188" },
  { phase: 3, path: "M500 138C536 138 572 140 626 140" },
  { phase: 3, path: "M564 92L626 140L566 188" },
];

const BASELINE_NETWORK_CLUSTERS = [
  { phase: 0, path: "M30 52Q30 36 46 36H174Q190 36 190 52V220Q190 236 174 236H46Q30 236 30 220Z" },
  { phase: 1, path: "M202 58Q202 44 216 44H326Q340 44 340 58V218Q340 232 326 232H216Q202 232 202 218Z" },
  { phase: 2, path: "M354 48Q354 34 368 34H506Q520 34 520 48V222Q520 236 506 236H368Q354 236 354 222Z" },
];

function networkProgress({ displayPercent, phase, stageIndex, complete }) {
  if (complete || stageIndex > phase) return 100;
  if (stageIndex < phase) return 0;
  const phaseStartPercent = [0, 35, 62, 84][phase] ?? 0;
  const phaseEndPercent = [35, 62, 84, 99][phase] ?? 100;
  const withinPhase = ((displayPercent - phaseStartPercent) / Math.max(1, phaseEndPercent - phaseStartPercent)) * 100;
  return Math.max(12, Math.min(100, Math.round(withinPhase)));
}

function resolveBaselineNetworkStage({ viewState, uploadJob, uploadState }) {
  if (viewState === "complete") {
    return { id: "complete", label: "Behavioral Baseline Established", index: BASELINE_NETWORK_STAGES.length };
  }
  if (viewState === "finalizing") {
    const normalized = primaryJobStatus(uploadJob, uploadState);
    if (normalized === "saving_results") {
      return { ...BASELINE_NETWORK_STAGES[3], label: "Persisting Behavioral Baseline", index: 3 };
    }
    if (normalized === "navigation_pending") {
      return { ...BASELINE_NETWORK_STAGES[3], label: "Opening Results", index: 3 };
    }
    return { ...BASELINE_NETWORK_STAGES[3], index: 3 };
  }
  if (viewState === "uploading") {
    return { ...BASELINE_NETWORK_STAGES[0], index: 0 };
  }

  const rawStage = String(
    uploadJob?.processing_state
      ?? uploadJob?.processingState
      ?? uploadJob?.status
      ?? uploadState
      ?? ""
  ).trim().toLowerCase();
  const normalized = primaryJobStatus(uploadJob, uploadState);
  const rawMatchedIndex = BASELINE_NETWORK_STAGES.findIndex((stage) => stage.states.includes(rawStage));
  const normalizedMatchedIndex = BASELINE_NETWORK_STAGES.findIndex((stage) => stage.states.includes(normalized));
  const index = rawMatchedIndex >= 0 ? rawMatchedIndex : normalizedMatchedIndex >= 0 ? normalizedMatchedIndex : 1;
  return { ...BASELINE_NETWORK_STAGES[index], index };
}

function safeStorage(storageName) {
  if (typeof window === "undefined") return null;
  try {
    return window[storageName] ?? null;
  } catch {
    return null;
  }
}

function readStorageValue(storageName, key) {
  try {
    return safeStorage(storageName)?.getItem(key) ?? "";
  } catch {
    return "";
  }
}

function writeStorageValue(storageName, key, value) {
  try {
    safeStorage(storageName)?.setItem(key, value);
  } catch {
    // Storage may be disabled in private or constrained browser contexts.
  }
}

function mediaMatches(query) {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  try {
    return window.matchMedia(query).matches;
  } catch {
    return false;
  }
}

function markBaselineNetworkRecovery(reason) {
  writeStorageValue("localStorage", BASELINE_NETWORK_RECOVERY_KEY, reason || "renderer-recovery");
}

function detectBaselineNetworkRenderTier() {
  if (typeof window === "undefined") return { tier: "safe", reason: "server-render" };
  const recoveryReason = readStorageValue("localStorage", BASELINE_NETWORK_RECOVERY_KEY);
  if (recoveryReason) return { tier: "safe", reason: recoveryReason };

  const navigatorInfo = window.navigator ?? {};
  const memory = Number(navigatorInfo.deviceMemory);
  const cores = Number(navigatorInfo.hardwareConcurrency);
  const reducedMotion = mediaMatches("(prefers-reduced-motion: reduce)");
  const constrainedMemory = Number.isFinite(memory) && memory > 0 && memory <= 2;
  const limitedMemory = Number.isFinite(memory) && memory > 0 && memory <= 4;
  const constrainedCpu = Number.isFinite(cores) && cores > 0 && cores <= 2;
  const mobileLike = mediaMatches("(max-width: 760px)") || mediaMatches("(hover: none) and (pointer: coarse)");
  const svgPathSupported = !window.CSS || typeof window.CSS.supports !== "function" || window.CSS.supports("stroke-dashoffset", "1");

  if (reducedMotion) return { tier: "safe", reason: "reduced-motion" };
  if (constrainedMemory || !svgPathSupported) return { tier: "safe", reason: constrainedMemory ? "low-memory" : "svg-path-support" };
  if (mobileLike || limitedMemory || constrainedCpu) return { tier: "enhanced", reason: mobileLike ? "mobile-capability" : "limited-capability" };
  return { tier: "premium", reason: "capable-device" };
}

function registerBaselineNetworkMount() {
  if (typeof window === "undefined") return false;
  const now = window.performance?.now?.() ?? Date.now();
  const raw = readStorageValue("sessionStorage", BASELINE_NETWORK_MOUNT_KEY);
  const previous = raw ? raw.split(",").map(Number).filter((value) => Number.isFinite(value)) : [];
  const recent = [...previous.filter((value) => now - value < 5000), now].slice(-5);
  writeStorageValue("sessionStorage", BASELINE_NETWORK_MOUNT_KEY, recent.join(","));
  return recent.length >= 4;
}

class BaselineNetworkRendererBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    markBaselineNetworkRecovery("renderer-error");
  }

  render() {
    if (this.state.failed) {
      return <BaselineNetworkBuildVisual {...this.props} forcedTier="safe" recoveryReason="renderer-error" />;
    }
    return <BaselineNetworkBuildVisual {...this.props} />;
  }
}

function BaselineNetworkBuild(props) {
  return <BaselineNetworkRendererBoundary {...props} />;
}

function BaselineNetworkBuildVisual({ percent, stage, complete = false, forcedTier = "", recoveryReason = "" }) {
  const displayPercent = clampPercent(percent);
  const stageIndex = stage?.index ?? 0;
  const stageCount = BASELINE_NETWORK_STAGES.length;
  const stageNumber = Math.min(stageIndex + 1, stageCount);
  const rootRef = useRef(null);
  const [renderProfile, setRenderProfile] = useState(() => forcedTier ? { tier: forcedTier, reason: recoveryReason || "renderer-recovery" } : detectBaselineNetworkRenderTier());
  const renderTier = forcedTier || renderProfile.tier;
  const compatibilityMode = renderTier === "safe";
  const statusTitle = complete ? "Behavioral Baseline Established" : stage?.label || "Learning Operational Relationships";

  useEffect(() => {
    if (forcedTier) return undefined;
    if (registerBaselineNetworkMount()) {
      markBaselineNetworkRecovery("repeated-remounts");
      setRenderProfile({ tier: "safe", reason: "repeated-remounts" });
      return undefined;
    }

    let active = true;
    const recover = (reason) => {
      if (!active) return;
      markBaselineNetworkRecovery(reason);
      setRenderProfile({ tier: "safe", reason });
    };
    const handleRendererError = () => recover("renderer-error");
    const handleCompatibilityRecovery = () => recover("black-screen-recovery");
    const recoveryEvents = ["neraium:baseline-network-renderer-failed", "neraium:fingerprint-renderer-failed"];

    window.addEventListener("error", handleRendererError);
    window.addEventListener("unhandledrejection", handleRendererError);
    recoveryEvents.forEach((eventName) => window.addEventListener(eventName, handleCompatibilityRecovery));

    const frame = window.requestAnimationFrame?.(() => {
      const box = rootRef.current?.getBoundingClientRect?.();
      if (box && box.width > 0 && box.height > 0 && (box.width < 24 || box.height < 24)) recover("black-screen-recovery");
    });

    return () => {
      active = false;
      window.removeEventListener("error", handleRendererError);
      window.removeEventListener("unhandledrejection", handleRendererError);
      recoveryEvents.forEach((eventName) => window.removeEventListener(eventName, handleCompatibilityRecovery));
      if (frame && window.cancelAnimationFrame) window.cancelAnimationFrame(frame);
    };
  }, [forcedTier]);

  useEffect(() => {
    if (!compatibilityMode || complete) return;
    if (readStorageValue("sessionStorage", BASELINE_NETWORK_REPORTED_KEY)) return;
    writeStorageValue("sessionStorage", BASELINE_NETWORK_REPORTED_KEY, "1");
  }, [compatibilityMode, complete]);

  return (
    <div
      ref={rootRef}
      className={`upload-network-build upload-network-build--${renderTier}${complete ? " upload-network-build--complete" : ""}`}
      data-testid="baseline-network-progress"
      data-render-tier={renderTier}
      data-render-reason={renderProfile.reason}
      data-build-stage={stage?.id || "evidence"}
    >
      <span
        className="sr-only"
        aria-label={`Analysis ${displayPercent}% complete`}
        aria-valuemin="0"
        aria-valuemax="100"
        aria-valuenow={displayPercent}
        role="progressbar"
      />
      <header className="upload-network-build__header">
        <p>Behavioral baseline</p>
        <div className="upload-network-build__title-row">
          <strong>{statusTitle}</strong>
          <div className="upload-network-build__meta">
            <span>Stage {stageNumber} of {stageCount}</span>
            <span>{displayPercent}%</span>
          </div>
        </div>
        {compatibilityMode && !complete ? (
          <small>Your browser is using a simplified view. Analysis quality is unchanged and no action is required.</small>
        ) : null}
      </header>

      <div className="upload-network-build__canvas" aria-hidden="true">
        <svg viewBox="0 0 680 280" focusable="false">
          <g className="upload-network-build__clusters">
            {BASELINE_NETWORK_CLUSTERS.map((cluster, index) => {
              const fill = networkProgress({ displayPercent, phase: cluster.phase, stageIndex, complete });
              return <path key={cluster.path} d={cluster.path} pathLength="100" style={{ "--network-offset": compatibilityMode ? (fill > 0 ? 0 : 100) : 100 - fill, "--cluster-index": index }} />;
            })}
          </g>
          <g className="upload-network-build__links">
            {BASELINE_NETWORK_LINKS.map((link, index) => {
              const fill = networkProgress({ displayPercent, phase: link.phase, stageIndex, complete });
              return <path key={link.path} d={link.path} pathLength="100" style={{ "--network-offset": compatibilityMode ? (fill > 0 ? 0 : 100) : 100 - fill, "--link-index": index }} />;
            })}
          </g>
          <rect className={`upload-network-build__baseline-boundary${complete || stageIndex >= 3 ? " is-resolved" : ""}`} x="542" y="58" width="112" height="164" rx="18" pathLength="100" />
          <g className="upload-network-build__evidence-nodes">
            {BASELINE_NETWORK_NODES.map((node) => {
              const resolved = complete || stageIndex >= node.phase;
              const active = !complete && stageIndex === node.phase;
              return (
                <circle
                  key={node.id}
                  className={`upload-network-build__node upload-network-build__node--${node.kind}${resolved ? " is-resolved" : ""}${active ? " is-active" : ""}`}
                  cx={node.x}
                  cy={node.y}
                  r={node.r}
                />
              );
            })}
          </g>
          {complete ? <path className="upload-network-build__completion-check" d="M616 140l7 7 14-17" /> : null}
        </svg>
      </div>

      <ol className="upload-network-build__stages" aria-label="Analysis stages">
        {BASELINE_NETWORK_STAGES.map((item, index) => {
          const isComplete = complete || index < stageIndex;
          const isActive = !complete && index === stageIndex;
          return (
            <li
              key={item.id}
              className={isComplete ? "is-complete" : isActive ? "is-active" : ""}
              aria-current={isActive ? "step" : undefined}
              aria-label={item.label}
            >
              <i aria-hidden="true">{isComplete ? "\u2713" : index + 1}</i>
              <b>{item.shortLabel}</b>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

const SUPPORTED_HISTORICAL_SOURCES = ["CSV", "SCADA Export", "Historian Export"];

function uploadOrbStatus(viewState) {
  if (["uploading", "analyzing", "finalizing"].includes(viewState)) return "learning";
  if (viewState === "complete") return "healthy";
  return "awaiting";
}

function uploadBaselineStatusText(viewState, hasSelectedFiles) {
  if (["uploading", "analyzing", "finalizing"].includes(viewState)) return "Learning Facility Behavior";
  if (viewState === "complete") return "Behavioral Baseline Active";
  if (viewState === "failed") return hasSelectedFiles ? "Historical Data Ready" : "Awaiting Behavioral Baseline";
  if (hasSelectedFiles) return "Historical Data Ready";
  return "Awaiting Behavioral Baseline";
}

function buildAdvancedRows({ uploadJob, uploadTransfer, propagationLabel, queuedWorkerDetail, latestMessage, uploadDebug }) {
  const rawError = uploadJob?.error ?? uploadJob?.detail ?? uploadJob?.message;
  return [
    ["Upload ID", uploadJob?.job_id ?? uploadJob?.id],
    ["Stage name", uploadJob?.processing_state ?? uploadJob?.processingState ?? uploadJob?.status],
    ["Timing", uploadJob?.processing_time_seconds ? `${uploadJob.processing_time_seconds}s` : null],
    ["Transfer", uploadTransfer?.label],
    ["Finalization", uploadJob?.result_available ? "Result available" : uploadJob?.first_usable_available ? "First result available" : null],
    ["Processing status", queuedWorkerDetail],
    ["Stage detail", propagationLabel],
    ["Failure phase", uploadJob?.failure_phase ?? uploadDebug?.failurePhase],
    ["Failed route", uploadJob?.failure_url ?? uploadDebug?.uploadUrl],
    ["HTTP status", uploadJob?.response_status ?? uploadDebug?.responseStatus],
    ["Raw message", latestMessage],
    ["Raw error", uploadJob?.error_type || uploadJob?.error ? rawError : null],
    ["Raw response", uploadJob?.raw_response_body ?? uploadDebug?.responseBodyOrError],
  ].filter(([, value]) => String(value ?? "").trim());
}

function AdvancedDetails({ latestUploadSnapshot, uploadJob, uploadState, uploadTransfer, propagationLabel, queuedWorkerDetail, latestMessage, uploadDebug }) {
  const rows = buildAdvancedRows({ uploadJob, uploadTransfer, propagationLabel, queuedWorkerDetail, latestMessage, uploadDebug });
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
  uploadDebug = null,
  uploadStateMessage,
  batchResults = [],
  onRetryFailedUploads,
  onResetWorkspace,
  onViewResults,
}) {
  void uploadStateMessage;
  void batchResults;
  const [isDragActive, setIsDragActive] = useState(false);

  const hasSelectedFiles = selectedFiles?.length > 0;
  const selectedFileLabel = hasSelectedFiles
    ? (selectedFiles.length === 1 ? selectedFiles[0].name : `${selectedFiles.length} files selected`)
    : "No file selected";
  const fileKind = String(pendingUploadKind || "csv").toUpperCase();
  const rawViewState = uploadViewState({ uploadState, hasSelectedFiles, isUploadProcessing });
  const analysisResult = finalAnalysisResult(latestUploadSnapshot, uploadJob);
  const viewState = rawViewState === "complete" && !analysisResult ? "finalizing" : rawViewState;
  const statusText = operatorStatusText({ viewState, uploadJob, uploadState, latestMessage });
  const mainPercent = resolveMainPercent({ viewState, uploadState, uploadJob, uploadTransfer, visibleProgressPercent });
  const baselineNetworkStage = resolveBaselineNetworkStage({ viewState, uploadJob, uploadState });
  const remaining = estimateRemaining(uploadTransfer);
  const errorMessage = String(latestMessage || "Choose another telemetry file and try again.").trim();
  const summary = analysisResult ? completionSummary({ analysisResult }) : [];
  const showProgress = viewState === "uploading" || viewState === "analyzing" || viewState === "finalizing";
  const baselineStatus = uploadBaselineStatusText(viewState, hasSelectedFiles);
  const resolvedOrbStatus = uploadOrbStatus(viewState);
  const chooseFileButtonText = "Choose File";
  const selectedFileDetail = hasSelectedFiles ? `${fileKind} telemetry - ${selectedFileSize}` : "No file selected";
  const dragClassName = isDragActive ? " upload-analysis-card--drag-active" : "";

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
    <Panel title="Analyze Historical Telemetry" className="span-7 upload-ops-panel upload-ops-panel--command">
      <form className={`intake-flow intake-flow--simple intake-flow--${viewState}`} onSubmit={handleUpload}>
        <p className="intake-flow__subtitle">Upload historical telemetry to establish a learned behavior baseline for this facility.</p>
        <input data-testid="csv-upload-input" ref={uploadInputRef} accept=".csv,text/csv" id="csv-upload" type="file" multiple className="intake-flow__input" style={hiddenFileInputStyle} onChange={handleFileSelection} />

        {(viewState === "noFile" || viewState === "fileSelected") ? (
          <section
            className={`upload-analysis-card${dragClassName}`}
            aria-label="Historical data upload"
            onDragOver={handleUploadDragOver}
            onDragLeave={handleUploadDragLeave}
            onDrop={handleUploadDrop}
          >
            <div className="upload-analysis-card__visual">
              <OperationalOrb
                status={resolvedOrbStatus}
                state={{
                  label: baselineStatus,
                  visualLabel: "Behavioral Baseline",
                }}
              />
              <div className="upload-analysis-card__status" aria-live="polite">
                <span>Status</span>
                <strong>{baselineStatus}</strong>
              </div>
            </div>

            <div className="upload-analysis-card__content">
              <div className="upload-analysis-card__copy">
                <p className="section-token">Historical Telemetry</p>
                <h3>Analyze Historical Telemetry</h3>
                <p>Upload historical telemetry to establish a learned behavior baseline for this facility.</p>
              </div>

              <div className="upload-analysis-card__sources" aria-label="Supported Sources">
                <span>Supported Sources</span>
                <ul>
                  {SUPPORTED_HISTORICAL_SOURCES.map((source) => <li key={source}>{source}</li>)}
                </ul>
              </div>

              <div className="upload-analysis-card__file">
                <span>{selectedFileLabel}</span>
                <strong>{selectedFileDetail}</strong>
              </div>

              <div className="upload-simple-actions upload-analysis-card__actions">
                <button type="button" className="secondary-command-button" onClick={() => openFilePicker("csv")}>{chooseFileButtonText}</button>
                <button data-testid="process-upload-button" className="command-button" type="submit" disabled={!hasSelectedFiles || isUploadProcessing(uploadState)}>
                  Analyze Historical Telemetry
                </button>
              </div>
            </div>
          </section>
        ) : null}

        {showProgress ? (
          <section className="upload-analysis-card upload-analysis-card--processing" aria-live="polite" aria-label={`Analysis progress: ${statusText}`}>
            <div className="upload-analysis-card__content">
              <div className="upload-processing-heading">
                <div className="upload-file-chip" title={`${selectedFileLabel} - ${selectedFileSize}`}>
                  <span className="upload-file-chip__icon" aria-hidden="true" />
                  <span className="upload-file-chip__name">{selectedFileLabel}</span>
                  <span className="upload-file-chip__meta">{selectedFileSize}</span>
                </div>
                <span className="upload-processing-heading__state">Analysis in progress</span>
              </div>
              <BaselineNetworkBuild percent={mainPercent} stage={baselineNetworkStage} />
              <div className="upload-processing-message">
                <p className="upload-simple-note upload-processing-status">{queuedWorkerDetail || statusText}</p>
                {remaining ? <p className="upload-simple-note upload-processing-remaining">{remaining}</p> : null}
              </div>
            </div>
          </section>
        ) : null}

        {viewState === "complete" ? (
          <section className="upload-analysis-card upload-simple-card--complete" aria-label="Analysis complete">
            <div className="upload-analysis-card__visual">
              <BaselineNetworkBuild percent={100} stage={resolveBaselineNetworkStage({ viewState: "complete", uploadJob, uploadState })} complete />
              <div className="upload-analysis-card__status">
                <span>Status</span>
                <strong>Behavioral Baseline Established</strong>
              </div>
            </div>
            <div className="upload-analysis-card__content">
              <div className="upload-complete-header">
                <h3>Behavioral Baseline Established</h3>
                <span className="upload-complete-filename" title={selectedFileLabel}>{selectedFileLabel}</span>
              </div>
              <p className="upload-complete-message">The behavioral baseline has been established. Neraium has learned how the facility normally behaves together.</p>
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
                <button type="button" className="secondary-command-button" onClick={onResetWorkspace}>Analyze New Telemetry</button>
              </div>
            </div>
          </section>
        ) : null}

        {viewState === "completion_error" ? (
          <section className="upload-analysis-card upload-simple-card--failed" role="alert" aria-live="assertive">
            <div className="upload-analysis-card__visual">
              <BaselineNetworkBuild percent={100} stage={resolveBaselineNetworkStage({ viewState: "complete", uploadJob, uploadState })} complete />
              <div className="upload-analysis-card__status">
                <span>Status</span>
                <strong>Behavioral Baseline Established</strong>
              </div>
            </div>
            <div className="upload-analysis-card__content">
              <div className="upload-complete-header">
                <h3>Results View Unavailable</h3>
                <span>{hasSelectedFiles ? selectedFileLabel : "Results saved"}</span>
              </div>
              <p className="upload-error-message">{errorMessage || "Results were saved, but the results view could not be loaded."}</p>
              <div className="upload-simple-actions">
                <button type="button" className="command-button" onClick={onViewResults}>Retry Results</button>
                <button type="button" className="secondary-command-button" onClick={onResetWorkspace}>Analyze New Telemetry</button>
              </div>
            </div>
          </section>
        ) : null}

        {viewState === "failed" ? (
          <section className="upload-analysis-card upload-simple-card--failed" role="alert" aria-live="assertive">
            <div className="upload-analysis-card__visual">
              <OperationalOrb
                status={resolvedOrbStatus}
                state={{
                  label: baselineStatus,
                  visualLabel: "Behavioral Baseline",
                }}
              />
              <div className="upload-analysis-card__status">
                <span>Status</span>
                <strong>{baselineStatus}</strong>
              </div>
            </div>
            <div className="upload-analysis-card__content">
              <div className="upload-complete-header">
                <h3>Upload Error</h3>
                <span>{hasSelectedFiles ? selectedFileLabel : "No file selected"}</span>
              </div>
              <p className="upload-error-message">{errorMessage}</p>
              <div className="upload-simple-actions">
                <button type="button" className="command-button" onClick={() => onRetryFailedUploads?.()} disabled={!hasSelectedFiles}>Retry</button>
                <button type="button" className="secondary-command-button" onClick={() => openFilePicker("csv")}>Choose File</button>
              </div>
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
          uploadDebug={uploadDebug}
        />
      </form>
    </Panel>
  );
}
