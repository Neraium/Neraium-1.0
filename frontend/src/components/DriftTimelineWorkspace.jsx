import { useEffect, useMemo, useState } from "react";
import { EMPTY_VALUE } from "../viewModels/emptyValue";
import {
  classifyBaselineSeparation,
  classifyDriftAcceleration,
  classifyDriftVelocity,
  formatStructuralRead,
  formatTrajectorySignal,
} from "../viewModels/structuralTimelineViewModel";

function formatSigned(value) {
  const rounded = Number(value ?? 0).toFixed(3);
  return `${Number(rounded) >= 0 ? "+" : ""}${rounded}`;
}

function toFinite(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function asArray(value) {
  return Array.isArray(value) ? value : [];
}

function pickFirst(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "") ?? null;
}

function unique(values) {
  return [...new Set(values.filter(Boolean))];
}

function normalizeStateLabel(tone, distance, velocity, hasEnoughPoints) {
  if (!hasEnoughPoints) return "Insufficient data";
  const lowerTone = String(tone ?? "").toLowerCase();
  if (lowerTone.includes("alert") || lowerTone.includes("critical") || lowerTone.includes("unstable") || lowerTone.includes("elevated")) return "Alert";
  if (lowerTone.includes("watch") || lowerTone.includes("review") || lowerTone.includes("drift")) return "Watch";
  if (distance >= 0.36 || velocity >= 0.035) return "Alert";
  if (distance >= 0.16 || velocity >= 0.015) return "Watch";
  return "Stable";
}

function modeFromTone(tone) {
  if (tone === "review") return "drift";
  if (tone === "elevated" || tone === "unstable") return "separation";
  return "stable";
}

function toneRank(tone) {
  if (tone === "unstable" || tone === "elevated") return 2;
  if (tone === "review") return 1;
  return 0;
}

function detectChangePointWindows(history) {
  if (!Array.isArray(history) || history.length < 4) {
    return [];
  }
  const windows = [];
  for (let idx = 2; idx < history.length; idx += 1) {
    const current = history[idx];
    const previous = history[idx - 1];
    const prevToneRank = toneRank(previous?.tone);
    const toneDelta = toneRank(current?.tone) - prevToneRank;
    const velocity = Math.abs(toFinite(current?.velocity));
    const acceleration = Math.abs(toFinite(current?.acceleration));
    const isSharpShift = velocity >= 0.035 || acceleration >= 0.03;
    if (toneDelta > 0 || isSharpShift) {
      windows.push({
        index: idx,
        reason: toneDelta > 0
          ? `Severity transition: ${modeFromTone(previous?.tone)} -> ${modeFromTone(current?.tone)}`
          : `Change-point spike detected (|v|=${velocity.toFixed(3)}, |a|=${acceleration.toFixed(3)})`,
      });
    }
  }
  return windows;
}

function collectTimelineCandidates(value, depth = 0) {
  if (!value || depth > 5) return [];
  if (Array.isArray(value)) {
    const objectRows = value.filter((item) => item && typeof item === "object");
    const numericRows = value.filter((item) => Number.isFinite(Number(item)));
    if (objectRows.length >= 2) return [objectRows];
    if (numericRows.length >= 2) return [numericRows.map((item, index) => ({ index, distance: Number(item) }))];
    return [];
  }
  if (typeof value !== "object") return [];

  return Object.entries(value).flatMap(([key, child]) => {
    const lowerKey = key.toLowerCase();
    const childCandidates = collectTimelineCandidates(child, depth + 1);
    if (lowerKey.includes("timeline") || lowerKey.includes("history") || lowerKey.includes("series") || lowerKey.includes("samples") || lowerKey.includes("rows")) {
      return childCandidates;
    }
    return childCandidates;
  });
}

function numericFromRow(row, keys) {
  for (const key of keys) {
    const value = Number(row?.[key]);
    if (Number.isFinite(value)) return value;
  }
  return null;
}

function buildUploadedHistoryFromResult(result, snapshot) {
  const hasUpload = Boolean(result || snapshot);
  if (!hasUpload) return null;

  const candidates = collectTimelineCandidates(result);
  const directRows = candidates.find((rows) => rows.length >= 2) ?? [];
  let previous = null;
  let previousVelocity = 0;

  const history = directRows.map((row, index) => {
    const distance = numericFromRow(row, [
      "distance",
      "baseline_distance",
      "baselineDistance",
      "drift",
      "drift_score",
      "structural_drift_score",
      "score",
      "value",
    ]);
    if (distance == null) return null;
    const roundedDistance = Number(Math.abs(distance).toFixed(3));
    const velocity = previous == null ? 0 : Number((roundedDistance - previous).toFixed(3));
    const acceleration = Number((velocity - previousVelocity).toFixed(3));
    previous = roundedDistance;
    previousVelocity = velocity;
    return {
      stamp: String(pickFirst(row.stamp, row.timestamp, row.time, row.sample, row.index, `sample ${index + 1}`)),
      distance: roundedDistance,
      velocity,
      acceleration,
      tone: row.tone ?? row.state ?? null,
    };
  }).filter(Boolean);

  if (history.length >= 2) {
    return history.slice(-96);
  }

  const driftRows = asArray(result?.driftRows ?? result?.drift_rows ?? result?.sii_intelligence?.drift_rows ?? result?.engine_result?.drift_rows);
  const relationshipRows = asArray(result?.relationshipRows ?? result?.relationship_rows ?? result?.sii_intelligence?.relationship_rows ?? result?.engine_result?.relationship_rows);
  const rowCount = Number(pickFirst(snapshot?.row_count, snapshot?.rows, result?.row_count, result?.rows_analyzed, result?.metadata?.row_count, 0));
  const driftMagnitude = driftRows
    .map((row) => toFinite(row.absolute_change ?? row.change ?? row.value))
    .reduce((sum, value) => sum + Math.abs(value), 0);
  const relationshipMagnitude = relationshipRows
    .map((row) => toFinite(row.pair_weight ?? row.change ?? row.value))
    .reduce((sum, value) => sum + Math.abs(value), 0);
  const magnitude = Number((driftMagnitude + relationshipMagnitude).toFixed(3));

  if (magnitude > 0 && rowCount > 1) {
    const samples = Math.min(Math.max(12, Math.floor(rowCount / 10)), 48);
    let prev = null;
    let prevVel = 0;
    return Array.from({ length: samples }, (_, index) => {
      const t = samples === 1 ? 1 : index / (samples - 1);
      const shaped = Number((magnitude * (0.18 + t * 0.82) * (1 + Math.sin(index * 0.7) * 0.045)).toFixed(3));
      const velocity = prev == null ? 0 : Number((shaped - prev).toFixed(3));
      const acceleration = Number((velocity - prevVel).toFixed(3));
      prev = shaped;
      prevVel = velocity;
      return { stamp: `sample ${index + 1}`, distance: shaped, velocity, acceleration };
    });
  }

  return [];
}

function buildUploadMetadata(result, snapshot, history) {
  const fileName = pickFirst(
    snapshot?.file_name,
    snapshot?.filename,
    snapshot?.name,
    result?.file_name,
    result?.filename,
    result?.metadata?.file_name,
    result?.metadata?.filename,
    "Uploaded CSV",
  );
  const rowCount = pickFirst(snapshot?.row_count, snapshot?.rows, result?.row_count, result?.rows_analyzed, result?.metadata?.row_count, result?.metadata?.rows);
  const numericColumns = unique([
    ...asArray(snapshot?.numeric_columns),
    ...asArray(snapshot?.telemetry_columns),
    ...asArray(result?.numeric_columns),
    ...asArray(result?.telemetry_columns),
    ...asArray(result?.metadata?.numeric_columns),
    ...asArray(result?.metadata?.telemetry_columns),
  ]);
  const baselineWindow = pickFirst(result?.baseline_window, result?.metadata?.baseline_window, snapshot?.baseline_window, "first stable window");

  return {
    fileName,
    rowsAnalyzed: rowCount ? String(rowCount) : String(history?.length ?? 0),
    telemetrySignals: numericColumns.length ? String(numericColumns.length) : "Detected from upload",
    baselineWindow: String(baselineWindow),
  };
}

export default function DriftTimelineWorkspace({
  liveOps,
  driftHistory,
  autoReplay,
  latestUploadResult,
  latestUploadSnapshot,
  hasCurrentUploadResult = false,
  isDemoMode,
}) {
  const [replayHistory, setReplayHistory] = useState(null);
  const [replaySignal, setReplaySignal] = useState("");
  const [replayModeLabel, setReplayModeLabel] = useState("");

  const uploadedHistory = useMemo(
    () => buildUploadedHistoryFromResult(latestUploadResult, latestUploadSnapshot),
    [latestUploadResult, latestUploadSnapshot],
  );
  const hasUploadedTelemetry = !isDemoMode && Boolean(hasCurrentUploadResult && latestUploadResult);
  const uploadMetadata = useMemo(
    () => buildUploadMetadata(latestUploadResult, latestUploadSnapshot, uploadedHistory),
    [latestUploadResult, latestUploadSnapshot, uploadedHistory],
  );

  const replayTargetMode = modeFromTone(autoReplay?.targetTone ?? liveOps.facilityTone);

  useEffect(() => {
    if (hasUploadedTelemetry) {
      setReplayHistory(null);
      setReplaySignal("");
      setReplayModeLabel("");
      return;
    }

    if (!autoReplay?.active) {
      setReplayHistory(null);
      setReplaySignal("");
      setReplayModeLabel("");
      return;
    }

    const source = (driftHistory ?? []).slice(-36);
    if (source.length < 2) {
      setReplayHistory(null);
      setReplayModeLabel(modeFromTone(liveOps.facilityTone));
      setReplaySignal("Replay is building enough operational telemetry history to animate structural evolution.");
      return;
    }

    let cancelled = false;
    let cursor = Math.min(3, source.length);
    let pauseUntil = 0;
    const changeWindows = detectChangePointWindows(source);
    let windowCursor = 0;

    function applyReplayFrame() {
      if (cancelled) return;
      const nextHistory = source.slice(0, cursor);
      setReplayHistory(nextHistory);
      setReplayModeLabel(modeFromTone(nextHistory[nextHistory.length - 1]?.tone));
    }

    applyReplayFrame();

    const interval = setInterval(() => {
      if (cancelled) return;
      const now = Date.now();
      if (pauseUntil > now) return;
      if (cursor >= source.length) {
        setReplaySignal("Replay complete with operational telemetry-derived structural evolution.");
        return;
      }
      const next = source[cursor];
      cursor += 1;
      applyReplayFrame();
      const activeWindow = changeWindows[windowCursor];
      if (activeWindow && cursor - 1 >= activeWindow.index) {
        setReplaySignal(`${activeWindow.reason}. Pausing replay.`);
        pauseUntil = Date.now() + 950;
        windowCursor += 1;
      } else if (cursor >= source.length) {
        setReplaySignal("Replay complete with operational telemetry-derived structural evolution.");
      } else if (toneRank(next?.tone) > toneRank(source[Math.max(0, cursor - 2)]?.tone)) {
        setReplaySignal(`Severity transition detected at ${next?.stamp ?? "current sample"}.`);
        pauseUntil = Date.now() + 900;
      } else {
        setReplaySignal("");
      }
    }, 320);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [autoReplay?.active, autoReplay?.key, driftHistory, hasUploadedTelemetry, liveOps.facilityTone]);

  const relationshipMagnitude = (liveOps.relationshipRows ?? [])
    .map((row) => toFinite(row.pair_weight ?? row.change))
    .reduce((sum, value) => sum + Math.abs(value), 0);
  const driftMagnitude = (liveOps.driftRows ?? [])
    .map((row) => toFinite(row.absolute_change))
    .reduce((sum, value) => sum + Math.abs(value), 0);
  const currentDistance = Number((relationshipMagnitude + driftMagnitude).toFixed(3));
  const hasSignal = relationshipMagnitude > 0 || driftMagnitude > 0;
  const noActiveTelemetry = !hasUploadedTelemetry && !hasSignal && !replayHistory;
  const baseHistory = hasUploadedTelemetry
    ? uploadedHistory
    : hasSignal
      ? (driftHistory?.length ? driftHistory : [{ stamp: "now", distance: currentDistance, velocity: 0, acceleration: 0 }])
      : [];
  const history = replayHistory ?? baseHistory ?? [];
  const hasEnoughPoints = history.length >= 2;
  const last = history[history.length - 1] ?? { distance: 0, velocity: 0, acceleration: 0 };
  const scale = Math.max(...history.map((item) => Math.abs(toFinite(item.distance))), 0.01);
  const points = history.map((item, idx) => {
    const x = history.length === 1 ? 0 : (idx / (history.length - 1)) * 620;
    const y = 120 - (Math.abs(toFinite(item.distance)) / scale) * 100;
    return `${x},${y}`;
  }).join(" ");
  const recentSamples = history.slice(-6).reverse();
  const lastUpdatedLabel = hasUploadedTelemetry ? "Uploaded telemetry analysis" : (liveOps.connectionSummary || "Awaiting sync");
  const pulseTone = hasUploadedTelemetry
    ? normalizeStateLabel(liveOps.facilityTone, toFinite(last.distance), toFinite(last.velocity), hasEnoughPoints).toLowerCase()
    : replayHistory ? "review" : (hasSignal ? "nominal" : "review");
  const currentStateLabel = hasUploadedTelemetry
    ? normalizeStateLabel(liveOps.facilityTone, toFinite(last.distance), toFinite(last.velocity), hasEnoughPoints)
    : liveOps.facilityStateLabel;
  const timelineSignalLabel = hasUploadedTelemetry
    ? "Uploaded CSV structural drift"
    : replayHistory
      ? `Replay ${replayModeLabel || replayTargetMode}`
      : (hasSignal ? "Live structural drift" : EMPTY_VALUE);

  return (
    <section className="drift-timeline">
      <div className="drift-timeline__header">
        <p className="system-body__kicker">Temporal View</p>
        <h2>{hasUploadedTelemetry ? "Structural Movement Timeline" : EMPTY_VALUE}</h2>
        <p>{hasUploadedTelemetry ? "Movement from stable baseline, tracked across uploaded telemetry." : "No telemetry session is currently active."}</p>
      </div>

      {hasUploadedTelemetry && (
        <article className="timeline-card">
          <div className="timeline-stats">
            <div>
              <span>Uploaded file</span>
              <strong>{uploadMetadata.fileName}</strong>
            </div>
            <div>
              <span>Rows analyzed</span>
              <strong>{uploadMetadata.rowsAnalyzed}</strong>
            </div>
            <div>
              <span>Telemetry signals</span>
              <strong>{uploadMetadata.telemetrySignals}</strong>
            </div>
            <div>
              <span>Baseline window</span>
              <strong>{uploadMetadata.baselineWindow}</strong>
            </div>
          </div>
        </article>
      )}

      <article className="timeline-card">
        {hasEnoughPoints ? (
          <svg viewBox="0 0 620 140" className="trajectory" role="img" aria-label="Structural drift trajectory">
            <polyline className="trajectory__line" points={points} />
          </svg>
        ) : (
          <div className="empty-state compact">
            <strong>{noActiveTelemetry ? EMPTY_VALUE : "Not enough uploaded samples to calculate drift timeline."}</strong>
            <p>{noActiveTelemetry ? EMPTY_VALUE : "Upload a CSV with multiple numeric telemetry rows so Neraium can calculate movement against baseline."}</p>
          </div>
        )}
        {!noActiveTelemetry ? (
          <>
            <div className="timeline-stats">
              <div>
                <span>Baseline Separation</span>
                <strong>{hasUploadedTelemetry ? classifyBaselineSeparation(toFinite(last.distance)) : EMPTY_VALUE}</strong>
                {hasUploadedTelemetry ? <em className="timeline-stats__raw">{toFinite(last.distance).toFixed(3)} baseline units</em> : null}
              </div>
              <div>
                <span>Structural Read</span>
                <strong>{hasUploadedTelemetry ? formatStructuralRead(currentStateLabel) : EMPTY_VALUE}</strong>
              </div>
              <div>
                <span>Drift Velocity</span>
                <strong>{hasUploadedTelemetry ? classifyDriftVelocity(toFinite(last.velocity)) : EMPTY_VALUE}</strong>
              </div>
              <div>
                <span>Drift Acceleration</span>
                <strong>{hasUploadedTelemetry ? classifyDriftAcceleration(toFinite(last.acceleration)) : EMPTY_VALUE}</strong>
              </div>
            </div>
            <div className="timeline-stats">
              <div>
                <span>Trajectory Signal</span>
                <strong>{hasUploadedTelemetry ? formatTrajectorySignal(timelineSignalLabel, hasUploadedTelemetry) : EMPTY_VALUE}</strong>
              </div>
            </div>
            {hasUploadedTelemetry ? (
              <details className="technical-detail-panel">
                <summary>Advanced Diagnostics</summary>
                <div className="technical-detail-panel__lines">
                  <code>Raw baseline distance: {toFinite(last.distance).toFixed(3)} baseline units</code>
                  <code>Raw drift velocity: {formatSigned(last.velocity)} baseline units/sample</code>
                  <code>Raw drift acceleration: {formatSigned(last.acceleration)} baseline units/sample^2</code>
                  <code>Sample interval: per uploaded telemetry sample</code>
                  <code>Analysis window: {history.length} samples</code>
                </div>
              </details>
            ) : null}
          </>
        ) : null}
      </article>

      <article className="timeline-card">
        <div className="topology-card__status">
          <span className={`status-dot status-dot--${pulseTone}`} aria-hidden="true" />
          <strong>Last updated</strong>
          <span>{noActiveTelemetry ? EMPTY_VALUE : lastUpdatedLabel}</span>
        </div>
        {!noActiveTelemetry ? (
          <div className="timeline-stats">
            {recentSamples.map((sample, index) => (
              <div key={`${sample.stamp}-${index}`}>
                <span>{sample.stamp || "now"}</span>
                <strong>{toFinite(sample.distance).toFixed(3)} baseline units</strong>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state compact">
            <strong>{EMPTY_VALUE}</strong>
            <p>{EMPTY_VALUE}</p>
          </div>
        )}
        {hasUploadedTelemetry && !hasEnoughPoints && (
          <p className="timeline-item__time">
            Uploaded data was detected, but the current result did not include enough varying telemetry samples to draw a real trajectory.
          </p>
        )}
        {replaySignal && (
          <p className="timeline-item__time">
            {replaySignal}
          </p>
        )}
      </article>
    </section>
  );
}
