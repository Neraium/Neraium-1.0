import { useEffect, useMemo, useState } from "react";
import { DataTable, EmptyState, MetricGrid, Panel } from "../workspacePrimitives";
import {
  classifyBaselineSeparation,
  classifyDriftAcceleration,
  classifyDriftVelocity,
  formatStructuralRead,
} from "../../viewModels/structuralTimelineViewModel";

const DASH = "-";

function formatConfidenceComponentValue(value) {
  if (!value) return DASH;
  const text = String(value);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

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
  apiFetch,
  accessCode,
  uploadStateView,
  uploadHistoryRows,
}) {
  const [replayFrames, setReplayFrames] = useState([]);
  const [replayError, setReplayError] = useState("");
  const activeJobId = useMemo(
    () => latestUploadSnapshot?.current_upload?.job_id ?? latestUploadResult?.job_id ?? latestUploadSnapshot?.job_id ?? null,
    [latestUploadSnapshot?.current_upload?.job_id, latestUploadResult?.job_id, latestUploadSnapshot?.job_id],
  );

  useEffect(() => {
    if (!hasActiveSession || !activeJobId) {
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
  }, [accessCode, activeJobId, apiFetch, hasActiveSession]);

  const showAnalysis = hasActiveSession && (hasCurrentUploadResult || hasResumedSession);
  const fallbackSummary = replaySummaryFromResult(latestUploadResult);
  const frameSummary = replaySummaryFromFrames(replayFrames);
  const summary = frameSummary.frameCount > 0 ? frameSummary : fallbackSummary;
  const contributors = readPrimaryContributors(latestUploadResult);

  const metrics = showAnalysis ? [
    { label: "Replay timeline", value: summary.frameCount > 0 ? summary.frameCount : "Active session" },
    { label: "Current Window", value: summary.currentWindow },
    { label: "Change strength", value: summary.baselineSeparation },
    { label: "Change direction", value: summary.driftVelocity },
    { label: "Change momentum", value: summary.driftAcceleration },
    { label: "System behavior", value: summary.structuralRead },
    { label: "Evidence focus", value: contributors },
    { label: "Confidence", value: summary.evidenceConfidence },
    { label: "Evidence replay", value: summary.replay },
    { label: "Lead Time", value: summary.leadTime },
    { label: "Preview Range", value: summary.previewRange },
  ] : [
    { label: "Replay timeline", value: DASH },
    { label: "Current Window", value: DASH },
    { label: "Change strength", value: DASH },
    { label: "Change direction", value: DASH },
    { label: "Change momentum", value: DASH },
    { label: "System behavior", value: DASH },
    { label: "Evidence focus", value: DASH },
    { label: "Confidence", value: DASH },
    { label: "Evidence replay", value: "Unavailable" },
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
  const systemIdentity = showAnalysis
    ? (latestUploadResult?.sii_intelligence?.system_identity ?? {
      profile: latestUploadResult?.sii_intelligence?.telemetry_profile ?? "unknown",
      confidence: latestUploadResult?.sii_intelligence?.telemetry_profile_confidence ?? "low",
      modality: latestUploadResult?.sii_intelligence?.telemetry_modality ?? "unknown",
      signals: latestUploadResult?.sii_intelligence?.telemetry_profile_signals ?? [],
      operational_profile: latestUploadResult?.sii_intelligence?.operational_signal_profile ?? "unknown",
      operational_confidence: latestUploadResult?.sii_intelligence?.operational_signal_profile_confidence ?? "low",
      operational_modality: latestUploadResult?.sii_intelligence?.operational_signal_modality ?? "unknown",
      operational_signals: latestUploadResult?.sii_intelligence?.operational_signal_profile_signals ?? [],
      claim_made: ["medium", "high"].includes(String(latestUploadResult?.sii_intelligence?.telemetry_profile_confidence ?? "").toLowerCase()),
    })
    : null;
  const roomConfidenceRows = showAnalysis && Array.isArray(latestUploadResult?.sii_intelligence?.rooms)
    ? latestUploadResult.sii_intelligence.rooms.map((room) => {
      const components = room?.confidence_components ?? {};
      return [
        room?.room ?? DASH,
        room?.urgency ?? DASH,
        room?.driver_category ?? DASH,
        room?.attribution_confidence ?? DASH,
        formatConfidenceComponentValue(components?.data_sufficiency),
        formatConfidenceComponentValue(components?.signal_strength),
        formatConfidenceComponentValue(components?.relationship_support),
        formatConfidenceComponentValue(components?.persistence),
      ];
    })
    : [];

  return (
    <Panel title="Evidence Details" className="span-12">
      {!showAnalysis ? (
        <EmptyState title="No active evidence session" body="Upload telemetry or resume a previous session to generate evidence replay." compact />
      ) : (
        <>
          <MetricGrid metrics={metrics} compact />
          {replayError ? <p className="narrative-text">{replayError}</p> : null}
          <Panel title="Session Context" className="span-12">
            <MetricGrid
              metrics={[
                { label: "System behavior", value: topology.topology },
                { label: "Change direction", value: topology.propagation },
                { label: "Recovery signal", value: topology.recovery },
                { label: "Confidence", value: topology.confidence },
              ]}
              compact
            />
          </Panel>
          <Panel title="Telemetry Identity" className="span-12">
            <MetricGrid
              metrics={[
                { label: "Profile", value: systemIdentity?.profile ?? DASH },
                { label: "Confidence", value: systemIdentity?.confidence ?? DASH },
                { label: "Modality", value: systemIdentity?.modality ?? DASH },
                { label: "Operational Profile", value: systemIdentity?.operational_profile ?? DASH },
                { label: "Operational Confidence", value: systemIdentity?.operational_confidence ?? DASH },
                { label: "Operational Modality", value: systemIdentity?.operational_modality ?? DASH },
                { label: "Claim Made", value: systemIdentity?.claim_made ? "Yes" : "No" },
              ]}
              compact
            />
            {Array.isArray(systemIdentity?.signals) && systemIdentity.signals.length > 0 ? (
              <DataTable
                columns={["Identity Signal"]}
                rows={systemIdentity.signals.map((signal) => [signal])}
              />
            ) : (
              <p className="narrative-text">Profile confidence is low, so the instrument is not making a telemetry-profile claim.</p>
            )}
            {Array.isArray(systemIdentity?.operational_signals) && systemIdentity.operational_signals.length > 0 ? (
              <DataTable
                columns={["Operational Signal"]}
                rows={systemIdentity.operational_signals.map((signal) => [signal])}
              />
            ) : null}
          </Panel>
          <Panel title="Per-Segment Confidence Breakdown" className="span-12">
            {roomConfidenceRows.length > 0 ? (
              <DataTable
                columns={[
                  "Segment",
                  "Urgency",
                  "Driver Category",
                  "Attribution",
                  "Data Sufficiency",
                  "Signal Strength",
                  "Relationship Support",
                  "Persistence",
                ]}
                rows={roomConfidenceRows}
              />
            ) : (
              <EmptyState
                title="No per-segment confidence data"
                body="Upload telemetry with segment-level intelligence output to view confidence components."
                compact
              />
            )}
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
            { label: "Change", value: latestUploadResult?.sii_intelligence?.urgency },
            { label: "Timestamp", value: uploadStateView.deriveTimeCoverage(latestUploadResult).summary },
            { label: "Job ID", value: activeJobId ?? DASH },
            { label: "Replay frames", value: replayFrames.length || DASH },
          ]}
          compact
        />
        <Panel title="Upload History" className="span-12">
          {uploadHistoryRows.length > 0 ? (
            <DataTable
              columns={["Result", "Status", "Score", "State", "Segment", "Delta"]}
              rows={uploadHistoryRows.map((row) => [row.filename, row.status, row.score, row.state, row.room, row.scoreDelta])}
            />
          ) : (
            <EmptyState title="No ingestion history" body="Completed uploads and evidence sessions will appear here." compact />
          )}
        </Panel>
      </details>
    </Panel>
  );
}
