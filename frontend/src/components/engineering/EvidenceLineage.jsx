import React from "react";

const VALUE_CLASSES = {
  measured: "Measured",
  derived: "Derived",
  inferred: "Inferred",
  configured: "Configured",
  human: "Human-entered",
};

function LineageStep({ label, value, classification = "inferred", detail }) {
  if (!value && !detail) return null;
  return (
    <details className="evidence-lineage__step">
      <summary><span className={`evidence-value-type evidence-value-type--${classification}`}>{VALUE_CLASSES[classification] ?? VALUE_CLASSES.inferred}</span><strong>{label}</strong><span>{value || "Available"}</span></summary>
      <div><p>{detail || value}</p></div>
    </details>
  );
}

export default function EvidenceLineage({ finding, relationship, result = {} }) {
  const observation = finding?.supporting?.[0] || finding?.observedChange;
  const normalization = result?.normalization ?? result?.normalization_summary;
  const drift = relationship?.delta === null || relationship?.delta === undefined ? null : `Relationship change ${relationship.delta}`;
  return (
    <div className="evidence-lineage" aria-label="Evidence reasoning lineage">
      <LineageStep label="Raw observation" value={observation} classification="measured" detail="The observation persisted with the evidence record; source values remain governed by the configured data policy." />
      <LineageStep label="Normalization" value={typeof normalization === "string" ? normalization : normalization?.summary || "Configured source normalization"} classification="configured" detail={typeof normalization === "object" ? normalization?.method : "Normalization metadata was not supplied beyond the configured processing boundary."} />
      <LineageStep label="Relationship inferred" value={relationship?.label || "No supported relationship selected"} classification="inferred" detail={relationship ? `Baseline ${relationship.baseline ?? "not supplied"}; current ${relationship.current ?? "not supplied"}.` : "Select a mapped relationship to inspect its comparison."} />
      <LineageStep label="Drift vector" value={drift || "Magnitude not supplied"} classification="derived" detail={relationship ? `Edge state: ${relationship.state}. Numerical values remain secondary to the bounded interpretation.` : "A drift vector cannot be shown without mapped relationship evidence."} />
      {finding?.engineeringPrior ? <LineageStep label="Engineering prior" value={typeof finding.engineeringPrior === "string" ? finding.engineeringPrior : finding.engineeringPrior?.label || "Conditional prior applied"} classification="configured" detail="This prior contributes conditionally and is not a universal diagnostic rule." /> : null}
      <LineageStep label="Interpretation" value={finding?.whyItMatters} classification="inferred" />
      <LineageStep label="Conclusion" value={finding?.title} classification="inferred" detail={`Conclusion is bounded to the ${finding?.tier ?? "Withheld"} confidence tier.`} />
      {finding?.outcome ? <LineageStep label="Engineer outcome" value={finding.outcome?.outcome || finding.outcome?.category} classification="human" detail={finding.outcome?.note} /> : null}
    </div>
  );
}
