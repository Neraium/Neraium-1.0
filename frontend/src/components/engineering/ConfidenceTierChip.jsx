import React from "react";

const DEFINITIONS = {
  Confirmed: "Complete, consistent evidence and applicable system context strongly support this conclusion.",
  Qualified: "Evidence supports the conclusion, with stated limitations or assumptions.",
  Narrowed: "Evidence supports only a less-specific conclusion.",
  Deferred: "Required evidence is delayed or incomplete; more data may resolve the question.",
  Withheld: "Evidence is insufficient, contradictory, or outside supported scope.",
};

export default function ConfidenceTierChip({ tier = "Withheld", showDefinition = false }) {
  const normalized = DEFINITIONS[tier] ? tier : "Withheld";
  return (
    <span className={`confidence-tier confidence-tier--${normalized.toLowerCase()}`} title={DEFINITIONS[normalized]} aria-label={`Confidence: ${normalized}. ${DEFINITIONS[normalized]}`}>
      <span className="confidence-tier__mark" aria-hidden="true" />
      {normalized}
      {showDefinition ? <span className="confidence-tier__definition">{DEFINITIONS[normalized]}</span> : null}
    </span>
  );
}

export { DEFINITIONS as CONFIDENCE_TIER_DEFINITIONS };
