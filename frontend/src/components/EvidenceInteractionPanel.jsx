import React, { useMemo, useState } from "react";
import { normalizeOperatorConfidenceLabel, sanitizeOperatorList, sanitizeOperatorText } from "../viewModels/operatorFinding";

function chipsForFrame(frame) {
  const archetypes = (frame?.active_archetypes ?? []).map((item) => ({
    id: `archetype-${item.name}`,
    label: sanitizeOperatorText(item.name.replaceAll("_", " ")),
    type: "Archetype",
    payload: item,
  }));
  const paths = (frame?.propagation_state?.dominant_paths ?? []).map((path, index) => ({
    id: `path-${index}`,
    label: sanitizeOperatorText(String(path).replaceAll("_", " ")),
    type: "Propagation Path",
    payload: { path },
  }));
  const continuation = [{
    id: "continuation",
    label: sanitizeOperatorText(frame?.continuation_window?.window ?? "Continuation window"),
    type: "Continuation Window",
    payload: frame?.continuation_window ?? {},
  }];
  const pressure = [{
    id: "pressure",
    label: sanitizeOperatorText(frame?.subsystem_pressure?.compression_intensity ?? "Compression"),
    type: "Operational Pressure",
    payload: frame?.subsystem_pressure ?? {},
  }];
  const cognition = [{
    id: "cognition",
    label: normalizeOperatorConfidenceLabel(frame?.cognition_state?.confidence_tier ?? "Cognition State"),
    type: "Cognition State",
    payload: frame?.cognition_state ?? {},
  }];
  return [...archetypes, ...paths, ...continuation, ...pressure, ...cognition];
}

export default function EvidenceInteractionPanel({ frame }) {
  const chips = useMemo(() => chipsForFrame(frame), [frame]);
  const [selectedId, setSelectedId] = useState(chips[0]?.id ?? null);
  const selected = chips.find((item) => item.id === selectedId) ?? chips[0] ?? null;
  const lineage = (frame?.evidence_state?.lineage_events ?? [])[0] ?? {};
  const sources = lineage.evidence_sources ?? {};
  const confidence = lineage.confidence_factors ?? {};

  return (
    <div className="evidence-interaction-panel">
      <div className="evidence-interaction-panel__chips">
        {chips.map((chip) => (
          <button
            type="button"
            key={chip.id}
            className={`evidence-chip ${selected?.id === chip.id ? "is-active" : ""}`}
            onClick={() => setSelectedId(chip.id)}
          >
            <span>{chip.type}</span>
            <strong>{chip.label}</strong>
          </button>
        ))}
      </div>
      <div className="evidence-interaction-panel__detail">
        <p className="evidence-lineage-panel__title">{sanitizeOperatorText(selected?.type ?? "Evidence Target")}</p>
        <p className="narrative-text">{sanitizeOperatorText(selected?.label ?? "Select an evidence item to inspect details.")}</p>
        <ul className="system-body-timeline-list">
          <li><span className="metadata-text">Corroborating Signals</span><strong>{sanitizeOperatorList((sources.supporting_signals ?? []).slice(0, 3)).join(" | ") || "n/a"}</strong></li>
          <li><span className="metadata-text">Persistence Evidence</span><strong>{sanitizeOperatorList(sources.persistence_evidence ?? []).join(" | ") || "n/a"}</strong></li>
          <li><span className="metadata-text">Historical comparison evidence</span><strong>{sanitizeOperatorList(sources.topology_evidence ?? []).join(" | ") || "n/a"}</strong></li>
          <li><span className="metadata-text">Change Support</span><strong>{sanitizeOperatorList((sources.propagation_confirmations ?? []).slice(0, 2)).join(" | ") || "n/a"}</strong></li>
          <li><span className="metadata-text">Historical Similarity</span><strong>{sanitizeOperatorText(confidence.historical_similarity ?? "n/a")}</strong></li>
          <li><span className="metadata-text">Confidence</span><strong>{normalizeOperatorConfidenceLabel(confidence.topology_support ?? "n/a")}</strong></li>
        </ul>
      </div>
    </div>
  );
}
