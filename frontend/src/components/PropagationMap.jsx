import React from "react";

function clamp(value) {
  return Math.max(0, Math.min(1, Number(value) || 0));
}

export default function PropagationMap({ frame }) {
  const nodes = frame?.topology_state ? [
    { id: "origin", label: "Structural Origin", pressure: frame.subsystem_pressure?.pressure_score ?? 0.2 },
    { id: "topology", label: "Topology Drift", pressure: frame.topology_state?.drift_index ?? 0.2 },
    { id: "propagation", label: "Propagation", pressure: frame.propagation_state?.activation_intensity ?? 0.2 },
    { id: "cognition", label: "Cognition State", pressure: frame.subsystem_pressure?.volatility_index ?? 0.2 },
  ] : [];

  const paths = frame?.propagation_state?.dominant_paths ?? [];

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
