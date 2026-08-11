import React from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";

function text(value, fallback = "Not recorded") {
  return String(value ?? "").trim() || fallback;
}

function label(value, fallback) {
  const clean = text(value, fallback);
  return clean.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function FindingConfidenceStrip({ finding }) {
  const dimensions = finding?.confidenceDimensions ?? {};
  const hasDimensions = Boolean(dimensions.changeDetection || dimensions.interpretation || dimensions.operatingContext);
  const persistence = finding?.classificationPresentation?.persistence?.label
    ?? (finding?.persistence?.persistent ? "Persistent" : finding?.persistence?.status);
  const context = dimensions.operatingContext?.level
    ? `${label(finding?.operatingMode?.match, "Context")} / ${label(dimensions.operatingContext.level)}`
    : "Not recorded";
  if (!hasDimensions) {
    return <aside className="finding-confidence-strip finding-confidence-strip--legacy" aria-label="Legacy confidence"><div><span>Legacy confidence</span><ConfidenceTierChip tier={finding?.tier ?? "Withheld"} /></div></aside>;
  }
  return (
    <aside className="finding-confidence-strip" aria-label="Independent finding confidence">
      <div><span>Change</span><strong>{label(dimensions.changeDetection?.level, "Not recorded")}</strong></div>
      <div><span>Interpretation</span><strong>{label(dimensions.interpretation?.level, "Not recorded")}</strong></div>
      <div><span>Persistence</span><strong>{label(persistence, "Not established")}</strong></div>
      <div><span>Context</span><strong>{context}</strong></div>
    </aside>
  );
}
