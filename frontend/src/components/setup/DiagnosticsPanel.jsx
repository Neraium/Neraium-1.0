import { useEffect, useMemo, useState } from "react";
import { DataTable, EmptyState, MetricGrid, Panel } from "../workspacePrimitives";
import {
  classifyBaselineSeparation,
  classifyDriftAcceleration,
  classifyDriftVelocity,
  formatStructuralRead,
} from "../../viewModels/structuralTimelineViewModel";

const DASH = "-";

function readPrimaryContributors(result) {
  const frameContributors = result?.sii_intelligence?.replay_timeline?.timeline?.at?.(-1)?.primary_contributors;
  if (Array.isArray(frameContributors) && frameContributors.length) {
    return frameContributors.slice(0, 3).join(" | ");
  }
  const driver = result?.sii_intelligence?.primary_driver;
  if (driver) return String(driver);
  const evidence = result?.sii_intelligence?.supporting_evidence;
  if (Array.isArray(evidence) && evidence.length) return String(evidence[0]);
  return DASH;
}

function replaySummaryFromFrames(frames) {
  if (!Array.isArray(frames) || frames.length === 0) {
    return {
      frameCount: 0,
      currentWindow: DASH,
      baselineSeparation: DASH,
      driftVelocity: DASH,
      driftAcceleration: DASH,
      structuralRead: DASH,
      evidenceConfidence: DASH,
      leadTime: DASH,
      previewRange: DASH,
      replay: "Unavailable",
    };
  }
  const last = frames[frames.length - 1] || {};
  const first = frames[0] || {};
  return {
    frameCount: frames.length,
    currentWindow: `${frames.length}/${frames.length}`,
    baselineSeparation: classifyBaselineSeparation(last?.baseline_distance ?? last?.topology_state?.drift_index),
    driftVelocity: classifyDriftVelocity(last?.drift_velocity ?? last?.subsystem_pressure?.volatility_index),
    driftAcceleration: classifyDriftAcceleration(last?.drift_acceleration ?? last?.propagation_state?.propagation_acceleration),
    structuralRead: formatStructuralRead(last?.topology_state?.stability_state ?? last?.cognition_state?.facility_state),
    evidenceConfidence: String(last?.evidence_confidence ?? last?.cognition_state?.confidence_tier ?? DASH),
    leadTime: String(last?.continuation_window?.window ?? DASH),
    previewRange: `${first?.timestamp_range?.start ?? first?.timestamp ?? DASH} -> ${last?.timestamp_range?.end ?? last?.timestamp ?? DASH}`,
    replay: "Available",
  };
}

function replaySummaryFromResult(result) {
  const intelligence = result?.sii_intelligence ?? {};
  return {
    frameCount: 0,
    currentWindow: String(intelligence?.observed_persistence ?? DASH),
    baselineSeparation: classifyBaselineSeparation(result?.baseline_analysis?.column_drift?.[0]?.percent_change),
    driftVelocity: String(result?.driver_attribution?.severity ?? DASH),
    driftAcceleration: DASH,
    structuralRead: formatStructuralRead(intelligence?.facility_state),
    evidenceConfidence: String(intelligence?.confidence_basis ?? DASH),
    leadTime: String(intelligence?.intervention_window ?? DASH),
    previewRange: String(result?.timestamp_profile?.first_timestamp && result?.timestamp_profile?.last_timestamp
      ? `${result.timestamp_profile.first_timestamp} -> ${result.timestamp_profile.last_timestamp}`
      : DASH),
    replay: "Unavailable",
  };
}

export default function DiagnosticsPanel({
  latestUploadResult,
  latestUploadSnapshot,
  hasActiveSession,
  hasCurrentUploadResult,
  hasResumedSession,
  hasRealSiiOutput,
  apiFetch,
  accessCode,
  uploadStateView,
  uploadHistoryRows,
}) {
  const [replayFrames, setReplayFrames] = useState([]);
  const [replayError, setReplayError] = useState("");
  const activeJobId = useMemo(
    () => latestUploadResult?.job_id ?? latestUploadSnapshot?.history?.[0]?.job_id ?? null,
    [latestUploadResult?.job_id, latestUploadSnapshot?.history],
  );

  useEffect(() => {
    if (!hasActiveSession || !hasRealSiiOutput || !activeJobId) {
      setReplayFrames([]);
      setReplayError("");
      return;
    }
    let cancelled = false;
    async function loadReplayByJob() {
      try {
        const response = await apiFetch(`/api/data/replay/${encodeURIComponent(activeJobId)}`, { accessCode });
        if (!response.ok) throw new Error(`Unexpected response: ${response.status}`);
        const payload = await response.json();
        if (cancelled) return;
        const frames = Array.isArray(payload?.timeline) ? payload.timeline : [];
        setReplayFrames(frames);
        setReplayError(frames.length ? "" : "No replay frames available for this session.");
      } catch {
        if (cancelled) return;
        setReplayFrames([]);
        setReplayError("No replay frames available for this session.");
      }
    }
    loadReplayByJob();
    return () => {
      cancelled = true;
    };
  }, [accessCode, activeJobId, apiFetch, hasActiveSession, hasRealSiiOutput]);

  const showAnalysis = hasActiveSession && hasRealSiiOutput && (hasCurrentUploadResult || hasResumedSession);
  const fallbackSummary = replaySummaryFromResult(latestUploadResult);
  const frameSummary = replaySummaryFromFrames(replayFrames);
  const summary = frameSummary.frameCount > 0 ? frameSummary : fallbackSummary;
  const contributors = readPrimaryContributors(latestUploadResult);

  const metrics = showAnalysis ? [
    { label: "Structural Movement Timeline", value: summary.frameCount > 0 ? summary.frameCount : "Active session" },
    { label: "Current Window", value: summary.currentWindow },
    { label: "Baseline Separation", value: summary.baselineSeparation },
    { label: "Drift Velocity", value: summary.driftVelocity },
    { label: "Drift Acceleration", value: summary.driftAcceleration },
    { label: "Structural Read", value: summary.structuralRead },
    { label: "Primary Contributors", value: contributors },
    { label: "Evidence Confidence", value: summary.evidenceConfidence },
    { label: "Replay", value: summary.replay },
    { label: "Lead Time", value: summary.leadTime },
    { label: "Preview Range", value: summary.previewRange },
  ] : [
    { label: "Structural Movement Timeline", value: DASH },
    { label: "Current Window", value: DASH },
    { label: "Baseline Separation", value: DASH },
    { label: "Drift Velocity", value: DASH },
    { label: "Drift Acceleration", value: DASH },
    { label: "Structural Read", value: DASH },
    { label: "Primary Contributors", value: DASH },
    { label: "Evidence Confidence", value: DASH },
    { label: "Replay", value: "Unavailable" },
    { label: "Lead Time", value: DASH },
    { label: "Preview Range", value: DASH },
  ];

  const topology = showAnalysis
    ? {
        topology: latestUploadResult?.sii_intelligence?.facility_state ?? DASH,
        propagation: latestUploadResult?.sii_intelligence?.urgency ?? DASH,
        recovery: latestUploadResult?.sii_intelligence?.projected_time_to_failure ?? DASH,
        confidence: latestUploadResult?.sii_intelligence?.confidence_basis ?? DASH,
      }
    : { topology: DASH, propagation: DASH, recovery: DASH, confidence: DASH };

  return (
    <Panel title="Diagnostics" className="span-12">
      {!showAnalysis ? (
        <EmptyState title="No active diagnostics session" body="Upload telemetry or resume a previous session to activate Infrastructure Diagnostics." compact />
      ) : (
        <>
          <MetricGrid metrics={metrics} compact />
          {replayError ? <p className="narrative-text">{replayError}</p> : null}
          <Panel title="Topology Session Context" className="span-12">
            <MetricGrid
              metrics={[
                { label: "Topology", value: topology.topology },
                { label: "Propagation", value: topology.propagation },
                { label: "Recovery", value: topology.recovery },
                { label: "Confidence", value: topology.confidence },
              ]}
              compact
            />
          </Panel>
          {/* TODO: Backend replay frame persistence should always provide frame-level topology details per upload job. */}
        </>
      )}
      <details className="technical-summary-panel">
        <summary>Show active result and upload history</summary>
        <MetricGrid
          metrics={[
            { label: "Score", value: latestUploadResult?.sii_intelligence?.neraium_score },
            { label: "State", value: latestUploadResult?.sii_intelligence?.facility_state },
            { label: "Drift", value: latestUploadResult?.sii_intelligence?.urgency },
            { label: "Timestamp", value: uploadStateView.deriveTimeCoverage(latestUploadResult).summary },
            { label: "Job ID", value: activeJobId ?? DASH },
            { label: "Replay Frames", value: replayFrames.length || DASH },
          ]}
          compact
        />
        <Panel title="Upload History" className="span-12">
          {uploadHistoryRows.length > 0 ? (
            <DataTable
              columns={["Result", "Status", "Score", "State", "Room", "Delta"]}
              rows={uploadHistoryRows.map((row) => [row.filename, row.status, row.score, row.state, row.room, row.scoreDelta])}
            />
          ) : (
            <EmptyState title="No ingestion history" body="Completed uploads and structural analysis sessions will appear here." compact />
          )}
        </Panel>
      </details>
    </Panel>
  );
}
