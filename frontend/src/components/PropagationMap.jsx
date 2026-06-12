import React from "react";

function clamp(value) {
  return Math.max(0, Math.min(1, Number(value) || 0));
}

export default function PropagationMap({ frame, comparisonFrame = null }) {
  const nodes = frame?.topology_state ? [
    { id: "origin", label: "Structural Origin", pressure: frame.subsystem_pressure?.pressure_score ?? 0.2 },
    { id: "topology", label: "Relationship Shift", pressure: frame.topology_state?.drift_index ?? 0.2 },
    { id: "propagation", label: "Propagation", pressure: frame.propagation_state?.activation_intensity ?? 0.2 },
    { id: "cognition", label: "Cognition State", pressure: frame.subsystem_pressure?.volatility_index ?? 0.2 },
  ] : [];

  const paths = frame?.propagation_state?.dominant_paths ?? [];
  const comparisonPressure = comparisonFrame?.subsystem_pressure?.pressure_score ?? null;
  const delta = comparisonPressure == null
    ? null
    : (Number(frame?.subsystem_pressure?.pressure_score ?? 0) - Number(comparisonPressure)).toFixed(3);

  return (
    <div className="propagation-map">
      <div className="propagation-map__graph">
        {nodes.map((node) => (
          <div
            key={node.id}
            className="propagation-map__node"
            style={{ "--pressure": clamp(node.pressure) }}
          >
            <span className="propagation-map__node-label">{node.label}</span>
            <span className="propagation-map__node-value">{Math.round(clamp(node.pressure) * 100)}%</span>
          </div>
        ))}
      </div>
      {delta !== null ? (
        <p className="metadata-text">
          Comparison delta (pressure score): {delta > 0 ? "+" : ""}{delta}
        </p>
      ) : null}
      <div className="propagation-map__paths">
        {(paths.length ? paths : ["Propagation path not yet isolated"]).map((path) => (
          <div key={path} className="propagation-map__path">
            <span className="propagation-map__pulse" />
            <span>{String(path).replaceAll("_", " ")}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
