import React from "react";

const EDGE_LABELS = {
  stable: "Stable learned relationship",
  weakening: "Weakening or drifting relationship",
  emerging: "Emerging relationship",
  insufficient: "Insufficient evidence",
  historical: "Historical-only relationship",
};

function nodeByLabel(nodes, label) {
  return nodes.find((node) => node.id === label || node.label === label);
}

export default function RelationshipGraph({ nodes = [], relationships = [], selectedId = null, timeLabel, onSelect }) {
  const selected = relationships.find((item) => item.id === selectedId) ?? nodes.find((item) => item.id === selectedId) ?? null;
  const relatedNodeIds = selected?.source ? new Set([selected.source, selected.target]) : selected?.id ? new Set(relationships.filter((edge) => edge.source === selected.id || edge.target === selected.id).flatMap((edge) => [edge.source, edge.target])) : new Set();
  const isDimmed = (id) => selected && id !== selected.id && !relatedNodeIds.has(id);
  if (!relationships.length && !nodes.length) {
    return <div className="relationship-graph relationship-graph--empty" role="img" aria-label="Relationship graph unavailable"><p>No mapped relationship evidence is available for this investigation.</p></div>;
  }
  return (
    <section className="relationship-graph" aria-labelledby="relationship-graph-title">
      <header><div><span className="forensic-kicker">Relationship field</span><h2 id="relationship-graph-title">Behavioral constellation</h2></div><span className="relationship-graph__time" aria-live="polite">{timeLabel}</span></header>
      <div className="relationship-graph__canvas">
        <svg viewBox="0 0 100 74" role="img" aria-label={`Relationship graph with ${nodes.length} nodes and ${relationships.length} relationships`}>
          <defs><filter id="selection-halo"><feGaussianBlur stdDeviation="1.2" /></filter></defs>
          {relationships.map((edge) => {
            const source = nodeByLabel(nodes, edge.source);
            const target = nodeByLabel(nodes, edge.target);
            if (!source || !target) return null;
            const active = selectedId === edge.id;
            const dimmed = selected && !active && selected.id !== edge.source && selected.id !== edge.target;
            return <g key={edge.id} className={`graph-edge graph-edge--${edge.state}${active ? " is-selected" : ""}${dimmed ? " is-dimmed" : ""}`}>
              {active ? <line className="graph-edge__halo" x1={source.x} y1={source.y} x2={target.x} y2={target.y} /> : null}
              <line x1={source.x} y1={source.y} x2={target.x} y2={target.y}>
                <title>{`${edge.label}: ${EDGE_LABELS[edge.state] ?? edge.state}`}</title>
              </line>
              <button type="button" aria-label={`Select ${edge.label}, ${EDGE_LABELS[edge.state] ?? edge.state}`} onClick={() => onSelect?.(edge)}>
                <circle cx={(source.x + target.x) / 2} cy={(source.y + target.y) / 2} r="4" fill="transparent" />
              </button>
            </g>;
          })}
          {nodes.map((node) => {
            const active = selectedId === node.id;
            return <g key={node.id} className={`graph-node${active ? " is-selected" : ""}${isDimmed(node.id) ? " is-dimmed" : ""}`} transform={`translate(${node.x} ${node.y})`}>
              {active ? <circle className="graph-node__halo" r="5.2" /> : null}
              <circle r="2.7" />
              <text y="6">{node.label.length > 22 ? `${node.label.slice(0, 20)}…` : node.label}</text>
              <button type="button" aria-label={`Select ${node.label}`} onClick={() => onSelect?.(node)}><circle r="5" fill="transparent" /></button>
            </g>;
          })}
        </svg>
      </div>
      <div className="relationship-legend" aria-label="Relationship graph legend">
        {Object.entries(EDGE_LABELS).map(([state, label]) => <span key={state}><i className={`legend-edge legend-edge--${state}`} aria-hidden="true" />{label}</span>)}
      </div>
      <details className="graph-alternative">
        <summary>View relationship table</summary>
        <div className="forensic-table-wrap"><table><caption>Text alternative for the relationship graph</caption><thead><tr><th>Relationship</th><th>State</th><th>Baseline</th><th>Current</th><th>Action</th></tr></thead><tbody>
          {relationships.map((edge) => <tr key={edge.id}><td>{edge.label}</td><td>{EDGE_LABELS[edge.state] ?? edge.state}</td><td>{edge.baseline ?? "Not supplied"}</td><td>{edge.current ?? "Not supplied"}</td><td><button type="button" onClick={() => onSelect?.(edge)}>Inspect evidence</button></td></tr>)}
        </tbody></table></div>
      </details>
    </section>
  );
}
