import React, { useMemo } from "react";
import { normalizeOperatorConfidenceLabel, sanitizeOperatorText } from "../viewModels/operatorFinding";

const BASE_NODES = [
  { id: "baseline", label: "Baseline", x: 118, y: 190, group: "anchor" },
  { id: "thermal", label: "Thermal", x: 250, y: 116, group: "environment" },
  { id: "chemistry", label: "Chemistry", x: 428, y: 142, group: "environment" },
  { id: "flow", label: "Flow", x: 602, y: 202, group: "propagation" },
  { id: "filtration", label: "Filtration", x: 522, y: 344, group: "support" },
  { id: "occupancy", label: "Occupancy", x: 334, y: 382, group: "support" },
  { id: "operator", label: "Recovery", x: 172, y: 318, group: "recovery" },
];

const LINKS = [
  ["baseline", "thermal"],
  ["thermal", "chemistry"],
  ["chemistry", "flow"],
  ["flow", "filtration"],
  ["filtration", "occupancy"],
  ["occupancy", "operator"],
  ["operator", "baseline"],
  ["thermal", "occupancy"],
  ["chemistry", "occupancy"],
  ["flow", "operator"],
];

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function textMagnitude(value) {
  const normalized = String(value ?? "").toLowerCase();
  if (normalized.includes("critical") || normalized.includes("deterior") || normalized.includes("high") || normalized.includes("fragment")) return 0.92;
  if (normalized.includes("watch") || normalized.includes("moderate") || normalized.includes("emerg") || normalized.includes("delay")) return 0.58;
  if (normalized.includes("recover") || normalized.includes("convergen") || normalized.includes("stable") || normalized.includes("low")) return 0.24;
  return 0.42;
}

function buildFieldModel(timeline, frameIndex) {
  const safeTimeline = Array.isArray(timeline) ? timeline : [];
  if (safeTimeline.length === 0) {
    const nodes = BASE_NODES.map((node) => ({ ...node, activity: 0.1 }));
    const nodeMap = Object.fromEntries(nodes.map((node) => [node.id, node]));
    return {
      activeFrame: null,
      safeTimeline: [],
      safeIndex: 0,
      activePhaseIndex: -1,
      drift: 0,
      propagation: 0,
      divergence: 0,
      recovery: 0,
      dominantPaths: [],
      nodes,
      nodeMap,
      trajectory: [],
      trajectoryPath: "",
      activeTrajectoryPath: "",
    };
  }
  const safeIndex = clamp(frameIndex, 0, safeTimeline.length - 1);
  const activeFrame = safeTimeline[safeIndex] ?? safeTimeline[safeTimeline.length - 1];
  const activePhaseIndex = safeIndex;
  const phaseProgress = safeTimeline.length > 1 ? safeIndex / (safeTimeline.length - 1) : 0;
  const drift = clamp(
    (textMagnitude(activeFrame?.topology_state?.stability_state)
      + textMagnitude(activeFrame?.topology_state?.fragmentation_indicator)
      + textMagnitude(activeFrame?.subsystem_pressure?.compression_intensity)) / 3,
    0,
    1,
  );
  const propagation = clamp(textMagnitude(activeFrame?.propagation_state?.propagation_acceleration), 0, 1);
  const convergence = clamp(1 - textMagnitude(activeFrame?.propagation_state?.recovery_convergence), 0, 1);
  const divergence = clamp((drift * 0.64) + (propagation * 0.28) + (phaseProgress * 0.16) - (convergence * 0.12), 0.08, 1);
  const recovery = clamp(1 - divergence + convergence * 0.24, 0, 1);
  const dominantPaths = activeFrame?.propagation_state?.dominant_paths ?? [];

  const nodes = BASE_NODES.map((node, index) => {
    const wave = Math.sin((safeIndex + 1) * 0.78 + index * 1.24);
    const radial = node.group === "anchor" ? -0.2 : node.group === "recovery" ? recovery - 0.5 : divergence;
    const dx = Math.cos(index * 0.9) * radial * 34 + wave * 12 * divergence;
    const dy = Math.sin(index * 1.1) * radial * 28 + Math.cos(safeIndex * 0.62 + index) * 10 * propagation;
    const activity = clamp((node.group === "propagation" ? propagation : node.group === "recovery" ? recovery : drift) + index * 0.025, 0.18, 1);
    return { ...node, x: node.x + dx, y: node.y + dy, activity };
  });
  const nodeMap = Object.fromEntries(nodes.map((node) => [node.id, node]));
  const trajectory = safeTimeline.map((frame, index) => {
    const localPhase = safeTimeline.length > 1 ? index / (safeTimeline.length - 1) : 0;
    const localDrift = textMagnitude(frame?.topology_state?.fragmentation_indicator ?? frame?.topology_state?.stability_state);
    return {
      x: 94 + (index / Math.max(safeTimeline.length - 1, 1)) * 548,
      y: 402 - (localDrift * 190) + Math.sin(localPhase * Math.PI * 2) * 30,
      active: index <= safeIndex,
    };
  });
  const trajectoryPath = trajectory.map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const activeTrajectoryPath = trajectory.filter((point) => point.active).map((point, index) => `${index === 0 ? "M" : "L"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");

  return {
    activeFrame,
    safeTimeline,
    safeIndex,
    phaseProgress,
    activePhaseIndex,
    drift,
    propagation,
    divergence,
    recovery,
    dominantPaths,
    nodes,
    nodeMap,
    trajectory,
    trajectoryPath,
    activeTrajectoryPath,
  };
}

function display(value, fallback = "-") {
  const raw = humanizeOperatorValue(value);
  return sanitizeOperatorText(raw || fallback);
}

function humanizeOperatorValue(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  const variableMap = new Map([
    ["chiller_load_pct", "Chiller load"],
    ["chiller load pct", "Chiller load"],
    ["compressor_power_kw", "Compressor power"],
    ["compressor power kw", "Compressor power"],
    ["chw_supply_temp_f", "CHW supply temp"],
    ["chw supply temp f", "CHW supply temp"],
    ["flow_gpm", "Flow"],
    ["flow gpm", "Flow"],
  ]);
  const normalized = text.toLowerCase().replace(/[-_]+/g, " ").replace(/\s+/g, " ").trim();
  if (variableMap.has(text) || variableMap.has(normalized)) return variableMap.get(text) ?? variableMap.get(normalized);
  return normalized.split(" ").filter(Boolean).map((part) => {
    if (part === "chw") return "CHW";
    return part.charAt(0).toUpperCase() + part.slice(1);
  }).join(" ");
}

function humanizeRelationshipPath(value) {
  const text = String(value ?? "").trim();
  if (!text || text === "-") return "";
  const pieces = text.split(/\s*(?:->|\/|>)\s*/).filter(Boolean);
  const useful = pieces
    .filter((piece) => !/relationship|weakening|strengthening|propagation/i.test(piece))
    .map((piece) => humanizeOperatorValue(piece))
    .filter(Boolean);
  if (useful.length === 0) return "";
  if (useful.length === 1) return useful[0];
  const signal = useful[useful.length - 1];
  if (useful.length >= 3 && /^(Pct|Kw|F|Gpm)$/i.test(signal)) {
    return humanizeOperatorValue(useful.slice(0, -1).join(" "));
  }
  return useful.join(" to ");
}

function formatReplayConfidence(value) {
  const text = String(value ?? "").trim();
  if (!text) return "Low";
  if (/baseline[_\s-]*evidence/i.test(text)) return "Historical comparison";
  return humanizeOperatorValue(normalizeOperatorConfidenceLabel(text));
}

function formatReplayTimestamp(value, formatClockTime) {
  if (!value) return "-";
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false }).format(date).replace(",", " at");
  }
  return formatClockTime(value);
}

export default function ReplayCognitionField({ timeline, frameIndex, isPlaying, comparisonMode, formatClockTime, inactive = false }) {
  const model = useMemo(() => buildFieldModel(timeline, frameIndex), [timeline, frameIndex]);
  const frame = model.activeFrame;
  const status = inactive ? "-" : display(frame?.topology_state?.stability_state, "-");
  const phase = inactive ? "-" : display(frame?.cognition_state?.canonical_phase ?? frame?.topology_state?.phase, "-");
  const confidence = inactive ? "-" : formatReplayConfidence(frame?.cognition_state?.confidence_tier);
  const pathLabel = inactive ? "" : humanizeRelationshipPath(model.dominantPaths?.[0] ?? "");
  const timestamp = frame?.timestamp ? formatReplayTimestamp(frame.timestamp, formatClockTime) : "-";

  return (
    <section
      className={`replay-cognition-field ${isPlaying ? "replay-cognition-field--playing" : ""} ${comparisonMode ? "replay-cognition-field--comparison" : ""} ${inactive ? "replay-cognition-field--inactive" : ""}`}
      style={{
        "--replay-drift": model.drift.toFixed(3),
        "--replay-propagation": model.propagation.toFixed(3),
        "--replay-divergence": model.divergence.toFixed(3),
        "--replay-recovery": model.recovery.toFixed(3),
      }}
      aria-label="Animated evidence replay field"
    >
      <div className="replay-cognition-field__header">
        <div>
          <p className="section-token">Evidence replay</p>
          <h3>{status}</h3>
          <span>{[phase, pathLabel].filter((item) => item && item !== "-").join(" - ") || "Replay context"}</span>
        </div>
        <div className="replay-cognition-field__state">
          <strong>{inactive ? "-" : `${Math.round(model.divergence * 100)}%`}</strong>
          <span>{inactive ? "-" : "change strength"}</span>
        </div>
      </div>

      <svg className="replay-cognition-field__svg" viewBox="0 0 720 460" role="img" aria-label="System behavior change, operating pattern, and recovery trajectory">
        <defs>
          <radialGradient id="replayFieldGlow" cx="50%" cy="48%" r="58%">
            <stop offset="0%" stopColor="rgba(138, 184, 196, 0.28)" />
            <stop offset="58%" stopColor="rgba(108, 186, 156, 0.08)" />
            <stop offset="100%" stopColor="rgba(8, 12, 15, 0)" />
          </radialGradient>
          <linearGradient id="replayTraceGradient" x1="0%" x2="100%" y1="0%" y2="0%">
            <stop offset="0%" stopColor="rgba(108, 186, 156, 0.18)" />
            <stop offset="48%" stopColor="rgba(138, 184, 196, 0.92)" />
            <stop offset="100%" stopColor="rgba(211, 170, 103, 0.88)" />
          </linearGradient>
          <filter id="replaySoftGlow" x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        <rect x="0" y="0" width="720" height="460" rx="28" className="replay-cognition-field__backdrop" />
        <circle cx="360" cy="230" r="224" fill="url(#replayFieldGlow)" className="replay-cognition-field__drift-field" />
        {Array.from({ length: 7 }, (_, index) => (
          <path
            key={`field-${index}`}
            d={`M ${72 + index * 34} ${74 + index * 21} C ${220 + index * 18} ${46 + index * 31}, ${442 - index * 8} ${404 - index * 28}, ${650 - index * 26} ${386 - index * 15}`}
            className="replay-cognition-field__field-line"
            style={{ "--line-index": index }}
          />
        ))}
        {LINKS.map(([from, to], index) => {
          const a = model.nodeMap[from];
          const b = model.nodeMap[to];
          const hot = index <= model.activePhaseIndex + 2 || (model.propagation > 0.6 && index % 2 === 0);
          return (
            <g key={`${from}-${to}`}>
              <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className={`replay-cognition-field__link ${hot ? "is-hot" : ""}`} />
              {hot ? <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className="replay-cognition-field__link-pulse" style={{ "--link-index": index }} /> : null}
            </g>
          );
        })}
        {!inactive ? (
          <>
            <path d={model.trajectoryPath} className="replay-cognition-field__trajectory replay-cognition-field__trajectory--ghost" />
            <path d={model.activeTrajectoryPath || model.trajectoryPath} className="replay-cognition-field__trajectory" filter="url(#replaySoftGlow)" />
            {model.trajectory.map((point, index) => (
              <circle key={`trajectory-${index}`} cx={point.x} cy={point.y} r={index === model.safeIndex ? 5 : 2.8} className={`replay-cognition-field__trajectory-node ${point.active ? "is-active" : ""} ${index === model.safeIndex ? "is-current" : ""}`} />
            ))}
          </>
        ) : null}
        {model.nodes.map((node, index) => (
          <g key={node.id} className="replay-cognition-field__node-group" style={{ "--node-index": index, "--node-activity": node.activity }}>
            <circle cx={node.x} cy={node.y} r={16 + node.activity * 10} className="replay-cognition-field__node-halo" />
            <circle cx={node.x} cy={node.y} r={7 + node.activity * 5} className={`replay-cognition-field__node replay-cognition-field__node--${node.group}`} />
            <text x={node.x} y={node.y + 30} className="replay-cognition-field__node-label">{node.label}</text>
          </g>
        ))}
        {!inactive ? <circle cx={model.nodes[2].x} cy={model.nodes[2].y} r={54 + model.propagation * 46} className="replay-cognition-field__structural-pulse" /> : null}
      </svg>

      <section className="replay-cognition-field__mobile-summary" aria-label="System story summary">
        <div><span>Status</span><strong>{status}</strong></div>
        <div><span>Change strength</span><strong>{inactive ? "-" : `${Math.round(model.divergence * 100)}%`}</strong></div>
        <div><span>Confidence</span><strong>{confidence}</strong></div>
        <div><span>Timestamp</span><strong>{timestamp}</strong></div>
      </section>

      <div className="replay-cognition-field__footer">
        <div><span>Change state</span><strong>{inactive ? "-" : display(frame?.topology_state?.fragmentation_indicator, "-")}</strong></div>
        <div><span>Coupling pressure</span><strong>{inactive ? "-" : display(frame?.propagation_state?.propagation_acceleration, "-")}</strong></div>
        <div><span>Return path</span><strong>{inactive ? "-" : display(frame?.propagation_state?.recovery_convergence, "-")}</strong></div>
        <div><span>Confidence</span><strong>{confidence}</strong></div>
        <div><span>Timestamp</span><strong>{timestamp}</strong></div>
      </div>
    </section>
  );
}
