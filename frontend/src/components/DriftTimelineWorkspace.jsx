function formatSigned(value) {
  const rounded = Number(value ?? 0).toFixed(3);
  return `${Number(rounded) >= 0 ? "+" : ""}${rounded}`;
}

function toFinite(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
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
  const history = driftHistory?.length
    ? driftHistory
    : [{ stamp: "now", distance: currentDistance, velocity: 0, acceleration: 0 }];
  const last = history[history.length - 1];
  const scale = Math.max(...history.map((item) => Math.abs(toFinite(item.distance))), 0.01);
  const points = history.map((item, idx) => {
    const x = history.length === 1 ? 0 : (idx / (history.length - 1)) * 620;
    const y = 120 - (Math.abs(toFinite(item.distance)) / scale) * 100;
    return `${x},${y}`;
  }).join(" ");
  const recentSamples = history.slice(-6).reverse();

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
            <span>Velocity</span>
            <strong>{formatSigned(last.velocity)} sigma/step</strong>
          </div>
          <div>
            <span>Acceleration</span>
            <strong>{formatSigned(last.acceleration)} sigma/step^2</strong>
          </div>
        </div>
        <div className="timeline-stats">
          <div>
            <span>Timeline signal</span>
            <strong>{hasSignal ? "Live" : "Waiting for upload"}</strong>
          </div>
        </div>
      </article>

      <article className="timeline-card">
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
            Upload telemetry in Data Connections to populate drift trajectory.
          </p>
        )}
      </article>
    </section>
  );
}
