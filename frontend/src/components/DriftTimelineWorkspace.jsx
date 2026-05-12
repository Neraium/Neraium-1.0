import { useEffect, useState } from "react";

function formatSigned(value) {
  const rounded = Number(value ?? 0).toFixed(3);
  return `${Number(rounded) >= 0 ? "+" : ""}${rounded}`;
}

function toFinite(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function buildSimulatedHistory(mode, phase = 0) {
  const samples = 24;
  const points = [];
  let previous = null;
  let previousVelocity = 0;

  for (let idx = 0; idx < samples; idx += 1) {
    const t = idx / (samples - 1);
    const p = phase * 0.18;
    let distance;

    if (mode === "stable") {
      distance = 0.075 + Math.sin(idx * 0.55 + p) * 0.012 + Math.cos(idx * 0.18 + p * 0.5) * 0.006;
    } else if (mode === "drift") {
      distance = 0.11 + t * 0.17 + Math.sin(idx * 0.5 + p) * 0.022;
    } else {
      distance = 0.18 + t * t * 0.62 + Math.sin(idx * 0.72 + p) * 0.03;
    }

    const roundedDistance = Number(distance.toFixed(3));
    const velocity = previous == null ? 0 : Number((roundedDistance - previous).toFixed(3));
    const acceleration = Number((velocity - previousVelocity).toFixed(3));

    points.push({
      stamp: `t-${samples - 1 - idx}`,
      distance: roundedDistance,
      velocity,
      acceleration,
    });

    previous = roundedDistance;
    previousVelocity = velocity;
  }

  return points;
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

export default function DriftTimelineWorkspace({ liveOps, driftHistory, autoReplay }) {
  const [simTick, setSimTick] = useState(0);
  const [replayHistory, setReplayHistory] = useState(null);
  const [replaySignal, setReplaySignal] = useState("");
  const [replayModeLabel, setReplayModeLabel] = useState("");

  useEffect(() => {
    const timer = setInterval(() => setSimTick((value) => value + 1), 1200);
    return () => clearInterval(timer);
  }, []);

  const replayTargetMode = modeFromTone(autoReplay?.targetTone ?? liveOps.facilityTone);

  useEffect(() => {
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
      setReplaySignal("Replay waiting for enough CSV-derived telemetry history.");
      return;
    }

    let cancelled = false;
    let cursor = Math.min(3, source.length);
    let pauseUntil = 0;
    const changeWindows = detectChangePointWindows(source);
    let windowCursor = 0;

    function applyReplayFrame() {
      if (cancelled) {
        return;
      }
      const nextHistory = source.slice(0, cursor);
      setReplayHistory(nextHistory);
      setReplayModeLabel(modeFromTone(nextHistory[nextHistory.length - 1]?.tone));
    }

    applyReplayFrame();

    const interval = setInterval(() => {
      if (cancelled) {
        return;
      }

      const now = Date.now();
      if (pauseUntil > now) {
        return;
      }

      if (cursor >= source.length) {
        setReplaySignal("Replay complete (CSV-derived).");
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
        setReplaySignal("Replay complete (CSV-derived).");
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
  }, [autoReplay?.active, autoReplay?.key, driftHistory, liveOps.facilityTone]);

  const relationshipMagnitude = (liveOps.relationshipRows ?? [])
    .map((row) => toFinite(row.pair_weight ?? row.change))
    .reduce((sum, value) => sum + Math.abs(value), 0);
  const driftMagnitude = (liveOps.driftRows ?? [])
    .map((row) => toFinite(row.absolute_change))
    .reduce((sum, value) => sum + Math.abs(value), 0);
  const currentDistance = Number((relationshipMagnitude + driftMagnitude).toFixed(3));
  const hasSignal = relationshipMagnitude > 0 || driftMagnitude > 0;
  const simulatedMode = modeFromTone(liveOps.facilityTone);
  const simulatedHistory = buildSimulatedHistory(simulatedMode, simTick);
  const baseHistory = hasSignal
    ? (driftHistory?.length
      ? driftHistory
      : [{ stamp: "now", distance: currentDistance, velocity: 0, acceleration: 0 }])
    : simulatedHistory;
  const history = replayHistory ?? baseHistory;
  const last = history[history.length - 1];
  const scale = Math.max(...history.map((item) => Math.abs(toFinite(item.distance))), 0.01);
  const points = history.map((item, idx) => {
    const x = history.length === 1 ? 0 : (idx / (history.length - 1)) * 620;
    const y = 120 - (Math.abs(toFinite(item.distance)) / scale) * 100;
    return `${x},${y}`;
  }).join(" ");
  const recentSamples = history.slice(-6).reverse();
  const lastUpdatedLabel = liveOps.connectionSummary || "Awaiting sync";
  const pulseTone = replayHistory ? "review" : (hasSignal ? "nominal" : "review");
  const timelineSignalLabel = replayHistory
    ? `Replay ${replayModeLabel || replayTargetMode} (CSV)`
    : (hasSignal ? "Live" : `Simulated ${simulatedMode}`);

  return (
    <section className="drift-timeline">
      <div className="drift-timeline__header">
        <p className="system-body__kicker">Temporal View</p>
        <h2>Drift Timeline</h2>
        <p>Distance from stable baseline, tracked as trajectory not isolated metrics.</p>
      </div>

      <article className="timeline-card">
        <svg viewBox="0 0 620 140" className="trajectory" role="img" aria-label="Structural drift trajectory">
          <polyline className="trajectory__line" points={points} />
        </svg>
        <div className="timeline-stats">
          <div>
            <span>Baseline distance</span>
            <strong>{toFinite(last.distance).toFixed(3)} baseline units</strong>
          </div>
          <div>
            <span>Current state</span>
            <strong>{liveOps.facilityStateLabel}</strong>
          </div>
          <div>
            <span>Rate of change</span>
            <strong>{formatSigned(last.velocity)} baseline units/sample</strong>
          </div>
          <div>
            <span>Change in rate</span>
            <strong>{formatSigned(last.acceleration)} baseline units/sample^2</strong>
          </div>
        </div>
        <div className="timeline-stats">
          <div>
            <span>Timeline signal</span>
            <strong>{timelineSignalLabel}</strong>
          </div>
        </div>
      </article>

      <article className="timeline-card">
        <div className="topology-card__status">
          <span className={`status-dot status-dot--${pulseTone}`} aria-hidden="true" />
          <strong>Last updated</strong>
          <span>{lastUpdatedLabel}</span>
        </div>
        <div className="timeline-stats">
          {recentSamples.map((sample, index) => (
            <div key={`${sample.stamp}-${index}`}>
              <span>{sample.stamp || "now"}</span>
              <strong>{toFinite(sample.distance).toFixed(3)} baseline units</strong>
            </div>
          ))}
        </div>
        {!hasSignal && !replayHistory && (
          <p className="timeline-item__time">
            Simulated trajectory is shown while telemetry is unavailable. Upload telemetry or run demo mode for live behavior.
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
