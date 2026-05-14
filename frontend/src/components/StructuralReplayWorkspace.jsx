import React, { useEffect, useMemo, useState } from "react";
import { fetchReplayRange, fetchReplayTimeline } from "../services/api/replayApi";
import PropagationMap from "./PropagationMap";
import StructuralMemoryPanel from "./StructuralMemoryPanel";
import EvidenceLineagePanel from "./EvidenceLineagePanel";
import EvidenceInteractionPanel from "./EvidenceInteractionPanel";

export default function StructuralReplayWorkspace({
  apiFetch,
  accessCode,
  normalizeErrorMessage,
  formatClockTime,
  Panel,
  MetricGrid,
  EmptyState,
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
          fetchReplayTimeline({ apiFetch, accessCode, intervals: 32, replayCompression }),
          fetchReplayTimeline({ apiFetch, accessCode, intervals: 32, replayCompression: Math.min(replayCompression + 1, 4) }),
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
          setError(normalizeErrorMessage(loadError?.message ?? loadError));
        }
      }
    }
    loadReplay();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch, normalizeErrorMessage, replayCompression]);

  useEffect(() => {
    if (!isPlaying || timeline.length === 0) {
      return undefined;
    }
    const intervalMs = Math.max(100, Math.round(900 / playbackSpeed));
    const timer = window.setInterval(() => {
      setFrameIndex((current) => (current + 1 >= timeline.length ? 0 : current + 1));
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
        });
        setRangePreviewCount(preview.frame_count ?? 0);
      } catch {
        setRangePreviewCount(0);
      }
    }
    loadRangePreview();
  }, [accessCode, apiFetch, frameIndex, timeline]);

  const activeFrame = timeline[frameIndex] ?? null;
  const comparisonFrame = comparisonTimeline[frameIndex] ?? null;
  const shownFrame = comparisonMode ? (comparisonFrame ?? activeFrame) : activeFrame;
  const canonicalFlow = meta.canonical_flow ?? [];

  const metrics = useMemo(() => ([
    { label: "Replay Frames", value: meta.frame_count ?? timeline.length },
    { label: "Frame", value: `${frameIndex + 1}/${Math.max(timeline.length, 1)}` },
    { label: "Playback", value: `${playbackSpeed.toFixed(1)}x` },
    { label: "Compression", value: `${replayCompression}x` },
    { label: "Range Preview", value: rangePreviewCount || "n/a" },
    { label: "Stability State", value: shownFrame?.topology_state?.stability_state ?? "Awaiting replay data" },
    { label: "Confidence Tier", value: shownFrame?.cognition_state?.confidence_tier ?? "Awaiting replay data" },
    { label: "Operational Phase", value: shownFrame?.cognition_state?.operational_phase ?? "Awaiting replay data" },
  ]), [frameIndex, meta.frame_count, playbackSpeed, rangePreviewCount, replayCompression, shownFrame?.cognition_state?.confidence_tier, shownFrame?.cognition_state?.operational_phase, shownFrame?.topology_state?.stability_state, timeline.length]);

  if (!shownFrame && !error) {
    return (
      <div className="workspace-grid workspace-grid--console">
        <Panel title="Structural Replay" className="span-12">
          <EmptyState title="Replay unavailable" body="Connect telemetry or upload facility data to initialize structural replay." />
        </Panel>
      </div>
    );
  }

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
          <button type="button" className="btn btn--secondary" onClick={() => setFrameIndex((value) => Math.min(value + 1, timeline.length - 1))}>
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
            max={Math.max(0, timeline.length - 1)}
            value={Math.min(frameIndex, Math.max(0, timeline.length - 1))}
            onChange={(event) => setFrameIndex(Number(event.target.value))}
          />
        </div>
        <p className="metadata-text">
          Active timestamp: {shownFrame?.timestamp ? formatClockTime(shownFrame.timestamp) : "n/a"}
        </p>
      </Panel>

      <Panel title="Canonical Cognition Flow" className="span-12">
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
          <li><span className="metadata-text">Canonical Phase</span><strong>{shownFrame?.cognition_state?.canonical_phase ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Propagation Acceleration</span><strong>{shownFrame?.propagation_state?.propagation_acceleration ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Compression</span><strong>{shownFrame?.subsystem_pressure?.compression_intensity ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Continuation Window</span><strong>{shownFrame?.continuation_window?.window ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Timing Window</span><strong>{shownFrame?.continuation_window?.timing_window ?? "n/a"}</strong></li>
        </ul>
      </Panel>

      <Panel title="Recovery Convergence" className="span-6">
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">Convergence Signal</span><strong>{shownFrame?.propagation_state?.recovery_convergence ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Fragmentation Indicator</span><strong>{shownFrame?.topology_state?.fragmentation_indicator ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Facility Cognition State</span><strong>{shownFrame?.cognition_state?.facility_state ?? "n/a"}</strong></li>
        </ul>
      </Panel>

      {error ? (
        <Panel title="Replay Notice" className="span-12">
          <p className="narrative-text">{error}</p>
        </Panel>
      ) : null}
    </div>
  );
}
