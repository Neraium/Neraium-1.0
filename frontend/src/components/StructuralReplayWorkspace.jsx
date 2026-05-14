import React, { useEffect, useMemo, useState } from "react";
import { fetchReplayFrame, fetchReplayRange, fetchReplayTimeline } from "../services/api/replayApi";
import PropagationMap from "./PropagationMap";
import StructuralMemoryPanel from "./StructuralMemoryPanel";
import EvidenceLineagePanel from "./EvidenceLineagePanel";

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
  const [frameIndex, setFrameIndex] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [error, setError] = useState("");
  const [meta, setMeta] = useState({ frame_count: 0, intervals: 24, replay_compression: 1 });
  const [rangePreviewCount, setRangePreviewCount] = useState(0);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const payload = await fetchReplayTimeline({
          apiFetch,
          accessCode,
          intervals: 28,
          replayCompression: 1,
        });
        if (cancelled) {
          return;
        }
        const nextTimeline = Array.isArray(payload.timeline) ? payload.timeline : [];
        setTimeline(nextTimeline);
        setMeta(payload.meta ?? {});
        setFrameIndex(Math.max(0, nextTimeline.length - 1));
        setError("");
      } catch (loadError) {
        if (!cancelled) {
          setError(normalizeErrorMessage(loadError?.message ?? loadError));
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [accessCode, apiFetch, normalizeErrorMessage]);

  useEffect(() => {
    if (!isPlaying || timeline.length === 0) {
      return undefined;
    }
    const stepMs = Math.max(100, Math.round(900 / playbackSpeed));
    const timer = window.setInterval(() => {
      setFrameIndex((current) => (current + 1 >= timeline.length ? 0 : current + 1));
    }, stepMs);
    return () => window.clearInterval(timer);
  }, [isPlaying, playbackSpeed, timeline.length]);

  useEffect(() => {
    async function loadRangePreview() {
      if (timeline.length < 2) {
        setRangePreviewCount(0);
        return;
      }
      const start = timeline[Math.max(0, frameIndex - 3)]?.timestamp;
      const end = timeline[Math.min(timeline.length - 1, frameIndex + 3)]?.timestamp;
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

  useEffect(() => {
    async function verifyFrame() {
      if (!activeFrame?.timestamp) {
        return;
      }
      try {
        await fetchReplayFrame({
          apiFetch,
          accessCode,
          timestamp: activeFrame.timestamp,
          intervals: timeline.length || 24,
        });
      } catch {
        // Frame verification is best-effort; UI already has timeline data.
      }
    }
    verifyFrame();
  }, [accessCode, activeFrame?.timestamp, apiFetch, timeline.length]);

  const metrics = useMemo(() => ([
    { label: "Replay Frames", value: meta.frame_count ?? timeline.length },
    { label: "Frame Index", value: `${frameIndex + 1}/${Math.max(timeline.length, 1)}` },
    { label: "Playback", value: `${playbackSpeed.toFixed(1)}x` },
    { label: "Range Preview", value: rangePreviewCount || "n/a" },
    { label: "Cognition State", value: activeFrame?.cognition_state?.facility_state ?? "Awaiting replay data" },
    { label: "Confidence Tier", value: activeFrame?.cognition_state?.confidence_tier ?? "Awaiting replay data" },
  ]), [activeFrame?.cognition_state?.confidence_tier, activeFrame?.cognition_state?.facility_state, frameIndex, meta.frame_count, playbackSpeed, rangePreviewCount, timeline.length]);

  if (!activeFrame && !error) {
    return (
      <div className="workspace-grid workspace-grid--console">
        <Panel title="Structural Replay" className="span-12">
          <EmptyState title="Replay unavailable" body="Upload telemetry or connect a live source to initialize structural replay." />
        </Panel>
      </div>
    );
  }

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Structural Replay Controls" className="span-12 workspace-hero-panel">
        <MetricGrid metrics={metrics} />
        <div className="structural-replay-controls">
          <button type="button" className="btn btn--secondary" onClick={() => setIsPlaying((value) => !value)}>
            {isPlaying ? "Pause Replay" : "Play Replay"}
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
          <input
            type="range"
            min={0}
            max={Math.max(0, timeline.length - 1)}
            value={Math.min(frameIndex, Math.max(0, timeline.length - 1))}
            onChange={(event) => setFrameIndex(Number(event.target.value))}
          />
        </div>
        <p className="metadata-text">
          Active frame timestamp: {activeFrame?.timestamp ? formatClockTime(activeFrame.timestamp) : "n/a"}
        </p>
      </Panel>

      <Panel title="Propagation Visualization" className="span-6">
        <PropagationMap frame={activeFrame} />
      </Panel>

      <Panel title="Structural Memory Replay" className="span-6">
        <StructuralMemoryPanel frame={activeFrame} />
      </Panel>

      <Panel title="Evidence Lineage" className="span-6">
        <EvidenceLineagePanel frame={activeFrame} />
      </Panel>

      <Panel title="Cognition Timeline" className="span-6">
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">Topology phase</span><strong>{activeFrame?.topology_state?.phase ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Drift index</span><strong>{activeFrame?.topology_state?.drift_index ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Fragmentation indicator</span><strong>{activeFrame?.topology_state?.fragmentation_indicator ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Continuation window</span><strong>{activeFrame?.continuation_window?.window ?? "n/a"}</strong></li>
          <li><span className="metadata-text">Scenario</span><strong>{activeFrame?.continuation_window?.active_scenario ?? "n/a"}</strong></li>
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
