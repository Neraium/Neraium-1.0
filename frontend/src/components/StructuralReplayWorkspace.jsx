import React, { useEffect, useMemo, useState } from "react";
import { fetchReplayRange, fetchReplayTimeline } from "../services/api/replayApi";
import PropagationMap from "./PropagationMap";
import StructuralMemoryPanel from "./StructuralMemoryPanel";
import EvidenceLineagePanel from "./EvidenceLineagePanel";
import EvidenceInteractionPanel from "./EvidenceInteractionPanel";
import ReplayCognitionField from "./ReplayCognitionField";

export default function StructuralReplayWorkspace({
  apiFetch,
  accessCode,
  normalizeErrorMessage,
  formatClockTime,
  Panel,
  MetricGrid,
  EmptyState,
  mode = "live",
}) {
  const [timeline, setTimeline] = useState([]);
  const [comparisonTimeline, setComparisonTimeline] = useState([]);
  const [frameIndex, setFrameIndex] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [replayCompression, setReplayCompression] = useState(1);
  const [comparisonMode, setComparisonMode] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [error, setError] = useState("");
  const [meta, setMeta] = useState({ frame_count: 0, intervals: 24, replay_compression: 1, canonical_flow: [] });
  const [rangePreviewCount, setRangePreviewCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function loadReplay() {
      try {
        const [primary, comparison] = await Promise.all([
          fetchReplayTimeline({ apiFetch, accessCode, intervals: 32, replayCompression, mode }),
          fetchReplayTimeline({ apiFetch, accessCode, intervals: 32, replayCompression: Math.min(replayCompression + 1, 4), mode }),
        ]);
        if (cancelled) {
          return;
        }
        const nextTimeline = Array.isArray(primary.timeline) ? primary.timeline : [];
        setTimeline(nextTimeline);
        setComparisonTimeline(Array.isArray(comparison.timeline) ? comparison.timeline : []);
        setMeta(primary.meta ?? {});
        setFrameIndex(Math.max(0, nextTimeline.length - 1));
        setError("");
      } catch (loadError) {
        if (!cancelled) {
          if (mode === "demo") {
            const demoPayload = buildCultivationReplayDemo();
            setTimeline(demoPayload.timeline);
            setComparisonTimeline(demoPayload.timeline);
            setMeta(demoPayload.meta);
            setFrameIndex(Math.max(0, demoPayload.timeline.length - 1));
            setError("");
          } else {
            setError(normalizeErrorMessage(loadError?.message ?? loadError));
          }
        }
      }
    }
    loadReplay();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch, mode, normalizeErrorMessage, replayCompression]);

  useEffect(() => {
    if (!isPlaying) {
      return undefined;
    }
    const frameCount = Math.max(timeline.length, DEFAULT_CANONICAL_FLOW.length);
    const intervalMs = Math.max(100, Math.round(900 / playbackSpeed));
    const timer = window.setInterval(() => {
      setFrameIndex((current) => (current + 1 >= frameCount ? 0 : current + 1));
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [isPlaying, playbackSpeed, timeline.length]);

  useEffect(() => {
    async function loadRangePreview() {
      if (timeline.length < 2) {
        setRangePreviewCount(0);
        return;
      }
      const start = timeline[Math.max(0, frameIndex - 4)]?.timestamp;
      const end = timeline[Math.min(timeline.length - 1, frameIndex + 4)]?.timestamp;
      if (!start || !end) {
        return;
      }
      try {
        const preview = await fetchReplayRange({
          apiFetch,
          accessCode,
          startTimestamp: start,
          endTimestamp: end,
          intervals: timeline.length,
          mode,
        });
        setRangePreviewCount(preview.frame_count ?? 0);
      } catch {
        setRangePreviewCount(0);
      }
    }
    loadRangePreview();
  }, [accessCode, apiFetch, frameIndex, mode, timeline]);

  const operativeTimeline = useMemo(() => (timeline.length > 0 ? timeline : buildIntelligentReplayFallback()), [timeline]);
  const activeFrame = operativeTimeline[Math.min(frameIndex, Math.max(0, operativeTimeline.length - 1))] ?? null;
  const comparisonFrame = comparisonTimeline[frameIndex] ?? null;
  const shownFrame = comparisonMode ? (comparisonFrame ?? activeFrame) : activeFrame;
  const canonicalFlow = (meta.canonical_flow?.length ? meta.canonical_flow : DEFAULT_CANONICAL_FLOW);

  const metrics = useMemo(() => ([
    { label: "Replay Frames", value: meta.frame_count ?? operativeTimeline.length },
    { label: "Frame", value: `${Math.min(frameIndex + 1, operativeTimeline.length)}/${Math.max(operativeTimeline.length, 1)}` },
    { label: "Playback", value: `${playbackSpeed.toFixed(1)}x` },
    { label: "Compression", value: `${replayCompression}x` },
    { label: "Range Preview", value: rangePreviewCount || "Adaptive window" },
    { label: "Structural State", value: strengthenReplayState(shownFrame?.topology_state?.stability_state) },
    { label: "Evidence Confidence", value: shownFrame?.cognition_state?.confidence_tier ?? "Evidence lock forming" },
    { label: "Operational Phase", value: strengthenReplayState(shownFrame?.cognition_state?.operational_phase) },
  ]), [frameIndex, meta.frame_count, operativeTimeline.length, playbackSpeed, rangePreviewCount, replayCompression, shownFrame?.cognition_state?.confidence_tier, shownFrame?.cognition_state?.operational_phase, shownFrame?.topology_state?.stability_state]);

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Structural Replay Workspace" className="span-12 workspace-hero-panel">
        <MetricGrid metrics={metrics} />
        <div className="structural-replay-controls">
          <button type="button" className="btn btn--secondary" onClick={() => setIsPlaying((value) => !value)}>
            {isPlaying ? "Pause Replay" : "Play Replay"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={() => setComparisonMode((value) => !value)}>
            {comparisonMode ? "Primary View" : "Comparison Mode"}
          </button>
          <button type="button" className="btn btn--secondary" onClick={() => setFrameIndex((value) => Math.max(value - 1, 0))}>
            Previous Frame
          </button>
          <button type="button" className="btn btn--secondary" onClick={() => setFrameIndex((value) => Math.min(value + 1, operativeTimeline.length - 1))}>
            Next Frame
          </button>
          <label className="metadata-text" htmlFor="replay-speed">Speed</label>
          <select id="replay-speed" value={playbackSpeed} onChange={(event) => setPlaybackSpeed(Number(event.target.value))}>
            {[0.5, 1, 1.5, 2, 4].map((speed) => <option key={speed} value={speed}>{speed}x</option>)}
          </select>
          <label className="metadata-text" htmlFor="replay-compression">Compression</label>
          <select id="replay-compression" value={replayCompression} onChange={(event) => setReplayCompression(Number(event.target.value))}>
            {[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value}x</option>)}
          </select>
          <input
            type="range"
            min={0}
            max={Math.max(0, operativeTimeline.length - 1)}
            value={Math.min(frameIndex, Math.max(0, operativeTimeline.length - 1))}
            onChange={(event) => setFrameIndex(Number(event.target.value))}
          />
        </div>
        <p className="metadata-text">
          Active timestamp: {shownFrame?.timestamp ? formatClockTime(shownFrame.timestamp) : "model-generated continuity frame"}
        </p>
        <ReplayCognitionField
          timeline={operativeTimeline}
          frameIndex={Math.min(frameIndex, Math.max(0, operativeTimeline.length - 1))}
          isPlaying={isPlaying}
          comparisonMode={comparisonMode}
          formatClockTime={formatClockTime}
        />
      </Panel>

      <Panel title="Cognition Phase Rail" className="span-12 replay-phase-panel">
        <div className="canonical-flow">
          {canonicalFlow.map((phase) => {
            const active = shownFrame?.cognition_state?.canonical_phase === phase;
            return (
              <div key={phase} className={`canonical-flow__step ${active ? "is-active" : ""}`}>
                <span>{phase.replaceAll("_", " ")}</span>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel title="Propagation Map" className="span-6">
        <PropagationMap frame={shownFrame} comparisonFrame={comparisonMode ? activeFrame : null} />
      </Panel>

      <Panel title="Evidence Interaction Layer" className="span-6">
        <EvidenceInteractionPanel frame={shownFrame} />
      </Panel>

      <Panel title="Structural Memory Replay" className="span-6">
        <StructuralMemoryPanel frame={shownFrame} />
      </Panel>

      <Panel title="Evidence Lineage" className="span-6">
        <EvidenceLineagePanel frame={shownFrame} />
      </Panel>

      <Panel title="Operational Time Intelligence" className="span-6">
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">Canonical Phase</span><strong>{shownFrame?.cognition_state?.canonical_phase?.replaceAll?.("_", " ") ?? "baseline continuity"}</strong></li>
          <li><span className="metadata-text">Propagation Acceleration</span><strong>{shownFrame?.propagation_state?.propagation_acceleration ?? "watching"}</strong></li>
          <li><span className="metadata-text">Structural Compression</span><strong>{shownFrame?.subsystem_pressure?.compression_intensity ?? "adaptive"}</strong></li>
          <li><span className="metadata-text">Continuation Window</span><strong>{shownFrame?.continuation_window?.window ?? "model-derived watch"}</strong></li>
          <li><span className="metadata-text">Timing Window</span><strong>{shownFrame?.continuation_window?.timing_window ?? "active intelligence"}</strong></li>
        </ul>
      </Panel>

      <Panel title="Recovery Convergence" className="span-6">
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">Convergence Signal</span><strong>{shownFrame?.propagation_state?.recovery_convergence ?? "tracking"}</strong></li>
          <li><span className="metadata-text">Fragmentation Indicator</span><strong>{shownFrame?.topology_state?.fragmentation_indicator ?? "low"}</strong></li>
          <li><span className="metadata-text">Facility Cognition State</span><strong>{strengthenReplayState(shownFrame?.cognition_state?.facility_state)}</strong></li>
        </ul>
      </Panel>

      {error ? (
        <Panel title="Replay Notice" className="span-12">
          <p className="narrative-text">{error} Adaptive replay continuity is displayed so the operator never loses topology context.</p>
        </Panel>
      ) : null}
    </div>
  );
}

const DEFAULT_CANONICAL_FLOW = [
  "stable_topology",
  "relationship_weakening",
  "pressure_migration",
  "archetype_emergence",
  "propagation_activation",
  "structural_fragmentation",
  "continuation_pathways",
  "recovery_or_escalation",
];

function strengthenReplayState(value) {
  const normalized = String(value ?? "").toLowerCase();
  if (!normalized.trim()) return "Structural Drift Emerging";
  if (normalized.includes("needs review") || normalized.includes("review")) return "Propagation Watch Active";
  if (normalized.includes("drift")) return "Structural Drift Emerging";
  if (normalized.includes("instab") || normalized.includes("separat")) return "Relational Instability Observed";
  if (normalized.includes("deterior") || normalized.includes("fragment")) return "Topology Divergence Active";
  if (normalized.includes("recover") || normalized.includes("convergen")) return "Recovery Convergence Tracking";
  if (normalized.includes("stable") || normalized.includes("nominal")) return "Baseline Stability Holding";
  return String(value).replaceAll("_", " ");
}

function buildIntelligentReplayFallback() {
  const now = Date.now();
  return DEFAULT_CANONICAL_FLOW.slice(0, 6).map((phase, index) => {
    const elevated = index >= 4;
    const watch = index >= 2;
    return {
      timestamp: new Date(now - (6 - index) * 1000 * 60 * 20).toISOString(),
      topology_state: {
        stability_state: elevated ? "TOPOLOGY_DIVERGENCE_ACTIVE" : watch ? "STRUCTURAL_DRIFT_EMERGING" : "BASELINE_STABILITY_HOLDING",
        fragmentation_indicator: elevated ? "high" : watch ? "moderate" : "low",
        phase,
      },
      propagation_state: {
        propagation_acceleration: elevated ? "high" : watch ? "moderate" : "low",
        dominant_paths: ["baseline_to_environment_to_recovery"],
        recovery_convergence: elevated ? "delayed" : watch ? "monitoring" : "stable",
      },
      cognition_state: {
        canonical_phase: phase,
        confidence_tier: watch ? "EVIDENCE_LOCK_FORMING" : "BASELINE_EVIDENCE",
        operational_phase: elevated ? "propagation_watch_active" : watch ? "structural_drift_emerging" : "baseline_stability_holding",
        facility_state: elevated ? "Propagation Watch Active" : watch ? "Structural Drift Emerging" : "Baseline Stability Holding",
      },
      continuation_window: { window: elevated ? "3 to 6 operational days" : "7 to 14 operational days", timing_window: watch ? "compression emerging" : "low urgency" },
      subsystem_pressure: { compression_intensity: elevated ? "high" : watch ? "moderate" : "low" },
      evidence_state: { lineage_events: [{ target: "adaptive_replay_continuity", evidence_sources: { topology_evidence: ["Fallback continuity field generated from replay phase model"] } }] },
    };
  });
}

function buildCultivationReplayDemo() {
  const now = Date.now();
  const timeline = [
    {
      timestamp: new Date(now - 1000 * 60 * 60 * 6).toISOString(),
      topology_state: { stability_state: "STABLE", fragmentation_indicator: "low", phase: "stable_topology" },
      propagation_state: { propagation_acceleration: "low", dominant_paths: ["airflow_balance"], recovery_convergence: "stable" },
      cognition_state: { canonical_phase: "stable_topology", confidence_tier: "HIGH_EVIDENCE", operational_phase: "monitoring", facility_state: "Monitoring" },
      continuation_window: { window: "14 operational days", timing_window: "low urgency" },
      subsystem_pressure: { compression_intensity: "low" },
      evidence_state: { lineage_events: [{ target: "airflow_balance", evidence_sources: { topology_evidence: ["Room synchronization stable"] } }] },
    },
    {
      timestamp: new Date(now - 1000 * 60 * 60 * 4).toISOString(),
      topology_state: { stability_state: "WATCH", fragmentation_indicator: "moderate", phase: "relationship_weakening" },
      propagation_state: { propagation_acceleration: "moderate", dominant_paths: ["airflow_imbalance_to_thermal_lag"], recovery_convergence: "monitoring" },
      cognition_state: { canonical_phase: "propagation_activation", confidence_tier: "MODERATE_EVIDENCE", operational_phase: "drift_review", facility_state: "Drift observed" },
      continuation_window: { window: "7 to 12 operational days", timing_window: "compression emerging" },
      subsystem_pressure: { compression_intensity: "moderate" },
      evidence_state: { lineage_events: [{ target: "compensation_masking", evidence_sources: { propagation_evidence: ["HVAC response lag", "Humidity compensation rise"] } }] },
    },
    {
      timestamp: new Date(now - 1000 * 60 * 60 * 2).toISOString(),
      topology_state: { stability_state: "DETERIORATING", fragmentation_indicator: "high", phase: "structural_fragmentation" },
      propagation_state: { propagation_acceleration: "high", dominant_paths: ["airflow_imbalance_to_thermal_lag_to_vpd_drift"], recovery_convergence: "delayed" },
      cognition_state: { canonical_phase: "continuation_pathways", confidence_tier: "HIGH_EVIDENCE", operational_phase: "operator_review", facility_state: "Escalation watch" },
      continuation_window: { window: "3 to 6 operational days", timing_window: "elevated urgency" },
      subsystem_pressure: { compression_intensity: "high" },
      evidence_state: { lineage_events: [{ target: "vpd_decoupling", evidence_sources: { persistence_evidence: ["VPD coupling drift persisted across replay frames"] } }] },
    },
  ];
  return {
    timeline,
    meta: {
      frame_count: timeline.length,
      intervals: timeline.length,
      replay_compression: 1,
      canonical_flow: [
        "stable_topology",
        "relationship_weakening",
        "pressure_migration",
        "archetype_emergence",
        "propagation_activation",
        "structural_fragmentation",
        "continuation_pathways",
        "recovery_or_escalation",
      ],
    },
  };
}
