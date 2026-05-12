function formatSigned(value) {
  const rounded = Number(value ?? 0).toFixed(3);
  return `${Number(rounded) >= 0 ? "+" : ""}${rounded}`;
}

function toFinite(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function buildSimulatedHistory(mode) {
  const samples = 24;
  const points = [];
  let previous = null;
  let previousVelocity = 0;

  for (let idx = 0; idx < samples; idx += 1) {
    const t = idx / (samples - 1);
    let distance;

    if (mode === "stable") {
      distance = 0.075 + Math.sin(idx * 0.55) * 0.012 + Math.cos(idx * 0.18) * 0.006;
    } else if (mode === "drift") {
      distance = 0.11 + t * 0.17 + Math.sin(idx * 0.5) * 0.022;
    } else {
      distance = 0.18 + t * t * 0.62 + Math.sin(idx * 0.72) * 0.03;
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

export default function DriftTimelineWorkspace({ liveOps, driftHistory }) {
  const relationshipMagnitude = (liveOps.relationshipRows ?? [])
    .map((row) => toFinite(row.pair_weight ?? row.change))
    .reduce((sum, value) => sum + Math.abs(value), 0);
  const driftMagnitude = (liveOps.driftRows ?? [])
    .map((row) => toFinite(row.absolute_change))
    .reduce((sum, value) => sum + Math.abs(value), 0);
  const currentDistance = Number((relationshipMagnitude + driftMagnitude).toFixed(3));
  const hasSignal = relationshipMagnitude > 0 || driftMagnitude > 0;
  const simulatedMode = liveOps.facilityTone === "nominal"
    ? "stable"
    : liveOps.facilityTone === "review"
      ? "drift"
      : liveOps.facilityTone === "elevated" || liveOps.facilityTone === "unstable"
        ? "separation"
        : "stable";
  const simulatedHistory = buildSimulatedHistory(simulatedMode);
  const history = hasSignal
    ? (driftHistory?.length
      ? driftHistory
      : [{ stamp: "now", distance: currentDistance, velocity: 0, acceleration: 0 }])
    : simulatedHistory;
  const last = history[history.length - 1];
  const scale = Math.max(...history.map((item) => Math.abs(toFinite(item.distance))), 0.01);
  const points = history.map((item, idx) => {
    const x = history.length === 1 ? 0 : (idx / (history.length - 1)) * 620;
    const y = 120 - (Math.abs(toFinite(item.distance)) / scale) * 100;
    return `${x},${y}`;
  }).join(" ");
  const recentSamples = history.slice(-6).reverse();
  const lastUpdatedLabel = liveOps.connectionSummary || "Awaiting sync";
  const pulseTone = hasSignal ? "nominal" : "review";

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
            <strong>{toFinite(last.distance).toFixed(3)} sigma</strong>
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
            <strong>{hasSignal ? "Live" : `Simulated ${simulatedMode}`}</strong>
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
              <strong>{toFinite(sample.distance).toFixed(3)} sigma</strong>
            </div>
          ))}
        </div>
        {!hasSignal && (
          <p className="timeline-item__time">
            Simulated trajectory is shown while telemetry is unavailable. Upload telemetry or run demo mode for live behavior.
          </p>
        )}
      </article>
    </section>
  );
}
