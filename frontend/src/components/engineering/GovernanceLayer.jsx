import React from "react";
const GovernanceAudit = React.lazy(() => import("./GovernanceAudit"));

// Display persisted backend fields; scores and local review state are not inputs.
export default function GovernanceLayer({ governance, audit, compact }) {
  const [open, setOpen] = React.useState(false);
  if (!governance || governance.schema_version !== "runtime-governance-v1") return null;
  if (compact) return <p className="operational-finding__compact-limit">Evidence maturity: {governance.maturity_label || "Unavailable"} · {governance.authority_label || "Authority unavailable"}</p>;
  const fields = [["Evidence maturity", governance.maturity_label], ["Context", governance.context_label], ["Authority", governance.authority_label]];
  if (governance.lifecycle) fields.push(["Lifecycle", governance.lifecycle.state.replaceAll("_", " ")]);
  if (governance.adaptation) fields.push(["Model adaptation", `${governance.adaptation.label}. ${governance.adaptation.reason}`]);
  return <section aria-label="Evidence governance">
    <dl className="classification-detail-grid">
      {fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value || "Unavailable"}</dd></div>)}
    </dl>
    {audit ? <details onToggle={event => setOpen(event.currentTarget.open)}><summary>Governance audit</summary>
      {open ? <React.Suspense fallback={null}><GovernanceAudit governance={governance} /></React.Suspense> : null}
    </details> : null}
  </section>;
}
