import React from "react";
function text(value, fallback = "Not recorded") {
  return String(value ?? "").trim() || fallback;
}

function label(value, fallback) {
  const clean = text(value, fallback);
  return clean.replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function FindingConfidenceStrip({ finding }) {
  const dimensions = finding?.confidenceDimensions ?? {};
  const changeLevel = dimensions.changeDetection?.level ?? finding?.confidence ?? finding?.tier;
  return (
    <aside className="finding-confidence-strip" aria-label="Change confidence">
      <div><span>Change confidence</span><strong>{label(changeLevel, "Not recorded")}</strong></div>
    </aside>
  );
}
