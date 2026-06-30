import React from "react";
import { normalizeOperatorConfidenceLabel, sanitizeOperatorList, sanitizeOperatorText } from "../viewModels/operatorFinding";

function renderLineageItem(label, value) {
  if (Array.isArray(value)) {
    return (
      <li key={label}>
        <span className="metadata-text">{label}</span>
        <strong>{value.length ? sanitizeOperatorList(value).join(" | ") : "none"}</strong>
      </li>
    );
  }
  return (
    <li key={label}>
      <span className="metadata-text">{label}</span>
      <strong>{sanitizeOperatorText(value ?? "n/a")}</strong>
    </li>
  );
}

function normalizeTier(value) {
  const normalized = String(value ?? "").toUpperCase();
  if (["LOW_EVIDENCE", "MODERATE_EVIDENCE", "HIGH_EVIDENCE", "STRONG_CONVERGENCE"].includes(normalized)) {
    return normalized;
  }
  if (normalized.includes("LOW")) return "LOW_EVIDENCE";
  if (normalized.includes("HIGH")) return "HIGH_EVIDENCE";
  if (normalized.includes("STRONG")) return "STRONG_CONVERGENCE";
  return "MODERATE_EVIDENCE";
}

export default function EvidenceLineagePanel({ frame, lineage = null }) {
  const lineageEvents = lineage?.lineages ?? frame?.evidence_state?.lineage_events ?? [];
  const first = lineageEvents[0] ?? null;
  if (!first) {
    return <p className="narrative-text">Evidence details are initializing.</p>;
  }
  const confidence = first.confidence_factors ?? {};
  const sources = first.evidence_sources ?? {};
  const confidenceTier = normalizeTier(confidence.confidence_tier ?? confidence.evidence_density ?? confidence.corroboration_strength);
  return (
    <div className="evidence-lineage-panel">
      <p className="evidence-lineage-panel__title">{sanitizeOperatorText(first.target ?? "Evidence Target")}</p>
      <ul className="system-body-timeline-list">
        {renderLineageItem("Contributing relationships", sources.supporting_signals ?? [])}
        {renderLineageItem("Subsystem corroboration", sources.subsystem_corroboration ?? [])}
        {renderLineageItem("Historical comparison evidence", sources.topology_evidence ?? [])}
        {renderLineageItem("Persistence", sources.persistence_evidence ?? [])}
        {renderLineageItem("Change support", sources.propagation_evidence ?? [])}
        {renderLineageItem("Historical evidence", sources.historical_memory_references ?? [])}
        {renderLineageItem("Behavior evidence", sources.replay_support ?? [])}
        {renderLineageItem("Confidence basis", confidence.corroboration_strength ?? confidence.evidence_density)}
        {renderLineageItem("Confidence", normalizeOperatorConfidenceLabel(confidenceTier))}
      </ul>
    </div>
  );
}
