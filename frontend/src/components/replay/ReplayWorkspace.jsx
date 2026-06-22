import React, { useEffect, useMemo, useRef, useState } from "react";
import PropagationMap from "../PropagationMap";
import StructuralMemoryPanel from "../StructuralMemoryPanel";
import EvidenceLineagePanel from "../EvidenceLineagePanel";
import EvidenceInteractionPanel from "../EvidenceInteractionPanel";
import ReplayCognitionField from "../ReplayCognitionField";
import { resolveSessionJobId } from "../../viewModels/currentSession";
import * as uploadStateView from "../../viewModels/uploadState";
import { buildPendingState, normalizeOperatorConfidenceLabel, sanitizeOperatorList, sanitizeOperatorText } from "../../viewModels/operatorFinding";

export default function ReplayWorkspace({
  apiFetch,
  accessCode,
  expertMode = false,
  normalizeErrorMessage,
  formatClockTime,
  Panel,
  MetricGrid,
  mode = "live",
  domainMode = null,
  hasActiveSession = false,
  hasCurrentUploadResult = false,
  hasResumedSession = false,
  hasRealSiiOutput = false,
  currentSession = null,
  canonicalFinding = null,
  onReplayFrameChange,
  onReplayModeChange,
}) {
  const [timeline, setTimeline] = useState([]);
  const [comparisonTimeline, setComparisonTimeline] = useState([]);
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [replayCompression, setReplayCompression] = useState(1);
  const [executionMode, setExecutionMode] = useState(mode || "live");
  const [comparisonMode, setComparisonMode] = useState(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [error, setError] = useState("");
  const [evidenceRun, setEvidenceRun] = useState(null);
  const [meta, setMeta] = useState({ frame_count: 0, intervals: 24, replay_compression: 1, canonical_flow: [] });
  const [rangePreviewCount, setRangePreviewCount] = useState(0);
  const sessionJobId = useMemo(() => resolveSessionJobId(currentSession), [currentSession]);
  const replaySessionKeyRef = useRef(null);
  const shouldRequestReplay = Boolean(
    sessionJobId
    || hasActiveSession
    || hasCurrentUploadResult
    || hasResumedSession
    || hasRealSiiOutput
  );
  const [replayMode, setReplayMode] = useState(false);
  const replayFinding = canonicalFinding ?? {
    exists: false,
    status: "Normal",
    confidence: "Low",
    summary: "No current observations.",
    whyItMatters: "Telemetry is being monitored.",
    reviewNext: "No equipment issues detected.",
    supportingEvidence: [],
    emptyState: { detail: "No equipment issues detected." },
  };
  const reviewReady = currentSession?.hasReliableOperatorEvidence === true;
  const togglePlayback = () => {
    setIsPlaying((value) => {
      const next = !value;
      if (next) {
        setReplayMode(true);
      }
      return next;
    });
  };

  useEffect(() => {
    if (!shouldRequestReplay) {
      setTimeline([]);
      setComparisonTimeline([]);
      setMeta({ frame_count: 0, intervals: 24, replay_compression: 1, canonical_flow: [] });
      setCurrentFrameIndex(0);
      setIsPlaying(false);
      setError("");
      setEvidenceRun(null);
      replaySessionKeyRef.current = null;
      return () => {};
    }
    let cancelled = false;
    async function loadReplay() {
      try {
        const scoped = await fetchUploadScopedReplay({ apiFetch, accessCode, jobId: sessionJobId });
        const matchedEvidenceRun = scoped.jobId && reviewReady
          ? await fetchEvidenceRunForJob({ apiFetch, accessCode, jobId: scoped.jobId })
          : null;
        console.info("[neraium] evidence fetch status", {
          jobId: scoped.jobId ?? sessionJobId ?? null,
          replayFrames: Array.isArray(scoped.timeline) ? scoped.timeline.length : 0,
          evidenceReady: Boolean(matchedEvidenceRun),
        });
        if (cancelled) return;
        const nextTimeline = scoped.timeline;
        const nextMeta = {
          ...(scoped.meta ?? {}),
          replay_source: "upload_job",
          replay_job_id: scoped.jobId,
          message: scoped.message,
        };
        const effectiveTimeline = sortReplayTimeline(nextTimeline);
        const effectiveMeta = nextMeta;
        const replaySessionKey = String(scoped.jobId ?? sessionJobId ?? "global");
        const sessionChanged = replaySessionKeyRef.current !== replaySessionKey;

        setTimeline(effectiveTimeline);
        setComparisonTimeline([]);
        setMeta(effectiveMeta);
        setEvidenceRun(matchedEvidenceRun);
        setError(effectiveTimeline.length > 0 ? "" : (nextMeta?.message ?? "No replay is available for this session."));

        if (sessionChanged) {
          replaySessionKeyRef.current = replaySessionKey;
          setCurrentFrameIndex(0);
          setIsPlaying(false);
        } else {
          setCurrentFrameIndex((current) => Math.min(current, Math.max(0, effectiveTimeline.length - 1)));
        }
      } catch (loadError) {
        if (cancelled) return;
        console.warn("[neraium] evidence fetch status", { error: buildReplayNotice(loadError, normalizeErrorMessage) });
        setTimeline([]);
        setComparisonTimeline([]);
        setMeta({ frame_count: 0, intervals: 24, replay_compression: 1, canonical_flow: [] });
        setCurrentFrameIndex(0);
        setIsPlaying(false);
        setError(buildReplayNotice(loadError, normalizeErrorMessage));
        setEvidenceRun(null);
      }
    }
    loadReplay();
    return () => { cancelled = true; };
  }, [accessCode, apiFetch, normalizeErrorMessage, reviewReady, sessionJobId, shouldRequestReplay]);

  useEffect(() => {
    if (!isPlaying) return undefined;
    if (timeline.length < 2) return undefined;
    const lastFrameIndex = timeline.length - 1;
    const intervalMs = Math.max(100, Math.round(900 / playbackSpeed));
    const timer = window.setInterval(() => {
      setCurrentFrameIndex((current) => Math.min(current + 1, lastFrameIndex));
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [isPlaying, playbackSpeed, timeline.length]);

  useEffect(() => {
    if (!isPlaying) return;
    if (timeline.length === 0) return;
    if (currentFrameIndex >= timeline.length - 1) {
      setIsPlaying(false);
    }
  }, [currentFrameIndex, isPlaying, timeline.length]);

  useEffect(() => {
    if (!shouldRequestReplay) {
      setRangePreviewCount(0);
      return () => {};
    }
    function loadRangePreview() {
      if (timeline.length < 2) {
        setRangePreviewCount(0);
        return;
      }
      const start = timeline[Math.max(0, currentFrameIndex - 4)]?.timestamp;
      const end = timeline[Math.min(timeline.length - 1, currentFrameIndex + 4)]?.timestamp;
      if (!start || !end) return;
      const localFrames = timeline.filter((frame) => {
        const frameTimestamp = String(frame?.timestamp ?? "");
        return frameTimestamp >= start && frameTimestamp <= end;
      });
      setRangePreviewCount(localFrames.length);
    }
    loadRangePreview();
  }, [currentFrameIndex, timeline, shouldRequestReplay]);

  const hasReplaySnapshots = timeline.length > 0;
  const dash = "-";
  const replayPendingState = hasReplaySnapshots && !reviewReady
    ? buildPendingState(currentSession?.reviewReadiness)
    : null;
  const hasDiagnosticsEvidence = Boolean(hasRealSiiOutput || hasCurrentUploadResult || hasActiveSession || hasResumedSession || hasReplaySnapshots);
  const hasTopologyEvidence = Boolean(hasReplaySnapshots && timeline[0]?.topology_state);
  const operativeTimeline = timeline;
  const activeFrame = operativeTimeline[Math.min(currentFrameIndex, Math.max(0, operativeTimeline.length - 1))] ?? null;
  const comparisonFrame = comparisonTimeline[currentFrameIndex] ?? null;
  const shownFrame = comparisonMode ? (comparisonFrame ?? activeFrame) : activeFrame;
  const currentTimeLabel = shownFrame?.timestamp_end ?? shownFrame?.timestamp ?? dash;

  useEffect(() => {
    if (typeof onReplayFrameChange === "function") {
      onReplayFrameChange(hasReplaySnapshots ? shownFrame : null, {
        frameIndex: Math.min(currentFrameIndex, Math.max(0, operativeTimeline.length - 1)),
        totalFrames: operativeTimeline.length,
        isPlaying,
      });
    }
  }, [currentFrameIndex, hasReplaySnapshots, isPlaying, onReplayFrameChange, operativeTimeline.length, shownFrame]);

  useEffect(() => {
    if (!hasReplaySnapshots && replayMode) {
      setReplayMode(false);
    }
  }, [hasReplaySnapshots, replayMode]);

  useEffect(() => {
    if (typeof onReplayModeChange === "function") {
      onReplayModeChange(replayMode && hasReplaySnapshots);
    }
  }, [hasReplaySnapshots, onReplayModeChange, replayMode]);
  const canonicalFlow = (meta.canonical_flow?.length ? meta.canonical_flow : DEFAULT_CANONICAL_FLOW);
  const replayConfidence = replayPendingState ? "Pending" : replayFinding.confidence;
  const replayStatusMetrics = useMemo(() => ([
    { label: "Change strength", value: hasReplaySnapshots ? formatChangeStrength(shownFrame) : dash },
    { label: "Confidence", value: replayConfidence },
  ]), [hasReplaySnapshots, replayConfidence, shownFrame]);

  const expertMetrics = useMemo(() => {
    if (!hasDiagnosticsEvidence) {
      return [
        { label: "Structure Timeline", value: dash },
        { label: "Current Frame", value: dash },
        { label: "Raw change strength", value: dash },
        { label: "Raw change direction", value: dash },
        { label: "Raw change momentum", value: dash },
        { label: "Raw state", value: dash },
        { label: "Primary Contributors", value: dash },
        { label: "Confidence", value: dash },
      ];
    }
    const contributors = Array.isArray(shownFrame?.primary_contributors) && shownFrame.primary_contributors.length
      ? shownFrame.primary_contributors.slice(0, 2).join(" | ")
      : dash;
    return [
      { label: "Structure Timeline", value: hasReplaySnapshots ? (meta.frame_count ?? operativeTimeline.length) : dash },
      { label: "Current Frame", value: hasReplaySnapshots ? `${Math.min(currentFrameIndex + 1, operativeTimeline.length)}/${Math.max(operativeTimeline.length, 1)}` : dash },
      { label: "Raw change strength", value: hasReplaySnapshots ? (shownFrame?.baseline_distance ?? shownFrame?.topology_state?.drift_index ?? dash) : dash },
      { label: "Raw change direction", value: hasReplaySnapshots ? (shownFrame?.drift_velocity ?? shownFrame?.subsystem_pressure?.volatility_index ?? dash) : dash },
      { label: "Raw change momentum", value: hasReplaySnapshots ? (shownFrame?.drift_acceleration ?? shownFrame?.propagation_state?.propagation_acceleration ?? dash) : dash },
      { label: "Raw state", value: hasTopologyEvidence ? strengthenReplayState(shownFrame?.topology_state?.stability_state) : dash },
      { label: "Primary Contributors", value: contributors },
      { label: "Playback", value: hasReplaySnapshots ? `${playbackSpeed.toFixed(1)}x` : dash },
      { label: "Lead time", value: hasReplaySnapshots ? (shownFrame?.continuation_window?.window ?? dash) : dash },
      { label: "Preview range", value: hasReplaySnapshots ? (rangePreviewCount || dash) : dash },
      { label: "Confidence", value: hasReplaySnapshots ? formatConfidenceLabel(shownFrame?.cognition_state?.confidence_tier) : dash },
    ];
  }, [currentFrameIndex, hasDiagnosticsEvidence, hasReplaySnapshots, hasTopologyEvidence, meta.frame_count, operativeTimeline.length, playbackSpeed, rangePreviewCount, shownFrame?.baseline_distance, shownFrame?.drift_velocity, shownFrame?.drift_acceleration, shownFrame?.primary_contributors, shownFrame?.cognition_state?.confidence_tier, shownFrame?.topology_state?.drift_index, shownFrame?.topology_state?.stability_state, shownFrame?.continuation_window?.window, shownFrame?.propagation_state?.propagation_acceleration, shownFrame?.subsystem_pressure?.volatility_index]);

  const discovery = useMemo(() => buildReplayDiscovery({
    timeline: operativeTimeline,
    frame: shownFrame,
    frameIndex: currentFrameIndex,
    formatClockTime,
  }), [currentFrameIndex, formatClockTime, operativeTimeline, shownFrame]);
  const replayStatusLabel = replayFinding.exists
    ? replayFinding.status
    : replayPendingState
      ? replayPendingState.title
      : (hasReplaySnapshots ? discovery.headline : "No replay available yet");
  const replaySummary = replayFinding.exists
    ? replayFinding.summary
    : replayPendingState
      ? replayPendingState.subtitle
      : (hasReplaySnapshots ? discovery.summary : "Upload data to create an evidence replay.");
  const replayReviewNext = replayFinding.exists
    ? replayFinding.reviewNext
    : replayPendingState
      ? replayPendingState.detail
      : "Telemetry replay unavailable";
  const replayReviewContext = replayFinding.exists
    ? replayFinding.whyItMatters
    : replayPendingState
      ? replayPendingState.subtitle
      : (hasReplaySnapshots ? discovery.reviewNext.detail : "No replay available yet.");
  const supportingEvidence = useMemo(() => {
    if (replayPendingState) {
      return sanitizeOperatorList([replayPendingState.subtitle]);
    }
    const evidenceJobId = sessionJobId ?? meta.replay_job_id ?? null;
    const replayLineage = meta.lineage && typeof meta.lineage === "object" ? meta.lineage : {};
    const uploadJobId = sessionJobId ?? null;
    const alignmentOk = Boolean(
      replayLineage.aligned
      && evidenceJobId
      && String(replayLineage.job_id ?? "") === String(evidenceJobId)
      && (!uploadJobId || String(uploadJobId) === String(evidenceJobId))
    );
    if (!reviewReady || !evidenceRun || String(evidenceRun.run_id ?? "") !== String(evidenceJobId ?? "") || !alignmentOk) {
      return [];
    }
    return buildSupportingEvidence({
      evidenceRun,
      uploadResult: currentSession?.latestUploadResult,
      frame: shownFrame,
      frameIndex: currentFrameIndex,
      frameCount: operativeTimeline.length,
      formatClockTime,
      lineage: replayLineage,
    });
  }, [currentFrameIndex, currentSession?.latestUploadResult, evidenceRun, formatClockTime, meta.lineage, meta.replay_job_id, operativeTimeline.length, replayPendingState, reviewReady, sessionJobId, shownFrame]);

  return (
    <div className="workspace-grid workspace-grid--console">
      <Panel title="Evidence Replay" className="span-12 workspace-hero-panel replay-discovery" subtitle="See what changed, why it matters, and what to review next.">
        <div className="replay-discovery__header">
          <div>
            <p className="section-token">Evidence</p>
            <h3>{replayStatusLabel}</h3>
            <p className="narrative-text">{replaySummary}</p>
          </div>
          <MetricGrid metrics={replayStatusMetrics} compact />
        </div>

        <div className="replay-discovery__sequence" aria-label="Evidence replay discovery sequence">
          <DiscoveryCard label="Before" item={discovery.before} active={hasReplaySnapshots && currentFrameIndex === 0} />
          <DiscoveryCard label="Behavior Change" item={discovery.current} active={hasReplaySnapshots} emphasized />
          <DiscoveryCard label="After" item={discovery.after} active={hasReplaySnapshots && currentFrameIndex === operativeTimeline.length - 1} />
        </div>

        <div className="replay-discovery__insight-grid">
          <section className="replay-discovery__insight" aria-label="What changed">
            <span className="section-token">Current Status</span>
            <strong>{replayStatusLabel}</strong>
            <p>{replaySummary}</p>
          </section>
          <section className="replay-discovery__insight" aria-label="Supporting evidence">
            <span className="section-token">Supporting Evidence</span>
            <ul className="compact-list">
              {sanitizeOperatorList(replayFinding.supportingEvidence.length > 0 ? replayFinding.supportingEvidence : supportingEvidence).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>
          <section className="replay-discovery__insight" aria-label="Next operator review">
            <span className="section-token">Review next</span>
            <strong>{replayReviewNext}</strong>
            <p>{replayReviewContext}</p>
          </section>
        </div>

        <div className="replay-discovery__controls" aria-label="Timeline replay controls">
          <div className="structural-replay-controls">
            <select value={executionMode} onChange={(event) => setExecutionMode(String(event.target.value))}>
              <option value="live">Evidence replay</option>
              <option value="live_causal">Evidence replay, no lookahead</option>
            </select>
            <button type="button" className="btn btn--secondary" onClick={() => setCurrentFrameIndex((value) => Math.max(value - 1, 0))} disabled={!hasReplaySnapshots}>{expertMode ? "Previous Frame" : "Previous"}</button>
            <button type="button" className="btn btn--secondary" onClick={() => setCurrentFrameIndex((value) => Math.min(value + 1, operativeTimeline.length - 1))} disabled={!hasReplaySnapshots}>{expertMode ? "Next Frame" : "Next"}</button>
            <button type="button" className="btn btn--secondary" onClick={togglePlayback} disabled={!hasReplaySnapshots}>{isPlaying ? "Pause" : "Play"}</button>
            <button type="button" className="btn btn--secondary" onClick={() => setCurrentFrameIndex(0)} disabled={!hasReplaySnapshots}>Start Over</button>
            <select value={playbackSpeed} onChange={(event) => setPlaybackSpeed(Number(event.target.value))} disabled={!hasReplaySnapshots}>{[0.5, 1, 1.5, 2, 4].map((speed) => <option key={speed} value={speed}>{speed}x</option>)}</select>
            {expertMode ? (
              <>
                <button type="button" className="btn btn--secondary" onClick={() => setComparisonMode((value) => !value)} disabled={!hasReplaySnapshots}>{comparisonMode ? "Primary View" : "Comparison Mode"}</button>
                <label className="metadata-text" htmlFor="replay-compression">Compression</label>
                <select id="replay-compression" value={replayCompression} onChange={(event) => setReplayCompression(Number(event.target.value))}>{[1, 2, 3, 4].map((value) => <option key={value} value={value}>{value}x</option>)}</select>
              </>
            ) : null}
            <button type="button" className="btn btn--secondary" onClick={() => setReplayMode((value) => !value)} disabled={!hasReplaySnapshots}>{replayMode ? "Exit Review Mode" : "Open in System Status"}</button>
            <input type="range" min={0} max={Math.max(0, operativeTimeline.length - 1)} value={Math.min(currentFrameIndex, Math.max(0, operativeTimeline.length - 1))} onChange={(event) => setCurrentFrameIndex(Number(event.target.value))} disabled={!hasReplaySnapshots} />
          </div>
        </div>

        {hasReplaySnapshots ? (
          <div className={["historian-replay-status", replayMode ? "historian-replay-status--active" : ""].filter(Boolean).join(" ")}>
            <span className="historian-replay-status__badge">{replayPendingState ? "Replay generated, review pending" : (replayMode ? "System Status review active" : "Replay ready")}</span>
            <span>{"Frame " + Math.min(currentFrameIndex + 1, Math.max(1, operativeTimeline.length)) + "/" + Math.max(1, operativeTimeline.length)}</span>
            <span>{formatClockTime(currentTimeLabel)}</span>
          </div>
        ) : (
          <p className="narrative-text">No replay yet. Upload data to create one.</p>
        )}
        <ReplayCognitionField timeline={operativeTimeline} frameIndex={Math.min(currentFrameIndex, Math.max(0, operativeTimeline.length - 1))} isPlaying={isPlaying} comparisonMode={comparisonMode} formatClockTime={formatClockTime} inactive={!hasReplaySnapshots} />
      </Panel>
      {expertMode ? (
        <Panel title="Structural Progression" className="span-12 replay-phase-panel">
          <div className="canonical-flow">
            {canonicalFlow.map((phase) => <div key={phase} className={["canonical-flow__step", hasReplaySnapshots && shownFrame?.cognition_state?.canonical_phase === phase ? "is-active" : ""].filter(Boolean).join(" ")}><span>{phase.replaceAll("_", " ")}</span></div>)}
          </div>
          <MetricGrid metrics={expertMetrics} compact />
        </Panel>
      ) : null}
      {expertMode ? (
        <>
          <Panel title="What Changed" className="span-6"><PropagationMap frame={shownFrame} comparisonFrame={comparisonMode ? activeFrame : null} /></Panel>
          <Panel title="Evidence Details" className="span-6"><EvidenceInteractionPanel frame={shownFrame} /></Panel>
          <Panel title="Why It Matters" className="span-6">
            <ul className="system-body-timeline-list">
              <li><span className="metadata-text">Recovery</span><strong>{hasReplaySnapshots ? simplifyRecoverySignal(shownFrame?.propagation_state?.recovery_convergence) : dash}</strong></li>
              <li><span className="metadata-text">Relationship continuity</span><strong>{hasReplaySnapshots ? formatRelationshipContinuity(shownFrame) : dash}</strong></li>
              <li><span className="metadata-text">Review state</span><strong>{hasReplaySnapshots ? strengthenReplayState(shownFrame?.cognition_state?.facility_state) : dash}</strong></li>
            </ul>
          </Panel>
        </>
      ) : null}
      {expertMode ? (
        <>
          <Panel title="Historical Structure Memory" className="span-6"><StructuralMemoryPanel frame={shownFrame} /></Panel>
          <Panel title="Evidence Details" className="span-6"><EvidenceLineagePanel frame={shownFrame} /></Panel>
          <Panel title="Temporal Structure" className="span-6">
            <ul className="system-body-timeline-list">
              <li><span className="metadata-text">State phase</span><strong>{hasReplaySnapshots ? (shownFrame?.cognition_state?.canonical_phase?.replaceAll?.("_", " ") ?? dash) : dash}</strong></li>
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

function DiscoveryCard({ label, item, active = false, emphasized = false }) {
  return (
    <section className={["replay-discovery-card", active ? "is-active" : "", emphasized ? "is-emphasized" : ""].filter(Boolean).join(" ")}>
      <span>{label}</span>
      <strong>{item.title}</strong>
      <p>{item.detail}</p>
      <em>{item.time}</em>
    </section>
  );
}


async function fetchUploadScopedReplay({ apiFetch, accessCode, jobId = null }) {
  let targetJobId = jobId;
  if (!targetJobId) {
    const latestResponse = await apiFetch("/api/data/latest-upload?include_persisted=1", { accessCode });
    if (!latestResponse.ok) {
      throw new Error(`Unexpected response: ${latestResponse.status}`);
    }
    const latestPayload = await latestResponse.json();
    const currentUpload = latestPayload?.current_upload ?? latestPayload?.snapshot?.current_upload ?? null;
    targetJobId = uploadStateView.resolveCurrentUploadJobId(latestPayload) ?? currentUpload?.job_id ?? null;
    if (!targetJobId) {
      return { jobId: null, timeline: [], meta: {}, message: "No replay is available for the active session." };
    }
  }
  const statusResponse = await apiFetch(`/api/data/upload-status/${encodeURIComponent(targetJobId)}`, { accessCode });
  let pendingReplayMessage = "";
  if (statusResponse.ok) {
    const statusPayload = await statusResponse.json();
    const status = String(statusPayload?.status ?? "").toUpperCase();
    const replayReady = Boolean(statusPayload?.replay_ready) || Number(statusPayload?.replay_frame_count ?? 0) > 0;
    const resultAvailable = Boolean(statusPayload?.result_available);
    const terminalOrFetchable = ["COMPLETE", "FAILED", "ACTIVE"].includes(status) || replayReady || resultAvailable;
    if (status && !terminalOrFetchable) {
      pendingReplayMessage = `Replay is still building for this upload job (${status.toLowerCase()}).`;
    }
  }
  const replayResponse = await apiFetch(`/api/data/replay/${encodeURIComponent(targetJobId)}?mode=${encodeURIComponent("live")}&replay_compression=${encodeURIComponent(String(1))}`, { accessCode });
  if (!replayResponse.ok) {
    throw new Error(`Unexpected response: ${replayResponse.status}`);
  }
  const replayPayload = await replayResponse.json();
  const timeline = Array.isArray(replayPayload?.timeline) ? replayPayload.timeline : [];
  const meta = replayPayload?.meta && typeof replayPayload.meta === "object" ? replayPayload.meta : {};
  return {
    jobId: targetJobId,
    timeline,
    meta: timeline.length ? meta : { ...meta, replay_pending: Boolean(pendingReplayMessage) },
    message: timeline.length
      ? (typeof replayPayload?.message === "string" ? replayPayload.message : "")
      : (pendingReplayMessage || (typeof replayPayload?.message === "string" ? replayPayload.message : "")),
  };
}

async function fetchEvidenceRunForJob({ apiFetch, accessCode, jobId }) {
  const response = await apiFetch("/api/evidence/runs", { accessCode });
  if (!response.ok) return null;
  const payload = await response.json();
  const runs = Array.isArray(payload?.runs) ? payload.runs : [];
  return runs.find((run) => (
    String(run?.run_id ?? "") === String(jobId)
    && String(run?.status ?? "").toLowerCase() === "completed"
  )) ?? null;
}

function sortReplayTimeline(frames) {
  if (!Array.isArray(frames) || frames.length === 0) return [];
  return frames
    .map((frame, originalIndex) => ({ frame, originalIndex }))
    .sort((a, b) => {
      const aFrameNumber = readFrameNumber(a.frame);
      const bFrameNumber = readFrameNumber(b.frame);
      if (aFrameNumber !== null && bFrameNumber !== null && aFrameNumber !== bFrameNumber) {
        return aFrameNumber - bFrameNumber;
      }
      const aTimestamp = readFrameTimestamp(a.frame);
      const bTimestamp = readFrameTimestamp(b.frame);
      if (aTimestamp !== null && bTimestamp !== null && aTimestamp !== bTimestamp) {
        return aTimestamp < bTimestamp ? -1 : 1;
      }
      return a.originalIndex - b.originalIndex;
    })
    .map((entry) => entry.frame);
}

function readFrameNumber(frame) {
  const candidates = [frame?.frame_number, frame?.frame_index, frame?.index];
  for (const candidate of candidates) {
    const value = Number(candidate);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

function readFrameTimestamp(frame) {
  const candidate = frame?.timestamp_start ?? frame?.timestamp ?? null;
  if (candidate == null) return null;
  const timeValue = new Date(candidate).getTime();
  if (Number.isNaN(timeValue)) return null;
  return timeValue;
}

function buildReplayDiscovery({ timeline, frame, frameIndex, formatClockTime }) {
  const frames = Array.isArray(timeline) ? timeline : [];
  const first = frames[0] ?? null;
  const last = frames[frames.length - 1] ?? null;
  const current = frame ?? first ?? null;
  const frameCount = frames.length;
  const dominantPaths = Array.isArray(current?.propagation_state?.dominant_paths) ? current.propagation_state.dominant_paths : [];
  const contributors = Array.isArray(current?.primary_contributors) ? current.primary_contributors.filter(Boolean).slice(0, 3) : [];
  const confidence = formatConfidenceLabel(current?.cognition_state?.confidence_tier);
  const changeStrength = formatChangeStrength(current);
  const relationshipSupport = dominantPaths.length > 0 ? String(dominantPaths.length) + " operating signal" + (dominantPaths.length === 1 ? "" : "s") + " changed together" : "Supporting signal changes not recorded in this time window";
  const contributorText = contributors.length ? contributors.join(" | ") : "No primary variables listed";

  return {
    headline: replayStateHeadline(current),
    summary: frameCount > 0
      ? "Telemetry replay available across " + String(frameCount) + " frame" + (frameCount === 1 ? "" : "s") + ". Current moment " + String(Math.min(frameIndex + 1, frameCount)) + " shows " + changeStrength.toLowerCase() + " change strength."
      : "No replay available yet.",
    before: buildDiscoveryMoment(first, "Before", "Usual behavior pattern", formatClockTime),
    current: buildDiscoveryMoment(current, "System behavior changed", replayMomentDetail(current), formatClockTime),
    after: buildDiscoveryMoment(last, "Latest replay state", "Most recent observed behavior pattern", formatClockTime),
    whatChanged: {
      title: replayStateHeadline(current),
      detail: contributors.length
        ? sanitizeOperatorText("Relationship pattern shifted around " + contributorText + ".")
        : sanitizeOperatorText(replayMomentDetail(current)),
    },
    evidence: [
      "Confidence: " + confidence,
      "Change strength: " + changeStrength,
      relationshipSupport,
    ],
    reviewNext: {
      title: contributors.length ? "Review supporting evidence" : "Review replay timeline",
      detail: contributors.length
        ? sanitizeOperatorText("Review " + contributorText + " against the source telemetry and operator notes.")
        : "Use the timeline controls to inspect when the change first appeared.",
    },
  };
}

function buildSupportingEvidence({ evidenceRun, uploadResult, frame, frameIndex, frameCount, formatClockTime, lineage = {} }) {
  const items = [];
  const sourceName = evidenceRun?.source_name ?? evidenceRun?.filename ?? uploadResult?.filename;
  const variables = Array.isArray(evidenceRun?.variables) ? evidenceRun.variables.filter(Boolean).slice(0, 4) : [];
  const summaries = Array.isArray(evidenceRun?.evidence_summary) ? evidenceRun.evidence_summary.filter(Boolean) : [];
  const metrics = evidenceRun?.drift_metrics && typeof evidenceRun.drift_metrics === "object" ? evidenceRun.drift_metrics : {};
  const detectedAt = evidenceRun?.deformation_started_at ?? frame?.timestamp_start ?? frame?.timestamp;
  const confidence = evidenceRun?.confidence
    ?? evidenceRun?.confidence_score
    ?? evidenceRun?.evidence_confidence
    ?? metrics.confidence
    ?? frame?.cognition_state?.confidence_tier;
  const changeMetric = firstFiniteNumber(
    metrics.baseline_distance,
    metrics.drift_index,
    metrics.coupling_delta,
    frame?.baseline_distance,
    frame?.topology_state?.drift_index,
  );

  if (sourceName) items.push("Source file: " + sanitizeOperatorText(sourceName));
  if (variables.length) items.push("Variables: " + sanitizeOperatorList(variables).join(" | "));
  if (summaries[0]) items.push("Relationship summary: " + sanitizeOperatorText(summaries[0]));
  if (changeMetric !== null) items.push("Change metric: " + String(changeMetric));
  if (detectedAt) items.push("Detected: " + formatClockTime(detectedAt));
  if (Array.isArray(lineage?.source_rows) && lineage.source_rows.length > 0) {
    const firstAnchor = lineage.source_rows[0] ?? {};
    items.push("Source rows: " + sanitizeOperatorText([firstAnchor.window, firstAnchor.source_row, firstAnchor.timestamp].filter((value) => value !== undefined && value !== null && String(value).trim() !== "").join(" @ ")));
  }
  if (Array.isArray(lineage?.evidence_windows) && lineage.evidence_windows.length > 0) {
    const firstWindow = lineage.evidence_windows[0] ?? {};
    const windowLabel = [
      humanizeReplayVariable(firstWindow.column),
      firstWindow.baseline_window && firstWindow.recent_window
        ? `${firstWindow.baseline_window} to ${firstWindow.recent_window}`
        : (firstWindow.window_start || firstWindow.window_end),
    ].filter(Boolean).join(" ");
    items.push("Evidence window: " + sanitizeOperatorText(windowLabel));
  }
  if (frameCount > 0) {
    const frameTime = frame?.timestamp_end ?? frame?.timestamp ?? frame?.timestamp_start;
    items.push("Replay frame: " + String(Math.min(frameIndex + 1, frameCount)) + "/" + String(frameCount) + (frameTime ? " at " + formatClockTime(frameTime) : ""));
  }
  if (confidence != null && String(confidence).trim()) {
    items.push("Confidence: " + formatEvidenceConfidence(confidence));
  }
  return sanitizeOperatorList(items);
}

function humanizeReplayVariable(value) {
  const text = String(value ?? "").trim();
  const normalized = text.toLowerCase();
  const labels = {
    chiller_load_pct: "Chiller load",
    compressor_power_kw: "Compressor power",
    chw_supply_temp_f: "CHW supply temp",
    flow_gpm: "Flow",
  };
  if (labels[normalized]) return labels[normalized];
  return text.replaceAll("_", " ");
}

function firstFiniteNumber(...values) {
  for (const value of values) {
    if (value == null || String(value).trim() === "") continue;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

function formatEvidenceConfidence(value) {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    const percent = numeric <= 1 ? numeric * 100 : numeric;
    return String(Math.round(percent)) + "%";
  }
  return formatConfidenceLabel(value);
}

function buildDiscoveryMoment(frame, title, fallbackDetail, formatClockTime) {
  if (!frame) {
    return { title: "No replay available yet", detail: "Upload telemetry to generate replay.", time: "-" };
  }
  return {
    title,
    detail: fallbackDetail || replayMomentDetail(frame),
    time: formatClockTime(frame.timestamp_end ?? frame.timestamp ?? frame.timestamp_start ?? "-"),
  };
}

function replayStateHeadline(frame) {
  const state = strengthenReplayState(frame?.topology_state?.stability_state ?? frame?.cognition_state?.facility_state);
  if (!frame) return "No replay available yet";
  if (state === "Stable") return "System behavior stable";
  if (state === "-") return "Change detected";
  return state;
}

function replayMomentDetail(frame) {
  if (!frame) return "No replay available yet.";
  const paths = Array.isArray(frame?.propagation_state?.dominant_paths) ? frame.propagation_state.dominant_paths.length : 0;
  if (paths > 0) return "Relationship pattern shifted with cross-variable support.";
  const strength = readChangeStrength(frame);
  if (Number.isFinite(strength) && strength > 0) return "System behavior changed from its usual pattern.";
  return "System behavior remains close to its usual pattern.";
}

function readChangeStrength(frame) {
  const candidates = [
    frame?.baseline_distance,
    frame?.topology_state?.drift_index,
    frame?.subsystem_pressure?.volatility_index,
  ];
  for (const candidate of candidates) {
    const value = Number(candidate);
    if (Number.isFinite(value)) return value;
  }
  return NaN;
}

function formatChangeStrength(frame) {
  const value = readChangeStrength(frame);
  if (!Number.isFinite(value)) return "Pending";
  if (value < 0.24) return "Low";
  if (value < 0.72) return "Moderate";
  return "High";
}

function simplifyRecoverySignal(value) {
  const normalized = String(value ?? "").toLowerCase();
  if (!normalized.trim()) return "Pending";
  if (normalized.includes("slow") || normalized.includes("elong") || normalized.includes("weak")) return "Slower than usual";
  if (normalized.includes("recover") || normalized.includes("convergen") || normalized.includes("stable")) return "Tracking";
  return sentenceCase(String(value).replaceAll("_", " "));
}

function formatRelationshipContinuity(frame) {
  const value = Number(frame?.topology_state?.fragmentation_indicator);
  if (!Number.isFinite(value)) return "Pending";
  if (value < 0.24) return "Connected";
  if (value < 0.72) return "Changing";
  return "Fragmented";
}
const DEFAULT_CANONICAL_FLOW = ["stable_topology", "relationship_weakening", "pressure_migration", "archetype_emergence", "propagation_activation", "structural_fragmentation", "continuation_pathways", "recovery_or_escalation"];

function strengthenReplayState(value) {
  const normalized = String(value ?? "").toLowerCase();
  if (!normalized.trim()) return "-";
  if (normalized.includes("needs review") || normalized.includes("review")) return "Propagation Watch Active";
  if (normalized.includes("drift")) return "System behavior changed";
  if (normalized.includes("instab") || normalized.includes("separat")) return "Relationship pattern shifted";
  if (normalized.includes("deterior") || normalized.includes("fragment")) return "Relationship pattern fragmented";
  if (normalized.includes("recover") || normalized.includes("convergen")) return "Recovery pattern tracking";
  if (normalized.includes("stable") || normalized.includes("nominal")) return "Stable";
  return sentenceCase(String(value).replaceAll("_", " "));
}

function sentenceCase(value) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1).toLowerCase();
}

function formatConfidenceLabel(value) {
  return normalizeOperatorConfidenceLabel(value);
}

function buildReplayNotice(error, normalizeErrorMessage) {
  const message = String(normalizeErrorMessage(error?.message ?? error) ?? "");
  const lower = message.toLowerCase();
  if (lower.includes("404") || lower.includes("unexpected response")) {
    return "No replay is available for this session.";
  }
  if (lower.includes("network") || lower.includes("failed to fetch")) {
    return "Replay will appear when processing completes.";
  }
  return "No replay is available for this session.";
}
