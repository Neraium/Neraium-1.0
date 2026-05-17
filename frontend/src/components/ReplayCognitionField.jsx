import React, { useMemo } from "react";

const PHASES = [
  "stable_topology",
  "relationship_weakening",
  "pressure_migration",
  "archetype_emergence",
  "propagation_activation",
  "structural_fragmentation",
  "continuation_pathways",
  "recovery_or_escalation",
];

const BASE_NODES = [
  { id: "baseline", label: "Baseline", x: 118, y: 190, group: "anchor" },
  { id: "thermal", label: "Thermal", x: 250, y: 116, group: "environment" },
  { id: "humidity", label: "Humidity", x: 428, y: 142, group: "environment" },
  { id: "airflow", label: "Airflow", x: 602, y: 202, group: "propagation" },
  { id: "irrigation", label: "Irrigation", x: 522, y: 344, group: "support" },
  { id: "canopy", label: "Canopy", x: 334, y: 382, group: "support" },
  { id: "operator", label: "Recovery", x: 172, y: 318, group: "recovery" },
];

const LINKS = [
  ["baseline", "thermal"],
  ["thermal", "humidity"],
  ["humidity", "airflow"],
  ["airflow", "irrigation"],
  ["irrigation", "canopy"],
  ["canopy", "operator"],
  ["operator", "baseline"],
  ["thermal", "canopy"],
  ["humidity", "canopy"],
  ["airflow", "operator"],
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

function phaseIndex(frame) {
  const phase = frame?.cognition_state?.canonical_phase ?? frame?.topology_state?.phase;
  const index = PHASES.indexOf(phase);
  return index >= 0 ? index : 0;
}

function buildFallbackTimeline(seedFrame) {
  const now = Date.now();
  return PHASES.slice(0, 6).map((phase, index) => {
    const intensity = index / 5;
    return {
      timestamp: new Date(now - (5 - index) * 1000 * 60 * 18).toISOString(),
      topology_state: {
        phase,
        stability_state: intensity > 0.72 ? "TOPOLOGY DIVERGENCE ACTIVE" : intensity > 0.44 ? "STRUCTURAL DRIFT EMERGING" : "BASELINE LOCKED",
        fragmentation_indicator: intensity > 0.72 ? "high" : intensity > 0.44 ? "moderate" : "low",
      },
      propagation_state: {
        propagation_acceleration: intensity > 0.7 ? "high" : intensity > 0.35 ? "moderate" : "low",
        recovery_convergence: intensity > 0.76 ? "delayed" : intensity > 0.5 ? "monitoring" : "stable",
        dominant_paths: seedFrame?.propagation_state?.dominant_paths ?? ["baseline_to_environment_to_recovery"],
      },
      cognition_state: {
        canonical_phase: phase,
        confidence_tier: intensity > 0.5 ? "EVIDENCE LOCK" : "BASELINE FORMING",
        operational_phase: intensity > 0.5 ? "propagation_watch" : "baseline_construction",
        facility_state: intensity > 0.62 ? "Propagation Watch Active" : "Structural Drift Emerging",
      },
      continuation_window: { window: intensity > 0.7 ? "3 to 6 operational days" : "7 to 14 operational days", timing_window: "model-derived watch" },
      subsystem_pressure: { compression_intensity: intensity > 0.7 ? "high" : intensity > 0.35 ? "moderate" : "low" },
    };
  });
}

function buildFieldModel(timeline, frameIndex) {
  const safeTimeline = Array.isArray(timeline) && timeline.length > 0 ? timeline : buildFallbackTimeline(null);
  const safeIndex = clamp(frameIndex, 0, safeTimeline.length - 1);
  const activeFrame = safeTimeline[safeIndex] ?? safeTimeline[safeTimeline.length - 1];
  const activePhaseIndex = phaseIndex(activeFrame);
  const phaseProgress = safeTimeline.length > 1 ? safeIndex / (safeTimeline.length - 1) : activePhaseIndex / (PHASES.length - 1);
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
    const localPhase = phaseIndex(frame) / Math.max(PHASES.length - 1, 1);
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

function display(value, fallback = "Telemetry-derived") {
  const raw = String(value ?? "").replaceAll("_", " ").trim();
  return raw || fallback;
}

export default function ReplayCognitionField({ timeline, frameIndex, isPlaying, comparisonMode, formatClockTime }) {
  const model = useMemo(() => buildFieldModel(timeline, frameIndex), [timeline, frameIndex]);
  const frame = model.activeFrame;
  const status = display(frame?.topology_state?.stability_state, "Structural Drift Emerging");
  const phase = display(frame?.cognition_state?.canonical_phase ?? frame?.topology_state?.phase, "baseline construction");
  const confidence = display(frame?.cognition_state?.confidence_tier, "Evidence lock forming");
  const pathLabel = model.dominantPaths?.[0]?.replaceAll?.("_", " → ") ?? "baseline → environment → recovery";

  return (
    <section
      className={`replay-cognition-field ${isPlaying ? "replay-cognition-field--playing" : ""} ${comparisonMode ? "replay-cognition-field--comparison" : ""}`}
      style={{
        "--replay-drift": model.drift.toFixed(3),
        "--replay-propagation": model.propagation.toFixed(3),
        "--replay-divergence": model.divergence.toFixed(3),
        "--replay-recovery": model.recovery.toFixed(3),
      }}
      aria-label="Animated structural replay cognition field"
    >
      <div className="replay-cognition-field__header">
        <div>
          <p className="section-token">Intake Status</p>
          <h3>{status}</h3>
          <span>{phase} · {pathLabel}</span>
        </div>
        <div className="replay-cognition-field__state">
          <strong>{Math.round(model.divergence * 100)}%</strong>
          <span>baseline divergence</span>
        </div>
      </div>

      <svg className="replay-cognition-field__svg" viewBox="0 0 720 460" role="img" aria-label="Topology evolution, drift trajectory, and relationship propagation">
        <defs>
          <radialGradient id="replayFieldGlow" cx="50%" cy="48%" r="58%">
            <stop offset="0%" stopColor="rgba(138, 184, 196, 0.28)" />
            <stop offset="58%" stopColor="rgba(108, 186, 156, 0.08)" />
            <stop offset="100%" stopColor="rgba(8, 12, 15, 0)" />
          </radialGradient>
          <linearGradient id="replayTraceGradient" x1="0%" x2="100%" y1="0%" y2="0%">
            <stop offset="0%" stopColor="rgba(108, 186, 156, 0.18)" />
            <stop offset="48%" stopColor="rgba(138, 184, 196, 0.92)" />
            <stop offset="100%" stopColor="rgba(212, 107, 95, 0.88)" />
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
        <path d={model.trajectoryPath} className="replay-cognition-field__trajectory replay-cognition-field__trajectory--ghost" />
        <path d={model.activeTrajectoryPath || model.trajectoryPath} className="replay-cognition-field__trajectory" filter="url(#replaySoftGlow)" />
        {model.trajectory.map((point, index) => (
          <circle key={`trajectory-${index}`} cx={point.x} cy={point.y} r={index === model.safeIndex ? 5 : 2.8} className={`replay-cognition-field__trajectory-node ${point.active ? "is-active" : ""} ${index === model.safeIndex ? "is-current" : ""}`} />
        ))}
        {model.nodes.map((node, index) => (
          <g key={node.id} className="replay-cognition-field__node-group" style={{ "--node-index": index, "--node-activity": node.activity }}>
            <circle cx={node.x} cy={node.y} r={16 + node.activity * 10} className="replay-cognition-field__node-halo" />
            <circle cx={node.x} cy={node.y} r={7 + node.activity * 5} className={`replay-cognition-field__node replay-cognition-field__node--${node.group}`} />
            <text x={node.x} y={node.y + 30} className="replay-cognition-field__node-label">{node.label}</text>
          </g>
        ))}
        <circle cx={model.nodes[2].x} cy={model.nodes[2].y} r={54 + model.propagation * 46} className="replay-cognition-field__structural-pulse" />
      </svg>

      <div className="replay-cognition-field__footer">
        <div><span>Topology</span><strong>{display(frame?.topology_state?.fragmentation_indicator, "coherent mesh")}</strong></div>
        <div><span>Propagation</span><strong>{display(frame?.propagation_state?.propagation_acceleration, "watching")}</strong></div>
        <div><span>Recovery</span><strong>{display(frame?.propagation_state?.recovery_convergence, "convergence tracking")}</strong></div>
        <div><span>Confidence</span><strong>{confidence}</strong></div>
        <div><span>Timestamp</span><strong>{frame?.timestamp ? formatClockTime(frame.timestamp) : "model generated"}</strong></div>
      </div>
    </section>
  );
}
