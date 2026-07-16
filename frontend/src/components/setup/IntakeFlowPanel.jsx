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
  const fingerprintStatus = formatFingerprintStatus(
    fingerprint?.status
      ?? fingerprint?.drift_status
      ?? fingerprint?.label
      ?? "Established"
  );

  return [
    { label: "Systems", value: String(analysisResult.systems.length) },
    { label: "Insights", value: String(analysisResult.insights.length) },
    { label: "Baseline", value: fingerprintStatus },
  ];
}

const FINGERPRINT_BUILD_STAGES = [
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

const FINGERPRINT_RENDERER_RECOVERY_KEY = "neraium.upload_fingerprint.compatibility_mode";
const FINGERPRINT_RENDERER_REPORTED_KEY = "neraium.upload_fingerprint.compatibility_reported";
const FINGERPRINT_RENDERER_MOUNT_KEY = "neraium.upload_fingerprint.mounts";
const FINGERPRINT_RENDERER_PARTICLES = {
  premium: 8,
  enhanced: 3,
  safe: 0,
};

const BASELINE_NETWORK_NODES = [
  { x: 80, y: 94, r: 5.2, role: "core" },
  { x: 50, y: 70, r: 3.3, role: "system" },
  { x: 109, y: 65, r: 3.5, role: "system" },
  { x: 119, y: 112, r: 3.1, role: "system" },
  { x: 65, y: 132, r: 3.4, role: "system" },
  { x: 35, y: 107, r: 2.6, role: "signal" },
  { x: 76, y: 47, r: 2.5, role: "signal" },
  { x: 137, y: 82, r: 2.4, role: "signal" },
  { x: 101, y: 145, r: 2.5, role: "signal" },
];

const BASELINE_NETWORK_LINKS = [
  { phase: 0, path: "M35 107L50 70L76 47" },
  { phase: 0, path: "M76 47L109 65L137 82" },
  { phase: 1, path: "M50 70Q66 77 80 94" },
  { phase: 1, path: "M109 65Q95 78 80 94" },
  { phase: 1, path: "M80 94Q101 95 119 112" },
  { phase: 2, path: "M80 94Q74 113 65 132" },
  { phase: 2, path: "M65 132Q83 142 101 145" },
  { phase: 2, path: "M119 112Q113 132 101 145" },
];

const BASELINE_ORBITS = [
  { phase: 1, path: "M37 93A44 31 0 1 0 125 93A44 31 0 1 0 37 93" },
  { phase: 2, path: "M54 50A35 55 18 1 0 108 139A35 55 18 1 0 54 50" },
  { phase: 3, path: "M30 72A58 58 -18 1 0 130 120A58 58 -18 1 0 30 72" },
];

function networkProgress({ displayPercent, phase, stageIndex, complete }) {
  if (complete || stageIndex > phase) return 100;
  if (stageIndex < phase) return 0;
  const phaseStartPercent = [0, 35, 62, 84][phase] ?? 0;
  const phaseEndPercent = [35, 62, 84, 99][phase] ?? 100;
  const withinPhase = ((displayPercent - phaseStartPercent) / Math.max(1, phaseEndPercent - phaseStartPercent)) * 100;
  return Math.max(12, Math.min(100, Math.round(withinPhase)));
}

function resolveFingerprintBuildStage({ viewState, uploadJob, uploadState }) {
  if (viewState === "complete") {
    return { id: "complete", label: "Behavioral Baseline Established", index: FINGERPRINT_BUILD_STAGES.length };
  }
  if (viewState === "finalizing") {
    const normalized = primaryJobStatus(uploadJob, uploadState);
    if (normalized === "saving_results") {
      return { ...FINGERPRINT_BUILD_STAGES[3], label: "Persisting Behavioral Baseline", index: 3 };
    }
    if (normalized === "navigation_pending") {
      return { ...FINGERPRINT_BUILD_STAGES[3], label: "Opening Results", index: 3 };
    }
    return { ...FINGERPRINT_BUILD_STAGES[3], index: 3 };
  }
  if (viewState === "uploading") {
    return { ...FINGERPRINT_BUILD_STAGES[0], index: 0 };
  }

  const rawStage = String(
    uploadJob?.processing_state
      ?? uploadJob?.processingState
      ?? uploadJob?.status
      ?? uploadState
      ?? ""
  ).trim().toLowerCase();
  const normalized = primaryJobStatus(uploadJob, uploadState);
  const rawMatchedIndex = FINGERPRINT_BUILD_STAGES.findIndex((stage) => stage.states.includes(rawStage));
  const normalizedMatchedIndex = FINGERPRINT_BUILD_STAGES.findIndex((stage) => stage.states.includes(normalized));
  const index = rawMatchedIndex >= 0 ? rawMatchedIndex : normalizedMatchedIndex >= 0 ? normalizedMatchedIndex : 1;
  return { ...FINGERPRINT_BUILD_STAGES[index], index };
}

function ridgeProgress({ displayPercent, ridge, stageIndex, complete }) {
  if (complete || stageIndex > ridge.phase) return 100;
  if (stageIndex < ridge.phase) return 0;

  const phaseStartPercent = [0, 35, 62, 84][ridge.phase] ?? 0;
  const phaseEndPercent = [35, 62, 84, 99][ridge.phase] ?? 100;
  const phaseSpan = Math.max(1, phaseEndPercent - phaseStartPercent);
  const withinPhase = ((displayPercent - phaseStartPercent) / phaseSpan) * 100;
  return Math.max(12, Math.min(100, Math.round(withinPhase)));
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

function markFingerprintRendererRecovery(reason) {
  writeStorageValue("localStorage", FINGERPRINT_RENDERER_RECOVERY_KEY, reason || "renderer-recovery");
}

function detectFingerprintRenderTier() {
  if (typeof window === "undefined") return { tier: "safe", reason: "server-render" };
  const recoveryReason = readStorageValue("localStorage", FINGERPRINT_RENDERER_RECOVERY_KEY);
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

function registerFingerprintRendererMount() {
  if (typeof window === "undefined") return false;
  const now = window.performance?.now?.() ?? Date.now();
  const raw = readStorageValue("sessionStorage", FINGERPRINT_RENDERER_MOUNT_KEY);
  const previous = raw ? raw.split(",").map(Number).filter((value) => Number.isFinite(value)) : [];
  const recent = [...previous.filter((value) => now - value < 5000), now].slice(-5);
  writeStorageValue("sessionStorage", FINGERPRINT_RENDERER_MOUNT_KEY, recent.join(","));
  return recent.length >= 4;
}

class FingerprintRendererBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    markFingerprintRendererRecovery("renderer-error");
  }

  render() {
    if (this.state.failed) {
      return <OperationalFingerprintBuildVisual {...this.props} forcedTier="safe" recoveryReason="renderer-error" />;
    }
    return <OperationalFingerprintBuildVisual {...this.props} />;
  }
}

function OperationalFingerprintBuild(props) {
  return <FingerprintRendererBoundary {...props} />;
}

function OperationalFingerprintBuildVisual({ percent, stage, complete = false, forcedTier = "", recoveryReason = "" }) {
  const displayPercent = clampPercent(percent);
  const stageIndex = stage?.index ?? 0;
  const stageCount = FINGERPRINT_BUILD_STAGES.length;
  const stageNumber = Math.min(stageIndex + 1, stageCount);
  const rootRef = useRef(null);
  const [renderProfile, setRenderProfile] = useState(() => forcedTier ? { tier: forcedTier, reason: recoveryReason || "renderer-recovery" } : detectFingerprintRenderTier());
  const renderTier = forcedTier || renderProfile.tier;
  const compatibilityMode = renderTier === "safe";
  const particleCount = FINGERPRINT_RENDERER_PARTICLES[renderTier] ?? 0;
  const statusTitle = complete
    ? "Behavioral Baseline Established"
    : compatibilityMode
      ? "Using an alternate processing path."
      : stage?.label || "Learning Operational Relationships";
  const statusDetail = complete
    ? "The behavioral baseline has been established"
    : compatibilityMode
      ? "Analysis quality is unchanged. Full SII results remain valid."
      : "Stage " + stageNumber + " of " + stageCount;

  useEffect(() => {
    if (forcedTier) return undefined;
    if (registerFingerprintRendererMount()) {
      markFingerprintRendererRecovery("repeated-remounts");
      setRenderProfile({ tier: "safe", reason: "repeated-remounts" });
      return undefined;
    }

    let active = true;
    const recover = (reason) => {
      if (!active) return;
      markFingerprintRendererRecovery(reason);
      setRenderProfile({ tier: "safe", reason });
    };
    const handleRendererError = () => recover("renderer-error");
    const handleCompatibilityRecovery = () => recover("black-screen-recovery");

    window.addEventListener("error", handleRendererError);
    window.addEventListener("unhandledrejection", handleRendererError);
    window.addEventListener("neraium:fingerprint-renderer-failed", handleCompatibilityRecovery);

    const frame = window.requestAnimationFrame?.(() => {
      const box = rootRef.current?.getBoundingClientRect?.();
      if (box && box.width > 0 && box.height > 0 && (box.width < 24 || box.height < 24)) recover("black-screen-recovery");
    });

    return () => {
      active = false;
      window.removeEventListener("error", handleRendererError);
      window.removeEventListener("unhandledrejection", handleRendererError);
      window.removeEventListener("neraium:fingerprint-renderer-failed", handleCompatibilityRecovery);
      if (frame && window.cancelAnimationFrame) window.cancelAnimationFrame(frame);
    };
  }, [forcedTier]);

  useEffect(() => {
    if (!compatibilityMode || complete) return;
    if (readStorageValue("sessionStorage", FINGERPRINT_RENDERER_REPORTED_KEY)) return;
    writeStorageValue("sessionStorage", FINGERPRINT_RENDERER_REPORTED_KEY, "1");
  }, [compatibilityMode, complete]);

  return (
    <div
      ref={rootRef}
      className={`upload-fingerprint-build upload-fingerprint-build--${renderTier}${complete ? " upload-fingerprint-build--complete" : ""}`}
      data-render-tier={renderTier}
      data-render-reason={renderProfile.reason}
      data-build-stage={stage?.id || "evidence"}
      aria-label={`Analysis ${displayPercent}% complete`}
      aria-valuemin="0"
      aria-valuemax="100"
      aria-valuenow={displayPercent}
      role="progressbar"
    >
      <div className="upload-fingerprint-build__halo" aria-hidden="true" />
      {particleCount > 0 ? (
        <div className="upload-fingerprint-build__particles" aria-hidden="true">
          {Array.from({ length: particleCount }, (_, index) => <span key={index} style={{ "--particle-index": index }} />)}
        </div>
      ) : null}
      <div className="upload-fingerprint-build__status">
        <strong>{statusTitle}</strong>
        <span>{statusDetail}</span>
        {compatibilityMode && !complete ? (
          <small>Analysis quality is unchanged. Full SII results remain valid. No action is required.</small>
        ) : null}
      </div>
      <svg className="upload-fingerprint-build__print" viewBox="0 0 160 190" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="upload-baseline-link" x1="38" y1="42" x2="126" y2="148" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="rgba(226, 232, 236, 0.82)" />
            <stop offset="0.58" stopColor="rgba(113, 128, 139, 0.7)" />
            <stop offset="1" stopColor="rgba(29, 216, 196, 0.78)" />
          </linearGradient>
          <radialGradient id="upload-fingerprint-core" cx="50%" cy="50%" r="58%">
            <stop offset="0" stopColor="rgba(92, 107, 118, 0.18)" />
            <stop offset="0.7" stopColor="rgba(29, 216, 196, 0.05)" />
            <stop offset="1" stopColor="rgba(29, 216, 196, 0)" />
          </radialGradient>
          <filter id="upload-baseline-node-glow" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="2.4" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <circle className="upload-fingerprint-build__field" cx="80" cy="95" r="69" />
        <g className="upload-fingerprint-build__orbits">
          {BASELINE_ORBITS.map((orbit, index) => {
            const fill = networkProgress({ displayPercent, phase: orbit.phase, stageIndex, complete });
            return <path key={orbit.path} d={orbit.path} pathLength="100" style={{ "--network-offset": compatibilityMode ? (fill > 0 ? 0 : 100) : 100 - fill, "--orbit-index": index }} />;
          })}
        </g>
        <g className="upload-fingerprint-build__relationship-links">
          {BASELINE_NETWORK_LINKS.map((link, index) => {
            const fill = networkProgress({ displayPercent, phase: link.phase, stageIndex, complete });
            return <path key={link.path} d={link.path} pathLength="100" style={{ "--network-offset": compatibilityMode ? (fill > 0 ? 0 : 100) : 100 - fill, "--link-index": index }} />;
          })}
        </g>
        <g className="upload-fingerprint-build__evidence-points" filter="url(#upload-baseline-node-glow)">
          {BASELINE_NETWORK_NODES.map((node, index) => (
            <g key={`${node.x}-${node.y}`} className={`upload-fingerprint-build__network-node upload-fingerprint-build__network-node--${node.role}`} style={{ "--point-index": index }}>
              <circle className="upload-fingerprint-build__node-orbit" cx={node.x} cy={node.y} r={node.r + 4.5} />
              <circle className="upload-fingerprint-build__node-core" cx={node.x} cy={node.y} r={node.r} />
            </g>
          ))}
        </g>
        <circle className="upload-fingerprint-build__baseline-lock" cx="80" cy="95" r="18" pathLength="100" />
      </svg>
      {complete ? <div className="upload-fingerprint-build__ripple" aria-hidden="true" /> : null}
      {complete ? <div className="upload-fingerprint-build__check" aria-hidden="true">✓</div> : null}
      <div className="upload-fingerprint-build__nodes" aria-hidden="true">
        {FINGERPRINT_BUILD_STAGES.map((item, index) => (
          <span
            key={item.id}
            className={index < stageIndex ? "is-complete" : index === stageIndex ? "is-active" : ""}
          >
            <i />
            <b>{item.shortLabel}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

const SUPPORTED_HISTORICAL_SOURCES = ["CSV", "SCADA Export", "Historian Export"];

function uploadOrbStatus(viewState) {
  if (["uploading", "analyzing", "finalizing"].includes(viewState)) return "learning";
  if (viewState === "complete") return "healthy";
  return "awaiting";
}

function uploadFingerprintStatusText(viewState, hasSelectedFiles) {
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
  const fingerprintBuildStage = resolveFingerprintBuildStage({ viewState, uploadJob, uploadState });
  const remaining = estimateRemaining(uploadTransfer);
  const errorMessage = String(latestMessage || "Choose another telemetry file and try again.").trim();
  const summary = analysisResult ? completionSummary({ analysisResult }) : [];
  const showProgress = viewState === "uploading" || viewState === "analyzing" || viewState === "finalizing";
  const fingerprintStatus = uploadFingerprintStatusText(viewState, hasSelectedFiles);
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
                  label: fingerprintStatus,
                  visualLabel: "Behavioral Baseline",
                }}
              />
              <div className="upload-analysis-card__status" aria-live="polite">
                <span>Status</span>
                <strong>{fingerprintStatus}</strong>
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
              <div className="upload-file-chip" title={`${selectedFileLabel} - ${selectedFileSize}`}>
                <span className="upload-file-chip__icon" aria-hidden="true" />
                <span className="upload-file-chip__name">{selectedFileLabel}</span>
                <span className="upload-file-chip__meta">{selectedFileSize}</span>
              </div>
              <OperationalFingerprintBuild percent={mainPercent} stage={fingerprintBuildStage} />
              {remaining ? <p className="upload-simple-note">{remaining}</p> : null}
            </div>
          </section>
        ) : null}

        {viewState === "complete" ? (
          <section className="upload-analysis-card upload-simple-card--complete" aria-label="Analysis complete">
            <div className="upload-analysis-card__visual">
              <OperationalFingerprintBuild percent={100} stage={resolveFingerprintBuildStage({ viewState: "complete", uploadJob, uploadState })} complete />
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
              <OperationalFingerprintBuild percent={100} stage={resolveFingerprintBuildStage({ viewState: "complete", uploadJob, uploadState })} complete />
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
                  label: fingerprintStatus,
                  visualLabel: "Behavioral Baseline",
                }}
              />
              <div className="upload-analysis-card__status">
                <span>Status</span>
                <strong>{fingerprintStatus}</strong>
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
