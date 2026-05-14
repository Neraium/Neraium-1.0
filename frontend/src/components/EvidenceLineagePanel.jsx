import React from "react";

function renderLineageItem(label, value) {
  if (Array.isArray(value)) {
    return (
      <li key={label}>
        <span className="metadata-text">{label}</span>
        <strong>{value.length ? value.join(" | ") : "none"}</strong>
      </li>
    );
  }
  return (
    <li key={label}>
      <span className="metadata-text">{label}</span>
      <strong>{value ?? "n/a"}</strong>
    </li>
  );
}

export default function EvidenceLineagePanel({ frame }) {
  const lineageEvents = frame?.evidence_state?.lineage_events ?? [];
  const first = lineageEvents[0] ?? null;
  if (!first) {
    return <p className="narrative-text">Evidence lineage is initializing.</p>;
  }
  const confidence = first.confidence_factors ?? {};
  const sources = first.evidence_sources ?? {};
  return (
    <div className="evidence-lineage-panel">
      <p className="evidence-lineage-panel__title">{first.target ?? "Lineage Target"}</p>
      <ul className="system-body-timeline-list">
        {renderLineageItem("Signals", sources.supporting_signals ?? [])}
        {renderLineageItem("Persistence", sources.persistence_evidence ?? [])}
        {renderLineageItem("Topology", sources.topology_evidence ?? [])}
        {renderLineageItem("Memory", sources.historical_memory_references ?? [])}
        {renderLineageItem("Corroboration", confidence.corroboration_strength)}
        {renderLineageItem("Evidence Density", confidence.evidence_density)}
      </ul>
    </div>
  );
}
