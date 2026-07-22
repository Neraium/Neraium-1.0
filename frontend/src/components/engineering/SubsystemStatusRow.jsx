import React from "react";
import ConfidenceTierChip from "./ConfidenceTierChip";

export default function SubsystemStatusRow({ subsystem, onSelect }) {
  return (
    <button type="button" className="subsystem-status-row" onClick={onSelect} disabled={!onSelect}>
      <span className="subsystem-status-row__name">{subsystem.name}</span>
      <span className={`subsystem-state subsystem-state--${subsystem.state.toLowerCase().replace(/\s+/g, "-")}`}>{subsystem.state}</span>
      <span>{subsystem.findingCount} {subsystem.findingCount === 1 ? "finding" : "findings"}</span>
      <span className="subsystem-status-row__explanation">{subsystem.explanation}</span>
      <span className="subsystem-status-row__evidence">Evidence <ConfidenceTierChip tier={subsystem.evidenceTier} /></span>
    </button>
  );
}
