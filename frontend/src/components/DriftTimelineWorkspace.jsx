function formatSigned(value) {
  const rounded = Number(value ?? 0).toFixed(3);
  return `${Number(rounded) >= 0 ? "+" : ""}${rounded}`;
}

export default function DriftTimelineWorkspace({ liveOps, driftHistory }) {
  const history = driftHistory?.length ? driftHistory : [{ stamp: "now", distance: 0, velocity: 0, acceleration: 0 }];
  const last = history[history.length - 1];
  const scale = Math.max(...history.map((item) => item.distance), 0.01);
  const points = history.map((item, idx) => {
    const x = history.length === 1 ? 0 : (idx / (history.length - 1)) * 620;
    const y = 120 - (item.distance / scale) * 100;
    return `${x},${y}`;
  }).join(" ");

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
      </article>
    </section>
  );
}
