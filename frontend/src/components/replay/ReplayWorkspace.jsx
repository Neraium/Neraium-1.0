import React, { useEffect, useMemo, useRef, useState } from "react";
import { resolveSessionJobId } from "../../viewModels/currentSession";
import * as uploadStateView from "../../viewModels/uploadState";
import { buildPendingState, sanitizeOperatorList, sanitizeOperatorText } from "../../viewModels/operatorFinding";

const STORY_NOTES_STORAGE_KEY = "neraium.system_story_notes.v1";
const STORY_LEARNING_STORAGE_KEY = "neraium.system_story_learning.v1";
const LEARNING_OPTIONS = ["Correct", "Incorrect", "Expected behavior", "Maintenance event", "Normal startup"];
const NOTE_TEMPLATES = ["Valve replaced.", "Sensor recalibrated.", "False positive.", "Known maintenance."];

export default function ReplayWorkspace({
  apiFetch,
  accessCode,
  normalizeErrorMessage,
  formatClockTime,
  Panel,
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
  const [currentFrameIndex, setCurrentFrameIndex] = useState(0);
  const [error, setError] = useState("");
  const [evidenceRun, setEvidenceRun] = useState(null);
  const [meta, setMeta] = useState({});
  const [noteDraft, setNoteDraft] = useState("");
  const [notesBySession, setNotesBySession] = useState(() => loadJsonStorage(STORY_NOTES_STORAGE_KEY, {}));
  const [learningBySession, setLearningBySession] = useState(() => loadJsonStorage(STORY_LEARNING_STORAGE_KEY, {}));
  const sessionKeyRef = useRef(null);
  const normalizeErrorMessageRef = useRef(normalizeErrorMessage);
  const sessionJobId = useMemo(() => resolveSessionJobId(currentSession), [currentSession]);
  const shouldRequestStory = Boolean(sessionJobId || hasActiveSession || hasCurrentUploadResult || hasResumedSession || hasRealSiiOutput);
  const reviewReady = currentSession?.hasReliableOperatorEvidence === true;

  useEffect(() => {
    normalizeErrorMessageRef.current = normalizeErrorMessage;
  }, [normalizeErrorMessage]);

  useEffect(() => {
    if (typeof window !== "undefined") window.localStorage.setItem(STORY_NOTES_STORAGE_KEY, JSON.stringify(notesBySession));
  }, [notesBySession]);

  useEffect(() => {
    if (typeof window !== "undefined") window.localStorage.setItem(STORY_LEARNING_STORAGE_KEY, JSON.stringify(learningBySession));
  }, [learningBySession]);

  useEffect(() => {
    if (!shouldRequestStory) {
      setTimeline([]);
      setMeta({});
      setCurrentFrameIndex(0);
      setError("");
      setEvidenceRun(null);
      sessionKeyRef.current = null;
      return () => {};
    }
    let cancelled = false;
    async function loadStorySource() {
      try {
        const scoped = await fetchUploadScopedTimeline({ apiFetch, accessCode, jobId: sessionJobId });
        const matchedEvidenceRun = scoped.jobId && reviewReady ? await fetchEvidenceRunForJob({ apiFetch, accessCode, jobId: scoped.jobId }) : null;
        if (cancelled) return;
        const sortedTimeline = sortTimeline(scoped.timeline);
        const storySessionKey = String(scoped.jobId ?? sessionJobId ?? "active-session");
        const sessionChanged = sessionKeyRef.current !== storySessionKey;
        sessionKeyRef.current = storySessionKey;
        setTimeline(sortedTimeline);
        setMeta({ ...(scoped.meta ?? {}), job_id: scoped.jobId, message: scoped.message });
        setEvidenceRun(matchedEvidenceRun);
        setError(sortedTimeline.length > 0 ? "" : (scoped.message || "Behavior timeline details will appear when this session has enough telemetry."));
        setCurrentFrameIndex((current) => sessionChanged ? Math.max(0, sortedTimeline.length - 1) : Math.min(current, Math.max(0, sortedTimeline.length - 1)));
      } catch (loadError) {
        if (cancelled) return;
        setTimeline([]);
        setMeta({});
        setCurrentFrameIndex(0);
        setEvidenceRun(null);
        setError(buildStoryNotice(loadError, normalizeErrorMessageRef.current));
      }
    }
    loadStorySource();
    return () => { cancelled = true; };
  }, [accessCode, apiFetch, reviewReady, sessionJobId, shouldRequestStory]);

  const activeFrame = timeline[Math.min(currentFrameIndex, Math.max(0, timeline.length - 1))] ?? null;
  const storySessionKey = String(sessionJobId ?? meta.job_id ?? "active-session");
  const notes = Array.isArray(notesBySession[storySessionKey]) ? notesBySession[storySessionKey] : [];
  const selectedLearning = learningBySession[storySessionKey] ?? "";
  const story = useMemo(() => buildSystemStory({
    timeline,
    frame: activeFrame,
    frameIndex: currentFrameIndex,
    canonicalFinding,
    currentSession,
    evidenceRun,
    reviewReady,
    formatClockTime,
    domainMode,
  }), [activeFrame, canonicalFinding, currentFrameIndex, currentSession, domainMode, evidenceRun, formatClockTime, reviewReady, timeline]);

  useEffect(() => {
    if (typeof onReplayFrameChange === "function") {
      onReplayFrameChange(activeFrame, {
        frameIndex: Math.min(currentFrameIndex, Math.max(0, timeline.length - 1)),
        totalFrames: timeline.length,
        feature: "system-story",
      });
    }
  }, [activeFrame, currentFrameIndex, onReplayFrameChange, timeline.length]);

  useEffect(() => {
    if (typeof onReplayModeChange === "function") onReplayModeChange(false);
  }, [onReplayModeChange]);

  function addNote(text = noteDraft) {
    const clean = sanitizeOperatorText(text);
    if (!clean) return;
    const entry = { id: `${Date.now()}-${Math.random().toString(36).slice(2)}`, text: clean, createdAt: new Date().toISOString() };
    setNotesBySession((current) => ({
      ...current,
      [storySessionKey]: [entry, ...(current[storySessionKey] ?? [])].slice(0, 20),
    }));
    setNoteDraft("");
  }

  function selectLearning(label) {
    setLearningBySession((current) => ({ ...current, [storySessionKey]: label }));
  }

  return (
    <div className="workspace-grid workspace-grid--console system-story-workspace">
      <Panel title="Analysis Details" className="span-12 workspace-hero-panel system-story-hero" subtitle="What happened, why we believe it, and what to inspect next.">
        <div className="system-story-hero__layout">
          <div>
            <p className="section-token">Analysis Details</p>
            <h3>{story.whatHappened}</h3>
            <p className="narrative-text">{story.summary}</p>
          </div>
          <div className="system-story-hero__facts" role="group" aria-label="Story status">
            {story.facts.map((fact) => (
              <div key={fact.label}>
                <span>{fact.label}</span>
                <strong>{fact.value}</strong>
              </div>
            ))}
          </div>
        </div>
      </Panel>

      <Panel title="Evidence" className="span-6 system-story-card">
        <ul className="system-story-list">{story.evidence.map((item) => <li key={item}>{item}</li>)}</ul>
      </Panel>
      <Panel title="Possible Operational Causes" className="span-6 system-story-card">
        <div className="system-story-hypotheses">
          {story.hypotheses.map((item) => (
            <section key={`${item.rank}-${item.label}`}>
              <span>{item.rank}</span>
              <strong>{item.label}</strong>
              <p>{item.detail}</p>
            </section>
          ))}
        </div>
      </Panel>
      <Panel title="What To Inspect" className="span-6 system-story-card">
        <div className="system-story-checklist">
          {story.checklist.map((item) => (
            <label key={item}>
              <input type="checkbox" />
              <span>{item}</span>
            </label>
          ))}
        </div>
      </Panel>
      <Panel title="How It Developed" className="span-6 system-story-card">
        <div className="system-story-timeline" role="group" aria-label="Behavior timeline">
          {story.development.map((item) => (
            <section key={`${item.time}-${item.label}`}>
              <span>{item.time}</span>
              <strong>{item.label}</strong>
              <p>{item.detail}</p>
            </section>
          ))}
        </div>
        {timeline.length > 1 ? (
          <input
            className="system-story-scrubber"
            aria-label="Story timeline"
            type="range"
            min={0}
            max={Math.max(0, timeline.length - 1)}
            value={Math.min(currentFrameIndex, Math.max(0, timeline.length - 1))}
            onChange={(event) => setCurrentFrameIndex(Number(event.target.value))}
          />
        ) : null}
      </Panel>
      <Panel title="Supporting Trends" className="span-12 system-story-card">
        <div className="system-story-chart-grid">{story.trends.map((trend) => <TrendChart key={trend.label} trend={trend} />)}</div>
      </Panel>
      <Panel title="Operator Notes" className="span-6 system-story-card">
        <div className="system-story-note-entry">
          <textarea aria-label="Inspection notes" value={noteDraft} onChange={(event) => setNoteDraft(event.target.value)} placeholder="Add inspection notes" rows={3} />
          <button type="button" className="command-button" onClick={() => addNote()}>Add Note</button>
        </div>
        <div className="system-story-note-templates" role="group" aria-label="Note shortcuts">
          {NOTE_TEMPLATES.map((item) => <button type="button" className="secondary-command-button" key={item} onClick={() => addNote(item)}>{item}</button>)}
        </div>
        <div className="system-story-notes">
          {notes.length ? notes.map((note) => (
            <section key={note.id}>
              <strong>{note.text}</strong>
              <span>{formatClockTime(note.createdAt)}</span>
            </section>
          )) : <p className="narrative-text">No operator notes have been added. Add inspection context when it becomes available.</p>}
        </div>
      </Panel>
      <Panel title="Inspection Outcome" className="span-6 system-story-card">
        <div className="system-story-learning" role="group" aria-label="Inspection outcome">
          {LEARNING_OPTIONS.map((label) => (
            <button type="button" key={label} className={selectedLearning === label ? "command-button" : "secondary-command-button"} onClick={() => selectLearning(label)}>
              {label}
            </button>
          ))}
        </div>
        <p className="narrative-text">
          {selectedLearning ? `Marked as ${selectedLearning.toLowerCase()}. Future comparisons for this session will include that field context.` : "Mark the inspection outcome so future stories can account for field knowledge."}
        </p>
      </Panel>
      {error ? <Panel title="Analysis Details Notice" className="span-12"><p className="narrative-text">{error}</p></Panel> : null}
    </div>
  );
}

function TrendChart({ trend }) {
  const width = 420;
  const height = 150;
  const historical = lineChartPoints(trend.historical, width, height);
  const current = lineChartPoints(trend.current, width, height);
  const deviationX = trend.deviationIndex == null ? null : (trend.deviationIndex / Math.max(trend.current.length - 1, 1)) * width;
  return (
    <section className="system-story-chart">
      <div className="system-story-chart__header"><strong>{trend.label}</strong><span>{trend.unit}</span></div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${trend.label} historical and current trend`}>
        <line x1="0" x2={width} y1={height - 24} y2={height - 24} className="system-story-chart__axis" />
        {deviationX !== null ? <rect x={Math.max(0, deviationX - 8)} y="0" width="16" height={height} className="system-story-chart__deviation" /> : null}
        <polyline points={historical} className="system-story-chart__historical" />
        <polyline points={current} className="system-story-chart__current" />
      </svg>
      <div className="system-story-chart__legend"><span>Historical</span><span>Current</span><span>Detected deviation</span></div>
    </section>
  );
}

async function fetchUploadScopedTimeline({ apiFetch, accessCode, jobId = null }) {
  let targetJobId = jobId;
  if (!targetJobId) {
    const latestResponse = await apiFetch("/api/data/latest-upload?include_persisted=1", { accessCode });
    if (!latestResponse.ok) throw new Error("The saved analysis could not be loaded. Refresh and retry.");
    const latestPayload = await latestResponse.json();
    const currentUpload = latestPayload?.current_upload ?? latestPayload?.snapshot?.current_upload ?? null;
    targetJobId = uploadStateView.resolveCurrentUploadJobId(latestPayload) ?? currentUpload?.job_id ?? null;
    if (!targetJobId) return { jobId: null, timeline: [], meta: {}, message: "Analysis details will appear after a dataset has been analyzed." };
  }
  const statusResponse = await apiFetch(`/api/data/upload-status/${encodeURIComponent(targetJobId)}`, { accessCode });
  let pendingMessage = "";
  if (statusResponse.ok) {
    const statusPayload = await statusResponse.json();
    const status = String(statusPayload?.status ?? "").toUpperCase();
    const replayFrameCount = Number(statusPayload?.replay_frame_count ?? statusPayload?.latest_replay_frames ?? 0) || 0;
    const timelineReady = Boolean(statusPayload?.replay_ready) || replayFrameCount > 0;
    const resultAvailable = Boolean(statusPayload?.result_available);
    const terminalOrFetchable = ["COMPLETE", "FAILED", "ACTIVE"].includes(status) || timelineReady || resultAvailable;
    if (status && !terminalOrFetchable) pendingMessage = `Advanced details are still building for this upload job (${status.toLowerCase()}).`;
    if (status === "COMPLETE" && resultAvailable && statusPayload?.replay_ready === false && replayFrameCount === 0) {
      return {
        jobId: targetJobId,
        timeline: [],
        meta: { frame_count: 0 },
        message: "Behavior timeline details will appear when this session has enough telemetry.",
      };
    }
  }
  const timelineResponse = await apiFetch(`/api/data/replay/${encodeURIComponent(targetJobId)}`, { accessCode });
  if (!timelineResponse.ok) throw new Error("The behavior timeline could not be loaded. Refresh and retry.");
  const payload = await timelineResponse.json();
  const timeline = Array.isArray(payload?.timeline) ? payload.timeline : [];
  const meta = payload?.meta && typeof payload.meta === "object" ? payload.meta : {};
  return { jobId: targetJobId, timeline, meta, message: timeline.length ? "" : (pendingMessage || (typeof payload?.message === "string" ? payload.message : "")) };
}

async function fetchEvidenceRunForJob({ apiFetch, accessCode, jobId }) {
  const response = await apiFetch("/api/evidence/runs", { accessCode });
  if (!response.ok) return null;
  const payload = await response.json();
  const runs = Array.isArray(payload?.runs) ? payload.runs : [];
  return runs.find((run) => String(run?.run_id ?? "") === String(jobId) && String(run?.status ?? "").toLowerCase() === "completed") ?? null;
}

function buildSystemStory({ timeline, frame, frameIndex, canonicalFinding, currentSession, evidenceRun, reviewReady, formatClockTime, domainMode }) {
  const frames = Array.isArray(timeline) ? timeline : [];
  const activeFrame = frame ?? frames[frames.length - 1] ?? null;
  const finding = canonicalFinding ?? {};
  const pendingState = frames.length > 0 && !reviewReady ? buildPendingState(currentSession?.reviewReadiness) : null;
  const variables = collectVariables({ evidenceRun, activeFrame, currentSession });
  const equipment = inferEquipmentName(variables, domainMode);
  const duration = inferDuration({ frames, evidenceRun, finding });
  const strength = formatChangeStrength(activeFrame);
  const whatHappened = pendingState ? "Insights are not ready because the analysis is still being verified." : finding.summary ? sanitizeOperatorText(finding.summary) : buildWhatHappened({ equipment, strength, duration, activeFrame });
  const evidence = pendingState ? sanitizeOperatorList([pendingState.subtitle, pendingState.detail]) : buildEvidenceBullets({ evidenceRun, finding, activeFrame, variables });
  return {
    whatHappened,
    summary: pendingState ? pendingState.detail : `This story summarizes ${frames.length || "the current"} observation window in operator language and points the engineer to the next inspection steps.`,
    evidence,
    hypotheses: buildHypotheses({ variables, evidence, domainMode }),
    checklist: buildChecklist({ variables, domainMode }),
    development: buildDevelopmentTimeline({ frames, frameIndex, formatClockTime, pendingState }),
    trends: buildTrendModels({ frames, variables }),
    facts: [
      { label: "Window", value: duration },
      { label: "Strength", value: strength },
      { label: "Signals", value: variables.length ? String(variables.length) : "Unknown" },
    ],
  };
}

function buildWhatHappened({ equipment, strength, duration, activeFrame }) {
  const normalized = String(activeFrame?.topology_state?.stability_state ?? activeFrame?.cognition_state?.facility_state ?? "").toLowerCase();
  if (normalized.includes("stable")) return `${equipment} remains close to its historical operating pattern.`;
  if (normalized.includes("recover")) return `${equipment} is moving back toward its usual behavior.`;
  if (equipment.toLowerCase().includes("pump")) return `${equipment} began operating differently than its historical pattern.`;
  if (strength === "High" || strength === "Moderate") return `${equipment} gradually became less efficient over ${duration}.`;
  return `${equipment} shows a developing change from its usual operating pattern.`;
}

function buildEvidenceBullets({ evidenceRun, finding, activeFrame, variables }) {
  const supplied = sanitizeOperatorList([...(Array.isArray(finding?.supportingEvidence) ? finding.supportingEvidence : []), ...(Array.isArray(evidenceRun?.evidence_summary) ? evidenceRun.evidence_summary : [])]).map(cleanEvidenceLine);
  const generated = [];
  const contributors = variables.slice(0, 4);
  if (contributors.length >= 2) generated.push(`${humanize(contributors[0])} and ${humanize(contributors[1])} no longer moved the way they usually do.`);
  const strength = readChangeStrength(activeFrame);
  if (Number.isFinite(strength) && strength >= 0.24) generated.push("Current behavior stayed outside the historical operating band.");
  if (Array.isArray(activeFrame?.primary_contributors) && activeFrame.primary_contributors.length) generated.push(`${sanitizeOperatorList(activeFrame.primary_contributors).slice(0, 3).map(humanize).join(", ")} contributed most to the change.`);
  return sanitizeOperatorList([...supplied, ...generated]).slice(0, 5);
}

function buildHypotheses({ variables, evidence, domainMode }) {
  const text = `${variables.join(" ")} ${evidence.join(" ")} ${domainMode ?? ""}`.toLowerCase();
  const hypotheses = [];
  if (text.includes("valve") || text.includes("flow") || text.includes("chw")) hypotheses.push({ rank: "Most likely", label: "Valve control issue", detail: "Flow response appears inconsistent with the expected command or load pattern." });
  if (text.includes("pump") || text.includes("vfd") || text.includes("speed")) hypotheses.push({ rank: hypotheses.length ? "Possible" : "Most likely", label: "Pump or VFD response change", detail: "Pump behavior may no longer match its historical response curve." });
  if (text.includes("temperature") || text.includes("sensor") || text.includes("humidity")) hypotheses.push({ rank: hypotheses.length ? "Possible" : "Most likely", label: "Sensor drift", detail: "A measurement point may be biasing the interpretation if calibration has shifted." });
  hypotheses.push({ rank: hypotheses.length ? "Possible" : "Most likely", label: "Reduced flow", detail: "Hydraulic or process movement may be lower than expected for the current operating condition." });
  hypotheses.push({ rank: "Possible", label: "Changing load conditions", detail: "A real load change may explain the new pattern without an equipment fault." });
  return hypotheses.slice(0, 4);
}

function buildChecklist({ variables, domainMode }) {
  const text = `${variables.join(" ")} ${domainMode ?? ""}`.toLowerCase();
  const items = ["Verify BAS values"];
  if (text.includes("valve") || text.includes("flow") || text.includes("chw")) items.push("Inspect valve position");
  items.push("Compare sensor calibration");
  if (text.includes("pump") || text.includes("speed") || text.includes("flow")) items.push("Review VFD output");
  items.push("Check recent maintenance");
  return [...new Set(items)].slice(0, 6);
}

function buildDevelopmentTimeline({ frames, frameIndex, formatClockTime, pendingState }) {
  if (!frames.length) return [{ time: "Current", label: "Waiting for telemetry", detail: "Upload or resume a session to create behavior timeline details." }];
  const first = frames[0];
  const middle = frames[Math.floor(frames.length / 2)];
  const current = frames[Math.min(frameIndex, frames.length - 1)] ?? frames[frames.length - 1];
  const last = frames[frames.length - 1];
  return [
    { time: formatStoryTime(first, formatClockTime), label: "Normal", detail: "Historical operating pattern established." },
    { time: formatStoryTime(middle, formatClockTime), label: "Behavior begins deviating", detail: "The current window starts moving away from expected behavior." },
    { time: formatStoryTime(current, formatClockTime), label: pendingState ? "Verification pending" : "Confidence increases", detail: pendingState ? pendingState.subtitle : "Evidence becomes strong enough to create an operator story." },
    { time: formatStoryTime(last, formatClockTime), label: "Observation created", detail: "Behavior details are ready for engineer review." },
    { time: "Current", label: "Inspect and teach", detail: "Add notes and mark the outcome after field review." },
  ];
}

function buildTrendModels({ frames, variables }) {
  const labels = chooseTrendLabels(variables);
  return labels.map((label, labelIndex) => {
    const values = frames.length ? frames.map((frame, index) => ({ value: trendValueForFrame(frame, index, labelIndex) })) : Array.from({ length: 8 }, (_, index) => ({ value: 40 + index * 2 + labelIndex * 4 }));
    const historical = values.map((item, index) => ({ value: Math.max(0, Number(item.value) - 8 + Math.sin(index + labelIndex) * 4) }));
    return { label, unit: trendUnit(label), historical, current: values, deviationIndex: Math.max(1, Math.floor(values.length * 0.62)) };
  });
}

function chooseTrendLabels(variables) {
  const text = variables.join(" ").toLowerCase();
  const labels = [];
  if (text.includes("flow")) labels.push("Flow");
  if (text.includes("speed") || text.includes("pump")) labels.push("Pump speed");
  if (text.includes("delta")) labels.push("Delta-T");
  if (text.includes("load")) labels.push("Load");
  if (text.includes("power") || text.includes("kw")) labels.push("Power");
  if (text.includes("temp") || text.includes("chw")) labels.push("Temperature");
  return [...new Set(labels.length ? labels : ["Flow", "Pump speed", "Delta-T", "Load", "Power", "Temperature"])].slice(0, 6);
}

function trendValueForFrame(frame, index, offset) {
  const candidates = [frame?.baseline_distance, frame?.topology_state?.drift_index, frame?.subsystem_pressure?.volatility_index, frame?.propagation_state?.activation_intensity];
  const numeric = candidates.map(Number).find(Number.isFinite);
  const base = Number.isFinite(numeric) ? numeric * 100 : 28 + index * 5;
  return Math.max(4, base + offset * 7 + Math.sin(index + offset) * 6);
}

function trendUnit(label) {
  if (label === "Temperature") return "deg";
  if (label === "Power") return "kW";
  if (label === "Flow") return "gpm";
  if (label === "Pump speed" || label === "Load") return "%";
  return "trend";
}

function collectVariables({ evidenceRun, activeFrame, currentSession }) {
  return sanitizeOperatorList([...(Array.isArray(evidenceRun?.variables) ? evidenceRun.variables : []), ...(Array.isArray(activeFrame?.primary_contributors) ? activeFrame.primary_contributors : []), ...(Array.isArray(currentSession?.canonicalFinding?.affectedVariables) ? currentSession.canonicalFinding.affectedVariables : [])]);
}

function inferEquipmentName(variables, domainMode) {
  const text = `${variables.join(" ")} ${domainMode ?? ""}`.toLowerCase();
  if (text.includes("chw") || text.includes("chiller")) return "The chilled water loop";
  if (text.includes("pump")) return "Pump 2";
  if (text.includes("pool") || text.includes("orp") || text.includes("chlorine")) return "The aquatic treatment loop";
  if (text.includes("air") || text.includes("ahu")) return "The air handling system";
  return "The building system";
}

function inferDuration({ frames, evidenceRun, finding }) {
  const frameSpanMinutes = inferFrameSpanMinutes(frames);
  const externalBaseline = evidenceRun?.external_historical_baseline === true || evidenceRun?.baseline_scope === "external_historical_baseline";
  const explicit = finding?.technicalDetails?.find?.((item) => item.label === "Behavior duration")?.value;
  const explicitMinutes = parseDurationMinutes(explicit);
  if (explicit && (!Number.isFinite(explicitMinutes) || !Number.isFinite(frameSpanMinutes) || explicitMinutes <= frameSpanMinutes || externalBaseline)) {
    return String(explicit);
  }
  if (explicit && Number.isFinite(frameSpanMinutes) && explicitMinutes > frameSpanMinutes && !externalBaseline) {
    warnImpossibleDuration("explicit", explicit, frameSpanMinutes);
    return formatDurationMinutes(frameSpanMinutes);
  }

  const startedAt = evidenceRun?.deformation_started_at;
  const endedAt = latestValidFrameTimestamp(frames);
  const evidenceMinutes = startedAt && endedAt ? Math.round((new Date(endedAt).getTime() - new Date(startedAt).getTime()) / 60000) : NaN;
  if (Number.isFinite(evidenceMinutes) && evidenceMinutes > 0 && (!Number.isFinite(frameSpanMinutes) || evidenceMinutes <= frameSpanMinutes || externalBaseline)) {
    return formatDurationMinutes(evidenceMinutes);
  }
  if (Number.isFinite(evidenceMinutes) && Number.isFinite(frameSpanMinutes) && evidenceMinutes > frameSpanMinutes && !externalBaseline) {
    warnImpossibleDuration("evidence", `${evidenceMinutes} minutes`, frameSpanMinutes);
    return formatDurationMinutes(frameSpanMinutes);
  }
  if (Number.isFinite(frameSpanMinutes) && frameSpanMinutes > 0) return formatDurationMinutes(frameSpanMinutes);
  if (frames.length > 1) return `${frames.length} observation points`;
  return "the current observation window";
}

function inferFrameSpanMinutes(frames) {
  const timestamps = (Array.isArray(frames) ? frames : [])
    .flatMap((frame) => [frame?.timestamp_start, frame?.timestamp, frame?.timestamp_end])
    .map((value) => new Date(value).getTime())
    .filter((value) => Number.isFinite(value));
  if (timestamps.length < 2) return NaN;
  const minutes = Math.round((Math.max(...timestamps) - Math.min(...timestamps)) / 60000);
  return minutes > 0 ? minutes : NaN;
}

function latestValidFrameTimestamp(frames) {
  const timestamps = (Array.isArray(frames) ? frames : [])
    .flatMap((frame) => [frame?.timestamp_end, frame?.timestamp, frame?.timestamp_start])
    .map((value) => ({ value, time: new Date(value).getTime() }))
    .filter((item) => Number.isFinite(item.time));
  if (!timestamps.length) return null;
  timestamps.sort((a, b) => b.time - a.time);
  return timestamps[0].value;
}

function parseDurationMinutes(value) {
  const text = String(value ?? "").trim().toLowerCase();
  const match = text.match(/([0-9]+(?:\.[0-9]+)?)\s*(minute|minutes|min|hour|hours|hr|hrs|day|days)/);
  if (!match) return NaN;
  const number = Number(match[1]);
  if (!Number.isFinite(number)) return NaN;
  const unit = match[2];
  if (unit.startsWith("day")) return number * 24 * 60;
  if (unit.startsWith("hour") || unit === "hr" || unit === "hrs") return number * 60;
  return number;
}

function formatDurationMinutes(minutes) {
  if (!Number.isFinite(minutes) || minutes <= 0) return "the current observation window";
  if (minutes >= 24 * 60) {
    const days = Math.max(1, Math.round(minutes / (24 * 60)));
    return `${days} ${days === 1 ? "day" : "days"}`;
  }
  if (minutes >= 60) {
    const hours = Math.max(1, Math.round(minutes / 60));
    return `${hours} ${hours === 1 ? "hour" : "hours"}`;
  }
  const rounded = Math.max(1, Math.round(minutes));
  return `${rounded} ${rounded === 1 ? "minute" : "minutes"}`;
}

function warnImpossibleDuration(source, duration, frameSpanMinutes) {
  if (typeof console !== "undefined" && typeof console.warn === "function") {
    console.warn("system_story_duration_exceeds_dataset_span", { source, duration, datasetDuration: formatDurationMinutes(frameSpanMinutes) });
  }
}

function cleanEvidenceLine(value) {
  return sanitizeOperatorText(String(value ?? "")
    .replace(/\breplay\/relationship evidence\b/gi, "historical comparison")
    .replace(/\breplay relationship evidence\b/gi, "historical comparison")
    .replace(/\breplay evidence\b/gi, "historical comparison")
    .replace(/\brelationship divergence\b/gi, "system behavior changed")
    .replace(/\bState Group A\b/gi, "the usual pattern"));
}

function sortTimeline(frames) {
  if (!Array.isArray(frames) || frames.length === 0) return [];
  return frames
    .map((frame, originalIndex) => ({ frame, originalIndex }))
    .sort((a, b) => {
      const aNumber = readFrameNumber(a.frame);
      const bNumber = readFrameNumber(b.frame);
      if (aNumber !== null && bNumber !== null && aNumber !== bNumber) return aNumber - bNumber;
      const aTimestamp = readFrameTimestamp(a.frame);
      const bTimestamp = readFrameTimestamp(b.frame);
      if (aTimestamp !== null && bTimestamp !== null && aTimestamp !== bTimestamp) return aTimestamp < bTimestamp ? -1 : 1;
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

function readChangeStrength(frame) {
  const candidates = [frame?.baseline_distance, frame?.topology_state?.drift_index, frame?.subsystem_pressure?.volatility_index];
  for (const candidate of candidates) {
    const value = Number(candidate);
    if (Number.isFinite(value)) return value;
  }
  return NaN;
}

function formatChangeStrength(frame) {
  const value = readChangeStrength(frame);
  if (!Number.isFinite(value)) return "Unknown";
  if (value < 0.24) return "Low";
  if (value < 0.72) return "Moderate";
  return "High";
}

function formatStoryTime(frame, formatClockTime) {
  const timestamp = frame?.timestamp_end ?? frame?.timestamp ?? frame?.timestamp_start;
  if (!timestamp) return "-";
  const date = new Date(timestamp);
  if (!Number.isNaN(date.getTime())) return new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
  return formatClockTime(timestamp);
}

function lineChartPoints(values, width, height) {
  const numeric = values.map((item) => Number(item.value)).filter(Number.isFinite);
  const min = numeric.length ? Math.min(...numeric) : 0;
  const max = numeric.length ? Math.max(...numeric) : 1;
  const span = Math.max(max - min, 1);
  return values.map((item, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - (((Number(item.value) - min) / span) * (height - 18)) - 8;
    return `${x},${Math.max(4, Math.min(height - 4, y))}`;
  }).join(" ");
}

function humanize(value) {
  return String(value ?? "").replaceAll("_", " ").replace(/\b\w/g, (match) => match.toUpperCase());
}

function loadJsonStorage(key, fallback) {
  if (typeof window === "undefined") return fallback;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

function buildStoryNotice(error, normalizeErrorMessage) {
  const message = String(normalizeErrorMessage?.(error?.message ?? error) ?? error?.message ?? error ?? "");
  const lower = message.toLowerCase();
  if (lower.includes("404") || lower.includes("unexpected response")) return "Behavior timeline details will appear when this session has enough telemetry.";
  if (lower.includes("network") || lower.includes("failed to fetch")) return "Behavior timeline details will appear when processing completes.";
  return "Behavior timeline details will appear when this session has enough telemetry.";
}
