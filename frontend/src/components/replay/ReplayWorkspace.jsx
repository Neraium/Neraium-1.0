import React, { useEffect, useMemo, useState } from "react";
import { fetchReplayRange, fetchReplayTimeline } from "../../services/api/replayApi";
import PropagationMap from "../PropagationMap";
import StructuralMemoryPanel from "../StructuralMemoryPanel";
import EvidenceLineagePanel from "../EvidenceLineagePanel";
import EvidenceInteractionPanel from "../EvidenceInteractionPanel";
import ReplayCognitionField from "../ReplayCognitionField";

export default function ReplayWorkspace({
  apiFetch,
  accessCode,
  expertMode = false,
  normalizeErrorMessage,
  formatClockTime,
  Panel,
  MetricGrid,
  mode = "live",
  hasActiveSession = false,
  hasCurrentUploadResult = false,
  hasResumedSession = false,
  hasRealSiiOutput = false,
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
        if (cancelled) return;
        const nextTimeline = Array.isArray(primary.timeline) ? primary.timeline : [];
        setTimeline(nextTimeline);
        setComparisonTimeline(Array.isArray(comparison.timeline) ? comparison.timeline : []);
        setMeta(primary.meta ?? {});
        setFrameIndex(Math.max(0, nextTimeline.length - 1));
        setError("");
      } catch (loadError) {
        if (cancelled) return;
        setTimeline([]);
        setComparisonTimeline([]);
        setMeta({ frame_count: 0, intervals: 24, replay_compression: 1, canonical_flow: [] });
        setFrameIndex(0);
        setError(buildReplayNotice(loadError, normalizeErrorMessage));
      }
    }
    loadReplay();
    return () => { cancelled = true; };
  }, [accessCode, apiFetch, mode, normalizeErrorMessage, replayCompression]);

  useEffect(() => {
    if (!isPlaying) return undefined;
    if (timeline.length < 2) return undefined;
    const frameCount = timeline.length;
    const intervalMs = Math.max(100, Math.round(900 / playbackSpeed));
    const timer = window.setInterval(() => setFrameIndex((current) => (current + 1 >= frameCount ? 0 : current + 1)), intervalMs);
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
      if (!start || !end) return;
      try {
        const preview = await fetchReplayRange({ apiFetch, accessCode, startTimestamp: start, endTimestamp: end, intervals: timeline.length, mode });
        setRangePreviewCount(preview.frame_count ?? 0);
      } catch {
        setRangePreviewCount(0);
      }
    }
    loadRangePreview();
  }, [accessCode, apiFetch, frameIndex, mode, timeline]);

  const hasReplaySnapshots = timeline.length > 0;
  const dash = "—";
  const hasDiagnosticsEvidence = Boolean(hasRealSiiOutput || hasCurrentUploadResult || hasActiveSession || hasResumedSession || hasReplaySnapshots);
  const hasTopologyEvidence = Boolean(hasReplaySnapshots && timeline[0]?.topology_state);
  const operativeTimeline = timeline;
  const activeFrame = operativeTimeline[Math.min(frameIndex, Math.max(0, operativeTimeline.length - 1))] ?? null;
  const comparisonFrame = comparisonTimeline[frameIndex] ?? null;
  const shownFrame = comparisonMode ? (comparisonFrame ?? activeFrame) : activeFrame;
  const canonicalFlow = (meta.canonical_flow?.length ? meta.canonical_flow : DEFAULT_CANONICAL_FLOW);
  const metrics = useMemo(() => {
    if (!hasDiagnosticsEvidence) {
      return [
        { label: "Replay snapshots", value: dash },
        { label: "Current point", value: dash },
        { label: "Lead time", value: dash },
        { label: "Evidence confidence", value: dash },
        { label: "System stability", value: dash },
        { label: "Progression state", value: dash },
      ];
    }
    return [
      { label: "Replay snapshots", value: hasReplaySnapshots ? (meta.frame_count ?? operativeTimeline.length) : dash },
      { label: "Current point", value: hasReplaySnapshots ? `${Math.min(frameIndex + 1, operativeTimeline.length)}/${Math.max(operativeTimeline.length, 1)}` : dash },
      { label: "Playback", value: hasReplaySnapshots ? `${playbackSpeed.toFixed(1)}x` : dash },
      { label: "Lead time", value: hasReplaySnapshots ? (shownFrame?.continuation_window?.window ?? dash) : dash },
      { label: "Preview range", value: hasReplaySnapshots ? (rangePreviewCount || dash) : dash },
      { label: "System stability", value: hasTopologyEvidence ? strengthenReplayState(shownFrame?.topology_state?.stability_state) : dash },
      { label: "Evidence confidence", value: hasReplaySnapshots ? formatConfidenceLabel(shownFrame?.cognition_state?.confidence_tier) : dash },
      { label: "Progression state", value: hasReplaySnapshots ? strengthenReplayState(shownFrame?.cognition_state?.operational_phase) : dash },
    ];
  }, [frameIndex, hasDiagnosticsEvidence, hasReplaySnapshots, hasTopologyEvidence, meta.frame_count, operativeTimeline.length, playbackSpeed, rangePreviewCount, shownFrame?.cognition_state?.confidence_tier, shownFrame?.cognition_state?.operational_phase, shownFrame?.topology_state?.stability_state, shownFrame?.continuation_window?.window]);

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Infrastructure Diagnostics" className="span-12 workspace-hero-panel" subtitle="Technical replay, topology, and evidence overlays separated from the operator flow.">
        <MetricGrid metrics={metrics} />
        {expertMode ? (
          <div className="structural-replay-controls">
            <button type="button" className="btn btn--secondary" onClick={() => setIsPlaying((value) => !value)} disabled={!hasReplaySnapshots}>{isPlaying ? "Pause Replay" : "Play Replay"}</button>
            <button type="button" className="btn btn--secondary" onClick={() => setComparisonMode((value) => !value)} disabled={!hasReplaySnapshots}>{comparisonMode ? "Primary View" : "Comparison Mode"}</button>
            <button type="button" className="btn btn--secondary" onClick={() => setFrameIndex((value) => Math.max(value - 1, 0))} disabled={!hasReplaySnapshots}>Previous Frame</button>
            <button type="button" className="btn btn--secondary" onClick={() => setFrameIndex((value) => Math.min(value + 1, operativeTimeline.length - 1))} disabled={!hasReplaySnapshots}>Next Frame</button>
            <label className="metadata-text" htmlFor="replay-speed">Speed</label>
            <select id="replay-speed" value={playbackSpeed} onChange={(event) => setPlaybackSpeed(Number(event.target.value))} disabled={!hasReplaySnapshots}>{[0.5, 1, 1.5, 2, 4].map((speed) => <option key={speed} value={speed}>{speed}x</option>)}</select>
            <label className="metadata-text" htmlFor="replay-compression">Compression</label>
            <select id="replay-compression" value={replayCompression} onChange={(event) => setReplayCompression(Number(event.target.value))}>{[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value}x</option>)}</select>
            <input type="range" min={0} max={Math.max(0, operativeTimeline.length - 1)} value={Math.min(frameIndex, Math.max(0, operativeTimeline.length - 1))} onChange={(event) => setFrameIndex(Number(event.target.value))} disabled={!hasReplaySnapshots} />
          </div>
        ) : (
          <div className="structural-replay-controls">
            <button type="button" className="btn btn--secondary" onClick={() => setFrameIndex((value) => Math.max(value - 1, 0))} disabled={!hasReplaySnapshots}>Previous</button>
            <button type="button" className="btn btn--secondary" onClick={() => setFrameIndex((value) => Math.min(value + 1, operativeTimeline.length - 1))} disabled={!hasReplaySnapshots}>Next</button>
            <button type="button" className="btn btn--secondary" onClick={() => setIsPlaying((value) => !value)} disabled={!hasReplaySnapshots}>{isPlaying ? "Pause" : "Play"}</button>
          </div>
        )}
        {!hasDiagnosticsEvidence ? (
          <p className="narrative-text">Diagnostics are unavailable until telemetry is uploaded or a historian stream is connected.</p>
        ) : null}
        <p className="metadata-text">Diagnostic timestamp: {shownFrame?.timestamp ? formatClockTime(shownFrame.timestamp) : dash}</p>
        <ReplayCognitionField timeline={operativeTimeline} frameIndex={Math.min(frameIndex, Math.max(0, operativeTimeline.length - 1))} isPlaying={isPlaying} comparisonMode={comparisonMode} formatClockTime={formatClockTime} inactive={!hasReplaySnapshots} />
      </Panel>
      {expertMode ? (
        <Panel title="State-Space Progression" className="span-12 replay-phase-panel">
          <div className="canonical-flow">
            {canonicalFlow.map((phase) => <div key={phase} className={`canonical-flow__step ${hasReplaySnapshots && shownFrame?.cognition_state?.canonical_phase === phase ? "is-active" : ""}`}><span>{phase.replaceAll("_", " ")}</span></div>)}
          </div>
        </Panel>
      ) : null}
      <Panel title="Topology Graph" className="span-6"><PropagationMap frame={shownFrame} comparisonFrame={comparisonMode ? activeFrame : null} /></Panel>
      <Panel title={expertMode ? "Evidence Diagnostics" : "Why Neraium Flagged This"} className="span-6">
        {expertMode ? <EvidenceInteractionPanel frame={shownFrame} /> : (
          <ul className="system-body-timeline-list">
            <li><span className="metadata-text">Evidence confidence</span><strong>{formatConfidenceLabel(shownFrame?.cognition_state?.confidence_tier)}</strong></li>
            <li><span className="metadata-text">System stability</span><strong>{strengthenReplayState(shownFrame?.topology_state?.stability_state)}</strong></li>
            <li><span className="metadata-text">Cross-system support</span><strong>{hasReplaySnapshots ? ((shownFrame?.propagation_state?.dominant_paths ?? []).length > 0 ? "Present" : dash) : dash}</strong></li>
          </ul>
        )}
      </Panel>
      <Panel title="Recovery Convergence" className="span-6">
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">Convergence Signal</span><strong>{hasReplaySnapshots ? (shownFrame?.propagation_state?.recovery_convergence ?? dash) : dash}</strong></li>
          <li><span className="metadata-text">Fragmentation Indicator</span><strong>{hasReplaySnapshots ? (shownFrame?.topology_state?.fragmentation_indicator ?? dash) : dash}</strong></li>
          <li><span className="metadata-text">Analysis state</span><strong>{hasReplaySnapshots ? strengthenReplayState(shownFrame?.cognition_state?.facility_state) : dash}</strong></li>
        </ul>
      </Panel>
      {expertMode ? (
        <>
          <Panel title="Historical Pattern Memory" className="span-6"><StructuralMemoryPanel frame={shownFrame} /></Panel>
          <Panel title="Evidence Lineage" className="span-6"><EvidenceLineagePanel frame={shownFrame} /></Panel>
          <Panel title="Operational Time Intelligence" className="span-6">
            <ul className="system-body-timeline-list">
              <li><span className="metadata-text">State-space phase</span><strong>{hasReplaySnapshots ? (shownFrame?.cognition_state?.canonical_phase?.replaceAll?.("_", " ") ?? dash) : dash}</strong></li>
              <li><span className="metadata-text">Propagation acceleration</span><strong>{hasReplaySnapshots ? (shownFrame?.propagation_state?.propagation_acceleration ?? dash) : dash}</strong></li>
              <li><span className="metadata-text">Structural compression</span><strong>{hasReplaySnapshots ? (shownFrame?.subsystem_pressure?.compression_intensity ?? dash) : dash}</strong></li>
              <li><span className="metadata-text">Continuation window</span><strong>{hasReplaySnapshots ? (shownFrame?.continuation_window?.window ?? dash) : dash}</strong></li>
              <li><span className="metadata-text">Timing window</span><strong>{hasReplaySnapshots ? (shownFrame?.continuation_window?.timing_window ?? dash) : dash}</strong></li>
            </ul>
          </Panel>
        </>
      ) : null}
      {error ? <Panel title="Replay Notice" className="span-12"><p className="narrative-text">{error}</p></Panel> : null}
    </div>
  );
}

const DEFAULT_CANONICAL_FLOW = ["stable_topology", "relationship_weakening", "pressure_migration", "archetype_emergence", "propagation_activation", "structural_fragmentation", "continuation_pathways", "recovery_or_escalation"];

function strengthenReplayState(value) {
  const normalized = String(value ?? "").toLowerCase();
  if (!normalized.trim()) return "—";
  if (normalized.includes("needs review") || normalized.includes("review")) return "Propagation Watch Active";
  if (normalized.includes("drift")) return "Structural Drift Emerging";
  if (normalized.includes("instab") || normalized.includes("separat")) return "Relational Instability Observed";
  if (normalized.includes("deterior") || normalized.includes("fragment")) return "Topology Divergence Active";
  if (normalized.includes("recover") || normalized.includes("convergen")) return "Recovery Convergence Tracking";
  if (normalized.includes("stable") || normalized.includes("nominal")) return "Baseline stability pending";
  return sentenceCase(String(value).replaceAll("_", " "));
}

function sentenceCase(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

function formatConfidenceLabel(value) {
  const normalized = String(value ?? "").toLowerCase();
  if (normalized.includes("structural_evidence_confirmed")) return "Structural evidence confirmed";
  if (normalized.includes("relationship_evidence_present")) return "Relationship evidence present";
  if (normalized.includes("baseline_reference_confirmed") || normalized.includes("baseline_evidence")) return "Baseline reference confirmed";
  if (!normalized.trim()) return "Baseline reference pending";
  return sentenceCase(String(value).replaceAll("_", " "));
}

function buildReplayNotice(error, normalizeErrorMessage) {
  const message = String(normalizeErrorMessage(error?.message ?? error) ?? "");
  const lower = message.toLowerCase();
  if (lower.includes("404") || lower.includes("unexpected response")) {
    return "No replay snapshots are available for this session.";
  }
  if (lower.includes("network") || lower.includes("failed to fetch")) {
    return "Replay data will appear after telemetry processing completes.";
  }
  return "No replay snapshots are available for this session.";
}
