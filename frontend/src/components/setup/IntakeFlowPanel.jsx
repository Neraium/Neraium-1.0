import { Component, useEffect, useRef, useState } from "react";

import { buildIntakeStages, normalizeUploadStatus as normalizeUploadLifecycle } from "../../viewModels/uploadFlow";
import OperationalOrb from "../operational/OperationalOrb";
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
  if (viewState === "uploading") return "Validating dataset";
  if (viewState === "complete") return "Analysis complete";
  if (viewState === "finalizing") return "Preparing results";
  if (viewState === "failed") return "Dataset import failed";
  if (viewState === "completion_error") return "Analysis saved, results not opened";
  if (/temporarily unavailable/i.test(cleanMessage)) return cleanMessage;

  const normalized = primaryJobStatus(uploadJob, uploadState);
  if (["writing_state", "cognition_ready", "saving_result", "saving_results"].includes(normalized)) return "Preparing evidence";
  if (["accepted", "queued", "validating_schema", "parsing"].includes(normalized)) return "Validating dataset";
  if (["mapping", "mapping_signals", "detecting_variables"].includes(normalized)) return "Mapping signals";
  if (["processing", "baseline_modeling", "building_baseline"].includes(normalized)) return "Building baseline";
  if (["building_fingerprint", "structural_scoring", "running_sii"].includes(normalized)) return "Comparing relationships";
  return cleanMessage || "Preparing analysis";
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

function relationshipChangeDetected(analysisResult) {
  const explicit = analysisResult?.relationship_change_detected
    ?? analysisResult?.relationshipChangeDetected
    ?? analysisResult?.fingerprint?.relationship_change_detected
    ?? analysisResult?.fingerprint?.change_detected;
  if (typeof explicit === "boolean") return explicit;

  const fingerprintStatus = String(
    analysisResult?.fingerprint?.status
      ?? analysisResult?.fingerprint?.drift_status
      ?? analysisResult?.fingerprint?.label
      ?? ""
  ).trim().toLowerCase();
  if (["changed", "drifting", "review", "unstable", "detected", "elevated", "alert", "watch"].includes(fingerprintStatus)) return true;
  if (["stable", "established", "unchanged", "not detected", "nominal"].includes(fingerprintStatus)) return false;
  if (Array.isArray(analysisResult?.relationships) && analysisResult.relationships.length > 0) return true;

  const primaryInsight = analysisResult?.insights?.find((insight) => insight && insight.id !== "baseline-stable");
  return Boolean(primaryInsight && String(primaryInsight.severity || "").toLowerCase() !== "low");
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

function normalizeEvidenceTier(value, analysisResult) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "confirmed") return "Confirmed";
  if (["qualified", "high", "moderate"].includes(normalized)) return "Qualified";
  if (["narrowed", "low", "weak"].includes(normalized)) return "Narrowed";
  if (["deferred", "pending", "incomplete"].includes(normalized)) return "Deferred";
  if (["withheld", "insufficient", "unreliable"].includes(normalized)) return "Withheld";
  const baselineStatus = String(analysisResult?.fingerprint?.status ?? analysisResult?.fingerprint?.drift_status ?? "").toLowerCase();
  return /established|stable|changed|complete/.test(baselineStatus) ? "Qualified" : "Deferred";
}

function activeFindingCount(analysisResult) {
  return analysisResult.insights.filter((insight) => {
    const id = String(insight?.id || "").toLowerCase();
    const status = String(insight?.status || insight?.state || "").toLowerCase();
    return id !== "baseline-stable" && !["normal", "stable", "resolved", "closed"].includes(status);
  }).length;
}

function completionResult(analysisResult) {
  const findings = activeFindingCount(analysisResult);
  let evidenceQuality = normalizeEvidenceTier(
    analysisResult?.evidence_quality
      ?? analysisResult?.confidence_tier
      ?? analysisResult?.insights?.[0]?.confidence_tier
      ?? analysisResult?.insights?.[0]?.confidence,
    analysisResult,
  );
  if (analysisResult?.reliable === false) evidenceQuality = "Withheld";
  else if (analysisResult?.baseline_sufficient === false && evidenceQuality !== "Withheld") evidenceQuality = "Deferred";
  const insufficient = ["Deferred", "Withheld"].includes(evidenceQuality);
  const status = insufficient ? "Evidence insufficient" : findings || relationshipChangeDetected(analysisResult) ? "Change detected" : "Normal";
  return { status, findings, evidenceQuality };
}

function completionSummary({ analysisResult }) {
  const completed = completionResult(analysisResult);
  return [
    { label: "Status", value: completed.status },
    { label: "Findings", value: String(completed.findings) },
    { label: "Evidence quality", value: completed.evidenceQuality },
  ];
}

const FINGERPRINT_BUILD_STAGES = [
  {
    id: "validate",
    label: "Validating dataset",
    description: "Checking the dataset format and required signals.",
    shortLabel: "Validate",
    states: ["uploading", "queued", "accepted", "validating_schema", "parsing", "validated"],
  },
  {
    id: "map",
    label: "Mapping signals",
    description: "Matching telemetry to supported systems and assets.",
    shortLabel: "Map",
    states: ["mapping", "mapping_signals", "detecting_variables"],
  },
  {
    id: "baseline",
    label: "Building baseline",
    description: "Learning the expected relationships in the baseline window.",
    shortLabel: "Baseline",
    states: ["processing", "baseline_modeling", "building_baseline"],
  },
  {
    id: "compare",
    label: "Comparing relationships",
    description: "Checking current behavior against the learned baseline.",
    shortLabel: "Compare",
    states: ["running_sii", "structural_scoring", "building_fingerprint"],
  },
  {
    id: "evidence",
    label: "Preparing evidence",
    description: "Saving the strongest observations and confidence result.",
    shortLabel: "Evidence",
    states: ["writing_state", "cognition_ready", "saving_result", "saving_results", "navigation_pending"],
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
  { x: 90, y: 70, r: 5.2, role: "core" },
  { x: 52, y: 48, r: 3.4, role: "system" },
  { x: 124, y: 38, r: 3.6, role: "system" },
  { x: 146, y: 76, r: 3.2, role: "system" },
  { x: 108, y: 108, r: 3.5, role: "system" },
  { x: 38, y: 94, r: 2.6, role: "signal" },
  { x: 77, y: 25, r: 2.5, role: "signal" },
  { x: 158, y: 43, r: 2.4, role: "signal" },
  { x: 62, y: 116, r: 2.5, role: "signal" },
  { x: 19, y: 65, r: 1.9, role: "signal" },
  { x: 164, y: 111, r: 2.1, role: "signal" },
];

const BASELINE_NETWORK_LINKS = [
  { phase: 0, path: "M19 65L52 48L77 25" },
  { phase: 0, path: "M77 25L124 38L158 43" },
  { phase: 1, path: "M52 48Q70 53 90 70" },
  { phase: 1, path: "M124 38Q108 50 90 70" },
  { phase: 1, path: "M90 70Q120 62 146 76" },
  { phase: 2, path: "M90 70Q101 88 108 108" },
  { phase: 2, path: "M108 108L164 111" },
  { phase: 2, path: "M146 76Q137 96 108 108" },
  { phase: 3, path: "M38 94L62 116L108 108" },
  { phase: 3, path: "M38 94Q56 76 90 70" },
];

const CONSTELLATION_SIGNAL_PATHS = [
  "M19 65L52 48L77 25L124 38L158 43",
  "M38 94Q56 76 90 70Q120 62 146 76Q137 96 108 108L164 111",
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
    return { id: "complete", label: "Analysis complete", description: "Evidence is ready to review.", index: FINGERPRINT_BUILD_STAGES.length };
  }
  if (viewState === "finalizing") return { ...FINGERPRINT_BUILD_STAGES[4], index: 4 };
  if (viewState === "uploading") return { ...FINGERPRINT_BUILD_STAGES[0], index: 0 };

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
  const index = rawMatchedIndex >= 0 ? rawMatchedIndex : normalizedMatchedIndex >= 0 ? normalizedMatchedIndex : 2;
  return { ...FINGERPRINT_BUILD_STAGES[index], index };
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
  const rootRef = useRef(null);
  const [renderProfile, setRenderProfile] = useState(() => forcedTier ? { tier: forcedTier, reason: recoveryReason || "renderer-recovery" } : detectFingerprintRenderTier());
  const renderTier = forcedTier || renderProfile.tier;
  const compatibilityMode = renderTier === "safe";
  const particleCount = FINGERPRINT_RENDERER_PARTICLES[renderTier] ?? 0;
  const statusTitle = stage?.label || (complete ? "Analysis complete" : "Preparing analysis");
  const statusDetail = stage?.description || (complete ? "Evidence is ready to review." : "Checking the dataset.");

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
      className={`upload-fingerprint-build infrastructure-constellation upload-fingerprint-build--${renderTier}${complete ? " upload-fingerprint-build--complete" : ""}`}
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
        <span className="upload-fingerprint-build__stage-readout"><i aria-hidden="true" />{statusDetail}</span>
      </div>
      <svg className="upload-fingerprint-build__print upload-fingerprint-build__constellation" viewBox="0 0 180 140" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id="upload-baseline-link" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--blue-primary)" stopOpacity="0.22" />
            <stop offset="0.52" stopColor="var(--blue-glow)" stopOpacity="0.96" />
            <stop offset="1" stopColor="var(--blue-primary)" stopOpacity="0.38" />
          </linearGradient>
          <radialGradient id="upload-intelligence-field" cx="50%" cy="48%" r="64%">
            <stop offset="0" stopColor="var(--blue-primary)" stopOpacity="0.1" />
            <stop offset="0.68" stopColor="var(--blue-deep)" stopOpacity="0.035" />
            <stop offset="1" stopColor="var(--blue-deep)" stopOpacity="0" />
          </radialGradient>
          <pattern id="upload-intelligence-grid" width="12" height="12" patternUnits="userSpaceOnUse">
            <path d="M12 0H0V12" fill="none" stroke="var(--blue-glow)" strokeOpacity="0.075" strokeWidth="0.35" />
          </pattern>
          <filter id="upload-baseline-node-glow" x="-200%" y="-200%" width="500%" height="500%">
            <feGaussianBlur stdDeviation="1.8" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <rect className="upload-fingerprint-build__field" x="2" y="2" width="176" height="136" rx="18" />
        <rect className="upload-fingerprint-build__field-light" x="2" y="2" width="176" height="136" rx="18" fill="url(#upload-intelligence-field)" />
        <rect className="upload-fingerprint-build__grid" x="10" y="10" width="160" height="120" rx="12" fill="url(#upload-intelligence-grid)" />
        <g className="upload-fingerprint-build__coordinates">
          <path d="M90 12V25M90 115V128M14 70H28M152 70H166" />
          <circle cx="90" cy="70" r="50" />
          <circle cx="90" cy="70" r="28" />
        </g>
        <g className="upload-fingerprint-build__relationship-ghosts">
          {BASELINE_NETWORK_LINKS.map((link) => <path key={`ghost-${link.path}`} d={link.path} />)}
        </g>
        <g className="upload-fingerprint-build__relationship-links">
          {BASELINE_NETWORK_LINKS.map((link, index) => {
            const fill = networkProgress({ displayPercent, phase: link.phase, stageIndex, complete });
            return <path key={link.path} d={link.path} pathLength="100" style={{ "--network-offset": compatibilityMode ? (fill > 0 ? 0 : 100) : 100 - fill, "--link-index": index }} />;
          })}
        </g>
        <g className="upload-fingerprint-build__signals" aria-hidden="true">
          {CONSTELLATION_SIGNAL_PATHS.map((path, index) => (
            <circle key={path} className="upload-fingerprint-build__signal" r="1.8" style={{ offsetPath: `path('${path}')`, animationDelay: `${index * -1.8}s` }} />
          ))}
        </g>
        <g className="upload-fingerprint-build__evidence-points" filter="url(#upload-baseline-node-glow)">
          {BASELINE_NETWORK_NODES.map((node, index) => (
            <g key={`${node.x}-${node.y}`} className={`upload-fingerprint-build__network-node upload-fingerprint-build__network-node--${node.role}`} style={{ "--point-index": index }}>
              <circle className="upload-fingerprint-build__node-orbit" cx={node.x} cy={node.y} r={node.r + 4.5} />
              <circle className="upload-fingerprint-build__node-core" cx={node.x} cy={node.y} r={node.r} />
            </g>
          ))}
        </g>
      </svg>
      {complete ? <div className="upload-fingerprint-build__check" aria-hidden="true">✓</div> : null}
      <ol className="upload-fingerprint-build__nodes" aria-label="Analysis stages">
        {FINGERPRINT_BUILD_STAGES.map((item, index) => {
          const state = complete || index < stageIndex ? "complete" : index === stageIndex ? "active" : "pending";
          return (
            <li
              key={item.id}
              className={`${state === "complete" ? "is-complete" : state === "active" ? "is-active" : ""}${index === FINGERPRINT_BUILD_STAGES.length - 1 ? " is-final" : ""}`}
              aria-label={`${item.shortLabel}: ${state === "complete" ? "completed" : state}`}
              aria-current={state === "active" ? "step" : undefined}
            >
              <i aria-hidden="true">{state === "complete" ? "✓" : ""}</i>
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

function uploadFingerprintStatusText(viewState, hasSelectedFiles) {
  if (["uploading", "analyzing", "finalizing"].includes(viewState)) return "Analysis in Progress";
  if (viewState === "complete") return "Behavior Baseline Active";
  if (viewState === "failed") return hasSelectedFiles ? "Dataset Ready" : "Awaiting Behavior Baseline";
  if (hasSelectedFiles) return "Dataset Ready";
  return "Awaiting Behavior Baseline";
}

function buildAdvancedRows({ uploadJob, uploadTransfer, propagationLabel, queuedWorkerDetail, latestMessage, uploadDebug }) {
  return [
    ["Analysis ID", uploadJob?.job_id ?? uploadJob?.id],
    ["Analysis stage", uploadJob?.processing_state ?? uploadJob?.processingState ?? uploadJob?.status],
    ["Elapsed time", uploadJob?.processing_time_seconds ? `${uploadJob.processing_time_seconds}s` : null],
    ["Transfer", uploadTransfer?.label],
    ["Analysis result", uploadJob?.result_available ? "Available" : uploadJob?.first_usable_available ? "Preliminary result available" : null],
    ["Analysis status", queuedWorkerDetail],
    ["Current step", propagationLabel],
    ["Operator message", latestMessage],
  ].filter(([, value]) => String(value ?? "").trim());
}

function buildFailureRecoveryRows({ viewState, hasSelectedFiles, selectedFileLabel, uploadJob, errorMessage }) {
  if (viewState === "completion_error") {
    return [
      ["What failed", "The analysis saved, but Portfolio did not open the result."],
      ["What still succeeded", "The behavior baseline and evidence record were saved."],
      ["Next action", "Open the analysis again. If that fails, analyze another dataset or refresh."],
    ];
  }
  return [
    ["What failed", errorMessage || "The dataset could not finish import or processing."],
    ["What still succeeded", hasSelectedFiles ? `${selectedFileLabel} is still selected for retry.` : "No dataset is currently selected."],
    ["Next action", uploadJob?.job_id ? "Retry the analysis. If the job expired, choose the dataset again." : "Choose a dataset and start the analysis again."],
  ];
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

function RecoverySummary({ rows }) {
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
      <summary><span className="upload-advanced-details__summary-label"><i aria-hidden="true" />Analysis Details</span><span className="upload-advanced-details__chevron" aria-hidden="true" /></summary>
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
        <ol className="upload-advanced-details__stages" aria-label="Analysis stages">
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
  const errorMessage = String(latestMessage || "Choose another telemetry dataset and try again.").trim();
  const failureRecoveryRows = buildFailureRecoveryRows({ viewState, hasSelectedFiles, selectedFileLabel, uploadJob, errorMessage });
  const summary = analysisResult ? completionSummary({ analysisResult }) : [];
  const completed = analysisResult ? completionResult(analysisResult) : null;
  const showProgress = viewState === "uploading" || viewState === "analyzing" || viewState === "finalizing";
  const fingerprintStatus = uploadFingerprintStatusText(viewState, hasSelectedFiles);
  const resolvedOrbStatus = uploadOrbStatus(viewState);
  const chooseFileButtonText = "Choose Dataset";
  const selectedFileDetail = hasSelectedFiles ? `${fileKind} dataset, ${selectedFileSize}` : "No file selected";
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
    <Panel title="Import and Analyze Dataset" className="span-7 upload-ops-panel upload-ops-panel--command">
      <form className={`intake-flow intake-flow--simple intake-flow--${viewState}`} onSubmit={handleUpload}>
        {(["noFile", "fileSelected"].includes(viewState)) ? <p className="intake-flow__subtitle">Import a historical telemetry dataset so SII can learn the facility behavior baseline and produce evidence-backed insights.</p> : null}
        <input data-testid="csv-upload-input" ref={uploadInputRef} accept=".csv,text/csv" id="csv-upload" type="file" multiple className="intake-flow__input" style={hiddenFileInputStyle} aria-label="Choose telemetry dataset CSV files" tabIndex={-1} onChange={handleFileSelection} />

        {(viewState === "noFile" || viewState === "fileSelected") ? (
          <section
            className={`upload-analysis-card${dragClassName}`}
            aria-label="Historical dataset import"
            onDragOver={handleUploadDragOver}
            onDragLeave={handleUploadDragLeave}
            onDrop={handleUploadDrop}
          >
            <div className="upload-analysis-card__visual">
              <OperationalOrb
                status={resolvedOrbStatus}
                state={{
                  label: fingerprintStatus,
                  visualLabel: "Behavior Baseline",
                }}
              />
              <div className="upload-analysis-card__status" aria-live="polite">
                <span>Status</span>
                <strong>{fingerprintStatus}</strong>
              </div>
            </div>

            <div className="upload-analysis-card__content">
              <div className="upload-analysis-card__copy">
                <p className="section-token">Historical Dataset</p>
                <h3>Import and Analyze Dataset</h3>
                <p>Import a historical telemetry dataset so SII can learn the facility behavior baseline and produce evidence-backed insights.</p>
              </div>

              <div className="upload-analysis-card__sources" role="group" aria-label="Supported dataset types">
                <span>Supported Dataset Types</span>
                <ul>
                  {SUPPORTED_HISTORICAL_SOURCES.map((source) => <li key={source}>{source}</li>)}
                </ul>
              </div>

              {hasSelectedFiles ? (
                <DatasetFileRow filename={selectedFileLabel} size={selectedFileSize} status="Ready" />
              ) : (
                <div className="upload-analysis-card__file">
                  <i className="upload-analysis-card__file-icon" aria-hidden="true" />
                  <span className="upload-analysis-card__file-copy">
                    <span>Dataset</span>
                    <strong>{selectedFileDetail}</strong>
                  </span>
                </div>
              )}

              <div className="upload-simple-actions upload-analysis-card__actions">
                <button type="button" className="secondary-command-button" onClick={() => openFilePicker("csv")}>{chooseFileButtonText}</button>
                <button data-testid="process-upload-button" className="command-button" type="submit" disabled={!hasSelectedFiles || isUploadProcessing(uploadState)} title={!hasSelectedFiles ? "Choose a CSV dataset before starting analysis." : isUploadProcessing(uploadState) ? "Analysis is already in progress." : "Start dataset analysis."}>
                  Analyze Dataset
                </button>
              </div>
            </div>
          </section>
        ) : null}

        {showProgress ? (
          <section className="upload-analysis-card upload-analysis-card--processing upload-analysis-card--compact" aria-live="polite" aria-label={`Analysis progress: ${statusText}`}>
            <div className="upload-analysis-card__content">
              <p className="upload-processing-file"><span>Dataset</span><strong>{selectedFileLabel}</strong></p>
              <div className="upload-analysis-card__intelligence">
                <OperationalFingerprintBuild percent={mainPercent} stage={fingerprintBuildStage} />
              </div>
            </div>
          </section>
        ) : null}

        {viewState === "complete" ? (
          <section className="upload-analysis-card upload-simple-card--complete upload-analysis-card--compact" aria-labelledby="analysis-complete-heading" aria-live="polite">
            <div className="upload-analysis-card__visual">
              <OperationalFingerprintBuild percent={100} stage={resolveFingerprintBuildStage({ viewState: "complete", uploadJob, uploadState })} complete />
            </div>
            <div className="upload-analysis-card__content">
              <div className="upload-complete-header">
                <h3 id="analysis-complete-heading">Analysis complete</h3>
              </div>
              <p className="upload-processing-file"><span>Dataset</span><strong>{selectedFileLabel}</strong></p>
              <dl className="upload-result-summary" aria-label="Analysis result summary">
                {summary.map((item) => (
                  <div key={item.label} className="upload-result-summary__item">
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
              <div className="upload-simple-actions upload-completion-actions">
                <button type="button" className="command-button upload-completion-actions__primary" onClick={onViewResults}>{completed?.status === "Evidence insufficient" ? "Review Data Requirements" : "View Results"}</button>
                <button type="button" className="secondary-command-button upload-completion-actions__secondary" onClick={onResetWorkspace}>Analyze Another Dataset</button>
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
                <strong>Behavior Baseline Established</strong>
              </div>
            </div>
            <div className="upload-analysis-card__content">
              <div className="upload-complete-header">
                <h3>Analysis Saved, Results Not Opened</h3>
                <span>{hasSelectedFiles ? selectedFileLabel : "Results saved"}</span>
              </div>
              <p className="upload-error-message">{errorMessage || "The analysis was saved, but its results could not be opened. Try opening the analysis again."}</p>
              <RecoverySummary rows={failureRecoveryRows} />
              <div className="upload-simple-actions">
                <button type="button" className="command-button" onClick={onViewResults}>Open Analysis Again</button>
                <button type="button" className="secondary-command-button" onClick={onResetWorkspace}>Analyze Another Dataset</button>
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
                  visualLabel: "Behavior Baseline",
                }}
              />
              <div className="upload-analysis-card__status">
                <span>Status</span>
                <strong>{fingerprintStatus}</strong>
              </div>
            </div>
            <div className="upload-analysis-card__content">
              <div className="upload-complete-header">
                <h3>Dataset Import Failed</h3>
                <span>{hasSelectedFiles ? selectedFileLabel : "No file selected"}</span>
              </div>
              <p className="upload-error-message">{errorMessage}</p>
              <RecoverySummary rows={failureRecoveryRows} />
              <div className="upload-simple-actions">
                <button type="button" className="command-button" onClick={() => onRetryFailedUploads?.()} disabled={!hasSelectedFiles} title={!hasSelectedFiles ? "Choose the source dataset again before retrying." : "Retry this analysis."}>Retry Analysis</button>
                <button type="button" className="secondary-command-button" onClick={() => openFilePicker("csv")}>Choose Dataset</button>
              </div>
            </div>
          </section>
        ) : null}

        {["failed", "completion_error"].includes(viewState) ? (
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
        ) : null}
      </form>
    </Panel>
  );
}
